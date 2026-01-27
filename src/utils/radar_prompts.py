"""
News Radar Prompts V2.0

Optimized prompts for high-value betting signal extraction.
Designed to work with any language (DeepSeek handles multilingual natively).

Key changes from V1:
- Focus on STRUCTURED extraction (team, count, match)
- Quality gate: reject if missing critical fields
- Explicit betting value assessment
- Italian output for summary

V2.0: Complete rewrite based on real betting value analysis.
"""


def build_analysis_prompt_v2(content: str) -> str:
    """
    Build the V2 analysis prompt for DeepSeek.
    
    This prompt is designed to:
    1. Work with ANY language (DeepSeek handles multilingual)
    2. Extract STRUCTURED data (team, count, match, etc.)
    3. Apply strict quality gates
    4. Focus on HIGH-VALUE betting signals only
    
    Args:
        content: Raw content text (any language)
        
    Returns:
        Formatted prompt string
    """
    # Truncate content for prompt
    max_content = 12000
    if len(content) > max_content:
        content = content[:max_content]
    
    return f"""You are a sports betting analyst. Analyze this football news article (in ANY language) and extract betting-relevant information.

⚠️ CRITICAL: Only mark as relevant if there is REAL BETTING VALUE:
- 3+ first-team players unavailable = HIGH VALUE ✅
- Youth/reserve team playing = HIGH VALUE ✅
- Confirmed turnover/rotation = HIGH VALUE ✅
- Team decimated/emergency = HIGH VALUE ✅
- Financial crisis (unpaid wages, strike) = HIGH VALUE ✅
- Logistical problems (flight issues, late arrival) = MEDIUM VALUE ✅
- Goalkeeper unavailable = MEDIUM VALUE ✅
- 1-2 non-key players out = LOW VALUE ❌ (DO NOT ALERT)
- Player returning from injury = NO VALUE ❌ (DO NOT ALERT)
- General team news = NO VALUE ❌ (DO NOT ALERT)

❌ AUTOMATICALLY REJECT:
- Basketball, tennis, golf, cricket, rugby, NFL, handball
- Women's football
- Player RETURNING from injury (positive news)
- News about transfers, contracts, rumors without lineup impact
- Content that is navigation menu, login page, or garbage

ARTICLE TEXT:
{content}

Respond in JSON format ONLY (no markdown, no explanation):
{{
  "is_high_value": true/false,
  "team": "exact team name or null if cannot determine",
  "opponent": "opponent team name or null",
  "competition": "league/cup name or null",
  "match_date": "date if mentioned or null",
  "category": "MASS_ABSENCE|DECIMATED|YOUTH_TEAM|TURNOVER|FINANCIAL_CRISIS|LOGISTICAL_CRISIS|GOALKEEPER_OUT|MOTIVATION|CONFIRMED_LINEUP|LOW_VALUE|NOT_RELEVANT",
  "absent_count": number of players unavailable (0 if unknown),
  "absent_players": ["list", "of", "player", "names"] or [],
  "absent_reason": "injury|suspension|rotation|national_team|strike|lineup_confirmed|other",
  "betting_impact": "CRITICAL|HIGH|MEDIUM|LOW|NONE",
  "confidence": 0.0-1.0,
  "summary_italian": "Riepilogo in ITALIANO (max 250 caratteri) - focus sul fatto chiave per lo scommettitore"
}}

RULES:
1. is_high_value=true ONLY if betting_impact is CRITICAL, HIGH, or MEDIUM
2. team MUST be extracted - if you cannot determine the team, set is_high_value=false
3. absent_count >= 3 OR goalkeeper out OR youth team = HIGH/CRITICAL impact
4. absent_count = 1-2 (non-key players) = LOW impact = is_high_value=false
5. summary_italian must be in ITALIAN, concise, actionable for a bettor
6. If content is garbage (menu, login, etc.) = is_high_value=false, category=NOT_RELEVANT
7. confidence >= 0.8 for clear high-value signals"""


def build_quick_check_prompt(content: str) -> str:
    """
    Build a quick check prompt for initial filtering.
    
    Faster and cheaper than full analysis.
    Used to decide if content is worth full analysis.
    
    Args:
        content: Raw content text (any language)
        
    Returns:
        Formatted prompt string
    """
    # Use only first 3000 chars for quick check
    max_content = 3000
    if len(content) > max_content:
        content = content[:max_content]
    
    return f"""Quick check: Does this football news have betting value?

BETTING VALUE = lineup disruption (3+ players out, youth team, turnover, crisis)
NO VALUE = single player news, transfers, rumors, positive news (player returning)

TEXT:
{content}

Reply with ONLY one word: YES or NO"""


# Category mappings for display
# V2.1: Added V1 categories for backward compatibility
# V2.3: Added CONFIRMED_LINEUP for early lineup announcements
CATEGORY_EMOJI = {
    # V2 categories
    "MASS_ABSENCE": "🚨",
    "DECIMATED": "💥",
    "YOUTH_TEAM": "🧒",
    "TURNOVER": "🔄",
    "FINANCIAL_CRISIS": "💰",
    "LOGISTICAL_CRISIS": "✈️",
    "GOALKEEPER_OUT": "🧤",
    "MOTIVATION": "😴",
    "CONFIRMED_LINEUP": "📋",  # V2.3: Early lineup announcement
    "LOW_VALUE": "📉",
    "NOT_RELEVANT": "❌",
    # V1 categories (backward compatibility)
    "INJURY": "🏥",
    "SUSPENSION": "🟥",
    "NATIONAL_TEAM": "🌍",
    "CUP_ABSENCE": "🏆",
    "YOUTH_CALLUP": "🧒",
    "OTHER": "📰",
}

CATEGORY_ITALIAN = {
    # V2 categories
    "MASS_ABSENCE": "EMERGENZA ASSENZE",
    "DECIMATED": "SQUADRA DECIMATA",
    "YOUTH_TEAM": "FORMAZIONE GIOVANILE",
    "TURNOVER": "TURNOVER CONFERMATO",
    "FINANCIAL_CRISIS": "CRISI FINANZIARIA",
    "LOGISTICAL_CRISIS": "PROBLEMI LOGISTICI",
    "GOALKEEPER_OUT": "PORTIERE ASSENTE",
    "MOTIVATION": "MOTIVAZIONE BASSA",
    "CONFIRMED_LINEUP": "FORMAZIONE UFFICIALE",  # V2.3: Early lineup
    "LOW_VALUE": "BASSO VALORE",
    "NOT_RELEVANT": "NON RILEVANTE",
    # V1 categories (backward compatibility)
    "INJURY": "INFORTUNIO",
    "SUSPENSION": "SQUALIFICA",
    "NATIONAL_TEAM": "NAZIONALE",
    "CUP_ABSENCE": "ASSENZA COPPA",
    "YOUTH_CALLUP": "CONVOCAZIONE GIOVANILI",
    "OTHER": "ALTRO",
}

BETTING_IMPACT_EMOJI = {
    "CRITICAL": "🔥🔥🔥",
    "HIGH": "🔥🔥",
    "MEDIUM": "🔥",
    "LOW": "📉",
    "NONE": "❌",
}
