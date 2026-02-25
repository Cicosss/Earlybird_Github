"""
DuckDuckGo Query Optimization Tests - V9.5

Tests for DDG query optimization and degradation strategy
implemented in search_provider.py and tavily_provider.py.

Created: 2026-02-19 (COVE Verification Fix)
"""

import pytest

from src.ingestion.search_provider import SearchProvider


class TestDDGQueryOptimization:
    """Test DDG query optimization functionality."""

    @pytest.fixture
    def search_provider(self):
        """Create SearchProvider instance for testing."""
        return SearchProvider()

    def test_optimize_query_short_query(self, search_provider):
        """Test that short queries are not modified."""
        short_query = "Inter Milan injury"
        result = search_provider._optimize_query_for_ddg(short_query)

        assert result == short_query, "Short query should not be modified"
        assert len(result) <= 280, "Short query should be within DDG limit"

    def test_optimize_query_long_query(self, search_provider):
        """Test that long queries are optimized to fit within DDG limit."""
        from src.ingestion.search_provider import SPORT_EXCLUSION_TERMS

        # Create a long query that exceeds DDG limit
        long_query = f'"Team Name" injury {SPORT_EXCLUSION_TERMS} ' * 10
        result = search_provider._optimize_query_for_ddg(long_query)

        assert len(result) <= 280, "Optimized query should be within DDG limit"
        assert len(result) < len(long_query), "Optimized query should be shorter"

    def test_get_query_variations_simple_query(self, search_provider):
        """Test that simple queries generate 1 variation."""
        simple_query = "Team Name injury"
        variations = search_provider._get_query_variations(simple_query)

        assert len(variations) == 1, "Simple query should generate 1 variation"
        assert variations[0] == simple_query, "Variation should match original query"

    def test_get_query_variations_with_exclusions(self, search_provider):
        """Test that queries with exclusions generate multiple variations."""
        from src.ingestion.search_provider import SPORT_EXCLUSION_TERMS

        query_with_exclusions = f'"Team Name" injury {SPORT_EXCLUSION_TERMS}'
        variations = search_provider._get_query_variations(query_with_exclusions)

        # Should generate at least 2 variations
        assert len(variations) >= 2, "Query with exclusions should generate at least 2 variations"
        # Check that one variation removes exclusions
        has_variation_without_exclusions = any(SPORT_EXCLUSION_TERMS not in v for v in variations)
        assert has_variation_without_exclusions, "At least one variation should not have exclusions"

    def test_get_query_variations_with_site_dork(self, search_provider):
        """Test that queries with site dork generate multiple variations."""
        query_with_site = '"Team Name" injury (site:domain1.com OR site:domain2.com)'
        variations = search_provider._get_query_variations(query_with_site)

        # Should generate at least 2 variations
        assert len(variations) >= 2, "Query with site dork should generate at least 2 variations"
        # Check that one variation removes site dork
        has_variation_without_site = any("site:" not in v for v in variations)
        assert has_variation_without_site, "At least one variation should remove site dork"

    def test_get_query_variations_complex_query(self, search_provider):
        """Test that complex queries generate multiple variations."""
        from src.ingestion.search_provider import SPORT_EXCLUSION_TERMS

        complex_query = (
            f'"Team Name" injury {SPORT_EXCLUSION_TERMS} '
            "(site:domain1.com OR site:domain2.com OR site:domain3.com OR site:domain4.com)"
        )
        variations = search_provider._get_query_variations(complex_query)

        # Should generate multiple variations
        assert len(variations) >= 2, "Complex query should generate at least 2 variations"

        # Check that all variations are within DDG limit
        for i, variation in enumerate(variations):
            assert len(variation) <= 280, f"Variation {i + 1} should be within DDG limit"

        # Check that last variation is simplified (team name + football)
        assert "Team Name" in variations[-1], "Last variation should contain team name"
        assert "football" in variations[-1], "Last variation should contain 'football'"

    def test_all_variations_within_ddg_limit(self, search_provider):
        """Test that all query variations are within DDG's ~300 char limit."""
        from src.ingestion.search_provider import SPORT_EXCLUSION_TERMS

        # Test various query types
        test_queries = [
            "Simple query",
            f'"Team Name" injury {SPORT_EXCLUSION_TERMS}',
            '"Team Name" injury (site:domain1.com OR site:domain2.com OR site:domain3.com)',
            f'"Team Name" injury {SPORT_EXCLUSION_TERMS} (site:domain1.com OR site:domain2.com OR site:domain3.com OR site:domain4.com OR site:domain5.com)',
        ]

        for query in test_queries:
            variations = search_provider._get_query_variations(query)
            for i, variation in enumerate(variations):
                assert len(variation) <= 280, (
                    f"Query '{query[:30]}...' variation {i + 1} exceeds DDG limit: {len(variation)} chars"
                )

    def test_query_degradation_order(self, search_provider):
        """Test that query variations are ordered from most specific to most general."""
        from src.ingestion.search_provider import SPORT_EXCLUSION_TERMS

        complex_query = (
            f'"Team Name" injury {SPORT_EXCLUSION_TERMS} (site:domain1.com OR site:domain2.com)'
        )
        variations = search_provider._get_query_variations(complex_query)

        # First variation should be optimized (most specific)
        assert "Team Name" in variations[0], "Variation 1 should contain team name"
        assert "injury" in variations[0], "Variation 1 should contain keywords"

        # Last variation should be simplified (most general)
        assert "football" in variations[-1], "Last variation should contain 'football'"
        # Last variation should not have exclusions or site dork
        assert SPORT_EXCLUSION_TERMS not in variations[-1], (
            "Last variation should not have exclusions"
        )
        assert "site:" not in variations[-1], "Last variation should not have site dork"


class TestTavilyDDGOptimization:
    """Test DDG query optimization in tavily_provider.py."""

    @pytest.fixture
    def tavily_provider(self):
        """Create TavilyProvider instance for testing."""
        try:
            from src.ingestion.tavily_provider import TavilyProvider

            return TavilyProvider()
        except ImportError:
            pytest.skip("TavilyProvider not available")

    def test_optimize_query_for_ddg_short_query(self, tavily_provider):
        """Test that short queries are not modified."""
        short_query = "Inter Milan injury"
        result = tavily_provider._optimize_query_for_ddg(short_query)

        assert result == short_query, "Short query should not be modified"
        assert len(result) <= 280, "Short query should be within DDG limit"

    def test_optimize_query_for_ddg_long_query(self, tavily_provider):
        """Test that long queries are optimized."""
        from src.ingestion.search_provider import SPORT_EXCLUSION_TERMS

        long_query = (
            f'"Team Name" injury {SPORT_EXCLUSION_TERMS} '
            "(site:domain1.com OR site:domain2.com OR site:domain3.com OR site:domain4.com OR site:domain5.com)"
        )
        result = tavily_provider._optimize_query_for_ddg(long_query)

        assert len(result) <= 280, "Optimized query should be within DDG limit"
        # Either exclusions removed or site dork removed
        assert SPORT_EXCLUSION_TERMS not in result or "site:" not in result, (
            "Long query should have exclusions or site dork removed"
        )
