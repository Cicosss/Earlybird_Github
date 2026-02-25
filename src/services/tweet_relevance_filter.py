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
from typing import Any

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Import from content_analysis module
from src.utils.content_analysis import (
    ExclusionFilter,
    PositiveNewsFilter,
    RelevanceAnalyzer,
)

logger = logging.getLogger(__name__)


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
        self._exclusion_filter = ExclusionFilter()
        self._positive_filter = PositiveNewsFilter()

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

        topics = []

        # Priority 1: Check for excluded sports (basketball, tennis, etc.)
        if self._exclusion_filter.is_excluded(text):
            reason = self._exclusion_filter.get_exclusion_reason(text)
            logger.debug(f"[TWEET-FILTER] Excluded sport detected: {reason}")
            return {"is_relevant": False, "score": 0.0, "topics": []}

        # Priority 2: Check for positive news (recoveries, returns to training)
        # This is aggressive - we want to filter out positive news
        if self._positive_filter.is_positive_news(text):
            reason = self._positive_filter.get_positive_reason(text)
            logger.debug(f"[TWEET-FILTER] Positive news detected (skipping): {reason}")
            return {"is_relevant": False, "score": 0.0, "topics": []}

        # Priority 3: Check for injury keywords (HIGH relevance)
        if self._injury_pattern.search(text):
            topics.append("injury")
            logger.debug(f"[TWEET-FILTER] Injury detected in short text: {text[:50]}...")
            return {"is_relevant": True, "score": 0.8, "topics": topics}

        # Priority 4: Check for suspension keywords (HIGH relevance)
        if self._suspension_pattern.search(text):
            topics.append("suspension")
            logger.debug(f"[TWEET-FILTER] Suspension detected in short text: {text[:50]}...")
            return {"is_relevant": True, "score": 0.8, "topics": topics}

        # Default: Low relevance (may be worth monitoring but not high priority)
        logger.debug(f"[TWEET-FILTER] Low relevance (default): {text[:50]}...")
        return {"is_relevant": False, "score": 0.1, "topics": topics}


# ============================================
# SINGLETON INSTANCE
# ============================================

_tweet_relevance_filter: TweetRelevanceFilter | None = None


def get_tweet_relevance_filter() -> TweetRelevanceFilter:
    """
    Get the singleton instance of TweetRelevanceFilter.

    Returns:
        TweetRelevanceFilter instance
    """
    global _tweet_relevance_filter
    if _tweet_relevance_filter is None:
        _tweet_relevance_filter = TweetRelevanceFilter()
    return _tweet_relevance_filter


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
