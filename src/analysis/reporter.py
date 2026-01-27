"""
Daily CSV Report Generator for EarlyBird
Exports human-readable betting history with team names and leagues.
"""
import csv
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.database.models import Match, NewsLog, SessionLocal

logger = logging.getLogger(__name__)


def export_bet_history(days: int = 1, output_dir: str = "temp") -> Optional[str]:
    """
    Export betting history to a human-readable CSV file.
    
    Args:
        days: Number of days to look back (default: 1 for daily report)
        output_dir: Directory to save the CSV file
        
    Returns:
        Path to the generated CSV file, or None if no data/error
    """
    db = SessionLocal()
    
    try:
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
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
            logger.info("📊 No betting history found for the specified period")
            return None
        
        # Generate filename with date
        date_str = now.strftime("%Y-%m-%d")
        filename = f"EarlyBird_Report_{date_str}.csv"
        filepath = os.path.join(output_dir, filename)
        
        # Write CSV with Italian headers (utf-8-sig for Excel compatibility)
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            
            # Header row
            writer.writerow([
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
            ])
            
            # Data rows
            for log in results:
                # Safety: Handle orphan logs (match deleted)
                match = log.match
                if not match:
                    logger.warning(f"Orphan NewsLog found: {log.id}")
                    continue
                
                # Format match string
                partita = f"{match.home_team} vs {match.away_team}"
                
                # Format date/time
                match_time = match.start_time.strftime("%d/%m %H:%M") if match.start_time else "N/A"
                
                # Format odds string
                odds_str = ""
                if match.current_home_odd and match.current_draw_odd and match.current_away_odd:
                    odds_str = f"1:{match.current_home_odd:.2f} X:{match.current_draw_odd:.2f} 2:{match.current_away_odd:.2f}"
                
                # Use combo_suggestion if available, otherwise recommended_market
                pronostico = log.combo_suggestion or log.recommended_market or "N/A"
                
                # Result and Outcome (Pending - settlement done separately)
                # Check if match should be finished (started > 2 hours ago)
                is_finished = match.start_time and (now - match.start_time).total_seconds() > 7200
                risultato = "Pending" if not is_finished else "Da verificare"
                esito = "PENDING"
                
                writer.writerow([
                    match.league or "N/A",
                    partita,
                    match_time,
                    pronostico,
                    log.recommended_market or "N/A",
                    f"{log.score}/10" if log.score else "N/A",
                    log.primary_driver or "N/A",
                    odds_str,
                    risultato,
                    esito
                ])
        
        logger.info(f"📊 Report generated: {filepath} ({len(results)} records)")
        return filepath
        
    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
        return None
        
    finally:
        db.close()


def get_daily_summary() -> dict:
    """
    Get a summary of today's betting activity for the report caption.
    
    Returns:
        Dict with total_alerts, leagues_covered, top_score
    """
    db = SessionLocal()
    
    try:
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
        top_score = db.query(NewsLog.score).filter(
            NewsLog.timestamp >= today_start,
            NewsLog.sent == True
        ).order_by(NewsLog.score.desc()).first()
        
        return {
            'total_alerts': total_alerts,
            'leagues_covered': len(leagues),
            'top_score': top_score[0] if top_score else 0
        }
        
    except Exception as e:
        logger.error(f"Error getting daily summary: {e}")
        return {'total_alerts': 0, 'leagues_covered': 0, 'top_score': 0}
        
    finally:
        db.close()
