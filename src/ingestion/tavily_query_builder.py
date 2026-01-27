"""
Tavily Query Builder - V7.0

Builds optimized queries for Tavily AI Search with batching support.
Combines multiple questions into single queries to maximize API efficiency.

Requirements: 2.1, 2.2, 2.3, 2.4
"""
import logging
import re
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.ingestion.tavily_provider import TavilyResponse

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
    Query builder with batching support.
    
    Combines multiple questions into single queries
    to maximize API efficiency.
    
    Requirements: 2.1, 2.2, 2.3, 2.4
    """
    
    @staticmethod
    def build_match_enrichment_query(
        home_team: str,
        away_team: str,
        match_date: str,
        questions: Optional[List[str]] = None
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
        news_title: str,
        team_name: str,
        additional_context: str = ""
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
        home_team: str,
        away_team: str,
        league: str,
        season_context: str
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
            "standings implications | mutual benefit | draw scenario | both teams need points"
        ]
        
        # Filter empty parts and join
        query = " ".join(part for part in query_parts if part)
        
        return query
    
    @staticmethod
    def build_twitter_recovery_query(
        handle: str,
        keywords: Optional[List[str]] = None
    ) -> str:
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
    
    @staticmethod
    def parse_batched_response(
        response: "TavilyResponse",
        question_count: int
    ) -> List[str]:
        """
        Parse batched response into individual answers.
        
        Extracts individual answers from a Tavily response that
        was generated from a batched query.
        
        Args:
            response: TavilyResponse from Tavily API
            question_count: Number of questions in the original batch
            
        Returns:
            List of answer strings mapped to original questions
            
        Requirements: 2.3
        """
        if not response:
            return [""] * question_count
        
        answers = []
        
        # If we have an AI-generated answer, try to parse it
        if response.answer:
            # Try to split by common separators
            raw_answer = response.answer
            
            # Try numbered list format (1. answer 2. answer)
            numbered_pattern = r'\d+\.\s*'
            parts = re.split(numbered_pattern, raw_answer)
            parts = [p.strip() for p in parts if p.strip()]
            
            if len(parts) >= question_count:
                answers = parts[:question_count]
            else:
                # Try pipe separator
                pipe_parts = raw_answer.split("|")
                pipe_parts = [p.strip() for p in pipe_parts if p.strip()]
                
                if len(pipe_parts) >= question_count:
                    answers = pipe_parts[:question_count]
                else:
                    # Fall back to using the whole answer for each question
                    answers = [raw_answer] * question_count
        
        # If no answer, try to extract from results
        if not answers and response.results:
            # Use result snippets as answers
            for i in range(question_count):
                if i < len(response.results):
                    answers.append(response.results[i].content)
                else:
                    answers.append("")
        
        # Ensure we have the right number of answers
        while len(answers) < question_count:
            answers.append("")
        
        return answers[:question_count]
    
    @staticmethod
    def split_long_query(query: str, max_length: int = MAX_QUERY_LENGTH) -> List[str]:
        """
        Split a long query into multiple shorter queries.
        
        When a query exceeds the maximum length, splits it into
        multiple queries that can be executed separately.
        
        Args:
            query: Original query string
            max_length: Maximum length per query (default 500)
            
        Returns:
            List of query strings, each under max_length
            
        Requirements: 2.4
        """
        if not query:
            return []
        
        if len(query) <= max_length:
            return [query]
        
        queries = []
        
        # Try to split by pipe separator first (batched questions)
        if QUESTION_SEPARATOR in query:
            # Extract base context (before the colon)
            colon_idx = query.find(":")
            if colon_idx > 0:
                base_context = query[:colon_idx].strip()
                questions_part = query[colon_idx + 1:].strip()
                questions = questions_part.split(QUESTION_SEPARATOR)
                
                current_query = base_context + ":"
                current_questions = []
                
                for q in questions:
                    q = q.strip()
                    if not q:
                        continue
                    
                    # Check if adding this question would exceed limit
                    test_query = current_query + " " + QUESTION_SEPARATOR.join(current_questions + [q])
                    
                    if len(test_query) <= max_length:
                        current_questions.append(q)
                    else:
                        # Save current query and start new one
                        if current_questions:
                            queries.append(current_query + " " + QUESTION_SEPARATOR.join(current_questions))
                        current_questions = [q]
                
                # Add remaining questions
                if current_questions:
                    queries.append(current_query + " " + QUESTION_SEPARATOR.join(current_questions))
            else:
                # No colon, split by separator directly
                parts = query.split(QUESTION_SEPARATOR)
                current_query = ""
                
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    
                    test_query = current_query + (QUESTION_SEPARATOR if current_query else "") + part
                    
                    if len(test_query) <= max_length:
                        current_query = test_query
                    else:
                        if current_query:
                            queries.append(current_query)
                        current_query = part
                
                if current_query:
                    queries.append(current_query)
        else:
            # No separator, split by words
            words = query.split()
            current_query = ""
            
            for word in words:
                test_query = current_query + (" " if current_query else "") + word
                
                if len(test_query) <= max_length:
                    current_query = test_query
                else:
                    if current_query:
                        queries.append(current_query)
                    current_query = word
            
            if current_query:
                queries.append(current_query)
        
        # Ensure all queries are under max_length
        result = []
        for q in queries:
            if len(q) <= max_length:
                result.append(q)
            else:
                # Force truncate if still too long
                result.append(q[:max_length])
        
        return result if result else [query[:max_length]]
    
    @staticmethod
    def estimate_query_count(questions: List[str], base_context: str = "") -> int:
        """
        Estimate how many API calls will be needed for a set of questions.
        
        Args:
            questions: List of questions to batch
            base_context: Base context string
            
        Returns:
            Estimated number of API calls needed
        """
        if not questions:
            return 0
        
        # Build full query
        full_query = base_context + ": " + QUESTION_SEPARATOR.join(questions)
        
        # Count how many splits needed
        return len(TavilyQueryBuilder.split_long_query(full_query))
