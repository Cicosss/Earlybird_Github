"""
Daily CSV Report Generator for EarlyBird

Exports human-readable betting history with team names and leagues.
V2.0: Production-ready with comprehensive error handling
"""

import csv
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from sqlalchemy.orm import Session

# Database imports with fallback
try:
    from src.database.models import Match, NewsLog, SessionLocal
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    Match = None
    NewsLog = None
    SessionLocal = None

logger = logging.getLogger(__name__)

# ============================================
# CONSTANTS
# ============================================
DEFAULT_OUTPUT_DIR = "temp"
DEFAULT_DAYS = 1
MATCH_FINISHED_THRESHOLD_SECONDS = 7200  # 2 hours

# CSV Headers (Italian)
CSV_HEADERS = [
    'Lega',
    'Partita',
    'Data/Ora',
    'Pronostico',
    'Mercato',
    'AI_Confidence',
    'Motivo',
    'Quote_1X2',
    'Risultato',
    'Esito'
]


# ============================================
# HELPER FUNCTIONS
# ============================================

def _ensure_output_dir(output_dir: str) -> Path:
    """Ensure output directory exists and return Path object."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _format_match_string(match: Any) -> str:
    """Format match string from match object."""
    home_team = getattr(match, 'home_team', 'Unknown')
    away_team = getattr(match, 'away_team', 'Unknown')
    return f"{home_team} vs {away_team}"


def _format_match_time(match: Any) -> str:
    """Format match time for display."""
    start_time = getattr(match, 'start_time', None)
    if not start_time:
        return "N/A"
    try:
        return start_time.strftime("%d/%m %H:%M")
    except Exception:
        return "N/A"


def _format_odds(match: Any) -> str:
    """Format odds string for display."""
    home_odd = getattr(match, 'current_home_odd', None)
    draw_odd = getattr(match, 'current_draw_odd', None)
    away_odd = getattr(match, 'current_away_odd', None)

    if home_odd is None or draw_odd is None or away_odd is None:
        return ""

    try:
        return f"1:{home_odd:.2f} X:{draw_odd:.2f} 2:{away_odd:.2f}"
    except (TypeError, ValueError):
        return ""


def _is_match_finished(match: Any, now: datetime) -> bool:
    """Check if match should be considered finished (started > 2 hours ago)."""
    start_time = getattr(match, 'start_time', None)
    if not start_time:
        return False

    try:
        # Handle timezone-aware and naive datetimes
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)

        elapsed = (now - start_time).total_seconds()
        return elapsed > MATCH_FINISHED_THRESHOLD_SECONDS
    except Exception:
        return False


def _get_pronostico(log: Any) -> str:
    """Get pronostico from log, preferring combo_suggestion."""
    combo = getattr(log, 'combo_suggestion', None)
    market = getattr(log, 'recommended_market', None)
    return combo or market or "N/A"


# ============================================
# MAIN EXPORT FUNCTION
# ============================================

def export_bet_history(days: int = DEFAULT_DAYS, output_dir: str = DEFAULT_OUTPUT_DIR) -> Optional[str]:
    """
    Export betting history to a human-readable CSV file.

    Args:
        days: Number of days to look back (default: 1 for daily report)
        output_dir: Directory to save the CSV file

    Returns:
        Path to the generated CSV file, or None if no data/error
    """
    if not DB_AVAILABLE:
        logger.error("Database models not available. Cannot export bet history.")
        return None

    db: Optional[Session] = None
    try:
        db = SessionLocal()

        # Ensure output directory exists
        output_path = _ensure_output_dir(output_dir)

        # Calculate date range
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        # Query NewsLogs with JOIN to Match for human-readable data
        results = db.query(NewsLog).join(
            Match, NewsLog.match_id == Match.id
        ).filter(
            NewsLog.timestamp >= cutoff,
            NewsLog.sent == True  # Only sent alerts
        ).order_by(
            NewsLog.timestamp.desc()
        ).all()

        if not results:
            logger.info("No betting history found for the specified period")
            return None

        # Generate filename with date
        date_str = now.strftime("%Y-%m-%d")
        filename = f"EarlyBird_Report_{date_str}.csv"
        filepath = output_path / filename

        # Write CSV with Italian headers (utf-8-sig for Excel compatibility)
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)

            # Header row
            writer.writerow(CSV_HEADERS)

            # Data rows
            records_written = 0
            for log in results:
                # Safety: Handle orphan logs (match deleted)
                match = getattr(log, 'match', None)
                if not match:
                    logger.warning(f"Orphan NewsLog found: {getattr(log, 'id', 'unknown')}")
                    continue

                # Format data
                partita = _format_match_string(match)
                match_time = _format_match_time(match)
                odds_str = _format_odds(match)
                pronostico = _get_pronostico(log)

                # Result and Outcome (Pending - settlement done separately)
                is_finished = _is_match_finished(match, now)
                risultato = "Pending" if not is_finished else "Da verificare"
                esito = "PENDING"

                # Write row
                writer.writerow([
                    getattr(match, 'league', None) or "N/A",
                    partita,
                    match_time,
                    pronostico,
                    getattr(log, 'recommended_market', None) or "N/A",
                    f"{getattr(log, 'score', 0)}/10" if getattr(log, 'score', None) else "N/A",
                    getattr(log, 'primary_driver', None) or "N/A",
                    odds_str,
                    risultato,
                    esito
                ])
                records_written += 1

        logger.info(f"Report generated: {filepath} ({records_written} records)")
        return str(filepath)

    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
        return None

    finally:
        if db:
            try:
                db.close()
            except Exception as e:
                logger.debug(f"Error closing database connection: {e}")


# ============================================
# DAILY SUMMARY FUNCTION
# ============================================

def get_daily_summary() -> Dict[str, Any]:
    """
    Get a summary of today's betting activity for the report caption.

    Returns:
        Dict with total_alerts, leagues_covered, top_score
    """
    if not DB_AVAILABLE:
        logger.error("Database models not available. Cannot get daily summary.")
        return {'total_alerts': 0, 'leagues_covered': 0, 'top_score': 0}

    db: Optional[Session] = None
    try:
        db = SessionLocal()

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Count alerts sent today
        total_alerts = db.query(NewsLog).filter(
            NewsLog.timestamp >= today_start,
            NewsLog.sent == True
        ).count()

        # Get unique leagues
        leagues = db.query(Match.league).join(
            NewsLog, NewsLog.match_id == Match.id
        ).filter(
            NewsLog.timestamp >= today_start,
            NewsLog.sent == True
        ).distinct().all()

        # Get top score
        top_score_result = db.query(NewsLog.score).filter(
            NewsLog.timestamp >= today_start,
            NewsLog.sent == True
        ).order_by(NewsLog.score.desc()).first()

        return {
            'total_alerts': total_alerts,
            'leagues_covered': len(leagues),
            'top_score': top_score_result[0] if top_score_result else 0
        }

    except Exception as e:
        logger.error(f"Error getting daily summary: {e}")
        return {'total_alerts': 0, 'leagues_covered': 0, 'top_score': 0}

    finally:
        if db:
            try:
                db.close()
            except Exception as e:
                logger.debug(f"Error closing database connection: {e}")


# ============================================
# BATCH REPORT FUNCTION
# ============================================

def export_bet_history_batch(
    days_list: List[int],
    output_dir: str = DEFAULT_OUTPUT_DIR
) -> Dict[int, Optional[str]]:
    """
    Export betting history for multiple time periods.

    Args:
        days_list: List of day periods to export (e.g., [1, 7, 30])
        output_dir: Directory to save CSV files

    Returns:
        Dict mapping days to file paths (or None if failed)
    """
    results = {}
    for days in days_list:
        filepath = export_bet_history(days=days, output_dir=output_dir)
        results[days] = filepath
    return results
