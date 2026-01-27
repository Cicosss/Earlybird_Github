"""
Property-Based Tests for DeepSeekIntelProvider

Tests correctness properties defined in the design document.
Uses Hypothesis for property-based testing with 100+ iterations.

**Feature: deepseek-migration**
"""
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from unittest.mock import patch, MagicMock
import os


# ============================================
# FIXTURES
# ============================================

@pytest.fixture
def mock_no_api_key(monkeypatch):
    """Remove OPENROUTER_API_KEY to simulate disabled provider."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


@pytest.fixture
def mock_api_key(monkeypatch):
    """Set a test OPENROUTER_API_KEY."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-12345")


@pytest.fixture
def disabled_provider():
    """Create a disabled provider (no API key)."""
    import importlib
    import src.ingestion.deepseek_intel_provider as module
    
    # Reload to get fresh module
    importlib.reload(module)
    
    # Save original key
    original_key = module.OPENROUTER_API_KEY
    
    # Temporarily set module-level key to None
    module.OPENROUTER_API_KEY = None
    
    # Create provider - it will read None from module variable
    provider = module.DeepSeekIntelProvider()
    
    # Restore module variable for other tests
    module.OPENROUTER_API_KEY = original_key
    
    # Verify provider is disabled
    assert provider._api_key is None
    assert provider._enabled is False
    
    return provider


# ============================================
# STRATEGIES
# ============================================

# Strategy for team names
team_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'Zs')),
    min_size=1,
    max_size=50
).filter(lambda x: x.strip())

# Strategy for optional team names (can be None or empty)
optional_team_strategy = st.one_of(
    st.none(),
    st.just(""),
    st.just("   "),  # whitespace only
)

# Strategy for match dates
date_strategy = st.one_of(
    st.none(),
    st.dates().map(lambda d: d.strftime("%Y-%m-%d"))
)

# Strategy for Brave search results
brave_result_strategy = st.fixed_dictionaries({
    "title": st.text(min_size=1, max_size=100),
    "url": st.text(min_size=1, max_size=200).map(lambda x: f"https://example.com/{x}"),
    "snippet": st.text(min_size=0, max_size=300),
})

brave_results_list_strategy = st.lists(brave_result_strategy, min_size=0, max_size=10)


# ============================================
# PROPERTY 1: Disabled Provider Returns None
# **Feature: deepseek-migration, Property 1: Disabled Provider Returns None**
# **Validates: Requirements 1.3**
# ============================================

class TestProperty1DisabledProviderReturnsNone:
    """
    Property 1: Disabled Provider Returns None
    
    *For any* method call on a disabled provider (no API key), 
    the method SHALL return None without throwing exceptions.
    
    **Validates: Requirements 1.3**
    """
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        home_team=team_name_strategy,
        away_team=team_name_strategy,
        match_date=date_strategy
    )
    def test_get_match_deep_dive_returns_none_when_disabled(
        self, home_team, away_team, match_date, disabled_provider
    ):
        """
        **Feature: deepseek-migration, Property 1: Disabled Provider Returns None**
        **Validates: Requirements 1.3**
        """
        result = disabled_provider.get_match_deep_dive(
            home_team=home_team,
            away_team=away_team,
            match_date=match_date
        )
        assert result is None
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        home_team=team_name_strategy,
        away_team=team_name_strategy,
        match_date=st.dates().map(lambda d: d.strftime("%Y-%m-%d"))
    )
    def test_get_betting_stats_returns_none_when_disabled(
        self, home_team, away_team, match_date, disabled_provider
    ):
        """
        **Feature: deepseek-migration, Property 1: Disabled Provider Returns None**
        **Validates: Requirements 1.3**
        """
        result = disabled_provider.get_betting_stats(
            home_team=home_team,
            away_team=away_team,
            match_date=match_date
        )
        assert result is None
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        news_title=st.text(min_size=1, max_size=100),
        team_name=team_name_strategy
    )
    def test_verify_news_item_returns_none_when_disabled(
        self, news_title, team_name, disabled_provider
    ):
        """
        **Feature: deepseek-migration, Property 1: Disabled Provider Returns None**
        **Validates: Requirements 1.3**
        """
        result = disabled_provider.verify_news_item(
            news_title=news_title,
            news_snippet="Test snippet",
            team_name=team_name
        )
        assert result is None
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        home_team=team_name_strategy,
        away_team=team_name_strategy,
        draw_odds=st.floats(min_value=1.1, max_value=10.0)
    )
    def test_confirm_biscotto_returns_none_when_disabled(
        self, home_team, away_team, draw_odds, disabled_provider
    ):
        """
        **Feature: deepseek-migration, Property 1: Disabled Provider Returns None**
        **Validates: Requirements 1.3**
        """
        result = disabled_provider.confirm_biscotto(
            home_team=home_team,
            away_team=away_team,
            match_date="2026-01-15",
            league="Serie A",
            draw_odds=draw_odds,
            implied_prob=30.0,
            odds_pattern="STABLE",
            season_context="End of season"
        )
        assert result is None
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        home_team=team_name_strategy,
        away_team=team_name_strategy
    )
    def test_enrich_match_context_returns_none_when_disabled(
        self, home_team, away_team, disabled_provider
    ):
        """
        **Feature: deepseek-migration, Property 1: Disabled Provider Returns None**
        **Validates: Requirements 1.3**
        """
        result = disabled_provider.enrich_match_context(
            home_team=home_team,
            away_team=away_team,
            match_date="2026-01-15",
            league="Serie A"
        )
        assert result is None
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(handles=st.lists(st.text(min_size=2, max_size=20).map(lambda x: f"@{x}"), min_size=1, max_size=5))
    def test_extract_twitter_intel_returns_none_when_disabled(
        self, handles, disabled_provider
    ):
        """
        **Feature: deepseek-migration, Property 1: Disabled Provider Returns None**
        **Validates: Requirements 1.3**
        """
        result = disabled_provider.extract_twitter_intel(handles=handles)
        assert result is None


# ============================================
# PROPERTY 2: Availability Reflects State
# **Feature: deepseek-migration, Property 2: Availability Reflects State**
# **Validates: Requirements 1.4**
# V6.0: Updated - DeepSeek no longer uses CooldownManager
# ============================================

class TestProperty2AvailabilityReflectsState:
    """
    Property 2: Availability Reflects State
    
    V6.0: DeepSeek no longer uses CooldownManager (OpenRouter has high rate limits).
    is_available() returns True when API key is set, regardless of cooldown state.
    
    **Validates: Requirements 1.4**
    """
    
    def test_no_api_key_returns_false(self, disabled_provider):
        """
        **Feature: deepseek-migration, Property 2: Availability Reflects State**
        **Validates: Requirements 1.4**
        
        No API key -> is_available() returns False
        """
        assert disabled_provider.is_available() is False
    
    def test_api_key_with_cooldown_active_returns_true_v6(self, mock_api_key):
        """
        **Feature: deepseek-migration, Property 2: Availability Reflects State**
        **Validates: Requirements 1.4**
        
        V6.0: API key set + cooldown active -> is_available() returns True
        (DeepSeek no longer checks CooldownManager)
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        importlib.reload(module)
        
        # Mock brave provider to avoid initialization issues
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        # V6.0: DeepSeek should be available even with cooldown active
        # because it doesn't use CooldownManager anymore
        assert provider.is_available() is True
    
    def test_api_key_with_cooldown_inactive_returns_true(self, mock_api_key):
        """
        **Feature: deepseek-migration, Property 2: Availability Reflects State**
        **Validates: Requirements 1.4**
        
        API key set + cooldown inactive -> is_available() returns True
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        importlib.reload(module)
        
        # Mock brave provider to avoid initialization issues
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        # V6.0: No need to mock CooldownManager - DeepSeek doesn't use it
        assert provider.is_available() is True
    
    @settings(max_examples=100)
    @given(
        has_api_key=st.booleans(),
        cooldown_active=st.booleans()  # V6.0: This parameter is now ignored
    )
    def test_availability_truth_table(self, has_api_key, cooldown_active):
        """
        **Feature: deepseek-migration, Property 2: Availability Reflects State**
        **Validates: Requirements 1.4**
        
        V6.0: Property: is_available() == has_api_key
        (cooldown_active is ignored - DeepSeek doesn't use CooldownManager)
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        
        # Set or unset API key
        if has_api_key:
            os.environ["OPENROUTER_API_KEY"] = "test-key"
        else:
            os.environ.pop("OPENROUTER_API_KEY", None)
        
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        # V6.0: DeepSeek availability depends only on API key, not cooldown
        expected = has_api_key
        assert provider.is_available() == expected


# ============================================
# CLEANUP
# ============================================

@pytest.fixture(autouse=True)
def cleanup_env():
    """Cleanup environment after each test."""
    yield
    # Restore original state
    os.environ.pop("OPENROUTER_API_KEY", None)



# ============================================
# PROPERTY 4: Brave Results Formatting
# **Feature: deepseek-migration, Property 4: Brave Results Formatting**
# **Validates: Requirements 3.5**
# ============================================

class TestProperty4BraveResultsFormatting:
    """
    Property 4: Brave Results Formatting
    
    *For any* list of Brave search results, the formatted output 
    SHALL contain title, URL, and snippet for each result.
    
    **Validates: Requirements 3.5**
    """
    
    @settings(max_examples=100)
    @given(results=brave_results_list_strategy)
    def test_formatted_results_contain_all_fields(self, results):
        """
        **Feature: deepseek-migration, Property 4: Brave Results Formatting**
        **Validates: Requirements 3.5**
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        formatted = provider._format_brave_results(results)
        
        if not results:
            # Empty results should return empty string
            assert formatted == ""
        else:
            # Each result should have title, URL, snippet in output
            for result in results:
                title = result.get("title", "No title")
                url = result.get("url", "")
                snippet = result.get("snippet", "")
                
                # Title should always be present
                assert title in formatted or "No title" in formatted
                
                # URL should be present if not empty
                if url:
                    assert url in formatted
                
                # Snippet should be present if not empty
                if snippet:
                    assert snippet in formatted
    
    def test_empty_results_returns_empty_string(self):
        """
        **Feature: deepseek-migration, Property 4: Brave Results Formatting**
        **Validates: Requirements 3.5**
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        assert provider._format_brave_results([]) == ""
        assert provider._format_brave_results(None) == ""


# ============================================
# PROPERTY 6: Prompts Without Google References
# **Feature: deepseek-migration, Property 6: Prompts Without Google References**
# **Validates: Requirements 5.1**
# ============================================

class TestProperty6PromptsWithoutGoogleReferences:
    """
    Property 6: Prompts Without Google References
    
    *For any* prompt generated for DeepSeek, the prompt SHALL NOT 
    contain the strings "Google Search" or "search grounding".
    
    **Validates: Requirements 5.1**
    """
    
    @settings(max_examples=100)
    @given(
        base_prompt=st.text(min_size=10, max_size=500),
    )
    def test_no_google_references_in_prompt(self, base_prompt):
        """
        **Feature: deepseek-migration, Property 6: Prompts Without Google References**
        **Validates: Requirements 5.1**
        
        Note: Only the base_prompt is cleaned. Brave results are external data
        that may legitimately contain "Google Search" text.
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        # Add Google references to base prompt to test removal
        test_prompt = base_prompt + " Google Search grounding Search Grounding google search"
        
        # Use clean brave_results (no Google references) to isolate the test
        clean_brave_results = "Some web search results about football"
        final_prompt = provider._build_prompt_with_context(test_prompt, clean_brave_results)
        
        # Should not contain Google Search references from the base_prompt
        # (brave_results are external data and not cleaned)
        assert "Google Search" not in final_prompt
        assert "google search" not in final_prompt
        assert "search grounding" not in final_prompt
        assert "Search Grounding" not in final_prompt
    
    def test_real_prompts_cleaned(self):
        """
        **Feature: deepseek-migration, Property 6: Prompts Without Google References**
        **Validates: Requirements 5.1**
        
        Test with actual prompts from prompts.py
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        from src.ingestion.prompts import (
            build_deep_dive_prompt,
            build_betting_stats_prompt,
            build_news_verification_prompt
        )
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        # Test with real prompts
        prompts = [
            build_deep_dive_prompt("Inter", "Milan", "2026-01-15"),
            build_betting_stats_prompt("Inter", "Milan", "2026-01-15", "Serie A"),
            build_news_verification_prompt("Injury news", "Player out", "Inter"),
        ]
        
        for base_prompt in prompts:
            final_prompt = provider._build_prompt_with_context(base_prompt, "Some results")
            
            assert "Google Search" not in final_prompt
            assert "search grounding" not in final_prompt.lower()


# ============================================
# PROPERTY 7: Prompts Include Brave Context
# **Feature: deepseek-migration, Property 7: Prompts Include Brave Context**
# **Validates: Requirements 5.2, 5.3**
# ============================================

class TestProperty7PromptsIncludeBraveContext:
    """
    Property 7: Prompts Include Brave Context
    
    *For any* prompt generated when Brave results are available, 
    the prompt SHALL include a section with the formatted Brave results.
    
    **Validates: Requirements 5.2, 5.3**
    """
    
    @settings(max_examples=100)
    @given(
        base_prompt=st.text(min_size=10, max_size=200),
        brave_results=st.text(min_size=1, max_size=200).filter(lambda x: x.strip())
    )
    def test_brave_results_included_when_available(self, base_prompt, brave_results):
        """
        **Feature: deepseek-migration, Property 7: Prompts Include Brave Context**
        **Validates: Requirements 5.2, 5.3**
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        final_prompt = provider._build_prompt_with_context(base_prompt, brave_results)
        
        # Brave results should be in the prompt
        assert brave_results in final_prompt
        # Should have instruction to analyze sources
        assert "web search results" in final_prompt.lower() or "provided sources" in final_prompt.lower()
    
    @settings(max_examples=100)
    @given(base_prompt=st.text(min_size=10, max_size=200))
    def test_training_knowledge_instruction_when_no_results(self, base_prompt):
        """
        **Feature: deepseek-migration, Property 7: Prompts Include Brave Context**
        **Validates: Requirements 5.4**
        
        When no Brave results, should instruct to use training knowledge.
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        # Empty results
        final_prompt = provider._build_prompt_with_context(base_prompt, "")
        
        # Should have instruction about training knowledge
        assert "training knowledge" in final_prompt.lower()


# ============================================
# PROPERTY 8: Invalid Input Returns None
# **Feature: deepseek-migration, Property 8: Invalid Input Returns None**
# **Validates: Requirements 7.1**
# V6.0: Updated - CooldownManager patches removed (DeepSeek doesn't use it)
# ============================================

class TestProperty8InvalidInputReturnsNone:
    """
    Property 8: Invalid Input Returns None
    
    *For any* method call with None or empty required parameters, 
    the method SHALL return None without making API calls.
    
    **Validates: Requirements 7.1**
    """
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(invalid_team=optional_team_strategy)
    def test_deep_dive_invalid_home_team(self, invalid_team, mock_api_key):
        """
        **Feature: deepseek-migration, Property 8: Invalid Input Returns None**
        **Validates: Requirements 7.1**
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        # V6.0: No CooldownManager patch needed - DeepSeek doesn't use it
        # Invalid home_team should return None
        result = provider.get_match_deep_dive(
            home_team=invalid_team,
            away_team="Valid Team"
        )
        assert result is None
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    @given(invalid_team=optional_team_strategy)
    def test_deep_dive_invalid_away_team(self, invalid_team, mock_api_key):
        """
        **Feature: deepseek-migration, Property 8: Invalid Input Returns None**
        **Validates: Requirements 7.1**
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        # V6.0: No CooldownManager patch needed - DeepSeek doesn't use it
        # Invalid away_team should return None
        result = provider.get_match_deep_dive(
            home_team="Valid Team",
            away_team=invalid_team
        )
        assert result is None
    
    def test_verify_news_no_title_no_snippet(self, mock_api_key):
        """
        **Feature: deepseek-migration, Property 8: Invalid Input Returns None**
        **Validates: Requirements 7.1**
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        # V6.0: No CooldownManager patch needed - DeepSeek doesn't use it
        # No title and no snippet should return None
        result = provider.verify_news_item(
            news_title="",
            news_snippet="",
            team_name="Inter"
        )
        assert result is None
    
    def test_verify_news_no_team_name(self, mock_api_key):
        """
        **Feature: deepseek-migration, Property 8: Invalid Input Returns None**
        **Validates: Requirements 7.1**
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        # V6.0: No CooldownManager patch needed - DeepSeek doesn't use it
        # No team_name should return None
        result = provider.verify_news_item(
            news_title="Some news",
            news_snippet="Some snippet",
            team_name=""
        )
        assert result is None
    
    def test_confirm_biscotto_invalid_odds(self, mock_api_key):
        """
        **Feature: deepseek-migration, Property 8: Invalid Input Returns None**
        **Validates: Requirements 7.1**
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        # V6.0: No CooldownManager patch needed - DeepSeek doesn't use it
        # Invalid draw_odds (<=1.0) should return None
        result = provider.confirm_biscotto(
            home_team="Inter",
            away_team="Milan",
            match_date="2026-01-15",
            league="Serie A",
            draw_odds=0.5,  # Invalid
            implied_prob=30.0,
            odds_pattern="STABLE",
            season_context="End of season"
        )
        assert result is None
        
        # None draw_odds should return None
        result = provider.confirm_biscotto(
            home_team="Inter",
            away_team="Milan",
            match_date="2026-01-15",
            league="Serie A",
            draw_odds=None,
            implied_prob=30.0,
            odds_pattern="STABLE",
            season_context="End of season"
        )
        assert result is None
    
    def test_extract_twitter_no_handles(self, mock_api_key):
        """
        **Feature: deepseek-migration, Property 8: Invalid Input Returns None**
        **Validates: Requirements 7.1**
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            provider = module.DeepSeekIntelProvider()
        
        # V6.0: No CooldownManager patch needed - DeepSeek doesn't use it
        # Empty handles should return None
        assert provider.extract_twitter_intel(handles=[]) is None
        assert provider.extract_twitter_intel(handles=None) is None


# ============================================
# PROPERTY 11: Singleton Consistency
# **Feature: deepseek-migration, Property 11: Singleton Consistency**
# **Validates: Requirements 8.1**
# ============================================

class TestProperty11SingletonConsistency:
    """
    Property 11: Singleton Consistency
    
    *For any* number of calls to get_deepseek_provider(), 
    all calls SHALL return the same instance.
    
    **Validates: Requirements 8.1**
    """
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(num_calls=st.integers(min_value=2, max_value=20))
    def test_singleton_returns_same_instance(self, num_calls, mock_api_key):
        """
        **Feature: deepseek-migration, Property 11: Singleton Consistency**
        **Validates: Requirements 8.1**
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        
        # Reset singleton
        module._deepseek_instance = None
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            
            # Get provider multiple times
            instances = [module.get_deepseek_provider() for _ in range(num_calls)]
            
            # All should be the same instance
            first_instance = instances[0]
            for instance in instances[1:]:
                assert instance is first_instance
    
    def test_singleton_persists_across_calls(self, mock_api_key):
        """
        **Feature: deepseek-migration, Property 11: Singleton Consistency**
        **Validates: Requirements 8.1**
        """
        import importlib
        import src.ingestion.deepseek_intel_provider as module
        
        # Reset singleton
        module._deepseek_instance = None
        importlib.reload(module)
        
        with patch.object(module, 'get_brave_provider') as mock_brave:
            mock_brave.return_value = MagicMock()
            
            provider1 = module.get_deepseek_provider()
            provider2 = module.get_deepseek_provider()
            provider3 = module.get_deepseek_provider()
            
            assert provider1 is provider2
            assert provider2 is provider3
            assert id(provider1) == id(provider2) == id(provider3)
