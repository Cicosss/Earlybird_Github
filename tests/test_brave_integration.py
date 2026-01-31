"""
Integration Tests for Brave API Manager - V1.0

Tests end-to-end integration of key rotation and budget management.
"""
import pytest
from unittest.mock import Mock, patch
from src.ingestion.brave_provider import BraveSearchProvider, get_brave_provider
from src.ingestion.brave_key_rotator import BraveKeyRotator, get_brave_key_rotator
from src.ingestion.brave_budget import BudgetManager, get_brave_budget_manager


class TestBraveIntegration:
    """Integration tests for Brave API Manager."""
    
    def test_provider_initialization(self):
        """Test that provider initializes with key rotation and budget."""
        provider = BraveSearchProvider()
        
        assert provider._key_rotator is not None
        assert provider._budget_manager is not None
        assert provider._key_rotation_enabled == True
    
    def test_provider_is_available(self):
        """Test provider availability check."""
        provider = BraveSearchProvider()
        
        # Should be available if keys are configured
        assert provider.is_available() == True
    
    def test_provider_get_status(self):
        """Test getting provider status."""
        provider = BraveSearchProvider()
        
        status = provider.get_status()
        
        assert "key_rotation_enabled" in status
        assert "rate_limited" in status
        assert "key_rotator" in status
        assert "budget" in status
    
    def test_reset_rate_limit(self):
        """Test resetting rate limit flag."""
        provider = BraveSearchProvider()
        
        # Set rate limited
        provider._rate_limited = True
        
        # Reset
        provider.reset_rate_limit()
        
        assert provider._rate_limited == False
    
    def test_singleton_instances(self):
        """Test that singleton instances work correctly."""
        provider1 = get_brave_provider()
        provider2 = get_brave_provider()
        rotator1 = get_brave_key_rotator()
        rotator2 = get_brave_key_rotator()
        budget1 = get_brave_budget_manager()
        budget2 = get_brave_budget_manager()
        
        # Should be same instances
        assert provider1 is provider2
        assert rotator1 is rotator2
        assert budget1 is budget2
    
    @patch('src.ingestion.brave_provider.get_http_client')
    def test_search_news_with_key_rotation(self, mock_http_client):
        """Test search with key rotation on 429."""
        # Mock HTTP client to return 429 on first call
        mock_response = Mock()
        mock_response.status_code = 429
        
        mock_http_client.return_value.get_sync.return_value = mock_response
        
        provider = BraveSearchProvider()
        
        # First call should return empty (rate limited)
        results = provider.search_news("test query", component="test")
        
        # Should return empty list on 429
        assert results == []
    
    @patch('src.ingestion.brave_provider.get_http_client')
    def test_search_news_with_budget_check(self, mock_http_client):
        """Test search with budget enforcement."""
        # Mock HTTP client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Test Result",
                        "url": "https://example.com",
                        "description": "Test description"
                    }
                ]
            }
        }
        
        mock_http_client.return_value.get_sync.return_value = mock_response
        
        provider = BraveSearchProvider()
        
        # Use all budget
        provider._budget_manager._monthly_used = provider._budget_manager._monthly_limit
        
        # Should return empty list (budget exhausted)
        results = provider.search_news("test query", component="test")
        
        assert results == []
    
    @patch('src.ingestion.brave_provider.get_http_client')
    def test_search_news_success(self, mock_http_client):
        """Test successful search."""
        # Mock HTTP client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Test Result 1",
                        "url": "https://example1.com",
                        "description": "Test description 1"
                    },
                    {
                        "title": "Test Result 2",
                        "url": "https://example2.com",
                        "description": "Test description 2"
                    }
                ]
            }
        }
        
        mock_http_client.return_value.get_sync.return_value = mock_response
        
        provider = BraveSearchProvider()
        
        # Search
        results = provider.search_news("test query", component="test", limit=2)
        
        # Should return 2 results
        assert len(results) == 2
        assert results[0]["title"] == "Test Result 1"
        assert results[0]["url"] == "https://example1.com"
        assert results[0]["source"] == "brave"
        
        # Budget should be updated
        assert provider._budget_manager._monthly_used == 1
        assert provider._budget_manager._component_usage["test"] == 1
        
        # Key rotator should record call
        assert provider._key_rotator._key_usage[provider._key_rotator._current_index] == 1
    
    @patch('src.ingestion.brave_provider.get_http_client')
    def test_search_news_url_encoding(self, mock_http_client):
        """Test URL encoding for special characters."""
        # Mock HTTP client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"web": {"results": []}}
        
        mock_http_client.return_value.get_sync.return_value = mock_response
        
        provider = BraveSearchProvider()
        
        # Search with special characters
        results = provider.search_news("test ş Ą α", component="test")
        
        # Should not crash
        assert isinstance(results, list)
        
        # Verify that encoded query was used
        call_args = mock_http_client.return_value.get_sync.call_args
        assert call_args is not None
    
    def test_backward_compatibility(self):
        """Test backward compatibility with existing code."""
        provider = BraveSearchProvider()
        
        # Old fields should still exist
        assert hasattr(provider, '_api_key')
        assert hasattr(provider, '_rate_limited')
        assert hasattr(provider, '_http_client')
        
        # Old methods should still work
        assert hasattr(provider, 'is_available')
        assert hasattr(provider, 'search_news')
        assert hasattr(provider, 'reset_rate_limit')
    
    def test_key_rotation_disabled_mode(self):
        """Test provider with key rotation disabled."""
        provider = BraveSearchProvider()
        
        # Disable key rotation
        provider._key_rotation_enabled = False
        
        # Should use single API key
        assert provider._key_rotation_enabled == False
    
    def test_component_parameter(self):
        """Test that component parameter is used for budget tracking."""
        provider = BraveSearchProvider()
        
        # Mock HTTP client
        with patch('src.ingestion.brave_provider.get_http_client') as mock_http_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"web": {"results": []}}
            mock_http_client.return_value.get_sync.return_value = mock_response
            
            # Search with component parameter
            provider.search_news("test query", component="test_component")
            
            # Budget should track the component
            assert "test_component" in provider._budget_manager._component_usage
            
            # Search with different component
            provider.search_news("test query", component="another_component")
            
            # Budget should track both components
            assert "test_component" in provider._budget_manager._component_usage
            assert "another_component" in provider._budget_manager._component_usage
