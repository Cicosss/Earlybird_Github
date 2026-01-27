"""
Test di integrazione V4.6 - Verifica flusso dati end-to-end

Questi test verificano che i fix V4.6 si integrino correttamente
nel flusso dati del bot, dalla raccolta dati all'analisi finale.

Author: EarlyBird Audit V4.6
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


class TestMathEngineIntegration:
    """Test integrazione MathPredictor nel flusso principale."""
    
    def test_analyze_match_with_league_specific_ha(self):
        """
        Verifica che MathPredictor usi correttamente l'Home Advantage
        specifico per lega quando chiamato da main.py.
        """
        from src.analysis.math_engine import MathPredictor
        
        # Simula chiamata come in main.py linea 1207
        predictor = MathPredictor(league_key="soccer_turkey_super_league")
        
        # Verifica che HA sia stato caricato correttamente
        assert predictor.home_advantage == 0.38, \
            f"Turkey HA should be 0.38, got {predictor.home_advantage}"
        
        # Esegui analisi completa
        result = predictor.analyze_match(
            home_scored=1.8,
            home_conceded=1.0,
            away_scored=1.2,
            away_conceded=1.5,
            home_odd=1.65,
            draw_odd=3.80,
            away_odd=5.50
        )
        
        assert result is not None
        assert 'poisson' in result
        assert 'edges' in result
        
        # Verifica che le probabilità sommino a ~1
        poisson = result['poisson']
        total = poisson.home_win_prob + poisson.draw_prob + poisson.away_win_prob
        assert 0.99 <= total <= 1.01, f"Probabilities sum to {total}, should be ~1.0"
    
    def test_kelly_stake_reasonable_for_small_samples(self):
        """
        Verifica che Kelly stake sia ragionevole anche con pochi dati.
        Fix #12: Shrinkage Kelly rilassato.
        """
        from src.analysis.math_engine import MathPredictor
        
        # Edge chiaro con pochi dati (tipico scenario reale)
        edge = MathPredictor.calculate_edge(
            math_prob=0.55,  # 55% probability
            bookmaker_odd=2.10,  # Implied ~47.6%
            sample_size=8,  # Pochi match giocati
            use_shrinkage=True
        )
        
        # Con il fix, dovrebbe dare uno stake > 0
        assert edge.kelly_stake > 0, \
            f"Kelly stake is {edge.kelly_stake}%, should be > 0 for clear edge"
        
        # Ma non troppo alto (max 5%)
        assert edge.kelly_stake <= 5.0, \
            f"Kelly stake {edge.kelly_stake}% exceeds cap"
    
    def test_dixon_coles_in_simulate_match(self):
        """
        Verifica che Dixon-Coles correction sia applicata correttamente
        durante simulate_match e non produca valori estremi.
        """
        from src.analysis.math_engine import MathPredictor
        
        predictor = MathPredictor()
        
        # Scenario con lambda alti (dove il bug si manifestava)
        result = predictor.simulate_match(
            home_scored=2.5,  # Team molto offensivo
            home_conceded=0.8,
            away_scored=2.0,
            away_conceded=1.0,
            use_dixon_coles=True
        )
        
        assert result is not None
        
        # Verifica che le probabilità siano valide
        assert 0 <= result.home_win_prob <= 1
        assert 0 <= result.draw_prob <= 1
        assert 0 <= result.away_win_prob <= 1
        
        # Verifica che la somma sia ~1 (normalizzazione funziona)
        total = result.home_win_prob + result.draw_prob + result.away_win_prob
        assert 0.99 <= total <= 1.01


class TestFatigueEngineIntegration:
    """Test integrazione Fatigue Engine nel flusso principale."""
    
    def test_get_enhanced_fatigue_context_with_fotmob_data(self):
        """
        Verifica che get_enhanced_fatigue_context funzioni con dati
        nel formato restituito da FotMob (get_full_team_context).
        """
        from src.analysis.fatigue_engine import get_enhanced_fatigue_context
        
        # Simula dati come restituiti da data_provider.get_full_team_context
        home_context = {
            "team": "Galatasaray",
            "injuries": [{"name": "Icardi", "reason": "Knee"}],
            "motivation": {"zone": "Title Race", "position": 1},
            "fatigue": {
                "hours_since_last": 68.5,  # Meno di 72h
                "fatigue_level": "HIGH - Less than 72h rest",
                "last_match": "vs Fenerbahce"
            }
        }
        
        away_context = {
            "team": "Besiktas",
            "injuries": [],
            "motivation": {"zone": "Europa League", "position": 4},
            "fatigue": {
                "hours_since_last": 120.0,  # 5 giorni
                "fatigue_level": "LOW - Normal rest (4-7 days)",
                "last_match": "vs Trabzonspor"
            }
        }
        
        match_time = datetime.now(timezone.utc) + timedelta(hours=2)
        
        differential, context_str = get_enhanced_fatigue_context(
            home_team="Galatasaray",
            away_team="Besiktas",
            home_context=home_context,
            away_context=away_context,
            match_start_time=match_time
        )
        
        # Verifica risultato
        assert differential is not None
        assert differential.home_fatigue.team_name == "Galatasaray"
        assert differential.away_fatigue.team_name == "Besiktas"
        
        # Home è più stanco (68h vs 120h)
        assert differential.differential > 0, \
            "Home should be more fatigued (positive differential)"
        
        # Verifica context string generato
        assert "FATIGUE ANALYSIS" in context_str
        assert "Galatasaray" in context_str
    
    def test_fatigue_with_none_hours(self):
        """
        Verifica gestione quando hours_since_last è None
        (es. inizio stagione, team senza partite recenti).
        """
        from src.analysis.fatigue_engine import get_enhanced_fatigue_context
        
        # Simula team senza partite recenti
        home_context = {
            "fatigue": {
                "hours_since_last": None,
                "fatigue_level": "FRESH - Season start"
            }
        }
        
        away_context = {
            "fatigue": {
                "hours_since_last": 96.0,
                "fatigue_level": "LOW"
            }
        }
        
        # Non deve crashare
        differential, context_str = get_enhanced_fatigue_context(
            home_team="New Team FC",
            away_team="Established FC",
            home_context=home_context,
            away_context=away_context
        )
        
        assert differential is not None
        assert context_str is not None


class TestWeatherProviderIntegration:
    """Test integrazione Weather Provider nel flusso principale."""
    
    def test_weather_thresholds_match_documentation(self):
        """
        Verifica che i threshold siano allineati con la documentazione
        e le soglie scientifiche per impatto sul calcio.
        """
        from src.ingestion.weather_provider import (
            WIND_HIGH_THRESHOLD,
            RAIN_HEAVY_THRESHOLD,
            SNOW_THRESHOLD
        )
        
        # V4.6: Threshold aggiornati
        assert WIND_HIGH_THRESHOLD == 40.0, "Wind threshold should be 40 km/h"
        assert RAIN_HEAVY_THRESHOLD == 5.0, "Rain threshold should be 5 mm/h"
        assert SNOW_THRESHOLD == 0.0, "Any snow should trigger alert"
    
    def test_analyze_weather_returns_correct_format(self):
        """
        Verifica che analyze_weather_impact restituisca il formato
        atteso da main.py per l'integrazione.
        """
        from src.ingestion.weather_provider import analyze_weather_impact
        
        # Simula condizioni meteo avverse
        weather_data = {
            "wind_kmh": 45,
            "precipitation_mm": 6,
            "snowfall_cm": 0,
            "temperature_c": 8
        }
        
        result = analyze_weather_impact(weather_data)
        
        assert result is not None
        
        # Verifica campi richiesti da main.py
        assert "status" in result
        assert "summary" in result
        assert "conditions" in result
        assert "betting_advice" in result
        
        # Verifica formato summary (usato in official_data)
        assert "WEATHER ALERT" in result["summary"]


class TestInjuryImpactIntegration:
    """Test integrazione Injury Impact Engine nel flusso analyzer."""
    
    def test_analyze_match_injuries_with_snippet_data_format(self):
        """
        Verifica che analyze_match_injuries funzioni con il formato
        di snippet_data passato da main.py.
        """
        from src.analysis.injury_impact_engine import analyze_match_injuries
        
        # Simula home_context come passato in snippet_data
        home_context = {
            "injuries": [
                {"name": "Osimhen", "reason": "Hamstring"},
                {"name": "Mertens", "reason": "Knee"}
            ],
            "squad": None  # Spesso non disponibile
        }
        
        away_context = {
            "injuries": [
                {"name": "Backup Player", "reason": "Illness"}
            ],
            "squad": None
        }
        
        result = analyze_match_injuries(
            home_team="Napoli",
            away_team="Roma",
            home_context=home_context,
            away_context=away_context
        )
        
        assert result is not None
        assert result.home_impact is not None
        assert result.away_impact is not None
        
        # Home ha più infortuni
        assert result.home_impact.total_impact_score > result.away_impact.total_impact_score
        
        # Differential dovrebbe essere positivo (home più colpita)
        assert result.differential > 0
    
    def test_injury_impact_with_empty_injuries(self):
        """
        Verifica gestione quando non ci sono infortuni.
        """
        from src.analysis.injury_impact_engine import analyze_match_injuries
        
        home_context = {"injuries": []}
        away_context = {"injuries": []}
        
        result = analyze_match_injuries(
            home_team="Team A",
            away_team="Team B",
            home_context=home_context,
            away_context=away_context
        )
        
        assert result is not None
        assert result.differential == 0.0
        assert result.score_adjustment == 0.0


class TestEndToEndDataFlow:
    """Test flusso dati completo dalla raccolta all'analisi."""
    
    def test_math_context_format_for_ai(self):
        """
        Verifica che format_math_context produca output
        utilizzabile dal prompt AI.
        """
        from src.analysis.math_engine import MathPredictor, format_math_context
        
        predictor = MathPredictor(league_key="soccer_italy_serie_a")
        
        analysis = predictor.analyze_match(
            home_scored=1.5,
            home_conceded=1.0,
            away_scored=1.2,
            away_conceded=1.3,
            home_odd=1.80,
            draw_odd=3.50,
            away_odd=4.50
        )
        
        context = format_math_context(analysis, "home")
        
        # Verifica che contenga le informazioni chiave
        assert "MATH MODEL" in context
        assert "Expected Goals" in context
        assert "Home Win" in context
        assert "%" in context  # Percentuali presenti
    
    def test_all_engines_handle_none_gracefully(self):
        """
        Verifica che tutti gli engine gestiscano None senza crash.
        Questo è critico per la stabilità in produzione.
        """
        from src.analysis.math_engine import MathPredictor, calculate_btts_trend
        from src.analysis.fatigue_engine import (
            get_squad_depth_score,
            calculate_fatigue_index,
            analyze_team_fatigue
        )
        from src.analysis.injury_impact_engine import (
            estimate_player_role,
            analyze_match_injuries
        )
        from src.ingestion.weather_provider import (
            validate_coordinates,
            analyze_weather_impact
        )
        
        # Math Engine
        assert calculate_btts_trend(None) == {
            "btts_rate": 0.0, "btts_hits": 0, 
            "total_games": 0, "trend_signal": "Unknown"
        }
        
        # Fatigue Engine
        assert get_squad_depth_score(None) == 1.0
        fatigue, matches = calculate_fatigue_index(None, datetime.now(timezone.utc))
        assert fatigue == 0.0 and matches == 0
        
        # Injury Engine
        from src.analysis.injury_impact_engine import PlayerRole
        assert estimate_player_role(None, 0, 0, 0) == PlayerRole.BACKUP
        
        # Weather Provider
        assert validate_coordinates(None, None) == False
        assert analyze_weather_impact(None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
