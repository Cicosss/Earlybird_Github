"""
EarlyBird Shared Prompts V4.6

Centralized prompt templates for AI providers (Gemini, Perplexity).
Ensures identical behavior across providers.

V4.6: Removed OUTPUT FORMAT blocks - now handled by structured outputs system prompts.
V4.5: Added NEWS_VERIFICATION_PROMPT for Gemini news confirmation.
V4.5: Added BISCOTTO_CONFIRMATION_PROMPT for uncertain biscotto signals.
V4.4: Added BETTING_STATS_PROMPT for corners/cards data enrichment.

Phase 1 Critical Fix: Added Unicode normalization and safe UTF-8 truncation
"""
import unicodedata


def normalize_unicode(text: str) -> str:
    """
    Normalize Unicode to NFC form for consistent text handling.
    
    Phase 1 Critical Fix: Ensures special characters from Turkish, Polish,
    Greek, Arabic, Chinese, Japanese, Korean, and other languages
    are handled consistently across all components.
    
    Args:
        text: Input text to normalize
        
    Returns:
        Normalized text in NFC form
    """
    if not text:
        return ""
    return unicodedata.normalize('NFC', text)


def truncate_utf8(text: str, max_bytes: int) -> str:
    """
    Truncate text to fit within max_bytes UTF-8 encoded.
    
    Phase 1 Critical Fix: Safe truncation that preserves UTF-8 characters
    instead of cutting at arbitrary byte positions which can corrupt
    multi-byte characters.
    
    Args:
        text: Input text to truncate
        max_bytes: Maximum bytes in UTF-8 encoding
        
    Returns:
        Truncated text with valid UTF-8 characters
    """
    if not text:
        return ""
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return text
    # Truncate and decode, removing incomplete characters
    truncated = encoded[:max_bytes].decode('utf-8', errors='ignore')
    return truncated
 
# Deep Dive Analysis Prompt Template
# Used by: GeminiAgentProvider, PerplexityProvider
DEEP_DIVE_PROMPT_TEMPLATE = """CONTEXT: Today is {today_iso}.
 
TASK: Analyze the football match {home_team} vs {away_team} scheduled for {date_str}.
 
IMPORTANT: Verify the news refers to FOOTBALL (Soccer) team. Teams like {home_team}/{away_team} may have Basketball squads. Ignore Basketball news completely.
 
VERIFY GENDER: Ignore news about Women's team / Ladies squad. Focus strictly on Men's First Team.
 
ACTIONS:
1. Search local news (in native language) for: Unpaid wages, Player Strikes, Manager Fights.
2. Search for "Tactical Turnover": Is the manager resting players for a Cup match?
3. Check Referee {referee_str}: Avg Yellow Cards? Strict or Lenient?
4. Check "Biscotto": Does a DRAW help both teams?
5. **MOTIVATION ANALYSIS:** Determine motivation level for EACH team:
    - HIGH: Title race, Relegation battle, Cup Final, Derby, Golden Boot contender playing
    - MEDIUM: European spots, Playoff positions
    - LOW: Mid-table safe, Nothing to play for, Dead rubber, End of season friendly
{injury_section}
"""
 
# Injury Impact Section Template (appended when missing_players provided)
INJURY_SECTION_TEMPLATE = """
5. **INJURY IMPACT:** Analyze these missing players: {players_str}.
    For each player, verify:
    - Role: Starter or Bench player?
    - Importance: Captain? Top Scorer? Key Defender?
    - VERDICT: Critical (team significantly weakened) or Manageable (adequate replacements)?
    Output as: "injury_impact": "Critical/Manageable - [Player]: [Role], [Importance]. [Overall assessment]"

6. **BTTS TACTICAL ANALYSIS (CRITICAL):**
    Analyze the missing players BY POSITION for BTTS (Both Teams To Score) impact:
    - Missing KEY DEFENDERS or GOALKEEPER → INCREASES BTTS chance (weaker defense = more goals conceded)
    - Missing KEY STRIKERS or PLAYMAKERS → DECREASES BTTS chance (weaker attack = fewer goals scored)

    Output as: "btts_impact": "Positive/Negative/Neutral - [Explanation]. Net effect: [team] more/less likely to score/concede."
"""


# ============================================
# PROMPT BUILDER FUNCTIONS
# ============================================


def build_deep_dive_prompt(
    home_team: str,
    away_team: str,
    match_date: str,
    referee: str,
    missing_players: Optional[str] = None,
    today_iso: Optional[str] = None
) -> str:
    """
    Build the deep dive analysis prompt with optional injury section.
    
    Args:
        home_team: Home team name
        away_team: Away team name
        match_date: Match date string (called 'match_date' by callers)
        referee: Referee name/info (called 'referee' by callers)
        missing_players: Optional string of missing players for injury analysis
        today_iso: Today's date in ISO format (defaults to current date)
    
    Returns:
        Formatted prompt string for deep dive analysis
    """
    from datetime import datetime, timezone
    
    if today_iso is None:
        today_iso = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    # Build injury section if missing players provided
    injury_section = ""
    if missing_players:
        injury_section = INJURY_SECTION_TEMPLATE.format(players_str=missing_players)
    
    # Format the main prompt
    prompt = DEEP_DIVE_PROMPT_TEMPLATE.format(
        today_iso=today_iso,
        home_team=home_team,
        away_team=away_team,
        date_str=match_date,
        referee_str=referee,
        injury_section=injury_section
    )
    
    return prompt


def build_betting_stats_prompt(
    home_team: str,
    away_team: str,
    league: str
) -> str:
    """
    Build the betting stats prompt for corners/cards data enrichment.

    Args:
        home_team: Home team name
        away_team: Away team name
        league: League name

    Returns:
        Formatted prompt string for betting stats analysis
    """
    # This is a placeholder - the actual template would be defined above
    # For now, return a basic prompt structure
    return f"""TASK: Analyze betting statistics for the match {home_team} vs {away_team} in {league}.

Focus on:
1. Average corners per match for both teams (home and away)
2. Average yellow cards per match for both teams
3. Recent trends in corners and cards
4. Referee tendencies for this match

Provide specific numbers and trends."""


def build_news_verification_prompt(
    news_title: str,
    news_summary: str,
    source_url: str
) -> str:
    """
    Build the news verification prompt for Gemini news confirmation.

    Args:
        news_title: Title of the news article
        news_summary: Summary of the news
        source_url: URL of the source

    Returns:
        Formatted prompt string for news verification
    """
    # This is a placeholder - the actual template would be defined above
    return f"""TASK: Verify the following news article for authenticity and relevance.

Title: {news_title}
Summary: {news_summary}
Source: {source_url}

Please verify:
1. Is this news current and relevant?
2. Is the source reliable?
3. Does the news actually refer to the football match in question?

Return your verification status and confidence level."""


def build_biscotto_confirmation_prompt(
    home_team: str,
    away_team: str,
    league: str,
    league_position_home: int,
    league_position_away: int
) -> str:
    """
    Build the biscotto confirmation prompt for uncertain biscotto signals.

    Args:
        home_team: Home team name
        away_team: Away team name
        league: League name
        league_position_home: Home team's league position
        league_position_away: Away team's league position

    Returns:
        Formatted prompt string for biscotto confirmation
    """
    # This is a placeholder - the actual template would be defined above
    return f"""TASK: Analyze the potential for a "Biscotto" (mutual draw benefit) in this match.

Match: {home_team} vs {away_team}
League: {league}
Home Team Position: {league_position_home}
Away Team Position: {league_position_away}

Please analyze:
1. Does a draw benefit both teams?
2. What are each team's current objectives?
3. Is there historical evidence of such arrangements?
4. What is the confidence level of this being a true biscotto?

Return your analysis with severity level and confidence."""


def build_match_context_enrichment_prompt(
    home_team: str,
    away_team: str,
    league: str
) -> str:
    """
    Build the match context enrichment prompt.

    Args:
        home_team: Home team name
        away_team: Away team name
        league: League name

    Returns:
        Formatted prompt string for match context enrichment
    """
    # This is a placeholder - the actual template would be defined above
    return f"""TASK: Enrich the context for the match {home_team} vs {away_team} in {league}.

Please provide:
1. Recent form trends for both teams
2. Head-to-head history
3. Key player news
4. Any tactical considerations
5. Weather forecast if available

Return structured data for each category."""
