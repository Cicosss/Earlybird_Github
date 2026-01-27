"""
Tests for IntelligenceRouter - V6.0 (DeepSeek Only)

Property-based tests using Hypothesis to verify correctness properties.
Unit tests for specific behaviors and edge cases.

V6.0: Updated for DeepSeek as sole primary provider (no cooldown)

Test Coverage:
- Property 4: Request Routing Consistency
- Property 5: Response Format Compatibility
- Property 10: Graceful Error Handling
"""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from hypothesis import given, settings, strategies as st, assume


# ============================================
# HYPOTHESIS STRATEGIES
# ============================================

SLOW_SETTINGS = settings(max_examples=20, deadline=None)


@st.composite
def team_names(draw):
    """Generate realistic team names."""
    prefixes = ["FC", "Real", "Club", "Sporting", "Athletic", ""]
    cities = ["Madrid", "Barcelona", "Milan", "Munich", "London", "Paris", "Rome", "Istanbul"]
    suffixes = ["United", "City", "FC", "SC", ""]
    
    prefix = draw(st.sampled_from(prefixes))
    city = draw(st.sampled_from(cities))
    suffix = draw(st.sampled_from(suffixes))
    
    parts = [p for p in [prefix, city, suffix] if p]
    return " ".join(parts)


@st.composite
def match_dates(draw):
    """Generate valid match dates."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    offset_days = draw(st.integers(min_value=0, max_value=30))
    dt = base + timedelta(days=offset_days)
    return dt.strftime('%Y-%m-%d')


@st.composite
def deep_dive_responses(draw):
    """Generate valid deep dive response structures."""
    return {
        "internal_crisis": draw(st.sampled_from(["High", "Medium", "Low", "Unknown"])),
        "turnover_risk": draw(st.sampled_from(["High", "Medium", "Low", "Unknown"])),
        "referee_intel": draw(st.sampled_from(["Strict", "Lenient", "Unknown"])),
        "biscotto_potential": draw(st.sampled_from(["Yes", "No", "Unknown"])),
        "injury_impact": draw(st.sampled_from(["Critical", "Manageable", "None reported"])),
        "btts_impact": draw(st.sampled_from(["Positive", "Negative", "Neutral", "Unknown"])),
        "motivation_home": draw(st.sampled_from(["High", "Medium", "Low", "Unknown"])),
        "motivation_away": draw(st.sampled_from(["High", "Medium", "Low", "Unknown"])),
        "table_context": draw(st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z'))))
    }


@st.composite
def verification_responses(draw):
    """Generate valid verification response structures."""
    return {
        "verified": draw(st.booleans()),
        "verification_status": draw(st.sampled_from(["CONFIRMED", "DENIED", "UNVERIFIED", "OUTDATED"])),
        "confidence_level": draw(st.sampled_from(["HIGH", "MEDIUM", "LOW"])),
        "verification_sources": draw(st.lists(st.text(min_size=3, max_size=30), min_size=0, max_size=3)),
        "additional_context": draw(st.text(min_size=0, max_size=100)),
        "betting_impact": draw(st.sampled_from(["Critical", "Significant", "Minor", "None", "Unknown"])),
        "is_current": draw(st.booleans()),
        "notes": draw(st.text(min_size=0, max_size=50))
    }


# ============================================
# RESPONSE FORMAT KEYS (for compatibility check)
# ============================================

DEEP_DIVE_REQUIRED_KEYS = {
    "internal_crisis", "turnover_risk", "referee_intel", "biscotto_potential",
    "injury_impact", "btts_impact", "motivation_home", "motivation_away", "table_context"
}

VERIFICATION_REQUIRED_KEYS = {
    "verified", "verification_status", "confidence_level", "verification_sources",
    "additional_context", "betting_impact", "is_current", "notes"
}


# ============================================
# PROPERTY-BASED TESTS
# ============================================

class TestResponseFormatCompatibility:
    """
    **Feature: intelligence-router, Property 5: Response Format Compatibility**
    **Validates: Requirements 2.5**
    """
    
    @given(deep_dive_responses())
    @SLOW_SETTINGS
    def test_deep_dive_response_keys_match(self, response_data):
        """Property test: Deep dive responses have all required keys."""
        from src.ingestion.perplexity_provider import PerplexityProvider
        
        perplexity = PerplexityProvider()
        
        with patch.object(perplexity, '_query_api', return_value=response_data):
            with patch.object(perplexity, 'is_available', return_value=True):
                result = perplexity.get_match_deep_dive("Home", "Away", "2026-01-15")
        
        if result is not None:
            result_keys = set(result.keys())
            missing_keys = DEEP_DIVE_REQUIRED_KEYS - result_keys
            assert not missing_keys, f"Missing keys: {missing_keys}"


class TestRequestRoutingConsistency:
    """
    **Feature: intelligence-router V6.0, Property 4: Request Routing Consistency**
    V6.0: All requests go to DeepSeek (no cooldown management).
    """
    
    def test_always_routes_to_deepseek(self):
        """Test that requests are always routed to DeepSeek (V6.0)."""
        from src.services.intelligence_router import IntelligenceRouter
        
        router = IntelligenceRouter()
        provider_name = router.get_active_provider_name()
        assert provider_name == "deepseek"
    
    def test_cooldown_status_returns_none(self):
        """Test that get_cooldown_status returns None (V6.0 - no cooldown)."""
        from src.services.intelligence_router import IntelligenceRouter
        
        router = IntelligenceRouter()
        status = router.get_cooldown_status()
        assert status is None
    
    @given(team_names(), team_names(), match_dates())
    @SLOW_SETTINGS
    def test_deep_dive_uses_deepseek_primary(self, home_team, away_team, match_date):
        """Property test: Deep dive requests always use DeepSeek as primary."""
        assume(home_team != away_team)
        assume(len(home_team) > 2 and len(away_team) > 2)
        
        from src.services.intelligence_router import IntelligenceRouter
        
        router = IntelligenceRouter()
        
        with patch.object(router._primary_provider, 'get_match_deep_dive') as mock_primary:
            mock_primary.return_value = {"test": "data"}
            router.get_match_deep_dive(home_team, away_team, match_date)
            mock_primary.assert_called_once()


class TestGracefulErrorHandling:
    """
    **Feature: intelligence-router V6.0, Property 10: Graceful Error Handling**
    """
    
    def test_deepseek_failure_falls_back_to_perplexity(self):
        """Test that DeepSeek failures fall back to Perplexity."""
        from src.services.intelligence_router import IntelligenceRouter
        
        router = IntelligenceRouter()
        
        with patch.object(router._primary_provider, 'get_match_deep_dive', side_effect=Exception("DeepSeek Error")):
            with patch.object(router._fallback_provider, 'get_match_deep_dive', return_value={"fallback": "data"}):
                result = router.get_match_deep_dive("Home", "Away", "2026-01-15")
                assert result == {"fallback": "data"}
    
    def test_both_providers_fail_returns_none(self):
        """Test that when both providers fail, None is returned."""
        from src.services.intelligence_router import IntelligenceRouter
        
        router = IntelligenceRouter()
        
        with patch.object(router._primary_provider, 'get_match_deep_dive', side_effect=Exception("DeepSeek Error")):
            with patch.object(router._fallback_provider, 'get_match_deep_dive', side_effect=Exception("Perplexity Error")):
                result = router.get_match_deep_dive("Home", "Away", "2026-01-15")
                assert result is None
    
    def test_circuit_status_shows_no_cooldown(self):
        """Test that circuit status shows cooldown_active=False (V6.0)."""
        from src.services.intelligence_router import IntelligenceRouter
        
        router = IntelligenceRouter()
        
        with patch.object(router._primary_provider, 'is_available', return_value=True):
            status = router.get_circuit_status()
            assert status["provider"] == "deepseek"
            assert status["cooldown_active"] is False


# ============================================
# UNIT TESTS
# ============================================

class TestIntelligenceRouterUnit:
    """Unit tests for IntelligenceRouter specific behaviors."""
    
    def test_router_initialization(self):
        """Test that router initializes with all required components."""
        from src.services.intelligence_router import IntelligenceRouter
        
        router = IntelligenceRouter()
        assert router._primary_provider is not None
        assert router._fallback_provider is not None
    
    def test_is_available_checks_deepseek(self):
        """Test that is_available() checks DeepSeek availability."""
        from src.services.intelligence_router import IntelligenceRouter
        
        router = IntelligenceRouter()
        
        with patch.object(router._primary_provider, 'is_available', return_value=True):
            assert router.is_available() is True
        
        with patch.object(router._primary_provider, 'is_available', return_value=False):
            assert router.is_available() is False
    
    def test_format_for_prompt_uses_deepseek(self):
        """Test that format_for_prompt uses DeepSeek's formatter."""
        from src.services.intelligence_router import IntelligenceRouter
        
        router = IntelligenceRouter()
        test_data = {"internal_crisis": "High", "turnover_risk": "Low"}
        
        result = router.format_for_prompt(test_data)
        assert "[DEEPSEEK INTELLIGENCE]" in result or "[INTELLIGENCE]" in result


class TestPerplexityProviderMethods:
    """Unit tests for PerplexityProvider edge cases."""
    
    def test_verify_news_item_edge_cases(self):
        """Test verify_news_item handles edge cases correctly."""
        from src.ingestion.perplexity_provider import PerplexityProvider
        
        provider = PerplexityProvider()
        
        with patch.object(provider, 'is_available', return_value=True):
            result = provider.verify_news_item("", "", "Team")
            assert result is None
            
            result = provider.verify_news_item("Title", "Snippet", "")
            assert result is None
    
    def test_get_betting_stats_edge_cases(self):
        """Test get_betting_stats handles edge cases correctly."""
        from src.ingestion.perplexity_provider import PerplexityProvider
        
        provider = PerplexityProvider()
        
        with patch.object(provider, 'is_available', return_value=False):
            result = provider.get_betting_stats("Home", "Away", "2026-01-15")
            assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
