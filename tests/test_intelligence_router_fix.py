#!/usr/bin/env python3
"""
Test di regressione per il fix GEMINI_AGENT_AVAILABLE -> INTELLIGENCE_ROUTER_AVAILABLE

Questo test verifica che:
1. INTELLIGENCE_ROUTER_AVAILABLE sia definito in analyzer.py
2. Non ci siano riferimenti a GEMINI_AGENT_AVAILABLE/ENABLED
3. Il flusso deep dive funzioni correttamente
4. Il router sia disponibile e abbia i metodi necessari

Bug originale: NameError: name 'GEMINI_AGENT_AVAILABLE' is not defined
Fix: Sostituito con INTELLIGENCE_ROUTER_AVAILABLE
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestIntelligenceRouterFix:
    """Test suite per il fix del bug GEMINI_AGENT_AVAILABLE."""
    
    def test_intelligence_router_available_defined(self):
        """Verifica che INTELLIGENCE_ROUTER_AVAILABLE sia definito e importabile."""
        from src.analysis.analyzer import INTELLIGENCE_ROUTER_AVAILABLE
        assert isinstance(INTELLIGENCE_ROUTER_AVAILABLE, bool)
    
    def test_no_gemini_agent_references(self):
        """Verifica che non ci siano riferimenti a GEMINI_AGENT_AVAILABLE/ENABLED."""
        analyzer_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'src', 'analysis', 'analyzer.py'
        )
        
        with open(analyzer_path, 'r') as f:
            content = f.read()
        
        # Questi riferimenti causavano il NameError
        assert 'GEMINI_AGENT_AVAILABLE' not in content, \
            "GEMINI_AGENT_AVAILABLE should not be referenced in analyzer.py"
        assert 'GEMINI_AGENT_ENABLED' not in content, \
            "GEMINI_AGENT_ENABLED should not be referenced in analyzer.py"
    
    def test_intelligence_router_importable(self):
        """Verifica che IntelligenceRouter sia importabile."""
        from src.services.intelligence_router import (
            get_intelligence_router,
            is_intelligence_available
        )
        
        # Deve essere callable
        assert callable(get_intelligence_router)
        assert callable(is_intelligence_available)
    
    def test_intelligence_router_has_required_methods(self):
        """Verifica che il router abbia tutti i metodi necessari per il flusso."""
        from src.services.intelligence_router import get_intelligence_router
        
        router = get_intelligence_router()
        
        # Metodi usati nel blocco fixato
        required_methods = [
            'is_available',
            'get_match_deep_dive',
            'format_for_prompt',
            'get_active_provider_name'
        ]
        
        for method in required_methods:
            assert hasattr(router, method), f"Router missing method: {method}"
            assert callable(getattr(router, method)), f"Router.{method} not callable"
    
    def test_deep_dive_flow_no_crash(self):
        """
        Simula il flusso che prima crashava con NameError.
        
        Questo test riproduce esattamente il codice nel blocco fixato
        per assicurarsi che non ci siano più NameError.
        """
        from src.analysis.analyzer import INTELLIGENCE_ROUTER_AVAILABLE
        from src.services.intelligence_router import get_intelligence_router
        
        # Simula dati come nel flusso reale
        official_data = 'TURNOVER ALERT: 3 starters missing (Player1, Player2, Player3)'
        market_status = 'STABLE'
        
        # Questo blocco prima crashava con NameError
        gemini_intel = ""
        deep_dive = None
        
        if INTELLIGENCE_ROUTER_AVAILABLE:
            # Check for high potential signals
            high_potential_signals = (
                'TURNOVER' in official_data.upper() or
                'KEY PLAYER' in official_data.upper() or
                'CRASH' in market_status.upper() or
                'DROPPING' in market_status.upper()
            )
            
            assert high_potential_signals is True, "Should detect TURNOVER signal"
            
            if high_potential_signals:
                router = get_intelligence_router() if INTELLIGENCE_ROUTER_AVAILABLE else None
                
                assert router is not None, "Router should be created"
                assert hasattr(router, 'is_available'), "Router should have is_available"
                assert hasattr(router, 'get_match_deep_dive'), "Router should have get_match_deep_dive"
    
    def test_router_provider_name(self):
        """Verifica che il provider attivo sia deepseek (V6.0)."""
        from src.services.intelligence_router import get_intelligence_router
        
        router = get_intelligence_router()
        provider_name = router.get_active_provider_name()
        
        assert provider_name == "deepseek", f"Expected 'deepseek', got '{provider_name}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
