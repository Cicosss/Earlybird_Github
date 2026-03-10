"""
Contract Integration Tests V14.0

Tests the integration of contract validation between components.
This ensures that data flows correctly through the pipeline with proper validation.
"""

from src.utils.contracts import (
    ALERT_PAYLOAD_CONTRACT,
    ANALYSIS_RESULT_CONTRACT,
    NEWS_ITEM_CONTRACT,
    SNIPPET_DATA_CONTRACT,
    VERIFICATION_RESULT_CONTRACT,
)


class TestNewsItemContractIntegration:
    """Test NEWS_ITEM_CONTRACT with real-world data from news_hunter."""

    def test_browser_monitor_news_item(self):
        """Test news item from browser_monitor with all new fields."""
        news_item = {
            "match_id": "test_match_123",
            "team": "Test Team",
            "title": "Test Title",
            "snippet": "Test Snippet",
            "link": "https://example.com/test",
            "source": "test_source.com",
            "search_type": "browser_monitor",
            # V14.0: New fields
            "keyword": "browser_monitor",
            "category": "INJURY",
            "source_type": "browser_monitor",
            "league_key": "soccer_test_league",
            "gemini_confidence": 0.85,
            "discovered_at": "2026-03-09T21:00:00Z",
            "topics": ["injury", "lineup"],
        }

        # Should not raise
        NEWS_ITEM_CONTRACT.assert_valid(news_item, context="test_browser_monitor")

    def test_beat_writer_news_item(self):
        """Test news item from beat_writer with all new fields."""
        news_item = {
            "match_id": "test_match_123",
            "team": "Test Team",
            "title": "Test Title",
            "snippet": "Test Snippet",
            "link": "https://example.com/test",
            "source": "Test Source",
            "search_type": "beat_writer_cache",
            "confidence": "HIGH",
            "priority_boost": 1.5,
            "source_type": "beat_writer",
            "topics": ["injury"],
            # V14.0: Beat writer metadata
            "beat_writer_name": "John Doe",
            "beat_writer_outlet": "Test Outlet",
            "beat_writer_specialty": "Injury Reporter",
            "beat_writer_reliability": 0.9,
        }

        # Should not raise
        NEWS_ITEM_CONTRACT.assert_valid(news_item, context="test_beat_writer")


class TestAnalysisResultContractIntegration:
    """Test ANALYSIS_RESULT_CONTRACT with real-world data from analyzer."""

    def test_full_analysis_result(self):
        """Test analysis result with all new fields."""
        analysis_result = {
            # Original fields
            "score": 8.5,
            "summary": "Test Summary",
            "category": "INJURY",
            "recommended_market": "Test Market",
            "combo_suggestion": "Test Combo",
            "combo_reasoning": "Test Reasoning",
            "primary_driver": "INJURY_INTEL",
            # V14.0: New fields
            "match_id": "test_match_123",
            "url": "https://example.com/test",
            "affected_team": "Test Team",
            "confidence": 85,
            "odds_taken": 2.50,
            "confidence_breakdown": '{"news_weight": 0.4, "odds_weight": 0.3, "form_weight": 0.2, "injuries_weight": 0.1}',
            "is_convergent": True,
            "convergence_sources": '{"web": {"count": 5}, "social": {"count": 3}}',
        }

        # Should not raise
        ANALYSIS_RESULT_CONTRACT.assert_valid(analysis_result, context="test_full_analysis")

    def test_minimal_analysis_result(self):
        """Test analysis result with only required fields."""
        analysis_result = {
            "score": 7.0,
            "summary": "Test Summary",
            "category": "INJURY",
            "recommended_market": "Test Market",
            "combo_suggestion": "Test Combo",
            "combo_reasoning": "Test Reasoning",
            "primary_driver": "INJURY_INTEL",
        }

        # Should not raise
        ANALYSIS_RESULT_CONTRACT.assert_valid(analysis_result, context="test_minimal_analysis")


class TestVerificationResultContractIntegration:
    """Test VERIFICATION_RESULT_CONTRACT with real-world data from verification_layer."""

    def test_full_verification_result(self):
        """Test verification result with all new fields."""
        verification_result = {
            # Original fields
            "status": "confirm",
            "original_score": 8.5,
            "adjusted_score": 8.0,
            "original_market": "Test Market",
            "recommended_market": "Test Market",
            "overall_confidence": "HIGH",
            "reasoning": "Test Reasoning",
            "rejection_reason": None,
            "inconsistencies": [],
            # V14.0: New fields
            "score_adjustment_reason": "Minor adjustment based on form",
            "alternative_markets": ["Alternative Market 1", "Alternative Market 2"],
            "verified_data": {
                "source": "tavily",
                "data_confidence": "HIGH",
                "form_confidence": "HIGH",
                "h2h_confidence": "MEDIUM",
                "referee_confidence": "HIGH",
                "corner_confidence": "MEDIUM",
            },
        }

        # Should not raise
        VERIFICATION_RESULT_CONTRACT.assert_valid(
            verification_result, context="test_full_verification"
        )

    def test_minimal_verification_result(self):
        """Test verification result with only required fields."""
        verification_result = {
            "status": "confirm",
            "original_score": 8.5,
            "adjusted_score": 8.0,
            "overall_confidence": "HIGH",
            "reasoning": "Test Reasoning",
            "rejection_reason": None,
            "inconsistencies": [],
        }

        # Should not raise
        VERIFICATION_RESULT_CONTRACT.assert_valid(
            verification_result, context="test_minimal_verification"
        )


class TestAlertPayloadContractIntegration:
    """Test ALERT_PAYLOAD_CONTRACT with real-world data from notifier."""

    def test_full_alert_payload(self):
        """Test alert payload with all new fields."""

        # Create a mock match object
        class MockMatch:
            id = "test_match_123"
            home_team = "Home Team"
            away_team = "Away Team"

        alert_payload = {
            # Original fields
            "match_obj": MockMatch(),
            "news_summary": "Test Summary",
            "news_url": "https://example.com/test",
            "score": 8.5,
            "league": "Test League",
            "combo_suggestion": "Test Combo",
            "recommended_market": "Test Market",
            "verification_info": {"status": "confirm", "confidence": "HIGH"},
            "is_convergent": True,
            "convergence_sources": {"web": {"count": 5}, "social": {"count": 3}},
            # V14.0: New fields
            "math_edge": {"market": "Test Market", "edge": 7.5, "kelly_stake": 0.05},
            "is_update": False,
            "financial_risk": "LOW",
            "intel_source": "web",
            "referee_intel": {"referee_name": "Test Referee", "referee_cards_avg": 3.5},
            "twitter_intel": {"tweets": [{"content": "Test tweet"}]},
            "validated_home_team": "Home Team",
            "validated_away_team": "Away Team",
            "final_verification_info": {"status": "CONFIRMED", "confidence": "HIGH"},
            "injury_intel": {"home_severity": "HIGH", "away_severity": "LOW"},
            "confidence_breakdown": {
                "news_weight": 0.4,
                "odds_weight": 0.3,
                "form_weight": 0.2,
                "injuries_weight": 0.1,
            },
            "market_warning": None,
        }

        # Should not raise
        ALERT_PAYLOAD_CONTRACT.assert_valid(alert_payload, context="test_full_alert")

    def test_minimal_alert_payload(self):
        """Test alert payload with only required fields."""

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
        }

        # Should not raise
        ALERT_PAYLOAD_CONTRACT.assert_valid(alert_payload, context="test_minimal_alert")


class TestCrossComponentIntegration:
    """Test data flow between components with contract validation."""

    def test_news_to_snippet_flow(self):
        """Test that news item data can be transformed to snippet data."""
        news_item = {
            "match_id": "test_match_123",
            "team": "Test Team",
            "title": "Test Title",
            "snippet": "Test Snippet",
            "link": "https://example.com/test",
            "source": "test_source.com",
            "search_type": "browser_monitor",
        }

        # Validate news item
        NEWS_ITEM_CONTRACT.assert_valid(news_item, context="test_news_to_snippet")

        # Transform to snippet data (what main.py would do)
        snippet_data = {
            "match_id": news_item["match_id"],
            "link": news_item["link"],
            "team": news_item["team"],
            "home_team": "Home Team",  # Would be set by main.py
            "away_team": "Away Team",  # Would be set by main.py
            "snippet": news_item["snippet"],
            "league_id": None,
            "current_home_odd": None,
            "current_away_odd": None,
            "current_draw_odd": None,
            "home_context": None,
            "away_context": None,
        }

        # Validate snippet data
        SNIPPET_DATA_CONTRACT.assert_valid(snippet_data, context="test_news_to_snippet")

    def test_analysis_to_verification_flow(self):
        """Test that analysis result can be passed to verification."""
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

        # Validate analysis result
        ANALYSIS_RESULT_CONTRACT.assert_valid(
            analysis_result, context="test_analysis_to_verification"
        )

        # Create verification result (what verification_layer would return)
        verification_result = {
            "status": "confirm",
            "original_score": analysis_result["score"],
            "adjusted_score": analysis_result["score"],
            "original_market": analysis_result["recommended_market"],
            "recommended_market": analysis_result["recommended_market"],
            "overall_confidence": "HIGH",
            "reasoning": "Test Reasoning",
            "rejection_reason": None,
            "inconsistencies": [],
            "score_adjustment_reason": None,
            "alternative_markets": [],
            "verified_data": {
                "source": "tavily",
                "data_confidence": "HIGH",
            },
        }

        # Validate verification result
        VERIFICATION_RESULT_CONTRACT.assert_valid(
            verification_result, context="test_analysis_to_verification"
        )

    def test_verification_to_alert_flow(self):
        """Test that verification result can be passed to alert."""

        class MockMatch:
            id = "test_match_123"
            home_team = "Home Team"
            away_team = "Away Team"

        verification_result = {
            "status": "confirm",
            "original_score": 8.5,
            "adjusted_score": 8.0,
            "overall_confidence": "HIGH",
            "reasoning": "Test Reasoning",
            "rejection_reason": None,
            "inconsistencies": [],
        }

        # Validate verification result
        VERIFICATION_RESULT_CONTRACT.assert_valid(
            verification_result, context="test_verification_to_alert"
        )

        # Create alert payload (what notifier would receive)
        alert_payload = {
            "match_obj": MockMatch(),
            "news_summary": "Test Summary",
            "news_url": "https://example.com/test",
            "score": verification_result["adjusted_score"],
            "league": "Test League",
            "verification_info": {
                "status": verification_result["status"],
                "confidence": verification_result["overall_confidence"],
            },
            "is_convergent": False,
            "convergence_sources": None,
            "math_edge": None,
            "is_update": False,
            "financial_risk": None,
            "intel_source": "web",
            "referee_intel": None,
            "twitter_intel": None,
            "validated_home_team": None,
            "validated_away_team": None,
            "final_verification_info": None,
            "injury_intel": None,
            "confidence_breakdown": None,
            "market_warning": None,
        }

        # Validate alert payload
        ALERT_PAYLOAD_CONTRACT.assert_valid(alert_payload, context="test_verification_to_alert")
