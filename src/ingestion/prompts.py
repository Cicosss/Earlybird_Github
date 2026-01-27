"""
EarlyBird Shared Prompts V4.6

Centralized prompt templates for AI providers (Gemini, Perplexity).
Ensures identical behavior across providers.

V4.6: Removed OUTPUT FORMAT blocks - now handled by structured outputs system prompts.
V4.5: Added NEWS_VERIFICATION_PROMPT for Gemini news confirmation.
V4.5: Added BISCOTTO_CONFIRMATION_PROMPT for uncertain biscotto signals.
V4.4: Added BETTING_STATS_PROMPT for corner/cards data enrichment.
"""

# Deep Dive Analysis Prompt Template
# Used by: GeminiAgentProvider, PerplexityProvider
DEEP_DIVE_PROMPT_TEMPLATE = """CONTEXT: Today is {today_iso}.

TASK: Analyze the football match {home_team} vs {away_team} scheduled for {date_str}.

IMPORTANT: Verify the news refers to the FOOTBALL (Soccer) team. Teams like {home_team}/{away_team} may have Basketball squads. Ignore Basketball news completely.

VERIFY GENDER: Ignore news about the Women's team / Ladies squad. Focus strictly on Men's First Team.

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


def build_deep_dive_prompt(
    home_team: str,
    away_team: str,
    match_date: str = None,
    referee: str = None,
    missing_players: list = None
) -> str:
    """
    Build the deep dive analysis prompt.
    
    Args:
        home_team: Home team name
        away_team: Away team name
        match_date: Match date (optional, YYYY-MM-DD format)
        referee: Referee name (optional)
        missing_players: List of missing player names (optional)
        
    Returns:
        Formatted prompt string
    """
    from datetime import datetime, timezone
    
    # ISO 8601 date format to avoid USA/EU ambiguity
    today_iso = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    date_str = match_date or "upcoming"
    referee_str = referee if referee and referee != "Unknown" else "the assigned referee"
    
    # Build injury section based on missing_players status
    injury_section = ""
    if missing_players and len(missing_players) > 0:
        # Players reported missing - analyze their impact
        players_str = ', '.join(missing_players[:10])  # Limit to 10 players
        injury_section = INJURY_SECTION_TEMPLATE.format(players_str=players_str)
    else:
        # No injuries reported - explicit message for AI clarity
        injury_section = """
5. **INJURY STATUS:** No major injuries or suspensions reported for either team.
   Output as: "injury_impact": "None reported - Both squads appear fully available."
   Output as: "btts_impact": "Neutral - No defensive/attacking absences to affect BTTS probability."
"""
    
    return DEEP_DIVE_PROMPT_TEMPLATE.format(
        today_iso=today_iso,
        home_team=home_team,
        away_team=away_team,
        date_str=date_str,
        referee_str=referee_str,
        injury_section=injury_section
    )


# ============================================
# BETTING STATS PROMPT (V4.4 - Corner/Cards Enrichment)
# ============================================
# Used when FotMob doesn't provide corner/cards data
# Called ONLY when a signal is about to be sent (score >= 8.2)
# to enrich the combo suggestion with statistical markets

BETTING_STATS_PROMPT_TEMPLATE = """CONTEXT: Today is {today_iso}.

TASK: Provide BETTING STATISTICS for the MEN'S FOOTBALL (Soccer) match:
⚽ {home_team} vs {away_team}
📅 Match Date: {match_date}
🏆 League: {league}

⚠️ CRITICAL FILTERS - EXCLUDE FROM SEARCH:
- Basketball / NBA / Euroleague / ACB statistics
- Women's team / Ladies / Femminile statistics
- Youth team / Primavera / U19 / U21 statistics
- NFL / American Football / Rugby
- Any sport other than Men's Football (Soccer)

I need SPECIFIC STATISTICS for betting markets. Search for recent season data about the MEN'S FIRST TEAM only.

REQUIRED DATA (search team statistics pages, league stats, betting sites):

1. **RECENT FORM (Last 5 matches):**
   - {home_team}: Wins, Draws, Losses in last 5 league matches
   - {away_team}: Wins, Draws, Losses in last 5 league matches
   - Goals scored and conceded in last 5 matches (if available)

2. **CORNERS STATISTICS:**
   - {home_team}: Average corners WON per home game (search: "{home_team} corners per game" or "{home_team} statistiche calci d'angolo")
   - {away_team}: Average corners WON per away game
   - Combined average corners in H2H matches (if available)
   - Playing style: Do they attack wide (= more corners) or through the middle?

3. **CARDS STATISTICS:**
   - {home_team}: Average yellow cards per game this season
   - {away_team}: Average yellow cards per game this season
   - Are they aggressive/physical teams? (fouls per game if available)

4. **REFEREE (if assigned):**
   - Search for the referee assigned to this match
   - If found: Average cards per game, reputation (strict/lenient)
   - If not found: Say "Referee not yet assigned"

5. **MATCH CONTEXT FOR CARDS:**
   - Is this a Derby? Rivalry? High-stakes match?
   - These factors INCREASE card probability

RULES:
- Use NUMBERS, not text for averages (e.g., 5.2 not "five point two")
- If you cannot find data, use null for that field
- Be CONSERVATIVE: only recommend bets if data confidence is Medium or High
- Corner line = combined average rounded to nearest .5 minus 0.5 (e.g., avg 10.2 → Over 9.5)
- Cards line = referee avg + team aggression factor
"""


def build_betting_stats_prompt(
    home_team: str,
    away_team: str,
    match_date: str,
    league: str = "Unknown"
) -> str:
    """
    Build prompt for corner/cards statistics enrichment.
    
    Called when a signal is confirmed (score >= 8.2) but FotMob
    didn't provide corner/cards data. Gemini will search for this data
    to enable better combo suggestions.
    
    Args:
        home_team: Home team name
        away_team: Away team name  
        match_date: Match date in YYYY-MM-DD format
        league: League name for context
        
    Returns:
        Formatted prompt string
    """
    from datetime import datetime, timezone
    
    today_iso = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    return BETTING_STATS_PROMPT_TEMPLATE.format(
        today_iso=today_iso,
        home_team=home_team,
        away_team=away_team,
        match_date=match_date or "upcoming",
        league=league or "Unknown"
    )


# ============================================
# NEWS VERIFICATION PROMPT (V4.5 - Gemini News Confirmation)
# ============================================
# Used to verify news items from scrapers before including in AI dossier.
# Called for news with MEDIUM/LOW confidence to confirm with Google Search.
# This prevents false positives from unreliable sources.

NEWS_VERIFICATION_PROMPT_TEMPLATE = """CONTEXT: Today is {today_iso}.

TASK: VERIFY this football news claim using Google Search.

TEAM: {team_name}
MATCH: {match_context}
NEWS CLAIM: "{news_title}"
DETAILS: "{news_snippet}"
SOURCE: {news_source}

⚠️ CRITICAL FILTERS - EXCLUDE FROM SEARCH:
- Basketball / NBA / Euroleague / ACB
- Women's team / Ladies / Femminile / Femenino
- Youth team / Primavera / U19 / U21 / Academy
- NFL / American Football
- Rugby / Cricket / Hockey
- eSports / FIFA video game
- Fantasy Football / FPL

VERIFICATION STEPS:
1. Search for this EXACT news on reliable sports sources (ESPN, Sky Sports, BBC Sport, official club sites)
2. Check if the claim is CONFIRMED, DENIED, or UNVERIFIED
3. Look for ADDITIONAL DETAILS not in the original claim
4. Check the TIMING - is this news still current or outdated?

IMPORTANT:
- Verify this is about the MEN'S FIRST TEAM FOOTBALL (Soccer) only
- IGNORE any results about basketball, women's team, youth teams
- Check if the player/situation mentioned actually exists
- Look for official club announcements

RULES:
- verified=true ONLY if you find the SAME news on at least 1 reliable source
- verified=false if you find CONTRADICTING information
- verification_status="UNVERIFIED" if you cannot find any confirmation
- verification_status="OUTDATED" if the news is old (player already recovered, etc.)
- Be CONSERVATIVE: when in doubt, mark as UNVERIFIED
"""


def build_news_verification_prompt(
    news_title: str,
    news_snippet: str,
    team_name: str,
    news_source: str = "Unknown",
    match_context: str = "upcoming match"
) -> str:
    """
    Build prompt for news verification via Gemini Google Search.
    
    Called for news items with MEDIUM/LOW confidence to verify
    the claim before including it in the AI dossier.
    
    Args:
        news_title: Title of the news article
        news_snippet: Snippet/summary of the news
        team_name: Team the news is about
        news_source: Original source of the news
        match_context: Match context (e.g., "vs Real Madrid on 2024-01-15")
        
    Returns:
        Formatted prompt string
    """
    from datetime import datetime, timezone
    
    today_iso = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    # Truncate long snippets to avoid token overflow
    snippet_truncated = news_snippet[:500] if news_snippet else ""
    title_truncated = news_title[:200] if news_title else "No title"
    
    return NEWS_VERIFICATION_PROMPT_TEMPLATE.format(
        today_iso=today_iso,
        team_name=team_name,
        match_context=match_context,
        news_title=title_truncated,
        news_snippet=snippet_truncated,
        news_source=news_source or "Unknown"
    )


# ============================================
# BISCOTTO CONFIRMATION PROMPT (V4.5 - Gemini Biscotto Verification)
# ============================================
# Used when BiscottoEngine detects a MEDIUM severity signal (uncertain).
# Gemini searches for additional context to confirm or deny the biscotto.
# This prevents false positives and increases confidence in real signals.

BISCOTTO_CONFIRMATION_PROMPT_TEMPLATE = """CONTEXT: Today is {today_iso}.

TASK: INVESTIGATE potential "Biscotto" (mutually beneficial draw) for this FOOTBALL match.

MATCH: {home_team} vs {away_team}
DATE: {match_date}
LEAGUE: {league}

⚠️ CRITICAL FILTERS - EXCLUDE FROM SEARCH:
- Basketball / NBA / Euroleague / ACB
- Women's team / Ladies / Femminile / Femenino
- Youth team / Primavera / U19 / U21
- NFL / American Football / Rugby
- Any sport other than Men's Football (Soccer)

CURRENT SIGNALS DETECTED:
- Draw Odds: {draw_odds} (implied probability: {implied_prob}%)
- Odds Movement: {odds_pattern}
- Season Context: {season_context}
{detected_factors}

A "Biscotto" is when both teams benefit from a draw (e.g., both avoid relegation, both qualify).
This is NOT illegal, but a statistical pattern worth betting on.

INVESTIGATION STEPS:
1. **LEAGUE TABLE CONTEXT:**
   - Search current standings for {league}
   - What does {home_team} need? (safety, promotion, nothing)
   - What does {away_team} need?
   - Would a DRAW help BOTH teams achieve their objective?

2. **HEAD-TO-HEAD HISTORY:**
   - Search H2H results between these teams in END-OF-SEASON matches
   - Have they drawn suspiciously often in final rounds before?
   - Any pattern of low-scoring draws?

3. **CLUB RELATIONSHIPS:**
   - Are there any known relationships between the clubs? (same owner, loan deals, friendly clubs)
   - Any recent news about agreements or cooperation?

4. **MANAGER STATEMENTS:**
   - Search for recent press conferences
   - Any hints about "taking a point" or "not risking"?
   - Any rotation/rest mentioned?

5. **BETTING MARKET ANALYSIS:**
   - Is the draw being heavily backed?
   - Any unusual betting patterns reported?

RULES:
- biscotto_confirmed=true ONLY if you find CLEAR evidence of mutual benefit
- confidence_boost: Add 10-30 points if confirmed, 0 if not
- Be SPECIFIC about what each team needs (points, position, etc.)
- Look for CONCRETE evidence, not speculation
- If uncertain, recommend MONITOR LIVE
"""


def build_biscotto_confirmation_prompt(
    home_team: str,
    away_team: str,
    match_date: str,
    league: str,
    draw_odds: float,
    implied_prob: float,
    odds_pattern: str,
    season_context: str,
    detected_factors: list = None
) -> str:
    """
    Build prompt for biscotto confirmation via Gemini Google Search.
    
    Called when BiscottoEngine detects a MEDIUM severity signal
    to gather additional context and confirm/deny the biscotto.
    
    Args:
        home_team: Home team name
        away_team: Away team name
        match_date: Match date in YYYY-MM-DD format
        league: League name
        draw_odds: Current draw odds
        implied_prob: Implied probability percentage
        odds_pattern: Pattern detected (DRIFT, CRASH, STABLE)
        season_context: End of season or not
        detected_factors: List of factors already detected
        
    Returns:
        Formatted prompt string
    """
    from datetime import datetime, timezone
    
    today_iso = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    # Format detected factors
    factors_str = ""
    if detected_factors:
        factors_str = "\nDetected Factors:\n" + "\n".join(f"  - {f}" for f in detected_factors[:5])
    
    return BISCOTTO_CONFIRMATION_PROMPT_TEMPLATE.format(
        today_iso=today_iso,
        home_team=home_team,
        away_team=away_team,
        match_date=match_date or "upcoming",
        league=league or "Unknown",
        draw_odds=f"{draw_odds:.2f}" if draw_odds else "N/A",
        implied_prob=f"{implied_prob:.0f}" if implied_prob else "N/A",
        odds_pattern=odds_pattern or "Unknown",
        season_context=season_context or "Unknown",
        detected_factors=factors_str
    )


# ============================================
# MATCH CONTEXT ENRICHMENT PROMPT (V4.5 - Phase 3)
# ============================================
# Used to enrich match context before DeepSeek analysis.
# Called ONLY for high_potential matches to gather fresh intel:
# - Recent form (last 5 matches)
# - Latest news from the week
# - Motivational context
# - H2H recent history
# - Weather impact

MATCH_CONTEXT_ENRICHMENT_PROMPT_TEMPLATE = """CONTEXT: Today is {today_iso}.

TASK: Provide FRESH CONTEXT for the MEN'S FOOTBALL (Soccer) match:
⚽ {home_team} vs {away_team}
📅 Match Date: {match_date}
🏆 League: {league}

⚠️ CRITICAL FILTERS - EXCLUDE FROM SEARCH:
- Basketball / NBA / Euroleague / ACB (teams like Real Madrid, Barcelona have basketball squads - IGNORE)
- Women's team / Ladies / Femminile / Femenino / NWSL
- Youth team / Primavera / U19 / U21 / Academy / Reserve
- NFL / American Football / Rugby / Cricket
- eSports / FIFA video game news
- Fantasy Football / FPL tips
- Transfer RUMORS without official confirmation

EXISTING CONTEXT (already gathered):
{existing_context}

I need ADDITIONAL FRESH INFORMATION to enrich the analysis. Search for recent data about the MEN'S FIRST TEAM only.

REQUIRED DATA:

1. **RECENT FORM (Last 5 matches):**
   - {home_team}: Results of last 5 matches (W/D/L format), points collected
   - {away_team}: Results of last 5 matches (W/D/L format), points collected
   - Trend: Improving, Declining, or Stable?

2. **LATEST NEWS (Last 7 days):**
   - {home_team}: Any significant news (injuries, transfers, internal issues, morale)
   - {away_team}: Any significant news
   - Focus on news that could affect match outcome

3. **HEAD-TO-HEAD RECENT:**
   - Last 5 meetings between these teams
   - Home/Away advantage pattern
   - Goals scored pattern

4. **MATCH IMPORTANCE:**
   - What's at stake for each team?
   - Is this a Derby? Rivalry? Cup match?
   - End of season implications?

5. **WEATHER FORECAST:**
   - Expected weather conditions for match day
   - Impact on playing style (rain = slower, wind = long balls less effective)

6. **MOTIVATIONAL FACTORS:**
   - Manager under pressure?
   - Contract situations?
   - Revenge factor from previous meetings?

RULES:
- Focus on FRESH information (last 7 days for news, current season for form)
- Be SPECIFIC with form results (use W/D/L format)
- If you cannot find data, use "Unknown" for that field
- Prioritize BETTING-RELEVANT information
- Keep summaries concise but informative
"""


def build_match_context_enrichment_prompt(
    home_team: str,
    away_team: str,
    match_date: str,
    league: str,
    existing_context: str = ""
) -> str:
    """
    Build prompt for match context enrichment via Gemini Google Search.
    
    Called for high_potential matches BEFORE DeepSeek analysis to gather
    fresh context: recent form, latest news, H2H, weather, motivation.
    
    Args:
        home_team: Home team name
        away_team: Away team name
        match_date: Match date in YYYY-MM-DD format
        league: League name for context
        existing_context: Already gathered context to avoid duplication
        
    Returns:
        Formatted prompt string
    """
    from datetime import datetime, timezone
    
    today_iso = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    # Truncate existing context to avoid token overflow
    context_truncated = existing_context[:1000] if existing_context else "None gathered yet"
    
    return MATCH_CONTEXT_ENRICHMENT_PROMPT_TEMPLATE.format(
        today_iso=today_iso,
        home_team=home_team,
        away_team=away_team,
        match_date=match_date or "upcoming",
        league=league or "Unknown",
        existing_context=context_truncated
    )
