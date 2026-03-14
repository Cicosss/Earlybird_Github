"""
EarlyBird Database Models - SQLAlchemy ORM

Defines the core database schema for the EarlyBird betting intelligence system.
All models are designed for SQLite with WAL mode for better concurrency.

VPS Compatibility:
- Uses relative paths for database file
- Includes connection pooling and retry logic
- Thread-safe session management
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

logger = logging.getLogger(__name__)
Base = declarative_base()


class Match(Base):
    """
    Match model representing a football match with odds and metadata.

    Tracks opening and current odds, sharp money signals, alert flags,
    and post-match statistics for settlement analysis.
    """

    __tablename__ = "matches"

    # Primary identification
    # Phase 1 Critical Fix: Added COLLATE NOCASE for proper Unicode handling
    id = Column(String, primary_key=True, comment="Unique ID from The-Odds-API")
    league = Column(String, nullable=False, comment="Sport/league key (e.g., soccer_epl)")
    home_team = Column(String, nullable=False, comment="Home team name")
    away_team = Column(String, nullable=False, comment="Away team name")
    start_time = Column(DateTime, nullable=False, comment="Match kickoff time (UTC)")

    # Opening Odds (First time we see the match - NEVER updated)
    opening_home_odd = Column(Float, nullable=True, comment="Opening home win odds")
    opening_away_odd = Column(Float, nullable=True, comment="Opening away win odds")
    opening_draw_odd = Column(
        Float, nullable=True, comment="Opening draw odds (Biscotto detection)"
    )

    # Current Odds (Latest market prices - Updated on each ingestion)
    current_home_odd = Column(Float, nullable=True, comment="Current home win odds")
    current_away_odd = Column(Float, nullable=True, comment="Current away win odds")
    current_draw_odd = Column(Float, nullable=True, comment="Current draw odds")

    # Totals Market (Over/Under 2.5 Goals)
    opening_over_2_5 = Column(Float, nullable=True, comment="Opening over 2.5 goals odds")
    opening_under_2_5 = Column(Float, nullable=True, comment="Opening under 2.5 goals odds")
    current_over_2_5 = Column(Float, nullable=True, comment="Current over 2.5 goals odds")
    current_under_2_5 = Column(Float, nullable=True, comment="Current under 2.5 goals odds")

    # Sharp Odds (Smart Money Detection)
    sharp_bookie = Column(String, nullable=True, comment="Sharp bookie name (e.g., 'pinnacle')")
    sharp_home_odd = Column(Float, nullable=True, comment="Sharp bookie home odds")
    sharp_draw_odd = Column(Float, nullable=True, comment="Sharp bookie draw odds")
    sharp_away_odd = Column(Float, nullable=True, comment="Sharp bookie away odds")
    avg_home_odd = Column(Float, nullable=True, comment="Average home odds across bookies")
    avg_draw_odd = Column(Float, nullable=True, comment="Average draw odds across bookies")
    avg_away_odd = Column(Float, nullable=True, comment="Average away odds across bookies")
    is_sharp_drop = Column(Boolean, default=False, comment="True if smart money detected")
    sharp_signal = Column(
        String, nullable=True, comment="Signal description (e.g., 'SMART MONEY on HOME')"
    )

    # Alert flags to prevent spam
    odds_alert_sent = Column(Boolean, default=False, comment="Prevents repeated odds alerts")
    biscotto_alert_sent = Column(
        Boolean, default=False, comment="Prevents repeated biscotto alerts"
    )
    sharp_alert_sent = Column(Boolean, default=False, comment="Prevents repeated sharp alerts")

    # Score-delta deduplication
    highest_score_sent = Column(
        Float, default=0.0, comment="Highest score already alerted for this match"
    )
    last_alert_time = Column(
        DateTime, nullable=True, comment="When last alert was sent (temporal reset)"
    )

    # Investigation cooldown
    last_deep_dive_time = Column(
        DateTime, nullable=True, comment="When last full investigation was done"
    )

    # Post-match statistics (populated by settler)
    home_corners = Column(Integer, nullable=True, comment="Final home team corners")
    away_corners = Column(Integer, nullable=True, comment="Final away team corners")
    home_yellow_cards = Column(Integer, nullable=True, comment="Final home yellow cards")
    away_yellow_cards = Column(Integer, nullable=True, comment="Final away yellow cards")
    home_red_cards = Column(Integer, nullable=True, comment="Final home red cards")
    away_red_cards = Column(Integer, nullable=True, comment="Final away red cards")
    home_xg = Column(Float, nullable=True, comment="Home expected goals (xG)")
    away_xg = Column(Float, nullable=True, comment="Away expected goals (xG)")
    home_possession = Column(Float, nullable=True, comment="Home possession percentage")
    away_possession = Column(Float, nullable=True, comment="Away possession percentage")
    home_shots_on_target = Column(Integer, nullable=True, comment="Home shots on target")
    away_shots_on_target = Column(Integer, nullable=True, comment="Away shots on target")
    home_big_chances = Column(Integer, nullable=True, comment="Home big chances created")
    away_big_chances = Column(Integer, nullable=True, comment="Away big chances created")
    home_fouls = Column(Integer, nullable=True, comment="Home fouls committed")
    away_fouls = Column(Integer, nullable=True, comment="Away fouls committed")

    # Final result (populated after match ends)
    final_home_goals = Column(Integer, nullable=True, comment="Final home goals")
    final_away_goals = Column(Integer, nullable=True, comment="Final away goals")
    match_status = Column(String, nullable=True, comment="Match status: scheduled, live, finished")

    # Timestamps
    created_at = Column(
        DateTime, default=datetime.now(timezone.utc), comment="Record creation time"
    )
    last_updated = Column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
        comment="Last update time",
    )

    # Relationships
    news_logs = relationship("NewsLog", back_populates="match", cascade="all, delete-orphan")

    # Indexes for query optimization
    __table_args__ = (
        Index("idx_match_time_league", "start_time", "league"),
        Index("idx_match_teams", "home_team", "away_team"),
        Index("idx_match_status", "match_status"),
    )

    @property
    def sport_key(self) -> str:
        """Compatibility property for code expecting sport_key."""
        return self.league

    @property
    def commence_time(self) -> datetime:
        """Compatibility property for code expecting commence_time."""
        return self.start_time

    def get_odds_movement(self) -> dict[str, Any]:
        """
        Calculate odds movement percentages using shared intelligence.

        This method now uses the RadarOddsChecker for consistent analysis
        across all components. It provides backward compatibility by returning
        a simple dict with movement percentages.

        Returns:
            Dict with movement percentages for home/away/draw (negative = odds dropped)
        """
        try:
            from src.utils.radar_odds_check import get_radar_odds_checker

            checker = get_radar_odds_checker()
            movement = checker.check_match_movement(match_id=self.id)
            return movement.to_dict()
        except Exception:
            # Fallback to simple calculation if checker not available
            movement = {}

            if self.opening_home_odd and self.current_home_odd and self.opening_home_odd > 0:
                movement["home"] = (
                    (self.opening_home_odd - self.current_home_odd) / self.opening_home_odd
                ) * 100

            if self.opening_away_odd and self.current_away_odd and self.opening_away_odd > 0:
                movement["away"] = (
                    (self.opening_away_odd - self.current_away_odd) / self.opening_away_odd
                ) * 100

            if self.opening_draw_odd and self.current_draw_odd and self.opening_draw_odd > 0:
                movement["draw"] = (
                    (self.opening_draw_odd - self.current_draw_odd) / self.opening_draw_odd
                ) * 100

            return movement

    def is_upcoming(self) -> bool:
        """
        Check if match is in the future.

        VPS CRITICAL FIX: Handle both naive and timezone-aware datetimes correctly.
        The start_time is stored as naive datetime (UTC) in the database,
        so we need to make it timezone-aware before comparison.
        """
        if not self.start_time:
            return False

        # Make start_time timezone-aware for comparison
        # start_time is stored as naive datetime (UTC) in the database
        if self.start_time.tzinfo is None:
            start_time_utc = self.start_time.replace(tzinfo=timezone.utc)
        else:
            start_time_utc = self.start_time

        return start_time_utc > datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return f"<Match(id='{self.id}', {self.home_team} vs {self.away_team}, {self.start_time})>"


class NewsLog(Base):
    """
    NewsLog model for tracking analyzed news and betting alerts.

    Stores analysis results, betting recommendations, combo suggestions,
    and post-alert tracking for CLV (Closing Line Value) analysis.
    """

    __tablename__ = "news_logs"

    # Primary identification
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)

    # Content fields
    url = Column(String, nullable=True, comment="Source URL")
    summary = Column(Text, nullable=True, comment="Analysis summary/reasoning")
    score = Column(Integer, default=0, comment="Relevance score 0-10")
    category = Column(String, nullable=True, comment="Alert category (INJURY, TURNOVER, etc.)")
    affected_team = Column(String, nullable=True, comment="Team affected by the news")

    # Status tracking
    sent = Column(Boolean, default=False, comment="Whether alert was sent to Telegram")
    status = Column(String, nullable=True, comment="Alert status: pending, sent, no_bet, rejected")
    verification_status = Column(String, nullable=True, comment="Verification layer status")
    verification_reason = Column(String, nullable=True, comment="Reason for verification decision")

    # Combo bet fields
    combo_suggestion = Column(String, nullable=True, comment="e.g., 'Over 2.5 + BTTS'")
    combo_reasoning = Column(Text, nullable=True, comment="Why this combo was suggested")
    recommended_market = Column(String, nullable=True, comment="Primary market recommendation")

    # Driver classification
    primary_driver = Column(
        String,
        nullable=True,
        comment="Main signal: INJURY_INTEL, SHARP_MONEY, MATH_VALUE, CONTEXT_PLAY, CONTRARIAN",
    )

    # CLV Tracking (Closing Line Value) - V8.3 FIX: Proper historical odds capture
    odds_taken = Column(
        Float, nullable=True, comment="Odds when alert was sent (legacy - use odds_at_alert)"
    )
    closing_odds = Column(
        Float, nullable=True, comment="Closing odds for CLV analysis (legacy - use odds_at_kickoff)"
    )
    clv_percent = Column(Float, nullable=True, comment="Calculated CLV percentage")
    line_movement_explanation = Column(
        Text, nullable=True, comment="AI-generated explanation of line movement cause (via Tavily)"
    )

    # V8.3: Proper historical odds tracking for accurate ROI calculation
    odds_at_alert = Column(
        Float,
        nullable=True,
        comment="Actual odds when Telegram alert was sent (for ROI calculation)",
    )
    odds_at_kickoff = Column(
        Float, nullable=True, comment="Actual odds at match kickoff (for CLV analysis)"
    )
    alert_sent_at = Column(
        DateTime, nullable=True, comment="Timestamp when alert was sent to Telegram"
    )

    # Combo outcome tracking (Auto-Learning)
    combo_outcome = Column(String, nullable=True, comment="WIN/LOSS/PENDING for expansion")
    combo_explanation = Column(
        Text, nullable=True, comment="Detailed explanation of expansion result"
    )
    expansion_type = Column(
        String, nullable=True, comment="Type: over/under, gg/ng, corners, cards"
    )

    # V13.0: Primary bet outcome tracking (for CLV and ROI analysis)
    outcome = Column(String, nullable=True, comment="WIN/LOSS/PUSH/PENDING for primary bet")
    outcome_explanation = Column(
        Text, nullable=True, comment="Detailed explanation of primary bet result"
    )

    # V11.1: AI confidence (0-100) - Used by BettingQuant for market warning generation
    confidence = Column(Float, nullable=True, comment="AI confidence percentage 0-100")

    # Source tracking
    source = Column(String, default="web", comment="Source: web, telegram_ocr, telegram_channel")
    source_confidence = Column(Float, nullable=True, comment="Confidence in source reliability 0-1")

    # V8.1: Confidence breakdown (JSON)
    confidence_breakdown = Column(
        Text, nullable=True, comment='JSON: {"news_weight": 30, "odds_weight": 20, ...}'
    )

    # V8.2: Final Verifier tracking (JSON)
    final_verifier_result = Column(
        Text, nullable=True, comment="JSON with complete verifier result"
    )

    # V8.2: Feedback Loop tracking
    feedback_loop_used = Column(Boolean, default=False, comment="Whether feedback loop was applied")
    feedback_loop_iterations = Column(Integer, default=0, comment="Number of feedback iterations")
    modification_plan = Column(Text, nullable=True, comment="JSON with modification plan")
    modification_applied = Column(
        Boolean, default=False, comment="Whether modifications were applied"
    )
    original_score = Column(Integer, nullable=True, comment="Original score before modifications")
    original_market = Column(String, nullable=True, comment="Original market before modifications")

    # V9.5: Cross-Source Convergence Detection
    is_convergent = Column(
        Boolean,
        default=False,
        comment="True if signal confirmed by both Web (Brave) and Social (Nitter) sources",
    )
    convergence_sources = Column(
        Text,
        nullable=True,
        comment="JSON: {'web': {'type': 'Injury', 'confidence': 0.8}, 'social': {'type': 'Injury', 'confidence': 0.75}}",
    )

    # Timestamps
    # COVE FIX: Use timezone-aware datetime for consistency with Match model
    # datetime.utcnow() returns naive datetime, datetime.now(timezone.utc) returns timezone-aware
    timestamp = Column(DateTime, default=datetime.now(timezone.utc), comment="Analysis timestamp")
    created_at = Column(
        DateTime, default=datetime.now(timezone.utc), comment="Record creation time"
    )
    updated_at = Column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
        comment="Last update time",
    )

    # Relationships
    match = relationship("Match", back_populates="news_logs")

    # Indexes
    __table_args__ = (
        Index("idx_newslog_match_id", "match_id"),
        Index("idx_newslog_timestamp", "timestamp"),
        Index("idx_newslog_sent", "sent"),
        Index("idx_newslog_category", "category"),
    )

    def get_confidence_breakdown(self) -> dict[str, Any] | None:
        """Parse confidence_breakdown JSON field."""
        if self.confidence_breakdown:
            try:
                return json.loads(self.confidence_breakdown)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    def set_confidence_breakdown(self, breakdown: dict[str, Any]) -> None:
        """Serialize confidence_breakdown to JSON."""
        try:
            self.confidence_breakdown = json.dumps(breakdown)
        except (TypeError, ValueError):
            self.confidence_breakdown = None

    def get_final_verifier_result(self) -> dict[str, Any] | None:
        """Parse final_verifier_result JSON field."""
        if self.final_verifier_result:
            try:
                return json.loads(self.final_verifier_result)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    def set_final_verifier_result(self, result: dict[str, Any]) -> None:
        """Serialize final_verifier_result to JSON."""
        try:
            self.final_verifier_result = json.dumps(result)
        except (TypeError, ValueError):
            self.final_verifier_result = None

    def get_modification_plan(self) -> dict[str, Any] | None:
        """Parse modification_plan JSON field."""
        if self.modification_plan:
            try:
                return json.loads(self.modification_plan)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    def set_modification_plan(self, plan: dict[str, Any]) -> None:
        """Serialize modification_plan to JSON."""
        try:
            self.modification_plan = json.dumps(plan)
        except (TypeError, ValueError):
            self.modification_plan = None

    def get_convergence_sources(self) -> dict[str, Any] | None:
        """Parse convergence_sources JSON field."""
        if self.convergence_sources:
            try:
                return json.loads(self.convergence_sources)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    def set_convergence_sources(self, sources: dict[str, Any]) -> None:
        """Serialize convergence_sources to JSON."""
        try:
            self.convergence_sources = json.dumps(sources)
        except (TypeError, ValueError):
            self.convergence_sources = None

    def is_high_confidence(self) -> bool:
        """Check if this is a high confidence alert."""
        return self.score >= 8 if self.score else False

    def __repr__(self) -> str:
        return f"<NewsLog(id={self.id}, match_id='{self.match_id}', score={self.score}, sent={self.sent})>"


class TeamAlias(Base):
    """
    TeamAlias model for mapping API team names to search-friendly names.

    Also stores social media handles for insider intelligence gathering.
    """

    __tablename__ = "team_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_name = Column(
        String, unique=True, nullable=False, comment="Team name from API (The-Odds-API)"
    )
    search_name = Column(String, nullable=False, comment="Clean name for search queries")
    twitter_handle = Column(
        String, nullable=True, comment="Twitter/X handle (e.g., @GalatasaraySK)"
    )
    telegram_channel = Column(
        String, nullable=True, comment="Telegram channel (e.g., 'galatasaray')"
    )
    fotmob_id = Column(String, nullable=True, comment="FotMob team ID for data enrichment")
    country = Column(String, nullable=True, comment="Team country for regional context")
    league = Column(String, nullable=True, comment="Primary league for this team")

    # Indexes
    __table_args__ = (
        Index("idx_teamalias_api_name", "api_name"),
        Index("idx_teamalias_search_name", "search_name"),
    )

    def __repr__(self) -> str:
        return f"<TeamAlias(id={self.id}, api_name='{self.api_name}', search_name='{self.search_name}')>"


class ModificationHistory(Base):
    """
    ModificationHistory model for tracking all modifications applied by the intelligent feedback loop.

    Stores the complete history of modifications for learning and analysis.
    """

    __tablename__ = "modification_history"

    # Primary identification
    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(Integer, ForeignKey("news_logs.id", ondelete="CASCADE"), nullable=False)
    match_id = Column(String, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)

    # Modification details
    modification_type = Column(
        String,
        nullable=False,
        comment="Type: market_change, score_adjustment, data_correction, reasoning_update (combo_modification removed as dead code)",
    )
    original_value = Column(Text, nullable=True, comment="Original value before modification")
    suggested_value = Column(Text, nullable=True, comment="Suggested value after modification")
    reason = Column(Text, nullable=True, comment="Reason for the modification")
    priority = Column(String, nullable=False, comment="Priority: critical, high, medium, low")
    confidence = Column(Float, nullable=True, comment="Confidence level (0-1)")
    impact_assessment = Column(
        String, nullable=True, comment="Impact assessment: HIGH, MEDIUM, LOW"
    )

    # Execution details
    applied = Column(Boolean, default=False, comment="Whether modification was applied")
    success = Column(Boolean, nullable=True, comment="Whether modification was successful")
    error_message = Column(Text, nullable=True, comment="Error message if failed")

    # Context
    verification_context = Column(Text, nullable=True, comment="JSON with verification context")
    component_communications = Column(
        Text, nullable=True, comment="JSON with component communication results"
    )

    # Timestamps
    # COVE FIX: Use timezone-aware datetime for consistency
    created_at = Column(
        DateTime, default=datetime.now(timezone.utc), comment="When modification was suggested"
    )
    applied_at = Column(DateTime, nullable=True, comment="When modification was applied")

    # Relationships
    alert = relationship("NewsLog", backref="modifications")
    match = relationship("Match", backref="modifications")

    # Indexes
    __table_args__ = (
        Index("idx_modification_alert_id", "alert_id"),
        Index("idx_modification_match_id", "match_id"),
        Index("idx_modification_type", "modification_type"),
        Index("idx_modification_applied", "applied"),
    )

    def __repr__(self) -> str:
        return f"<ModificationHistory(id={self.id}, type='{self.modification_type}', applied={self.applied})>"


class ManualReview(Base):
    """
    ManualReview model for logging alerts that require manual review.

    Stores alerts that need human intervention for complex modifications.
    """

    __tablename__ = "manual_reviews"

    # Primary identification
    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(Integer, ForeignKey("news_logs.id", ondelete="CASCADE"), nullable=False)
    match_id = Column(String, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)

    # Review details
    modification_plan = Column(Text, nullable=False, comment="JSON with modification plan")
    original_alert_data = Column(Text, nullable=True, comment="JSON with original alert data")
    context_data = Column(Text, nullable=True, comment="JSON with context data")

    # Status tracking
    status = Column(
        String,
        default="pending_review",
        comment="Status: pending_review, reviewed, approved, rejected",
    )
    reviewed_by = Column(String, nullable=True, comment="Username of reviewer")
    review_timestamp = Column(DateTime, nullable=True, comment="When review was completed")
    review_decision = Column(String, nullable=True, comment="Decision: approve, reject, modify")
    review_notes = Column(Text, nullable=True, comment="Notes from reviewer")

    # Risk assessment
    risk_level = Column(String, nullable=False, comment="Risk level: LOW, MEDIUM, HIGH")
    modification_count = Column(Integer, nullable=False, comment="Number of modifications needed")

    # Timestamps
    # COVE FIX: Use timezone-aware datetime for consistency
    created_at = Column(
        DateTime, default=datetime.now(timezone.utc), comment="When review was queued"
    )

    # Relationships
    alert = relationship("NewsLog", backref="manual_reviews")
    match = relationship("Match", backref="manual_reviews")

    # Indexes
    __table_args__ = (
        Index("idx_manual_review_alert_id", "alert_id"),
        Index("idx_manual_review_match_id", "match_id"),
        Index("idx_manual_review_status", "status"),
        Index("idx_manual_review_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ManualReview(id={self.id}, alert_id={self.alert_id}, status='{self.status}')>"


class LearningPattern(Base):
    """
    LearningPattern model for storing learned patterns from modification history.

    Enables the system to learn from past modifications and improve decision making.
    """

    __tablename__ = "learning_patterns"

    # Primary identification
    id = Column(Integer, primary_key=True, autoincrement=True)
    pattern_key = Column(String, unique=True, nullable=False, comment="Unique pattern identifier")

    # Pattern data
    modification_count = Column(
        Integer, nullable=False, comment="Number of modifications in pattern"
    )
    confidence_level = Column(String, nullable=False, comment="Confidence level: HIGH, MEDIUM, LOW")
    discrepancy_count = Column(Integer, nullable=False, comment="Number of data discrepancies")

    # Decision tracking
    total_occurrences = Column(Integer, default=0, comment="Total times pattern occurred")
    auto_apply_count = Column(Integer, default=0, comment="Times AUTO_APPLY was chosen")
    manual_review_count = Column(Integer, default=0, comment="Times MANUAL_REVIEW was chosen")
    ignore_count = Column(Integer, default=0, comment="Times IGNORE was chosen")

    # Success metrics
    success_rate = Column(Float, nullable=True, comment="Success rate when applied")
    # COVE FIX: Use timezone-aware datetime for consistency
    last_updated = Column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
        comment="Last update time",
    )

    # Indexes
    __table_args__ = (
        Index("idx_learning_pattern_key", "pattern_key"),
        Index("idx_learning_pattern_confidence", "confidence_level"),
    )

    def __repr__(self) -> str:
        return f"<LearningPattern(id={self.id}, key='{self.pattern_key}', occurrences={self.total_occurrences})>"


# ============================================
# DATABASE SETUP AND CONNECTION MANAGEMENT
# ============================================

import os
import time
from contextlib import contextmanager
from functools import wraps

# Database configuration
DB_DIR = os.getenv("EARLYBIRD_DATA_DIR", "data")
DB_FILE = os.getenv("EARLYBIRD_DB_FILE", "earlybird.db")

# Ensure data directory exists
os.makedirs(DB_DIR, exist_ok=True)

DB_PATH = f"sqlite:///{os.path.join(DB_DIR, DB_FILE)}"

# SQLite connection configuration for VPS/production use
# - check_same_thread=False: Allow multi-threaded access (required for async operations)
# - timeout=60: Wait up to 60s for lock release
# - pool_pre_ping: Verify connections before use to handle stale connections
# - pool_size=5: Allow multiple concurrent connections
# - max_overflow=5: Allow up to 10 total connections under load
# - pool_recycle=7200: Recycle connections after 2 hours to prevent memory leaks (VPS FIX: increased from 3600)
engine = create_engine(
    DB_PATH,
    connect_args={"check_same_thread": False, "timeout": 60},
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_timeout=60,
    pool_recycle=7200,
    echo=False,  # Set to True for SQL debugging
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Configure SQLite pragmas for optimal performance and concurrency.

    - WAL mode: Write-Ahead Logging for concurrent reads/writes
    - busy_timeout: Wait instead of failing on lock
    - synchronous=NORMAL: Balance between speed and safety
    - foreign_keys: Enforce referential integrity
    - cache_size: 64MB page cache for better performance
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=60000")  # 60 seconds
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
        cursor.execute("PRAGMA temp_store=memory")  # Store temp tables in memory
        cursor.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O
    finally:
        cursor.close()


def init_db() -> None:
    """
    Initialize the database by creating all tables.
    Safe to call multiple times (idempotent).
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info(f"Database initialized successfully at {DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


@contextmanager
def get_db_session(max_retries: int = 3, retry_delay: float = 1.0):
    """
    Context manager for database sessions with automatic retry on lock.

    Usage:
        with get_db_session() as db:
            matches = db.query(Match).all()
            # Auto-commits on success, auto-rollbacks on error

    Args:
        max_retries: Number of retries on database lock
        retry_delay: Base delay between retries (exponential backoff)

    Yields:
        SQLAlchemy session object
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
            if "database is locked" in error_str or "locked" in error_str:
                last_error = e
                wait_time = retry_delay * (2**attempt)  # Exponential backoff
                logger.warning(
                    f"⚠️ DB locked (attempt {attempt + 1}/{max_retries}), waiting {wait_time:.1f}s..."
                )
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
    """
    Legacy generator for FastAPI-style dependency injection.

    Usage:
        db = next(get_db())
        try:
            # use db
        finally:
            db.close()
    """
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
            with get_db_session() as db:
                # ... db operations
                return result
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
                    if "database is locked" in error_str or "locked" in error_str:
                        last_error = e
                        wait_time = retry_delay * (2**attempt)
                        logger.warning(
                            f"⚠️ DB locked in {func.__name__} (attempt {attempt + 1}/{max_retries}), waiting {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)
                        continue
                    raise
            if last_error:
                raise last_error

        return wrapper

    return decorator


# ============================================
# UTILITY FUNCTIONS
# ============================================


def get_db_stats() -> dict[str, Any]:
    """Get database statistics for monitoring."""
    try:
        with get_db_session() as db:
            match_count = db.query(Match).count()
            newslog_count = db.query(NewsLog).count()
            alias_count = db.query(TeamAlias).count()

            return {
                "matches": match_count,
                "news_logs": newslog_count,
                "team_aliases": alias_count,
                "db_path": DB_PATH,
                "status": "healthy",
            }
    except Exception as e:
        logger.error(f"Failed to get DB stats: {e}")
        return {
            "matches": 0,
            "news_logs": 0,
            "team_aliases": 0,
            "db_path": DB_PATH,
            "status": f"error: {str(e)}",
        }


def vacuum_db() -> None:
    """Run VACUUM to optimize database file size."""
    try:
        with engine.connect() as conn:
            conn.execute("VACUUM")
        logger.info("Database vacuum completed")
    except Exception as e:
        logger.error(f"Database vacuum failed: {e}")


# ============================================
# MODULE EXPORTS
# ============================================

__all__ = [
    "Base",
    "Match",
    "NewsLog",
    "TeamAlias",
    "engine",
    "SessionLocal",
    "init_db",
    "get_db_session",
    "get_db",
    "with_db_retry",
    "get_db_stats",
    "vacuum_db",
    "DB_PATH",
]
