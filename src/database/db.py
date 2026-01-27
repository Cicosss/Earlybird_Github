import logging
from typing import List
from datetime import datetime
from contextlib import contextmanager
from src.database.models import init_db as init_models, SessionLocal, Match as MatchModel, NewsLog, TeamAlias


@contextmanager
def get_db_context():
    """Context manager per sessioni DB con auto-commit/rollback."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

# Re-exporting init for compatibility
def init_db():
    init_models()
    logging.info("Database initialized successfully (SQLAlchemy).")

# Adapter classes/types if needed, or we can use the Models directly if we update the rest of the app.
# For now, let's keep the calling signature similar but use SQLAlchemy internals.

def save_matches(matches_data: List[object]):
    """
    Saves a list of match objects (dataclasses or dicts) to the DB.
    Expects objects with: id, sport_key, home_team, away_team, commence_time
    Uses context manager pattern for proper session handling.
    """
    db = SessionLocal()
    try:
        for m in matches_data:
            # Parse time if needed, assuming m.commence_time is ISO string or datetime
            if isinstance(m.commence_time, str):
                start_time = datetime.fromisoformat(m.commence_time.replace('Z', '+00:00')).replace(tzinfo=None)
            else:
                start_time = m.commence_time

            # Check if exists
            existing = db.query(MatchModel).filter(MatchModel.id == m.id).first()
            if existing:
                existing.league = m.sport_key
                existing.home_team = m.home_team
                existing.away_team = m.away_team
                existing.start_time = start_time
                # odds not passed in current simple object, ignore for now
            else:
                new_match = MatchModel(
                    id=m.id,
                    league=m.sport_key,
                    home_team=m.home_team,
                    away_team=m.away_team,
                    start_time=start_time
                )
                db.add(new_match)
                
                # Create default Team Aliases if they don't exist
                _ensure_alias(db, m.home_team)
                _ensure_alias(db, m.away_team)
                
        db.commit()
    except Exception as e:
        logging.error(f"Error saving matches: {e}")
        try:
            db.rollback()
        except Exception as rollback_err:
            logging.error(f"Error during rollback: {rollback_err}")
    finally:
        try:
            db.close()
        except Exception as close_err:
            logging.error(f"Error closing database session: {close_err}")

def _ensure_alias(db, team_name):
    # Simple clean: remove FC, SK, etc can be added here or in ingest
    # For now just ensure the entity exists
    try:
        if not db.query(TeamAlias).filter(TeamAlias.api_name == team_name).first():
           # Default clean name (placeholder logic)
           clean_name = team_name.replace(" FC", "").replace(" SK", "").replace(" Club", "")
           alias = TeamAlias(api_name=team_name, search_name=clean_name)
           db.add(alias)
    except Exception as e:
        logging.error(f"Handled error in _ensure_alias: {e}")

def save_analysis(analysis_data: object):
    """
    Saves analysis result.
    Expects object with: match_id, url, summary, relevance_score, category, affected_team
    Uses proper error handling for rollback and close operations.
    """
    db = SessionLocal()
    try:
        log = NewsLog(
            match_id=analysis_data.match_id,
            url=analysis_data.url,
            summary=analysis_data.summary,
            score=analysis_data.score,
            category=analysis_data.category,
            affected_team=analysis_data.affected_team
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logging.error(f"Error saving analysis: {e}")
        try:
            db.rollback()
        except Exception as rollback_err:
            logging.error(f"Error during rollback: {rollback_err}")
    finally:
        try:
            db.close()
        except Exception as close_err:
            logging.error(f"Error closing database session: {close_err}")

def get_upcoming_matches():
    db = SessionLocal()
    try:
        # Return SQLAlchemy objects, or convert to simple objects if needed
        # The main app expects objects with .id, .sport_key (mapped to league), .home_team, .away_team
        matches = db.query(MatchModel).all()
        # Conversion to generic object to maintain compatibility with main.py if it expects specific attrs
        # We can just return the model instances if we verify attribute names align.
        # MatchModel has: id, league (needs alias to sport_key?), home_team, away_team
        
        # Quick adapter list
        results = []
        for m in matches:
            # Dynamically adding sport_key for compatibility
            m.sport_key = m.league 
            # ensure commence_time is string if expected, or datetime
            m.commence_time = m.start_time
            results.append(m)
        return results
    finally:
        db.close()
