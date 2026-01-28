"""
EarlyBird Configuration Module

Centralized configuration for the EarlyBird betting intelligence system.
All environment-specific settings are loaded from .env file.

VPS Compatibility Notes:
- All paths use relative paths (data/, logs/)
- File operations include proper error handling
- Environment variables have sensible defaults
"""

import os
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ========================================
# PROJECT PATHS (VPS Compatible)
# ========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Ensure directories exist (VPS safety)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# ========================================
# NATIVE KEYWORDS FOR OSINT (Multi-language)
# ========================================
NATIVE_KEYWORDS: Dict[str, List[str]] = {
    "pt": ["escalação", "poupados", "reservas", "sub-20", "desfalques", "time misto"],
    "tr": ["kadro", "yedek", "sakat", "rotasyon", "gençler", "eksik"],
    "pl": ["skład", "kontuzja", "rezerwowy", "absencja", "młodzież"],
    "ro": ["echipa", "absenti", "rezerve", "indisponibili", "jucatori menajati"],
    "es": ["nómina", "alterna", "bajas", "lesionados", "suplentes", "rotación"],
}

# ========================================
# API CONFIGURATION
# ========================================
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
MEDIASTACK_API_KEY = os.getenv("MEDIASTACK_API_KEY", "")

# ========================================
# TELEGRAM CONFIGURATION (Centralized)
# ========================================
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "") or os.getenv("TELEGRAM_TOKEN", "")

# ========================================
# FOTMOB TEAM MAPPING (Lazy Import)
# ========================================
_TEAM_FOTMOB_IDS: Optional[Dict] = None


def get_team_fotmob_ids() -> Dict:
    """Lazy load FotMob team mapping to avoid circular imports."""
    global _TEAM_FOTMOB_IDS
    if _TEAM_FOTMOB_IDS is None:
        try:
            from src.ingestion.fotmob_team_mapping import TEAM_FOTMOB_IDS
            _TEAM_FOTMOB_IDS = TEAM_FOTMOB_IDS
        except ImportError:
            _TEAM_FOTMOB_IDS = {}
    return _TEAM_FOTMOB_IDS


# ========================================
# THRESHOLDS & TIME WINDOWS
# ========================================
MATCH_LOOKAHEAD_HOURS = 96  # Extended to 4 days for early odds tracking
ANALYSIS_WINDOW_HOURS = 72  # 72h = 3 days (captures weekend fixtures early)

# Alert thresholds
ALERT_THRESHOLD_HIGH = 8.6      # Minimum score for standard alerts ("Cream of the Crop")
ALERT_THRESHOLD_RADAR = 7.0     # Lower threshold when forced_narrative present (Radar boost)
SETTLEMENT_MIN_SCORE = 7.0      # Minimum highest_score_sent to include in settlement

# ========================================
# HOME ADVANTAGE BY LEAGUE (V4.3 - Deep Research)
# ========================================
# Home Advantage varies significantly by league culture and logistics.
# Values represent expected goal boost for home team (added to lambda).
# Source: Post-COVID analysis shows HA declining but still significant.
#
# High HA (0.35-0.45): Balkan leagues, Turkey, South America (hot atmosphere)
# Medium HA (0.25-0.35): Most European leagues
# Low HA (0.20-0.25): Bundesliga, Premier League (modern stadia, short travel)

HOME_ADVANTAGE_BY_LEAGUE: Dict[str, float] = {
    # HIGH HA - Intense atmospheres, long travel, passionate fans
    "soccer_turkey_super_league": 0.38,
    "soccer_greece_super_league": 0.40,
    "soccer_argentina_primera_division": 0.38,
    "soccer_brazil_serie_a": 0.35,
    "soccer_brazil_serie_b": 0.38,
    "soccer_mexico_ligamx": 0.35,
    "soccer_colombia_primera_a": 0.36,
    "soccer_usa_mls": 0.35,  # Long travel distances
    
    # MEDIUM-HIGH HA - Strong home cultures
    "soccer_scotland_premiership": 0.32,
    "soccer_portugal_primeira_liga": 0.32,
    "soccer_australia_aleague": 0.30,  # Travel factor
    "soccer_poland_ekstraklasa": 0.32,
    "soccer_romania_liga_i": 0.33,
    
    # MEDIUM HA - Standard European leagues
    "soccer_france_ligue_one": 0.28,
    "soccer_italy_serie_a": 0.28,
    "soccer_spain_la_liga": 0.27,
    "soccer_netherlands_eredivisie": 0.27,
    "soccer_belgium_first_div": 0.28,
    "soccer_austria_bundesliga": 0.28,
    "soccer_switzerland_super_league": 0.28,
    "soccer_norway_eliteserien": 0.28,
    
    # LOW HA - Modern stadia, standardized refereeing, short travel
    "soccer_england_premier_league": 0.25,
    "soccer_germany_bundesliga": 0.22,
    "soccer_germany_bundesliga2": 0.24,
    
    # ASIA - Variable
    "soccer_japan_j_league": 0.28,
    "soccer_china_superleague": 0.30,
    "soccer_korea_kleague1": 0.28,
    "soccer_saudi_pro_league": 0.32,
}

DEFAULT_HOME_ADVANTAGE = 0.30  # Default for leagues not in map


def get_home_advantage(league_key: str) -> float:
    """
    Get league-specific home advantage value.
    
    Args:
        league_key: League identifier string
        
    Returns:
        Home advantage factor (float)
    """
    if not league_key or not isinstance(league_key, str):
        return DEFAULT_HOME_ADVANTAGE
    return HOME_ADVANTAGE_BY_LEAGUE.get(league_key, DEFAULT_HOME_ADVANTAGE)


# ========================================
# LEAGUE TIERS FOR NEWS DECAY (V4.3)
# ========================================
# V4.3 Enhancement: League-adaptive decay rates
# 
# TIER 1 LEAGUES (fast markets): λ = 0.14 (half-life ~5 min)
# - Premier League, La Liga, Serie A, Bundesliga, Ligue 1
# - These markets react very quickly to news
#
# ELITE LEAGUES (slower markets): λ = 0.023 (half-life ~30 min)
# - Turkey, Argentina, Greece, Scotland, Australia, etc.
# - Niche markets with slower reaction times

TIER1_LEAGUES = {
    "soccer_england_premier_league",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga",
    "soccer_champions_league",
    "soccer_europa_league",
}

# Decay rates
NEWS_DECAY_LAMBDA_TIER1 = 0.14    # Fast decay: half-life ~5 min
NEWS_DECAY_LAMBDA_ELITE = 0.023   # Slow decay: half-life ~30 min

# Source-based decay modifiers (V4.3)
# Insider sources decay slower (news persists longer)
SOURCE_DECAY_MODIFIERS = {
    "insider_verified": 0.5,    # Decay 50% slower
    "beat_writer": 0.7,         # Decay 30% slower
    "beat_writer_priority": 0.7,
    "mainstream": 1.0,          # Normal decay
    "reddit": 1.2,              # Decay 20% faster
    "unknown": 1.5,             # Decay 50% faster
}


def get_news_decay_lambda(league_key: str) -> float:
    """
    V4.3: Get news decay lambda for a league.
    
    Tier 1 leagues (PL, La Liga, etc.) have fast-reacting markets,
    so news decays quickly (λ = 0.14, half-life ~5 min).
    
    Elite leagues (Turkey, Argentina, etc.) have slower markets,
    so news persists longer (λ = 0.023, half-life ~30 min).
    
    Args:
        league_key: League identifier
        
    Returns:
        Decay lambda value
    """
    if not league_key or not isinstance(league_key, str):
        return NEWS_DECAY_LAMBDA_ELITE
    
    if league_key in TIER1_LEAGUES:
        return NEWS_DECAY_LAMBDA_TIER1
    
    return NEWS_DECAY_LAMBDA_ELITE


def get_source_decay_modifier(source_type: str) -> float:
    """
    V4.3: Get decay modifier based on news source type.
    
    Insider sources decay slower because their information
    is often not yet priced into the market.
    
    Args:
        source_type: Type of source (e.g., 'beat_writer', 'reddit')
        
    Returns:
        Decay modifier (< 1.0 = slower decay, > 1.0 = faster decay)
    """
    if not source_type or not isinstance(source_type, str):
        return 1.0
    
    return SOURCE_DECAY_MODIFIERS.get(source_type.lower(), 1.0)


# ========================================
# BISCOTTO DETECTION THRESHOLDS
# ========================================
# A "Biscotto" is a mutually beneficial draw where both teams need 1 point.
# Bookmakers slash Draw odds when they suspect collusion.

BISCOTTO_SUSPICIOUS_LOW = 2.50    # Draw odd below this is suspicious
BISCOTTO_EXTREME_LOW = 2.00      # Draw odd below this is VERY suspicious
BISCOTTO_SIGNIFICANT_DROP = 15.0  # % drop from opening that triggers alert

# Biscotto keywords for news validation (multi-language)
BISCOTTO_KEYWORDS: Dict[str, List[str]] = {
    "en": ["convenient draw", "mutually beneficial", "both teams need", "point for both", 
           "boring match", "no motivation", "tacit agreement", "fixed match"],
    "pt": ["empate conveniente", "ambos precisam", "ponto para ambos", "jogo morno",
           "sem motivação", "acordo tácito", "combinado"],
    "tr": ["beraberlik yeterli", "her iki takım", "motivasyon yok", "anlaşmalı maç"],
    "pl": ["remis wystarczy", "obu drużynom", "brak motywacji", "ustawiony mecz"],
    "ro": ["egal convenabil", "ambele echipe", "fără motivație", "meci aranjat"],
    "es": ["empate conveniente", "ambos equipos", "sin motivación", "partido arreglado"],
}


# ========================================
# FATIGUE ENGINE V2.0 THRESHOLDS
# ========================================
# Advanced fatigue analysis with exponential decay model

FATIGUE_CRITICAL_HOURS = 72       # Less than 3 days = CRITICAL fatigue
FATIGUE_OPTIMAL_HOURS = 96        # 4 days = full recovery
FATIGUE_WINDOW_DAYS = 21          # Analyze matches in last 21 days
FATIGUE_LATE_GAME_THRESHOLD = 0.40  # Probability threshold for late-game alert


# ========================================
# BISCOTTO ENGINE V2.0 THRESHOLDS
# ========================================
# Enhanced biscotto detection with Z-Score and end-of-season analysis

BISCOTTO_ZSCORE_THRESHOLD = 1.5   # Z-Score above this triggers analysis
BISCOTTO_END_SEASON_ROUNDS = 5    # Last N rounds considered "end of season"
BISCOTTO_LEAGUE_AVG_DRAW = 0.28   # League average draw probability (~28%)


# ========================================
# DEEPSEEK INTEL PROVIDER CONFIGURATION (V6.0 - Primary)
# ========================================
# DeepSeek Intel Provider for deep match analysis using OpenRouter + Brave Search
# High rate limits, no cooldown management needed
# Requires: OPENROUTER_API_KEY + BRAVE_API_KEY in .env
DEEPSEEK_INTEL_ENABLED = os.getenv("DEEPSEEK_INTEL_ENABLED", "true").lower() == "true"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ========================================
# PERPLEXITY PROVIDER CONFIGURATION (V4.2 - Fallback)
# ========================================
# Perplexity Sonar as luxury fallback when DeepSeek fails
# Uses sonar-pro model with web search grounding
PERPLEXITY_ENABLED = os.getenv("PERPLEXITY_ENABLED", "true").lower() == "true"
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")

# ========================================
# REDDIT MONITOR CONFIGURATION (DEPRECATED V8.0)
# ========================================
# V8.0: Reddit monitoring removed - provided no betting edge.
# Reddit rumors arrive too late (already priced in by market).
# Keeping flag for backward compatibility during transition.
REDDIT_ENABLED = False  # Permanently disabled

# ========================================
# PAUSE/RESUME CONTROL
# ========================================
# Semaphore file for /stop and /resume commands
PAUSE_FILE = os.path.join(DATA_DIR, "pause.lock")

# ========================================
# ANALYZER LIMITS (V6.1)
# ========================================
# Maximum characters for news snippet before truncation
# Prevents token overflow in LLM calls
NEWS_SNIPPET_MAX_CHARS = 3000

# ========================================
# TAVILY AI SEARCH CONFIGURATION (V7.0)
# ========================================
# Tavily AI Search - 7 API keys with 1000 calls each = 7000 calls/month
# Keys rotate automatically: when Key 1 exhausts (429), switches to Key 2, etc.
# https://tavily.com/ - AI-optimized search for match enrichment

TAVILY_ENABLED = os.getenv("TAVILY_ENABLED", "true").lower() == "true"

# API Keys (loaded in order for rotation)
TAVILY_API_KEYS = [
    os.getenv("TAVILY_API_KEY_1", ""),
    os.getenv("TAVILY_API_KEY_2", ""),
    os.getenv("TAVILY_API_KEY_3", ""),
    os.getenv("TAVILY_API_KEY_4", ""),
    os.getenv("TAVILY_API_KEY_5", ""),
    os.getenv("TAVILY_API_KEY_6", ""),
    os.getenv("TAVILY_API_KEY_7", ""),
]

# Rate limiting: 1 request per second (Tavily API limit)
TAVILY_RATE_LIMIT_SECONDS = 1.0

# Cache TTL: 30 minutes to avoid duplicate queries
TAVILY_CACHE_TTL_SECONDS = 1800

# Budget allocation per component (calls/month)
TAVILY_BUDGET_ALLOCATION = {
    "main_pipeline": 2100,      # 30% - Match enrichment
    "news_radar": 1500,         # 21% - Pre-enrichment for ambiguous content
    "browser_monitor": 750,     # 11% - Short content expansion
    "telegram_monitor": 450,    # 6% - Intel verification
    "settlement_clv": 225,      # 3% - Post-match analysis
    "twitter_recovery": 1975,   # 29% - Buffer/recovery
}

# Total monthly budget (7 keys × 1000 calls)
TAVILY_MONTHLY_BUDGET = 7000

# Threshold percentages for degraded/disabled modes
TAVILY_DEGRADED_THRESHOLD = 0.90   # 90% - Non-critical calls throttled
TAVILY_DISABLED_THRESHOLD = 0.95   # 95% - Only critical calls allowed

# ========================================
# VERIFICATION LAYER V7.0 (Alert Fact-Checking)
# ========================================
# The Verification Layer acts as a quality filter between preliminary alerts
# and the final send decision. It verifies data with external sources
# (Tavily/Perplexity) to validate betting logic.
#
# Key Problem Solved: Prevents suggesting Over 2.5 Goals for a team with
# 7 CRITICAL absences without considering that a decimated squad typically
# produces fewer goals.

VERIFICATION_ENABLED = os.getenv("VERIFICATION_ENABLED", "true").lower() == "true"
VERIFICATION_SCORE_THRESHOLD = 7.5   # Minimum score to trigger verification
VERIFICATION_TIMEOUT = 30            # Seconds timeout for API calls

# Player Impact Thresholds
PLAYER_KEY_IMPACT_THRESHOLD = 7      # Score >= 7 = key player
CRITICAL_IMPACT_THRESHOLD = 20       # Total impact >= 20 = critical situation

# Form Analysis Thresholds
FORM_DEVIATION_THRESHOLD = 0.30      # 30% deviation from season avg = warning
LOW_SCORING_THRESHOLD = 1.0          # Goals/game < 1.0 = low scoring team

# H2H Thresholds
H2H_CARDS_THRESHOLD = 4.5            # Avg cards >= 4.5 = suggest Over Cards
H2H_CORNERS_THRESHOLD = 10           # Avg corners >= 10 = suggest Over Corners
COMBINED_CORNERS_THRESHOLD = 10.5    # Combined avg >= 10.5 = Over 9.5 Corners

# Referee Thresholds
REFEREE_STRICT_THRESHOLD = 5.0       # Cards/game >= 5 = strict referee
REFEREE_LENIENT_THRESHOLD = 3.0      # Cards/game <= 3 = lenient referee

# Score Adjustment Penalties
CRITICAL_INJURY_OVER_PENALTY = 1.5   # Points to subtract for critical injury + Over
FORM_WARNING_PENALTY = 0.5           # Points to subtract for form warning
INCONSISTENCY_PENALTY = 0.3          # Points to subtract per inconsistency


# ========================================
# DATABASE CONFIGURATION
# ========================================
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    f"sqlite:///{os.path.join(DATA_DIR, 'earlybird.db')}"
)

# ========================================
# LOGGING CONFIGURATION
# ========================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.path.join(LOGS_DIR, "earlybird.log")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ========================================
# MONITORING & HEALTH CHECKS
# ========================================
HEALTH_CHECK_INTERVAL = 300  # 5 minutes
MAX_ALERTS_PER_HOUR = 10     # Rate limiting for alerts

# ========================================
# VALIDATION FUNCTIONS
# ========================================
def validate_config() -> List[str]:
    """
    Validate configuration and return list of missing critical settings.
    
    Returns:
        List of error messages for missing/invalid configurations
    """
    errors = []
    
    # Critical API keys
    if not ODDS_API_KEY:
        errors.append("Missing ODDS_API_KEY - required for match data")
    
    if not TELEGRAM_BOT_TOKEN:
        errors.append("Missing TELEGRAM_BOT_TOKEN - required for notifications")
    
    if not TELEGRAM_CHAT_ID:
        errors.append("Missing TELEGRAM_CHAT_ID - required for notifications")
    
    # Check data directory is writable
    try:
        test_file = os.path.join(DATA_DIR, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except Exception as e:
        errors.append(f"Data directory not writable: {e}")
    
    return errors


def is_config_valid() -> bool:
    """Check if configuration is valid for operation."""
    return len(validate_config()) == 0


# ========================================
# MODULE EXPORTS
# ========================================
__all__ = [
    # Paths
    "BASE_DIR", "DATA_DIR", "LOGS_DIR",
    # API Keys
    "ODDS_API_KEY", "SERPER_API_KEY", "GEMINI_API_KEY", "BRAVE_API_KEY",
    "MEDIASTACK_API_KEY", "OPENROUTER_API_KEY", "PERPLEXITY_API_KEY",
    # Telegram
    "TELEGRAM_CHAT_ID", "TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_BOT_TOKEN",
    # Thresholds
    "ALERT_THRESHOLD_HIGH", "ALERT_THRESHOLD_RADAR", "SETTLEMENT_MIN_SCORE",
    "MATCH_LOOKAHEAD_HOURS", "ANALYSIS_WINDOW_HOURS",
    # Home Advantage
    "HOME_ADVANTAGE_BY_LEAGUE", "DEFAULT_HOME_ADVANTAGE", "get_home_advantage",
    # News Decay
    "TIER1_LEAGUES", "NEWS_DECAY_LAMBDA_TIER1", "NEWS_DECAY_LAMBDA_ELITE",
    "SOURCE_DECAY_MODIFIERS", "get_news_decay_lambda", "get_source_decay_modifier",
    # Biscotto
    "BISCOTTO_SUSPICIOUS_LOW", "BISCOTTO_EXTREME_LOW", "BISCOTTO_SIGNIFICANT_DROP",
    "BISCOTTO_KEYWORDS", "BISCOTTO_ZSCORE_THRESHOLD", "BISCOTTO_END_SEASON_ROUNDS",
    "BISCOTTO_LEAGUE_AVG_DRAW",
    # Fatigue
    "FATIGUE_CRITICAL_HOURS", "FATIGUE_OPTIMAL_HOURS", "FATIGUE_WINDOW_DAYS",
    "FATIGUE_LATE_GAME_THRESHOLD",
    # Providers
    "DEEPSEEK_INTEL_ENABLED", "PERPLEXITY_ENABLED", "REDDIT_ENABLED", "TAVILY_ENABLED",
    # Tavily Config
    "TAVILY_API_KEYS", "TAVILY_RATE_LIMIT_SECONDS", "TAVILY_CACHE_TTL_SECONDS",
    "TAVILY_BUDGET_ALLOCATION", "TAVILY_MONTHLY_BUDGET",
    "TAVILY_DEGRADED_THRESHOLD", "TAVILY_DISABLED_THRESHOLD",
    # Verification
    "VERIFICATION_ENABLED", "VERIFICATION_SCORE_THRESHOLD", "VERIFICATION_TIMEOUT",
    "PLAYER_KEY_IMPACT_THRESHOLD", "CRITICAL_IMPACT_THRESHOLD",
    "FORM_DEVIATION_THRESHOLD", "LOW_SCORING_THRESHOLD",
    "H2H_CARDS_THRESHOLD", "H2H_CORNERS_THRESHOLD", "COMBINED_CORNERS_THRESHOLD",
    "REFEREE_STRICT_THRESHOLD", "REFEREE_LENIENT_THRESHOLD",
    "CRITICAL_INJURY_OVER_PENALTY", "FORM_WARNING_PENALTY", "INCONSISTENCY_PENALTY",
    # Database
    "DATABASE_URL",
    # Logging
    "LOG_LEVEL", "LOG_FILE", "LOG_FORMAT", "LOG_DATE_FORMAT",
    # Monitoring
    "HEALTH_CHECK_INTERVAL", "MAX_ALERTS_PER_HOUR",
    # Validation
    "validate_config", "is_config_valid",
]
