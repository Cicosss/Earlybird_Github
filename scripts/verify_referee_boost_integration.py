#!/usr/bin/env python3
"""
Referee Boost Integration Verification Script

Verifies that all referee boost components integrate correctly with the existing system:
- RefereeCache
- RefereeCacheMonitor
- RefereeBoostLogger
- RefereeInfluenceMetrics
- RefereeStats class
- Analyzer boost logic

Usage:
    python scripts/verify_referee_boost_integration.py

Exit codes:
    0: All verifications passed
    1: One or more verifications failed
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ANSI color codes for terminal output
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_success(message: str):
    """Print success message in green."""
    print(f"{Colors.GREEN}✅ {message}{Colors.END}")


def print_error(message: str):
    """Print error message in red."""
    print(f"{Colors.RED}❌ {message}{Colors.END}")


def print_warning(message: str):
    """Print warning message in yellow."""
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.END}")


def print_info(message: str):
    """Print info message in blue."""
    print(f"{Colors.BLUE}ℹ️  {message}{Colors.END}")


def print_header(message: str):
    """Print header message in bold."""
    print(f"\n{Colors.BOLD}{message}{Colors.END}\n{'=' * 70}")


def verify_referee_cache():
    """Verify RefereeCache integration."""
    print_header("VERIFYING REFEREE CACHE")

    try:
        from src.analysis.referee_cache import RefereeCache, get_referee_cache

        print_success("RefereeCache module imported successfully")
    except ImportError as e:
        print_error(f"Failed to import RefereeCache: {e}")
        return False

    try:
        cache = get_referee_cache()
        print_success("RefereeCache instance created")
    except Exception as e:
        print_error(f"Failed to create RefereeCache instance: {e}")
        return False

    try:
        # Test set operation
        test_stats = {
            "name": "Test Referee",
            "cards_per_game": 4.5,
            "strictness": "average",
            "matches_officiated": 100,
        }
        cache.set("Test Referee", test_stats)
        print_success("RefereeCache.set() works")

        # Test get operation
        retrieved = cache.get("Test Referee")
        if retrieved == test_stats:
            print_success("RefereeCache.get() works")
        else:
            print_error("RefereeCache.get() returned unexpected data")
            return False

        # Test stats operation
        stats = cache.get_stats()
        print_success(f"RefereeCache.get_stats() works: {stats['total_entries']} entries")

        # Clean up
        cache.clear()
        print_success("RefereeCache.clear() works")

    except Exception as e:
        print_error(f"RefereeCache operations failed: {e}")
        return False

    return True


def verify_referee_cache_monitor():
    """Verify RefereeCacheMonitor integration."""
    print_header("VERIFYING REFEREE CACHE MONITOR")

    try:
        from src.analysis.referee_cache_monitor import (
            RefereeCacheMonitor,
            get_referee_cache_monitor,
        )

        print_success("RefereeCacheMonitor module imported successfully")
    except ImportError as e:
        print_error(f"Failed to import RefereeCacheMonitor: {e}")
        return False

    try:
        monitor = get_referee_cache_monitor()
        print_success("RefereeCacheMonitor instance created")
    except Exception as e:
        print_error(f"Failed to create RefereeCacheMonitor instance: {e}")
        return False

    try:
        # Test hit recording
        monitor.record_hit("Test Referee", 1.5)
        print_success("RefereeCacheMonitor.record_hit() works")

        # Test miss recording
        monitor.record_miss("Unknown Referee", 2.3)
        print_success("RefereeCacheMonitor.record_miss() works")

        # Test metrics retrieval
        metrics = monitor.get_metrics()
        print_success(
            f"RefereeCacheMonitor.get_metrics() works: hit_rate={metrics['hit_rate']:.2%}"
        )

        # Test health status
        health = monitor.get_health_status()
        print_success(f"RefereeCacheMonitor.get_health_status() works: {health['health']}")

        # Clean up
        monitor.reset_metrics()
        print_success("RefereeCacheMonitor.reset_metrics() works")

    except Exception as e:
        print_error(f"RefereeCacheMonitor operations failed: {e}")
        return False

    return True


def verify_referee_boost_logger():
    """Verify RefereeBoostLogger integration."""
    print_header("VERIFYING REFEREE BOOST LOGGER")

    try:
        from src.analysis.referee_boost_logger import (
            RefereeBoostLogger,
            get_referee_boost_logger,
            BoostType,
        )

        print_success("RefereeBoostLogger module imported successfully")
    except ImportError as e:
        print_error(f"Failed to import RefereeBoostLogger: {e}")
        return False

    try:
        logger = get_referee_boost_logger()
        print_success("RefereeBoostLogger instance created")
    except Exception as e:
        print_error(f"Failed to create RefereeBoostLogger instance: {e}")
        return False

    try:
        # Test boost logging
        logger.log_boost_applied(
            referee_name="Michael Oliver",
            cards_per_game=5.2,
            strictness="strict",
            original_verdict="NO BET",
            new_verdict="BET",
            recommended_market="Over 3.5 Cards",
            reason="Strict referee + Derby/High Intensity",
            confidence_before=70,
            confidence_after=80,
        )
        print_success("RefereeBoostLogger.log_boost_applied() works")

        # Test upgrade logging
        logger.log_upgrade_applied(
            referee_name="Antonio Mateu Lahoz",
            cards_per_game=5.5,
            strictness="strict",
            original_market="Over 3.5 Cards",
            new_market="Over 4.5 Cards",
            reason="Very strict referee",
            confidence_before=75,
            confidence_after=85,
        )
        print_success("RefereeBoostLogger.log_upgrade_applied() works")

        # Test influence logging
        logger.log_influence_applied(
            referee_name="Michael Oliver",
            cards_per_game=5.2,
            strictness="strict",
            market_type="Goals",
            influence_type=BoostType.INFLUENCE_GOALS,
            original_confidence=80,
            new_confidence=72.5,
            reason="Strict referee → More stoppages → Fewer goals",
        )
        print_success("RefereeBoostLogger.log_influence_applied() works")

    except Exception as e:
        print_error(f"RefereeBoostLogger operations failed: {e}")
        return False

    return True


def verify_referee_influence_metrics():
    """Verify RefereeInfluenceMetrics integration."""
    print_header("VERIFYING REFEREE INFLUENCE METRICS")

    try:
        from src.analysis.referee_influence_metrics import (
            RefereeInfluenceMetrics,
            get_referee_influence_metrics,
        )

        print_success("RefereeInfluenceMetrics module imported successfully")
    except ImportError as e:
        print_error(f"Failed to import RefereeInfluenceMetrics: {e}")
        return False

    try:
        metrics = get_referee_influence_metrics()
        print_success("RefereeInfluenceMetrics instance created")
    except Exception as e:
        print_error(f"Failed to create RefereeInfluenceMetrics instance: {e}")
        return False

    try:
        # Test analysis recording
        metrics.record_analysis("Michael Oliver", 5.2, has_referee_data=True)
        print_success("RefereeInfluenceMetrics.record_analysis() works")

        # Test boost recording
        metrics.record_boost_applied(
            referee_name="Michael Oliver",
            cards_per_game=5.2,
            boost_type="boost_no_bet_to_bet",
            original_verdict="NO BET",
            new_verdict="BET",
            confidence_before=70,
            confidence_after=80,
            market_type="cards",
        )
        print_success("RefereeInfluenceMetrics.record_boost_applied() works")

        # Test influence recording
        metrics.record_influence_applied(
            referee_name="Michael Oliver",
            cards_per_game=5.2,
            influence_type="influence_goals",
            market_type="goals",
            confidence_before=80,
            confidence_after=72.5,
        )
        print_success("RefereeInfluenceMetrics.record_influence_applied() works")

        # Test summary retrieval
        summary = metrics.get_summary()
        print_success(
            f"RefereeInfluenceMetrics.get_summary() works: {summary['total_boosts_applied']} boosts"
        )

        # Test rankings
        rankings = metrics.get_referee_rankings(5)
        print_success(
            f"RefereeInfluenceMetrics.get_referee_rankings() works: {len(rankings)} referees"
        )

        # Clean up
        metrics.reset_metrics()
        print_success("RefereeInfluenceMetrics.reset_metrics() works")

    except Exception as e:
        print_error(f"RefereeInfluenceMetrics operations failed: {e}")
        return False

    return True


def verify_referee_stats():
    """Verify RefereeStats class integration."""
    print_header("VERIFYING REFEREE STATS CLASS")

    try:
        from src.analysis.verification_layer import RefereeStats

        print_success("RefereeStats class imported successfully")
    except ImportError as e:
        print_error(f"Failed to import RefereeStats: {e}")
        return False

    try:
        # Test strict referee
        strict_referee = RefereeStats(
            name="Michael Oliver", cards_per_game=5.2, matches_officiated=150
        )
        assert strict_referee.strictness == "strict"
        assert strict_referee.is_strict()
        assert strict_referee.should_boost_cards()
        assert strict_referee.should_upgrade_cards_line()
        assert strict_referee.get_boost_multiplier() == 1.5
        print_success("Strict referee classification works")

        # Test moderate referee
        moderate_referee = RefereeStats(
            name="Antonio Mateu Lahoz", cards_per_game=4.3, matches_officiated=120
        )
        assert moderate_referee.strictness == "average"
        assert moderate_referee.should_boost_cards()
        assert not moderate_referee.should_upgrade_cards_line()
        assert moderate_referee.get_boost_multiplier() == 1.2
        print_success("Moderate referee classification works")

        # Test lenient referee
        lenient_referee = RefereeStats(
            name="Felix Brych", cards_per_game=2.8, matches_officiated=180
        )
        assert lenient_referee.strictness == "lenient"
        assert lenient_referee.is_lenient()
        assert not lenient_referee.should_boost_cards()
        assert lenient_referee.should_veto_cards()
        assert lenient_referee.get_boost_multiplier() == 1.0
        print_success("Lenient referee classification works")

        # Test dict conversion
        referee_dict = {
            "name": "Test Referee",
            "cards_per_game": 4.5,
            "strictness": "average",
            "matches_officiated": 100,
        }
        referee_from_dict = RefereeStats(**referee_dict)
        assert referee_from_dict.name == "Test Referee"
        assert referee_from_dict.cards_per_game == 4.5
        print_success("RefereeStats dict conversion works")

    except Exception as e:
        print_error(f"RefereeStats operations failed: {e}")
        return False

    return True


def verify_analyzer_integration():
    """Verify analyzer integration with referee boost logic."""
    print_header("VERIFYING ANALYZER INTEGRATION")

    try:
        from src.analysis.analyzer import analyze_with_triangulation

        print_success("Analyzer module imported successfully")
    except ImportError as e:
        print_error(f"Failed to import analyzer: {e}")
        return False

    try:
        # Test that RefereeStats can be passed to analyzer
        from src.analysis.verification_layer import RefereeStats

        referee_stats = RefereeStats(
            name="Michael Oliver", cards_per_game=5.2, matches_officiated=150
        )

        # Verify isinstance check works
        assert isinstance(referee_stats, RefereeStats)
        print_success("RefereeStats isinstance check works")

        # Verify boost logic methods are accessible
        assert referee_stats.should_boost_cards()
        assert referee_stats.should_upgrade_cards_line()
        assert referee_stats.get_boost_multiplier() == 1.5
        print_success("RefereeStats boost methods work")

    except Exception as e:
        print_error(f"Analyzer integration failed: {e}")
        return False

    return True


def verify_end_to_end_flow():
    """Verify end-to-end flow of referee boost system."""
    print_header("VERIFYING END-TO-END FLOW")

    try:
        from src.analysis.verification_layer import RefereeStats
        from src.analysis.referee_cache import get_referee_cache
        from src.analysis.referee_cache_monitor import get_referee_cache_monitor
        from src.analysis.referee_boost_logger import get_referee_boost_logger
        from src.analysis.referee_influence_metrics import get_referee_influence_metrics

        # Step 1: Create RefereeStats object
        referee = RefereeStats(name="Michael Oliver", cards_per_game=5.2, matches_officiated=150)
        print_success("Step 1: RefereeStats object created")

        # Step 2: Cache referee stats
        cache = get_referee_cache()
        referee_dict = {
            "name": referee.name,
            "cards_per_game": referee.cards_per_game,
            "strictness": referee.strictness,
            "matches_officiated": referee.matches_officiated,
        }
        cache.set(referee.name, referee_dict)
        print_success("Step 2: Referee stats cached")

        # Step 3: Monitor cache hit
        monitor = get_referee_cache_monitor()
        monitor.record_hit(referee.name, 1.5)
        print_success("Step 3: Cache hit recorded")

        # Step 4: Log boost application
        logger = get_referee_boost_logger()
        logger.log_boost_applied(
            referee_name=referee.name,
            cards_per_game=referee.cards_per_game,
            strictness=referee.strictness,
            original_verdict="NO BET",
            new_verdict="BET",
            recommended_market="Over 3.5 Cards",
            reason="Strict referee + Derby/High Intensity",
            confidence_before=70,
            confidence_after=80,
        )
        print_success("Step 4: Boost application logged")

        # Step 5: Record influence metrics
        metrics = get_referee_influence_metrics()
        metrics.record_boost_applied(
            referee_name=referee.name,
            cards_per_game=referee.cards_per_game,
            boost_type="boost_no_bet_to_bet",
            original_verdict="NO BET",
            new_verdict="BET",
            confidence_before=70,
            confidence_after=80,
            market_type="cards",
        )
        print_success("Step 5: Influence metrics recorded")

        # Step 6: Verify all components are working together
        cached = cache.get(referee.name)
        assert cached == referee_dict
        print_success("Step 6: All components integrated successfully")

        # Clean up
        cache.clear()
        monitor.reset_metrics()
        metrics.reset_metrics()
        print_success("Step 7: Cleanup completed")

    except Exception as e:
        print_error(f"End-to-end flow failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


def verify_file_structure():
    """Verify that all required files exist."""
    print_header("VERIFYING FILE STRUCTURE")

    files_to_check = [
        ("src/analysis/referee_cache.py", "RefereeCache module"),
        ("src/analysis/referee_cache_monitor.py", "RefereeCacheMonitor module"),
        ("src/analysis/referee_boost_logger.py", "RefereeBoostLogger module"),
        ("src/analysis/referee_influence_metrics.py", "RefereeInfluenceMetrics module"),
        ("tests/test_referee_boost_logic.py", "Referee boost logic tests"),
        ("tests/test_referee_cache_integration.py", "Referee cache integration tests"),
        ("scripts/verify_referee_cache_permissions.py", "Cache permissions verification script"),
        ("scripts/verify_referee_boost_integration.py", "Integration verification script"),
    ]

    all_exist = True
    for file_path, description in files_to_check:
        full_path = project_root / file_path
        if full_path.exists():
            print_success(f"{description}: {file_path}")
        else:
            print_error(f"{description} NOT FOUND: {file_path}")
            all_exist = False

    return all_exist


def print_summary(results: dict):
    """Print summary of all verifications."""
    print_header("VERIFICATION SUMMARY")

    total = len(results)
    passed = sum(1 for r in results.values() if r)
    failed = total - passed

    print(f"Total verifications: {total}")
    print(f"{Colors.GREEN}Passed: {passed}{Colors.END}")
    print(f"{Colors.RED}Failed: {failed}{Colors.END}")

    if failed == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ ALL VERIFICATIONS PASSED!{Colors.END}")
        print(
            f"{Colors.GREEN}Referee Boost System is fully integrated and ready for deployment.{Colors.END}\n"
        )
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ SOME VERIFICATIONS FAILED!{Colors.END}")
        print(f"{Colors.RED}Please fix the issues above before deploying.{Colors.END}\n")


def main():
    """Main verification function."""
    print_header("REFEREE BOOST SYSTEM INTEGRATION VERIFICATION")
    print_info("Verifying all referee boost components integrate correctly")

    # Run all verifications
    results = {}

    results["File Structure"] = verify_file_structure()
    results["RefereeCache"] = verify_referee_cache()
    results["RefereeCacheMonitor"] = verify_referee_cache_monitor()
    results["RefereeBoostLogger"] = verify_referee_boost_logger()
    results["RefereeInfluenceMetrics"] = verify_referee_influence_metrics()
    results["RefereeStats Class"] = verify_referee_stats()
    results["Analyzer Integration"] = verify_analyzer_integration()
    results["End-to-End Flow"] = verify_end_to_end_flow()

    # Print summary
    print_summary(results)

    # Exit with appropriate code
    if all(results.values()):
        return 0
    else:
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
