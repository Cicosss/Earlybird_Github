"""
Bet Settler Module for EarlyBird
Checks match results and calculates ROI for sent alerts.

Fetches final scores from FotMob and settles pending bets.
Updates the database with actual outcomes for learning.

V4.2: Added CLV (Closing Line Value) calculation for edge validation.
"""
import logging
import re
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import and_
from sqlalchemy.orm import joinedload

from src.database.models import Match, NewsLog
from src.database.db import get_db_context
from src.ingestion.data_provider import get_data_provider
from config.settings import SETTLEMENT_MIN_SCORE

logger = logging.getLogger(__name__)

# Result status constants
RESULT_WIN = "WIN"
RESULT_LOSS = "LOSS"
RESULT_PUSH = "PUSH"  # Void/cancelled
RESULT_PENDING = "PENDING"


def _tavily_post_match_search(home_team: str, away_team: str, match_date: datetime) -> Optional[str]:
    """
    V7.0: Use Tavily to search for post-match reports and insights.
    
    Called during settlement to understand why bets won or lost.
    
    Args:
        home_team: Home team name
        away_team: Away team name
        match_date: Match date
        
    Returns:
        Post-match insights string or None
        
    Requirements: 7.1, 7.2
    """
    try:
        from src.ingestion.tavily_provider import get_tavily_provider
        from src.ingestion.tavily_budget import get_budget_manager
        
        tavily = get_tavily_provider()
        budget = get_budget_manager()
        
        if not tavily or not tavily.is_available():
            return None
        
        if not budget or not budget.can_call("settlement_clv"):
            logger.debug("📊 [SETTLER] Tavily budget limit reached")
            return None
        
        # Build post-match query
        date_str = match_date.strftime("%Y-%m-%d") if match_date else ""
        query = f"{home_team} vs {away_team} {date_str} match report result analysis"
        
        # V7.1: Use native Tavily news parameters for better filtering
        response = tavily.search(
            query=query,
            search_depth="basic",
            max_results=3,
            include_answer=True,
            topic="news",
            days=3
        )
        
        if response:
            budget.record_call("settlement_clv")
            
            insights = []
            
            if response.answer:
                insights.append(response.answer[:300])
            
            if response.results:
                for r in response.results[:2]:
                    # V5.3 FIX: Guard against None title/content
                    title = r.title if r.title else "Unknown"
                    content = r.content[:100] if r.content else ""
                    if title and content:
                        insights.append(f"• {title}: {content}")
            
            if insights:
                logger.info(f"🔍 [SETTLER] Tavily post-match insights found for {home_team} vs {away_team}")
                return "\n".join(insights)
        
        return None
        
    except ImportError:
        logger.debug("⚠️ [SETTLER] Tavily not available")
        return None
    except Exception as e:
        logger.warning(f"⚠️ [SETTLER] Tavily post-match search failed: {e}")
        return None


def calculate_clv(odds_taken: float, closing_odds: float, margin: float = 0.05) -> Optional[float]:
    """
    Calculate Closing Line Value (CLV) - V4.2 NEW.
    
    CLV measures if we beat the closing line, which is the best predictor
    of long-term profitability in sports betting.
    
    Formula:
    1. Remove bookmaker margin from closing odds to get "fair" odds
    2. CLV = (odds_taken / fair_closing_odds) - 1
    
    Args:
        odds_taken: The decimal odds when we placed/recommended the bet
        closing_odds: The decimal odds at match kickoff
        margin: Estimated bookmaker margin (default 5%)
        
    Returns:
        CLV as percentage (e.g., 3.5 means +3.5% CLV), or None if invalid
        
    Edge Cases:
        - Returns None if odds_taken or closing_odds <= 1.0 (invalid)
        - Returns None if closing_odds is None
        - Returns None if odds are unreasonably high (> 1000) or infinite
    """
    # Validate inputs
    if not odds_taken or not closing_odds:
        return None
    if odds_taken <= 1.0 or closing_odds <= 1.0:
        return None
    if math.isinf(odds_taken) or math.isinf(closing_odds):
        return None
    if math.isnan(odds_taken) or math.isnan(closing_odds):
        return None
    if odds_taken > 1000 or closing_odds > 1000:
        return None
    
    try:
        # Convert closing odds to implied probability
        implied_prob = 1.0 / closing_odds
        
        # Remove margin (proportional method)
        fair_prob = implied_prob / (1.0 + margin)
        
        # Clamp to valid range
        fair_prob = max(0.01, min(0.99, fair_prob))
        
        # Fair closing odds
        fair_closing_odds = 1.0 / fair_prob
        
        # CLV = how much better our odds were vs fair closing
        clv = ((odds_taken / fair_closing_odds) - 1.0) * 100
        
        return round(clv, 2)
        
    except (ZeroDivisionError, ValueError):
        return None


def evaluate_over_under(market_string: str, actual_total: int, stat_available: bool = True) -> Tuple[str, str]:
    """
    Generic Over/Under evaluator for Corners, Cards, Goals.
    
    Args:
        market_string: e.g., "Over 9.5 Corners", "Under 4.5 Cards", "Over 2.5 Goals"
        actual_total: The actual stat total from the match
        stat_available: Whether the stat data is available (False = PENDING)
        
    Returns:
        Tuple of (result_status, explanation)
        
    V5.1 FIX: Pattern regex now explicitly requires .5 to avoid wrong matches.
    Supports integer formats (Over 9 Corners) for backward compatibility.
    """
    if not stat_available:
        return RESULT_PENDING, f"⏳ Stats non disponibili per: {market_string}"
    
    # V5.1 FIX: More precise pattern for Over/Under
    pattern = r'(over|under)\s+(\d+(?:\.5)?)\s*(corner|card|goal)'
    match = re.search(pattern, market_string.lower())
    
    if not match:
        return RESULT_PENDING, f"Formato mercato non riconosciuto: {market_string}"
    
    direction = match.group(1)
    limit = float(match.group(2))
    stat_type = match.group(3)
    
    if not isinstance(actual_total, (int, float)) or actual_total < 0:
        logger.warning(f"⚠️ actual_total non valido: {actual_total} per {market_string}")
        return RESULT_PENDING, f"⏳ Valore stats non valido: {actual_total}"
    
    if direction == "over":
        if actual_total > limit:
            return RESULT_WIN, f"✅ Over {limit} {stat_type.title()}s Preso ({actual_total} totali)"
        else:
            return RESULT_LOSS, f"❌ Under {limit} {stat_type.title()}s ({actual_total} totali)"
    else:
        if actual_total < limit:
            return RESULT_WIN, f"✅ Under {limit} {stat_type.title()}s Preso ({actual_total} totali)"
        else:
            return RESULT_LOSS, f"❌ Over {limit} {stat_type.title()}s ({actual_total} totali)"


def get_match_result(home_team: str, away_team: str, match_time: datetime) -> Optional[Dict]:
    """
    Fetch final match result from FotMob.
    
    Args:
        home_team: Home team name
        away_team: Away team name
        match_time: Match start time
        
    Returns:
        Dict with home_score, away_score, status, match_id or None
        Status can be: 'FINISHED', 'CANCELLED', 'POSTPONED'
    """
    try:
        fotmob = get_data_provider()
        if not fotmob:
            return None
        
        team_id, _ = fotmob.search_team_id(home_team)
        if not team_id:
            logger.debug(f"Could not find team ID for {home_team}")
            return None
        
        team_data = fotmob.get_team_details(team_id)
        if not team_data:
            return None
        
        fixtures = team_data.get('fixtures', {})
        all_fixtures = fixtures.get('allFixtures', {})
        previous = all_fixtures.get('fixtures', [])
        
        for match in previous:
            match_home = match.get('home', {}).get('name', '')
            match_away = match.get('away', {}).get('name', '')
            
            if (home_team.lower() in match_home.lower() or match_home.lower() in home_team.lower()) and \
               (away_team.lower() in match_away.lower() or match_away.lower() in away_team.lower()):
                
                match_id = match.get('id')
                
                match_status = match.get('status', {})
                if isinstance(match_status, dict):
                    is_cancelled = match_status.get('cancelled', False)
                    reason_raw = match_status.get('reason', '')
                    if isinstance(reason_raw, dict):
                        reason = reason_raw.get('long', reason_raw.get('short', '')).lower()
                    else:
                        reason = str(reason_raw).lower() if reason_raw else ''
                    
                    if is_cancelled or 'postponed' in reason or 'cancelled' in reason or 'abandoned' in reason:
                        status_type = 'POSTPONED' if 'postponed' in reason else 'CANCELLED'
                        logger.info(f"⚠️ Match rinviato/annullato: {match_home} vs {match_away} ({reason or status_type})")
                        return {
                            'home_score': 0,
                            'away_score': 0,
                            'status': status_type,
                            'home_team': match_home,
                            'away_team': match_away,
                            'reason': reason,
                            'match_id': match_id
                        }
                
                home_score = match.get('home', {}).get('score')
                away_score = match.get('away', {}).get('score')
                
                if home_score is not None and away_score is not None:
                    return {
                        'home_score': int(home_score),
                        'away_score': int(away_score),
                        'status': 'FINISHED',
                        'home_team': match_home,
                        'away_team': match_away,
                        'match_id': match_id
                    }
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching match result: {e}")
        return None


def evaluate_combo_bet(combo_suggestion: str, home_score: int, away_score: int, match_stats: Dict = None) -> Tuple[str, str, str]:
    """
    V7.4: Evaluate a combo bet like "1 + over2.5" or "X2 + over cards"
    
    Args:
        combo_suggestion: Combo string like "1 + over2.5" or "Home Win + Over 9.5 Corners"
        home_score: Final home score
        away_score: Final away score  
        match_stats: Dict with corner/card stats
        
    Returns:
        Tuple of (outcome, explanation, expansion_type)
        outcome: WIN/LOSS/PENDING
        explanation: Detailed breakdown
        expansion_type: Type of expansion for categorization
    """
    if not combo_suggestion or "+" not in combo_suggestion:
        return RESULT_PENDING, "Formato combo non valido", "unknown"
    
    components = [c.strip() for c in combo_suggestion.split("+")]
    if len(components) != 2:
        return RESULT_PENDING, f"Combo con {len(components)} componenti non supportata", "unknown"
    
    outcomes = []
    explanations = []
    expansion_type = "unknown"
    
    for i, component in enumerate(components):
        outcome, explanation = evaluate_bet(component, home_score, away_score, None, "FINISHED", match_stats)
        outcomes.append(outcome)
        explanations.append(f"{component}: {explanation}")
        
        if i == 1:
            component_lower = component.lower()
            if "over" in component_lower or "under" in component_lower:
                if "goal" in component_lower or "2.5" in component_lower or "1.5" in component_lower:
                    expansion_type = "over_under_goals"
                elif "corner" in component_lower:
                    expansion_type = "over_under_corners"
                elif "card" in component_lower:
                    expansion_type = "over_under_cards"
                else:
                    expansion_type = "over_under_other"
            elif "btts" in component_lower or "both teams" in component_lower:
                expansion_type = "btts"
    
    if all(o == RESULT_WIN for o in outcomes):
        return RESULT_WIN, f"✅ COMBO VINCENTE | {' | '.join(explanations)}", expansion_type
    elif any(o == RESULT_LOSS for o in outcomes):
        return RESULT_LOSS, f"❌ COMBO PERDENTE | {' | '.join(explanations)}", expansion_type
    elif any(o == RESULT_PENDING for o in outcomes):
        return RESULT_PENDING, f"⏳ COMBO IN ATTESA | {' | '.join(explanations)}", expansion_type
    else:
        return RESULT_PENDING, f"⏳ COMBO STATO SCONOSCIUTO | {' | '.join(explanations)}", expansion_type


def evaluate_bet(
    recommended_market: str,
    home_score: int,
    away_score: int,
    home_odd: float = None,
    match_status: str = "FINISHED",
    match_stats: Dict = None
) -> Tuple[str, str]:
    """
    Evaluate if a bet won or lost based on the result.
    
    Args:
        recommended_market: The market we recommended (e.g., "Home Win", "Over 2.5 Goals", "Over 9.5 Corners")
        home_score: Final home score
        away_score: Final away score
        home_odd: Home odds (for context)
        match_status: Match status ('FINISHED', 'CANCELLED', 'POSTPONED')
        match_stats: Dict with corner/card stats (home_corners, away_corners, home_yellow_cards, etc.)
        
    Returns:
        Tuple of (result_status, explanation)
    """
    if match_status in ('CANCELLED', 'POSTPONED'):
        return RESULT_PUSH, f"⚠️ Match {match_status.lower()} - Scommessa Annullata"
    
    if home_score is None or away_score is None:
        logger.warning(f"⚠️ evaluate_bet called with None score: home={home_score}, away={away_score}")
        return RESULT_PENDING, "⏳ Score non disponibile"
    
    try:
        home_score = int(home_score)
        away_score = int(away_score)
    except (TypeError, ValueError) as e:
        logger.warning(f"⚠️ Invalid score values: home={home_score}, away={away_score}")
        return RESULT_PENDING, "⏳ Score non valido"
    
    total_goals = home_score + away_score
    market_lower = recommended_market.lower() if recommended_market else ""
    match_stats = match_stats or {}
    
    # CORNERS MARKET
    if "corner" in market_lower:
        home_corners = match_stats.get('home_corners')
        away_corners = match_stats.get('away_corners')
        
        if home_corners is None or away_corners is None:
            return RESULT_PENDING, f"⏳ Corner stats non disponibili"
        
        try:
            home_corners = int(home_corners)
            away_corners = int(away_corners)
        except (TypeError, ValueError) as e:
            logger.warning(f"⚠️ Corner stats non numerici: home={home_corners}, away={away_corners}")
            return RESULT_PENDING, f"⏳ Corner stats non validi"
        
        if home_corners < 0 or away_corners < 0:
            logger.warning(f"⚠️ Corner stats negativi: home={home_corners}, away={away_corners}")
            return RESULT_PENDING, f"⏳ Corner stats non validi (negativi)"
        
        total_corners = home_corners + away_corners
        return evaluate_over_under(recommended_market, total_corners, stat_available=True)
    
    # CARDS MARKET
    if "card" in market_lower:
        def safe_int(val, default=0):
            if val is None:
                return default
            try:
                result = int(val)
                return result if result >= 0 else default
            except (TypeError, ValueError):
                return default
        
        home_yellow = safe_int(match_stats.get('home_yellow_cards'))
        away_yellow = safe_int(match_stats.get('away_yellow_cards'))
        home_red = safe_int(match_stats.get('home_red_cards'))
        away_red = safe_int(match_stats.get('away_red_cards'))
        
        if match_stats.get('home_yellow_cards') is None and match_stats.get('away_yellow_cards') is None:
            return RESULT_PENDING, f"⏳ Card stats non disponibili"
        
        total_cards = home_yellow + away_yellow + home_red + away_red
        return evaluate_over_under(recommended_market, total_cards, stat_available=True)
    
    # GOALS MARKET (Over/Under X.5 Goals format)
    if "goal" in market_lower and ("over" in market_lower or "under" in market_lower):
        return evaluate_over_under(recommended_market, total_goals, stat_available=True)
    
    # Home Win
    if "home" in market_lower and "win" in market_lower:
        if home_score > away_score:
            return RESULT_WIN, f"✅ Vittoria Casa {home_score}-{away_score}"
        else:
            return RESULT_LOSS, f"❌ Casa non vince ({home_score}-{away_score})"
    
    # Away Win
    if "away" in market_lower and "win" in market_lower:
        if away_score > home_score:
            return RESULT_WIN, f"✅ Vittoria Trasferta {home_score}-{away_score}"
        else:
            return RESULT_LOSS, f"❌ Trasferta non vince ({home_score}-{away_score})"
    
    # Draw
    if "draw" in market_lower or market_lower == "x":
        if home_score == away_score:
            return RESULT_WIN, f"✅ Pareggio {home_score}-{away_score}"
        else:
            return RESULT_LOSS, f"❌ Non pareggio ({home_score}-{away_score})"
    
    # Single digit markets: "1", "2", "X"
    if market_lower == "1":
        if home_score > away_score:
            return RESULT_WIN, f"✅ 1 - Vittoria Casa {home_score}-{away_score}"
        else:
            return RESULT_LOSS, f"❌ 1 - Casa non vince ({home_score}-{away_score})"
    
    if market_lower == "2":
        if away_score > home_score:
            return RESULT_WIN, f"✅ 2 - Vittoria Trasferta {home_score}-{away_score}"
        else:
            return RESULT_LOSS, f"❌ 2 - Trasferta non vince ({home_score}-{away_score})"
    
    # Double Chance 1X
    if "1x" in market_lower or ("home" in market_lower and "draw" in market_lower):
        if home_score >= away_score:
            return RESULT_WIN, f"✅ 1X coperto ({home_score}-{away_score})"
        else:
            return RESULT_LOSS, f"❌ Trasferta vince ({home_score}-{away_score})"
    
    # Double Chance X2
    if "x2" in market_lower or ("away" in market_lower and "draw" in market_lower):
        if away_score >= home_score:
            return RESULT_WIN, f"✅ X2 coperto ({home_score}-{away_score})"
        else:
            return RESULT_LOSS, f"❌ Casa vince ({home_score}-{away_score})"
    
    # Over 2.5 (legacy format)
    if "over 2.5" in market_lower or "over2.5" in market_lower:
        if total_goals > 2.5:
            return RESULT_WIN, f"✅ Over 2.5 Preso ({total_goals} gol)"
        else:
            return RESULT_LOSS, f"❌ Under 2.5 ({total_goals} gol)"
    
    # Under 2.5 (legacy format)
    if "under 2.5" in market_lower or "under2.5" in market_lower:
        if total_goals < 2.5:
            return RESULT_WIN, f"✅ Under 2.5 Preso ({total_goals} gol)"
        else:
            return RESULT_LOSS, f"❌ Over 2.5 ({total_goals} gol)"
    
    # BTTS (Both Teams To Score)
    if "btts" in market_lower or "both teams" in market_lower:
        if home_score > 0 and away_score > 0:
            return RESULT_WIN, f"✅ BTTS Preso ({home_score}-{away_score})"
        else:
            return RESULT_LOSS, f"❌ BTTS Mancato ({home_score}-{away_score})"
    
    # Over 1.5 (legacy format)
    if "over 1.5" in market_lower:
        if total_goals > 1.5:
            return RESULT_WIN, f"✅ Over 1.5 Preso ({total_goals} gol)"
        else:
            return RESULT_LOSS, f"❌ Under 1.5 ({total_goals} gol)"
    
    # Default: can't evaluate
    return RESULT_PENDING, f"Mercato sconosciuto: {recommended_market}"


def settle_pending_bets(lookback_hours: int = 48) -> Dict:
    """
    Main settlement function. Checks all sent alerts from the last N hours
    and evaluates their outcomes.
    
    V4.1 FIX: Fetch-then-Save pattern to avoid DB lock during network calls.
    
    Args:
        lookback_hours: How far back to look for unsettled bets
        
    Returns:
        Dict with settlement statistics
    """
    logger.info("🌙 STARTING BET SETTLEMENT...")
    
    stats = {
        'total_checked': 0,
        'settled': 0,
        'wins': 0,
        'losses': 0,
        'pending': 0,
        'errors': 0,
        'roi_pct': 0.0,
        'details': []
    }
    
    # PHASE 1: Query DB (fast, minimal lock time)
    matches_to_settle = []
    
    with get_db_context() as db:
        try:
            now = datetime.now(timezone.utc)
            cutoff_finished = now - timedelta(hours=2)
            cutoff_lookback = now - timedelta(hours=lookback_hours)
            
            matches = db.query(Match).options(
                joinedload(Match.news_logs)
            ).filter(
                and_(
                    Match.start_time < cutoff_finished,
                    Match.start_time > cutoff_lookback,
                    Match.highest_score_sent >= SETTLEMENT_MIN_SCORE
                )
            ).all()
            
            logger.info(f"📋 Found {len(matches)} matches to settle")
            
            for match in matches:
                sent_logs = [nl for nl in match.news_logs if nl.sent and nl.recommended_market]
                news_log = max(sent_logs, key=lambda x: x.score, default=None) if sent_logs else None
                
                if not news_log or not news_log.recommended_market:
                    logger.debug(f"No recommendation found for {match.home_team} vs {match.away_team}")
                    continue
                
                matches_to_settle.append({
                    'match_id': match.id,
                    'news_log_id': news_log.id,
                    'home_team': match.home_team,
                    'away_team': match.away_team,
                    'start_time': match.start_time,
                    'league': match.league,
                    'current_home_odd': match.current_home_odd,
                    'current_away_odd': match.current_away_odd,
                    'current_draw_odd': match.current_draw_odd,
                    'recommended_market': news_log.recommended_market,
                    'combo_suggestion': getattr(news_log, 'combo_suggestion', None),
                    'news_log_score': news_log.score,
                    'closing_odds': getattr(news_log, 'closing_odds', None),
                    'odds_taken': getattr(news_log, 'odds_taken', None),
                    'primary_driver': getattr(news_log, 'primary_driver', None) or 'UNKNOWN'
                })
                
        except Exception as e:
            logger.error(f"Settlement query error: {e}", exc_info=True)
            stats['errors'] += 1
            return stats
    
    # PHASE 2: Fetch results from FotMob (NO DB LOCK)
    logger.info(f"🌐 Fetching results for {len(matches_to_settle)} matches (no DB lock)...")
    
    results_cache = []
    
    for match_data in matches_to_settle:
        stats['total_checked'] += 1
        
        result = get_match_result(
            match_data['home_team'],
            match_data['away_team'],
            match_data['start_time']
        )
        
        if not result:
            stats['pending'] += 1
            logger.debug(f"Result not available for {match_data['home_team']} vs {match_data['away_team']}")
            continue
        
        match_stats = None
        fotmob_match_id = result.get('match_id')
        if fotmob_match_id and result.get('status') == 'FINISHED':
            try:
                fotmob = get_data_provider()
                match_stats = fotmob.get_match_stats(fotmob_match_id)
            except Exception as e:
                logger.warning(f"⚠️ Could not fetch stats: {e}")
        
        outcome, explanation = evaluate_bet(
            match_data['recommended_market'],
            result['home_score'],
            result['away_score'],
            match_data['current_home_odd'],
            result.get('status', 'FINISHED'),
            match_stats
        )
        
        combo_outcome = None
        combo_explanation = None
        expansion_type = None
        
        if match_data['combo_suggestion']:
            combo_outcome, combo_explanation, expansion_type = evaluate_combo_bet(
                match_data['combo_suggestion'],
                result['home_score'],
                result['away_score'],
                match_stats
            )
            logger.info(f"🧩 [SETTLER] Combo evaluation: {match_data['combo_suggestion']} → {combo_outcome}")
        
        results_cache.append({
            'match_data': match_data,
            'result': result,
            'match_stats': match_stats,
            'outcome': outcome,
            'explanation': explanation,
            'combo_outcome': combo_outcome,
            'combo_explanation': combo_explanation,
            'expansion_type': expansion_type
        })
    
    # PHASE 3: Save to DB (fast batch update)
    logger.info(f"💾 Saving {len(results_cache)} results to DB...")
    
    total_stake = 0
    total_return = 0
    
    with get_db_context() as db:
        try:
            for item in results_cache:
                match_data = item['match_data']
                result = item['result']
                match_stats = item['match_stats']
                outcome = item['outcome']
                explanation = item['explanation']
                combo_outcome = item.get('combo_outcome')
                combo_explanation = item.get('combo_explanation')
                expansion_type = item.get('expansion_type')
                
                if match_stats:
                    match = db.query(Match).filter(Match.id == match_data['match_id']).first()
                    if match:
                        match.home_corners = match_stats.get('home_corners')
                        match.away_corners = match_stats.get('away_corners')
                        match.home_yellow_cards = match_stats.get('home_yellow_cards')
                        match.away_yellow_cards = match_stats.get('away_yellow_cards')
                        match.home_red_cards = match_stats.get('home_red_cards')
                        match.away_red_cards = match_stats.get('away_red_cards')
                        match.home_xg = match_stats.get('home_xg')
                        match.away_xg = match_stats.get('away_xg')
                        match.home_possession = match_stats.get('home_possession')
                        match.away_possession = match_stats.get('away_possession')
                        match.home_shots_on_target = match_stats.get('home_shots_on_target')
                        match.away_shots_on_target = match_stats.get('away_shots_on_target')
                        match.home_big_chances = match_stats.get('home_big_chances')
                        match.away_big_chances = match_stats.get('away_big_chances')
                        match.home_fouls = match_stats.get('home_fouls')
                        match.away_fouls = match_stats.get('away_fouls')
                
                if combo_outcome:
                    news_log = db.query(NewsLog).filter(NewsLog.id == match_data['news_log_id']).first()
                    if news_log:
                        news_log.combo_outcome = combo_outcome
                        news_log.combo_explanation = combo_explanation
                        news_log.expansion_type = expansion_type
                
                if outcome == RESULT_PENDING:
                    stats['pending'] += 1
                    continue
                
                stats['settled'] += 1
                stake = 1.0
                total_stake += stake
                
                if outcome == RESULT_PUSH:
                    stats['pushes'] = stats.get('pushes', 0) + 1
                    total_return += stake
                    logger.info(f"⚠️ VOID: {match_data['home_team']} vs {match_data['away_team']} | {match_data['recommended_market']} | {explanation}")
                    stats['details'].append({
                        'match': f"{match_data['home_team']} vs {match_data['away_team']}",
                        'league': match_data['league'],
                        'market': match_data['recommended_market'],
                        'score': match_data['news_log_score'],
                        'result': f"VOID ({result.get('reason', 'cancelled')})",
                        'outcome': outcome,
                        'explanation': explanation,
                        'odds': 1.0,
                        'driver': match_data['primary_driver']
                    })
                    continue
                
                bet_odds = None
                market_lower = match_data['recommended_market'].lower()
                
                if match_data['closing_odds'] and match_data['closing_odds'] > 1.0:
                    bet_odds = match_data['closing_odds']
                
                if bet_odds is None:
                    if "home" in market_lower and "win" in market_lower:
                        bet_odds = match_data['current_home_odd'] if match_data['current_home_odd'] and match_data['current_home_odd'] > 1.0 else None
                    elif "away" in market_lower and "win" in market_lower:
                        bet_odds = match_data['current_away_odd'] if match_data['current_away_odd'] and match_data['current_away_odd'] > 1.0 else None
                    elif "draw" in market_lower:
                        bet_odds = match_data['current_draw_odd'] if match_data['current_draw_odd'] and match_data['current_draw_odd'] > 1.0 else None
                
                if bet_odds is None:
                    bet_odds = 1.9
                    logger.warning(f"⚠️ Quote non disponibili per {match_data['home_team']} vs {match_data['away_team']}. Uso default 1.9")
                
                if outcome == RESULT_WIN:
                    stats['wins'] += 1
                    total_return += stake * bet_odds
                    logger.info(f"✅ WIN: {match_data['home_team']} vs {match_data['away_team']} | {match_data['recommended_market']} @{bet_odds:.2f} | {explanation}")
                else:
                    stats['losses'] += 1
                    logger.info(f"❌ LOSS: {match_data['home_team']} vs {match_data['away_team']} | {match_data['recommended_market']} @{bet_odds:.2f} | {explanation}")
                
                clv_value = None
                odds_taken = match_data.get('odds_taken')
                closing_odds = match_data.get('closing_odds') or bet_odds
                
                if odds_taken and closing_odds:
                    clv_value = calculate_clv(odds_taken, closing_odds)
                    if clv_value is not None:
                        news_log_id = match_data.get('news_log_id')
                        if news_log_id:
                            news_log = db.query(NewsLog).filter(NewsLog.id == news_log_id).first()
                            if news_log:
                                news_log.clv_percent = clv_value
                    
                    clv_emoji = "📈" if clv_value > 0 else "📉"
                    logger.info(f"   {clv_emoji} CLV: {clv_value:+.2f}% (taken @{odds_taken:.2f} vs closing @{closing_odds:.2f})")
                
                stats['details'].append({
                    'match': f"{match_data['home_team']} vs {match_data['away_team']}",
                    'league': match_data['league'],
                    'market': match_data['recommended_market'],
                    'score': match_data['news_log_score'],
                    'result': f"{result['home_score']}-{result['away_score']}",
                    'outcome': outcome,
                    'explanation': explanation,
                    'odds': bet_odds,
                    'driver': match_data['primary_driver'],
                    'clv': clv_value,
                    'combo_suggestion': match_data.get('combo_suggestion'),
                    'combo_outcome': combo_outcome,
                    'combo_explanation': combo_explanation,
                    'expansion_type': expansion_type
                })
                
                tavily_insights = _tavily_post_match_search(
                    match_data['home_team'],
                    match_data['away_team'],
                    match_data['start_time']
                )
                if tavily_insights:
                    stats['details'][-1]['tavily_insights'] = tavily_insights
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Settlement save error: {e}", exc_info=True)
            stats['errors'] += 1
    
    if total_stake > 0:
        profit = total_return - total_stake
        stats['roi_pct'] = (profit / total_stake) * 100
    
    clv_values = [d.get('clv') for d in stats['details'] if d.get('clv') is not None]
    if clv_values:
        stats['avg_clv'] = round(sum(clv_values) / len(clv_values), 2)
        stats['clv_positive_rate'] = round(len([c for c in clv_values if c > 0]) / len(clv_values) * 100, 1)
        logger.info(f"📈 CLV SUMMARY: Avg {stats['avg_clv']:+.2f}% | Positive CLV: {stats['clv_positive_rate']}% ({len(clv_values)} bets tracked)")
    
    total_bets = stats['wins'] + stats['losses']
    if total_bets >= 10:
        false_positive_rate = (stats['losses'] / total_bets) * 100
        stats['false_positive_rate'] = round(false_positive_rate, 1)

    combo_bets = [d for d in stats['details'] if d.get('combo_suggestion')]
    if combo_bets:
        combo_wins = len([c for c in combo_bets if c.get('combo_outcome') == 'WIN'])
        combo_losses = len([c for c in combo_bets if c.get('combo_outcome') == 'LOSS'])
        combo_pending = len([c for c in combo_bets if c.get('combo_outcome') == 'PENDING'])

        stats['combo_stats'] = {
            'total_combo_bets': len(combo_bets),
            'combo_wins': combo_wins,
            'combo_losses': combo_losses,
            'combo_pending': combo_pending,
            'combo_win_rate': round((combo_wins / (combo_wins + combo_losses)) * 100, 1) if (combo_wins + combo_losses) > 0 else 0
        }

        expansion_performance = {}
        for bet in combo_bets:
            exp_type = bet.get('expansion_type', 'unknown')
            if exp_type not in expansion_performance:
                expansion_performance[exp_type] = {'wins': 0, 'losses': 0, 'total': 0}

            expansion_performance[exp_type]['total'] += 1
            if bet.get('combo_outcome') == 'WIN':
                expansion_performance[exp_type]['wins'] += 1
            elif bet.get('combo_outcome') == 'LOSS':
                expansion_performance[exp_type]['losses'] += 1

        for exp_type, data in expansion_performance.items():
            if data['wins'] + data['losses'] > 0:
                data['win_rate'] = round((data['wins'] / (data['wins'] + data['losses'])) * 100, 1)
            else:
                data['win_rate'] = 0

        stats['combo_stats']['expansion_performance'] = expansion_performance

        logger.info(f" COMBO STATS: {combo_wins}W / {combo_losses}L / {combo_pending}P | Win Rate: {stats['combo_stats']['combo_win_rate']}%")
        for exp_type, data in expansion_performance.items():
            logger.info(f"   {exp_type}: {data['wins']}W/{data['losses']}L ({data['win_rate']}%)")

    if total_bets >= 10 and stats.get('false_positive_rate', 0) > 40.0:
        false_positive_rate = stats['false_positive_rate']
        alert_msg = (
            f" <b>ALERT: False Positive Rate Alto</b>\n\n"
            f" Loss Rate: {false_positive_rate:.1f}% ({stats['losses']}/{total_bets} bets)\n"
            f" ROI: {stats['roi_pct']:.1f}%\n\n"
            f" <b>Azione Richiesta:</b>\n"
            f" • Rivedere thresholds (attuale: {stats.get('threshold', 8.6)})\n"
            f" • Verificare Verification Layer\n"
            f" • Controllare AI confidence checks\n\n"
            f" Ultimi {len(stats['details'])} risultati disponibili con /report"
        )
        
        try:
            from src.alerting.notifier import send_status_message
            send_status_message(alert_msg)
            logger.warning(f"🚨 False positive rate alert sent: {false_positive_rate:.1f}%")
        except Exception as e:
            logger.error(f"Failed to send false positive alert: {e}")

    logger.info(f"📊 SETTLEMENT COMPLETE: {stats['wins']}W / {stats['losses']}L | ROI: {stats['roi_pct']:.1f}%")
    
    return stats


def get_league_performance(days: int = 30) -> Dict[str, Dict]:
    """
    Calculate performance by league for optimizer weighting.
    
    DEPRECATED V5.1: This function is no longer used.
    The optimizer now calculates performance directly from optimizer_weights.json
    via StrategyOptimizer.record_bet_result().
    
    Kept for backward compatibility but always returns empty dict.
    
    Args:
        days: Lookback period in days (ignored)
        
    Returns:
        Empty dict - use StrategyOptimizer instead
    """
    logger.debug("⚠️ get_league_performance() è deprecata - usa StrategyOptimizer")
    return {}
