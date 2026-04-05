"""
EarlyBird News Radar Monitor - Autonomous Web Monitoring

Independent component that monitors configured web sources 24/7 to discover
betting-relevant news on minor leagues NOT covered by the main bot.

Unlike the Browser Monitor (which feeds the main pipeline), News Radar:
- Operates completely independently from the main bot
- Sends direct Telegram alerts without database interaction
- Monitors leagues/sources NOT covered by the existing system
- Has a simplified flow: extract → filter → analyze → alert

Flow:
1. Load configured source URLs from config/news_radar_sources.json
2. Continuously scan sources in a loop (default 5 min interval)
3. Extract page text with HTTP + Trafilatura (fallback: Playwright)
4. Apply exclusion filters (basketball, women's, youth, NFL, etc.)
5. Analyze relevance for betting-relevant news (injuries, suspensions, etc.)
6. If ambiguous (0.5-0.7 confidence): call DeepSeek for deeper analysis
7. If relevant (confidence >= 0.7): send Telegram alert
8. Deduplicate using content hash cache (24h TTL)

Requirements: 1.1-1.4, 2.1-2.4, 3.1-3.5, 4.1-4.5, 5.1-5.4, 6.1-6.4, 7.1-7.4, 8.1-8.4, 9.1-9.4, 10.1-10.4
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import time
import traceback
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

# V1.1: Import shared content analysis utilities
from src.utils.content_analysis import (
    AnalysisResult,
    get_exclusion_filter,
    get_positive_news_filter,
)

# V2.0: Import high-value signal detection
from src.utils.high_value_detector import (
    SignalType,
    StructuredAnalysis,
    get_garbage_filter,
    get_signal_detector,
)

# V8.1: Import centralized HTTP client for rate limiting
from src.utils.http_client import get_http_client

# V8.1: Import centralized HTTP client for rate limiting
from src.utils.radar_prompts import (
    BETTING_IMPACT_EMOJI,
    CATEGORY_EMOJI,
    CATEGORY_ITALIAN,
    build_analysis_prompt_v2,
)
from src.utils.validators import safe_get

# V1.3: Import light enrichment for database context
try:
    from src.utils.radar_enrichment import EnrichmentContext, enrich_radar_alert_async

    _ENRICHMENT_AVAILABLE = True
except ImportError:
    _ENRICHMENT_AVAILABLE = False
    EnrichmentContext = None

# V7.3: Import odds movement checker
try:
    from src.utils.radar_odds_check import OddsMovementStatus, check_odds_for_alert_async

    _ODDS_CHECK_AVAILABLE = True
except ImportError:
    _ODDS_CHECK_AVAILABLE = False
    OddsMovementStatus = None

# V7.3: Import cross-source validator
try:
    from src.utils.radar_cross_validator import get_cross_validator

    _CROSS_VALIDATOR_AVAILABLE = True
except ImportError:
    _CROSS_VALIDATOR_AVAILABLE = False

# V12.1: playwright-stealth import with fallback (COVE FIX)
try:
    from playwright_stealth import Stealth

    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    Stealth = None

# V13.1: ArticleReader for Scrapling-based stealth extraction (WAF bypass)
try:
    from src.utils.article_reader import ArticleReader as _ArticleReader

    _ARTICLE_READER_AVAILABLE = True
except ImportError:
    _ARTICLE_READER_AVAILABLE = False
    _ArticleReader = None  # type: ignore

# V11.0: Import DiscoveryQueue for GlobalRadarMonitor intelligence queue
from src.utils.discovery_queue import DiscoveryQueue, get_discovery_queue

logger = logging.getLogger(__name__)

# V12.1: Log stealth availability (COVE FIX)
if not STEALTH_AVAILABLE:
    logger.warning("⚠️ [NEWS-RADAR] playwright-stealth not installed, running without stealth")

# V13.1: Log ArticleReader availability
if _ARTICLE_READER_AVAILABLE:
    logger.info("✅ [NEWS-RADAR] ArticleReader (Scrapling) available - WAF bypass enabled")
else:
    logger.warning(
        "⚠️ [NEWS-RADAR] ArticleReader not available - HTTP extraction without WAF bypass"
    )

# Configuration constants
DEFAULT_CONFIG_FILE = "config/news_radar_sources.json"
DEFAULT_SCAN_INTERVAL_MINUTES = 5
DEFAULT_PAGE_TIMEOUT_SECONDS = 30
DEFAULT_CACHE_TTL_HOURS = 24
DEFAULT_CACHE_MAX_ENTRIES = 5000
DEFAULT_NAVIGATION_DELAY_SECONDS = 3
DEFAULT_MAX_LINKS_PER_PAGINATED = 10
MAX_TEXT_LENGTH = 30000

# Confidence thresholds
DEEPSEEK_CONFIDENCE_THRESHOLD = 0.5  # Below this: skip
ALERT_CONFIDENCE_THRESHOLD = 0.7  # Above this: alert directly

# DeepSeek rate limiting
DEEPSEEK_MIN_INTERVAL_SECONDS = 2.0

# Circuit breaker configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 300  # 5 minutes
CIRCUIT_BREAKER_MAX_RETRIES = 20  # Give up after 20 total attempts (approx 100 min)

# HTTP configuration
HTTP_TIMEOUT = 15
HTTP_MIN_CONTENT_LENGTH = 200

# V13.1: WAF detection status codes
WAF_BLOCK_CODES = {403, 429}

# OpenRouter API
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Trafilatura extraction via centralized module (handles warning suppression)
try:
    from src.utils.trafilatura_extractor import (
        TRAFILATURA_AVAILABLE,
        is_valid_html,
        record_extraction,
    )
    from src.utils.trafilatura_extractor import (
        extract_with_fallback as _extract_with_fallback,
    )
    from src.utils.trafilatura_extractor import (
        extract_with_trafilatura as _central_extract,
    )

    # Keep trafilatura import for backward compatibility in type hints
    if TRAFILATURA_AVAILABLE:
        import trafilatura
except ImportError:
    TRAFILATURA_AVAILABLE = False
    _central_extract = None
    _extract_with_fallback = None
    is_valid_html = lambda x: True  # type: ignore
    record_extraction = lambda x, y: None  # type: ignore
    logger.warning("⚠️ [NEWS-RADAR] trafilatura_extractor not available, using raw text extraction")


# ============================================
# DATA MODELS
# ============================================


@dataclass
class RadarSource:
    """
    Configuration for a monitored source URL.

    Attributes:
        url: Source URL to monitor
        name: Human-readable name for the source
        priority: Scan priority (1=highest, higher numbers=lower priority)
        scan_interval_minutes: How often to scan this source
        navigation_mode: "single" for single page, "paginated" for multi-page
        link_selector: CSS selector for links in paginated mode
        last_scanned: Timestamp of last scan
        source_timezone: Timezone of the source (e.g., "Europe/London", "America/Sao_Paulo")
                        Used for timezone-aware scanning optimization

    Requirements: 1.1, 8.1, 8.4, 9.1
    """

    url: str
    name: str = ""
    priority: int = 1
    scan_interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES
    navigation_mode: str = "single"  # "single" or "paginated"
    link_selector: str | None = None
    last_scanned: datetime | None = None
    source_timezone: str | None = None  # V7.3: e.g., "Europe/London"

    def __post_init__(self):
        if not self.name:
            self.name = self.url[:50]

    def is_due_for_scan(self) -> bool:
        """
        Check if this source is due for scanning.

        V7.3: Considers timezone for off-peak optimization.
        """
        if self.last_scanned is None:
            return True

        # Calculate effective interval (may be extended during off-peak)
        effective_interval = self._get_effective_interval()

        elapsed = datetime.now(timezone.utc) - self.last_scanned
        return elapsed >= timedelta(minutes=effective_interval)

    def _get_effective_interval(self) -> int:
        """
        V7.3: Get effective scan interval based on source timezone.

        During off-peak hours (midnight-6am local time), extends interval
        to save resources since news is less likely to be published.

        V14.0: Enhanced timezone validation with specific logging for invalid timezones.

        Returns:
            Effective interval in minutes
        """
        if not self.source_timezone:
            return self.scan_interval_minutes

        try:
            # Try to get local hour for the source
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            tz = ZoneInfo(self.source_timezone)
            local_now = datetime.now(tz)
            local_hour = local_now.hour

            # Off-peak: midnight to 6am local time
            if 0 <= local_hour < 6:
                # Double the interval during off-peak
                return self.scan_interval_minutes * 2

            # Peak hours: normal interval
            return self.scan_interval_minutes

        except ZoneInfoNotFoundError:
            # Specific logging for invalid timezone
            logger.warning(
                f"⚠️ [NEWS-RADAR] Invalid timezone '{self.source_timezone}' for source '{self.name}'. "
                f"Using default interval ({self.scan_interval_minutes} min). "
                f"Valid timezone format: 'Europe/London', 'America/Sao_Paulo', etc."
            )
            return self.scan_interval_minutes
        except Exception as e:
            # Generic error handling for other timezone issues
            logger.warning(
                f"⚠️ [NEWS-RADAR] Error parsing timezone '{self.source_timezone}' for source '{self.name}': {e}. "
                f"Using default interval ({self.scan_interval_minutes} min)."
            )
            return self.scan_interval_minutes


@dataclass
class RadarAlert:
    """
    Alert to be sent to Telegram.

    V2.0: Enhanced with structured betting data.

    Attributes:
        source_name: Name of the source where news was found
        source_url: URL of the source
        affected_team: Team affected by the news
        opponent: Opponent team (if known)
        competition: League/cup name (if known)
        match_date: Match date (if known)
        category: Type of signal (MASS_ABSENCE, DECIMATED, YOUTH_TEAM, etc.)
        absent_count: Number of players unavailable
        absent_players: List of player names (if known)
        betting_impact: CRITICAL, HIGH, MEDIUM, LOW (validated in __post_init__)
        summary: Brief summary of the news (in Italian)
        confidence: Confidence score (0.0-1.0)
        discovered_at: Timestamp when news was discovered
        enrichment_context: Optional enrichment data from database (must have format_context_line() method)

    Requirements: 6.1, 6.2
    """

    source_name: str
    source_url: str
    affected_team: str
    category: str
    summary: str
    confidence: float
    # V2.0: New structured fields
    opponent: str | None = None
    competition: str | None = None
    match_date: str | None = None
    absent_count: int = 0
    absent_players: list[str] = field(default_factory=list)
    betting_impact: str = "MEDIUM"
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    enrichment_context: Any | None = None

    def __post_init__(self):
        """
        Validate and normalize fields after initialization.

        Ensures betting_impact is a valid value and enrichment_context has required method.
        """
        # Validate betting_impact
        VALID_BETTING_IMPACTS = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        if self.betting_impact not in VALID_BETTING_IMPACTS:
            logger.warning(
                f"⚠️ [RADAR-ALERT] Invalid betting_impact: '{self.betting_impact}', "
                f"valid values: {VALID_BETTING_IMPACTS}. Defaulting to MEDIUM."
            )
            # Use object.__setattr__ to bypass dataclass frozen field restriction
            object.__setattr__(self, "betting_impact", "MEDIUM")

        # Validate enrichment_context has format_context_line method
        if self.enrichment_context is not None:
            if not hasattr(self.enrichment_context, "format_context_line"):
                logger.warning(
                    f"⚠️ [RADAR-ALERT] enrichment_context does not have format_context_line() method. "
                    f"Type: {type(self.enrichment_context).__name__}. "
                    f"Enrichment context will not be displayed in alert."
                )

    def to_telegram_message(self) -> str:
        """
        Format alert as Telegram message in Italian.

        V2.0: Enhanced format with structured betting data.
        Uses 🔔 RADAR emoji to distinguish from main bot (🚨 EARLYBIRD).

        Requirements: 6.2, 6.3
        """
        # Get emoji and Italian category from prompts module
        emoji = CATEGORY_EMOJI.get(self.category, "📰")
        category_it = CATEGORY_ITALIAN.get(self.category, self.category)
        impact_emoji = BETTING_IMPACT_EMOJI.get(self.betting_impact, "")

        # Handle unknown team
        team_display = (
            self.affected_team
            if self.affected_team and self.affected_team != "Unknown"
            else "Da verificare"
        )

        # Build match info line
        match_info = ""
        if self.opponent:
            match_info = f"\n⚽ *Partita:* {team_display} vs {self.opponent}"
            if self.competition:
                match_info += f" ({self.competition})"
            if self.match_date:
                match_info += f"\n📅 *Data:* {self.match_date}"

        # Build absent players line
        absent_info = ""
        if self.absent_count > 0:
            absent_info = f"\n❌ *Assenti:* {self.absent_count} giocatori"
            if self.absent_players:
                # Show max 5 names
                names = self.absent_players[:5]
                if len(self.absent_players) > 5:
                    names.append(f"+{len(self.absent_players) - 5} altri")
                absent_info += f"\n   {', '.join(names)}"

        # Build enrichment line if available
        enrichment_line = ""
        if self.enrichment_context and hasattr(self.enrichment_context, "format_context_line"):
            context_str = self.enrichment_context.format_context_line()
            if context_str:
                enrichment_line = f"\n{context_str}"

        # V7.3: Build validation line (odds + cross-source)
        validation_line = ""
        validation_parts: list[str] = []

        # Add odds suffix if available
        if hasattr(self, "_odds_suffix") and self._odds_suffix:
            validation_parts.append(self._odds_suffix)

        # Add cross-source validation tag if available
        if hasattr(self, "_validation_tag") and self._validation_tag:
            validation_parts.append(self._validation_tag)

        if validation_parts:
            validation_line = f"\n{' | '.join(validation_parts)}"

        return (
            f"🔔 *RADAR ALERT* {emoji} {impact_emoji}\n\n"
            f"*Squadra:* {team_display}\n"
            f"*Categoria:* {category_it}"
            f"{match_info}"
            f"{absent_info}\n\n"
            f"📋 *Riepilogo:* {self.summary}"
            f"{enrichment_line}"
            f"{validation_line}\n\n"
            f"*Fonte:* {self.source_name}\n"
            f"🔗 {self.source_url}\n\n"
            f"_Impatto betting: {self.betting_impact} | Affidabilità: {self.confidence:.0%}_"
        )


# NOTE: AnalysisResult is now imported from src.utils.content_analysis


# ============================================
# SIGNAL CROSS-VALIDATION (V3.0)
# ============================================


def cross_validate_signals(
    signal_type: SignalType,
    deepseek_category: str,
    deepseek_absent_count: int,
    extracted_number: int | None = None,
) -> dict[str, Any]:
    """
    Intelligently cross-validate pattern-detected signal with DeepSeek analysis.

    V3.0: Implements intelligent two-level analysis coordination:
    - Validates consistency between signal_detector and DeepSeek
    - Makes intelligent decisions when there's disagreement
    - Adjusts confidence based on validation results
    - Preserves valuable context from both sources

    Args:
        signal_type: Signal type detected by pattern matching
        deepseek_category: Category returned by DeepSeek
        deepseek_absent_count: Absent count from DeepSeek
        extracted_number: Number extracted by pattern detector (optional)

    Returns:
        Dict with:
            - is_validated: bool - Whether signals are consistent
            - final_category: str - Final category decision
            - final_absent_count: int - Final absent count decision
            - confidence_adjustment: float - Adjustment to apply to confidence
            - validation_reason: str - Explanation of validation decision
            - validation_level: str - "HIGH", "MEDIUM", or "LOW" confidence
    """
    # Mapping from SignalType to DeepSeek categories
    SIGNAL_TO_CATEGORY = {
        SignalType.MASS_ABSENCE: "MASS_ABSENCE",
        SignalType.DECIMATED: "DECIMATED",
        SignalType.YOUTH_TEAM: "YOUTH_TEAM",
        SignalType.TURNOVER: "TURNOVER",
        SignalType.FINANCIAL_CRISIS: "FINANCIAL_CRISIS",
        SignalType.LOGISTICAL_CRISIS: "LOGISTICAL_CRISIS",
        SignalType.GOALKEEPER_OUT: "GOALKEEPER_OUT",
        SignalType.MOTIVATION: "MOTIVATION",
        SignalType.KEY_PLAYER: "LOW_VALUE",  # Key player alone is low value
        SignalType.CONFIRMED_LINEUP: "CONFIRMED_LINEUP",
        SignalType.NONE: "NOT_RELEVANT",
    }

    # Get expected category from signal type
    expected_category = SIGNAL_TO_CATEGORY.get(signal_type, "OTHER")

    # Case 1: Perfect agreement - HIGH confidence
    if expected_category == deepseek_category:
        # Validate absent count if available
        final_absent_count = deepseek_absent_count

        # Only boost confidence if they agree on a HIGH-VALUE signal, not on NOT_RELEVANT
        confidence_adjustment = 0.0 if deepseek_category == "NOT_RELEVANT" else 0.1

        # Use extracted_number if it's more specific
        if extracted_number is not None and signal_type == SignalType.MASS_ABSENCE:
            # If both sources agree on MASS_ABSENCE, use the more precise number
            if deepseek_absent_count == 0 or extracted_number > deepseek_absent_count:
                final_absent_count = extracted_number
                confidence_adjustment = 0.15  # Extra boost for precise data

        return {
            "is_validated": True,
            "final_category": deepseek_category,
            "final_absent_count": final_absent_count,
            "confidence_adjustment": confidence_adjustment,
            "validation_reason": f"✅ Perfect agreement: Pattern '{signal_type.value}' matches DeepSeek '{deepseek_category}'",
            "validation_level": "HIGH",
        }

    # Case 2: Related but different signals - MEDIUM confidence
    related_signals = {
        SignalType.MASS_ABSENCE: ["DECIMATED", "YOUTH_TEAM"],
        SignalType.DECIMATED: ["MASS_ABSENCE", "YOUTH_TEAM"],
        SignalType.YOUTH_TEAM: ["MASS_ABSENCE", "DECIMATED", "TURNOVER"],
        SignalType.TURNOVER: ["YOUTH_TEAM"],
    }

    if signal_type in related_signals and deepseek_category in related_signals[signal_type]:
        # Signals are related - make intelligent choice
        # Prefer DeepSeek for category, but consider signal type for context
        confidence_adjustment = 0.0  # No adjustment

        # If signal detected MASS_ABSENCE with a number, but DeepSeek says DECIMATED
        if signal_type == SignalType.MASS_ABSENCE and deepseek_category == "DECIMATED":
            if extracted_number is not None and extracted_number >= 5:
                # Strong evidence for MASS_ABSENCE - override DeepSeek
                return {
                    "is_validated": True,
                    "final_category": "MASS_ABSENCE",
                    "final_absent_count": extracted_number,
                    "confidence_adjustment": 0.05,
                    "validation_reason": f"🔄 Related signals: Pattern '{signal_type.value}' (n={extracted_number}) overrides DeepSeek '{deepseek_category}' due to strong evidence",
                    "validation_level": "MEDIUM",
                }

        # Default to DeepSeek for related signals
        return {
            "is_validated": True,
            "final_category": deepseek_category,
            "final_absent_count": deepseek_absent_count,
            "confidence_adjustment": 0.0,
            "validation_reason": f"🔄 Related signals: Pattern '{signal_type.value}' and DeepSeek '{deepseek_category}' are consistent",
            "validation_level": "MEDIUM",
        }

    # Case 3: Disagreement - LOW confidence, need intelligent resolution
    # Check if one source has stronger evidence
    if signal_type != SignalType.NONE and deepseek_category != "NOT_RELEVANT":
        # Both detected something, but different - analyze evidence strength

        # If pattern detector has extracted number, it has strong evidence
        if extracted_number is not None and extracted_number >= 3:
            # Pattern detector has strong numerical evidence
            return {
                "is_validated": False,
                "final_category": expected_category,
                "final_absent_count": extracted_number,
                "confidence_adjustment": -0.1,  # Reduce confidence due to disagreement
                "validation_reason": f"⚠️ Disagreement: Pattern '{signal_type.value}' (n={extracted_number}) vs DeepSeek '{deepseek_category}'. Using pattern due to strong numerical evidence.",
                "validation_level": "LOW",
            }

        # If DeepSeek detected high-value signal but pattern didn't
        if deepseek_category in ["MASS_ABSENCE", "DECIMATED", "YOUTH_TEAM", "TURNOVER"]:
            # DeepSeek might be more nuanced - trust it
            return {
                "is_validated": False,
                "final_category": deepseek_category,
                "final_absent_count": deepseek_absent_count,
                "confidence_adjustment": -0.05,
                "validation_reason": f"⚠️ Disagreement: Pattern '{signal_type.value}' vs DeepSeek '{deepseek_category}'. Using DeepSeek due to high-value detection.",
                "validation_level": "LOW",
            }

        # Default: prefer pattern detector for specific signals
        if signal_type in [
            SignalType.MASS_ABSENCE,
            SignalType.GOALKEEPER_OUT,
            SignalType.KEY_PLAYER,
        ]:
            return {
                "is_validated": False,
                "final_category": expected_category,
                "final_absent_count": extracted_number
                if extracted_number is not None
                else deepseek_absent_count,
                "confidence_adjustment": -0.15,  # Significant reduction
                "validation_reason": f"⚠️ Disagreement: Pattern '{signal_type.value}' vs DeepSeek '{deepseek_category}'. Using pattern due to specific signal detection.",
                "validation_level": "LOW",
            }

    # Case 4: Pattern detected but DeepSeek says NOT_RELEVANT
    if signal_type != SignalType.NONE and deepseek_category == "NOT_RELEVANT":
        # Pattern detector found something DeepSeek missed
        if extracted_number is not None and extracted_number >= 3:
            # Strong evidence - override DeepSeek
            return {
                "is_validated": False,
                "final_category": expected_category,
                "final_absent_count": extracted_number,
                "confidence_adjustment": -0.05,
                "validation_reason": f"🔍 DeepSeek missed: Pattern '{signal_type.value}' (n={extracted_number}) overrides DeepSeek 'NOT_RELEVANT' due to strong evidence",
                "validation_level": "MEDIUM",
            }

        # Pattern detected but weak evidence - trust DeepSeek
        return {
            "is_validated": True,
            "final_category": "NOT_RELEVANT",
            "final_absent_count": 0,
            "confidence_adjustment": 0.0,
            "validation_reason": f"✅ DeepSeek correct: Pattern '{signal_type.value}' overridden by DeepSeek 'NOT_RELEVANT' due to weak evidence",
            "validation_level": "HIGH",
        }

    # Case 5: DeepSeek detected but pattern didn't
    if signal_type == SignalType.NONE and deepseek_category != "NOT_RELEVANT":
        # DeepSeek found something pattern detector missed
        if deepseek_category in ["MASS_ABSENCE", "DECIMATED", "YOUTH_TEAM", "TURNOVER"]:
            # High-value signal - trust DeepSeek
            return {
                "is_validated": True,
                "final_category": deepseek_category,
                "final_absent_count": deepseek_absent_count,
                "confidence_adjustment": 0.0,
                "validation_reason": f"🔍 Pattern missed: DeepSeek '{deepseek_category}' overrides pattern 'NONE' due to high-value detection",
                "validation_level": "MEDIUM",
            }

        # Low-value signal - trust pattern detector
        return {
            "is_validated": True,
            "final_category": "NOT_RELEVANT",
            "final_absent_count": 0,
            "confidence_adjustment": 0.0,
            "validation_reason": f"✅ Pattern correct: DeepSeek '{deepseek_category}' overridden by pattern 'NONE' due to low-value detection",
            "validation_level": "HIGH",
        }

    # Default: both agree it's not relevant
    # Only boost confidence if they agree on a HIGH-VALUE signal, not on NOT_RELEVANT
    confidence_adj = 0.0 if deepseek_category == "NOT_RELEVANT" else 0.1
    return {
        "is_validated": True,
        "final_category": "NOT_RELEVANT",
        "final_absent_count": 0,
        "confidence_adjustment": confidence_adj,
        "validation_reason": f"✅ Both agree: Pattern '{signal_type.value}' and DeepSeek '{deepseek_category}'",
        "validation_level": "HIGH",
    }


@dataclass
class GlobalSettings:
    """Global settings for News Radar."""

    default_scan_interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES
    page_timeout_seconds: int = DEFAULT_PAGE_TIMEOUT_SECONDS
    cache_ttl_hours: int = DEFAULT_CACHE_TTL_HOURS
    deepseek_confidence_threshold: float = DEEPSEEK_CONFIDENCE_THRESHOLD
    alert_confidence_threshold: float = ALERT_CONFIDENCE_THRESHOLD
    navigation_delay_seconds: int = DEFAULT_NAVIGATION_DELAY_SECONDS
    max_links_per_paginated_source: int = DEFAULT_MAX_LINKS_PER_PAGINATED


@dataclass
class RadarConfig:
    """Complete News Radar configuration."""

    sources: list[RadarSource] = field(default_factory=list)
    global_settings: GlobalSettings = field(default_factory=GlobalSettings)


# ============================================
# CONTENT CACHE (Deduplication)
# ============================================


class ContentCache:
    """
    Hash-based content cache for deduplication.

    Uses first 1000 chars of content to compute hash.
    Implements LRU eviction when max entries exceeded.
    Entries expire after TTL hours.

    Requirements: 7.1, 7.2, 7.3, 7.4
    """

    def __init__(
        self, max_entries: int = DEFAULT_CACHE_MAX_ENTRIES, ttl_hours: int = DEFAULT_CACHE_TTL_HOURS
    ):
        self._cache: OrderedDict[str, datetime] = OrderedDict()
        self._max_entries = max_entries
        self._ttl_hours = ttl_hours
        self._lock = (
            asyncio.Lock()
        )  # V13.0 COVE FIX: Thread-safe cache operations for async concurrent access

    def compute_hash(self, content: str) -> str:
        """
        Compute hash from first 1000 chars of content.

        Requirements: 7.1

        Phase 1 Critical Fix: Changed errors='ignore' to errors='replace' to preserve
        special characters. Added Unicode normalization before hashing.
        """
        content_prefix = content[:1000] if len(content) > 1000 else content
        # Phase 1 Critical Fix: Use errors='replace' instead of 'ignore' to preserve special characters
        # Phase 1 Critical Fix: Add Unicode normalization before hashing
        return hashlib.sha256(content_prefix.encode("utf-8", errors="replace")).hexdigest()[:16]

    async def is_cached(self, content: str) -> bool:
        """
        Check if content hash exists and is not expired.

        Requirements: 7.2, 7.4
        V13.0 COVE FIX: Made async to use asyncio.Lock for thread safety
        """
        if not content:
            return False

        content_hash = self.compute_hash(content)

        async with self._lock:
            if content_hash not in self._cache:
                return False

            # Check expiration
            cached_at = self._cache[content_hash]
            if datetime.now(timezone.utc) - cached_at > timedelta(hours=self._ttl_hours):
                del self._cache[content_hash]
                return False

            # Move to end (LRU)
            self._cache.move_to_end(content_hash)
            return True

    async def add(self, content: str) -> None:
        """
        Store content hash with current timestamp.

        Requirements: 7.3
        V13.0 COVE FIX: Made async to use asyncio.Lock for thread safety
        """
        if not content:
            return

        content_hash = self.compute_hash(content)

        async with self._lock:
            # Evict oldest if at capacity
            while len(self._cache) >= self._max_entries:
                self._cache.popitem(last=False)

            self._cache[content_hash] = datetime.now(timezone.utc)

    async def evict_expired(self) -> int:
        """
        Remove all expired entries. Returns count of evicted entries.
        V13.0 COVE FIX: Made async to use asyncio.Lock for thread safety
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            expired = [
                h for h, ts in self._cache.items() if now - ts > timedelta(hours=self._ttl_hours)
            ]
            for h in expired:
                del self._cache[h]
            return len(expired)

    async def size(self) -> int:
        """
        Return current cache size.
        V13.0 COVE FIX: Made async to use asyncio.Lock for thread safety
        """
        async with self._lock:
            return len(self._cache)

    def size_sync(self) -> int:
        """
        Return current cache size (synchronous version for non-async contexts).
        V13.0 COVE FIX: Added synchronous version for get_stats() and other non-async contexts

        Note: While len() is atomic in Python (single bytecode operation), it may return
        stale/inconsistent values during concurrent modifications. This is acceptable for
        logging/stats purposes, but for critical decisions, use the async size() method
        with proper locking.
        """
        return len(self._cache)

    async def clear(self) -> None:
        """
        Clear all cache entries.
        V13.0 COVE FIX: Made async to use asyncio.Lock for thread safety
        """
        async with self._lock:
            self._cache.clear()


# ============================================
# CIRCUIT BREAKER
# ============================================


class CircuitBreaker:
    """
    Circuit Breaker pattern for per-source failure handling.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Source is failing, skip requests for recovery_timeout
    - HALF_OPEN: Testing if source recovered, allow one request
    - COOLDOWN: Source hit max_retries, long cooldown before retrying (V12.4)

    V12.4 FIX: "Ending News Source Atrophy"
    NO news domain is ever permanently blacklisted. After max_retries (20),
    the source enters a COOLDOWN state (4 hours) and then auto-recovers to HALF_OPEN.
    After the cooldown, the counter resets and the source goes to HALF_OPEN
    for another attempt. The bot is "Relentless."

    Requirements: 1.4
    VPS FIX: Added max_retries to prevent infinite retry loops
    """

    # V12.4: Cooldown duration after hitting max_retries (4 hours)
    COOLDOWN_SECONDS = 4 * 3600

    def __init__(
        self,
        failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: int = CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
        max_retries: int = CIRCUIT_BREAKER_MAX_RETRIES,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.max_retries = max_retries
        self.failure_count = 0
        self.total_attempts = 0  # VPS FIX: Track total attempts across all cycles
        self.last_failure_time: float | None = None
        self.state = "CLOSED"

    def can_execute(self) -> bool:
        """Check if request should be allowed."""
        # V12.4: Sources are NEVER permanently blacklisted - COOLDOWN auto-recovers after 4h
        if self.state == "COOLDOWN":
            # Check if cooldown period has elapsed
            if (
                self.last_failure_time
                and (time.time() - self.last_failure_time) > self.COOLDOWN_SECONDS
            ):
                logger.info(
                    f"🔄 [CIRCUIT-BREAKER] Source COOLDOWN elapsed ({self.COOLDOWN_SECONDS / 3600:.0f}h). "
                    f"Resetting counters and transitioning to HALF_OPEN for retry."
                )
                self.total_attempts = 0
                self.failure_count = 0
                self.state = "HALF_OPEN"
                return True
            logger.debug(
                f"🧊 [CIRCUIT-BREAKER] Source in COOLDOWN (will retry after {self.COOLDOWN_SECONDS / 3600:.0f}h). "
                f"Elapsed: {(time.time() - self.last_failure_time) / 3600:.1f}h"
            )
            return False

        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            if (
                self.last_failure_time
                and (time.time() - self.last_failure_time) > self.recovery_timeout
            ):
                self.state = "HALF_OPEN"
                logger.debug("🔄 [CIRCUIT-BREAKER] Transitioning to HALF_OPEN")
                return True
            return False

        if self.state == "HALF_OPEN":
            return True

        return False

    def record_success(self) -> None:
        """Record a successful request."""
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self.failure_count = 0
            logger.info("✅ [CIRCUIT-BREAKER] Circuit CLOSED (recovered)")
        elif self.state == "CLOSED":
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed request."""
        self.failure_count += 1
        self.total_attempts += 1  # VPS FIX: Track total attempts
        self.last_failure_time = time.time()

        # V12.4: Use COOLDOWN with auto-reset instead of permanent blacklisting
        if self.total_attempts >= self.max_retries:
            self.state = "COOLDOWN"
            logger.warning(
                f"🧊 [CIRCUIT-BREAKER] Source entering COOLDOWN after {self.total_attempts} total attempts "
                f"(max_retries={self.max_retries}). Will retry in {self.COOLDOWN_SECONDS / 3600:.0f}h. "
                f"NO source is permanently blacklisted."
            )
            return

        if self.state == "HALF_OPEN":
            self.state = "OPEN"
            logger.warning(
                f"⚠️ [CIRCUIT-BREAKER] Circuit OPEN (failed in HALF_OPEN). "
                f"Total attempts: {self.total_attempts}/{self.max_retries}"
            )
        elif self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                f"🔴 [CIRCUIT-BREAKER] Circuit OPEN after {self.failure_count} failures. "
                f"Total attempts: {self.total_attempts}/{self.max_retries}"
            )

    def get_state(self) -> dict[str, Any]:
        """Get circuit breaker state for stats."""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "total_attempts": self.total_attempts,  # VPS FIX: Include total attempts
            "max_retries": self.max_retries,  # VPS FIX: Include max_retries
            "last_failure": self.last_failure_time,
        }


# ============================================
# EXCLUSION FILTER & RELEVANCE ANALYZER
# ============================================
# NOTE: ExclusionFilter and RelevanceAnalyzer are now imported from
# src.utils.content_analysis for DRY compliance and shared usage with browser_monitor.


# ============================================
# CONFIG LOADING
# ============================================


def load_config(config_file: str = DEFAULT_CONFIG_FILE) -> RadarConfig:
    """
    Load News Radar configuration from JSON file.

    Requirements: 1.1, 8.1, 8.3
    """
    config_path = Path(config_file)

    if not config_path.exists():
        logger.warning(f"⚠️ [NEWS-RADAR] Config file not found: {config_file}")
        return RadarConfig()

    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)

        # Parse global settings
        gs_data = data.get("global_settings", {})
        global_settings = GlobalSettings(
            default_scan_interval_minutes=gs_data.get(
                "default_scan_interval_minutes", DEFAULT_SCAN_INTERVAL_MINUTES
            ),
            page_timeout_seconds=gs_data.get("page_timeout_seconds", DEFAULT_PAGE_TIMEOUT_SECONDS),
            cache_ttl_hours=gs_data.get("cache_ttl_hours", DEFAULT_CACHE_TTL_HOURS),
            deepseek_confidence_threshold=gs_data.get(
                "deepseek_confidence_threshold", DEEPSEEK_CONFIDENCE_THRESHOLD
            ),
            alert_confidence_threshold=gs_data.get(
                "alert_confidence_threshold", ALERT_CONFIDENCE_THRESHOLD
            ),
            navigation_delay_seconds=gs_data.get(
                "navigation_delay_seconds", DEFAULT_NAVIGATION_DELAY_SECONDS
            ),
            max_links_per_paginated_source=gs_data.get(
                "max_links_per_paginated_source", DEFAULT_MAX_LINKS_PER_PAGINATED
            ),
        )

        # Parse sources
        sources: list[RadarSource] = []
        for src_data in data.get("sources", []):
            # Skip sources without required 'url' field
            if "url" not in src_data:
                logger.warning(f"⚠️ [NEWS-RADAR] Skipping source without URL: {src_data}")
                continue

            source = RadarSource(
                url=src_data["url"],
                name=src_data.get("name", src_data["url"][:50]),
                priority=src_data.get("priority", 1),
                scan_interval_minutes=src_data.get(
                    "scan_interval_minutes", global_settings.default_scan_interval_minutes
                ),
                navigation_mode=src_data.get("navigation_mode", "single"),
                link_selector=src_data.get("link_selector"),
                source_timezone=src_data.get("source_timezone"),  # V7.3: timezone-aware scanning
            )
            sources.append(source)

        logger.info(f"✅ [NEWS-RADAR] Loaded {len(sources)} sources from {config_file}")
        return RadarConfig(sources=sources, global_settings=global_settings)

    except json.JSONDecodeError as e:
        logger.error(f"❌ [NEWS-RADAR] Invalid JSON in config: {e}")
        return RadarConfig()
    except Exception as e:
        logger.error(f"❌ [NEWS-RADAR] Failed to load config: {e}")
        return RadarConfig()


def load_config_from_supabase() -> RadarConfig:
    """
    Load News Radar configuration from Supabase database.

    Fetches news sources from the news_sources table and filters for
    traditional web domains only (excluding social media handles).

    Returns:
        RadarConfig with web-only sources from Supabase
    """
    import time

    try:
        from src.database.supabase_provider import SupabaseProvider

        logger.info("🔄 [NEWS-RADAR] Initializing Supabase provider...")
        start = time.time()
        provider = SupabaseProvider()
        init_time = time.time() - start
        logger.info(f"✅ [NEWS-RADAR] SupabaseProvider initialized in {init_time:.2f}s")

        if not provider.is_connected():
            logger.error(
                f"❌ [NEWS-RADAR] Supabase connection failed: {provider.get_connection_error()}"
            )
            return RadarConfig()

        logger.info("✅ [NEWS-RADAR] Supabase connected, fetching news sources...")
        start = time.time()
        all_sources = provider.fetch_all_news_sources()
        fetch_time = time.time() - start
        logger.info(f"✅ [NEWS-RADAR] Fetched {len(all_sources)} sources in {fetch_time:.2f}s")

        if not all_sources:
            logger.warning("⚠️ [NEWS-RADAR] No news sources found in Supabase")
            return RadarConfig()

        # Filter for web-only sources (exclude social media handles)
        web_sources: list[RadarSource] = []
        social_domains = {
            "twitter.com",
            "x.com",
            "t.me",
            "telegram.org",
            "telegram.me",
            "facebook.com",
            "instagram.com",
            "linkedin.com",
            "tiktok.com",
            "youtube.com",
            "reddit.com",
            "threads.net",
        }

        for src_data in all_sources:
            # V8.0: Handle both 'url' and 'domain' fields
            # Supabase news_sources table uses 'domain' field
            domain = src_data.get("domain", "")
            url = src_data.get("url", "")

            # If no URL but domain exists, construct URL from domain
            if not url and domain:
                # Add https:// prefix if not present
                if not domain.startswith("http"):
                    url = f"https://{domain}"
                else:
                    url = domain
            elif not url and not domain:
                logger.warning(f"⚠️ [NEWS-RADAR] Skipping source without URL/domain: {src_data}")
                continue

            # Parse URL to check if it's a social media domain
            try:
                from urllib.parse import urlparse

                parsed = urlparse(url)
                domain = parsed.netloc.lower()

                # Skip if it's a social media domain
                if any(social_domain in domain for social_domain in social_domains):
                    logger.debug(f"🚫 [NEWS-RADAR] Skipping social media source: {url}")
                    continue

                # Also skip if the URL contains social media handle patterns
                if any(pattern in url.lower() for pattern in ["twitter.com/", "x.com/", "t.me/"]):
                    logger.debug(f"🚫 [NEWS-RADAR] Skipping social media handle: {url}")
                    continue

            except Exception as e:
                logger.debug(f"⚠️ [NEWS-RADAR] Failed to parse URL {url}: {e}")
                continue

            # V14.0: Validate critical fields before creating RadarSource
            # This prevents unexpected behavior with invalid data from Supabase

            # Validate URL (already validated above, but double-check)
            if not url or not url.startswith(("http://", "https://")):
                logger.warning(
                    f"⚠️ [NEWS-RADAR] Skipping source with invalid URL: {url} (data: {src_data})"
                )
                continue

            # Validate priority (must be positive integer)
            priority = src_data.get("priority", 1)
            if not isinstance(priority, int) or priority < 1:
                logger.warning(
                    f"⚠️ [NEWS-RADAR] Invalid priority '{priority}' for {url}, using default 1"
                )
                priority = 1

            # Validate scan_interval_minutes (must be positive integer, min 1)
            scan_interval = src_data.get("scan_interval_minutes", DEFAULT_SCAN_INTERVAL_MINUTES)
            if not isinstance(scan_interval, int) or scan_interval < 1:
                logger.warning(
                    f"⚠️ [NEWS-RADAR] Invalid scan_interval_minutes '{scan_interval}' for {url}, "
                    f"using default {DEFAULT_SCAN_INTERVAL_MINUTES}"
                )
                scan_interval = DEFAULT_SCAN_INTERVAL_MINUTES

            # Validate navigation_mode (must be "single" or "paginated")
            navigation_mode = src_data.get("navigation_mode", "single")
            if navigation_mode not in ("single", "paginated"):
                logger.warning(
                    f"⚠️ [NEWS-RADAR] Invalid navigation_mode '{navigation_mode}' for {url}, "
                    f"using default 'single'"
                )
                navigation_mode = "single"

            # Create RadarSource from validated Supabase data
            source = RadarSource(
                url=url,
                name=src_data.get("name", url[:50]),
                priority=priority,
                scan_interval_minutes=scan_interval,
                navigation_mode=navigation_mode,
                link_selector=src_data.get("link_selector"),
                source_timezone=src_data.get("source_timezone"),
            )
            web_sources.append(source)

        logger.info(
            f"✅ [NEWS-RADAR] Loaded {len(web_sources)} web sources from Supabase (filtered from {len(all_sources)} total)"
        )
        return RadarConfig(sources=web_sources, global_settings=GlobalSettings())

    except ImportError:
        logger.error(
            "❌ [NEWS-RADAR] SupabaseProvider not available - falling back to default config"
        )
        return RadarConfig()
    except Exception as e:
        logger.error(f"❌ [NEWS-RADAR] Failed to load config from Supabase: {e}")
        return RadarConfig()


# ============================================
# CONTENT EXTRACTOR
# ============================================


class ContentExtractor:
    """
    Extracts clean text from web pages.

    Uses hybrid approach:
    1. HTTP + Trafilatura (fast, works for ~80% of sites)
    2. Playwright fallback with stealth mode (slower, ~95% success)

    V1.3: Added browser lock for race condition protection

    Requirements: 2.1, 2.2, 2.3, 2.4
    """

    def __init__(self, page_timeout: int = DEFAULT_PAGE_TIMEOUT_SECONDS):
        self._page_timeout = page_timeout
        self._playwright = None
        self._browser = None
        self._browser_lock: asyncio.Lock | None = None  # V1.3: Lock for browser recreation

        # V13.1: Scrapling-based stealth extractor (WAF bypass)
        self._article_reader = None
        if _ARTICLE_READER_AVAILABLE and _ArticleReader is not None:
            try:
                self._article_reader = _ArticleReader()
                logger.debug("✅ [NEWS-RADAR] ArticleReader initialized for stealth extraction")
            except Exception as e:
                logger.warning(f"⚠️ [NEWS-RADAR] ArticleReader init failed: {e}")
                self._article_reader = None

        # Stats
        self._http_extractions = 0
        self._browser_extractions = 0
        self._failed_extractions = 0
        self._waf_bypasses = 0  # V13.1: Track WAF bypass successes

    def _diagnose_playwright_installation(self) -> dict:
        """
        Diagnose Playwright installation status.

        Checks:
        - Playwright Python package installation
        - Chromium browser binaries
        - System dependencies

        Returns dict with diagnostic results.
        """
        diagnostics = {
            "playwright_installed": False,
            "chromium_binaries_installed": False,
            "system_dependencies_installed": False,
            "details": [],
        }

        # Check Playwright Python package
        try:
            import playwright

            diagnostics["playwright_installed"] = True
            # V12.5: Add error handling for version access (COVE FIX 2026-03-04)
            # Playwright 1.58.0 removed __version__ from main module
            try:
                version = playwright.__version__
                diagnostics["details"].append(f"✅ Playwright v{version} installed")
            except AttributeError:
                # Fallback: try to get version from _repo_version
                try:
                    from playwright._repo_version import __version__

                    diagnostics["details"].append(f"✅ Playwright v{__version__} installed")
                except (ImportError, AttributeError):
                    diagnostics["details"].append("✅ Playwright installed (version unknown)")
        except ImportError:
            diagnostics["details"].append("❌ Playwright Python package not installed")
            return diagnostics

        # Check Chromium binaries using subprocess
        try:
            result = subprocess.run(
                ["python", "-m", "playwright", "install", "--dry-run", "chromium"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                diagnostics["chromium_binaries_installed"] = True
                diagnostics["details"].append("✅ Chromium browser binaries installed")
            else:
                diagnostics["details"].append(
                    "❌ Chromium binaries not installed (run: python -m playwright install chromium)"
                )
        except subprocess.TimeoutExpired:
            diagnostics["details"].append("⚠️ Timeout checking Chromium binaries")
        except Exception as e:
            diagnostics["details"].append(f"⚠️ Error checking Chromium binaries: {e}")

        # Check system dependencies using subprocess
        try:
            result = subprocess.run(
                ["python", "-m", "playwright", "install-deps", "--dry-run", "chromium"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                diagnostics["system_dependencies_installed"] = True
                diagnostics["details"].append("✅ System dependencies installed")
            else:
                diagnostics["details"].append(
                    "❌ System dependencies not installed (run: python -m playwright install-deps chromium)"
                )
        except subprocess.TimeoutExpired:
            diagnostics["details"].append("⚠️ Timeout checking system dependencies")
        except Exception as e:
            diagnostics["details"].append(f"⚠️ Error checking system dependencies: {e}")

        return diagnostics

    async def initialize(self) -> bool:
        """
        Initialize Playwright browser (optional).

        V7.4: Now returns True even without Playwright - HTTP-only mode is supported.
        Playwright is optional and provides fallback for JS-heavy sites.
        V13.0: Added diagnostic logging for Playwright installation status.

        Returns True if initialized successfully (HTTP-only or with Playwright).
        """
        # Run diagnostics before attempting initialization
        logger.info("🔍 [NEWS-RADAR] Running Playwright diagnostics...")
        diagnostics = self._diagnose_playwright_installation()
        for detail in diagnostics["details"]:
            logger.info(f"   {detail}")

        try:
            from playwright.async_api import async_playwright

            logger.info("🌐 [NEWS-RADAR] Launching Playwright...")
            self._playwright = await async_playwright().start()

            # V1.3: Removed --single-process (causes instability on heavy sites)
            # Chromium with --single-process crashes frequently on ads/JS-heavy pages
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                    "--no-sandbox",
                    "--disable-extensions",
                ],
            )

            logger.info("✅ [NEWS-RADAR] Playwright initialized")

            # V1.3: Initialize browser lock for race condition protection
            self._browser_lock = asyncio.Lock()

            return True

        except ImportError:
            # V7.4: Playwright is optional - HTTP-only mode works for most sites
            logger.warning("⚠️ [NEWS-RADAR] Playwright not installed - running in HTTP-only mode")
            logger.info("   HTTP + Trafilatura will be used for content extraction")
            logger.info(
                "   To enable browser extraction: pip install playwright && python -m playwright install chromium"
            )
            return True  # Continue without Playwright
        except Exception as e:
            logger.error(
                f"❌ [NEWS-RADAR] Failed to initialize Playwright: {type(e).__name__}: {e}"
            )
            logger.debug(f"   Traceback:\n{traceback.format_exc()}")
            logger.info("   Troubleshooting:")
            logger.info(
                "   1. Check if Chromium binaries are installed: python -m playwright install chromium"
            )
            logger.info(
                "   2. Check system dependencies: python -m playwright install-deps chromium"
            )
            logger.info("   3. Verify VPS resources (CPU, RAM)")
            return False

    async def shutdown(self) -> None:
        """Shutdown Playwright and release resources."""
        # V13.1: Close ArticleReader
        if self._article_reader:
            try:
                await self._article_reader.close()
            except Exception as e:
                logger.debug(f"⚠️ [NEWS-RADAR] Error closing ArticleReader: {e}")
            self._article_reader = None

        # V9.0: Explicit cleanup of browser contexts if they exist
        if hasattr(self, "_contexts") and self._contexts:
            for context in self._contexts:
                try:
                    await context.close()
                except Exception as e:
                    logger.warning(f"⚠️ [NEWS-RADAR] Error closing browser context: {e}")
            self._contexts.clear()

        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.warning(f"⚠️ [NEWS-RADAR] Error closing browser: {e}")
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.warning(f"⚠️ [NEWS-RADAR] Error stopping Playwright: {e}")
            self._playwright = None

    async def _ensure_browser_connected(self) -> bool:
        """
        V1.3: Ensure browser is connected, recreate if disconnected.

        This fixes the critical bug where the browser crashes/disconnects
        but self._browser is not None, causing TargetClosedError on new_page().

        V1.3: Uses asyncio.Lock to serialize browser recreation across coroutines.
        V13.0: Added detailed logging with traceback for debugging.

        Returns:
            True if browser is available and connected, False otherwise
        """
        # V1.3: Use lock to serialize browser recreation
        if self._browser_lock is None:
            self._browser_lock = asyncio.Lock()

        async with self._browser_lock:
            # Re-check after acquiring lock (another coroutine might have fixed it)
            if self._browser and self._browser.is_connected():
                return True

            # Case 1: No browser at all
            if not self._browser:
                logger.warning("⚠️ [NEWS-RADAR] Browser is None, attempting to recreate...")
                return await self._recreate_browser_internal()

            # Case 2: Browser exists but is disconnected
            try:
                if not self._browser.is_connected():
                    logger.warning("⚠️ [NEWS-RADAR] Browser disconnected, recreating...")
                    return await self._recreate_browser_internal()
            except Exception as e:
                # is_connected() itself failed - browser is in bad state
                logger.error(f"❌ [NEWS-RADAR] Browser state check failed: {type(e).__name__}: {e}")
                logger.debug(f"   Traceback:\n{traceback.format_exc()}")
                logger.warning("⚠️ [NEWS-RADAR] Browser in bad state, attempting to recreate...")
                return await self._recreate_browser_internal()

            return True

    async def _recreate_browser_internal(self) -> bool:
        """
        V1.3: Internal browser recreation (called with lock held).

        Safely closes existing resources and reinitializes Playwright.
        IMPORTANT: This method assumes the caller holds self._browser_lock.
        V13.0: Added detailed logging with traceback for debugging.

        Returns:
            True if browser was successfully recreated
        """
        logger.info("🔄 [NEWS-RADAR] Recreating browser...")

        # Clean up existing browser (if any)
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.debug(f"⚠️ [NEWS-RADAR] Error closing existing browser: {e}")
            self._browser = None

        # Recreate browser using existing playwright instance
        if self._playwright:
            try:
                # V1.3: Removed --single-process (causes instability on heavy sites)
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                        "--disable-setuid-sandbox",
                        "--no-sandbox",
                        "--disable-extensions",
                    ],
                )
                logger.info("✅ [NEWS-RADAR] Browser recreated successfully")
                return True
            except Exception as e:
                logger.error(f"❌ [NEWS-RADAR] Failed to recreate browser: {type(e).__name__}: {e}")
                logger.debug(f"   Traceback:\n{traceback.format_exc()}")
                logger.warning("⚠️ [NEWS-RADAR] Attempting full reinitialization...")
                # Try full reinitialization
                await self.shutdown()
                return await self.initialize()
        else:
            # No playwright instance, do full initialization
            logger.warning(
                "⚠️ [NEWS-RADAR] No Playwright instance, attempting full initialization..."
            )
            return await self.initialize()

    def _extract_with_trafilatura(self, html: str) -> str | None:
        """
        Extract clean article text using Trafilatura with intelligent fallback.

        V8.5: Fixed to avoid duplicate trafilatura calls.
        Now uses centralized extract_with_fallback() which includes:
        - Pre-validation to avoid "discarding data: None" warnings
        - Intelligent fallback chain (trafilatura → regex → raw)
        - Proper failure recording for all methods

        Requirements: 2.1
        """
        if not TRAFILATURA_AVAILABLE or not html:
            return None

        # V8.5: Use centralized extractor with full fallback chain
        # This eliminates duplicate trafilatura calls (was calling _central_extract
        # and then _extract_with_fallback which also calls trafilatura)
        if _extract_with_fallback is not None:
            text, method = _extract_with_fallback(html)
            if text:
                logger.debug(f"[NEWS-RADAR] Extraction succeeded: {method}")
                return text
            return None

        # Legacy fallback if centralized extractor not available
        try:
            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
                favor_precision=True,
            )

            if text and len(text) > 100:
                return text

            return None

        except Exception as e:
            logger.debug(f"⚠️ [NEWS-RADAR] Trafilatura extraction failed: {e}")
            return None

    async def _extract_with_http(self, url: str) -> str | None:
        """
        Try to extract content using HTTP with WAF bypass.

        V8.1: Uses centralized HTTP client with rate limiting to prevent bans.
        V13.1: Uses ArticleReader (Scrapling) for TLS fingerprint impersonation
               and automatic WAF bypass. Falls back to standard httpx if unavailable.

        Strategy:
        1. Scrapling AsyncFetcher (HTTP with TLS impersonation) - fastest, bypasses most WAFs
        2. Scrapling Fetcher (browser impersonation) - for stubborn WAF blocks
        3. Standard httpx (legacy fallback) - if Scrapling unavailable

        Requirements: 2.1
        """
        # V13.1: Primary path - Scrapling-based stealth extraction
        if self._article_reader is not None:
            try:
                result = await self._article_reader.fetch_and_extract(url, timeout=HTTP_TIMEOUT)
                if result["success"] and result["text"]:
                    text = result["text"]
                    if len(text) > HTTP_MIN_CONTENT_LENGTH:
                        method = result["method"]
                        if method == "browser":
                            self._waf_bypasses += 1
                            self._browser_extractions += 1
                            logger.info(
                                f"🛡️ [NEWS-RADAR] WAF bypass via Scrapling browser: {url[:40]}..."
                            )
                        else:
                            self._http_extractions += 1
                            logger.debug(f"⚡ [NEWS-RADAR] Scrapling HTTP success: {url[:40]}...")
                        return text
                    logger.debug(
                        f"⚠️ [NEWS-RADAR] Scrapling extracted too short "
                        f"({len(result['text'])} chars): {url[:40]}..."
                    )
                else:
                    status_info = ""
                    logger.debug(
                        f"⚠️ [NEWS-RADAR] Scrapling extraction failed{status_info}: {url[:40]}..."
                    )
            except Exception as e:
                logger.debug(f"⚠️ [NEWS-RADAR] Scrapling error: {e}")

        # V13.1: Legacy fallback - standard httpx (no WAF bypass)
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }

            http_client = get_http_client()
            response = await asyncio.to_thread(
                http_client.get_sync,
                url,
                rate_limit_key="news_radar",
                use_fingerprint=False,
                timeout=HTTP_TIMEOUT,
                headers=headers,
            )

            if response.status_code in WAF_BLOCK_CODES:
                logger.warning(
                    f"🛡️ [NEWS-RADAR] WAF block ({response.status_code}) from "
                    f"{url.split('//')[1].split('/')[0] if '//' in url else url[:30]}"
                )
                return None

            if response.status_code != 200:
                return None

            html = response.text
            text = self._extract_with_trafilatura(html)

            if text and len(text) > HTTP_MIN_CONTENT_LENGTH:
                self._http_extractions += 1
                logger.debug(f"⚡ [NEWS-RADAR] HTTP extraction success: {url[:40]}...")
                return text

            return None

        except Exception as e:
            logger.debug(f"⚠️ [NEWS-RADAR] HTTP extraction failed: {e}")
            return None

    async def _extract_with_browser(self, url: str) -> str | None:
        """
        Extract content using Playwright browser.

        V1.2: Now uses _ensure_browser_connected() for auto-recovery.

        Requirements: 2.2
        """
        # V1.2: Ensure browser is connected, recreate if needed
        if not await self._ensure_browser_connected():
            logger.error("❌ [NEWS-RADAR] Browser not available and could not be recreated")
            return None

        page = None
        try:
            page = await self._browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 720})

            # V12.1: Apply stealth if available (COVE FIX)
            if STEALTH_AVAILABLE and Stealth is not None:
                try:
                    stealth = Stealth()
                    await stealth.apply_stealth_async(page)
                    logger.debug("🥷 [NEWS-RADAR] Stealth mode applied")
                except Exception as e:
                    logger.warning(f"⚠️ [NEWS-RADAR] Stealth failed: {e}")
            else:
                logger.debug(
                    "⚠️ [NEWS-RADAR] playwright-stealth not available, continuing without stealth"
                )

            # Navigate
            timeout_ms = self._page_timeout * 1000
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

            # Get HTML for Trafilatura
            html = await page.content()
            text = self._extract_with_trafilatura(html)

            # Fallback to raw text
            if not text:
                text = await page.inner_text("body")

            if text and len(text) > MAX_TEXT_LENGTH:
                text = text[:MAX_TEXT_LENGTH]

            self._browser_extractions += 1
            return text

        except asyncio.TimeoutError:
            logger.warning(
                f"⚠️ [NEWS-RADAR] Browser timeout after {self._page_timeout}s: {url[:60]}..."
            )
            logger.debug(f"   Full URL: {url}")
            return None
        except Exception as e:
            logger.error(f"❌ [NEWS-RADAR] Browser extraction error: {type(e).__name__}: {e}")
            logger.error(f"   URL: {url}")
            logger.debug(f"   Traceback:\n{traceback.format_exc()}")
            return None
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    async def extract(self, url: str) -> str | None:
        """
        Extract text content from URL.

        Uses hybrid approach: HTTP first, browser fallback.

        Requirements: 2.1, 2.2, 2.4
        """
        # Try HTTP first (fast)
        text = await self._extract_with_http(url)
        if text:
            return text

        # Fallback to browser
        text = await self._extract_with_browser(url)
        if text:
            return text

        self._failed_extractions += 1
        logger.debug(f"📄 [NEWS-RADAR] Extraction failed: {url[:50]}...")
        return None

    async def extract_with_navigation(
        self,
        url: str,
        link_selector: str,
        max_links: int = DEFAULT_MAX_LINKS_PER_PAGINATED,
        delay_seconds: int = DEFAULT_NAVIGATION_DELAY_SECONDS,
    ) -> list[tuple[str, str]]:
        """
        Extract from paginated source.

        Extracts links from main page, visits each, and extracts content.

        V1.2: Now uses _ensure_browser_connected() for auto-recovery.
        V7.5: Added race condition protection with:
        - wait_for_load_state('networkidle') with timeout
        - wait_for_selector() for dynamic selector
        - Retry logic for specific errors
        - Fallback to HTTP extraction

        Requirements: 9.1, 9.2, 9.3, 9.4

        Returns:
            List of (url, content) tuples
        """
        # V1.2: Ensure browser is connected, recreate if needed
        if not await self._ensure_browser_connected():
            logger.error(
                "❌ [NEWS-RADAR] Browser not available for navigation and could not be recreated"
            )
            return []

        results: list[tuple[str, str]] = []
        page = None
        max_retries = 2  # Retry on specific errors

        for attempt in range(max_retries):
            try:
                page = await self._browser.new_page()
                await page.set_viewport_size({"width": 1280, "height": 720})

                # V12.1: Apply stealth if available (COVE FIX)
                if STEALTH_AVAILABLE and Stealth is not None:
                    try:
                        stealth = Stealth()
                        await stealth.apply_stealth_async(page)
                        logger.debug("🥷 [NEWS-RADAR] Stealth mode applied")
                    except Exception as e:
                        logger.warning(f"[NEWS-RADAR] Stealth failed: {e}")
                else:
                    logger.debug(
                        "[NEWS-RADAR] playwright-stealth not available, continuing without stealth"
                    )

                # Navigate to main page
                timeout_ms = self._page_timeout * 1000
                await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

                # V7.5: Wait for network idle with timeout (not all pages reach networkidle)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    # Some pages never reach networkidle (polling, websockets)
                    logger.debug(
                        f"⏱️ [NEWS-RADAR] Network idle timeout for {url[:40]}..., proceeding anyway"
                    )

                # V7.5: Wait for selector to be available
                try:
                    await page.wait_for_selector(link_selector, timeout=3000)
                except Exception:
                    logger.debug(
                        f"⚠️ [NEWS-RADAR] Selector '{link_selector}' not found, attempting extraction anyway"
                    )

                # Extract links
                links = await page.eval_on_selector_all(
                    link_selector,
                    "elements => elements.map(e => e.href).filter(h => h && h.startsWith('http'))",
                )

                # Limit number of links
                links = links[:max_links]
                logger.info(f"🔗 [NEWS-RADAR] Found {len(links)} links on {url[:40]}...")

                # Visit each link
                for link_url in links:
                    try:
                        # Delay between pages
                        await asyncio.sleep(delay_seconds)

                        # Extract content from linked page
                        content = await self.extract(link_url)
                        if content:
                            results.append((link_url, content))

                    except Exception as e:
                        logger.debug(f"⚠️ [NEWS-RADAR] Failed to extract {link_url[:40]}: {e}")
                        continue

                return results  # Success!

            except Exception as e:
                error_msg = str(e)

                # V7.5: Check if this is a retryable error
                is_retryable = any(
                    [
                        "Execution context was destroyed" in error_msg,
                        "Target closed" in error_msg,
                        "Session closed" in error_msg,
                    ]
                )

                if is_retryable and attempt < max_retries - 1:
                    logger.warning(
                        f"⚠️ [NEWS-RADAR] Retryable error (attempt {attempt + 1}/{max_retries}): {e}"
                    )
                    await asyncio.sleep(2)  # Wait before retry
                    continue

                # Non-retryable error or max retries reached
                logger.error(f"❌ [NEWS-RADAR] Navigation extraction failed: {e}")
                return results

            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass

        return results

    async def extract_batch_http(
        self, urls: list[str], max_concurrent: int = 5
    ) -> dict[str, str | None]:
        """
        V7.3: Batch HTTP extraction for multiple URLs in parallel.

        Uses asyncio.gather() to parallelize HTTP requests.
        Falls back to browser only for URLs that fail HTTP extraction.

        Args:
            urls: List of URLs to extract
            max_concurrent: Maximum concurrent HTTP requests (default 5)

        Returns:
            Dict mapping URL -> extracted content (or None if failed)
        """
        if not urls:
            return {}

        results: dict[str, str | None] = {}

        # Use semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def extract_single(url: str) -> tuple[str, str | None]:
            """Extract single URL with semaphore."""
            async with semaphore:
                try:
                    # Try HTTP first (fast)
                    content = await self._extract_with_http(url)
                    return (url, content)
                except Exception as e:
                    logger.debug(f"⚠️ [NEWS-RADAR] Batch HTTP failed for {url[:40]}: {e}")
                    return (url, None)

        # Run all extractions in parallel
        tasks = [extract_single(url) for url in urls]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        browser_fallback_urls: list[str] = []
        for i, result in enumerate(completed):
            url = urls[i]  # Get original URL by index
            if isinstance(result, Exception):
                # Exception occurred - add to fallback
                logger.debug(f"⚠️ [NEWS-RADAR] Batch task exception for {url[:40]}: {result}")
                browser_fallback_urls.append(url)
                continue

            _, content = result
            if content:
                results[url] = content
            else:
                # Mark for browser fallback
                browser_fallback_urls.append(url)

        # Browser fallback for failed URLs (sequential to avoid overload)
        if browser_fallback_urls:
            logger.debug(f"🌐 [NEWS-RADAR] Browser fallback for {len(browser_fallback_urls)} URLs")
            for url in browser_fallback_urls:
                content = await self._extract_with_browser(url)
                results[url] = content

        return results

    def get_stats(self) -> dict[str, int]:
        """Get extraction statistics."""
        return {
            "http_extractions": self._http_extractions,
            "browser_extractions": self._browser_extractions,
            "failed_extractions": self._failed_extractions,
            "waf_bypasses": self._waf_bypasses,
        }


# ============================================
# DEEPSEEK FALLBACK
# ============================================


class DeepSeekFallback:
    """
    DeepSeek API for content analysis.

    V2.0: Completely rewritten for high-value signal extraction.
    - Uses new structured prompt
    - Extracts team, opponent, absent count, player names
    - Applies strict quality gates

    Requirements: 5.1, 5.2, 5.3, 5.4
    """

    def __init__(self, min_interval: float = DEEPSEEK_MIN_INTERVAL_SECONDS):
        self._min_interval = min_interval
        self._last_call_time: float = 0.0
        self._call_count = 0

    async def _wait_for_rate_limit(self) -> None:
        """
        Wait if needed to respect rate limit.

        Requirements: 5.4
        """
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            wait_time = self._min_interval - elapsed
            await asyncio.sleep(wait_time)

    def _parse_response_v2(self, response_text: str) -> dict[str, Any] | None:
        """
        Parse JSON response from DeepSeek V2 prompt.

        Returns structured dict or None if parsing fails.
        """
        # Handle DeepSeek <think> tags
        if "<think>" in response_text:
            response_text = re.sub(r"<think>[\s\S]*?</think>", "", response_text)

        try:
            data = json.loads(response_text.strip())
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    return None
            else:
                # Try to find JSON object in text
                json_match = re.search(r"\{[\s\S]*\}", response_text)
                if json_match:
                    try:
                        data = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        return None
                else:
                    return None

        return data

    async def analyze_v2(
        self,
        content: str,
        detected_signal: str | None = None,
        extracted_number: int | None = None,
        team_hint: str | None = None,
        source_context: str | None = None,
        timeout: int = 60,
        max_retries: int = 3,
    ) -> dict[str, Any] | None:
        """
        V2.0: Analyze content with structured extraction.

        V2.1 FIX: Added retry logic with exponential backoff for network errors and empty responses.
        Prevents permanent failures due to temporary network issues or API timeouts.

        V2.2 FIX (2026-02-14): Enhanced empty response handling with:
        - Increased default max_retries from 2 to 3 (4 total attempts)
        - Added jitter to backoff to prevent thundering herd
        - Enhanced logging with raw response details for debugging

        V3.0 FIX (2026-03-16): Added signal context integration for cross-validation:
        - Accepts detected_signal and extracted_number from pattern detector
        - Passes signal context to DeepSeek for intelligent cross-validation
        - Enables coordinated two-level analysis architecture

        V4.0 FIX (2026-04-01): Added intelligence context for team extraction:
        - Accepts team_hint from pattern-based pre-extraction
        - Accepts source_context from source geographic inference
        - Passes both to DeepSeek for informed team identification
        - Enables root-cause fix: components communicate before LLM analysis

        Returns dict with:
        - is_high_value: bool
        - team: str or None
        - opponent: str or None
        - competition: str or None
        - match_date: str or None
        - category: str
        - absent_count: int
        - absent_players: list
        - betting_impact: str
        - confidence: float
        - summary_italian: str

        Returns None if API unavailable or parsing fails after all retries.

        Args:
            content: The text content to analyze
            detected_signal: Signal type detected by pattern matching (optional)
            extracted_number: Number extracted from text (optional)
            team_hint: Team name pre-extracted by pattern matching (optional)
            source_context: Geographic context string from source analysis (optional)
            timeout: Maximum time to wait for API response in seconds (default: 60)
            max_retries: Maximum number of retries for network errors and empty responses (default: 3)
        """
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.error("❌ [NEWS-RADAR] No OpenRouter API key for DeepSeek")
            return None

        model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324")
        prompt = build_analysis_prompt_v2(
            content, detected_signal, extracted_number,
            team_hint=team_hint,
            source_context=source_context,
        )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://earlybird.local",
            "X-Title": "EarlyBird News Radar V2",
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,  # Lower for more consistent structured output
            "max_tokens": 800,
        }

        # V2.1 FIX: Retry logic with exponential backoff
        retry_count = 0
        last_error = None

        while retry_count <= max_retries:
            try:
                # Rate limiting before each attempt
                await self._wait_for_rate_limit()

                response = await asyncio.to_thread(
                    requests.post,
                    OPENROUTER_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                )

                self._last_call_time = time.time()
                self._call_count += 1

                if response.status_code != 200:
                    logger.error(f"❌ [NEWS-RADAR] DeepSeek HTTP error: {response.status_code}")
                    last_error = ValueError(f"HTTP {response.status_code}")
                    if retry_count < max_retries:
                        # V2.2 FIX: Exponential backoff with jitter
                        import random

                        base_backoff = 2**retry_count
                        jitter = random.uniform(0, 0.5)
                        backoff_time = base_backoff + jitter
                        logger.warning(f"⏳ Retrying in {backoff_time:.2f}s after HTTP error...")
                        await asyncio.sleep(backoff_time)
                        retry_count += 1
                        continue
                    break

                try:
                    data = response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"❌ [NEWS-RADAR] DeepSeek returned invalid JSON: {e}")
                    last_error = e
                    if retry_count < max_retries:
                        # V2.2 FIX: Exponential backoff with jitter
                        import random

                        base_backoff = 2**retry_count
                        jitter = random.uniform(0, 0.5)
                        backoff_time = base_backoff + jitter
                        logger.warning(f"⏳ Retrying in {backoff_time:.2f}s after JSON error...")
                        await asyncio.sleep(backoff_time)
                        retry_count += 1
                        continue
                    break

                # Extract response text
                choices = data.get("choices", [])
                if not choices:
                    logger.warning("⚠️ [NEWS-RADAR] DeepSeek response missing 'choices'")
                    last_error = ValueError("Missing choices in response")
                    if retry_count < max_retries:
                        # V2.2 FIX: Exponential backoff with jitter
                        import random

                        base_backoff = 2**retry_count
                        jitter = random.uniform(0, 0.5)
                        backoff_time = base_backoff + jitter
                        logger.warning(f"⏳ Retrying in {backoff_time:.2f}s...")
                        await asyncio.sleep(backoff_time)
                        retry_count += 1
                        continue
                    break

                first_choice = (
                    choices[0] if isinstance(choices, list) and len(choices) > 0 else None
                )
                if not isinstance(first_choice, dict):
                    logger.warning("⚠️ [NEWS-RADAR] DeepSeek invalid choice format")
                    last_error = ValueError("Invalid choice format")
                    if retry_count < max_retries:
                        # V2.2 FIX: Exponential backoff with jitter
                        import random

                        base_backoff = 2**retry_count
                        jitter = random.uniform(0, 0.5)
                        backoff_time = base_backoff + jitter
                        logger.warning(f"⏳ Retrying in {backoff_time:.2f}s...")
                        await asyncio.sleep(backoff_time)
                        retry_count += 1
                        continue
                    break

                message = first_choice.get("message", {})
                if not isinstance(message, dict):
                    logger.warning("⚠️ [NEWS-RADAR] DeepSeek invalid message format")
                    last_error = ValueError("Invalid message format")
                    if retry_count < max_retries:
                        # V2.2 FIX: Exponential backoff with jitter
                        import random

                        base_backoff = 2**retry_count
                        jitter = random.uniform(0, 0.5)
                        backoff_time = base_backoff + jitter
                        logger.warning(f"⏳ Retrying in {backoff_time:.2f}s...")
                        await asyncio.sleep(backoff_time)
                        retry_count += 1
                        continue
                    break

                response_text = message.get("content", "")

                # V2.2 FIX: Enhanced empty response validation with detailed logging
                if not response_text or not response_text.strip():
                    logger.warning(
                        f"⚠️ [NEWS-RADAR] DeepSeek returned empty response (attempt {retry_count + 1}/{max_retries + 1})"
                    )

                    # V2.2 FIX: Log raw response details for debugging
                    try:
                        logger.debug(f"🔍 [DEBUG] Raw response data: {data}")
                        logger.debug(
                            f"🔍 [DEBUG] Response text: '{response_text}' (len={len(response_text)})"
                        )
                    except Exception as debug_e:
                        logger.debug(f"🔍 [DEBUG] Could not log raw response: {debug_e}")

                    last_error = ValueError("Empty response from API")
                    if retry_count < max_retries:
                        # V2.2 FIX: Exponential backoff with jitter to prevent thundering herd
                        import random

                        base_backoff = 2**retry_count  # 1s, 2s, 4s, etc.
                        jitter = random.uniform(0, 0.5)  # Add 0-0.5s random jitter
                        backoff_time = base_backoff + jitter
                        logger.warning(
                            f"⏳ Retrying in {backoff_time:.2f}s with exponential backoff + jitter..."
                        )
                        await asyncio.sleep(backoff_time)
                        retry_count += 1
                        continue
                    break

                logger.debug(
                    f"🤖 [NEWS-RADAR] DeepSeek V2 analysis complete (call #{self._call_count})"
                )

                result = self._parse_response_v2(response_text)

                # Apply quality gate
                if result:
                    result = self._apply_quality_gate(result)

                return result

            except requests.Timeout:
                logger.warning(
                    f"⚠️ [NEWS-RADAR] DeepSeek timeout after {timeout}s (attempt {retry_count + 1}/{max_retries + 1})"
                )
                last_error = TimeoutError(f"Timeout after {timeout}s")
                if retry_count < max_retries:
                    # V2.2 FIX: Exponential backoff with jitter
                    import random

                    base_backoff = 2**retry_count
                    jitter = random.uniform(0, 0.5)
                    backoff_time = base_backoff + jitter
                    logger.warning(
                        f"⏳ Retrying in {backoff_time:.2f}s with exponential backoff + jitter..."
                    )
                    await asyncio.sleep(backoff_time)
                    retry_count += 1
                    continue
                break

            except requests.RequestException as e:
                logger.error(
                    f"❌ [NEWS-RADAR] DeepSeek network error: {e} (attempt {retry_count + 1}/{max_retries + 1})"
                )
                last_error = e
                if retry_count < max_retries:
                    # V2.2 FIX: Exponential backoff with jitter
                    import random

                    base_backoff = 2**retry_count
                    jitter = random.uniform(0, 0.5)
                    backoff_time = base_backoff + jitter
                    logger.warning(
                        f"⏳ Retrying in {backoff_time:.2f}s with exponential backoff + jitter..."
                    )
                    await asyncio.sleep(backoff_time)
                    retry_count += 1
                    continue
                break

            except Exception as e:
                logger.error(f"❌ [NEWS-RADAR] DeepSeek unexpected error: {e}")
                last_error = e
                break

        # All retries exhausted
        logger.error(
            f"❌ [NEWS-RADAR] DeepSeek analysis failed after {max_retries + 1} attempts: {last_error}"
        )
        return None

    def _apply_quality_gate(self, result: dict[str, Any]) -> dict[str, Any]:
        """
        Apply strict quality gate to analysis result.

        Rules:
        1. If team is null/empty → is_high_value = False
        2. If betting_impact is LOW/NONE → is_high_value = False
        3. If category is LOW_VALUE/NOT_RELEVANT → is_high_value = False
        4. If confidence < 0.7 → is_high_value = False
        """
        # Rule 1: Team must be identified
        team = result.get("team")
        if not team or team.lower() in ("null", "unknown", "none", ""):
            result["is_high_value"] = False
            result["quality_gate_reason"] = "team_not_identified"
            logger.debug("🚫 [NEWS-RADAR] Quality gate: team not identified")
            return result

        # Rule 2: Betting impact must be meaningful
        impact = result.get("betting_impact", "NONE")
        if impact in ("LOW", "NONE"):
            result["is_high_value"] = False
            result["quality_gate_reason"] = f"low_betting_impact ({impact})"
            logger.debug(f"🚫 [NEWS-RADAR] Quality gate: low betting impact ({impact})")
            return result

        # Rule 3: Category must be high-value
        category = result.get("category", "NOT_RELEVANT")
        if category in ("LOW_VALUE", "NOT_RELEVANT"):
            result["is_high_value"] = False
            result["quality_gate_reason"] = f"low_value_category ({category})"
            logger.debug(f"🚫 [NEWS-RADAR] Quality gate: low value category ({category})")
            return result

        # Rule 4: Confidence must be sufficient
        confidence = result.get("confidence", 0.0)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0

        if confidence < 0.7:
            result["is_high_value"] = False
            result["quality_gate_reason"] = f"low_confidence ({confidence:.2f})"
            logger.debug(f"🚫 [NEWS-RADAR] Quality gate: low confidence ({confidence:.2f})")
            return result

        # Passed all gates
        result["quality_gate_reason"] = "passed"
        return result

    # ============================================
    # BACKWARD COMPATIBILITY METHODS (V1 API)
    # ============================================

    def _build_prompt(self, content: str) -> str:
        """
        V1 backward compatibility: Build analysis prompt.

        Redirects to V2 prompt builder.
        """
        return build_analysis_prompt_v2(content)

    def _parse_response(self, response_text: str) -> AnalysisResult | None:
        """
        V1 backward compatibility: Parse JSON response.

        Parses both V1 and V2 formats and converts to V1 AnalysisResult.
        Applies quality gate for betting_impact.

        V1 format: is_relevant, affected_team, summary
        V2 format: is_high_value, team, summary_italian
        """
        result = self._parse_response_v2(response_text)
        if not result:
            return None

        # Apply quality gate
        result = self._apply_quality_gate(result)

        # Determine is_relevant based on V2 fields (or V1 fallback)
        # V1 logic: is_relevant = True only if betting_impact is HIGH/MEDIUM/CRITICAL
        betting_impact = result.get("betting_impact", "LOW")
        if betting_impact not in ("HIGH", "MEDIUM", "CRITICAL"):
            betting_impact = "LOW"

        # Support both V1 (is_relevant) and V2 (is_high_value)
        is_relevant = result.get("is_high_value", result.get("is_relevant", False))
        if betting_impact == "LOW":
            is_relevant = False

        # Support both V1 (affected_team) and V2 (team)
        affected_team = result.get("team") or result.get("affected_team")

        # Support both V1 (summary) and V2 (summary_italian)
        summary = result.get("summary_italian") or result.get("summary", "")

        # Safe confidence conversion with error handling (COVE FIX 2026-03-07)
        try:
            confidence_raw = result.get("confidence", 0.0)
            if isinstance(confidence_raw, str):
                # Try to extract number from string (e.g., "0.85" or "85%")
                import re

                match = re.search(r"[\d.]+", confidence_raw)
                if match:
                    confidence = float(match.group())
                    # If the value is a percentage (e.g., "85"), convert to 0.0-1.0 range
                    if confidence > 1.0:
                        confidence = confidence / 100.0
                else:
                    logger.warning(f"Invalid confidence value: {confidence_raw}, using default 0.0")
                    confidence = 0.0
            else:
                confidence = float(confidence_raw)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to convert confidence to float: {e}, using default 0.0")
            confidence = 0.0

        return AnalysisResult(
            is_relevant=is_relevant,
            category=result.get("category", "OTHER"),
            affected_team=affected_team,
            confidence=confidence,
            summary=summary,
            betting_impact=betting_impact,
        )

    # Keep old method for backward compatibility
    async def analyze(self, content: str) -> AnalysisResult | None:
        """
        Legacy method - redirects to V2 and converts result.

        Kept for backward compatibility.
        """
        result = await self.analyze_v2(content)
        if not result:
            return None

        # Convert V2 result to AnalysisResult
        return AnalysisResult(
            is_relevant=result.get("is_high_value", False),
            category=result.get("category", "OTHER"),
            affected_team=result.get("team"),
            confidence=float(result.get("confidence", 0.0)),
            summary=result.get("summary_italian", ""),
            betting_impact=result.get("betting_impact", "LOW"),
        )

    def get_last_call_time(self) -> float:
        """Get timestamp of last API call."""
        return self._last_call_time

    def get_call_count(self) -> int:
        """Get total number of API calls."""
        return self._call_count


# ============================================
# TELEGRAM ALERTER
# ============================================


class TelegramAlerter:
    """
    Sends alerts to Telegram.

    Uses 🔔 RADAR emoji to distinguish from main bot (🚨 EARLYBIRD).
    Implements retry with exponential backoff.

    Requirements: 6.1, 6.2, 6.3, 6.4
    """

    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self._token = token or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
        self._chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self._alerts_sent = 0
        self._alerts_failed = 0

    async def send_alert(self, alert: RadarAlert, max_retries: int = 3) -> bool:
        """
        Send formatted alert to Telegram.

        Returns True if sent successfully.

        Requirements: 6.1, 6.2, 6.3, 6.4
        """
        if not self._token or not self._chat_id:
            logger.error("❌ [NEWS-RADAR] Telegram credentials not configured")
            return False

        message = alert.to_telegram_message()
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"

        payload = {
            "chat_id": self._chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        # Retry with exponential backoff
        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(requests.post, url, json=payload, timeout=10)

                if response.status_code == 200:
                    self._alerts_sent += 1
                    logger.info(
                        f"🔔 [NEWS-RADAR] Alert sent: {alert.affected_team} - {alert.category}"
                    )
                    return True

                if response.status_code == 429:
                    # Rate limited - wait and retry
                    retry_after = safe_get(response.json(), "parameters", "retry_after", default=5)
                    logger.warning(f"⚠️ [NEWS-RADAR] Telegram rate limited, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue

                logger.error(
                    f"❌ [NEWS-RADAR] Telegram error: {response.status_code} - {response.text[:100]}"
                )

            except requests.Timeout:
                logger.warning(
                    f"⚠️ [NEWS-RADAR] Telegram timeout (attempt {attempt + 1}/{max_retries})"
                )
            except Exception as e:
                logger.error(f"❌ [NEWS-RADAR] Telegram error: {e}")

            # Exponential backoff: 2s, 4s, 8s
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                await asyncio.sleep(wait_time)

        self._alerts_failed += 1
        logger.error(f"❌ [NEWS-RADAR] Failed to send alert after {max_retries} attempts")
        return False

    def get_stats(self) -> dict[str, int]:
        """Get alerter statistics."""
        return {
            "alerts_sent": self._alerts_sent,
            "alerts_failed": self._alerts_failed,
        }


# ============================================
# NEWS RADAR MONITOR (Main Class)
# ============================================


class NewsRadarMonitor:
    """
    Autonomous news monitoring component.

    Runs independently from main bot, sends direct Telegram alerts.

    Flow:
    1. Load sources from config
    2. Scan sources in priority order
    3. Extract content (HTTP + Playwright fallback)
    4. Apply exclusion filter
    5. Analyze relevance
    6. Route based on confidence (alert / deepseek / skip)
    7. Send Telegram alerts

    Requirements: 1.1-1.4, 10.1-10.4
    """

    def __init__(self, config_file: str = DEFAULT_CONFIG_FILE, use_supabase: bool = True):
        """
        Initialize NewsRadarMonitor.

        V2.0: Simplified - uses singleton filters from modules.
        V8.0: Added Supabase support for dynamic source fetching.
        V9.0: Added Supabase polling for hot reload.

        Args:
            config_file: Path to config file (fallback if Supabase fails)
            use_supabase: Whether to fetch sources from Supabase (default: True)

        Requirements: 1.1
        """
        self._config_file = config_file
        self._use_supabase = use_supabase
        self._config: RadarConfig = RadarConfig()
        self._config_mtime: float = 0.0

        # Components
        self._content_cache: ContentCache | None = None
        self._extractor: ContentExtractor | None = None
        self._deepseek: DeepSeekFallback | None = None
        self._alerter: TelegramAlerter | None = None

        # V7.0: Optional Tavily
        self._tavily = None
        self._tavily_budget = None

        # Circuit breakers per source
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

        # V8.0: Lock for async-safe cache writing (prevents race conditions in concurrent scanning)
        # V12.0 FIX: Initialize lock in __init__ to prevent lazy initialization race condition
        self._cache_lock = asyncio.Lock()

        # V9.0: Supabase hot reload polling
        self._last_supabase_check = 0.0
        self._supabase_check_interval = 300  # 5 minutes

        # State
        self._running = False
        self._stop_event = asyncio.Event()
        self._scan_task: asyncio.Task | None = None

        # Stats
        self._urls_scanned = 0
        self._alerts_sent = 0
        self._excluded_count = 0  # VPS FIX: Track excluded content statistics
        self._last_cycle_time: datetime | None = None

        logger.info("🔔 [NEWS-RADAR] V2.0 Monitor created")

    async def start(self) -> bool:
        """
        Start the monitor.

        Returns True if started successfully.

        Requirements: 1.1, 10.1
        """
        if self._running:
            logger.warning("⚠️ [NEWS-RADAR] Already running")
            return True

        try:
            # Load configuration
            if self._use_supabase:
                logger.info("🔄 [NEWS-RADAR] Loading sources from Supabase...")
                self._config = load_config_from_supabase()
                # Fallback to file if Supabase returns no sources
                if not self._config.sources:
                    logger.warning(
                        "⚠️ [NEWS-RADAR] No sources from Supabase, falling back to config file"
                    )
                    self._config = load_config(self._config_file)
                    self._update_config_mtime()
            else:
                self._config = load_config(self._config_file)
                self._update_config_mtime()

            if not self._config.sources:
                logger.warning("⚠️ [NEWS-RADAR] No sources configured")

            # Initialize components
            self._content_cache = ContentCache(
                max_entries=DEFAULT_CACHE_MAX_ENTRIES,
                ttl_hours=self._config.global_settings.cache_ttl_hours,
            )

            self._extractor = ContentExtractor(
                page_timeout=self._config.global_settings.page_timeout_seconds
            )

            if not await self._extractor.initialize():
                logger.error("❌ [NEWS-RADAR] Failed to initialize extractor")
                return False

            # V2.0: Initialize DeepSeek and alerter (other filters are singletons)
            self._deepseek = DeepSeekFallback()
            self._alerter = TelegramAlerter()

            # V7.0: Initialize Tavily for pre-enrichment (optional)
            try:
                from src.ingestion.tavily_budget import get_budget_manager
                from src.ingestion.tavily_provider import get_tavily_provider

                self._tavily = get_tavily_provider()
                self._tavily_budget = get_budget_manager()
                tavily_status = "enabled" if self._tavily.is_available() else "disabled"
                logger.info(f"🔍 [NEWS-RADAR] Tavily pre-enrichment {tavily_status}")
            except ImportError:
                self._tavily = None
                self._tavily_budget = None
                logger.debug("⚠️ [NEWS-RADAR] Tavily not available")

            # V12.0 FIX: Cache lock now initialized in __init__ to prevent race condition
            # No need to initialize here anymore

            # Start scan loop
            self._running = True
            self._stop_event.clear()
            self._scan_task = asyncio.create_task(self._scan_loop())

            logger.info(f"✅ [NEWS-RADAR] V2.0 Started with {len(self._config.sources)} sources")
            logger.info("   High-value signal detection: ENABLED")
            logger.info("   Quality gate: ENABLED (team required, impact >= MEDIUM)")
            logger.info("   Concurrent processing: ENABLED (adaptive chunking)")
            if self._use_supabase:
                logger.info("   Supabase hot reload: ENABLED (polling every 5 minutes)")
            return True

        except Exception as e:
            logger.error(f"❌ [NEWS-RADAR] Failed to start: {e}")
            return False

    async def stop(self) -> bool:
        """
        Stop the monitor gracefully.

        Requirements: 10.3
        """
        if not self._running:
            return True

        logger.info("🛑 [NEWS-RADAR] Stopping...")

        self._running = False
        self._stop_event.set()

        # Wait for scan task
        if self._scan_task:
            try:
                self._scan_task.cancel()
                await asyncio.wait_for(asyncio.shield(self._scan_task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._scan_task = None

        # Shutdown extractor
        if self._extractor:
            await self._extractor.shutdown()

        logger.info("✅ [NEWS-RADAR] Stopped")
        return True

    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._running

    def _update_config_mtime(self) -> None:
        """Update stored config file modification time."""
        try:
            self._config_mtime = Path(self._config_file).stat().st_mtime
        except Exception:
            self._config_mtime = 0.0

    def _check_config_changed(self) -> bool:
        """Check if config file has been modified."""
        try:
            current_mtime = Path(self._config_file).stat().st_mtime
            return current_mtime > self._config_mtime
        except Exception:
            return False

    def reload_sources(self) -> None:
        """
        Reload sources from config file or Supabase (hot reload).

        V8.0: Added Supabase support for dynamic source reloading.
        V14.0: Preserves last_scanned timestamps during hot reload to prevent duplicate scans.

        Requirements: 8.2
        """
        old_count = len(self._config.sources)

        # Preserve last_scanned timestamps before reload
        # This prevents duplicate scans immediately after hot reload
        preserved_last_scanned = {}
        for source in self._config.sources:
            if source.last_scanned is not None:
                # Use URL as key since it's unique per source
                preserved_last_scanned[source.url] = source.last_scanned

        if self._use_supabase:
            logger.info("🔄 [NEWS-RADAR] Reloading sources from Supabase...")
            self._config = load_config_from_supabase()
            # Fallback to file if Supabase returns no sources
            if not self._config.sources:
                logger.warning(
                    "⚠️ [NEWS-RADAR] No sources from Supabase, falling back to config file"
                )
                self._config = load_config(self._config_file)
                self._update_config_mtime()
        else:
            self._config = load_config(self._config_file)
            self._update_config_mtime()

        # Restore last_scanned timestamps after reload
        # This maintains scan timing continuity across hot reloads
        restored_count = 0
        for source in self._config.sources:
            if source.url in preserved_last_scanned:
                source.last_scanned = preserved_last_scanned[source.url]
                restored_count += 1

        new_count = len(self._config.sources)
        logger.info(
            f"🔄 [NEWS-RADAR] Reloaded config: {old_count} → {new_count} sources "
            f"(preserved {restored_count} last_scanned timestamps)"
        )

    def _get_circuit_breaker(self, url: str) -> CircuitBreaker:
        """Get or create circuit breaker for a URL."""
        if url not in self._circuit_breakers:
            self._circuit_breakers[url] = CircuitBreaker()
        return self._circuit_breakers[url]

    def _check_supabase_changed(self) -> bool:
        """
        V9.0: Check if Supabase sources should be reloaded based on polling interval.

        Returns True if it's time to check Supabase for updates.
        """
        if not self._use_supabase:
            return False
        now = time.time()
        return now - self._last_supabase_check > self._supabase_check_interval

    async def _scan_loop(self) -> None:
        """
        Main scan loop that runs continuously.

        Requirements: 1.2, 1.3
        V13.0 COVE FIX: Added error classification and max retry logic with exponential backoff
        """
        logger.info("🔄 [NEWS-RADAR] Scan loop started")

        consecutive_errors = 0
        max_consecutive_errors = 10  # Stop after 10 consecutive errors

        while self._running and not self._stop_event.is_set():
            try:
                # Check for config hot reload (file-based)
                if self._check_config_changed():
                    self.reload_sources()

                # V9.0: Check for Supabase hot reload (polling-based)
                if self._check_supabase_changed():
                    logger.info("🔄 [NEWS-RADAR] Checking Supabase for source updates...")
                    self.reload_sources()
                    self._last_supabase_check = time.time()

                # Run scan cycle
                alerts_sent = await self.scan_cycle()

                # Reset error counter on success
                consecutive_errors = 0

                self._last_cycle_time = datetime.now(timezone.utc)
                logger.info(
                    f"🔔 [NEWS-RADAR] Cycle complete: {self._urls_scanned} URLs, {alerts_sent} alerts"
                )

                # Wait before next cycle
                interval = self._config.global_settings.default_scan_interval_minutes * 60
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                    break
                except asyncio.TimeoutError:
                    pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                # V13.0 COVE FIX: Classify error type for appropriate handling
                error_class = self._classify_error(e)

                if error_class == "PERMANENT":
                    logger.error(
                        f"💀 [NEWS-RADAR] Permanent error detected, stopping monitor: {type(e).__name__}: {e}"
                    )
                    self._running = False
                    break

                elif error_class == "RATE_LIMIT":
                    # Longer backoff for rate limits (30 minutes)
                    backoff_time = 1800
                    logger.warning(
                        f"⚠️ [NEWS-RADAR] Rate limited, waiting {backoff_time}s (30 minutes) before retry..."
                    )
                    await asyncio.sleep(backoff_time)
                    # Reset error counter after rate limit backoff
                    consecutive_errors = 0

                else:  # TRANSIENT
                    consecutive_errors += 1
                    logger.error(
                        f"❌ [NEWS-RADAR] Transient error ({consecutive_errors}/{max_consecutive_errors}): {type(e).__name__}: {e}"
                    )

                    # Check if we should stop due to too many consecutive errors
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(
                            f"💀 [NEWS-RADAR] Too many consecutive errors ({consecutive_errors}). Stopping monitor."
                        )
                        self._running = False
                        break

                    # Exponential backoff: 60s, 120s, 240s, 480s, 600s (max)
                    backoff_time = min(60 * (2 ** (consecutive_errors - 1)), 600)
                    logger.warning(f"⚠️ [NEWS-RADAR] Waiting {backoff_time}s before retry...")
                    await asyncio.sleep(backoff_time)

        logger.info("🛑 [NEWS-RADAR] Scan loop stopped")

    def _classify_error(self, error: Exception) -> str:
        """
        Classify error type for appropriate handling in the scan loop.

        This method determines whether an error is:
        - PERMANENT: Cannot be resolved by retrying (stop immediately)
        - RATE_LIMIT: API rate limit (long backoff required)
        - TRANSIENT: Temporary issue (retry with exponential backoff)

        Args:
            error: The exception to classify

        Returns:
            Error classification: 'PERMANENT', 'RATE_LIMIT', or 'TRANSIENT'

        V13.0 COVE FIX: Added intelligent error classification to prevent
        unnecessary retries on permanent errors and appropriate backoff for rate limits.
        """
        error_type = type(error).__name__
        error_msg = str(error).lower()

        # Permanent errors - stop immediately
        # These errors cannot be resolved by retrying
        if error_type in ["FileNotFoundError", "JSONDecodeError", "SyntaxError"]:
            return "PERMANENT"

        # Configuration errors - typically permanent
        if "config" in error_msg and ("invalid" in error_msg or "not found" in error_msg):
            return "PERMANENT"

        # Permission errors - typically permanent
        if error_type in ["PermissionError"]:
            return "PERMANENT"

        # Rate limit errors - longer backoff (30 minutes)
        # Check for HTTP 429 status
        if error_type == "HTTPStatusError" and hasattr(error, "status"):
            if error.status == 429:
                return "RATE_LIMIT"

        # Check for rate limit in error message
        if "rate limit" in error_msg or "429" in error_msg or "too many requests" in error_msg:
            return "RATE_LIMIT"

        # Transient errors - retry with exponential backoff
        # These are temporary issues that can be resolved by retrying
        if error_type in [
            "TimeoutError",
            "ConnectionError",
            "ConnectionRefusedError",
            "ConnectionResetError",
            "ConnectionAbortedError",
            "OSError",
            "RuntimeError",
        ]:
            return "TRANSIENT"

        # Network-related errors
        if "timeout" in error_msg or "connection" in error_msg or "network" in error_msg:
            return "TRANSIENT"

        # HTTP errors that might be transient
        if error_type in ["HTTPError", "HTTPStatusError"]:
            # 5xx errors are server-side and typically transient
            if hasattr(error, "status") and error.status >= 500:
                return "TRANSIENT"
            # 4xx errors (except 429) are client-side and typically permanent
            if hasattr(error, "status") and error.status >= 400 and error.status < 500:
                return "PERMANENT"

        # Default to TRANSIENT for unknown errors
        # This is safer than stopping on unknown errors
        return "TRANSIENT"

    async def scan_cycle(self) -> int:
        """
        Execute one scan cycle over all due sources.

        V7.3: Uses batch HTTP extraction for single-page sources.

        Returns number of alerts sent.

        Requirements: 1.2, 8.4
        """
        alerts_sent = 0
        urls_scanned = 0

        # Get sources due for scanning, sorted by priority (descending = highest first)
        due_sources = [s for s in self._config.sources if s.is_due_for_scan()]
        due_sources.sort(key=lambda s: s.priority)  # Lower number = higher priority

        if not due_sources:
            return 0

        # V7.3: Separate single-page and paginated sources
        single_sources = [s for s in due_sources if s.navigation_mode != "paginated"]
        paginated_sources = [s for s in due_sources if s.navigation_mode == "paginated"]

        # V7.3: Batch HTTP extraction for single-page sources
        if single_sources:
            # Filter by circuit breaker
            eligible_sources: list[RadarSource] = []
            for source in single_sources:
                breaker = self._get_circuit_breaker(source.url)
                if breaker.can_execute():
                    eligible_sources.append(source)
                else:
                    logger.debug(f"🔴 [NEWS-RADAR] Skipping {source.name} (circuit OPEN)")

            if eligible_sources:
                # Batch extract all URLs
                urls = [s.url for s in eligible_sources]
                logger.info(f"⚡ [NEWS-RADAR] Batch extracting {len(urls)} single-page sources")

                contents = await self._extractor.extract_batch_http(urls, max_concurrent=5)

                # Process each result
                for source in eligible_sources:
                    if not self._running or self._stop_event.is_set():
                        break

                    content = contents.get(source.url)
                    breaker = self._get_circuit_breaker(source.url)
                    urls_scanned += 1

                    # Update counter immediately to avoid loss on interruption
                    self._urls_scanned = urls_scanned

                    if content:
                        breaker.record_success()
                        alert = await self._process_content(content, source, source.url)

                        if alert:
                            # CROSS-PROCESS HANDOFF: High-confidence alerts to Main Pipeline
                            if alert.confidence >= ALERT_CONFIDENCE_THRESHOLD:
                                await self._handoff_to_main_pipeline(alert, content)

                            # Send Telegram alert
                            if self._alerter and await self._alerter.send_alert(alert):
                                alerts_sent += 1
                                self._alerts_sent += 1

                        # Update last scanned time ONLY on success
                        # This ensures circuit breaker effectiveness and proper retry timing
                        source.last_scanned = datetime.now(timezone.utc)
                    else:
                        breaker.record_failure()
                        # DO NOT update last_scanned on failure
                        # This allows circuit breaker to work correctly and retry sooner

        # V8.0: Process paginated sources concurrently using 3 browser contexts (tabs)
        if paginated_sources:
            alerts_sent, urls_scanned = await self._scan_paginated_sources_concurrent(
                paginated_sources, alerts_sent, urls_scanned
            )

        # Final assignment (in case loop completes normally)
        self._urls_scanned = urls_scanned
        return alerts_sent

    async def _scan_paginated_sources_concurrent(
        self, paginated_sources: list[RadarSource], alerts_sent: int, urls_scanned: int
    ) -> tuple[int, int]:
        """
        V8.0: Scan paginated sources concurrently using 3 browser contexts (tabs).

        Splits sources into 3 chunks and processes them in parallel using asyncio.gather.
        Uses async-safe cache writing with locks to prevent race conditions.

        Args:
            paginated_sources: List of paginated sources to scan
            alerts_sent: Current alert count (will be incremented)
            urls_scanned: Current URL scan count (will be incremented)

        Returns:
            Tuple of (alerts_sent, urls_scanned) after concurrent processing
        """
        if not paginated_sources:
            return alerts_sent, urls_scanned

        # V11.0 TURBO: Increased chunk size for 12GB RAM - use min(6, len(sources)) for efficiency
        num_chunks = min(6, len(paginated_sources))
        chunk_size = max(1, len(paginated_sources) // num_chunks) if num_chunks > 0 else 0
        chunks = [paginated_sources[i::num_chunks] for i in range(num_chunks)]

        logger.info(
            f"🚀 [NEWS-RADAR] Concurrent processing: {len(paginated_sources)} paginated sources in {num_chunks} chunk(s)"
        )
        for i, chunk in enumerate(chunks):
            logger.info(f"   Chunk {i + 1}: {len(chunk)} sources")

        # Define async task for scanning a chunk with retry logic
        async def scan_chunk(chunk: list[RadarSource], chunk_id: int) -> tuple[int, int]:
            """Scan a chunk of sources and return (alerts_sent, urls_scanned)."""
            chunk_alerts = 0
            chunk_scanned = 0

            for source in chunk:
                if not self._running or self._stop_event.is_set():
                    break

                # V9.0: Retry logic for failed source scans
                max_retries = 2
                for retry in range(max_retries):
                    try:
                        # Scan source
                        alert = await self.scan_source(source)
                        chunk_scanned += 1

                        # V8.0: Async-safe counter increment with lock
                        # V12.0: Fixed async lock usage - use try/finally instead of async with
                        if alert:
                            try:
                                # Send alert first (I/O operation, no lock needed)
                                alert_sent = False
                                if self._alerter:
                                    alert_sent = await asyncio.wait_for(
                                        self._alerter.send_alert(alert), timeout=10.0
                                    )

                                # Then acquire lock only for counter increment (minimal lock time)
                                if alert_sent:
                                    # V12.0 FIX: Lock is now initialized in __init__, no race condition
                                    try:
                                        await asyncio.wait_for(
                                            self._cache_lock.acquire(), timeout=5.0
                                        )
                                        try:
                                            chunk_alerts += 1
                                            self._alerts_sent += 1
                                        finally:
                                            self._cache_lock.release()
                                    except asyncio.TimeoutError:
                                        logger.warning(
                                            f"⚠️ [NEWS-RADAR] Chunk {chunk_id + 1} failed to acquire lock for counter increment"
                                        )
                            except asyncio.TimeoutError:
                                logger.warning(
                                    f"⚠️ [NEWS-RADAR] Chunk {chunk_id + 1} alert send timeout"
                                )

                        # Update last scanned time
                        source.last_scanned = datetime.now(timezone.utc)

                        # Success - break retry loop
                        break

                    except Exception as e:
                        if retry < max_retries - 1:
                            logger.warning(
                                f"⚠️ [NEWS-RADAR] Chunk {chunk_id + 1} retry {retry + 1}/{max_retries} for {source.name}: {e}"
                            )
                            await asyncio.sleep(1.0)  # Brief delay before retry
                        else:
                            logger.error(
                                f"❌ [NEWS-RADAR] Chunk {chunk_id + 1} failed after {max_retries} retries for {source.name}: {e}"
                            )

            return chunk_alerts, chunk_scanned

        # Run all chunks in parallel using asyncio.gather
        try:
            results = await asyncio.gather(
                *[scan_chunk(chunks[i], i) for i in range(num_chunks)],
                return_exceptions=True,
            )

            # Aggregate results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"❌ [NEWS-RADAR] Chunk {i + 1} failed: {result}")
                else:
                    chunk_alerts, chunk_scanned = result
                    alerts_sent += chunk_alerts
                    urls_scanned += chunk_scanned
                    logger.info(
                        f"✅ [NEWS-RADAR] Tab {i + 1} complete: {chunk_scanned} sources, {chunk_alerts} alerts"
                    )

        except Exception as e:
            logger.error(f"❌ [NEWS-RADAR] Concurrent scanning failed: {e}")

        return alerts_sent, urls_scanned

    async def scan_source(self, source: RadarSource) -> RadarAlert | None:
        """
        Scan a single source URL.

        Requirements: 1.4, 2.4, 10.2
        """
        try:
            # Check circuit breaker
            breaker = self._get_circuit_breaker(source.url)
            if not breaker.can_execute():
                logger.debug(f"🔴 [NEWS-RADAR] Skipping {source.name} (circuit OPEN)")
                return None

            # Extract content
            if source.navigation_mode == "paginated" and source.link_selector:
                # Paginated extraction
                results = await self._extractor.extract_with_navigation(
                    source.url,
                    source.link_selector,
                    max_links=self._config.global_settings.max_links_per_paginated_source,
                    delay_seconds=self._config.global_settings.navigation_delay_seconds,
                )

                # Process each extracted page
                for page_url, content in results:
                    alert = await self._process_content(content, source, page_url)
                    if alert:
                        breaker.record_success()
                        # CROSS-PROCESS HANDOFF: High-confidence alerts to Main Pipeline
                        if alert.confidence >= ALERT_CONFIDENCE_THRESHOLD:
                            await self._handoff_to_main_pipeline(alert, content)
                        return alert

                if not results:
                    breaker.record_failure()
                else:
                    breaker.record_success()
                return None
            else:
                # Single page extraction
                content = await self._extractor.extract(source.url)

                if not content:
                    breaker.record_failure()
                    return None

                breaker.record_success()
                alert = await self._process_content(content, source, source.url)

                # CROSS-PROCESS HANDOFF: High-confidence alerts to Main Pipeline
                if alert and alert.confidence >= ALERT_CONFIDENCE_THRESHOLD:
                    await self._handoff_to_main_pipeline(alert, content)

                return alert

        except Exception as e:
            # V12.6: Record failure for circuit breaker on scan exceptions.
            # Previously exceptions (timeouts, network errors) were silently swallowed,
            # causing infinite retry loops without circuit breaker protection.
            try:
                breaker = self._get_circuit_breaker(source.url)
                breaker.record_failure()
            except Exception:
                pass  # Don't let circuit breaker recording mask the original error
            logger.error(f"❌ [NEWS-RADAR] Error scanning {source.name}: {e}")
            return None

    async def _process_content(
        self, content: str, source: RadarSource, url: str
    ) -> RadarAlert | None:
        """
        V2.0: Process extracted content through the new high-value pipeline.

        New flow:
        1. Garbage filter (skip menus, login, etc.)
        2. High-value signal detection (multilingual patterns)
        3. If signal detected → DeepSeek for structured extraction
        4. Quality gate (team must be identified, impact must be HIGH/MEDIUM)
        5. Create alert only if passes all gates

        Requirements: 3.5, 4.5, 5.1, 5.2
        """
        # V1.1: Safety check - ensure components are initialized
        if not self._content_cache:
            logger.error("❌ [NEWS-RADAR] Components not initialized - call start() first")
            return None

        # V7.0: Check shared cache first (cross-component deduplication)
        # V14.0 COVE FIX: Use atomic check_and_mark_async() for thread safety
        try:
            from src.utils.shared_cache import get_shared_cache

            shared_cache = get_shared_cache()
            # Atomic check-and-mark operation to prevent race conditions
            if await shared_cache.check_and_mark_async(
                content=content, url=url, source="news_radar"
            ):
                logger.debug(f"🔄 [NEWS-RADAR] Skipping cross-component duplicate: {url[:50]}...")
                return None
        except ImportError:
            pass  # Shared cache not available, continue with local cache
        except Exception as e:
            # V14.0 COVE FIX: Cache error handling - continue processing despite cache failure
            logger.warning(f"⚠️ [NEWS-RADAR] Shared cache check failed, continuing: {e}")
            # Continue processing despite shared cache failure

        # Check local cache (deduplication)
        # V13.0 COVE FIX: Wrap in try/except for cache error handling
        try:
            if await self._content_cache.is_cached(content):
                logger.debug(f"🔄 [NEWS-RADAR] Skipping duplicate: {url[:50]}...")
                return None
        except Exception as e:
            # V13.0 COVE FIX: Cache error handling - continue processing despite cache failure
            logger.warning(f"⚠️ [NEWS-RADAR] Local cache check failed, continuing: {e}")
            # Continue processing despite cache failure

        # Cache content locally
        # V13.0 COVE FIX: Wrap in try/except for cache error handling
        try:
            await self._content_cache.add(content)
        except Exception as e:
            # V13.0 COVE FIX: Cache error handling - continue processing despite cache failure
            logger.warning(f"⚠️ [NEWS-RADAR] Failed to cache content locally, continuing: {e}")
            # Continue processing despite cache failure

        # ============================================
        # V2.0: NEW HIGH-VALUE PIPELINE
        # ============================================

        # Step 1: Garbage filter
        garbage_filter = get_garbage_filter()
        is_garbage, garbage_reason = garbage_filter.is_garbage(content)
        if is_garbage:
            logger.debug(f"🗑️ [NEWS-RADAR] Garbage filtered ({garbage_reason}): {url[:50]}...")
            return None

        # Clean content
        cleaned_content = garbage_filter.clean_content(content)
        if len(cleaned_content) < 100:
            logger.debug(f"🗑️ [NEWS-RADAR] Content too short after cleaning: {url[:50]}...")
            return None

        # VPS FIX: Removed redundant exclusion filter check
        # The garbage_filter.is_garbage() already checks for excluded sports (basketball, women's, NFL, etc.)
        # using the same exclusion patterns from centralized config (src/config/exclusion_lists.py)
        # This eliminates duplicate regex matching and improves performance

        # Step 2: Apply positive news filter (player returning = skip)
        # VPS FIX: Add error handling to prevent bot crash
        try:
            positive_filter = get_positive_news_filter()
            if positive_filter.is_positive_news(cleaned_content):
                reason = positive_filter.get_positive_reason(cleaned_content)
                logger.debug(f"✅ [NEWS-RADAR] Skipping positive news ({reason}): {url[:50]}...")
                return None
        except Exception as e:
            logger.warning(f"⚠️ [NEWS-RADAR] Error checking positive news filter: {e}")
            # Continue to next check

        # Step 3: High-value signal detection
        signal_detector = get_signal_detector()
        signal = signal_detector.detect(cleaned_content)

        if not signal.detected:
            # No high-value signal detected by patterns
            # Still try DeepSeek for non-European languages or subtle signals
            # But only if content looks promising (has some football keywords)
            if not self._has_football_keywords(cleaned_content):
                logger.debug(f"📭 [NEWS-RADAR] No signal, no football keywords: {url[:50]}...")
                return None

            # V7.3: Pre-filter score to reduce unnecessary DeepSeek calls
            prefilter_score = self._compute_prefilter_score(cleaned_content)
            if prefilter_score < 0.3:
                logger.debug(
                    f"📭 [NEWS-RADAR] Pre-filter score too low ({prefilter_score:.2f}): {url[:50]}..."
                )
                return None

            logger.debug(
                f"🔍 [NEWS-RADAR] No pattern match, pre-filter={prefilter_score:.2f}, trying DeepSeek: {url[:50]}..."
            )
        else:
            logger.info(
                f"🎯 [NEWS-RADAR] High-value signal: {signal.signal_type} ({signal.matched_pattern})"
            )

        # Step 4: V4.0 INTELLIGENCE PRE-ENRICHMENT
        # ROOT CAUSE FIX: Before calling DeepSeek, gather intelligence from:
        # A) Source context (WHERE is this content from? → narrows team candidates)
        # B) Pattern-based team extraction (regex found a team? → strong hint for LLM)
        # This makes the pipeline INTELLIGENT: components communicate BEFORE the LLM call.

        # 5A: Source context intelligence (non-blocking: DB queries run in thread pool)
        source_country_code = None
        source_context_str = None
        try:
            source_country_code, source_context_str = await asyncio.to_thread(
                self._infer_source_context, source
            )
        except Exception as e:
            logger.debug(f"⚠️ [NEWS-RADAR] Source context inference failed: {e}")

        # 5B: Pattern-based team hint extraction
        # Uses the 7-pattern heuristic from content_analysis.py (zero-cost, no API call)
        team_hint = None
        try:
            from src.utils.content_analysis import get_relevance_analyzer
            analyzer = get_relevance_analyzer()
            team_hint = analyzer.extract_team_name(cleaned_content)
            if team_hint:
                logger.info(f"🧠 [TEAM-HINT] Pattern pre-extracted team: '{team_hint}' from {source.name}")
        except Exception as e:
            logger.debug(f"⚠️ [NEWS-RADAR] Team hint extraction failed: {e}")

        # Step 5: DeepSeek structured extraction with ALL intelligence context
        # V3.0: Pass signal detection information for cross-validation
        # V4.0: Pass team_hint + source_context for informed team extraction
        detected_signal_str = signal.signal_type.value if signal.detected else None
        extracted_number = signal.extracted_number if signal.detected else None

        deep_result = await self._deepseek.analyze_v2(
            cleaned_content,
            detected_signal=detected_signal_str,
            extracted_number=extracted_number,
            team_hint=team_hint,
            source_context=source_context_str,
        )

        if not deep_result:
            logger.debug(f"❌ [NEWS-RADAR] DeepSeek analysis failed: {url[:50]}...")
            return None

        # Step 6: Check if passed quality gate
        if not deep_result.get("is_high_value", False):
            reason = deep_result.get("quality_gate_reason", "unknown")
            logger.debug(f"🚫 [NEWS-RADAR] Quality gate failed ({reason}): {url[:50]}...")
            return None

        # Step 7: V3.0 - Convert dict to StructuredAnalysis for intelligent processing
        # This enables component communication and intelligent validation
        structured_analysis = StructuredAnalysis.from_dict(deep_result)

        # Step 8: V4.0 FUZZY TEAM NORMALIZATION
        # ROOT CAUSE FIX: DeepSeek extracts "São Paulo" but DB has "Sao Paulo FC"
        # The substring match in enrichment fails on accents and abbreviations.
        # Solution: normalize the extracted team against DB teams using thefuzz.
        if structured_analysis.team:
            normalized_team = await asyncio.to_thread(
                self._fuzzy_match_team, structured_analysis.team
            )
            if normalized_team and normalized_team != structured_analysis.team:
                logger.info(
                    f"🔄 [TEAM-NORMALIZE] '{structured_analysis.team}' → '{normalized_team}' "
                    f"(fuzzy matched against DB)"
                )
                structured_analysis.team = normalized_team
                # Also update deep_result for consistency
                deep_result["team"] = normalized_team

        # Store pattern detection data for cross-validation
        structured_analysis.pattern_detected_signal = detected_signal_str
        structured_analysis.pattern_extracted_number = extracted_number

        # Step 9: Intelligent self-validation using StructuredAnalysis methods
        # This allows the component to validate itself before proceeding
        if not structured_analysis.is_valid_for_alert():
            logger.debug(f"🚫 [NEWS-RADAR] StructuredAnalysis validation failed: {url[:50]}...")
            return None

        # Step 10: Cross-validate signal_detector with DeepSeek analysis
        # This creates a coordinated two-level analysis architecture
        is_valid, confidence_adjustment = structured_analysis.cross_validate_with_pattern(
            signal_type=detected_signal_str,
            extracted_number=extracted_number,
        )

        if not is_valid:
            logger.debug(f"🚫 [NEWS-RADAR] Cross-validation failed: {url[:50]}...")
            return None

        # Step 11: Enrich StructuredAnalysis with database context
        # This enables intelligent component communication with enrichment system
        enrichment_context = None  # Initialize to None for reuse
        if _ENRICHMENT_AVAILABLE:
            # Get enrichment context before creating alert
            try:
                enrichment_context = await enrich_radar_alert_async(
                    affected_team=structured_analysis.team,
                    team=structured_analysis.team,  # Alias for compatibility
                    opponent=structured_analysis.opponent,
                    competition=structured_analysis.competition,
                    match_date=structured_analysis.match_date,
                )
                if enrichment_context:
                    # Extract enrichment data for StructuredAnalysis
                    enrichment_data = {
                        "motivation_home": getattr(enrichment_context, "motivation_home", None),
                        "motivation_away": getattr(enrichment_context, "motivation_away", None),
                        "match_importance": getattr(enrichment_context, "match_importance", None),
                        "opponent": getattr(enrichment_context, "opponent", None),
                        "competition": getattr(enrichment_context, "competition", None),
                        "match_date": getattr(enrichment_context, "match_date", None),
                    }
                    # Enrich the analysis
                    structured_analysis.enrich_with_context(enrichment_data)
            except Exception as e:
                logger.debug(f"⚠️ [NEWS-RADAR] Enrichment failed: {e}")

        # Step 12: Get intelligent priority from StructuredAnalysis
        # This uses the component's own logic to determine priority
        intelligent_priority = structured_analysis.get_alert_priority()

        # Step 13: Apply confidence adjustment from cross-validation
        base_confidence = structured_analysis.confidence
        adjusted_confidence = max(0.0, min(1.0, base_confidence + confidence_adjustment))

        # Step 14: Create alert with validated and enriched data
        # Convert StructuredAnalysis back to dict for RadarAlert creation
        alert_dict = structured_analysis.to_dict()

        alert = RadarAlert(
            source_name=source.name,
            source_url=url,
            affected_team=alert_dict.get("team", "Unknown"),
            opponent=alert_dict.get("opponent"),
            competition=alert_dict.get("competition"),
            match_date=alert_dict.get("match_date"),
            category=alert_dict.get("category"),
            absent_count=alert_dict.get("absent_count"),
            absent_players=alert_dict.get("absent_players"),
            betting_impact=intelligent_priority,  # V3.0: Use intelligent priority
            summary=alert_dict.get("summary_italian", "Notizia rilevante per betting"),
            confidence=adjusted_confidence,  # V3.0: Use adjusted confidence
        )

        # Step 15: Store enrichment context for later use
        # Reuse the enrichment_context from Step 10 instead of calling again
        if enrichment_context:
            alert.enrichment_context = enrichment_context

        # ============================================
        # Steps 16-18: Post-creation validation (V7.3)
        # ============================================

        # Step 16: Fixture correlation check
        # Skip alert if team doesn't play within 72h
        if alert.enrichment_context and not alert.enrichment_context.has_match():
            logger.info(
                f"⏭️ [NEWS-RADAR] Skipping alert - no match within 72h for {alert.affected_team}"
            )
            return None

        # Step 17: Odds movement check
        odds_suffix = ""
        if _ODDS_CHECK_AVAILABLE and alert.affected_team and alert.affected_team != "Unknown":
            try:
                match_id = alert.enrichment_context.match_id if alert.enrichment_context else None

                # Determine if the affected team is home or away
                is_home_team = None
                if alert.enrichment_context:
                    home_team = alert.enrichment_context.home_team
                    away_team = alert.enrichment_context.away_team
                    if home_team and away_team:
                        if alert.affected_team.lower() in home_team.lower():
                            is_home_team = True
                        elif alert.affected_team.lower() in away_team.lower():
                            is_home_team = False

                odds_result, odds_suffix = await check_odds_for_alert_async(
                    alert.affected_team, match_id=match_id, is_home_team=is_home_team
                )

                # Log odds status
                if odds_result.status != OddsMovementStatus.UNKNOWN:
                    logger.info(
                        f"📊 [NEWS-RADAR] Odds check for {alert.affected_team}: {odds_result.edge_assessment}"
                    )

                # Adjust confidence based on odds movement
                if odds_result.should_boost_priority:
                    alert.confidence = min(alert.confidence + 0.05, 0.95)
                    logger.info(
                        f"💎 [NEWS-RADAR] Confidence boosted (stable odds): {alert.confidence:.0%}"
                    )
                elif odds_result.should_reduce_priority:
                    # Don't skip, but note in summary
                    alert.summary = f"{alert.summary} [⚠️ Quote già mosse]"
                    logger.warning(
                        "⚠️ [NEWS-RADAR] Major odds movement detected - market may already know"
                    )
            except Exception as e:
                logger.debug(f"⚠️ [NEWS-RADAR] Odds check failed: {e}")

        # Step 18: Cross-source validation
        validation_tag = ""
        if _CROSS_VALIDATOR_AVAILABLE and alert.affected_team and alert.affected_team != "Unknown":
            try:
                validator = get_cross_validator()
                boosted_confidence, is_multi_source, validation_tag = validator.register_alert(
                    team=alert.affected_team,
                    category=alert.category,
                    source_name=source.name,
                    source_url=url,
                    confidence=alert.confidence,
                )

                if is_multi_source:
                    alert.confidence = boosted_confidence
                    logger.info(f"✅ [NEWS-RADAR] Multi-source confirmation: {validation_tag}")
            except Exception as e:
                logger.warning(f"⚠️ [NEWS-RADAR] Cross-validation failed: {e}")
                validation_tag = "⚠️ Cross-validation failed"

        # Store validation info for alert message
        alert._odds_suffix = odds_suffix
        alert._validation_tag = validation_tag

        logger.info(
            f"🔔 [NEWS-RADAR] Alert created: {alert.affected_team} - {alert.category} "
            f"({alert.absent_count} assenti, impact={alert.betting_impact})"
        )

        return alert

    # ============================================
    # V4.0: SOURCE CONTEXT INTELLIGENCE
    # ============================================

    # Timezone → country code mapping for source context inference
    _TZ_COUNTRY_MAP: dict[str, str] = {
        "America/Sao_Paulo": "BR", "America/Buenos_Aires": "AR",
        "America/Mexico_City": "MX", "America/Tegucigalpa": "HN",
        "America/Bogota": "CO", "America/Lima": "PE", "America/Santiago": "CL",
        "Europe/London": "GB", "Europe/Rome": "IT", "Europe/Paris": "FR",
        "Europe/Berlin": "DE", "Europe/Moscow": "RU", "Europe/Prague": "CZ",
        "Europe/Athens": "GR", "Europe/Istanbul": "TR",
        "Africa/Lagos": "NG", "Africa/Cairo": "EG", "Africa/Johannesburg": "ZA",
        "Asia/Singapore": "SG", "Asia/Shanghai": "CN",
        "Asia/Tokyo": "JP", "Asia/Jakarta": "ID", "Asia/Seoul": "KR",
    }

    # URL domain suffix → country code
    _DOMAIN_COUNTRY_MAP: dict[str, str] = {
        ".com.br": "BR", ".com.ar": "AR", ".com.mx": "MX", ".com.hn": "HN",
        ".ru": "RU", ".de": "DE", ".it": "IT", ".uk": "GB",
        ".id": "ID", ".cn": "CN", ".jp": "JP", ".kr": "KR",
        ".ng": "NG", ".eg": "EG", ".za": "ZA", ".hn": "HN",
    }

    # Source name/URL keywords → country code
    _SOURCE_KEYWORD_MAP: dict[str, str] = {
        "brazil": "BR", "brasil": "BR", "brasileiro": "BR", "brasileirao": "BR",
        "gazeta": "BR", "esportiva": "BR", "jogada": "BR", "globo": "BR",
        "bauru": "BR", "correio": "BR",
        "honduras": "HN", "hondudiario": "HN", "heraldo": "HN",
        "nigeria": "NG", "nigeriasoccer": "NG", "brila": "NG", "panafrica": "NG",
        "egypt": "EG", "ahram": "EG",
        "scotland": "GB", "stv": "GB", "chesterfield": "GB",
        "germany": "DE", "liga3": "DE",
        "calcio": "IT", "tuttomercato": "IT",
        "indonesia": "ID", "palembang": "ID", "superball": "ID", "tribun": "ID",
        "supersport": "ZA", "flashscore": "INT", "besoccer": "INT",
    }

    def _infer_source_context(self, source: RadarSource) -> tuple[str | None, str | None]:
        """
        V4.0: Infer geographic context from source properties.

        Maps timezone, URL domain, and source name to a country code,
        then queries DB for team candidates from that country's leagues.

        This is the ROOT CAUSE FIX: the system processes content without knowing
        WHERE it comes from. A Brazilian portal talks about Brazilian teams,
        but DeepSeek gets no geographic hint. Now it does.

        Args:
            source: RadarSource with url, name, source_timezone

        Returns:
            Tuple of (country_code, source_context_string_for_prompt)
            country_code is like "BR", "IT", "GB" or None if unknown
            source_context_string is a formatted hint for DeepSeek or None
        """
        # Strategy 1: Timezone → country (most reliable)
        tz_country = self._TZ_COUNTRY_MAP.get(source.source_timezone or "") if source.source_timezone else None

        # Strategy 2: URL hostname → country (hostname-only to prevent false positives like /player-id/)
        from urllib.parse import urlparse

        url_lower = (source.url or "").lower()  # Kept for Strategy 3 keyword matching
        domain_country = None
        try:
            parsed_url = urlparse(source.url or "")
            hostname = parsed_url.netloc.lower()
        except Exception:
            hostname = url_lower
        for suffix, country in sorted(self._DOMAIN_COUNTRY_MAP.items(), key=lambda x: -len(x[0])):
            if suffix in hostname:
                domain_country = country
                break

        # Strategy 3: Source name keywords → country
        name_lower = (source.name or "").lower()
        name_country = None
        for keyword, country in self._SOURCE_KEYWORD_MAP.items():
            if keyword in name_lower or keyword in url_lower:
                name_country = country
                break

        # Merge: timezone > domain > name
        country_code = tz_country or domain_country or name_country

        if not country_code or country_code == "INT":
            return None, None

        # Build context string for DeepSeek prompt
        country_names = {
            "BR": "Brazil", "AR": "Argentina", "MX": "Mexico", "HN": "Honduras",
            "GB": "United Kingdom", "IT": "Italy", "DE": "Germany", "FR": "France",
            "TR": "Turkey", "GR": "Greece", "NL": "Netherlands", "NO": "Norway",
            "PL": "Poland", "RU": "Russia", "ID": "Indonesia", "CN": "China",
            "JP": "Japan", "SG": "Singapore", "NG": "Nigeria", "EG": "Egypt",
            "ZA": "South Africa", "CO": "Colombia", "PE": "Peru", "CL": "Chile",
            "KR": "South Korea", "CZ": "Czech Republic",
        }

        country_name = country_names.get(country_code, country_code)

        # Try to get team candidates from DB for this country's leagues
        team_candidates = self._get_teams_for_country(country_code)

        context_parts = [f"  - Source country: {country_name}"]
        if team_candidates:
            candidates_str = ", ".join(team_candidates[:15])
            context_parts.append(f"  - Likely teams from this source's region: {candidates_str}")

        source_context_str = "\n".join(context_parts)
        logger.debug(
            f"🧠 [SOURCE-CONTEXT] {source.name}: country={country_code}, "
            f"teams={len(team_candidates)}"
        )

        return country_code, source_context_str

    def _get_teams_for_country(self, country_code: str) -> list[str]:
        """
        Get team names from DB for leagues associated with a country.

        Queries upcoming matches in the next 96h to find team names
        from leagues typically associated with the given country.
        """
        # Map country → league key patterns
        country_league_patterns: dict[str, list[str]] = {
            "BR": ["brazil"],
            "AR": ["argentina"],
            "MX": ["mexico"],
            "HN": ["honduras"],
            "GB": ["epl", "england", "championship", "league_one", "national_league"],
            "IT": ["italy", "serie_a", "serie_b"],
            "DE": ["germany", "bundesliga", "liga3"],
            "FR": ["france", "ligue"],
            "TR": ["turkey"],
            "GR": ["greece"],
            "NL": ["netherlands", "eredivisie"],
            "NO": ["norway"],
            "PL": ["poland"],
            "RU": ["russia"],
            "ID": ["indonesia"],
            "CN": ["china"],
            "JP": ["japan"],
            "KR": ["korea"],
            "NG": ["nigeria"],
            "EG": ["egypt"],
            "ZA": ["south_africa"],
            "CO": ["colombia"],
            "PE": ["peru"],
            "CL": ["chile"],
            "CZ": ["czech"],
        }

        patterns = country_league_patterns.get(country_code, [])
        if not patterns:
            return []

        try:
            from src.database.models import Match, SessionLocal

            db = SessionLocal()
            try:
                from datetime import timedelta
                now = datetime.now(timezone.utc)
                max_time = now + timedelta(hours=96)

                matches = (
                    db.query(Match)
                    .filter(Match.start_time >= now.replace(tzinfo=None))
                    .filter(Match.start_time <= max_time.replace(tzinfo=None))
                    .all()
                )

                teams: list[str] = []
                for m in matches:
                    league = getattr(m, "league", "") or ""
                    # Check if this match's league matches any of the country patterns
                    if any(p in league.lower() for p in patterns):
                        home = getattr(m, "home_team", None)
                        away = getattr(m, "away_team", None)
                        if home:
                            teams.append(home)
                        if away:
                            teams.append(away)

                return sorted(set(teams))[:20]
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"[SOURCE-CONTEXT] DB lookup failed for {country_code}: {e}")
            return []

    def _fuzzy_match_team(self, extracted_team: str) -> str | None:
        """
        V4.0: Normalize extracted team name against DB using fuzzy matching.

        ROOT CAUSE FIX: DeepSeek extracts "São Paulo" but the DB has "Sao Paulo FC".
        The substring match in radar_enrichment.find_upcoming_match() fails because:
        - Accents: "São" ≠ "Sao"
        - Suffixes: "São Paulo" not in "Sao Paulo FC" (the reverse works, but not both ways)

        This method:
        1. Gets all team names from upcoming matches in DB
        2. Uses thefuzz (already in requirements.txt) for fuzzy matching
        3. Returns the canonical DB team name if match found (threshold >= 80)
        4. Returns the original name if no better match found

        Uses the same thefuzz library already used in:
        - data_provider.py:338 (team search)
        - verification_layer.py:1881 (player matching)
        - text_normalizer.py:88 (general fuzzy matching)

        Args:
            extracted_team: Team name extracted by DeepSeek

        Returns:
            Canonical team name from DB, or original if no match found
        """
        if not extracted_team:
            return extracted_team

        # Try thefuzz import (already in requirements.txt, used elsewhere in the bot)
        try:
            from thefuzz import fuzz
        except ImportError:
            return extracted_team

        # Get accent folding utility (already used in text_normalizer.py)
        fold_accents_fn = None
        try:
            from src.utils.text_normalizer import fold_accents as fa
            fold_accents_fn = fa
        except ImportError:
            pass

        # Get all team names from upcoming matches in DB
        try:
            from src.database.models import Match, SessionLocal

            db = SessionLocal()
            try:
                now = datetime.now(timezone.utc)
                max_time = now + timedelta(hours=96)

                matches = (
                    db.query(Match)
                    .filter(Match.start_time >= now.replace(tzinfo=None))
                    .filter(Match.start_time <= max_time.replace(tzinfo=None))
                    .all()
                )

                # Build candidate list from DB
                db_teams: list[str] = []
                for m in matches:
                    home = getattr(m, "home_team", None)
                    away = getattr(m, "away_team", None)
                    if home:
                        db_teams.append(home)
                    if away:
                        db_teams.append(away)

                if not db_teams:
                    return extracted_team

                # Deduplicate
                db_teams = list(set(db_teams))

                # Helper: normalize a string for comparison
                def _normalize(text: str) -> str:
                    t = text.lower().strip()
                    if fold_accents_fn:
                        t = fold_accents_fn(t)
                    return t

                extracted_norm = _normalize(extracted_team)

                # Strategy 1: Exact match after accent folding (most common case)
                for db_team in db_teams:
                    if _normalize(db_team) == extracted_norm:
                        return db_team

                # Strategy 2: thefuzz token_set_ratio (handles partial names, word reordering)
                best_match = None
                best_score = 0
                FUZZY_THRESHOLD = 80  # Same threshold used in verification_layer.py

                for db_team in db_teams:
                    score = fuzz.token_set_ratio(extracted_team, db_team)
                    if score > best_score:
                        best_score = score
                        best_match = db_team

                if best_score >= FUZZY_THRESHOLD and best_match:
                    logger.debug(
                        f"[FUZZY-MATCH] '{extracted_team}' → '{best_match}' "
                        f"(score={best_score})"
                    )
                    return best_match

                # No good match found — return original
                return extracted_team

            finally:
                db.close()

        except Exception as e:
            logger.debug(f"[FUZZY-MATCH] Team normalization failed: {e}")
            return extracted_team

    def _has_football_keywords(self, content: str) -> bool:
        """
        Quick check if content has basic football keywords.

        Used to decide if DeepSeek analysis is worth trying
        when no high-value pattern was detected.
        """
        football_keywords = [
            "football",
            "soccer",
            "match",
            "game",
            "team",
            "player",
            "goal",
            "league",
            "cup",
            "coach",
            "manager",
            "squad",
            "calcio",
            "fútbol",
            "futebol",
            "fußball",
            "voetbal",
            "partita",
            "partido",
            "jogo",
            "spiel",
            "wedstrijd",
        ]
        content_lower = content.lower()
        return any(kw in content_lower for kw in football_keywords)

    def _compute_prefilter_score(self, content: str) -> float:
        """
        V7.3: Compute quick pre-filter score to decide if DeepSeek is worth calling.

        This reduces unnecessary API calls by ~30-40% by filtering out
        content that is unlikely to be betting-relevant.

        Score components:
        - Injury/absence keywords: +0.3
        - Team/player mentions: +0.2
        - Match context (vs, against): +0.2
        - Negative sentiment (out, miss, doubt): +0.2
        - Recency indicators (today, tomorrow): +0.1

        Returns:
            Score 0.0-1.0 (threshold 0.3 for DeepSeek call)
        """
        if not content:
            return 0.0

        content_lower = content.lower()
        score = 0.0

        # Injury/absence keywords (+0.3)
        injury_keywords = [
            "injury",
            "injured",
            "infortunio",
            "lesión",
            "lesão",
            "out",
            "miss",
            "absent",
            "assente",
            "ausente",
            "ruled out",
            "sidelined",
            "unavailable",
            "suspended",
            "sospeso",
            "suspenso",
            "sancionado",
            "doubt",
            "doubtful",
            "dubbio",
            "duda",
        ]
        if any(kw in content_lower for kw in injury_keywords):
            score += 0.3

        # Team/player context (+0.2)
        team_indicators = [
            "team",
            "squad",
            "club",
            "squadra",
            "equipo",
            "equipe",
            "player",
            "giocatore",
            "jugador",
            "jogador",
            "striker",
            "midfielder",
            "defender",
            "goalkeeper",
            "attaccante",
            "centrocampista",
            "difensore",
            "portiere",
        ]
        if any(kw in content_lower for kw in team_indicators):
            score += 0.2

        # Match context (+0.2)
        match_indicators = [
            " vs ",
            " v ",
            "against",
            "contro",
            "contra",
            "match",
            "game",
            "partita",
            "partido",
            "jogo",
            "fixture",
            "clash",
            "derby",
        ]
        if any(kw in content_lower for kw in match_indicators):
            score += 0.2

        # Negative sentiment for betting (+0.2)
        negative_betting = [
            "will miss",
            "won't play",
            "not available",
            "ruled out",
            "sidelined",
            "benched",
            "non giocherà",
            "no jugará",
            "não jogará",
            "crisis",
            "emergency",
            "blow",
            "setback",
        ]
        if any(kw in content_lower for kw in negative_betting):
            score += 0.2

        # Recency indicators (+0.1)
        recency = [
            "today",
            "tomorrow",
            "tonight",
            "weekend",
            "oggi",
            "domani",
            "stasera",
            "hoy",
            "mañana",
            "hoje",
            "amanhã",
        ]
        if any(kw in content_lower for kw in recency):
            score += 0.1

        return min(score, 1.0)

    async def _handoff_to_main_pipeline(self, alert: RadarAlert, content: str) -> None:
        """
        CROSS-PROCESS HANDOFF: Drop high-confidence news in shared DB inbox.

        When confidence >= 0.7, instead of just sending Telegram alert,
        also save trigger to NewsLog table for Main Pipeline to process.

        This enables full AI triangulation analysis on high-confidence radar alerts.

        Args:
            alert: RadarAlert with enrichment_context
            content: Original news content (for forced narrative)
        """
        if not alert.enrichment_context or not alert.enrichment_context.has_match():
            logger.debug("⏭️ [NEWS-RADAR] Skipping handoff - no match found")
            return

        try:
            from src.database.models import NewsLog, SessionLocal

            # V13.0 COVE FIX: Wrap synchronous DB operations in asyncio.to_thread()
            # to prevent event loop blocking
            def db_operations():
                db = SessionLocal()
                try:
                    # V15.0 FIX: Apply optimizer weight to radar handoff score (Learning Loop Integration)
                    # This ensures that weights learned from historical performance are applied
                    # to radar handoff scores
                    base_score = int(alert.confidence * 10) if alert.confidence is not None else 8
                    score = base_score

                    try:
                        from src.analysis.optimizer import get_optimizer
                        from src.database.models import Match

                        optimizer = get_optimizer()

                        # Query match to get league information
                        match = (
                            db.query(Match)
                            .filter(Match.id == alert.enrichment_context.match_id)
                            .first()
                        )
                        league = match.league if match else None

                        # Radar handoff doesn't have a specific market, use None
                        # The optimizer will use league-level weights
                        if league:
                            # COVE FIX: Use apply_weight_to_score_with_original to preserve
                            # original AI score for threshold checks
                            original_score, adjusted_score, weight_log_msg, weight = (
                                optimizer.apply_weight_to_score_with_original(
                                    base_score=score,
                                    league=league,
                                    market=None,  # No specific market for radar handoff
                                    driver=alert.category,  # Use alert category as driver
                                )
                            )
                            if weight_log_msg:
                                logger.info(weight_log_msg)
                            # COVE FIX: Use ORIGINAL AI score for NewsLog, not adjusted
                            score = original_score
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to apply optimizer weight to radar handoff: {e}")
                        # Continue with original score

                    # Create NewsLog entry with PENDING_RADAR_TRIGGER status
                    news_log = NewsLog(
                        match_id=alert.enrichment_context.match_id,
                        url=alert.source_url,
                        summary=f"RADAR HANDOFF: {alert.summary}",
                        score=score,
                        category=alert.category,
                        affected_team=alert.affected_team,
                        status="PENDING_RADAR_TRIGGER",  # Special status for cross-process handoff
                        sent=False,
                        source="news_radar",
                        source_confidence=alert.confidence,
                        confidence=alert.confidence * 100
                        if alert.confidence is not None
                        else None,  # V11.1: Convert 0-1 to 0-100 for BettingQuant, handle None
                        # Store original content as forced narrative
                        # Use verification_reason to store the full content
                        verification_reason=content[:10000],  # Limit to 10KB
                    )

                    db.add(news_log)
                    db.commit()

                    return True, None
                except Exception as e:
                    db.rollback()
                    return False, str(e)
                finally:
                    db.close()

            success, error = await asyncio.to_thread(db_operations)

            if success:
                logger.info(
                    f"✅ [NEWS-RADAR] CROSS-PROCESS HANDOFF: "
                    f"Match {alert.enrichment_context.match_id} "
                    f"({alert.enrichment_context.home_team} vs {alert.enrichment_context.away_team}) "
                    f"queued for full AI analysis"
                )
            else:
                logger.error(f"❌ [NEWS-RADAR] Failed to save handoff to DB: {error}")

        except ImportError:
            logger.warning("⚠️ [NEWS-RADAR] Database models not available for handoff")
        except Exception as e:
            logger.error(f"❌ [NEWS-RADAR] Handoff failed: {e}")

    async def _enrich_alert(self, alert: RadarAlert) -> RadarAlert:
        """
        V1.3: Enrich alert with database context (classifica, biscotto).

        Light enrichment that adds context without heavy API calls.
        Uses data already in database or FotMob cache.

        V7.3: Always sets enrichment_context (even if no match found)
        to allow fixture correlation check in Step 9.

        Args:
            alert: RadarAlert to enrich

        Returns:
            Same alert with enrichment_context populated (if available)
        """
        if not _ENRICHMENT_AVAILABLE:
            logger.debug("⚠️ [NEWS-RADAR] Enrichment module not available")
            return alert

        # Skip if no team to enrich
        if not alert.affected_team or alert.affected_team == "Unknown":
            return alert

        try:
            # Get enrichment context asynchronously
            context = await enrich_radar_alert_async(alert.affected_team)

            # V7.3: Always set context (even if no match) for fixture correlation
            if context:
                alert.enrichment_context = context
                if context.has_match():
                    logger.info(
                        f"✨ [NEWS-RADAR] Enriched alert for {alert.affected_team}: "
                        f"{context.team_zone}, match {context.home_team} vs {context.away_team}"
                    )
                else:
                    logger.debug(f"📭 [NEWS-RADAR] No upcoming match for {alert.affected_team}")

        except Exception as e:
            # Enrichment failure should not block alert
            logger.warning(f"⚠️ [NEWS-RADAR] Enrichment failed for {alert.affected_team}: {e}")

        return alert

    async def _tavily_enrich(self, content: str, url: str) -> str | None:
        """
        V7.0: Use Tavily to enrich ambiguous content before DeepSeek.

        Called when initial analysis has confidence between 0.5 and 0.7.

        Args:
            content: Original content text
            url: Source URL for context

        Returns:
            Enriched context string or None

        Requirements: 4.1, 4.2
        """
        if not self._tavily or not self._tavily.is_available():
            return None

        if not self._tavily_budget or not self._tavily_budget.can_call("news_radar"):
            logger.debug("📊 [NEWS-RADAR] Tavily budget limit reached")
            return None

        try:
            # Extract key terms from content for search
            # Use first 200 chars as search context
            search_context = content[:200].replace("\n", " ").strip()

            # Build search query
            query = f"football soccer {search_context}"

            # V7.1: Use native Tavily news parameters for better filtering
            response = self._tavily.search(
                query=query,
                search_depth="basic",
                max_results=3,
                include_answer=True,
                topic="news",
                days=3,
            )

            if response:
                self._tavily_budget.record_call("news_radar")

                enrichment_parts: list[str] = []

                if response.answer:
                    enrichment_parts.append(f"[TAVILY CONTEXT]\n{response.answer}")

                if response.results:
                    snippets = [f"• {r.content[:150]}" for r in response.results[:2]]
                    if snippets:
                        enrichment_parts.append("\n".join(snippets))

                if enrichment_parts:
                    logger.info(f"🔍 [NEWS-RADAR] Tavily enrichment found for {url[:50]}...")
                    return "\n".join(enrichment_parts)

            return None

        except Exception as e:
            logger.warning(f"⚠️ [NEWS-RADAR] Tavily enrichment failed: {e}")
            return None

    def get_stats(self) -> dict[str, Any]:
        """Get monitor statistics."""
        return {
            "running": self._running,
            "sources_count": len(self._config.sources),
            "urls_scanned": self._urls_scanned,
            "alerts_sent": self._alerts_sent,
            "cache_size": self._content_cache.size_sync() if self._content_cache else 0,
            "last_cycle_time": self._last_cycle_time.isoformat() if self._last_cycle_time else None,
            "extractor_stats": self._extractor.get_stats() if self._extractor else {},
            "alerter_stats": self._alerter.get_stats() if self._alerter else {},
        }


# ============================================
# V11.0: GLOBAL PARALLEL RADAR (4-TAB ARCHITECTURE)
# ============================================


class GlobalRadarMonitor:
    """
    V11.0: Global Parallel Radar with 4-Tab Architecture.

    Implements GLOBAL EYES: monitors ALL active leagues simultaneously using
    4 parallel async contexts (LATAM, ASIA, AFRICA, GLOBAL).

    Architecture:
    - 1 Playwright Browser with 4 Async Contexts
    - Each context scans assigned sources/leagues
    - Parallel discovery via asyncio.gather()
    - Intelligence Queue for serialized processing (safety valve)

    Flow:
    1. Initialize 1 Playwright Browser
    2. Create 4 Async Contexts: LATAM, ASIA, AFRICA, GLOBAL
    3. Assign sources to contexts based on continent
    4. Run 4 scanning loops concurrently using asyncio.gather()
    5. Discovered signals -> Queue.put()
    6. Main loop -> Queue.get() -> DeepSeek -> DB

    Safety:
    - Prevents DB locks by serializing heavy lifting
    - Prevents API rate limits by controlling queue consumption
    - Budget checks for Tavily and Brave APIs

    Note: This module uses 4 contexts (LATAM, ASIA, AFRICA, GLOBAL) for news source
    categorization, which is different from global_orchestrator.py that uses 3 continents
    for match monitoring. The GLOBAL context here serves as a fallback for uncategorized
    global news sources.
    """

    # Continent mappings for source assignment
    # Note: GLOBAL context is used as fallback for uncategorized sources
    CONTINENT_CONTEXTS = ["LATAM", "ASIA", "AFRICA", "GLOBAL"]

    def __init__(self, config_file: str = DEFAULT_CONFIG_FILE):
        """
        Initialize GlobalRadarMonitor.

        Args:
            config_file: Path to news radar sources config
        """
        self._config_file = config_file
        self._config: RadarConfig = RadarConfig()

        # Browser and contexts
        self._playwright = None
        self._browser = None
        self._contexts: dict[str, Any] = {}  # context_name -> BrowserContext

        # Components
        self._content_cache: ContentCache | None = None
        self._deepseek: DeepSeekFallback | None = None
        self._alerter: TelegramAlerter | None = None

        # Intelligence Queue (safety valve)
        self._discovery_queue: DiscoveryQueue | None = None

        # Budget managers
        self._tavily = None
        self._tavily_budget = None
        self._brave = None
        self._brave_budget = None

        # Circuit breakers per source
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

        # V13.1: Scrapling-based stealth extractor for WAF bypass
        self._article_reader = None
        if _ARTICLE_READER_AVAILABLE and _ArticleReader is not None:
            try:
                self._article_reader = _ArticleReader()
                logger.debug("✅ [GLOBAL-RADAR] ArticleReader initialized for stealth extraction")
            except Exception as e:
                logger.warning(f"⚠️ [GLOBAL-RADAR] ArticleReader init failed: {e}")
                self._article_reader = None

        # State
        self._running = False
        self._stop_event = asyncio.Event()
        self._scan_tasks: list[asyncio.Task] = []

        # Stats
        self._urls_scanned = 0
        self._alerts_sent = 0
        self._excluded_count = 0  # VPS FIX: Track excluded content statistics
        self._last_cycle_time: datetime | None = None

        logger.info("🌐 [GLOBAL-RADAR] V11.0 Monitor created")

    async def start(self) -> bool:
        """
        Start GlobalRadarMonitor with 4-tab parallel architecture.

        Returns True if started successfully.
        """
        if self._running:
            logger.warning("⚠️ [GLOBAL-RADAR] Already running")
            return True

        try:
            # Load configuration
            self._config = load_config(self._config_file)

            if not self._config.sources:
                logger.warning("⚠️ [GLOBAL-RADAR] No sources configured")

            # Initialize Intelligence Queue (use global singleton for data sharing)
            self._discovery_queue = get_discovery_queue()
            logger.info("✅ [GLOBAL-RADAR] Intelligence Queue initialized (global singleton)")

            # Initialize components
            self._content_cache = ContentCache(
                max_entries=DEFAULT_CACHE_MAX_ENTRIES,
                ttl_hours=self._config.global_settings.cache_ttl_hours,
            )

            # Initialize DeepSeek and alerter
            self._deepseek = DeepSeekFallback()
            self._alerter = TelegramAlerter()

            # Initialize Tavily and Brave budget managers
            try:
                from src.ingestion.tavily_budget import get_budget_manager as get_tavily_budget
                from src.ingestion.tavily_provider import get_tavily_provider

                self._tavily = get_tavily_provider()
                self._tavily_budget = get_tavily_budget()
                tavily_status = "enabled" if self._tavily.is_available() else "disabled"
                logger.info(f"🔍 [GLOBAL-RADAR] Tavily {tavily_status}")
            except ImportError:
                self._tavily = None
                self._tavily_budget = None
                logger.debug("⚠️ [GLOBAL-RADAR] Tavily not available")

            try:
                from src.ingestion.brave_budget import get_budget_manager as get_brave_budget
                from src.ingestion.brave_provider import get_brave_provider

                self._brave = get_brave_provider()
                self._brave_budget = get_brave_budget()
                brave_status = "enabled" if self._brave.is_available() else "disabled"
                logger.info(f"🔍 [GLOBAL-RADAR] Brave {brave_status}")
            except ImportError:
                self._brave = None
                self._brave_budget = None
                logger.debug("⚠️ [GLOBAL-RADAR] Brave not available")

            # Initialize Playwright Browser
            if not await self._initialize_browser():
                logger.error("❌ [GLOBAL-RADAR] Failed to initialize browser")
                return False

            # Create 4 async contexts (LATAM, ASIA, AFRICA, GLOBAL)
            await self._create_contexts()

            # Start scan loops for all 4 contexts
            self._running = True
            self._stop_event.clear()

            # Start 4 parallel scan tasks
            for context_name in self.CONTINENT_CONTEXTS:
                task = asyncio.create_task(self._context_scan_loop(context_name))
                self._scan_tasks.append(task)

            logger.info(
                "✅ [GLOBAL-RADAR] V11.0 Started with 4 parallel contexts (LATAM, ASIA, AFRICA, GLOBAL)"
            )
            logger.info(f"   Contexts: {', '.join(self.CONTINENT_CONTEXTS)}")
            logger.info(f"   Sources: {len(self._config.sources)}")
            return True

        except Exception as e:
            logger.error(f"❌ [GLOBAL-RADAR] Failed to start: {e}")
            return False

    async def stop(self) -> bool:
        """
        Stop GlobalRadarMonitor gracefully.
        """
        if not self._running:
            return True

        logger.info("🛑 [GLOBAL-RADAR] Stopping...")

        self._running = False
        self._stop_event.set()

        # V13.1: Close ArticleReader
        if self._article_reader:
            try:
                await self._article_reader.close()
            except Exception:
                pass
            self._article_reader = None

        # Cancel all scan tasks
        for task in self._scan_tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self._scan_tasks:
            await asyncio.gather(*self._scan_tasks, return_exceptions=True)

        self._scan_tasks: list[dict[str, Any]] = []

        # Close all contexts
        for context_name, context in self._contexts.items():
            try:
                await context.close()
                logger.debug(f"✅ [GLOBAL-RADAR] Closed context: {context_name}")
            except Exception as e:
                logger.warning(f"⚠️ [GLOBAL-RADAR] Error closing {context_name}: {e}")

        # Close browser
        if self._browser:
            await self._browser.close()

        if self._playwright:
            await self._playwright.stop()

        logger.info("✅ [GLOBAL-RADAR] Stopped")
        return True

    async def _initialize_browser(self) -> bool:
        """
        Initialize Playwright browser with stealth mode.
        """
        try:
            from playwright.async_api import async_playwright

            logger.info("🌐 [GLOBAL-RADAR] Launching Playwright...")
            self._playwright = await async_playwright().start()

            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                    "--no-sandbox",
                    "--disable-extensions",
                ],
            )

            logger.info("✅ [GLOBAL-RADAR] Playwright initialized")
            return True

        except ImportError:
            logger.error("❌ [GLOBAL-RADAR] Playwright not installed")
            return False
        except Exception as e:
            logger.error(f"❌ [GLOBAL-RADAR] Failed to initialize Playwright: {e}")
            return False

    async def _create_contexts(self) -> None:
        """
        Create 4 async contexts: LATAM, ASIA, AFRICA, GLOBAL.

        Each context gets its own browser context for isolated scanning.
        Note: The GLOBAL context is used as a fallback for uncategorized news sources,
        which is different from global_orchestrator.py that uses 3 continents for match monitoring.
        """
        for context_name in self.CONTINENT_CONTEXTS:
            try:
                context = await self._browser.new_context(
                    user_agent=f"EarlyBird-Radar-{context_name}/11.0"
                )
                self._contexts[context_name] = context
                logger.info(f"✅ [GLOBAL-RADAR] Created context: {context_name}")
            except Exception as e:
                logger.error(f"❌ [GLOBAL-RADAR] Failed to create {context_name}: {e}")

    def _assign_sources_to_contexts(self) -> dict[str, list[RadarSource]]:
        """
        Assign sources to contexts based on continent.

        Returns:
            Dict mapping context_name -> list of sources
        """
        context_sources = {ctx: [] for ctx in self.CONTINENT_CONTEXTS}

        for source in self._config.sources:
            # Determine which context this source belongs to
            assigned_context = self._determine_context_for_source(source)
            context_sources[assigned_context].append(source)

        # Log assignment
        for context_name, sources in context_sources.items():
            logger.info(f"📋 [GLOBAL-RADAR] {context_name}: {len(sources)} sources assigned")

        return context_sources

    def _determine_context_for_source(self, source: RadarSource) -> str:
        """
        Determine which context a source should be assigned to.

        This is a simplified implementation. In production, you'd use:
        - Source URL analysis
        - League mapping
        - Continent metadata

        Args:
            source: RadarSource to assign

        Returns:
            Context name (LATAM, ASIA, AFRICA, or GLOBAL)
            Note: GLOBAL is used as fallback for uncategorized sources
        """
        # Simple heuristic based on source name or URL
        source_lower = source.name.lower() if source.name else ""
        url_lower = source.url.lower()

        # Check for LATAM indicators
        latam_keywords = ["brazil", "argentina", "mexico", "colombia", "chile", "peru"]
        if any(kw in source_lower or kw in url_lower for kw in latam_keywords):
            return "LATAM"

        # Check for ASIA indicators
        asia_keywords = ["japan", "korea", "china", "india", "thailand", "vietnam"]
        if any(kw in source_lower or kw in url_lower for kw in asia_keywords):
            return "ASIA"

        # Check for AFRICA indicators
        africa_keywords = ["south africa", "nigeria", "egypt", "morocco", "ghana"]
        if any(kw in source_lower or kw in url_lower for kw in africa_keywords):
            return "AFRICA"

        # Default to GLOBAL
        return "GLOBAL"

    async def _context_scan_loop(self, context_name: str) -> None:
        """
        Scan loop for a specific context.

        Each context runs its own scan loop independently.
        """
        logger.info(f"🔄 [GLOBAL-RADAR] {context_name} scan loop started")

        while self._running and not self._stop_event.is_set():
            try:
                # Get sources assigned to this context
                context_sources = self._assign_sources_to_contexts()
                assigned_sources = context_sources.get(context_name, [])

                if not assigned_sources:
                    await asyncio.sleep(60)
                    continue

                # Scan sources for this context
                await self._scan_context_sources(context_name, assigned_sources)

                # Wait before next cycle
                interval = self._config.global_settings.default_scan_interval_minutes * 60
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                    break
                except asyncio.TimeoutError:
                    pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [GLOBAL-RADAR] {context_name} scan error: {e}")
                await asyncio.sleep(60)

        logger.info(f"🛑 [GLOBAL-RADAR] {context_name} scan loop stopped")

    async def _scan_context_sources(self, context_name: str, sources: list[RadarSource]) -> int:
        """
        Scan all sources assigned to a context.

        Args:
            context_name: Name of context
            sources: List of sources to scan

        Returns:
            Number of signals discovered
        """
        signals_discovered = 0
        context = self._contexts.get(context_name)

        if not context:
            logger.warning(f"⚠️ [GLOBAL-RADAR] Context not found: {context_name}")
            return 0

        # Filter sources due for scanning
        due_sources = [s for s in sources if s.is_due_for_scan()]
        due_sources.sort(key=lambda s: s.priority)

        if not due_sources:
            return 0

        logger.info(f"⚡ [GLOBAL-RADAR] {context_name}: Scanning {len(due_sources)} sources")

        for source in due_sources:
            try:
                # Check circuit breaker
                breaker = self._get_circuit_breaker(source.url)
                if not breaker.can_execute():
                    logger.debug(f"🔴 [GLOBAL-RADAR] Skipping {source.name} (circuit OPEN)")
                    continue

                # Extract content
                content = await self._extract_content_from_source(context, source)

                if not content:
                    breaker.record_failure()
                    continue

                breaker.record_success()

                # Process content
                signal = await self._process_content(source, content)

                if signal:
                    # Push to intelligence queue
                    # V11.0 FIX: Use "GLOBAL" as league key so items can be retrieved during match analysis
                    # The pop_for_match() method now includes GLOBAL items for all matches
                    self._discovery_queue.push(
                        data=signal,
                        league_key="GLOBAL",  # Use GLOBAL key for cross-league discoveries
                        team=signal.get("team", "Unknown"),
                        title=signal.get("title", ""),
                        snippet=signal.get("snippet", ""),
                        url=signal.get("url", source.url),
                        source_name=source.name,
                        category=signal.get("category", "OTHER"),
                        confidence=signal.get("confidence", 0.0),
                    )
                    signals_discovered += 1
                    logger.info(
                        f"📥 [GLOBAL-RADAR] {context_name}: Signal queued - "
                        f"{signal.get('team', 'Unknown')} ({signal.get('category', 'OTHER')})"
                    )

            except Exception as e:
                logger.error(f"❌ [GLOBAL-RADAR] Error scanning {source.name}: {e}")
                breaker.record_failure()

        return signals_discovered

    async def _extract_content_from_source(self, context: Any, source: RadarSource) -> str | None:
        """
        Extract content from a source using given context.

        Args:
            context: Playwright BrowserContext
            source: RadarSource to extract from

        Returns:
            Extracted content or None
        """
        try:
            # Use HTTP extraction first (faster)
            if source.navigation_mode == "single":
                content = await self._extract_http(source.url)
                if content:
                    return content

            # Fallback to Playwright
            page = await context.new_page()
            try:
                await page.goto(source.url, timeout=30000)
                await page.wait_for_load_state("networkidle", timeout=15000)
                content = await page.inner_text("body")
                return content
            finally:
                await page.close()

        except Exception as e:
            logger.debug(f"⚠️ [GLOBAL-RADAR] Extraction failed for {source.url}: {e}")
            return None

    async def _extract_http(self, url: str) -> str | None:
        """
        HTTP-based content extraction with WAF bypass.

        V8.1: Uses centralized HTTP client with rate limiting to prevent bans.
        V13.1: Uses ArticleReader (Scrapling) for TLS fingerprint impersonation.
               Fixes: bot User-Agent, missing trafilatura, WAF block detection.

        Args:
            url: URL to extract from

        Returns:
            Extracted clean text or None
        """
        # V13.1: Primary path - Scrapling stealth extraction
        if self._article_reader is not None:
            try:
                result = await self._article_reader.fetch_and_extract(url, timeout=15)
                if result["success"] and result["text"]:
                    if len(result["text"]) >= HTTP_MIN_CONTENT_LENGTH:
                        method = (
                            "Scrapling/browser"
                            if result["method"] == "browser"
                            else "Scrapling/HTTP"
                        )
                        logger.debug(f"⚡ [GLOBAL-RADAR] {method} success: {url[:40]}...")
                        return result["text"]
                logger.debug(f"⚠️ [GLOBAL-RADAR] Scrapling failed for {url[:40]}...")
            except Exception as e:
                logger.debug(f"⚠️ [GLOBAL-RADAR] Scrapling error: {e}")

        # Legacy fallback - standard httpx
        try:
            http_client = get_http_client()
            response = await asyncio.to_thread(
                http_client.get_sync,
                url,
                rate_limit_key="news_radar",
                use_fingerprint=False,
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )

            if response.status_code in WAF_BLOCK_CODES:
                logger.warning(
                    f"🛡️ [GLOBAL-RADAR] WAF block ({response.status_code}): "
                    f"{url.split('//')[1].split('/')[0] if '//' in url else url[:30]}"
                )
                return None

            if response.status_code == 200:
                content = response.text
                if len(content) >= HTTP_MIN_CONTENT_LENGTH:
                    # V13.1: Apply trafilatura for clean text (was missing before)
                    text = None
                    if _extract_with_fallback is not None:
                        text, _ = _extract_with_fallback(content)
                    if text:
                        return text
                    return content[:MAX_TEXT_LENGTH]

            return None

        except Exception as e:
            logger.debug(f"⚠️ [GLOBAL-RADAR] HTTP extraction failed: {e}")
            return None

    async def _process_content(self, source: RadarSource, content: str) -> dict[str, Any] | None:
        """
        Process extracted content to detect betting-relevant signals.

        Args:
            source: Source that provided content
            content: Extracted content

        Returns:
            Signal dict or None
        """
        # Check cache
        if await self._content_cache.is_cached(content):
            return None

        # Apply exclusion filter
        exclusion_filter = get_exclusion_filter()
        if exclusion_filter.is_excluded(content):
            logger.debug(f"🚫 [GLOBAL-RADAR] Content excluded: {source.name}")
            self._excluded_count += 1  # VPS FIX: Track excluded content statistics
            return None

        # Analyze relevance
        analysis = self._analyze_relevance(source, content)

        if (
            not analysis
            or analysis.confidence < self._config.global_settings.alert_confidence_threshold
        ):
            return None

        # Add to cache
        await self._content_cache.add(content)

        return {
            "team": analysis.affected_team or "Unknown",  # COVE FIX 2026-03-07: Use correct field
            "title": analysis.summary,  # COVE FIX 2026-03-07: Use summary as title
            "snippet": analysis.summary,  # COVE FIX 2026-03-07: Use summary as snippet
            "url": source.url,
            "category": analysis.category,
            "confidence": analysis.confidence,
            "betting_impact": analysis.betting_impact,
        }

    def _analyze_relevance(self, source: RadarSource, content: str) -> AnalysisResult | None:
        """
        Analyze content relevance for betting signals.

        Args:
            source: Source that provided content
            content: Extracted content

        Returns:
            AnalysisResult or None
        """
        try:
            # Use shared content analysis utilities
            from src.utils.content_analysis import get_relevance_analyzer

            analyzer = get_relevance_analyzer()
            return analyzer.analyze(content)

        except Exception as e:
            logger.error(f"❌ [GLOBAL-RADAR] Analysis failed: {e}")
            return None

    def _get_circuit_breaker(self, url: str) -> CircuitBreaker:
        """Get or create circuit breaker for a URL."""
        if url not in self._circuit_breakers:
            self._circuit_breakers[url] = CircuitBreaker()
        return self._circuit_breakers[url]

    def get_stats(self) -> dict[str, Any]:
        """Get monitor statistics."""
        return {
            "running": self._running,
            "contexts": list(self._contexts.keys()),
            "sources_count": len(self._config.sources),
            "urls_scanned": self._urls_scanned,
            "alerts_sent": self._alerts_sent,
            "queue_size": self._discovery_queue.size() if self._discovery_queue else 0,
            "last_cycle_time": self._last_cycle_time.isoformat() if self._last_cycle_time else None,
        }


# Convenience function for easy access
def get_global_radar_monitor(config_file: str = DEFAULT_CONFIG_FILE) -> GlobalRadarMonitor:
    """
    Get a GlobalRadarMonitor instance.

    Args:
        config_file: Path to news radar sources config

    Returns:
        GlobalRadarMonitor instance
    """
    return GlobalRadarMonitor(config_file)
