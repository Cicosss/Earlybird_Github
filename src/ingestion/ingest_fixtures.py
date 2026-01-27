import requests
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Tuple
from src.database.models import Match as MatchModel, TeamAlias, SessionLocal
from config.settings import ODDS_API_KEY, MATCH_LOOKAHEAD_HOURS
from src.ingestion.league_manager import (
    get_active_niche_leagues, 
    get_leagues_for_cycle,
    get_elite_leagues,
    is_elite_league,
    MAX_LEAGUES_PER_RUN
)
from sqlalchemy import func

# ============================================
# MARKET INTELLIGENCE (Odds Snapshot Tracking)
# ============================================
try:
    from src.analysis.market_intelligence import save_odds_snapshot, init_market_intelligence_db
    _MARKET_INTEL_AVAILABLE = True
except ImportError:
    _MARKET_INTEL_AVAILABLE = False
    logging.debug("Market Intelligence module not available - snapshots disabled")

BASE_URL = "https://api.the-odds-api.com/v4/sports"

# Reusable session for connection pooling (faster API calls)
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Get or create reusable requests session for connection pooling."""
    global _session
    if _session is None:
        _session = requests.Session()
    return _session

# ============================================
# SMART FREQUENCY & REGION OPTIMIZATION
# ============================================
# Maximize 20k API credits with intelligent scheduling

# Region mapping by league (cost optimization)
LEAGUE_REGIONS: Dict[str, str] = {
    # Europe: eu,uk
    "soccer_turkey_super_league": "eu,uk",
    "soccer_greece_super_league": "eu,uk",
    "soccer_spl": "eu,uk",
    # Americas: us,eu
    "soccer_argentina_primera_division": "us,eu",
    "soccer_mexico_ligamx": "us",
    "soccer_brazil_serie_b": "us,eu",
    # Oceania/Asia: au or au,eu
    "soccer_australia_aleague": "au",
    "soccer_china_superleague": "au,eu",
    "soccer_japan_j_league": "au,eu",
}

# Frequency thresholds (hours)
HIGH_ALERT_THRESHOLD = 24  # Match within 24h -> update every 1h
MAINTENANCE_FREQUENCY = 6  # Match > 24h away -> update every 6h


def get_optimized_regions(sport_key: str) -> str:
    """
    Get optimized regions for a league to minimize API cost.
    Only fetches from relevant bookmaker regions.
    """
    return LEAGUE_REGIONS.get(sport_key, "eu,uk")


def should_update_league(db, sport_key: str) -> Tuple[bool, str, Optional[float]]:
    """
    SMART FREQUENCY: Determine if a league needs updating based on match proximity.
    
    Rules:
    - Match < 24h away: HIGH ALERT - update every 1 hour
    - Match > 24h away: MAINTENANCE - update every 6 hours
    - No matches: SKIP
    
    V6.1: Robust timezone handling - all comparisons done in UTC-aware datetimes.
    
    Args:
        db: Database session
        sport_key: League key
        
    Returns:
        Tuple of (should_update, reason, hours_to_next_match)
    """
    now = datetime.now(timezone.utc)
    
    # Find the soonest upcoming match for this league
    # V6.1: Query all matches and filter in Python for timezone safety
    all_matches = db.query(MatchModel).filter(
        MatchModel.league == sport_key
    ).order_by(MatchModel.start_time.asc()).all()
    
    # Filter to future matches with proper timezone handling
    next_match = None
    for match in all_matches:
        match_time = match.start_time
        # Ensure timezone-aware for comparison
        if match_time.tzinfo is None:
            match_time = match_time.replace(tzinfo=timezone.utc)
        if match_time > now:
            next_match = match
            break
    
    if not next_match:
        # No upcoming matches - still fetch to discover new ones
        return True, "NO_MATCHES_DISCOVERY", None
    
    # Ensure both datetimes are comparable (handle naive vs aware)
    match_time = next_match.start_time
    if match_time.tzinfo is None:
        match_time = match_time.replace(tzinfo=timezone.utc)
    hours_to_match = (match_time - now).total_seconds() / 3600
    
    # Check last update time for this league
    last_updated = db.query(func.max(MatchModel.last_updated)).filter(
        MatchModel.league == sport_key
    ).scalar()
    
    if not last_updated:
        return True, "FIRST_FETCH", hours_to_match
    
    # Ensure last_updated is timezone-aware for comparison
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)
    hours_since_update = (now - last_updated).total_seconds() / 3600
    
    # HIGH ALERT: Match within 24h
    if hours_to_match < HIGH_ALERT_THRESHOLD:
        if hours_since_update >= 1:
            return True, f"HIGH_ALERT ({hours_to_match:.1f}h to match)", hours_to_match
        else:
            return False, f"HIGH_ALERT_FRESH (updated {hours_since_update:.1f}h ago)", hours_to_match
    
    # MAINTENANCE: Match > 24h away
    if hours_since_update >= MAINTENANCE_FREQUENCY:
        return True, f"MAINTENANCE ({hours_to_match:.1f}h to match)", hours_to_match
    else:
        return False, f"MAINTENANCE_FRESH (updated {hours_since_update:.1f}h ago)", hours_to_match

def clean_team_name(name: str) -> str:
    """
    Removes common suffixes to create a better search term.
    """
    ignore_terms = [" FC", " SK", " Club", " AS", " AC", " FK", " SC", " Calcio", " Spor"]
    clean = name
    for term in ignore_terms:
        clean = clean.replace(term, "")
    return clean.strip()

def extract_h2h_odds(bookmakers_data: list, home_team: str = None, away_team: str = None) -> tuple:
    """
    Extract Home, Draw, and Away odds from bookmakers data.
    Returns (home_odd, draw_odd, away_odd) or (None, None, None) if not found.
    
    BISCOTTO STRATEGY: Now captures Draw odds for anomaly detection.
    """
    if not bookmakers_data:
        return None, None, None
    
    # Take first bookmaker's h2h market
    for bookmaker in bookmakers_data:
        markets = bookmaker.get('markets', [])
        for market in markets:
            if market.get('key') == 'h2h':
                outcomes = market.get('outcomes', [])
                home_odd = None
                draw_odd = None
                away_odd = None
                
                # Parse outcomes by name
                for outcome in outcomes:
                    name = outcome.get('name', '')
                    price = outcome.get('price')
                    
                    if price:
                        if name == 'Draw':
                            draw_odd = float(price)
                        elif home_team and name == home_team:
                            home_odd = float(price)
                        elif away_team and name == away_team:
                            away_odd = float(price)
                
                # Fallback: if names didn't match, use position
                if home_odd is None or away_odd is None:
                    if len(outcomes) >= 3:
                        # 3-way market: Home, Draw, Away
                        home_odd = float(outcomes[0].get('price', 0)) if outcomes[0].get('price') else None
                        draw_odd = float(outcomes[1].get('price', 0)) if outcomes[1].get('price') else None
                        away_odd = float(outcomes[2].get('price', 0)) if outcomes[2].get('price') else None
                    elif len(outcomes) >= 2:
                        # 2-way market (no draw)
                        home_odd = float(outcomes[0].get('price', 0)) if outcomes[0].get('price') else None
                        away_odd = float(outcomes[1].get('price', 0)) if outcomes[1].get('price') else None
                
                return home_odd, draw_odd, away_odd
    
    return None, None, None


def extract_totals_odds(bookmakers_data: list) -> Tuple[Optional[float], Optional[float]]:
    """
    Extract Over/Under 2.5 goals odds from bookmakers data.
    Returns (over_2_5, under_2_5) or (None, None) if not found.
    """
    if not bookmakers_data:
        return None, None
    
    for bookmaker in bookmakers_data:
        markets = bookmaker.get('markets', [])
        for market in markets:
            if market.get('key') == 'totals':
                outcomes = market.get('outcomes', [])
                over_odd = None
                under_odd = None
                
                for outcome in outcomes:
                    name = outcome.get('name', '')
                    point = outcome.get('point')
                    price = outcome.get('price')
                    
                    # Look for 2.5 line specifically
                    if point == 2.5 and price:
                        if name == 'Over':
                            over_odd = float(price)
                        elif name == 'Under':
                            under_odd = float(price)
                
                if over_odd and under_odd:
                    return over_odd, under_odd
    
    return None, None


# ============================================
# LAYER 3: SHARP vs SOFT ODDS DETECTION
# ============================================

# Sharp bookmakers (professional/syndicate money)
SHARP_BOOKIES = ['pinnacle', 'betfair_ex_eu', 'betfair_ex_uk', 'betfair', '1xbet', 'matchbook']

def extract_sharp_odds_analysis(bookmakers_data: list, home_team: str = None, away_team: str = None) -> dict:
    """
    LAYER 3: SHARP vs SOFT ODDS ANALYSIS
    
    Detects "Smart Money" by comparing sharp bookmaker odds vs average.
    
    ROBUST LOGIC:
    1. Try to find a Sharp Bookie (Pinnacle, Betfair, etc.)
    2. If NOT found, use MINIMUM odd as "Sharp Proxy" (smart money sits at lowest price)
    3. Calculate sharp_diff = (Average - Sharp)
    4. If sharp_diff > 0.10 -> Signal: "Sharp Drop"
    
    Args:
        bookmakers_data: List of bookmaker data from Odds API
        home_team: Home team name
        away_team: Away team name
        
    Returns:
        Dict with sharp analysis for home/draw/away
    """
    result = {
        "sharp_bookie": None,
        "sharp_home": None,
        "sharp_draw": None,
        "sharp_away": None,
        "avg_home": None,
        "avg_draw": None,
        "avg_away": None,
        "min_home": None,
        "min_draw": None,
        "min_away": None,
        "home_signal": None,
        "draw_signal": None,
        "away_signal": None,
        "is_sharp_drop": False,
        "sharp_diff": 0,
        "analysis": "No data"
    }
    
    if not bookmakers_data:
        return result
    
    # Collect all odds by outcome
    home_odds = []
    draw_odds = []
    away_odds = []
    
    sharp_home = None
    sharp_draw = None
    sharp_away = None
    sharp_bookie_found = None
    
    for bookmaker in bookmakers_data:
        bookie_key = bookmaker.get('key', '').lower()
        markets = bookmaker.get('markets', [])
        
        for market in markets:
            if market.get('key') != 'h2h':
                continue
                
            outcomes = market.get('outcomes', [])
            
            # Parse outcomes
            h_odd, d_odd, a_odd = None, None, None
            
            for outcome in outcomes:
                name = outcome.get('name', '')
                price = outcome.get('price')
                
                if price:
                    if name == 'Draw':
                        d_odd = float(price)
                    elif home_team and name == home_team:
                        h_odd = float(price)
                    elif away_team and name == away_team:
                        a_odd = float(price)
            
            # Fallback by position
            if (h_odd is None or a_odd is None) and len(outcomes) >= 3:
                h_odd = float(outcomes[0].get('price', 0)) if outcomes[0].get('price') else None
                d_odd = float(outcomes[1].get('price', 0)) if outcomes[1].get('price') else None
                a_odd = float(outcomes[2].get('price', 0)) if outcomes[2].get('price') else None
            
            # Collect for averaging
            if h_odd:
                home_odds.append(h_odd)
            if d_odd:
                draw_odds.append(d_odd)
            if a_odd:
                away_odds.append(a_odd)
            
            # Check if this is a sharp bookie
            if bookie_key in SHARP_BOOKIES and not sharp_bookie_found:
                sharp_bookie_found = bookie_key
                sharp_home = h_odd
                sharp_draw = d_odd
                sharp_away = a_odd
    
    # Calculate averages and minimums
    if home_odds:
        result["avg_home"] = round(sum(home_odds) / len(home_odds), 2)
        result["min_home"] = min(home_odds)
    if draw_odds:
        result["avg_draw"] = round(sum(draw_odds) / len(draw_odds), 2)
        result["min_draw"] = min(draw_odds)
    if away_odds:
        result["avg_away"] = round(sum(away_odds) / len(away_odds), 2)
        result["min_away"] = min(away_odds)
    
    # Use sharp bookie if found, otherwise use minimum as proxy
    if sharp_bookie_found:
        result["sharp_bookie"] = sharp_bookie_found
        result["sharp_home"] = sharp_home
        result["sharp_draw"] = sharp_draw
        result["sharp_away"] = sharp_away
        logging.info(f"📊 Sharp bookie found: {sharp_bookie_found}")
    else:
        # FALLBACK: Use minimum odds as sharp proxy
        result["sharp_bookie"] = "min_proxy"
        result["sharp_home"] = result["min_home"]
        result["sharp_draw"] = result["min_draw"]
        result["sharp_away"] = result["min_away"]
        logging.debug(f"📊 No sharp bookie - using minimum odds as proxy")
    
    # Calculate sharp differences and signals
    signals = []
    
    if result["sharp_home"] and result["avg_home"]:
        diff = result["avg_home"] - result["sharp_home"]
        if diff > 0.10:
            result["home_signal"] = f"SHARP DROP: Sharp {result['sharp_home']:.2f} vs Avg {result['avg_home']:.2f} (diff: {diff:.2f})"
            signals.append(("HOME", diff))
            result["is_sharp_drop"] = True
    
    if result["sharp_draw"] and result["avg_draw"]:
        diff = result["avg_draw"] - result["sharp_draw"]
        if diff > 0.10:
            result["draw_signal"] = f"SHARP DROP: Sharp {result['sharp_draw']:.2f} vs Avg {result['avg_draw']:.2f} (diff: {diff:.2f})"
            signals.append(("DRAW", diff))
            result["is_sharp_drop"] = True
    
    if result["sharp_away"] and result["avg_away"]:
        diff = result["avg_away"] - result["sharp_away"]
        if diff > 0.10:
            result["away_signal"] = f"SHARP DROP: Sharp {result['sharp_away']:.2f} vs Avg {result['avg_away']:.2f} (diff: {diff:.2f})"
            signals.append(("AWAY", diff))
            result["is_sharp_drop"] = True
    
    # Build analysis summary
    if signals:
        biggest = max(signals, key=lambda x: x[1])
        result["sharp_diff"] = biggest[1]
        result["analysis"] = f"🎯 SMART MONEY on {biggest[0]} (diff: {biggest[1]:.2f})"
    else:
        result["analysis"] = "No significant sharp movement detected"
    
    return result

def update_team_aliases(matches):
    """
    Ensures all teams in the fetched matches have an alias entry.
    """
    db = SessionLocal()
    processed_teams = set()  # Track teams already added in this session
    try:
        for m in matches:
            for team_name in [m.home_team, m.away_team]:
                if team_name in processed_teams:
                    continue
                existing = db.query(TeamAlias).filter(TeamAlias.api_name == team_name).first()
                if not existing:
                    clean_name = clean_team_name(team_name)
                    logging.info(f"Creating Alias: {team_name} -> {clean_name}")
                    alias = TeamAlias(api_name=team_name, search_name=clean_name)
                    db.add(alias)
                processed_teams.add(team_name)
        db.commit()
    except Exception as e:
        logging.error(f"Error updating aliases: {e}")
        db.rollback()
    finally:
        db.close()

def check_quota_status() -> dict:
    """
    Check current API quota from response headers.
    Returns dict with 'remaining' and 'emergency_mode' flag.
    """
    try:
        url = f"{BASE_URL.replace('/sports', '')}/sports"
        params = {"apiKey": ODDS_API_KEY}
        response = _get_session().get(url, params=params, timeout=10)
        
        remaining = response.headers.get("x-requests-remaining", "500")
        try:
            # Handle both "500" and "20000.0" formats
            remaining_int = int(float(remaining))
        except Exception as e:
            logging.error(f"Handled error in check_quota_status (parsing remaining): {e}")
            remaining_int = 500
        
        return {
            "remaining": remaining_int,
            "used": response.headers.get("x-requests-used", "0"),
            "emergency_mode": remaining_int < 50
        }
    except Exception as e:
        logging.warning(f"⚠️ Could not check quota: {e}")
        return {"remaining": 500, "used": "unknown", "emergency_mode": False}


def ingest_fixtures(use_auto_discovery: bool = True, force_all: bool = False):
    """
    Fetches upcoming fixtures with odds and saves them to the DB.
    
    SMART FREQUENCY STRATEGY:
    - Match < 24h: HIGH ALERT - update every 1 hour
    - Match > 24h: MAINTENANCE - update every 6 hours
    - Region optimization per league to save API credits
    
    CRITICAL LOGIC:
    - NEW Match: Save odds to BOTH opening_* AND current_*
    - EXISTING Match: Update ONLY current_*, preserve opening_*
    
    Args:
        use_auto_discovery: If True, use Elite 6 strategy. If False, use config.
        force_all: If True, bypass Smart Frequency and fetch all leagues.
    """
    logging.info("🚀 Starting Fixture Ingestion - Smart Frequency Strategy...")
    
    if ODDS_API_KEY == "YOUR_ODDS_API_KEY" or not ODDS_API_KEY:
        if os.getenv("USE_MOCK_DATA") == "true":
             logging.warning("Odds API Key not set (or MOCK flag). Using MOCK data.")
             from src.mocks import MOCK_MATCHES
             logging.warning("Mock mode enabled but odds tracking requires real API.")
             return
        logging.error("❌ ODDS_API_KEY not configured!")
        return

    # Check quota status
    quota = check_quota_status()
    logging.info(f"💰 API Quota: {quota['remaining']} remaining (used: {quota['used']})")
    
    if quota['emergency_mode']:
        logging.warning(f"🚨 LOW QUOTA WARNING: Only {quota['remaining']} calls remaining!")
    
    # Get Elite 6 leagues
    if use_auto_discovery:
        leagues_to_process = get_active_niche_leagues()
        logging.info(f"🎯 Elite 6 Strategy: {len(leagues_to_process)} leagues available")
    else:
        from src.ingestion.league_manager import ELITE_LEAGUES
        leagues_to_process = ELITE_LEAGUES[:MAX_LEAGUES_PER_RUN]
        logging.info(f"📋 Using Elite leagues fallback: {len(leagues_to_process)}")

    if not leagues_to_process:
        logging.warning("⚠️ No leagues to process!")
        return

    db = SessionLocal()
    now = datetime.now(timezone.utc)
    min_time = now + timedelta(hours=2)
    max_time = now + timedelta(hours=96)  # Extended to 4 days for early odds tracking
    
    matches_processed = 0
    leagues_processed = 0
    leagues_skipped = 0
    processed_teams = set()
    
    try:
        for sport_key in leagues_to_process:
            # ============================================
            # SMART FREQUENCY: Check if update needed
            # ============================================
            if not force_all:
                should_update, reason, hours_to_match = should_update_league(db, sport_key)
                
                if not should_update:
                    leagues_skipped += 1
                    logging.info(f"⏭️ SKIP {sport_key}: {reason}")
                    continue
                
                logging.info(f"📊 {sport_key}: {reason}")
            
            try:
                url = f"{BASE_URL}/{sport_key}/odds"
                
                # REGION OPTIMIZATION: Use league-specific regions
                regions = get_optimized_regions(sport_key)
                logging.info(f"🌎 Fetching {sport_key} with regions={regions}")
                
                params = {
                    "apiKey": ODDS_API_KEY,
                    "regions": regions,
                    "markets": "h2h,totals",  # Now fetching totals for Over/Under
                    "dateFormat": "iso",
                    "oddsFormat": "decimal"
                }
                
                response = _get_session().get(url, params=params, timeout=30)
                if response.status_code != 200:
                    logging.error(f"API Error {response.status_code}: {response.text}")
                    continue

                data = response.json()
                
                # Verbose logging for raw API response
                logging.debug(f"League {sport_key} returned {len(data)} raw matches from API.")
                
                for event in data:
                    # SAFETY: Skip malformed events (missing required fields)
                    if not all(k in event for k in ('id', 'commence_time', 'home_team', 'away_team')):
                        logging.warning(f"⚠️ Skipping malformed event in {sport_key}: missing required fields")
                        continue
                    
                    # Parse commence_time and ensure it's timezone-aware (UTC)
                    commence_time_str = event['commence_time']
                    if commence_time_str.endswith('Z'):
                        commence_time_str = commence_time_str.replace('Z', '+00:00')
                    commence_time = datetime.fromisoformat(commence_time_str)
                    # Ensure timezone-aware for comparison
                    if commence_time.tzinfo is None:
                        commence_time = commence_time.replace(tzinfo=timezone.utc)
                    
                    # HARD-BLOCK: Skip historical matches (Ghost Match Prevention)
                    if commence_time < now:
                        logging.debug(f"Skipping past match: {event.get('home_team')} vs {event.get('away_team')} (started {commence_time})")
                        continue
                    
                    # Filter by time window (both are now timezone-aware)
                    if not (min_time <= commence_time <= max_time):
                        continue
                    
                    match_id = event['id']
                    home_team = event['home_team']
                    away_team = event['away_team']
                    
                    # Convert to naive datetime for DB storage (remove timezone)
                    commence_time_naive = commence_time.replace(tzinfo=None)
                    
                    # Extract odds (H2H + Totals)
                    bookmakers = event.get('bookmakers', [])
                    home_odd, draw_odd, away_odd = extract_h2h_odds(bookmakers, home_team, away_team)
                    over_2_5, under_2_5 = extract_totals_odds(bookmakers)
                    
                    # LAYER 3: Sharp odds analysis
                    sharp_analysis = extract_sharp_odds_analysis(bookmakers, home_team, away_team)
                    
                    if sharp_analysis.get('is_sharp_drop'):
                        logging.info(f"🎯 {sharp_analysis['analysis']} for {home_team} vs {away_team}")
                    
                    # Check if match exists
                    existing = db.query(MatchModel).filter(MatchModel.id == match_id).first()
                    
                    if existing:
                        # UPDATE: Only update current odds, preserve opening
                        if home_odd is not None:
                            existing.current_home_odd = home_odd
                        if draw_odd is not None:
                            existing.current_draw_odd = draw_odd
                        if away_odd is not None:
                            existing.current_away_odd = away_odd
                        
                        # Update totals (current only)
                        if over_2_5 is not None:
                            existing.current_over_2_5 = over_2_5
                        if under_2_5 is not None:
                            existing.current_under_2_5 = under_2_5
                        
                        # Update sharp odds analysis
                        existing.sharp_bookie = sharp_analysis.get('sharp_bookie')
                        existing.sharp_home_odd = sharp_analysis.get('sharp_home')
                        existing.sharp_draw_odd = sharp_analysis.get('sharp_draw')
                        existing.sharp_away_odd = sharp_analysis.get('sharp_away')
                        existing.avg_home_odd = sharp_analysis.get('avg_home')
                        existing.avg_draw_odd = sharp_analysis.get('avg_draw')
                        existing.avg_away_odd = sharp_analysis.get('avg_away')
                        existing.is_sharp_drop = sharp_analysis.get('is_sharp_drop', False)
                        existing.sharp_signal = sharp_analysis.get('analysis')
                        
                        existing.last_updated = datetime.now(timezone.utc)
                        
                        # MARKET INTELLIGENCE: Save odds snapshot for time-based analysis
                        if _MARKET_INTEL_AVAILABLE:
                            save_odds_snapshot(
                                match_id=match_id,
                                home_odd=home_odd,
                                draw_odd=draw_odd,
                                away_odd=away_odd,
                                sharp_home_odd=sharp_analysis.get('sharp_home'),
                                sharp_draw_odd=sharp_analysis.get('sharp_draw'),
                                sharp_away_odd=sharp_analysis.get('sharp_away'),
                                sharp_bookie=sharp_analysis.get('sharp_bookie')
                            )
                        
                        logging.debug(f"Updated: {home_team} vs {away_team} | O/U: {over_2_5}/{under_2_5}")
                    else:
                        # NEW MATCH: Set BOTH opening and current odds
                        new_match = MatchModel(
                            id=match_id,
                            league=sport_key,
                            home_team=home_team,
                            away_team=away_team,
                            start_time=commence_time_naive,
                            # H2H Opening
                            opening_home_odd=home_odd,
                            opening_away_odd=away_odd,
                            opening_draw_odd=draw_odd,
                            # H2H Current
                            current_home_odd=home_odd,
                            current_away_odd=away_odd,
                            current_draw_odd=draw_odd,
                            # Totals Opening
                            opening_over_2_5=over_2_5,
                            opening_under_2_5=under_2_5,
                            # Totals Current
                            current_over_2_5=over_2_5,
                            current_under_2_5=under_2_5,
                            # LAYER 3: Sharp odds
                            sharp_bookie=sharp_analysis.get('sharp_bookie'),
                            sharp_home_odd=sharp_analysis.get('sharp_home'),
                            sharp_draw_odd=sharp_analysis.get('sharp_draw'),
                            sharp_away_odd=sharp_analysis.get('sharp_away'),
                            avg_home_odd=sharp_analysis.get('avg_home'),
                            avg_draw_odd=sharp_analysis.get('avg_draw'),
                            avg_away_odd=sharp_analysis.get('avg_away'),
                            is_sharp_drop=sharp_analysis.get('is_sharp_drop', False),
                            sharp_signal=sharp_analysis.get('analysis'),
                            last_updated=datetime.now(timezone.utc)
                        )
                        db.add(new_match)
                        logging.info(f"New: {home_team} vs {away_team} | H{home_odd}/X{draw_odd}/A{away_odd} | O{over_2_5}/U{under_2_5}")
                        
                        # Create aliases
                        for team_name in [home_team, away_team]:
                            if team_name not in processed_teams:
                                if not db.query(TeamAlias).filter(TeamAlias.api_name == team_name).first():
                                    clean_name = clean_team_name(team_name)
                                    alias = TeamAlias(api_name=team_name, search_name=clean_name)
                                    db.add(alias)
                                processed_teams.add(team_name)
                    
                    matches_processed += 1
                
                leagues_processed += 1
                logging.info(f"✅ {sport_key}: {matches_processed} matches")
                        
            except Exception as e:
                logging.error(f"Error fetching data for {sport_key}: {e}")
        
        db.commit()
        logging.info(f"🏁 Ingestion complete: {matches_processed} matches | {leagues_processed} fetched | {leagues_skipped} skipped (fresh)")
        
    except Exception as e:
        logging.error(f"Critical error in ingestion: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # Setup simple logging if run directly
    logging.basicConfig(level=logging.INFO)
    ingest_fixtures()
