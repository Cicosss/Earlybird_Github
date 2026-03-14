"""
Test MediaStack Query Builder (V1.0)

Tests for MediaStackQueryBuilder component.

Run: pytest tests/test_mediastack_query_builder.py -v
"""

from src.ingestion.mediastack_query_builder import MediaStackQueryBuilder


class TestMediaStackQueryBuilder:
    """Tests for MediaStackQueryBuilder class."""

    def test_build_news_query_with_valid_query(self):
        """build_news_query should build valid query."""
        builder = MediaStackQueryBuilder()
        query = builder.build_news_query("Serie A injury")

        # V2.0: Builder uses quote(safe=' '), so spaces are preserved.
        # Requests/HTTP client will handle final encoding.
        assert query == "Serie A injury"
        assert "Serie" in query
        assert "injury" in query

    def test_build_news_query_with_empty_query(self):
        """build_news_query should return empty string for empty query."""
        builder = MediaStackQueryBuilder()
        query = builder.build_news_query("")

        assert query == ""

    def test_build_news_query_with_short_query(self):
        """build_news_query should return empty string for too short query."""
        builder = MediaStackQueryBuilder()
        query = builder.build_news_query("x")

        assert query == ""

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

    def test_build_batched_queries_with_short_list(self):
        """build_batched_queries should handle short list without splitting."""
        builder = MediaStackQueryBuilder()
        questions = ["Serie A injury", "Milan Inter lineup", "Juventus news"]
        queries = builder.build_batched_queries(questions)

        assert len(queries) == 1
        assert "Serie" in queries[0]
        assert "injury" in queries[0]
        assert "Milan" in queries[0]
        assert "Inter" in queries[0]
        assert "Juventus" in queries[0]
        assert " OR " in queries[0]

    def test_build_batched_queries_with_long_list(self):
        """build_batched_queries should split long list into multiple queries."""
        builder = MediaStackQueryBuilder()
        # Use longer questions to force splitting
        questions = [
            "Serie A injury news update latest transfer rumors",
            "Milan Inter lineup starting eleven formation tactics",
            "Juventus team news squad updates injuries suspensions",
            "Roma Napoli match preview prediction analysis statistics",
            "Atalanta Lazio head to head record recent results",
            "Fiorentina Torino player ratings performance review",
            "Bologna Verona highlights goals assists key moments",
            "Genoa Cagliari standings table position points",
            "Monza Lecce live score commentary minute by minute",
            "Udinese Sassuolo transfer market rumors signings",
        ]
        queries = builder.build_batched_queries(questions)

        # Should split into multiple queries
        assert len(queries) >= 2
        # All questions should be included across all queries
        all_questions_combined = " ".join(queries)
        for q in questions:
            assert q in all_questions_combined

    def test_build_batched_queries_with_empty_list(self):
        """build_batched_queries should return empty list for empty input."""
        builder = MediaStackQueryBuilder()
        queries = builder.build_batched_queries([])

        assert queries == []

    def test_build_batched_queries_filters_invalid_questions(self):
        """build_batched_queries should filter out invalid questions."""
        builder = MediaStackQueryBuilder()
        questions = ["valid", "", "  ", "also valid", "x"]
        queries = builder.build_batched_queries(questions)

        assert len(queries) >= 1
        all_questions_combined = " ".join(queries)
        assert "valid" in all_questions_combined
        assert "also valid" in all_questions_combined
        # Empty and single-char questions should be filtered out

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
        answers = builder.parse_batched_response(response, query_count=1)

        assert len(answers) == 2
        assert "News 1" in answers[0]
        assert "News 2" in answers[1]

    def test_parse_batched_response_with_query_count(self):
        """parse_batched_response should accept query_count parameter."""
        builder = MediaStackQueryBuilder()
        response = {
            "data": [
                {"title": "News 1", "url": "http://example.com/1"},
            ]
        }
        # Should not crash with query_count parameter
        answers = builder.parse_batched_response(response, query_count=3)

        assert len(answers) == 1
        assert "News 1" in answers[0]

    def test_parse_batched_response_with_missing_title(self):
        """parse_batched_response should handle missing title."""
        builder = MediaStackQueryBuilder()
        response = {
            "data": [
                {"url": "http://example.com/1"},  # Missing title
            ]
        }
        answers = builder.parse_batched_response(response, query_count=1)

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
