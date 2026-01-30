"""
Database Operations Module for EarlyBird
=======================================
Provides clean, maintainable database operations with proper session handling and error management.

Phase 1 Critical Fix: Added Unicode normalization for consistent text handling
"""
 
import logging
import unicodedata
from typing import List, Optional, Any
from datetime import datetime
from contextlib import contextmanager
from src.database.models import (
    init_db as init_models,
    SessionLocal,
    Match as MatchModel,
    NewsLog,
    TeamAlias
)

# Configure logger
logger = logging.getLogger(__name__)


def normalize_unicode(text: str) -> str:
    """
    Normalize Unicode to NFC form for consistent text handling.
    
    Phase 1 Critical Fix: Ensures special characters from Turkish, Polish,
    Greek, Arabic, Chinese, Japanese, Korean, and other languages
    are handled consistently across all components.
    
    Args:
        text: Input text to normalize
        
    Returns:
        Normalized text in NFC form
    """
    if not text:
        return ""
    return unicodedata.normalize('NFC', text)


@contextmanager
def get_db_context():
    """
    Context manager for database sessions with auto-commit/rollback and proper cleanup.
    
    Yields:
        SQLAlchemy session object
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"Database operation failed: {e}")
        session.rollback()
        raise
    finally:
        session.close()


# Re-exporting init for compatibility
def init_db() -> None:
    """Initialize the database models."""
    init_models()
    logger.info("Database initialized successfully (SQLAlchemy).")


def _ensure_alias(session, team_name: str) -> None:
    """
    Ensure a TeamAlias exists for the given team name.
    
    Args:
        session: Active database session
        team_name: Name of the team to create an alias for
    """
    try:
        existing = session.query(TeamAlias).filter(TeamAlias.api_name == team_name).first()
        if not existing:
            # Clean common team name suffixes for search optimization
            clean_name = team_name.replace(" FC", "").replace(" SK", "").replace(" Club", "")
            alias = TeamAlias(api_name=team_name, search_name=clean_name)
            session.add(alias)
    except Exception as e:
        logger.error(f"Error ensuring team alias for '{team_name}': {e}")


def save_matches(matches_data: List[Any]) -> None:
    """
    Saves a list of match objects to the database.
    
    Expects objects with: id, sport_key, home_team, away_team, commence_time
    
    Args:
        matches_data: List of match objects/dataclasses/dictionaries to save
    """
    with get_db_context() as session:
        for m in matches_data:
            try:
                # Parse and normalize match time
                if isinstance(m.commence_time, str):
                    start_time = datetime.fromisoformat(m.commence_time.replace('Z', '+00:00')).replace(tzinfo=None)
                else:
                    start_time = m.commence_time.replace(tzinfo=None) if m.commence_time.tzinfo else m.commence_time

                # Check if match already exists
                existing = session.query(MatchModel).filter(MatchModel.id == m.id).first()
                if existing:
                    # Update existing match
                    existing.league = m.sport_key
                    existing.home_team = m.home_team
                    existing.away_team = m.away_team
                    existing.start_time = start_time
                else:
                    # Create new match
                    new_match = MatchModel(
                        id=m.id,
                        league=m.sport_key,
                        home_team=m.home_team,
                        away_team=m.away_team,
                        start_time=start_time
                    )
                    session.add(new_match)
                    
                    # Create team aliases if they don't exist
                    _ensure_alias(session, m.home_team)
                    _ensure_alias(session, m.away_team)
            except Exception as e:
                logger.error(f"Error processing match '{getattr(m, 'id', 'unknown')}': {e}")


def save_analysis(analysis_data: Any) -> None:
    """
    Saves an analysis result to the database.
    
    Expects object with: match_id, url, summary, relevance_score, category, affected_team
    
    Args:
        analysis_data: Analysis result object/dataclass/dictionary
    """
    with get_db_context() as session:
        try:
            log = NewsLog(
                match_id=analysis_data.match_id,
                url=analysis_data.url,
                summary=analysis_data.summary,
                score=analysis_data.score,
                category=analysis_data.category,
                affected_team=analysis_data.affected_team
            )
            session.add(log)
        except Exception as e:
            logger.error(f"Error saving analysis: {e}")


def get_upcoming_matches() -> List[MatchModel]:
    """
    Get all upcoming matches from the database.
    
    Returns:
        List of MatchModel objects with compatibility attributes (sport_key, commence_time)
    """
    with get_db_context() as session:
        try:
            matches = session.query(MatchModel).all()
            
            # Add compatibility attributes for older code that uses sport_key and commence_time
            for match in matches:
                match.sport_key = match.league
                match.commence_time = match.start_time
                
            return matches
        except Exception as e:
            logger.error(f"Error getting upcoming matches: {e}")
            return []
