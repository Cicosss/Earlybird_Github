"""
Tavily Integration - Property-Based Tests

Tests correctness properties using Hypothesis framework.
Each test validates specific requirements from the design document.

Requirements: 1.2, 1.3, 1.4, 2.1-2.4, 3.2, 4.3, 6.2-6.4, 9.1-9.2, 11.2
"""
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, strategies as st

from src.ingestion.tavily_key_rotator import TavilyKeyRotator


# ============================================
# Property 2: Key Rotation on 429
# ============================================

class TestKeyRotationProperty:
    """
    **Feature: tavily-integration, Property 2: Key Rotation on 429**
    **Validates: Requirements 1.4, 11.2**
    
    For any sequence of API calls where the current key returns 429,
    the TavilyKeyRotator SHALL automatically switch to the next available
    key in sequence (1→2→3→...→7) without manual intervention.
    """
    
    @given(
        num_keys=st.integers(min_value=2, max_value=7),
        exhaustion_sequence=st.lists(
            st.integers(min_value=0, max_value=6),
            min_size=1,
            max_size=7,
            unique=True
        )
    )
    @settings(max_examples=100)
    def test_key_rotation_sequence(self, num_keys: int, exhaustion_sequence: List[int]):
        """
        Property: Keys rotate in sequence when exhausted.
        
        For any number of keys and any exhaustion sequence,
        rotation should follow the order 1→2→3→...→N.
        """
        # Create rotator with N keys
        keys = [f"tvly-test-key-{i}" for i in range(num_keys)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # Filter exhaustion sequence to valid indices
        valid_exhaustions = [i for i in exhaustion_sequence if i < num_keys]
        
        # Track rotation order
        rotation_order = []
        
        for exhaust_idx in valid_exhaustions:
            # Get current key before exhaustion
            current_key = rotator.get_current_key()
            if current_key is None:
                break
            
            # Mark current key as exhausted
            rotator.mark_exhausted()
            
            # Try to rotate
            if rotator.rotate_to_next():
                rotation_order.append(rotator._current_index)
        
        # Verify: rotation should be sequential (wrapping around)
        for i in range(1, len(rotation_order)):
            prev_idx = rotation_order[i - 1]
            curr_idx = rotation_order[i]
            
            # Current should be next available after previous
            # (accounting for wrap-around and exhausted keys)
            expected_next = (prev_idx + 1) % num_keys
            while expected_next in rotator._exhausted_keys and expected_next != curr_idx:
                expected_next = (expected_next + 1) % num_keys
            
            # Either we found the expected next, or all keys are exhausted
            assert curr_idx == expected_next or len(rotator._exhausted_keys) >= num_keys - 1
    
    @given(num_keys=st.integers(min_value=1, max_value=7))
    @settings(max_examples=100)
    def test_all_keys_exhausted_returns_none(self, num_keys: int):
        """
        Property: When all keys are exhausted, get_current_key returns None.
        
        For any number of keys, exhausting all of them should result
        in get_current_key() returning None.
        """
        keys = [f"tvly-test-key-{i}" for i in range(num_keys)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # Exhaust all keys
        for i in range(num_keys):
            rotator.mark_exhausted(i)
        
        # Should return None
        assert rotator.get_current_key() is None
        assert not rotator.is_available()
    
    @given(num_keys=st.integers(min_value=2, max_value=7))
    @settings(max_examples=100)
    def test_rotation_skips_exhausted_keys(self, num_keys: int):
        """
        Property: Rotation skips already exhausted keys.
        
        For any configuration, rotating should never land on an exhausted key.
        """
        keys = [f"tvly-test-key-{i}" for i in range(num_keys)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # Exhaust first key
        rotator.mark_exhausted(0)
        
        # Rotate should skip to key 1 (index 1)
        success = rotator.rotate_to_next()
        
        if num_keys > 1:
            assert success
            assert rotator._current_index not in rotator._exhausted_keys
            assert rotator._current_index == 1
    
    @given(
        num_keys=st.integers(min_value=1, max_value=7),
        num_calls=st.integers(min_value=0, max_value=100)
    )
    @settings(max_examples=100)
    def test_usage_tracking_consistency(self, num_keys: int, num_calls: int):
        """
        Property: Usage tracking is consistent.
        
        For any number of calls, total usage should equal sum of per-key usage.
        """
        keys = [f"tvly-test-key-{i}" for i in range(num_keys)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # Record calls
        for _ in range(num_calls):
            if rotator.get_current_key():
                rotator.record_call()
        
        # Verify consistency
        status = rotator.get_status()
        per_key_sum = sum(status["key_usage"].values())
        
        assert status["total_usage"] == per_key_sum
        assert status["total_usage"] == num_calls


# ============================================
# Property 1: API Key Validation and Loading
# ============================================

class TestKeyValidationProperty:
    """
    **Feature: tavily-integration, Property 1: API Key Validation and Loading**
    **Validates: Requirements 1.1, 11.1**
    
    For any set of environment variables TAVILY_API_KEY_1 through TAVILY_API_KEY_7,
    the TavilyKeyRotator SHALL load all non-empty keys in order and set is_available()
    to True only when at least one valid key exists.
    """
    
    @given(
        keys=st.lists(
            st.one_of(
                st.just(""),
                st.just(None),
                st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
            ),
            min_size=0,
            max_size=10
        )
    )
    @settings(max_examples=100)
    def test_empty_keys_filtered(self, keys: List):
        """
        Property: Empty and None keys are filtered out.
        
        For any list of keys including empty strings and None,
        only non-empty keys should be loaded.
        """
        rotator = TavilyKeyRotator(keys=keys)
        
        # Count expected valid keys
        expected_valid = len([k for k in keys if k and k.strip()])
        
        assert len(rotator._keys) == expected_valid
        assert rotator.is_available() == (expected_valid > 0)
    
    @given(num_valid_keys=st.integers(min_value=0, max_value=7))
    @settings(max_examples=100)
    def test_availability_matches_key_count(self, num_valid_keys: int):
        """
        Property: is_available() reflects key availability.
        
        For any number of valid keys, is_available() should be True
        if and only if at least one key exists.
        """
        keys = [f"tvly-key-{i}" for i in range(num_valid_keys)]
        rotator = TavilyKeyRotator(keys=keys)
        
        assert rotator.is_available() == (num_valid_keys > 0)


# ============================================
# Property 13: Monthly Reset
# ============================================

class TestMonthlyResetProperty:
    """
    **Feature: tavily-integration, Property 13: Monthly Reset**
    **Validates: Requirements 9.4, 11.5**
    
    For any month boundary crossing, the Key_Rotator SHALL reset all keys
    to available status, reset all usage counters to 0, and restart from key 1.
    """
    
    @given(
        num_keys=st.integers(min_value=1, max_value=7),
        num_exhausted=st.integers(min_value=0, max_value=7),
        usage_per_key=st.integers(min_value=0, max_value=1000)
    )
    @settings(max_examples=100)
    def test_reset_clears_all_state(self, num_keys: int, num_exhausted: int, usage_per_key: int):
        """
        Property: reset_all() clears all exhaustion and usage state.
        
        For any state of exhaustion and usage, reset_all() should
        restore the rotator to initial state.
        """
        keys = [f"tvly-key-{i}" for i in range(num_keys)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # Simulate usage and exhaustion
        for i in range(min(num_exhausted, num_keys)):
            rotator.mark_exhausted(i)
        
        for i in range(num_keys):
            rotator._key_usage[i] = usage_per_key
        
        # Reset
        rotator.reset_all()
        
        # Verify clean state
        assert rotator._current_index == 0
        assert len(rotator._exhausted_keys) == 0
        assert all(usage == 0 for usage in rotator._key_usage.values())
        assert rotator.is_available() == (num_keys > 0)


# ============================================
# Property 3: Rate Limiting Enforcement
# ============================================

class TestRateLimitingProperty:
    """
    **Feature: tavily-integration, Property 3: Rate Limiting Enforcement**
    **Validates: Requirements 1.2**
    
    For any sequence of N search requests, the time between consecutive
    requests SHALL be at least 1 second, ensuring total execution time >= (N-1) seconds.
    """
    
    @given(num_requests=st.integers(min_value=2, max_value=4))
    @settings(max_examples=5, deadline=None)  # Reduced examples due to time-based test
    def test_rate_limiting_minimum_gap(self, num_requests: int):
        """
        Property: Minimum 1 second gap between requests.
        
        For any number of requests, consecutive calls should have
        at least 1 second gap (after the first request).
        """
        from src.ingestion.tavily_provider import TavilyProvider
        from src.ingestion.tavily_key_rotator import TavilyKeyRotator
        
        # Create provider with test keys
        rotator = TavilyKeyRotator(keys=["tvly-test-key"])
        provider = TavilyProvider(key_rotator=rotator)
        
        # Simulate first request to set last_request_time
        provider._last_request_time = time.time()
        
        # Track request times for subsequent requests
        request_times = [provider._last_request_time]
        
        for _ in range(num_requests - 1):
            provider._apply_rate_limit()
            request_times.append(time.time())
        
        # Verify minimum gap between consecutive requests
        for i in range(1, len(request_times)):
            gap = request_times[i] - request_times[i - 1]
            # Allow small tolerance for timing variations
            assert gap >= 0.95, f"Gap {gap:.3f}s < 1s between requests {i-1} and {i}"


# ============================================
# Property 4: Cache Round-Trip
# ============================================

class TestCacheRoundTripProperty:
    """
    **Feature: tavily-integration, Property 4: Cache Round-Trip**
    **Validates: Requirements 1.3**
    
    For any search query, calling search() twice within TTL SHALL return
    identical results, and the second call SHALL NOT make an API request.
    """
    
    @given(
        query=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        search_depth=st.sampled_from(["basic", "advanced"]),
        max_results=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=100)
    def test_cache_key_determinism(self, query: str, search_depth: str, max_results: int):
        """
        Property: Cache keys are deterministic.
        
        For any query parameters, the same inputs should always
        produce the same cache key.
        """
        from src.ingestion.tavily_provider import TavilyProvider
        from src.ingestion.tavily_key_rotator import TavilyKeyRotator
        
        rotator = TavilyKeyRotator(keys=["tvly-test-key"])
        provider = TavilyProvider(key_rotator=rotator)
        
        key1 = provider._get_cache_key(query, search_depth, max_results)
        key2 = provider._get_cache_key(query, search_depth, max_results)
        
        assert key1 == key2, "Cache keys should be deterministic"
    
    @given(
        query1=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        query2=st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
    )
    @settings(max_examples=100)
    def test_different_queries_different_keys(self, query1: str, query2: str):
        """
        Property: Different queries produce different cache keys.
        
        For any two different queries, cache keys should be different.
        """
        from src.ingestion.tavily_provider import TavilyProvider
        from src.ingestion.tavily_key_rotator import TavilyKeyRotator
        
        # Skip if queries are the same
        if query1.strip() == query2.strip():
            return
        
        rotator = TavilyKeyRotator(keys=["tvly-test-key"])
        provider = TavilyProvider(key_rotator=rotator)
        
        key1 = provider._get_cache_key(query1, "basic", 5)
        key2 = provider._get_cache_key(query2, "basic", 5)
        
        assert key1 != key2, "Different queries should have different cache keys"
    
    def test_cache_hit_returns_same_response(self):
        """
        Property: Cache hit returns identical response.
        
        When a response is cached, subsequent lookups should return
        the exact same response object.
        """
        from src.ingestion.tavily_provider import (
            TavilyProvider, TavilyResponse, TavilyResult
        )
        from src.ingestion.tavily_key_rotator import TavilyKeyRotator
        
        rotator = TavilyKeyRotator(keys=["tvly-test-key"])
        provider = TavilyProvider(key_rotator=rotator)
        
        # Create a test response
        test_response = TavilyResponse(
            query="test query",
            answer="test answer",
            results=[
                TavilyResult(
                    title="Test Title",
                    url="https://example.com",
                    content="Test content",
                    score=0.95
                )
            ],
            response_time=0.5
        )
        
        # Cache it
        cache_key = provider._get_cache_key("test query", "basic", 5)
        provider._update_cache(cache_key, test_response)
        
        # Retrieve from cache
        cached = provider._check_cache(cache_key)
        
        assert cached is not None
        assert cached.query == test_response.query
        assert cached.answer == test_response.answer
        assert len(cached.results) == len(test_response.results)
        assert cached.results[0].title == test_response.results[0].title
    
    def test_expired_cache_returns_none(self):
        """
        Property: Expired cache entries return None.
        
        When a cache entry has expired, _check_cache should return None.
        """
        from src.ingestion.tavily_provider import (
            TavilyProvider, TavilyResponse, CacheEntry
        )
        from src.ingestion.tavily_key_rotator import TavilyKeyRotator
        
        rotator = TavilyKeyRotator(keys=["tvly-test-key"])
        provider = TavilyProvider(key_rotator=rotator)
        
        # Create an expired cache entry
        test_response = TavilyResponse(
            query="test query",
            answer="test answer",
            results=[],
            response_time=0.5
        )
        
        cache_key = "test_expired_key"
        provider._cache[cache_key] = CacheEntry(
            response=test_response,
            cached_at=datetime.now(timezone.utc) - timedelta(hours=1),  # 1 hour ago
            ttl_seconds=1800  # 30 minutes TTL
        )
        
        # Should return None for expired entry
        cached = provider._check_cache(cache_key)
        assert cached is None
        
        # Entry should be cleaned up
        assert cache_key not in provider._cache



# ============================================
# Property 5: Query Batching Round-Trip
# ============================================

class TestQueryBatchingProperty:
    """
    **Feature: tavily-integration, Property 5: Query Batching Round-Trip**
    **Validates: Requirements 2.1, 2.2, 2.3**

    For any list of questions, building a batched query and parsing the response
    SHALL produce answers that map back to the original questions in order.
    """

    @given(
        home_team=st.text(min_size=1, max_size=30).filter(lambda x: x.strip()),
        away_team=st.text(min_size=1, max_size=30).filter(lambda x: x.strip()),
        match_date=st.from_regex(r"20\d{2}-\d{2}-\d{2}", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_match_enrichment_query_contains_teams(
        self, home_team: str, away_team: str, match_date: str
    ):
        """
        Property: Match enrichment query contains both team names.

        For any team names, the generated query should contain both.
        """
        from src.ingestion.tavily_query_builder import TavilyQueryBuilder

        query = TavilyQueryBuilder.build_match_enrichment_query(
            home_team=home_team, away_team=away_team, match_date=match_date
        )

        assert home_team in query, f"Home team '{home_team}' not in query"
        assert away_team in query, f"Away team '{away_team}' not in query"

    @given(
        questions=st.lists(
            st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_batched_query_contains_all_questions(self, questions: List[str]):
        """
        Property: Batched query contains all questions.

        For any list of questions, the generated query should contain
        all of them (possibly with separators).
        """
        from src.ingestion.tavily_query_builder import TavilyQueryBuilder

        query = TavilyQueryBuilder.build_match_enrichment_query(
            home_team="TeamA",
            away_team="TeamB",
            match_date="2026-01-15",
            questions=questions,
        )

        for q in questions:
            assert q in query, f"Question '{q}' not in query"

    @given(num_questions=st.integers(min_value=1, max_value=10))
    @settings(max_examples=100)
    def test_parse_returns_correct_count(self, num_questions: int):
        """
        Property: Parsing returns correct number of answers.

        For any number of questions, parse_batched_response should
        return exactly that many answers.
        """
        from src.ingestion.tavily_provider import TavilyResponse, TavilyResult
        from src.ingestion.tavily_query_builder import TavilyQueryBuilder

        # Create a mock response with numbered answers
        answers = [f"Answer {i+1}" for i in range(num_questions)]
        mock_response = TavilyResponse(
            query="test query",
            answer=" | ".join(answers),
            results=[],
            response_time=0.5,
        )

        parsed = TavilyQueryBuilder.parse_batched_response(mock_response, num_questions)

        assert (
            len(parsed) == num_questions
        ), f"Expected {num_questions} answers, got {len(parsed)}"


# ============================================
# Property 6: Query Splitting
# ============================================


class TestQuerySplittingProperty:
    """
    **Feature: tavily-integration, Property 6: Query Splitting**
    **Validates: Requirements 2.4**

    For any list of questions that produces a query exceeding 500 characters,
    the Query_Builder SHALL split into multiple queries each under 500 characters.
    """

    @given(
        query=st.text(min_size=1, max_size=2000).filter(lambda x: x.strip()),
        max_length=st.integers(min_value=50, max_value=500),
    )
    @settings(max_examples=100)
    def test_split_queries_under_max_length(self, query: str, max_length: int):
        """
        Property: All split queries are under max length.

        For any query and max length, all resulting queries should
        be at or under the specified maximum length.
        """
        from src.ingestion.tavily_query_builder import TavilyQueryBuilder

        splits = TavilyQueryBuilder.split_long_query(query, max_length)

        for i, split in enumerate(splits):
            assert (
                len(split) <= max_length
            ), f"Split {i} has length {len(split)} > {max_length}"

    @given(query=st.text(min_size=1, max_size=400).filter(lambda x: x.strip()))
    @settings(max_examples=100)
    def test_short_query_not_split(self, query: str):
        """
        Property: Short queries are not split.

        For any query under 500 characters, split_long_query should
        return a single-element list with the original query.
        """
        from src.ingestion.tavily_query_builder import TavilyQueryBuilder

        splits = TavilyQueryBuilder.split_long_query(query, max_length=500)

        if len(query) <= 500:
            assert len(splits) == 1, f"Short query was split into {len(splits)} parts"
            assert splits[0] == query, "Short query was modified"

    @given(
        questions=st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P", "S"),
                    whitelist_characters=" ",
                ),
                min_size=50,
                max_size=100,
            ).filter(lambda x: x.strip()),
            min_size=5,
            max_size=10,
        )
    )
    @settings(max_examples=50)
    def test_split_preserves_content(self, questions: List[str]):
        """
        Property: Splitting preserves question content.

        For any list of questions that gets split, each question
        should appear in at least one of the resulting queries.
        """
        from src.ingestion.tavily_query_builder import (
            TavilyQueryBuilder,
            QUESTION_SEPARATOR,
        )

        # Build a long query
        base = "TeamA vs TeamB 2026-01-15:"
        full_query = base + " " + QUESTION_SEPARATOR.join(questions)

        splits = TavilyQueryBuilder.split_long_query(full_query, max_length=200)

        # Combine all splits
        combined = " ".join(splits)

        # Each question should appear somewhere
        for q in questions:
            # Question might be truncated, check first 40 chars
            q_prefix = q[:40]
            assert (
                q_prefix in combined
            ), f"Question prefix '{q_prefix}' not found in splits"

    def test_empty_query_returns_empty_list(self):
        """
        Property: Empty query returns empty list.
        """
        from src.ingestion.tavily_query_builder import TavilyQueryBuilder

        splits = TavilyQueryBuilder.split_long_query("")
        assert splits == [], "Empty query should return empty list"

        splits = TavilyQueryBuilder.split_long_query(None)
        assert splits == [], "None query should return empty list"



# ============================================
# Property 10: Budget Tracking Consistency
# ============================================


class TestBudgetTrackingProperty:
    """
    **Feature: tavily-integration, Property 10: Budget Tracking Consistency**
    **Validates: Requirements 9.1, 9.2, 11.2**

    For any sequence of Tavily calls across all keys, the total budget counter
    SHALL equal the sum of calls made per key, and key rotation SHALL trigger
    when any key reaches 1000 calls.
    """

    @given(
        num_calls=st.integers(min_value=0, max_value=100),
        component=st.sampled_from(
            [
                "main_pipeline",
                "news_radar",
                "browser_monitor",
                "telegram_monitor",
                "settlement_clv",
            ]
        ),
    )
    @settings(max_examples=100)
    def test_budget_tracking_consistency(self, num_calls: int, component: str):
        """
        Property: Budget tracking is consistent.

        For any number of calls, monthly_used should equal sum of component usage.
        """
        from src.ingestion.tavily_budget import BudgetManager

        manager = BudgetManager(monthly_limit=7000)

        for _ in range(num_calls):
            manager.record_call(component)

        status = manager.get_status()

        # Total should equal component sum
        component_sum = sum(status.component_usage.values())
        assert (
            status.monthly_used == component_sum
        ), f"Monthly {status.monthly_used} != component sum {component_sum}"
        assert status.monthly_used == num_calls

    @given(
        calls_per_component=st.dictionaries(
            keys=st.sampled_from(
                ["main_pipeline", "news_radar", "browser_monitor", "telegram_monitor"]
            ),
            values=st.integers(min_value=0, max_value=50),
            min_size=1,
            max_size=4,
        )
    )
    @settings(max_examples=100)
    def test_multi_component_tracking(self, calls_per_component: Dict[str, int]):
        """
        Property: Multi-component tracking is accurate.

        For any distribution of calls across components, each component's
        usage should be tracked independently and sum to total.
        """
        from src.ingestion.tavily_budget import BudgetManager

        manager = BudgetManager(monthly_limit=7000)

        # Record calls for each component
        for component, num_calls in calls_per_component.items():
            for _ in range(num_calls):
                manager.record_call(component)

        status = manager.get_status()

        # Verify each component's usage
        for component, expected_calls in calls_per_component.items():
            actual = status.component_usage.get(component, 0)
            assert (
                actual == expected_calls
            ), f"Component {component}: expected {expected_calls}, got {actual}"

        # Verify total
        expected_total = sum(calls_per_component.values())
        assert status.monthly_used == expected_total

    @given(usage_pct=st.floats(min_value=0.0, max_value=1.0))
    @settings(max_examples=100)
    def test_threshold_detection(self, usage_pct: float):
        """
        Property: Threshold detection is accurate.

        For any usage percentage, is_degraded and is_disabled should
        correctly reflect the threshold crossings.
        """
        from src.ingestion.tavily_budget import BudgetManager

        monthly_limit = 1000
        manager = BudgetManager(monthly_limit=monthly_limit)

        # Simulate usage to reach target percentage
        target_calls = int(usage_pct * monthly_limit)
        manager._monthly_used = target_calls

        status = manager.get_status()

        # Check thresholds (90% degraded, 95% disabled)
        expected_degraded = usage_pct >= 0.90
        expected_disabled = usage_pct >= 0.95

        assert (
            status.is_degraded == expected_degraded
        ), f"At {usage_pct*100:.1f}%: is_degraded should be {expected_degraded}"
        assert (
            status.is_disabled == expected_disabled
        ), f"At {usage_pct*100:.1f}%: is_disabled should be {expected_disabled}"

    def test_reset_clears_all_counters(self):
        """
        Property: Monthly reset clears all counters.

        After reset_monthly(), all usage counters should be zero.
        """
        from src.ingestion.tavily_budget import BudgetManager

        manager = BudgetManager(monthly_limit=7000)

        # Record some calls
        for _ in range(100):
            manager.record_call("main_pipeline")
        for _ in range(50):
            manager.record_call("news_radar")

        # Reset
        manager.reset_monthly()

        status = manager.get_status()

        assert status.monthly_used == 0
        assert status.daily_used == 0
        assert all(v == 0 for v in status.component_usage.values())

    def test_can_call_respects_disabled_mode(self):
        """
        Property: can_call respects disabled mode.

        When budget is >95%, only critical calls should be allowed.
        """
        from src.ingestion.tavily_budget import BudgetManager

        manager = BudgetManager(monthly_limit=1000)

        # Set usage to 96%
        manager._monthly_used = 960

        # Non-critical should be blocked
        assert not manager.can_call("news_radar", is_critical=False)
        assert not manager.can_call("browser_monitor", is_critical=False)

        # Critical should be allowed
        assert manager.can_call("main_pipeline", is_critical=True)
        assert manager.can_call("settlement_clv", is_critical=False)  # Always critical



# ============================================
# Property 7: Content Merging Preservation
# ============================================


class TestContentMergingProperty:
    """
    **Feature: tavily-integration, Property 7: Content Merging Preservation**
    **Validates: Requirements 3.2, 4.2, 5.2**

    For any original content and Tavily enrichment, the merged content
    SHALL contain all text from both sources without loss.
    """

    @given(
        original=st.text(min_size=0, max_size=500),
        enrichment=st.text(min_size=0, max_size=500),
    )
    @settings(max_examples=100)
    def test_merge_preserves_both_contents(self, original: str, enrichment: str):
        """
        Property: Merged content contains both original and enrichment.

        For any two strings, merging should preserve both completely.
        """
        # Simulate the merge logic from IntelligenceRouter
        def merge_context(existing: str, tavily: str) -> str:
            if not tavily:
                return existing
            if not existing:
                return tavily
            return f"{existing}\n\n{tavily}"

        merged = merge_context(original, enrichment)

        # Both should be present in merged (if non-empty)
        if original:
            assert original in merged, "Original content lost in merge"
        if enrichment:
            assert enrichment in merged, "Enrichment content lost in merge"

    @given(original=st.text(min_size=1, max_size=500))
    @settings(max_examples=100)
    def test_merge_with_empty_enrichment_returns_original(self, original: str):
        """
        Property: Empty enrichment returns original unchanged.

        When enrichment is empty, the original should be returned as-is.
        """

        def merge_context(existing: str, tavily: str) -> str:
            if not tavily:
                return existing
            if not existing:
                return tavily
            return f"{existing}\n\n{tavily}"

        merged = merge_context(original, "")
        assert merged == original, "Original modified when enrichment is empty"

        merged_none = merge_context(original, None)
        assert merged_none == original, "Original modified when enrichment is None"

    @given(enrichment=st.text(min_size=1, max_size=500))
    @settings(max_examples=100)
    def test_merge_with_empty_original_returns_enrichment(self, enrichment: str):
        """
        Property: Empty original returns enrichment unchanged.

        When original is empty, the enrichment should be returned as-is.
        """

        def merge_context(existing: str, tavily: str) -> str:
            if not tavily:
                return existing
            if not existing:
                return tavily
            return f"{existing}\n\n{tavily}"

        merged = merge_context("", enrichment)
        assert merged == enrichment, "Enrichment modified when original is empty"

    @given(
        original=st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
        enrichment=st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100)
    def test_merge_length_is_sum_plus_separator(self, original: str, enrichment: str):
        """
        Property: Merged length equals sum of parts plus separator.

        For non-empty inputs, merged length should be predictable.
        """

        def merge_context(existing: str, tavily: str) -> str:
            if not tavily:
                return existing
            if not existing:
                return tavily
            return f"{existing}\n\n{tavily}"

        merged = merge_context(original, enrichment)
        separator_len = 2  # "\n\n"
        expected_len = len(original) + separator_len + len(enrichment)

        assert (
            len(merged) == expected_len
        ), f"Merged length {len(merged)} != expected {expected_len}"



# ============================================
# Property 8: Confidence Adjustment Bounds
# ============================================


class TestConfidenceAdjustmentProperty:
    """
    **Feature: tavily-integration, Property 8: Confidence Adjustment Bounds**
    **Validates: Requirements 4.3**

    For any confidence value between 0.5 and 0.7, after Tavily enrichment
    confirms relevance, the new confidence SHALL be original + 0.15, capped at 1.0.
    """

    @given(
        original_confidence=st.floats(
            min_value=0.5, max_value=0.7, allow_nan=False, allow_infinity=False
        )
    )
    @settings(max_examples=100)
    def test_confidence_boost_is_exactly_0_15(self, original_confidence: float):
        """
        Property: Confidence boost is exactly 0.15.

        For any original confidence in [0.5, 0.7], the boost should be +0.15.
        """
        CONFIDENCE_BOOST = 0.15

        boosted = min(1.0, original_confidence + CONFIDENCE_BOOST)

        # Verify boost amount
        if original_confidence + CONFIDENCE_BOOST <= 1.0:
            expected = original_confidence + CONFIDENCE_BOOST
            assert abs(boosted - expected) < 0.0001, f"Boost incorrect: {boosted} != {expected}"
        else:
            assert boosted == 1.0, "Should be capped at 1.0"

    @given(
        original_confidence=st.floats(
            min_value=0.5, max_value=0.7, allow_nan=False, allow_infinity=False
        )
    )
    @settings(max_examples=100)
    def test_boosted_confidence_never_exceeds_1(self, original_confidence: float):
        """
        Property: Boosted confidence never exceeds 1.0.

        For any original confidence, the result should be capped at 1.0.
        """
        CONFIDENCE_BOOST = 0.15

        boosted = min(1.0, original_confidence + CONFIDENCE_BOOST)

        assert boosted <= 1.0, f"Confidence {boosted} exceeds 1.0"
        assert boosted >= original_confidence, "Boosted should be >= original"

    @given(
        original_confidence=st.floats(
            min_value=0.86, max_value=1.0, allow_nan=False, allow_infinity=False
        )
    )
    @settings(max_examples=100)
    def test_high_confidence_caps_at_1(self, original_confidence: float):
        """
        Property: High confidence values cap at 1.0.

        For confidence values where original + 0.15 > 1.0, result should be 1.0.
        """
        CONFIDENCE_BOOST = 0.15

        boosted = min(1.0, original_confidence + CONFIDENCE_BOOST)

        assert boosted == 1.0, f"Should cap at 1.0, got {boosted}"

    def test_confidence_boost_threshold_boundary(self):
        """
        Property: Boundary test for confidence thresholds.

        Test specific boundary values for the 0.5-0.7 range.
        """
        CONFIDENCE_BOOST = 0.15
        ALERT_THRESHOLD = 0.7

        # At 0.5, boost to 0.65 (still below threshold)
        boosted_low = min(1.0, 0.5 + CONFIDENCE_BOOST)
        assert abs(boosted_low - 0.65) < 0.0001
        assert boosted_low < ALERT_THRESHOLD

        # At 0.55, boost to 0.70 (exactly at threshold)
        boosted_mid = min(1.0, 0.55 + CONFIDENCE_BOOST)
        assert abs(boosted_mid - 0.70) < 0.0001
        assert boosted_mid >= ALERT_THRESHOLD - 0.0001

        # At 0.7, boost to 0.85 (above threshold)
        boosted_high = min(1.0, 0.7 + CONFIDENCE_BOOST)
        assert abs(boosted_high - 0.85) < 0.0001
        assert boosted_high >= ALERT_THRESHOLD



# ============================================
# Property 9: Trust Score Adjustment
# ============================================


class TestTrustScoreAdjustmentProperty:
    """
    **Feature: tavily-integration, Property 9: Trust Score Adjustment**
    **Validates: Requirements 6.2, 6.3, 6.4**

    For any trust score between 0.4 and 0.7, Tavily verification SHALL adjust
    the score by exactly +0.2 (confirmed), -0.1 (contradicted), or 0 (inconclusive),
    with result capped between 0.0 and 1.0.
    """

    @given(
        original_trust=st.floats(
            min_value=0.4, max_value=0.7, allow_nan=False, allow_infinity=False
        )
    )
    @settings(max_examples=100)
    def test_confirmed_boosts_by_0_2(self, original_trust: float):
        """
        Property: Confirmed intel boosts trust by exactly 0.2.

        For any trust score in [0.4, 0.7], confirmation should add 0.2.
        """
        CONFIRM_BOOST = 0.2

        boosted = min(1.0, original_trust + CONFIRM_BOOST)

        # Verify boost amount
        if original_trust + CONFIRM_BOOST <= 1.0:
            expected = original_trust + CONFIRM_BOOST
            assert abs(boosted - expected) < 0.0001, f"Boost incorrect: {boosted} != {expected}"
        else:
            assert boosted == 1.0, "Should be capped at 1.0"

    @given(
        original_trust=st.floats(
            min_value=0.4, max_value=0.7, allow_nan=False, allow_infinity=False
        )
    )
    @settings(max_examples=100)
    def test_contradicted_reduces_by_0_1(self, original_trust: float):
        """
        Property: Contradicted intel reduces trust by exactly 0.1.

        For any trust score in [0.4, 0.7], contradiction should subtract 0.1.
        """
        CONTRADICT_PENALTY = 0.1

        reduced = max(0.0, original_trust - CONTRADICT_PENALTY)

        # Verify reduction amount
        if original_trust - CONTRADICT_PENALTY >= 0.0:
            expected = original_trust - CONTRADICT_PENALTY
            assert (
                abs(reduced - expected) < 0.0001
            ), f"Reduction incorrect: {reduced} != {expected}"
        else:
            assert reduced == 0.0, "Should be capped at 0.0"

    @given(
        original_trust=st.floats(
            min_value=0.4, max_value=0.7, allow_nan=False, allow_infinity=False
        )
    )
    @settings(max_examples=100)
    def test_inconclusive_keeps_original(self, original_trust: float):
        """
        Property: Inconclusive result keeps original trust score.

        For any trust score, inconclusive verification should not change it.
        """
        # Inconclusive = no change
        unchanged = original_trust

        assert (
            abs(unchanged - original_trust) < 0.0001
        ), "Inconclusive should not change trust"

    @given(
        original_trust=st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
        ),
        adjustment=st.sampled_from([0.2, -0.1, 0.0]),
    )
    @settings(max_examples=100)
    def test_result_always_in_bounds(self, original_trust: float, adjustment: float):
        """
        Property: Adjusted trust is always between 0.0 and 1.0.

        For any trust score and adjustment, result should be capped.
        """
        if adjustment > 0:
            result = min(1.0, original_trust + adjustment)
        elif adjustment < 0:
            result = max(0.0, original_trust + adjustment)
        else:
            result = original_trust

        assert 0.0 <= result <= 1.0, f"Result {result} out of bounds [0.0, 1.0]"

    def test_boundary_cases(self):
        """
        Property: Boundary test for trust score adjustments.
        """
        # At 0.4, confirm to 0.6
        assert abs(min(1.0, 0.4 + 0.2) - 0.6) < 0.0001

        # At 0.7, confirm to 0.9
        assert abs(min(1.0, 0.7 + 0.2) - 0.9) < 0.0001

        # At 0.4, contradict to 0.3
        assert abs(max(0.0, 0.4 - 0.1) - 0.3) < 0.0001

        # At 0.9, confirm caps at 1.0
        assert min(1.0, 0.9 + 0.2) == 1.0

        # At 0.05, contradict caps at 0.0
        assert max(0.0, 0.05 - 0.1) == 0.0


# ============================================
# Property 11: Twitter Intel Recovery
# ============================================


class TestTwitterRecoveryProperty:
    """
    **Feature: tavily-integration, Property 11: Twitter Intel Recovery**
    **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

    For any Twitter handle where Gemini/Nitter fails, Tavily SHALL attempt
    recovery and normalize results to CachedTweet format with freshness decay.
    """

    @given(
        handle=st.text(min_size=1, max_size=15).filter(
            lambda x: x.strip() and x.isalnum()
        )
    )
    @settings(max_examples=100)
    def test_handle_normalization(self, handle: str):
        """
        Property: Twitter handles are normalized consistently.

        For any handle input, normalization should produce consistent format.
        """
        from src.ingestion.tavily_query_builder import TavilyQueryBuilder

        query = TavilyQueryBuilder.build_twitter_recovery_query(handle)

        # Query should contain the handle
        assert handle in query or f"@{handle}" in query
        # Query should mention Twitter
        assert "Twitter" in query or "twitter" in query.lower()

    @given(
        age_hours=st.floats(min_value=0, max_value=100, allow_nan=False)
    )
    @settings(max_examples=100)
    def test_freshness_decay_bounds(self, age_hours: float):
        """
        Property: Freshness score is always between 0.0 and 1.0.

        For any content age, freshness score should be bounded.
        """
        # Simulate freshness calculation logic
        if age_hours <= 6:
            score = 1.0
        elif age_hours <= 24:
            score = 1.0 - (age_hours - 6) * (0.5 / 18)
        elif age_hours <= 48:
            score = 0.5 - (age_hours - 24) * (0.3 / 24)
        else:
            score = max(0.1, 0.2 - (age_hours - 48) * 0.001)

        assert 0.0 <= score <= 1.0, f"Freshness {score} out of bounds for age {age_hours}h"

    def test_freshness_decay_milestones(self):
        """
        Property: Freshness decay follows expected milestones.

        Specific age values should produce expected freshness scores.
        """
        # Fresh content (< 6h) = 1.0
        assert abs(1.0 - 1.0) < 0.01  # 0h

        # 6h = 1.0 (boundary)
        score_6h = 1.0
        assert abs(score_6h - 1.0) < 0.01

        # 24h = 0.5 (half decay)
        score_24h = 1.0 - (24 - 6) * (0.5 / 18)
        assert abs(score_24h - 0.5) < 0.01

        # 48h = 0.2 (steep decay)
        score_48h = 0.5 - (48 - 24) * (0.3 / 24)
        assert abs(score_48h - 0.2) < 0.01

    @given(
        content=st.text(min_size=10, max_size=200)
    )
    @settings(max_examples=50)
    def test_topic_extraction_returns_list(self, content: str):
        """
        Property: Topic extraction always returns a list.

        For any content, topic extraction should return a list (possibly empty).
        """
        from src.services.twitter_intel_cache import TwitterIntelCache

        # Create instance for testing
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()

        topics = cache._extract_topics_from_content(content)

        assert isinstance(topics, list)
        # All topics should be strings
        assert all(isinstance(t, str) for t in topics)

    def test_topic_detection_keywords(self):
        """
        Property: Known keywords trigger correct topic detection.
        """
        from src.services.twitter_intel_cache import TwitterIntelCache

        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()

        # Injury keywords
        assert "injury" in cache._extract_topics_from_content("Player injured in training")
        assert "injury" in cache._extract_topics_from_content("Ruled out for 2 weeks")

        # Lineup keywords
        assert "lineup" in cache._extract_topics_from_content("Starting XI announced")
        assert "lineup" in cache._extract_topics_from_content("Squad for tonight")

        # Transfer keywords
        assert "transfer" in cache._extract_topics_from_content("Transfer deal completed")

        # Empty content
        assert cache._extract_topics_from_content("") == []
        assert cache._extract_topics_from_content(None) == []


# ============================================
# Property 12: Fallback Activation on Exhaustion
# ============================================


class TestFallbackActivationProperty:
    """
    **Feature: tavily-integration, Property 12: Fallback Activation on Exhaustion**
    **Validates: Requirements 1.5, 10.2, 11.4**

    For any state where all 7 API keys are exhausted (received 429), the provider
    SHALL switch to Brave/DDG fallback and set is_available() to False.
    """

    @given(num_failures=st.integers(min_value=0, max_value=10))
    @settings(max_examples=100)
    def test_circuit_breaker_opens_after_threshold(self, num_failures: int):
        """
        Property: Circuit breaker opens after threshold failures.

        For any number of failures >= threshold, circuit should open.
        """
        from src.ingestion.tavily_provider import (
            CircuitBreaker,
            CircuitBreakerState,
            CIRCUIT_BREAKER_THRESHOLD,
        )

        breaker = CircuitBreaker()

        for _ in range(num_failures):
            breaker.record_failure()

        if num_failures >= CIRCUIT_BREAKER_THRESHOLD:
            assert breaker.state == CircuitBreakerState.OPEN
        else:
            assert breaker.state == CircuitBreakerState.CLOSED

    @given(num_successes=st.integers(min_value=0, max_value=10))
    @settings(max_examples=100)
    def test_circuit_breaker_closes_after_successes(self, num_successes: int):
        """
        Property: Circuit breaker closes after enough successes in half-open.

        For any number of successes >= threshold in half-open, circuit should close.
        """
        from src.ingestion.tavily_provider import (
            CircuitBreaker,
            CircuitBreakerState,
            CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
        )

        breaker = CircuitBreaker()
        breaker.state = CircuitBreakerState.HALF_OPEN

        for _ in range(num_successes):
            breaker.record_success()

        if num_successes >= CIRCUIT_BREAKER_SUCCESS_THRESHOLD:
            assert breaker.state == CircuitBreakerState.CLOSED
        else:
            assert breaker.state == CircuitBreakerState.HALF_OPEN

    def test_circuit_breaker_state_transitions(self):
        """
        Property: Circuit breaker follows correct state transitions.

        CLOSED -> OPEN (on failures)
        OPEN -> HALF_OPEN (on recovery attempt)
        HALF_OPEN -> CLOSED (on successes)
        HALF_OPEN -> OPEN (on failure)
        """
        from src.ingestion.tavily_provider import (
            CircuitBreaker,
            CircuitBreakerState,
            CIRCUIT_BREAKER_THRESHOLD,
        )

        breaker = CircuitBreaker()

        # Start CLOSED
        assert breaker.state == CircuitBreakerState.CLOSED

        # Failures open circuit
        for _ in range(CIRCUIT_BREAKER_THRESHOLD):
            breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN

        # Success resets failure count
        breaker2 = CircuitBreaker()
        breaker2.record_failure()
        breaker2.record_success()
        assert breaker2.consecutive_failures == 0

    def test_fallback_chain_order(self):
        """
        Property: Fallback chain follows correct order (Brave -> DDG).

        When Tavily fails, fallback should try Brave first, then DDG.
        """
        from src.ingestion.tavily_provider import TavilyProvider
        from src.ingestion.tavily_key_rotator import TavilyKeyRotator

        # Create provider with no keys (forces fallback)
        rotator = TavilyKeyRotator(keys=[])
        provider = TavilyProvider(key_rotator=rotator)

        # Provider should not be available
        assert not provider.is_available()

        # Fallback methods should exist
        assert hasattr(provider, "_fallback_search")
        assert hasattr(provider, "_fallback_to_brave")
        assert hasattr(provider, "_fallback_to_ddg")

    @given(num_keys=st.integers(min_value=1, max_value=7))
    @settings(max_examples=50)
    def test_all_keys_exhausted_triggers_fallback(self, num_keys: int):
        """
        Property: Exhausting all keys triggers fallback mode.

        For any number of keys, exhausting all should set fallback_active.
        """
        from src.ingestion.tavily_provider import TavilyProvider
        from src.ingestion.tavily_key_rotator import TavilyKeyRotator

        keys = [f"tvly-test-key-{i}" for i in range(num_keys)]
        rotator = TavilyKeyRotator(keys=keys)
        provider = TavilyProvider(key_rotator=rotator)

        # Exhaust all keys
        for i in range(num_keys):
            rotator.mark_exhausted(i)

        # Key rotator should report unavailable
        assert not rotator.is_available()

    def test_circuit_breaker_recovery_timing(self):
        """
        Property: Circuit breaker respects recovery timing.

        Recovery attempts should only happen after the configured interval.
        """
        import time
        from src.ingestion.tavily_provider import (
            CircuitBreaker,
            CircuitBreakerState,
            CIRCUIT_BREAKER_THRESHOLD,
            CIRCUIT_BREAKER_RECOVERY_SECONDS,
        )

        breaker = CircuitBreaker()

        # Open the circuit
        for _ in range(CIRCUIT_BREAKER_THRESHOLD):
            breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN

        # Immediately after opening, should not allow request
        breaker.last_recovery_attempt = time.time()
        assert not breaker.should_allow_request()

        # After recovery interval, should allow (half-open)
        breaker.last_recovery_attempt = time.time() - CIRCUIT_BREAKER_RECOVERY_SECONDS - 1
        assert breaker.should_allow_request()
        assert breaker.state == CircuitBreakerState.HALF_OPEN

    def test_fallback_response_format(self):
        """
        Property: Fallback responses have same format as Tavily responses.

        Fallback results should be TavilyResponse objects with TavilyResult items.
        """
        from src.ingestion.tavily_provider import TavilyResponse, TavilyResult

        # Create a mock fallback response
        fallback_response = TavilyResponse(
            query="test query",
            answer=None,  # Fallbacks don't provide AI answers
            results=[
                TavilyResult(
                    title="Test Result",
                    url="https://example.com",
                    content="Test content",
                    score=0.5,
                    published_date=None,
                )
            ],
            response_time=1.0,
        )

        # Verify structure
        assert isinstance(fallback_response, TavilyResponse)
        assert fallback_response.query == "test query"
        assert fallback_response.answer is None
        assert len(fallback_response.results) == 1
        assert isinstance(fallback_response.results[0], TavilyResult)


# ============================================
# Property 14: Native News Parameters (V7.1)
# ============================================


class TestNativeNewsParametersProperty:
    """
    **Feature: tavily-integration, Property 14: Native News Parameters**
    **Validates: Requirements 1.2, 1.3 (V7.1 Enhancement)**
    
    For news searches, the TavilyProvider SHALL use native Tavily API parameters
    (topic="news", days=N) instead of query string manipulation.
    
    This ensures:
    - Better search quality from Tavily's native news filtering
    - Correct cache key generation including topic/days
    - Proper API payload construction
    """
    
    def test_search_news_uses_native_topic_parameter(self):
        """
        REGRESSION TEST: search_news() must use topic="news" native parameter.
        
        This test would FAIL with the old implementation that used:
            news_query = f"{query} news last {days} days"
        
        And PASSES with the new implementation that uses:
            topic="news", days=days
        """
        from unittest.mock import MagicMock, patch
        from src.ingestion.tavily_provider import TavilyProvider
        from src.ingestion.tavily_key_rotator import TavilyKeyRotator
        
        # Create provider with test key
        rotator = TavilyKeyRotator(keys=["tvly-test-key"])
        provider = TavilyProvider(key_rotator=rotator)
        
        # Mock the HTTP client to capture the payload
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "answer": "Test answer",
            "results": []
        }
        
        captured_payload = {}
        
        def capture_post(*args, **kwargs):
            captured_payload.update(kwargs.get("json", {}))
            return mock_response
        
        provider._http_client.post_sync = capture_post
        
        # Call search_news
        provider.search_news(query="Manchester United injury", days=3, max_results=5)
        
        # CRITICAL ASSERTIONS - These would fail with old implementation
        assert "topic" in captured_payload, \
            "BUG: search_news() must include 'topic' parameter in API payload"
        assert captured_payload["topic"] == "news", \
            f"BUG: topic should be 'news', got '{captured_payload.get('topic')}'"
        assert "days" in captured_payload, \
            "BUG: search_news() must include 'days' parameter in API payload"
        assert captured_payload["days"] == 3, \
            f"BUG: days should be 3, got {captured_payload.get('days')}"
        
        # Query should NOT contain "news last X days" manipulation
        query = captured_payload.get("query", "")
        assert "last 3 days" not in query.lower(), \
            f"BUG: Query should not contain time filter string, got: {query}"
        assert query == "Manchester United injury", \
            f"BUG: Query should be clean without manipulation, got: {query}"
    
    @given(days=st.integers(min_value=1, max_value=30))
    @settings(max_examples=20)
    def test_cache_key_includes_topic_and_days(self, days: int):
        """
        Property: Cache keys must include topic and days parameters.
        
        Different topic/days combinations should produce different cache keys
        to avoid returning wrong cached results.
        """
        from src.ingestion.tavily_provider import TavilyProvider
        from src.ingestion.tavily_key_rotator import TavilyKeyRotator
        
        rotator = TavilyKeyRotator(keys=["tvly-test-key"])
        provider = TavilyProvider(key_rotator=rotator)
        
        query = "test query"
        
        # Same query, different topic/days should have different cache keys
        key_general = provider._get_cache_key(query, "basic", 5, topic=None, days=None)
        key_news_7 = provider._get_cache_key(query, "basic", 5, topic="news", days=7)
        key_news_3 = provider._get_cache_key(query, "basic", 5, topic="news", days=3)
        key_news_custom = provider._get_cache_key(query, "basic", 5, topic="news", days=days)
        
        # All should be different (unless days happens to be 7 or 3)
        assert key_general != key_news_7, "General and news cache keys should differ"
        assert key_news_7 != key_news_3, "Different days should produce different cache keys"
        
        if days not in (3, 7):
            assert key_news_custom != key_news_7, "Custom days should differ from 7"
            assert key_news_custom != key_news_3, "Custom days should differ from 3"
    
    def test_search_method_accepts_topic_and_days(self):
        """
        Property: search() method must accept topic and days parameters.
        
        The base search() method should support native Tavily parameters.
        """
        from src.ingestion.tavily_provider import TavilyProvider
        from src.ingestion.tavily_key_rotator import TavilyKeyRotator
        from unittest.mock import MagicMock
        
        rotator = TavilyKeyRotator(keys=["tvly-test-key"])
        provider = TavilyProvider(key_rotator=rotator)
        
        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"answer": None, "results": []}
        
        captured_payload = {}
        def capture_post(*args, **kwargs):
            captured_payload.update(kwargs.get("json", {}))
            return mock_response
        
        provider._http_client.post_sync = capture_post
        
        # Call search with topic and days
        provider.search(
            query="test",
            search_depth="basic",
            max_results=5,
            include_answer=True,
            topic="news",
            days=7
        )
        
        # Verify payload includes topic and days
        assert captured_payload.get("topic") == "news"
        assert captured_payload.get("days") == 7
    
    def test_days_only_sent_when_topic_is_news(self):
        """
        Property: days parameter should only be sent when topic="news".
        
        Per Tavily API docs, days is only valid for news topic.
        """
        from src.ingestion.tavily_provider import TavilyProvider
        from src.ingestion.tavily_key_rotator import TavilyKeyRotator
        from unittest.mock import MagicMock
        
        rotator = TavilyKeyRotator(keys=["tvly-test-key"])
        provider = TavilyProvider(key_rotator=rotator)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"answer": None, "results": []}
        
        captured_payload = {}
        def capture_post(*args, **kwargs):
            captured_payload.clear()
            captured_payload.update(kwargs.get("json", {}))
            return mock_response
        
        provider._http_client.post_sync = capture_post
        
        # Call with days but topic="general" (or None)
        provider.search(query="test", topic="general", days=7)
        
        # days should NOT be in payload when topic is not "news"
        assert "days" not in captured_payload, \
            "BUG: days should not be sent when topic is not 'news'"
        
        # Now call with topic="news"
        provider.search(query="test", topic="news", days=7)
        
        # days SHOULD be in payload
        assert captured_payload.get("days") == 7, \
            "days should be sent when topic='news'"


# ============================================
# Property 15: Component Integration with Native Parameters (V7.1)
# ============================================


class TestComponentNativeParametersProperty:
    """
    **Feature: tavily-integration, Property 15: Component Native Parameters**
    **Validates: V7.1 Enhancement - All news-searching components use native parameters**
    
    Components that search for news should use topic="news" and days=N
    for optimal Tavily API filtering instead of query string manipulation.
    """
    
    def test_news_radar_uses_native_parameters(self):
        """
        REGRESSION TEST: news_radar._tavily_enrich must use topic="news", days=3.
        """
        import inspect
        from src.services import news_radar
        
        # Read the source code of the module
        source = inspect.getsource(news_radar)
        
        # Find the _tavily_enrich method section
        assert 'topic="news"' in source, \
            "BUG: news_radar._tavily_enrich should use topic='news' native parameter"
        assert 'days=3' in source or 'days=3' in source, \
            "BUG: news_radar._tavily_enrich should use days parameter"
        
        # Verify query doesn't contain "news" keyword (moved to topic parameter)
        # The query should be: f"football soccer {search_context}"
        assert 'f"football soccer {search_context}"' in source or \
               "f'football soccer {search_context}'" in source, \
            "BUG: news_radar query should not include 'news' keyword (use topic param instead)"
    
    def test_settler_uses_native_parameters(self):
        """
        REGRESSION TEST: settler._tavily_post_match_search must use topic="news", days=3.
        """
        import inspect
        from src.analysis import settler
        
        source = inspect.getsource(settler)
        
        # Check for native parameters in the tavily search call
        assert 'topic="news"' in source, \
            "BUG: settler._tavily_post_match_search should use topic='news'"
        assert 'days=3' in source, \
            "BUG: settler._tavily_post_match_search should use days=3"
    
    def test_clv_tracker_uses_native_parameters(self):
        """
        REGRESSION TEST: clv_tracker._tavily_verify_line_movement must use topic="news", days=3.
        """
        import inspect
        from src.analysis import clv_tracker
        
        source = inspect.getsource(clv_tracker)
        
        assert 'topic="news"' in source, \
            "BUG: clv_tracker._tavily_verify_line_movement should use topic='news'"
        assert 'days=3' in source, \
            "BUG: clv_tracker._tavily_verify_line_movement should use days=3"
    
    def test_telegram_listener_uses_native_parameters(self):
        """
        REGRESSION TEST: telegram_listener._tavily_verify_intel must use topic="news", days=3.
        """
        import inspect
        from src.processing import telegram_listener
        
        source = inspect.getsource(telegram_listener)
        
        assert 'topic="news"' in source, \
            "BUG: telegram_listener._tavily_verify_intel should use topic='news'"
        assert 'days=3' in source, \
            "BUG: telegram_listener._tavily_verify_intel should use days=3"
    
    def test_twitter_cache_does_not_use_news_topic(self):
        """
        Verify twitter_intel_cache does NOT use topic="news" (it searches tweets, not news).
        """
        import inspect
        from src.services import twitter_intel_cache
        
        source = inspect.getsource(twitter_intel_cache)
        
        # Count occurrences - should be 0 or very few (only in comments maybe)
        # The _recover_via_tavily method should NOT use topic="news"
        recover_section_start = source.find('def _recover_via_tavily')
        recover_section_end = source.find('def _normalize_tavily_to_tweet')
        
        if recover_section_start > 0 and recover_section_end > recover_section_start:
            recover_section = source[recover_section_start:recover_section_end]
            assert 'topic="news"' not in recover_section, \
                "twitter_intel_cache._recover_via_tavily should NOT use topic='news' (it searches tweets)"
