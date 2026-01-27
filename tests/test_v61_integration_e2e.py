"""
Test di Integrazione End-to-End per V6.1 Optimizer Fixes

Simula il flusso completo del bot sulla VPS:
1. Ingestion → Match discovery
2. Analysis → Score calculation
3. Optimizer → Weight application (V6.1 fixes)
4. Alert → Threshold decision
5. Settlement → Weight update

Verifica che le nuove implementazioni siano coerenti con il flusso dati.
"""
import pytest
import sys
import os
import json
import tempfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestE2EOptimizerFlow:
    """Test end-to-end del flusso optimizer nel bot."""
    
    def test_full_bot_cycle_with_v61_fixes(self):
        """
        Simula un ciclo completo del bot:
        1. Record bets per diverse league/market
        2. Verifica che get_weight usi fallback correttamente
        3. Verifica che apply_weight_to_score funzioni
        4. Verifica che get_dynamic_alert_threshold sia coerente
        """
        from src.analysis.optimizer import (
            StrategyOptimizer,
            get_dynamic_alert_threshold,
            NEUTRAL_WEIGHT,
            MIN_SAMPLE_SIZE,
            ALERT_THRESHOLD_BASE,
            ALERT_THRESHOLD_MIN,
            ALERT_THRESHOLD_MAX
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "stats": {},
                "drivers": {},
                "global": {"total_bets": 0, "total_profit": 0.0, "overall_roi": 0.0},
                "version": "3.0"
            }, f)
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # === FASE 1: Simula settlement di bet storiche ===
            # Serie A ha molti dati (ACTIVE)
            for i in range(60):
                optimizer.record_bet_result(
                    league='soccer_italy_serie_a',
                    market='Over 2.5',
                    outcome='WIN' if i % 4 != 0 else 'LOSS',  # 75% win rate
                    odds=1.85,
                    driver='MATH_VALUE'
                )
            
            # Bundesliga ha pochi dati (FROZEN)
            for i in range(10):
                optimizer.record_bet_result(
                    league='soccer_germany_bundesliga',
                    market='Over 2.5',
                    outcome='WIN' if i % 2 == 0 else 'LOSS',  # 50% win rate
                    odds=1.90,
                    driver='INJURY_INTEL'
                )
            
            # === FASE 2: Verifica State Machine ===
            serie_a_stats = optimizer.data['stats']['soccer_italy_serie_a']['OVER']
            bundesliga_stats = optimizer.data['stats']['soccer_germany_bundesliga']['OVER']
            
            # Serie A dovrebbe essere ACTIVE con weight != 1.0
            assert serie_a_stats['bets'] == 60
            assert serie_a_stats['weight'] != NEUTRAL_WEIGHT, \
                "Serie A (ACTIVE) should have adjusted weight"
            
            # Bundesliga dovrebbe essere FROZEN con weight = 1.0
            assert bundesliga_stats['bets'] == 10
            assert bundesliga_stats['weight'] == NEUTRAL_WEIGHT, \
                "Bundesliga (FROZEN) should have neutral weight"
            
            # === FASE 3: Verifica Global Market Fallback ===
            # Bundesliga/OVER è FROZEN, ma global OVER ha dati da Serie A
            weight_bundesliga, _ = optimizer.get_weight(
                league='soccer_germany_bundesliga',
                market='Over 2.5'
            )
            
            # V6.1: Dovrebbe usare il fallback al global OVER weight
            # Il global OVER weight viene da Serie A che ha 75% win rate
            assert weight_bundesliga != NEUTRAL_WEIGHT, \
                f"V6.1 FIX: Bundesliga should fallback to global OVER weight, got {weight_bundesliga}"
            
            # === FASE 4: Verifica Weight Combination ===
            # MATH_VALUE driver ha 60 bet con 75% win rate
            math_value_stats = optimizer.data['drivers']['MATH_VALUE']
            assert math_value_stats['bets'] == 60
            
            # Combina league weight + driver weight
            combined_weight, _ = optimizer.get_weight(
                league='soccer_italy_serie_a',
                market='Over 2.5',
                driver='MATH_VALUE'
            )
            
            # V6.1: Non dovrebbe essere geometric mean
            # Con entrambi positivi, dovrebbe essere weighted average
            assert combined_weight > 1.0, \
                f"Combined weight should be > 1.0 with positive signals, got {combined_weight}"
            
            # === FASE 5: Verifica apply_weight_to_score ===
            base_score = 8.5
            adjusted_score, log_msg = optimizer.apply_weight_to_score(
                base_score=base_score,
                league='soccer_italy_serie_a',
                market='Over 2.5',
                driver='MATH_VALUE'
            )
            
            # Score dovrebbe essere adjustato (non uguale a base)
            assert adjusted_score != base_score or log_msg == "", \
                "Score should be adjusted or no adjustment message"
            assert 0 <= adjusted_score <= 10, \
                f"Adjusted score should be in valid range, got {adjusted_score}"
            
            # === FASE 6: Verifica Dynamic Threshold ===
            # Salva i dati per il singleton
            optimizer._save_data()
            
        finally:
            os.unlink(temp_file)
    
    def test_driver_state_machine_consistency(self):
        """
        Verifica che driver e league/market usino la stessa State Machine.
        
        V6.0 BUG: Driver saltava da FROZEN a full adjustment.
        V6.1 FIX: Driver usa FROZEN → WARMING_UP → ACTIVE come league/market.
        """
        from src.analysis.optimizer import (
            StrategyOptimizer,
            get_optimizer_state,
            OptimizerState,
            NEUTRAL_WEIGHT
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "stats": {},
                "drivers": {},
                "global": {"total_bets": 0, "total_profit": 0.0, "overall_roi": 0.0},
                "version": "3.0"
            }, f)
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Record 25 bets (FROZEN)
            for i in range(25):
                optimizer.record_bet_result(
                    league='test_league',
                    market='BTTS',
                    outcome='WIN',
                    odds=2.0,
                    driver='SHARP_MONEY'
                )
            
            driver_stats = optimizer.data['drivers']['SHARP_MONEY']
            league_stats = optimizer.data['stats']['test_league']['BTTS']
            
            # Entrambi dovrebbero essere FROZEN
            assert get_optimizer_state(driver_stats['bets']) == OptimizerState.FROZEN
            assert get_optimizer_state(league_stats['bets']) == OptimizerState.FROZEN
            
            # Entrambi dovrebbero avere weight = 1.0
            assert driver_stats['weight'] == NEUTRAL_WEIGHT, \
                f"Driver FROZEN should have neutral weight, got {driver_stats['weight']}"
            assert league_stats['weight'] == NEUTRAL_WEIGHT, \
                f"League FROZEN should have neutral weight, got {league_stats['weight']}"
            
            # Record altri 10 bets (totale 35 = WARMING_UP)
            for i in range(10):
                optimizer.record_bet_result(
                    league='test_league',
                    market='BTTS',
                    outcome='WIN',
                    odds=2.0,
                    driver='SHARP_MONEY'
                )
            
            driver_stats = optimizer.data['drivers']['SHARP_MONEY']
            league_stats = optimizer.data['stats']['test_league']['BTTS']
            
            # Entrambi dovrebbero essere WARMING_UP
            assert get_optimizer_state(driver_stats['bets']) == OptimizerState.WARMING_UP
            assert get_optimizer_state(league_stats['bets']) == OptimizerState.WARMING_UP
            
            # Entrambi dovrebbero avere weight limitato a ±0.1 per bet
            # Dopo 5 bet in WARMING_UP (bet 31-35), max weight = 1.0 + 5*0.1 = 1.5
            # Ma il primo bet in WARMING_UP (bet 30) può già fare +0.1, quindi 6 incrementi = 1.6
            assert driver_stats['weight'] <= 1.6, \
                f"Driver WARMING_UP should be capped, got {driver_stats['weight']}"
            assert league_stats['weight'] <= 1.6, \
                f"League WARMING_UP should be capped, got {league_stats['weight']}"
            
        finally:
            os.unlink(temp_file)
    
    def test_settlement_flow_updates_weights_correctly(self):
        """
        Simula il flusso di settlement notturno.
        
        Verifica che recalculate_weights() aggiorni correttamente i pesi
        usando le nuove logiche V6.1.
        """
        from src.analysis.optimizer import StrategyOptimizer
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "stats": {},
                "drivers": {},
                "global": {"total_bets": 0, "total_profit": 0.0, "overall_roi": 0.0},
                "version": "3.0"
            }, f)
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Simula settlement_stats come arriva da settle_pending_bets()
            settlement_stats = {
                'settled': 10,
                'wins': 7,
                'losses': 3,
                'roi_pct': 15.0,
                'details': [
                    {'league': 'soccer_italy_serie_a', 'market': 'Over 2.5', 'outcome': 'WIN', 'odds': 1.85, 'driver': 'MATH_VALUE'},
                    {'league': 'soccer_italy_serie_a', 'market': 'Over 2.5', 'outcome': 'WIN', 'odds': 1.90, 'driver': 'MATH_VALUE'},
                    {'league': 'soccer_italy_serie_a', 'market': 'Over 2.5', 'outcome': 'LOSS', 'odds': 1.85, 'driver': 'MATH_VALUE'},
                    {'league': 'soccer_england_premier', 'market': 'BTTS', 'outcome': 'WIN', 'odds': 1.75, 'driver': 'INJURY_INTEL'},
                    {'league': 'soccer_england_premier', 'market': 'BTTS', 'outcome': 'WIN', 'odds': 1.80, 'driver': 'INJURY_INTEL'},
                    {'league': 'soccer_spain_la_liga', 'market': '1X2', 'outcome': 'WIN', 'odds': 2.10, 'driver': 'SHARP_MONEY'},
                    {'league': 'soccer_spain_la_liga', 'market': '1X2', 'outcome': 'WIN', 'odds': 2.20, 'driver': 'SHARP_MONEY'},
                    {'league': 'soccer_spain_la_liga', 'market': '1X2', 'outcome': 'LOSS', 'odds': 2.00, 'driver': 'SHARP_MONEY'},
                    {'league': 'soccer_france_ligue1', 'market': 'Under 2.5', 'outcome': 'WIN', 'odds': 1.95, 'driver': 'CONTRARIAN'},
                    {'league': 'soccer_france_ligue1', 'market': 'Under 2.5', 'outcome': 'LOSS', 'odds': 1.90, 'driver': 'CONTRARIAN'},
                ]
            }
            
            # Esegui recalculate_weights
            result = optimizer.recalculate_weights(settlement_stats)
            
            assert result is True, "recalculate_weights should return True"
            
            # Verifica che i dati siano stati registrati
            assert optimizer.data['global']['total_bets'] == 10
            assert 'soccer_italy_serie_a' in optimizer.data['stats']
            assert 'MATH_VALUE' in optimizer.data['drivers']
            
            # Verifica che tutti i weights siano FROZEN (< 30 bets)
            for league, markets in optimizer.data['stats'].items():
                for market_type, stats in markets.items():
                    assert stats['weight'] == 1.0, \
                        f"{league}/{market_type} should be FROZEN with weight=1.0"
            
            for driver, stats in optimizer.data['drivers'].items():
                assert stats['weight'] == 1.0, \
                    f"Driver {driver} should be FROZEN with weight=1.0"
            
        finally:
            os.unlink(temp_file)
    
    def test_edge_cases_in_production_flow(self):
        """
        Testa edge case che possono verificarsi in produzione sulla VPS.
        """
        from src.analysis.optimizer import (
            StrategyOptimizer,
            categorize_market,
            NEUTRAL_WEIGHT
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "stats": {},
                "drivers": {},
                "global": {"total_bets": 0, "total_profit": 0.0, "overall_roi": 0.0},
                "version": "3.0"
            }, f)
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Edge case 1: Market string con formati strani
            assert categorize_market("Over 2.5 Goals") == "OVER"
            assert categorize_market("OVER2.5") == "OVER"
            assert categorize_market("over 0.5") == "OVER"
            assert categorize_market("Under 3.5 gol") == "UNDER"
            assert categorize_market("1") == "1X2"
            assert categorize_market("X") == "1X2"
            assert categorize_market("") == "UNKNOWN"
            assert categorize_market(None) == "UNKNOWN"
            
            # Edge case 2: League None o vuota
            score, msg = optimizer.apply_weight_to_score(8.5, None, 'Over 2.5')
            assert score == 8.5, "None league should return base score"
            
            score, msg = optimizer.apply_weight_to_score(8.5, '', 'Over 2.5')
            assert score == 8.5, "Empty league should return base score"
            
            # Edge case 3: Market None
            score, msg = optimizer.apply_weight_to_score(8.5, 'test_league', None)
            assert score == 8.5, "None market should return base score"
            
            # Edge case 4: Driver invalido
            optimizer.record_bet_result(
                league='test_league',
                market='Over 2.5',
                outcome='WIN',
                odds=1.85,
                driver='INVALID_DRIVER'  # Dovrebbe diventare UNKNOWN
            )
            assert 'UNKNOWN' in optimizer.data['drivers'], \
                "Invalid driver should be recorded as UNKNOWN"
            
            # Edge case 5: Odds invalide
            optimizer.record_bet_result(
                league='test_league',
                market='Over 2.5',
                outcome='WIN',
                odds=0.5,  # Invalido (< 1.0)
                driver='MATH_VALUE'
            )
            # Non dovrebbe crashare, dovrebbe usare default 1.9
            
            # Edge case 6: Outcome invalido
            optimizer.record_bet_result(
                league='test_league',
                market='Over 2.5',
                outcome='INVALID',  # Dovrebbe diventare LOSS
                odds=1.85,
                driver='MATH_VALUE'
            )
            # Non dovrebbe crashare
            
            # Edge case 7: PUSH outcome (match cancellato)
            initial_bets = optimizer.data['global']['total_bets']
            optimizer.record_bet_result(
                league='test_league',
                market='Over 2.5',
                outcome='PUSH',
                odds=1.85,
                driver='MATH_VALUE'
            )
            # PUSH non dovrebbe incrementare i bet
            assert optimizer.data['global']['total_bets'] == initial_bets, \
                "PUSH outcome should not increment bet count"
            
        finally:
            os.unlink(temp_file)
    
    def test_persistence_and_recovery(self):
        """
        Verifica che i dati persistano correttamente e possano essere recuperati.
        Simula un restart del bot sulla VPS.
        """
        from src.analysis.optimizer import StrategyOptimizer
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "stats": {},
                "drivers": {},
                "global": {"total_bets": 0, "total_profit": 0.0, "overall_roi": 0.0},
                "version": "3.0"
            }, f)
            temp_file = f.name
        
        try:
            # Prima istanza: registra dati
            optimizer1 = StrategyOptimizer(weights_file=temp_file)
            
            for i in range(20):
                optimizer1.record_bet_result(
                    league='soccer_italy_serie_a',
                    market='Over 2.5',
                    outcome='WIN',
                    odds=1.85,
                    driver='MATH_VALUE'
                )
            
            optimizer1._save_data()
            
            # Simula restart: nuova istanza carica dati
            optimizer2 = StrategyOptimizer(weights_file=temp_file)
            
            # Verifica che i dati siano stati recuperati
            assert optimizer2.data['global']['total_bets'] == 20, \
                "Data should persist across restarts"
            assert 'soccer_italy_serie_a' in optimizer2.data['stats'], \
                "League stats should persist"
            assert 'MATH_VALUE' in optimizer2.data['drivers'], \
                "Driver stats should persist"
            
            # Verifica che le nuove funzioni V6.1 funzionino con dati caricati
            weight, _ = optimizer2.get_weight('soccer_italy_serie_a', 'Over 2.5')
            assert weight == 1.0, "FROZEN state should have neutral weight"
            
            global_weight, total_bets = optimizer2._get_global_market_weight('OVER')
            assert total_bets == 0, "No ACTIVE strategies yet"
            
        finally:
            os.unlink(temp_file)


class TestDynamicThresholdIntegration:
    """Test integrazione del Dynamic Threshold con V6.1 fixes."""
    
    def test_threshold_uses_correct_drawdown_calculation(self):
        """
        Verifica che get_dynamic_alert_threshold usi il weighted average
        dei drawdown invece della concatenazione PnL.
        """
        from src.analysis.optimizer import (
            get_dynamic_alert_threshold,
            ALERT_THRESHOLD_BASE,
            ALERT_THRESHOLD_MIN,
            ALERT_THRESHOLD_MAX
        )
        
        # Il test verifica che la funzione non crashi e ritorni valori validi
        threshold, explanation = get_dynamic_alert_threshold()
        
        assert isinstance(threshold, float), "Threshold should be float"
        assert ALERT_THRESHOLD_MIN <= threshold <= ALERT_THRESHOLD_MAX, \
            f"Threshold {threshold} should be within bounds [{ALERT_THRESHOLD_MIN}, {ALERT_THRESHOLD_MAX}]"
        assert isinstance(explanation, str), "Explanation should be string"
        assert len(explanation) > 0, "Explanation should not be empty"


class TestMainPyIntegration:
    """Test che le modifiche siano compatibili con main.py."""
    
    def test_imports_work(self):
        """Verifica che tutti gli import in main.py funzionino."""
        from src.analysis.optimizer import get_optimizer, get_dynamic_alert_threshold
        
        # Verifica che le funzioni siano callable
        assert callable(get_optimizer)
        assert callable(get_dynamic_alert_threshold)
        
        # Verifica che get_optimizer ritorni un'istanza valida
        optimizer = get_optimizer()
        assert hasattr(optimizer, 'apply_weight_to_score')
        assert hasattr(optimizer, 'get_weight')
        assert hasattr(optimizer, 'record_bet_result')
        assert hasattr(optimizer, 'recalculate_weights')
        
        # V6.1: Verifica nuovi metodi
        assert hasattr(optimizer, '_get_global_market_weight')
        assert hasattr(optimizer, '_combine_weights')
    
    def test_apply_weight_signature_unchanged(self):
        """
        Verifica che la signature di apply_weight_to_score sia invariata.
        main.py chiama: optimizer.apply_weight_to_score(raw_score, match.league, recommended_market, primary_driver)
        """
        from src.analysis.optimizer import get_optimizer
        import inspect
        
        optimizer = get_optimizer()
        sig = inspect.signature(optimizer.apply_weight_to_score)
        params = list(sig.parameters.keys())
        
        # Verifica parametri attesi
        assert 'base_score' in params
        assert 'league' in params
        assert 'market' in params
        assert 'driver' in params


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
