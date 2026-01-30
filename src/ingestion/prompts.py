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
