import logging
import os
from difflib import SequenceMatcher
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

# Import from centralized settings (with fallback)
try:
    from config.settings import API_FOOTBALL_KEY
except ImportError:
    API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")

API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"

# Simple in-memory cache for team+season data
_team_season_cache: Dict[tuple, List[Dict]] = {}


def normalize_name(name: str) -> str:
    """Normalize player name for matching."""
    if not name:
        return ""
    # Remove accents, convert to lowercase, strip
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [" jr", " sr", " ii", " iii"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    return name


def similarity(a: str, b: str) -> float:
    """Calculate string similarity (0-1)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def extract_lastname(full_name: str) -> str:
    """Extract last name from full name."""
    if not full_name:
        return ""
    parts = full_name.split()
    if len(parts) >= 2:
        return parts[-1]  # Last word is usually last name
    return full_name


def match_player(player_name: str, team_players: List[Dict]) -> Optional[tuple]:
    """
    Match a player name against a list of players.
    Returns (player_data, similarity_score) if similarity > 0.7, else (None, 0).
    """
    player_name_norm = normalize_name(player_name)
    player_lastname = extract_lastname(player_name_norm)

    best_match = None
    best_score = 0

    for player in team_players:
        player_info = player.get("player", {})
        player_full_name = player_info.get("name", "")
        player_firstname = player_info.get("firstname", "")
        player_lastname_api = player_info.get("lastname", "")

        # Try different matching strategies
        scores = []

        # 1. Full name match
        scores.append(similarity(player_name_norm, normalize_name(player_full_name)))

        # 2. Last name match
        scores.append(similarity(player_lastname, normalize_name(player_lastname_api)))

        # 3. First name + last name match
        if player_firstname:
            scores.append(
                similarity(
                    player_name_norm, normalize_name(f"{player_firstname} {player_lastname_api}")
                )
            )

        # Take best score for this player
        max_score = max(scores)

        if max_score > best_score:
            best_score = max_score
            best_match = player

    # Only return if similarity is above threshold
    if best_score > 0.7:
        return best_match, best_score
    return None, best_score


def is_key_player(stats: Dict) -> bool:
    """Determine if a player is a key player based on stats."""
    games = stats.get("games", {})
    goals = stats.get("goals", {})

    lineups = games.get("lineups", 0) or 0
    total_goals = goals.get("total", 0) or 0

    # Key player criteria: >15 lineups OR >5 goals
    return lineups > 15 or total_goals > 5


def get_player_role(stats: Dict) -> str:
    """Determine player role based on stats."""
    games = stats.get("games", {})
    goals = stats.get("goals", {})

    lineups = games.get("lineups", 0) or 0
    total_goals = goals.get("total", 0) or 0
    appearances = games.get("appeararences", 0) or 0

    if lineups > 15 or total_goals > 5:
        return "Key Player"
    elif lineups > 10:
        return "Regular Starter"
    elif appearances > 10:
        return "Rotation Player"
    else:
        return "Reserve"


def get_team_players_with_stats(team_id: int, season: int) -> Optional[List[Dict]]:
    """
    Get all players for a team and season with pagination.
    Uses in-memory cache to avoid repeated API calls.

    Args:
        team_id: API-Football team ID
        season: Season year

    Returns:
        List of player data with statistics, or None on error
    """
    # Check cache first
    cache_key = (team_id, season)
    if cache_key in _team_season_cache:
        logging.debug(f"Cache hit for team {team_id}, season {season}")
        return _team_season_cache[cache_key]

    if not API_FOOTBALL_KEY or API_FOOTBALL_KEY == "YOUR_API_FOOTBALL_KEY":
        logging.warning("API-Football key not configured. Skipping player intelligence check.")
        return None

    headers = {"x-rapidapi-key": API_FOOTBALL_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}

    try:
        all_players = []
        page = 1

        while True:
            logging.info(f"Fetching players for team {team_id}, season {season}, page {page}...")
            response = requests.get(
                f"{API_FOOTBALL_BASE_URL}/players",
                headers=headers,
                params={"team": team_id, "season": season, "page": page},
                timeout=15,
            )

            if response.status_code != 200:
                logging.error(f"API-Football error: {response.status_code} - {response.text}")
                return None

            data = response.json()
            players = data.get("response", [])

            if not players:
                break

            all_players.extend(players)
            logging.debug(f"Page {page}: {len(players)} players")

            if len(players) < 20:  # Last page
                break

            page += 1

        # Cache the results
        _team_season_cache[cache_key] = all_players
        logging.info(f"✅ Cached {len(all_players)} players for team {team_id}, season {season}")

        return all_players

    except Exception as e:
        logging.error(f"Error fetching team players: {e}")
        return None


def resolve_player_in_team(player_name: str, team_id: int, season: int) -> Optional[Dict]:
    """
    Resolve a player name within a team's roster.

    Args:
        player_name: Full name of the player
        team_id: API-Football team ID
        season: Season year

    Returns:
        Player data dictionary with statistics, or None if not found
    """
    # Get all players for the team
    team_players = get_team_players_with_stats(team_id, season)

    if not team_players:
        logging.warning(f"No players found for team {team_id}, season {season}")
        return None

    # Match player locally
    matched_player, match_score = match_player(player_name, team_players)

    if matched_player:
        player_info = matched_player.get("player", {})
        stats_list = matched_player.get("statistics", [])

        if stats_list:
            stats = stats_list[0]
            player_name_full = player_info.get("name", player_name)

            logging.info(f"✅ Player matched: {player_name_full} (similarity: {match_score:.2f})")

            return {"player_info": player_info, "stats": stats, "match_score": match_score}

    logging.warning(
        f"Player '{player_name}' not found in team {team_id} roster "
        f"(best match score: {match_score:.2f})"
    )
    return None


def check_player_status(player_name: str, team_id: int, season: int = 2024) -> Optional[Dict]:
    """
    Check if a player is a key player by querying API-Football.

    NEW APPROACH (V2): Uses team+season with local name matching
    instead of search parameter which doesn't work reliably.

    Args:
        player_name: Full name of the player
        team_id: API-Football team ID
        season: Season year (default: 2024)

    Returns:
        Dict with keys: 'is_key', 'stats_summary', 'role', 'player_name',
        'lineups', 'goals', 'appearances', 'match_score'
        None if player not found or API error
    """
    # Resolve player in team roster
    result = resolve_player_in_team(player_name, team_id, season)

    if not result:
        return None

    player_info = result["player_info"]
    stats = result["stats"]
    match_score = result["match_score"]

    # Extract stats
    player_name_full = player_info.get("name", player_name)
    games = stats.get("games", {})
    goals = stats.get("goals", {})

    appearances = games.get("appeararences", 0) or 0
    lineups = games.get("lineups", 0) or 0
    total_goals = goals.get("total", 0) or 0

    # Calculate if key player
    is_key = is_key_player(stats)
    role = get_player_role(stats)

    # Build stats summary
    stats_summary = f"{player_name_full}: {lineups} titolare, {total_goals} gol"

    logging.info(
        f"Player Intel: {player_name_full} - {role} (Lineups: {lineups}, Goals: {total_goals})"
    )

    return {
        "is_key": is_key,
        "stats_summary": stats_summary,
        "role": role,
        "player_name": player_name_full,
        "lineups": lineups,
        "goals": total_goals,
        "appearances": appearances,
        "match_score": match_score,
    }


def clear_cache():
    """Clear the in-memory cache for team+season data."""
    global _team_season_cache
    _team_season_cache.clear()
    logging.info("Player intelligence cache cleared")
