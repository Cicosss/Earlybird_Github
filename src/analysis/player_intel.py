import os
import logging
import requests
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()

# Import from centralized settings (with fallback)
try:
    from config.settings import API_FOOTBALL_KEY
except ImportError:
    API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")

API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"

def check_player_status(player_last_name: str, team_name: str, season: int = 2024) -> Optional[Dict]:
    """
    Check if a player is a key player by querying API-Football.
    
    Args:
        player_last_name: Last name of the player to search
        team_name: Name of the team (for filtering results)
        season: Season year (default: 2024)
    
    Returns:
        Dict with keys: 'is_key', 'stats_summary', 'role', 'player_name'
        None if player not found or API error
    """
    
    if not API_FOOTBALL_KEY or API_FOOTBALL_KEY == "YOUR_API_FOOTBALL_KEY":
        logging.warning("API-Football key not configured. Skipping player intelligence check.")
        return None
    
    headers = {
        'x-rapidapi-key': API_FOOTBALL_KEY,
        'x-rapidapi-host': 'v3.football.api-sports.io'
    }
    
    try:
        # Search for player
        url = f"{API_FOOTBALL_BASE_URL}/players"
        params = {
            'search': player_last_name,
            'season': season
        }
        
        logging.info(f"Searching player: {player_last_name} in season {season}")
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code != 200:
            logging.error(f"API-Football error: {response.status_code} - {response.text}")
            return None
        
        data = response.json()
        
        if not data.get('response') or len(data['response']) == 0:
            logging.warning(f"No player found for: {player_last_name}")
            return None
        
        # Filter by team (fuzzy match)
        team_lower = team_name.lower().strip()
        matching_player = None
        
        for player_data in data['response']:
            player_info = player_data.get('player', {})
            stats_list = player_data.get('statistics', [])
            
            if not stats_list:
                continue
            
            # Check if any of the player's teams match
            for stat in stats_list:
                team_data = stat.get('team', {})
                current_team = team_data.get('name', '').lower()
                
                # Fuzzy match: check if team_name is contained or vice versa
                if team_lower in current_team or current_team in team_lower:
                    matching_player = {
                        'info': player_info,
                        'stats': stat
                    }
                    break
            
            if matching_player:
                break
        
        if not matching_player:
            logging.warning(f"Player {player_last_name} found, but not for team {team_name}")
            return None
        
        # Extract stats
        player_info = matching_player['info']
        stats = matching_player['stats']
        
        player_name = player_info.get('name', player_last_name)
        games = stats.get('games', {})
        goals = stats.get('goals', {})
        
        appearances = games.get('appearences', 0) or 0
        lineups = games.get('lineups', 0) or 0
        total_goals = goals.get('total', 0) or 0
        
        # Calculate if key player
        is_key = False
        role = "Reserve"
        
        if lineups > 15 or total_goals > 5:
            is_key = True
            role = "Key Player"
        elif lineups > 10:
            role = "Regular Starter"
        elif appearances > 10:
            role = "Rotation Player"
        
        # Build stats summary
        stats_summary = f"{player_name}: {lineups} titolare, {total_goals} gol"
        
        logging.info(f"Player Intel: {player_name} - {role} (Lineups: {lineups}, Goals: {total_goals})")
        
        return {
            'is_key': is_key,
            'stats_summary': stats_summary,
            'role': role,
            'player_name': player_name,
            'lineups': lineups,
            'goals': total_goals,
            'appearances': appearances
        }
        
    except Exception as e:
        logging.error(f"Error checking player status: {e}")
        return None
