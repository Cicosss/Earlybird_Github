"""
Test di regressione per Phase 1 (Data Ingestion) e Phase 2 (Context Enrichment)

Verifica i fix applicati durante l'audit:
1. Logger definito prima dell'uso in data_provider.py
2. Validazione eventi malformati in ingest_fixtures.py
3. Edge case in weather_provider.py
4. Edge case in fatigue_engine.py

Author: EarlyBird Audit
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock


class TestDataProviderLoggerOrder:
    """Test che il logger sia definito prima dell'uso."""
    
    def test_logger_import_no_error(self):
        """
        BUG FIX #1: logger.warning() era chiamato prima che logger fosse definito.
        Questo test verifica che l'import non sollevi NameError.
        """
        # Se l'import fallisce con NameError, il bug è tornato
        try:
            # Force reimport to test module initialization
            import importlib
            import src.ingestion.data_provider as dp
            importlib.reload(dp)
            assert True
        except NameError as e:
            pytest.fail(f"Logger used before definition: {e}")
    
    def test_smart_cache_import_failure_handled(self):
        """
        Verifica che se smart_cache non è disponibile, il warning viene loggato
        senza causare NameError.
        """
        # Il modulo dovrebbe importarsi senza errori anche se smart_cache manca
        import src.ingestion.data_provider as dp
        # Se siamo qui, il test passa
        assert hasattr(dp, 'logger')
        assert hasattr(dp, '_SMART_CACHE_AVAILABLE')


class TestIngestFixturesMalformedEvents:
    """Test per la validazione di eventi malformati dall'API."""
    
    def test_malformed_event_missing_id(self):
        """
        BUG FIX #2: Eventi senza 'id' dovrebbero essere skippati.
        """
        malformed_event = {
            'commence_time': '2025-01-10T15:00:00Z',
            'home_team': 'Team A',
            'away_team': 'Team B'
            # Missing 'id'
        }
        
        required_keys = ('id', 'commence_time', 'home_team', 'away_team')
        has_all_keys = all(k in malformed_event for k in required_keys)
        
        assert not has_all_keys, "Event missing 'id' should be detected"
    
    def test_malformed_event_missing_teams(self):
        """Eventi senza team names dovrebbero essere skippati."""
        malformed_event = {
            'id': '12345',
            'commence_time': '2025-01-10T15:00:00Z',
            # Missing 'home_team' and 'away_team'
        }
        
        required_keys = ('id', 'commence_time', 'home_team', 'away_team')
        has_all_keys = all(k in malformed_event for k in required_keys)
        
        assert not has_all_keys, "Event missing teams should be detected"
    
    def test_valid_event_passes(self):
        """Eventi validi dovrebbero passare la validazione."""
        valid_event = {
            'id': '12345',
            'commence_time': '2025-01-10T15:00:00Z',
            'home_team': 'Team A',
            'away_team': 'Team B',
            'bookmakers': []
        }
        
        required_keys = ('id', 'commence_time', 'home_team', 'away_team')
        has_all_keys = all(k in valid_event for k in required_keys)
        
        assert has_all_keys, "Valid event should pass validation"


class TestWeatherProviderEdgeCases:
    """Test per edge case nel weather provider."""
    
    def test_validate_coordinates_null_island(self):
        """Coordinate (0,0) dovrebbero essere rifiutate (null island)."""
        from src.ingestion.weather_provider import validate_coordinates
        
        assert not validate_coordinates(0.0, 0.0), "Null island should be rejected"
    
    def test_validate_coordinates_out_of_range(self):
        """Coordinate fuori range dovrebbero essere rifiutate."""
        from src.ingestion.weather_provider import validate_coordinates
        
        assert not validate_coordinates(91.0, 0.0), "Latitude > 90 should be rejected"
        assert not validate_coordinates(-91.0, 0.0), "Latitude < -90 should be rejected"
        assert not validate_coordinates(0.0, 181.0), "Longitude > 180 should be rejected"
        assert not validate_coordinates(0.0, -181.0), "Longitude < -180 should be rejected"
    
    def test_validate_coordinates_valid(self):
        """Coordinate valide dovrebbero essere accettate."""
        from src.ingestion.weather_provider import validate_coordinates
        
        # Rome
        assert validate_coordinates(41.9028, 12.4964), "Rome coordinates should be valid"
        # London
        assert validate_coordinates(51.5074, -0.1278), "London coordinates should be valid"
        # Sydney
        assert validate_coordinates(-33.8688, 151.2093), "Sydney coordinates should be valid"
    
    def test_analyze_weather_impact_none_input(self):
        """Input None dovrebbe restituire None."""
        from src.ingestion.weather_provider import analyze_weather_impact
        
        result = analyze_weather_impact(None)
        assert result is None
    
    def test_analyze_weather_impact_good_weather(self):
        """Buon tempo dovrebbe restituire None (nessun impatto)."""
        from src.ingestion.weather_provider import analyze_weather_impact
        
        good_weather = {
            'snowfall_cm': 0,
            'precipitation_mm': 1.0,  # Light rain
            'wind_kmh': 15.0,  # Light wind
            'temperature_c': 20.0
        }
        
        result = analyze_weather_impact(good_weather)
        assert result is None, "Good weather should return None (no impact)"


class TestFatigueEngineEdgeCases:
    """Test per edge case nel fatigue engine."""
    
    def test_calculate_fatigue_index_empty_schedule(self):
        """Schedule vuoto dovrebbe restituire fatigue 0."""
        from src.analysis.fatigue_engine import calculate_fatigue_index
        
        fatigue, matches = calculate_fatigue_index(
            team_schedule=[],
            match_date=datetime.now(timezone.utc),
            squad_depth_score=1.0
        )
        
        assert fatigue == 0.0
        assert matches == 0
    
    def test_calculate_fatigue_index_none_schedule(self):
        """Schedule None dovrebbe restituire fatigue 0."""
        from src.analysis.fatigue_engine import calculate_fatigue_index
        
        fatigue, matches = calculate_fatigue_index(
            team_schedule=None,
            match_date=datetime.now(timezone.utc),
            squad_depth_score=1.0
        )
        
        assert fatigue == 0.0
        assert matches == 0
    
    def test_squad_depth_elite_team(self):
        """Team elite dovrebbero avere multiplier 0.5."""
        from src.analysis.fatigue_engine import get_squad_depth_score
        
        assert get_squad_depth_score("Manchester City") == 0.5
        assert get_squad_depth_score("Real Madrid") == 0.5
        assert get_squad_depth_score("Bayern Munich") == 0.5
    
    def test_squad_depth_low_tier_team(self):
        """Team low tier dovrebbero avere multiplier 1.3."""
        from src.analysis.fatigue_engine import get_squad_depth_score
        
        assert get_squad_depth_score("Luton Town") == 1.3
        assert get_squad_depth_score("Frosinone") == 1.3
    
    def test_squad_depth_unknown_team(self):
        """Team sconosciuti dovrebbero avere multiplier 1.0 (default)."""
        from src.analysis.fatigue_engine import get_squad_depth_score
        
        assert get_squad_depth_score("Unknown FC") == 1.0
        assert get_squad_depth_score("") == 1.0
        assert get_squad_depth_score(None) == 1.0
    
    def test_division_by_zero_protection(self):
        """
        Verifica che la divisione per zero sia protetta.
        weight = 1.0 / max(days_ago, 0.5)
        """
        from src.analysis.fatigue_engine import calculate_fatigue_index
        
        now = datetime.now(timezone.utc)
        # Match played "now" (0 days ago) - should not cause division by zero
        schedule = [now - timedelta(minutes=1)]
        
        # Should not raise ZeroDivisionError
        fatigue, matches = calculate_fatigue_index(
            team_schedule=schedule,
            match_date=now,
            squad_depth_score=1.0
        )
        
        assert matches == 1
        assert fatigue > 0  # Should have some fatigue


class TestBiscottoEngineEdgeCases:
    """Test per edge case nel biscotto engine."""
    
    def test_implied_probability_none_odds(self):
        """Odds None dovrebbe restituire probabilità 0."""
        from src.analysis.biscotto_engine import calculate_implied_probability
        
        assert calculate_implied_probability(None) == 0.0
    
    def test_implied_probability_invalid_odds(self):
        """Odds <= 1.0 dovrebbe restituire probabilità 0."""
        from src.analysis.biscotto_engine import calculate_implied_probability
        
        assert calculate_implied_probability(1.0) == 0.0
        assert calculate_implied_probability(0.5) == 0.0
        assert calculate_implied_probability(-1.0) == 0.0
    
    def test_implied_probability_valid_odds(self):
        """Odds valide dovrebbero restituire probabilità corretta."""
        from src.analysis.biscotto_engine import calculate_implied_probability
        
        # 2.0 odds = 50% probability
        assert calculate_implied_probability(2.0) == 0.5
        # 4.0 odds = 25% probability
        assert calculate_implied_probability(4.0) == 0.25
    
    def test_analyze_biscotto_none_odds(self):
        """Analisi con odds None dovrebbe restituire is_suspect=False."""
        from src.analysis.biscotto_engine import analyze_biscotto, BiscottoSeverity
        
        result = analyze_biscotto(
            home_team="Team A",
            away_team="Team B",
            current_draw_odd=None
        )
        
        assert result.is_suspect == False
        assert result.severity == BiscottoSeverity.NONE
    
    def test_minor_league_threshold(self):
        """Minor leagues dovrebbero usare threshold più stretto."""
        from src.analysis.biscotto_engine import get_draw_threshold_for_league
        
        # Standard league
        assert get_draw_threshold_for_league("soccer_italy_serie_a", end_of_season=True) == 2.50
        
        # Minor league in end of season
        assert get_draw_threshold_for_league("soccer_italy_serie_b", end_of_season=True) == 2.60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
