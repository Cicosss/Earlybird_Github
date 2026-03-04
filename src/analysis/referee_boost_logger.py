"""
Referee Boost Logging Module

Provides structured logging for referee boost events, including:
- Boost applications (CASE1: NO BET → Over 3.5 Cards)
- Upgrade applications (CASE 2: Over 3.5 → Over 4.5)
- Influence on other markets (Goals, Corners, Winner)
- Referee statistics used in decisions
- Performance metrics

Usage:
    from src.analysis.referee_boost_logger import get_referee_boost_logger

    logger = get_referee_boost_logger()
    logger.log_boost_applied(
        referee_name="Michael Oliver",
        cards_per_game=5.2,
        original_verdict="NO BET",
        new_verdict="BET",
        recommended_market="Over 3.5 Cards",
        reason="Strict referee + Derby/High Intensity"
    )
"""

import json
import logging
import threading
from datetime import datetime, timezone
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

# Log file location
LOG_DIR = Path("logs")
BOOST_LOG_FILE = LOG_DIR / "referee_boost.log"


class BoostType(Enum):
    """Types of referee boost actions."""

    BOOST_NO_BET_TO_BET = "boost_no_bet_to_bet"  # CASE 1
    UPGRADE_CARDS_LINE = "upgrade_cards_line"  # CASE 2
    INFLUENCE_GOALS = "influence_goals"  # V9.1
    INFLUENCE_CORNERS = "influence_corners"  # V9.1
    INFLUENCE_WINNER = "influence_winner"  # V9.1
    VETO_CARDS = "veto_cards"  # Lenient referee veto


class RefereeBoostLogger:
    """
    Logger for referee boost events.

    Provides structured logging with JSON format for easy parsing and analysis.
    """

    def __init__(self, log_file: Path = BOOST_LOG_FILE):
        self.log_file = log_file
        self._lock = threading.Lock()  # Thread safety for logging operations
        self._setup_logger()

    def _setup_logger(self):
        """Setup logger with file and console handlers."""
        self.logger = logging.getLogger("referee_boost")
        self.logger.setLevel(logging.INFO)

        # Clear existing handlers
        self.logger.handlers.clear()

        # Create log directory if it doesn't exist
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # File handler with JSON format and rotation (5MB max, 3 backups = 15MB total max)
        file_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=5_000_000,  # 5MB max file size
            backupCount=3,  # Keep 3 backup files
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(file_handler)

        # Console handler with human-readable format
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        self.logger.addHandler(console_handler)

    def _format_log_entry(self, entry: Dict[str, Any]) -> str:
        """Format log entry as JSON."""
        return json.dumps(entry, ensure_ascii=False)

    def log_boost_applied(
        self,
        referee_name: str,
        cards_per_game: float,
        strictness: str,
        original_verdict: str,
        new_verdict: str,
        recommended_market: str,
        reason: str,
        match_id: Optional[str] = None,
        home_team: Optional[str] = None,
        away_team: Optional[str] = None,
        league: Optional[str] = None,
        confidence_before: Optional[float] = None,
        confidence_after: Optional[float] = None,
        tactical_context: Optional[str] = None,
    ):
        """
        Log a boost application (CASE 1: NO BET → Over 3.5 Cards).

        Args:
            referee_name: Name of referee
            cards_per_game: Average cards per game
            strictness: Strictness classification
            original_verdict: Original verdict before boost
            new_verdict: New verdict after boost
            recommended_market: Recommended market
            reason: Reason for boost
            match_id: Optional match ID
            home_team: Optional home team name
            away_team: Optional away team name
            league: Optional league name
            confidence_before: Confidence before boost
            confidence_after: Confidence after boost
            tactical_context: Tactical context (derby, rivalry, etc.)
        """
        with self._lock:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": "boost_applied",
                "boost_type": BoostType.BOOST_NO_BET_TO_BET.value,
                "referee": {
                    "name": referee_name,
                    "cards_per_game": cards_per_game,
                    "strictness": strictness,
                },
                "match": {
                    "match_id": match_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "league": league,
                },
                "decision": {
                    "original_verdict": original_verdict,
                    "new_verdict": new_verdict,
                    "recommended_market": recommended_market,
                    "confidence_before": confidence_before,
                    "confidence_after": confidence_after,
                    "confidence_delta": (confidence_after - confidence_before)
                    if confidence_before and confidence_after
                    else None,
                },
                "context": {"reason": reason, "tactical_context": tactical_context},
            }

            self.logger.info(self._format_log_entry(entry))

    def log_upgrade_applied(
        self,
        referee_name: str,
        cards_per_game: float,
        strictness: str,
        original_market: str,
        new_market: str,
        reason: str,
        match_id: Optional[str] = None,
        home_team: Optional[str] = None,
        away_team: Optional[str] = None,
        league: Optional[str] = None,
        confidence_before: Optional[float] = None,
        confidence_after: Optional[float] = None,
    ):
        """
        Log a cards line upgrade (CASE 2: Over 3.5 → Over 4.5) (thread-safe).

        Args:
            referee_name: Name of referee
            cards_per_game: Average cards per game
            strictness: Strictness classification
            original_market: Original market line
            new_market: New market line
            reason: Reason for upgrade
            match_id: Optional match ID
            home_team: Optional home team name
            away_team: Optional away team name
            league: Optional league name
            confidence_before: Confidence before upgrade
            confidence_after: Confidence after upgrade
        """
        with self._lock:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": "upgrade_applied",
                "boost_type": BoostType.UPGRADE_CARDS_LINE.value,
                "referee": {
                    "name": referee_name,
                    "cards_per_game": cards_per_game,
                    "strictness": strictness,
                },
                "match": {
                    "match_id": match_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "league": league,
                },
                "decision": {
                    "original_market": original_market,
                    "new_market": new_market,
                    "confidence_before": confidence_before,
                    "confidence_after": confidence_after,
                    "confidence_delta": (confidence_after - confidence_before)
                    if confidence_before and confidence_after
                    else None,
                },
                "context": {"reason": reason},
            }

            self.logger.info(self._format_log_entry(entry))

    def log_influence_applied(
        self,
        referee_name: str,
        cards_per_game: float,
        strictness: str,
        market_type: str,
        influence_type: BoostType,
        original_confidence: float,
        new_confidence: float,
        reason: str,
        match_id: Optional[str] = None,
        home_team: Optional[str] = None,
        away_team: Optional[str] = None,
        league: Optional[str] = None,
    ):
        """
        Log referee influence on other markets (Goals, Corners, Winner) (thread-safe).

        Args:
            referee_name: Name of referee
            cards_per_game: Average cards per game
            strictness: Strictness classification
            market_type: Type of market (Goals, Corners, Winner)
            influence_type: Type of influence
            original_confidence: Confidence before influence
            new_confidence: Confidence after influence
            reason: Reason for influence
            match_id: Optional match ID
            home_team: Optional home team name
            away_team: Optional away team name
            league: Optional league name
        """
        with self._lock:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": "influence_applied",
                "boost_type": influence_type.value,
                "referee": {
                    "name": referee_name,
                    "cards_per_game": cards_per_game,
                    "strictness": strictness,
                },
                "match": {
                    "match_id": match_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "league": league,
                },
                "decision": {
                    "market_type": market_type,
                    "confidence_before": original_confidence,
                    "confidence_after": new_confidence,
                    "confidence_delta": new_confidence - original_confidence,
                },
                "context": {"reason": reason},
            }

            self.logger.info(self._format_log_entry(entry))

    def log_veto_applied(
        self,
        referee_name: str,
        cards_per_game: float,
        strictness: str,
        recommended_market: str,
        reason: str,
        match_id: Optional[str] = None,
        home_team: Optional[str] = None,
        away_team: Optional[str] = None,
        league: Optional[str] = None,
    ):
        """
        Log a veto applied by lenient referee (thread-safe).

        Args:
            referee_name: Name of referee
            cards_per_game: Average cards per game
            strictness: Strictness classification
            recommended_market: Market being vetoed
            reason: Reason for veto
            match_id: Optional match ID
            home_team: Optional home team name
            away_team: Optional away team name
            league: Optional league name
        """
        with self._lock:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": "veto_applied",
                "boost_type": BoostType.VETO_CARDS.value,
                "referee": {
                    "name": referee_name,
                    "cards_per_game": cards_per_game,
                    "strictness": strictness,
                },
                "match": {
                    "match_id": match_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "league": league,
                },
                "decision": {"vetoed_market": recommended_market},
                "context": {"reason": reason},
            }

            self.logger.warning(self._format_log_entry(entry))

    def log_referee_stats_used(
        self,
        referee_name: str,
        cards_per_game: float,
        strictness: str,
        matches_officiated: int,
        source: str = "cache",
        match_id: Optional[str] = None,
        league: Optional[str] = None,
    ):
        """
        Log referee statistics used in analysis (thread-safe).

        Args:
            referee_name: Name of referee
            cards_per_game: Average cards per game
            strictness: Strictness classification
            matches_officiated: Number of matches officiated
            source: Source of stats (cache, api, etc.)
            match_id: Optional match ID
            league: Optional league name
        """
        with self._lock:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": "referee_stats_used",
                "referee": {
                    "name": referee_name,
                    "cards_per_game": cards_per_game,
                    "strictness": strictness,
                    "matches_officiated": matches_officiated,
                },
                "match": {"match_id": match_id, "league": league},
                "context": {"source": source},
            }

            self.logger.debug(self._format_log_entry(entry))

    def log_cache_miss(self, referee_name: str, reason: str = "not_in_cache"):
        """
        Log a cache miss event (thread-safe).

        Args:
            referee_name: Name of referee
            reason: Reason for cache miss
        """
        with self._lock:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": "cache_miss",
                "referee": {"name": referee_name},
                "context": {"reason": reason},
            }

            self.logger.debug(self._format_log_entry(entry))

    def log_error(
        self,
        error_type: str,
        error_message: str,
        referee_name: Optional[str] = None,
        match_id: Optional[str] = None,
    ):
        """
        Log an error in referee boost logic (thread-safe).

        Args:
            error_type: Type of error
            error_message: Error message
            referee_name: Optional referee name
            match_id: Optional match ID
        """
        with self._lock:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": "error",
                "error": {"type": error_type, "message": error_message},
                "referee": {"name": referee_name} if referee_name else None,
                "match": {"match_id": match_id} if match_id else None,
            }

            self.logger.error(self._format_log_entry(entry))


# Global logger instance
_referee_boost_logger = None
_referee_boost_logger_lock = threading.Lock()


def get_referee_boost_logger() -> RefereeBoostLogger:
    """
    Get global referee boost logger instance.

    Returns:
        RefereeBoostLogger instance
    """
    global _referee_boost_logger
    with _referee_boost_logger_lock:
        if _referee_boost_logger is None:
            _referee_boost_logger = RefereeBoostLogger()
    return _referee_boost_logger
