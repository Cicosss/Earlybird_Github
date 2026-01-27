import logging
from typing import Optional, List, Dict
from src.analysis.player_intel import check_player_status
from src.analysis.image_ocr import process_squad_image, extract_player_names

def get_top_key_players(team_name: str, count: int = 3) -> List[Dict]:
    """
    Get top N key players for a team using API-Football.
    
    Args:
        team_name: Team name to search
        count: Number of top players to return
    
    Returns:
        List of player dicts with name, role, stats
    """
    # This is a simplified version - ideally we'd query API-Football
    # for the team's top scorers/assisters directly
    # For now, we'll use a mock structure
    
    # In production, you'd call API-Football /players/topscorers endpoint
    # filtering by team_name and season
    
    # MOCK for demonstration
    logging.info(f"Fetching top key players for {team_name}")
    
    # Return empty list for now - will be populated dynamically in production
    return []

def analyze_squad_list(image_url: str, team_name: str, match_id: str) -> Optional[Dict]:
    """
    Analyze squad list image and detect if key players are missing.
    
    Args:
        image_url: URL of squad list image
        team_name: Team name
        match_id: Match ID
        
    Returns:
        Alert dict if critical player missing, None otherwise
    """
    # Keywords that indicate an official squad list
    SQUAD_KEYWORDS = [
        'KADRO',  # Turkish
        'SQUAD',  # English
        'FORMAZIONE',  # Italian
        'SKŁAD',  # Polish
        'CONVOCAȚI',  # Romanian
        'CONVOCADOS',  # Spanish
        'LINEUP',
        'STARTING XI',
        '11'
    ]
    
    try:
        # Step 1: Extract text from image
        ocr_text = process_squad_image(image_url)
        
        if not ocr_text:
            logging.warning("No text extracted from squad image")
            return None
        
        # Step 2: Check if it's actually a squad list
        is_squad_list = any(keyword in ocr_text for keyword in SQUAD_KEYWORDS)
        
        if not is_squad_list:
            logging.info("Image doesn't appear to be a squad list")
            return None
        
        logging.info(f"✅ Squad list detected for {team_name}")
        
        # Step 3: Extract player names from OCR
        detected_names = extract_player_names(ocr_text)
        logging.info(f"Detected {len(detected_names)} player names: {detected_names[:10]}")
        
        # Step 4: Get key players for this team
        # For MVP, we'll use a simpler approach: check predefined star players
        # In production, this would query API-Football for team's top scorers
        
        # HARDCODED KEY PLAYERS (MVP - Replace with API call)
        KEY_PLAYERS_DB = {
            'GALATASARAY': ['ICARDI', 'OSIMHEN', 'MUSLERA'],
            'BESIKTAS': ['IMMOBILE', 'RAFA SILVA', 'NDOUR'],
            'FENERBAHCE': ['DZEKO', 'TADIC', 'LIVAKOVIC'],
            'ALANYASPOR': ['HADEBE', 'CORDOVA'],
            # Add more teams as needed
        }
        
        team_upper = team_name.upper()
        key_players = []
        
        # Fuzzy match team name
        for team_key in KEY_PLAYERS_DB:
            if team_key in team_upper or team_upper in team_key:
                key_players = KEY_PLAYERS_DB[team_key]
                break
        
        if not key_players:
            logging.warning(f"No key players database entry for {team_name}")
            return None
        
        # Step 5: Check if any key player is MISSING
        missing_players = []
        
        for key_player in key_players:
            # Check if player's surname appears in the OCR text
            if key_player not in ocr_text:
                missing_players.append(key_player)
                logging.warning(f"🚨 KEY PLAYER MISSING: {key_player}")
        
        # Step 6: Generate alert if critical player missing
        if missing_players:
            return {
                'match_id': match_id,
                'team': team_name,
                'missing_players': missing_players,
                'detected_names': detected_names[:15],  # First 15 for logging
                'source': 'SQUAD_LIST_OCR',
                'score': 10,  # Maximum alert level
                'category': 'SQUAD_LIST_ALERT',
                'summary': f"⚠️ OFFICIAL SQUAD LIST: {', '.join(missing_players)} NOT CONVOCATED!",
                'url': image_url
            }
        
        logging.info(f"✅ All key players present in squad list")
        return None
        
    except Exception as e:
        logging.error(f"Error analyzing squad list: {e}")
        return None
