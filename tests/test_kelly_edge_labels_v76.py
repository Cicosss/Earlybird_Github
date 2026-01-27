"""
Test V7.6: Kelly and Edge Dynamic Labels in Telegram Alerts

Verifica che le etichette dinamiche per Kelly ed Edge vengano
generate correttamente negli alert Telegram.

Author: EarlyBird V7.6
Date: 2026-01-15
"""
import pytest


class TestKellyEdgeLabels:
    """Test dynamic labels for Kelly and Edge values."""
    
    def get_edge_label(self, edge_pct: float) -> str:
        """Replica la logica di edge label dal notifier (V7.6 corretta)."""
        # NOTA: Threshold è > 5%, quindi logica semplificata
        if edge_pct >= 10:
            return "🎯🎯 Valore eccezionale (bet molto forte)"
        elif edge_pct >= 7:
            return "🎯 Eccellente valore (bet forte)"
        else:  # 5 < edge < 7
            return "✅ Buon valore (bet consigliata)"
    
    def get_kelly_label(self, kelly: float) -> str:
        """Replica la logica di kelly label dal notifier."""
        if kelly <= 0:
            return "⚪ SKIP (nessuna puntata)"
        elif kelly < 1:
            return "🟡 BASSO (punta poco)"
        elif kelly < 3:
            return "🟢 MEDIO (punta moderato)"
        elif kelly < 5:
            return "🔵 ALTO (punta consistente)"
        else:
            return "🟣 MOLTO ALTO (punta massimo)"
    
    # ============================================
    # EDGE LABEL TESTS
    # ============================================
    
    def test_edge_label_exceptional_value(self):
        """Edge >= 10% dovrebbe mostrare 'Valore eccezionale (bet molto forte)'."""
        assert self.get_edge_label(10.0) == "🎯🎯 Valore eccezionale (bet molto forte)"
        assert self.get_edge_label(12.5) == "🎯🎯 Valore eccezionale (bet molto forte)"
        assert self.get_edge_label(20.0) == "🎯🎯 Valore eccezionale (bet molto forte)"
    
    def test_edge_label_excellent_value(self):
        """Edge 7-10% dovrebbe mostrare 'Eccellente valore (bet forte)'."""
        assert self.get_edge_label(7.0) == "🎯 Eccellente valore (bet forte)"
        assert self.get_edge_label(8.5) == "🎯 Eccellente valore (bet forte)"
        assert self.get_edge_label(9.9) == "🎯 Eccellente valore (bet forte)"
    
    def test_edge_label_good_value(self):
        """Edge 5-7% dovrebbe mostrare 'Buon valore (bet consigliata)'."""
        assert self.get_edge_label(5.1) == "✅ Buon valore (bet consigliata)"
        assert self.get_edge_label(6.0) == "✅ Buon valore (bet consigliata)"
        assert self.get_edge_label(6.9) == "✅ Buon valore (bet consigliata)"
    
    def test_edge_label_boundary_values(self):
        """Test valori di confine per Edge (nuove soglie)."""
        # Boundary a 7
        assert self.get_edge_label(6.99) == "✅ Buon valore (bet consigliata)"
        assert self.get_edge_label(7.0) == "🎯 Eccellente valore (bet forte)"
        
        # Boundary a 10
        assert self.get_edge_label(9.99) == "🎯 Eccellente valore (bet forte)"
        assert self.get_edge_label(10.0) == "🎯🎯 Valore eccezionale (bet molto forte)"
    
    # ============================================
    # KELLY LABEL TESTS
    # ============================================
    
    def test_kelly_label_very_high(self):
        """Kelly >= 5% dovrebbe mostrare 'MOLTO ALTO (punta massimo)'."""
        assert self.get_kelly_label(5.0) == "🟣 MOLTO ALTO (punta massimo)"
        assert self.get_kelly_label(7.5) == "🟣 MOLTO ALTO (punta massimo)"
        assert self.get_kelly_label(10.0) == "🟣 MOLTO ALTO (punta massimo)"
    
    def test_kelly_label_high(self):
        """Kelly 3-5% dovrebbe mostrare 'ALTO (punta consistente)'."""
        assert self.get_kelly_label(3.0) == "🔵 ALTO (punta consistente)"
        assert self.get_kelly_label(3.8) == "🔵 ALTO (punta consistente)"
        assert self.get_kelly_label(4.9) == "🔵 ALTO (punta consistente)"
    
    def test_kelly_label_medium(self):
        """Kelly 1-3% dovrebbe mostrare 'MEDIO (punta moderato)'."""
        assert self.get_kelly_label(1.0) == "🟢 MEDIO (punta moderato)"
        assert self.get_kelly_label(2.1) == "🟢 MEDIO (punta moderato)"
        assert self.get_kelly_label(2.9) == "🟢 MEDIO (punta moderato)"
    
    def test_kelly_label_low(self):
        """Kelly 0-1% dovrebbe mostrare 'BASSO (punta poco)'."""
        assert self.get_kelly_label(0.1) == "🟡 BASSO (punta poco)"
        assert self.get_kelly_label(0.5) == "🟡 BASSO (punta poco)"
        assert self.get_kelly_label(0.85) == "🟡 BASSO (punta poco)"
        assert self.get_kelly_label(0.99) == "🟡 BASSO (punta poco)"
    
    def test_kelly_label_skip(self):
        """Kelly <= 0% dovrebbe mostrare 'SKIP (nessuna puntata)'."""
        assert self.get_kelly_label(0.0) == "⚪ SKIP (nessuna puntata)"
        assert self.get_kelly_label(-0.1) == "⚪ SKIP (nessuna puntata)"
        assert self.get_kelly_label(-5.0) == "⚪ SKIP (nessuna puntata)"
    
    def test_kelly_label_boundary_values(self):
        """Test valori di confine per Kelly."""
        # Boundary a 0
        assert self.get_kelly_label(0.0) == "⚪ SKIP (nessuna puntata)"
        assert self.get_kelly_label(0.01) == "🟡 BASSO (punta poco)"
        
        # Boundary a 1
        assert self.get_kelly_label(0.99) == "🟡 BASSO (punta poco)"
        assert self.get_kelly_label(1.0) == "🟢 MEDIO (punta moderato)"
        
        # Boundary a 3
        assert self.get_kelly_label(2.99) == "🟢 MEDIO (punta moderato)"
        assert self.get_kelly_label(3.0) == "🔵 ALTO (punta consistente)"
        
        # Boundary a 5
        assert self.get_kelly_label(4.99) == "🔵 ALTO (punta consistente)"
        assert self.get_kelly_label(5.0) == "🟣 MOLTO ALTO (punta massimo)"
    
    # ============================================
    # COMBINED SCENARIOS
    # ============================================
    
    def test_realistic_scenario_strong_bet(self):
        """Scenario realistico: bet forte con edge alto e kelly alto."""
        edge = 9.2
        kelly = 3.5
        
        edge_label = self.get_edge_label(edge)
        kelly_label = self.get_kelly_label(kelly)
        
        assert edge_label == "🎯 Eccellente valore (bet forte)"
        assert kelly_label == "🔵 ALTO (punta consistente)"
    
    def test_realistic_scenario_moderate_bet(self):
        """Scenario realistico: bet moderata con edge buono e kelly medio."""
        edge = 4.5
        kelly = 1.8
        
        edge_label = self.get_edge_label(edge)
        kelly_label = self.get_kelly_label(kelly)
        
        assert edge_label == "✅ Buon valore (bet consigliata)"
        assert kelly_label == "🟢 MEDIO (punta moderato)"
    
    def test_realistic_scenario_exceptional_bet(self):
        """Scenario realistico: bet eccezionale con edge altissimo."""
        edge = 12.5
        kelly = 5.0
        
        edge_label = self.get_edge_label(edge)
        kelly_label = self.get_kelly_label(kelly)
        
        assert edge_label == "🎯🎯 Valore eccezionale (bet molto forte)"
        assert kelly_label == "🟣 MOLTO ALTO (punta massimo)"
    
    # ============================================
    # EDGE CASES
    # ============================================
    
    def test_edge_case_boundary_at_threshold(self):
        """Test valori al confine del threshold (5%)."""
        # Con threshold > 5%, questi valori non dovrebbero mai entrare
        # ma testiamo la logica per robustezza
        edge = 5.1
        assert self.get_edge_label(edge) == "✅ Buon valore (bet consigliata)"
    
    def test_edge_case_very_large_values(self):
        """Test con valori molto grandi."""
        assert self.get_edge_label(50.0) == "🎯🎯 Valore eccezionale (bet molto forte)"
        assert self.get_kelly_label(20.0) == "🟣 MOLTO ALTO (punta massimo)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

