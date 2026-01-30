"""
Odds Capture Service for EarlyBird

Captures odds at match kickoff time for accurate CLV calculation.

V8.3: Part of the learning loop integrity fix.

This module provides a scheduled job that:
1. Finds upcoming matches with sent alerts but no kickoff odds captured
2. Captures current odds at match kickoff time
3. Stores them in NewsLog.odds_at_kickoff field

Usage:
    from src.services.odds_capture import capture_kickoff_odds
    capture_kickoff_odds()  # Run as scheduled job
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from sqlalchemy import and_, or_
from src.database.models import Match, NewsLog
from src.database.db import get_db_context
from src.ingestion.data_provider import get_data_provider
from src.utils.odds_utils import get_market_odds

logger = logging.getLogger(__name__)


def capture_kickoff_odds() -> int:
    """
    Capture odds at match kickoff time for all relevant matches.
    
    This function should be run as a scheduled job (e.g., every 5 minutes).
    It finds matches that:
    1. Have started within the last 10 minutes (just kicked off)
    2. Have sent alerts (sent=True)
    3. Don't have kickoff odds captured yet (odds_at_kickoff IS NULL)
    
    Args:
        None
        
    Returns:
        Number of NewsLog records updated
    """
    updated_count = 0
    
    with get_db_context() as db:
        try:
            # Find matches that just started (within last 10 minutes)
            now = datetime.now(timezone.utc)
            kickoff_window_start = now - timedelta(minutes=10)
            kickoff_window_end = now - timedelta(minutes=1)  # At least 1 minute ago
            
            # Query for matches that just started
            upcoming_matches = db.query(Match).filter(
                and_(
                    Match.start_time >= kickoff_window_start,
                    Match.start_time <= kickoff_window_end,
                    Match.match_status == 'scheduled'  # Not yet marked as live/finished
                )
            ).all()
            
            if not upcoming_matches:
                logger.debug("📊 No matches in kickoff window. Skipping odds capture.")
                return 0
            
            logger.info(f"📊 Found {len(upcoming_matches)} matches in kickoff window")
            
            # For each match, find sent NewsLog records without kickoff odds
            for match in upcoming_matches:
                news_logs = db.query(NewsLog).filter(
                    and_(
                        NewsLog.match_id == match.id,
                        NewsLog.sent == True,
                        NewsLog.odds_at_kickoff.is_(None)  # Not captured yet
                    )
                ).all()
                
                if not news_logs:
                    continue
                
                # Refresh match odds from data provider
                # V8.3 FIX: Add retry mechanism for data provider unavailability
                max_retries = 3
                retry_delay_seconds = 2
                provider_available = False
                
                for attempt in range(max_retries):
                    try:
                        provider = get_data_provider()
                        if not provider:
                            if attempt < max_retries - 1:
                                logger.warning(
                                    f"⚠️  Data provider not available (attempt {attempt + 1}/{max_retries}). "
                                    f"Retrying in {retry_delay_seconds}s..."
                                )
                                import time
                                time.sleep(retry_delay_seconds)
                                continue
                            else:
                                logger.warning(
                                    f"⚠️  Data provider not available after {max_retries} attempts. "
                                    f"Skipping odds refresh for {match.home_team} vs {match.away_team}."
                                )
                                break
                        
                        provider_available = True
                        
                        # Fetch latest odds for this match
                        updated_match = provider.get_match_by_id(match.id)
                        if updated_match:
                            # Update match with latest odds
                            match.current_home_odd = updated_match.current_home_odd
                            match.current_away_odd = updated_match.current_away_odd
                            match.current_draw_odd = updated_match.current_draw_odd
                            db.add(match)
                            logger.info(f"📊 Refreshed odds for {match.home_team} vs {match.away_team}")
                        break  # Success, exit retry loop
                        
                    except Exception as e:
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"⚠️  Could not refresh odds for {match.id} (attempt {attempt + 1}/{max_retries}): {e}. "
                                f"Retrying in {retry_delay_seconds}s..."
                            )
                            import time
                            time.sleep(retry_delay_seconds)
                        else:
                            logger.warning(
                                f"⚠️  Could not refresh odds for {match.id} after {max_retries} attempts: {e}. "
                                f"Continuing with existing odds."
                            )
                
                if not provider_available:
                    # Continue with existing odds if provider unavailable after retries
                    pass
                
                # Capture kickoff odds for each NewsLog
                for news_log in news_logs:
                    if not news_log.recommended_market:
                        continue
                    
                    kickoff_odds = get_market_odds(news_log.recommended_market, match)
                    
                    if kickoff_odds:
                        news_log.odds_at_kickoff = kickoff_odds
                        db.add(news_log)
                        updated_count += 1
                        
                        logger.info(
                            f"✅ Captured kickoff odds: {kickoff_odds:.2f} "
                            f"for {news_log.recommended_market} "
                            f"({match.home_team} vs {match.away_team})"
                        )
                    else:
                        logger.warning(
                            f"⚠️  Could not capture kickoff odds for "
                            f"{news_log.recommended_market} ({match.home_team} vs {match.away_team})"
                        )
            
            if updated_count > 0:
                db.commit()
                logger.info(f"✅ V8.3: Captured kickoff odds for {updated_count} alerts")
            else:
                logger.debug("📊 No kickoff odds to capture in this run")
            
            return updated_count
            
        except Exception as e:
            logger.error(f"❌ V8.3: Odds capture failed: {e}", exc_info=True)
            db.rollback()
            return 0


def get_kickoff_odds_capture_stats() -> dict:
    """
    Get statistics on kickoff odds capture status.
    
    Returns:
        Dict with capture statistics
    """
    with get_db_context() as db:
        try:
            # Count sent alerts with and without kickoff odds
            total_sent = db.query(NewsLog).filter(
                and_(
                    NewsLog.sent == True,
                    NewsLog.recommended_market.isnot(None)
                )
            ).count()
            
            with_kickoff = db.query(NewsLog).filter(
                and_(
                    NewsLog.sent == True,
                    NewsLog.recommended_market.isnot(None),
                    NewsLog.odds_at_kickoff.isnot(None)
                )
            ).count()
            
            without_kickoff = total_sent - with_kickoff
            
            # Count with alert odds
            with_alert_odds = db.query(NewsLog).filter(
                and_(
                    NewsLog.sent == True,
                    NewsLog.recommended_market.isnot(None),
                    NewsLog.odds_at_alert.isnot(None)
                )
            ).count()
            
            return {
                'total_sent': total_sent,
                'with_kickoff_odds': with_kickoff,
                'without_kickoff_odds': without_kickoff,
                'with_alert_odds': with_alert_odds,
                'kickoff_capture_rate': (with_kickoff / total_sent * 100) if total_sent > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"❌ Could not get kickoff odds stats: {e}")
            return {}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("📊 V8.3: Running kickoff odds capture...")
    count = capture_kickoff_odds()
    
    stats = get_kickoff_odds_capture_stats()
    logger.info(f"📊 Kickoff Odds Capture Stats: {stats}")
