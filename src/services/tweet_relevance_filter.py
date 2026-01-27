"""
EarlyBird Tweet Relevance Filter - V4.6

Intelligent filtering of Twitter Intel for match analysis.
Filters cached tweets to find only those relevant to a specific match,
applying freshness decay and relevance scoring.

FLOW:
1. Receive match context (home_team, away_team, league_key)
2. Search TwitterIntelCache for relevant tweets
3. Apply freshness decay (reusing market_intelligence logic)
4. Score and rank by relevance × freshness
5. Return top N tweets formatted for AI consumption

INTEGRATION:
- Called by analyzer.py before analyze_with_triangulation()
- Uses existing calculate_news_freshness_multiplier() for decay
- Outputs formatted string for injection into AI prompt

Author: EarlyBird V4.6
"""
import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================

# Freshness thresholds (hours)
TWEET_FRESH_THRESHOLD_HOURS = 6      # < 6h = FRESH
TWEET_AGING_THRESHOLD_HOURS = 24     # 6-24h = AGING
TWEET_STALE_THRESHOLD_HOURS = 72     # 24-72h = STALE (only if HIGH relevance)
TWEET_MAX_AGE_HOURS = 72             # > 72h = EXCLUDED

# Relevance scoring
RELEVANCE_INJURY = 1.0               # injury, infortunio, lesión
RELEVANCE_LINEUP = 0.9               # lineup, squad, convocati
RELEVANCE_TRANSFER = 0.7             # transfer, signing
RELEVANCE_GENERAL = 0.5              # general football news

# Output limits
MAX_TWEETS_PER_MATCH = 5             # Absolute max tweets to pass to AI
PREFERRED_TWEETS_COUNT = 3           # Preferred count if many available

# Team name aliases for fuzzy matching
# Populated dynamically from twitter_intel_accounts.py focus fields
TEAM_ALIASES: Dict[str, List[str]] = {
    # Turkey
    "galatasaray": ["gala", "gs", "cimbom", "galatasaray sk", "aslan"],
    "fenerbahce": ["fener", "fb", "fenerbahçe", "fenerbahce sk", "kanarya"],
    "besiktas": ["bjk", "beşiktaş", "kartal"],
    "trabzonspor": ["trabzon", "ts", "bordo mavi"],
    # Argentina
    "boca juniors": ["boca", "cabj", "xeneize"],
    "river plate": ["river", "carp", "millonario"],
    "independiente": ["rojo", "diablo rojo"],
    "racing club": ["racing", "academia"],
    # Mexico
    "club america": ["america", "aguilas", "las aguilas"],
    "cruz azul": ["cruz azul", "la maquina", "cementeros"],
    "chivas": ["guadalajara", "chivas", "rebano"],
    # Greece
    "olympiacos": ["olympiakos", "thrylos"],
    "panathinaikos": ["pao", "trifogli"],
    "aek athens": ["aek", "enosi"],
    "paok": ["paok", "dikefalos"],
    # Scotland
    "celtic": ["celtic", "bhoys", "hoops"],
    "rangers": ["rangers", "gers", "teddy bears"],
    "hearts": ["hearts", "jambos"],
    "hibernian": ["hibs", "hibees"],
    # Australia
    "melbourne victory": ["victory", "mv"],
    "sydney fc": ["sydney", "sky blues"],
    "western sydney": ["wanderers", "wsw"],
    # Poland
    "legia warsaw": ["legia", "legia warszawa"],
    "lech poznan": ["lech", "kolejorz"],
}


# ============================================
# DATA CLASSES
# ============================================

@dataclass
class ScoredTweet:
    """Tweet with relevance and freshness scores."""
    handle: str
    content: str
    date: str
    topics: List[str]
    relevance_score: float      # 0.0 - 1.0
    freshness_score: float      # 0.0 - 1.0
    combined_score: float       # relevance × freshness
    freshness_tag: str          # 🔥 FRESH, ⏰ AGING, ⚠️ STALE
    age_hours: float            # Age in hours
    matched_team: str           # Which team this tweet is about


@dataclass
class TweetFilterResult:
    """Result of tweet filtering for a match."""
    tweets: List[ScoredTweet]
    total_found: int
    total_relevant: int
    has_conflicts: bool
    conflict_description: Optional[str]
    formatted_for_ai: str


# ============================================
# FRESHNESS CALCULATION
# ============================================

def calculate_tweet_freshness(date_str: str) -> Tuple[float, float, str]:
    """
    Calculate freshness score and tag for a tweet.
    
    Reuses logic from market_intelligence.calculate_news_freshness_multiplier
    but with tweet-specific thresholds.
    
    Args:
        date_str: Date string from tweet (e.g., "2026-01-01", "2 hours ago")
        
    Returns:
        Tuple of (freshness_score, age_hours, freshness_tag)
    """
    try:
        from src.analysis.market_intelligence import calculate_news_freshness_multiplier
        multiplier, minutes_old = calculate_news_freshness_multiplier(date_str)
        age_hours = minutes_old / 60.0
    except ImportError:
        # Fallback if market_intelligence not available
        age_hours = 12.0  # Default assumption
        multiplier = 0.5
    
    # Apply tweet-specific freshness tags
    if age_hours <= TWEET_FRESH_THRESHOLD_HOURS:
        freshness_tag = "🔥 FRESH"
        freshness_score = 1.0
    elif age_hours <= TWEET_AGING_THRESHOLD_HOURS:
        freshness_tag = "⏰ AGING"
        freshness_score = 0.5
    elif age_hours <= TWEET_STALE_THRESHOLD_HOURS:
        freshness_tag = "⚠️ STALE"
        freshness_score = 0.1
    else:
        freshness_tag = "❌ EXPIRED"
        freshness_score = 0.0
    
    return freshness_score, age_hours, freshness_tag


# ============================================
# TEAM MATCHING
# ============================================

def normalize_team_name(name: str) -> str:
    """Normalize team name for matching."""
    if not name:
        return ""
    # Remove common suffixes and normalize
    normalized = name.lower().strip()
    normalized = re.sub(r'\s+(fc|sc|cf|sk|fk|ac|as|ss|afc|bk)$', '', normalized)
    normalized = re.sub(r'^(fc|sc|cf|sk|fk|ac|as|ss|afc|bk)\s+', '', normalized)
    return normalized


def get_team_aliases(team_name: str) -> List[str]:
    """Get all aliases for a team name."""
    normalized = normalize_team_name(team_name)
    
    # Check if team is in our alias map
    if normalized in TEAM_ALIASES:
        return [normalized] + TEAM_ALIASES[normalized]
    
    # Check if team name matches any alias
    for canonical, aliases in TEAM_ALIASES.items():
        if normalized in aliases or normalized == canonical:
            return [canonical] + aliases
    
    # Fallback: return normalized name and its tokens
    tokens = normalized.split()
    return [normalized] + tokens


def match_team_in_text(text: str, team_name: str) -> Tuple[bool, float]:
    """
    Check if text mentions a team.
    
    Args:
        text: Tweet content to search
        team_name: Team name to find
        
    Returns:
        Tuple of (matched, confidence)
        confidence: 1.0 for exact match, 0.7 for alias match, 0.5 for token match
    """
    if not text or not team_name:
        return False, 0.0
    
    text_lower = text.lower()
    aliases = get_team_aliases(team_name)
    
    # Exact match (highest confidence)
    normalized = normalize_team_name(team_name)
    
    # Edge case: empty normalized name (e.g., team_name was only spaces)
    if not normalized:
        return False, 0.0
    
    if normalized in text_lower:
        return True, 1.0
    
    # Alias match (high confidence)
    for alias in aliases:
        if alias and alias in text_lower:
            return True, 0.8
    
    # Token overlap (medium confidence)
    team_tokens = set(normalized.split())
    text_tokens = set(text_lower.split())
    
    # Edge case: empty token sets
    if not team_tokens:
        return False, 0.0
    
    overlap = team_tokens & text_tokens
    
    if len(overlap) >= 1 and len(team_tokens) <= 2:
        return True, 0.6
    elif len(overlap) >= 2:
        return True, 0.5
    
    return False, 0.0


# ============================================
# RELEVANCE SCORING
# ============================================

def calculate_relevance_score(tweet_topics: List[str], tweet_content: str) -> float:
    """
    Calculate relevance score based on topics and content.
    
    Args:
        tweet_topics: List of topics from cached tweet
        tweet_content: Tweet text content
        
    Returns:
        Relevance score 0.0 - 1.0
    """
    score = RELEVANCE_GENERAL  # Base score
    
    # Topic-based scoring
    topics_lower = [t.lower() for t in (tweet_topics or [])]
    content_lower = (tweet_content or "").lower()
    
    # Injury keywords (highest relevance)
    injury_keywords = ['injury', 'injured', 'infortunio', 'lesión', 'lesão', 
                       'out', 'ruled out', 'miss', 'absent', 'doubt', 'doubtful']
    if 'injury' in topics_lower or any(kw in content_lower for kw in injury_keywords):
        score = max(score, RELEVANCE_INJURY)
    
    # Lineup/squad keywords
    lineup_keywords = ['lineup', 'squad', 'convocati', 'escalação', 'starting',
                       'team news', 'selection', 'xi', 'formazione']
    if 'lineup' in topics_lower or 'squad' in topics_lower or any(kw in content_lower for kw in lineup_keywords):
        score = max(score, RELEVANCE_LINEUP)
    
    # Transfer keywords
    transfer_keywords = ['transfer', 'signing', 'loan', 'deal', 'contract']
    if 'transfer' in topics_lower or any(kw in content_lower for kw in transfer_keywords):
        score = max(score, RELEVANCE_TRANSFER)
    
    return score


# ============================================
# CONFLICT DETECTION
# ============================================

def detect_conflicts(tweets: List[ScoredTweet], fotmob_data: str) -> Tuple[bool, Optional[str]]:
    """
    Detect conflicts between Twitter intel and FotMob data.
    
    Looks for contradictions like:
    - Twitter says "Player X fit" but FotMob says "Player X injured"
    - Twitter says "Player Y out" but FotMob doesn't list them as missing
    
    Args:
        tweets: List of scored tweets
        fotmob_data: Official FotMob data string
        
    Returns:
        Tuple of (has_conflict, conflict_description)
    """
    if not tweets or not fotmob_data:
        return False, None
    
    fotmob_lower = fotmob_data.lower()
    
    # Keywords indicating player status
    fit_keywords = ['fit', 'available', 'returns', 'back', 'recovered', 'cleared']
    out_keywords = ['out', 'injured', 'missing', 'absent', 'ruled out', 'doubt']
    
    conflicts = []
    
    for tweet in tweets:
        content_lower = tweet.content.lower()
        
        # Check for "fit" claims in tweet vs "injured" in FotMob
        for fit_kw in fit_keywords:
            if fit_kw in content_lower:
                # Extract potential player name (word before/after keyword)
                # This is a simplified heuristic
                for out_kw in out_keywords:
                    if out_kw in fotmob_lower:
                        conflicts.append(f"Twitter ({tweet.handle}) suggests player fit, FotMob shows injuries")
                        break
        
        # Check for "out" claims in tweet not reflected in FotMob
        for out_kw in out_keywords:
            if out_kw in content_lower:
                # If FotMob doesn't mention injuries, potential conflict
                if 'missing' not in fotmob_lower and 'injured' not in fotmob_lower:
                    conflicts.append(f"Twitter ({tweet.handle}) reports absence not in FotMob")
    
    if conflicts:
        return True, "; ".join(conflicts[:2])  # Limit to 2 conflicts
    
    return False, None


# ============================================
# MAIN FILTER FUNCTION
# ============================================

def filter_tweets_for_match(
    home_team: str,
    away_team: str,
    league_key: str,
    fotmob_data: str = "",
    max_tweets: int = MAX_TWEETS_PER_MATCH
) -> TweetFilterResult:
    """
    Filter and score tweets relevant to a specific match.
    
    Main entry point for tweet filtering. Searches the TwitterIntelCache,
    applies relevance and freshness scoring, and returns formatted output.
    
    Args:
        home_team: Home team name
        away_team: Away team name
        league_key: League API key (e.g., 'soccer_turkey_super_league')
        fotmob_data: Official FotMob data for conflict detection
        max_tweets: Maximum tweets to return
        
    Returns:
        TweetFilterResult with scored tweets and formatted AI string
    """
    # Import cache (lazy to avoid circular imports)
    try:
        from src.services.twitter_intel_cache import get_twitter_intel_cache, CachedTweet
        cache = get_twitter_intel_cache()
    except ImportError as e:
        logger.warning(f"TwitterIntelCache not available: {e}")
        return TweetFilterResult(
            tweets=[],
            total_found=0,
            total_relevant=0,
            has_conflicts=False,
            conflict_description=None,
            formatted_for_ai=""
        )
    
    # Check cache freshness
    if not cache.is_fresh:
        logger.debug("Twitter Intel cache is stale, skipping")
        return TweetFilterResult(
            tweets=[],
            total_found=0,
            total_relevant=0,
            has_conflicts=False,
            conflict_description=None,
            formatted_for_ai=""
        )
    
    # Search for tweets about both teams
    all_tweets: List[CachedTweet] = []
    
    # Get tweets for league first
    league_tweets = cache.get_intel_for_league(league_key)
    all_tweets.extend(league_tweets)
    
    # Also search by team names
    for team in [home_team, away_team]:
        team_tweets = cache.search_intel(team, league_key=league_key)
        for t in team_tweets:
            if t not in all_tweets:
                all_tweets.append(t)
    
    total_found = len(all_tweets)
    
    if not all_tweets:
        logger.debug(f"No tweets found for {home_team} vs {away_team}")
        return TweetFilterResult(
            tweets=[],
            total_found=0,
            total_relevant=0,
            has_conflicts=False,
            conflict_description=None,
            formatted_for_ai=""
        )
    
    # Score and filter tweets
    scored_tweets: List[ScoredTweet] = []
    
    for tweet in all_tweets:
        # Check team match
        home_match, home_conf = match_team_in_text(tweet.content, home_team)
        away_match, away_conf = match_team_in_text(tweet.content, away_team)
        
        if not home_match and not away_match:
            continue  # Not relevant to this match
        
        matched_team = home_team if home_conf >= away_conf else away_team
        team_confidence = max(home_conf, away_conf)
        
        # Calculate freshness
        freshness_score, age_hours, freshness_tag = calculate_tweet_freshness(tweet.date)
        
        # Skip expired tweets
        if freshness_score == 0.0:
            continue
        
        # Calculate relevance
        relevance_score = calculate_relevance_score(tweet.topics, tweet.content)
        
        # Apply team match confidence to relevance
        relevance_score *= team_confidence
        
        # Combined score
        combined_score = relevance_score * freshness_score
        
        # For STALE tweets, only keep if HIGH relevance (injury/lineup)
        if freshness_tag == "⚠️ STALE" and relevance_score < RELEVANCE_LINEUP:
            continue
        
        scored_tweets.append(ScoredTweet(
            handle=tweet.handle,
            content=tweet.content,
            date=tweet.date,
            topics=tweet.topics,
            relevance_score=relevance_score,
            freshness_score=freshness_score,
            combined_score=combined_score,
            freshness_tag=freshness_tag,
            age_hours=age_hours,
            matched_team=matched_team
        ))
    
    total_relevant = len(scored_tweets)
    
    # Sort by combined score (descending)
    scored_tweets.sort(key=lambda t: t.combined_score, reverse=True)
    
    # Apply limits
    if len(scored_tweets) > max_tweets:
        scored_tweets = scored_tweets[:max_tweets]
    
    # Detect conflicts with FotMob
    has_conflicts, conflict_desc = detect_conflicts(scored_tweets, fotmob_data)
    
    # Format for AI
    formatted = format_tweets_for_ai(scored_tweets, has_conflicts, conflict_desc, total_relevant)
    
    logger.info(f"🐦 Tweet Filter: {total_found} found → {total_relevant} relevant → {len(scored_tweets)} selected")
    
    return TweetFilterResult(
        tweets=scored_tweets,
        total_found=total_found,
        total_relevant=total_relevant,
        has_conflicts=has_conflicts,
        conflict_description=conflict_desc,
        formatted_for_ai=formatted
    )


# ============================================
# AI FORMATTING
# ============================================

def format_tweets_for_ai(
    tweets: List[ScoredTweet],
    has_conflicts: bool,
    conflict_desc: Optional[str],
    total_relevant: int
) -> str:
    """
    Format filtered tweets for injection into AI prompt.
    
    Output format matches the style of other data sources in analyzer.py.
    
    Args:
        tweets: List of scored tweets to format
        has_conflicts: Whether conflicts were detected
        conflict_desc: Description of conflicts
        total_relevant: Total relevant tweets found (for context)
        
    Returns:
        Formatted string for AI prompt
    """
    if not tweets:
        return ""
    
    lines = [f"[TWITTER INTEL - {len(tweets)} tweet rilevanti]"]
    
    # Add conflict warning if detected
    if has_conflicts and conflict_desc:
        lines.append(f"⚠️ CONFLICT DETECTED: {conflict_desc}")
        lines.append("   → Verify with Gemini before trusting Twitter claims")
        lines.append("")
    
    for tweet in tweets:
        # Format age display
        if tweet.age_hours < 1:
            age_display = f"{int(tweet.age_hours * 60)}m ago"
        elif tweet.age_hours < 24:
            age_display = f"{int(tweet.age_hours)}h ago"
        else:
            age_display = f"{int(tweet.age_hours / 24)}d ago"
        
        # Format topics
        topics_str = ", ".join(tweet.topics) if tweet.topics else "general"
        
        # Build tweet line
        lines.append(f"🐦 {tweet.handle} ({age_display}) [{tweet.freshness_tag}]")
        lines.append(f'   "{tweet.content[:180]}{"..." if len(tweet.content) > 180 else ""}"')
        lines.append(f"   Topics: {topics_str} | Team: {tweet.matched_team}")
        lines.append("")
    
    # Add summary if we filtered many tweets
    if total_relevant > len(tweets):
        lines.append(f"ℹ️ Altri {total_relevant - len(tweets)} tweet meno rilevanti omessi")
    
    return "\n".join(lines)


# ============================================
# CONFLICT RESOLUTION VIA GEMINI
# ============================================

def resolve_conflict_via_gemini(
    conflict_description: str,
    home_team: str,
    away_team: str,
    twitter_claim: str,
    fotmob_claim: str
) -> Optional[Dict]:
    """
    Resolve Twitter vs FotMob conflict using IntelligenceRouter.
    
    V5.0: Now uses IntelligenceRouter for automatic Gemini/Perplexity fallback.
    Called when detect_conflicts() finds a contradiction.
    
    Args:
        conflict_description: Description of the conflict
        home_team: Home team name
        away_team: Away team name
        twitter_claim: What Twitter says
        fotmob_claim: What FotMob says
        
    Returns:
        Dict with resolution result or None if unavailable
    """
    try:
        from src.services.intelligence_router import get_intelligence_router
        router = get_intelligence_router()
        
        if not router.is_available():
            logger.debug("Intelligence Router not available for conflict resolution")
            return None
        
        # Use verify_news_item for conflict resolution
        result = router.verify_news_item(
            news_title=f"Conflict: {conflict_description}",
            news_snippet=f"Twitter claims: {twitter_claim}. FotMob shows: {fotmob_claim}",
            team_name=home_team,
            news_source="Twitter vs FotMob",
            match_context=f"{home_team} vs {away_team}"
        )
        
        if result:
            logger.info(f"🔍 Conflict resolution ({router.get_active_provider_name()}): {result.get('verification_status', 'UNKNOWN')}")
        
        return result
        
    except Exception as e:
        logger.warning(f"Conflict resolution failed: {e}")
        return None


# ============================================
# CLI TEST
# ============================================

if __name__ == "__main__":
    import json
    
    print("=" * 60)
    print("🐦 TWEET RELEVANCE FILTER - TEST")
    print("=" * 60)
    
    # Test team matching
    print("\n📋 Team Matching Tests:")
    test_cases = [
        ("Galatasaray injury update: Icardi out", "Galatasaray"),
        ("Gala vs Fener derby preview", "Galatasaray"),
        ("Boca Juniors squad for Copa", "Boca Juniors"),
        ("CABJ lineup confirmed", "Boca Juniors"),
        ("Random news about weather", "Galatasaray"),
    ]
    
    for text, team in test_cases:
        matched, conf = match_team_in_text(text, team)
        print(f"   '{text[:40]}...' → {team}: {matched} ({conf:.1f})")
    
    # Test freshness calculation
    print("\n⏰ Freshness Tests:")
    date_tests = ["just now", "2 hours ago", "1 day ago", "3 days ago", "1 week ago"]
    for date_str in date_tests:
        score, hours, tag = calculate_tweet_freshness(date_str)
        print(f"   '{date_str}' → {tag} (score: {score:.2f}, {hours:.1f}h)")
    
    # Test full filter (requires cache)
    print("\n🔍 Full Filter Test:")
    result = filter_tweets_for_match(
        home_team="Galatasaray",
        away_team="Fenerbahce",
        league_key="soccer_turkey_super_league",
        fotmob_data="FotMob: 2 players missing (Icardi, Mertens)"
    )
    
    print(f"   Found: {result.total_found}")
    print(f"   Relevant: {result.total_relevant}")
    print(f"   Selected: {len(result.tweets)}")
    print(f"   Conflicts: {result.has_conflicts}")
    
    if result.formatted_for_ai:
        print("\n📝 Formatted Output:")
        print(result.formatted_for_ai)
    
    print("\n✅ Test complete")
