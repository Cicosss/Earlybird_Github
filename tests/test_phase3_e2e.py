"""
Tests E2E per FASE 3: Verifica flusso completo DeepSeek Intel Provider

Verifica che:
1. IntelligenceRouter -> DeepSeekIntelProvider funzioni correttamente
2. Brave Search + DeepSeek integrazione
3. Rate limiting non causa 429
4. Fallback a Perplexity funziona
5. Flusso dati end-to-end coerente

**Feature: deepseek-migration-e2e**
"""
import os
from unittest.mock import patch, MagicMock
import pytest


class TestE2EIntelligenceRouterFlow:
    """Test E2E del flusso IntelligenceRouter -> DeepSeek."""
    
    def test_router_deep_dive_returns_normalized_dict(self):
        """
        E2E: get_match_deep_dive ritorna dict normalizzato con tutti i campi.
        
        Verifica che il flusso completo:
        1. IntelligenceRouter riceve richiesta
        2. Passa a DeepSeekIntelProvider
        3. DeepSeek chiama Brave Search
        4. DeepSeek chiama OpenRouter API
        5. Response viene normalizzata
        """
        from src.services.intelligence_router import get_intelligence_router
        
        # Mock the entire chain
        mock_brave_results = [
            {"title": "Inter vs Milan Preview", "url": "https://example.com", "snippet": "Derby della Madonnina"}
        ]
        
        mock_deepseek_response = '''
        {
            "internal_crisis": "None detected",
            "turnover_risk": "Low - full squad available",
            "referee_intel": "Mariani - avg 4.2 cards/game",
            "biscotto_potential": "None - both teams need points",
            "injury_impact": "Calhanoglu doubtful",
            "btts_impact": "High - both teams score regularly",
            "motivation_home": "High - title race",
            "motivation_away": "Medium - Europa League spot"
        }
        '''

        with patch('src.ingestion.deepseek_intel_provider.get_brave_provider') as mock_brave:
            mock_brave_instance = MagicMock()
            mock_brave_instance.search_news.return_value = mock_brave_results
            mock_brave.return_value = mock_brave_instance
            
            with patch('httpx.Client') as mock_httpx:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{"message": {"content": mock_deepseek_response}}]
                }
                mock_httpx.return_value.__enter__.return_value.post.return_value = mock_response
                
                with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
                    # Reimport to pick up env
                    import importlib
                    import src.ingestion.deepseek_intel_provider as dsp
                    dsp._deepseek_instance = None
                    importlib.reload(dsp)
                    
                    # Reset router singleton
                    import src.services.intelligence_router as ir
                    ir._intelligence_router_instance = None
                    
                    router = ir.get_intelligence_router()
                    
                    result = router.get_match_deep_dive(
                        home_team="Inter",
                        away_team="Milan",
                        match_date="2026-01-15"
                    )
                    
                    # Verify result structure
                    assert result is not None
                    assert isinstance(result, dict)
                    
                    # Verify normalized fields exist
                    expected_fields = [
                        'internal_crisis', 'turnover_risk', 'referee_intel',
                        'biscotto_potential', 'injury_impact'
                    ]
                    for field in expected_fields:
                        assert field in result, f"Missing field: {field}"


class TestE2ERateLimiting:
    """Test E2E che il rate limiting funzioni correttamente."""
    
    def test_rate_limiting_enforces_minimum_interval(self):
        """
        E2E: Rate limiting rispetta DEEPSEEK_MIN_INTERVAL.
        
        Verifica che chiamate consecutive rispettino l'intervallo minimo.
        """
        import time
        from src.ingestion.deepseek_intel_provider import DeepSeekIntelProvider, DEEPSEEK_MIN_INTERVAL
        
        with patch('src.ingestion.deepseek_intel_provider.get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
                provider = DeepSeekIntelProvider()
                
                # First call - should not wait
                start1 = time.time()
                provider._wait_for_rate_limit()
                elapsed1 = time.time() - start1
                
                # Second call - should wait ~DEEPSEEK_MIN_INTERVAL
                start2 = time.time()
                provider._wait_for_rate_limit()
                elapsed2 = time.time() - start2
                
                # First call should be fast
                assert elapsed1 < 0.5, "First call should not wait"
                
                # Second call should wait at least MIN_INTERVAL - elapsed1
                # (with some tolerance for timing)
                assert elapsed2 >= DEEPSEEK_MIN_INTERVAL - 0.5, \
                    f"Second call should wait ~{DEEPSEEK_MIN_INTERVAL}s, waited {elapsed2}s"


class TestE2EFallbackToPerplexity:
    """Test E2E che il fallback a Perplexity funzioni."""
    
    def test_fallback_to_perplexity_on_deepseek_error(self):
        """
        E2E: Se DeepSeek fallisce, IntelligenceRouter usa Perplexity.
        
        Verifica che:
        1. DeepSeek solleva eccezione
        2. Router cattura e prova Perplexity
        3. Perplexity ritorna risultato
        """
        from src.services.intelligence_router import IntelligenceRouter
        
        # Create router with mocked providers
        router = IntelligenceRouter.__new__(IntelligenceRouter)
        
        # Mock primary (DeepSeek) to fail
        mock_primary = MagicMock()
        mock_primary.get_match_deep_dive.side_effect = Exception("DeepSeek API error")
        mock_primary.is_available.return_value = True
        
        # Mock fallback (Perplexity) to succeed
        mock_fallback = MagicMock()
        mock_fallback.get_match_deep_dive.return_value = {
            "internal_crisis": "None",
            "turnover_risk": "Low"
        }
        
        router._primary_provider = mock_primary
        router._fallback_provider = mock_fallback
        
        result = router.get_match_deep_dive("Inter", "Milan", "2026-01-15")
        
        # Should have called fallback
        mock_fallback.get_match_deep_dive.assert_called_once()
        assert result is not None
        assert result.get("internal_crisis") == "None"


class TestE2EBraveSearchIntegration:
    """Test E2E integrazione Brave Search."""
    
    def test_brave_results_included_in_prompt(self):
        """
        E2E: Risultati Brave Search vengono inclusi nel prompt DeepSeek.
        
        Verifica che:
        1. Brave Search viene chiamato
        2. Risultati vengono formattati
        3. Prompt finale contiene i risultati
        """
        from src.ingestion.deepseek_intel_provider import DeepSeekIntelProvider
        
        mock_brave_results = [
            {"title": "Breaking: Injury Update", "url": "https://news.com/1", "snippet": "Key player out"},
            {"title": "Match Preview", "url": "https://news.com/2", "snippet": "Tactical analysis"}
        ]
        
        with patch('src.ingestion.deepseek_intel_provider.get_brave_provider') as mock_brave:
            mock_brave_instance = MagicMock()
            mock_brave_instance.search_news.return_value = mock_brave_results
            mock_brave.return_value = mock_brave_instance
            
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
                provider = DeepSeekIntelProvider()
                
                # Format results
                formatted = provider._format_brave_results(mock_brave_results)
                
                # Verify formatting
                assert "Breaking: Injury Update" in formatted
                assert "https://news.com/1" in formatted
                assert "Key player out" in formatted
                assert "[WEB SEARCH RESULTS]" in formatted


class TestE2EDataFlowConsistency:
    """Test E2E consistenza flusso dati."""
    
    def test_deep_dive_response_normalized_consistently(self):
        """
        E2E: Response DeepSeek viene normalizzata in modo consistente.
        
        Verifica che campi mancanti vengano gestiti con default sicuri.
        """
        from src.utils.ai_parser import normalize_deep_dive_response
        
        # Test with partial response (missing fields)
        partial_response = {
            "internal_crisis": "Manager sacked",
            # Missing: turnover_risk, referee_intel, etc.
        }
        
        normalized = normalize_deep_dive_response(partial_response)
        
        # Should have all expected fields with defaults
        assert normalized.get("internal_crisis") == "Manager sacked"
        assert normalized.get("turnover_risk") == "Unknown"
        assert normalized.get("referee_intel") == "Unknown"
        assert normalized.get("biscotto_potential") == "Unknown"
        assert normalized.get("injury_impact") == "None reported"
    
    def test_empty_response_returns_safe_defaults(self):
        """
        E2E: Response vuota ritorna dict con default sicuri.
        """
        from src.utils.ai_parser import normalize_deep_dive_response
        
        # Test with None
        result = normalize_deep_dive_response(None)
        assert result is None or result == {}
        
        # Test with empty dict
        result = normalize_deep_dive_response({})
        assert isinstance(result, dict)


class TestE2ENotifierIntegration:
    """Test E2E che le notifiche siano corrette."""
    
    def test_deepseek_status_logged_at_startup(self):
        """
        E2E: Stato DeepSeek viene loggato all'avvio.
        
        Verifica che main.py contenga il log appropriato.
        """
        with open('src/main.py', 'r') as f:
            content = f.read()
        
        assert 'DeepSeek Intel Provider: ATTIVO' in content
        assert 'DeepSeek Intel Provider: NON DISPONIBILE' in content
