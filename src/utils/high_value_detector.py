"""
High Value Detector Module - V2.5

Detects high-value betting signals from sports news content.
Replaces the old keyword-matching approach with a smarter pipeline:

1. GarbageFilter: Removes navigation menus, login pages, garbage content
2. HighSignalDetector: Detects critical patterns that indicate betting value

Key insight: "Better 1 good alert than 20 useless ones"

High-value signals (from real examples):
- Multiple players absent (3+)
- Full squad rotation / youth team fielded
- "Decimated" / "crisis" situations
- Financial crisis / player strikes
- Logistical disruptions (travel chaos)
- Motivational mismatch (one team has nothing to play for)

V2.0: Complete rewrite based on real betting value analysis.
V2.1: Added SignalType enum, extracted_number, exclusion filters integration.
V2.2: Fixed truncated regex, duplicate dict keys, import cleanup.
V2.3: Added CONFIRMED_LINEUP for early lineup announcements.
V2.4: Fixed thread safety (separate locks for singletons), removed unused fields (priority, all_matches).
V2.5: Removed StructuredAnalysis dead code (never used in production, data flows use dict-based approach).
"""

import logging
import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.config.exclusion_lists import (
    EXCLUDED_CATEGORIES,
    EXCLUDED_OTHER_SPORTS,
    EXCLUDED_SPORTS,
)

logger = logging.getLogger(__name__)


# ============================================
# SIGNAL TYPE ENUM
# ============================================


class SignalType(Enum):
    """
    Types of high-value betting signals.

    V2.1: Added as enum for type safety and test compatibility.
    V2.3: Added CONFIRMED_LINEUP for early lineup announcements.
    """

    NONE = "NONE"
    MASS_ABSENCE = "MASS_ABSENCE"  # 3+ players out
    DECIMATED = "DECIMATED"  # Team decimated/crisis
    YOUTH_TEAM = "YOUTH_TEAM"  # Youth/reserve team fielded
    TURNOVER = "TURNOVER"  # Full rotation confirmed
    FINANCIAL_CRISIS = "FINANCIAL_CRISIS"  # Unpaid wages, strike
    LOGISTICAL_CRISIS = "LOGISTICAL_CRISIS"  # Travel chaos, flight issues
    GOALKEEPER_OUT = "GOALKEEPER_OUT"  # Goalkeeper unavailable
    MOTIVATION = "MOTIVATION"  # Nothing to play for
    KEY_PLAYER = "KEY_PLAYER"  # Captain/star out
    CONFIRMED_LINEUP = "CONFIRMED_LINEUP"  # V2.3: Early lineup announcement (24-48h before)

    def __str__(self) -> str:
        return self.value


# ============================================
# GARBAGE FILTER
# ============================================


class GarbageFilter:
    """
    Filters out garbage content before analysis.

    V2.1: Integrated exclusion filters from content_analysis.py
    V2.2: Fixed truncated regex pattern

    Detects:
    - Navigation menus (Home News Sport Football...)
    - Login/subscription prompts
    - Cookie notices
    - Very short content
    - Repeated words (broken extraction)
    - Excluded sports (basketball, tennis, NFL, rugby, handball, etc.)
    - Women's football
    """

    # ============================================
    # EXCLUSION KEYWORDS
    # ============================================
    # VPS FIX: Now imported from centralized config to eliminate duplication
    # See src/config/exclusion_lists.py for the complete lists
    # These are imported at module level and used directly in __init__

    # Patterns that indicate garbage content
    GARBAGE_PATTERNS = [
        # Login/subscription
        r"\b(login|sign in|subscribe|newsletter|cookie|privacy policy)\b",
        # Social media prompts
        r"\b(follow us|share this|tweet|facebook|instagram)\b",
        # Broken extraction (same word repeated 4+ times)
        r"(\b\w+\b)(\s+\1){3,}",
    ]

    # V2.3: Pattern for navigation menu detection (separate, not in GARBAGE_PATTERNS)
    # VPS FIX: Now handles both title-case (Home News Sport) and all-caps (HOME NEWS SPORT) menus
    # Also handles mixed-case menus (HOME About Contact MORE)
    # Pattern matches: 4+ words, each can be all-caps or title-case
    NAVIGATION_MENU_PATTERN = r"^(?:[A-Z][a-z]+|[A-Z]+)(?:\s+(?:[A-Z][a-z]+|[A-Z]+)){3,}$"

    # Minimum content requirements
    MIN_CONTENT_LENGTH = 100  # chars (lowered from 150)
    MIN_WORD_COUNT = 15  # words (lowered from 20)
    MAX_CAPS_RATIO = 0.4  # Max 40% uppercase

    def __init__(self):
        """Initialize with compiled patterns."""
        self._garbage_patterns = [
            re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.GARBAGE_PATTERNS
        ]

        # V2.2: Compile navigation menu pattern separately
        self._nav_menu_pattern = re.compile(self.NAVIGATION_MENU_PATTERN)

        # Build exclusion pattern from all excluded keywords (imported from centralized config)
        all_excluded = EXCLUDED_SPORTS + EXCLUDED_CATEGORIES + EXCLUDED_OTHER_SPORTS
        exclusion_pattern = r"\b(" + "|".join(re.escape(kw) for kw in all_excluded) + r")\b"
        self._exclusion_pattern = re.compile(exclusion_pattern, re.IGNORECASE)

    def is_garbage(self, content: str) -> tuple[bool, str | None]:
        """
        Check if content is garbage (should be discarded).

        Args:
            content: Text content to check

        Returns:
            Tuple of (is_garbage: bool, reason: str or None)
        """
        if not content:
            return True, "empty_content"

        # Check minimum length
        clean_content = content.strip()
        if len(clean_content) < self.MIN_CONTENT_LENGTH:
            return True, f"too_short ({len(clean_content)} chars)"

        # Check minimum word count
        words = clean_content.split()
        if len(words) < self.MIN_WORD_COUNT:
            return True, f"too_few_words ({len(words)} words)"

        # Check caps ratio (too many caps = navigation/headers)
        if clean_content:
            caps_count = sum(1 for c in clean_content if c.isupper())
            alpha_count = sum(1 for c in clean_content if c.isalpha())
            if alpha_count > 0 and caps_count / alpha_count > self.MAX_CAPS_RATIO:
                return True, "too_many_caps (likely navigation)"

        # Check garbage patterns
        for i, pattern in enumerate(self._garbage_patterns):
            if pattern.search(clean_content):
                return True, f"garbage_pattern_{i}"

        # V2.1: Check exclusion patterns (basketball, women's, NFL, etc.)
        exclusion_match = self._exclusion_pattern.search(clean_content)
        if exclusion_match:
            return True, f"excluded_sport ({exclusion_match.group(1).lower()})"

        return False, None

    def is_excluded_sport(self, content: str) -> tuple[bool, str | None]:
        """
        Check if content is about an excluded sport.

        Args:
            content: Text content to check

        Returns:
            Tuple of (is_excluded: bool, matched_keyword: str or None)
        """
        if not content:
            return False, None

        match = self._exclusion_pattern.search(content)
        if match:
            return True, match.group(1).lower()
        return False, None

    def clean_content(self, content: str) -> str:
        """
        Clean content by removing garbage patterns.

        Args:
            content: Raw content text

        Returns:
            Cleaned content with garbage removed
        """
        if not content:
            return ""

        cleaned = content.strip()

        # Remove multiple consecutive newlines
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        # Remove lines that look like navigation (short lines with only caps words)
        lines = cleaned.split("\n")
        filtered_lines = []
        for line in lines:
            line = line.strip()
            # Skip empty lines
            if not line:
                continue
            # VPS FIX: Skip lines that are all caps (likely nav) - removed length restriction
            # Long uppercase menus like "HOME ABOUT CONTACT MORE NEWS SPORTS FOOTBALL" should also be skipped
            if line.isupper():
                continue
            # V2.2: Fixed - Skip lines that look like menu items (Home News Sport...)
            if self._nav_menu_pattern.match(line):
                continue
            filtered_lines.append(line)

        cleaned = "\n".join(filtered_lines)

        # Remove excessive whitespace
        cleaned = re.sub(r"[ \t]+", " ", cleaned)

        return cleaned.strip()

    def get_garbage_reason(self, content: str) -> str | None:
        """Get the reason why content is garbage."""
        is_garbage, reason = self.is_garbage(content)
        return reason if is_garbage else None


# ============================================
# SIGNAL RESULT DATACLASS
# ============================================


@dataclass
class SignalResult:
    """
    Result of high-value signal detection.

    V2.1: Added signal_type as SignalType enum and extracted_number.
    V2.4: Removed unused fields (priority, all_matches) to reduce dead code.
    """

    detected: bool = False
    signal_type: SignalType = SignalType.NONE
    matched_pattern: str | None = None
    extracted_number: int | None = (
        None  # V2.1: Number extracted from text (e.g., "without 9 players" -> 9)
    )
    all_signals: list[SignalType] = field(default_factory=list)


# ============================================
# STRUCTURED ANALYSIS RESULT
# ============================================


@dataclass
class StructuredAnalysis:
    """
    Structured analysis result from LLM.

    V3.0: Reintegrated with enhanced fields and intelligent workflow integration.

    Contains all information needed for a high-value betting alert.
    All fields are extracted by LLM from original content.

    This class acts as an intelligent component that:
    - Validates itself using is_valid_for_alert()
    - Determines priority using get_alert_priority()
    - Converts from dict for seamless integration
    - Communicates with other components (enrichment, validation)
    """

    # Required fields (alert not sent if missing)
    team: str | None = None
    opponent: str | None = None

    # Absence information
    absent_count: int = 0
    absent_type: str = "UNKNOWN"  # INJURY, ROTATION, YOUTH_TEAM, STRIKE, OTHER
    absent_names: list[str] = field(default_factory=list)
    absent_roles: list[str] = field(default_factory=list)  # GK, DEF, MID, FWD

    # Match context
    competition: str | None = None
    match_date: str | None = None
    match_importance: str = "NORMAL"  # CRITICAL, IMPORTANT, NORMAL, LOW

    # Situational factors
    motivation_home: str = "NORMAL"  # HIGH, NORMAL, LOW, NONE
    motivation_away: str = "NORMAL"
    has_travel_issues: bool = False
    has_financial_crisis: bool = False

    # Analysis metadata
    confidence: float = 0.0
    summary_en: str = ""  # Summary in English
    summary_it: str = ""  # Summary in Italian
    betting_impact: str = "LOW"  # CRITICAL, HIGH, MEDIUM, LOW

    # Optional: Cross-validation data from pattern detector
    pattern_detected_signal: str | None = None
    pattern_extracted_number: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StructuredAnalysis":
        """
        Create StructuredAnalysis from dict (LLM response).

        This enables intelligent integration with the existing dict-based workflow.
        Maps dict keys to class fields with safe defaults.

        Args:
            data: Dict from DeepSeek LLM response

        Returns:
            StructuredAnalysis instance
        """
        # Map absent_players to absent_names for compatibility
        absent_names = data.get("absent_players", [])
        if isinstance(absent_names, list):
            absent_names = [str(p) for p in absent_names if p]
        else:
            absent_names = []

        # Map category to absent_type for compatibility
        category = data.get("category", "")
        absent_type = "UNKNOWN"
        if category == "MASS_ABSENCE":
            absent_type = "INJURY"
        elif category == "DECIMATED":
            absent_type = "INJURY"
        elif category == "YOUTH_TEAM":
            absent_type = "YOUTH_TEAM"
        elif category == "TURNOVER":
            absent_type = "ROTATION"
        elif category == "FINANCIAL_CRISIS":
            absent_type = "STRIKE"
        elif category == "LOGISTICAL_CRISIS":
            absent_type = "OTHER"
        elif category == "GOALKEEPER_OUT":
            absent_type = "INJURY"
        elif category == "MOTIVATION":
            absent_type = "OTHER"
        elif category == "CONFIRMED_LINEUP":
            absent_type = "OTHER"

        # Extract absent_roles
        absent_roles = data.get("absent_roles", [])
        if isinstance(absent_roles, list):
            absent_roles = [str(r).upper() for r in absent_roles if r]
        else:
            absent_roles = []

        return cls(
            team=data.get("team"),
            opponent=data.get("opponent"),
            absent_count=int(data.get("absent_count", 0)),
            absent_type=absent_type,
            absent_names=absent_names,
            absent_roles=absent_roles,
            competition=data.get("competition"),
            match_date=data.get("match_date"),
            match_importance=data.get("match_importance", "NORMAL"),
            motivation_home=data.get("motivation_home", "NORMAL"),
            motivation_away=data.get("motivation_away", "NORMAL"),
            has_travel_issues=bool(data.get("has_travel_issues", False)),
            has_financial_crisis=bool(data.get("has_financial_crisis", False)),
            confidence=float(data.get("confidence", 0.0)),
            summary_en=data.get("summary_en", ""),
            summary_it=data.get("summary_italian", ""),
            betting_impact=data.get("betting_impact", "LOW"),
        )

    def is_valid_for_alert(self) -> bool:
        """
        Check if this analysis has enough info for a valid alert.

        V3.0: Enhanced validation with intelligent component communication.

        Rules:
        - Must have team name
        - Must have either:
          - 3+ absent players, OR
          - Goalkeeper absent, OR
          - Youth team fielded, OR
          - Financial crisis/strike

        Returns:
            True if valid for alert, False otherwise
        """
        if not self.team:
            return False

        # Youth team = always valid
        if self.absent_type == "YOUTH_TEAM":
            return True

        # Financial crisis = always valid
        if self.has_financial_crisis:
            return True

        # 3+ absences = valid
        if self.absent_count >= 3:
            return True

        # Goalkeeper absent = valid
        if self.absent_roles and "GK" in self.absent_roles:
            return True
        # V2.2: Safe check for absent_names (could be None or empty)
        if self.absent_names and "goalkeeper" in " ".join(self.absent_names).lower():
            return True

        # Captain absent with 2+ others = valid
        if self.absent_count >= 2 and self.absent_names:
            if any("captain" in name.lower() for name in self.absent_names):
                return True

        return False

    def get_alert_priority(self) -> str:
        """
        Get alert priority based on analysis.

        V3.0: Enhanced priority calculation with multiple factors.

        Returns:
            Priority level: CRITICAL, HIGH, MEDIUM, LOW
        """
        # Critical situations
        if self.absent_type == "YOUTH_TEAM":
            return "CRITICAL"
        if self.has_financial_crisis:
            return "CRITICAL"
        if self.absent_count >= 5:
            return "CRITICAL"

        # High impact situations
        if self.absent_count >= 3:
            return "HIGH"
        if self.absent_roles and "GK" in self.absent_roles:
            return "HIGH"
        if self.has_travel_issues:
            return "HIGH"
        if self.match_importance == "CRITICAL":
            return "HIGH"

        # Medium impact
        if self.absent_count >= 1:
            return "MEDIUM"
        if self.match_importance == "IMPORTANT":
            return "MEDIUM"

        return "LOW"

    def enrich_with_context(self, enrichment_data: dict[str, Any]) -> None:
        """
        Enrich analysis with database context.

        V3.0: Intelligent component communication with enrichment system.

        This method allows StructuredAnalysis to communicate with
        the enrichment system to fill missing fields with database data.

        FIXED: Now only enriches when field is None, empty, or "UNKNOWN".
        Does NOT override valid values like "NORMAL", "HIGH", "MEDIUM", "LOW".

        Args:
            enrichment_data: Dict with enrichment context
        """
        # Enrich motivation_home only if not provided by LLM
        # Only enrich when field is None, empty, or "UNKNOWN"
        if not self.motivation_home or self.motivation_home == "UNKNOWN":
            if "motivation_home" in enrichment_data and enrichment_data["motivation_home"]:
                self.motivation_home = enrichment_data["motivation_home"]

        # Enrich motivation_away only if not provided by LLM
        if not self.motivation_away or self.motivation_away == "UNKNOWN":
            if "motivation_away" in enrichment_data and enrichment_data["motivation_away"]:
                self.motivation_away = enrichment_data["motivation_away"]

        # Enrich match_importance only if not provided by LLM
        if not self.match_importance or self.match_importance == "UNKNOWN":
            if "match_importance" in enrichment_data and enrichment_data["match_importance"]:
                self.match_importance = enrichment_data["match_importance"]

        # Enrich opponent if missing
        if not self.opponent:
            if "opponent" in enrichment_data and enrichment_data["opponent"]:
                self.opponent = enrichment_data["opponent"]

        # Enrich competition if missing
        if not self.competition:
            if "competition" in enrichment_data and enrichment_data["competition"]:
                self.competition = enrichment_data["competition"]

        # Enrich match_date if missing
        if not self.match_date:
            if "match_date" in enrichment_data and enrichment_data["match_date"]:
                self.match_date = enrichment_data["match_date"]

    def cross_validate_with_pattern(
        self, signal_type: str | None, extracted_number: int | None
    ) -> tuple[bool, float]:
        """
        Cross-validate LLM analysis with pattern detector results.

        V3.0: Intelligent two-level validation architecture.

        This method allows StructuredAnalysis to communicate with
        the pattern detector to improve accuracy.

        Args:
            signal_type: Signal type detected by pattern matching
            extracted_number: Number extracted from text

        Returns:
            Tuple of (is_valid, confidence_adjustment)
        """
        confidence_adjustment = 0.0

        # If pattern detected same category as LLM, boost confidence
        if signal_type:
            # Map signal types to absent_type
            signal_to_type = {
                "MASS_ABSENCE": "INJURY",
                "DECIMATED": "INJURY",
                "YOUTH_TEAM": "YOUTH_TEAM",
                "TURNOVER": "ROTATION",
                "FINANCIAL_CRISIS": "STRIKE",
                "LOGISTICAL_CRISIS": "OTHER",
                "GOALKEEPER_OUT": "INJURY",
                "MOTIVATION": "OTHER",
                "CONFIRMED_LINEUP": "OTHER",
            }

            expected_type = signal_to_type.get(signal_type)
            if expected_type and self.absent_type == expected_type:
                confidence_adjustment += 0.05  # 5% boost for agreement

        # If extracted number matches absent_count, boost confidence
        if extracted_number is not None and self.absent_count > 0:
            if abs(extracted_number - self.absent_count) <= 1:
                confidence_adjustment += 0.03  # 3% boost for number match

        # If pattern detected but LLM didn't, flag for review
        if signal_type and signal_type in ["MASS_ABSENCE", "DECIMATED", "YOUTH_TEAM"]:
            if self.absent_count < 3 and self.absent_type != "YOUTH_TEAM":
                # Pattern detected high-value but LLM didn't
                confidence_adjustment -= 0.10  # 10% penalty

        return (True, confidence_adjustment)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dict for RadarAlert creation.

        V3.0: Seamless integration with existing workflow.

        Returns:
            Dict with all fields needed for RadarAlert
        """
        return {
            "team": self.team,
            "opponent": self.opponent,
            "absent_count": self.absent_count,
            "absent_players": self.absent_names,  # Map back to absent_players
            "competition": self.competition,
            "match_date": self.match_date,
            "category": self._map_type_to_category(),
            "betting_impact": self.betting_impact,
            "confidence": self.confidence,
            "summary_italian": self.summary_it,
            "summary_en": self.summary_en,
            "absent_roles": self.absent_roles,
            "match_importance": self.match_importance,
            "motivation_home": self.motivation_home,
            "motivation_away": self.motivation_away,
            "has_travel_issues": self.has_travel_issues,
            "has_financial_crisis": self.has_financial_crisis,
        }

    def _map_type_to_category(self) -> str:
        """Map absent_type back to category for RadarAlert."""
        type_to_category = {
            "INJURY": "MASS_ABSENCE",
            "ROTATION": "TURNOVER",
            "YOUTH_TEAM": "YOUTH_TEAM",
            "STRIKE": "FINANCIAL_CRISIS",
            "OTHER": "LOW_VALUE",
        }
        return type_to_category.get(self.absent_type, "LOW_VALUE")


# ============================================
# HIGH SIGNAL DETECTOR
# ============================================


class HighSignalDetector:
    """
    Detects high-value betting signals using multilingual patterns.

    V2.1: Enhanced with SignalType enum and number extraction.
    V2.2: Fixed duplicate dictionary keys in NUMBER_WORDS.
    V2.4: Removed unused _calculate_priority() method, integrated priority logic into has_high_value_signal().

    Uses root-based patterns that work across multiple languages:
    - Latin roots (decim-, cris-, emerg-)
    - Numeric patterns (without X players, X absent)
    - Universal terms (youth, U19, U21)

    Only content matching these patterns goes to LLM analysis.
    This saves API costs by filtering out low-value content early.
    """

    # Minimum threshold for MASS_ABSENCE (3+ players)
    MASS_ABSENCE_THRESHOLD = 3

    # V2.2: Fixed - Number words mapping (multilingual, no duplicate keys)
    # Note: Some words are shared across languages (e.g., 'seis' in ES/PT)
    # We keep only unique keys, values are the same anyway
    NUMBER_WORDS = {
        # English
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "several": 4,
        "multiple": 4,
        "numerous": 5,
        # Italian (unique)
        "uno": 1,
        "due": 2,
        "tre": 3,
        "quattro": 4,
        "cinque": 5,
        "sei": 6,
        "sette": 7,
        "otto": 8,
        "nove": 9,
        "dieci": 10,
        # Spanish (unique - 'uno' shared with IT, same value)
        "dos": 2,
        "tres": 3,
        "cuatro": 4,
        "siete": 7,
        "ocho": 8,
        "nueve": 9,
        "diez": 10,
        # Portuguese (unique)
        "um": 1,
        "dois": 2,
        "três": 3,
        "oito": 8,
        "dez": 10,
        # Shared ES/PT
        "cinco": 5,
        "seis": 6,
        # German (unique)
        "ein": 1,
        "zwei": 2,
        "drei": 3,
        "vier": 4,
        "fünf": 5,
        "sechs": 6,
        "sieben": 7,
        "acht": 8,
        "neun": 9,
        "zehn": 10,
    }

    # HIGH-VALUE PATTERNS (multilingual roots)
    # These patterns indicate content worth analyzing with LLM

    # Pattern 1: Decimated/Crisis (Latin root works in EN/ES/IT/PT/FR/DE)
    CRISIS_PATTERNS = [
        r"\b(decimat|diezm|dizim)",  # decimated/diezmado/dizimado
        r"\b(cris[ie]s?|kris[ei])",  # crisis/crisi/krise
        r"\b(emerg[eê]nc)",  # emergency/emergência/emergenza
        r"\b(desfalc|depaupera)",  # depleted (PT/ES)
        r"\b(notstand|ausnahmezustand)",  # emergency (DE)
    ]

    # Pattern 2: Multiple absences with numbers
    NUMERIC_ABSENCE_PATTERNS = [
        r"\b(without|sans|sin|senza|ohne|sem)\s+(\d+|[a-z]+)\s+(player|joueur|jugador|giocator|spieler|jogador)",
        r"\b(\d+)\s+(player|joueur|jugador|giocator|spieler|jogador)s?\s+(out|absent|missing|unavailable)",
        r"\b(miss|without|lacking)\s+(\d+|several|multiple|numerous)",
        r"\bmissing\s+(\d+|several|multiple)",
        r"\b(\d+)\s+(absent|assent|ausente)",
        r"\bsenza\s+(\d+)",  # Italian: senza 9 giocatori
        r"\bsin\s+(\d+)",  # Spanish: sin 7 jugadores
        r"\bsem\s+(\d+)",  # Portuguese: sem 5 jogadores
        r"\bohne\s+(\d+)",  # German: ohne 6 spieler
    ]

    # Pattern 3: Youth team / Reserves fielded
    YOUTH_ROTATION_PATTERNS = [
        r"\b(youth\s+team|youth\s+squad|reserve\s+team|second\s+team|b\s+team)",
        r"\b(squadra\s+giovanile|formazione\s+giovanile|primavera)",  # IT
        r"\b(equipo\s+juvenil|equipo\s+reserva|filial)",  # ES
        r"\b(time\s+de\s+base|equipe\s+reserva|sub-\d+)",  # PT
        r"\b(jugendmannschaft|zweite\s+mannschaft|reservemannschaft)",  # DE
        r"\b(équipe\s+réserve|équipe\s+jeunes)",  # FR
        r"\b(field|play|start)\s+(with\s+)?(youth|youngsters|reserves|kids)",
        r"\b(punta\s+sui\s+giovani)",  # IT: relies on youth
        r"\b(apuesta\s+por\s+los\s+jóvenes)",  # ES
    ]

    # Pattern 4: Full rotation / Resting starters
    ROTATION_PATTERNS = [
        r"\b(full\s+rotation|complete\s+rotation|total\s+rotation)",
        r"\b(rest|rested|resting)\s+(all|entire|whole|most)\s+(starter|first\s+team|regular)",
        r"\b(turnover\s+(totale|completo|masivo|massif))",
        r"\b(rotazione\s+(totale|completa))",  # IT
        r"\b(rotación\s+(total|completa))",  # ES
        r"\b(rodízio\s+(total|completo))",  # PT
    ]

    # Pattern 5: Strike / Financial crisis
    # V2.3: Fixed - Added \b at end to prevent matching "striker"
    CRISIS_EXTERNAL_PATTERNS = [
        r"\b(strike|sciopero|huelga|grève|streik|greve)\b",
        r"\b(unpaid|salari[eo]s?\s+(non\s+)?paga[td]|wages?\s+unpaid)\b",
        r"\b(financial\s+crisis|crisi\s+finanziaria|crisis\s+financiera)\b",
        r"\b(stipendi\s+arretrati|sueldos\s+atrasados)\b",
    ]

    # Pattern 6: Travel/Logistical disruption
    DISRUPTION_PATTERNS = [
        r"\b(flight\s+(cancel|delay|divert)|volo\s+(cancellat|deviat|ritard))",
        r"\b(travel\s+(chaos|problem|issue|disruption))",
        r"\b(bus\s+journey|viaggio\s+in\s+(autobus|pullman))",
        r"\b(chaotic\s+arrival|arrivo\s+caotico)",
        r"\b(no\s+training|senza\s+allenamento|sin\s+entrenamiento)",
    ]

    # Pattern 7: Motivational mismatch
    MOTIVATION_PATTERNS = [
        r"\b(nothing\s+to\s+play\s+for|niente\s+da\s+giocare|nada\s+que\s+jugar)",
        r"\b(already\s+(qualified|relegated|safe|promoted))",
        r"\b(già\s+(qualificat|retrocesso|salv))",  # IT
        r"\b(ya\s+(clasificad|descendid|salvad))",  # ES
        r"\b(mathematically\s+(safe|relegated|out))",
        r"\b(no\s+(more\s+)?options?\s+to\s+(advance|qualify))",
    ]

    # Pattern 8: Goalkeeper out (separate from KEY_PLAYER for specific detection)
    GOALKEEPER_PATTERNS = [
        r"\b(goalkeeper|portiere|portero|goleiro|torwart|gardien)\s+(out|injured|absent|unavailable|will miss)",
        r"\b(without\s+(their\s+)?goalkeeper)",
        r"\b(senza\s+(il\s+)?portiere)",  # IT
        r"\b(sin\s+(el\s+)?portero)",  # ES
    ]

    # Pattern 9: Other key players out (captain, star - NOT goalkeeper)
    KEY_PLAYER_PATTERNS = [
        r"\b(captain|capitano|capitán|capitão|kapitän|capitaine)\s+(out|injured|absent|suspended)",
        r"\b(star\s+player|top\s+scorer|capocannoniere|goleador|artilheiro)\s+(out|miss|absent)",
        r"\b(without\s+(their\s+)?(captain|star))",
        r"\b(senza\s+(il\s+)?capitano)",  # IT
        r"\b(sin\s+(el\s+)?capitán)",  # ES
    ]

    # Pattern 10: Confirmed lineup announced early (V2.3 NEW)
    # GOLD SIGNAL: Some managers announce lineup 24-48h before match
    # This gives betting edge before market reacts
    CONFIRMED_LINEUP_PATTERNS = [
        # English
        r"\b(confirmed|official|announced)\s+(lineup|line-up|starting\s+xi|starting\s+eleven|formation)",
        r"\b(starting\s+xi|starting\s+eleven|starting\s+lineup)\s+(confirmed|announced|revealed)",
        r"\b(lineup|line-up|formation)\s+(revealed|announced|confirmed)",
        r"\b(manager|coach|boss)\s+(confirms?|announces?|reveals?)\s+(lineup|starting|team|formation)",
        r"\b(coach|manager|boss)\s+reveals?\s+(the\s+)?(lineup|formation|starting|team)",
        # Italian
        r"\b(formazione\s+ufficiale|undici\s+titolare|formazione\s+confermata)",
        r"\b(conferma\s+(la\s+)?formazione|annuncia\s+(la\s+)?formazione)",
        r"\b(ecco\s+(la\s+)?formazione|scelte\s+di\s+formazione)",
        # Spanish
        r"\b(alineación\s+(confirmada|oficial)|once\s+titular\s+(confirmado|oficial))",
        r"\b(confirma\s+(la\s+)?alineación|anuncia\s+(la\s+)?alineación)",
        r"\b(formación\s+(confirmada|oficial))",
        r"\b(técnico|entrenador)\s+anuncia\s+(la\s+)?alineación",
        # Portuguese
        r"\b(escalação\s+(confirmada|oficial)|onze\s+titular\s+confirmado)",
        r"\b(confirma\s+(a\s+)?escalação|anuncia\s+(a\s+)?escalação)",
        # German
        r"\b(aufstellung\s+(bestätigt|offiziell)|startelf\s+bestätigt)",
        r"\b(bestätigt\s+(die\s+)?aufstellung)",
        # French
        r"\b(composition\s+(confirmée|officielle)|onze\s+de\s+départ\s+confirmé)",
        r"\b(confirme\s+(la\s+)?composition|annonce\s+(la\s+)?composition)",
    ]

    # Mapping from internal pattern group to SignalType
    PATTERN_TO_SIGNAL_TYPE = {
        "CRISIS": SignalType.DECIMATED,
        "NUMERIC_ABSENCE": SignalType.MASS_ABSENCE,
        "YOUTH_ROTATION": SignalType.YOUTH_TEAM,
        "ROTATION": SignalType.TURNOVER,
        "CRISIS_EXTERNAL": SignalType.FINANCIAL_CRISIS,
        "DISRUPTION": SignalType.LOGISTICAL_CRISIS,
        "MOTIVATION": SignalType.MOTIVATION,
        "GOALKEEPER": SignalType.GOALKEEPER_OUT,
        "KEY_PLAYER": SignalType.KEY_PLAYER,
        "CONFIRMED_LINEUP": SignalType.CONFIRMED_LINEUP,  # V2.3: Early lineup
    }

    def __init__(self):
        """Initialize with compiled patterns."""
        self._all_patterns: list[tuple[str, re.Pattern]] = []

        # Compile all pattern groups
        # NOTE: GOALKEEPER must come BEFORE KEY_PLAYER for correct priority
        # NOTE: CONFIRMED_LINEUP added at end (lower priority than absences)
        pattern_groups = [
            ("CRISIS", self.CRISIS_PATTERNS),
            ("NUMERIC_ABSENCE", self.NUMERIC_ABSENCE_PATTERNS),
            ("YOUTH_ROTATION", self.YOUTH_ROTATION_PATTERNS),
            ("ROTATION", self.ROTATION_PATTERNS),
            ("CRISIS_EXTERNAL", self.CRISIS_EXTERNAL_PATTERNS),
            ("DISRUPTION", self.DISRUPTION_PATTERNS),
            ("MOTIVATION", self.MOTIVATION_PATTERNS),
            ("GOALKEEPER", self.GOALKEEPER_PATTERNS),  # Before KEY_PLAYER!
            ("KEY_PLAYER", self.KEY_PLAYER_PATTERNS),
            ("CONFIRMED_LINEUP", self.CONFIRMED_LINEUP_PATTERNS),  # V2.3
        ]

        for group_name, patterns in pattern_groups:
            for pattern in patterns:
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                    self._all_patterns.append((group_name, compiled))
                except re.error as e:
                    logger.warning(f"Invalid regex pattern in {group_name}: {pattern} - {e}")

        # Compile number extraction pattern
        self._number_pattern = re.compile(
            r"\b(without|sans|sin|senza|ohne|sem|missing)\s+(\d+|[a-z]+)", re.IGNORECASE
        )

    def _extract_number(self, content: str) -> int | None:
        """
        Extract number of absent players from content.

        V2.1: Handles both digits and word numbers (multilingual).

        Args:
            content: Text content to analyze

        Returns:
            Extracted number or None if not found
        """
        if not content:
            return None

        # Try to find patterns like "without 9 players", "sin 5 jugadores"
        match = self._number_pattern.search(content)
        if match:
            num_str = match.group(2).lower()

            # Try digit first
            if num_str.isdigit():
                return int(num_str)

            # Try word number
            if num_str in self.NUMBER_WORDS:
                return self.NUMBER_WORDS[num_str]

        # Fallback: look for standalone numbers near absence keywords
        absence_keywords = ["without", "missing", "absent", "out", "senza", "sin", "sem", "ohne"]
        content_lower = content.lower()

        for keyword in absence_keywords:
            if keyword in content_lower:
                # Find numbers within 20 chars of keyword
                idx = content_lower.find(keyword)
                context = content_lower[max(0, idx - 10) : idx + 30]
                numbers = re.findall(r"\b(\d+)\b", context)
                if numbers:
                    # Return first reasonable number (1-20)
                    for num in numbers:
                        n = int(num)
                        if 1 <= n <= 20:
                            return n

        return None

    def detect_signals(self, content: str) -> dict[str, Any]:
        """
        Detect high-value signals in content.

        Args:
            content: Text content to analyze

        Returns:
            Dict with:
                - has_signal: bool - True if any high-value signal found
                - signals: List[str] - Names of detected signal types
                - matches: List[str] - Actual matched text
                - extracted_number: int or None - Number of absent players
        """
        if not content:
            return {
                "has_signal": False,
                "signals": [],
                "matches": [],
                "extracted_number": None,
            }

        signals = []
        matches = []

        for group_name, pattern in self._all_patterns:
            match = pattern.search(content)
            if match:
                if group_name not in signals:
                    signals.append(group_name)
                matches.append(match.group(0))

        # Extract number
        extracted_number = self._extract_number(content)

        return {
            "has_signal": len(signals) > 0,
            "signals": signals,
            "matches": matches[:5],  # Limit to 5 matches
            "extracted_number": extracted_number,
        }

    def has_high_value_signal(self, content: str) -> bool:
        """Quick check if content has any high-value signal."""
        result = self.detect_signals(content)

        # HIGH priority signals
        high_priority = {"CRISIS", "NUMERIC_ABSENCE", "YOUTH_ROTATION", "CRISIS_EXTERNAL"}
        if any(s in high_priority for s in result["signals"]):
            # For NUMERIC_ABSENCE, check threshold
            if "NUMERIC_ABSENCE" in result["signals"] and result["extracted_number"] is not None:
                if result["extracted_number"] < self.MASS_ABSENCE_THRESHOLD:
                    # Below threshold, downgrade to MEDIUM
                    if len(result["signals"]) == 1:
                        return False
            return True

        # MEDIUM priority signals (GOALKEEPER added)
        medium_priority = {"ROTATION", "DISRUPTION", "KEY_PLAYER", "GOALKEEPER"}
        if any(s in medium_priority for s in result["signals"]):
            return True

        # LOW priority (motivation alone)
        return False

    def detect(self, content: str) -> SignalResult:
        """
        Detect high-value signals and return structured result.

        V2.1: Returns SignalType enum and extracted_number.

        Args:
            content: Text content to analyze

        Returns:
            SignalResult with detection details
        """
        raw_result = self.detect_signals(content)

        # Convert internal signal names to SignalType enum
        signal_types = []
        for sig in raw_result["signals"]:
            signal_type = self.PATTERN_TO_SIGNAL_TYPE.get(sig, SignalType.NONE)
            signal_types.append(signal_type)

        # Get primary signal type
        primary_signal = signal_types[0] if signal_types else SignalType.NONE

        # V2.1: For MASS_ABSENCE, check threshold
        extracted_number = raw_result.get("extracted_number")
        if primary_signal == SignalType.MASS_ABSENCE:
            if extracted_number is not None and extracted_number < self.MASS_ABSENCE_THRESHOLD:
                # Below threshold - not a valid detection
                return SignalResult(
                    detected=False,
                    signal_type=SignalType.NONE,
                    matched_pattern=raw_result["matches"][0] if raw_result["matches"] else None,
                    extracted_number=extracted_number,
                    all_signals=[],
                )

        return SignalResult(
            detected=raw_result["has_signal"],
            signal_type=primary_signal,
            matched_pattern=raw_result["matches"][0] if raw_result["matches"] else None,
            extracted_number=extracted_number,
            all_signals=signal_types,
        )


# ============================================
# SINGLETON INSTANCES
# ============================================

_garbage_filter: GarbageFilter | None = None
_high_signal_detector: HighSignalDetector | None = None
_garbage_filter_lock = threading.Lock()
_high_signal_detector_lock = threading.Lock()


def get_garbage_filter() -> GarbageFilter:
    """Get singleton GarbageFilter instance."""
    global _garbage_filter
    if _garbage_filter is None:
        with _garbage_filter_lock:
            if _garbage_filter is None:
                _garbage_filter = GarbageFilter()
    return _garbage_filter


def get_high_signal_detector() -> HighSignalDetector:
    """Get singleton HighSignalDetector instance."""
    global _high_signal_detector
    if _high_signal_detector is None:
        with _high_signal_detector_lock:
            if _high_signal_detector is None:
                _high_signal_detector = HighSignalDetector()
    return _high_signal_detector


# Alias for backward compatibility
def get_signal_detector() -> HighSignalDetector:
    """Alias for get_high_signal_detector()."""
    return get_high_signal_detector()


# V2.1: Alias for test compatibility
HighValueSignalDetector = HighSignalDetector
