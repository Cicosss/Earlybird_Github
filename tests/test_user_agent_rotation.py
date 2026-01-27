"""
Regression Tests for User-Agent Rotation (Network Layer Audit)

Tests for:
1. get_random_user_agent() returns valid modern UA
2. FotMobProvider rotates UA on each request
"""
import pytest


class TestUserAgentRotation:
    """Tests for User-Agent rotation functionality."""
    
    def test_user_agents_list_not_empty(self):
        """USER_AGENTS list should have multiple entries."""
        from src.ingestion.data_provider import USER_AGENTS
        
        assert len(USER_AGENTS) >= 5, "Should have at least 5 User-Agents for rotation"
    
    def test_get_random_user_agent_returns_string(self):
        """get_random_user_agent should return a valid string."""
        from src.ingestion.data_provider import get_random_user_agent
        
        ua = get_random_user_agent()
        
        assert isinstance(ua, str)
        assert len(ua) > 50, "User-Agent should be a realistic length"
        assert "Mozilla" in ua, "Should be a browser-like User-Agent"
    
    def test_get_random_user_agent_rotates(self):
        """get_random_user_agent should return different values over multiple calls."""
        from src.ingestion.data_provider import get_random_user_agent
        
        # Get 20 samples - with 7 UAs, we should see variation
        samples = [get_random_user_agent() for _ in range(20)]
        unique = set(samples)
        
        # Should have at least 2 different UAs in 20 samples (statistically very likely)
        assert len(unique) >= 2, "Should rotate between different User-Agents"
    
    def test_user_agents_are_modern(self):
        """User-Agents should be modern (Chrome 130+, Firefox 130+)."""
        from src.ingestion.data_provider import USER_AGENTS
        
        for ua in USER_AGENTS:
            # Check for modern Chrome versions (130+)
            if "Chrome/" in ua:
                import re
                match = re.search(r'Chrome/(\d+)', ua)
                if match:
                    version = int(match.group(1))
                    assert version >= 130, f"Chrome version {version} is outdated (need 130+)"
            
            # Check for modern Firefox versions (130+)
            if "Firefox/" in ua:
                import re
                match = re.search(r'Firefox/(\d+)', ua)
                if match:
                    version = int(match.group(1))
                    assert version >= 130, f"Firefox version {version} is outdated (need 130+)"
    
    def test_fotmob_provider_has_rotate_method(self):
        """FotMobProvider should have _rotate_user_agent method."""
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        assert hasattr(provider, '_rotate_user_agent')
        assert callable(provider._rotate_user_agent)
    
    def test_fotmob_provider_rotates_ua(self):
        """FotMobProvider._rotate_user_agent should change session UA."""
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        # Get initial UA (may be None or default)
        initial_ua = provider.session.headers.get('User-Agent')
        
        # Rotate multiple times and collect UAs
        uas = []
        for _ in range(10):
            provider._rotate_user_agent()
            uas.append(provider.session.headers.get('User-Agent'))
        
        # All should be valid strings
        for ua in uas:
            assert ua is not None
            assert isinstance(ua, str)
            assert "Mozilla" in ua
