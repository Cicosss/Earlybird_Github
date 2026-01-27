from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, create_engine, Boolean, Float, event, Index
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime

Base = declarative_base()

class Match(Base):
    __tablename__ = 'matches'
    
    id = Column(String, primary_key=True) # Unique ID from The-Odds-API
    league = Column(String) # sport_key
    home_team = Column(String)
    away_team = Column(String)
    start_time = Column(DateTime)
    
    # Opening Odds (First time we see the match - NEVER updated)
    opening_home_odd = Column(Float, nullable=True)
    opening_away_odd = Column(Float, nullable=True)
    opening_draw_odd = Column(Float, nullable=True)  # BISCOTTO: Draw opening line
    
    # Current Odds (Latest market prices - Updated on each ingestion)
    current_home_odd = Column(Float, nullable=True)
    current_away_odd = Column(Float, nullable=True)
    current_draw_odd = Column(Float, nullable=True)  # BISCOTTO: Draw current line
    
    # Totals Market (Over/Under 2.5 Goals)
    opening_over_2_5 = Column(Float, nullable=True)
    opening_under_2_5 = Column(Float, nullable=True)
    current_over_2_5 = Column(Float, nullable=True)
    current_under_2_5 = Column(Float, nullable=True)
    
    # LAYER 3: Sharp Odds (Smart Money Detection)
    sharp_bookie = Column(String, nullable=True)  # e.g., 'pinnacle' or 'min_proxy'
    sharp_home_odd = Column(Float, nullable=True)
    sharp_draw_odd = Column(Float, nullable=True)
    sharp_away_odd = Column(Float, nullable=True)
    avg_home_odd = Column(Float, nullable=True)
    avg_draw_odd = Column(Float, nullable=True)
    avg_away_odd = Column(Float, nullable=True)
    is_sharp_drop = Column(Boolean, default=False)  # True if smart money detected
    sharp_signal = Column(String, nullable=True)  # e.g., "SMART MONEY on HOME"
    
    # Alert flags to prevent spam
    odds_alert_sent = Column(Boolean, default=False)  # Prevents repeated odds alerts
    biscotto_alert_sent = Column(Boolean, default=False)  # Prevents repeated biscotto alerts
    sharp_alert_sent = Column(Boolean, default=False)  # Prevents repeated sharp alerts
    
    # Score-delta deduplication (V2.6)
    highest_score_sent = Column(Float, default=0.0)  # Highest score already alerted for this match
    last_alert_time = Column(DateTime, nullable=True)  # V7.3: When last alert was sent (for temporal reset)
    
    # INVESTIGATOR MODE: Case Closed cooldown (V3.2)
    last_deep_dive_time = Column(DateTime, nullable=True)  # When last full investigation was done
    
    # V3.7: Stats Warehousing (populated by settler after match ends)
    home_corners = Column(Integer, nullable=True)
    away_corners = Column(Integer, nullable=True)
    home_yellow_cards = Column(Integer, nullable=True)
    away_yellow_cards = Column(Integer, nullable=True)
    home_red_cards = Column(Integer, nullable=True)
    away_red_cards = Column(Integer, nullable=True)
    home_xg = Column(Float, nullable=True)  # Expected Goals
    away_xg = Column(Float, nullable=True)
    home_possession = Column(Float, nullable=True)  # Possession %
    away_possession = Column(Float, nullable=True)
    home_shots_on_target = Column(Integer, nullable=True)
    away_shots_on_target = Column(Integer, nullable=True)
    home_big_chances = Column(Integer, nullable=True)
    away_big_chances = Column(Integer, nullable=True)
    home_fouls = Column(Integer, nullable=True)
    away_fouls = Column(Integer, nullable=True)
    
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    news_logs = relationship("NewsLog", back_populates="match")
    
    # Composite Index for main query optimization (start_time + league filter)
    # Speeds up the hourly match fetch by ~10x
    __table_args__ = (
        Index('idx_match_time_league', 'start_time', 'league'),
    )

class NewsLog(Base):
    __tablename__ = 'news_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, ForeignKey('matches.id'))
    url = Column(String)
    summary = Column(String)
    score = Column(Integer) # Relevance Score 0-10
    category = Column(String) # INJURY, TURNOVER, etc.
    affected_team = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    sent = Column(Boolean, default=False)
    
    # Combo bet fields (added v2.1)
    combo_suggestion = Column(String, nullable=True)  # e.g., "Over 2.5 + BTTS"
    combo_reasoning = Column(String, nullable=True)   # Why this combo was suggested
    recommended_market = Column(String, nullable=True)  # Primary market recommendation
    
    # Quantitative fields (added v2.9)
    primary_driver = Column(String, nullable=True)  # INJURY_INTEL, SHARP_MONEY, MATH_VALUE, CONTEXT_PLAY, CONTRARIAN
    closing_odds = Column(Float, nullable=True)  # For Closing Line Value analysis (future)
    
    # V4.2: CLV Tracking - odds at moment of alert vs closing
    odds_taken = Column(Float, nullable=True)  # Odds when we sent the alert
    clv_percent = Column(Float, nullable=True)  # Calculated CLV after match starts
    
    # V7.4: Combo Expansion Tracking - Auto-Learning System
    combo_outcome = Column(String, nullable=True)  # WIN/LOSS/PENDING for expansion
    combo_explanation = Column(String, nullable=True)  # Detailed explanation of expansion result
    expansion_type = Column(String, nullable=True)  # Type: over/under, gg/ng, corners, cards
    
    # Intelligence source (added v3.5)
    source = Column(String, nullable=True, default='web')  # 'web', 'telegram_ocr', 'telegram_channel'
    
    # V8.1: Confidence breakdown for transparency
    confidence_breakdown = Column(String, nullable=True)  # JSON string: {"news_weight": 30, "odds_weight": 20, ...}
    
    # V8.2: Final Verifier and Feedback Loop tracking
    final_verifier_result = Column(String, nullable=True)  # JSON string with complete verifier result
    feedback_loop_used = Column(Boolean, default=False)  # Whether feedback loop was applied
    feedback_loop_iterations = Column(Integer, default=0)  # Number of feedback loop iterations
    modification_plan = Column(String, nullable=True)  # JSON string with modification plan
    modification_applied = Column(Boolean, default=False)  # Whether modifications were applied
    original_score = Column(Integer, nullable=True)  # Original score before modifications
    original_market = Column(String, nullable=True)  # Original market before modifications
    
    match = relationship("Match", back_populates="news_logs")

class TeamAlias(Base):
    __tablename__ = 'team_aliases'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    api_name = Column(String, unique=True, nullable=False)
    search_name = Column(String, nullable=False)
    twitter_handle = Column(String, nullable=True)  # e.g., "@GalatasaraySK"
    telegram_channel = Column(String, nullable=True)  # e.g., "galatasaray" or "flamengooficial"


# Database Setup
import os
import time
from contextlib import contextmanager
from functools import wraps

DB_DIR = "data"
DB_FILE = "earlybird.db"

# Ensure data directory exists
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

DB_PATH = f"sqlite:///{DB_DIR}/{DB_FILE}"

# SQLite connection args for better concurrency
# - check_same_thread=False: Allow multi-threaded access
# - timeout=60: Wait up to 60s for lock release (increased from 30)
engine = create_engine(
    DB_PATH,
    connect_args={
        "check_same_thread": False,
        "timeout": 60
    },
    pool_pre_ping=True,  # Verify connections before use
    pool_size=5,         # Allow multiple connections for concurrent operations
    max_overflow=5,      # Allow up to 10 total connections under load
    pool_timeout=60,     # Wait up to 60s for a connection from pool
    pool_recycle=3600    # Recycle connections after 1 hour
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Enable WAL mode + busy_timeout for better concurrency
# WAL allows concurrent reads while writing
# busy_timeout waits instead of failing immediately on lock
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=60000")  # 60 seconds wait on lock (increased)
    cursor.execute("PRAGMA synchronous=NORMAL")  # Faster writes, still safe with WAL
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA cache_size=-64000")   # 64MB cache
    cursor.close()

def init_db():
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db_session(max_retries: int = 3, retry_delay: float = 1.0):
    """
    Context manager for database sessions with automatic retry on lock.
    
    Usage:
        with get_db_session() as db:
            db.query(Match).all()
            # Auto-commits on success, auto-rollbacks on error
    
    Args:
        max_retries: Number of retries on database lock
        retry_delay: Base delay between retries (exponential backoff)
    """
    last_error = None
    
    for attempt in range(max_retries):
        db = SessionLocal()
        try:
            yield db
            db.commit()
            return
        except Exception as e:
            db.rollback()
            error_str = str(e).lower()
            
            # Check if it's a lock error
            if 'database is locked' in error_str or 'locked' in error_str:
                last_error = e
                wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                import logging
                logging.warning(f"⚠️ DB locked (attempt {attempt + 1}/{max_retries}), waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
                continue
            else:
                # Non-lock error, re-raise immediately
                raise
        finally:
            db.close()
    
    # All retries exhausted
    if last_error:
        raise last_error


def get_db():
    """Legacy generator for FastAPI dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def with_db_retry(max_retries: int = 3, retry_delay: float = 1.0):
    """
    Decorator for functions that need DB access with retry logic.
    
    Usage:
        @with_db_retry()
        def my_db_function():
            db = SessionLocal()
            try:
                # ... db operations
            finally:
                db.close()
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).lower()
                    if 'database is locked' in error_str or 'locked' in error_str:
                        last_error = e
                        wait_time = retry_delay * (2 ** attempt)
                        import logging
                        logging.warning(f"⚠️ DB locked in {func.__name__} (attempt {attempt + 1}/{max_retries}), waiting {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        continue
                    raise
            if last_error:
                raise last_error
        return wrapper
    return decorator
