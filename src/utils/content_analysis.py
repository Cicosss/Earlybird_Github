"""
Content Analysis Module - Shared utilities for content filtering and relevance analysis.

This module provides reusable components for:
- ExclusionFilter: Filters out non-relevant content (basketball, women's sports, NFL, etc.)
- RelevanceAnalyzer: Analyzes content for betting-relevant keywords
- AnalysisResult: Dataclass for analysis results

Used by:
- src/services/news_radar.py
- src/services/browser_monitor.py

V1.0: Extracted from news_radar.py for DRY compliance and shared usage.
"""
import re
import logging
from dataclasses import dataclass
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """
    Result of content relevance analysis.
    
    Attributes:
        is_relevant: True if content is betting-relevant
        category: INJURY, SUSPENSION, NATIONAL_TEAM, CUP_ABSENCE, YOUTH_CALLUP, OTHER
        affected_team: Extracted team name (may be None)
        confidence: 0.0 - 1.0 confidence score
        summary: Brief summary of the content
        betting_impact: V1.4 - HIGH, MEDIUM, LOW (optional, from DeepSeek)
    """
    is_relevant: bool
    category: str
    affected_team: Optional[str]
    confidence: float
    summary: str
    betting_impact: Optional[str] = None  # V1.4: HIGH, MEDIUM, LOW


class PositiveNewsFilter:
    """
    V1.4: Filters out "positive" news that don't affect betting negatively.
    V1.5: Enhanced with sentence-level analysis to avoid false negatives.
    
    Positive news = player returning from injury, back in training, fit again.
    These don't create betting opportunities (no lineup disruption).
    
    IMPORTANT (V1.5): Now uses sentence-level analysis instead of document-level.
    This prevents false negatives like "Salah returns but Nunez OUT" being skipped.
    If a sentence contains BOTH positive AND negative keywords, it's NOT positive news.
    
    This filter saves API calls by skipping content before DeepSeek analysis.
    """
    
    # Positive news keywords (multilingual) - player RETURNING, not going OUT
    POSITIVE_KEYWORDS = [
        # English
        "returns to training", "back in training", "fit again", "fully fit",
        "back in squad", "returns to squad", "cleared to play", "given green light",
        "recovered", "recovery complete", "back from injury", "returns from injury",
        "available again", "back in contention", "passed fitness test",
        # Italian
        "torna in gruppo", "rientra in gruppo", "recuperato", "recupero completato",
        "torna disponibile", "di nuovo disponibile", "torna in squadra",
        "supera i controlli", "torna ad allenarsi", "rientro in gruppo",
        # Spanish
        "vuelve a entrenar", "recuperado", "regresa al grupo", "alta médica",
        "vuelve a estar disponible", "se reincorpora",
        # Portuguese
        "volta aos treinos", "recuperado", "volta ao grupo", "liberado",
        # German
        "zurück im training", "wieder fit", "genesen", "zurück im kader",
        # French
        "de retour à l'entraînement", "rétabli", "apte", "de retour dans le groupe"
    ]
    
    # V1.5: Negative keywords that override positive news in same sentence
    NEGATIVE_OVERRIDE_KEYWORDS = [
        # English
        "out", "miss", "absent", "injured", "ruled out", "sidelined", "doubt",
        "unavailable", "suspended", "banned", "will not play", "won't play",
        "doubtful", "uncertain", "unlikely", "fitness concern",
        # Italian
        "fuori", "assente", "infortunato", "squalificato", "indisponibile",
        "non giocherà", "in dubbio", "a rischio",
        # Spanish
        "fuera", "ausente", "lesionado", "sancionado", "no jugará", "duda",
        "baja", "descartado",
        # Portuguese
        "fora", "ausente", "lesionado", "suspenso", "não jogará", "dúvida",
        # German
        "fehlt", "verletzt", "gesperrt", "fällt aus", "fraglich",
        # French
        "absent", "blessé", "suspendu", "forfait", "incertain"
    ]
    
    def __init__(self):
        """Initialize with compiled regex patterns for efficiency."""
        positive_pattern = r'\b(' + '|'.join(re.escape(kw) for kw in self.POSITIVE_KEYWORDS) + r')\b'
        self._positive_pattern = re.compile(positive_pattern, re.IGNORECASE)
        
        # V1.5: Compile negative override pattern
        negative_pattern = r'\b(' + '|'.join(re.escape(kw) for kw in self.NEGATIVE_OVERRIDE_KEYWORDS) + r')\b'
        self._negative_pattern = re.compile(negative_pattern, re.IGNORECASE)
    
    def _split_into_sentences(self, content: str) -> List[str]:
        """
        Split content into sentences for granular analysis.
        
        Handles multiple sentence delimiters and edge cases.
        """
        if not content:
            return []
        
        # Split by common sentence delimiters
        # Also split by newlines (common in news articles)
        sentences = re.split(r'[.!?]\s+|\n+', content)
        
        # Filter out very short segments (likely not real sentences)
        return [s.strip() for s in sentences if s and len(s.strip()) > 10]
    
    def is_positive_news(self, content: str) -> bool:
        """
        V1.5: Check if content is PURELY positive news (player returning).
        
        Uses sentence-level analysis:
        - If a sentence has positive keywords BUT ALSO negative keywords,
          it's NOT considered positive news (e.g., "Salah returns but Nunez OUT")
        - Only returns True if ALL positive matches are in sentences WITHOUT negatives
        
        Args:
            content: Text content to check
            
        Returns:
            True if content is purely positive news (should be skipped), False otherwise
        """
        if not content:
            return False
        
        # Quick check: if no positive keywords at all, not positive news
        if not self._positive_pattern.search(content):
            return False
        
        # V1.5: Sentence-level analysis
        sentences = self._split_into_sentences(content)
        
        has_pure_positive = False
        
        for sentence in sentences:
            has_positive = bool(self._positive_pattern.search(sentence))
            has_negative = bool(self._negative_pattern.search(sentence))
            
            if has_positive:
                if has_negative:
                    # This sentence has BOTH positive and negative
                    # The negative overrides - this is NOT purely positive news
                    # Example: "Salah returns but Nunez is OUT"
                    logger.debug(f"[POSITIVE-FILTER] Mixed sentence detected, not skipping: {sentence[:60]}...")
                    return False
                else:
                    # Pure positive sentence found
                    has_pure_positive = True
        
        # Only skip if we found pure positive sentences and NO mixed sentences
        return has_pure_positive
    
    def get_positive_reason(self, content: str) -> Optional[str]:
        """
        Get the matched positive keyword.
        
        Args:
            content: Text content to check
            
        Returns:
            Matched positive keyword, or None if not positive news
        """
        if not content:
            return None
        
        # Only return reason if is_positive_news() would return True
        if not self.is_positive_news(content):
            return None
        
        match = self._positive_pattern.search(content)
        if match:
            return match.group(1).lower()
        return None


class ExclusionFilter:
    """
    Filters out non-relevant content based on exclusion keywords.
    
    Excludes:
    - Basketball, tennis, golf, cricket, hockey, baseball
    - Women's/Ladies football
    - NFL/American Football, Rugby
    - Handball, volleyball, futsal, esports
    
    NOTE: Youth/Primavera/U19 are NOT excluded - they are RELEVANT for betting
    when youth players are called up to first team or replace injured starters.
    """
    
    # Exclusion keywords (multilingual)
    EXCLUDED_SPORTS = [
        # Basketball
        "basket", "basketball", "nba", "euroleague", "pallacanestro",
        "baloncesto", "koszykówka", "basketbol", "acb", "fiba",
        # Other sports explicitly excluded
        "tennis", "golf", "cricket", "hockey", "baseball", "mlb"
    ]
    
    EXCLUDED_CATEGORIES = [
        # Women's football
        "women", "woman", "ladies", "feminine", "femminile", "femenino",
        "kobiet", "kadın", "bayan", "wsl", "liga f", "women's", "womens",
        "donne", "féminin", "feminino", "frauen", "vrouwen", "damernas"
    ]
    
    EXCLUDED_OTHER_SPORTS = [
        # American sports
        "nfl", "american football", "super bowl", "touchdown",
        # Rugby
        "rugby", "six nations", "rugby union", "rugby league",
        # Other
        "handball", "volleyball", "futsal", "pallavolo", "balonmano",
        "beach soccer", "esports", "e-sports", "gaming"
    ]
    
    def __init__(self):
        """Initialize with compiled regex pattern for efficiency."""
        all_excluded = (
            self.EXCLUDED_SPORTS + 
            self.EXCLUDED_CATEGORIES + 
            self.EXCLUDED_OTHER_SPORTS
        )
        # Create case-insensitive pattern with word boundaries
        pattern = r'\b(' + '|'.join(re.escape(kw) for kw in all_excluded) + r')\b'
        self._exclusion_pattern = re.compile(pattern, re.IGNORECASE)
    
    def is_excluded(self, content: str) -> bool:
        """
        Check if content should be excluded.
        
        Args:
            content: Text content to check
            
        Returns:
            True if content matches exclusion keywords, False otherwise
        """
        if not content:
            return True
        
        return bool(self._exclusion_pattern.search(content))
    
    def get_exclusion_reason(self, content: str) -> Optional[str]:
        """
        Get the reason for exclusion.
        
        Args:
            content: Text content to check
            
        Returns:
            Matched exclusion keyword, or None if not excluded
        """
        if not content:
            return "empty_content"
        
        match = self._exclusion_pattern.search(content)
        if match:
            return match.group(1).lower()
        return None


class RelevanceAnalyzer:
    """
    Analyzes content for betting relevance using keyword matching.
    
    Categories detected:
    - INJURY: Player injuries, absences
    - SUSPENSION: Red cards, bans
    - NATIONAL_TEAM: International call-ups
    - CUP_ABSENCE: Cup rotation, rest
    - YOUTH_CALLUP: Youth players promoted to first team
    
    Confidence calculation:
    - Base: 0.3
    - Per keyword match: +0.1
    - Maximum: 0.85 (leaves room for DeepSeek refinement)
    """
    
    # Relevance keywords (multilingual)
    INJURY_KEYWORDS = [
        # English
        "injury", "injured", "out", "ruled out", "miss", "absent", "sidelined",
        "hamstring", "knee", "ankle", "muscle", "strain", "sprain", "fracture",
        # Italian
        "infortunio", "infortunato", "assente", "fuori", "indisponibile",
        # Spanish
        "lesión", "lesionado", "baja", "ausente",
        # Portuguese
        "lesão", "lesionado", "ausente", "fora",
        # Polish
        "kontuzja", "kontuzjowany", "nieobecny",
        # Turkish
        "sakatlık", "sakatlandı", "yok", "eksik",
        # German
        "verletzung", "verletzt", "fehlt", "ausfall",
        # French
        "blessure", "blessé", "absent", "forfait"
    ]
    
    SUSPENSION_KEYWORDS = [
        # English
        "suspended", "suspension", "ban", "banned", "red card", "sent off",
        # Italian
        "squalificato", "squalifica", "espulso",
        # Spanish
        "sancionado", "sanción", "expulsado",
        # Portuguese
        "suspenso", "suspensão", "expulso",
        # Polish
        "zawieszony", "zawieszenie", "czerwona kartka",
        # Turkish
        "cezalı", "ceza", "kırmızı kart",
        # German
        "gesperrt", "sperre", "rote karte",
        # French
        "suspendu", "suspension", "carton rouge"
    ]
    
    NATIONAL_TEAM_KEYWORDS = [
        # English
        "national team", "call-up", "called up", "international duty",
        # Italian
        "nazionale", "convocato", "convocazione",
        # Spanish
        "selección", "convocado", "convocatoria",
        # Portuguese
        "seleção", "convocado", "convocação",
        # Polish
        "reprezentacja", "powołany", "powołanie",
        # Turkish
        "milli takım", "davet", "çağrıldı",
        # German
        "nationalmannschaft", "nominiert", "länderspiel",
        # French
        "équipe nationale", "convoqué", "sélection"
    ]
    
    CUP_ABSENCE_KEYWORDS = [
        # English
        "cup", "cup tie", "cup match", "rested", "rotation",
        # Italian
        "coppa", "turno di riposo", "rotazione",
        # Spanish
        "copa", "descanso", "rotación",
        # Portuguese
        "taça", "copa", "descanso", "rodízio",
        # Polish
        "puchar", "odpoczynek", "rotacja",
        # Turkish
        "kupa", "dinlenme", "rotasyon",
        # German
        "pokal", "geschont", "rotation",
        # French
        "coupe", "repos", "rotation"
    ]
    
    # YOUTH CALLUP - Very relevant for betting!
    YOUTH_CALLUP_KEYWORDS = [
        # English
        "primavera", "u19", "u21", "u17", "u18", "u20", "u23",
        "youth", "academy", "youth player", "promoted", "called up from",
        "reserves", "b team", "under-19", "under-21", "under-17", "under-18", "under-20",
        "youth team", "reserve team", "second team",
        # Italian
        "giovanili", "convocato dalla primavera", "aggregato", "juniores",
        "settore giovanile", "allievi", "berretti",
        # Spanish
        "juvenil", "cantera", "filial", "promovido", "canterano",
        "equipo reserva", "segundo equipo", "fuerzas básicas",
        # Portuguese (Brazil)
        "juvenis", "base", "promovido", "sub-19", "sub-21", "sub-17", "sub-20",
        "categorias de base", "time b", "aspirantes",
        # Polish
        "młodzież", "rezerwy", "powołany z juniorów", "juniorzy",
        "drużyna rezerw", "młodzieżowiec",
        # Turkish
        "gençler", "altyapı", "a takıma çağrıldı", "genç oyuncu",
        "alt yapıdan", "u19", "u21",
        # German
        "jugend", "nachwuchs", "hochgezogen", "zweite mannschaft",
        "jugendmannschaft", "u19", "u21", "junioren", "amateure",
        # French
        "jeunes", "réserve", "promu", "espoirs", "équipe réserve",
        "centre de formation", "formé au club",
        # Greek
        "νέοι", "ακαδημία", "εφηβικό", "νεανικό", "κ19", "κ21",
        # Russian
        "молодёжь", "молодежка", "дубль", "резерв", "юноши",
        "молодёжная команда",
        # Danish
        "ungdom", "ungdomshold", "u19", "u21", "talenthold",
        "reservehold", "andethold",
        # Norwegian
        "ungdom", "ungdomslag", "juniorlag", "andrelag",
        "rekruttlag", "u19", "u21",
        # Swedish
        "ungdom", "ungdomslag", "juniorlag", "andralag",
        "u19", "u21", "akademi",
        # Dutch/Belgian
        "jeugd", "beloften", "jong", "reserven", "tweede elftal",
        "jeugdspeler", "doorgestroomd",
        # Ukrainian
        "молодь", "молодіжка", "дубль", "резерв", "юнаки",
        # Indonesian
        "pemuda", "junior", "tim cadangan", "akademi",
        # Arabic (Egyptian)
        "شباب", "ناشئين", "فريق الشباب"
    ]
    
    def __init__(self):
        """Initialize with compiled regex patterns for efficiency."""
        self._injury_pattern = self._compile_pattern(self.INJURY_KEYWORDS)
        self._suspension_pattern = self._compile_pattern(self.SUSPENSION_KEYWORDS)
        self._national_pattern = self._compile_pattern(self.NATIONAL_TEAM_KEYWORDS)
        self._cup_pattern = self._compile_pattern(self.CUP_ABSENCE_KEYWORDS)
        self._youth_pattern = self._compile_pattern(self.YOUTH_CALLUP_KEYWORDS)
    
    def _compile_pattern(self, keywords: List[str]) -> re.Pattern:
        """Compile keywords into case-insensitive regex pattern."""
        pattern = r'\b(' + '|'.join(re.escape(kw) for kw in keywords) + r')\b'
        return re.compile(pattern, re.IGNORECASE)
    
    def analyze(self, content: str) -> AnalysisResult:
        """
        Analyze content for betting relevance.
        
        Args:
            content: Text content to analyze
            
        Returns:
            AnalysisResult with is_relevant, category, team, confidence, summary
        """
        if not content:
            return AnalysisResult(
                is_relevant=False,
                category="OTHER",
                affected_team=None,
                confidence=0.0,
                summary="Empty content"
            )
        
        # Count keyword matches for each category
        injury_matches = len(self._injury_pattern.findall(content))
        suspension_matches = len(self._suspension_pattern.findall(content))
        national_matches = len(self._national_pattern.findall(content))
        cup_matches = len(self._cup_pattern.findall(content))
        youth_matches = len(self._youth_pattern.findall(content))
        
        total_matches = injury_matches + suspension_matches + national_matches + cup_matches + youth_matches
        
        if total_matches == 0:
            return AnalysisResult(
                is_relevant=False,
                category="OTHER",
                affected_team=None,
                confidence=0.1,
                summary="No relevance keywords found"
            )
        
        # Determine primary category based on highest match count
        max_matches = max(injury_matches, suspension_matches, national_matches, cup_matches, youth_matches)
        
        if injury_matches == max_matches:
            category = "INJURY"
        elif suspension_matches == max_matches:
            category = "SUSPENSION"
        elif national_matches == max_matches:
            category = "NATIONAL_TEAM"
        elif youth_matches == max_matches:
            category = "YOUTH_CALLUP"
        else:
            category = "CUP_ABSENCE"
        
        # Calculate confidence based on keyword density
        # More matches = higher confidence, capped at 0.85 (leave room for DeepSeek)
        confidence = min(0.3 + (total_matches * 0.1), 0.85)
        
        # Try to extract team name (simple heuristic)
        affected_team = self._extract_team_name(content)
        
        # Generate summary
        summary = self._generate_summary(content, category)
        
        return AnalysisResult(
            is_relevant=True,
            category=category,
            affected_team=affected_team,
            confidence=confidence,
            summary=summary
        )
    
    def _extract_team_name(self, content: str) -> Optional[str]:
        """
        Try to extract team name from content using heuristics.
        
        V1.3: Fixed pattern order - check known clubs FIRST to avoid false positives.
        """
        # Common words to exclude (articles, prepositions, etc.)
        excluded_words = {
            'the', 'at', 'for', 'from', 'with', 'and', 'but', 'or', 'in', 'on',
            'to', 'of', 'by', 'as', 'is', 'it', 'be', 'are', 'was', 'were',
            'has', 'have', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
            'face', 'play', 'beat', 'lose', 'win', 'draw', 'meet', 'host', 'visit',
            'martin', 'oxford', 'hugo', 'saka', 'kerkez',  # Common player names
            'glance', 'clear', 'points', 'match', 'game', 'news', 'sport',
            'football', 'soccer', 'live', 'update', 'breaking', 'report'
        }
        
        # Pattern 1 (PRIORITY): Known club names directly - most reliable
        known_clubs = [
            'Arsenal', 'Chelsea', 'Liverpool', 'Manchester United', 'Manchester City',
            'Tottenham', 'West Ham', 'Newcastle', 'Aston Villa', 'Brighton',
            'Bournemouth', 'Brentford', 'Crystal Palace', 'Everton', 'Fulham',
            'Nottingham Forest', 'Southampton', 'Wolves', 'Leicester', 'Leeds',
            'AC Milan', 'Inter Milan', 'Juventus', 'Roma', 'Napoli', 'Lazio', 'Atalanta', 'Fiorentina',
            'Real Madrid', 'Barcelona', 'Atletico Madrid', 'Sevilla', 'Valencia', 'Villarreal',
            'Bayern Munich', 'Borussia Dortmund', 'RB Leipzig', 'Bayer Leverkusen',
            'PSG', 'Paris Saint-Germain', 'Lyon', 'Marseille', 'Monaco', 'Lille',
            'Ajax', 'PSV', 'Feyenoord', 'Porto', 'Benfica', 'Sporting Lisbon',
            # Additional clubs
            'Bournemouth', 'Ipswich', 'Luton', 'Sheffield United', 'Burnley',
            'Galatasaray', 'Fenerbahce', 'Besiktas', 'Trabzonspor',
            'Celtic', 'Rangers', 'Olympiacos', 'Panathinaikos', 'AEK Athens',
            'Sporting CP', 'Braga', 'Vitoria Guimaraes',
            'Anderlecht', 'Club Brugge', 'Genk', 'Standard Liege',
        ]
        
        # Check known clubs first (case-insensitive)
        content_lower = content.lower()
        for club in known_clubs:
            if club.lower() in content_lower:
                return club
        
        # Pattern 2: "[Team] FC/United/City/etc." - for unknown clubs
        team_suffix_pattern = r'\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+(?:FC|United|City|Town|Athletic|Rovers|Wanderers|Albion|Hotspur|Villa|Palace|County|SC|CF|SV|BV)\b'
        match = re.search(team_suffix_pattern, content)
        if match:
            team = match.group(0).strip()
            first_word = team.split()[0].lower()
            if first_word not in excluded_words:
                return team
        
        # Pattern 3: "X's player/star/striker" - possessive form
        possessive_pattern = r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)'s\s+(?:player|star|striker|midfielder|defender|goalkeeper|manager|coach|boss)"
        match = re.search(possessive_pattern, content)
        if match:
            team = match.group(1).strip()
            if team.lower() not in excluded_words and len(team) > 2:
                return team
        
        return None
    
    def _generate_summary(self, content: str, category: str) -> str:
        """
        Generate a brief summary of the content.
        
        V1.3: Improved to handle content without traditional punctuation.
        Looks for sentences containing relevant keywords, with fallback to line-based splitting.
        """
        if not content:
            return "Contenuto non disponibile"
        
        # Clean content: remove excessive whitespace and normalize
        clean_content = ' '.join(content.split())
        
        # If content is too short, return as-is
        if len(clean_content) < 50:
            return clean_content if clean_content else "Notizia rilevata - verifica il link"
        
        # Keywords to look for based on category
        category_keywords = {
            'INJURY': ['injury', 'injured', 'out', 'miss', 'absent', 'sidelined', 'ruled out', 
                       'hamstring', 'knee', 'ankle', 'infortunio', 'lesión', 'blessure'],
            'SUSPENSION': ['suspended', 'suspension', 'ban', 'red card', 'squalifica', 'sanción', 'suspendu'],
            'NATIONAL_TEAM': ['national team', 'call-up', 'international', 'nazionale', 'selección', 'équipe nationale'],
            'CUP_ABSENCE': ['cup', 'rested', 'rotation', 'coppa', 'copa', 'coupe'],
            'YOUTH_CALLUP': ['youth', 'primavera', 'u19', 'u21', 'academy', 'giovanili', 'juvenil', 'jeunes'],
        }
        
        keywords = category_keywords.get(category, [])
        
        # Try multiple splitting strategies
        # Strategy 1: Traditional sentence splitting
        sentences = re.split(r'[.!?]\s+', clean_content)
        
        # Strategy 2: If only one "sentence", try splitting by newlines or common separators
        if len(sentences) <= 1:
            sentences = re.split(r'\n+|(?<=[a-z])\s+(?=[A-Z][a-z])', clean_content)
        
        # Find the most relevant segment
        best_segment = None
        best_score = 0
        
        for segment in sentences:
            segment = segment.strip()
            # Skip very short segments
            if len(segment) < 15:
                continue
            
            # Skip segments that look like navigation/menu items (all caps, too few words)
            word_count = segment.count(' ') + 1
            if word_count < 3:
                continue
            
            # Skip if it looks like a menu (Home News Sport Football Live...)
            if re.match(r'^[A-Z][a-z]+(\s+[A-Z][a-z]+){3,}$', segment):
                continue
            
            # Score based on keyword matches
            score = sum(1 for kw in keywords if kw.lower() in segment.lower())
            
            # Bonus for segments with team names
            if re.search(r'\b(Arsenal|Chelsea|Liverpool|Manchester|Tottenham|Newcastle|West Ham|'
                        r'Milan|Inter|Juventus|Roma|Napoli|Real Madrid|Barcelona|Bayern|'
                        r'PSG|Dortmund|Ajax|Porto|Benfica)\b', segment, re.IGNORECASE):
                score += 2
            
            # Bonus for segments that look like news headlines (contains verb-like patterns)
            if re.search(r'\b(miss|ruled out|injured|suspended|called up|promoted|out for|'
                        r'sidelined|absent|returns|doubtful|uncertain)\b', segment, re.IGNORECASE):
                score += 1
            
            if score > best_score:
                best_score = score
                best_segment = segment
        
        # If we found a good segment, use it
        if best_segment and best_score > 0:
            # Truncate if too long
            if len(best_segment) > 200:
                # Try to cut at word boundary
                truncated = best_segment[:197]
                last_space = truncated.rfind(' ')
                if last_space > 150:
                    best_segment = truncated[:last_space] + "..."
                else:
                    best_segment = truncated + "..."
            return best_segment
        
        # Fallback: find first reasonably long segment that's not navigation
        for segment in sentences:
            segment = segment.strip()
            word_count = segment.count(' ') + 1
            if 20 < len(segment) < 250 and word_count >= 4:
                # Skip obvious navigation patterns
                if not re.match(r'^[A-Z][a-z]+(\s+[A-Z][a-z]+){3,}$', segment):
                    if len(segment) > 200:
                        segment = segment[:197] + "..."
                    return segment
        
        # Last resort: cleaned content with smart truncation
        summary = clean_content[:200].strip()
        if len(clean_content) > 200:
            # Try to cut at word boundary
            last_space = summary.rfind(' ')
            if last_space > 150:
                summary = summary[:last_space] + "..."
            else:
                summary += "..."
        
        return summary if summary else "Notizia rilevata - verifica il link"


# Singleton instances for efficiency (patterns compiled once)
# V1.1: Thread-safe singleton with lock for multi-threaded environments
import threading

_exclusion_filter: Optional[ExclusionFilter] = None
_relevance_analyzer: Optional[RelevanceAnalyzer] = None
_positive_news_filter: Optional[PositiveNewsFilter] = None
_singleton_lock = threading.Lock()


def get_exclusion_filter() -> ExclusionFilter:
    """Get singleton ExclusionFilter instance (thread-safe)."""
    global _exclusion_filter
    if _exclusion_filter is None:
        with _singleton_lock:
            # Double-check locking pattern
            if _exclusion_filter is None:
                _exclusion_filter = ExclusionFilter()
    return _exclusion_filter


def get_relevance_analyzer() -> RelevanceAnalyzer:
    """Get singleton RelevanceAnalyzer instance (thread-safe)."""
    global _relevance_analyzer
    if _relevance_analyzer is None:
        with _singleton_lock:
            # Double-check locking pattern
            if _relevance_analyzer is None:
                _relevance_analyzer = RelevanceAnalyzer()
    return _relevance_analyzer


def get_positive_news_filter() -> PositiveNewsFilter:
    """Get singleton PositiveNewsFilter instance (thread-safe). V1.4"""
    global _positive_news_filter
    if _positive_news_filter is None:
        with _singleton_lock:
            # Double-check locking pattern
            if _positive_news_filter is None:
                _positive_news_filter = PositiveNewsFilter()
    return _positive_news_filter
