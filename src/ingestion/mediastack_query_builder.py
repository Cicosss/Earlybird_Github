"""
MediaStack Query Builder - V2.0

Builds optimized queries for MediaStack API with intelligent batching support.

Requirements: Standard library only (no new dependencies)

V2.0 CHANGES:
- Fixed _clean_query() to handle multi-word exclusions correctly
- Implemented intelligent batching with query packing algorithm
- Removed unused countries parameter from build_news_query()
- Added build_batched_queries() that returns multiple queries when needed
- Integrated with MediastackProvider for production use
"""

import logging
import re
from typing import List
from urllib.parse import quote

logger = logging.getLogger(__name__)


class MediaStackQueryBuilder:
    """
    Builds optimized queries for MediaStack API.

    Features:
    - Query building for news search
    - Intelligent query splitting for long queries (>500 chars)
    - URL encoding for special characters
    - Smart packing algorithm to maximize query capacity

    Requirements: Standard library only
    """

    MAX_QUERY_LENGTH = 500  # MediaStack API query length limit

    # Exclusion keywords for query cleaning (operator -term removal)
    # These are terms that MediaStack API doesn't support as negative operators
    # NOTE: This is DIFFERENT from post-fetch filtering in mediastack_provider.py
    # which uses a larger list for filtering results after fetch
    QUERY_CLEANING_EXCLUSIONS = [
        # Basketball
        "basket",
        "basketball",
        "euroleague",
        "nba",
        "pallacanestro",
        "baloncesto",
        # American Football
        "nfl",
        "american football",
        "touchdown",
        "super bowl",
        # Women's Football (to avoid false positives on shared team names)
        "women",
        "woman",
        "ladies",
        "feminine",
        "femminile",
        "femenino",
        # Other sports
        "handball",
        "volleyball",
        "rugby",
        "futsal",
    ]

    @staticmethod
    def build_news_query(query: str) -> str:
        """
        Build a news search query for MediaStack API.

        Args:
            query: Search query string

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
        encoded_query = quote(cleaned_query, safe=" ")

        logger.debug(f"🔍 MediaStack query built: {encoded_query[:60]}...")

        return encoded_query

    @staticmethod
    def build_batched_query(questions: List[str]) -> str:
        """
        Build a batched query combining multiple questions.

        MediaStack API doesn't natively support batching,
        so we combine questions with OR operator.

        DEPRECATED: Use build_batched_queries() instead for intelligent batching.
        This method is kept for backward compatibility.

        Args:
            questions: List of search questions

        Returns:
            Combined query string with OR operators (or first question if too long)
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
                "using first question as fallback"
            )
            # Return first question as fallback (backward compatibility)
            return cleaned_questions[0]

        # URL-encode
        encoded_query = quote(combined, safe=" ")

        logger.debug(f"🔍 MediaStack batched query built: {encoded_query[:60]}...")

        return encoded_query

    @staticmethod
    def build_batched_queries(questions: List[str]) -> List[str]:
        """
        Build multiple batched queries using intelligent packing algorithm.

        When the combined query exceeds MAX_QUERY_LENGTH, this method
        intelligently packs questions into multiple queries to maximize
        the number of questions per query while respecting the limit.

        Algorithm:
        1. Sort questions by length (shortest first) for better packing
        2. Use greedy bin-packing to fit as many questions as possible
        3. Each query is combined with OR operators
        4. URL-encode each final query

        Args:
            questions: List of search questions

        Returns:
            List of URL-encoded query strings, each within MAX_QUERY_LENGTH
        """
        if not questions:
            return []

        # Clean each question
        cleaned_questions = [
            MediaStackQueryBuilder._clean_query(q) for q in questions if q and len(q.strip()) >= 2
        ]

        if not cleaned_questions:
            logger.warning("⚠️ MediaStackQueryBuilder: No valid questions after cleaning")
            return []

        # Sort by length (shortest first) for better packing efficiency
        cleaned_questions.sort(key=len)

        # Pack questions into bins using greedy algorithm
        bins = []
        OR_LENGTH = len(" OR ")  # Length of separator between questions

        for question in cleaned_questions:
            question_len = len(question)

            # Try to fit in existing bins
            placed = False
            for bin_questions in bins:
                # Calculate current bin length with OR separators
                if bin_questions:
                    current_len = sum(len(q) for q in bin_questions) + OR_LENGTH * (
                        len(bin_questions) - 1
                    )
                    new_len = current_len + OR_LENGTH + question_len
                else:
                    new_len = question_len

                if new_len <= MediaStackQueryBuilder.MAX_QUERY_LENGTH:
                    bin_questions.append(question)
                    placed = True
                    break

            # Create new bin if couldn't fit
            if not placed:
                bins.append([question])

        # Combine questions in each bin with OR operator and URL-encode
        result_queries = []
        for i, bin_questions in enumerate(bins):
            combined = " OR ".join(bin_questions)
            encoded_query = quote(combined, safe=" ")
            result_queries.append(encoded_query)

        logger.info(
            f"🔍 MediaStack: Packed {len(cleaned_questions)} questions into {len(result_queries)} queries"
        )

        return result_queries

    @staticmethod
    def parse_batched_response(response: dict, query_count: int = 1) -> List[str]:
        """
        Parse a batched response to extract individual answers.

        Since MediaStack doesn't natively support batching,
        this returns the combined result as a single item.

        Args:
            response: MediaStack API response
            query_count: Number of queries that were batched (for future expansion)

        Returns:
            List of answer strings (single item for MediaStack)
        """
        # MediaStack doesn't provide AI-generated answers like Tavily
        # This method exists for API compatibility and future expansion
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

        This method handles multi-word exclusions correctly by processing
        them first (e.g., "american football", "super bowl") before
        processing single-word exclusions.

        Args:
            query: Original query with potential -term exclusions

        Returns:
            Cleaned query with only positive keywords
        """
        if not query:
            return ""

        cleaned = query

        # First pass: remove multi-word exclusions (e.g., "-american football", "-super bowl")
        multi_word_exclusions = [
            kw for kw in MediaStackQueryBuilder.QUERY_CLEANING_EXCLUSIONS if " " in kw
        ]
        for kw in multi_word_exclusions:
            # Match "-american football" or "- american football"
            pattern = rf"\s*-\s*{re.escape(kw)}\b"
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Second pass: remove single-word exclusions
        single_word_exclusions = [
            kw for kw in MediaStackQueryBuilder.QUERY_CLEANING_EXCLUSIONS if " " not in kw
        ]
        for kw in single_word_exclusions:
            pattern = rf"\s*-\s*{re.escape(kw)}\b"
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Clean up multiple spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned


# ============================================
# CLI TEST
# ============================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    print("=" * 60)
    print("🔍 MEDIASTACK QUERY BUILDER TEST V2.0")
    print("=" * 60)

    builder = MediaStackQueryBuilder()

    # Test single query
    print("\n📝 Testing single query...")
    query1 = builder.build_news_query("Serie A injury lineup")
    print(f"   Query: {query1}")

    # Test batched query (deprecated, backward compatibility)
    print("\n📝 Testing batched query (deprecated)...")
    questions = ["Serie A injury", "Milan Inter lineup", "Juventus news"]
    query2 = builder.build_batched_query(questions)
    print(f"   Batched Query: {query2}")

    # Test intelligent batching
    print("\n📝 Testing intelligent batching...")
    questions_long = [
        "Serie A injury news",
        "Milan Inter lineup",
        "Juventus team news",
        "Roma Napoli match",
        "Atalanta Lazio",
        "Fiorentina Torino",
        "Bologna Verona",
        "Genoa Cagliari",
        "Monza Lecce",
        "Udinese Sassuolo",
    ]
    queries_v2 = builder.build_batched_queries(questions_long)
    print(f"   Packed {len(questions_long)} questions into {len(queries_v2)} queries:")
    for i, q in enumerate(queries_v2, 1):
        print(f"   Query {i}: {q[:80]}... (length: {len(q)})")

    # Test query cleaning
    print("\n📝 Testing query cleaning...")
    dirty = "football news -basket -basketball -women -american football"
    clean = MediaStackQueryBuilder._clean_query(dirty)
    print(f"   Dirty: {dirty}")
    print(f"   Clean: {clean}")

    # Test multi-word exclusion handling
    print("\n📝 Testing multi-word exclusion handling...")
    dirty_multi = "football -american football -super bowl -nfl"
    clean_multi = MediaStackQueryBuilder._clean_query(dirty_multi)
    print(f"   Dirty: {dirty_multi}")
    print(f"   Clean: {clean_multi}")

    print("\n✅ MediaStack Query Builder V2.0 test complete")
