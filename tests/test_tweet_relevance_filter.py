"""
Tests for Tweet Relevance Filter - EarlyBird V4.6

Tests the intelligent filtering of Twitter Intel for match analysis.
Covers:
- Team name matching (exact, alias, fuzzy)
- Freshness calculation
- Relevance scoring
- Conflict detection
- Edge cases (None, empty lists, missing data)
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock


class TestTeamMatching:
    """Tests for team name matching logic."""
    
    def test_exact_team_match(self):
        """Exact team name should match with high confidence."""
        from src.services.tweet_relevance_filter import match_team_in_text
        
        matched, confidence = match_team_in_text(
            "Galatasaray injury update: Icardi out for 2 weeks",
            "Galatasaray"
        )
        
        assert matched is True
        assert confidence >= 0.8
    
    def test_alias_match_gala(self):
        """Alias 'Gala' should match Galatasaray."""
        from src.services.tweet_relevance_filter import match_team_in_text
        
        matched, confidence = match_team_in_text(
            "Gala vs Fener derby preview",
            "Galatasaray"
        )
        
        assert matched is True
        assert confidence >= 0.6
    
    def test_alias_match_boca(self):
        """Alias 'CABJ' should match Boca Juniors."""
        from src.services.tweet_relevance_filter import match_team_in_text
        
        matched, confidence = match_team_in_text(
            "CABJ lineup confirmed for Copa",
            "Boca Juniors"
        )
        
        assert matched is True
        assert confidence >= 0.6
    
    def test_no_match_unrelated_text(self):
        """Unrelated text should not match."""
        from src.services.tweet_relevance_filter import match_team_in_text
        
        matched, confidence = match_team_in_text(
            "Weather forecast for tomorrow",
            "Galatasaray"
        )
        
        assert matched is False
        assert confidence == 0.0
    
    def test_empty_text_no_crash(self):
        """Empty text should not crash, return no match."""
        from src.services.tweet_relevance_filter import match_team_in_text
        
        matched, confidence = match_team_in_text("", "Galatasaray")
        assert matched is False
        
        matched, confidence = match_team_in_text(None, "Galatasaray")
        assert matched is False
    
    def test_empty_team_no_crash(self):
        """Empty team name should not crash, return no match."""
        from src.services.tweet_relevance_filter import match_team_in_text
        
        matched, confidence = match_team_in_text("Some text", "")
        assert matched is False
        
        matched, confidence = match_team_in_text("Some text", None)
        assert matched is False
    
    def test_case_insensitive_match(self):
        """Matching should be case insensitive."""
        from src.services.tweet_relevance_filter import match_team_in_text
        
        matched1, _ = match_team_in_text("GALATASARAY news", "galatasaray")
        matched2, _ = match_team_in_text("galatasaray news", "GALATASARAY")
        
        assert matched1 is True
        assert matched2 is True


class TestFreshnessCalculation:
    """Tests for tweet freshness calculation."""
    
    def test_fresh_tweet_just_now(self):
        """'just now' should be FRESH with high score."""
        from src.services.tweet_relevance_filter import calculate_tweet_freshness
        
        score, hours, tag = calculate_tweet_freshness("just now")
        
        assert tag == "🔥 FRESH"
        assert score == 1.0
        assert hours < 1
    
    def test_fresh_tweet_2_hours(self):
        """2 hours ago should be FRESH."""
        from src.services.tweet_relevance_filter import calculate_tweet_freshness
        
        score, hours, tag = calculate_tweet_freshness("2 hours ago")
        
        assert tag == "🔥 FRESH"
        assert score == 1.0
        assert 1 <= hours <= 3
    
    def test_aging_tweet_12_hours(self):
        """12 hours ago should be AGING."""
        from src.services.tweet_relevance_filter import calculate_tweet_freshness
        
        score, hours, tag = calculate_tweet_freshness("12 hours ago")
        
        assert tag == "⏰ AGING"
        assert score == 0.5
        assert 10 <= hours <= 14
    
    def test_stale_tweet_2_days(self):
        """2 days ago should be STALE."""
        from src.services.tweet_relevance_filter import calculate_tweet_freshness
        
        score, hours, tag = calculate_tweet_freshness("2 days ago")
        
        assert tag == "⚠️ STALE"
        assert score == 0.1
        assert 40 <= hours <= 50
    
    def test_expired_tweet_1_week(self):
        """1 week ago should be EXPIRED."""
        from src.services.tweet_relevance_filter import calculate_tweet_freshness
        
        score, hours, tag = calculate_tweet_freshness("1 week ago")
        
        assert tag == "❌ EXPIRED"
        assert score == 0.0
    
    def test_none_date_default(self):
        """None date should use default (not crash)."""
        from src.services.tweet_relevance_filter import calculate_tweet_freshness
        
        # Should not raise exception
        score, hours, tag = calculate_tweet_freshness(None)
        
        assert score > 0  # Some default score
        assert hours > 0  # Some default hours
    
    def test_empty_date_default(self):
        """Empty date should use default (not crash)."""
        from src.services.tweet_relevance_filter import calculate_tweet_freshness
        
        score, hours, tag = calculate_tweet_freshness("")
        
        assert score > 0
        assert hours > 0


class TestRelevanceScoring:
    """Tests for relevance scoring logic."""
    
    def test_injury_topic_high_relevance(self):
        """Injury topic should have highest relevance."""
        from src.services.tweet_relevance_filter import calculate_relevance_score
        
        score = calculate_relevance_score(
            tweet_topics=["injury"],
            tweet_content="Player X injured"
        )
        
        assert score >= 0.9
    
    def test_lineup_topic_high_relevance(self):
        """Lineup topic should have high relevance."""
        from src.services.tweet_relevance_filter import calculate_relevance_score
        
        score = calculate_relevance_score(
            tweet_topics=["lineup", "squad"],
            tweet_content="Starting XI confirmed"
        )
        
        assert score >= 0.8
    
    def test_transfer_topic_medium_relevance(self):
        """Transfer topic should have medium relevance."""
        from src.services.tweet_relevance_filter import calculate_relevance_score
        
        score = calculate_relevance_score(
            tweet_topics=["transfer"],
            tweet_content="New signing announced"
        )
        
        assert 0.6 <= score <= 0.8
    
    def test_general_topic_base_relevance(self):
        """General topic should have base relevance."""
        from src.services.tweet_relevance_filter import calculate_relevance_score
        
        score = calculate_relevance_score(
            tweet_topics=["general"],
            tweet_content="Match preview"
        )
        
        assert score >= 0.4
        assert score <= 0.6
    
    def test_empty_topics_no_crash(self):
        """Empty topics should not crash."""
        from src.services.tweet_relevance_filter import calculate_relevance_score
        
        score = calculate_relevance_score(
            tweet_topics=[],
            tweet_content="Some content"
        )
        
        assert score >= 0  # Base score
    
    def test_none_topics_no_crash(self):
        """None topics should not crash."""
        from src.services.tweet_relevance_filter import calculate_relevance_score
        
        score = calculate_relevance_score(
            tweet_topics=None,
            tweet_content="Some content"
        )
        
        assert score >= 0
    
    def test_injury_keyword_in_content(self):
        """Injury keyword in content should boost relevance."""
        from src.services.tweet_relevance_filter import calculate_relevance_score
        
        score = calculate_relevance_score(
            tweet_topics=[],
            tweet_content="Player ruled out with injury"
        )
        
        assert score >= 0.9


class TestConflictDetection:
    """Tests for conflict detection between Twitter and FotMob."""
    
    def test_no_conflict_when_empty(self):
        """Empty inputs should not detect conflict."""
        from src.services.tweet_relevance_filter import detect_conflicts
        
        has_conflict, desc = detect_conflicts([], "")
        assert has_conflict is False
        assert desc is None
    
    def test_no_conflict_when_tweets_none(self):
        """None tweets should not crash."""
        from src.services.tweet_relevance_filter import detect_conflicts
        
        has_conflict, desc = detect_conflicts(None, "FotMob data")
        assert has_conflict is False
    
    def test_no_conflict_when_fotmob_none(self):
        """None FotMob data should not crash."""
        from src.services.tweet_relevance_filter import detect_conflicts, ScoredTweet
        
        mock_tweet = ScoredTweet(
            handle="@test",
            content="Player fit",
            date="1h ago",
            topics=["injury"],
            relevance_score=1.0,
            freshness_score=1.0,
            combined_score=1.0,
            freshness_tag="🔥 FRESH",
            age_hours=1.0,
            matched_team="Test FC"
        )
        
        has_conflict, desc = detect_conflicts([mock_tweet], None)
        assert has_conflict is False


class TestFilterTweetsForMatch:
    """Tests for the main filter function."""
    
    def test_filter_returns_result_structure(self):
        """Filter should return proper TweetFilterResult structure."""
        from src.services.tweet_relevance_filter import filter_tweets_for_match, TweetFilterResult
        
        result = filter_tweets_for_match(
            home_team="Galatasaray",
            away_team="Fenerbahce",
            league_key="soccer_turkey_super_league"
        )
        
        assert isinstance(result, TweetFilterResult)
        assert hasattr(result, 'tweets')
        assert hasattr(result, 'total_found')
        assert hasattr(result, 'total_relevant')
        assert hasattr(result, 'has_conflicts')
        assert hasattr(result, 'formatted_for_ai')
    
    def test_filter_empty_cache_no_crash(self):
        """Filter with empty cache should not crash."""
        from src.services.tweet_relevance_filter import filter_tweets_for_match
        
        # Should not raise exception even if cache is empty/stale
        result = filter_tweets_for_match(
            home_team="Unknown Team",
            away_team="Another Unknown",
            league_key="unknown_league"
        )
        
        assert result.tweets == []
        assert result.total_found == 0
    
    def test_filter_none_teams_no_crash(self):
        """Filter with None teams should not crash."""
        from src.services.tweet_relevance_filter import filter_tweets_for_match
        
        result = filter_tweets_for_match(
            home_team=None,
            away_team=None,
            league_key=None
        )
        
        # Should return empty result, not crash
        assert result.total_found >= 0


class TestFormatForAI:
    """Tests for AI formatting output."""
    
    def test_format_empty_tweets(self):
        """Empty tweets should return empty string."""
        from src.services.tweet_relevance_filter import format_tweets_for_ai
        
        result = format_tweets_for_ai(
            tweets=[],
            has_conflicts=False,
            conflict_desc=None,
            total_relevant=0
        )
        
        assert result == ""
    
    def test_format_includes_freshness_tag(self):
        """Formatted output should include freshness tags."""
        from src.services.tweet_relevance_filter import format_tweets_for_ai, ScoredTweet
        
        mock_tweet = ScoredTweet(
            handle="@RudyGaletti",
            content="Icardi out for 2 weeks",
            date="2h ago",
            topics=["injury"],
            relevance_score=1.0,
            freshness_score=1.0,
            combined_score=1.0,
            freshness_tag="🔥 FRESH",
            age_hours=2.0,
            matched_team="Galatasaray"
        )
        
        result = format_tweets_for_ai(
            tweets=[mock_tweet],
            has_conflicts=False,
            conflict_desc=None,
            total_relevant=1
        )
        
        assert "🔥 FRESH" in result
        assert "@RudyGaletti" in result
        assert "Icardi" in result
    
    def test_format_includes_conflict_warning(self):
        """Formatted output should include conflict warning if detected."""
        from src.services.tweet_relevance_filter import format_tweets_for_ai, ScoredTweet
        
        mock_tweet = ScoredTweet(
            handle="@test",
            content="Player fit",
            date="1h ago",
            topics=["injury"],
            relevance_score=1.0,
            freshness_score=1.0,
            combined_score=1.0,
            freshness_tag="🔥 FRESH",
            age_hours=1.0,
            matched_team="Test FC"
        )
        
        result = format_tweets_for_ai(
            tweets=[mock_tweet],
            has_conflicts=True,
            conflict_desc="Twitter says fit, FotMob says injured",
            total_relevant=1
        )
        
        assert "CONFLICT" in result
        assert "Gemini" in result or "Verify" in result


class TestNormalizeTeamName:
    """Tests for team name normalization."""
    
    def test_normalize_removes_fc_suffix(self):
        """Should remove FC suffix."""
        from src.services.tweet_relevance_filter import normalize_team_name
        
        assert normalize_team_name("Celtic FC") == "celtic"
        assert normalize_team_name("Sydney FC") == "sydney"
    
    def test_normalize_removes_sk_suffix(self):
        """Should remove SK suffix."""
        from src.services.tweet_relevance_filter import normalize_team_name
        
        assert normalize_team_name("Galatasaray SK") == "galatasaray"
    
    def test_normalize_handles_none(self):
        """Should handle None input."""
        from src.services.tweet_relevance_filter import normalize_team_name
        
        assert normalize_team_name(None) == ""
        assert normalize_team_name("") == ""


class TestGetTeamAliases:
    """Tests for team alias retrieval."""
    
    def test_get_aliases_known_team(self):
        """Known team should return aliases."""
        from src.services.tweet_relevance_filter import get_team_aliases
        
        aliases = get_team_aliases("Galatasaray")
        
        assert "galatasaray" in aliases
        assert "gala" in aliases or "gs" in aliases
    
    def test_get_aliases_unknown_team(self):
        """Unknown team should return at least the normalized name."""
        from src.services.tweet_relevance_filter import get_team_aliases
        
        aliases = get_team_aliases("Unknown Team FC")
        
        assert len(aliases) >= 1
        assert "unknown team" in aliases or "unknown" in aliases


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_division_by_zero_protection(self):
        """Should not crash on potential division by zero."""
        from src.services.tweet_relevance_filter import match_team_in_text
        
        # Team with no tokens after normalization
        matched, conf = match_team_in_text("text", "   ")
        assert conf == 0.0
    
    def test_unicode_team_names(self):
        """Should handle unicode team names."""
        from src.services.tweet_relevance_filter import match_team_in_text
        
        matched, conf = match_team_in_text(
            "Fenerbahçe news update",
            "Fenerbahçe"
        )
        
        assert matched is True
    
    def test_very_long_content(self):
        """Should handle very long tweet content."""
        from src.services.tweet_relevance_filter import format_tweets_for_ai, ScoredTweet
        
        long_content = "A" * 500  # Very long content
        
        mock_tweet = ScoredTweet(
            handle="@test",
            content=long_content,
            date="1h ago",
            topics=[],
            relevance_score=0.5,
            freshness_score=1.0,
            combined_score=0.5,
            freshness_tag="🔥 FRESH",
            age_hours=1.0,
            matched_team="Test"
        )
        
        result = format_tweets_for_ai([mock_tweet], False, None, 1)
        
        # Should truncate content
        assert len(result) < len(long_content) + 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestGeminiConflictResolution:
    """Tests for Gemini conflict resolution integration."""
    
    def test_resolve_conflict_via_gemini_exists(self):
        """resolve_conflict_via_gemini function should exist."""
        from src.services.tweet_relevance_filter import resolve_conflict_via_gemini
        
        assert callable(resolve_conflict_via_gemini)
    
    def test_resolve_conflict_returns_none_when_gemini_unavailable(self):
        """Should return None gracefully when Gemini is not available."""
        from src.services.tweet_relevance_filter import resolve_conflict_via_gemini
        
        # This will return None if Gemini is not configured (expected in test env)
        result = resolve_conflict_via_gemini(
            conflict_description="Test conflict",
            home_team="Test FC",
            away_team="Other FC",
            twitter_claim="Player fit",
            fotmob_claim="Player injured"
        )
        
        # Should not crash, returns None or dict
        assert result is None or isinstance(result, dict)
    
    def test_format_gemini_resolution_empty(self):
        """Empty resolution should return empty string."""
        from src.main import _format_gemini_resolution
        
        assert _format_gemini_resolution(None) == ""
        assert _format_gemini_resolution({}) == ""
    
    def test_format_gemini_resolution_confirmed(self):
        """CONFIRMED status should show verified message."""
        from src.main import _format_gemini_resolution
        
        resolution = {
            'verification_status': 'CONFIRMED',
            'confidence_level': 'HIGH',
            'additional_context': 'Multiple sources confirm'
        }
        
        result = _format_gemini_resolution(resolution)
        
        assert "CONFIRMED" in result
        assert "VERIFIED" in result
        assert "HIGH" in result
    
    def test_format_gemini_resolution_denied(self):
        """DENIED status should show FotMob is correct."""
        from src.main import _format_gemini_resolution
        
        resolution = {
            'verification_status': 'DENIED',
            'confidence_level': 'MEDIUM'
        }
        
        result = _format_gemini_resolution(resolution)
        
        assert "DENIED" in result
        assert "FotMob" in result
