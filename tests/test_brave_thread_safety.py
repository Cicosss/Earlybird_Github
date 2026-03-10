"""
Test for BraveSearchProvider thread-safety.

This test verifies that the singleton pattern is thread-safe and prevents
race conditions in multi-threaded environments (VPS deployment).

V12.2: Added thread-safety test for double-checked locking pattern.
"""

import threading
import pytest
from unittest.mock import patch, MagicMock

from src.ingestion.brave_provider import get_brave_provider, reset_brave_provider, BraveSearchProvider


class TestBraveProviderThreadSafety:
    """Test thread-safety of BraveSearchProvider singleton."""

    def setup_method(self):
        """Reset the singleton before each test."""
        reset_brave_provider()

    def test_singleton_returns_same_instance(self):
        """Test that singleton returns the same instance across multiple calls."""
        # Get instance multiple times
        instance1 = get_brave_provider()
        instance2 = get_brave_provider()
        instance3 = get_brave_provider()

        # All should be the same instance
        assert instance1 is instance2
        assert instance2 is instance3
        assert id(instance1) == id(instance2) == id(instance3)

    def test_concurrent_singleton_creation(self):
        """Test that singleton is thread-safe under concurrent access."""
        instances = []
        num_threads = 20

        def create_instance():
            """Create instance from a thread."""
            instance = get_brave_provider()
            instances.append(instance)

        # Create multiple threads that all try to create the instance simultaneously
        threads = [threading.Thread(target=create_instance) for _ in range(num_threads)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # All instances should be the same (no duplicates)
        assert len(instances) == num_threads, "Not all threads returned an instance"

        # Check that all instances are the same object
        instance_ids = [id(i) for i in instances]
        unique_ids = set(instance_ids)

        assert len(unique_ids) == 1, f"Multiple instances created: {len(unique_ids)} unique instances"

    def test_concurrent_singleton_creation_with_mock_init(self):
        """Test thread-safety with a mocked __init__ that simulates slow initialization."""
        instances = []
        num_threads = 10
        init_delay = 0.1  # seconds

        def slow_init(self):
            """Simulate slow initialization to increase race condition probability."""
            import time
            time.sleep(init_delay)
            # Original __init__ logic
            from src.ingestion.brave_key_rotator import get_brave_key_rotator
            from src.ingestion.brave_budget import get_brave_budget_manager
            from src.utils.http_client import get_http_client
            from config.settings import BRAVE_API_KEY

            self._key_rotator = get_brave_key_rotator()
            self._budget_manager = get_brave_budget_manager()
            self._api_key = BRAVE_API_KEY
            self._rate_limited = False
            self._http_client = get_http_client()
            self._key_rotation_enabled = True

        def create_instance():
            """Create instance from a thread."""
            instance = get_brave_provider()
            instances.append(instance)

        # Patch __init__ to be slow
        with patch.object(BraveSearchProvider, '__init__', slow_init):
            # Create multiple threads
            threads = [threading.Thread(target=create_instance) for _ in range(num_threads)]

            # Start all threads simultaneously
            for t in threads:
                t.start()

            # Wait for all threads to complete
            for t in threads:
                t.join()

        # All instances should be the same (no duplicates even with slow init)
        assert len(instances) == num_threads, "Not all threads returned an instance"

        instance_ids = [id(i) for i in instances]
        unique_ids = set(instance_ids)

        assert len(unique_ids) == 1, f"Multiple instances created with slow init: {len(unique_ids)} unique instances"

    def test_reset_brave_provider(self):
        """Test that reset_brave_provider() allows re-initialization."""
        # Get initial instance
        instance1 = get_brave_provider()
        instance_id1 = id(instance1)

        # Reset the singleton
        reset_brave_provider()

        # Get new instance
        instance2 = get_brave_provider()
        instance_id2 = id(instance2)

        # Should be different instances
        assert instance_id1 != instance_id2, "Reset did not create a new instance"

    def test_concurrent_reset_and_creation(self):
        """Test that reset and creation are thread-safe."""
        instances = []
        num_threads = 10

        def create_instance():
            """Create instance from a thread."""
            instance = get_brave_provider()
            instances.append(instance)

        def reset_instance():
            """Reset instance from a thread."""
            reset_brave_provider()

        # Create threads that both create and reset
        threads = []
        for i in range(num_threads):
            if i % 2 == 0:
                threads.append(threading.Thread(target=create_instance))
            else:
                threads.append(threading.Thread(target=reset_instance))

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # All non-reset instances should be the same
        non_reset_instances = [i for i in instances if i is not None]
        if non_reset_instances:
            instance_ids = [id(i) for i in non_reset_instances]
            unique_ids = set(instance_ids)
            assert len(unique_ids) == 1, f"Multiple instances after concurrent reset: {len(unique_ids)} unique instances"

    def test_singleton_is_initialized_once(self):
        """Test that __init__ is called exactly once even with concurrent access."""
        init_count = 0
        init_lock = threading.Lock()

        def counting_init(self):
            """Count how many times __init__ is called."""
            nonlocal init_count
            with init_lock:
                init_count += 1

            # Simulate some initialization work
            import time
            time.sleep(0.01)

            # Minimal initialization for test
            self._api_key = "test_key"
            self._rate_limited = False
            self._key_rotation_enabled = False

        def create_instance():
            """Create instance from a thread."""
            get_brave_provider()

        # Patch __init__ to count calls
        with patch.object(BraveSearchProvider, '__init__', counting_init):
            # Create multiple threads
            num_threads = 10
            threads = [threading.Thread(target=create_instance) for _ in range(num_threads)]

            # Start all threads simultaneously
            for t in threads:
                t.start()

            # Wait for all threads to complete
            for t in threads:
                t.join()

        # __init__ should be called exactly once
        assert init_count == 1, f"__init__ was called {init_count} times, expected 1"


class TestBraveProviderThreadSafetyIntegration:
    """Integration tests for thread-safety with other components."""

    def setup_method(self):
        """Reset the singleton before each test."""
        reset_brave_provider()

    def test_concurrent_search_news_calls(self):
        """Test that concurrent search_news calls are thread-safe."""
        # Mock the HTTP client to avoid actual API calls
        mock_http_client = MagicMock()
        mock_response = MagicMock()
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
        mock_http_client.get_sync.return_value = mock_response

        results_list = []
        num_threads = 5

        def search_from_thread(query):
            """Perform search from a thread."""
            provider = get_brave_provider()
            # Patch the HTTP client
            provider._http_client = mock_http_client
            results = provider.search_news(query, limit=5, component="test_component")
            results_list.append(len(results))

        # Create threads with different queries
        queries = [f"test query {i}" for i in range(num_threads)]
        threads = [threading.Thread(target=search_from_thread, args=(q,)) for q in queries]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # All searches should complete successfully
        assert len(results_list) == num_threads, "Not all searches completed"

        # All should return 1 result
        assert all(r == 1 for r in results_list), f"Some searches failed: {results_list}"

    def test_concurrent_is_available_calls(self):
        """Test that concurrent is_available calls are thread-safe."""
        results_list = []
        num_threads = 10

        def check_availability():
            """Check availability from a thread."""
            provider = get_brave_provider()
            available = provider.is_available()
            results_list.append(available)

        # Create threads
        threads = [threading.Thread(target=check_availability) for _ in range(num_threads)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # All calls should complete successfully
        assert len(results_list) == num_threads, "Not all availability checks completed"

        # All should return the same result
        assert all(r == results_list[0] for r in results_list), "Inconsistent availability results"

    def test_concurrent_get_status_calls(self):
        """Test that concurrent get_status calls are thread-safe."""
        results_list = []
        num_threads = 10

        def get_status():
            """Get status from a thread."""
            provider = get_brave_provider()
            status = provider.get_status()
            results_list.append(status)

        # Create threads
        threads = [threading.Thread(target=get_status) for _ in range(num_threads)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # All calls should complete successfully
        assert len(results_list) == num_threads, "Not all status calls completed"

        # All should return a dict with expected keys
        expected_keys = {"key_rotation_enabled", "rate_limited", "key_rotator", "budget"}
        for status in results_list:
            assert isinstance(status, dict), "Status should be a dict"
            assert expected_keys.issubset(status.keys()), f"Missing keys in status: {status.keys()}"
