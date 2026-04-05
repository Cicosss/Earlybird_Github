"""
Tweet Relevance Filter - EarlyBird V10.5

Specialized filter for short text (Tweets) using precision gating.
Adapted from RelevanceAnalyzer logic but optimized for short, concise content.

Key differences from RelevanceAnalyzer:
- Aggressive filtering against "Positive News" (recoveries, returns to training)
- High sensitivity to "Negative News" (injuries, suspensions) even in 5-word tweets
- Simplified scoring for short text: 0.0 (excluded), 0.1 (low relevance), 0.8 (high relevance)

Requirements: V10.5 - Precision Gating & Persistence
"""

import logging
import os
import re
import sys
import threading
from dataclasses import dataclass
from typing import Any

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Import from content_analysis module
from src.utils.content_analysis import (
    RelevanceAnalyzer,
    get_exclusion_filter,
    get_positive_news_filter,
)

# Import from text_normalizer for team matching utilities
from src.utils.text_normalizer import (
    fuzzy_match_team,
    normalize_for_matching,
)
from src.utils.text_normalizer import (
    get_team_aliases as get_team_aliases_from_text_normalizer,
)

logger = logging.getLogger(__name__)


# ============================================
# DATA CLASSES
# ============================================


@dataclass
class ScoredTweet:
    """A tweet with relevance and freshness scores."""

    handle: str
    content: str
    date: str
    topics: list[str]
    relevance_score: float
    freshness_score: float
    combined_score: float
    freshness_tag: str
    age_hours: float
    matched_team: str = ""


@dataclass
class TweetFilterResult:
    """Result of filtering tweets for a match."""

    tweets: list[ScoredTweet]
    total_found: int
    total_relevant: int
    has_conflicts: bool
    formatted_for_ai: str
    conflict_description: str | None = None


# ============================================
# MAIN FILTER CLASS
# ============================================


class TweetRelevanceFilter:
    """
    Specialized filter for tweet relevance analysis (short text mode).

    Uses precision gating to filter noise while being sensitive to
    negative news (injuries, suspensions) even in very short tweets.

    Scoring Logic (Short Text Mode):
    - 0.0: Contains excluded sports OR positive news (recoveries)
    - 0.8: Contains ANY injury or suspension keywords (high relevance)
    - 0.1: Default low relevance (may be worth monitoring)

    This ensures the filter is aggressive against "Positive News" (Recoveries)
    but sensitive to "Negative News" (Injuries), even if the tweet is just 5 words.
    """

    def __init__(self):
        """Initialize with compiled regex patterns for efficiency."""
        # Initialize filters for keyword access
        # VPS FIX: Use singleton instead of creating new instance
        self._exclusion_filter = get_exclusion_filter()
        self._positive_filter = get_positive_news_filter()

        # Compile injury/suspension patterns for short text matching
        # Access keywords from RelevanceAnalyzer class
        injury_pattern = (
            r"\b(" + "|".join(re.escape(kw) for kw in RelevanceAnalyzer.INJURY_KEYWORDS) + r")\b"
        )
        self._injury_pattern = re.compile(injury_pattern, re.IGNORECASE)

        suspension_pattern = (
            r"\b("
            + "|".join(re.escape(kw) for kw in RelevanceAnalyzer.SUSPENSION_KEYWORDS)
            + r")\b"
        )
        self._suspension_pattern = re.compile(suspension_pattern, re.IGNORECASE)

    def analyze(self, text: str) -> dict[str, Any]:
        """
        Analyze tweet text for relevance (short text mode).

        Args:
            text: Tweet content to analyze

        Returns:
            Dict with keys:
                - is_relevant: bool (True if score > 0.1)
                - score: float (0.0, 0.1, or 0.8)
                - topics: list of detected topics (e.g., ["injury"], ["suspension"])
        """
        if not text or not isinstance(text, str):
            logger.debug("[TWEET-FILTER] Empty or invalid text")
            return {"is_relevant": False, "score": 0.0, "topics": []}

        topics: list[str] = []

        # Priority 1: Check for excluded sports (basketball, tennis, etc.)
        # VPS FIX: Add error handling
        try:
            if self._exclusion_filter.is_excluded(text):
                reason = self._exclusion_filter.get_exclusion_reason(text)
                logger.debug(f"[TWEET-FILTER] Excluded sport detected: {reason}")
                return {"is_relevant": False, "score": 0.0, "topics": []}
        except Exception as e:
            logger.warning(f"[TWEET-FILTER] Error checking exclusion filter: {e}")
            # Continue to next check

        # Priority 2: Check for positive news (recoveries, returns to training)
        # This is aggressive - we want to filter out positive news
        # VPS FIX: Add error handling
        try:
            if self._positive_filter.is_positive_news(text):
                reason = self._positive_filter.get_positive_reason(text)
                logger.debug(f"[TWEET-FILTER] Positive news detected (skipping): {reason}")
                return {"is_relevant": False, "score": 0.0, "topics": []}
        except Exception as e:
            logger.warning(f"[TWEET-FILTER] Error checking positive news filter: {e}")
            # Continue to next check

        # Priority 3: Check for injury keywords (HIGH relevance)
        # VPS FIX: Add error handling
        try:
            if self._injury_pattern.search(text):
                topics.append("injury")
                logger.debug(f"[TWEET-FILTER] Injury detected in short text: {text[:50]}...")
                return {"is_relevant": True, "score": 0.8, "topics": topics}
        except Exception as e:
            logger.warning(f"[TWEET-FILTER] Error checking injury pattern: {e}")
            # Continue to next check

        # Priority 4: Check for suspension keywords (HIGH relevance)
        # VPS FIX: Add error handling
        try:
            if self._suspension_pattern.search(text):
                topics.append("suspension")
                logger.debug(f"[TWEET-FILTER] Suspension detected in short text: {text[:50]}...")
                return {"is_relevant": True, "score": 0.8, "topics": topics}
        except Exception as e:
            logger.warning(f"[TWEET-FILTER] Error checking suspension pattern: {e}")
            # Continue to default

        # Default: Low relevance (may be worth monitoring but not high priority)
        logger.debug(f"[TWEET-FILTER] Low relevance (default): {text[:50]}...")
        return {"is_relevant": False, "score": 0.1, "topics": topics}


# ============================================
# SINGLETON INSTANCE (THREAD-SAFE)
# ============================================

_tweet_relevance_filter: TweetRelevanceFilter | None = None
_singleton_lock = threading.Lock()


def get_tweet_relevance_filter() -> TweetRelevanceFilter:
    """
    Get the singleton instance of TweetRelevanceFilter (thread-safe).

    Uses double-check locking pattern for thread safety in concurrent environments.

    Returns:
        TweetRelevanceFilter instance
    """
    global _tweet_relevance_filter
    if _tweet_relevance_filter is None:
        with _singleton_lock:
            # Double-check locking pattern
            if _tweet_relevance_filter is None:
                _tweet_relevance_filter = TweetRelevanceFilter()
    return _tweet_relevance_filter


# ============================================
# TEAM MATCHING FUNCTIONS
# ============================================


def match_team_in_text(text: str, team_name: str) -> tuple[bool, float]:
    """
    Check if a team name appears in text using fuzzy matching.

    Args:
        text: Text to search in
        team_name: Team name to search for

    Returns:
        Tuple of (matched: bool, confidence: float)
        Confidence is 0.0-1.0 (1.0 = exact match)
    """
    if not text or not team_name:
        return False, 0.0

    # Normalize inputs
    text_norm = normalize_for_matching(text)
    team_norm = normalize_for_matching(team_name)

    # Handle division by zero case (empty team after normalization)
    if not team_norm:
        return False, 0.0

    # Check for exact match
    if team_norm in text_norm:
        return True, 1.0

    # Check for alias match
    try:
        aliases = get_team_aliases_from_text_normalizer(team_name)
        for alias in aliases:
            alias_norm = normalize_for_matching(alias)
            if alias_norm in text_norm:
                return True, 0.8
    except Exception as e:
        logger.warning(f"[TWEET-FILTER] Error getting team aliases: {e}")

    # Use fuzzy matching with higher threshold to avoid false positives
    try:
        matched, score = fuzzy_match_team(team_name, text, threshold=85)
        confidence = score / 100.0 if score else 0.0
        # Only return match if confidence is reasonably high
        if matched and confidence >= 0.5:
            return matched, confidence
        return False, 0.0
    except Exception as e:
        logger.warning(f"[TWEET-FILTER] Error in fuzzy matching: {e}")
        return False, 0.0


def normalize_team_name(team_name: str) -> str:
    """
    Normalize team name by removing common suffixes and lowercasing.

    Args:
        team_name: Team name to normalize

    Returns:
        Normalized team name
    """
    if not team_name:
        return ""

    normalized = normalize_for_matching(team_name)

    # Remove common suffixes
    suffixes = [" fc", " sk", " cf", " sc", " ac", " afc", " cfc", " ssc"]
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()

    return normalized


def get_team_aliases_wrapper(team_name: str) -> list[str]:
    """
    Get all known aliases for a team name.

    Args:
        team_name: Team name to get aliases for

    Returns:
        List of aliases (includes the normalized name)
    """
    if not team_name:
        return []

    try:
        aliases = get_team_aliases_from_text_normalizer(team_name)
        # If only the original name is returned, normalize it
        if len(aliases) == 1 and aliases[0] == team_name:
            return [normalize_team_name(team_name)]
        return aliases
    except Exception as e:
        logger.warning(f"[TWEET-FILTER] Error getting team aliases: {e}")
        return [normalize_team_name(team_name)]


# ============================================
# FRESHNESS CALCULATION
# ============================================


def calculate_tweet_freshness(date_str: str | None) -> tuple[float, float, str]:
    """
    Calculate tweet freshness score and age in hours.

    Args:
        date_str: Date string (e.g., "2h ago", "1d ago", "just now")

    Returns:
        Tuple of (score: float, hours: float, tag: str)
        - score: 1.0 (fresh), 0.5 (aging), 0.1 (stale), 0.0 (expired)
        - hours: Age in hours
        - tag: "🔥 FRESH", "⏰ AGING", "📜 STALE", "❌ EXPIRED"
    """
    if not date_str:
        # Default: treat as fresh (24 hours old)
        return 0.5, 24.0, "⏰ AGING"

    try:
        date_str = date_str.lower().strip()

        # Parse common formats
        if "just now" in date_str or "now" in date_str:
            return 1.0, 0.1, "🔥 FRESH"

        # Extract numbers and units
        import re

        match = re.search(r"(\d+)\s*(h|hour|d|day|w|week|m|min|second|s)", date_str)
        if not match:
            # Default: treat as fresh
            return 0.5, 24.0, "⏰ AGING"

        value = int(match.group(1))
        unit = match.group(2)

        # Convert to hours
        if unit.startswith("h"):
            hours = float(value)
        elif unit.startswith("d"):
            hours = float(value * 24)
        elif unit.startswith("w"):
            hours = float(value * 24 * 7)
        elif unit.startswith("m"):
            hours = float(value / 60)
        elif unit.startswith("s"):
            hours = float(value / 3600)
        else:
            hours = 24.0

        # Determine freshness (adjusted to match test expectations)
        if hours < 3:
            return 1.0, hours, "🔥 FRESH"
        elif hours < 12:
            return 1.0, hours, "🔥 FRESH"
        elif hours < 48:
            return 0.5, hours, "⏰ AGING"
        elif hours < 168:  # 1 week
            return 0.1, hours, "📜 STALE"
        else:
            return 0.0, hours, "❌ EXPIRED"

    except Exception as e:
        logger.warning(f"[TWEET-FILTER] Error calculating tweet freshness: {e}")
        return 0.5, 24.0, "⏰ AGING"


# ============================================
# RELEVANCE SCORING
# ============================================


def calculate_relevance_score(tweet_topics: list[str] | None, tweet_content: str) -> float:
    """
    Calculate relevance score based on topics and content.

    Args:
        tweet_topics: List of detected topics
        tweet_content: Tweet content

    Returns:
        Relevance score (0.0-1.0)
    """
    if not tweet_topics:
        tweet_topics: list[str] = []

    score = 0.0

    # Base score for any content
    score = max(score, 0.4)

    # Boost based on topics
    for topic in tweet_topics:
        if topic == "injury":
            score = max(score, 0.9)
        elif topic == "suspension":
            score = max(score, 0.9)
        elif topic in ["lineup", "squad", "starting xi"]:
            score = max(score, 0.8)
        elif topic == "transfer":
            score = max(score, 0.7)
        elif topic == "general":
            score = max(score, 0.5)

    # Boost based on content keywords
    if tweet_content:
        content_lower = tweet_content.lower()
        injury_keywords = ["injured", "injury", "out", "ruled out", "unavailable"]
        if any(kw in content_lower for kw in injury_keywords):
            score = max(score, 0.9)

    return min(score, 1.0)


# ============================================
# CONFLICT DETECTION
# ============================================


def detect_conflicts(
    tweets: list[ScoredTweet] | None, fotmob_data: str | None
) -> tuple[bool, str | None]:
    """
    Detect conflicts between Twitter intel and FotMob data.

    Args:
        tweets: List of scored tweets
        fotmob_data: FotMob status data

    Returns:
        Tuple of (has_conflict: bool, description: str | None)
    """
    if not tweets or not fotmob_data:
        return False, None

    try:
        # Check for injury conflicts
        fotmob_lower = fotmob_data.lower()
        has_fotmob_injury = any(kw in fotmob_lower for kw in ["injured", "doubtful", "suspended"])

        for tweet in tweets:
            if "injury" in tweet.topics or "suspension" in tweet.topics:
                tweet_content_lower = tweet.content.lower()
                has_twitter_fit = any(
                    kw in tweet_content_lower for kw in ["fit", "available", "ready", "recovered"]
                )

                if has_twitter_fit and has_fotmob_injury:
                    conflict_desc = f"Twitter says fit, FotMob says injured: {tweet.content[:100]}"
                    return True, conflict_desc

        return False, None

    except Exception as e:
        logger.warning(f"[TWEET-FILTER] Error detecting conflicts: {e}")
        return False, None


# ============================================
# CONFLICT RESOLUTION
# ============================================


def resolve_conflict_via_gemini(
    conflict_description: str,
    home_team: str,
    away_team: str,
    twitter_claim: str,
    fotmob_claim: str,
) -> dict[str, Any] | None:
    """
    Resolve conflict via IntelligenceRouter (DeepSeek primary, Tavily/Claude fallback).

    V13.0 FIX: Replaced non-existent _resolve_conflict_via_gemini() with proper
    IntelligenceRouter.verify_news_item() integration.

    The original implementation called AnalysisEngine._resolve_conflict_via_gemini()
    which NEVER EXISTED - this method was never implemented. Now uses the proper
    LLM routing system (DeepSeek → Tavily → Claude 3 Haiku fallback chain).

    Args:
        conflict_description: Description of the conflict
        home_team: Home team name
        away_team: Away team name
        twitter_claim: Twitter's claim
        fotmob_claim: FotMob's claim

    Returns:
        Resolution dict with keys:
        - verification_status: CONFIRMED | DENIED | OUTDATED | UNVERIFIED
        - confidence_level: HIGH | MEDIUM | LOW
        - additional_context: str
        - verified: bool
        Or None if intelligence router unavailable
    """
    try:
        # V13.0: Use IntelligenceRouter singleton (DeepSeek primary)
        from src.services.intelligence_router import get_intelligence_router

        router = get_intelligence_router()

        if not router or not router.is_available():
            logger.debug("[TWEET-FILTER] IntelligenceRouter not available for conflict resolution")
            return None

        # Build news verification request from conflict data
        # Map conflict parameters to verify_news_item() signature:
        # - news_title: Brief conflict summary
        # - news_snippet: Combined claims from both sources
        # - team_name: Primary team (home)
        # - news_source: Indicate this is a cross-source conflict
        # - match_context: Full match context

        news_title = (
            f"Conflict: {conflict_description[:80]}..."
            if len(conflict_description) > 80
            else f"Conflict: {conflict_description}"
        )

        news_snippet = f"TWITTER CLAIM: {twitter_claim[:300]}\n\nFOTMOB CLAIM: {fotmob_claim[:300]}"

        match_context = f"{home_team} vs {away_team}"

        logger.info(f"[TWEET-FILTER] Resolving conflict via IntelligenceRouter for {match_context}")

        # Call verify_news_item through the router
        # This routes to: DeepSeek (primary) → Claude 3 Haiku (fallback)
        result = router.verify_news_item(
            news_title=news_title,
            news_snippet=news_snippet,
            team_name=home_team,
            news_source="Twitter vs FotMob Conflict",
            match_context=match_context,
        )

        if result:
            status = result.get("verification_status", "UNVERIFIED")
            confidence = result.get("confidence_level", "LOW")
            logger.info(f"[TWEET-FILTER] Conflict resolution: {status} (confidence: {confidence})")
        else:
            logger.warning("[TWEET-FILTER] Conflict resolution returned no result")

        return result

    except ImportError as e:
        logger.debug(f"[TWEET-FILTER] IntelligenceRouter not available: {e}")
        return None
    except Exception as e:
        logger.warning(f"[TWEET-FILTER] Error resolving conflict via IntelligenceRouter: {e}")
        return None


# ============================================
# MAIN FILTER FUNCTION
# ============================================


def filter_tweets_for_match(
    home_team: str,
    away_team: str,
    league_key: str,
    max_tweets: int = 10,
    fotmob_data: str | None = None,
) -> TweetFilterResult:
    """
    Filter and score tweets for a specific match.

    Args:
        home_team: Home team name
        away_team: Away team name
        league_key: League identifier
        max_tweets: Maximum number of tweets to return
        fotmob_data: Optional FotMob status data as JSON string

    Returns:
        TweetFilterResult with filtered and scored tweets
    """
    try:
        # Import here to avoid circular dependencies
        from src.services.twitter_intel_cache import get_twitter_intel_cache

        cache = get_twitter_intel_cache()
        filter_instance = get_tweet_relevance_filter()

        # Get cached tweets for this match
        all_tweets = cache.get_cached_tweets_for_match(home_team, away_team, league_key)

        if not all_tweets:
            return TweetFilterResult(
                tweets=[],
                total_found=0,
                total_relevant=0,
                has_conflicts=False,
                formatted_for_ai="",
            )

        scored_tweets: list[ScoredTweet] = []

        for tweet_data in all_tweets:
            try:
                content = tweet_data.get("content", "")
                handle = tweet_data.get("handle", "@unknown")
                date = tweet_data.get("date", "")

                # Apply relevance filter
                relevance_result = filter_instance.analyze(content)

                # Skip irrelevant tweets
                if not relevance_result["is_relevant"]:
                    continue

                # Calculate freshness
                freshness_score, age_hours, freshness_tag = calculate_tweet_freshness(date)

                # Match team
                matched, confidence = match_team_in_text(content, home_team)
                if not matched:
                    matched, confidence = match_team_in_text(content, away_team)

                matched_team = home_team if match_team_in_text(content, home_team)[0] else away_team

                # Calculate combined score
                combined_score = (relevance_result["score"] * 0.7) + (freshness_score * 0.3)

                scored_tweet = ScoredTweet(
                    handle=handle,
                    content=content,
                    date=date,
                    topics=relevance_result["topics"],
                    relevance_score=relevance_result["score"],
                    freshness_score=freshness_score,
                    combined_score=combined_score,
                    freshness_tag=freshness_tag,
                    age_hours=age_hours,
                    matched_team=matched_team,
                )
                scored_tweets.append(scored_tweet)

            except Exception as e:
                logger.warning(f"[TWEET-FILTER] Error processing tweet: {e}")
                continue

        # Sort by combined score
        scored_tweets.sort(key=lambda t: t.combined_score, reverse=True)

        # Limit results
        scored_tweets = scored_tweets[:max_tweets]

        # Detect conflicts
        # Use provided fotmob_data if available, otherwise fetch from cache
        if fotmob_data is None:
            fotmob_data = cache.get_fotmob_status_for_match(home_team, away_team, league_key)
        has_conflicts, conflict_desc = detect_conflicts(scored_tweets, fotmob_data)

        # Format for AI
        formatted = format_tweets_for_ai(
            tweets=scored_tweets,
            has_conflicts=has_conflicts,
            conflict_desc=conflict_desc,
            total_relevant=len(scored_tweets),
        )

        return TweetFilterResult(
            tweets=scored_tweets,
            total_found=len(all_tweets),
            total_relevant=len(scored_tweets),
            has_conflicts=has_conflicts,
            formatted_for_ai=formatted,
            conflict_description=conflict_desc,
        )

    except Exception as e:
        logger.error(f"[TWEET-FILTER] Error filtering tweets for match: {e}")
        return TweetFilterResult(
            tweets=[],
            total_found=0,
            total_relevant=0,
            has_conflicts=False,
            formatted_for_ai="",
        )


# ============================================
# FORMATTING FUNCTIONS
# ============================================


def format_tweets_for_ai(
    tweets: list[ScoredTweet],
    has_conflicts: bool,
    conflict_desc: str | None,
    total_relevant: int,
) -> str:
    """
    Format tweets for AI consumption.

    Args:
        tweets: List of scored tweets
        has_conflicts: Whether conflicts were detected
        conflict_desc: Conflict description
        total_relevant: Total number of relevant tweets

    Returns:
        Formatted string for AI
    """
    if not tweets:
        return ""

    lines: list[str] = []
    lines.append(f"🐦 TWITTER INTEL ({total_relevant} relevant tweets)")
    lines.append("=" * 60)

    for i, tweet in enumerate(tweets, 1):
        # Truncate content if too long
        content = tweet.content[:200] + "..." if len(tweet.content) > 200 else tweet.content

        lines.append(f"\n{i}. {tweet.handle} {tweet.freshness_tag}")
        lines.append(f"   Team: {tweet.matched_team}")
        lines.append(
            f"   Score: {tweet.combined_score:.2f} (R:{tweet.relevance_score:.1f} F:{tweet.freshness_score:.1f})"
        )
        lines.append(f"   Topics: {', '.join(tweet.topics) if tweet.topics else 'N/A'}")
        lines.append(f"   Content: {content}")

    # Add conflict warning
    if has_conflicts and conflict_desc:
        lines.append("\n" + "=" * 60)
        lines.append("⚠️ CONFLICT DETECTED")
        lines.append(f"   {conflict_desc}")
        lines.append("   ⚠️ Gemini should verify this information")

    return "\n".join(lines)


# ============================================
# PUBLIC API EXPORTS
# ============================================

# Export get_team_aliases as a public function (wrapper around text_normalizer)
# This ensures tests can import it from this module
get_team_aliases = get_team_aliases_wrapper


# ============================================
# CLI TEST
# ============================================

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("🐦 TWEET RELEVANCE FILTER - TEST")
    print("=" * 60)

    filter = get_tweet_relevance_filter()

    # Test cases
    test_cases = [
        # High relevance (injury/suspension)
        ("Icardi out 2 weeks", True, 0.8, ["injury"]),
        ("Salah injured", True, 0.8, ["injury"]),
        ("Ronaldo suspended", True, 0.8, ["suspension"]),
        ("Kane ruled out", True, 0.8, ["injury"]),
        # Positive news (should be filtered out)
        ("Salah back in training", False, 0.0, []),
        ("Icardi recovered", False, 0.0, []),
        ("Kane fit again", False, 0.0, []),
        # Excluded sports (sport names, not athlete names)
        ("basketball injury", False, 0.0, []),
        ("tennis match", False, 0.0, []),
        ("NBA game", False, 0.0, []),
        # Low relevance (default)
        ("Match preview", False, 0.1, []),
        ("Score update", False, 0.1, []),
    ]

    print("\n📋 Test Results:")
    all_passed = True
    for text, expected_relevant, expected_score, expected_topics in test_cases:
        result = filter.analyze(text)
        passed = (
            result["is_relevant"] == expected_relevant
            and result["score"] == expected_score
            and result["topics"] == expected_topics
        )
        status = "✅" if passed else "❌"
        print(f"{status} '{text}'")
        print(
            f"   Expected: relevant={expected_relevant}, score={expected_score}, topics={expected_topics}"
        )
        print(
            f"   Got:      relevant={result['is_relevant']}, score={result['score']}, topics={result['topics']}"
        )
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed!")
        sys.exit(1)
