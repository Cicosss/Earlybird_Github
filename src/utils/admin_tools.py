"""
EarlyBird Admin Tools - Shared utilities for Bot commands.

Provides helper functions for:
- /debug: Log reading
- /report: CSV export
- /stat: Stats dashboard

These are sync functions - use asyncio.to_thread() when calling from async handlers.
"""
import os
import logging
from collections import deque
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


def read_last_error_lines(filepath: str = "earlybird.log", n: int = 15) -> List[str]:
    """
    Memory-efficient sync helper to read last N error/warning lines from log.
    Uses deque with maxlen to avoid loading entire file into memory.
    
    Args:
        filepath: Path to log file
        n: Number of error lines to return
        
    Returns:
        List of last N error/warning/critical lines
    """
    error_levels = ("WARNING", "ERROR", "CRITICAL")
    error_lines = deque(maxlen=n)
    
    try:
        if not os.path.exists(filepath):
            return []
            
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                for level in error_levels:
                    if level in line:
                        error_lines.append(line.strip())
                        break
    except Exception as e:
        logger.error(f"Errore lettura log: {e}")
        return []
    
    return list(error_lines)


def format_debug_output(error_lines: List[str]) -> str:
    """
    Format error lines for Telegram message with icons.
    
    Args:
        error_lines: List of raw log lines
        
    Returns:
        Formatted string for Telegram
    """
    if not error_lines:
        return "✅ **Nessun errore recente.**"
    
    formatted_lines = []
    for line in error_lines:
        # Add appropriate icon
        if "CRITICAL" in line:
            icon = "🔴"
        elif "ERROR" in line:
            icon = "❌"
        else:  # WARNING
            icon = "⚠️"
        
        # Extract timestamp and message
        parts = line.split(" - ", 1)
        if len(parts) >= 2:
            try:
                timestamp = parts[0].split(" ")[-1][:5] if " " in parts[0] else parts[0][:5]
                message = parts[1][:100]
                formatted_lines.append(f"{icon} {timestamp} {message}")
            except Exception:
                formatted_lines.append(f"{icon} {line[:100]}")
        else:
            formatted_lines.append(f"{icon} {line[:100]}")
    
    output = "🔍 **Ultimi errori/warning:**\n\n```\n"
    output += "\n".join(formatted_lines)
    output += "\n```"
    
    return output


def generate_report(days: int = 7) -> Optional[str]:
    """
    Generate CSV report of bet history.
    
    Args:
        days: Number of days to include
        
    Returns:
        Path to generated CSV file, or None if no data
    """
    try:
        from src.analysis.reporter import export_bet_history
        return export_bet_history(days=days)
    except Exception as e:
        logger.error(f"Errore generazione report: {e}")
        return None


def get_report_summary() -> Dict:
    """
    Get summary stats for report caption.
    
    Returns:
        Dict with total_alerts, leagues_covered, top_score
    """
    try:
        from src.analysis.reporter import get_daily_summary
        return get_daily_summary()
    except Exception as e:
        logger.error(f"Errore lettura summary: {e}")
        return {
            'total_alerts': 0,
            'leagues_covered': 0,
            'top_score': 0
        }


def generate_stats_dashboard() -> Optional[str]:
    """
    Generate stats dashboard image.
    
    Returns:
        Path to generated image, or None on error
    """
    try:
        from src.analysis.stats_drawer import generate_dashboard
        return generate_dashboard()
    except ImportError:
        logger.warning("matplotlib non disponibile per dashboard")
        return None
    except Exception as e:
        logger.error(f"Errore generazione dashboard: {e}")
        return None


def get_stats_text_summary() -> str:
    """
    Get text-only stats summary (fallback when matplotlib unavailable).
    
    Returns:
        HTML formatted stats summary
    """
    try:
        from src.analysis.stats_drawer import get_text_summary
        return get_text_summary()
    except Exception as e:
        logger.error(f"Errore lettura stats: {e}")
        return "❌ Errore lettura statistiche"
