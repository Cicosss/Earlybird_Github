"""
Budget Persistence Module - V1.1

Provides persistent storage for budget data using SQLite.
Ensures thread-safe operations and handles monthly/daily resets.

V1.1 Changes:
- Fixed database connection handling to use context managers
- Fixed path handling to use relative paths instead of os.getcwd()

Created: 2026-03-08
Purpose: Resolve budget data loss on bot restart
"""

import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BudgetPersistence:
    """
    Thread-safe persistent storage for budget data.

    Stores budget usage, component usage, and reset timestamps in SQLite.
    Handles monthly/daily resets automatically.
    """

    def __init__(self, db_path: str | None = None):
        """
        Initialize BudgetPersistence.

        Args:
            db_path: Path to SQLite database (default: data/budget_persistence.db)
        """
        if db_path is None:
            # Default path: data/budget_persistence.db (relative to project root)
            # Use pathlib for reliable relative path handling
            db_path = str(Path(__file__).parent.parent / "data" / "budget_persistence.db")

        self._db_path = db_path
        self._lock = threading.Lock()

        # Ensure data directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # Initialize database
        self._init_db()

        logger.info(f"💾 BudgetPersistence initialized: {db_path}")

    @contextmanager
    def _get_connection(self):
        """
        Context manager for SQLite connections.

        Ensures connections are properly closed even if errors occur.
        """
        conn = None
        try:
            conn = sqlite3.connect(self._db_path)
            yield conn
            conn.commit()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    def _init_db(self) -> None:
        """Initialize SQLite database with required tables."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Create budget_data table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS budget_data (
                        provider_name TEXT PRIMARY KEY,
                        monthly_used INTEGER NOT NULL DEFAULT 0,
                        daily_used INTEGER NOT NULL DEFAULT 0,
                        monthly_limit INTEGER NOT NULL DEFAULT 0,
                        component_usage TEXT NOT NULL DEFAULT '{}',
                        last_reset_day INTEGER,
                        last_reset_month INTEGER,
                        last_updated TEXT NOT NULL
                    )
                """)

                # Create budget_history table for reporting
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS budget_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider_name TEXT NOT NULL,
                        monthly_used INTEGER NOT NULL,
                        daily_used INTEGER NOT NULL,
                        usage_percentage REAL NOT NULL,
                        is_degraded INTEGER NOT NULL DEFAULT 0,
                        is_disabled INTEGER NOT NULL DEFAULT 0,
                        component_usage TEXT NOT NULL DEFAULT '{}',
                        timestamp TEXT NOT NULL
                    )
                """)

                # Create index for faster queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_budget_history_timestamp
                    ON budget_history(timestamp)
                """)

    def save_budget(
        self,
        provider_name: str,
        monthly_used: int,
        daily_used: int,
        monthly_limit: int,
        component_usage: dict[str, int],
        last_reset_day: int | None = None,
        last_reset_month: int | None = None,
    ) -> None:
        """
        Save budget data to database.

        Args:
            provider_name: Name of the provider
            monthly_used: Monthly API calls used
            daily_used: Daily API calls used
            monthly_limit: Monthly API call limit
            component_usage: Per-component usage breakdown
            last_reset_day: Last daily reset day
            last_reset_month: Last monthly reset month
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Serialize component_usage to JSON
                    component_usage_json = json.dumps(component_usage)

                    # Get current timestamp
                    timestamp = datetime.now(timezone.utc).isoformat()

                    # Upsert budget data
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO budget_data
                        (provider_name, monthly_used, daily_used, monthly_limit,
                         component_usage, last_reset_day, last_reset_month, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            provider_name,
                            monthly_used,
                            daily_used,
                            monthly_limit,
                            component_usage_json,
                            last_reset_day,
                            last_reset_month,
                            timestamp,
                        ),
                    )

                    logger.debug(
                        f"💾 Budget saved for {provider_name}: {monthly_used}/{monthly_limit}"
                    )

            except Exception as e:
                logger.error(f"🚨 Failed to save budget for {provider_name}: {e}")
                raise

    def load_budget(self, provider_name: str) -> dict[str, Any] | None:
        """
        Load budget data from database.

        Args:
            provider_name: Name of the provider

        Returns:
            Dictionary with budget data or None if not found
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    cursor.execute(
                        """
                        SELECT monthly_used, daily_used, monthly_limit, component_usage,
                               last_reset_day, last_reset_month, last_updated
                        FROM budget_data
                        WHERE provider_name = ?
                    """,
                        (provider_name,),
                    )

                    row = cursor.fetchone()

                    if row is None:
                        logger.debug(f"💾 No budget data found for {provider_name}")
                        return None

                    # Deserialize component_usage from JSON
                    component_usage = json.loads(row[3])

                    return {
                        "monthly_used": row[0],
                        "daily_used": row[1],
                        "monthly_limit": row[2],
                        "component_usage": component_usage,
                        "last_reset_day": row[4],
                        "last_reset_month": row[5],
                        "last_updated": row[6],
                    }

            except Exception as e:
                logger.error(f"🚨 Failed to load budget for {provider_name}: {e}")
                return None

    def save_budget_history(
        self,
        provider_name: str,
        monthly_used: int,
        daily_used: int,
        usage_percentage: float,
        is_degraded: bool,
        is_disabled: bool,
        component_usage: dict[str, int],
    ) -> None:
        """
        Save budget history entry for reporting.

        Args:
            provider_name: Name of the provider
            monthly_used: Monthly API calls used
            daily_used: Daily API calls used
            usage_percentage: Usage as percentage (0-100)
            is_degraded: Whether provider is in degraded mode
            is_disabled: Whether provider is in disabled mode
            component_usage: Per-component usage breakdown
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Serialize component_usage to JSON
                    component_usage_json = json.dumps(component_usage)

                    # Get current timestamp
                    timestamp = datetime.now(timezone.utc).isoformat()

                    # Insert budget history entry
                    cursor.execute(
                        """
                        INSERT INTO budget_history
                        (provider_name, monthly_used, daily_used, usage_percentage,
                         is_degraded, is_disabled, component_usage, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            provider_name,
                            monthly_used,
                            daily_used,
                            usage_percentage,
                            1 if is_degraded else 0,
                            1 if is_disabled else 0,
                            component_usage_json,
                            timestamp,
                        ),
                    )

                    logger.debug(f"💾 Budget history saved for {provider_name}")

            except Exception as e:
                logger.error(f"🚨 Failed to save budget history for {provider_name}: {e}")
                # Don't raise - history saving is non-critical

    def get_budget_history(
        self,
        provider_name: str,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        """
        Get budget history for a provider.

        Args:
            provider_name: Name of the provider
            hours: Number of hours of history to retrieve

        Returns:
            List of budget history entries
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Calculate timestamp threshold
                    threshold = datetime.now(timezone.utc) - timedelta(hours=hours)
                    threshold_iso = threshold.isoformat()

                    cursor.execute(
                        """
                        SELECT monthly_used, daily_used, usage_percentage,
                               is_degraded, is_disabled, component_usage, timestamp
                        FROM budget_history
                        WHERE provider_name = ? AND timestamp >= ?
                        ORDER BY timestamp DESC
                    """,
                        (provider_name, threshold_iso),
                    )

                    rows = cursor.fetchall()

                    history: list[dict[str, Any]] = []
                    for row in rows:
                        # Deserialize component_usage from JSON
                        component_usage = json.loads(row[5])

                        history.append(
                            {
                                "monthly_used": row[0],
                                "daily_used": row[1],
                                "usage_percentage": row[2],
                                "is_degraded": bool(row[3]),
                                "is_disabled": bool(row[4]),
                                "component_usage": component_usage,
                                "timestamp": row[6],
                            }
                        )

                    return history

            except Exception as e:
                logger.error(f"🚨 Failed to get budget history for {provider_name}: {e}")
                return []

    def delete_old_history(self, days: int = 30) -> None:
        """
        Delete old budget history entries.

        Args:
            days: Number of days of history to keep
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Calculate timestamp threshold
                    threshold = datetime.now(timezone.utc) - timedelta(days=days)
                    threshold_iso = threshold.isoformat()

                    # Delete old entries
                    cursor.execute(
                        """
                        DELETE FROM budget_history
                        WHERE timestamp < ?
                    """,
                        (threshold_iso,),
                    )

                    deleted_count = cursor.rowcount

                    if deleted_count > 0:
                        logger.info(f"💾 Deleted {deleted_count} old budget history entries")

            except Exception as e:
                logger.error(f"🚨 Failed to delete old budget history: {e}")
                # Don't raise - cleanup is non-critical

    def clear_budget(self, provider_name: str) -> None:
        """
        Clear budget data for a provider.

        Args:
            provider_name: Name of the provider
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    cursor.execute(
                        """
                        DELETE FROM budget_data
                        WHERE provider_name = ?
                    """,
                        (provider_name,),
                    )

                    logger.info(f"💾 Budget data cleared for {provider_name}")

            except Exception as e:
                logger.error(f"🚨 Failed to clear budget for {provider_name}: {e}")
                raise
