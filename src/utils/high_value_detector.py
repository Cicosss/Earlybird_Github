"""
High Value Detector Module - V2.0

Detects high-value betting signals from sports news content.
Replaces the old keyword-matching approach with a smarter pipeline:

1. GarbageFilter: Removes navigation menus, login pages, garbage content
2. HighSignalDetector: Detects critical patterns that indicate betting value
3. StructuredAnalysis: Dataclass for LLM-extracted structured data

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
"""
import re
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

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
    MASS_ABSENCE = "MASS_ABSENCE"           # 3+ players out
    DECIMATED = "DECIMATED"                 # Team decimated/crisis
    YOUTH_TEAM = "YOUTH_TEAM"               # Youth/reserve team fielded
    TURNOVER = "TURNOVER"                   # Full rotation confirmed
    FINANCIAL_CRISIS = "FINANCIAL_CRISIS"   # Unpaid wages, strike
    LOGISTICAL_CRISIS = "LOGISTICAL_CRISIS" # Travel chaos, flight issues
    GOALKEEPER_OUT = "GOALKEEPER_OUT"       # Goalkeeper unavailable
    MOTIVATION = "MOTIVATION"               # Nothing to play for
    KEY_PLAYER = "KEY_PLAYER"               # Captain/star out
    CONFIRMED_LINEUP = "CONFIRMED_LINEUP"   # V2.3: Early lineup announcement (24-48h before)
    
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
    # EXCLUSION KEYWORDS (from content_analysis.py)
    # ============================================
    
    # Basketball and other excluded sports
    EXCLUDED_SPORTS = [
        # Basketball
        "basket", "basketball", "nba", "euroleague", "pallacanestro",
        "baloncesto", "koszykówka", "basketbol", "acb", "fiba",
        # Other sports explicitly excluded
        "tennis", "golf", "cricket", "hockey", "baseball", "mlb"
    ]
    
    # Women's football
    EXCLUDED_CATEGORIES = [
        "women", "woman", "ladies", "feminine", "femminile", "femenino",
        "kobiet", "kadın", "bayan", "wsl", "liga f", "women's", "womens",
        "donne", "féminin", "feminino", "frauen", "vrouwen", "damernas"
    ]
    
    # Other excluded sports
    EXCLUDED_OTHER_SPORTS = [
        # American sports
        "nfl", "american football", "super bowl", "touchdown",
        # Rugby
        "rugby", "six nations", "rugby union", "rugby league",
        # Other
        "handball", "volleyball", "futsal", "pallavolo", "balonmano",
        "beach soccer", "esports", "e-sports", "gaming"
    ]
    
    # Patterns that indicate garbage content
    GARBAGE_PATTERNS = [
        # Login/subscription
        r'\b(login|sign in|subscribe|newsletter|cookie|privacy policy)\b',
        # Social media prompts
        r'\b(follow us|share this|tweet|facebook|instagram)\b',
        # Broken extraction (same word repeated 4+ times)
        r'(\b\w+\b)(\s+\1){3,}',
    ]
    
    # V2.2: Pattern for navigation menu detection (separate, not in GARBAGE_PATTERNS)
    NAVIGATION_MENU_PATTERN = r'^[A-Z][a-z]+(\s+[A-Z][a-z]+){3,}$'
    
    # Minimum content requirements
    MIN_CONTENT_LENGTH = 100  # chars (lowered from 150)
    MIN_WORD_COUNT = 15  # words (lowered from 20)
    MAX_CAPS_RATIO = 0.4  # Max 40% uppercase
    
    def __init__(self):
        """Initialize with compiled patterns."""
        self._garbage_patterns = [
            re.compile(p, re.IGNORECASE | re.MULTILINE) 
            for p in self.GARBAGE_PATTERNS
        ]
        
        # V2.2: Compile navigation menu pattern separately
        self._nav_menu_pattern = re.compile(self.NAVIGATION_MENU_PATTERN)
        
        # Build exclusion pattern from all excluded keywords
        all_excluded = (
            self.EXCLUDED_SPORTS + 
            self.EXCLUDED_CATEGORIES + 
            self.EXCLUDED_OTHER_SPORTS
        )
        exclusion_pattern = r'\b(' + '|'.join(re.escape(kw) for kw in all_excluded) + r')\b'
        self._exclusion_pattern = re.compile(exclusion_pattern, re.IGNORECASE)
    
    def is_garbage(self, content: str) -> Tuple[bool, Optional[str]]:
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
    
    def is_excluded_sport(self, content: str) -> Tuple[bool, Optional[str]]:
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
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
        # Remove lines that look like navigation (short lines with only caps words)
        lines = cleaned.split('\n')
        filtered_lines = []
        for line in lines:
            line = line.strip()
            # Skip empty lines
            if not line:
                continue
            # Skip short lines that are all caps (likely nav)
            if len(line) < 50 and line.isupper():
                continue
            # V2.2: Fixed - Skip lines that look like menu items (Home News Sport...)
            if self._nav_menu_pattern.match(line):
                continue
            filtered_lines.append(line)
        
        cleaned = '\n'.join(filtered_lines)
        
        # Remove excessive whitespace
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        
        return cleaned.strip()
    
    def get_garbage_reason(self, content: str) -> Optional[str]:
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
    """
    detected: bool = False
    signal_type: SignalType = SignalType.NONE
    matched_pattern: Optional[str] = None
    extracted_number: Optional[int] = None  # V2.1: Number extracted from text (e.g., "without 9 players" -> 9)
    priority: str = "NONE"
    all_signals: List[SignalType] = field(default_factory=list)
    all_matches: List[str] = field(default_factory=list)


# ============================================
# HIGH SIGNAL DETECTOR
# ============================================

class HighSignalDetector:
    """
    Detects high-value betting signals using multilingual patterns.
    
    V2.1: Enhanced with SignalType enum and number extraction.
    V2.2: Fixed duplicate dictionary keys in NUMBER_WORDS.
    
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
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'eleven': 11, 'twelve': 12, 'several': 4, 'multiple': 4, 'numerous': 5,
        # Italian (unique)
        'uno': 1, 'due': 2, 'tre': 3, 'quattro': 4, 'cinque': 5,
        'sei': 6, 'sette': 7, 'otto': 8, 'nove': 9, 'dieci': 10,
        # Spanish (unique - 'uno' shared with IT, same value)
        'dos': 2, 'tres': 3, 'cuatro': 4,
        'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10,
        # Portuguese (unique)
        'um': 1, 'dois': 2, 'três': 3,
        'oito': 8, 'dez': 10,
        # Shared ES/PT
        'cinco': 5, 'seis': 6,
        # German (unique)
        'ein': 1, 'zwei': 2, 'drei': 3, 'vier': 4, 'fünf': 5,
        'sechs': 6, 'sieben': 7, 'acht': 8, 'neun': 9, 'zehn': 10,
    }
    
    # HIGH-VALUE PATTERNS (multilingual roots)
    # These patterns indicate content worth analyzing with LLM
    
    # Pattern 1: Decimated/Crisis (Latin root works in EN/ES/IT/PT/FR/DE)
    CRISIS_PATTERNS = [
        r'\b(decimat|diezm|dizim)',  # decimated/diezmado/dizimado
        r'\b(cris[ie]s?|kris[ei])',   # crisis/crisi/krise
        r'\b(emerg[eê]nc)',           # emergency/emergência/emergenza
        r'\b(desfalc|depaupera)',     # depleted (PT/ES)
        r'\b(notstand|ausnahmezustand)',  # emergency (DE)
    ]
    
    # Pattern 2: Multiple absences with numbers
    NUMERIC_ABSENCE_PATTERNS = [
        r'\b(without|sans|sin|senza|ohne|sem)\s+(\d+|[a-z]+)\s+(player|joueur|jugador|giocator|spieler|jogador)',
        r'\b(\d+)\s+(player|joueur|jugador|giocator|spieler|jogador)s?\s+(out|absent|missing|unavailable)',
        r'\b(miss|without|lacking)\s+(\d+|several|multiple|numerous)',
        r'\bmissing\s+(\d+|several|multiple)',
        r'\b(\d+)\s+(absent|assent|ausente)',
        r'\bsenza\s+(\d+)',  # Italian: senza 9 giocatori
        r'\bsin\s+(\d+)',    # Spanish: sin 7 jugadores
        r'\bsem\s+(\d+)',    # Portuguese: sem 5 jogadores
        r'\bohne\s+(\d+)',   # German: ohne 6 spieler
    ]
    
    # Pattern 3: Youth team / Reserves fielded
    YOUTH_ROTATION_PATTERNS = [
        r'\b(youth\s+team|youth\s+squad|reserve\s+team|second\s+team|b\s+team)',
        r'\b(squadra\s+giovanile|formazione\s+giovanile|primavera)',  # IT
        r'\b(equipo\s+juvenil|equipo\s+reserva|filial)',  # ES
        r'\b(time\s+de\s+base|equipe\s+reserva|sub-\d+)',  # PT
        r'\b(jugendmannschaft|zweite\s+mannschaft|reservemannschaft)',  # DE
        r'\b(équipe\s+réserve|équipe\s+jeunes)',  # FR
        r'\b(field|play|start)\s+(with\s+)?(youth|youngsters|reserves|kids)',
        r'\b(punta\s+sui\s+giovani)',  # IT: relies on youth
        r'\b(apuesta\s+por\s+los\s+jóvenes)',  # ES
    ]
    
    # Pattern 4: Full rotation / Resting starters
    ROTATION_PATTERNS = [
        r'\b(full\s+rotation|complete\s+rotation|total\s+rotation)',
        r'\b(rest|rested|resting)\s+(all|entire|whole|most)\s+(starter|first\s+team|regular)',
        r'\b(turnover\s+(totale|completo|masivo|massif))',
        r'\b(rotazione\s+(totale|completa))',  # IT
        r'\b(rotación\s+(total|completa))',    # ES
        r'\b(rodízio\s+(total|completo))',     # PT
    ]
    
    # Pattern 5: Strike / Financial crisis
    # V2.3: Fixed - Added \b at end to prevent matching "striker"
    CRISIS_EXTERNAL_PATTERNS = [
        r'\b(strike|sciopero|huelga|grève|streik|greve)\b',
        r'\b(unpaid|salari[eo]s?\s+(non\s+)?paga[td]|wages?\s+unpaid)\b',
        r'\b(financial\s+crisis|crisi\s+finanziaria|crisis\s+financiera)\b',
        r'\b(stipendi\s+arretrati|sueldos\s+atrasados)\b',
    ]
    
    # Pattern 6: Travel/Logistical disruption
    DISRUPTION_PATTERNS = [
        r'\b(flight\s+(cancel|delay|divert)|volo\s+(cancellat|deviat|ritard))',
        r'\b(travel\s+(chaos|problem|issue|disruption))',
        r'\b(bus\s+journey|viaggio\s+in\s+(autobus|pullman))',
        r'\b(chaotic\s+arrival|arrivo\s+caotico)',
        r'\b(no\s+training|senza\s+allenamento|sin\s+entrenamiento)',
    ]
    
    # Pattern 7: Motivational mismatch
    MOTIVATION_PATTERNS = [
        r'\b(nothing\s+to\s+play\s+for|niente\s+da\s+giocare|nada\s+que\s+jugar)',
        r'\b(already\s+(qualified|relegated|safe|promoted))',
        r'\b(già\s+(qualificat|retrocesso|salv))',  # IT
        r'\b(ya\s+(clasificad|descendid|salvad))',  # ES
        r'\b(mathematically\s+(safe|relegated|out))',
        r'\b(no\s+(more\s+)?options?\s+to\s+(advance|qualify))',
    ]
    
    # Pattern 8: Goalkeeper out (separate from KEY_PLAYER for specific detection)
    GOALKEEPER_PATTERNS = [
        r'\b(goalkeeper|portiere|portero|goleiro|torwart|gardien)\s+(out|injured|absent|unavailable|will miss)',
        r'\b(without\s+(their\s+)?goalkeeper)',
        r'\b(senza\s+(il\s+)?portiere)',  # IT
        r'\b(sin\s+(el\s+)?portero)',      # ES
    ]
    
    # Pattern 9: Other key players out (captain, star - NOT goalkeeper)
    KEY_PLAYER_PATTERNS = [
        r'\b(captain|capitano|capitán|capitão|kapitän|capitaine)\s+(out|injured|absent|suspended)',
        r'\b(star\s+player|top\s+scorer|capocannoniere|goleador|artilheiro)\s+(out|miss|absent)',
        r'\b(without\s+(their\s+)?(captain|star))',
        r'\b(senza\s+(il\s+)?capitano)',  # IT
        r'\b(sin\s+(el\s+)?capitán)',      # ES
    ]
    
    # Pattern 10: Confirmed lineup announced early (V2.3 NEW)
    # GOLD SIGNAL: Some managers announce lineup 24-48h before match
    # This gives betting edge before market reacts
    CONFIRMED_LINEUP_PATTERNS = [
        # English
        r'\b(confirmed|official|announced)\s+(lineup|line-up|starting\s+xi|starting\s+eleven|formation)',
        r'\b(starting\s+xi|starting\s+eleven|starting\s+lineup)\s+(confirmed|announced|revealed)',
        r'\b(lineup|line-up|formation)\s+(revealed|announced|confirmed)',
        r'\b(manager|coach|boss)\s+(confirms?|announces?|reveals?)\s+(lineup|starting|team|formation)',
        r'\b(coach|manager|boss)\s+reveals?\s+(the\s+)?(lineup|formation|starting|team)',
        # Italian
        r'\b(formazione\s+ufficiale|undici\s+titolare|formazione\s+confermata)',
        r'\b(conferma\s+(la\s+)?formazione|annuncia\s+(la\s+)?formazione)',
        r'\b(ecco\s+(la\s+)?formazione|scelte\s+di\s+formazione)',
        # Spanish
        r'\b(alineación\s+(confirmada|oficial)|once\s+titular\s+(confirmado|oficial))',
        r'\b(confirma\s+(la\s+)?alineación|anuncia\s+(la\s+)?alineación)',
        r'\b(formación\s+(confirmada|oficial))',
        r'\b(técnico|entrenador)\s+anuncia\s+(la\s+)?alineación',
        # Portuguese
        r'\b(escalação\s+(confirmada|oficial)|onze\s+titular\s+confirmado)',
        r'\b(confirma\s+(a\s+)?escalação|anuncia\s+(a\s+)?escalação)',
        # German
        r'\b(aufstellung\s+(bestätigt|offiziell)|startelf\s+bestätigt)',
        r'\b(bestätigt\s+(die\s+)?aufstellung)',
        # French
        r'\b(composition\s+(confirmée|officielle)|onze\s+de\s+départ\s+confirmé)',
        r'\b(confirme\s+(la\s+)?composition|annonce\s+(la\s+)?composition)',
    ]
    
    # Mapping from internal pattern group to SignalType
    PATTERN_TO_SIGNAL_TYPE = {
        'CRISIS': SignalType.DECIMATED,
        'NUMERIC_ABSENCE': SignalType.MASS_ABSENCE,
        'YOUTH_ROTATION': SignalType.YOUTH_TEAM,
        'ROTATION': SignalType.TURNOVER,
        'CRISIS_EXTERNAL': SignalType.FINANCIAL_CRISIS,
        'DISRUPTION': SignalType.LOGISTICAL_CRISIS,
        'MOTIVATION': SignalType.MOTIVATION,
        'GOALKEEPER': SignalType.GOALKEEPER_OUT,
        'KEY_PLAYER': SignalType.KEY_PLAYER,
        'CONFIRMED_LINEUP': SignalType.CONFIRMED_LINEUP,  # V2.3: Early lineup
    }
    
    def __init__(self):
        """Initialize with compiled patterns."""
        self._all_patterns: List[Tuple[str, re.Pattern]] = []
        
        # Compile all pattern groups
        # NOTE: GOALKEEPER must come BEFORE KEY_PLAYER for correct priority
        # NOTE: CONFIRMED_LINEUP added at end (lower priority than absences)
        pattern_groups = [
            ('CRISIS', self.CRISIS_PATTERNS),
            ('NUMERIC_ABSENCE', self.NUMERIC_ABSENCE_PATTERNS),
            ('YOUTH_ROTATION', self.YOUTH_ROTATION_PATTERNS),
            ('ROTATION', self.ROTATION_PATTERNS),
            ('CRISIS_EXTERNAL', self.CRISIS_EXTERNAL_PATTERNS),
            ('DISRUPTION', self.DISRUPTION_PATTERNS),
            ('MOTIVATION', self.MOTIVATION_PATTERNS),
            ('GOALKEEPER', self.GOALKEEPER_PATTERNS),  # Before KEY_PLAYER!
            ('KEY_PLAYER', self.KEY_PLAYER_PATTERNS),
            ('CONFIRMED_LINEUP', self.CONFIRMED_LINEUP_PATTERNS),  # V2.3
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
            r'\b(without|sans|sin|senza|ohne|sem|missing)\s+(\d+|[a-z]+)',
            re.IGNORECASE
        )
    
    def _extract_number(self, content: str) -> Optional[int]:
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
        absence_keywords = ['without', 'missing', 'absent', 'out', 'senza', 'sin', 'sem', 'ohne']
        content_lower = content.lower()
        
        for keyword in absence_keywords:
            if keyword in content_lower:
                # Find numbers within 20 chars of keyword
                idx = content_lower.find(keyword)
                context = content_lower[max(0, idx-10):idx+30]
                numbers = re.findall(r'\b(\d+)\b', context)
                if numbers:
                    # Return first reasonable number (1-20)
                    for num in numbers:
                        n = int(num)
                        if 1 <= n <= 20:
                            return n
        
        return None

    
    def detect_signals(self, content: str) -> Dict[str, Any]:
        """
        Detect high-value signals in content.
        
        Args:
            content: Text content to analyze
            
        Returns:
            Dict with:
                - has_signal: bool - True if any high-value signal found
                - signals: List[str] - Names of detected signal types
                - matches: List[str] - Actual matched text
                - priority: str - HIGH/MEDIUM/LOW based on signal strength
                - extracted_number: int or None - Number of absent players
        """
        if not content:
            return {
                'has_signal': False,
                'signals': [],
                'matches': [],
                'priority': 'NONE',
                'extracted_number': None
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
        
        # Determine priority based on signals
        priority = self._calculate_priority(signals, extracted_number)
        
        return {
            'has_signal': len(signals) > 0,
            'signals': signals,
            'matches': matches[:5],  # Limit to 5 matches
            'priority': priority,
            'extracted_number': extracted_number
        }
    
    def _calculate_priority(self, signals: List[str], extracted_number: Optional[int] = None) -> str:
        """Calculate priority based on detected signals."""
        if not signals:
            return 'NONE'
        
        # HIGH priority signals
        high_priority = {'CRISIS', 'NUMERIC_ABSENCE', 'YOUTH_ROTATION', 'CRISIS_EXTERNAL'}
        if any(s in high_priority for s in signals):
            # For NUMERIC_ABSENCE, check threshold
            if 'NUMERIC_ABSENCE' in signals and extracted_number is not None:
                if extracted_number < self.MASS_ABSENCE_THRESHOLD:
                    # Below threshold, downgrade to MEDIUM
                    if len(signals) == 1:
                        return 'MEDIUM'
            return 'HIGH'
        
        # MEDIUM priority signals (GOALKEEPER added)
        medium_priority = {'ROTATION', 'DISRUPTION', 'KEY_PLAYER', 'GOALKEEPER'}
        if any(s in medium_priority for s in signals):
            return 'MEDIUM'
        
        # LOW priority (motivation alone)
        return 'LOW'
    
    def has_high_value_signal(self, content: str) -> bool:
        """Quick check if content has any high-value signal."""
        result = self.detect_signals(content)
        return result['has_signal'] and result['priority'] in ('HIGH', 'MEDIUM')
    
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
        for sig in raw_result['signals']:
            signal_type = self.PATTERN_TO_SIGNAL_TYPE.get(sig, SignalType.NONE)
            signal_types.append(signal_type)
        
        # Get primary signal type
        primary_signal = signal_types[0] if signal_types else SignalType.NONE
        
        # V2.1: For MASS_ABSENCE, check threshold
        extracted_number = raw_result.get('extracted_number')
        if primary_signal == SignalType.MASS_ABSENCE:
            if extracted_number is not None and extracted_number < self.MASS_ABSENCE_THRESHOLD:
                # Below threshold - not a valid detection
                return SignalResult(
                    detected=False,
                    signal_type=SignalType.NONE,
                    matched_pattern=raw_result['matches'][0] if raw_result['matches'] else None,
                    extracted_number=extracted_number,
                    priority='NONE',
                    all_signals=[],
                    all_matches=raw_result['matches']
                )
        
        return SignalResult(
            detected=raw_result['has_signal'],
            signal_type=primary_signal,
            matched_pattern=raw_result['matches'][0] if raw_result['matches'] else None,
            extracted_number=extracted_number,
            priority=raw_result['priority'],
            all_signals=signal_types,
            all_matches=raw_result['matches']
        )


# ============================================
# STRUCTURED ANALYSIS RESULT
# ============================================

@dataclass
class StructuredAnalysis:
    """
    Structured analysis result from LLM.
    
    Contains all information needed for a high-value betting alert.
    All fields are extracted by the LLM from the original content.
    """
    # Required fields (alert not sent if missing)
    team: Optional[str] = None
    opponent: Optional[str] = None
    
    # Absence information
    absent_count: int = 0
    absent_type: str = "UNKNOWN"  # INJURY, ROTATION, YOUTH_TEAM, STRIKE, OTHER
    absent_names: List[str] = field(default_factory=list)
    absent_roles: List[str] = field(default_factory=list)  # GK, DEF, MID, FWD
    
    # Match context
    competition: Optional[str] = None
    match_date: Optional[str] = None
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
    
    def is_valid_for_alert(self) -> bool:
        """
        Check if this analysis has enough info for a valid alert.
        
        Rules:
        - Must have team name
        - Must have either:
          - 3+ absent players, OR
          - Goalkeeper absent, OR
          - Youth team fielded, OR
          - Financial crisis/strike
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
        """Get alert priority based on analysis."""
        if self.absent_type == "YOUTH_TEAM":
            return "CRITICAL"
        if self.has_financial_crisis:
            return "CRITICAL"
        if self.absent_count >= 5:
            return "CRITICAL"
        if self.absent_count >= 3:
            return "HIGH"
        if self.absent_roles and "GK" in self.absent_roles:
            return "HIGH"
        return "MEDIUM"


# ============================================
# SINGLETON INSTANCES
# ============================================

_garbage_filter: Optional[GarbageFilter] = None
_high_signal_detector: Optional[HighSignalDetector] = None
_singleton_lock = threading.Lock()


def get_garbage_filter() -> GarbageFilter:
    """Get singleton GarbageFilter instance."""
    global _garbage_filter
    if _garbage_filter is None:
        with _singleton_lock:
            if _garbage_filter is None:
                _garbage_filter = GarbageFilter()
    return _garbage_filter


def get_high_signal_detector() -> HighSignalDetector:
    """Get singleton HighSignalDetector instance."""
    global _high_signal_detector
    if _high_signal_detector is None:
        with _singleton_lock:
            if _high_signal_detector is None:
                _high_signal_detector = HighSignalDetector()
    return _high_signal_detector


# Alias for backward compatibility
def get_signal_detector() -> HighSignalDetector:
    """Alias for get_high_signal_detector()."""
    return get_high_signal_detector()


# V2.1: Alias for test compatibility
HighValueSignalDetector = HighSignalDetector
