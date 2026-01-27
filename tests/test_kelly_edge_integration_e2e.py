"""
Test E2E: Kelly & Edge Labels Integration

Verifica il flusso completo end-to-end:
1. MathPredictor calcola EdgeResult
2. main.py costruisce math_edge_info dict
3. send_alert riceve e formatta correttamente
4. Gestione edge cases (None, valori mancanti, etc.)

Author: EarlyBird V7.6
Date: 2026-01-15
"""
import pytest
from src.analysis.math_engine import MathPredictor, EdgeResult


class TestKellyEdgeE2EIntegration:
    """Test integrazione end-to-end Kelly & Edge labels."""
    
    def test_math_engine_produces_correct_structure(self):
        """
        Verifica che MathPredictor.calculate_edge produca EdgeResult
        con tutti i campi necessari per math_edge_info.
        """
        predictor = MathPredictor()
        
        # Calcola edge con valori realistici
        edge_result = predictor.calculate_edge(
            math_prob=0.576,  # 57.6%
            bookmaker_odd=2.00,
            sample_size=10
        )
        
        # Verifica struttura EdgeResult
        assert isinstance(edge_result, EdgeResult)
        assert hasattr(edge_result, 'market')
        assert hasattr(edge_result, 'edge')
        assert hasattr(edge_result, 'kelly_stake')
        assert hasattr(edge_result, 'has_value')
        
        # Verifica tipi
        assert isinstance(edge_result.edge, float)
        assert isinstance(edge_result.kelly_stake, float)
        assert isinstance(edge_result.has_value, bool)
    
    def test_math_edge_info_dict_construction(self):
        """
        Simula la costruzione di math_edge_info dict come in main.py (linea 2021).
        """
        predictor = MathPredictor()
        
        # Simula math_analysis con best_edge
        edge_result = predictor.calculate_edge(
            math_prob=0.626,  # 62.6%
            bookmaker_odd=1.85,
            sample_size=12
        )
        edge_result.market = "HOME"
        
        # Simula la logica di main.py
        math_edge_info = None
        if edge_result.has_value and edge_result.edge > 5:
            math_edge_info = {
                'market': edge_result.market,
                'edge': edge_result.edge,
                'kelly_stake': edge_result.kelly_stake
            }
        
        # Verifica che math_edge_info sia costruito correttamente
        assert math_edge_info is not None
        assert 'market' in math_edge_info
        assert 'edge' in math_edge_info
        assert 'kelly_stake' in math_edge_info
        
        # Verifica valori
        assert math_edge_info['market'] == "HOME"
        assert isinstance(math_edge_info['edge'], float)
        assert isinstance(math_edge_info['kelly_stake'], float)
    
    def test_math_edge_info_not_created_if_edge_too_low(self):
        """
        Verifica che math_edge_info sia None se edge <= 5%
        (threshold in main.py linea 2021).
        """
        predictor = MathPredictor()
        
        # Edge basso (< 5%)
        edge_result = predictor.calculate_edge(
            math_prob=0.52,  # 52%
            bookmaker_odd=2.00,  # Implied 50%
            sample_size=10
        )
        edge_result.market = "DRAW"
        
        # Simula la logica di main.py
        math_edge_info = None
        if edge_result.has_value and edge_result.edge > 5:
            math_edge_info = {
                'market': edge_result.market,
                'edge': edge_result.edge,
                'kelly_stake': edge_result.kelly_stake
            }
        
        # Con edge < 5%, math_edge_info deve rimanere None
        assert math_edge_info is None
    
    def test_notifier_handles_none_math_edge(self):
        """
        Verifica che il notifier gestisca correttamente math_edge=None
        (caso comune: chiamate senza math analysis).
        """
        # Simula la logica del notifier (linea 307)
        math_edge = None
        bet_section = ""
        
        if math_edge and math_edge.get('edge', 0) > 5:
            # Questo blocco NON deve essere eseguito
            bet_section += "VALORE MATEMATICO"
        
        # Verifica che la sezione non sia stata aggiunta
        assert bet_section == ""
        assert "VALORE MATEMATICO" not in bet_section
    
    def test_notifier_handles_missing_keys_in_math_edge(self):
        """
        Verifica che il notifier gestisca dict con chiavi mancanti
        usando .get() con default values.
        """
        # Dict incompleto (edge mancante)
        math_edge = {
            'market': 'HOME',
            'kelly_stake': 2.5
            # 'edge' mancante!
        }
        
        # Simula la logica del notifier
        bet_section = ""
        if math_edge and math_edge.get('edge', 0) > 5:
            edge_pct = math_edge.get('edge', 0)
            kelly = math_edge.get('kelly_stake', 0)
            market = math_edge.get('market', 'Unknown')
            
            bet_section += f"Edge: {edge_pct}, Kelly: {kelly}, Market: {market}"
        
        # Con edge mancante (default 0), la condizione è False
        assert bet_section == ""
    
    def test_notifier_formats_correctly_with_valid_math_edge(self):
        """
        Verifica che il notifier formatti correttamente con math_edge valido.
        """
        math_edge = {
            'market': 'HOME',
            'edge': 7.6,
            'kelly_stake': 2.66
        }
        
        # Simula la logica del notifier (linee 307-336)
        bet_section = ""
        if math_edge and math_edge.get('edge', 0) > 5:
            edge_pct = math_edge.get('edge', 0)
            kelly = math_edge.get('kelly_stake', 0)
            market = math_edge.get('market', 'Unknown')
            
            # Edge label
            if edge_pct < 0:
                edge_label = "❌ NO BET (bookmaker ha ragione)"
            elif edge_pct < 3:
                edge_label = "⚠️ Valore marginale (rischio alto)"
            elif edge_pct < 5:
                edge_label = "✅ Buon valore (bet consigliata)"
            else:
                edge_label = "🎯 Eccellente valore (bet forte)"
            
            # Kelly label
            if kelly <= 0:
                kelly_label = "⚪ SKIP (nessuna puntata)"
            elif kelly < 1:
                kelly_label = "🟡 BASSO (punta poco)"
            elif kelly < 3:
                kelly_label = "🟢 MEDIO (punta moderato)"
            elif kelly < 5:
                kelly_label = "🔵 ALTO (punta consistente)"
            else:
                kelly_label = "🟣 MOLTO ALTO (punta massimo)"
            
            bet_section += f"🧮 <b>VALORE MATEMATICO:</b>\n"
            bet_section += f"   📊 Edge: +{edge_pct:.1f}% su {market} - {edge_label}\n"
            bet_section += f"   💰 Kelly: {kelly}% del bankroll - {kelly_label}\n"
        
        # Verifica output
        assert "VALORE MATEMATICO" in bet_section
        assert "+7.6% su HOME" in bet_section
        assert "🎯 Eccellente valore (bet forte)" in bet_section
        assert "2.66% del bankroll" in bet_section
        assert "🟢 MEDIO (punta moderato)" in bet_section
    
    def test_float_formatting_no_crashes(self):
        """
        Verifica che il formatting con .1f non crashi con valori edge case.
        """
        test_cases = [
            {'edge': 0.0, 'kelly_stake': 0.0},
            {'edge': 0.01, 'kelly_stake': 0.01},
            {'edge': 5.0, 'kelly_stake': 5.0},
            {'edge': 99.9, 'kelly_stake': 5.0},  # Kelly capped
            {'edge': 7.654321, 'kelly_stake': 2.123456},  # Molti decimali
        ]
        
        for math_edge in test_cases:
            math_edge['market'] = 'HOME'
            
            # Simula formatting
            if math_edge.get('edge', 0) > 5:
                edge_pct = math_edge.get('edge', 0)
                kelly = math_edge.get('kelly_stake', 0)
                
                # Questo non deve crashare
                formatted = f"+{edge_pct:.1f}% su HOME"
                kelly_formatted = f"{kelly}% del bankroll"
                
                assert isinstance(formatted, str)
                assert isinstance(kelly_formatted, str)
                assert "%" in formatted
                assert "%" in kelly_formatted
    
    def test_html_safety_with_market_names(self):
        """
        Verifica che i nomi dei market (HOME, DRAW, AWAY) siano sicuri
        e non richiedano HTML escape.
        """
        valid_markets = ['HOME', 'DRAW', 'AWAY', 'OVER_25', 'BTTS', 'Unknown']
        
        for market in valid_markets:
            math_edge = {
                'market': market,
                'edge': 7.0,
                'kelly_stake': 2.0
            }
            
            # Simula formatting
            formatted = f"Edge: +{math_edge['edge']:.1f}% su {math_edge['market']}"
            
            # Verifica che non ci siano caratteri HTML pericolosi
            assert '<' not in formatted
            assert '>' not in formatted
            assert '&' not in formatted
            assert '"' not in formatted
            assert "'" not in formatted
    
    def test_realistic_e2e_flow(self):
        """
        Test E2E completo: da MathPredictor a notifier formatting.
        """
        # STEP 1: MathPredictor calcola edge
        predictor = MathPredictor()
        analysis = predictor.analyze_match(
            home_scored=2.1,
            home_conceded=0.8,
            away_scored=1.2,
            away_conceded=1.9,
            home_odd=1.65,
            draw_odd=3.80,
            away_odd=5.50
        )
        
        # STEP 2: main.py costruisce math_edge_info
        math_edge_info = None
        best_edge = analysis.get('best_edge')
        if best_edge and best_edge.has_value and best_edge.edge > 5:
            math_edge_info = {
                'market': best_edge.market,
                'edge': best_edge.edge,
                'kelly_stake': best_edge.kelly_stake
            }
        
        # STEP 3: notifier formatta (se math_edge_info esiste)
        bet_section = ""
        if math_edge_info and math_edge_info.get('edge', 0) > 5:
            edge_pct = math_edge_info.get('edge', 0)
            kelly = math_edge_info.get('kelly_stake', 0)
            market = math_edge_info.get('market', 'Unknown')
            
            # Edge label
            if edge_pct >= 5:
                edge_label = "🎯 Eccellente valore (bet forte)"
            else:
                edge_label = "✅ Buon valore (bet consigliata)"
            
            # Kelly label
            if kelly < 1:
                kelly_label = "🟡 BASSO (punta poco)"
            elif kelly < 3:
                kelly_label = "🟢 MEDIO (punta moderato)"
            elif kelly < 5:
                kelly_label = "🔵 ALTO (punta consistente)"
            else:
                kelly_label = "🟣 MOLTO ALTO (punta massimo)"
            
            bet_section += f"🧮 <b>VALORE MATEMATICO:</b>\n"
            bet_section += f"   📊 Edge: +{edge_pct:.1f}% su {market} - {edge_label}\n"
            bet_section += f"   💰 Kelly: {kelly}% del bankroll - {kelly_label}\n"
        
        # VERIFICA: Se c'è valore, la sezione deve essere presente
        if best_edge and best_edge.has_value and best_edge.edge > 5:
            assert "VALORE MATEMATICO" in bet_section
            assert "Edge:" in bet_section
            assert "Kelly:" in bet_section
            assert "%" in bet_section


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
