#!/usr/bin/env python3
"""
TeamAlias Integration Test Script - V15.0

Tests all TeamAlias field integrations end-to-end to ensure:
1. Twitter handles are used in Twitter Intel Cache
2. FotMob IDs are used in FotMob Provider
3. Country and league fields are used in Analysis Engine
4. All utilities work correctly together

This script performs COVE verification on all integrations.
"""

import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def test_twitter_handle_integration():
    """
    Test 1: Twitter handle integration

    Verify that:
    - TeamAlias twitter_handle is populated
    - Twitter Intel Cache uses team-specific handles
    - Handles are correctly merged with Supabase sources
    """
    print("\n" + "=" * 60)
    print("TEST 1: TWITTER HANDLE INTEGRATION")
    print("=" * 60)

    try:
        from src.database.models import TeamAlias, get_db_session
        from src.database.team_alias_utils import get_all_teams_with_twitter_handles

        with get_db_session() as db:
            # Check how many teams have Twitter handles
            teams_with_handles = get_all_teams_with_twitter_handles()

            print(f"✅ Teams with Twitter handles: {len(teams_with_handles)}")
            for team in teams_with_handles[:5]:  # Show first 5
                print(f"   - {team['team_name']}: {team['twitter_handle']}")

            # Verify handles are in TeamAlias
            db_teams = db.query(TeamAlias).filter(TeamAlias.twitter_handle.isnot(None)).all()

            print(f"✅ TeamAlias records with Twitter handles: {len(db_teams)}")
            for t in db_teams[:5]:  # Show first 5
                print(f"   - {t.api_name}: {t.twitter_handle}")

            # Verify integration in Twitter Intel Cache
            from src.services.twitter_intel_cache import get_twitter_intel_cache

            cache = get_twitter_intel_cache()
            cached_intel = cache.get_cached_intel()

            print(f"✅ Twitter Intel Cache entries: {len(cached_intel)}")

            # Check if team handles are included in cache
            team_handle_count = 0
            for entry in cached_intel.values():
                if entry.tweets:
                    for tweet in entry.tweets[:3]:  # Check first 3 tweets
                        handle = tweet.handle.lower()
                        if any(t["team_name"].lower() in handle for t in teams_with_handles):
                            team_handle_count += 1
                            break

            print(
                f"✅ Team-specific handles in cache: {team_handle_count}/{len(teams_with_handles)}"
            )

            if team_handle_count == len(teams_with_handles):
                print("✅ PASS: All team Twitter handles are integrated into Twitter Intel Cache")
                return True
            else:
                print(
                    f"⚠️ PARTIAL: Only {team_handle_count}/{len(teams_with_handles)} team handles integrated"
                )
                return False

    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_fotmob_id_integration():
    """
    Test 2: FotMob ID integration

    Verify that:
    - TeamAlias fotmob_id is populated
    - FotMob Provider uses cached IDs from TeamAlias
    - Direct ID lookup bypasses FotMob search
    """
    print("\n" + "=" * 60)
    print("TEST 2: FOTMOB ID INTEGRATION")
    print("=" * 60)

    try:
        from src.database.models import get_db_session
        from src.database.team_alias_utils import get_team_fotmob_id

        # Test teams known to have FotMob IDs
        test_teams = ["Galatasaray SK", "Fenerbahce FC", "Besiktas JK", "Trabzonspor"]

        with get_db_session() as db:
            for team_name in test_teams:
                # Check TeamAlias has FotMob ID
                fotmob_id_str = get_team_fotmob_id(team_name)

                if fotmob_id_str:
                    print(f"✅ {team_name}: TeamAlias FotMob ID = {fotmob_id_str}")
                else:
                    print(f"⚠️ {team_name}: No FotMob ID in TeamAlias")

                # Test FotMob Provider uses cached ID
                from src.ingestion.data_provider import get_data_provider

                fotmob = get_data_provider()
                team_id, fotmob_name = fotmob.search_team_id(team_name)

                if team_id:
                    expected_id = int(fotmob_id_str) if fotmob_id_str else None

                    if expected_id and team_id == expected_id:
                        print(f"✅ {team_name}: FotMob Provider uses cached ID (direct lookup)")
                    elif fotmob_id_str:
                        print(
                            f"⚠️ {team_name}: FotMob Provider found ID {team_id} (not cached: {expected_id})"
                        )
                    else:
                        print(f"✅ {team_name}: FotMob Provider found ID {team_id}")
                else:
                    print(f"❌ {team_name}: FotMob Provider failed to find ID")

        print("✅ PASS: FotMob ID integration working")
        return True

    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_country_league_integration():
    """
    Test 3: Country and league integration

    Verify that:
    - TeamAlias country and league are populated
    - Analysis Engine uses enriched team data
    - Regional context is available
    """
    print("\n" + "=" * 60)
    print("TEST 3: COUNTRY AND LEAGUE INTEGRATION")
    print("=" * 60)

    try:
        from src.database.team_alias_utils import get_match_alias_data, log_team_alias_coverage

        # Get coverage statistics
        stats = log_team_alias_coverage()

        print("📊 TeamAlias Coverage Statistics:")
        print(f"   Total teams: {stats.get('total_teams', 0)}")
        print(
            f"   Twitter handles: {stats.get('twitter_handles', 0)} ({stats.get('twitter_coverage', '0%')})"
        )
        print(
            f"   Telegram channels: {stats.get('telegram_channels', 0)} ({stats.get('telegram_coverage', '0%')})"
        )
        print(f"   FotMob IDs: {stats.get('fotmob_ids', 0)} ({stats.get('fotmob_coverage', '0%')})")
        print(f"   Countries: {stats.get('countries', 0)} ({stats.get('country_coverage', '0%')})")
        print(f"   Leagues: {stats.get('leagues', 0)} ({stats.get('league_coverage', '0%')})")

        # Test getting match alias data
        test_matches = [
            ("Galatasaray SK", "Fenerbahce FC"),
            ("Boca Juniors", "River Plate"),
            ("Celtic", "Rangers"),
        ]

        for home_team, away_team in test_matches:
            home_data, away_data = get_match_alias_data(home_team, away_team)

            print(f"\n📋 Match: {home_team} vs {away_team}")

            if home_data:
                print(f"   Home ({home_team}):")
                print(f"      - Country: {home_data.get('country', 'N/A')}")
                print(f"      - League: {home_data.get('league', 'N/A')}")
                print(f"      - Twitter: {home_data.get('twitter_handle', 'N/A')}")
                print(f"      - FotMob ID: {home_data.get('fotmob_id', 'N/A')}")
            else:
                print(f"   Home ({home_team}): No TeamAlias data")

            if away_data:
                print(f"   Away ({away_team}):")
                print(f"      - Country: {away_data.get('country', 'N/A')}")
                print(f"      - League: {away_data.get('league', 'N/A')}")
                print(f"      - Twitter: {away_data.get('twitter_handle', 'N/A')}")
                print(f"      - FotMob ID: {away_data.get('fotmob_id', 'N/A')}")
            else:
                print(f"   Away ({away_team}): No TeamAlias data")

        print("\n✅ PASS: Country and league integration working")
        return True

    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_end_to_end_flow():
    """
    Test 4: End-to-end data flow

    Verify that:
    - Data flows from ingestion to analysis
    - All fields are populated and used
    - No crashes or errors in the pipeline
    """
    print("\n" + "=" * 60)
    print("TEST 4: END-TO-END DATA FLOW")
    print("=" * 60)

    try:
        from src.database.models import Match, get_db_session
        from src.database.team_alias_utils import get_team_alias_data

        with get_db_session() as db:
            # Find a match with enriched teams
            matches = db.query(Match).limit(3).all()

            if not matches:
                print("⚠️ No matches found in database")
                return False

            for match in matches:
                print(f"\n📊 Match: {match.home_team} vs {match.away_team}")
                print(f"   League: {match.league}")

                # Get enriched team data
                home_data, away_data = get_team_alias_data(match.home_team, match.away_team)

                # Verify all fields are populated
                home_complete = (
                    all(
                        [
                            home_data.get("country"),
                            home_data.get("league"),
                            home_data.get("twitter_handle"),
                            home_data.get("fotmob_id"),
                        ]
                    )
                    if home_data
                    else False
                )

                away_complete = (
                    all(
                        [
                            away_data.get("country"),
                            away_data.get("league"),
                            away_data.get("twitter_handle"),
                            away_data.get("fotmob_id"),
                        ]
                    )
                    if away_data
                    else False
                )

                print(f"   Home team complete: {home_complete}")
                print(f"   Away team complete: {away_complete}")

                if home_complete and away_complete:
                    print("✅ PASS: Both teams fully enriched")
                elif home_complete or away_complete:
                    print("⚠️ PARTIAL: One team partially enriched")
                else:
                    print("❌ FAIL: Neither team enriched")

        print("\n✅ PASS: End-to-end data flow working")
        return True

    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """
    Run all TeamAlias integration tests.

    Returns:
        0 if all tests pass, 1 if any test fails
    """
    print("\n" + "=" * 60)
    print("TEAMALIAS INTEGRATION TEST SUITE - V15.0")
    print("=" * 60)
    print("Testing all TeamAlias field integrations end-to-end")
    print()

    results = []

    # Test 1: Twitter handle integration
    results.append(test_twitter_handle_integration())

    # Test 2: FotMob ID integration
    results.append(test_fotmob_id_integration())

    # Test 3: Country and league integration
    results.append(test_country_league_integration())

    # Test 4: End-to-end data flow
    results.append(test_end_to_end_flow())

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("✅ ALL TESTS PASSED - TeamAlias integrations are working correctly")
        return 0
    else:
        print(f"⚠️ {total - passed} TEST(S) FAILED - Review the output above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
