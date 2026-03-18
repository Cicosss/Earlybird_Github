"""
TeamAlias Enrichment Module

This module provides intelligent enrichment for TeamAlias records by:
1. Mapping team names to their social media handles (Twitter, Telegram)
2. Mapping team names to FotMob IDs for data enrichment
3. Mapping team names to their countries and leagues
4. Automatically populating missing fields during TeamAlias creation
5. Providing seeding functions for initial data population

INTEGRATION:
- Integrates with config/twitter_intel_accounts.py for Twitter handles
- Integrates with src/ingestion/fotmob_team_mapping.py for FotMob IDs
- Integrates with src/processing/sources_config.py for country/league mapping
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================
# TEAM-SPECIFIC MAPPINGS
# ============================================

# Twitter handle mapping (team_name -> twitter_handle)
# These are official team Twitter accounts
# NOTE: Both base name AND common variants (with FC, SK, etc.) are included
# to ensure matching regardless of how The-Odds-API sends the team name
TEAM_TWITTER_HANDLES: Dict[str, str] = {
    # Turkey Super Lig - Base names
    "Galatasaray": "@GalatasaraySK",
    "Fenerbahce": "@Fenerbahce",
    "Besiktas": "@Besiktas",
    "Trabzonspor": "@Trabzonspor",
    # Turkey Super Lig - API variants (with suffixes)
    "Galatasaray SK": "@GalatasaraySK",
    "Fenerbahce FC": "@Fenerbahce",
    "Besiktas JK": "@Besiktas",
    # Argentina Primera - Base names
    "Boca Juniors": "@BocaJrsOficial",
    "River Plate": "@RiverPlate",
    "Independiente": "@Independiente",
    "Racing Club": "@RacingClub",
    "San Lorenzo": "@SanLorenzo",
    # Argentina Primera - API variants
    "Boca Juniors FC": "@BocaJrsOficial",
    "River Plate FC": "@RiverPlate",
    # Mexico Liga MX
    "America": "@ClubAmerica",
    "Chivas": "@Chivas",
    "Cruz Azul": "@CruzAzul",
    "Monterrey": "@Monterrey",
    "Tigres": "@TigresOficial",
    "Club America": "@ClubAmerica",
    # Greece Super League
    "Olympiacos": "@OlympiacosFC",
    "Panathinaikos": "@paok_fc",
    "AEK Athens": "@AEK_FC",
    "PAOK": "@paok_fc",
    "Olympiacos FC": "@OlympiacosFC",
    # Scotland Premiership
    "Celtic": "@CelticFC",
    "Rangers": "@RangersFC",
    "Aberdeen": "@AberdeenFC",
    "Hearts": "@HeartsOfficial",
    "Hibernian": "@HibernianFC",
    "Celtic FC": "@CelticFC",
    "Rangers FC": "@RangersFC",
    # Australia A-League
    "Sydney FC": "@SydneyFC",
    "Melbourne Victory": "@MVFC",
    "Melbourne City": "@MelbourneCity",
    "Perth Glory": "@PerthGloryFC",
    # Poland Ekstraklasa
    "Legia Warsaw": "@LegiaWarszawa",
    "Lech Poznan": "@LechPoznan",
    "Wisla Krakow": "@WislaKrakowSA",
    # Brazil Serie B
    "Ceara": "@CearaOficial",
    "Bahia": "@ECBahia",
    "Sport Recife": "@SportRecife",
    # China Super League
    "Beijing Guoan": "@BeijingGuoan",
    "Shanghai SIPG": "@ShanghaiSIPG",
    # Japan J-League
    "Kashima Antlers": "@Antlers_Kashima",
    "Urawa Red Diamonds": "@UrawaReds",
    # Norway Eliteserien
    "Bodø/Glimt": "@bodo_glimt",
    "Molde": "@Molde_FK",
    "Rosenborg": "@Rosenborg_BK",
    # France Ligue 1
    "PSG": "@PSG_inside",
    "Olympique Marseille": "@OM_Officiel",
    "Lyon": "@OL",
    "Monaco": "@AS_Monaco",
    "Paris Saint Germain": "@PSG_inside",
    # Belgium First Division
    "Club Brugge": "@ClubBrugge",
    "Anderlecht": "@RSCA",
    # Austria Bundesliga
    "Red Bull Salzburg": "@RedBullSalzburg",
    "Austria Wien": "@FKAustriaWien",
    # Netherlands Eredivisie
    "Ajax": "@Ajax",
    "PSV": "@PSV",
    "Feyenoord": "@Feyenoord",
    "Ajax Amsterdam": "@Ajax",
    "PSV Eindhoven": "@PSV",
}


# Telegram channel mapping (team_name -> telegram_channel)
# These are official or verified team Telegram channels
TEAM_TELEGRAM_CHANNELS: Dict[str, str] = {
    # Turkey Super Lig
    "Galatasaray": "galatasaray",
    "Fenerbahce": "fenerbahce",
    "Besiktas JK": "besiktas",
    "Trabzonspor": "trabzonspor",
    # Argentina Primera
    "Boca Juniors": "infoboca",
    "River Plate": "riverplate",
    # Scotland Premiership
    "Rangers": "GlasgowRangersUpdates",
    # Greece Super League
    "Olympiacos": "olympiacos",
    "Panathinaikos": "panathinaikos",
    "PAOK": "paok",
}


# FotMob ID mapping (team_name -> fotmob_id)
# This integrates with src/ingestion/fotmob_team_mapping.py
# NOTE: Both base name AND common variants (with FC, SK, etc.) are included
TEAM_FOTMOB_IDS: Dict[str, int] = {
    # Turkey Super Lig - Base names
    "Galatasaray": 8601,
    "Fenerbahce": 8600,
    "Besiktas": 8598,
    "Trabzonspor": 8609,
    # Turkey Super Lig - API variants
    "Galatasaray SK": 8601,
    "Fenerbahce FC": 8600,
    "Besiktas JK": 8598,
    # Poland Ekstraklasa
    "Legia Warsaw": 8673,
    "Lech Poznan": 8672,
}


# Team to country mapping (team_name -> country)
# NOTE: Both base name AND common variants (with FC, SK, etc.) are included
TEAM_TO_COUNTRY: Dict[str, str] = {
    # Turkey - Base names
    "Galatasaray": "turkey",
    "Fenerbahce": "turkey",
    "Besiktas": "turkey",
    "Trabzonspor": "turkey",
    # Turkey - API variants
    "Galatasaray SK": "turkey",
    "Fenerbahce FC": "turkey",
    "Besiktas JK": "turkey",
    # Argentina - Base names
    "Boca Juniors": "argentina",
    "River Plate": "argentina",
    "Independiente": "argentina",
    "Racing Club": "argentina",
    "San Lorenzo": "argentina",
    # Argentina - API variants
    "Boca Juniors FC": "argentina",
    "River Plate FC": "argentina",
    # Mexico
    "America": "mexico",
    "Chivas": "mexico",
    "Cruz Azul": "mexico",
    "Monterrey": "mexico",
    "Tigres": "mexico",
    "Club America": "mexico",
    # Greece
    "Olympiacos": "greece",
    "Panathinaikos": "greece",
    "AEK Athens": "greece",
    "PAOK": "greece",
    "Olympiacos FC": "greece",
    # Scotland - Base names
    "Celtic": "scotland",
    "Rangers": "scotland",
    "Aberdeen": "scotland",
    "Hearts": "scotland",
    "Hibernian": "scotland",
    # Scotland - API variants
    "Celtic FC": "scotland",
    "Rangers FC": "scotland",
    # Australia
    "Sydney FC": "australia",
    "Melbourne Victory": "australia",
    "Melbourne City": "australia",
    "Perth Glory": "australia",
    # Poland
    "Legia Warsaw": "poland",
    "Lech Poznan": "poland",
    "Wisla Krakow": "poland",
    # Brazil
    "Ceara": "brazil_b",
    "Bahia": "brazil_b",
    "Sport Recife": "brazil_b",
    # China
    "Beijing Guoan": "china",
    "Shanghai SIPG": "china",
    # Japan
    "Kashima Antlers": "japan",
    "Urawa Red Diamonds": "japan",
    # Norway
    "Bodø/Glimt": "norway",
    "Molde": "norway",
    "Rosenborg": "norway",
    # France
    "PSG": "france",
    "Olympique Marseille": "france",
    "Lyon": "france",
    "Monaco": "france",
    "Paris Saint Germain": "france",
    # Belgium
    "Club Brugge": "belgium",
    "Anderlecht": "belgium",
    # Austria
    "Red Bull Salzburg": "austria",
    "Austria Wien": "austria",
    # Netherlands
    "Ajax": "netherlands",
    "PSV": "netherlands",
    "Feyenoord": "netherlands",
    "Ajax Amsterdam": "netherlands",
    "PSV Eindhoven": "netherlands",
}


# Team to league mapping (team_name -> league_key)
# NOTE: Both base name AND common variants (with FC, SK, etc.) are included
TEAM_TO_LEAGUE: Dict[str, str] = {
    # Turkey Super Lig - Base names
    "Galatasaray": "soccer_turkey_super_league",
    "Fenerbahce": "soccer_turkey_super_league",
    "Besiktas": "soccer_turkey_super_league",
    "Trabzonspor": "soccer_turkey_super_league",
    # Turkey Super Lig - API variants
    "Galatasaray SK": "soccer_turkey_super_league",
    "Fenerbahce FC": "soccer_turkey_super_league",
    "Besiktas JK": "soccer_turkey_super_league",
    # Argentina Primera - Base names
    "Boca Juniors": "soccer_argentina_primera_division",
    "River Plate": "soccer_argentina_primera_division",
    "Independiente": "soccer_argentina_primera_division",
    "Racing Club": "soccer_argentina_primera_division",
    "San Lorenzo": "soccer_argentina_primera_division",
    # Argentina Primera - API variants
    "Boca Juniors FC": "soccer_argentina_primera_division",
    "River Plate FC": "soccer_argentina_primera_division",
    # Mexico Liga MX
    "America": "soccer_mexico_ligamx",
    "Chivas": "soccer_mexico_ligamx",
    "Cruz Azul": "soccer_mexico_ligamx",
    "Monterrey": "soccer_mexico_ligamx",
    "Tigres": "soccer_mexico_ligamx",
    "Club America": "soccer_mexico_ligamx",
    # Greece Super League
    "Olympiacos": "soccer_greece_super_league",
    "Panathinaikos": "soccer_greece_super_league",
    "AEK Athens": "soccer_greece_super_league",
    "PAOK": "soccer_greece_super_league",
    "Olympiacos FC": "soccer_greece_super_league",
    # Scotland Premiership - Base names
    "Celtic": "soccer_spl",
    "Rangers": "soccer_spl",
    "Aberdeen": "soccer_spl",
    "Hearts": "soccer_spl",
    "Hibernian": "soccer_spl",
    # Scotland Premiership - API variants
    "Celtic FC": "soccer_spl",
    "Rangers FC": "soccer_spl",
    # Australia A-League
    "Sydney FC": "soccer_australia_aleague",
    "Melbourne Victory": "soccer_australia_aleague",
    "Melbourne City": "soccer_australia_aleague",
    "Perth Glory": "soccer_australia_aleague",
    # Poland Ekstraklasa
    "Legia Warsaw": "soccer_poland_ekstraklasa",
    "Lech Poznan": "soccer_poland_ekstraklasa",
    "Wisla Krakow": "soccer_poland_ekstraklasa",
    # Brazil Serie B
    "Ceara": "soccer_brazil_serie_b",
    "Bahia": "soccer_brazil_serie_b",
    "Sport Recife": "soccer_brazil_serie_b",
    # China Super League
    "Beijing Guoan": "soccer_china_superleague",
    "Shanghai SIPG": "soccer_china_superleague",
    # Japan J-League
    "Kashima Antlers": "soccer_japan_j_league",
    "Urawa Red Diamonds": "soccer_japan_j_league",
    # Norway Eliteserien
    "Bodø/Glimt": "soccer_norway_eliteserien",
    "Molde": "soccer_norway_eliteserien",
    "Rosenborg": "soccer_norway_eliteserien",
    # France Ligue 1
    "PSG": "soccer_france_ligue_one",
    "Olympique Marseille": "soccer_france_ligue_one",
    "Lyon": "soccer_france_ligue_one",
    "Monaco": "soccer_france_ligue_one",
    "Paris Saint Germain": "soccer_france_ligue_one",
    # Belgium First Division
    "Club Brugge": "soccer_belgium_first_div",
    "Anderlecht": "soccer_belgium_first_div",
    # Austria Bundesliga
    "Red Bull Salzburg": "soccer_austria_bundesliga",
    "Austria Wien": "soccer_austria_bundesliga",
    # Netherlands Eredivisie
    "Ajax": "soccer_netherlands_eredivisie",
    "PSV": "soccer_netherlands_eredivisie",
    "Feyenoord": "soccer_netherlands_eredivisie",
    "Ajax Amsterdam": "soccer_netherlands_eredivisie",
    "PSV Eindhoven": "soccer_netherlands_eredivisie",
}


# ============================================
# TEAM NAME NORMALIZATION
# ============================================


def normalize_team_name(team_name: str) -> str:
    """
    Normalize team name by removing common suffixes and prefixes.

    This ensures that team names from The-Odds-API (which often include
    suffixes like "FC", "SK", "Club", etc.) can be matched against
    the mapping dictionaries.

    Args:
        team_name: Raw team name from The-Odds-API

    Returns:
        Normalized team name suitable for mapping lookup
    """
    # Remove common suffixes
    ignore_terms = [" FC", " SK", " Club", " AS", " AC", " FK", " SC", " Calcio", " Spor"]
    clean = team_name
    for term in ignore_terms:
        clean = clean.replace(term, "")
    return clean.strip()


# ============================================
# ENRICHMENT FUNCTIONS
# ============================================


def get_twitter_handle(team_name: str) -> Optional[str]:
    """
    Get Twitter handle for a team.

    Args:
        team_name: Team name from The-Odds-API

    Returns:
        Twitter handle (e.g., @GalatasaraySK) or None
    """
    # Direct lookup
    if team_name in TEAM_TWITTER_HANDLES:
        return TEAM_TWITTER_HANDLES[team_name]

    # Try case-insensitive lookup
    team_lower = team_name.lower()
    for name, handle in TEAM_TWITTER_HANDLES.items():
        if name.lower() == team_lower:
            return handle

    # Try with normalized team name (remove suffixes like "FC", "SK", etc.)
    normalized_name = normalize_team_name(team_name)
    if normalized_name != team_name:
        # Try direct lookup with normalized name
        if normalized_name in TEAM_TWITTER_HANDLES:
            return TEAM_TWITTER_HANDLES[normalized_name]

        # Try case-insensitive lookup with normalized name
        normalized_lower = normalized_name.lower()
        for name, handle in TEAM_TWITTER_HANDLES.items():
            if name.lower() == normalized_lower:
                return handle

    return None


def get_telegram_channel(team_name: str) -> Optional[str]:
    """
    Get Telegram channel for a team.

    Args:
        team_name: Team name from The-Odds-API

    Returns:
        Telegram channel name (e.g., 'galatasaray') or None
    """
    # Direct lookup
    if team_name in TEAM_TELEGRAM_CHANNELS:
        return TEAM_TELEGRAM_CHANNELS[team_name]

    # Try case-insensitive lookup
    team_lower = team_name.lower()
    for name, channel in TEAM_TELEGRAM_CHANNELS.items():
        if name.lower() == team_lower:
            return channel

    # Try with normalized team name (remove suffixes like "FC", "SK", etc.)
    normalized_name = normalize_team_name(team_name)
    if normalized_name != team_name:
        # Try direct lookup with normalized name
        if normalized_name in TEAM_TELEGRAM_CHANNELS:
            return TEAM_TELEGRAM_CHANNELS[normalized_name]

        # Try case-insensitive lookup with normalized name
        normalized_lower = normalized_name.lower()
        for name, channel in TEAM_TELEGRAM_CHANNELS.items():
            if name.lower() == normalized_lower:
                return channel

    return None


def get_fotmob_id(team_name: str) -> Optional[int]:
    """
    Get FotMob ID for a team.

    This integrates with src/ingestion/fotmob_team_mapping.py
    but provides a local cache for faster access.

    Args:
        team_name: Team name from The-Odds-API

    Returns:
        FotMob team ID or None
    """
    # Direct lookup
    if team_name in TEAM_FOTMOB_IDS:
        return TEAM_FOTMOB_IDS[team_name]

    # Try case-insensitive lookup
    team_lower = team_name.lower()
    for name, fotmob_id in TEAM_FOTMOB_IDS.items():
        if name.lower() == team_lower:
            return fotmob_id

    # Try with normalized team name (remove suffixes like "FC", "SK", etc.)
    normalized_name = normalize_team_name(team_name)
    if normalized_name != team_name:
        # Try direct lookup with normalized name
        if normalized_name in TEAM_FOTMOB_IDS:
            return TEAM_FOTMOB_IDS[normalized_name]

        # Try case-insensitive lookup with normalized name
        normalized_lower = normalized_name.lower()
        for name, fotmob_id in TEAM_FOTMOB_IDS.items():
            if name.lower() == normalized_lower:
                return fotmob_id

    # Fallback to fotmob_team_mapping.py
    try:
        from src.ingestion.fotmob_team_mapping import get_fotmob_team_id

        return get_fotmob_team_id(team_name)
    except ImportError:
        logger.warning("fotmob_team_mapping not available")
        return None


def get_team_country(team_name: str) -> Optional[str]:
    """
    Get country for a team.

    Args:
        team_name: Team name from The-Odds-API

    Returns:
        Country key (e.g., 'turkey', 'argentina') or None
    """
    # Direct lookup
    if team_name in TEAM_TO_COUNTRY:
        return TEAM_TO_COUNTRY[team_name]

    # Try case-insensitive lookup
    team_lower = team_name.lower()
    for name, country in TEAM_TO_COUNTRY.items():
        if name.lower() == team_lower:
            return country

    # Try with normalized team name (remove suffixes like "FC", "SK", etc.)
    normalized_name = normalize_team_name(team_name)
    if normalized_name != team_name:
        # Try direct lookup with normalized name
        if normalized_name in TEAM_TO_COUNTRY:
            return TEAM_TO_COUNTRY[normalized_name]

        # Try case-insensitive lookup with normalized name
        normalized_lower = normalized_name.lower()
        for name, country in TEAM_TO_COUNTRY.items():
            if name.lower() == normalized_lower:
                return country

    return None


def get_team_league(team_name: str) -> Optional[str]:
    """
    Get league for a team.

    Args:
        team_name: Team name from The-Odds-API

    Returns:
        League key (e.g., 'soccer_turkey_super_league') or None
    """
    # Direct lookup
    if team_name in TEAM_TO_LEAGUE:
        return TEAM_TO_LEAGUE[team_name]

    # Try case-insensitive lookup
    team_lower = team_name.lower()
    for name, league in TEAM_TO_LEAGUE.items():
        if name.lower() == team_lower:
            return league

    # Try with normalized team name (remove suffixes like "FC", "SK", etc.)
    normalized_name = normalize_team_name(team_name)
    if normalized_name != team_name:
        # Try direct lookup with normalized name
        if normalized_name in TEAM_TO_LEAGUE:
            return TEAM_TO_LEAGUE[normalized_name]

        # Try case-insensitive lookup with normalized name
        normalized_lower = normalized_name.lower()
        for name, league in TEAM_TO_LEAGUE.items():
            if name.lower() == normalized_lower:
                return league

    return None


def enrich_team_alias_data(team_name: str) -> Dict[str, Any]:
    """
    Enrich TeamAlias data with all available information.

    This function gathers all available enrichment data for a team
    and returns it as a dictionary.

    Args:
        team_name: Team name from The-Odds-API

    Returns:
        Dictionary with enriched data:
        {
            'twitter_handle': str or None,
            'telegram_channel': str or None,
            'fotmob_id': int or None,
            'country': str or None,
            'league': str or None
        }
    """
    return {
        "twitter_handle": get_twitter_handle(team_name),
        "telegram_channel": get_telegram_channel(team_name),
        "fotmob_id": get_fotmob_id(team_name),
        "country": get_team_country(team_name),
        "league": get_team_league(team_name),
    }


def add_team_mapping(
    team_name: str,
    twitter_handle: Optional[str] = None,
    telegram_channel: Optional[str] = None,
    fotmob_id: Optional[int] = None,
    country: Optional[str] = None,
    league: Optional[str] = None,
) -> None:
    """
    Add or update team mappings at runtime.

    This allows dynamic addition of team mappings without
    modifying the source code.

    Args:
        team_name: Team name from The-Odds-API
        twitter_handle: Optional Twitter handle
        telegram_channel: Optional Telegram channel
        fotmob_id: Optional FotMob ID
        country: Optional country key
        league: Optional league key
    """
    if twitter_handle:
        TEAM_TWITTER_HANDLES[team_name] = twitter_handle
        logger.info(f"Added Twitter handle for {team_name}: {twitter_handle}")

    if telegram_channel:
        TEAM_TELEGRAM_CHANNELS[team_name] = telegram_channel
        logger.info(f"Added Telegram channel for {team_name}: {telegram_channel}")

    if fotmob_id:
        TEAM_FOTMOB_IDS[team_name] = fotmob_id
        logger.info(f"Added FotMob ID for {team_name}: {fotmob_id}")

    if country:
        TEAM_TO_COUNTRY[team_name] = country
        logger.info(f"Added country for {team_name}: {country}")

    if league:
        TEAM_TO_LEAGUE[team_name] = league
        logger.info(f"Added league for {team_name}: {league}")


def get_all_mapped_teams() -> List[str]:
    """
    Get list of all teams with at least one mapping.

    Returns:
        List of team names that have at least one mapping
    """
    all_teams = set()
    all_teams.update(TEAM_TWITTER_HANDLES.keys())
    all_teams.update(TEAM_TELEGRAM_CHANNELS.keys())
    all_teams.update(TEAM_FOTMOB_IDS.keys())
    all_teams.update(TEAM_TO_COUNTRY.keys())
    all_teams.update(TEAM_TO_LEAGUE.keys())

    return sorted(list(all_teams))


def get_team_mapping_stats() -> Dict[str, int]:
    """
    Get statistics about team mappings.

    Returns:
        Dictionary with mapping counts:
        {
            'total_teams': int,
            'twitter_handles': int,
            'telegram_channels': int,
            'fotmob_ids': int,
            'countries': int,
            'leagues': int
        }
    """
    all_teams = get_all_mapped_teams()

    return {
        "total_teams": len(all_teams),
        "twitter_handles": len(TEAM_TWITTER_HANDLES),
        "telegram_channels": len(TEAM_TELEGRAM_CHANNELS),
        "fotmob_ids": len(TEAM_FOTMOB_IDS),
        "countries": len(TEAM_TO_COUNTRY),
        "leagues": len(TEAM_TO_LEAGUE),
    }
