"""
Contract Performance Tests V14.0

Tests the actual performance overhead of contract validation.
This measures the real overhead to correct the claim of 46ms.
"""

import time

from src.utils.contracts import (
    ALERT_PAYLOAD_CONTRACT,
    ANALYSIS_RESULT_CONTRACT,
    NEWS_ITEM_CONTRACT,
    VERIFICATION_RESULT_CONTRACT,
)


class TestContractPerformance:
    """Test contract validation performance."""

    def test_news_item_contract_performance(self):
        """Measure NEWS_ITEM_CONTRACT validation performance."""
        news_item = {
            "match_id": "test_match_123",
            "team": "Test Team",
            "title": "Test Title",
            "snippet": "Test Snippet",
            "link": "https://example.com/test",
            "source": "test_source.com",
            "search_type": "browser_monitor",
            "keyword": "browser_monitor",
            "category": "INJURY",
            "source_type": "browser_monitor",
            "league_key": "soccer_test_league",
            "gemini_confidence": 0.85,
            "discovered_at": "2026-03-09T21:00:00Z",
            "topics": ["injury", "lineup"],
        }

        # Measure performance
        start_time = time.perf_counter()
        NEWS_ITEM_CONTRACT.assert_valid(news_item, context="performance_test")
        elapsed = time.perf_counter() - start_time
        elapsed_microseconds = elapsed / 1000  # Convert to microseconds

        print(
            f"NEWS_ITEM_CONTRACT validation took {elapsed_microseconds:.2f} microseconds ({elapsed_microseconds / 1000:.3f} milliseconds)"
        )

        # Should be much less than 46ms (46000 microseconds)
        assert elapsed_microseconds < 46000, (
            f"Validation took {elapsed_microseconds}μs, expected < 46000μs"
        )

    def test_analysis_result_contract_performance(self):
        """Measure ANALYSIS_RESULT_CONTRACT validation performance."""
        analysis_result = {
            "score": 8.5,
            "summary": "Test Summary",
            "category": "INJURY",
            "recommended_market": "Test Market",
            "combo_suggestion": "Test Combo",
            "combo_reasoning": "Test Reasoning",
            "primary_driver": "INJURY_INTEL",
            "match_id": "test_match_123",
            "url": "https://example.com/test",
            "affected_team": "Test Team",
            "confidence": 85,
            "odds_taken": 2.50,
            "confidence_breakdown": '{"news_weight": 0.4}',
            "is_convergent": True,
            "convergence_sources": '{"web": {"count": 5}}',
        }

        # Measure performance
        start_time = time.perf_counter()
        ANALYSIS_RESULT_CONTRACT.assert_valid(analysis_result, context="performance_test")
        elapsed = time.perf_counter() - start_time
        elapsed_microseconds = elapsed / 1000  # Convert to microseconds

        print(
            f"ANALYSIS_RESULT_CONTRACT validation took {elapsed_microseconds:.2f} microseconds ({elapsed_microseconds / 1000:.3f} milliseconds)"
        )

        # Should be much less than 46ms (46000 microseconds)
        assert elapsed_microseconds < 46000, (
            f"Validation took {elapsed_microseconds}μs, expected < 46000μs"
        )

    def test_verification_result_contract_performance(self):
        """Measure VERIFICATION_RESULT_CONTRACT validation performance."""
        verification_result = {
            "status": "confirm",
            "original_score": 8.5,
            "adjusted_score": 8.0,
            "original_market": "Test Market",
            "recommended_market": "Test Market",
            "overall_confidence": "HIGH",
            "reasoning": "Test Reasoning",
            "rejection_reason": None,
            "inconsistencies": [],
            "score_adjustment_reason": "Minor adjustment",
            "alternative_markets": ["Alternative Market 1"],
            "verified_data": {
                "source": "tavily",
                "data_confidence": "HIGH",
                "form_confidence": "HIGH",
            },
        }

        # Measure performance
        start_time = time.perf_counter()
        VERIFICATION_RESULT_CONTRACT.assert_valid(verification_result, context="performance_test")
        elapsed = time.perf_counter() - start_time
        elapsed_microseconds = elapsed / 1000  # Convert to microseconds

        print(
            f"VERIFICATION_RESULT_CONTRACT validation took {elapsed_microseconds:.2f} microseconds ({elapsed_microseconds / 1000:.3f} milliseconds)"
        )

        # Should be much less than 46ms (46000 microseconds)
        assert elapsed_microseconds < 46000, (
            f"Validation took {elapsed_microseconds}μs, expected < 46000μs"
        )

    def test_alert_payload_contract_performance(self):
        """Measure ALERT_PAYLOAD_CONTRACT validation performance."""

        class MockMatch:
            id = "test_match_123"
            home_team = "Home Team"
            away_team = "Away Team"

        alert_payload = {
            "match_obj": MockMatch(),
            "news_summary": "Test Summary",
            "news_url": "https://example.com/test",
            "score": 8.5,
            "league": "Test League",
            "combo_suggestion": "Test Combo",
            "recommended_market": "Test Market",
            "verification_info": {"status": "confirm"},
            "is_convergent": True,
            "convergence_sources": {"web": {"count": 5}},
            "math_edge": {"market": "Test Market", "edge": 7.5},
            "is_update": False,
            "financial_risk": "LOW",
            "intel_source": "web",
            "referee_intel": {"referee_name": "Test Referee"},
            "twitter_intel": {"tweets": [{"content": "Test tweet"}]},
            "validated_home_team": "Home Team",
            "validated_away_team": "Away Team",
            "final_verification_info": {"status": "CONFIRMED"},
            "injury_intel": {"home_severity": "HIGH"},
            "confidence_breakdown": {"news_weight": 0.4},
            "market_warning": None,
        }

        # Measure performance
        start_time = time.perf_counter()
        ALERT_PAYLOAD_CONTRACT.assert_valid(alert_payload, context="performance_test")
        elapsed = time.perf_counter() - start_time
        elapsed_microseconds = elapsed / 1000  # Convert to microseconds

        print(
            f"ALERT_PAYLOAD_CONTRACT validation took {elapsed_microseconds:.2f} microseconds ({elapsed_microseconds / 1000:.3f} milliseconds)"
        )

        # Should be much less than 46ms (46000 microseconds)
        assert elapsed_microseconds < 46000, (
            f"Validation took {elapsed_microseconds}μs, expected < 46000μs"
        )
