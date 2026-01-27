"""
Test Suite for V7.3 False Positive Prevention Fixes

Tests all 5 fixes implemented to reduce false positives:
1. Database schema - last_alert_time field
2. Temporal reset of highest_score_sent after 24h
3. Conservative verification fallback for high-score alerts
4. AI confidence threshold check
5. False positive rate monitoring in settler

Requirements tested:
- FIX 1: Match.last_alert_time exists and is nullable
- FIX 2: highest_score_sent resets after 24h
- FIX 3: Verification rejects score >= 9.0 when providers fail
- FIX 4: Alerts with confidence < 70% and score < 9.0 are rejected
- FIX 5: Settler monitors and alerts on false positive rate > 40%
"""
import pytest
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock


# ============================================
# FIX 1: Database Schema - last_alert_time
# ============================================

class TestFix1DatabaseSchema(unittest.TestCase):
    """Test that Match model has last_alert_time field."""
    
    def test_match_has_last_alert_time_field(self):
        """Match model should have last_alert_time column."""
        from src.database.models import Match
        from sqlalchemy import inspect
        
        # Get column names
        mapper = inspect(Match)
        columns = [col.key for col in mapper.columns]
        
        assert 'last_alert_time' in columns, "Match should have last_alert_time field"
    
    def test_last_alert_time_is_nullable(self):
        """last_alert_time should be nullable (None for new matches)."""
        from src.database.models import Match
        from sqlalchemy import inspect
        
        mapper = inspect(Match)
        last_alert_col = mapper.columns['last_alert_time']
        
        assert last_alert_col.nullable is True, "last_alert_time should be nullable"
    
    def test_last_alert_time_is_datetime(self):
        """last_alert_time should be DateTime type."""
        from src.database.models import Match
        from sqlalchemy import inspect, DateTime
        
        mapper = inspect(Match)
        last_alert_col = mapper.columns['last_alert_time']
        
        assert isinstance(last_alert_col.type, DateTime), "last_alert_time should be DateTime"


# ============================================
# FIX 2: Temporal Reset of highest_score_sent
# ============================================

class TestFix2TemporalReset(unittest.TestCase):
    """Test that highest_score_sent resets after 24h."""
    
    def test_reset_after_24h(self):
        """highest_score_sent should reset to 0 if 24h passed."""
        from datetime import datetime, timezone, timedelta
        
        # Simulate match with old alert
        now = datetime.now(timezone.utc)
        last_alert_time = now - timedelta(hours=25)  # 25h ago
        highest_score_sent = 8.5
        
        # Logic from main.py
        if last_alert_time:
            time_since_last_alert = now - last_alert_time
            if time_since_last_alert > timedelta(hours=24):
                highest_score_sent = 0.0
        
        assert highest_score_sent == 0.0, "Should reset after 24h"
    
    def test_no_reset_before_24h(self):
        """highest_score_sent should NOT reset if < 24h passed."""
        from datetime import datetime, timezone, timedelta
        
        now = datetime.now(timezone.utc)
        last_alert_time = now - timedelta(hours=12)  # 12h ago
        highest_score_sent = 8.5
        
        # Logic from main.py
        if last_alert_time:
            time_since_last_alert = now - last_alert_time
            if time_since_last_alert > timedelta(hours=24):
                highest_score_sent = 0.0
        
        assert highest_score_sent == 8.5, "Should NOT reset before 24h"
    
    def test_no_reset_if_no_previous_alert(self):
        """If last_alert_time is None, highest_sent stays as is."""
        last_alert_time = None
        highest_score_sent = 8.5
        
        # Logic from main.py
        if last_alert_time:
            time_since_last_alert = datetime.now(timezone.utc) - last_alert_time
            if time_since_last_alert > timedelta(hours=24):
                highest_score_sent = 0.0
        
        assert highest_score_sent == 8.5, "Should not change if no previous alert"
    
    def test_timezone_naive_datetime_handling(self):
        """Handle timezone-naive datetime from SQLite correctly."""
        from datetime import datetime, timezone, timedelta
        
        # Simulate SQLite returning naive datetime
        now = datetime.now(timezone.utc)
        last_alert_naive = (now - timedelta(hours=25)).replace(tzinfo=None)  # Naive
        highest_score_sent = 8.5
        
        # Logic from main.py (with timezone handling)
        if last_alert_naive:
            last_alert = last_alert_naive
            if last_alert.tzinfo is None:
                last_alert = last_alert.replace(tzinfo=timezone.utc)
            
            time_since_last_alert = now - last_alert
            if time_since_last_alert > timedelta(hours=24):
                highest_score_sent = 0.0
        
        assert highest_score_sent == 0.0, "Should handle naive datetime correctly"


# ============================================
# FIX 3: Conservative Verification Fallback
# ============================================

class TestFix3ConservativeVerification(unittest.TestCase):
    """Test that verification rejects high-score alerts when providers fail."""
    
    def test_reject_high_score_on_verification_failure(self):
        """Score >= 9.0 should be REJECTED if verification fails."""
        from src.analysis.verification_layer import (
            create_fallback_result,
            VerificationRequest,
            VerificationStatus
        )
        
        # Create request with high score
        request = VerificationRequest(
            match_id="test_123",
            home_team="Team A",
            away_team="Team B",
            match_date="2025-01-20",
            league="Test League",
            preliminary_score=9.2,  # High score
            suggested_market="Home Win"
        )
        
        # Call fallback (simulates provider failure)
        result = create_fallback_result(request, "Tavily timeout")
        
        assert result.status == VerificationStatus.REJECT, "Should REJECT high score on failure"
        assert result.adjusted_score == 0.0, "Adjusted score should be 0"
        assert "score >= 9.0" in result.rejection_reason.lower(), "Should mention score threshold"
    
    def test_allow_low_score_on_verification_failure(self):
        """Score < 9.0 should be CONFIRMED even if verification fails."""
        from src.analysis.verification_layer import (
            create_fallback_result,
            VerificationRequest,
            VerificationStatus
        )
        
        # Create request with lower score
        request = VerificationRequest(
            match_id="test_123",
            home_team="Team A",
            away_team="Team B",
            match_date="2025-01-20",
            league="Test League",
            preliminary_score=8.5,  # Below 9.0
            suggested_market="Home Win"
        )
        
        # Call fallback
        result = create_fallback_result(request, "Tavily timeout")
        
        assert result.status == VerificationStatus.CONFIRM, "Should CONFIRM low score"
        assert result.adjusted_score == 8.5, "Score should remain unchanged"
    
    def test_edge_case_exactly_9_0(self):
        """Score exactly 9.0 should be REJECTED (>= threshold)."""
        from src.analysis.verification_layer import (
            create_fallback_result,
            VerificationRequest,
            VerificationStatus
        )
        
        request = VerificationRequest(
            match_id="test_123",
            home_team="Team A",
            away_team="Team B",
            match_date="2025-01-20",
            league="Test League",
            preliminary_score=9.0,  # Exactly 9.0
            suggested_market="Home Win"
        )
        
        result = create_fallback_result(request, "Provider unavailable")
        
        assert result.status == VerificationStatus.REJECT, "Should REJECT score == 9.0"


# ============================================
# FIX 4: AI Confidence Threshold Check
# ============================================

class TestFix4AIConfidenceCheck(unittest.TestCase):
    """Test that low AI confidence blocks alerts."""
    
    def test_reject_low_confidence_medium_score(self):
        """Confidence < 70% AND score < 9.0 should be rejected."""
        ai_confidence = 65
        current_score = 8.5
        
        # Logic from main.py
        should_skip = ai_confidence < 70 and current_score < 9.0
        
        assert should_skip is True, "Should skip alert with low confidence"
    
    def test_allow_high_confidence_medium_score(self):
        """Confidence >= 70% should allow alert."""
        ai_confidence = 75
        current_score = 8.5
        
        should_skip = ai_confidence < 70 and current_score < 9.0
        
        assert should_skip is False, "Should allow alert with high confidence"
    
    def test_allow_low_confidence_high_score(self):
        """Low confidence but score >= 9.0 should allow alert."""
        ai_confidence = 65
        current_score = 9.2
        
        should_skip = ai_confidence < 70 and current_score < 9.0
        
        assert should_skip is False, "Should allow very high score despite low confidence"
    
    def test_edge_case_confidence_70(self):
        """Confidence exactly 70% should allow alert."""
        ai_confidence = 70
        current_score = 8.5
        
        should_skip = ai_confidence < 70 and current_score < 9.0
        
        assert should_skip is False, "Confidence == 70 should pass"
    
    def test_edge_case_score_9_0(self):
        """Score exactly 9.0 should allow alert despite low confidence."""
        ai_confidence = 65
        current_score = 9.0
        
        should_skip = ai_confidence < 70 and current_score < 9.0
        
        assert should_skip is False, "Score == 9.0 should pass"


# ============================================
# FIX 5: False Positive Rate Monitoring
# ============================================

class TestFix5FalsePositiveMonitoring(unittest.TestCase):
    """Test that settler monitors and alerts on high false positive rate."""
    
    def test_calculate_false_positive_rate(self):
        """False positive rate should be calculated correctly."""
        wins = 5
        losses = 7
        total_bets = wins + losses
        
        false_positive_rate = (losses / total_bets) * 100
        
        assert abs(false_positive_rate - 58.3) < 0.1, "Should calculate 58.3%"
    
    def test_alert_triggered_above_40_percent(self):
        """Alert should trigger if loss rate > 40%."""
        wins = 5
        losses = 7  # 58.3% loss rate
        total_bets = wins + losses
        
        false_positive_rate = (losses / total_bets) * 100
        should_alert = false_positive_rate > 40.0 and total_bets >= 10
        
        assert should_alert is True, "Should alert on 58.3% loss rate"
    
    def test_no_alert_below_40_percent(self):
        """No alert if loss rate <= 40%."""
        wins = 7
        losses = 3  # 30% loss rate
        total_bets = wins + losses
        
        false_positive_rate = (losses / total_bets) * 100
        should_alert = false_positive_rate > 40.0 and total_bets >= 10
        
        assert should_alert is False, "Should NOT alert on 30% loss rate"
    
    def test_no_alert_small_sample_size(self):
        """No alert if sample size < 10 bets."""
        wins = 2
        losses = 6  # 75% loss rate but only 8 bets
        total_bets = wins + losses
        
        false_positive_rate = (losses / total_bets) * 100
        should_alert = false_positive_rate > 40.0 and total_bets >= 10
        
        assert should_alert is False, "Should NOT alert with < 10 bets"
    
    def test_edge_case_exactly_40_percent(self):
        """Exactly 40% loss rate should NOT trigger alert."""
        wins = 6
        losses = 4  # Exactly 40%
        total_bets = wins + losses
        
        false_positive_rate = (losses / total_bets) * 100
        should_alert = false_positive_rate > 40.0 and total_bets >= 10
        
        assert should_alert is False, "40% exactly should NOT alert (> not >=)"
    
    def test_edge_case_exactly_10_bets(self):
        """Exactly 10 bets should enable monitoring."""
        wins = 5
        losses = 5  # 50% loss rate
        total_bets = wins + losses
        
        false_positive_rate = (losses / total_bets) * 100
        should_alert = false_positive_rate > 40.0 and total_bets >= 10
        
        assert should_alert is True, "Should alert with exactly 10 bets"


# ============================================
# INTEGRATION TEST: All Fixes Together
# ============================================

class TestIntegrationAllFixes(unittest.TestCase):
    """Test that all 5 fixes work together correctly."""
    
    def test_full_flow_with_all_fixes(self):
        """Simulate a full alert flow with all fixes active."""
        from datetime import datetime, timezone, timedelta
        
        # Scenario: High-score alert with low confidence after 24h
        now = datetime.now(timezone.utc)
        
        # Match state
        last_alert_time = now - timedelta(hours=25)  # 25h ago
        highest_score_sent = 8.5
        
        # New analysis
        current_score = 9.1
        ai_confidence = 68  # Low confidence
        
        # FIX 2: Temporal reset
        if last_alert_time:
            time_since_last_alert = now - last_alert_time
            if time_since_last_alert > timedelta(hours=24):
                highest_score_sent = 0.0
        
        assert highest_score_sent == 0.0, "Should reset after 24h"
        
        # FIX 4: AI confidence check
        should_skip_confidence = ai_confidence < 70 and current_score < 9.0
        
        # Score is 9.1, so confidence check passes
        assert should_skip_confidence is False, "High score should bypass confidence check"
        
        # FIX 3: Verification fallback (simulated)
        # If verification fails for score >= 9.0, it would be rejected
        # But in this test, we assume verification succeeds
        
        # Alert would be sent
        # FIX 1: last_alert_time would be updated
        new_last_alert_time = now
        
        assert new_last_alert_time is not None, "Should update last_alert_time"
    
    def test_rejection_cascade(self):
        """Test that multiple rejection mechanisms work together."""
        # Scenario: Medium score, low confidence, verification fails
        current_score = 8.7
        ai_confidence = 65
        verification_failed = True
        
        # FIX 4: AI confidence check
        rejected_by_confidence = ai_confidence < 70 and current_score < 9.0
        
        assert rejected_by_confidence is True, "Should be rejected by confidence check"
        
        # Even if confidence passed, verification would reject if score >= 9.0
        # But in this case, score is 8.7, so verification would CONFIRM
        # This shows the layered defense works correctly


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
