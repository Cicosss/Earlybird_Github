"""
Test di regressione per Phase 2 (Context Enrichment) e Phase 3 (Math Engine).

Questi test verificano:
1. Fatigue Engine V2.0 - edge cases e calcoli
2. Weather Provider - validazione coordinate e thresholds
3. Math Engine (Poisson + Kelly) - edge cases e bounds
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock


class TestFatigueEngineV2:
    """Test per src/analysis/fatigue_engine.py"""
    
    def test_empty_schedule_returns_zero_fatigue(self):
        """Lista vuota di partite = 0 fatigue."""
        from src.analysis.fatigue_engine import calculate_fatigue_index
        
        fatigue_index, matches = calculate_fatigue_index(
            team_schedule=[],
            match_date=datetime.now(timezone.utc),
            squad_depth_score=1.0
        )
        
        assert fatigue_index == 0.0
        assert matches == 0
    
    def test_none_schedule_returns_zero_fatigue(self):
        """None schedule = 0 fatigue (no crash)."""
        from src.analysis.fatigue_engine import calculate_fatigue_index
        
        fatigue_index, matches = calculate_fatigue_index(
            team_schedule=None,
            match_date=datetime.now(timezone.utc),
            squad_depth_score=1.0
        )
        
        assert fatigue_index == 0.0
        assert matches == 0
    
    def test_elite_squad_reduces_fatigue(self):
        """Elite squads (0.5x) should have lower fatigue index."""
        from src.analysis.fatigue_engine import calculate_fatigue_index
        
        now = datetime.now(timezone.utc)
        recent_games = [now - timedelta(days=2), now - timedelta(days=5)]
        
        # Same schedule, different squad depth
        fatigue_elite, _ = calculate_fatigue_index(recent_games, now, 0.5)
        fatigue_mid, _ = calculate_fatigue_index(recent_games, now, 1.0)
        fatigue_low, _ = calculate_fatigue_index(recent_games, now, 1.3)
        
        assert fatigue_elite < fatigue_mid < fatigue_low
    
    def test_squad_depth_lookup_known_teams(self):
        """Verifica che i team noti abbiano il corretto squad depth."""
        from src.analysis.fatigue_engine import get_squad_depth_score, SQUAD_DEPTH_ELITE, SQUAD_DEPTH_LOW
        
        # Elite teams
        assert get_squad_depth_score("Manchester City") == SQUAD_DEPTH_ELITE
        assert get_squad_depth_score("Real Madrid") == SQUAD_DEPTH_ELITE
        
        # Low tier teams
        assert get_squad_depth_score("Luton Town") == SQUAD_DEPTH_LOW
        assert get_squad_depth_score("Frosinone") == SQUAD_DEPTH_LOW
    
    def test_squad_depth_unknown_team_returns_mid(self):
        """Team sconosciuto = squad depth medio (1.0)."""
        from src.analysis.fatigue_engine import get_squad_depth_score, SQUAD_DEPTH_MID
        
        assert get_squad_depth_score("Unknown FC 2024") == SQUAD_DEPTH_MID
        assert get_squad_depth_score("") == SQUAD_DEPTH_MID
        assert get_squad_depth_score(None) == SQUAD_DEPTH_MID
    
    def test_late_game_risk_increases_with_fatigue(self):
        """Higher fatigue = higher late game risk."""
        from src.analysis.fatigue_engine import calculate_late_game_risk
        
        risk_fresh, prob_fresh = calculate_late_game_risk(0.0, "FRESH")
        risk_critical, prob_critical = calculate_late_game_risk(0.9, "CRITICAL")
        
        assert prob_fresh < prob_critical
        assert risk_fresh == "LOW"
        assert risk_critical == "HIGH"


class TestWeatherProvider:
    """Test per src/ingestion/weather_provider.py"""
    
    def test_invalid_coordinates_rejected(self):
        """Coordinate non valide devono essere rifiutate."""
        from src.ingestion.weather_provider import validate_coordinates
        
        # Null island (0,0) - likely missing data
        assert validate_coordinates(0.0, 0.0) is False
        
        # Out of range
        assert validate_coordinates(91.0, 0.0) is False
        assert validate_coordinates(0.0, 181.0) is False
        assert validate_coordinates(-91.0, 0.0) is False
        
        # Valid coordinates
        assert validate_coordinates(45.0, 9.0) is True  # Milan
        assert validate_coordinates(51.5, -0.1) is True  # London
    
    def test_none_coordinates_rejected(self):
        """None coordinates = False (no crash)."""
        from src.ingestion.weather_provider import validate_coordinates
        
        assert validate_coordinates(None, None) is False
        assert validate_coordinates(45.0, None) is False
        assert validate_coordinates(None, 9.0) is False
    
    def test_weather_impact_thresholds(self):
        """Verifica che i threshold generino gli alert corretti."""
        from src.ingestion.weather_provider import analyze_weather_impact
        
        # High wind - V4.6: threshold raised from 30 to 40 km/h
        high_wind_data = {"wind_kmh": 45, "precipitation_mm": 0, "snowfall_cm": 0}
        result = analyze_weather_impact(high_wind_data)
        assert result is not None
        assert result["status"] == "HIGH"
        assert "HIGH WIND" in result["conditions"][0]
        
        # Wind below threshold should NOT trigger alert
        moderate_wind_data = {"wind_kmh": 35, "precipitation_mm": 0, "snowfall_cm": 0}
        result = analyze_weather_impact(moderate_wind_data)
        assert result is None, "35 km/h wind should not trigger alert (threshold is 40)"
        
        # Heavy rain - V4.6: threshold raised from 4 to 5 mm/h
        heavy_rain_data = {"wind_kmh": 10, "precipitation_mm": 6, "snowfall_cm": 0}
        result = analyze_weather_impact(heavy_rain_data)
        assert result is not None
        assert "HEAVY RAIN" in result["conditions"][0]
        
        # Rain below threshold should NOT trigger alert
        moderate_rain_data = {"wind_kmh": 10, "precipitation_mm": 4, "snowfall_cm": 0}
        result = analyze_weather_impact(moderate_rain_data)
        assert result is None, "4 mm/h rain should not trigger alert (threshold is 5)"
        
        # Good weather = None (no alert)
        good_weather = {"wind_kmh": 10, "precipitation_mm": 1, "snowfall_cm": 0}
        result = analyze_weather_impact(good_weather)
        assert result is None
    
    def test_snow_is_extreme(self):
        """Any snowfall should be EXTREME severity."""
        from src.ingestion.weather_provider import analyze_weather_impact
        
        snow_data = {"wind_kmh": 5, "precipitation_mm": 0, "snowfall_cm": 0.5}
        result = analyze_weather_impact(snow_data)
        
        assert result is not None
        assert result["status"] == "EXTREME"


class TestMathEnginePoisson:
    """Test per src/analysis/math_engine.py - Poisson Model"""
    
    def test_poisson_probability_zero_lambda(self):
        """Lambda = 0 deve restituire 1.0 per k=0, 0.0 altrimenti."""
        from src.analysis.math_engine import MathPredictor
        
        assert MathPredictor.poisson_probability(0, 0) == 1.0
        assert MathPredictor.poisson_probability(0, 1) == 0.0
        assert MathPredictor.poisson_probability(0, 5) == 0.0
    
    def test_poisson_probability_negative_lambda(self):
        """Lambda negativo = stesso comportamento di zero."""
        from src.analysis.math_engine import MathPredictor
        
        assert MathPredictor.poisson_probability(-1, 0) == 1.0
        assert MathPredictor.poisson_probability(-1, 1) == 0.0
    
    def test_simulate_match_invalid_inputs_returns_none(self):
        """Input non validi devono restituire None."""
        from src.analysis.math_engine import MathPredictor
        
        predictor = MathPredictor()
        
        # None values
        result = predictor.simulate_match(None, 1.0, 1.0, 1.0)
        assert result is None
        
        # Negative values
        result = predictor.simulate_match(-1, 1.0, 1.0, 1.0)
        assert result is None
    
    def test_simulate_match_probabilities_sum_to_one(self):
        """Le probabilità H/D/A devono sommare a ~1.0."""
        from src.analysis.math_engine import MathPredictor
        
        predictor = MathPredictor()
        result = predictor.simulate_match(1.5, 1.0, 1.2, 1.3)
        
        assert result is not None
        total = result.home_win_prob + result.draw_prob + result.away_win_prob
        assert 0.99 <= total <= 1.01  # Allow small floating point error
    
    def test_dixon_coles_correction_applied(self):
        """Dixon-Coles correction deve modificare le probabilità low-score."""
        from src.analysis.math_engine import MathPredictor
        
        predictor = MathPredictor()
        
        # With Dixon-Coles
        result_dc = predictor.simulate_match(1.0, 1.0, 1.0, 1.0, use_dixon_coles=True)
        # Without Dixon-Coles
        result_no_dc = predictor.simulate_match(1.0, 1.0, 1.0, 1.0, use_dixon_coles=False)
        
        # Draw probability should be different (DC increases 0-0, 1-1 probability)
        assert result_dc.draw_prob != result_no_dc.draw_prob
    
    def test_home_advantage_applied(self):
        """Home advantage deve aumentare home_lambda."""
        from src.analysis.math_engine import MathPredictor
        
        # With HA
        predictor_ha = MathPredictor(league_key="soccer_epl")
        result_ha = predictor_ha.simulate_match(1.5, 1.0, 1.5, 1.0, apply_home_advantage=True)
        
        # Without HA
        result_no_ha = predictor_ha.simulate_match(1.5, 1.0, 1.5, 1.0, apply_home_advantage=False)
        
        # Home win prob should be higher with HA
        assert result_ha.home_win_prob >= result_no_ha.home_win_prob


class TestMathEngineKelly:
    """Test per src/analysis/math_engine.py - Kelly Criterion"""
    
    def test_kelly_capped_at_max_stake(self):
        """Kelly stake deve essere capped a MAX_STAKE_PCT (5%)."""
        from src.analysis.math_engine import MathPredictor, MAX_STAKE_PCT
        
        # Very high edge scenario that would suggest >5% stake
        edge = MathPredictor.calculate_edge(
            math_prob=0.80,  # 80% probability
            bookmaker_odd=2.0,  # 50% implied
            sample_size=100
        )
        
        assert edge.kelly_stake <= MAX_STAKE_PCT
    
    def test_kelly_zero_for_no_value(self):
        """Kelly = 0 quando non c'è value (edge negativo)."""
        from src.analysis.math_engine import MathPredictor
        
        edge_result = MathPredictor.calculate_edge(
            math_prob=0.30,  # 30% probability
            bookmaker_odd=2.0,  # 50% implied - no value!
            sample_size=50
        )
        
        # V8.3: Minimum stake is 5.0%
        assert edge_result.kelly_stake == 5.0
        assert edge_result.has_value is False
    
    def test_kelly_rejects_low_odds(self):
        """Odds troppo basse (<=1.05) devono essere rifiutate."""
        from src.analysis.math_engine import MathPredictor
        
        edge_result = MathPredictor.calculate_edge(
            math_prob=0.99,
            bookmaker_odd=1.02,  # Too low
            sample_size=50
        )
        
        assert edge_result.kelly_stake == 0
        assert edge_result.has_value is False
    
    def test_shrinkage_kelly_reduces_stake_for_small_samples(self):
        """Shrinkage Kelly deve ridurre lo stake con pochi sample."""
        from src.analysis.math_engine import MathPredictor
        
        # Same probability, different sample sizes
        edge_small = MathPredictor.calculate_edge(0.60, 2.0, sample_size=5)
        edge_large = MathPredictor.calculate_edge(0.60, 2.0, sample_size=50)
        
        # Larger sample = higher confidence = higher stake
        assert edge_small.kelly_stake <= edge_large.kelly_stake


class TestBTTSTrend:
    """Test per calculate_btts_trend in math_engine.py"""
    
    def test_empty_h2h_returns_unknown(self):
        """Lista vuota = Unknown signal."""
        from src.analysis.math_engine import calculate_btts_trend
        
        result = calculate_btts_trend([])
        assert result["trend_signal"] == "Unknown"
        assert result["btts_rate"] == 0.0
    
    def test_none_h2h_returns_unknown(self):
        """None input = Unknown signal (no crash)."""
        from src.analysis.math_engine import calculate_btts_trend
        
        result = calculate_btts_trend(None)
        assert result["trend_signal"] == "Unknown"
    
    def test_btts_calculation_correct(self):
        """Verifica calcolo BTTS rate."""
        from src.analysis.math_engine import calculate_btts_trend
        
        h2h = [
            {"home_score": 2, "away_score": 1},  # BTTS
            {"home_score": 1, "away_score": 0},  # No BTTS
            {"home_score": 3, "away_score": 2},  # BTTS
            {"home_score": 0, "away_score": 0},  # No BTTS
            {"home_score": 1, "away_score": 1},  # BTTS
        ]
        
        result = calculate_btts_trend(h2h)
        
        assert result["btts_hits"] == 3
        assert result["total_games"] == 5
        assert result["btts_rate"] == 60.0
        assert result["trend_signal"] == "High"  # >=60%
    
    def test_btts_handles_none_scores(self):
        """Score None devono essere skippati senza crash."""
        from src.analysis.math_engine import calculate_btts_trend
        
        h2h = [
            {"home_score": 2, "away_score": 1},
            {"home_score": None, "away_score": 1},  # Skip
            {"home_score": 1, "away_score": None},  # Skip
        ]
        
        result = calculate_btts_trend(h2h)
        
        assert result["total_games"] == 1
        assert result["btts_hits"] == 1
    
    def test_btts_logs_debug_on_invalid_input(self, caplog):
        """V4.6 Fix: Verifica che input invalidi generino log debug."""
        import logging
        from src.analysis.math_engine import calculate_btts_trend
        
        with caplog.at_level(logging.DEBUG):
            # Test con None
            result_none = calculate_btts_trend(None)
            assert result_none["trend_signal"] == "Unknown"
            
            # Test con stringa (tipo invalido)
            result_str = calculate_btts_trend("not a list")
            assert result_str["trend_signal"] == "Unknown"
        
        # Verifica che i log debug siano stati generati
        debug_logs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debug_logs) >= 2, "Should log debug for invalid inputs"
        assert any("NoneType" in r.message for r in debug_logs), "Should log None type"
        assert any("str" in r.message for r in debug_logs), "Should log string type"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
