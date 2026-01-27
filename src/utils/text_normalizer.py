"""
Text Normalizer V1.1 - Intelligent Text Processing for Multi-Language Support

Provides utilities for:
- Unicode normalization (NFKC)
- Accent folding for fuzzy matching
- Fuzzy team/player name matching using thefuzz
- Multi-language pattern support
- Multi-currency value extraction

Used by: verification_layer.py OptimizedResponseParser

Requirements: Supports all leagues (Turkey, Greece, Japan, China, Brazil, etc.)
"""
import re
import unicodedata
from typing import Optional, List, Tuple, Dict

# thefuzz is already in requirements.txt
try:
    from thefuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False


# ============================================
# UNICODE NORMALIZATION
# ============================================

def normalize_unicode(text: str) -> str:
    """Normalize Unicode text using NFKC normalization."""
    if not text:
        return ""
    return unicodedata.normalize('NFKC', text)


def fold_accents(text: str) -> str:
    """Remove accents/diacritics for fuzzy matching."""
    if not text:
        return ""
    nfd = unicodedata.normalize('NFD', text)
    result = ''.join(
        char for char in nfd
        if unicodedata.category(char) != 'Mn'
    )
    return result


def normalize_for_matching(text: str) -> str:
    """Full normalization pipeline for fuzzy matching."""
    if not text:
        return ""
    text = normalize_unicode(text)
    text = fold_accents(text)
    text = text.lower()
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ============================================
# FUZZY MATCHING
# ============================================

def fuzzy_match_team(
    query: str,
    text: str,
    threshold: int = 75
) -> Tuple[bool, int]:
    """Check if team name appears in text using fuzzy matching."""
    if not query or not text:
        return False, 0
    
    if not FUZZY_AVAILABLE:
        query_norm = normalize_for_matching(query)
        text_norm = normalize_for_matching(text)
        return query_norm in text_norm, 100 if query_norm in text_norm else 0
    
    query_norm = normalize_for_matching(query)
    text_norm = normalize_for_matching(text)
    
    if query_norm in text_norm:
        return True, 100
    
    words = text_norm.split()
    query_words = len(query_norm.split())
    best_score = 0
    
    for i in range(len(words)):
        for window_size in range(query_words, min(query_words + 3, len(words) - i + 1)):
            chunk = ' '.join(words[i:i + window_size])
            score = fuzz.token_set_ratio(query_norm, chunk)
            best_score = max(best_score, score)
            if score >= threshold:
                return True, score
    
    return best_score >= threshold, best_score


def fuzzy_match_player(
    player_name: str,
    text: str,
    threshold: int = 70
) -> Tuple[bool, int, Optional[str]]:
    """Find player name in text using fuzzy matching."""
    if not player_name or not text:
        return False, 0, None
    
    player_norm = normalize_for_matching(player_name)
    text_norm = normalize_for_matching(text)
    
    if player_norm in text_norm:
        return True, 100, player_name
    
    name_parts = player_norm.split()
    for part in name_parts:
        if len(part) >= 4 and part in text_norm:
            return True, 90, part
    
    if not FUZZY_AVAILABLE:
        return False, 0, None
    
    words = text_norm.split()
    best_score = 0
    best_match = None
    
    for i in range(len(words)):
        for window_size in range(1, min(4, len(words) - i + 1)):
            chunk = ' '.join(words[i:i + window_size])
            score = fuzz.token_set_ratio(player_norm, chunk)
            if score > best_score:
                best_score = score
                best_match = chunk
    
    return best_score >= threshold, best_score, best_match


# ============================================
# MULTI-LANGUAGE PATTERNS
# ============================================

FORM_PATTERNS = {
    'en': (r'won', r'drew', r'lost'),
    'es': (r'gan[óo]', r'empat[óo]', r'perdi[óo]'),
    'pt': (r'venceu', r'empatou', r'perdeu'),
    'de': (r'gewonnen', r'unentschieden', r'verloren'),
    'fr': (r'gagn[ée]', r'nul', r'perdu'),
    'it': (r'vinto', r'pareggi(?:ato|o)', r'perso'),
    'tr': (r'kazand[ıi]', r'berabere', r'kaybetti'),
    'nl': (r'gewonnen', r'gelijk', r'verloren'),
    'pl': (r'wygra[łl]', r'remis', r'przegra[łl]'),
}

def get_multilang_form_pattern() -> str:
    """Build a combined regex pattern for form stats in multiple languages."""
    won_patterns = '|'.join(p[0] for p in FORM_PATTERNS.values())
    drew_patterns = '|'.join(p[1] for p in FORM_PATTERNS.values())
    lost_patterns = '|'.join(p[2] for p in FORM_PATTERNS.values())
    return rf'({won_patterns})\s*(\d+)[^.]*?({drew_patterns})\s*(\d+)[^.]*?({lost_patterns})\s*(\d+)'


def get_value_patterns() -> List[Tuple[str, float]]:
    """
    Get all value extraction patterns with their multipliers.
    
    V1.1: Enhanced patterns to match various formats:
    - "Player's value is €60m"
    - "Endrick's is €55 million"
    - "valued at £50 million"
    """
    patterns = []
    
    # Currency symbols: euro, pound, dollar
    symbols = [r'€', r'£', r'\$']
    
    # Million suffixes
    m_suffix = r'm(?:illion(?:s)?|ln)?'
    
    for sym in symbols:
        # Pattern 1: "Player's value is €60m" or "Player's is €60 million"
        p1 = rf"(\w+(?:\s+\w+)?)'?s?\s*(?:market\s*)?(?:value\s*)?(?:is\s*)?{sym}\s*(\d+(?:\.\d+)?)\s*{m_suffix}"
        patterns.append((p1, 1.0))
        
        # Pattern 2: "Player has a value of €60m"
        p2 = rf"(\w+(?:\s+\w+)?)\s*(?:has\s*)?(?:a\s*)?(?:market\s*)?value\s*(?:of\s*)?{sym}\s*(\d+(?:\.\d+)?)\s*{m_suffix}"
        patterns.append((p2, 1.0))
        
        # Pattern 3: "valued at €60m"
        p3 = rf"(\w+(?:\s+\w+)?)\s*(?:is\s*)?valued\s*at\s*{sym}\s*(\d+(?:\.\d+)?)\s*{m_suffix}"
        patterns.append((p3, 1.0))
        
        # Pattern 4: Thousands (€500k)
        p4 = rf"(\w+(?:\s+\w+)?)'?s?\s*(?:market\s*)?(?:value\s*)?(?:is\s*)?{sym}\s*(\d+(?:\.\d+)?)\s*k"
        patterns.append((p4, 0.001))
    
    return patterns


# Referee card patterns for different languages
REFEREE_CARD_PATTERNS = [
    r'(\d+\.?\d*)\s*(?:yellow\s*)?cards?\s*(?:per\s*(?:game|match)|average)',
    r'average[^.]*?(\d+\.?\d*)\s*(?:yellow\s*)?cards?',
    r'(\d+\.?\d*)\s*tarjetas?\s*(?:por\s*partido|promedio)',
    r'(\d+\.?\d*)\s*cart[õo]es?\s*(?:por\s*jogo|m[ée]dia)',
    r'(\d+\.?\d*)\s*(?:gelbe\s*)?karten?\s*(?:pro\s*spiel|durchschnitt)',
    r'(\d+\.?\d*)\s*cartellini?\s*(?:per\s*partita|media)',
    r'(\d+\.?\d*)\s*kart\s*(?:maç\s*başına|ortalama)',
]


# ============================================
# TEAM NAME ALIASES
# ============================================

TEAM_ALIASES: Dict[str, List[str]] = {
    # Brazil
    'flamengo': ['flamengo', 'mengao', 'fla', 'clube de regatas do flamengo'],
    'palmeiras': ['palmeiras', 'verdao', 'sep', 'sociedade esportiva palmeiras'],
    'corinthians': ['corinthians', 'timao', 'sccp'],
    'sao paulo': ['sao paulo', 'spfc', 'tricolor paulista'],
    # Turkey
    'galatasaray': ['galatasaray', 'gala', 'cimbom', 'aslan'],
    'fenerbahce': ['fenerbahce', 'fener', 'kanarya'],
    'besiktas': ['besiktas', 'bjk', 'kara kartal'],
    'trabzonspor': ['trabzonspor', 'trabzon', 'ts', 'bordo mavi'],
    # Greece
    'olympiacos': ['olympiacos', 'olympiakos', 'thrylos'],
    'panathinaikos': ['panathinaikos', 'pao', 'trifouli'],
    'aek athens': ['aek athens', 'aek', 'enosi'],
    'paok': ['paok', 'dikefalos'],
    # Japan
    'urawa reds': ['urawa reds', 'urawa', 'urawa red diamonds'],
    'vissel kobe': ['vissel kobe', 'vissel', 'kobe'],
    'kawasaki frontale': ['kawasaki frontale', 'kawasaki'],
    # Argentina
    'boca juniors': ['boca juniors', 'boca', 'cabj', 'xeneize'],
    'river plate': ['river plate', 'river', 'carp', 'millonario'],
    # Mexico
    'club america': ['club america', 'america', 'las aguilas'],
    'chivas': ['chivas', 'guadalajara', 'cd guadalajara'],
    # Scotland
    'celtic': ['celtic', 'celtic fc', 'the hoops', 'bhoys'],
    'rangers': ['rangers', 'rangers fc', 'the gers'],
    # Australia
    'melbourne victory': ['melbourne victory', 'victory', 'big v'],
    'sydney fc': ['sydney fc', 'sydney', 'sky blues'],
    # Poland
    'legia warsaw': ['legia warsaw', 'legia', 'legia warszawa'],
    'lech poznan': ['lech poznan', 'lech', 'kolejorz'],
}


def get_team_aliases(team_name: str) -> List[str]:
    """Get all known aliases for a team name."""
    team_lower = normalize_for_matching(team_name)
    for canonical, aliases in TEAM_ALIASES.items():
        if team_lower in [normalize_for_matching(a) for a in aliases]:
            return aliases
    return [team_name]


def find_team_in_text(team_name: str, text: str, threshold: int = 75) -> Tuple[bool, int]:
    """Find team in text using aliases and fuzzy matching."""
    aliases = get_team_aliases(team_name)
    best_score = 0
    found = False
    for alias in aliases:
        matched, score = fuzzy_match_team(alias, text, threshold)
        if score > best_score:
            best_score = score
            found = matched
    return found, best_score
