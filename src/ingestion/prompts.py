"""
EarlyBird Shared Prompts V4.6

Centralized prompt templates for AI providers (Gemini, Perplexity).
Ensures identical behavior across providers.

V4.6: Removed OUTPUT FORMAT blocks - now handled by structured outputs system prompts.
V4.5: Added NEWS_VERIFICATION_PROMPT for Gemini news confirmation.
V4.5: Added BISCOTTO_CONFIRMATION_PROMPT for uncertain biscotto signals.
V4.4: Added BETTING_STATS_PROMPT for corners/cards data enrichment.

Note: Unicode normalization functions removed - use src.utils.text_normalizer
"""

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
    missing_players: str | None = None,
    today_iso: str | None = None,
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
        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

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
        injury_section=injury_section,
    )

    return prompt


def build_betting_stats_prompt(
    home_team: str, away_team: str, league: str, match_date: str | None = None
) -> str:
    """
    Build the betting stats prompt for corners/cards data enrichment.

    Args:
        home_team: Home team name
        away_team: Away team name
        league: League name
        match_date: Match date string (optional)

    Returns:
        Formatted prompt string for betting stats analysis
    """
    # This is a placeholder - the actual template would be defined above
    # For now, return a basic prompt structure
    date_str = f" scheduled for {match_date}" if match_date else ""
    return f"""TASK: Analyze betting statistics for the match {home_team} vs {away_team} in {league}{date_str}.

Focus on:
1. Average corners per match for both teams (home and away)
2. Average yellow cards per match for both teams
3. Recent trends in corners and cards
4. Referee tendencies for this match

Provide specific numbers and trends."""


def build_news_verification_prompt(
    news_title: str,
    news_snippet: str,
    team_name: str,
    news_source: str,
    match_context: str,
) -> str:
    """
    Build the news verification prompt for AI news confirmation.

    Args:
        news_title: Title of the news article
        news_snippet: Snippet or summary of the news content
        team_name: Name of the football team to verify against
        news_source: Source of the news (e.g., Twitter handle, website)
        match_context: Context about the match (optional, for additional verification)

    Returns:
        Formatted prompt string for news verification
    """
    # Build intelligent verification prompt using all available context
    context_section = f"\nMatch Context: {match_context}" if match_context else ""

    return f"""TASK: Verify the following news article for authenticity and relevance to {team_name}.

Title: {news_title}
Snippet: {news_snippet}
Source: {news_source}{context_section}

Please verify:
1. Is this news current and relevant to {team_name}?
2. Is the source reliable and trustworthy?
3. Does the news actually refer to the MEN'S FIRST TEAM (not women's or youth)?
4. Is the news about FOOTBALL (soccer), not basketball or other sports?
5. Does this news impact the upcoming match (injuries, motivation, tactics)?

Return your verification with:
- status: "VERIFIED" or "REJECTED" or "UNCERTAIN"
- confidence: 0.0 to 1.0
- reasoning: Brief explanation
- impact: "HIGH" or "MEDIUM" or "LOW" (if verified)"""


def build_biscotto_confirmation_prompt(
    home_team: str,
    away_team: str,
    match_date: str,
    league: str,
    draw_odds: float,
    implied_prob: float,
    odds_pattern: str,
    season_context: str,
    detected_factors: str,
) -> str:
    """
    Build the biscotto confirmation prompt for uncertain biscotto signals.

    Args:
        home_team: Home team name
        away_team: Away team name
        match_date: Date of the match
        league: League name
        draw_odds: Current draw odds
        implied_prob: Implied probability of draw (0.0 to 1.0)
        odds_pattern: Pattern in odds movement (e.g., "dropping", "stable", "rising")
        season_context: Context about the season (e.g., "final matchday", "mid-season")
        detected_factors: Factors that triggered biscotto detection

    Returns:
        Formatted prompt string for biscotto confirmation
    """
    # Build intelligent analysis prompt using all available data
    factors_section = f"\nDetected Factors: {detected_factors}" if detected_factors else ""

    return f"""TASK: Analyze the potential for a "Biscotto" (mutual draw benefit) in this match.

Match Details:
- Teams: {home_team} vs {away_team}
- Date: {match_date}
- League: {league}
- Draw Odds: {draw_odds}
- Implied Probability: {implied_prob:.1%}
- Odds Pattern: {odds_pattern}
- Season Context: {season_context}{factors_section}

Please analyze:
1. Does a draw benefit BOTH teams equally?
2. What are each team's current objectives (title race, relegation, European spots)?
3. Is this a critical matchday (final round, decisive moment)?
4. Are there historical precedents of biscotto in this league?
5. Does the odds pattern suggest suspicious activity?
6. What is the motivation level for each team (HIGH/MEDIUM/LOW)?
7. Are there any external factors (injuries, suspensions, manager issues)?

Return your analysis with:
- biscotto_confidence: 0.0 to 1.0 (probability of true biscotto)
- severity: "CRITICAL" or "HIGH" or "MEDIUM" or "LOW"
- reasoning: Detailed explanation of your analysis
- recommendation: "ALERT" or "MONITOR" or "IGNORE" """


def build_match_context_enrichment_prompt(
    home_team: str,
    away_team: str,
    match_date: str,
    league: str,
    existing_context: str,
) -> str:
    """
    Build the match context enrichment prompt.

    Args:
        home_team: Home team name
        away_team: Away team name
        match_date: Date of the match
        league: League name
        existing_context: Existing context to build upon (if any)

    Returns:
        Formatted prompt string for match context enrichment
    """
    # Build intelligent enrichment prompt using all available data
    context_section = f"\nExisting Context:\n{existing_context}" if existing_context else ""

    return f"""TASK: Enrich the context for the match {home_team} vs {away_team}.

Match Details:
- Date: {match_date}
- League: {league}{context_section}

Please provide comprehensive analysis:

1. **Recent Form Trends**:
   - Last 5 matches for {home_team} (results, goals scored/conceded)
   - Last 5 matches for {away_team} (results, goals scored/conceded)
   - Home/away performance patterns

2. **Head-to-Head History**:
   - Last 5 meetings between these teams
   - Common patterns (high scoring, draws, etc.)
   - Home advantage factor

3. **Key Player News**:
   - Injuries for both teams (key players only)
   - Suspensions
   - Recent transfers or returns
   - Player form/momentum

4. **Tactical Considerations**:
   - Playing styles of both teams
   - Tactical matchups
   - Managerial approaches
   - Formation preferences

5. **External Factors**:
   - Weather forecast (if available)
   - Pitch conditions
   - Crowd atmosphere expectations
   - Motivation levels (title race, relegation, etc.)

Return structured JSON with all categories filled."""
