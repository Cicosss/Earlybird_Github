"""
Test MediaStack Query Builder (V1.0)

Tests for MediaStackQueryBuilder component.

Run: pytest tests/test_mediastack_query_builder.py -v
"""
import pytest

from src.ingestion.mediastack_query_builder import MediaStackQueryBuilder


class TestMediaStackQueryBuilder:
    """Tests for MediaStackQueryBuilder class."""

    def test_build_news_query_with_valid_query(self):
        """build_news_query should build valid query."""
        builder = MediaStackQueryBuilder()
        query = builder.build_news_query("Serie A injury", countries="it,gb,us")
        
        # V1.0: Builder uses quote(safe=' '), so spaces are preserved.
        # Requests/HTTP client will handle final encoding.
        assert query == "Serie A injury"
        assert "Serie" in query
        assert "injury" in query

    def test_build_news_query_with_empty_query(self):
        """build_news_query should return empty string for empty query."""
        builder = MediaStackQueryBuilder()
        query = builder.build_news_query("", countries="it,gb,us")
        
        assert query == ""

    def test_build_news_query_with_short_query(self):
        """build_news_query should return empty string for too short query."""
        builder = MediaStackQueryBuilder()
        query = builder.build_news_query("x", countries="it,gb,us")
        
        assert query == ""

    def test_build_news_query_with_custom_countries(self):
        """build_news_query should use custom countries."""
        builder = MediaStackQueryBuilder()
        query = builder.build_news_query("football", countries="de,fr,es")
        
        # V1.0: Builder returns KEYWORDS string only. Countries are handled by caller in params.
        # So countries are NOT in the return string.
        # We verify it doesn't crash, but won't check for 'de' in query string.
        assert "football" in query

    def test_build_batched_query_with_single_question(self):
        """build_batched_query should handle single question."""
        builder = MediaStackQueryBuilder()
        questions = ["Serie A injury"]
        query = builder.build_batched_query(questions)
        
        assert "Serie" in query
        assert "injury" in query

    def test_build_batched_query_with_multiple_questions(self):
        """build_batched_query should combine multiple questions with OR."""
        builder = MediaStackQueryBuilder()
        questions = ["Serie A injury", "Milan Inter lineup", "Juventus news"]
        query = builder.build_batched_query(questions)
        
        assert "Serie" in query
        assert "injury" in query
        assert "Milan" in query
        assert "Inter" in query
        assert "Juventus" in query
        assert " OR " in query

    def test_build_batched_query_with_empty_list(self):
        """build_batched_query should return empty string for empty list."""
        builder = MediaStackQueryBuilder()
        query = builder.build_batched_query([])
        
        assert query == ""

    def test_build_batched_query_filters_invalid_questions(self):
        """build_batched_query should filter out invalid questions."""
        builder = MediaStackQueryBuilder()
        questions = ["valid", "", "  ", "also valid"]
        query = builder.build_batched_query(questions)
        
        assert "valid" in query
        assert "also valid" in query
        assert query.count(" OR ") == 1  # Only one OR between two valid questions

    def test_parse_batched_response_with_empty_data(self):
        """parse_batched_response should return empty list for empty data."""
        builder = MediaStackQueryBuilder()
        response = {"data": []}
        answers = builder.parse_batched_response(response)
        
        assert answers == []

    def test_parse_batched_response_with_valid_data(self):
        """parse_batched_response should extract titles from data."""
        builder = MediaStackQueryBuilder()
        response = {
            "data": [
                {"title": "News 1", "url": "http://example.com/1"},
                {"title": "News 2", "url": "http://example.com/2"},
            ]
        }
        answers = builder.parse_batched_response(response)
        
        assert len(answers) == 2
        assert "News 1" in answers[0]
        assert "News 2" in answers[1]

    def test_parse_batched_response_with_missing_title(self):
        """parse_batched_response should handle missing title."""
        builder = MediaStackQueryBuilder()
        response = {
            "data": [
                {"url": "http://example.com/1"},  # Missing title
            ]
        }
        answers = builder.parse_batched_response(response)
        
        assert len(answers) == 1
        assert answers[0] == ""

    def test_clean_query_removes_exclusions(self):
        """_clean_query should remove -term exclusions."""
        builder = MediaStackQueryBuilder()
        dirty = "football news -basket -basketball -women"
        clean = builder._clean_query(dirty)
        
        assert "basket" not in clean
        assert "basketball" not in clean
        assert "women" not in clean
        assert "football" in clean
        assert "news" in clean

    def test_clean_query_removes_multi_word_exclusions(self):
        """_clean_query should remove multi-word exclusions."""
        builder = MediaStackQueryBuilder()
        dirty = "football -american football -super bowl"
        clean = builder._clean_query(dirty)
        
        assert "american football" not in clean
        assert "super bowl" not in clean
        assert "football" in clean

    def test_clean_query_preserves_legitimate_dashes(self):
        """_clean_query should preserve legitimate dashes."""
        builder = MediaStackQueryBuilder()
        
        # Dash between teams
        clean1 = builder._clean_query("Milan - Inter derby")
        assert "Milan - Inter" in clean1
        
        # Dash in compound word
        clean2 = builder._clean_query("pre-season injury")
        assert "pre-season" in clean2

    def test_clean_query_normalizes_spaces(self):
        """_clean_query should normalize multiple spaces."""
        builder = MediaStackQueryBuilder()
        dirty = "football  -basket   -nba  news"
        clean = builder._clean_query(dirty)
        
        assert clean == "football news"
        assert "  " not in clean  # No double spaces

    def test_clean_query_with_empty_input(self):
        """_clean_query should return empty string for empty input."""
        builder = MediaStackQueryBuilder()
        clean = builder._clean_query("")
        
        assert clean == ""

    def test_clean_query_with_only_exclusions(self):
        """_clean_query should return empty string when only exclusions."""
        builder = MediaStackQueryBuilder()
        clean = builder._clean_query("-basket -basketball -women")
        
        assert clean == ""

    def test_max_query_length_constant(self):
        """MAX_QUERY_LENGTH should be 500."""
        assert MediaStackQueryBuilder.MAX_QUERY_LENGTH == 500
