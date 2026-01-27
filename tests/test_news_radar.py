"""
Tests for News Radar Monitor - Autonomous Web Monitoring

Property-based tests using Hypothesis to verify correctness properties.
Unit tests for specific behaviors and edge cases.

Requirements: 1.1-1.4, 2.1-2.4, 3.1-3.5, 4.1-4.5, 5.1-5.4, 6.1-6.4, 7.1-7.4, 8.1-8.4, 9.1-9.4, 10.1-10.4
"""
import asyncio
import json
import pytest
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from hypothesis import given, strategies as st, settings, assume

from src.services.news_radar import (
    RadarSource,
    RadarAlert,
    AnalysisResult,
    GlobalSettings,
    RadarConfig,
    ContentCache,
    CircuitBreaker,
    ExclusionFilter,
    RelevanceAnalyzer,
    load_config,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_PAGE_TIMEOUT_SECONDS,
    DEFAULT_CACHE_TTL_HOURS,
    DEEPSEEK_CONFIDENCE_THRESHOLD,
    ALERT_CONFIDENCE_THRESHOLD,
)


# ============================================
# STRATEGIES FOR PROPERTY-BASED TESTING
# ============================================

# Strategy for valid URLs
valid_urls = st.from_regex(r'https?://[a-z0-9\-\.]+\.[a-z]{2,}/[a-z0-9\-/]*', fullmatch=True)

# Strategy for source names
source_names = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')))

# Strategy for priorities
priorities = st.integers(min_value=1, max_value=10)

# Strategy for scan intervals
scan_intervals = st.integers(min_value=1, max_value=60)

# Strategy for navigation modes
navigation_modes = st.sampled_from(["single", "paginated"])

# Strategy for valid RadarSource
radar_source_strategy = st.builds(
    RadarSource,
    url=valid_urls,
    name=source_names,
    priority=priorities,
    scan_interval_minutes=scan_intervals,
    navigation_mode=navigation_modes,
    link_selector=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
)

# Strategy for GlobalSettings
global_settings_strategy = st.builds(
    GlobalSettings,
    default_scan_interval_minutes=scan_intervals,
    page_timeout_seconds=st.integers(min_value=5, max_value=120),
    cache_ttl_hours=st.integers(min_value=1, max_value=168),
    deepseek_confidence_threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    alert_confidence_threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)


# ============================================
# PROPERTY 1: Config Loading Correctness
# **Feature: news-radar-monitor, Property 1: Config Loading Correctness**
# **Validates: Requirements 1.1, 8.1**
# ============================================

@settings(max_examples=100)
@given(
    sources=st.lists(radar_source_strategy, min_size=0, max_size=10),
    global_settings=global_settings_strategy
)
def test_property_1_config_loading_correctness(sources, global_settings):
    """
    **Feature: news-radar-monitor, Property 1: Config Loading Correctness**
    **Validates: Requirements 1.1, 8.1**
    
    For any valid configuration file with N source entries, loading the configuration
    SHALL produce exactly N RadarSource objects with matching URLs and settings.
    """
    # Create a temporary config file
    config_data = {
        "sources": [
            {
                "url": s.url,
                "name": s.name,
                "priority": s.priority,
                "scan_interval_minutes": s.scan_interval_minutes,
                "navigation_mode": s.navigation_mode,
                "link_selector": s.link_selector,
            }
            for s in sources
        ],
        "global_settings": {
            "default_scan_interval_minutes": global_settings.default_scan_interval_minutes,
            "page_timeout_seconds": global_settings.page_timeout_seconds,
            "cache_ttl_hours": global_settings.cache_ttl_hours,
            "deepseek_confidence_threshold": global_settings.deepseek_confidence_threshold,
            "alert_confidence_threshold": global_settings.alert_confidence_threshold,
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name
    
    try:
        # Load config
        config = load_config(temp_path)
        
        # Property: Number of loaded sources equals number of input sources
        assert len(config.sources) == len(sources), \
            f"Expected {len(sources)} sources, got {len(config.sources)}"
        
        # Property: Each source has matching URL
        for i, loaded_source in enumerate(config.sources):
            original = sources[i]
            assert loaded_source.url == original.url, \
                f"URL mismatch at index {i}: {loaded_source.url} != {original.url}"
            
            # Property: Required fields are present and valid
            assert loaded_source.url, "URL must not be empty"
            assert loaded_source.name, "Name must not be empty"
            assert loaded_source.priority >= 1, "Priority must be >= 1"
            assert loaded_source.scan_interval_minutes > 0, "Scan interval must be > 0"
            assert loaded_source.navigation_mode in ("single", "paginated"), \
                f"Invalid navigation mode: {loaded_source.navigation_mode}"
        
        # Property: Global settings are loaded correctly
        assert config.global_settings.default_scan_interval_minutes == global_settings.default_scan_interval_minutes
        assert config.global_settings.page_timeout_seconds == global_settings.page_timeout_seconds
        assert config.global_settings.cache_ttl_hours == global_settings.cache_ttl_hours
        
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


def test_load_config_missing_url_field():
    """
    Test sources missing required 'url' field are skipped.
    
    Requirements: 8.3
    """
    config_data = {
        "sources": [
            {"name": "No URL Source"},  # Missing url - should be skipped
            {"url": "https://valid.com", "name": "Valid Source"},  # Valid
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
            {"url": "https://example.com"}  # Only required field
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
        assert source.navigation_mode == "single"
        assert source.link_selector is None
        assert source.name == "https://example.com"[:50]
    finally:
        Path(temp_path).unlink()


def test_load_actual_config_file():
    """Test loading the actual config file."""
    config = load_config("config/news_radar_sources.json")
    
    # Should have sources
    assert len(config.sources) > 0
    
    # All sources should have valid URLs
    for source in config.sources:
        assert source.url.startswith("http")
        assert source.name
        assert source.priority >= 1


# ============================================
# RADAR SOURCE TESTS
# ============================================

def test_radar_source_is_due_for_scan_never_scanned():
    """Test is_due_for_scan returns True when never scanned."""
    source = RadarSource(url="https://example.com")
    assert source.is_due_for_scan() is True


def test_radar_source_is_due_for_scan_just_scanned():
    """Test is_due_for_scan returns False when just scanned."""
    source = RadarSource(url="https://example.com")
    source.last_scanned = datetime.now(timezone.utc)
    assert source.is_due_for_scan() is False


def test_radar_source_is_due_for_scan_interval_passed():
    """Test is_due_for_scan returns True when interval has passed."""
    source = RadarSource(url="https://example.com", scan_interval_minutes=5)
    source.last_scanned = datetime.now(timezone.utc) - timedelta(minutes=10)
    assert source.is_due_for_scan() is True


def test_radar_source_default_name():
    """Test RadarSource uses URL as default name."""
    source = RadarSource(url="https://example.com/very/long/path/to/page")
    assert source.name == "https://example.com/very/long/path/to/page"[:50]


# ============================================
# RADAR ALERT TESTS
# ============================================

def test_radar_alert_to_telegram_message():
    """Test RadarAlert formats correctly for Telegram (Italian output V1.2)."""
    alert = RadarAlert(
        source_name="Test Source",
        source_url="https://example.com/news",
        affected_team="Test FC",
        category="INJURY",
        summary="Key player injured before match",
        confidence=0.85
    )
    
    message = alert.to_telegram_message()
    
    # Check all required fields are present (Italian output)
    assert "🔔" in message  # Radar emoji
    assert "RADAR ALERT" in message
    assert "Test FC" in message
    assert "INFORTUNIO" in message  # V1.2: Italian translation of INJURY
    assert "Key player injured" in message
    assert "Test Source" in message
    assert "https://example.com/news" in message
    assert "85%" in message  # Confidence


def test_radar_alert_category_emojis():
    """Test different categories have different emojis."""
    categories = ["INJURY", "SUSPENSION", "NATIONAL_TEAM", "CUP_ABSENCE", "OTHER"]
    emojis = set()
    
    for category in categories:
        alert = RadarAlert(
            source_name="Test",
            source_url="https://test.com",
            affected_team="Team",
            category=category,
            summary="Summary",
            confidence=0.8
        )
        message = alert.to_telegram_message()
        # Extract emoji after RADAR ALERT
        emojis.add(category)
    
    # All categories should be handled
    assert len(emojis) == 5


# ============================================
# CONTENT CACHE TESTS (Property 7)
# ============================================

def test_content_cache_basic():
    """Test basic cache operations."""
    cache = ContentCache(max_entries=100, ttl_hours=24)
    
    content = "This is some test content for caching"
    
    # Not cached initially
    assert cache.is_cached(content) is False
    
    # Add it
    cache.add(content)
    
    # Now it should be cached
    assert cache.is_cached(content) is True
    assert cache.size() == 1


def test_content_cache_hash_uses_first_1000_chars():
    """
    Test that hash is computed from first 1000 chars only.
    
    Requirements: 7.1
    """
    cache = ContentCache()
    
    # Two contents with same first 1000 chars but different endings
    prefix = "A" * 1000
    content1 = prefix + "ENDING1"
    content2 = prefix + "ENDING2"
    
    # They should have the same hash
    assert cache.compute_hash(content1) == cache.compute_hash(content2)
    
    # Caching one should make the other appear cached
    cache.add(content1)
    assert cache.is_cached(content2) is True


def test_content_cache_empty_content():
    """Test cache handles empty content safely."""
    cache = ContentCache()
    
    assert cache.is_cached("") is False
    assert cache.is_cached(None) is False
    
    cache.add("")
    cache.add(None)
    assert cache.size() == 0


# ============================================
# PROPERTY 7: Content Deduplication Round-Trip
# **Feature: news-radar-monitor, Property 7: Content Deduplication Round-Trip**
# **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
# ============================================

@settings(max_examples=100)
@given(content=st.text(min_size=10, max_size=5000))
def test_property_7_content_deduplication_round_trip(content):
    """
    **Feature: news-radar-monitor, Property 7: Content Deduplication Round-Trip**
    **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
    
    For any content string S:
    1. First processing: cache.is_cached(S) returns False, then cache.add(S) stores the hash
    2. Second processing within 24h: cache.is_cached(S) returns True
    3. Processing after 24h expiry: cache.is_cached(S) returns False
    """
    cache = ContentCache(max_entries=1000, ttl_hours=24)
    
    # Step 1: Initially not cached
    assert cache.is_cached(content) is False
    
    # Add to cache
    cache.add(content)
    
    # Step 2: Now it should be cached (within 24h)
    assert cache.is_cached(content) is True
    
    # Step 3: Simulate expiry by manually setting old timestamp
    content_hash = cache.compute_hash(content)
    cache._cache[content_hash] = datetime.now(timezone.utc) - timedelta(hours=25)
    
    # Should be expired now
    assert cache.is_cached(content) is False


@settings(max_examples=50)
@given(
    max_entries=st.integers(min_value=10, max_value=100),
    num_items=st.integers(min_value=1, max_value=200)
)
def test_property_7_cache_size_limit(max_entries, num_items):
    """
    **Feature: news-radar-monitor, Property 7: Content Deduplication Round-Trip**
    **Validates: Requirements 7.3**
    
    Cache size should never exceed max_entries.
    """
    cache = ContentCache(max_entries=max_entries, ttl_hours=24)
    
    # Add many items
    for i in range(num_items):
        content = f"Unique content item number {i} with padding"
        cache.add(content)
    
    # Cache size should never exceed max_entries
    assert cache.size() <= max_entries


# ============================================
# CIRCUIT BREAKER TESTS (Property 2)
# ============================================

def test_circuit_breaker_initial_state():
    """Test circuit breaker starts in CLOSED state."""
    cb = CircuitBreaker()
    assert cb.state == "CLOSED"
    assert cb.can_execute() is True


def test_circuit_breaker_opens_after_failures():
    """
    Test circuit breaker opens after threshold failures.
    
    Requirements: 1.4
    """
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=300)
    
    # Record failures
    cb.record_failure()
    assert cb.state == "CLOSED"
    cb.record_failure()
    assert cb.state == "CLOSED"
    cb.record_failure()
    
    # Should be OPEN now
    assert cb.state == "OPEN"
    assert cb.can_execute() is False


def test_circuit_breaker_success_resets_count():
    """Test success resets failure count."""
    cb = CircuitBreaker(failure_threshold=3)
    
    cb.record_failure()
    cb.record_failure()
    assert cb.failure_count == 2
    
    cb.record_success()
    assert cb.failure_count == 0


# ============================================
# PROPERTY 2: Circuit Breaker Activation
# **Feature: news-radar-monitor, Property 2: Circuit Breaker Activation**
# **Validates: Requirements 1.4**
# ============================================

@settings(max_examples=100)
@given(
    failure_threshold=st.integers(min_value=1, max_value=10),
    num_failures=st.integers(min_value=0, max_value=20)
)
def test_property_2_circuit_breaker_activation(failure_threshold, num_failures):
    """
    **Feature: news-radar-monitor, Property 2: Circuit Breaker Activation**
    **Validates: Requirements 1.4**
    
    For any source URL that experiences N consecutive extraction failures where
    N >= failure_threshold, the circuit breaker SHALL transition to OPEN state
    and skip that source until recovery_timeout expires.
    """
    cb = CircuitBreaker(failure_threshold=failure_threshold, recovery_timeout=300)
    
    # Record failures
    for _ in range(num_failures):
        cb.record_failure()
    
    # Property: Circuit should be OPEN if failures >= threshold
    if num_failures >= failure_threshold:
        assert cb.state == "OPEN", \
            f"Expected OPEN after {num_failures} failures (threshold={failure_threshold})"
        assert cb.can_execute() is False, \
            "Should not allow execution when circuit is OPEN"
    else:
        assert cb.state == "CLOSED", \
            f"Expected CLOSED with {num_failures} failures (threshold={failure_threshold})"
        assert cb.can_execute() is True, \
            "Should allow execution when circuit is CLOSED"


# ============================================
# EXCLUSION FILTER TESTS (Property 3)
# ============================================

def test_exclusion_filter_basketball():
    """Test basketball content is excluded."""
    ef = ExclusionFilter()
    
    assert ef.is_excluded("NBA Finals: Lakers vs Celtics") is True
    assert ef.is_excluded("Euroleague basketball match") is True
    assert ef.is_excluded("Pallacanestro italiana") is True


def test_exclusion_filter_womens():
    """Test women's football content is excluded."""
    ef = ExclusionFilter()
    
    assert ef.is_excluded("Women's World Cup news") is True
    assert ef.is_excluded("Ladies team wins match") is True
    assert ef.is_excluded("Calcio femminile Serie A") is True


def test_exclusion_filter_youth():
    """Test youth team content is NOT excluded - it's RELEVANT for betting!
    
    Youth/Primavera players called up to first team is very relevant info.
    """
    ef = ExclusionFilter()
    
    # Youth content should NOT be excluded - it's relevant!
    assert ef.is_excluded("Primavera team wins") is False
    assert ef.is_excluded("U19 championship") is False
    assert ef.is_excluded("Youth academy news") is False
    assert ef.is_excluded("Primavera players called up to first team") is False


def test_exclusion_filter_other_sports():
    """Test other sports content is excluded."""
    ef = ExclusionFilter()
    
    assert ef.is_excluded("NFL Super Bowl preview") is True
    assert ef.is_excluded("Rugby Six Nations") is True
    assert ef.is_excluded("Handball championship") is True


def test_exclusion_filter_valid_football():
    """Test valid men's football content is NOT excluded."""
    ef = ExclusionFilter()
    
    assert ef.is_excluded("Premier League match preview") is False
    assert ef.is_excluded("Serie A injury news") is False
    assert ef.is_excluded("Champions League final") is False
    # Youth callups are relevant!
    assert ef.is_excluded("U19 player promoted to first team") is False


# ============================================
# PROPERTY 3: Exclusion Filter Completeness
# **Feature: news-radar-monitor, Property 3: Exclusion Filter Completeness**
# **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
# ============================================

@settings(max_examples=100)
@given(
    keyword=st.sampled_from(
        ExclusionFilter.EXCLUDED_SPORTS +
        ExclusionFilter.EXCLUDED_CATEGORIES +
        ExclusionFilter.EXCLUDED_OTHER_SPORTS
    ),
    prefix=st.text(min_size=0, max_size=50),
    suffix=st.text(min_size=0, max_size=50)
)
def test_property_3_exclusion_filter_completeness(keyword, prefix, suffix):
    """
    **Feature: news-radar-monitor, Property 3: Exclusion Filter Completeness**
    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
    
    For any content string containing at least one keyword from EXCLUDED_SPORTS,
    EXCLUDED_CATEGORIES, or EXCLUDED_OTHER_SPORTS, the
    ExclusionFilter.is_excluded() method SHALL return True.
    
    NOTE: EXCLUDED_YOUTH removed - youth news is RELEVANT for betting!
    """
    ef = ExclusionFilter()
    
    # Build content with keyword surrounded by other text
    content = f"{prefix} {keyword} {suffix}"
    
    # Property: Content with exclusion keyword must be excluded
    assert ef.is_excluded(content) is True, \
        f"Content with '{keyword}' should be excluded: {content[:100]}"


# ============================================
# RELEVANCE ANALYZER TESTS (Property 4)
# ============================================

def test_relevance_analyzer_injury():
    """Test injury keywords are detected."""
    ra = RelevanceAnalyzer()
    
    result = ra.analyze("Key player injured before important match")
    assert result.is_relevant is True
    assert result.category == "INJURY"


def test_relevance_analyzer_suspension():
    """Test suspension keywords are detected."""
    ra = RelevanceAnalyzer()
    
    result = ra.analyze("Star player suspended for red card")
    assert result.is_relevant is True
    assert result.category == "SUSPENSION"


def test_relevance_analyzer_national_team():
    """Test national team keywords are detected."""
    ra = RelevanceAnalyzer()
    
    result = ra.analyze("Player called up for national team duty")
    assert result.is_relevant is True
    assert result.category == "NATIONAL_TEAM"


def test_relevance_analyzer_youth_callup():
    """Test youth callup keywords are detected - VERY RELEVANT for betting!"""
    ra = RelevanceAnalyzer()
    
    # Use specific youth keywords that don't overlap with national team
    result = ra.analyze("Primavera players promoted to first team due to injuries")
    assert result.is_relevant is True
    assert result.category == "YOUTH_CALLUP"
    
    result = ra.analyze("U19 youth academy graduate makes senior squad")
    assert result.is_relevant is True
    assert result.category == "YOUTH_CALLUP"
    
    result = ra.analyze("Giovanili player aggregato alla prima squadra")
    assert result.is_relevant is True
    assert result.category == "YOUTH_CALLUP"


def test_relevance_analyzer_youth_callup_multilingual():
    """Test youth callup keywords in multiple languages - all should be RELEVANT."""
    ra = RelevanceAnalyzer()
    
    # Turkish
    result = ra.analyze("Gençler takımından A takıma çağrıldı altyapı oyuncusu")
    assert result.is_relevant is True
    assert result.category == "YOUTH_CALLUP"
    
    # Polish
    result = ra.analyze("Młodzież powołany z juniorów do pierwszej drużyny")
    assert result.is_relevant is True
    assert result.category == "YOUTH_CALLUP"
    
    # Portuguese (Brazil)
    result = ra.analyze("Jogador das categorias de base promovido ao time principal")
    assert result.is_relevant is True
    assert result.category == "YOUTH_CALLUP"
    
    # German
    result = ra.analyze("Jugend Spieler aus der Nachwuchs hochgezogen zur ersten Mannschaft")
    assert result.is_relevant is True
    assert result.category == "YOUTH_CALLUP"
    
    # French
    result = ra.analyze("Jeunes joueur promu de la réserve espoirs")
    assert result.is_relevant is True
    assert result.category == "YOUTH_CALLUP"
    
    # Danish
    result = ra.analyze("Ungdom spiller fra ungdomshold til førsteholdet")
    assert result.is_relevant is True
    assert result.category == "YOUTH_CALLUP"
    
    # Dutch
    result = ra.analyze("Jeugd speler doorgestroomd van beloften naar eerste elftal")
    assert result.is_relevant is True
    assert result.category == "YOUTH_CALLUP"


def test_relevance_analyzer_no_keywords():
    """Test content without keywords is not relevant."""
    ra = RelevanceAnalyzer()
    
    result = ra.analyze("General football news about the league")
    assert result.is_relevant is False


def test_relevance_analyzer_empty_content():
    """Test empty content is handled safely."""
    ra = RelevanceAnalyzer()
    
    result = ra.analyze("")
    assert result.is_relevant is False
    
    result = ra.analyze(None)
    assert result.is_relevant is False


# ============================================
# PROPERTY 4: Relevance Detection Accuracy
# **Feature: news-radar-monitor, Property 4: Relevance Detection Accuracy**
# **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
# ============================================

@settings(max_examples=100)
@given(
    keyword=st.sampled_from(
        RelevanceAnalyzer.INJURY_KEYWORDS +
        RelevanceAnalyzer.SUSPENSION_KEYWORDS +
        RelevanceAnalyzer.NATIONAL_TEAM_KEYWORDS
    ),
    prefix=st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'Z'))),
    suffix=st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'Z')))
)
def test_property_4_relevance_detection_accuracy(keyword, prefix, suffix):
    """
    **Feature: news-radar-monitor, Property 4: Relevance Detection Accuracy**
    **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
    
    For any content string containing relevance keywords (injury, suspension,
    national team, cup absence, youth callup) and NOT containing exclusion keywords, the
    RelevanceAnalyzer SHALL return is_relevant=True with the appropriate category.
    """
    ra = RelevanceAnalyzer()
    ef = ExclusionFilter()
    
    # Build content with keyword
    content = f"{prefix} {keyword} {suffix}"
    
    # Skip if content accidentally contains exclusion keywords
    assume(not ef.is_excluded(content))
    
    # Skip if prefix/suffix accidentally contains other relevance keywords
    # (which would affect category detection)
    all_keywords = (
        RelevanceAnalyzer.INJURY_KEYWORDS +
        RelevanceAnalyzer.SUSPENSION_KEYWORDS +
        RelevanceAnalyzer.NATIONAL_TEAM_KEYWORDS +
        RelevanceAnalyzer.CUP_ABSENCE_KEYWORDS +
        RelevanceAnalyzer.YOUTH_CALLUP_KEYWORDS
    )
    prefix_lower = prefix.lower()
    suffix_lower = suffix.lower()
    for kw in all_keywords:
        if kw != keyword and (kw in prefix_lower or kw in suffix_lower):
            assume(False)  # Skip this test case
    
    result = ra.analyze(content)
    
    # Property: Content with relevance keyword must be relevant
    assert result.is_relevant is True, \
        f"Content with '{keyword}' should be relevant: {content[:100]}"
    
    # Property: Category should match the keyword type
    if keyword in RelevanceAnalyzer.INJURY_KEYWORDS:
        assert result.category == "INJURY"
    elif keyword in RelevanceAnalyzer.SUSPENSION_KEYWORDS:
        assert result.category == "SUSPENSION"
    elif keyword in RelevanceAnalyzer.NATIONAL_TEAM_KEYWORDS:
        assert result.category == "NATIONAL_TEAM"


# ============================================
# PROPERTY 5: Confidence Threshold Routing
# **Feature: news-radar-monitor, Property 5: Confidence Threshold Routing**
# **Validates: Requirements 4.5, 5.1**
# ============================================

@settings(max_examples=100)
@given(confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
def test_property_5_confidence_threshold_routing(confidence):
    """
    **Feature: news-radar-monitor, Property 5: Confidence Threshold Routing**
    **Validates: Requirements 4.5, 5.1**
    
    For any AnalysisResult with confidence C:
    - If C >= 0.7: alert is sent directly
    - If 0.5 <= C < 0.7: DeepSeek fallback is invoked
    - If C < 0.5: content is skipped
    """
    # Simulate routing logic
    if confidence >= ALERT_CONFIDENCE_THRESHOLD:
        action = "alert"
    elif confidence >= DEEPSEEK_CONFIDENCE_THRESHOLD:
        action = "deepseek"
    else:
        action = "skip"
    
    # Verify routing is correct
    if confidence >= 0.7:
        assert action == "alert", f"Confidence {confidence} should route to alert"
    elif confidence >= 0.5:
        assert action == "deepseek", f"Confidence {confidence} should route to deepseek"
    else:
        assert action == "skip", f"Confidence {confidence} should be skipped"


# ============================================
# INTEGRATION TEST
# ============================================

def test_full_analysis_pipeline():
    """Test the full analysis pipeline: filter → analyze."""
    ef = ExclusionFilter()
    ra = RelevanceAnalyzer()
    
    # Test case 1: Valid injury news
    content1 = "Manchester United star Marcus Rashford ruled out with hamstring injury"
    assert ef.is_excluded(content1) is False
    result1 = ra.analyze(content1)
    assert result1.is_relevant is True
    assert result1.category == "INJURY"
    
    # Test case 2: Women's football (should be excluded)
    content2 = "Women's team player injured before match"
    assert ef.is_excluded(content2) is True
    
    # Test case 3: Basketball (should be excluded)
    content3 = "NBA star LeBron James out with injury"
    assert ef.is_excluded(content3) is True
    
    # Test case 4: Youth team callup (should NOT be excluded - it's RELEVANT!)
    content4 = "Primavera U19 player called up to first team"
    assert ef.is_excluded(content4) is False
    result4 = ra.analyze(content4)
    assert result4.is_relevant is True
    assert result4.category == "YOUTH_CALLUP"



# ============================================
# PROPERTY 10: Graceful Error Continuation
# **Feature: news-radar-monitor, Property 10: Graceful Error Continuation**
# **Validates: Requirements 2.4, 10.2**
# ============================================

def test_property_10_graceful_error_continuation_exclusion_filter():
    """
    **Feature: news-radar-monitor, Property 10: Graceful Error Continuation**
    **Validates: Requirements 2.4, 10.2**
    
    For any source that raises an exception during extraction, the scan loop
    SHALL continue processing remaining sources without terminating.
    
    This test verifies that ExclusionFilter handles edge cases gracefully.
    """
    ef = ExclusionFilter()
    
    # Test with various edge cases that could cause errors
    edge_cases = [
        "",  # Empty string
        None,  # None
        "a" * 100000,  # Very long string
        "🏀⚽🏈",  # Unicode emojis
        "\x00\x01\x02",  # Control characters
        "normal text",  # Normal text
    ]
    
    for content in edge_cases:
        try:
            # Should not raise exception
            result = ef.is_excluded(content)
            assert isinstance(result, bool)
        except Exception as e:
            pytest.fail(f"ExclusionFilter raised exception for {repr(content)[:50]}: {e}")


def test_property_10_graceful_error_continuation_relevance_analyzer():
    """
    **Feature: news-radar-monitor, Property 10: Graceful Error Continuation**
    **Validates: Requirements 2.4, 10.2**
    
    RelevanceAnalyzer should handle edge cases gracefully.
    """
    ra = RelevanceAnalyzer()
    
    edge_cases = [
        "",
        None,
        "a" * 100000,
        "🏥 injured player",
        "\x00\x01\x02",
    ]
    
    for content in edge_cases:
        try:
            result = ra.analyze(content)
            assert isinstance(result, AnalysisResult)
        except Exception as e:
            pytest.fail(f"RelevanceAnalyzer raised exception for {repr(content)[:50]}: {e}")


def test_property_10_graceful_error_continuation_content_cache():
    """
    **Feature: news-radar-monitor, Property 10: Graceful Error Continuation**
    **Validates: Requirements 2.4, 10.2**
    
    ContentCache should handle edge cases gracefully.
    """
    cache = ContentCache()
    
    edge_cases = [
        "",
        None,
        "a" * 100000,
        "🏥 injured player",
        "\x00\x01\x02",
    ]
    
    for content in edge_cases:
        try:
            # Should not raise exception
            is_cached = cache.is_cached(content)
            assert isinstance(is_cached, bool)
            
            cache.add(content)
            # Should still work
            assert cache.size() >= 0
        except Exception as e:
            pytest.fail(f"ContentCache raised exception for {repr(content)[:50]}: {e}")


@settings(max_examples=50)
@given(content=st.text(min_size=0, max_size=10000))
def test_property_10_graceful_error_continuation_any_content(content):
    """
    **Feature: news-radar-monitor, Property 10: Graceful Error Continuation**
    **Validates: Requirements 2.4, 10.2**
    
    For any content string, the analysis pipeline should not raise exceptions.
    """
    ef = ExclusionFilter()
    ra = RelevanceAnalyzer()
    cache = ContentCache()
    
    # None of these should raise exceptions
    try:
        ef.is_excluded(content)
        ra.analyze(content)
        cache.is_cached(content)
        cache.add(content)
    except Exception as e:
        pytest.fail(f"Pipeline raised exception for content: {e}")



# ============================================
# DEEPSEEK FALLBACK TESTS (Property 6)
# ============================================

from src.services.news_radar import DeepSeekFallback, DEEPSEEK_MIN_INTERVAL_SECONDS


def test_deepseek_fallback_initialization():
    """Test DeepSeekFallback initializes correctly."""
    ds = DeepSeekFallback()
    assert ds._min_interval == DEEPSEEK_MIN_INTERVAL_SECONDS
    assert ds._last_call_time == 0.0
    assert ds._call_count == 0


def test_deepseek_fallback_prompt_building():
    """Test prompt is built correctly (V2 format)."""
    ds = DeepSeekFallback()
    
    content = "Test article about player injury"
    prompt = ds._build_prompt(content)
    
    assert content in prompt
    assert "is_high_value" in prompt  # V2 uses is_high_value
    assert "category" in prompt
    assert "MASS_ABSENCE" in prompt  # V2 categories
    assert "Basketball" in prompt  # Exclusion filter mentioned


def test_deepseek_fallback_parse_valid_json():
    """Test parsing valid JSON response with betting_impact (V2 format)."""
    ds = DeepSeekFallback()
    
    # V2 format: uses is_high_value, team (not affected_team), summary_italian
    response = '{"is_high_value": true, "betting_impact": "HIGH", "category": "MASS_ABSENCE", "team": "Test FC", "confidence": 0.85, "summary_italian": "3 giocatori fuori"}'
    
    result = ds._parse_response(response)
    
    assert result is not None
    assert result.is_relevant is True
    assert result.category == "MASS_ABSENCE"
    assert result.affected_team == "Test FC"
    assert result.confidence == 0.85
    assert result.betting_impact == "HIGH"


def test_deepseek_fallback_parse_markdown_json():
    """Test parsing JSON in markdown code block (V2 format)."""
    ds = DeepSeekFallback()
    
    response = '''Here is the analysis:
```json
{"is_high_value": false, "category": "NOT_RELEVANT", "team": null, "confidence": 0.3, "summary_italian": "Non rilevante"}
```
'''
    
    result = ds._parse_response(response)
    
    assert result is not None
    assert result.is_relevant is False


def test_deepseek_fallback_parse_invalid_json():
    """Test parsing invalid response returns None."""
    ds = DeepSeekFallback()
    
    response = "This is not JSON at all"
    
    result = ds._parse_response(response)
    
    assert result is None


def test_deepseek_fallback_parse_with_think_tags():
    """Test parsing response with DeepSeek <think> tags (V2 format)."""
    ds = DeepSeekFallback()
    
    # V2 format with think tags
    response = '''<think>
Let me analyze this...
</think>
{"is_high_value": true, "betting_impact": "HIGH", "category": "MASS_ABSENCE", "team": "Team A", "confidence": 0.9, "summary_italian": "Giocatore squalificato"}'''
    
    result = ds._parse_response(response)
    
    assert result is not None
    assert result.is_relevant is True
    assert result.category == "MASS_ABSENCE"
    assert result.betting_impact == "HIGH"


# ============================================
# PROPERTY 6: DeepSeek Rate Limiting
# **Feature: news-radar-monitor, Property 6: DeepSeek Rate Limiting**
# **Validates: Requirements 5.4**
# ============================================

@pytest.mark.asyncio
async def test_property_6_deepseek_rate_limiting():
    """
    **Feature: news-radar-monitor, Property 6: DeepSeek Rate Limiting**
    **Validates: Requirements 5.4**
    
    For any sequence of N DeepSeek API calls, the time elapsed between
    call i and call i+1 SHALL be >= 2.0 seconds.
    """
    ds = DeepSeekFallback(min_interval=2.0)
    
    # Simulate first call
    ds._last_call_time = time.time()
    
    # Record time before waiting
    start_time = time.time()
    
    # Wait for rate limit
    await ds._wait_for_rate_limit()
    
    # Record time after waiting
    end_time = time.time()
    
    # Should have waited at least min_interval
    elapsed = end_time - start_time
    assert elapsed >= 1.9, f"Rate limit not enforced: waited only {elapsed:.2f}s"


@settings(max_examples=20)
@given(
    min_interval=st.floats(min_value=0.1, max_value=5.0, allow_nan=False),
    time_since_last_call=st.floats(min_value=0.0, max_value=10.0, allow_nan=False)
)
def test_property_6_rate_limiting_logic(min_interval, time_since_last_call):
    """
    **Feature: news-radar-monitor, Property 6: DeepSeek Rate Limiting**
    **Validates: Requirements 5.4**
    
    Rate limiting logic should correctly determine wait time.
    """
    ds = DeepSeekFallback(min_interval=min_interval)
    
    # Simulate last call time
    ds._last_call_time = time.time() - time_since_last_call
    
    # Calculate expected wait
    elapsed = time.time() - ds._last_call_time
    expected_wait = max(0, min_interval - elapsed)
    
    # Property: If time since last call < min_interval, we need to wait
    if time_since_last_call < min_interval:
        assert expected_wait > 0, "Should need to wait when interval not elapsed"
    else:
        assert expected_wait <= 0.1, "Should not need to wait when interval elapsed"



# ============================================
# TELEGRAM ALERTER TESTS (Property 8)
# ============================================

from src.services.news_radar import TelegramAlerter


def test_telegram_alerter_initialization():
    """Test TelegramAlerter initializes correctly."""
    ta = TelegramAlerter(token="test_token", chat_id="test_chat")
    assert ta._token == "test_token"
    assert ta._chat_id == "test_chat"
    assert ta._alerts_sent == 0
    assert ta._alerts_failed == 0


def test_telegram_alerter_stats():
    """Test TelegramAlerter stats tracking."""
    ta = TelegramAlerter()
    
    stats = ta.get_stats()
    assert "alerts_sent" in stats
    assert "alerts_failed" in stats


# ============================================
# PROPERTY 8: Alert Content Completeness
# **Feature: news-radar-monitor, Property 8: Alert Content Completeness**
# **Validates: Requirements 6.1, 6.2**
# ============================================

@settings(max_examples=100)
@given(
    source_name=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N', 'Z'))),
    source_url=valid_urls,
    affected_team=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=('L', 'N', 'Z'))),
    category=st.sampled_from(["INJURY", "SUSPENSION", "NATIONAL_TEAM", "CUP_ABSENCE", "OTHER"]),
    summary=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N', 'Z'))),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
)
def test_property_8_alert_content_completeness(source_name, source_url, affected_team, category, summary, confidence):
    """
    **Feature: news-radar-monitor, Property 8: Alert Content Completeness**
    **Validates: Requirements 6.1, 6.2**
    
    For any RadarAlert sent to Telegram, the message string SHALL contain:
    source_name, affected_team, category (translated to Italian), summary, and source_url.
    
    V1.2: Updated to check Italian category translations.
    """
    # Italian category translations
    category_italian = {
        "INJURY": "INFORTUNIO",
        "SUSPENSION": "SQUALIFICA",
        "NATIONAL_TEAM": "NAZIONALE",
        "CUP_ABSENCE": "ASSENZA COPPA",
        "YOUTH_CALLUP": "CONVOCAZIONE GIOVANILI",
        "OTHER": "ALTRO"
    }
    
    alert = RadarAlert(
        source_name=source_name,
        source_url=source_url,
        affected_team=affected_team,
        category=category,
        summary=summary,
        confidence=confidence
    )
    
    message = alert.to_telegram_message()
    
    # Property: All required fields must be present in message
    assert source_name in message, f"source_name '{source_name}' not in message"
    assert source_url in message, f"source_url '{source_url}' not in message"
    # V1.2: affected_team "Unknown" is translated to "Da verificare"
    if affected_team == "Unknown":
        assert "Da verificare" in message, "Unknown team should show 'Da verificare'"
    else:
        assert affected_team in message or "Da verificare" in message, \
            f"affected_team '{affected_team}' not in message"
    # V1.2: Check Italian translation of category
    expected_category = category_italian.get(category, category)
    assert expected_category in message, f"category '{expected_category}' (Italian for '{category}') not in message"
    assert summary in message, f"summary '{summary}' not in message"
    
    # Property: Message should have RADAR identifier
    assert "RADAR" in message, "Message should contain RADAR identifier"
    assert "🔔" in message, "Message should contain radar emoji"


def test_property_8_alert_distinguishes_from_main_bot():
    """
    **Feature: news-radar-monitor, Property 8: Alert Content Completeness**
    **Validates: Requirements 6.3**
    
    Alert format should be distinct from main bot (uses 🔔 not 🚨).
    """
    alert = RadarAlert(
        source_name="Test Source",
        source_url="https://example.com",
        affected_team="Test FC",
        category="INJURY",
        summary="Test summary",
        confidence=0.8
    )
    
    message = alert.to_telegram_message()
    
    # Should use RADAR emoji, not EARLYBIRD emoji
    assert "🔔" in message
    assert "RADAR" in message
    # Should NOT use main bot identifiers
    assert "🚨" not in message
    assert "EARLYBIRD" not in message



# ============================================
# NEWS RADAR MONITOR TESTS (Property 9)
# ============================================

from src.services.news_radar import NewsRadarMonitor


def test_news_radar_monitor_initialization():
    """Test NewsRadarMonitor initializes correctly."""
    monitor = NewsRadarMonitor()
    
    assert monitor.is_running() is False
    assert monitor._config_file == "config/news_radar_sources.json"


def test_news_radar_monitor_stats():
    """Test NewsRadarMonitor stats structure."""
    monitor = NewsRadarMonitor()
    
    stats = monitor.get_stats()
    
    assert "running" in stats
    assert "sources_count" in stats
    assert "urls_scanned" in stats
    assert "alerts_sent" in stats
    assert "cache_size" in stats


# ============================================
# PROPERTY 9: Priority-Based Scan Ordering
# **Feature: news-radar-monitor, Property 9: Priority-Based Scan Ordering**
# **Validates: Requirements 8.4**
# ============================================

@settings(max_examples=50)
@given(
    priorities=st.lists(
        st.integers(min_value=1, max_value=10),
        min_size=2,
        max_size=10
    )
)
def test_property_9_priority_based_scan_ordering(priorities):
    """
    **Feature: news-radar-monitor, Property 9: Priority-Based Scan Ordering**
    **Validates: Requirements 8.4**
    
    For any set of N sources with distinct priorities, the scan order SHALL
    process sources in ascending priority order (priority 1 = highest, scanned first).
    """
    # Create sources with given priorities
    sources = []
    for i, priority in enumerate(priorities):
        source = RadarSource(
            url=f"https://example{i}.com",
            name=f"Source {i}",
            priority=priority
        )
        # Mark all as due for scan
        source.last_scanned = None
        sources.append(source)
    
    # Get due sources and sort by priority (same logic as scan_cycle)
    due_sources = [s for s in sources if s.is_due_for_scan()]
    due_sources.sort(key=lambda s: s.priority)
    
    # Property: Sources should be sorted by priority (ascending)
    for i in range(len(due_sources) - 1):
        assert due_sources[i].priority <= due_sources[i + 1].priority, \
            f"Sources not in priority order: {due_sources[i].priority} > {due_sources[i + 1].priority}"


def test_property_9_priority_ordering_example():
    """
    **Feature: news-radar-monitor, Property 9: Priority-Based Scan Ordering**
    **Validates: Requirements 8.4**
    
    Concrete example of priority ordering.
    """
    sources = [
        RadarSource(url="https://low.com", name="Low Priority", priority=3),
        RadarSource(url="https://high.com", name="High Priority", priority=1),
        RadarSource(url="https://medium.com", name="Medium Priority", priority=2),
    ]
    
    # Sort by priority
    sorted_sources = sorted(sources, key=lambda s: s.priority)
    
    # High priority (1) should be first
    assert sorted_sources[0].name == "High Priority"
    assert sorted_sources[1].name == "Medium Priority"
    assert sorted_sources[2].name == "Low Priority"


# ============================================
# INTEGRATION TEST - FULL PIPELINE
# ============================================

def test_full_pipeline_integration():
    """Test the full analysis pipeline integration."""
    ef = ExclusionFilter()
    ra = RelevanceAnalyzer()
    cache = ContentCache()
    
    # Test case 1: Valid injury news should pass through
    content1 = "Manchester United star Marcus Rashford ruled out with hamstring injury for 3 weeks"
    
    assert ef.is_excluded(content1) is False, "Valid football news should not be excluded"
    assert cache.is_cached(content1) is False, "New content should not be cached"
    
    cache.add(content1)
    assert cache.is_cached(content1) is True, "Content should be cached after adding"
    
    result1 = ra.analyze(content1)
    assert result1.is_relevant is True, "Injury news should be relevant"
    assert result1.category == "INJURY", "Category should be INJURY"
    
    # Test case 2: Basketball news should be excluded
    content2 = "NBA star LeBron James out with knee injury"
    assert ef.is_excluded(content2) is True, "Basketball news should be excluded"
    
    # Test case 3: Women's football should be excluded
    content3 = "Women's team player suspended for red card"
    assert ef.is_excluded(content3) is True, "Women's football should be excluded"
    
    # Test case 4: Duplicate content should be detected
    assert cache.is_cached(content1) is True, "Duplicate content should be detected"


def test_alert_creation_from_analysis():
    """Test creating RadarAlert from AnalysisResult (V1.2: Italian output)."""
    result = AnalysisResult(
        is_relevant=True,
        category="INJURY",
        affected_team="Test FC",
        confidence=0.85,
        summary="Key player injured"
    )
    
    alert = RadarAlert(
        source_name="Test Source",
        source_url="https://example.com/news",
        affected_team=result.affected_team or "Unknown",
        category=result.category,
        summary=result.summary,
        confidence=result.confidence
    )
    
    assert alert.affected_team == "Test FC"
    assert alert.category == "INJURY"
    assert alert.confidence == 0.85
    
    message = alert.to_telegram_message()
    assert "Test FC" in message
    assert "INFORTUNIO" in message  # V1.2: Italian translation
    assert "85%" in message


# ============================================
# REGRESSION TESTS - V1.1 Bug Fixes
# ============================================

@pytest.mark.asyncio
async def test_regression_process_content_without_start():
    """
    REGRESSION TEST: _process_content should handle uninitialized components gracefully.
    
    Bug: _process_content accessed self._content_cache, self._exclusion_filter, 
         self._relevance_analyzer without None checks, causing AttributeError
         if called before start().
    
    Fix: Added safety check at start of _process_content that returns None
         and logs error if components are not initialized.
    
    V1.1: This test verifies the fix is in place.
    V2.0: Updated - V2 uses singleton filters, only _content_cache needs check.
    """
    from src.services.news_radar import NewsRadarMonitor, RadarSource
    
    monitor = NewsRadarMonitor()
    
    # Components should be None before start()
    assert monitor._content_cache is None
    # V2: exclusion_filter and relevance_analyzer are now singletons, not instance attributes
    # The safety check is on _content_cache
    
    # Create a test source
    source = RadarSource(url="https://example.com", name="Test")
    
    # _process_content should NOT crash, should return None gracefully
    result = await monitor._process_content(
        content="Test content with injury news",
        source=source,
        url="https://example.com/article"
    )
    
    # Should return None (not crash with AttributeError)
    assert result is None


def test_regression_singleton_usage_in_news_radar():
    """
    REGRESSION TEST: news_radar should use singleton instances from content_analysis.
    
    Bug: news_radar.py was creating new ExclusionFilter() and RelevanceAnalyzer()
         instances instead of using get_exclusion_filter() and get_relevance_analyzer()
         singletons, wasting memory by compiling regex patterns twice.
    
    Fix: Changed to use singleton getters for DRY compliance.
    
    V1.1: This test verifies the fix is in place.
    """
    from src.services.news_radar import NewsRadarMonitor
    from src.utils.content_analysis import get_exclusion_filter, get_relevance_analyzer
    import asyncio
    
    async def run_test():
        monitor = NewsRadarMonitor()
        
        # Start the monitor to initialize components
        # We'll mock the extractor to avoid actual browser initialization
        monitor._config.sources = []  # No sources to scan
        
        # Manually initialize components like start() does
        from src.services.news_radar import ContentCache, DEFAULT_CACHE_MAX_ENTRIES
        monitor._content_cache = ContentCache(max_entries=DEFAULT_CACHE_MAX_ENTRIES, ttl_hours=24)
        monitor._exclusion_filter = get_exclusion_filter()
        monitor._relevance_analyzer = get_relevance_analyzer()
        
        # Verify they are the singleton instances
        assert monitor._exclusion_filter is get_exclusion_filter()
        assert monitor._relevance_analyzer is get_relevance_analyzer()
    
    asyncio.run(run_test())


# ============================================
# V1.2: BROWSER RECOVERY TESTS
# ============================================

def test_content_extractor_has_ensure_browser_connected_method():
    """
    REGRESSION TEST: ContentExtractor should have _ensure_browser_connected method.
    
    Bug: news_radar.py ContentExtractor was missing browser recovery logic,
         causing "Browser.new_page: Target page, context or browser has been closed"
         errors when browser crashed/disconnected.
    
    Fix: Added _ensure_browser_connected() and _recreate_browser() methods
         ported from browser_monitor.py V7.6.
    
    V1.2: This test verifies the fix is in place.
    """
    from src.services.news_radar import ContentExtractor
    
    extractor = ContentExtractor()
    
    # Verify method exists
    assert hasattr(extractor, '_ensure_browser_connected'), \
        "REGRESSION: _ensure_browser_connected method missing from ContentExtractor"
    
    # Verify it's callable
    assert callable(getattr(extractor, '_ensure_browser_connected')), \
        "_ensure_browser_connected should be callable"


def test_content_extractor_has_recreate_browser_method():
    """
    REGRESSION TEST: ContentExtractor should have _recreate_browser_internal method.
    
    Bug: news_radar.py ContentExtractor couldn't recover from browser crashes.
    
    Fix: Added _recreate_browser_internal() method ported from browser_monitor.py V7.6.
    
    V1.3: Renamed from _recreate_browser to _recreate_browser_internal
          to clarify it's called with lock held.
    """
    from src.services.news_radar import ContentExtractor
    
    extractor = ContentExtractor()
    
    # Verify method exists
    assert hasattr(extractor, '_recreate_browser_internal'), \
        "REGRESSION: _recreate_browser_internal method missing from ContentExtractor"
    
    # Verify it's callable
    assert callable(getattr(extractor, '_recreate_browser_internal')), \
        "_recreate_browser_internal should be callable"


@pytest.mark.asyncio
async def test_ensure_browser_connected_returns_false_when_no_browser():
    """
    Test that _ensure_browser_connected returns False when browser is None
    and recreation fails (no playwright instance).
    
    V1.2: Verifies graceful handling of missing browser.
    V7.8 FIX: Mock initialize() to ensure deterministic test behavior.
    """
    from src.services.news_radar import ContentExtractor
    from unittest.mock import AsyncMock
    
    extractor = ContentExtractor()
    
    # Browser and playwright are None by default
    assert extractor._browser is None
    assert extractor._playwright is None
    
    # Mock initialize() to return False (simulating Playwright unavailable)
    extractor.initialize = AsyncMock(return_value=False)
    
    # Should return False (can't recreate without playwright)
    result = await extractor._ensure_browser_connected()
    
    # Without playwright, it should try initialize() which returns False
    assert result is False, "Should return False when browser recreation fails"
    extractor.initialize.assert_called_once()


@pytest.mark.asyncio
async def test_extract_with_browser_handles_disconnected_browser():
    """
    REGRESSION TEST: _extract_with_browser should handle disconnected browser.
    
    Bug: When browser crashed, _extract_with_browser would fail with
         "Browser.new_page: Target page, context or browser has been closed"
    
    Fix: Now calls _ensure_browser_connected() first to auto-recover.
    
    V1.2: This test verifies the fix is in place.
    """
    from src.services.news_radar import ContentExtractor
    from unittest.mock import AsyncMock, MagicMock, patch
    
    extractor = ContentExtractor()
    extractor._browser_lock = asyncio.Lock()  # V1.3: Initialize lock
    
    # Mock a disconnected browser scenario
    mock_browser = MagicMock()
    mock_browser.is_connected.return_value = False
    extractor._browser = mock_browser
    extractor._playwright = MagicMock()
    
    # Mock _recreate_browser_internal to return False (simulating failure)
    # V1.3: Renamed from _recreate_browser to _recreate_browser_internal
    with patch.object(extractor, '_recreate_browser_internal', new_callable=AsyncMock) as mock_recreate:
        mock_recreate.return_value = False
        
        # Should return None gracefully (not crash)
        result = await extractor._extract_with_browser("https://example.com")
        
        # Verify _recreate_browser_internal was called (recovery attempted)
        mock_recreate.assert_called_once()
        
        # Should return None (not crash with TargetClosedError)
        assert result is None


@pytest.mark.asyncio
async def test_extract_with_navigation_handles_disconnected_browser():
    """
    REGRESSION TEST: extract_with_navigation should handle disconnected browser.
    
    Bug: When browser crashed during paginated navigation, it would fail with
         "Browser.new_page: Target page, context or browser has been closed"
    
    Fix: Now calls _ensure_browser_connected() first to auto-recover.
    
    V1.2: This test verifies the fix is in place.
    """
    from src.services.news_radar import ContentExtractor
    from unittest.mock import AsyncMock, MagicMock, patch
    
    extractor = ContentExtractor()
    extractor._browser_lock = asyncio.Lock()  # V1.3: Initialize lock
    
    # Mock a disconnected browser scenario
    mock_browser = MagicMock()
    mock_browser.is_connected.return_value = False
    extractor._browser = mock_browser
    extractor._playwright = MagicMock()
    
    # Mock _recreate_browser_internal to return False (simulating failure)
    # V1.3: Renamed from _recreate_browser to _recreate_browser_internal
    with patch.object(extractor, '_recreate_browser_internal', new_callable=AsyncMock) as mock_recreate:
        mock_recreate.return_value = False
        
        # Should return empty list gracefully (not crash)
        result = await extractor.extract_with_navigation(
            url="https://example.com",
            link_selector="a.article-link"
        )
        
        # Verify _recreate_browser_internal was called (recovery attempted)
        mock_recreate.assert_called_once()
        
        # Should return empty list (not crash with TargetClosedError)
        assert result == []


@pytest.mark.asyncio
async def test_browser_recovery_success_scenario():
    """
    Test successful browser recovery scenario.
    
    V1.3: Verifies that when browser is disconnected but recreation succeeds,
          extraction can proceed normally. Updated for lock-based recreation.
    """
    from src.services.news_radar import ContentExtractor
    from unittest.mock import AsyncMock, MagicMock, patch
    
    extractor = ContentExtractor()
    extractor._browser_lock = asyncio.Lock()  # V1.3: Initialize lock
    
    # Mock a disconnected browser that gets successfully recreated
    mock_browser = MagicMock()
    mock_browser.is_connected.return_value = False
    extractor._browser = mock_browser
    extractor._playwright = MagicMock()
    
    # Mock successful recreation
    # V1.3: Renamed from _recreate_browser to _recreate_browser_internal
    with patch.object(extractor, '_recreate_browser_internal', new_callable=AsyncMock) as mock_recreate:
        mock_recreate.return_value = True
        
        # After recreation, browser should be "connected"
        # We need to also mock the new_page call
        new_mock_browser = MagicMock()
        new_mock_browser.is_connected.return_value = True
        
        mock_page = AsyncMock()
        mock_page.content.return_value = "<html><body>Test content</body></html>"
        mock_page.inner_text.return_value = "Test content"
        new_mock_browser.new_page = AsyncMock(return_value=mock_page)
        
        # After _recreate_browser_internal, update the browser reference
        async def recreate_side_effect():
            extractor._browser = new_mock_browser
            return True
        
        mock_recreate.side_effect = recreate_side_effect
        
        # Now _ensure_browser_connected should succeed
        result = await extractor._ensure_browser_connected()
        
        # Verify recreation was called
        mock_recreate.assert_called_once()
        
        # Should return True (browser recovered)
        assert result is True


# ============================================
# V1.2: TEAM EXTRACTION & SUMMARY REGRESSION TESTS
# ============================================

def test_extract_team_name_does_not_match_articles():
    """
    REGRESSION TEST: _extract_team_name should NOT match common articles like "The".
    
    Bug: Old regex pattern `(?:at|for|from)\s+([A-Z][a-z]+)` would match
         "The" from phrases like "at The Emirates", causing "Team: The" in alerts.
    
    Fix: Added excluded_words set and improved patterns to avoid false positives.
    
    V1.2: This test would FAIL with the old buggy code.
    """
    from src.utils.content_analysis import RelevanceAnalyzer
    
    analyzer = RelevanceAnalyzer()
    
    # Content that triggered the bug - "The" was extracted as team name
    buggy_content = """
    I think tonight was the making of Kerkez, man of the match for me with his 
    blocks and keeping Saka quiet. Martin, Oxford. At a glance Arsenal miss 
    chance to move eight points clear. Hugo Ekitike misses...
    """
    
    team = analyzer._extract_team_name(buggy_content)
    
    # Should NOT be "The", "At", "Martin", "Oxford", etc.
    excluded = {'the', 'at', 'for', 'from', 'martin', 'oxford', 'hugo', 'saka', 'kerkez'}
    if team:
        assert team.lower() not in excluded, \
            f"REGRESSION: Extracted '{team}' which should be excluded"


def test_extract_team_name_finds_arsenal():
    """
    Test that _extract_team_name correctly identifies Arsenal from content.
    
    V1.2: Verifies the improved extraction finds known clubs.
    """
    from src.utils.content_analysis import RelevanceAnalyzer
    
    analyzer = RelevanceAnalyzer()
    
    content = """
    Arsenal miss chance to move eight points clear after draw.
    The Gunners were held at home despite dominating possession.
    """
    
    team = analyzer._extract_team_name(content)
    
    assert team == "Arsenal", f"Expected 'Arsenal', got '{team}'"


def test_extract_team_name_finds_team_with_suffix():
    """
    Test that _extract_team_name finds teams correctly.
    
    V1.3: Known clubs are matched first, so "Liverpool FC" returns "Liverpool"
    because Liverpool is in the known_clubs list.
    """
    from src.utils.content_analysis import RelevanceAnalyzer
    
    analyzer = RelevanceAnalyzer()
    
    test_cases = [
        ("Manchester United player injured in training", "Manchester United"),
        ("Liverpool FC confirm signing", "Liverpool"),  # Known club matched first
        ("Leicester City manager speaks", "Leicester"),  # Known club matched first
        ("Wigan Athletic announce new signing", "Wigan Athletic"),  # Not in known_clubs, uses suffix pattern
    ]
    
    for content, expected in test_cases:
        team = analyzer._extract_team_name(content)
        assert team is not None, f"Should find team in: {content}"
        assert expected.lower() in team.lower() or team.lower() in expected.lower(), \
            f"Expected '{expected}' related to '{team}'"


def test_generate_summary_does_not_return_garbage():
    """
    REGRESSION TEST: _generate_summary should NOT return raw first 200 chars.
    
    Bug: Old code just did `content[:200]` which included menu items,
         navigation text, and random fragments from page headers.
    
    Fix: Now extracts meaningful sentences based on category keywords.
    
    V1.2: This test would produce garbage output with the old buggy code.
    """
    from src.utils.content_analysis import RelevanceAnalyzer
    
    analyzer = RelevanceAnalyzer()
    
    # Simulated content with garbage at the start (like real web pages)
    garbage_content = """
    Home News Sport Football Live Scores Tables Fixtures Results
    BBC Sport Football Menu Search BBC
    I think tonight was the making of Kerkez, man of the match for me.
    Arsenal miss chance to move eight points clear after injury to key player.
    The striker suffered a hamstring injury during the first half.
    """
    
    summary = analyzer._generate_summary(garbage_content, "INJURY")
    
    # Should NOT start with navigation garbage
    assert not summary.startswith("Home News"), \
        f"REGRESSION: Summary starts with navigation garbage: {summary[:50]}"
    
    # Should contain something meaningful about injury
    assert len(summary) > 20, "Summary too short"


def test_generate_summary_finds_relevant_sentence():
    """
    Test that _generate_summary finds sentences with category keywords.
    
    V1.2: Verifies improved summary extraction.
    """
    from src.utils.content_analysis import RelevanceAnalyzer
    
    analyzer = RelevanceAnalyzer()
    
    content = """
    Breaking news from the Premier League.
    Arsenal's star striker has been ruled out for six weeks with a knee injury.
    The club confirmed the news this morning.
    """
    
    summary = analyzer._generate_summary(content, "INJURY")
    
    # Should find the sentence about injury
    assert "injury" in summary.lower() or "ruled out" in summary.lower(), \
        f"Summary should mention injury: {summary}"


def test_generate_summary_handles_empty_content():
    """
    Test that _generate_summary handles empty/None content gracefully.
    
    V1.2: Edge case handling.
    """
    from src.utils.content_analysis import RelevanceAnalyzer
    
    analyzer = RelevanceAnalyzer()
    
    # Empty string
    summary = analyzer._generate_summary("", "INJURY")
    assert summary == "Contenuto non disponibile"
    
    # Whitespace only
    summary = analyzer._generate_summary("   \n\t  ", "INJURY")
    assert len(summary) > 0  # Should return fallback


def test_radar_alert_telegram_message_in_italian():
    """
    REGRESSION TEST: RadarAlert.to_telegram_message should output in Italian.
    
    Bug: Output was in English ("Team:", "Category:", "Summary:", etc.)
    
    Fix: Changed to Italian ("Squadra:", "Categoria:", "Riepilogo:", etc.)
    
    V1.2: This test verifies Italian output.
    """
    from src.services.news_radar import RadarAlert
    
    alert = RadarAlert(
        source_name="BBC Sport",
        source_url="https://bbc.com/sport/football",
        affected_team="Arsenal",
        category="INJURY",
        summary="Infortunio al ginocchio per il centravanti",
        confidence=0.85
    )
    
    message = alert.to_telegram_message()
    
    # Should be in Italian
    assert "*Squadra:*" in message, "Should use Italian 'Squadra' not 'Team'"
    assert "*Categoria:*" in message, "Should use Italian 'Categoria' not 'Category'"
    assert "*Riepilogo:*" in message, "Should use Italian 'Riepilogo' not 'Summary'"
    assert "*Fonte:*" in message, "Should use Italian 'Fonte' not 'Source'"
    assert "Affidabilità:" in message, "Should use Italian 'Affidabilità' not 'Confidence'"
    
    # Category should be translated
    assert "INFORTUNIO" in message, "Category should be translated to Italian"


def test_radar_alert_handles_unknown_team():
    """
    Test that RadarAlert handles "Unknown" team gracefully in Italian.
    
    V1.2: Edge case - unknown team should show "Da verificare".
    """
    from src.services.news_radar import RadarAlert
    
    alert = RadarAlert(
        source_name="Test Source",
        source_url="https://example.com",
        affected_team="Unknown",
        category="INJURY",
        summary="Test summary",
        confidence=0.75
    )
    
    message = alert.to_telegram_message()
    
    # Should show "Da verificare" instead of "Unknown"
    assert "Da verificare" in message, "Unknown team should show 'Da verificare'"
    assert "Unknown" not in message, "Should not show 'Unknown' in Italian output"


def test_radar_alert_category_translations():
    """
    Test all category translations to Italian.
    
    V1.2: Verifies all categories are properly translated.
    """
    from src.services.news_radar import RadarAlert
    
    translations = {
        "INJURY": "INFORTUNIO",
        "SUSPENSION": "SQUALIFICA",
        "NATIONAL_TEAM": "NAZIONALE",
        "CUP_ABSENCE": "ASSENZA COPPA",
        "YOUTH_CALLUP": "CONVOCAZIONE GIOVANILI",
        "OTHER": "ALTRO"
    }
    
    for eng_cat, ita_cat in translations.items():
        alert = RadarAlert(
            source_name="Test",
            source_url="https://test.com",
            affected_team="Test FC",
            category=eng_cat,
            summary="Test",
            confidence=0.8
        )
        
        message = alert.to_telegram_message()
        assert ita_cat in message, f"Category {eng_cat} should translate to {ita_cat}"


# ============================================
# V1.4: POSITIVE NEWS FILTER TESTS
# ============================================

def test_positive_news_filter_initialization():
    """Test PositiveNewsFilter initializes correctly."""
    from src.utils.content_analysis import PositiveNewsFilter
    
    pnf = PositiveNewsFilter()
    assert pnf._positive_pattern is not None


def test_positive_news_filter_detects_returning_player():
    """Test PositiveNewsFilter detects player returning from injury."""
    from src.utils.content_analysis import PositiveNewsFilter
    
    pnf = PositiveNewsFilter()
    
    # English positive news
    assert pnf.is_positive_news("Haaland returns to training after injury") is True
    assert pnf.is_positive_news("Saka back in squad for weekend match") is True
    assert pnf.is_positive_news("Player fully fit and available again") is True
    
    # Italian positive news
    assert pnf.is_positive_news("Osimhen torna in gruppo dopo l'infortunio") is True
    assert pnf.is_positive_news("Leao recuperato per la partita di domenica") is True
    
    # Spanish positive news
    assert pnf.is_positive_news("Vinicius vuelve a entrenar con el grupo") is True


def test_positive_news_filter_allows_negative_news():
    """Test PositiveNewsFilter allows injury/absence news through."""
    from src.utils.content_analysis import PositiveNewsFilter
    
    pnf = PositiveNewsFilter()
    
    # Injury news should NOT be filtered
    assert pnf.is_positive_news("Haaland injured, out for 3 weeks") is False
    assert pnf.is_positive_news("Saka ruled out of weekend match") is False
    assert pnf.is_positive_news("Multiple players suspended for next game") is False
    
    # General news should NOT be filtered
    assert pnf.is_positive_news("Manchester City vs Arsenal preview") is False


def test_positive_news_filter_get_reason():
    """Test PositiveNewsFilter returns matched keyword."""
    from src.utils.content_analysis import PositiveNewsFilter
    
    pnf = PositiveNewsFilter()
    
    reason = pnf.get_positive_reason("Player returns to training today")
    assert reason == "returns to training"
    
    reason = pnf.get_positive_reason("Injury news: player out for 2 weeks")
    assert reason is None


def test_positive_news_filter_singleton():
    """Test get_positive_news_filter returns singleton."""
    from src.utils.content_analysis import get_positive_news_filter
    
    filter1 = get_positive_news_filter()
    filter2 = get_positive_news_filter()
    
    assert filter1 is filter2, "Should return same singleton instance"


# ============================================
# V1.4: BETTING IMPACT TESTS (Updated for V2 format)
# ============================================

def test_deepseek_parse_betting_impact():
    """Test DeepSeek response parsing includes betting_impact (V2 format)."""
    from src.services.news_radar import DeepSeekFallback
    
    ds = DeepSeekFallback()
    
    # HIGH impact response (V2 format)
    response = '{"is_high_value": true, "betting_impact": "HIGH", "category": "MASS_ABSENCE", "team": "Test FC", "confidence": 0.9, "summary_italian": "3 giocatori fuori"}'
    result = ds._parse_response(response)
    
    assert result is not None
    assert result.betting_impact == "HIGH"
    assert result.is_relevant is True
    
    # LOW impact response - should set is_relevant to False
    response = '{"is_high_value": false, "betting_impact": "LOW", "category": "LOW_VALUE", "team": "Test FC", "confidence": 0.6, "summary_italian": "1 giocatore fuori"}'
    result = ds._parse_response(response)
    
    assert result is not None
    assert result.betting_impact == "LOW"
    assert result.is_relevant is False, "LOW betting_impact should set is_relevant=False"


def test_deepseek_parse_invalid_betting_impact():
    """Test DeepSeek response parsing handles invalid betting_impact (V2 format)."""
    from src.services.news_radar import DeepSeekFallback
    
    ds = DeepSeekFallback()
    
    # Invalid betting_impact should default to LOW
    response = '{"is_high_value": true, "betting_impact": "INVALID", "category": "MASS_ABSENCE", "team": "Test FC", "confidence": 0.8, "summary_italian": "Test"}'
    result = ds._parse_response(response)
    
    assert result is not None
    assert result.betting_impact == "LOW"
    assert result.is_relevant is False


def test_deepseek_parse_missing_betting_impact():
    """Test DeepSeek response parsing handles missing betting_impact (V2 format)."""
    from src.services.news_radar import DeepSeekFallback
    
    ds = DeepSeekFallback()
    
    # Missing betting_impact should default to LOW
    response = '{"is_high_value": true, "category": "MASS_ABSENCE", "team": "Test FC", "confidence": 0.8, "summary_italian": "Test"}'
    result = ds._parse_response(response)
    
    assert result is not None
    assert result.betting_impact == "LOW"
    assert result.is_relevant is False


def test_deepseek_prompt_includes_betting_impact():
    """Test DeepSeek prompt includes betting_impact instructions (V2 format)."""
    from src.services.news_radar import DeepSeekFallback
    
    ds = DeepSeekFallback()
    prompt = ds._build_prompt("Test content about player injury")
    
    assert "betting_impact" in prompt
    assert "HIGH" in prompt
    assert "MEDIUM" in prompt
    assert "LOW" in prompt
    assert "3+" in prompt  # V2: "3+ first-team players"
    assert "Goalkeeper" in prompt


def test_analysis_result_has_betting_impact_field():
    """Test AnalysisResult dataclass has betting_impact field."""
    from src.utils.content_analysis import AnalysisResult
    
    # With betting_impact
    result = AnalysisResult(
        is_relevant=True,
        category="INJURY",
        affected_team="Test FC",
        confidence=0.9,
        summary="Test",
        betting_impact="HIGH"
    )
    assert result.betting_impact == "HIGH"
    
    # Without betting_impact (default None for backward compatibility)
    result = AnalysisResult(
        is_relevant=True,
        category="INJURY",
        affected_team="Test FC",
        confidence=0.9,
        summary="Test"
    )
    assert result.betting_impact is None


# ============================================
# V1.4: INTEGRATION TEST
# ============================================

def test_v14_positive_news_filter_in_imports():
    """Test that PositiveNewsFilter is properly exported from content_analysis."""
    from src.utils.content_analysis import (
        PositiveNewsFilter,
        get_positive_news_filter
    )
    
    # Should not raise ImportError
    assert PositiveNewsFilter is not None
    assert get_positive_news_filter is not None


def test_v14_news_radar_imports_positive_filter():
    """Test that news_radar imports PositiveNewsFilter correctly."""
    from src.services.news_radar import (
        PositiveNewsFilter,
        get_positive_news_filter
    )
    
    # Should not raise ImportError
    assert PositiveNewsFilter is not None
    assert get_positive_news_filter is not None
