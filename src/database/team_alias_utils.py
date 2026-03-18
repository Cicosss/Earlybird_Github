"""
TeamAlias Utilities - Intelligent Field Integration

This module provides intelligent integration points for TeamAlias fields
in the bot's data flow. It makes the stored metadata (twitter_handle,
fotmob_id, country, league) actively used in the intelligence pipeline.

INTEGRATION POINTS:
1. Twitter Intel - Use twitter_handle for targeted team monitoring
2. FotMob Data - Use fotmob_id for direct data fetching
3. Regional Context - Use country for regional filtering
4. League Analysis - Use league for league-specific analysis

LOOKUP STRATEGY (Multi-Level):
1. Exact match - Fastest, uses index
2. Case-insensitive ILIKE - Efficient SQL query
3. Normalized match - Removes suffixes (FC, SK, Club, etc.)
"""

import logging
from typing import Optional, Tuple

from src.database.models import TeamAlias, get_db_session

logger = logging.getLogger(__name__)


# ============================================
# TEAM NAME NORMALIZATION (Synced with enrichment module)
# ============================================

# Common suffixes to remove for normalization
_TEAM_SUFFIXES = [" FC", " SK", " Club", " AS", " AC", " FK", " SC", " Calcio", " Spor"]


def _normalize_team_name(team_name: str) -> str:
    """
    Normalize team name by removing common suffixes.

    This is a local copy of the normalization logic to avoid circular imports
    and ensure consistency with team_alias_enrichment.py.

    Args:
        team_name: Raw team name

    Returns:
        Normalized team name without common suffixes
    """
    clean = team_name
    for suffix in _TEAM_SUFFIXES:
        clean = clean.replace(suffix, "")
    return clean.strip()


# ============================================
# INTELLIGENT LOOKUP HELPER
# ============================================


def _find_team_alias(db, team_name: str) -> Optional[TeamAlias]:
    """
    Intelligent multi-level lookup for TeamAlias.

    This function implements a progressive lookup strategy:
    1. Exact match (uses index, fastest)
    2. Case-insensitive ILIKE query (efficient SQL)
    3. Normalized match (removes suffixes like FC, SK, etc.)

    Args:
        db: Database session
        team_name: Team name to look up

    Returns:
        TeamAlias object or None
    """
    if not team_name:
        return None

    # Level 1: Exact match (uses index)
    alias = db.query(TeamAlias).filter(TeamAlias.api_name == team_name).first()
    if alias:
        logger.debug(f"✅ Found TeamAlias for '{team_name}' (exact match)")
        return alias

    # Level 2: Case-insensitive ILIKE query (efficient)
    alias = db.query(TeamAlias).filter(TeamAlias.api_name.ilike(team_name)).first()
    if alias:
        logger.debug(f"✅ Found TeamAlias for '{team_name}' (case-insensitive match)")
        return alias

    # Level 3: Normalized match (remove suffixes)
    normalized = _normalize_team_name(team_name)
    if normalized != team_name:
        # Try exact match with normalized name
        alias = db.query(TeamAlias).filter(TeamAlias.api_name == normalized).first()
        if alias:
            logger.debug(f"✅ Found TeamAlias for '{team_name}' (normalized: '{normalized}')")
            return alias

        # Try ILIKE with normalized name
        alias = db.query(TeamAlias).filter(TeamAlias.api_name.ilike(normalized)).first()
        if alias:
            logger.debug(f"✅ Found TeamAlias for '{team_name}' (normalized ILIKE: '{normalized}')")
            return alias

        # Try reverse: find records where normalized api_name matches input
        # This handles: DB has "Galatasaray SK", we search "Galatasaray"
        all_aliases = db.query(TeamAlias).all()
        for a in all_aliases:
            if _normalize_team_name(a.api_name).lower() == normalized.lower():
                logger.debug(f"✅ Found TeamAlias for '{team_name}' (reverse normalized match)")
                return a

    logger.debug(f"❌ No TeamAlias found for '{team_name}'")
    return None


# ============================================
# TWITTER HANDLE INTEGRATION
# ============================================


def get_team_twitter_handle(team_name: str) -> Optional[str]:
    """
    Get Twitter handle for a team from TeamAlias.

    This allows targeted monitoring of specific team accounts instead of
    searching all configured accounts.

    Uses intelligent multi-level lookup:
    1. Exact match
    2. Case-insensitive ILIKE
    3. Normalized match (removes suffixes)

    Args:
        team_name: Team name from The-Odds-API

    Returns:
        Twitter handle (e.g., @GalatasaraySK) or None
    """
    try:
        with get_db_session() as db:
            alias = _find_team_alias(db, team_name)
            if alias and alias.twitter_handle:
                logger.debug(f"✅ Found Twitter handle for {team_name}: {alias.twitter_handle}")
                return alias.twitter_handle

            logger.debug(f"❌ No Twitter handle found for {team_name}")
            return None
    except Exception as e:
        logger.error(f"Error getting Twitter handle for {team_name}: {e}")
        return None


def get_all_teams_with_twitter_handles() -> list[dict]:
    """
    Get all teams that have Twitter handles configured.

    This can be used to prioritize monitoring of official team accounts.

    Returns:
        List of dicts with team_name and twitter_handle
    """
    try:
        with get_db_session() as db:
            teams = db.query(TeamAlias).filter(TeamAlias.twitter_handle.isnot(None)).all()
            return [{"team_name": t.api_name, "twitter_handle": t.twitter_handle} for t in teams]
    except Exception as e:
        logger.error(f"Error getting teams with Twitter handles: {e}")
        return []


# ============================================
# FOTMOB ID INTEGRATION
# ============================================


def get_team_fotmob_id(team_name: str) -> Optional[str]:
    """
    Get FotMob ID for a team from TeamAlias.

    This allows direct FotMob data fetching without team search,
    improving performance and reliability.

    Uses intelligent multi-level lookup:
    1. Exact match
    2. Case-insensitive ILIKE
    3. Normalized match (removes suffixes)

    Args:
        team_name: Team name from The-Odds-API

    Returns:
        FotMob team ID as string or None
    """
    try:
        with get_db_session() as db:
            alias = _find_team_alias(db, team_name)
            if alias and alias.fotmob_id:
                logger.debug(f"✅ Found FotMob ID for {team_name}: {alias.fotmob_id}")
                return alias.fotmob_id

            logger.debug(f"❌ No FotMob ID found for {team_name}")
            return None
    except Exception as e:
        logger.error(f"Error getting FotMob ID for {team_name}: {e}")
        return None


def get_match_fotmob_ids(home_team: str, away_team: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get FotMob IDs for both teams in a match.

    This enables direct FotMob match data fetching without team searches.

    Args:
        home_team: Home team name
        away_team: Away team name

    Returns:
        Tuple of (home_fotmob_id, away_fotmob_id)
    """
    home_id = get_team_fotmob_id(home_team)
    away_id = get_team_fotmob_id(away_team)
    return home_id, away_id


# ============================================
# COUNTRY INTEGRATION
# ============================================


def get_team_country(team_name: str) -> Optional[str]:
    """
    Get country for a team from TeamAlias.

    This provides regional context for filtering and analysis.

    Uses intelligent multi-level lookup:
    1. Exact match
    2. Case-insensitive ILIKE
    3. Normalized match (removes suffixes)

    Args:
        team_name: Team name from The-Odds-API

    Returns:
        Country key (e.g., 'turkey', 'argentina') or None
    """
    try:
        with get_db_session() as db:
            alias = _find_team_alias(db, team_name)
            if alias and alias.country:
                logger.debug(f"✅ Found country for {team_name}: {alias.country}")
                return alias.country

            logger.debug(f"❌ No country found for {team_name}")
            return None
    except Exception as e:
        logger.error(f"Error getting country for {team_name}: {e}")
        return None


def get_teams_by_country(country: str) -> list[str]:
    """
    Get all teams from a specific country.

    This enables country-specific filtering and analysis.

    Args:
        country: Country key (e.g., 'turkey', 'argentina')

    Returns:
        List of team names from that country
    """
    try:
        with get_db_session() as db:
            teams = db.query(TeamAlias).filter(TeamAlias.country == country).all()
            return [t.api_name for t in teams]
    except Exception as e:
        logger.error(f"Error getting teams by country {country}: {e}")
        return []


# ============================================
# LEAGUE INTEGRATION
# ============================================


def get_team_league(team_name: str) -> Optional[str]:
    """
    Get primary league for a team from TeamAlias.

    This provides league context for filtering and analysis.

    Uses intelligent multi-level lookup:
    1. Exact match
    2. Case-insensitive ILIKE
    3. Normalized match (removes suffixes)

    Args:
        team_name: Team name from The-Odds-API

    Returns:
        League key (e.g., 'soccer_turkey_super_league') or None
    """
    try:
        with get_db_session() as db:
            alias = _find_team_alias(db, team_name)
            if alias and alias.league:
                logger.debug(f"✅ Found league for {team_name}: {alias.league}")
                return alias.league

            logger.debug(f"❌ No league found for {team_name}")
            return None
    except Exception as e:
        logger.error(f"Error getting league for {team_name}: {e}")
        return None


def get_teams_by_league(league: str) -> list[str]:
    """
    Get all teams from a specific league.

    This enables league-specific filtering and analysis.

    Args:
        league: League key (e.g., 'soccer_turkey_super_league')

    Returns:
        List of team names from that league
    """
    try:
        with get_db_session() as db:
            teams = db.query(TeamAlias).filter(TeamAlias.league == league).all()
            return [t.api_name for t in teams]
    except Exception as e:
        logger.error(f"Error getting teams by league {league}: {e}")
        return []


# ============================================
# COMPREHENSIVE TEAM DATA
# ============================================


def get_team_alias_data(team_name: str) -> Optional[dict]:
    """
    Get all enriched data for a team from TeamAlias.

    This provides a single source of truth for all team metadata.

    Uses intelligent multi-level lookup:
    1. Exact match
    2. Case-insensitive ILIKE
    3. Normalized match (removes suffixes)

    Args:
        team_name: Team name from The-Odds-API

    Returns:
        Dict with all TeamAlias fields or None
    """
    try:
        with get_db_session() as db:
            alias = _find_team_alias(db, team_name)
            if alias:
                return {
                    "api_name": alias.api_name,
                    "search_name": alias.search_name,
                    "twitter_handle": alias.twitter_handle,
                    "telegram_channel": alias.telegram_channel,
                    "fotmob_id": alias.fotmob_id,
                    "country": alias.country,
                    "league": alias.league,
                }

            logger.debug(f"❌ No TeamAlias found for {team_name}")
            return None
    except Exception as e:
        logger.error(f"Error getting TeamAlias data for {team_name}: {e}")
        return None


def get_match_alias_data(home_team: str, away_team: str) -> Tuple[Optional[dict], Optional[dict]]:
    """
    Get enriched data for both teams in a match.

    This enables intelligent match processing with full team context.

    Args:
        home_team: Home team name
        away_team: Away team name

    Returns:
        Tuple of (home_alias_data, away_alias_data)
    """
    home_data = get_team_alias_data(home_team)
    away_data = get_team_alias_data(away_team)
    return home_data, away_data


# ============================================
# UTILITIES
# ============================================


def log_team_alias_coverage() -> dict:
    """
    Log coverage statistics for TeamAlias fields.

    This helps identify which teams have complete metadata.

    Returns:
        Dict with coverage statistics
    """
    try:
        with get_db_session() as db:
            total = db.query(TeamAlias).count()
            twitter_count = db.query(TeamAlias).filter(TeamAlias.twitter_handle.isnot(None)).count()
            telegram_count = (
                db.query(TeamAlias).filter(TeamAlias.telegram_channel.isnot(None)).count()
            )
            fotmob_count = db.query(TeamAlias).filter(TeamAlias.fotmob_id.isnot(None)).count()
            country_count = db.query(TeamAlias).filter(TeamAlias.country.isnot(None)).count()
            league_count = db.query(TeamAlias).filter(TeamAlias.league.isnot(None)).count()

            stats = {
                "total_teams": total,
                "twitter_handles": twitter_count,
                "twitter_coverage": f"{(twitter_count / total * 100):.1f}%" if total > 0 else "0%",
                "telegram_channels": telegram_count,
                "telegram_coverage": f"{(telegram_count / total * 100):.1f}%"
                if total > 0
                else "0%",
                "fotmob_ids": fotmob_count,
                "fotmob_coverage": f"{(fotmob_count / total * 100):.1f}%" if total > 0 else "0%",
                "countries": country_count,
                "country_coverage": f"{(country_count / total * 100):.1f}%" if total > 0 else "0%",
                "leagues": league_count,
                "league_coverage": f"{(league_count / total * 100):.1f}%" if total > 0 else "0%",
            }

            logger.info(f"📊 TeamAlias Coverage: {stats}")
            return stats
    except Exception as e:
        logger.error(f"Error logging TeamAlias coverage: {e}")
        return {}
