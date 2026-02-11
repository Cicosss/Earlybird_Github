#!/usr/bin/env python3
"""
ContinentalOrchestrator - "Follow the Sun" Scheduler (V1.0)

This module implements the "Follow the Sun" scheduling logic that determines which
leagues to scan based on the current UTC time and continental windows.

The system operates on three continental blocks:
- AFRICA: Active during UTC hours 08:00-19:00 (12-hour window)
- ASIA: Active during UTC hours 00:00-11:00 (12-hour window)
- LATAM: Active during UTC hours 12:00-23:00 (12-hour window)

There is also a maintenance/settlement window from 04:00-06:00 UTC where
no analysis is performed, only settlement of pending bets.

Resilience Features:
- Falls back to local mirror (data/supabase_mirror.json) if Supabase is slow/unreachable
- Comprehensive error handling and logging
- Preserves Tactical Veto V5.0 and Balanced Probability logic (imported from analyzer/math_engine)

Author: Lead Architect
Date: 2026-02-08
"""

import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path

# Setup path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Constants
MIRROR_FILE_PATH = Path("data/supabase_mirror.json")
MAINTENANCE_WINDOW_START = 4  # 04:00 UTC
MAINTENANCE_WINDOW_END = 6    # 06:00 UTC

# Continental UTC hour windows
CONTINENTAL_WINDOWS = {
    "AFRICA": list(range(8, 20)),   # 08:00-19:00 UTC (12 hours)
    "ASIA": list(range(0, 12)),     # 00:00-11:00 UTC (12 hours)
    "LATAM": list(range(12, 24)),   # 12:00-23:00 UTC (12 hours)
}


class ContinentalOrchestrator:
    """
    Orchestrates the "Follow the Sun" scheduling logic for league scanning.
    
    This class is responsible for:
    1. Fetching active leagues from Supabase
    2. Applying UTC hour filters for continental windows
    3. Handling the maintenance window (04:00-06:00 UTC)
    4. Falling back to local mirror if Supabase is slow/unreachable
    
    The Tactical Veto V5.0 and Balanced Probability logic are preserved by
    importing from the analyzer and math_engine modules respectively.
    """
    
    def __init__(self, supabase_provider=None):
        """
        Initialize the Continental Orchestrator.
        
        Args:
            supabase_provider: Optional SupabaseProvider instance. If None, will
                             attempt to import and create one.
        """
        self.supabase_provider = supabase_provider
        self.supabase_available = False
        
        # Try to get Supabase provider if not provided
        if self.supabase_provider is None:
            self._initialize_supabase_provider()
        
        # Check if Supabase is available
        self.supabase_available = (
            self.supabase_provider is not None and
            hasattr(self.supabase_provider, 'is_connected') and
            self.supabase_provider.is_connected()
        )
        
        if self.supabase_available:
            logger.info("✅ ContinentalOrchestrator: Supabase connection available")
        else:
            logger.warning("⚠️ ContinentalOrchestrator: Using local mirror fallback")
    
    def _initialize_supabase_provider(self) -> None:
        """Initialize Supabase provider by importing from database module."""
        try:
            from src.database.supabase_provider import get_supabase
            self.supabase_provider = get_supabase()
            logger.info("Supabase provider initialized successfully")
        except ImportError as e:
            logger.warning(f"Supabase provider not available: {e}")
            self.supabase_provider = None
        except Exception as e:
            logger.error(f"Failed to initialize Supabase provider: {e}")
            self.supabase_provider = None
    
    def get_active_leagues_for_current_time(self) -> Dict[str, Any]:
        """
        Main method that returns leagues to scan based on current UTC time.
        
        This is the primary entry point for the "Follow the Sun" scheduler.
        It determines which continental blocks are active, checks for the
        maintenance window, and returns the appropriate leagues.
        
        Returns:
            Dict with keys:
            - 'leagues': List of active league api_keys to scan
            - 'continent_blocks': List of active continent names
            - 'settlement_mode': Boolean indicating if in maintenance window
            - 'source': 'supabase' or 'mirror'
            - 'utc_hour': Current UTC hour
        """
        # Get current UTC hour
        current_utc_hour = datetime.now(timezone.utc).hour
        logger.info(f"🕐 Current UTC time: {current_utc_hour}:00")
        
        # Check if we're in maintenance/settlement window
        if self.is_maintenance_window(current_utc_hour):
            logger.info("⏰ SETTLEMENT-ONLY WINDOW: 04:00-06:00 UTC - Skipping analysis")
            return {
                'leagues': [],
                'continent_blocks': [],
                'settlement_mode': True,
                'source': 'none',
                'utc_hour': current_utc_hour
            }
        
        # Determine active continental blocks
        active_continent_blocks = self.apply_continental_filters(current_utc_hour)
        logger.info(f"🌍 Active continental blocks: {', '.join(active_continent_blocks) if active_continent_blocks else 'None'}")
        
        # Fetch active leagues for the active continental blocks
        active_leagues = []
        source = 'mirror'
        
        if self.supabase_available and active_continent_blocks:
            try:
                # Try to fetch from Supabase
                for continent_name in active_continent_blocks:
                    continent_leagues = self.supabase_provider.get_active_leagues_for_continent(continent_name)
                    active_leagues.extend(continent_leagues)
                
                if active_leagues:
                    source = 'supabase'
                    logger.info(f"📋 Found {len(active_leagues)} active leagues from Supabase")
                    
                    # Validate API keys
                    validation_result = self.supabase_provider.validate_api_keys(active_leagues)
                    if validation_result['invalid_count'] > 0:
                        logger.warning(f"⚠️ API Key Validation: {validation_result['invalid_count']} invalid keys found")
                        for invalid in validation_result['invalid']:
                            logger.warning(f"   ❌ {invalid['league']}: {invalid['error']}")
                    
                    # Update local mirror at start of successful cycle
                    mirror_updated = self.supabase_provider.update_mirror(force=False)
                    if mirror_updated:
                        logger.info("✅ Local mirror updated successfully")
                    else:
                        logger.warning("⚠️ Mirror update failed, using cached data")
            except Exception as e:
                logger.error(f"❌ Supabase integration failed: {e}")
                logger.warning("⚠️ Falling back to local mirror")
                active_leagues = self.fallback_to_local_mirror(active_continent_blocks)
        else:
            # Fallback to local mirror
            active_leagues = self.fallback_to_local_mirror(active_continent_blocks)
        
        # Extract api_keys from league records
        league_api_keys = [league['api_key'] for league in active_leagues]
        
        logger.info(f"🎯 Total leagues to scan: {len(league_api_keys)}")
        for league in league_api_keys:
            logger.info(f"   📌 {league}")
        
        return {
            'leagues': league_api_keys,
            'continent_blocks': active_continent_blocks,
            'settlement_mode': False,
            'source': source,
            'utc_hour': current_utc_hour
        }
    
    def apply_continental_filters(self, current_utc_hour: int) -> List[str]:
        """
        Apply the UTC hour filters for AFRICA, ASIA, LATAM continental windows.
        
        This method determines which continental blocks are active based on the
        current UTC hour. Each continent has a 12-hour active window:
        - AFRICA: 08:00-19:00 UTC
        - ASIA: 00:00-11:00 UTC
        - LATAM: 12:00-23:00 UTC
        
        Args:
            current_utc_hour: Current hour in UTC (0-23)
            
        Returns:
            List of active continent names (e.g., ["LATAM", "ASIA"])
        """
        active_blocks = []
        
        for continent_name, active_hours in CONTINENTAL_WINDOWS.items():
            if current_utc_hour in active_hours:
                active_blocks.append(continent_name)
        
        logger.debug(f"Active continental blocks at {current_utc_hour}:00 UTC: {active_blocks}")
        return active_blocks
    
    def is_maintenance_window(self, current_utc_hour: int) -> bool:
        """
        Check if current time is in the 04:00-06:00 UTC maintenance/settlement window.
        
        During the maintenance window, no analysis is performed. Only settlement
        of pending bets is allowed.
        
        Args:
            current_utc_hour: Current hour in UTC (0-23)
            
        Returns:
            True if in maintenance window (04:00-06:00 UTC), False otherwise
        """
        is_maintenance = MAINTENANCE_WINDOW_START <= current_utc_hour < MAINTENANCE_WINDOW_END
        
        if is_maintenance:
            logger.debug(f"Maintenance window active at {current_utc_hour}:00 UTC")
        
        return is_maintenance
    
    def fallback_to_local_mirror(self, active_continent_blocks: List[str]) -> List[Dict[str, Any]]:
        """
        Implement resilience to fall back to data/supabase_mirror.json if Supabase is slow/unreachable.
        
        This method loads the local mirror file and filters the leagues based on
        the active continental blocks. It provides a fail-safe mechanism to ensure
        the system can continue operating even when Supabase is unavailable.
        
        Args:
            active_continent_blocks: List of active continent names
            
        Returns:
            List of active league records from the mirror
        """
        if not MIRROR_FILE_PATH.exists():
            logger.warning(f"Mirror file not found: {MIRROR_FILE_PATH}")
            return []
        
        try:
            with open(MIRROR_FILE_PATH, 'r', encoding='utf-8') as f:
                mirror_data = json.load(f)
            
            timestamp = mirror_data.get("timestamp", "")
            data = mirror_data.get("data", {})
            
            logger.info(f"Loaded mirror from {timestamp}")
            
            # Extract continents, countries, and leagues from mirror
            continents = data.get("continents", [])
            countries = data.get("countries", [])
            leagues_data = data.get("leagues", [])
            
            # Build lookup dictionaries
            continent_map = {c["id"]: c for c in continents}
            country_map = {c["id"]: c for c in countries}
            
            # Filter leagues by active continental blocks
            active_leagues = []
            
            for league in leagues_data:
                # Skip inactive leagues
                if not league.get("is_active", False):
                    continue
                
                # Get country for this league
                country_id = league.get("country_id")
                country = country_map.get(country_id)
                
                if not country:
                    continue
                
                # Get continent for this country
                continent_id = country.get("continent_id")
                continent = continent_map.get(continent_id)
                
                if not continent:
                    continue
                
                # Check if this continent is in the active blocks
                continent_name = continent.get("name")
                if continent_name in active_continent_blocks:
                    # Enrich league with country and continent data
                    enriched_league = {
                        **league,
                        "country": {
                            "id": country["id"],
                            "name": country["name"],
                            "iso_code": country.get("iso_code")
                        },
                        "continent": {
                            "id": continent["id"],
                            "name": continent["name"],
                            "active_hours_utc": continent.get("active_hours_utc", [])
                        }
                    }
                    active_leagues.append(enriched_league)
            
            logger.info(f"📋 Found {len(active_leagues)} active leagues from local mirror")
            return active_leagues
            
        except Exception as e:
            logger.error(f"Failed to load mirror: {e}")
            return []
    
    def get_continental_status(self) -> Dict[str, Any]:
        """
        Get the current status of all continental blocks.
        
        This is a utility method for debugging and monitoring purposes.
        It shows which continental blocks are currently active and their
        configured UTC hour windows.
        
        Returns:
            Dict with continental status information
        """
        current_utc_hour = datetime.now(timezone.utc).hour
        
        status = {
            'current_utc_hour': current_utc_hour,
            'in_maintenance_window': self.is_maintenance_window(current_utc_hour),
            'supabase_available': self.supabase_available,
            'continents': {}
        }
        
        for continent_name, active_hours in CONTINENTAL_WINDOWS.items():
            is_active = current_utc_hour in active_hours
            status['continents'][continent_name] = {
                'active_hours_utc': active_hours,
                'is_currently_active': is_active
            }
        
        return status


# Convenience function for easy access
def get_continental_orchestrator(supabase_provider=None) -> ContinentalOrchestrator:
    """
    Get a ContinentalOrchestrator instance.
    
    Args:
        supabase_provider: Optional SupabaseProvider instance
        
    Returns:
        ContinentalOrchestrator instance
    """
    return ContinentalOrchestrator(supabase_provider)


# Preserved imports for Tactical Veto V5.0 and Balanced Probability logic
# These are the project's "Gold Standard" logic that must be preserved
try:
    from src.analysis.analyzer import (
        # Tactical Veto V5.0 logic is implemented in analyzer.py
        # The analyzer module handles tactical veto rules for injury impact
        analyze_with_triangulation
    )
    _ANALYZER_AVAILABLE = True
    logger.info("✅ Analyzer module loaded (Tactical Veto V5.0 preserved)")
except ImportError as e:
    _ANALYZER_AVAILABLE = False
    logger.warning(f"⚠️ Analyzer module not available: {e}")


try:
    from src.analysis.math_engine import (
        # Balanced Probability logic is implemented in math_engine.py
        # The math_engine module handles balanced probability calculations
        MathPredictor,
        format_math_context
    )
    _MATH_ENGINE_AVAILABLE = True
    logger.info("✅ Math Engine module loaded (Balanced Probability preserved)")
except ImportError as e:
    _MATH_ENGINE_AVAILABLE = False
    logger.warning(f"⚠️ Math Engine module not available: {e}")


if __name__ == "__main__":
    # Test the Continental Orchestrator
    print("=" * 60)
    print("ContinentalOrchestrator - Follow the Sun Scheduler Test")
    print("=" * 60)
    
    orchestrator = get_continental_orchestrator()
    
    # Test continental status
    print("\n1. Continental Status...")
    status = orchestrator.get_continental_status()
    print(f"   Current UTC hour: {status['current_utc_hour']}")
    print(f"   In maintenance window: {status['in_maintenance_window']}")
    print(f"   Supabase available: {status['supabase_available']}")
    for continent, info in status['continents'].items():
        active_str = "ACTIVE" if info['is_currently_active'] else "INACTIVE"
        print(f"   {continent}: {active_str} (hours: {info['active_hours_utc'][0]}-{info['active_hours_utc'][-1]})")
    
    # Test getting active leagues
    print("\n2. Getting active leagues for current time...")
    result = orchestrator.get_active_leagues_for_current_time()
    print(f"   Settlement mode: {result['settlement_mode']}")
    print(f"   Source: {result['source']}")
    print(f"   Active continent blocks: {result['continent_blocks']}")
    print(f"   Leagues to scan: {len(result['leagues'])}")
    for league in result['leagues']:
        print(f"      - {league}")
    
    print("\n" + "=" * 60)
    print("ContinentalOrchestrator Active. Follow the Sun scheduling operational.")
    print("=" * 60)
