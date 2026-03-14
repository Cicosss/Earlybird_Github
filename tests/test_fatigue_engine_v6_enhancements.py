"""
Comprehensive Unit Tests for Fatigue Engine V6.0 Enhancements

Tests for:
1. Enhanced format_fatigue_context() with all fields
2. Real match history tracking from database
3. Integration with database queries
4. Cache functionality
5. Error handling and graceful degradation

Author: EarlyBird AI
Date: 2026-03-10
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock

from src.analysis.fatigue_engine import (
    FatigueAnalysis,
    FatigueDifferential,
    format_fatigue_context,
    get_team_match_history,
    clear_match_history_cache,
    get_enhanced_fatigue_context,
    analyze_fatigue_differential,
    analyze_team_fatigue,
)


class TestEnhancedFormatFatigueContext:
    """Test enhanced format_fatigue_context() with all fields."""

    def test_format_includes_matches_in_window(self):
        """Should include matches_in_window field in output."""
        home = FatigueAnalysis(
            team_name="Home FC",
            fatigue_index=0.75,
            fatigue_level="HIGH",
            hours_since_last=68.0,
            matches_in_window=4,
            squad_depth_score=1.0,
            late_game_risk="HIGH",
            late_game_probability=0.45,
            reasoning="4 partite negli ultimi 21 giorni",
        )
        away = FatigueAnalysis(
            team_name="Away FC",
            fatigue_index=0.25,
            fatigue_level="LOW",
            hours_since_last=120.0,
            matches_in_window=2,
            squad_depth_score=0.7,
            late_game_risk="LOW",
            late_game_probability=0.20,
            reasoning="2 partite negli ultimi 21 giorni",
        )
        differential = FatigueDifferential(
            home_fatigue=home,
            away_fatigue=away,
            differential=0.5,
            advantage="AWAY",
            late_game_edge="HOME",
            betting_signal="⚡ FATIGUE EDGE: Away FC significativamente più fresco di Home FC",
        )

        result = format_fatigue_context(differential)

        assert "Matches: 4" in result
        assert "Matches: 2" in result

    def test_format_includes_reasoning(self):
        """Should include reasoning field in output."""
        home = FatigueAnalysis(
            team_name="Home FC",
            fatigue_index=0.75,
            fatigue_level="HIGH",
            hours_since_last=68.0,
            matches_in_window=4,
            squad_depth_score=1.0,
            late_game_risk="HIGH",
            late_game_probability=0.45,
            reasoning="4 partite negli ultimi 21 giorni | Rosa corta (soffre la congestione)",
        )
        away = FatigueAnalysis(
            team_name="Away FC",
            fatigue_index=0.25,
            fatigue_level="LOW",
            hours_since_last=120.0,
            matches_in_window=2,
            squad_depth_score=0.5,
            late_game_risk="LOW",
            late_game_probability=0.20,
            reasoning="2 partite negli ultimi 21 giorni | Rosa profonda (gestisce bene la fatica)",
        )
        differential = FatigueDifferential(
            home_fatigue=home,
            away_fatigue=away,
            differential=0.5,
            advantage="AWAY",
            late_game_edge="HOME",
            betting_signal="⚡ FATIGUE EDGE: Away FC significativamente più fresco di Home FC",
        )

        result = format_fatigue_context(differential)

        assert "Reasoning: 4 partite negli ultimi 21 giorni | Rosa corta (soffre la congestione)" in result
        assert "Reasoning: 2 partite negli ultimi 21 giorni | Rosa profonda (gestisce bene la fatica)" in result

    def test_format_includes_squad_depth_score(self):
        """Should include squad_depth_score field in output."""
        home = FatigueAnalysis(
            team_name="Home FC",
            fatigue_index=0.75,
            fatigue_level="HIGH",
            hours_since_last=68.0,
            matches_in_window=4,
            squad_depth_score=1.3,
            late_game_risk="HIGH",
            late_game_probability=0.45,
            reasoning="Rosa corta (soffre la congestione)",
        )
        away = FatigueAnalysis(
            team_name="Away FC",
            fatigue_index=0.25,
            fatigue_level="LOW",
            hours_since_last=120.0,
            matches_in_window=2,
            squad_depth_score=0.5,
            late_game_risk="LOW",
            late_game_probability=0.20,
            reasoning="Rosa profonda (gestisce bene la fatica)",
        )
        differential = FatigueDifferential(
            home_fatigue=home,
            away_fatigue=away,
            differential=0.5,
            advantage="AWAY",
            late_game_edge="HOME",
            betting_signal="⚡ FATIGUE EDGE: Away FC significativamente più fresco di Home FC",
        )

        result = format_fatigue_context(differential)

        assert "Squad Depth: 1.3x" in result
        assert "Squad Depth: 0.5x" in result

    def test_format_with_none_hours_since_last(self):
        """Should handle None hours_since_last gracefully."""
        home = FatigueAnalysis(
            team_name="Home FC",
            fatigue_index=0.0,
            fatigue_level="FRESH",
            hours_since_last=None,
            matches_in_window=0,
            squad_depth_score=1.0,
            late_game_risk="LOW",
            late_game_probability=0.20,
            reasoning="Condizione fisica normale",
        )
        away = FatigueAnalysis(
            team_name="Away FC",
            fatigue_index=0.0,
            fatigue_level="FRESH",
            hours_since_last=None,
            matches_in_window=0,
            squad_depth_score=1.0,
            late_game_risk="LOW",
            late_game_probability=0.20,
            reasoning="Condizione fisica normale",
        )
        differential = FatigueDifferential(
            home_fatigue=home,
            away_fatigue=away,
            differential=0.0,
            advantage="NEUTRAL",
            late_game_edge="NEUTRAL",
            betting_signal=None,
        )

        result = format_fatigue_context(differential)

        # Should still include matches and squad depth even without hours
        assert "Matches: 0" in result
        assert "Squad Depth: 1.0x" in result
        # Should not show hours
        assert "h riposo" not in result

    def test_format_complete_output(self):
        """Should produce complete formatted output with all fields."""
        home = FatigueAnalysis(
            team_name="Manchester City",
            fatigue_index=0.30,
            fatigue_level="MEDIUM",
            hours_since_last=96.0,
            matches_in_window=3,
            squad_depth_score=0.5,
            late_game_risk="LOW",
            late_game_probability=0.22,
            reasoning="3 partite negli ultimi 21 giorni | Rosa profonda (gestisce bene la fatica)",
        )
        away = FatigueAnalysis(
            team_name="Luton Town",
            fatigue_index=0.65,
            fatigue_level="HIGH",
            hours_since_last=72.0,
            matches_in_window=4,
            squad_depth_score=1.3,
            late_game_risk="HIGH",
            late_game_probability=0.50,
            reasoning="4 partite negli ultimi 21 giorni | Rosa corta (soffre la congestione) | Alto rischio goal subiti dopo 75' (50%)",
        )
        differential = FatigueDifferential(
            home_fatigue=home,
            away_fatigue=away,
            differential=-0.35,
            advantage="HOME",
            late_game_edge="AWAY",
            betting_signal="⚡ FATIGUE EDGE: Manchester City significativamente più fresco di Luton Town | ⏱️ LATE GOAL: Luton Town a rischio goal dopo 75' (50%)",
        )

        result = format_fatigue_context(differential)

        # Verify all fields are present
        assert "⚡ FATIGUE ANALYSIS (V2.0):" in result
        assert "Manchester City: MEDIUM (Index: 0.30)" in result
        assert "Luton Town: HIGH (Index: 0.65)" in result
        assert "96h riposo" in result
        assert "72h riposo" in result
        assert "Matches: 3" in result
        assert "Matches: 4" in result
        assert "Squad Depth: 0.5x" in result
        assert "Squad Depth: 1.3x" in result
        assert "Late Risk: LOW" in result
        assert "Late Risk: HIGH" in result
        assert "Reasoning:" in result
        assert "📊 Vantaggio: HOME" in result
        assert "🎯 ⚡ FATIGUE EDGE:" in result


class TestMatchHistoryTracking:
    """Test real match history tracking from database."""

    @patch("src.analysis.fatigue_engine.get_db_session")
    def test_get_team_match_history_queries_database(self, mock_get_db_session):
        """Should query database for team's recent matches."""
        # Setup mock
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        # Create mock matches
        now = datetime.now(timezone.utc)
        match1 = now - timedelta(days=1)
        match2 = now - timedelta(days=5)
        match3 = now - timedelta(days=10)

        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [Mock(start_time=match1), Mock(start_time=match2), Mock(start_time=match3)]

        # Execute
        match_dates, hours_since_last = get_team_match_history("Test Team", now)

        # Verify
        assert len(match_dates) == 3
        assert hours_since_last is not None
        assert hours_since_last > 0
        mock_session.query.assert_called_once()

    @patch("src.analysis.fatigue_engine.get_db_session")
    def test_get_team_match_history_calculates_hours_since_last(self, mock_get_db_session):
        """Should correctly calculate hours since last match."""
        # Setup mock
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        now = datetime.now(timezone.utc)
        last_match_time = now - timedelta(hours=72)

        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [Mock(start_time=last_match_time)]

        # Execute
        match_dates, hours_since_last = get_team_match_history("Test Team", now)

        # Verify
        assert len(match_dates) == 1
        assert hours_since_last == pytest.approx(72.0, abs=0.1)

    @patch("src.analysis.fatigue_engine.get_db_session")
    def test_get_team_match_history_empty_result(self, mock_get_db_session):
        """Should return empty list and None hours when no matches found."""
        # Setup mock
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        # Execute
        match_dates, hours_since_last = get_team_match_history("New Team", datetime.now(timezone.utc))

        # Verify
        assert match_dates == []
        assert hours_since_last is None

    @patch("src.analysis.fatigue_engine.get_db_session")
    def test_get_team_match_history_filters_by_window(self, mock_get_db_session):
        """Should only return matches within the specified window."""
        # Setup mock
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        now = datetime.now(timezone.utc)
        match_in_window = now - timedelta(days=10)
        match_out_of_window = now - timedelta(days=30)

        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [Mock(start_time=match_in_window)]

        # Execute with 21-day window
        match_dates, hours_since_last = get_team_match_history("Test Team", now, window_days=21)

        # Verify filter was called with correct window
        assert len(match_dates) == 1

    @patch("src.analysis.fatigue_engine.get_db_session")
    def test_get_team_match_history_queries_both_home_and_away(self, mock_get_db_session):
        """Should query matches where team played both home and away."""
        # Setup mock
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        now = datetime.now(timezone.utc)
        match1 = now - timedelta(days=1)
        match2 = now - timedelta(days=5)

        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [Mock(start_time=match1), Mock(start_time=match2)]

        # Execute
        match_dates, hours_since_last = get_team_match_history("Test Team", now)

        # Verify query was made
        mock_session.query.assert_called_once()

    def test_clear_match_history_cache(self):
        """Should clear the match history cache."""
        # Setup: Add something to cache
        from src.analysis.fatigue_engine import _match_history_cache
        _match_history_cache["test_key"] = ([], None, datetime.now(timezone.utc))

        assert len(_match_history_cache) > 0

        # Execute
        clear_match_history_cache()

        # Verify
        assert len(_match_history_cache) == 0


class TestMatchHistoryCaching:
    """Test caching functionality for match history."""

    @patch("src.analysis.fatigue_engine.get_db_session")
    def test_cache_hit_returns_cached_data(self, mock_get_db_session):
        """Should return cached data without querying database."""
        # Setup mock
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        now = datetime.now(timezone.utc)
        team_name = "Test Team"

        # First call - should query database
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [Mock(start_time=now - timedelta(hours=72))]

        match_dates1, hours1 = get_team_match_history(team_name, now)

        # Second call - should use cache (no database query)
        match_dates2, hours2 = get_team_match_history(team_name, now)

        # Verify both calls returned same data
        assert match_dates1 == match_dates2
        assert hours1 == hours2

    @patch("src.analysis.fatigue_engine.get_db_session")
    def test_cache_expires_after_ttl(self, mock_get_db_session):
        """Should expire cache after TTL and query database again."""
        from src.analysis.fatigue_engine import _CACHE_TTL

        # Setup mock
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        now = datetime.now(timezone.utc)
        team_name = "Test Team"

        # First call
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [Mock(start_time=now - timedelta(hours=72))]

        match_dates1, hours1 = get_team_match_history(team_name, now)

        # Simulate cache expiration by modifying cache timestamp
        from src.analysis.fatigue_engine import _match_history_cache
        cache_key = f"{team_name.lower()}_{now.isoformat()}"
        if cache_key in _match_history_cache:
            data, _, _ = _match_history_cache[cache_key]
            expired_time = now - _CACHE_TTL - timedelta(minutes=1)
            _match_history_cache[cache_key] = (data, expired_time)

        # Second call - should query database again due to expired cache
        mock_query.all.return_value = [Mock(start_time=now - timedelta(hours=48))]

        match_dates2, hours2 = get_team_match_history(team_name, now)

        # Verify database was queried again
        assert mock_session.query.call_count == 2


class TestEnhancedFatigueContextIntegration:
    """Test integration of enhanced fatigue context with database."""

    @patch("src.analysis.fatigue_engine.get_db_session")
    def test_get_enhanced_fatigue_context_uses_db_data(self, mock_get_db_session):
        """Should use real match history from database when available."""
        # Setup mock
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        now = datetime.now(timezone.utc)

        # Mock home team match history
        mock_query_home = MagicMock()
        mock_session.query.return_value = mock_query_home
        mock_query_home.filter.return_value = mock_query_home
        mock_query_home.order_by.return_value = mock_query_home
        mock_query_home.all.return_value = [Mock(start_time=now - timedelta(hours=68))]

        home_context = {"fatigue": {"hours_since_last": None}}
        away_context = {"fatigue": {"hours_since_last": None}}

        # Execute
        differential, context_str = get_enhanced_fatigue_context(
            home_team="Home FC",
            away_team="Away FC",
            home_context=home_context,
            away_context=away_context,
            match_start_time=now,
        )

        # Verify database data was used
        assert differential.home_fatigue.hours_since_last == pytest.approx(68.0, abs=0.1)

    @patch("src.analysis.fatigue_engine.get_db_session")
    def test_get_enhanced_fatigue_context_fallback_on_error(self, mock_get_db_session):
        """Should fallback to FotMob data if database query fails."""
        # Setup mock to raise exception
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.side_effect = Exception("Database error")

        now = datetime.now(timezone.utc)

        home_context = {"fatigue": {"hours_since_last": 72.0}}
        away_context = {"fatigue": {"hours_since_last": 96.0}}

        # Execute - should not crash
        differential, context_str = get_enhanced_fatigue_context(
            home_team="Home FC",
            away_team="Away FC",
            home_context=home_context,
            away_context=away_context,
            match_start_time=now,
        )

        # Verify fallback data was used
        assert differential.home_fatigue.hours_since_last == 72.0
        assert differential.away_fatigue.hours_since_last == 96.0

    @patch("src.analysis.fatigue_engine.get_db_session")
    def test_analyze_fatigue_differential_with_real_history(self, mock_get_db_session):
        """Should use real match history for exponential decay calculation."""
        # Setup mock
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        now = datetime.now(timezone.utc)

        # Mock congested schedule (4 matches in 7 days)
        match_dates = [
            now - timedelta(hours=48),
            now - timedelta(hours=96),
            now - timedelta(hours=144),
            now - timedelta(hours=168),
        ]

        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [Mock(start_time=dt) for dt in match_dates]

        # Execute
        differential = analyze_fatigue_differential(
            home_team="Congested Team",
            away_team="Fresh Team",
            home_hours_since_last=48.0,
            away_hours_since_last=168.0,
            home_recent_matches=match_dates,
            away_recent_matches=[],
            target_match_date=now,
        )

        # Verify exponential decay was used
        assert differential.home_fatigue.matches_in_window == 4
        assert differential.home_fatigue.fatigue_index > 0.3  # Should show fatigue from congestion


class TestErrorHandling:
    """Test error handling and graceful degradation."""

    @patch("src.analysis.fatigue_engine.get_db_session")
    def test_database_error_returns_empty_data(self, mock_get_db_session):
        """Should return empty data on database error."""
        # Setup mock to raise exception
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.side_effect = Exception("Connection failed")

        # Execute
        match_dates, hours_since_last = get_team_match_history(
            "Test Team", datetime.now(timezone.utc)
        )

        # Verify graceful degradation
        assert match_dates == []
        assert hours_since_last is None

    def test_format_fatigue_context_handles_empty_reasoning(self):
        """Should handle empty reasoning string."""
        home = FatigueAnalysis(
            team_name="Home FC",
            fatigue_index=0.5,
            fatigue_level="MEDIUM",
            hours_since_last=96.0,
            matches_in_window=2,
            squad_depth_score=1.0,
            late_game_risk="MEDIUM",
            late_game_probability=0.30,
            reasoning="",  # Empty reasoning
        )
        away = FatigueAnalysis(
            team_name="Away FC",
            fatigue_index=0.5,
            fatigue_level="MEDIUM",
            hours_since_last=96.0,
            matches_in_window=2,
            squad_depth_score=1.0,
            late_game_risk="MEDIUM",
            late_game_probability=0.30,
            reasoning="",  # Empty reasoning
        )
        differential = FatigueDifferential(
            home_fatigue=home,
            away_fatigue=away,
            differential=0.0,
            advantage="NEUTRAL",
            late_game_edge="NEUTRAL",
            betting_signal=None,
        )

        # Should not crash
        result = format_fatigue_context(differential)
        assert result is not None
        assert "⚡ FATIGUE ANALYSIS (V2.0):" in result
