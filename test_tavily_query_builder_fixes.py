#!/usr/bin/env python3
"""
Test script for TavilyQueryBuilder V8.0

Tests the query builder functions that are actually used in production:
1. Python 3.9 compatibility (Optional[list[str]] syntax)
2. build_match_enrichment_query()
3. build_news_verification_query()
4. build_biscotto_query()
5. build_twitter_recovery_query()

Note: V8.0 removed unused functions (parse_batched_response, split_long_query,
      estimate_query_count) that were never called in production.
"""

import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Add src to path
sys.path.insert(0, "src")

from src.ingestion.tavily_query_builder import TavilyQueryBuilder


def test_python_39_compatibility():
    """Test that the code uses Optional[list[str]] syntax compatible with Python 3.9"""
    print("\n" + "=" * 80)
    print("TEST 1: Python 3.9 Compatibility")
    print("=" * 80)

    try:
        # Test build_match_enrichment_query with Optional[list[str]]
        query = TavilyQueryBuilder.build_match_enrichment_query(
            home_team="Team A",
            away_team="Team B",
            match_date="2024-01-01",
            questions=None,  # Test None value
        )
        assert (
            query
            == "Team A vs Team B 2024-01-01: Recent team news and injuries | Head-to-head history | Current form and standings | Key player availability"
        )
        print("✅ build_match_enrichment_query with questions=None: PASSED")

        # Test with empty list
        query = TavilyQueryBuilder.build_match_enrichment_query(
            home_team="Team A", away_team="Team B", match_date="2024-01-01", questions=[]
        )
        assert query == "Team A vs Team B 2024-01-01"
        print("✅ build_match_enrichment_query with questions=[]: PASSED")

        # Test with custom questions
        query = TavilyQueryBuilder.build_match_enrichment_query(
            home_team="Team A",
            away_team="Team B",
            match_date="2024-01-01",
            questions=["Question 1", "Question 2"],
        )
        assert query == "Team A vs Team B 2024-01-01: Question 1 | Question 2"
        print("✅ build_match_enrichment_query with custom questions: PASSED")

        # Test build_twitter_recovery_query with Optional[list[str]]
        query = TavilyQueryBuilder.build_twitter_recovery_query(handle="@user", keywords=None)
        assert query == "Twitter @user recent tweets"
        print("✅ build_twitter_recovery_query with keywords=None: PASSED")

        query = TavilyQueryBuilder.build_twitter_recovery_query(
            handle="@user", keywords=["keyword1", "keyword2"]
        )
        assert query == "Twitter @user recent tweets keyword1 keyword2"
        print("✅ build_twitter_recovery_query with keywords: PASSED")

        print("\n✅ TEST 1: Python 3.9 Compatibility - ALL PASSED")
        return True

    except Exception as e:
        print(f"\n❌ TEST 1: Python 3.9 Compatibility - FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_build_match_enrichment_query():
    """Test build_match_enrichment_query() edge cases"""
    print("\n" + "=" * 80)
    print("TEST 2: build_match_enrichment_query() Edge Cases")
    print("=" * 80)

    try:
        # Test 1: Empty home team
        query = TavilyQueryBuilder.build_match_enrichment_query(
            home_team="", away_team="Team B", match_date="2024-01-01"
        )
        assert query == ""
        print("✅ build_match_enrichment_query with empty home_team: PASSED")

        # Test 2: Empty away team
        query = TavilyQueryBuilder.build_match_enrichment_query(
            home_team="Team A", away_team="", match_date="2024-01-01"
        )
        assert query == ""
        print("✅ build_match_enrichment_query with empty away_team: PASSED")

        # Test 3: None home team
        query = TavilyQueryBuilder.build_match_enrichment_query(
            home_team=None, away_team="Team B", match_date="2024-01-01"
        )
        assert query == ""
        print("✅ build_match_enrichment_query with None home_team: PASSED")

        # Test 4: Empty match date (should still work)
        query = TavilyQueryBuilder.build_match_enrichment_query(
            home_team="Team A", away_team="Team B", match_date=""
        )
        assert "Team A vs Team B" in query
        print("✅ build_match_enrichment_query with empty match_date: PASSED")

        print("\n✅ TEST 2: build_match_enrichment_query() Edge Cases - ALL PASSED")
        return True

    except Exception as e:
        print(f"\n❌ TEST 2: build_match_enrichment_query() Edge Cases - FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_build_news_verification_query():
    """Test build_news_verification_query() edge cases"""
    print("\n" + "=" * 80)
    print("TEST 3: build_news_verification_query() Edge Cases")
    print("=" * 80)

    try:
        # Test 1: Empty news title
        query = TavilyQueryBuilder.build_news_verification_query(news_title="", team_name="Team A")
        assert query == ""
        print("✅ build_news_verification_query with empty news_title: PASSED")

        # Test 2: None news title
        query = TavilyQueryBuilder.build_news_verification_query(
            news_title=None, team_name="Team A"
        )
        assert query == ""
        print("✅ build_news_verification_query with None news_title: PASSED")

        # Test 3: Very long title (should truncate)
        long_title = "A" * 300
        query = TavilyQueryBuilder.build_news_verification_query(
            news_title=long_title, team_name="Team A"
        )
        assert len(query) < 350  # Should be truncated
        print("✅ build_news_verification_query with long title: PASSED")

        # Test 4: With all parameters
        query = TavilyQueryBuilder.build_news_verification_query(
            news_title="Breaking News", team_name="Team A", additional_context="urgent"
        )
        assert "Verify:" in query
        assert "Team A" in query
        assert "urgent" in query
        print("✅ build_news_verification_query with all parameters: PASSED")

        print("\n✅ TEST 3: build_news_verification_query() Edge Cases - ALL PASSED")
        return True

    except Exception as e:
        print(f"\n❌ TEST 3: build_news_verification_query() Edge Cases - FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_build_biscotto_query():
    """Test build_biscotto_query() edge cases"""
    print("\n" + "=" * 80)
    print("TEST 4: build_biscotto_query() Edge Cases")
    print("=" * 80)

    try:
        # Test 1: Empty home team
        query = TavilyQueryBuilder.build_biscotto_query(
            home_team="", away_team="Team B", league="Serie A", season_context="end of season"
        )
        assert query == ""
        print("✅ build_biscotto_query with empty home_team: PASSED")

        # Test 2: Empty away team
        query = TavilyQueryBuilder.build_biscotto_query(
            home_team="Team A", away_team="", league="Serie A", season_context="end of season"
        )
        assert query == ""
        print("✅ build_biscotto_query with empty away_team: PASSED")

        # Test 3: Missing league (should still work)
        query = TavilyQueryBuilder.build_biscotto_query(
            home_team="Team A", away_team="Team B", league="", season_context="end of season"
        )
        assert "Team A vs Team B" in query
        assert "mutual benefit" in query
        print("✅ build_biscotto_query with empty league: PASSED")

        # Test 4: Full parameters
        query = TavilyQueryBuilder.build_biscotto_query(
            home_team="Team A",
            away_team="Team B",
            league="Serie A",
            season_context="last 3 matches of season",
        )
        assert "Team A vs Team B" in query
        assert "Serie A" in query
        assert "mutual benefit" in query
        print("✅ build_biscotto_query with full parameters: PASSED")

        print("\n✅ TEST 4: build_biscotto_query() Edge Cases - ALL PASSED")
        return True

    except Exception as e:
        print(f"\n❌ TEST 4: build_biscotto_query() Edge Cases - FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_build_twitter_recovery_query():
    """Test build_twitter_recovery_query() edge cases"""
    print("\n" + "=" * 80)
    print("TEST 5: build_twitter_recovery_query() Edge Cases")
    print("=" * 80)

    try:
        # Test 1: Empty handle
        query = TavilyQueryBuilder.build_twitter_recovery_query(handle="")
        assert query == ""
        print("✅ build_twitter_recovery_query with empty handle: PASSED")

        # Test 2: None handle
        query = TavilyQueryBuilder.build_twitter_recovery_query(handle=None)
        assert query == ""
        print("✅ build_twitter_recovery_query with None handle: PASSED")

        # Test 3: Handle without @ (should add it)
        query = TavilyQueryBuilder.build_twitter_recovery_query(handle="user")
        assert "@user" in query
        print("✅ build_twitter_recovery_query with handle without @: PASSED")

        # Test 4: Handle with @ (should not duplicate)
        query = TavilyQueryBuilder.build_twitter_recovery_query(handle="@user")
        assert query.count("@") == 1
        print("✅ build_twitter_recovery_query with handle with @: PASSED")

        # Test 5: With keywords (should limit to 5)
        many_keywords = ["kw1", "kw2", "kw3", "kw4", "kw5", "kw6", "kw7"]
        query = TavilyQueryBuilder.build_twitter_recovery_query(
            handle="@user", keywords=many_keywords
        )
        assert "kw1" in query
        assert "kw5" in query
        assert "kw6" not in query  # Should be limited to 5
        print("✅ build_twitter_recovery_query with many keywords: PASSED")

        print("\n✅ TEST 5: build_twitter_recovery_query() Edge Cases - ALL PASSED")
        return True

    except Exception as e:
        print(f"\n❌ TEST 5: build_twitter_recovery_query() Edge Cases - FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("TAVILY QUERY BUILDER V8.0 - TEST SUITE")
    print("=" * 80)

    results = []

    results.append(("Python 3.9 Compatibility", test_python_39_compatibility()))
    results.append(
        ("build_match_enrichment_query() Edge Cases", test_build_match_enrichment_query())
    )
    results.append(
        ("build_news_verification_query() Edge Cases", test_build_news_verification_query())
    )
    results.append(("build_biscotto_query() Edge Cases", test_build_biscotto_query()))
    results.append(
        ("build_twitter_recovery_query() Edge Cases", test_build_twitter_recovery_query())
    )

    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False

    print("=" * 80)

    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
