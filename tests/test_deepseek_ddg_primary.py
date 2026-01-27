#!/usr/bin/env python3
"""
Test di regressione per DeepSeek V6.1 - DDG come primary search.

Verifica che:
1. DeepSeek usi SearchProvider (DDG) come primary
2. Brave sia usato solo come fallback
3. La quota Brave sia preservata per news_hunter

Bug originale: Brave rate limit (429) causato da troppe chiamate
Fix: DDG come primary, Brave come fallback
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDeepSeekDDGPrimary:
    """Test suite per DeepSeek V6.1 DDG primary."""
    
    def test_search_provider_initialized(self):
        """Verifica che _search_provider sia inizializzato."""
        from src.ingestion.deepseek_intel_provider import get_deepseek_provider
        
        provider = get_deepseek_provider()
        assert hasattr(provider, '_search_provider'), "Missing _search_provider attribute"
    
    def test_brave_provider_still_available(self):
        """Verifica che _brave_provider sia ancora disponibile come fallback."""
        from src.ingestion.deepseek_intel_provider import get_deepseek_provider
        
        provider = get_deepseek_provider()
        assert hasattr(provider, '_brave_provider'), "Missing _brave_provider attribute"
    
    def test_search_brave_uses_ddg_first(self):
        """Verifica che _search_brave chiami DDG prima di Brave."""
        import inspect
        from src.ingestion.deepseek_intel_provider import get_deepseek_provider
        
        provider = get_deepseek_provider()
        source = inspect.getsource(provider._search_brave)
        
        # DDG deve essere chiamato prima di Brave
        ddg_pos = source.find('_search_provider')
        brave_pos = source.find('_brave_provider.search_news')
        
        assert ddg_pos > 0, "_search_provider not found in _search_brave"
        assert brave_pos > 0, "_brave_provider not found in _search_brave"
        assert ddg_pos < brave_pos, "DDG should be called BEFORE Brave (DDG primary)"
    
    def test_search_brave_returns_ddg_results_when_available(self):
        """Verifica che DDG results vengano usati quando disponibili."""
        from src.ingestion.deepseek_intel_provider import DeepSeekIntelProvider
        
        provider = DeepSeekIntelProvider()
        
        # Mock SearchProvider con risultati
        mock_search_provider = MagicMock()
        mock_search_provider.search.return_value = [
            {"title": "DDG Result", "url": "https://ddg.com", "snippet": "test"}
        ]
        provider._search_provider = mock_search_provider
        
        # Mock BraveProvider (non dovrebbe essere chiamato)
        mock_brave = MagicMock()
        provider._brave_provider = mock_brave
        
        results = provider._search_brave("test query", limit=5)
        
        # DDG dovrebbe essere chiamato
        mock_search_provider.search.assert_called_once_with("test query", 5)
        
        # Brave NON dovrebbe essere chiamato (DDG ha risultati)
        mock_brave.search_news.assert_not_called()
        
        assert len(results) == 1
        assert results[0]["title"] == "DDG Result"
    
    def test_search_brave_falls_back_to_brave_on_ddg_failure(self):
        """Verifica che Brave sia usato come fallback quando DDG fallisce."""
        from src.ingestion.deepseek_intel_provider import DeepSeekIntelProvider
        
        provider = DeepSeekIntelProvider()
        
        # Mock SearchProvider che fallisce
        mock_search_provider = MagicMock()
        mock_search_provider.search.return_value = []  # Empty = fallback
        provider._search_provider = mock_search_provider
        
        # Mock BraveProvider con risultati
        mock_brave = MagicMock()
        mock_brave.search_news.return_value = [
            {"title": "Brave Result", "url": "https://brave.com", "snippet": "test"}
        ]
        provider._brave_provider = mock_brave
        
        results = provider._search_brave("test query", limit=5)
        
        # DDG dovrebbe essere chiamato prima
        mock_search_provider.search.assert_called_once()
        
        # Brave dovrebbe essere chiamato come fallback
        mock_brave.search_news.assert_called_once_with("test query", limit=5)
        
        assert len(results) == 1
        assert results[0]["title"] == "Brave Result"
    
    def test_search_brave_handles_missing_search_provider(self):
        """Verifica gestione caso _search_provider non disponibile."""
        from src.ingestion.deepseek_intel_provider import DeepSeekIntelProvider
        
        provider = DeepSeekIntelProvider()
        provider._search_provider = None  # Simula provider non disponibile
        
        # Mock BraveProvider
        mock_brave = MagicMock()
        mock_brave.search_news.return_value = [
            {"title": "Brave Only", "url": "https://brave.com", "snippet": "test"}
        ]
        provider._brave_provider = mock_brave
        
        results = provider._search_brave("test query", limit=5)
        
        # Brave dovrebbe essere usato direttamente
        mock_brave.search_news.assert_called_once()
        assert len(results) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
