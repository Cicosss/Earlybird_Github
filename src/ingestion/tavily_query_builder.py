"""
Tavily Query Builder - V8.0

Builds optimized queries for Tavily AI Search.
Provides query building utilities for various search scenarios.

Requirements: 2.1, 2.2

Note: V8.0 removed unused functions (parse_batched_response, split_long_query,
      estimate_query_count) that were never called in production.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum query length before splitting
MAX_QUERY_LENGTH = 500

# Separator for batched questions
QUESTION_SEPARATOR = " | "

# Default questions for match enrichment
DEFAULT_MATCH_QUESTIONS = [
    "Recent team news and injuries",
    "Head-to-head history",
    "Current form and standings",
    "Key player availability",
]


class TavilyQueryBuilder:
    """
    Query builder for Tavily AI Search.

    Provides static methods to build optimized queries for various
    search scenarios including match enrichment, news verification,
    biscotto analysis, and Twitter recovery.

    Requirements: 2.1, 2.2
    """

    @staticmethod
    def build_match_enrichment_query(
        home_team: str, away_team: str, match_date: str, questions: Optional[list[str]] = None
    ) -> str:
        """
        Build batched query for match enrichment.

        Combines match context with multiple questions into a single
        optimized query for Tavily AI Search.

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date (YYYY-MM-DD format)
            questions: List of questions to include (defaults to standard set)

        Returns:
            Formatted query string

        Requirements: 2.1, 2.2
        """
        if not home_team or not away_team:
            return ""

        # Use default questions if none provided
        if questions is None:
            questions = DEFAULT_MATCH_QUESTIONS

        # Build base context
        base_context = f"{home_team} vs {away_team}"
        if match_date:
            base_context += f" {match_date}"

        # Combine questions with separator
        if questions:
            questions_str = QUESTION_SEPARATOR.join(questions)
            query = f"{base_context}: {questions_str}"
        else:
            query = base_context

        return query

    @staticmethod
    def build_news_verification_query(
        news_title: str, team_name: str, additional_context: str = ""
    ) -> str:
        """
        Build query for news verification.

        Creates a query to verify if a news item is accurate
        and find corroborating sources.

        Args:
            news_title: Title of the news to verify
            team_name: Team the news is about
            additional_context: Extra context to include

        Returns:
            Formatted verification query

        Requirements: 2.1
        """
        if not news_title:
            return ""

        # Clean and truncate title if needed
        clean_title = news_title.strip()[:200]

        query = f'Verify: "{clean_title}"'

        if team_name:
            query += f" {team_name}"

        if additional_context:
            query += f" {additional_context.strip()[:100]}"

        return query

    @staticmethod
    def build_biscotto_query(
        home_team: str, away_team: str, league: str, season_context: str
    ) -> str:
        """
        Build query for biscotto (match-fixing) confirmation.

        Creates a query to search for evidence of mutual benefit
        scenarios between two teams.

        Args:
            home_team: Home team name
            away_team: Away team name
            league: League name
            season_context: Season context (e.g., "last 3 matches of season")

        Returns:
            Formatted biscotto query

        Requirements: 2.1
        """
        if not home_team or not away_team:
            return ""

        query_parts = [
            f"{home_team} vs {away_team}",
            league if league else "",
            season_context if season_context else "",
            "standings implications | mutual benefit | draw scenario | both teams need points",
        ]

        # Filter empty parts and join
        query = " ".join(part for part in query_parts if part)

        return query

    @staticmethod
    def build_twitter_recovery_query(handle: str, keywords: Optional[list[str]] = None) -> str:
        """
        Build query for Twitter intel recovery.

        Creates a query to find recent tweets from a specific account
        when direct Twitter access fails.

        Args:
            handle: Twitter handle (with or without @)
            keywords: Optional keywords to filter results

        Returns:
            Formatted Twitter recovery query

        Requirements: 2.1
        """
        if not handle:
            return ""

        # Normalize handle
        clean_handle = handle.strip()
        if not clean_handle.startswith("@"):
            clean_handle = f"@{clean_handle}"

        query = f"Twitter {clean_handle} recent tweets"

        if keywords:
            keywords_str = " ".join(keywords[:5])  # Limit to 5 keywords
            query += f" {keywords_str}"

        return query
