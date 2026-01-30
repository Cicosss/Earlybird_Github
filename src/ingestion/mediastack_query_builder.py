"""
MediaStack Query Builder - V1.0

Builds optimized queries for MediaStack API with batching support.

Requirements: Standard library only (no new dependencies)
"""
import logging
from typing import List, Dict
from urllib.parse import quote

logger = logging.getLogger(__name__)


class MediaStackQueryBuilder:
    """
    Builds optimized queries for MediaStack API.

    Features:
    - Query building for news search
    - Query splitting for long queries (>500 chars)
    - URL encoding for special characters

    Requirements: Standard library only
    """

    MAX_QUERY_LENGTH = 500  # MediaStack API query length limit

    @staticmethod
    def build_news_query(query: str, countries: str = "it,gb,us") -> str:
        """
        Build a news search query for MediaStack API.

        Args:
            query: Search query string
            countries: Comma-separated country codes (default: it,gb,us)

        Returns:
            URL-encoded query string ready for MediaStack API
        """
        if not query or len(query.strip()) < 2:
            logger.warning("⚠️ MediaStackQueryBuilder: Empty or too short query")
            return ""

        # Clean query: remove -term exclusions (MediaStack doesn't support them)
        cleaned_query = MediaStackQueryBuilder._clean_query(query)

        if not cleaned_query or len(cleaned_query.strip()) < 2:
            logger.warning("⚠️ MediaStackQueryBuilder: Query empty after cleaning exclusions")
            return ""

        # URL-encode query for special characters
        encoded_query = quote(cleaned_query, safe=' ')

        logger.debug(f"🔍 MediaStack query built: {encoded_query[:60]}...")

        return encoded_query

    @staticmethod
    def build_batched_query(questions: List[str]) -> str:
        """
        Build a batched query combining multiple questions.

        MediaStack API doesn't natively support batching,
        so we combine questions with OR operator.

        Args:
            questions: List of search questions

        Returns:
            Combined query string with OR operators
        """
        if not questions:
            return ""

        # Clean each question
        cleaned_questions = [
            MediaStackQueryBuilder._clean_query(q) for q in questions if q and len(q.strip()) >= 2
        ]

        if not cleaned_questions:
            logger.warning("⚠️ MediaStackQueryBuilder: No valid questions after cleaning")
            return ""

        # Combine with OR operator
        combined = " OR ".join(cleaned_questions)

        # Check length and split if needed
        if len(combined) > MediaStackQueryBuilder.MAX_QUERY_LENGTH:
            logger.warning(
                f"⚠️ MediaStackQueryBuilder: Batched query too long "
                f"({len(combined)} > {MediaStackQueryBuilder.MAX_QUERY_LENGTH}), "
                "will be split"
            )
            # Return first question as fallback
            return cleaned_questions[0]

        # URL-encode
        encoded_query = quote(combined, safe=' ')

        logger.debug(f"🔍 MediaStack batched query built: {encoded_query[:60]}...")

        return encoded_query

    @staticmethod
    def parse_batched_response(response: Dict) -> List[str]:
        """
        Parse a batched response to extract individual answers.

        Since MediaStack doesn't natively support batching,
        this returns the combined result as a single item.

        Args:
            response: MediaStack API response

        Returns:
            List of answer strings (single item for MediaStack)
        """
        # MediaStack doesn't provide AI-generated answers like Tavily
        # This method exists for API compatibility
        results = response.get("data", [])

        if not results:
            return []

        # Return titles as "answers" for compatibility
        return [item.get("title", "") for item in results]

    @staticmethod
    def _clean_query(query: str) -> str:
        """
        Clean query by removing -term exclusions.

        MediaStack API doesn't support negative search operators,
        so we strip them to avoid polluting the keyword search.

        Args:
            query: Original query with potential -term exclusions

        Returns:
            Cleaned query with only positive keywords
        """
        if not query:
            return ""

        # Exclusion keywords (aligned with mediastack_provider.py)
        EXCLUSION_KEYWORDS = [
            "basket", "basketball", "euroleague", "nba", "pallacanestro", "baloncesto",
            "nfl", "american football", "touchdown", "super bowl",
            "women", "woman", "ladies", "feminine", "femminile", "femenino",
            "handball", "volleyball", "rugby", "futsal",
        ]

        cleaned = query

        # Remove -term patterns
        for kw in EXCLUSION_KEYWORDS:
            # Match "-keyword" or "- keyword"
            import re
            pattern = rf'\s*-\s*{re.escape(kw)}\b'
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        # Clean up multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        return cleaned


# ============================================
# CLI TEST
# ============================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("🔍 MEDIASTACK QUERY BUILDER TEST")
    print("=" * 60)

    builder = MediaStackQueryBuilder()

    # Test single query
    print("\n📝 Testing single query...")
    query1 = builder.build_news_query("Serie A injury lineup", countries="it,gb,us")
    print(f"   Query: {query1}")

    # Test batched query
    print("\n📝 Testing batched query...")
    questions = [
        "Serie A injury",
        "Milan Inter lineup",
        "Juventus news"
    ]
    query2 = builder.build_batched_query(questions)
    print(f"   Batched Query: {query2}")

    # Test query cleaning
    print("\n📝 Testing query cleaning...")
    dirty = "football news -basket -basketball -women"
    clean = MediaStackQueryBuilder._clean_query(dirty)
    print(f"   Dirty: {dirty}")
    print(f"   Clean: {clean}")

    print("\n✅ MediaStack Query Builder test complete")
