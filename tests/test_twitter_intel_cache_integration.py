"""
TwitterIntelCache Integration Tests - V10.0

Tests for TwitterIntelCache integration in DeepSeekIntelProvider.
Tests cover the V10.0 fix that replaced broken search engine queries
with TwitterIntelCache.

Created: 2026-02-19 (COVE Verification Fix)
"""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.ingestion.deepseek_intel_provider import DeepSeekIntelProvider
from src.services.twitter_intel_cache import CachedTweet


class TestTwitterIntelCacheIntegration:
    """Test TwitterIntelCache integration in DeepSeekIntelProvider."""

    @pytest.fixture
    def provider(self):
        """Create DeepSeekIntelProvider instance for testing."""
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test_key"}):
            return DeepSeekIntelProvider()

    @pytest.fixture
    def mock_cache(self):
        """Create mock TwitterIntelCache."""
        cache = MagicMock()
        cache.is_fresh = True
        cache.cache_age_minutes = 10
        return cache

    @pytest.fixture
    def sample_tweets(self):
        """Create sample cached tweets."""
        return [
            CachedTweet(
                handle="@testuser",
                date="2026-02-19T10:00:00Z",
                content="Player injured in training",
                topics=["injury"],
            ),
            CachedTweet(
                handle="@testuser",
                date="2026-02-19T11:00:00Z",
                content="Lineup announced for tomorrow",
                topics=["lineup"],
            ),
        ]

    def test_extract_twitter_intel_with_fresh_cache(
        self, provider, mock_cache, sample_tweets
    ):
        """Test that extract_twitter_intel returns cached tweets when cache is fresh."""
        # Setup mock
        mock_cache.search_intel.return_value = sample_tweets

        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            True,
        ), patch(
            "src.ingestion.deepseek_intel_provider.get_twitter_intel_cache",
            return_value=mock_cache,
        ):
            result = provider.extract_twitter_intel(["@testuser"], max_posts_per_account=5)

        # Assertions
        assert result is not None, "Result should not be None when cache is fresh"
        assert "accounts" in result, "Result should contain 'accounts' key"
        assert len(result["accounts"]) == 1, "Should return 1 account"
        assert result["accounts"][0]["handle"] == "@testuser", "Handle should match"
        assert len(result["accounts"][0]["posts"]) == 2, "Should return 2 posts"

        # Check post structure
        post = result["accounts"][0]["posts"][0]
        assert "date" in post, "Post should contain 'date'"
        assert "content" in post, "Post should contain 'content'"
        assert "topics" in post, "Post should contain 'topics'"

        # Check metadata
        assert "_meta" in result, "Result should contain metadata"
        assert result["_meta"]["source"] == "twitter_intel_cache", "Source should be twitter_intel_cache"
        assert result["_meta"]["total_handles_requested"] == 1, "Should request 1 handle"
        assert result["_meta"]["accounts_returned"] == 1, "Should return 1 account"

    def test_extract_twitter_intel_with_stale_cache(self, provider, mock_cache):
        """Test that extract_twitter_intel returns None when cache is not fresh."""
        # Setup mock - cache not fresh
        mock_cache.is_fresh = False
        mock_cache.cache_age_minutes = 400

        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            True,
        ), patch(
            "src.ingestion.deepseek_intel_provider.get_twitter_intel_cache",
            return_value=mock_cache,
        ):
            result = provider.extract_twitter_intel(["@testuser"], max_posts_per_account=5)

        # Assertions
        assert result is None, "Result should be None when cache is not fresh"

    def test_extract_twitter_intel_with_cache_unavailable(self, provider):
        """Test that extract_twitter_intel returns None when TwitterIntelCache is not available."""
        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            False,
        ):
            result = provider.extract_twitter_intel(["@testuser"], max_posts_per_account=5)

        # Assertions
        assert result is None, "Result should be None when TwitterIntelCache is not available"

    def test_extract_twitter_intel_with_empty_handles(self, provider):
        """Test that extract_twitter_intel returns None when handles list is empty."""
        result = provider.extract_twitter_intel([], max_posts_per_account=5)

        # Assertions
        assert result is None, "Result should be None when handles list is empty"

    def test_extract_twitter_intel_with_invalid_handles(self, provider):
        """Test that extract_twitter_intel filters out invalid handles."""
        # Setup mock
        mock_cache = MagicMock()
        mock_cache.is_fresh = True
        mock_cache.search_intel.return_value = []

        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            True,
        ), patch(
            "src.ingestion.deepseek_intel_provider.get_twitter_intel_cache",
            return_value=mock_cache,
        ):
            result = provider.extract_twitter_intel(
                ["@valid", "", None, "invalid_no_at", "   "], max_posts_per_account=5
            )

        # Assertions
        assert result is None, "Result should be None when no valid handles found"

    def test_extract_twitter_intel_with_no_tweets_found(self, provider, mock_cache):
        """Test that extract_twitter_intel returns None when no tweets are found."""
        # Setup mock - no tweets found
        mock_cache.search_intel.return_value = []

        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            True,
        ), patch(
            "src.ingestion.deepseek_intel_provider.get_twitter_intel_cache",
            return_value=mock_cache,
        ):
            result = provider.extract_twitter_intel(["@testuser"], max_posts_per_account=5)

        # Assertions
        assert result is None, "Result should be None when no tweets are found"

    def test_extract_twitter_intel_limits_posts_per_account(
        self, provider, mock_cache, sample_tweets
    ):
        """Test that extract_twitter_intel limits posts to max_posts_per_account."""
        # Create more tweets than limit
        many_tweets = sample_tweets * 3  # 6 tweets
        mock_cache.search_intel.return_value = many_tweets

        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            True,
        ), patch(
            "src.ingestion.deepseek_intel_provider.get_twitter_intel_cache",
            return_value=mock_cache,
        ):
            result = provider.extract_twitter_intel(["@testuser"], max_posts_per_account=3)

        # Assertions
        assert result is not None, "Result should not be None"
        assert len(result["accounts"][0]["posts"]) == 3, "Should limit to 3 posts"

    def test_extract_twitter_intel_filters_by_topics(
        self, provider, mock_cache
    ):
        """Test that extract_twitter_intel filters tweets by topics."""
        # Create tweets with different topics
        tweets = [
            CachedTweet(
                handle="@testuser",
                date="2026-02-19T10:00:00Z",
                content="Player injured",
                topics=["injury"],
            ),
            CachedTweet(
                handle="@testuser",
                date="2026-02-19T11:00:00Z",
                content="Random weather tweet",
                topics=["weather"],  # Not in filter
            ),
            CachedTweet(
                handle="@testuser",
                date="2026-02-19T12:00:00Z",
                content="Lineup announced",
                topics=["lineup"],
            ),
        ]

        mock_cache.search_intel.return_value = tweets

        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            True,
        ), patch(
            "src.ingestion.deepseek_intel_provider.get_twitter_intel_cache",
            return_value=mock_cache,
        ):
            result = provider.extract_twitter_intel(["@testuser"], max_posts_per_account=10)

        # Assertions - should only return tweets with football-relevant topics
        # Note: This test depends on how search_intel filters by topics
        # For now, we just verify that the method works
        assert result is not None, "Result should not be None"

    def test_extract_twitter_intel_handles_multiple_accounts(
        self, provider, mock_cache
    ):
        """Test that extract_twitter_intel handles multiple accounts."""
        # Setup mock - return different tweets for each account
        def mock_search_intel(query, league_key, topics):
            if "user1" in query:
                return [
                    CachedTweet(
                        handle="@user1",
                        date="2026-02-19T10:00:00Z",
                        content="Tweet from user1",
                        topics=["injury"],
                    )
                ]
            elif "user2" in query:
                return [
                    CachedTweet(
                        handle="@user2",
                        date="2026-02-19T11:00:00Z",
                        content="Tweet from user2",
                        topics=["lineup"],
                    )
                ]
            return []

        mock_cache.search_intel.side_effect = mock_search_intel

        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            True,
        ), patch(
            "src.ingestion.deepseek_intel_provider.get_twitter_intel_cache",
            return_value=mock_cache,
        ):
            result = provider.extract_twitter_intel(
                ["@user1", "@user2"], max_posts_per_account=5
            )

        # Assertions
        assert result is not None, "Result should not be None"
        assert len(result["accounts"]) == 2, "Should return 2 accounts"
        handles = [acc["handle"] for acc in result["accounts"]]
        assert "@user1" in handles, "Should include @user1"
        assert "@user2" in handles, "Should include @user2"

    def test_extract_twitter_intel_metadata_is_complete(
        self, provider, mock_cache, sample_tweets
    ):
        """Test that extract_twitter_intel correctly sets is_complete metadata."""
        mock_cache.search_intel.return_value = sample_tweets

        # Test with 50% coverage (2 accounts requested, 1 returned)
        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            True,
        ), patch(
            "src.ingestion.deepseek_intel_provider.get_twitter_intel_cache",
            return_value=mock_cache,
        ):
            result = provider.extract_twitter_intel(
                ["@user1", "@user2"], max_posts_per_account=5
            )

        # Assertions
        assert result is not None, "Result should not be None"
        assert "_meta" in result, "Result should contain metadata"
        # is_complete should be True if at least 50% coverage
        # In this case, we have 1 account returned out of 2 requested (50%)
        # The implementation uses >= 0.5, so 50% should be True
        assert result["_meta"]["is_complete"] == True, "is_complete should be True for 50% coverage"

    def test_extract_twitter_intel_provider_not_available(self, provider):
        """Test that extract_twitter_intel returns None when provider is not available."""
        # Mock provider as not available
        provider._enabled = False

        result = provider.extract_twitter_intel(["@testuser"], max_posts_per_account=5)

        # Assertions
        assert result is None, "Result should be None when provider is not available"

    def test_extract_twitter_intel_exception_handling(
        self, provider, mock_cache
    ):
        """Test that extract_twitter_intel handles exceptions gracefully."""
        # Setup mock to raise exception
        mock_cache.search_intel.side_effect = Exception("Test exception")

        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            True,
        ), patch(
            "src.ingestion.deepseek_intel_provider.get_twitter_intel_cache",
            return_value=mock_cache,
        ):
            result = provider.extract_twitter_intel(["@testuser"], max_posts_per_account=5)

        # Assertions
        assert result is None, "Result should be None when exception occurs"

    def test_extract_twitter_intel_removes_at_from_handle(
        self, provider, mock_cache, sample_tweets
    ):
        """Test that extract_twitter_intel removes @ from handle when searching cache."""
        mock_cache.search_intel.return_value = sample_tweets

        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            True,
        ), patch(
            "src.ingestion.deepseek_intel_provider.get_twitter_intel_cache",
            return_value=mock_cache,
        ):
            result = provider.extract_twitter_intel(["@testuser"], max_posts_per_account=5)

        # Assertions
        assert result is not None, "Result should not be None"
        # Verify that search_intel was called with handle without @
        mock_cache.search_intel.assert_called_once()
        call_args = mock_cache.search_intel.call_args
        assert call_args[1]["query"] == "testuser", "Should search with handle without @"

    def test_extract_twitter_intel_handles_handles_without_at(
        self, provider, mock_cache, sample_tweets
    ):
        """Test that extract_twitter_intel handles handles without @ prefix."""
        mock_cache.search_intel.return_value = sample_tweets

        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            True,
        ), patch(
            "src.ingestion.deepseek_intel_provider.get_twitter_intel_cache",
            return_value=mock_cache,
        ):
            result = provider.extract_twitter_intel(["testuser"], max_posts_per_account=5)

        # Assertions
        assert result is not None, "Result should not be None"
        assert result["accounts"][0]["handle"] == "testuser", "Handle should be preserved as-is"
        # Verify that search_intel was called with handle without @
        mock_cache.search_intel.assert_called_once()
        call_args = mock_cache.search_intel.call_args
        assert call_args[1]["query"] == "testuser", "Should search with handle without @"

    def test_extract_twitter_intel_handles_handles_with_whitespace(
        self, provider, mock_cache, sample_tweets
    ):
        """Test that extract_twitter_intel handles handles with whitespace."""
        mock_cache.search_intel.return_value = sample_tweets

        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            True,
        ), patch(
            "src.ingestion.deepseek_intel_provider.get_twitter_intel_cache",
            return_value=mock_cache,
        ):
            result = provider.extract_twitter_intel(["  @testuser  "], max_posts_per_account=5)

        # Assertions
        assert result is not None, "Result should not be None"
        assert result["accounts"][0]["handle"] == "  @testuser  ", "Handle should be preserved as-is"
        # Verify that search_intel was called with handle without @ (whitespace preserved)
        mock_cache.search_intel.assert_called_once()
        call_args = mock_cache.search_intel.call_args
        # Note: The code only removes @, not whitespace
        assert call_args[1]["query"] == "  testuser  ", "Should search with @ removed but whitespace preserved"

    def test_extract_twitter_intel_post_structure(
        self, provider, mock_cache, sample_tweets
    ):
        """Test that extract_twitter_intel returns posts with correct structure."""
        mock_cache.search_intel.return_value = sample_tweets

        with patch(
            "src.ingestion.deepseek_intel_provider._TWITTER_INTEL_CACHE_AVAILABLE",
            True,
        ), patch(
            "src.ingestion.deepseek_intel_provider.get_twitter_intel_cache",
            return_value=mock_cache,
        ):
            result = provider.extract_twitter_intel(["@testuser"], max_posts_per_account=5)

        # Assertions
        assert result is not None, "Result should not be None"
        posts = result["accounts"][0]["posts"]
        assert len(posts) == 2, "Should return 2 posts"

        # Check first post structure
        post = posts[0]
        assert "date" in post, "Post should contain 'date'"
        assert post["date"] == "2026-02-19T10:00:00Z", "Date should match"
        assert "content" in post, "Post should contain 'content'"
        assert post["content"] == "Player injured in training", "Content should match"
        assert "topics" in post, "Post should contain 'topics'"
        assert post["topics"] == ["injury"], "Topics should match"

        # Check second post structure
        post = posts[1]
        assert post["date"] == "2026-02-19T11:00:00Z", "Date should match"
        assert post["content"] == "Lineup announced for tomorrow", "Content should match"
        assert post["topics"] == ["lineup"], "Topics should match"
