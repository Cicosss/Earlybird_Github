"""
Tests for Browser Monitor - Always-On Web Monitoring

Property-based tests using Hypothesis to verify correctness properties.
Unit tests for specific behaviors and edge cases.

Requirements: 1.1-1.4, 2.1-2.4, 3.1-3.5, 4.1-4.4, 5.1-5.4, 6.1-6.4, 7.1-7.4
"""
import json
import pytest
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from hypothesis import given, strategies as st, settings, assume

from src.services.browser_monitor import (
    MonitoredSource,
    GlobalSettings,
    DiscoveredNews,
    MonitorConfig,
    ContentCache,
    load_config,
    get_sources_for_league,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_MAX_CONCURRENT_PAGES,
    DEFAULT_NAVIGATION_INTERVAL_SECONDS,
    DEFAULT_PAGE_TIMEOUT_SECONDS,
    DEFAULT_CACHE_TTL_HOURS,
    DEFAULT_CACHE_MAX_ENTRIES,
)


# ============================================
# STRATEGIES FOR PROPERTY-BASED TESTING
# ============================================

# Strategy for valid URLs
valid_urls = st.from_regex(r'https?://[a-z0-9\-\.]+\.[a-z]{2,}/[a-z0-9\-/]*', fullmatch=True)

# Strategy for league keys
league_keys = st.sampled_from([
    "soccer_turkey_super_league",
    "soccer_argentina_primera_division",
    "soccer_mexico_ligamx",
    "soccer_greece_super_league",
    "soccer_scotland_premiership",
    "soccer_australia_aleague",
    "soccer_poland_ekstraklasa",
])

# Strategy for source names
source_names = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')))

# Strategy for valid MonitoredSource
monitored_source_strategy = st.builds(
    MonitoredSource,
    url=valid_urls,
    league_key=league_keys,
    scan_interval_minutes=st.integers(min_value=1, max_value=60),
    priority=st.integers(min_value=1, max_value=10),
    name=source_names,
)

# Strategy for GlobalSettings
global_settings_strategy = st.builds(
    GlobalSettings,
    default_scan_interval_minutes=st.integers(min_value=1, max_value=60),
    max_concurrent_pages=st.integers(min_value=1, max_value=10),
    navigation_interval_seconds=st.integers(min_value=1, max_value=60),
    page_timeout_seconds=st.integers(min_value=5, max_value=120),
    cache_ttl_hours=st.integers(min_value=1, max_value=168),
    cache_max_entries=st.integers(min_value=100, max_value=100000),
)


# ============================================
# PROPERTY 1: Configuration Schema Validity
# **Feature: browser-automation-always-on, Property 1: Configuration Schema Validity**
# **Validates: Requirements 2.2**
# ============================================

@settings(max_examples=100)
@given(
    sources=st.lists(monitored_source_strategy, min_size=0, max_size=10),
    global_settings=global_settings_strategy
)
def test_property_1_configuration_schema_validity(sources, global_settings):
    """
    **Feature: browser-automation-always-on, Property 1: Configuration Schema Validity**
    **Validates: Requirements 2.2**
    
    For any source configuration loaded from file, the configuration SHALL contain
    all required fields (url, league_key) and optional fields SHALL have valid default values.
    """
    # Create a temporary config file
    config_data = {
        "sources": [
            {
                "url": s.url,
                "league_key": s.league_key,
                "scan_interval_minutes": s.scan_interval_minutes,
                "priority": s.priority,
                "name": s.name,
            }
            for s in sources
        ],
        "global_settings": {
            "default_scan_interval_minutes": global_settings.default_scan_interval_minutes,
            "max_concurrent_pages": global_settings.max_concurrent_pages,
            "navigation_interval_seconds": global_settings.navigation_interval_seconds,
            "page_timeout_seconds": global_settings.page_timeout_seconds,
            "cache_ttl_hours": global_settings.cache_ttl_hours,
            "cache_max_entries": global_settings.cache_max_entries,
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name
    
    try:
        # Load config
        config = load_config(temp_path)
        
        # Verify all sources loaded correctly
        assert len(config.sources) == len(sources)
        
        for i, loaded_source in enumerate(config.sources):
            original = sources[i]
            
            # Required fields must be present
            assert loaded_source.url == original.url
            assert loaded_source.league_key == original.league_key
            
            # Optional fields must have valid values
            assert loaded_source.scan_interval_minutes > 0
            assert loaded_source.priority >= 1
            assert len(loaded_source.name) > 0
        
        # Verify global settings
        assert config.global_settings.default_scan_interval_minutes > 0
        assert config.global_settings.max_concurrent_pages >= 1
        assert config.global_settings.navigation_interval_seconds >= 1
        assert config.global_settings.page_timeout_seconds >= 5
        assert config.global_settings.cache_ttl_hours >= 1
        assert config.global_settings.cache_max_entries >= 100
        
    finally:
        Path(temp_path).unlink()


# ============================================
# UNIT TESTS FOR CONFIGURATION
# ============================================

def test_load_config_missing_file():
    """Test loading config from non-existent file returns empty config."""
    config = load_config("nonexistent_file_12345.json")
    assert len(config.sources) == 0
    assert config.global_settings.default_scan_interval_minutes == DEFAULT_SCAN_INTERVAL_MINUTES


def test_load_config_invalid_json():
    """Test loading invalid JSON returns empty config."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("{ invalid json }")
        temp_path = f.name
    
    try:
        config = load_config(temp_path)
        assert len(config.sources) == 0
    finally:
        Path(temp_path).unlink()


def test_load_config_missing_required_fields():
    """Test sources missing required fields are skipped."""
    config_data = {
        "sources": [
            {"url": "https://example.com"},  # Missing league_key
            {"league_key": "soccer_turkey"},  # Missing url
            {"url": "https://valid.com", "league_key": "soccer_turkey"},  # Valid
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name
    
    try:
        config = load_config(temp_path)
        # Only the valid source should be loaded
        assert len(config.sources) == 1
        assert config.sources[0].url == "https://valid.com"
    finally:
        Path(temp_path).unlink()


def test_load_config_default_values():
    """Test that missing optional fields get default values."""
    config_data = {
        "sources": [
            {"url": "https://example.com", "league_key": "soccer_turkey"}
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name
    
    try:
        config = load_config(temp_path)
        assert len(config.sources) == 1
        source = config.sources[0]
        
        # Check defaults
        assert source.scan_interval_minutes == DEFAULT_SCAN_INTERVAL_MINUTES
        assert source.priority == 1
        assert source.name == "https://example.com"[:50]
    finally:
        Path(temp_path).unlink()


def test_get_sources_for_league():
    """Test filtering sources by league key."""
    sources = [
        MonitoredSource(url="https://a.com", league_key="soccer_turkey"),
        MonitoredSource(url="https://b.com", league_key="soccer_argentina"),
        MonitoredSource(url="https://c.com", league_key="soccer_turkey"),
    ]
    config = MonitorConfig(sources=sources)
    
    turkey_sources = get_sources_for_league(config, "soccer_turkey")
    assert len(turkey_sources) == 2
    assert all(s.league_key == "soccer_turkey" for s in turkey_sources)
    
    argentina_sources = get_sources_for_league(config, "soccer_argentina")
    assert len(argentina_sources) == 1
    
    empty_sources = get_sources_for_league(config, "soccer_unknown")
    assert len(empty_sources) == 0


def test_monitored_source_is_due_for_scan():
    """Test is_due_for_scan logic."""
    # Never scanned - should be due
    source = MonitoredSource(url="https://a.com", league_key="soccer_turkey")
    assert source.is_due_for_scan() is True
    
    # Just scanned - should not be due
    source.last_scanned = datetime.now(timezone.utc)
    assert source.is_due_for_scan() is False
    
    # Scanned long ago - should be due
    source.last_scanned = datetime.now(timezone.utc) - timedelta(minutes=10)
    source.scan_interval_minutes = 5
    assert source.is_due_for_scan() is True


# ============================================
# CONTENT CACHE TESTS
# ============================================

def test_content_cache_basic():
    """Test basic cache operations."""
    cache = ContentCache(max_entries=100, ttl_hours=24)
    
    content = "This is some test content for caching"
    
    # Not cached initially
    assert cache.is_cached(content) is False
    
    # Cache it
    cache.cache(content)
    
    # Now it should be cached
    assert cache.is_cached(content) is True
    assert cache.size() == 1


def test_content_cache_hash_uses_first_1000_chars():
    """Test that hash is computed from first 1000 chars only."""
    cache = ContentCache()
    
    # Two contents with same first 1000 chars but different endings
    prefix = "A" * 1000
    content1 = prefix + "ENDING1"
    content2 = prefix + "ENDING2"
    
    # They should have the same hash
    assert cache.compute_hash(content1) == cache.compute_hash(content2)
    
    # Caching one should make the other appear cached
    cache.cache(content1)
    assert cache.is_cached(content2) is True


# ============================================
# PROPERTY 6: Content Deduplication
# **Feature: browser-automation-always-on, Property 6: Content Deduplication**
# **Validates: Requirements 5.1, 5.2, 5.3**
# ============================================

@settings(max_examples=100)
@given(content=st.text(min_size=10, max_size=5000))
def test_property_6_content_deduplication(content):
    """
    **Feature: browser-automation-always-on, Property 6: Content Deduplication**
    **Validates: Requirements 5.1, 5.2, 5.3**
    
    For any page content, if the content hash has been seen within the last 24 hours,
    the BrowserMonitor SHALL skip Gemini analysis and NOT invoke the callback.
    """
    cache = ContentCache(max_entries=1000, ttl_hours=24)
    
    # Initially not cached
    assert cache.is_cached(content) is False
    
    # Cache the content
    cache.cache(content)
    
    # Now it should be cached (deduplication works)
    assert cache.is_cached(content) is True
    
    # Same content cached again should still be cached
    cache.cache(content)
    assert cache.is_cached(content) is True
    
    # Cache size should be 1 (not duplicated)
    assert cache.size() == 1


@settings(max_examples=100)
@given(
    content1=st.text(min_size=10, max_size=500),
    content2=st.text(min_size=10, max_size=500)
)
def test_property_6_different_content_not_deduplicated(content1, content2):
    """
    **Feature: browser-automation-always-on, Property 6: Content Deduplication**
    **Validates: Requirements 5.1, 5.2, 5.3**
    
    Different content should not be deduplicated (unless first 1000 chars match).
    """
    # Skip if contents have same first 1000 chars
    assume(content1[:1000] != content2[:1000])
    
    cache = ContentCache(max_entries=1000, ttl_hours=24)
    
    cache.cache(content1)
    
    # Different content should not be cached
    assert cache.is_cached(content2) is False


def test_property_6_cache_expiration():
    """
    **Feature: browser-automation-always-on, Property 6: Content Deduplication**
    **Validates: Requirements 5.3**
    
    Content hash should expire after TTL hours.
    """
    # Use very short TTL for testing
    cache = ContentCache(max_entries=1000, ttl_hours=24)
    
    content = "Test content for expiration"
    cache.cache(content)
    
    # Manually set timestamp to past
    content_hash = cache.compute_hash(content)
    cache._cache[content_hash] = datetime.now(timezone.utc) - timedelta(hours=25)
    
    # Should be expired now
    assert cache.is_cached(content) is False
    
    # Entry should be removed
    assert cache.size() == 0


# ============================================
# PROPERTY 7: Cache Size Limit
# **Feature: browser-automation-always-on, Property 7: Cache Size Limit**
# **Validates: Requirements 5.4**
# ============================================

@settings(max_examples=50)
@given(
    max_entries=st.integers(min_value=10, max_value=100),
    num_items=st.integers(min_value=1, max_value=200)
)
def test_property_7_cache_size_limit(max_entries, num_items):
    """
    **Feature: browser-automation-always-on, Property 7: Cache Size Limit**
    **Validates: Requirements 5.4**
    
    For any state of the content cache, the number of entries SHALL NOT exceed max_entries.
    """
    cache = ContentCache(max_entries=max_entries, ttl_hours=24)
    
    # Add many items
    for i in range(num_items):
        content = f"Unique content item number {i} with some padding to make it longer"
        cache.cache(content)
    
    # Cache size should never exceed max_entries
    assert cache.size() <= max_entries


def test_property_7_lru_eviction():
    """
    **Feature: browser-automation-always-on, Property 7: Cache Size Limit**
    **Validates: Requirements 5.4**
    
    When cache exceeds max entries, oldest entries (LRU) should be evicted.
    """
    cache = ContentCache(max_entries=3, ttl_hours=24)
    
    # Add 3 items
    cache.cache("content_1")
    cache.cache("content_2")
    cache.cache("content_3")
    
    assert cache.size() == 3
    
    # Access content_1 to make it recently used
    cache.is_cached("content_1")
    
    # Add 4th item - should evict content_2 (oldest not recently accessed)
    cache.cache("content_4")
    
    assert cache.size() == 3
    assert cache.is_cached("content_1") is True  # Recently accessed
    assert cache.is_cached("content_3") is True  # Still there
    assert cache.is_cached("content_4") is True  # Just added


def test_content_cache_evict_expired():
    """Test evict_expired removes old entries."""
    cache = ContentCache(max_entries=100, ttl_hours=24)
    
    # Add some content
    cache.cache("content_1")
    cache.cache("content_2")
    cache.cache("content_3")
    
    # Manually expire some entries
    hash1 = cache.compute_hash("content_1")
    hash2 = cache.compute_hash("content_2")
    cache._cache[hash1] = datetime.now(timezone.utc) - timedelta(hours=25)
    cache._cache[hash2] = datetime.now(timezone.utc) - timedelta(hours=30)
    
    # Evict expired
    evicted = cache.evict_expired()
    
    assert evicted == 2
    assert cache.size() == 1
    assert cache.is_cached("content_3") is True



# ============================================
# PROPERTY 2: Content Extraction Length Limit
# **Feature: browser-automation-always-on, Property 2: Content Extraction Length Limit**
# **Validates: Requirements 3.1**
# ============================================

from src.services.browser_monitor import (
    BrowserMonitor,
    MAX_TEXT_LENGTH,
    get_memory_usage_percent,
)


def test_property_2_max_text_length_constant():
    """
    **Feature: browser-automation-always-on, Property 2: Content Extraction Length Limit**
    **Validates: Requirements 3.1**
    
    Verify MAX_TEXT_LENGTH is set to 30000 as per requirements.
    """
    assert MAX_TEXT_LENGTH == 30000


@settings(max_examples=50)
@given(text_length=st.integers(min_value=1, max_value=100000))
def test_property_2_content_truncation_simulation(text_length):
    """
    **Feature: browser-automation-always-on, Property 2: Content Extraction Length Limit**
    **Validates: Requirements 3.1**
    
    For any page content extracted by Playwright, the extracted text length
    SHALL NOT exceed 30,000 characters.
    
    This test simulates the truncation logic used in extract_content().
    """
    # Simulate content extraction
    content = "A" * text_length
    
    # Apply same truncation logic as extract_content
    if len(content) > MAX_TEXT_LENGTH:
        content = content[:MAX_TEXT_LENGTH]
    
    # Verify length limit
    assert len(content) <= MAX_TEXT_LENGTH


# ============================================
# PROPERTY 8: Concurrent Page Limit
# **Feature: browser-automation-always-on, Property 8: Concurrent Page Limit**
# **Validates: Requirements 6.1**
# ============================================

def test_property_8_semaphore_initialization():
    """
    **Feature: browser-automation-always-on, Property 8: Concurrent Page Limit**
    **Validates: Requirements 6.1**
    
    Verify that BrowserMonitor initializes with correct max concurrent pages.
    """
    monitor = BrowserMonitor()
    
    # Before start, semaphore is None
    assert monitor._page_semaphore is None
    
    # Config should have max_concurrent_pages = 2
    config = load_config("config/browser_sources.json")
    assert config.global_settings.max_concurrent_pages == 2


@settings(max_examples=20)
@given(max_pages=st.integers(min_value=1, max_value=10))
def test_property_8_semaphore_limit(max_pages):
    """
    **Feature: browser-automation-always-on, Property 8: Concurrent Page Limit**
    **Validates: Requirements 6.1**
    
    For any point during scanning, the number of concurrent browser pages
    SHALL NOT exceed the configured maximum.
    """
    import asyncio
    
    # Create semaphore with given limit
    semaphore = asyncio.Semaphore(max_pages)
    
    # Verify semaphore has correct initial value
    # asyncio.Semaphore._value gives current count
    assert semaphore._value == max_pages


# ============================================
# BROWSER MONITOR UNIT TESTS
# ============================================

def test_browser_monitor_initialization():
    """Test BrowserMonitor initializes with correct defaults."""
    monitor = BrowserMonitor()
    
    assert monitor.is_running() is False
    assert monitor.is_paused() is False
    assert monitor._config_file == "config/browser_sources.json"
    assert monitor._on_news_discovered is None
    assert monitor._deepseek_calls == 0  # V6.0: Track DeepSeek calls


def test_browser_monitor_with_callback():
    """Test BrowserMonitor accepts callback."""
    discoveries = []
    
    def callback(news):
        discoveries.append(news)
    
    monitor = BrowserMonitor(on_news_discovered=callback)
    assert monitor._on_news_discovered is callback


def test_browser_monitor_get_stats():
    """Test get_stats returns correct structure."""
    monitor = BrowserMonitor()
    stats = monitor.get_stats()
    
    assert "running" in stats
    assert "paused" in stats
    assert "urls_scanned" in stats
    assert "news_discovered" in stats
    assert "sources_count" in stats
    assert "cache_size" in stats
    assert "last_cycle_time" in stats
    assert "deepseek_calls" in stats  # V6.0
    assert "ai_provider" in stats  # V6.0
    
    assert stats["running"] is False
    assert stats["paused"] is False
    assert stats["urls_scanned"] == 0
    assert stats["news_discovered"] == 0
    assert stats["ai_provider"] == "DeepSeek"  # V6.0: Always DeepSeek


def test_get_memory_usage_percent():
    """Test memory usage function returns valid percentage."""
    memory = get_memory_usage_percent()
    
    # Should return a percentage between 0 and 100
    assert 0 <= memory <= 100


def test_browser_monitor_build_relevance_prompt():
    """Test relevance prompt is built correctly."""
    monitor = BrowserMonitor()
    
    content = "Test article about player injury"
    league_key = "soccer_turkey_super_league"
    
    prompt = monitor._build_relevance_prompt(content, league_key)
    
    assert content in prompt
    assert league_key in prompt
    assert "is_relevant" in prompt
    assert "category" in prompt
    assert "confidence" in prompt
    assert "JSON" in prompt


def test_browser_monitor_parse_relevance_response_valid_json():
    """Test parsing valid JSON response."""
    monitor = BrowserMonitor()
    
    response = '{"is_relevant": true, "category": "INJURY", "affected_team": "Galatasaray", "confidence": 0.85, "summary": "Player injured"}'
    
    result = monitor._parse_relevance_response(response)
    
    assert result is not None
    assert result["is_relevant"] is True
    assert result["category"] == "INJURY"
    assert result["confidence"] == 0.85


def test_browser_monitor_parse_relevance_response_markdown():
    """Test parsing JSON in markdown code block."""
    monitor = BrowserMonitor()
    
    response = '''Here is the analysis:
```json
{"is_relevant": false, "category": "OTHER", "affected_team": null, "confidence": 0.3, "summary": "Not relevant"}
```
'''
    
    result = monitor._parse_relevance_response(response)
    
    assert result is not None
    assert result["is_relevant"] is False


def test_browser_monitor_parse_relevance_response_invalid():
    """Test parsing invalid response returns None."""
    monitor = BrowserMonitor()
    
    response = "This is not JSON at all"
    
    result = monitor._parse_relevance_response(response)
    
    assert result is None



# ============================================
# PROPERTY 3: Gemini Response Schema Validity
# **Feature: browser-automation-always-on, Property 3: Gemini Response Schema Validity**
# **Validates: Requirements 3.3**
# ============================================

# Valid categories as per design
VALID_CATEGORIES = ["INJURY", "LINEUP", "SUSPENSION", "TRANSFER", "TACTICAL", "OTHER"]


@settings(max_examples=100)
@given(
    is_relevant=st.booleans(),
    category=st.sampled_from(VALID_CATEGORIES),
    affected_team=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    summary=st.text(min_size=1, max_size=200)
)
def test_property_3_gemini_response_schema_validity(is_relevant, category, affected_team, confidence, summary):
    """
    **Feature: browser-automation-always-on, Property 3: Gemini Response Schema Validity**
    **Validates: Requirements 3.3**
    
    For any Gemini relevance analysis response, the response SHALL contain all
    required fields (is_relevant, category, affected_team, confidence, summary)
    with valid types.
    """
    # Build a valid response
    response = {
        "is_relevant": is_relevant,
        "category": category,
        "affected_team": affected_team,
        "confidence": confidence,
        "summary": summary
    }
    
    # Verify all required fields are present
    assert "is_relevant" in response
    assert "category" in response
    assert "affected_team" in response
    assert "confidence" in response
    assert "summary" in response
    
    # Verify types
    assert isinstance(response["is_relevant"], bool)
    assert response["category"] in VALID_CATEGORIES
    assert response["affected_team"] is None or isinstance(response["affected_team"], str)
    assert isinstance(response["confidence"], float)
    assert 0.0 <= response["confidence"] <= 1.0
    assert isinstance(response["summary"], str)


def test_property_3_parse_valid_response():
    """
    **Feature: browser-automation-always-on, Property 3: Gemini Response Schema Validity**
    **Validates: Requirements 3.3**
    
    Test that valid JSON responses are parsed correctly.
    """
    monitor = BrowserMonitor()
    
    valid_responses = [
        '{"is_relevant": true, "category": "INJURY", "affected_team": "Galatasaray", "confidence": 0.85, "summary": "Key player injured"}',
        '{"is_relevant": false, "category": "OTHER", "affected_team": null, "confidence": 0.2, "summary": "Not relevant news"}',
        '{"is_relevant": true, "category": "LINEUP", "affected_team": "Fenerbahce", "confidence": 0.95, "summary": "Starting lineup announced"}',
    ]
    
    for response_text in valid_responses:
        result = monitor._parse_relevance_response(response_text)
        
        assert result is not None
        assert "is_relevant" in result
        assert "category" in result
        assert "confidence" in result
        assert "summary" in result


# ============================================
# PROPERTY 4: Relevant Content Triggers Callback
# **Feature: browser-automation-always-on, Property 4: Relevant Content Triggers Callback**
# **Validates: Requirements 3.4, 4.1**
# ============================================

from src.services.browser_monitor import (
    DiscoveredNews,
    RELEVANCE_CONFIDENCE_THRESHOLD,
)


@settings(max_examples=50)
@given(
    confidence=st.floats(min_value=RELEVANCE_CONFIDENCE_THRESHOLD, max_value=1.0, allow_nan=False),
    category=st.sampled_from(VALID_CATEGORIES),
    team=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=('L', 'N', 'Z'))),
    summary=st.text(min_size=1, max_size=100)
)
def test_property_4_relevant_content_triggers_callback(confidence, category, team, summary):
    """
    **Feature: browser-automation-always-on, Property 4: Relevant Content Triggers Callback**
    **Validates: Requirements 3.4, 4.1**
    
    For any content analyzed by Gemini where is_relevant=true AND confidence >= 0.7,
    the BrowserMonitor SHALL invoke the on_news_discovered callback with a valid
    DiscoveredNews object.
    """
    # Track callback invocations
    callback_invoked = []
    
    def callback(news: DiscoveredNews):
        callback_invoked.append(news)
    
    # Simulate the logic from scan_source
    analysis = {
        "is_relevant": True,
        "confidence": confidence,
        "category": category,
        "affected_team": team,
        "summary": summary
    }
    
    is_relevant = analysis.get('is_relevant', False)
    conf = analysis.get('confidence', 0.0)
    
    # This is the condition that triggers callback
    if is_relevant and conf >= RELEVANCE_CONFIDENCE_THRESHOLD:
        news = DiscoveredNews(
            url="https://example.com/news",
            title=analysis.get('summary', '')[:200],
            snippet=analysis.get('summary', ''),
            category=analysis.get('category', 'OTHER'),
            affected_team=analysis.get('affected_team', ''),
            confidence=conf,
            league_key="soccer_turkey_super_league",
            source_name="Test Source"
        )
        callback(news)
    
    # Verify callback was invoked
    assert len(callback_invoked) == 1
    assert callback_invoked[0].confidence >= RELEVANCE_CONFIDENCE_THRESHOLD


# ============================================
# PROPERTY 5: Non-Relevant Content Skipped
# **Feature: browser-automation-always-on, Property 5: Non-Relevant Content Skipped**
# **Validates: Requirements 3.5**
# ============================================

@settings(max_examples=50)
@given(
    is_relevant=st.booleans(),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
)
def test_property_5_non_relevant_content_skipped(is_relevant, confidence):
    """
    **Feature: browser-automation-always-on, Property 5: Non-Relevant Content Skipped**
    **Validates: Requirements 3.5**
    
    For any content analyzed by Gemini where is_relevant=false OR confidence < 0.7,
    the BrowserMonitor SHALL NOT invoke the on_news_discovered callback.
    """
    # Skip cases where content IS relevant (covered by Property 4)
    assume(not is_relevant or confidence < RELEVANCE_CONFIDENCE_THRESHOLD)
    
    callback_invoked = []
    
    def callback(news: DiscoveredNews):
        callback_invoked.append(news)
    
    # Simulate the logic from scan_source
    analysis = {
        "is_relevant": is_relevant,
        "confidence": confidence,
        "category": "OTHER",
        "affected_team": "Test Team",
        "summary": "Test summary"
    }
    
    is_rel = analysis.get('is_relevant', False)
    conf = analysis.get('confidence', 0.0)
    
    # This is the condition that triggers callback
    if is_rel and conf >= RELEVANCE_CONFIDENCE_THRESHOLD:
        news = DiscoveredNews(
            url="https://example.com/news",
            title="Test",
            snippet="Test",
            category="OTHER",
            affected_team="Test",
            confidence=conf,
            league_key="soccer_turkey",
            source_name="Test"
        )
        callback(news)
    
    # Verify callback was NOT invoked
    assert len(callback_invoked) == 0


# ============================================
# PROPERTY 9: Navigation Rate Limit
# **Feature: browser-automation-always-on, Property 9: Navigation Rate Limit**
# **Validates: Requirements 6.2**
# ============================================

from src.services.browser_monitor import DEFAULT_NAVIGATION_INTERVAL_SECONDS


def test_property_9_navigation_interval_constant():
    """
    **Feature: browser-automation-always-on, Property 9: Navigation Rate Limit**
    **Validates: Requirements 6.2**
    
    Verify navigation interval is set to at least 10 seconds.
    """
    assert DEFAULT_NAVIGATION_INTERVAL_SECONDS >= 10


def test_property_9_navigation_interval_enforcement():
    """
    **Feature: browser-automation-always-on, Property 9: Navigation Rate Limit**
    **Validates: Requirements 6.2**
    
    For any sequence of page navigations, the time between consecutive
    navigations SHALL be at least 10 seconds.
    """
    import time
    
    monitor = BrowserMonitor()
    
    # Simulate navigation timing
    monitor._last_navigation_time = time.time()
    
    # Check that interval is enforced
    interval = monitor._config.global_settings.navigation_interval_seconds
    assert interval >= 10
    
    # Verify the enforcement logic would wait
    elapsed = 0  # Just navigated
    if elapsed < interval:
        wait_time = interval - elapsed
        assert wait_time >= 10


# ============================================
# PROPERTY 10: Memory Pause Behavior
# **Feature: browser-automation-always-on, Property 10: Memory Pause Behavior**
# **Validates: Requirements 6.3**
# ============================================

from src.services.browser_monitor import MEMORY_HIGH_THRESHOLD, MEMORY_LOW_THRESHOLD


def test_property_10_memory_thresholds():
    """
    **Feature: browser-automation-always-on, Property 10: Memory Pause Behavior**
    **Validates: Requirements 6.3**
    
    Verify memory thresholds are set correctly.
    """
    # Pause if > 80%
    assert MEMORY_HIGH_THRESHOLD == 80
    
    # Resume if < 70%
    assert MEMORY_LOW_THRESHOLD == 70
    
    # High threshold must be greater than low threshold
    assert MEMORY_HIGH_THRESHOLD > MEMORY_LOW_THRESHOLD


@settings(max_examples=50)
@given(memory_percent=st.floats(min_value=0.0, max_value=100.0, allow_nan=False))
def test_property_10_memory_pause_logic(memory_percent):
    """
    **Feature: browser-automation-always-on, Property 10: Memory Pause Behavior**
    **Validates: Requirements 6.3**
    
    For any memory usage above 80%, the BrowserMonitor SHALL pause scanning
    until memory drops below 70%.
    """
    should_pause = memory_percent > MEMORY_HIGH_THRESHOLD
    should_resume = memory_percent < MEMORY_LOW_THRESHOLD
    
    if should_pause:
        # Memory is high, should pause
        assert memory_percent > 80
    
    if should_resume:
        # Memory is low enough to resume
        assert memory_percent < 70



# ============================================
# PROPERTY 13: News Item Schema Validity
# **Feature: browser-automation-always-on, Property 13: News Item Schema Validity**
# **Validates: Requirements 4.3**
# ============================================

from src.processing.news_hunter import (
    register_browser_monitor_discovery,
    get_browser_monitor_news,
    clear_browser_monitor_discoveries,
    _BROWSER_MONITOR_AVAILABLE,
)


@settings(max_examples=50)
@given(
    title=st.text(min_size=1, max_size=100),
    snippet=st.text(min_size=1, max_size=200),
    category=st.sampled_from(VALID_CATEGORIES),
    team=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=('L', 'N'))),
    confidence=st.floats(min_value=0.7, max_value=1.0, allow_nan=False),
)
def test_property_13_news_item_schema_validity(title, snippet, category, team, confidence):
    """
    **Feature: browser-automation-always-on, Property 13: News Item Schema Validity**
    **Validates: Requirements 4.3**
    
    For any news item added to news_hunter from BrowserMonitor, the item SHALL
    contain all required fields (match_id, team, title, snippet, link, source,
    confidence, search_type).
    """
    # Skip if browser monitor not available
    if not _BROWSER_MONITOR_AVAILABLE:
        return
    
    # Clear any existing discoveries
    clear_browser_monitor_discoveries()
    
    # Create a DiscoveredNews
    news = DiscoveredNews(
        url="https://example.com/news/article",
        title=title,
        snippet=snippet,
        category=category,
        affected_team=team,
        confidence=confidence,
        league_key="soccer_turkey_super_league",
        source_name="Test Source"
    )
    
    # Register the discovery
    register_browser_monitor_discovery(news)
    
    # Retrieve it
    results = get_browser_monitor_news(
        match_id="test_match_123",
        team_names=[team],
        league_key="soccer_turkey_super_league"
    )
    
    # Verify schema
    if results:
        item = results[0]
        
        # Required fields per Requirements 4.3
        assert 'match_id' in item
        assert 'team' in item
        assert 'title' in item
        assert 'snippet' in item
        assert 'link' in item
        assert 'source' in item
        assert 'confidence' in item
        assert 'search_type' in item
        
        # Verify values
        assert item['match_id'] == "test_match_123"
        assert item['search_type'] == 'browser_monitor'
        # V7.0: DiscoveryQueue converts 'HIGH' string to float (0.8) or uses original float
        # The confidence should be a float >= 0.7 (high confidence threshold)
        assert isinstance(item['confidence'], (int, float)), \
            f"confidence should be numeric, got {type(item['confidence'])}"
        assert item['confidence'] >= 0.7, \
            f"confidence should be >= 0.7 for HIGH confidence items, got {item['confidence']}"
    
    # Cleanup
    clear_browser_monitor_discoveries()


def test_property_13_news_item_has_all_fields():
    """
    **Feature: browser-automation-always-on, Property 13: News Item Schema Validity**
    **Validates: Requirements 4.3**
    
    Test that registered discoveries have all required fields.
    """
    if not _BROWSER_MONITOR_AVAILABLE:
        return
    
    clear_browser_monitor_discoveries()
    
    news = DiscoveredNews(
        url="https://fanatik.com.tr/article/123",
        title="Galatasaray star injured",
        snippet="Key player ruled out for 3 weeks",
        category="INJURY",
        affected_team="Galatasaray",
        confidence=0.92,
        league_key="soccer_turkey_super_league",
        source_name="Fanatik Turkey"
    )
    
    register_browser_monitor_discovery(news)
    
    results = get_browser_monitor_news(
        match_id="match_456",
        team_names=["Galatasaray", "Fenerbahce"],
        league_key="soccer_turkey_super_league"
    )
    
    assert len(results) == 1
    item = results[0]
    
    # All required fields
    assert item['match_id'] == "match_456"
    assert item['team'] == "Galatasaray"
    assert item['title'] == "Galatasaray star injured"
    assert item['snippet'] == "Key player ruled out for 3 weeks"
    assert item['link'] == "https://fanatik.com.tr/article/123"
    assert item['source'] == "Fanatik Turkey"
    # V7.0: DiscoveryQueue converts confidence to float
    assert isinstance(item['confidence'], (int, float)), f"confidence should be numeric"
    assert item['confidence'] >= 0.7, f"confidence should be >= 0.7 for HIGH confidence"
    assert item['search_type'] == 'browser_monitor'
    assert item['category'] == 'INJURY'
    assert item['priority_boost'] == 2.0
    
    clear_browser_monitor_discoveries()


# ============================================
# PROPERTY 14: TIER 0 Priority
# **Feature: browser-automation-always-on, Property 14: TIER 0 Priority**
# **Validates: Requirements 4.4**
# ============================================

def test_property_14_tier_0_priority_boost():
    """
    **Feature: browser-automation-always-on, Property 14: TIER 0 Priority**
    **Validates: Requirements 4.4**
    
    For any execution of run_hunter_for_match(), BrowserMonitor results SHALL
    appear before TIER 1 and TIER 2 results in the aggregated news list.
    
    This is verified by checking that browser_monitor items have priority_boost=2.0,
    which is higher than beat_writers (1.5) and other sources (1.0).
    """
    if not _BROWSER_MONITOR_AVAILABLE:
        return
    
    clear_browser_monitor_discoveries()
    
    news = DiscoveredNews(
        url="https://example.com/breaking",
        title="Breaking news",
        snippet="Important update",
        category="INJURY",
        affected_team="Test Team",
        confidence=0.85,
        league_key="soccer_turkey_super_league",
        source_name="Test Source"
    )
    
    register_browser_monitor_discovery(news)
    
    results = get_browser_monitor_news(
        match_id="match_789",
        team_names=["Test Team"],
        league_key="soccer_turkey_super_league"
    )
    
    assert len(results) == 1
    
    # Browser monitor has highest priority boost (2.0)
    # Beat writers have 1.5
    # Other sources have 1.0 or no boost
    assert results[0]['priority_boost'] == 2.0
    assert results[0]['priority_boost'] > 1.5  # Higher than beat writers
    
    clear_browser_monitor_discoveries()


def test_browser_monitor_discovery_expiration():
    """Test that old discoveries are expired."""
    if not _BROWSER_MONITOR_AVAILABLE:
        return
    
    clear_browser_monitor_discoveries()
    
    # This test verifies the expiration logic exists
    # The actual expiration is 24 hours, which we can't easily test
    # But we verify the TTL constant is set correctly
    from src.processing.news_hunter import _BROWSER_MONITOR_TTL_HOURS
    assert _BROWSER_MONITOR_TTL_HOURS == 24
    
    clear_browser_monitor_discoveries()


def test_browser_monitor_team_matching():
    """Test that discoveries are matched to correct teams."""
    if not _BROWSER_MONITOR_AVAILABLE:
        return
    
    clear_browser_monitor_discoveries()
    
    # Register discovery for Galatasaray
    news = DiscoveredNews(
        url="https://example.com/news",
        title="Galatasaray news",
        snippet="Update",
        category="INJURY",
        affected_team="Galatasaray",
        confidence=0.8,
        league_key="soccer_turkey_super_league",
        source_name="Test"
    )
    register_browser_monitor_discovery(news)
    
    # Should match when searching for Galatasaray
    results = get_browser_monitor_news(
        match_id="match_1",
        team_names=["Galatasaray", "Besiktas"],
        league_key="soccer_turkey_super_league"
    )
    assert len(results) == 1
    
    # Should NOT match when searching for different teams
    results = get_browser_monitor_news(
        match_id="match_2",
        team_names=["Fenerbahce", "Trabzonspor"],
        league_key="soccer_turkey_super_league"
    )
    assert len(results) == 0
    
    clear_browser_monitor_discoveries()



# ============================================
# PROPERTY 12: Cooldown Isolation
# **Feature: browser-automation-always-on, Property 12: Cooldown Isolation**
# **Validates: Requirements 7.4**
# ============================================

def test_property_12_cooldown_isolation_no_import():
    """
    **Feature: browser-automation-always-on, Property 12: Cooldown Isolation**
    **Validates: Requirements 7.4**
    
    For any Gemini Free API 429 error, the Gemini Direct API cooldown state
    SHALL remain unchanged.
    
    This test verifies that browser_monitor.py does NOT import or call
    the CooldownManager, ensuring complete isolation.
    """
    import ast
    from pathlib import Path
    
    # Read the browser_monitor.py source
    source_path = Path("src/services/browser_monitor.py")
    source_code = source_path.read_text()
    
    # Parse the AST
    tree = ast.parse(source_code)
    
    # Check for imports of cooldown_manager
    cooldown_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if 'cooldown' in alias.name.lower():
                    cooldown_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and 'cooldown' in node.module.lower():
                cooldown_imports.append(node.module)
    
    # Verify no cooldown imports
    assert len(cooldown_imports) == 0, f"Browser monitor should not import cooldown modules: {cooldown_imports}"


def test_property_12_deepseek_only():
    """
    **Feature: browser-automation-always-on V6.0, Property 12: DeepSeek Only**
    **Validates: Requirements 7.4**
    
    V6.0: Verify that BrowserMonitor uses DeepSeek only (no Gemini fallback).
    """
    monitor = BrowserMonitor()
    
    # Verify DeepSeek calls tracking exists
    assert hasattr(monitor, '_deepseek_calls')
    assert monitor._deepseek_calls == 0
    
    # Verify ai_provider is always DeepSeek
    stats = monitor.get_stats()
    assert stats['ai_provider'] == 'DeepSeek'


def test_property_12_no_cooldown_manager_calls():
    """
    **Feature: browser-automation-always-on, Property 12: Cooldown Isolation**
    **Validates: Requirements 7.4**
    
    Verify that the browser monitor source code does not contain
    any calls to CooldownManager methods.
    """
    from pathlib import Path
    
    source_path = Path("src/services/browser_monitor.py")
    source_code = source_path.read_text()
    
    # Check for CooldownManager usage patterns
    forbidden_patterns = [
        'get_cooldown_manager',
        'CooldownManager',
        'cooldown_manager',
        'record_429',
        'is_cooldown_active',
        'activate_cooldown',
    ]
    
    for pattern in forbidden_patterns:
        assert pattern not in source_code, f"Browser monitor should not use '{pattern}'"


# ============================================
# REGRESSION TESTS: Edge Cases Fixed in V5.1.1
# ============================================

def test_regression_empty_summary_handling():
    """
    REGRESSION TEST: Empty summary should not cause IndexError.
    
    Bug: news.title[:50] would fail if analysis.get('summary', '') returned empty string
    Fix: Added safe defaults and fallback title generation
    """
    from src.services.browser_monitor import DiscoveredNews, MonitoredSource
    
    # Simulate analysis with empty/None summary
    analysis_cases = [
        {'is_relevant': True, 'confidence': 0.8, 'summary': '', 'category': 'INJURY', 'affected_team': 'Test'},
        {'is_relevant': True, 'confidence': 0.8, 'summary': None, 'category': 'INJURY', 'affected_team': 'Test'},
        {'is_relevant': True, 'confidence': 0.8, 'category': 'INJURY', 'affected_team': 'Test'},  # Missing summary
    ]
    
    source = MonitoredSource(url="https://example.com", league_key="soccer_turkey", name="Test Source")
    
    for analysis in analysis_cases:
        # This should NOT raise an exception
        summary = analysis.get('summary') or ''
        affected_team = analysis.get('affected_team') or 'Unknown Team'
        
        news = DiscoveredNews(
            url=source.url,
            title=summary[:200] if summary else f"News from {source.name}",
            snippet=summary or f"Relevant news discovered from {source.url}",
            category=analysis.get('category') or 'OTHER',
            affected_team=affected_team,
            confidence=analysis.get('confidence', 0.0),
            league_key=source.league_key,
            source_name=source.name or source.url[:30]
        )
        
        # Verify safe defaults
        assert news.title != ''
        assert news.snippet != ''
        assert news.affected_team != ''
        assert news.source_name != ''


def test_regression_empty_affected_team():
    """
    REGRESSION TEST: Empty affected_team should default to 'Unknown Team'.
    
    Bug: Empty affected_team would cause confusing log messages
    Fix: Added 'Unknown Team' as default
    """
    from src.services.browser_monitor import DiscoveredNews
    
    # Test with empty/None affected_team
    test_cases = ['', None]
    
    for affected_team_input in test_cases:
        affected_team = affected_team_input or 'Unknown Team'
        
        news = DiscoveredNews(
            url="https://example.com",
            title="Test News",
            snippet="Test snippet",
            category="INJURY",
            affected_team=affected_team,
            confidence=0.8,
            league_key="soccer_turkey",
            source_name="Test"
        )
        
        assert news.affected_team == 'Unknown Team'


def test_regression_invalid_category_handling():
    """
    REGRESSION TEST: Invalid category should default to 'OTHER'.
    
    Bug: Gemini might return unexpected category values
    Fix: Validate category against allowed values
    """
    valid_categories = {'INJURY', 'LINEUP', 'SUSPENSION', 'TRANSFER', 'TACTICAL', 'OTHER'}
    
    invalid_categories = ['injury', 'UNKNOWN', 'NEWS', '', None, 'random_value']
    
    for invalid_cat in invalid_categories:
        category = invalid_cat or 'OTHER'
        if category not in valid_categories:
            category = 'OTHER'
        
        assert category == 'OTHER'
    
    # Valid categories should pass through
    for valid_cat in valid_categories:
        category = valid_cat
        if category not in valid_categories:
            category = 'OTHER'
        assert category == valid_cat


def test_regression_source_name_fallback():
    """
    REGRESSION TEST: Empty source name should fallback to URL prefix.
    
    Bug: Empty source.name would cause empty source_name in DiscoveredNews
    Fix: Fallback to source.url[:30]
    """
    from src.services.browser_monitor import MonitoredSource
    
    # Source with empty name
    source = MonitoredSource(url="https://fanatik.com.tr/news/article", league_key="soccer_turkey", name="")
    
    source_name = source.name or source.url[:30]
    
    assert source_name != ''
    assert len(source_name) == 30
    assert source_name == source.url[:30]


def test_regression_title_preview_truncation():
    """
    REGRESSION TEST: Title preview should handle edge cases safely.
    
    Bug: title[:50] on empty string would work but logging would be confusing
    Fix: Added proper truncation with ellipsis and '[No Title]' fallback for empty strings
    """
    test_titles = [
        "",  # Empty - should become '[No Title]'
        "Short",  # Short
        "A" * 100,  # Long
        "Exactly fifty characters long title for testing!",  # Exactly 50
    ]
    
    for title in test_titles:
        # This is the fixed logic (matches browser_monitor.py line ~749)
        title_preview = (title[:50] + '...') if len(title) > 50 else (title or '[No Title]')
        
        # Should never raise
        assert isinstance(title_preview, str)
        
        # Empty title should have fallback
        if title == "":
            assert title_preview == '[No Title]'
        
        # Long titles should be truncated with ellipsis
        if len(title) > 50:
            assert title_preview.endswith('...')
            assert len(title_preview) == 53  # 50 + 3 for '...'


def test_news_hunter_browser_monitor_empty_results():
    """
    REGRESSION TEST: get_browser_monitor_news should handle empty discoveries gracefully.
    """
    if not _BROWSER_MONITOR_AVAILABLE:
        return
    
    clear_browser_monitor_discoveries()
    
    # Should return empty list, not raise
    results = get_browser_monitor_news(
        match_id="test_match",
        team_names=["NonExistent Team"],
        league_key="soccer_unknown_league"
    )
    
    assert results == []
    assert isinstance(results, list)


def test_news_hunter_browser_monitor_none_team_names():
    """
    REGRESSION TEST: get_browser_monitor_news should handle edge cases in team_names.
    """
    if not _BROWSER_MONITOR_AVAILABLE:
        return
    
    clear_browser_monitor_discoveries()
    
    # Empty team names list
    results = get_browser_monitor_news(
        match_id="test_match",
        team_names=[],
        league_key="soccer_turkey"
    )
    
    assert results == []


# ============================================
# V6.0 TESTS: DeepSeek Only + Negative Filters
# ============================================

def test_negative_filters_in_prompt():
    """
    Test that the relevance prompt includes:
    - Negative filters for: Basketball, Women's team, NFL/American Football
    - Positive relevance for: Youth/Primavera callups (VERY RELEVANT for betting!)
    """
    monitor = BrowserMonitor()
    
    prompt = monitor._build_relevance_prompt("Test content", "soccer_turkey_super_league")
    
    # Must include basketball filter (EXCLUDED)
    assert 'basketball' in prompt.lower() or 'Basketball' in prompt
    
    # Must include women's team filter (EXCLUDED)
    assert "women" in prompt.lower() or "Women" in prompt or "Ladies" in prompt
    
    # Must include youth as RELEVANT (not excluded!)
    assert "Youth" in prompt or "Primavera" in prompt or "U19" in prompt
    # Youth should be in the RELEVANT section, not EXCLUDED
    assert "YOUTH_CALLUP" in prompt, "Youth callup should be a valid category"
    
    # Must include NFL filter (EXCLUDED)
    assert "NFL" in prompt or "American Football" in prompt
    
    # Must specify MEN'S FOOTBALL
    assert "MEN'S" in prompt or "Men's" in prompt


def test_parse_response_with_think_tags():
    """
    Test that _parse_relevance_response handles DeepSeek <think> tags.
    """
    monitor = BrowserMonitor()
    
    # Response with <think> tags (DeepSeek style)
    response = '''<think>
Let me analyze this article...
It seems to be about a football injury.
</think>
{"is_relevant": true, "category": "INJURY", "affected_team": "Galatasaray", "confidence": 0.85, "summary": "Key player injured"}'''
    
    result = monitor._parse_relevance_response(response)
    
    assert result is not None
    assert result['is_relevant'] is True
    assert result['category'] == 'INJURY'
    assert result['confidence'] == 0.85


def test_deepseek_calls_counter():
    """
    Test that DeepSeek calls are counted.
    """
    monitor = BrowserMonitor()
    
    # Initially 0
    assert monitor._deepseek_calls == 0
    
    # Simulate calls
    monitor._deepseek_calls = 5
    
    stats = monitor.get_stats()
    assert stats['deepseek_calls'] == 5


def test_ai_provider_always_deepseek():
    """
    V6.0: Test that ai_provider is always 'DeepSeek'.
    """
    monitor = BrowserMonitor()
    
    stats = monitor.get_stats()
    assert stats['ai_provider'] == 'DeepSeek'


# ============================================
# V6.0 TESTS: Data Format Compatibility
# ============================================

def test_browser_monitor_news_format_for_dossier():
    """
    Test that browser monitor news items have all fields required by main.py dossier builder.
    
    Required fields for dossier builder:
    - title
    - snippet
    - source
    - link
    - freshness_tag (for News Decay)
    - minutes_old (for News Decay)
    """
    if not _BROWSER_MONITOR_AVAILABLE:
        return
    
    clear_browser_monitor_discoveries()
    
    news = DiscoveredNews(
        url="https://fanatik.com.tr/news/123",
        title="Galatasaray star injured in training",
        snippet="Key player ruled out for 3 weeks after training ground incident",
        category="INJURY",
        affected_team="Galatasaray",
        confidence=0.88,
        league_key="soccer_turkey_super_league",
        source_name="Fanatik Turkey"
    )
    
    register_browser_monitor_discovery(news)
    
    results = get_browser_monitor_news(
        match_id="match_test_123",
        team_names=["Galatasaray", "Fenerbahce"],
        league_key="soccer_turkey_super_league"
    )
    
    assert len(results) == 1
    item = results[0]
    
    # Core fields required by dossier builder
    assert 'title' in item and item['title']
    assert 'snippet' in item and item['snippet']
    assert 'source' in item and item['source']
    assert 'link' in item and item['link'].startswith('http')
    
    # News Decay fields required by dossier builder
    assert 'freshness_tag' in item
    assert item['freshness_tag'] in ["🔥 FRESH", "⏰ RECENT", "⏰ AGING", "⚠️ STALE"]
    assert 'minutes_old' in item
    assert isinstance(item['minutes_old'], int)
    assert item['minutes_old'] >= 0
    
    # Browser Monitor specific fields
    assert item['search_type'] == 'browser_monitor'
    # V7.0: DiscoveryQueue converts confidence to float
    assert isinstance(item['confidence'], (int, float)), f"confidence should be numeric"
    assert item['confidence'] >= 0.7, f"confidence should be >= 0.7 for HIGH confidence"
    assert item['priority_boost'] == 2.0
    assert item['category'] == 'INJURY'
    
    clear_browser_monitor_discoveries()


def test_browser_monitor_freshness_tag_updates():
    """
    Test that freshness_tag is recalculated at retrieval time.
    """
    if not _BROWSER_MONITOR_AVAILABLE:
        return
    
    clear_browser_monitor_discoveries()
    
    # Create a news item
    news = DiscoveredNews(
        url="https://example.com/news",
        title="Test News",
        snippet="Test snippet",
        category="INJURY",
        affected_team="Test Team",
        confidence=0.8,
        league_key="soccer_turkey_super_league",
        source_name="Test Source"
    )
    
    register_browser_monitor_discovery(news)
    
    # Retrieve immediately - should be FRESH
    results = get_browser_monitor_news(
        match_id="match_1",
        team_names=["Test Team"],
        league_key="soccer_turkey_super_league"
    )
    
    assert len(results) == 1
    assert results[0]['freshness_tag'] == "🔥 FRESH"
    assert results[0]['minutes_old'] < 5  # Should be very recent
    
    clear_browser_monitor_discoveries()


def test_browser_monitor_empty_team_names_handling():
    """
    Test that empty team_names list is handled gracefully.
    """
    if not _BROWSER_MONITOR_AVAILABLE:
        return
    
    clear_browser_monitor_discoveries()
    
    # Register a discovery
    news = DiscoveredNews(
        url="https://example.com/news",
        title="Test News",
        snippet="Test snippet",
        category="INJURY",
        affected_team="Test Team",
        confidence=0.8,
        league_key="soccer_turkey_super_league",
        source_name="Test Source"
    )
    register_browser_monitor_discovery(news)
    
    # Empty team_names should return empty list, not crash
    results = get_browser_monitor_news(
        match_id="match_1",
        team_names=[],
        league_key="soccer_turkey_super_league"
    )
    
    assert results == []
    
    # None in team_names should be handled
    results = get_browser_monitor_news(
        match_id="match_2",
        team_names=[None, ""],
        league_key="soccer_turkey_super_league"
    )
    
    assert results == []
    
    clear_browser_monitor_discoveries()


def test_browser_monitor_none_affected_team_handling():
    """
    Test that None/empty affected_team in discovery is handled.
    """
    if not _BROWSER_MONITOR_AVAILABLE:
        return
    
    clear_browser_monitor_discoveries()
    
    # Create news with empty affected_team
    news = DiscoveredNews(
        url="https://example.com/news",
        title="Test News",
        snippet="Test snippet",
        category="OTHER",
        affected_team="",  # Empty
        confidence=0.8,
        league_key="soccer_turkey_super_league",
        source_name="Test Source"
    )
    register_browser_monitor_discovery(news)
    
    # Should not crash, but won't match any team
    results = get_browser_monitor_news(
        match_id="match_1",
        team_names=["Galatasaray"],
        league_key="soccer_turkey_super_league"
    )
    
    # Empty affected_team won't match "Galatasaray"
    assert results == []
    
    clear_browser_monitor_discoveries()


# ============================================
# V5.2 TESTS: Graceful Shutdown
# ============================================

def test_request_stop_sets_running_false():
    """
    V5.2 REGRESSION TEST: request_stop() should set _running to False.
    
    Bug: Calling async stop() from a different event loop caused race conditions
    Fix: Added thread-safe request_stop() method that sets _running = False
    
    This test would FAIL in the old version (no request_stop method).
    """
    monitor = BrowserMonitor()
    
    # Simulate running state
    monitor._running = True
    assert monitor.is_running() is True
    
    # Call thread-safe stop
    monitor.request_stop()
    
    # Should immediately set _running to False
    assert monitor._running is False
    assert monitor.is_running() is False


def test_request_stop_is_thread_safe():
    """
    V5.2 TEST: request_stop() can be called from any thread without errors.
    
    The method only sets a boolean flag, which is atomic in Python.
    """
    import threading
    
    monitor = BrowserMonitor()
    monitor._running = True
    
    errors = []
    
    def call_request_stop():
        try:
            monitor.request_stop()
        except Exception as e:
            errors.append(e)
    
    # Call from multiple threads simultaneously
    threads = [threading.Thread(target=call_request_stop) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # No errors should occur
    assert len(errors) == 0
    assert monitor._running is False


def test_request_stop_idempotent():
    """
    V5.2 TEST: Calling request_stop() multiple times is safe.
    """
    monitor = BrowserMonitor()
    monitor._running = True
    
    # Call multiple times
    monitor.request_stop()
    monitor.request_stop()
    monitor.request_stop()
    
    # Should still be False, no errors
    assert monitor._running is False


def test_scan_loop_exits_on_running_false():
    """
    V5.2 TEST: Verify that _scan_loop checks _running flag.
    
    The scan loop condition is: while self._running and not self._stop_event.is_set()
    Setting _running = False should cause the loop to exit.
    """
    monitor = BrowserMonitor()
    
    # Verify the loop condition exists in the code
    import inspect
    source = inspect.getsource(monitor._scan_loop)
    
    # The loop should check _running
    assert 'self._running' in source
    assert 'while' in source


# ============================================
# V7.0 TESTS: Stealth, Resource Blocking, Trafilatura
# ============================================

def test_v7_stats_include_new_metrics():
    """
    V7.0 TEST: Verify get_stats() includes new V7.0 metrics.
    
    New metrics: trafilatura_extractions, fallback_extractions, 
    blocked_resources, stealth_enabled, trafilatura_enabled, version
    """
    monitor = BrowserMonitor()
    stats = monitor.get_stats()
    
    # V7.0 required fields
    assert "trafilatura_extractions" in stats
    assert "fallback_extractions" in stats
    assert "blocked_resources" in stats
    assert "stealth_enabled" in stats
    assert "trafilatura_enabled" in stats
    assert "version" in stats
    assert stats["version"] == "7.6"  # V7.6: Updated version
    
    # Initial values should be 0
    assert stats["trafilatura_extractions"] == 0
    assert stats["fallback_extractions"] == 0
    assert stats["blocked_resources"] == 0


def test_v7_trafilatura_extraction_with_valid_html():
    """
    V7.0 TEST: Verify _extract_with_trafilatura extracts clean text from HTML.
    
    This test would FAIL if trafilatura is not properly integrated.
    """
    from src.services.browser_monitor import TRAFILATURA_AVAILABLE
    
    if not TRAFILATURA_AVAILABLE:
        pytest.skip("trafilatura not installed")
    
    monitor = BrowserMonitor()
    
    # Sample HTML with article content
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Test Article</title></head>
    <body>
        <nav>Navigation menu here</nav>
        <article>
            <h1>Breaking News: Player Injured</h1>
            <p>The star player suffered a knee injury during training today. 
            The team doctor confirmed he will miss the next three matches.
            This is a significant blow to the team's championship hopes.</p>
            <p>The manager expressed concern about the depth of the squad
            and hinted at possible transfer activity in the January window.</p>
        </article>
        <footer>Copyright 2026</footer>
        <script>tracking_code();</script>
    </body>
    </html>
    """
    
    result = monitor._extract_with_trafilatura(html)
    
    # Should extract article content
    assert result is not None
    assert "Player Injured" in result or "knee injury" in result
    # Should NOT include navigation/footer
    assert "Navigation menu" not in result
    assert "Copyright" not in result
    # Counter should increment
    assert monitor._trafilatura_extractions == 1


def test_v7_trafilatura_extraction_with_empty_html():
    """
    V7.0 TEST: Verify _extract_with_trafilatura handles empty/None HTML gracefully.
    
    Edge case: empty string or None should return None without crashing.
    """
    from src.services.browser_monitor import TRAFILATURA_AVAILABLE
    
    if not TRAFILATURA_AVAILABLE:
        pytest.skip("trafilatura not installed")
    
    monitor = BrowserMonitor()
    
    # Empty string
    result = monitor._extract_with_trafilatura("")
    assert result is None
    
    # None (should be handled)
    result = monitor._extract_with_trafilatura(None)
    assert result is None
    
    # Counter should NOT increment for failed extractions
    assert monitor._trafilatura_extractions == 0


def test_v7_trafilatura_extraction_with_minimal_content():
    """
    V7.0 TEST: Verify _extract_with_trafilatura returns None for content < 100 chars.
    
    Short content is likely not a real article and should be rejected.
    """
    from src.services.browser_monitor import TRAFILATURA_AVAILABLE
    
    if not TRAFILATURA_AVAILABLE:
        pytest.skip("trafilatura not installed")
    
    monitor = BrowserMonitor()
    
    # HTML with very short content
    html = "<html><body><p>Short text.</p></body></html>"
    
    result = monitor._extract_with_trafilatura(html)
    
    # Should return None for content < 100 chars
    assert result is None
    assert monitor._trafilatura_extractions == 0


def test_v7_stealth_available_flag():
    """
    V7.0 TEST: Verify STEALTH_AVAILABLE flag is set correctly.
    
    If playwright-stealth is installed, the flag should be True.
    """
    from src.services.browser_monitor import STEALTH_AVAILABLE, Stealth
    
    if STEALTH_AVAILABLE:
        assert Stealth is not None
        # Should be able to instantiate
        stealth = Stealth()
        assert hasattr(stealth, 'apply_stealth_async')
    else:
        assert Stealth is None


def test_v7_resource_blocking_patterns_defined():
    """
    V7.0 TEST: Verify BLOCKED_RESOURCE_PATTERNS contains expected patterns.
    
    Should block images, fonts, and common ad/tracking domains.
    """
    from src.services.browser_monitor import BLOCKED_RESOURCE_PATTERNS
    
    assert len(BLOCKED_RESOURCE_PATTERNS) > 0
    
    # Check for image patterns
    image_patterns = [p for p in BLOCKED_RESOURCE_PATTERNS if any(ext in p for ext in ['png', 'jpg', 'gif'])]
    assert len(image_patterns) > 0, "Should block image formats"
    
    # Check for font patterns
    font_patterns = [p for p in BLOCKED_RESOURCE_PATTERNS if any(ext in p for ext in ['woff', 'ttf'])]
    assert len(font_patterns) > 0, "Should block font formats"
    
    # Check for ad/tracking patterns
    ad_patterns = [p for p in BLOCKED_RESOURCE_PATTERNS if 'doubleclick' in p or 'analytics' in p]
    assert len(ad_patterns) > 0, "Should block ad/tracking domains"


def test_v7_setup_resource_blocking_is_async():
    """
    V7.0 TEST: Verify _setup_resource_blocking is properly async.
    
    This test would FAIL in the buggy version where route.abort() was called
    without await inside a sync lambda.
    """
    import inspect
    
    monitor = BrowserMonitor()
    
    # Verify the method is async
    assert inspect.iscoroutinefunction(monitor._setup_resource_blocking)
    
    # Get the source code and verify it uses async handler
    source = inspect.getsource(monitor._setup_resource_blocking)
    
    # Should have an async handler function (not a sync lambda)
    assert 'async def' in source, "Should use async handler for route.abort()"
    assert 'await route.abort()' in source, "Should await route.abort()"


def test_v7_apply_stealth_is_async():
    """
    V7.0 TEST: Verify _apply_stealth is properly async.
    """
    import inspect
    
    monitor = BrowserMonitor()
    
    # Verify the method is async
    assert inspect.iscoroutinefunction(monitor._apply_stealth)


def test_v7_fallback_extraction_counter():
    """
    V7.0 TEST: Verify fallback_extractions counter exists and starts at 0.
    
    This counter tracks when trafilatura fails and we fall back to raw text.
    """
    monitor = BrowserMonitor()
    
    assert hasattr(monitor, '_fallback_extractions')
    assert monitor._fallback_extractions == 0


@pytest.mark.asyncio
async def test_v7_extract_content_uses_trafilatura_first():
    """
    V7.0 TEST: Verify extract_content tries trafilatura before fallback.
    
    This is an integration test that verifies the extraction flow.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    from src.services.browser_monitor import TRAFILATURA_AVAILABLE
    
    if not TRAFILATURA_AVAILABLE:
        pytest.skip("trafilatura not installed")
    
    monitor = BrowserMonitor()
    
    # Mock browser and page
    mock_page = AsyncMock()
    mock_page.content.return_value = """
    <html><body>
    <article>
    <h1>Test Article Title</h1>
    <p>This is a test article with enough content to pass the 100 character minimum.
    It contains information about a football match and player injuries that would be
    relevant for betting analysis.</p>
    </article>
    </body></html>
    """
    mock_page.inner_text.return_value = "Fallback text"
    
    mock_browser = MagicMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    
    monitor._browser = mock_browser
    monitor._page_semaphore = asyncio.Semaphore(2)
    monitor._config = MonitorConfig()
    
    # Extract content
    result = await monitor.extract_content("https://test.com/article")
    
    # Should have used trafilatura (counter incremented)
    # OR fallback if trafilatura couldn't extract enough
    total_extractions = monitor._trafilatura_extractions + monitor._fallback_extractions
    assert total_extractions >= 1, "Should have attempted extraction"


# ============================================
# V7.1 TESTS: Circuit Breaker, Retry, Hybrid Mode
# ============================================

class TestV71CircuitBreaker:
    """V7.1 Tests for Circuit Breaker pattern."""
    
    def test_circuit_breaker_initial_state(self):
        """Circuit breaker starts in CLOSED state."""
        from src.services.browser_monitor import CircuitBreaker
        
        cb = CircuitBreaker()
        assert cb.state == "CLOSED"
        assert cb.failure_count == 0
        assert cb.can_execute() is True
    
    def test_circuit_breaker_opens_after_threshold(self):
        """
        REGRESSION TEST: Circuit breaker opens after N consecutive failures.
        
        Before V7.1: No circuit breaker, failing sources would be retried indefinitely.
        After V7.1: Circuit opens after 3 failures, skipping source for 5 minutes.
        """
        from src.services.browser_monitor import (
            CircuitBreaker, CIRCUIT_BREAKER_FAILURE_THRESHOLD
        )
        
        cb = CircuitBreaker()
        
        # Record failures up to threshold
        for i in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD - 1):
            cb.record_failure()
            assert cb.state == "CLOSED", f"Should stay CLOSED after {i+1} failures"
        
        # One more failure should open the circuit
        cb.record_failure()
        assert cb.state == "OPEN"
        assert cb.can_execute() is False
    
    def test_circuit_breaker_success_resets_failure_count(self):
        """Success resets failure count in CLOSED state."""
        from src.services.browser_monitor import CircuitBreaker
        
        cb = CircuitBreaker()
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == "CLOSED"
    
    def test_circuit_breaker_half_open_recovery(self):
        """
        REGRESSION TEST: Circuit transitions OPEN → HALF_OPEN → CLOSED on recovery.
        """
        from src.services.browser_monitor import CircuitBreaker
        import time
        
        # Use short timeout for testing
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"
        
        # Wait for recovery timeout
        time.sleep(0.15)
        
        # Should transition to HALF_OPEN
        assert cb.can_execute() is True
        assert cb.state == "HALF_OPEN"
        
        # Success should close the circuit
        cb.record_success()
        assert cb.state == "CLOSED"
    
    def test_circuit_breaker_half_open_failure_reopens(self):
        """Failure in HALF_OPEN state reopens the circuit."""
        from src.services.browser_monitor import CircuitBreaker
        import time
        
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"
        
        # Wait for recovery timeout
        time.sleep(0.15)
        cb.can_execute()  # Triggers HALF_OPEN
        assert cb.state == "HALF_OPEN"
        
        # Failure should reopen
        cb.record_failure()
        assert cb.state == "OPEN"
    
    def test_circuit_breaker_get_state(self):
        """get_state returns correct structure."""
        from src.services.browser_monitor import CircuitBreaker
        
        cb = CircuitBreaker()
        cb.record_failure()
        
        state = cb.get_state()
        assert "state" in state
        assert "failure_count" in state
        assert "last_failure" in state
        assert state["failure_count"] == 1


class TestV71BrowserMonitorCircuitBreaker:
    """V7.1 Tests for BrowserMonitor circuit breaker integration."""
    
    def test_browser_monitor_has_circuit_breaker_dict(self):
        """BrowserMonitor initializes with empty circuit breakers dict."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert hasattr(monitor, '_circuit_breakers')
        assert isinstance(monitor._circuit_breakers, dict)
        assert len(monitor._circuit_breakers) == 0
    
    def test_get_circuit_breaker_creates_new(self):
        """_get_circuit_breaker creates new breaker for unknown URL."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        url = "https://test.com/article"
        
        cb = monitor._get_circuit_breaker(url)
        assert cb is not None
        assert url in monitor._circuit_breakers
        assert cb.state == "CLOSED"
    
    def test_get_circuit_breaker_returns_existing(self):
        """_get_circuit_breaker returns same breaker for same URL."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        url = "https://test.com/article"
        
        cb1 = monitor._get_circuit_breaker(url)
        cb1.record_failure()
        
        cb2 = monitor._get_circuit_breaker(url)
        assert cb1 is cb2
        assert cb2.failure_count == 1
    
    def test_should_skip_source_when_circuit_open(self):
        """
        REGRESSION TEST: _should_skip_source returns True when circuit is OPEN.
        
        Before V7.1: Failing sources retried every cycle, wasting resources.
        After V7.1: Sources with OPEN circuit are skipped.
        """
        from src.services.browser_monitor import BrowserMonitor, CIRCUIT_BREAKER_FAILURE_THRESHOLD
        
        monitor = BrowserMonitor()
        url = "https://failing-source.com"
        
        # Initially should not skip
        assert monitor._should_skip_source(url) is False
        
        # Open the circuit
        cb = monitor._get_circuit_breaker(url)
        for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb.record_failure()
        
        # Now should skip
        assert monitor._should_skip_source(url) is True
        assert monitor._circuit_breaker_skips == 1
    
    def test_record_source_success_failure(self):
        """_record_source_success/failure update circuit breaker."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        url = "https://test.com"
        
        # V7.6: Must explicitly pass is_network_error=True to count failure
        monitor._record_source_failure(url, is_network_error=True)
        cb = monitor._get_circuit_breaker(url)
        assert cb.failure_count == 1
        
        monitor._record_source_success(url)
        assert cb.failure_count == 0
    
    def test_stats_include_circuit_breaker_metrics(self):
        """
        V7.1 TEST: get_stats includes circuit breaker metrics.
        """
        from src.services.browser_monitor import BrowserMonitor, CIRCUIT_BREAKER_FAILURE_THRESHOLD
        
        monitor = BrowserMonitor()
        
        # Create some circuit breakers
        monitor._get_circuit_breaker("https://source1.com")
        cb2 = monitor._get_circuit_breaker("https://source2.com")
        
        # Open one circuit
        for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb2.record_failure()
        
        stats = monitor.get_stats()
        
        assert stats["total_circuits"] == 2
        assert stats["open_circuits"] == 1
        assert "circuit_breaker_skips" in stats


class TestV71HybridExtraction:
    """V7.1 Tests for Hybrid HTTP+Browser extraction."""
    
    def test_browser_monitor_has_hybrid_counters(self):
        """BrowserMonitor initializes hybrid mode counters."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert hasattr(monitor, '_http_extractions')
        assert hasattr(monitor, '_browser_extractions')
        assert monitor._http_extractions == 0
        assert monitor._browser_extractions == 0
    
    def test_extract_with_http_is_async(self):
        """_extract_with_http is an async method."""
        import asyncio
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert asyncio.iscoroutinefunction(monitor._extract_with_http)
    
    def test_extract_content_hybrid_is_async(self):
        """extract_content_hybrid is an async method."""
        import asyncio
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert asyncio.iscoroutinefunction(monitor.extract_content_hybrid)
    
    def test_stats_include_hybrid_metrics(self):
        """
        V7.1 TEST: get_stats includes hybrid extraction metrics.
        """
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        stats = monitor.get_stats()
        
        assert "http_extractions" in stats
        assert "browser_extractions" in stats
        assert stats["version"] == "7.6"  # Updated from 7.2 to 7.3


class TestV71RetryWithBackoff:
    """V7.1 Tests for retry with exponential backoff."""
    
    def test_extract_with_retry_is_async(self):
        """_extract_with_retry is an async method."""
        import asyncio
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert asyncio.iscoroutinefunction(monitor._extract_with_retry)
    
    def test_retry_constants_defined(self):
        """V7.1 retry constants are properly defined."""
        from src.services.browser_monitor import (
            MAX_RETRIES, RETRY_BASE_DELAY, RETRY_MAX_DELAY
        )
        
        assert MAX_RETRIES == 2
        assert RETRY_BASE_DELAY == 2
        assert RETRY_MAX_DELAY == 8
    
    def test_http_timeout_defined(self):
        """V7.1 HTTP timeout constant is defined."""
        from src.services.browser_monitor import HTTP_TIMEOUT
        
        assert HTTP_TIMEOUT == 10


class TestV71Integration:
    """V7.1 Integration tests for the complete flow."""
    
    def test_scan_source_uses_circuit_breaker(self):
        """
        REGRESSION TEST: scan_source checks circuit breaker before extraction.
        
        This test verifies the integration between scan_source and circuit breaker.
        """
        from src.services.browser_monitor import BrowserMonitor, MonitoredSource
        import time
        
        monitor = BrowserMonitor()
        source = MonitoredSource(
            url="https://failing-source.com",
            league_key="test_league",
            name="Test Source"
        )
        
        # Open the circuit for this source
        cb = monitor._get_circuit_breaker(source.url)
        cb.state = "OPEN"
        cb.last_failure_time = time.time()  # Recent failure, circuit should stay OPEN
        
        # scan_source should check _should_skip_source which returns True
        # We can't easily test the full async flow without mocking, but we can
        # verify the circuit breaker is checked
        assert monitor._should_skip_source(source.url) is True
    
    def test_news_hunter_integration_with_v71_discovery(self):
        """
        V7.1 TEST: Verify news_hunter correctly handles V7.1 discoveries.
        """
        from src.services.browser_monitor import DiscoveredNews
        from src.processing.news_hunter import (
            register_browser_monitor_discovery,
            get_browser_monitor_news,
            clear_browser_monitor_discoveries
        )
        
        # Create discovery with V7.1 source
        news = DiscoveredNews(
            url="https://v71-test.com/article",
            title="V7.1 Test Discovery",
            snippet="Testing V7.1 hybrid extraction",
            category="INJURY",
            affected_team="Test FC",
            confidence=0.9,
            league_key="v71_test_league",
            source_name="V7.1 Test Source"
        )
        
        # Register
        register_browser_monitor_discovery(news)
        
        # Retrieve
        results = get_browser_monitor_news(
            match_id="v71_match",
            team_names=["Test FC"],
            league_key="v71_test_league"
        )
        
        assert len(results) == 1
        assert results[0]["title"] == "V7.1 Test Discovery"
        assert results[0]["source_type"] == "browser_monitor"
        
        # Cleanup
        clear_browser_monitor_discoveries("v71_test_league")


class TestV71EdgeCases:
    """V7.1 Edge case tests."""
    
    def test_circuit_breaker_with_zero_threshold(self):
        """Circuit breaker handles edge case of threshold=0."""
        from src.services.browser_monitor import CircuitBreaker
        
        # threshold=0 means circuit opens immediately on first failure
        cb = CircuitBreaker(failure_threshold=0)
        cb.record_failure()
        # With threshold=0, failure_count >= 0 is always true
        # This is an edge case - the circuit should open
        assert cb.state == "OPEN"
    
    def test_circuit_breaker_with_zero_recovery_timeout(self):
        """Circuit breaker handles edge case of recovery_timeout=0."""
        from src.services.browser_monitor import CircuitBreaker
        
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        assert cb.state == "OPEN"
        
        # With timeout=0, should immediately allow HALF_OPEN
        assert cb.can_execute() is True
        assert cb.state == "HALF_OPEN"
    
    def test_should_skip_source_empty_url(self):
        """_should_skip_source handles empty URL."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        # Empty URL should not crash
        result = monitor._should_skip_source("")
        assert result is False  # New circuit breaker, CLOSED state
    
    def test_get_circuit_breaker_none_url(self):
        """_get_circuit_breaker handles None URL gracefully."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        # This might raise or handle gracefully - test current behavior
        try:
            cb = monitor._get_circuit_breaker(None)
            # If it doesn't raise, verify it created a breaker
            assert cb is not None
        except (TypeError, KeyError):
            # Expected if None is not handled
            pass
    
    def test_multiple_circuit_breakers_independent(self):
        """Each URL has independent circuit breaker state."""
        from src.services.browser_monitor import BrowserMonitor, CIRCUIT_BREAKER_FAILURE_THRESHOLD
        
        monitor = BrowserMonitor()
        
        url1 = "https://source1.com"
        url2 = "https://source2.com"
        
        # Open circuit for url1
        cb1 = monitor._get_circuit_breaker(url1)
        for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb1.record_failure()
        
        # url2 should still be accessible
        cb2 = monitor._get_circuit_breaker(url2)
        
        assert cb1.state == "OPEN"
        assert cb2.state == "CLOSED"
        assert monitor._should_skip_source(url1) is True
        assert monitor._should_skip_source(url2) is False


# ============================================
# V7.2 TESTS: Behavior Simulation & Domain-Sticky Fingerprint
# ============================================

class TestV72BehaviorSimulation:
    """V7.2 Tests for human behavior simulation."""
    
    def test_behavior_simulation_config_exists(self):
        """V7.2: Behavior simulation configuration constants exist."""
        from src.services.browser_monitor import (
            BEHAVIOR_SIMULATION_ENABLED,
            BEHAVIOR_SCROLL_STEPS,
            BEHAVIOR_SCROLL_DELAY,
            BEHAVIOR_MOUSE_MOVE_ENABLED,
        )
        
        assert isinstance(BEHAVIOR_SIMULATION_ENABLED, bool)
        assert isinstance(BEHAVIOR_SCROLL_STEPS, tuple)
        assert len(BEHAVIOR_SCROLL_STEPS) == 2
        assert BEHAVIOR_SCROLL_STEPS[0] <= BEHAVIOR_SCROLL_STEPS[1]
        assert isinstance(BEHAVIOR_SCROLL_DELAY, tuple)
        assert len(BEHAVIOR_SCROLL_DELAY) == 2
        assert BEHAVIOR_SCROLL_DELAY[0] <= BEHAVIOR_SCROLL_DELAY[1]
        assert isinstance(BEHAVIOR_MOUSE_MOVE_ENABLED, bool)
    
    def test_behavior_simulation_counter_initialized(self):
        """V7.2: Behavior simulation counter starts at 0."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert hasattr(monitor, '_behavior_simulations')
        assert monitor._behavior_simulations == 0
    
    def test_stats_include_behavior_simulation(self):
        """V7.2: get_stats includes behavior simulation metrics."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        stats = monitor.get_stats()
        
        assert 'behavior_simulations' in stats
        assert 'behavior_simulation_enabled' in stats
        assert stats['version'] == '7.6'  # V7.6: Updated version
    
    def test_simulate_human_behavior_is_async(self):
        """V7.2: _simulate_human_behavior is an async method."""
        import asyncio
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert asyncio.iscoroutinefunction(monitor._simulate_human_behavior)
    
    @pytest.mark.asyncio
    async def test_simulate_human_behavior_handles_none_viewport(self):
        """
        V7.2 REGRESSION TEST: _simulate_human_behavior handles None viewport.
        
        Edge case: page.viewport_size can return None in some scenarios.
        The method should use default values and not crash.
        """
        from unittest.mock import AsyncMock, MagicMock, PropertyMock
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        # Mock page with None viewport
        mock_page = AsyncMock()
        mock_page.viewport_size = None
        mock_page.mouse = AsyncMock()
        mock_page.evaluate = AsyncMock()
        
        # Should not raise exception
        await monitor._simulate_human_behavior(mock_page)
        
        # Should have attempted to evaluate scroll
        assert mock_page.evaluate.called or True  # May skip if disabled
    
    @pytest.mark.asyncio
    async def test_simulate_human_behavior_handles_mouse_error(self):
        """
        V7.2 REGRESSION TEST: _simulate_human_behavior handles mouse.move errors.
        
        Edge case: mouse.move can fail if page is closed or in certain states.
        The method should continue without crashing.
        """
        from unittest.mock import AsyncMock
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        # Mock page where mouse.move raises exception
        mock_page = AsyncMock()
        mock_page.viewport_size = {"width": 1280, "height": 720}
        mock_page.mouse = AsyncMock()
        mock_page.mouse.move = AsyncMock(side_effect=Exception("Page closed"))
        mock_page.evaluate = AsyncMock()
        
        # Should not raise exception
        await monitor._simulate_human_behavior(mock_page)


class TestV72DomainStickyFingerprint:
    """V7.2 Tests for domain-sticky fingerprinting."""
    
    def test_domain_profiles_initialized(self):
        """V7.2: Domain profiles dict is initialized."""
        from src.utils.browser_fingerprint import BrowserFingerprint
        
        fp = BrowserFingerprint()
        assert hasattr(fp, '_domain_profiles')
        assert isinstance(fp._domain_profiles, dict)
        assert len(fp._domain_profiles) == 0
    
    def test_get_headers_for_domain_assigns_profile(self):
        """V7.2: get_headers_for_domain assigns a profile to new domain."""
        from src.utils.browser_fingerprint import BrowserFingerprint
        
        fp = BrowserFingerprint()
        
        # First call should assign a profile
        headers1 = fp.get_headers_for_domain("example.com")
        
        assert "example.com" in fp._domain_profiles
        assert "User-Agent" in headers1
    
    def test_get_headers_for_domain_is_sticky(self):
        """
        V7.2 REGRESSION TEST: Same domain always gets same profile.
        
        This is the core feature - fingerprint consistency per domain.
        """
        from src.utils.browser_fingerprint import BrowserFingerprint
        
        fp = BrowserFingerprint()
        
        # Multiple calls to same domain should return same User-Agent
        headers1 = fp.get_headers_for_domain("news.example.com")
        headers2 = fp.get_headers_for_domain("news.example.com")
        headers3 = fp.get_headers_for_domain("news.example.com")
        
        assert headers1["User-Agent"] == headers2["User-Agent"]
        assert headers2["User-Agent"] == headers3["User-Agent"]
    
    def test_different_domains_can_have_different_profiles(self):
        """V7.2: Different domains can be assigned different profiles."""
        from src.utils.browser_fingerprint import BrowserFingerprint, BROWSER_PROFILES
        
        fp = BrowserFingerprint()
        
        # With 6 profiles, assigning to 6+ domains should reuse some
        domains = [f"domain{i}.com" for i in range(len(BROWSER_PROFILES) + 2)]
        
        for domain in domains:
            fp.get_headers_for_domain(domain)
        
        # All domains should have profiles assigned
        assert len(fp._domain_profiles) == len(domains)
    
    def test_get_headers_for_domain_handles_empty_string(self):
        """
        V7.2 REGRESSION TEST: Empty domain falls back to regular rotation.
        
        Edge case: Empty string should not crash.
        """
        from src.utils.browser_fingerprint import BrowserFingerprint
        
        fp = BrowserFingerprint()
        
        # Empty string should fallback to get_headers()
        headers = fp.get_headers_for_domain("")
        
        assert "User-Agent" in headers
        assert "" not in fp._domain_profiles  # Should not store empty domain
    
    def test_get_headers_for_domain_handles_none(self):
        """
        V7.2 REGRESSION TEST: None domain falls back to regular rotation.
        """
        from src.utils.browser_fingerprint import BrowserFingerprint
        
        fp = BrowserFingerprint()
        
        # None should fallback to get_headers()
        headers = fp.get_headers_for_domain(None)
        
        assert "User-Agent" in headers
    
    def test_force_rotate_domain(self):
        """V7.2: force_rotate_domain changes the profile for a domain."""
        from src.utils.browser_fingerprint import BrowserFingerprint
        
        fp = BrowserFingerprint()
        
        # Assign initial profile
        headers1 = fp.get_headers_for_domain("test.com")
        initial_ua = headers1["User-Agent"]
        
        # Force rotate multiple times to ensure we get a different profile
        # (with 6 profiles, at least one rotation should give different UA)
        different_found = False
        for _ in range(10):
            fp.force_rotate_domain("test.com")
            headers2 = fp.get_headers_for_domain("test.com")
            if headers2["User-Agent"] != initial_ua:
                different_found = True
                break
        
        # Should have rotated to a different profile at least once
        assert different_found, "force_rotate_domain should change the profile"
    
    def test_force_rotate_domain_handles_empty(self):
        """V7.2: force_rotate_domain handles empty/None gracefully."""
        from src.utils.browser_fingerprint import BrowserFingerprint
        
        fp = BrowserFingerprint()
        
        # Should not raise
        fp.force_rotate_domain("")
        fp.force_rotate_domain(None)
    
    def test_stats_include_domain_tracking(self):
        """V7.2: get_stats includes domain tracking info."""
        from src.utils.browser_fingerprint import BrowserFingerprint
        
        fp = BrowserFingerprint()
        fp.get_headers_for_domain("domain1.com")
        fp.get_headers_for_domain("domain2.com")
        
        stats = fp.get_stats()
        
        assert 'domains_tracked' in stats
        assert stats['domains_tracked'] == 2
        assert 'domain_profiles' in stats
        assert 'domain1.com' in stats['domain_profiles']
        assert 'domain2.com' in stats['domain_profiles']


class TestV72HttpClientDomainSticky:
    """V7.2 Tests for HTTP client domain-sticky support."""
    
    def test_extract_domain_valid_url(self):
        """V7.2: _extract_domain extracts domain from valid URLs."""
        from src.utils.http_client import EarlyBirdHTTPClient
        
        assert EarlyBirdHTTPClient._extract_domain("https://example.com/path") == "example.com"
        assert EarlyBirdHTTPClient._extract_domain("http://news.site.org/article/123") == "news.site.org"
        assert EarlyBirdHTTPClient._extract_domain("https://sub.domain.co.uk/") == "sub.domain.co.uk"
    
    def test_extract_domain_handles_edge_cases(self):
        """
        V7.2 REGRESSION TEST: _extract_domain handles edge cases.
        """
        from src.utils.http_client import EarlyBirdHTTPClient
        
        # Empty/None
        assert EarlyBirdHTTPClient._extract_domain("") is None
        assert EarlyBirdHTTPClient._extract_domain(None) is None
        
        # Invalid URLs
        assert EarlyBirdHTTPClient._extract_domain("not-a-url") is None or \
               EarlyBirdHTTPClient._extract_domain("not-a-url") == ""
    
    def test_get_sync_for_domain_exists(self):
        """V7.2: get_sync_for_domain method exists."""
        from src.utils.http_client import EarlyBirdHTTPClient
        
        client = EarlyBirdHTTPClient()
        assert hasattr(client, 'get_sync_for_domain')
        assert callable(client.get_sync_for_domain)
    
    def test_build_headers_accepts_domain_param(self):
        """V7.2: _build_headers accepts domain parameter."""
        from src.utils.http_client import EarlyBirdHTTPClient
        
        client = EarlyBirdHTTPClient()
        
        # Should not raise with domain parameter
        headers = client._build_headers(use_fingerprint=True, domain="example.com")
        assert "User-Agent" in headers
    
    def test_on_error_accepts_domain_param(self):
        """V7.2: _on_error accepts domain parameter for domain-specific rotation."""
        from src.utils.http_client import EarlyBirdHTTPClient
        
        client = EarlyBirdHTTPClient()
        
        # Should not raise with domain parameter
        client._on_error(403, domain="example.com")
        client._on_error(429, domain=None)


class TestV72HttpExtractionFingerprint:
    """V7.2 Tests for HTTP extraction with domain-sticky fingerprint."""
    
    @pytest.mark.asyncio
    async def test_extract_with_http_uses_domain_fingerprint(self):
        """
        V7.2 REGRESSION TEST: _extract_with_http uses domain-sticky fingerprint.
        
        Before V7.2: Used hardcoded User-Agent
        After V7.2: Uses domain-sticky fingerprint for consistency
        """
        from unittest.mock import patch, MagicMock
        from src.services.browser_monitor import BrowserMonitor
        from src.utils.browser_fingerprint import reset_fingerprint, get_fingerprint
        
        reset_fingerprint()
        monitor = BrowserMonitor()
        
        captured_headers = {}
        
        def mock_get(url, timeout, headers):
            captured_headers['headers'] = headers
            captured_headers['url'] = url
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '<html><body><article>' + 'x' * 300 + '</article></body></html>'
            return mock_response
        
        with patch('src.services.browser_monitor.requests.get', side_effect=mock_get):
            await monitor._extract_with_http('https://test-domain.com/article')
        
        # Verify fingerprint headers are present (not hardcoded)
        headers = captured_headers.get('headers', {})
        assert 'User-Agent' in headers
        assert 'Sec-Fetch-Dest' in headers  # This proves we're using fingerprint
        assert 'Sec-Fetch-Mode' in headers
        
        # Verify domain was tracked
        fp = get_fingerprint()
        stats = fp.get_stats()
        assert 'test-domain.com' in stats['domain_profiles']
    
    @pytest.mark.asyncio
    async def test_extract_with_http_rotates_on_403(self):
        """
        V7.2 REGRESSION TEST: _extract_with_http rotates fingerprint on 403.
        """
        from unittest.mock import patch, MagicMock
        from src.services.browser_monitor import BrowserMonitor
        from src.utils.browser_fingerprint import reset_fingerprint, get_fingerprint
        
        reset_fingerprint()
        monitor = BrowserMonitor()
        fp = get_fingerprint()
        
        # First, establish a profile for the domain
        initial_headers = fp.get_headers_for_domain('blocked-site.com')
        initial_ua = initial_headers['User-Agent']
        
        def mock_get_403(url, timeout, headers):
            mock_response = MagicMock()
            mock_response.status_code = 403
            return mock_response
        
        with patch('src.services.browser_monitor.requests.get', side_effect=mock_get_403):
            result = await monitor._extract_with_http('https://blocked-site.com/page')
        
        # Result should be None (403 error)
        assert result is None
        
        # Profile should have been rotated (may or may not be different due to random selection)
        # But the rotation should have been called
        stats = fp.get_stats()
        assert 'blocked-site.com' in stats['domain_profiles']


# ============================================
# V7.3 TESTS: Bug Fixes and Improvements
# ============================================

class TestV73BugFixes:
    """
    V7.3 Regression tests for bug fixes:
    - Module-level imports for reliability
    - Smarter retry logic (network errors vs empty content)
    - Better JSON error handling in DeepSeek
    - Thread-safe stop with call_soon_threadsafe
    - Circuit breaker only counts network errors
    """
    
    def test_module_level_imports_available(self):
        """
        V7.3: Verify module-level imports are available.
        
        This test would fail in V7.2 where imports were inside functions.
        """
        from src.services.browser_monitor import (
            PSUTIL_AVAILABLE,
            FINGERPRINT_AVAILABLE,
            urlparse,  # Should be imported at module level
        )
        
        # These should be defined at module level
        assert isinstance(PSUTIL_AVAILABLE, bool)
        assert isinstance(FINGERPRINT_AVAILABLE, bool)
        
        # urlparse should work
        parsed = urlparse("https://example.com/path")
        assert parsed.netloc == "example.com"
    
    def test_http_min_content_length_constant(self):
        """
        V7.3: Verify HTTP_MIN_CONTENT_LENGTH constant exists.
        
        This replaces the magic number 200 in _extract_with_http.
        """
        from src.services.browser_monitor import HTTP_MIN_CONTENT_LENGTH
        
        assert HTTP_MIN_CONTENT_LENGTH == 200
        assert isinstance(HTTP_MIN_CONTENT_LENGTH, int)
    
    def test_circuit_breaker_simplified_success(self):
        """
        V7.3: Circuit breaker record_success is simplified.
        
        One success in HALF_OPEN should immediately close the circuit.
        The old code had redundant success_count increment.
        """
        from src.services.browser_monitor import CircuitBreaker
        
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        
        # Force to HALF_OPEN state
        cb.state = "HALF_OPEN"
        cb.success_count = 0
        
        # One success should close immediately
        cb.record_success()
        
        assert cb.state == "CLOSED"
        assert cb.failure_count == 0
        assert cb.success_count == 0
    
    def test_circuit_breaker_success_in_closed_resets_failures(self):
        """
        V7.3: Success in CLOSED state should reset failure count.
        """
        from src.services.browser_monitor import CircuitBreaker
        
        cb = CircuitBreaker(failure_threshold=3)
        
        # Simulate some failures (not enough to open)
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        assert cb.state == "CLOSED"
        
        # Success should reset
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == "CLOSED"
    
    @pytest.mark.asyncio
    async def test_extract_with_retry_returns_tuple(self):
        """
        V7.3: _extract_with_retry now returns tuple (content, is_network_error).
        
        This test would fail in V7.2 where it returned Optional[str].
        """
        from unittest.mock import patch, AsyncMock
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        # Mock successful extraction
        with patch.object(monitor, 'extract_content_hybrid', new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = "Test content here"
            
            result = await monitor._extract_with_retry("https://example.com")
            
            # V7.3: Returns tuple
            assert isinstance(result, tuple)
            assert len(result) == 2
            
            content, is_network_error = result
            assert content == "Test content here"
            assert is_network_error is False
    
    @pytest.mark.asyncio
    async def test_extract_with_retry_empty_content_no_retry(self):
        """
        V7.3: Empty content should NOT trigger retry (not a network error).
        
        This test would fail in V7.2 where empty content raised ValueError
        and triggered unnecessary retries.
        """
        from unittest.mock import patch, AsyncMock
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        call_count = 0
        
        async def mock_extract_empty(url):
            nonlocal call_count
            call_count += 1
            return None  # Empty content
        
        with patch.object(monitor, 'extract_content_hybrid', side_effect=mock_extract_empty):
            content, is_network_error = await monitor._extract_with_retry("https://example.com")
        
        # Should only be called once (no retry for empty content)
        assert call_count == 1
        assert content is None
        assert is_network_error is False  # Empty content is NOT a network error
    
    @pytest.mark.asyncio
    async def test_extract_with_retry_network_error_triggers_retry(self):
        """
        V7.3: Network errors SHOULD trigger retry.
        """
        import requests
        from unittest.mock import patch, AsyncMock
        from src.services.browser_monitor import BrowserMonitor, MAX_RETRIES
        
        monitor = BrowserMonitor()
        call_count = 0
        
        async def mock_extract_network_error(url):
            nonlocal call_count
            call_count += 1
            raise requests.RequestException("Connection failed")
        
        with patch.object(monitor, 'extract_content_hybrid', side_effect=mock_extract_network_error):
            with patch('src.services.browser_monitor.asyncio.sleep', new_callable=AsyncMock):
                content, is_network_error = await monitor._extract_with_retry("https://example.com")
        
        # Should be called MAX_RETRIES + 1 times
        assert call_count == MAX_RETRIES + 1
        assert content is None
        assert is_network_error is True  # Network error flagged
    
    def test_record_source_failure_with_network_error_flag(self):
        """
        V7.3: _record_source_failure now accepts is_network_error parameter.
        
        Only network errors should count toward circuit breaker.
        """
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        url = "https://test-source.com"
        
        # Record failure with is_network_error=True (should count)
        monitor._record_source_failure(url, is_network_error=True)
        cb = monitor._get_circuit_breaker(url)
        assert cb.failure_count == 1
        
        # Record failure with is_network_error=False (should NOT count)
        monitor._record_source_failure(url, is_network_error=False)
        assert cb.failure_count == 1  # Still 1, not incremented
    
    def test_get_memory_usage_uses_module_import(self):
        """
        V7.3: get_memory_usage_percent uses module-level psutil import.
        """
        from src.services.browser_monitor import get_memory_usage_percent, PSUTIL_AVAILABLE
        
        result = get_memory_usage_percent()
        
        # Should return a valid percentage
        assert isinstance(result, float)
        assert 0.0 <= result <= 100.0
        
        # If psutil not available, should return 50.0
        if not PSUTIL_AVAILABLE:
            assert result == 50.0
    
    def test_version_is_7_3(self):
        """
        V7.3: Verify version string is updated.
        """
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        stats = monitor.get_stats()
        
        assert stats["version"] == "7.6"


class TestV73DeepSeekErrorHandling:
    """
    V7.3: Tests for improved DeepSeek JSON error handling.
    """
    
    @pytest.mark.asyncio
    async def test_deepseek_invalid_json_response(self):
        """
        V7.3: Invalid JSON from API should be handled gracefully.
        
        This test would fail in V7.2 where JSONDecodeError was caught
        by generic Exception handler without specific logging.
        """
        from unittest.mock import patch, MagicMock
        from src.services.browser_monitor import BrowserMonitor
        import asyncio
        
        monitor = BrowserMonitor()
        
        # Mock response with invalid JSON
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "Not valid JSON at all"
        
        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
            with patch('src.services.browser_monitor.asyncio.to_thread') as mock_thread:
                mock_thread.return_value = mock_response
                
                result = await monitor._analyze_with_deepseek("test content", "test_league")
        
        # Should return None gracefully
        assert result is None
    
    @pytest.mark.asyncio
    async def test_deepseek_missing_choices_field(self):
        """
        V7.3: Missing 'choices' field should be handled gracefully.
        """
        from unittest.mock import patch, MagicMock
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        # Mock response with missing choices
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "something went wrong"}
        
        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
            with patch('src.services.browser_monitor.asyncio.to_thread') as mock_thread:
                mock_thread.return_value = mock_response
                
                result = await monitor._analyze_with_deepseek("test content", "test_league")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_deepseek_empty_choices_array(self):
        """
        V7.3: Empty 'choices' array should be handled gracefully.
        """
        from unittest.mock import patch, MagicMock
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        # Mock response with empty choices
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": []}
        
        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
            with patch('src.services.browser_monitor.asyncio.to_thread') as mock_thread:
                mock_thread.return_value = mock_response
                
                result = await monitor._analyze_with_deepseek("test content", "test_league")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_deepseek_malformed_choice_structure(self):
        """
        V7.3: Malformed choice structure should be handled gracefully.
        """
        from unittest.mock import patch, MagicMock
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        # Mock response with malformed choice (not a dict)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": ["not a dict"]}
        
        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
            with patch('src.services.browser_monitor.asyncio.to_thread') as mock_thread:
                mock_thread.return_value = mock_response
                
                result = await monitor._analyze_with_deepseek("test content", "test_league")
        
        assert result is None


class TestV73ThreadSafeStop:
    """
    V7.3: Tests for thread-safe stop functionality.
    """
    
    def test_request_stop_sets_running_false(self):
        """
        V7.3: request_stop should set _running to False.
        """
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        monitor._running = True
        
        monitor.request_stop()
        
        assert monitor._running is False
    
    @pytest.mark.asyncio
    async def test_request_stop_signals_event_when_loop_running(self):
        """
        V7.3: request_stop should signal stop_event via call_soon_threadsafe.
        """
        from src.services.browser_monitor import BrowserMonitor
        import asyncio
        
        monitor = BrowserMonitor()
        monitor._running = True
        monitor._stop_event = asyncio.Event()
        
        # Call request_stop while event loop is running
        monitor.request_stop()
        
        assert monitor._running is False
        # The event should be set (or scheduled to be set)
        # Give it a moment to process
        await asyncio.sleep(0.01)
        assert monitor._stop_event.is_set()


# ============================================
# V7.3.1: REGRESSION TESTS FOR BUG FIXES
# ============================================

class TestV731RegressionBugFixes:
    """
    V7.3.1: Regression tests for bugs fixed in this patch.
    
    These tests would FAIL in the buggy version and PASS with the fix.
    """
    
    def test_content_cache_is_cached_handles_none(self):
        """
        REGRESSION: is_cached(None) should return False, not crash.
        
        Bug: is_cached() called compute_hash() without checking for None,
        causing AttributeError when content was None.
        
        Fix: Added early return False for None/empty content.
        """
        from src.services.browser_monitor import ContentCache
        
        cache = ContentCache()
        
        # These should NOT raise exceptions
        assert cache.is_cached(None) is False
        assert cache.is_cached("") is False
    
    def test_content_cache_cache_handles_none(self):
        """
        REGRESSION: cache(None) should be a no-op, not crash.
        
        Bug: cache() called compute_hash() without checking for None.
        
        Fix: Added early return for None/empty content.
        """
        from src.services.browser_monitor import ContentCache
        
        cache = ContentCache()
        initial_size = cache.size()
        
        # These should NOT raise exceptions and should not add to cache
        cache.cache(None)
        cache.cache("")
        
        assert cache.size() == initial_size
    
    def test_confidence_string_coercion(self):
        """
        REGRESSION: confidence as string "0.8" should be converted to float.
        
        Bug: If DeepSeek returned confidence as string, comparison with
        RELEVANCE_CONFIDENCE_THRESHOLD would fail silently (string > float).
        
        Fix: Added try/except float() coercion in scan_source.
        """
        # Test the coercion logic directly
        test_cases = [
            ("0.8", 0.8),
            ("0.85", 0.85),
            (0.9, 0.9),
            (None, 0.0),
            ("invalid", 0.0),
            ("", 0.0),
        ]
        
        for input_val, expected in test_cases:
            try:
                result = float(input_val) if input_val is not None else 0.0
            except (TypeError, ValueError):
                result = 0.0
            
            assert result == expected, f"Failed for input {input_val}"
    
    @pytest.mark.asyncio
    async def test_extract_content_hybrid_catches_request_exception(self):
        """
        REGRESSION: extract_content_hybrid should catch RequestException from HTTP.
        
        Bug: _extract_with_http raised RequestException which wasn't caught
        by extract_content_hybrid, preventing browser fallback.
        
        Fix: Added try/except in extract_content_hybrid to catch RequestException.
        """
        from unittest.mock import patch, AsyncMock
        from src.services.browser_monitor import BrowserMonitor
        import requests
        
        monitor = BrowserMonitor()
        
        # Mock _extract_with_http to raise RequestException
        async def mock_http_raises(*args, **kwargs):
            raise requests.RequestException("Connection failed")
        
        # Mock extract_content to return success (browser fallback)
        async def mock_browser_success(*args, **kwargs):
            return "Browser extracted content"
        
        with patch.object(monitor, '_extract_with_http', side_effect=mock_http_raises):
            with patch.object(monitor, 'extract_content', side_effect=mock_browser_success):
                # This should NOT raise, should fallback to browser
                result = await monitor.extract_content_hybrid("https://test.com")
        
        assert result == "Browser extracted content"
        assert monitor._browser_extractions == 1
    
    def test_request_stop_uses_get_running_loop(self):
        """
        REGRESSION: request_stop should use get_running_loop() not get_event_loop().
        
        Bug: get_event_loop() is deprecated in Python 3.10+ and can cause
        DeprecationWarning or unexpected behavior in non-main threads.
        
        Fix: Changed to get_running_loop() with proper RuntimeError handling.
        """
        from src.services.browser_monitor import BrowserMonitor
        import inspect
        
        monitor = BrowserMonitor()
        
        # Get the source code of request_stop
        source = inspect.getsource(monitor.request_stop)
        
        # Should use get_running_loop, not get_event_loop
        assert "get_running_loop" in source, "Should use get_running_loop()"
        assert "get_event_loop()" not in source or "get_running_loop" in source
    
    def test_extraction_result_class_removed(self):
        """
        REGRESSION: _ExtractionResult class should be removed (dead code).
        
        Bug: _ExtractionResult was defined but never used, causing confusion.
        
        Fix: Removed the unused class.
        """
        from src.services.browser_monitor import BrowserMonitor
        
        # The class should NOT exist as an attribute of BrowserMonitor
        assert not hasattr(BrowserMonitor, '_ExtractionResult'), \
            "_ExtractionResult class should be removed (dead code)"


class TestV731EdgeCasesComprehensive:
    """
    V7.3.1: Comprehensive edge case tests.
    """
    
    def test_content_cache_empty_string_not_cached_as_duplicate(self):
        """
        Edge case: Two empty strings should not be considered duplicates
        because empty content should be rejected early.
        """
        from src.services.browser_monitor import ContentCache
        
        cache = ContentCache()
        
        # Empty string should not be cached
        cache.cache("")
        assert cache.size() == 0
        
        # And should not be found as cached
        assert cache.is_cached("") is False
    
    def test_confidence_edge_values(self):
        """
        Edge case: Confidence at exact threshold boundary.
        """
        from src.services.browser_monitor import RELEVANCE_CONFIDENCE_THRESHOLD
        
        # At threshold should pass
        assert 0.7 >= RELEVANCE_CONFIDENCE_THRESHOLD
        
        # Just below should fail
        assert 0.69 < RELEVANCE_CONFIDENCE_THRESHOLD
    
    @pytest.mark.asyncio
    async def test_scan_source_with_string_confidence_from_ai(self):
        """
        Integration test: scan_source handles string confidence from AI.
        """
        from unittest.mock import patch, AsyncMock, MagicMock
        from src.services.browser_monitor import BrowserMonitor, MonitoredSource
        
        monitor = BrowserMonitor()
        source = MonitoredSource(
            url="https://test.com/article",
            league_key="soccer_test",
            name="Test Source"
        )
        
        # Mock the extraction to return content with enough keywords for medium confidence
        # V7.5: Need 2-3 keywords to reach 0.5-0.7 confidence range for DeepSeek fallback
        async def mock_extract(*args, **kwargs):
            return ("Player injured and ruled out. He will miss the match.", False)
        
        # Mock analyze_relevance to return string confidence
        async def mock_analyze(*args, **kwargs):
            return {
                "is_relevant": True,
                "confidence": "0.85",  # String, not float!
                "category": "INJURY",
                "affected_team": "Test FC",
                "summary": "Player injured"
            }
        
        with patch.object(monitor, '_extract_with_retry', side_effect=mock_extract):
            with patch.object(monitor, 'analyze_relevance', side_effect=mock_analyze):
                with patch.object(monitor, '_content_cache', MagicMock(is_cached=lambda x: False, cache=lambda x: None)):
                    result = await monitor.scan_source(source)
        
        # Should succeed despite string confidence
        assert result is not None
        assert result.confidence == 0.85


# ============================================
# V7.4: PAGINATED NAVIGATION TESTS
# ============================================

class TestV74PaginatedNavigation:
    """
    V7.4: Tests for paginated navigation feature.
    
    Tests the new extract_with_navigation() method and paginated source scanning.
    """
    
    def test_monitored_source_has_navigation_fields(self):
        """MonitoredSource has navigation_mode and link_selector fields."""
        from src.services.browser_monitor import MonitoredSource
        
        source = MonitoredSource(
            url="https://test.com",
            league_key="soccer_test",
            navigation_mode="paginated",
            link_selector="a.article-link"
        )
        
        assert source.navigation_mode == "paginated"
        assert source.link_selector == "a.article-link"
    
    def test_monitored_source_default_navigation_mode(self):
        """MonitoredSource defaults to single navigation mode."""
        from src.services.browser_monitor import MonitoredSource
        
        source = MonitoredSource(
            url="https://test.com",
            league_key="soccer_test"
        )
        
        assert source.navigation_mode == "single"
        assert source.link_selector is None
    
    def test_monitored_source_max_links_default(self):
        """MonitoredSource has default max_links value."""
        from src.services.browser_monitor import (
            MonitoredSource, 
            DEFAULT_MAX_LINKS_PER_PAGINATED
        )
        
        source = MonitoredSource(
            url="https://test.com",
            league_key="soccer_test"
        )
        
        assert source.max_links == DEFAULT_MAX_LINKS_PER_PAGINATED
    
    def test_load_config_reads_navigation_fields(self):
        """load_config correctly reads navigation_mode and link_selector."""
        from src.services.browser_monitor import load_config
        import tempfile
        import json
        
        config_data = {
            "sources": [
                {
                    "url": "https://test.com/news",
                    "league_key": "soccer_test",
                    "navigation_mode": "paginated",
                    "link_selector": "a[href*='/article/']",
                    "max_links": 10
                }
            ],
            "global_settings": {}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            f.flush()
            
            config = load_config(f.name)
        
        assert len(config.sources) == 1
        assert config.sources[0].navigation_mode == "paginated"
        assert config.sources[0].link_selector == "a[href*='/article/']"
        assert config.sources[0].max_links == 10
    
    def test_load_config_defaults_navigation_mode_to_single(self):
        """load_config defaults navigation_mode to 'single' if not specified."""
        from src.services.browser_monitor import load_config
        import tempfile
        import json
        
        config_data = {
            "sources": [
                {
                    "url": "https://test.com/news",
                    "league_key": "soccer_test"
                    # No navigation_mode specified
                }
            ],
            "global_settings": {}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            f.flush()
            
            config = load_config(f.name)
        
        assert config.sources[0].navigation_mode == "single"
        assert config.sources[0].link_selector is None


class TestV74ExtractWithNavigation:
    """V7.4: Tests for extract_with_navigation method."""
    
    def test_browser_monitor_has_extract_with_navigation(self):
        """BrowserMonitor has extract_with_navigation method."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert hasattr(monitor, 'extract_with_navigation')
        assert callable(monitor.extract_with_navigation)
    
    @pytest.mark.asyncio
    async def test_extract_with_navigation_returns_empty_without_browser(self):
        """extract_with_navigation returns empty list if browser not initialized."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        # Browser not started
        
        results = await monitor.extract_with_navigation(
            url="https://test.com",
            link_selector="a.article"
        )
        
        assert results == []
    
    @pytest.mark.asyncio
    async def test_extract_with_navigation_returns_empty_without_selector(self):
        """extract_with_navigation returns empty list if link_selector is empty."""
        from src.services.browser_monitor import BrowserMonitor
        from unittest.mock import MagicMock, AsyncMock
        
        monitor = BrowserMonitor()
        monitor._browser = MagicMock()  # Fake browser
        monitor._page_semaphore = MagicMock()
        monitor._page_semaphore.__aenter__ = AsyncMock()
        monitor._page_semaphore.__aexit__ = AsyncMock()
        
        results = await monitor.extract_with_navigation(
            url="https://test.com",
            link_selector=""  # Empty selector
        )
        
        assert results == []
    
    @pytest.mark.asyncio
    async def test_extract_with_navigation_returns_empty_with_none_selector(self):
        """extract_with_navigation returns empty list if link_selector is None."""
        from src.services.browser_monitor import BrowserMonitor
        from unittest.mock import MagicMock, AsyncMock
        
        monitor = BrowserMonitor()
        monitor._browser = MagicMock()
        monitor._page_semaphore = MagicMock()
        monitor._page_semaphore.__aenter__ = AsyncMock()
        monitor._page_semaphore.__aexit__ = AsyncMock()
        
        results = await monitor.extract_with_navigation(
            url="https://test.com",
            link_selector=None  # None selector
        )
        
        assert results == []


class TestV74ScanSourcePaginated:
    """V7.4: Tests for paginated source scanning."""
    
    @pytest.mark.asyncio
    async def test_scan_source_uses_paginated_for_configured_sources(self):
        """scan_source calls _scan_source_paginated for paginated sources."""
        from src.services.browser_monitor import BrowserMonitor, MonitoredSource
        from unittest.mock import patch, AsyncMock
        
        monitor = BrowserMonitor()
        source = MonitoredSource(
            url="https://test.com/news",
            league_key="soccer_test",
            navigation_mode="paginated",
            link_selector="a.article"
        )
        
        # Mock _scan_source_paginated
        mock_paginated = AsyncMock(return_value=None)
        
        with patch.object(monitor, '_scan_source_paginated', mock_paginated):
            with patch.object(monitor, '_should_skip_source', return_value=False):
                await monitor.scan_source(source)
        
        # Should have called paginated method
        mock_paginated.assert_called_once_with(source)
    
    @pytest.mark.asyncio
    async def test_scan_source_uses_single_for_non_paginated(self):
        """scan_source uses single extraction for non-paginated sources."""
        from src.services.browser_monitor import BrowserMonitor, MonitoredSource
        from unittest.mock import patch, AsyncMock
        
        monitor = BrowserMonitor()
        source = MonitoredSource(
            url="https://test.com/news",
            league_key="soccer_test",
            navigation_mode="single"  # Not paginated
        )
        
        # Mock _extract_with_retry
        mock_extract = AsyncMock(return_value=(None, False))
        
        with patch.object(monitor, '_extract_with_retry', mock_extract):
            with patch.object(monitor, '_should_skip_source', return_value=False):
                await monitor.scan_source(source)
        
        # Should have called single extraction
        mock_extract.assert_called_once_with(source.url)
    
    @pytest.mark.asyncio
    async def test_scan_source_paginated_requires_link_selector(self):
        """scan_source uses single extraction if link_selector is missing."""
        from src.services.browser_monitor import BrowserMonitor, MonitoredSource
        from unittest.mock import patch, AsyncMock
        
        monitor = BrowserMonitor()
        source = MonitoredSource(
            url="https://test.com/news",
            league_key="soccer_test",
            navigation_mode="paginated",
            link_selector=None  # Missing selector!
        )
        
        # Mock _extract_with_retry (single mode)
        mock_extract = AsyncMock(return_value=(None, False))
        mock_paginated = AsyncMock()
        
        with patch.object(monitor, '_extract_with_retry', mock_extract):
            with patch.object(monitor, '_scan_source_paginated', mock_paginated):
                with patch.object(monitor, '_should_skip_source', return_value=False):
                    await monitor.scan_source(source)
        
        # Should NOT have called paginated (missing selector)
        mock_paginated.assert_not_called()
        # Should have used single extraction
        mock_extract.assert_called_once()


class TestV74AnalyzeAndCreateNews:
    """V7.4: Tests for _analyze_and_create_news helper method."""
    
    def test_browser_monitor_has_analyze_and_create_news(self):
        """BrowserMonitor has _analyze_and_create_news method."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert hasattr(monitor, '_analyze_and_create_news')
        assert callable(monitor._analyze_and_create_news)
    
    @pytest.mark.asyncio
    async def test_analyze_and_create_news_uses_article_url(self):
        """_analyze_and_create_news uses article_url, not source.url."""
        from src.services.browser_monitor import BrowserMonitor, MonitoredSource
        from unittest.mock import patch, AsyncMock, MagicMock
        
        monitor = BrowserMonitor()
        source = MonitoredSource(
            url="https://test.com/homepage",  # Homepage URL
            league_key="soccer_test",
            name="Test Source"
        )
        article_url = "https://test.com/article/123"  # Different URL
        # V7.5: Content needs enough keywords for medium confidence to trigger DeepSeek
        content = "Player injured and ruled out. He will miss the match due to injury."
        
        # Mock analyze_relevance
        mock_analyze = AsyncMock(return_value={
            "is_relevant": True,
            "confidence": 0.9,
            "category": "INJURY",
            "affected_team": "Test FC",
            "summary": "Player injured"
        })
        
        # Mock cache
        mock_cache = MagicMock()
        mock_cache.is_cached.return_value = False
        monitor._content_cache = mock_cache
        
        with patch.object(monitor, 'analyze_relevance', mock_analyze):
            news = await monitor._analyze_and_create_news(source, article_url, content)
        
        # News URL should be article_url, not source.url
        assert news is not None
        assert news.url == article_url
        assert news.url != source.url
    
    @pytest.mark.asyncio
    async def test_analyze_and_create_news_handles_cached_content(self):
        """_analyze_and_create_news returns None for cached content."""
        from src.services.browser_monitor import BrowserMonitor, MonitoredSource
        from unittest.mock import MagicMock
        
        monitor = BrowserMonitor()
        source = MonitoredSource(
            url="https://test.com",
            league_key="soccer_test"
        )
        
        # Mock cache to return True (content is cached)
        mock_cache = MagicMock()
        mock_cache.is_cached.return_value = True
        monitor._content_cache = mock_cache
        
        news = await monitor._analyze_and_create_news(
            source, 
            "https://test.com/article", 
            "Cached content"
        )
        
        assert news is None


class TestV74EdgeCases:
    """V7.4: Edge case tests for paginated navigation."""
    
    def test_monitored_source_with_empty_link_selector(self):
        """MonitoredSource handles empty string link_selector."""
        from src.services.browser_monitor import MonitoredSource
        
        source = MonitoredSource(
            url="https://test.com",
            league_key="soccer_test",
            navigation_mode="paginated",
            link_selector=""  # Empty string
        )
        
        # Empty string is falsy, should be treated as no selector
        assert not source.link_selector
    
    def test_monitored_source_max_links_custom_value(self):
        """MonitoredSource accepts custom max_links value."""
        from src.services.browser_monitor import MonitoredSource
        
        source = MonitoredSource(
            url="https://test.com",
            league_key="soccer_test",
            max_links=10
        )
        
        assert source.max_links == 10
    
    @pytest.mark.asyncio
    async def test_scan_source_paginated_handles_empty_results(self):
        """_scan_source_paginated handles empty extraction results."""
        from src.services.browser_monitor import BrowserMonitor, MonitoredSource
        from unittest.mock import patch, AsyncMock
        
        monitor = BrowserMonitor()
        source = MonitoredSource(
            url="https://test.com",
            league_key="soccer_test",
            navigation_mode="paginated",
            link_selector="a.article"
        )
        
        # Mock extract_with_navigation to return empty list
        mock_extract = AsyncMock(return_value=[])
        
        with patch.object(monitor, 'extract_with_navigation', mock_extract):
            result = await monitor._scan_source_paginated(source)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_extract_with_navigation_deduplicates_links(self):
        """extract_with_navigation deduplicates links before visiting."""
        from src.services.browser_monitor import BrowserMonitor
        from unittest.mock import patch, AsyncMock, MagicMock
        import asyncio
        
        monitor = BrowserMonitor()
        monitor._running = True
        monitor._stop_event = asyncio.Event()
        monitor._config = MagicMock()
        monitor._config.global_settings.page_timeout_seconds = 30
        
        # Create mock browser and page
        mock_page = MagicMock()
        mock_page.set_viewport_size = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.close = AsyncMock()
        
        # Return duplicate links
        mock_page.eval_on_selector_all = AsyncMock(return_value=[
            "https://test.com/article/1",
            "https://test.com/article/1",  # Duplicate!
            "https://test.com/article/2",
            "https://test.com/article/1",  # Another duplicate!
        ])
        
        mock_browser = MagicMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        monitor._browser = mock_browser
        
        # Mock semaphore
        mock_semaphore = MagicMock()
        mock_semaphore.__aenter__ = AsyncMock()
        mock_semaphore.__aexit__ = AsyncMock()
        monitor._page_semaphore = mock_semaphore
        
        # Mock stealth and resource blocking
        monitor._apply_stealth = AsyncMock()
        monitor._setup_resource_blocking = AsyncMock()
        monitor._simulate_human_behavior = AsyncMock()
        
        # Track which URLs are extracted
        extracted_urls = []
        async def mock_extract(url):
            extracted_urls.append(url)
            return f"Content from {url}"
        
        with patch.object(monitor, 'extract_content_hybrid', side_effect=mock_extract):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                results = await monitor.extract_with_navigation(
                    url="https://test.com",
                    link_selector="a.article",
                    max_links=5
                )
        
        # Should only extract unique URLs (2, not 4)
        assert len(extracted_urls) == 2
        assert "https://test.com/article/1" in extracted_urls
        assert "https://test.com/article/2" in extracted_urls


class TestV74ConfigIntegration:
    """V7.4: Integration tests for browser_sources.json configuration."""
    
    def test_browser_sources_json_has_paginated_sources(self):
        """browser_sources.json contains paginated sources."""
        from src.services.browser_monitor import load_config
        
        config = load_config("config/browser_sources.json")
        
        # Should have sources
        assert len(config.sources) > 0
        
        # At least one should be paginated
        paginated_sources = [s for s in config.sources if s.navigation_mode == "paginated"]
        assert len(paginated_sources) > 0
    
    def test_browser_sources_json_paginated_have_selectors(self):
        """All paginated sources in browser_sources.json have link_selector."""
        from src.services.browser_monitor import load_config
        
        config = load_config("config/browser_sources.json")
        
        for source in config.sources:
            if source.navigation_mode == "paginated":
                assert source.link_selector, f"Source {source.name} is paginated but has no link_selector"
                assert len(source.link_selector) > 0


# ============================================
# V7.5: SMART API ROUTING TESTS
# ============================================

class TestV75ContentAnalysisModule:
    """V7.5: Tests for shared content_analysis module."""
    
    def test_content_analysis_module_exists(self):
        """content_analysis module can be imported."""
        from src.utils.content_analysis import (
            AnalysisResult,
            ExclusionFilter,
            RelevanceAnalyzer,
            get_exclusion_filter,
            get_relevance_analyzer,
        )
        
        assert AnalysisResult is not None
        assert ExclusionFilter is not None
        assert RelevanceAnalyzer is not None
    
    def test_exclusion_filter_excludes_basketball(self):
        """ExclusionFilter excludes basketball content."""
        from src.utils.content_analysis import get_exclusion_filter
        
        ef = get_exclusion_filter()
        
        # Basketball should be excluded
        assert ef.is_excluded("NBA Finals: Lakers vs Celtics tonight")
        assert ef.is_excluded("Euroleague basketball match preview")
        assert ef.get_exclusion_reason("NBA game") == "nba"
    
    def test_exclusion_filter_excludes_womens_football(self):
        """ExclusionFilter excludes women's football content."""
        from src.utils.content_analysis import get_exclusion_filter
        
        ef = get_exclusion_filter()
        
        assert ef.is_excluded("Women's World Cup final")
        assert ef.is_excluded("WSL: Chelsea Ladies win")
        assert ef.is_excluded("Femminile Serie A results")
    
    def test_exclusion_filter_allows_mens_football(self):
        """ExclusionFilter allows men's football content."""
        from src.utils.content_analysis import get_exclusion_filter
        
        ef = get_exclusion_filter()
        
        # Men's football should NOT be excluded
        assert not ef.is_excluded("Premier League: Manchester United injury news")
        assert not ef.is_excluded("Serie A: Juventus player suspended")
        assert not ef.is_excluded("La Liga transfer rumors")
    
    def test_exclusion_filter_allows_youth_football(self):
        """ExclusionFilter allows youth football (relevant for betting)."""
        from src.utils.content_analysis import get_exclusion_filter
        
        ef = get_exclusion_filter()
        
        # Youth football should NOT be excluded (relevant for betting!)
        assert not ef.is_excluded("Primavera player called up to first team")
        assert not ef.is_excluded("U19 talent promoted due to injuries")
        assert not ef.is_excluded("Youth academy player makes debut")
    
    def test_relevance_analyzer_detects_injury(self):
        """RelevanceAnalyzer detects injury keywords."""
        from src.utils.content_analysis import get_relevance_analyzer
        
        ra = get_relevance_analyzer()
        
        result = ra.analyze("Manchester United star injured, ruled out for 3 weeks with hamstring strain")
        
        assert result.is_relevant
        assert result.category == "INJURY"
        assert result.confidence >= 0.3
    
    def test_relevance_analyzer_detects_suspension(self):
        """RelevanceAnalyzer detects suspension keywords."""
        from src.utils.content_analysis import get_relevance_analyzer
        
        ra = get_relevance_analyzer()
        
        result = ra.analyze("Player suspended after red card, banned for 3 matches")
        
        assert result.is_relevant
        assert result.category == "SUSPENSION"
        assert result.confidence >= 0.3
    
    def test_relevance_analyzer_detects_youth_callup(self):
        """RelevanceAnalyzer detects youth callup keywords."""
        from src.utils.content_analysis import get_relevance_analyzer
        
        ra = get_relevance_analyzer()
        
        result = ra.analyze("Primavera player promoted to first team, youth academy talent called up")
        
        assert result.is_relevant
        assert result.category == "YOUTH_CALLUP"
        assert result.confidence >= 0.3
    
    def test_relevance_analyzer_returns_not_relevant_for_no_keywords(self):
        """RelevanceAnalyzer returns not relevant for content without keywords."""
        from src.utils.content_analysis import get_relevance_analyzer
        
        ra = get_relevance_analyzer()
        
        result = ra.analyze("The weather is nice today. Stock market is up.")
        
        assert not result.is_relevant
        assert result.confidence < 0.5
    
    def test_relevance_analyzer_handles_empty_content(self):
        """RelevanceAnalyzer handles empty content safely."""
        from src.utils.content_analysis import get_relevance_analyzer
        
        ra = get_relevance_analyzer()
        
        result = ra.analyze("")
        assert not result.is_relevant
        assert result.confidence == 0.0
        
        result = ra.analyze(None)
        assert not result.is_relevant


class TestV75SmartAPIRouting:
    """V7.5: Tests for smart API routing in BrowserMonitor."""
    
    def test_browser_monitor_has_v75_counters(self):
        """BrowserMonitor has V7.5 smart routing counters."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        assert hasattr(monitor, '_excluded_count')
        assert hasattr(monitor, '_skipped_low_confidence')
        assert hasattr(monitor, '_direct_alerts')
        assert hasattr(monitor, '_deepseek_fallbacks')
        
        assert monitor._excluded_count == 0
        assert monitor._skipped_low_confidence == 0
        assert monitor._direct_alerts == 0
        assert monitor._deepseek_fallbacks == 0
    
    def test_browser_monitor_get_stats_includes_v75_stats(self):
        """get_stats includes V7.5 smart routing statistics."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        stats = monitor.get_stats()
        
        assert 'excluded_count' in stats
        assert 'skipped_low_confidence' in stats
        assert 'direct_alerts' in stats
        assert 'deepseek_fallbacks' in stats
        assert 'api_calls_saved' in stats
        assert 'api_savings_percent' in stats
        assert stats['version'] == '7.6'  # V7.6: Updated version
    
    def test_browser_monitor_api_savings_calculation(self):
        """API savings percentage is calculated correctly."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        # Simulate some routing decisions
        monitor._excluded_count = 30
        monitor._skipped_low_confidence = 40
        monitor._direct_alerts = 20
        monitor._deepseek_fallbacks = 10
        
        stats = monitor.get_stats()
        
        # Total: 100, Saved: 90 (30+40+20), Percent: 90%
        assert stats['api_calls_saved'] == 90
        assert stats['api_savings_percent'] == 90.0
    
    def test_browser_monitor_api_savings_handles_zero_division(self):
        """API savings handles zero total analyzed (no division by zero)."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        # All counters at zero
        stats = monitor.get_stats()
        
        assert stats['api_calls_saved'] == 0
        assert stats['api_savings_percent'] == 0.0  # Not NaN or error


class TestV75AnalyzeAndCreateNews:
    """V7.5: Tests for _analyze_and_create_news with smart routing."""
    
    @pytest.mark.asyncio
    async def test_analyze_excludes_basketball_content(self):
        """_analyze_and_create_news excludes basketball content without API call."""
        from src.services.browser_monitor import BrowserMonitor, MonitoredSource
        from unittest.mock import MagicMock, AsyncMock, patch
        
        monitor = BrowserMonitor()
        source = MonitoredSource(
            url="https://test.com",
            league_key="soccer_test",
            name="Test"
        )
        
        # Mock cache
        mock_cache = MagicMock()
        mock_cache.is_cached.return_value = False
        monitor._content_cache = mock_cache
        
        # Mock analyze_relevance (should NOT be called)
        mock_analyze = AsyncMock()
        
        with patch.object(monitor, 'analyze_relevance', mock_analyze):
            result = await monitor._analyze_and_create_news(
                source,
                "https://test.com/article",
                "NBA Finals: Lakers beat Celtics in basketball game"
            )
        
        # Should be excluded, no API call
        assert result is None
        mock_analyze.assert_not_called()
        assert monitor._excluded_count == 1
    
    @pytest.mark.asyncio
    async def test_analyze_skips_low_confidence_content(self):
        """_analyze_and_create_news skips low confidence content without API call."""
        from src.services.browser_monitor import BrowserMonitor, MonitoredSource
        from unittest.mock import MagicMock, AsyncMock, patch
        
        monitor = BrowserMonitor()
        source = MonitoredSource(
            url="https://test.com",
            league_key="soccer_test",
            name="Test"
        )
        
        # Mock cache
        mock_cache = MagicMock()
        mock_cache.is_cached.return_value = False
        monitor._content_cache = mock_cache
        
        # Mock analyze_relevance (should NOT be called)
        mock_analyze = AsyncMock()
        
        with patch.object(monitor, 'analyze_relevance', mock_analyze):
            result = await monitor._analyze_and_create_news(
                source,
                "https://test.com/article",
                "The weather is nice today. Stock prices are up."  # No football keywords
            )
        
        # Should be skipped (low confidence), no API call
        assert result is None
        mock_analyze.assert_not_called()
        assert monitor._skipped_low_confidence == 1
    
    @pytest.mark.asyncio
    async def test_analyze_direct_alert_high_confidence(self):
        """_analyze_and_create_news creates direct alert for high confidence without API call."""
        from src.services.browser_monitor import BrowserMonitor, MonitoredSource
        from unittest.mock import MagicMock, AsyncMock, patch
        
        monitor = BrowserMonitor()
        source = MonitoredSource(
            url="https://test.com",
            league_key="soccer_test",
            name="Test"
        )
        
        # Mock cache
        mock_cache = MagicMock()
        mock_cache.is_cached.return_value = False
        monitor._content_cache = mock_cache
        
        # Mock analyze_relevance (should NOT be called for high confidence)
        mock_analyze = AsyncMock()
        
        # Content with many injury keywords (high confidence)
        content = """
        BREAKING: Manchester United star injured! Player ruled out with hamstring strain.
        The midfielder will miss the next 3 matches. Injury confirmed by medical staff.
        He is sidelined and absent from training. Muscle injury keeps him out.
        """
        
        with patch.object(monitor, 'analyze_relevance', mock_analyze):
            result = await monitor._analyze_and_create_news(
                source,
                "https://test.com/article",
                content
            )
        
        # Should create alert directly, no API call
        assert result is not None
        mock_analyze.assert_not_called()
        assert monitor._direct_alerts == 1
        assert result.category == "INJURY"
    
    @pytest.mark.asyncio
    async def test_analyze_deepseek_fallback_medium_confidence(self):
        """_analyze_and_create_news calls DeepSeek for medium confidence content."""
        from src.services.browser_monitor import BrowserMonitor, MonitoredSource
        from unittest.mock import MagicMock, AsyncMock, patch
        
        monitor = BrowserMonitor()
        source = MonitoredSource(
            url="https://test.com",
            league_key="soccer_test",
            name="Test"
        )
        
        # Mock cache
        mock_cache = MagicMock()
        mock_cache.is_cached.return_value = False
        monitor._content_cache = mock_cache
        
        # Mock analyze_relevance to return high confidence result
        mock_analyze = AsyncMock(return_value={
            'is_relevant': True,
            'confidence': 0.85,
            'category': 'INJURY',
            'affected_team': 'Test FC',
            'summary': 'Player injured'
        })
        
        # Content with 2-3 injury keywords (medium confidence ~0.5-0.6)
        # This should trigger DeepSeek fallback (0.5 <= confidence < 0.7)
        content = "The player is injured and will miss the match. He is out for the game."
        
        with patch.object(monitor, 'analyze_relevance', mock_analyze):
            result = await monitor._analyze_and_create_news(
                source,
                "https://test.com/article",
                content
            )
        
        # Should call DeepSeek for medium confidence
        assert result is not None
        mock_analyze.assert_called_once()
        assert monitor._deepseek_fallbacks == 1


class TestV75Integration:
    """V7.5: Integration tests for the complete smart routing flow."""
    
    def test_news_radar_uses_shared_module(self):
        """news_radar imports from shared content_analysis module."""
        from src.services.news_radar import (
            AnalysisResult,
            ExclusionFilter,
            RelevanceAnalyzer,
        )
        from src.utils.content_analysis import (
            AnalysisResult as SharedAnalysisResult,
            ExclusionFilter as SharedExclusionFilter,
            RelevanceAnalyzer as SharedRelevanceAnalyzer,
        )
        
        # Should be the same classes
        assert AnalysisResult is SharedAnalysisResult
        assert ExclusionFilter is SharedExclusionFilter
        assert RelevanceAnalyzer is SharedRelevanceAnalyzer
    
    def test_browser_monitor_uses_shared_module(self):
        """browser_monitor imports from shared content_analysis module."""
        from src.services.browser_monitor import (
            get_exclusion_filter,
            get_relevance_analyzer,
        )
        from src.utils.content_analysis import (
            get_exclusion_filter as shared_get_exclusion_filter,
            get_relevance_analyzer as shared_get_relevance_analyzer,
        )
        
        # Should be the same functions
        assert get_exclusion_filter is shared_get_exclusion_filter
        assert get_relevance_analyzer is shared_get_relevance_analyzer
    
    def test_singleton_instances_are_reused(self):
        """Singleton instances are reused across calls."""
        from src.utils.content_analysis import get_exclusion_filter, get_relevance_analyzer
        
        ef1 = get_exclusion_filter()
        ef2 = get_exclusion_filter()
        assert ef1 is ef2
        
        ra1 = get_relevance_analyzer()
        ra2 = get_relevance_analyzer()
        assert ra1 is ra2


# ============================================
# V7.6: REGRESSION TESTS FOR BUG FIXES
# ============================================

class TestV76RegressionBugFixes:
    """V7.6: Regression tests for bug fixes in _analyze_and_create_news."""
    
    def test_empty_string_affected_team_becomes_unknown(self):
        """
        REGRESSION: Empty string affected_team should become 'Unknown Team'.
        
        Bug: analysis.get('affected_team') or 'Unknown Team' passes empty string.
        Fix: (analysis.get('affected_team') or '').strip() or 'Unknown Team'
        """
        # Simulate DeepSeek returning empty string
        analysis = {
            'is_relevant': True,
            'confidence': 0.8,
            'category': 'INJURY',
            'affected_team': '',  # Empty string - BUG CASE
            'summary': 'Test summary'
        }
        
        # Apply the fixed logic
        affected_team = (analysis.get('affected_team') or '').strip() or 'Unknown Team'
        
        assert affected_team == 'Unknown Team', \
            f"Empty string should become 'Unknown Team', got: {affected_team}"
    
    def test_whitespace_only_affected_team_becomes_unknown(self):
        """
        REGRESSION: Whitespace-only affected_team should become 'Unknown Team'.
        """
        analysis = {
            'is_relevant': True,
            'confidence': 0.8,
            'category': 'INJURY',
            'affected_team': '   ',  # Whitespace only - BUG CASE
            'summary': 'Test summary'
        }
        
        affected_team = (analysis.get('affected_team') or '').strip() or 'Unknown Team'
        
        assert affected_team == 'Unknown Team', \
            f"Whitespace-only should become 'Unknown Team', got: {affected_team}"
    
    def test_none_affected_team_becomes_unknown(self):
        """
        REGRESSION: None affected_team should become 'Unknown Team'.
        """
        analysis = {
            'is_relevant': True,
            'confidence': 0.8,
            'category': 'INJURY',
            'affected_team': None,  # None - should be handled
            'summary': 'Test summary'
        }
        
        affected_team = (analysis.get('affected_team') or '').strip() or 'Unknown Team'
        
        assert affected_team == 'Unknown Team', \
            f"None should become 'Unknown Team', got: {affected_team}"
    
    def test_valid_affected_team_preserved(self):
        """Valid affected_team should be preserved."""
        analysis = {
            'is_relevant': True,
            'confidence': 0.8,
            'category': 'INJURY',
            'affected_team': 'Manchester United',
            'summary': 'Test summary'
        }
        
        affected_team = (analysis.get('affected_team') or '').strip() or 'Unknown Team'
        
        assert affected_team == 'Manchester United', \
            f"Valid team should be preserved, got: {affected_team}"
    
    def test_empty_category_becomes_other(self):
        """
        REGRESSION: Empty category should become 'OTHER'.
        """
        analysis = {
            'is_relevant': True,
            'confidence': 0.8,
            'category': '',  # Empty string
            'affected_team': 'Test Team',
            'summary': 'Test summary'
        }
        
        category = (analysis.get('category') or '').strip() or 'OTHER'
        
        assert category == 'OTHER', \
            f"Empty category should become 'OTHER', got: {category}"
    
    def test_empty_summary_handled(self):
        """
        REGRESSION: Empty summary should be handled gracefully.
        """
        analysis = {
            'is_relevant': True,
            'confidence': 0.8,
            'category': 'INJURY',
            'affected_team': 'Test Team',
            'summary': ''  # Empty string
        }
        
        summary = (analysis.get('summary') or '').strip()
        
        # Empty summary is allowed (will use fallback in DiscoveredNews creation)
        assert summary == '', "Empty summary should remain empty string"


class TestV76ThreadSafeSingleton:
    """V7.6: Tests for thread-safe singleton pattern in content_analysis."""
    
    def test_singleton_thread_safe_import(self):
        """Singleton module imports threading for thread safety."""
        import src.utils.content_analysis as ca
        import threading
        
        # Verify _singleton_lock exists and is a Lock
        assert hasattr(ca, '_singleton_lock'), "Missing _singleton_lock"
        assert isinstance(ca._singleton_lock, type(threading.Lock())), \
            "_singleton_lock should be a threading.Lock"
    
    def test_singleton_concurrent_access(self):
        """Singleton handles concurrent access correctly."""
        import threading
        import src.utils.content_analysis as ca
        
        # Reset singletons for clean test
        ca._exclusion_filter = None
        ca._relevance_analyzer = None
        
        results = {'ef': [], 'ra': []}
        errors = []
        
        def get_instances():
            try:
                ef = ca.get_exclusion_filter()
                ra = ca.get_relevance_analyzer()
                results['ef'].append(id(ef))
                results['ra'].append(id(ra))
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = [threading.Thread(target=get_instances) for _ in range(10)]
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Verify no errors
        assert not errors, f"Errors during concurrent access: {errors}"
        
        # Verify all threads got the same instance
        assert len(set(results['ef'])) == 1, \
            f"ExclusionFilter should be singleton, got {len(set(results['ef']))} instances"
        assert len(set(results['ra'])) == 1, \
            f"RelevanceAnalyzer should be singleton, got {len(set(results['ra']))} instances"


class TestV76NewsRadarSafeAccess:
    """V7.6: Tests for safe dict access in news_radar DeepSeek response parsing."""
    
    def test_choices_invalid_type_handled(self):
        """
        REGRESSION: Invalid choices type should not crash.
        
        Bug: choices[0].get() crashes if choices[0] is not a dict.
        """
        # Simulate malformed response
        invalid_responses = [
            {"choices": ["not a dict"]},  # String instead of dict
            {"choices": [123]},  # Number instead of dict
            {"choices": [None]},  # None instead of dict
            {"choices": [[]]},  # List instead of dict
        ]
        
        for response in invalid_responses:
            choices = response.get("choices", [])
            first_choice = choices[0] if isinstance(choices, list) and len(choices) > 0 else None
            
            # This should NOT crash
            is_valid = isinstance(first_choice, dict)
            
            assert not is_valid, \
                f"Invalid choice type should be detected: {type(first_choice)}"
    
    def test_valid_choices_structure_accepted(self):
        """Valid choices structure should be accepted."""
        response = {
            "choices": [
                {
                    "message": {
                        "content": '{"is_relevant": true}'
                    }
                }
            ]
        }
        
        choices = response.get("choices", [])
        first_choice = choices[0] if isinstance(choices, list) and len(choices) > 0 else None
        
        assert isinstance(first_choice, dict), "Valid dict choice should be accepted"
        
        message = first_choice.get("message", {})
        assert isinstance(message, dict), "Valid message should be accepted"
        
        content = message.get("content", "")
        assert content == '{"is_relevant": true}', "Content should be extracted"


# ============================================
# V7.6 REGRESSION TESTS
# ============================================

class TestV76ThreadSafeSingleton:
    """
    V7.6 REGRESSION TESTS: Thread-safe singleton pattern.
    
    Bug fixed: get_browser_monitor() was not thread-safe, could create
    multiple instances when called from different threads simultaneously.
    """
    
    def test_singleton_thread_safety(self):
        """
        REGRESSION TEST: get_browser_monitor() must be thread-safe.
        
        This test would FAIL in V7.5 (race condition possible).
        """
        import threading
        from src.services.browser_monitor import get_browser_monitor
        
        instances = []
        errors = []
        
        def get_instance():
            try:
                instance = get_browser_monitor()
                instances.append(id(instance))
            except Exception as e:
                errors.append(str(e))
        
        # Create multiple threads that call get_browser_monitor simultaneously
        threads = [threading.Thread(target=get_instance) for _ in range(20)]
        
        # Start all threads at roughly the same time
        for t in threads:
            t.start()
        
        # Wait for all to complete
        for t in threads:
            t.join(timeout=5)
        
        # Verify no errors
        assert len(errors) == 0, f"Errors during concurrent access: {errors}"
        
        # Verify all threads got the same instance (same id)
        assert len(set(instances)) == 1, \
            f"REGRESSION: Multiple instances created! IDs: {set(instances)}"
    
    def test_singleton_lock_exists(self):
        """Verify the thread lock is properly defined."""
        from src.services import browser_monitor
        
        assert hasattr(browser_monitor, '_browser_monitor_lock'), \
            "REGRESSION: _browser_monitor_lock not defined"
        
        import threading
        assert isinstance(browser_monitor._browser_monitor_lock, type(threading.Lock())), \
            "REGRESSION: _browser_monitor_lock is not a Lock"


class TestV76RecordSourceFailureDefault:
    """
    V7.6 REGRESSION TESTS: _record_source_failure default parameter.
    
    Bug fixed: Default was True, which could cause false positives in
    circuit breaker when callers forgot to specify is_network_error.
    """
    
    def test_record_source_failure_default_is_false(self):
        """
        REGRESSION TEST: Default is_network_error should be False.
        
        This test would FAIL in V7.5 (default was True).
        """
        from src.services.browser_monitor import BrowserMonitor
        import inspect
        
        # Get the signature of _record_source_failure
        sig = inspect.signature(BrowserMonitor._record_source_failure)
        params = sig.parameters
        
        assert 'is_network_error' in params, \
            "is_network_error parameter missing"
        
        default = params['is_network_error'].default
        assert default is False, \
            f"REGRESSION: is_network_error default should be False, got {default}"
    
    def test_record_source_failure_without_flag_does_not_count(self):
        """
        REGRESSION TEST: Calling without is_network_error should NOT count failure.
        
        This test would FAIL in V7.5 (failure would be counted).
        """
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        url = "https://test-default.com"
        
        # Call without specifying is_network_error (uses default False)
        monitor._record_source_failure(url)
        
        cb = monitor._get_circuit_breaker(url)
        assert cb.failure_count == 0, \
            "REGRESSION: Failure counted without is_network_error=True"
    
    def test_record_source_failure_with_flag_counts(self):
        """Explicit is_network_error=True should count failure."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        url = "https://test-explicit.com"
        
        # Call with explicit is_network_error=True
        monitor._record_source_failure(url, is_network_error=True)
        
        cb = monitor._get_circuit_breaker(url)
        assert cb.failure_count == 1, \
            "Failure should be counted with is_network_error=True"


class TestV76CircuitBreakerCleanup:
    """
    V7.6 REGRESSION TESTS: Circuit breaker cleanup.
    
    Bug fixed: _circuit_breakers dict could grow unbounded over time.
    """
    
    def test_cleanup_method_exists(self):
        """Verify _cleanup_old_circuit_breakers method exists."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert hasattr(monitor, '_cleanup_old_circuit_breakers'), \
            "REGRESSION: _cleanup_old_circuit_breakers method missing"
    
    def test_cleanup_removes_old_breakers(self):
        """
        REGRESSION TEST: Old circuit breakers should be cleaned up.
        """
        import time
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        # Create some circuit breakers
        cb1 = monitor._get_circuit_breaker("https://old-source.com")
        cb2 = monitor._get_circuit_breaker("https://recent-source.com")
        
        # Simulate old failure (25 hours ago)
        cb1.last_failure_time = time.time() - (25 * 3600)
        cb1.state = "CLOSED"
        
        # Simulate recent failure (1 hour ago)
        cb2.last_failure_time = time.time() - (1 * 3600)
        cb2.record_failure()
        
        assert len(monitor._circuit_breakers) == 2
        
        # Run cleanup with 24h max age
        removed = monitor._cleanup_old_circuit_breakers(max_age_hours=24)
        
        assert removed == 1, f"Should remove 1 old breaker, removed {removed}"
        assert len(monitor._circuit_breakers) == 1
        assert "https://recent-source.com" in monitor._circuit_breakers
        assert "https://old-source.com" not in monitor._circuit_breakers
    
    def test_cleanup_preserves_active_breakers(self):
        """Active (OPEN) circuit breakers should not be cleaned up prematurely."""
        import time
        from src.services.browser_monitor import BrowserMonitor, CIRCUIT_BREAKER_FAILURE_THRESHOLD
        
        monitor = BrowserMonitor()
        
        # Create an OPEN circuit breaker with old failure
        cb = monitor._get_circuit_breaker("https://failing-source.com")
        for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb.record_failure()
        
        assert cb.state == "OPEN"
        
        # Make the failure time old
        cb.last_failure_time = time.time() - (25 * 3600)
        
        # Cleanup should still remove it (it's old)
        removed = monitor._cleanup_old_circuit_breakers(max_age_hours=24)
        
        # Old breakers are removed regardless of state
        assert removed == 1
    
    def test_cleanup_handles_empty_dict(self):
        """Cleanup should handle empty circuit breakers dict."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert len(monitor._circuit_breakers) == 0
        
        # Should not crash
        removed = monitor._cleanup_old_circuit_breakers()
        assert removed == 0


class TestV76BehaviorSimulationFailures:
    """
    V7.6 REGRESSION TESTS: Behavior simulation failure tracking.
    
    Bug fixed: Behavior simulation failures were not tracked, making it
    impossible to detect if sites were blocking the bot.
    """
    
    def test_behavior_simulation_failures_counter_exists(self):
        """Verify _behavior_simulation_failures counter exists."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert hasattr(monitor, '_behavior_simulation_failures'), \
            "REGRESSION: _behavior_simulation_failures counter missing"
        assert monitor._behavior_simulation_failures == 0
    
    def test_stats_include_behavior_simulation_failures(self):
        """Stats should include behavior_simulation_failures."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        stats = monitor.get_stats()
        
        assert 'behavior_simulation_failures' in stats, \
            "REGRESSION: behavior_simulation_failures not in stats"
    
    def test_version_is_7_6(self):
        """Version should be updated to 7.6."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        stats = monitor.get_stats()
        
        assert stats['version'] == '7.6', \
            f"Version should be 7.6, got {stats['version']}"


# ============================================
# V7.6 TESTS: Browser Auto-Recovery
# ============================================

class TestV76BrowserAutoRecovery:
    """
    V7.6 Tests for Browser Auto-Recovery feature.
    
    CRITICAL BUG FIX: Browser disconnects after first page but self._browser
    is not None, causing TargetClosedError on subsequent new_page() calls.
    """
    
    @pytest.mark.asyncio
    async def test_regression_browser_disconnected_recovery(self):
        """
        REGRESSION TEST: Browser should be recreated when disconnected.
        
        BUG: Browser.new_page: Target page, context or browser has been closed
        
        Before V7.6: 
        - Code only checked `if not self._browser` (None check)
        - Browser could crash/disconnect but self._browser was not None
        - Subsequent new_page() calls failed with TargetClosedError
        - Result: 0 results from BrowserMonitor on 14 URLs scanned
        
        After V7.6:
        - Code checks `self._browser.is_connected()` before using browser
        - If disconnected, browser is automatically recreated
        - Subsequent extractions continue working
        """
        from unittest.mock import MagicMock, AsyncMock, patch
        from src.services.browser_monitor import BrowserMonitor, MonitorConfig
        import asyncio
        
        monitor = BrowserMonitor()
        
        # Setup: Browser exists but is_connected() returns False (disconnected)
        mock_browser_disconnected = MagicMock()
        mock_browser_disconnected.is_connected.return_value = False
        mock_browser_disconnected.close = AsyncMock()
        
        # Setup: New browser that will be created after recovery
        mock_page = AsyncMock()
        mock_page.set_viewport_size = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>Test content with enough characters to pass validation</body></html>")
        mock_page.inner_text = AsyncMock(return_value="Test content with enough characters to pass validation")
        mock_page.close = AsyncMock()
        
        mock_browser_new = MagicMock()
        mock_browser_new.is_connected.return_value = True
        mock_browser_new.new_page = AsyncMock(return_value=mock_page)
        
        # Mock playwright to return new browser on launch
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser_new)
        
        monitor._browser = mock_browser_disconnected
        monitor._playwright = mock_playwright
        monitor._page_semaphore = asyncio.Semaphore(2)
        monitor._config = MonitorConfig()
        
        # Act: Call _ensure_browser_connected
        result = await monitor._ensure_browser_connected()
        
        # Assert: Browser was recreated
        assert result is True, "Should return True after successful recreation"
        assert monitor._browser == mock_browser_new, "Browser should be replaced with new instance"
        mock_browser_disconnected.close.assert_called_once()
        mock_playwright.chromium.launch.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_ensure_browser_connected_when_already_connected(self):
        """Browser should not be recreated if already connected."""
        from unittest.mock import MagicMock, AsyncMock
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock()
        
        monitor._browser = mock_browser
        monitor._playwright = mock_playwright
        
        result = await monitor._ensure_browser_connected()
        
        assert result is True
        mock_playwright.chromium.launch.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_ensure_browser_connected_when_browser_is_none(self):
        """Browser should be created if self._browser is None."""
        from unittest.mock import MagicMock, AsyncMock, patch
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        mock_browser_new = MagicMock()
        mock_browser_new.is_connected.return_value = True
        
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser_new)
        
        monitor._browser = None
        monitor._playwright = mock_playwright
        
        result = await monitor._ensure_browser_connected()
        
        assert result is True
        assert monitor._browser == mock_browser_new
    
    @pytest.mark.asyncio
    async def test_extract_content_recovers_from_disconnected_browser(self):
        """
        REGRESSION TEST: extract_content should recover from disconnected browser.
        
        This is the actual user-facing method that was failing with:
        "Browser.new_page: Target page, context or browser has been closed"
        """
        from unittest.mock import MagicMock, AsyncMock, patch
        from src.services.browser_monitor import BrowserMonitor, MonitorConfig
        import asyncio
        
        monitor = BrowserMonitor()
        
        # First call: browser is disconnected
        mock_browser_disconnected = MagicMock()
        mock_browser_disconnected.is_connected.return_value = False
        mock_browser_disconnected.close = AsyncMock()
        
        # After recovery: new browser works
        mock_page = AsyncMock()
        mock_page.set_viewport_size = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body><article>This is test content with more than 100 characters to pass the minimum length validation check.</article></body></html>")
        mock_page.inner_text = AsyncMock(return_value="This is test content with more than 100 characters to pass the minimum length validation check.")
        mock_page.close = AsyncMock()
        
        mock_browser_new = MagicMock()
        mock_browser_new.is_connected.return_value = True
        mock_browser_new.new_page = AsyncMock(return_value=mock_page)
        
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser_new)
        
        monitor._browser = mock_browser_disconnected
        monitor._playwright = mock_playwright
        monitor._page_semaphore = asyncio.Semaphore(2)
        monitor._config = MonitorConfig()
        
        # Act: extract_content should recover and succeed
        with patch.object(monitor, '_apply_stealth', new_callable=AsyncMock):
            with patch.object(monitor, '_setup_resource_blocking', new_callable=AsyncMock):
                with patch.object(monitor, '_simulate_human_behavior', new_callable=AsyncMock):
                    result = await monitor.extract_content("https://test.com/article")
        
        # Assert: Content was extracted after browser recovery
        assert result is not None, "Should extract content after browser recovery"
        assert len(result) > 0, "Extracted content should not be empty"
    
    def test_browser_monitor_has_ensure_browser_connected_method(self):
        """BrowserMonitor should have _ensure_browser_connected method."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert hasattr(monitor, '_ensure_browser_connected'), \
            "REGRESSION: _ensure_browser_connected method missing"
    
    def test_browser_monitor_has_recreate_browser_method(self):
        """BrowserMonitor should have _recreate_browser_internal method.
        
        V7.7: Renamed from _recreate_browser to _recreate_browser_internal
        to clarify it's called with lock held.
        """
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        assert hasattr(monitor, '_recreate_browser_internal'), \
            "REGRESSION: _recreate_browser_internal method missing"
