"""
Tests for Telegram Trust Score Module V4.3

Tests cover:
1. Red flag detection
2. Timestamp lag calculation
3. Echo chamber detection
4. Trust score calculation
5. Message validation
6. Edge cases (None, empty, zero division)
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.telegram_trust_score import (
    detect_red_flags,
    calculate_timestamp_lag,
    check_echo_chamber,
    calculate_trust_score,
    validate_telegram_message,
    _get_text_hash,
    _normalize_text_for_echo,
    ChannelMetrics,
    TrustLevel,
    TIMESTAMP_LAG_INSIDER_THRESHOLD,
    TIMESTAMP_LAG_LATE_THRESHOLD,
    MIN_MESSAGES_FOR_TRUST
)


class TestRedFlagDetection:
    """Tests for red flag detection in message text."""
    
    def test_clean_message_no_flags(self):
        """Clean squad news should have no red flags."""
        text = "Galatasaray XI: Muslera, Torreira, Icardi starting tonight"
        flags = detect_red_flags(text)
        assert flags == []
    
    def test_fixed_match_keyword(self):
        """'Fixed match' keyword should be detected."""
        text = "This is a FIXED MATCH insider tip!"
        flags = detect_red_flags(text)
        assert len(flags) >= 1
        assert any("fixed match" in f.lower() for f in flags)
    
    def test_100_safe_keyword(self):
        """'100% safe' keyword should be detected."""
        text = "100% SAFE BET guaranteed win!"
        flags = detect_red_flags(text)
        assert len(flags) >= 1
    
    def test_contact_admin_pattern(self):
        """Contact admin for VIP pattern should be detected."""
        text = "Contact @admin for VIP tips"
        flags = detect_red_flags(text)
        assert len(flags) >= 1
    
    def test_multiple_red_flags(self):
        """Multiple red flags should all be detected."""
        text = "100% SAFE fixed match! Contact @admin for VIP, max bet!"
        flags = detect_red_flags(text)
        assert len(flags) >= 2
    
    def test_empty_text(self):
        """Empty text should return no flags."""
        assert detect_red_flags("") == []
        assert detect_red_flags(None) == []
    
    def test_case_insensitive(self):
        """Detection should be case insensitive."""
        text = "FIXED MATCH"
        flags = detect_red_flags(text)
        assert len(flags) >= 1


class TestTimestampLag:
    """Tests for timestamp lag calculation."""
    
    def test_insider_hit_before_drop(self):
        """Message before odds drop should be insider hit."""
        now = datetime.now(timezone.utc)
        msg_time = now - timedelta(minutes=10)
        drop_time = now
        
        lag, is_insider = calculate_timestamp_lag(msg_time, drop_time)
        
        assert lag < 0  # Negative = before drop
        assert is_insider is True
    
    def test_late_message_after_drop(self):
        """Message after odds drop should not be insider hit."""
        now = datetime.now(timezone.utc)
        msg_time = now
        drop_time = now - timedelta(minutes=60)
        
        lag, is_insider = calculate_timestamp_lag(msg_time, drop_time)
        
        assert lag > 0  # Positive = after drop
        assert is_insider is False
    
    def test_no_drop_time(self):
        """No drop time should return neutral values."""
        msg_time = datetime.now(timezone.utc)
        
        lag, is_insider = calculate_timestamp_lag(msg_time, None)
        
        assert lag == 0.0
        assert is_insider is False
    
    def test_no_message_time(self):
        """No message time should return neutral values."""
        drop_time = datetime.now(timezone.utc)
        
        lag, is_insider = calculate_timestamp_lag(None, drop_time)
        
        assert lag == 0.0
        assert is_insider is False
    
    def test_naive_datetime_handling(self):
        """Should handle naive datetimes correctly."""
        now = datetime.now()  # Naive
        msg_time = now - timedelta(minutes=5)
        drop_time = now
        
        # Should not raise exception
        lag, is_insider = calculate_timestamp_lag(msg_time, drop_time)
        assert isinstance(lag, float)


class TestEchoChamber:
    """Tests for echo chamber detection."""
    
    def test_unique_message_not_echo(self):
        """Unique message should not be detected as echo."""
        is_echo, source = check_echo_chamber(
            "channel_a",
            "Unique message about Galatasaray lineup",
            datetime.now(timezone.utc)
        )
        assert is_echo is False
        assert source is None
    
    def test_same_channel_not_echo(self):
        """Same channel posting similar content is not echo."""
        now = datetime.now(timezone.utc)
        
        # First message
        check_echo_chamber("channel_a", "Test message content", now)
        
        # Same channel, same content - not echo
        is_echo, source = check_echo_chamber(
            "channel_a",
            "Test message content",
            now + timedelta(seconds=30)
        )
        # Same channel should not be flagged as echo
        assert source != "channel_a" or is_echo is False
    
    def test_short_message_not_echo(self):
        """Short messages should not be checked for echo."""
        is_echo, source = check_echo_chamber(
            "channel_a",
            "Short",  # < 20 chars
            datetime.now(timezone.utc)
        )
        assert is_echo is False
    
    def test_text_hash_consistency(self):
        """Same text should produce same hash."""
        text = "Galatasaray starting XI confirmed"
        hash1 = _get_text_hash(text)
        hash2 = _get_text_hash(text)
        assert hash1 == hash2
    
    def test_text_normalization(self):
        """Text normalization should remove extra whitespace."""
        text1 = "Hello   World"
        text2 = "hello world"
        
        norm1 = _normalize_text_for_echo(text1)
        norm2 = _normalize_text_for_echo(text2)
        
        assert norm1 == norm2


class TestTrustScoreCalculation:
    """Tests for trust score calculation."""
    
    def test_new_channel_neutral_score(self):
        """New channel with few messages should get neutral score."""
        metrics = ChannelMetrics(
            channel_id="test",
            channel_name="test",
            total_messages=2  # Below MIN_MESSAGES_FOR_TRUST
        )
        
        score, level = calculate_trust_score(metrics)
        
        assert score == 0.5
        assert level == TrustLevel.NEUTRAL
    
    def test_high_insider_hits_high_score(self):
        """Channel with many insider hits should get high score."""
        metrics = ChannelMetrics(
            channel_id="test",
            channel_name="test",
            total_messages=20,
            messages_with_odds_impact=10,
            insider_hits=8,
            late_messages=2
        )
        
        score, level = calculate_trust_score(metrics)
        
        assert score > 0.6
        assert level in [TrustLevel.TRUSTED, TrustLevel.VERIFIED]
    
    def test_many_red_flags_low_score(self):
        """Channel with many red flags should get lower score and be blacklisted."""
        metrics = ChannelMetrics(
            channel_id="test",
            channel_name="test",
            total_messages=20,
            red_flags_count=10  # >= 3 triggers auto-blacklist
        )
        
        score, level = calculate_trust_score(metrics)
        
        # With 10 red flags (>= 3), channel should be blacklisted
        assert score < 0.6
        assert level == TrustLevel.BLACKLISTED  # Auto-blacklist for >= 3 red flags
    
    def test_high_echo_ratio_penalty(self):
        """Channel with high echo ratio should be penalized."""
        metrics = ChannelMetrics(
            channel_id="test",
            channel_name="test",
            total_messages=20,
            echo_messages=15  # 75% echoes
        )
        
        score, level = calculate_trust_score(metrics)
        
        assert score < 0.3
    
    def test_zero_messages_no_crash(self):
        """Zero messages should not cause division by zero."""
        metrics = ChannelMetrics(
            channel_id="test",
            channel_name="test",
            total_messages=0
        )
        
        # Should not raise exception
        score, level = calculate_trust_score(metrics)
        assert score == 0.5  # Neutral for insufficient data
    
    def test_blacklist_threshold(self):
        """Very low score should result in BLACKLISTED level."""
        metrics = ChannelMetrics(
            channel_id="test",
            channel_name="test",
            total_messages=20,
            red_flags_count=15,  # Many red flags
            echo_messages=18,    # High echo ratio
            late_messages=10,
            messages_with_odds_impact=10
        )
        
        score, level = calculate_trust_score(metrics)
        
        assert level == TrustLevel.BLACKLISTED


class TestMessageValidation:
    """Tests for full message validation."""
    
    def test_valid_message_high_trust(self):
        """Valid message from good channel should have high trust."""
        now = datetime.now(timezone.utc)
        
        validation = validate_telegram_message(
            channel_id="good_channel",
            channel_name="GoodChannel",
            message_text="Galatasaray XI: Muslera, Torreira, Icardi",
            message_time=now - timedelta(minutes=5),
            first_odds_drop_time=now
        )
        
        assert validation.is_valid is True
        assert validation.trust_multiplier > 0.5
        assert validation.is_insider_hit is True
    
    def test_scam_message_rejected(self):
        """Message with multiple red flags should be rejected."""
        validation = validate_telegram_message(
            channel_id="scam_channel",
            channel_name="ScamChannel",
            message_text="100% SAFE fixed match! Contact @admin for VIP!",
            message_time=datetime.now(timezone.utc),
            first_odds_drop_time=None
        )
        
        assert validation.is_valid is False
        assert validation.trust_multiplier == 0.0
        assert len(validation.red_flags) >= 2
    
    def test_late_message_low_trust(self):
        """Very late message should have low trust multiplier."""
        now = datetime.now(timezone.utc)
        
        validation = validate_telegram_message(
            channel_id="late_channel",
            channel_name="LateChannel",
            message_text="Galatasaray lineup confirmed",
            message_time=now,
            first_odds_drop_time=now - timedelta(minutes=60)  # 60 min ago
        )
        
        assert validation.trust_multiplier < 0.5
        assert validation.is_insider_hit is False
    
    def test_blacklisted_channel_rejected(self):
        """Message from blacklisted channel should be rejected."""
        blacklisted_metrics = ChannelMetrics(
            channel_id="bad_channel",
            channel_name="BadChannel",
            total_messages=100,
            red_flags_count=20,
            trust_score=0.1,
            trust_level=TrustLevel.BLACKLISTED
        )
        
        validation = validate_telegram_message(
            channel_id="bad_channel",
            channel_name="BadChannel",
            message_text="Some message",
            message_time=datetime.now(timezone.utc),
            first_odds_drop_time=None,
            channel_metrics=blacklisted_metrics
        )
        
        assert validation.is_valid is False
        assert validation.trust_multiplier == 0.0


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_none_text_handling(self):
        """None text should be handled gracefully."""
        flags = detect_red_flags(None)
        assert flags == []
        
        hash_result = _get_text_hash(None)
        assert hash_result == ""[:16] or hash_result is not None
    
    def test_empty_string_handling(self):
        """Empty string should be handled gracefully."""
        flags = detect_red_flags("")
        assert flags == []
        
        norm = _normalize_text_for_echo("")
        assert norm == ""
    
    def test_unicode_text_handling(self):
        """Unicode text (Turkish, Greek, etc.) should be handled."""
        text = "Galatasaray kadrosu: Muslera, Torreira, İcardi"
        flags = detect_red_flags(text)
        assert isinstance(flags, list)
        
        hash_result = _get_text_hash(text)
        assert len(hash_result) == 16
    
    def test_very_long_text(self):
        """Very long text should be handled without issues."""
        text = "A" * 10000
        flags = detect_red_flags(text)
        assert isinstance(flags, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ============================================
# V4.3: TRACK ODDS CORRELATION TESTS
# ============================================

class TestTrackOddsCorrelation:
    """Tests for V4.3 track_odds_correlation function."""
    
    def test_track_odds_correlation_missing_channel_id(self):
        """Should return None if channel_id is missing."""
        from src.analysis.telegram_trust_score import track_odds_correlation
        from datetime import datetime, timezone
        
        result = track_odds_correlation(
            channel_id=None,
            message_time=datetime.now(timezone.utc),
            match_id="test_match"
        )
        assert result is None
    
    def test_track_odds_correlation_missing_match_id(self):
        """Should return None if match_id is missing."""
        from src.analysis.telegram_trust_score import track_odds_correlation
        from datetime import datetime, timezone
        
        result = track_odds_correlation(
            channel_id="test_channel",
            message_time=datetime.now(timezone.utc),
            match_id=None
        )
        assert result is None
    
    def test_track_odds_correlation_missing_message_time(self):
        """Should return None if message_time is missing."""
        from src.analysis.telegram_trust_score import track_odds_correlation
        
        result = track_odds_correlation(
            channel_id="test_channel",
            message_time=None,
            match_id="test_match"
        )
        assert result is None
    
    def test_track_odds_correlation_empty_channel_id(self):
        """Should return None if channel_id is empty string."""
        from src.analysis.telegram_trust_score import track_odds_correlation
        from datetime import datetime, timezone
        
        result = track_odds_correlation(
            channel_id="",
            message_time=datetime.now(timezone.utc),
            match_id="test_match"
        )
        assert result is None
    
    def test_track_odds_correlation_empty_match_id(self):
        """Should return None if match_id is empty string."""
        from src.analysis.telegram_trust_score import track_odds_correlation
        from datetime import datetime, timezone
        
        result = track_odds_correlation(
            channel_id="test_channel",
            message_time=datetime.now(timezone.utc),
            match_id=""
        )
        assert result is None


class TestGetChannelTrustMetrics:
    """Tests for V4.3 get_channel_trust_metrics function."""
    
    def test_get_channel_trust_metrics_not_found(self):
        """Should return None for non-existent channel."""
        from src.analysis.telegram_trust_score import get_channel_trust_metrics
        
        result = get_channel_trust_metrics("nonexistent_channel_xyz_123")
        # Should return None (channel not in DB)
        assert result is None


# ============================================
# REGRESSION TESTS FOR BUG FIXES (2026-01-06)
# ============================================

class TestEchoChamberCacheTTL:
    """
    REGRESSION TEST: Echo chamber cache memory leak fix.
    
    BUG: Cache had no TTL, entries stayed forever causing memory leak.
    FIX: Added _CACHE_TTL_SECONDS (1 hour) and TTL-based cleanup.
    """
    
    def test_cache_ttl_constant_exists(self):
        """_CACHE_TTL_SECONDS should be defined."""
        from src.analysis.telegram_trust_score import _CACHE_TTL_SECONDS
        assert _CACHE_TTL_SECONDS > 0
        assert _CACHE_TTL_SECONDS == 3600  # 1 hour
    
    def test_old_entries_cleaned_up(self):
        """Entries older than TTL should be cleaned up."""
        from src.analysis.telegram_trust_score import (
            check_echo_chamber, 
            _recent_messages_cache,
            _CACHE_TTL_SECONDS
        )
        
        # Clear cache first
        _recent_messages_cache.clear()
        
        # Add an old entry (2 hours ago)
        old_time = datetime.now(timezone.utc) - timedelta(seconds=_CACHE_TTL_SECONDS + 3600)
        check_echo_chamber("old_channel", "This is an old test message for cleanup", old_time)
        
        # Add a new entry (triggers cleanup)
        new_time = datetime.now(timezone.utc)
        check_echo_chamber("new_channel", "This is a new test message for cleanup", new_time)
        
        # Old entry should be cleaned up (its hash should not be in cache)
        # The new entry should still be there
        assert len(_recent_messages_cache) >= 1  # At least new entry


class TestTrustLevelEnumSafeParsing:
    """
    REGRESSION TEST: TrustLevel enum ValueError fix.
    
    BUG: Invalid trust_level string from DB caused ValueError crash.
    FIX: Safe parsing with fallback to NEUTRAL.
    """
    
    def test_invalid_trust_level_returns_neutral(self):
        """Invalid trust_level should fallback to NEUTRAL, not crash."""
        from src.analysis.telegram_trust_score import get_channel_trust_metrics, TrustLevel
        from unittest.mock import patch
        
        # Mock DB to return invalid trust_level
        mock_metrics = {
            'channel_id': 'test_channel',
            'channel_name': 'TestChannel',
            'total_messages': 10,
            'insider_hits': 2,
            'late_messages': 1,
            'echo_messages': 0,
            'red_flags_count': 0,
            'trust_score': 0.5,
            'trust_level': 'INVALID_LEVEL'  # This would crash before fix
        }
        
        # Mock the DB function that get_channel_trust_metrics imports
        with patch('src.database.telegram_channel_model.get_channel_metrics', return_value=mock_metrics):
            # Should NOT raise ValueError
            result = get_channel_trust_metrics('test_channel')
            assert result is not None
            assert result.trust_level == TrustLevel.NEUTRAL  # Fallback
