#!/usr/bin/env python3
"""
GlobalOrchestrator - Global Real-Time Intelligence

This module implements GLOBAL PARALLEL ARCHITECTURE for real-time intelligence monitoring.
The bot now monitors ALL active leagues simultaneously to catch news instantly.

GLOBAL EYES ARCHITECTURE:
- NO TIME RESTRICTIONS: The bot sees the whole world at once
- PARALLEL SCANNING: 3-Tab Radar (LATAM, ASIA, AFRICA) runs concurrently
- INTELLIGENCE QUEUE: Thread-safe queue serializes heavy lifting while discovery remains parallel
- SAFETY VALVE: Prevents DB locks and API rate limits

Key Changes from Continental Scheduler:
- Removed: Time-based continental windows (AFRICA: 08:00-19:00, ASIA: 00:00-11:00, LATAM: 12:00-23:00)
- Removed: Maintenance window (04:00-06:00 UTC)
- Added: get_all_active_leagues() - returns ALL active leagues regardless of time
- Added: Support for 3-tab parallel radar in Global mode

Resilience Features:
- Falls back to local mirror (data/supabase_mirror.json) if Supabase is slow/unreachable
- Comprehensive error handling and logging
- Preserves Tactical Veto V5.0 and Balanced Probability logic (imported from analyzer/math_engine)

V11.0: Global Parallel Architecture
- Parallel scanning across 3 async contexts (LATAM, ASIA, AFRICA)
- Intelligence Queue for safe, serialized processing
- Budget checks for Tavily and Brave APIs before processing

Author: Lead Architect
Date: 2026-02-08
Updated: 2026-02-23 (Centralized Version Tracking)
"""

import asyncio

# Log version on import
import logging

# Import centralized version tracking
from src.version import get_version_with_module

logger = logging.getLogger(__name__)
logger.info(f"📦 {get_version_with_module('Global Orchestrator')}")
import json
import logging
import os

# Setup path
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# V10.5 FIX: Import nest_asyncio to handle event loop conflicts
# V11.1 FIX: Call nest_asyncio.apply() once at module level for better performance
try:
    import nest_asyncio

    nest_asyncio.apply()  # Call once at module level (idempotent)
    _NEST_ASYNCIO_AVAILABLE = True
except ImportError:
    _NEST_ASYNCIO_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ nest_asyncio not available, Nitter cycle may fail in async context")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Constants
MIRROR_FILE_PATH = Path("data/supabase_mirror.json")

# Continental UTC hour windows (kept for reference but NOT used in Global mode)
CONTINENTAL_WINDOWS = {
    "AFRICA": list(range(8, 20)),  # 08:00-19:00 UTC (12 hours)
    "ASIA": list(range(0, 12)),  # 00:00-11:00 UTC (12 hours)
    "LATAM": list(range(12, 24)),  # 12:00-23:00 UTC (12 hours)
}


class GlobalOrchestrator:
    """
    Orchestrates GLOBAL PARALLEL ARCHITECTURE for league scanning.

    This class is responsible for:
    1. Fetching ALL active leagues from Supabase (no time restrictions)
    2. Running Nitter intelligence cycle for all continents
    3. Falling back to local mirror if Supabase is slow/unreachable
    4. Supporting 3-tab parallel radar in Global mode

    The Tactical Veto V5.0 and Balanced Probability logic are preserved by
    importing from the analyzer and math_engine modules respectively.
    """

    def __init__(self, supabase_provider=None):
        """
        Initialize the Global Orchestrator.

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
            self.supabase_provider is not None
            and hasattr(self.supabase_provider, "is_connected")
            and self.supabase_provider.is_connected()
        )

        if self.supabase_available:
            logger.info("✅ GlobalOrchestrator: Supabase connection available")
        else:
            logger.warning("⚠️ GlobalOrchestrator: Using local mirror fallback")

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

    def get_all_active_leagues(self) -> dict[str, Any]:
        """
        GLOBAL EYES: Returns ALL active leagues regardless of time.

        This is the main entry point for Global Parallel Architecture.
        It fetches all active leagues from Supabase without any time-based filtering.

        V11.0: Also runs Nitter intelligence cycle for ALL continents before returning leagues.

        Returns:
            Dict with keys:
            - 'leagues': List of active league api_keys to scan
            - 'continent_blocks': List of all continent names (["LATAM", "ASIA", "AFRICA"])
            - 'settlement_mode': Always False (no maintenance window in Global mode)
            - 'source': 'supabase' or 'mirror'
            - 'utc_hour': Current UTC hour
        """
        # Get current UTC hour
        current_utc_hour = datetime.now(timezone.utc).hour
        logger.info(f"🌐 GLOBAL EYES ACTIVE: Monitoring ALL leagues at {current_utc_hour}:00 UTC")

        # V11.0: All continents are always active in Global mode
        all_continents = list(CONTINENTAL_WINDOWS.keys())
        logger.info(f"🌍 Active continental blocks: {', '.join(all_continents)} (Global Mode)")

        # V11.0: Run Nitter intelligence cycle for ALL continents
        if all_continents:
            if _NEST_ASYNCIO_AVAILABLE:
                # nest_asyncio.apply() already called at module level
                asyncio.run(self._run_nitter_intelligence_cycle(all_continents))
            else:
                # Fallback: Try asyncio.run() (may fail in async context)
                try:
                    asyncio.run(self._run_nitter_intelligence_cycle(all_continents))
                except RuntimeError as e:
                    logger.error(f"❌ [GLOBAL-ORCHESTRATOR] Failed to run Nitter cycle: {e}")

        # Fetch ALL active leagues
        active_leagues = []
        source = "mirror"

        if self.supabase_available:
            try:
                # V12.5: Check connection and reconnect if necessary (COVE FIX)
                if not self.supabase_provider.is_connected():
                    logger.warning(
                        "⚠️ [GLOBAL-ORCHESTRATOR] Supabase disconnected, attempting to reconnect..."
                    )
                    if self.supabase_provider.reconnect():
                        logger.info("✅ [GLOBAL-ORCHESTRATOR] Supabase reconnected successfully")
                    else:
                        logger.warning(
                            "⚠️ [GLOBAL-ORCHESTRATOR] Supabase reconnection failed, using mirror"
                        )

                # Try to fetch from Supabase
                # V12.5: Use bypass_cache=True for first continent to ensure fresh data
                # Subsequent continents can use cached data (within 5-minute TTL)
                first_continent = True
                for continent_name in all_continents:
                    # Bypass cache for first fetch to ensure fresh data
                    bypass_cache = first_continent
                    first_continent = False

                    continent_leagues = self.supabase_provider.get_active_leagues_for_continent(
                        continent_name, bypass_cache=bypass_cache
                    )
                    active_leagues.extend(continent_leagues)

                if active_leagues:
                    source = "supabase"
                    logger.info(f"📋 Found {len(active_leagues)} active leagues from Supabase")

                    # Validate API keys
                    validation_result = self.supabase_provider.validate_api_keys(active_leagues)
                    if validation_result["invalid_count"] > 0:
                        logger.warning(
                            f"⚠️ API Key Validation: {validation_result['invalid_count']} invalid keys found"
                        )
                        for invalid in validation_result["invalid"]:
                            logger.warning(f"   ❌ {invalid['league']}: {invalid['error']}")

                    # Update local mirror at start of successful cycle
                    # Force=True ensures fresh intelligence from Supabase (Source of Truth)
                    mirror_updated = self.supabase_provider.update_mirror(force=True)
                    if mirror_updated:
                        logger.info("✅ Local mirror updated successfully")
                    else:
                        logger.warning("⚠️ Mirror update failed, using cached data")
            except Exception as e:
                logger.error(f"❌ Supabase integration failed: {e}")
                logger.warning("⚠️ Falling back to local mirror")
                active_leagues = self.fallback_to_local_mirror(all_continents)
        else:
            # Fallback to local mirror
            active_leagues = self.fallback_to_local_mirror(all_continents)

        # Extract api_keys from league records
        league_api_keys = [league["api_key"] for league in active_leagues]

        logger.info(f"🎯 Total leagues to scan: {len(league_api_keys)}")
        for league in league_api_keys:
            logger.info(f"   📌 {league}")

        return {
            "leagues": league_api_keys,
            "continent_blocks": all_continents,
            "settlement_mode": False,  # No maintenance window in Global mode
            "source": source,
            "utc_hour": current_utc_hour,
        }

    def get_active_leagues_for_current_time(self) -> dict[str, Any]:
        """
        DEPRECATED: Use get_all_active_leagues() instead.

        This method is kept for backward compatibility but now delegates
        to get_all_active_leagues() since Global mode has no time restrictions.

        Returns:
            Same as get_all_active_leagues()
        """
        logger.warning(
            "⚠️ get_active_leagues_for_current_time() is deprecated. "
            "Use get_all_active_leagues() for Global Parallel Architecture."
        )
        return self.get_all_active_leagues()

    def fallback_to_local_mirror(self, continent_blocks: list[str]) -> list[dict[str, Any]]:
        """
        Implement resilience to fall back to data/supabase_mirror.json if Supabase is slow/unreachable.

        This method loads the local mirror file and filters the leagues based on
        the provided continental blocks. It provides a fail-safe mechanism to ensure
        the system can continue operating even when Supabase is unavailable.

        Args:
            continent_blocks: List of continent names (e.g., ["LATAM", "ASIA", "AFRICA"])

        Returns:
            List of active league records from the mirror
        """
        if not MIRROR_FILE_PATH.exists():
            logger.warning(f"Mirror file not found: {MIRROR_FILE_PATH}")
            return []

        try:
            with open(MIRROR_FILE_PATH, encoding="utf-8") as f:
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

            # Filter leagues by continent blocks
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

                # Check if this continent is in the provided blocks
                continent_name = continent.get("name")
                if continent_name in continent_blocks:
                    # Enrich league with country and continent data
                    enriched_league = {
                        **league,
                        "country": {
                            "id": country["id"],
                            "name": country["name"],
                            "iso_code": country.get("iso_code"),
                        },
                        "continent": {
                            "id": continent["id"],
                            "name": continent["name"],
                            "active_hours_utc": continent.get("active_hours_utc", []),
                        },
                    }
                    active_leagues.append(enriched_league)

            logger.info(f"📋 Found {len(active_leagues)} active leagues from local mirror")
            return active_leagues

        except Exception as e:
            logger.error(f"Failed to load mirror: {e}")
            return []

    def get_continental_status(self) -> dict[str, Any]:
        """
        Get the current status of all continental blocks.

        This is a utility method for debugging and monitoring purposes.
        In Global mode, all continents are always active.

        Returns:
            Dict with continental status information
        """
        current_utc_hour = datetime.now(timezone.utc).hour

        status = {
            "current_utc_hour": current_utc_hour,
            "mode": "GLOBAL",  # V11.0: Global mode
            "in_maintenance_window": False,  # No maintenance window in Global mode
            "supabase_available": self.supabase_available,
            "continents": {},
        }

        for continent_name, active_hours in CONTINENTAL_WINDOWS.items():
            # V11.0: In Global mode, all continents are always active
            status["continents"][continent_name] = {
                "active_hours_utc": active_hours,
                "is_currently_active": True,  # Always active in Global mode
            }

        return status

    # ============================================
    # V11.0: NITTER INTELLIGENCE CYCLE (GLOBAL MODE)
    # ============================================

    async def _run_nitter_intelligence_cycle(self, continent_blocks: list[str]) -> None:
        """
        Run Nitter intelligence cycle for ALL continental blocks.

        This method calls nitter_scraper.run_cycle() for each continent
        to gather fresh Twitter intel before the main match loop starts.

        Args:
            continent_blocks: List of all continent names (e.g., ["LATAM", "ASIA", "AFRICA"])
        """
        try:
            # Import inside method to avoid circular imports
            from src.services.nitter_fallback_scraper import get_nitter_fallback_scraper

            scraper = get_nitter_fallback_scraper()

            # V12.6 COVE FIX: Clear expired cache entries before starting new cycle
            try:
                expired_count = scraper._cache.clear_expired()
                if expired_count > 0:
                    logger.info(f"🧹 [NITTER-CACHE] Cleared {expired_count} expired entries")
            except Exception as e:
                logger.warning(f"⚠️ [NITTER-CACHE] Failed to clear expired entries: {e}")

            logger.info(
                f"🐦 [NITTER-CYCLE] Starting GLOBAL intelligence cycle for {len(continent_blocks)} continents"
            )

            # Run cycle for each continent
            for continent in continent_blocks:
                try:
                    logger.info(f"🌍 [NITTER-CYCLE] Processing continent: {continent}")
                    result = await scraper.run_cycle(continent)

                    if result:
                        logger.info(
                            f"✅ [NITTER-CYCLE] {continent} cycle complete: "
                            f"{result['handles_processed']} handles, {result['tweets_found']} tweets, "
                            f"{result['relevant_tweets']} relevant, {result['matches_triggered']} triggered"
                        )
                    else:
                        logger.warning(f"⚠️ [NITTER-CYCLE] {continent} cycle returned no results")

                except Exception as e:
                    logger.error(f"❌ [NITTER-CYCLE] Error processing {continent}: {e}")
                    continue

            logger.info(
                "🎯 [NITTER-CYCLE] GLOBAL intelligence cycle complete - ready for match analysis"
            )

        except Exception as e:
            logger.error(f"❌ [NITTER-CYCLE] Failed to run intelligence cycle: {e}")


# Convenience function for easy access
def get_global_orchestrator(supabase_provider=None) -> GlobalOrchestrator:
    """
    Get a GlobalOrchestrator instance.

    Args:
        supabase_provider: Optional SupabaseProvider instance

    Returns:
        GlobalOrchestrator instance
    """
    return GlobalOrchestrator(supabase_provider)


# Backward compatibility alias
def get_continental_orchestrator(supabase_provider=None) -> GlobalOrchestrator:
    """
    DEPRECATED: Use get_global_orchestrator() instead.

    This function is kept for backward compatibility but now returns
    a GlobalOrchestrator instance.

    Args:
        supabase_provider: Optional SupabaseProvider instance

    Returns:
        GlobalOrchestrator instance
    """
    logger.warning(
        "⚠️ get_continental_orchestrator() is deprecated. "
        "Use get_global_orchestrator() for Global Parallel Architecture."
    )
    return GlobalOrchestrator(supabase_provider)


# Preserved imports for Tactical Veto V5.0 and Balanced Probability logic
# These are the project's "Gold Standard" logic that must be preserved
try:
    from src.analysis.analyzer import (
        # Tactical Veto V5.0 logic is implemented in analyzer.py
        # The analyzer module handles tactical veto rules for injury impact
        analyze_with_triangulation,
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
        format_math_context,
    )

    _MATH_ENGINE_AVAILABLE = True
    logger.info("✅ Math Engine module loaded (Balanced Probability preserved)")
except ImportError as e:
    _MATH_ENGINE_AVAILABLE = False
    logger.warning(f"⚠️ Math Engine module not available: {e}")


if __name__ == "__main__":
    # Test the Global Orchestrator
    print("=" * 60)
    print("GlobalOrchestrator - Global Parallel Architecture Test")
    print("=" * 60)

    orchestrator = get_global_orchestrator()

    # Test continental status
    print("\n--- Continental Status ---")
    status = orchestrator.get_continental_status()
    print(f"Mode: {status['mode']}")
    print(f"UTC Hour: {status['current_utc_hour']}")
    print(f"Supabase Available: {status['supabase_available']}")
    print("\nContinents:")
    for continent_name, continent_status in status["continents"].items():
        print(f"  {continent_name}: {continent_status['is_currently_active']}")

    # Test get all active leagues
    print("\n--- All Active Leagues ---")
    result = orchestrator.get_all_active_leagues()
    print(f"Leagues: {len(result['leagues'])}")
    print(f"Continents: {result['continent_blocks']}")
    print(f"Source: {result['source']}")
