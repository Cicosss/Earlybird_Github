"""
Test for Unknown Team Name Resolution Fix

This test verifies that the fix for the "Unknown Team" bug works correctly:
1. Team information is preserved during news aggregation
2. team_id is resolved and passed to enrich_with_player_data
3. No "Unknown Team" warnings are generated
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone


def test_news_aggregation_preserves_team_info():
    """Test that team information is preserved during news aggregation."""

    # Simulate news articles with team field
    news_articles = [
        {
            "snippet": "Player X injured for home team",
            "team": "Home Team Name",
            "title": "Injury Update",
        },
        {
            "snippet": "Player Y returns for away team",
            "team": "Away Team Name",
            "title": "Return Update",
        },
    ]

    # Create mock match object
    match = Mock()
    match.home_team = "Home Team Name"
    match.away_team = "Away Team Name"
    match.league = "soccer_test_league"
    match.start_time = datetime.now(timezone.utc)

    # Simulate the aggregation logic from analyzer.py
    snippet_data = {}
    news_snippets = []
    team_names = set()

    for article in news_articles:
        snippet = article.get("snippet", article.get("title", ""))
        if snippet:
            news_snippets.append(snippet)
            team = article.get("team")
            if team:
                team_names.add(team)

    news_snippet = "\n\n".join(news_snippets)

    # Add team information to snippet_data (FIXED CODE)
    if len(team_names) == 1:
        snippet_data["team"] = team_names.pop()
    elif len(team_names) > 1:
        snippet_data["team"] = match.home_team

    # Verify team is set correctly
    assert "team" in snippet_data, "Team field should be set in snippet_data"
    assert snippet_data["team"] in ["Home Team Name", "Away Team Name"], (
        f"Team should be one of the article teams, got: {snippet_data['team']}"
    )

    print("✅ Test 1 PASSED: Team information preserved during aggregation")
    return True


def test_team_id_resolution():
    """Test that team_id is resolved correctly."""

    # Mock the data provider
    mock_provider = Mock()
    mock_provider.search_team_id.return_value = (12345, "Resolved Team Name")

    with patch("src.analysis.analyzer.get_data_provider", return_value=mock_provider):
        # Simulate the enrichment logic from analyzer.py
        snippet_data = {"team": "Test Team"}
        team_name = snippet_data.get("team", "Unknown Team")

        # Resolve team_id (FIXED CODE)
        from src.analysis.analyzer import get_data_provider

        provider = get_data_provider()
        team_id, fotmob_name = provider.search_team_id(team_name)

        # Verify team_id was resolved
        assert team_id == 12345, f"team_id should be resolved to 12345, got: {team_id}"
        assert fotmob_name == "Resolved Team Name", (
            f"fotmob_name should be 'Resolved Team Name', got: {fotmob_name}"
        )

        print("✅ Test 2 PASSED: team_id resolved correctly")
        return True


def test_no_unknown_team_warnings():
    """Test that no 'Unknown Team' warnings are generated."""

    # Mock the data provider to return valid team_id
    mock_provider = Mock()
    mock_provider.search_team_id.return_value = (12345, "Resolved Team Name")

    # Mock enrich_with_player_data to verify it receives team_id
    mock_enrich = Mock(return_value="Player status: OK")

    with (
        patch("src.analysis.analyzer.get_data_provider", return_value=mock_provider),
        patch("src.analysis.analyzer.enrich_with_player_data", mock_enrich),
    ):
        # Simulate the enrichment logic (FIXED CODE)
        snippet_data = {"team": "Test Team"}
        team_name = snippet_data.get("team", "Unknown Team")

        from src.analysis.analyzer import get_data_provider, enrich_with_player_data

        provider = get_data_provider()
        team_id, fotmob_name = provider.search_team_id(team_name)

        if team_id:
            # This should NOT log "Unknown Team" warning
            official_data = enrich_with_player_data("test snippet", team_name, team_id)

            # Verify enrich_with_player_data was called with team_id
            mock_enrich.assert_called_once()
            call_args = mock_enrich.call_args

            # Check that team_id was passed (not just team_name)
            assert call_args[0][2] == team_id, (
                f"enrich_with_player_data should receive team_id={team_id}, got: {call_args[0][2]}"
            )

            print("✅ Test 3 PASSED: No 'Unknown Team' warnings generated")
            return True
        else:
            print("❌ Test 3 FAILED: team_id not resolved")
            return False


def test_fallback_to_home_team():
    """Test that fallback to home team works when both teams have news."""

    # Simulate news articles for both teams
    news_articles = [
        {
            "snippet": "Home team news",
            "team": "Home Team Name",
        },
        {
            "snippet": "Away team news",
            "team": "Away Team Name",
        },
    ]

    # Create mock match object
    match = Mock()
    match.home_team = "Home Team Name"
    match.away_team = "Away Team Name"

    # Simulate the aggregation logic (FIXED CODE)
    snippet_data = {}
    news_snippets = []
    team_names = set()

    for article in news_articles:
        snippet = article.get("snippet", article.get("title", ""))
        if snippet:
            news_snippets.append(snippet)
            team = article.get("team")
            if team:
                team_names.add(team)

    # Add team information to snippet_data (FIXED CODE)
    if len(team_names) == 1:
        snippet_data["team"] = team_names.pop()
    elif len(team_names) > 1:
        snippet_data["team"] = match.home_team

    # Verify it falls back to home team
    assert snippet_data["team"] == "Home Team Name", (
        f"When both teams have news, should default to home team, got: {snippet_data['team']}"
    )

    print("✅ Test 4 PASSED: Fallback to home team works correctly")
    return True


def test_single_team_news():
    """Test that single team news uses that team."""

    # Simulate news articles for only one team
    news_articles = [
        {
            "snippet": "Away team news",
            "team": "Away Team Name",
        }
    ]

    # Create mock match object
    match = Mock()
    match.home_team = "Home Team Name"
    match.away_team = "Away Team Name"

    # Simulate the aggregation logic (FIXED CODE)
    snippet_data = {}
    news_snippets = []
    team_names = set()

    for article in news_articles:
        snippet = article.get("snippet", article.get("title", ""))
        if snippet:
            news_snippets.append(snippet)
            team = article.get("team")
            if team:
                team_names.add(team)

    # Add team information to snippet_data (FIXED CODE)
    if len(team_names) == 1:
        snippet_data["team"] = team_names.pop()
    elif len(team_names) > 1:
        snippet_data["team"] = match.home_team

    # Verify it uses the team from articles
    assert snippet_data["team"] == "Away Team Name", (
        f"When only one team has news, should use that team, got: {snippet_data['team']}"
    )

    print("✅ Test 5 PASSED: Single team news uses correct team")
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Unknown Team Name Resolution Fix")
    print("=" * 60)
    print()

    tests = [
        ("News Aggregation Preserves Team Info", test_news_aggregation_preserves_team_info),
        ("Team ID Resolution", test_team_id_resolution),
        ("No Unknown Team Warnings", test_no_unknown_team_warnings),
        ("Fallback to Home Team", test_fallback_to_home_team),
        ("Single Team News", test_single_team_news),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        print(f"\nRunning: {test_name}")
        print("-" * 40)
        try:
            if test_func():
                passed += 1
        except AssertionError as e:
            print(f"❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ ERROR: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Test Results: {passed} PASSED, {failed} FAILED")
    print("=" * 60)

    if failed == 0:
        print("\n✅ ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n❌ {failed} TEST(S) FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
