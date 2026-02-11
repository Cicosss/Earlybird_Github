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
        # ========== ENGLISH (Scotland, Australia) ==========
        "injury", "injured", "out", "ruled out", "miss", "absent", "sidelined",
        "hamstring", "knee", "ankle", "muscle", "strain", "sprain", "fracture",
        "team news", "fitness doubt", "recovery", "rehabilitation",
        
        # ========== ITALIAN ==========
        "infortunio", "infortunato", "assente", "fuori", "indisponibile",
        
        # ========== SPANISH (Argentina, Mexico) - V1.7 ==========
        "lesión", "lesiones", "lesionado", "lesionados", "lesionada", "lesionadas",
        "baja", "bajas", "ausente", "ausentes", "descarta", "descartado", "descartados",
        "fuera del partido", "no estará", "se perderá", "no jugará",
        "molestia", "molestias", "recuperación", "rehabilitación",
        
        # ========== PORTUGUESE (Brazil Serie B) - V1.7 ==========
        "lesão", "lesões", "lesionado", "lesionados", "ausente", "fora",
        "machucado", "machucados", "contundido", "contundidos",
        "desfalque", "desfalques", "baixa", "baixas",
        "problema físico", "dores", "tratamento",
        
        # ========== POLISH (Poland Ekstraklasa) - V1.7 ==========
        "kontuzja", "kontuzjowany", "kontuzjowani", "nieobecny", "nieobecni",
        "uraz", "urazy", "wypadł", "nie zagra",
        
        # ========== TURKISH (Turkey Super Lig) - V1.7 ==========
        "sakatlık", "sakatlandı", "sakatlar", "yok", "eksik", "eksikler",
        "tedavi", "toparlanıyor", "oynamayacak", "kadroda yok",
        
        # ========== GREEK (Greece Super League) - V1.7 ==========
        "τραυματίας", "τραυματίες", "τραυματισμός", "απουσία", "απουσίες",
        "εκτός", "αποθεραπεία", "δεν παίζει", "χάνει το ματς",
        
        # ========== GERMAN (Austria Bundesliga) - V1.7 ==========
        "verletzung", "verletzt", "verletzte", "fehlt", "ausfall", "ausfälle",
        "muskelverletzung", "knieverletzung", "reha", "pausiert",
        
        # ========== FRENCH (France, Belgium) - V1.7 ==========
        "blessure", "blessé", "blessés", "absent", "absents", "forfait",
        "indisponible", "incertain", "touché", "pépins physiques",
        
        # ========== DUTCH (Netherlands, Belgium) - V1.7 ==========
        "blessure", "geblesseerd", "geblesseerden", "afwezig", "mist",
        "herstel", "uitgevallen", "niet fit", "twijfelgeval",
        
        # ========== NORWEGIAN (Norway Eliteserien) - V1.7 ==========
        "skade", "skadet", "skadde", "ute", "mister", "borte",
        "rekonvalesens", "ikke klar", "usikker",
        
        # ========== JAPANESE (J-League) - V1.7 ==========
        "怪我", "負傷", "欠場", "離脱", "治療中", "欠席", "出場停止",
        "ケガ", "故障", "リハビリ",
        
        # ========== CHINESE (China Super League) - V1.7 ==========
        "伤病", "受伤", "缺阵", "伤停", "伤愈", "养伤", "伤势",
    ]
    
    SUSPENSION_KEYWORDS = [
        # ========== ENGLISH ==========
        "suspended", "suspension", "ban", "banned", "red card", "sent off",
        "serving suspension", "yellow card accumulation",
        
        # ========== ITALIAN ==========
        "squalificato", "squalifica", "espulso",
        
        # ========== SPANISH (Argentina, Mexico) ==========
        "sancionado", "sanción", "expulsado", "tarjeta roja", "suspendido",
        "acumulación de amarillas", "vio la roja",
        
        # ========== PORTUGUESE (Brazil) ==========
        "suspenso", "suspensão", "expulso", "cartão vermelho",
        "pendurado", "gancho",
        
        # ========== POLISH ==========
        "zawieszony", "zawieszenie", "czerwona kartka", "pauzuje za kartki",
        
        # ========== TURKISH ==========
        "cezalı", "ceza", "kırmızı kart", "ihraç", "men cezası",
        
        # ========== GREEK - V1.7 ==========
        "τιμωρία", "αποβολή", "κόκκινη κάρτα", "τιμωρημένος",
        
        # ========== GERMAN (Austria) ==========
        "gesperrt", "sperre", "rote karte", "gelbsperre",
        
        # ========== FRENCH (France, Belgium) ==========
        "suspendu", "suspension", "carton rouge", "expulsé",
        
        # ========== DUTCH (Netherlands, Belgium) - V1.7 ==========
        "geschorst", "schorsing", "rode kaart", "gele kaart",
        
        # ========== NORWEGIAN - V1.7 ==========
        "utestengt", "suspensjon", "rødt kort", "karantene",
        
        # ========== JAPANESE - V1.7 ==========
        "出場停止", "退場", "累積警告", "レッドカード",
        
        # ========== CHINESE - V1.7 ==========
        "停赛", "红牌", "禁赛", "累计黄牌",
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
    
    # GENERAL SPORTS KEYWORDS - V1.9: For PT/ES content without injury keywords
    # These keywords indicate sports relevance and help identify betting-relevant content
    # when team names are present but no specific injury/suspension keywords
    GENERAL_SPORTS_KEYWORDS = [
        # Portuguese
        "sucesso", "determinantes", "temporada", "campeonato", "vitória",
        "derrota", "título", "campeão", "partida", "jogo", "competição",
        "liga", "classificação", "desempenho", "estratégia", "preparação",
        "objetivo", "campeonato", "futebol", "equipe", "clube",
        "vence", "venceu", "perde", "perdeu", "empata", "empatou",
        "enfrenta", "enfrentou", "joga", "jogou", "recebe", "recebeu",
        "visita", "visitou", "derrota", "derrotou", "goleia", "goleou",
        "bate", "bateu", "supera", "superou", "elimina", "eliminou",
        # Spanish
        "éxito", "determinantes", "temporada", "campeonato", "victoria",
        "derrota", "título", "campeón", "partido", "juego", "competición",
        "liga", "clasificación", "rendimiento", "estrategia", "preparación",
        "objetivo", "fútbol", "equipo", "club",
        "vence", "venció", "pierde", "perdió", "empata", "empató",
        "enfrenta", "enfrentó", "juega", "jugó", "recibe", "recibió",
        "visita", "visitó", "derrota", "derrotó", "golea", "goleó",
        "bate", "bató", "supera", "superó", "elimina", "eliminó",
    ]
    
    def __init__(self):
        """Initialize with compiled regex patterns for efficiency."""
        self._injury_pattern = self._compile_pattern(self.INJURY_KEYWORDS)
        self._suspension_pattern = self._compile_pattern(self.SUSPENSION_KEYWORDS)
        self._national_pattern = self._compile_pattern(self.NATIONAL_TEAM_KEYWORDS)
        self._cup_pattern = self._compile_pattern(self.CUP_ABSENCE_KEYWORDS)
        self._youth_pattern = self._compile_pattern(self.YOUTH_CALLUP_KEYWORDS)
        self._general_sports_pattern = self._compile_pattern(self.GENERAL_SPORTS_KEYWORDS)
    
    def _compile_pattern(self, keywords: List[str]) -> re.Pattern:
        """
        Compile keywords into case-insensitive regex pattern.
        
        V1.7: Smart handling for CJK (Chinese/Japanese) which don't use word boundaries (\\b).
        Separates keywords into boundary-enforced and boundary-free groups.
        
        V1.8: Extended to include Greek characters which also don't use word boundaries.
        """
        boundary_kw = []
        no_boundary_kw = []
        
        # Helper to detect non-Latin characters (CJK, Greek, Cyrillic)
        # These scripts don't use word boundaries the same way as Latin
        # Using Unicode ranges for common non-Latin blocks
        def is_non_latin(s):
            return any(
                '\u4e00' <= c <= '\u9fff' or  # CJK Unified Ideographs (Chinese, Japanese Kanji)
                '\u3040' <= c <= '\u30ff' or  # Hiragana and Katakana (Japanese)
                '\u0370' <= c <= '\u03FF' or  # Greek and Coptic
                '\u0400' <= c <= '\u04FF'      # Cyrillic (for future expansion)
                for c in s
            )
            
        for kw in keywords:
            if is_non_latin(kw):
                no_boundary_kw.append(re.escape(kw))
            else:
                boundary_kw.append(re.escape(kw))
        
        parts = []
        if boundary_kw:
            # Traditional word boundary logic for Latin/Cyrillic/Greek
            parts.append(r'\b(?:' + '|'.join(boundary_kw) + r')\b')
        if no_boundary_kw:
            # No boundaries for non-Latin scripts (CJK, Greek, Cyrillic)
            parts.append(r'(?:' + '|'.join(no_boundary_kw) + r')')
            
        if not parts:
            # Fallback pattern that matches nothing
            # Changed to a pattern that never matches instead of '(?!x)x' which is broken
            return re.compile(r'(?!a)a')
            
        pattern = '|'.join(parts)
        return re.compile(pattern, re.IGNORECASE)
    
    def analyze(self, content: str) -> AnalysisResult:
        """
        Analyze content for betting relevance.
        
        V1.9: Enhanced to consider team extraction as relevance factor for PT/ES content.
        When a known team name is extracted, content is considered relevant even without
        injury/suspension keywords, especially when general sports keywords are present.
        
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
        general_sports_matches = len(self._general_sports_pattern.findall(content))
        
        # V1.9: Try to extract team name BEFORE checking relevance
        # This allows us to use team extraction as a relevance factor
        affected_team = self._extract_team_name(content)
        
        total_matches = injury_matches + suspension_matches + national_matches + cup_matches + youth_matches
        
        # V1.9: If no injury/suspension keywords but team name is found,
        # check for general sports keywords (PT/ES relevance)
        if total_matches == 0:
            if affected_team and general_sports_matches > 0:
                # Content has team name + general sports keywords = relevant
                # Use lower confidence since no specific injury/suspension info
                confidence = min(0.3 + (general_sports_matches * 0.05), 0.5)
                summary = self._generate_summary(content, "OTHER")
                return AnalysisResult(
                    is_relevant=True,
                    category="OTHER",
                    affected_team=affected_team,
                    confidence=confidence,
                    summary=summary
                )
            # No team name or no general sports keywords = not relevant
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
        
        # V1.9: Boost confidence when team name is extracted
        # This helps prioritize content with identifiable teams
        if affected_team:
            confidence = min(confidence + 0.1, 0.85)
        
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
        V1.6: Added Brazilian, Argentine, Honduran and other South American clubs
              for multi-language support (Portuguese/Spanish articles).
        V1.10: Added validation to ensure extracted team is in known clubs list
        """
        # DEBUG: Log content for debugging
        logger.debug(f"[TEAM-EXTRACTION] Analyzing content: {content[:100]}...")
        
        # Common words to exclude (articles, prepositions, etc.)
        excluded_words = {
            'the', 'at', 'for', 'from', 'with', 'and', 'but', 'or', 'in', 'on',
            'to', 'of', 'by', 'as', 'is', 'it', 'be', 'are', 'was', 'were',
            'has', 'have', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
            'face', 'play', 'beat', 'lose', 'win', 'draw', 'meet', 'host', 'visit',
            'martin', 'oxford', 'hugo', 'saka', 'kerkez',  # Common player names
            'glance', 'clear', 'points', 'match', 'game', 'news', 'sport',
            'football', 'soccer', 'live', 'update', 'breaking', 'report',
            # Portuguese/Spanish common words
            'para', 'com', 'por', 'sem', 'mais', 'como', 'sobre', 'entre',
            'jogo', 'partida', 'resultado', 'gol', 'time', 'clube',
            'sucesso', 'vitória', 'derrota', 'empate', 'campeonato',
        }
        
        # Pattern 1 (PRIORITY): Known club names directly - most reliable
        known_clubs = [
            # ========== ENGLAND - Premier League ==========
            'Arsenal', 'Chelsea', 'Liverpool', 'Manchester United', 'Manchester City',
            'Tottenham', 'West Ham', 'Newcastle', 'Aston Villa', 'Brighton',
            'Bournemouth', 'Brentford', 'Crystal Palace', 'Everton', 'Fulham',
            'Nottingham Forest', 'Southampton', 'Wolves', 'Leicester', 'Leeds',
            'Ipswich', 'Luton', 'Sheffield United', 'Burnley',
            # National League
            'Chesterfield',
            # Championship
            'Wigan Athletic',
            
            # ========== ITALY - Serie A ==========
            'AC Milan', 'Inter Milan', 'Juventus', 'Roma', 'Napoli', 'Lazio', 
            'Atalanta', 'Fiorentina',
            
            # ========== SPAIN - La Liga ==========
            'Real Madrid', 'Barcelona', 'Atletico Madrid', 'Sevilla', 'Valencia', 
            'Villarreal',
            
            # ========== GERMANY - Bundesliga ==========
            'Bayern Munich', 'Borussia Dortmund', 'RB Leipzig', 'Bayer Leverkusen',
            
            # ========== FRANCE - Ligue 1 ==========
            'PSG', 'Paris Saint-Germain', 'Lyon', 'Marseille', 'Monaco', 'Lille',
            
            # ========== NETHERLANDS - Eredivisie (V1.7 Tier 2) ==========
            'Ajax', 'PSV', 'PSV Eindhoven', 'Feyenoord', 'AZ Alkmaar', 'AZ',
            'FC Twente', 'Twente', 'FC Utrecht', 'Utrecht', 'Vitesse',
            'SC Heerenveen', 'Heerenveen', 'Sparta Rotterdam', 'Sparta',
            'Go Ahead Eagles', 'Fortuna Sittard', 'RKC Waalwijk', 'NEC Nijmegen',
            'PEC Zwolle', 'Excelsior', 'Heracles Almelo', 'FC Volendam',
            
            # ========== PORTUGAL ==========
            'Porto', 'Benfica', 'Sporting Lisbon', 'Sporting CP', 'Braga',
            'Vitoria Guimaraes', 'Rio Ave', 'Boavista', 'Maritimo',
            
            # ========== TURKEY - Süper Lig (V1.7 Elite 7) ==========
            'Galatasaray', 'Fenerbahce', 'Fenerbahçe', 'Besiktas', 'Beşiktaş',
            'Trabzonspor', 'Basaksehir', 'Başakşehir', 'Istanbul Basaksehir',
            'Antalyaspor', 'Konyaspor', 'Kasimpasa', 'Kasımpaşa', 'Sivasspor',
            'Alanyaspor', 'Kayserispor', 'Adana Demirspor', 'Gaziantep FK',
            'Rizespor', 'Çaykur Rizespor', 'Hatayspor', 'Samsunspor',
            'Pendikspor', 'Istanbulspor', 'Fatih Karagümrük', 'Ankaragücü',
            
            # ========== GREECE - Super League (V1.7 Elite 7) ==========
            'Olympiacos', 'Olympiakos', 'Ολυμπιακός', 
            'Panathinaikos', 'Παναθηναϊκός', 
            'AEK Athens', 'AEK', 'ΑΕΚ', 
            'PAOK', 'PAOK Thessaloniki', 'ΠΑΟΚ', 
            'Aris Thessaloniki', 'Aris', 'Άρης', 
            'Panetolikos', 'Παναιτωλικός', 
            'Asteras Tripolis', 'Αστέρας Τρίπολης', 
            'Atromitos', 'Ατρόμητος', 
            'OFI Crete', 'ΟΦΗ', 
            'Volos', 'Volos NFC', 'Βόλος', 
            'Lamia', 'Λαμία', 
            'Ionikos', 'Ιωνικός', 
            'Giannina', 'PAS Giannina', 'ΠΑΣ Γιάννινα', 
            'Levadiakos', 'Λεβαδειακός',
            
            # ========== SCOTLAND - Premiership (V1.7 Elite 7) ==========
            'Celtic', 'Rangers', 'Aberdeen', 'Hearts', 'Heart of Midlothian',
            'Hibernian', 'Hibs', 'Dundee', 'Dundee United', 'Kilmarnock',
            'Motherwell', 'Ross County', 'Livingston', 'St Mirren',
            'St Johnstone', 'Partick Thistle', 'Dundee FC',
            
            # ========== BELGIUM - First Division (V1.7 Tier 2) ==========
            'Anderlecht', 'Club Brugge', 'Club Bruges', 'Genk', 'KRC Genk',
            'Standard Liege', 'Standard Liège', 'Antwerp', 'Royal Antwerp',
            'Gent', 'KAA Gent', 'Union Saint-Gilloise', 'Union SG', 'Cercle Brugge',
            'Mechelen', 'KV Mechelen', 'Charleroi', 'Kortrijk', 'Sint-Truiden',
            'Westerlo', 'OH Leuven', 'Eupen', 'RWD Molenbeek',
            
            # ========== BRAZIL - Brasileirão (V1.6) ==========
            # Série A - Top 20
            'Flamengo', 'Palmeiras', 'Corinthians', 'São Paulo', 'Sao Paulo',
            'Santos', 'Fluminense', 'Botafogo', 'Vasco', 'Vasco da Gama',
            'Athletico Paranaense', 'Athletico-PR', 'Grêmio', 'Gremio',
            'Internacional', 'Inter de Porto Alegre', 'Cruzeiro', 'Atlético Mineiro',
            'Atletico Mineiro', 'Atlético-MG', 'Bahia', 'Fortaleza', 'Ceará', 'Ceara',
            'Sport Recife', 'Vitória', 'Vitoria', 'Juventude', 'América Mineiro',
            'America Mineiro', 'Cuiabá', 'Cuiaba', 'Red Bull Bragantino', 'Bragantino',
            'Coritiba', 'Goiás', 'Goias', 'Avaí', 'Avai', 'Chapecoense',
            # Série B (V1.7 Tier 2)
            'Guarani', 'Ponte Preta', 'Novorizontino', 'Mirassol', 'Vila Nova',
            'CRB', 'CSA', 'Sport', 'Náutico', 'Santa Cruz', 'ABC', 'Londrina',
            'Operário', 'Brusque', 'Ituano', 'Sampaio Corrêa',
            # Common shortened names (used in media)
            'Mengão', 'Mengao', 'Timão', 'Timao', 'Tricolor', 'Colorado',
            'Verdão', 'Verdao', 'Peixe', 'Fogão', 'Fogao', 'Galo',
            
            # ========== ARGENTINA - Primera División (V1.6 Elite 7) ==========
            'River Plate', 'Boca Juniors', 'Racing Club', 'Independiente',
            'San Lorenzo', 'Estudiantes', 'Vélez Sarsfield', 'Velez Sarsfield',
            'Lanús', 'Lanus', 'Rosario Central', "Newell's Old Boys", 'Newells',
            'Talleres', 'Argentinos Juniors', 'Defensa y Justicia', 'Banfield',
            'Godoy Cruz', 'Huracán', 'Huracan', 'Tigre', 'Colón', 'Colon',
            'Unión', 'Union', 'Central Córdoba', 'Platense', 'Sarmiento',
            
            # ========== MEXICO - Liga MX (V1.6 Elite 7) ==========
            'Club América', 'Club America', 'Chivas', 'Guadalajara', 'Cruz Azul',
            'Pumas', 'UNAM', 'Tigres', 'Monterrey', 'Rayados', 'Santos Laguna',
            'León', 'Leon', 'Toluca', 'Pachuca', 'Atlas', 'Tijuana', 'Xolos',
            'Necaxa', 'Puebla', 'Querétaro', 'Queretaro', 'Mazatlán', 'Mazatlan',
            'Juárez', 'FC Juarez', 'San Luis', 'Atlético San Luis',
            
            # ========== POLAND - Ekstraklasa (V1.7 Elite 7) ==========
            'Legia Warsaw', 'Legia Warszawa', 'Lech Poznan', 'Lech Poznań',
            'Raków Częstochowa', 'Rakow', 'Jagiellonia Białystok', 'Jagiellonia',
            'Pogoń Szczecin', 'Pogon', 'Górnik Zabrze', 'Gornik Zabrze',
            'Śląsk Wrocław', 'Slask Wroclaw', 'Cracovia', 'Wisła Kraków', 'Wisla Krakow',
            'Piast Gliwice', 'Warta Poznań', 'Korona Kielce', 'Zagłębie Lubin',
            'Radomiak', 'Stal Mielec', 'Widzew Łódź', 'Widzew Lodz', 'Puszcza Niepołomice',
            
            # ========== AUSTRALIA - A-League (V1.7 Elite 7) ==========
            'Melbourne Victory', 'Sydney FC', 'Western Sydney Wanderers', 'WSW',
            'Melbourne City', 'Brisbane Roar', 'Adelaide United', 'Perth Glory',
            'Central Coast Mariners', 'Mariners', 'Wellington Phoenix', 'Macarthur FC',
            'Western United', 'Newcastle Jets', 'Auckland FC',
            
            # ========== NORWAY - Eliteserien (V1.7 Tier 2) ==========
            'Bodø/Glimt', 'Bodo Glimt', 'Molde', 'Rosenborg', 'Viking',
            'Brann', 'Strømsgodset', 'Stromsgodset', 'Lillestrøm', 'Lillestrom',
            'Sarpsborg', 'Tromsø', 'Tromso', 'Odd', 'Vålerenga', 'Valerenga',
            'Haugesund', 'HamKam', 'Sandefjord', 'Kristiansund', 'Aalesund',
            
            # ========== FRANCE - Ligue 1 (V1.7 Tier 2) ==========
            'PSG', 'Paris Saint-Germain', 'Lyon', 'Olympique Lyon', 'OL',
            'Marseille', 'Olympique Marseille', 'OM', 'Monaco', 'AS Monaco',
            'Lille', 'LOSC', 'Nice', 'OGC Nice', 'Lens', 'RC Lens',
            'Rennes', 'Stade Rennais', 'Nantes', 'FC Nantes', 'Montpellier',
            'Strasbourg', 'RC Strasbourg', 'Brest', 'Stade Brestois',
            'Toulouse', 'Reims', 'Stade de Reims', 'Lorient', 'Le Havre',
            'Clermont', 'Metz', 'Auxerre',
            
            # ========== AUSTRIA - Bundesliga (V1.7 Tier 2) ==========
            'Red Bull Salzburg', 'Salzburg', 'Sturm Graz', 'SK Sturm',
            'Rapid Wien', 'Rapid Vienna', 'Austria Wien', 'Austria Vienna',
            'LASK', 'LASK Linz', 'Wolfsberg', 'WAC', 'Hartberg', 'TSV Hartberg',
            'Altach', 'SCR Altach', 'Rheindorf Altach', 'Austria Klagenfurt',
            'WSG Tirol', 'Blau-Weiß Linz', 'Austria Lustenau',
            
            # ========== CHINA - Super League (V1.7 Tier 2) ==========
            'Shanghai Port', 'Shanghai SIPG', '上海海港',
            'Shanghai Shenhua', '上海申花',
            'Shandong Taishan', '山东泰山',
            'Beijing Guoan', '北京国安',
            'Guangzhou FC', 'Guangzhou Evergrande', '广州队',
            'Henan Songshan', '河南嵩山龙门',
            'Wuhan Three Towns', '武汉三镇',
            'Chengdu Rongcheng', '成都蓉城',
            'Qingdao Hainiu', '青岛海牛',
            'Tianjin Jinmen Tiger', '天津津门虎',
            'Zhejiang FC', '浙江队',
            'Changchun Yatai', '长春亚泰',
            'Cangzhou Mighty Lions', '沧州雄狮',
            'Dalian Pro', '大连人',
            'Nantong Zhiyun', '南通支云',
            'Shenzhen FC', '深圳队',
            
            # ========== JAPAN - J-League (V1.7 Tier 2) ==========
            'Vissel Kobe', 'ヴィッセル神戸',
            'Yokohama F Marinos', 'Marinos', '横浜F・マリノス',
            'Kawasaki Frontale', '川崎フロンターレ',
            'Urawa Reds', 'Urawa Red Diamonds', '浦和レッズ',
            'FC Tokyo', 'FC東京',
            'Kashima Antlers', '鹿島アントラーズ',
            'Nagoya Grampus', '名古屋グランパス',
            'Cerezo Osaka', 'セレッソ大阪',
            'Gamba Osaka', 'ガンバ大阪',
            'Sanfrecce Hiroshima', 'サンフレッチェ広島',
            'Kashiwa Reysol', '柏レイソル',
            'Consadole Sapporo', '北海道コンサドーレ札幌',
            'Sagan Tosu', 'サガン鳥栖',
            'Avispa Fukuoka', 'アビスパ福岡',
            'Albirex Niigata', 'アルビレックス新潟',
            'Shonan Bellmare', '湘南ベルマーレ',
            'Kyoto Sanga', '京都サンガ',
            'Jubilo Iwata', 'ジュビロ磐田',
            'Tokyo Verdy', '東京ヴェルディ',
            'Machida Zelvia', '町田ゼルビア',
            
            # ========== HONDURAS - Liga Nacional (V1.6) ==========
            'Olimpia Honduras', 'Motagua', 'Real España', 'Real Espana',
            'Marathón', 'Marathon', 'Victoria Honduras', 'UPNFM', 'Honduras Progreso',
            'Vida', 'Real Sociedad Honduras', 'Platense Honduras', 'Lobos UPNFM',
            'Olancho FC', 'Génesis', 'Genesis',
            
            # ========== COLOMBIA/CHILE/PERU (V1.6) ==========
            # Colombia
            'Atlético Nacional', 'Atletico Nacional', 'Millonarios', 'América de Cali',
            'America de Cali', 'Independiente Medellín', 'Junior Barranquilla',
            'Deportivo Cali', 'Santa Fe', 'Once Caldas',
            # Chile
            'Colo-Colo', 'Colo Colo', 'Universidad de Chile', 'Universidad Católica',
            'Cobreloa', "O'Higgins", 'Huachipato',
            # Peru
            'Alianza Lima', 'Universitario', 'Sporting Cristal', 'Cienciano',
            'Melgar', 'Deportivo Municipal',
            
            # ========== INDONESIA (V1.6) ==========
            'Persija Jakarta', 'Persebaya', 'Arema FC', 'Persib Bandung',
            'Bali United', 'PSM Makassar', 'Persik Kediri', 'PSIS Semarang',
            'Madura United', 'Borneo FC', 'Persita Tangerang', 'Dewa United',
        ]
        
        # DEBUG: Check if we have CJK clubs in list and if content matches
        # Check known clubs first (case-insensitive) with word boundaries
        content_lower = content.lower()
        for club in known_clubs:
            # V1.10: Use word boundary matching to prevent partial matches
            # e.g., prevent "OL" from matching "Olimpia"
            pattern = r'\b' + re.escape(club.lower()) + r'\b'
            if re.search(pattern, content_lower):
                logger.debug(f"[TEAM-EXTRACTION] Known club matched: {club}")
                return club
        
        logger.debug(f"[TEAM-EXTRACTION] No known club match, trying patterns...")
        
        # Pattern 2: "[Team] FC/United/City/etc." - for unknown clubs (European + Americas)
        # V1.6: Added South American suffixes: EC, SE, CR, CA, AC, AP
        team_suffix_pattern = r'\b([A-Z][a-zA-ZÀ-ÿ]+(?:\s+[A-Z][a-zA-ZÀ-ÿ]+)?)\s+(?:FC|United|City|Town|Athletic|Rovers|Wanderers|Albion|Hotspur|Villa|Palace|County|SC|CF|SV|BV|EC|SE|CR|CA|AC|AP|Futebol Clube|Esporte Clube|Sport Club)\b'
        match = re.search(team_suffix_pattern, content)
        if match:
            team = match.group(0).strip()
            first_word = team.split()[0].lower()
            if first_word not in excluded_words:
                # V1.10: Validate team is in known clubs list
                if team in known_clubs or any(team.lower() == kc.lower() for kc in known_clubs):
                    return team
        
        # Pattern 3: "X's player/star/striker" - possessive form (English)
        possessive_pattern = r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)'s\s+(?:player|star|striker|midfielder|defender|goalkeeper|manager|coach|boss)"
        match = re.search(possessive_pattern, content)
        if match:
            team = match.group(1).strip()
            if team.lower() not in excluded_words and len(team) > 2:
                # V1.10: Validate team is in known clubs list
                if team in known_clubs or any(team.lower() == kc.lower() for kc in known_clubs):
                    return team
        
        # Pattern 4 (V1.8): Portuguese/Spanish possessive - "jogador do [Team]" / "jugador del [Team]"
        # V1.8: Added Brazilian variants: lateral, volante, puntero, centroavante
        pt_es_pattern = r'\b(?:jogador|atacante|zagueiro|goleiro|meia|lateral|volante|puntero|centroavante|técnico|treinador|jugador|delantero|defensor|portero|entrenador|DT)\s+(?:do|da|de|del|de la|de los|el|la)\s+([A-Z][a-zA-ZÀ-ÿ]+(?:\s+[A-Z][a-zA-ZÀ-ÿ]+){0,2})'
        match = re.search(pt_es_pattern, content)
        if match:
            team = match.group(1).strip()
            if team.lower() not in excluded_words and len(team) > 2:
                # V1.10: Validate team is in known clubs list
                if team in known_clubs or any(team.lower() == kc.lower() for kc in known_clubs):
                    return team
        
        # Pattern 5 (V1.8): Common Brazilian news patterns - "[Team] vence/perde/enfrenta"
        # V1.8: Support multi-word team names (e.g., "São Paulo vence")
        # V1.8: Added past tense variants (venceu, perdeu, empatou, etc.)
        br_action_pattern = r'\b([A-Z][a-zA-ZÀ-ÿ]+(?:\s+[A-Z][a-zA-ZÀ-ÿ]+){0,2})\s+(?:vence|perde|empata|enfrenta|joga|recebe|visita|derrota|goleia|bate|supera|elimina|venceu|perdeu|empatou|enfrentou|jogou|recebeu|visitou|derrotou|goleou|bateu|superou|eliminou)\b'
        match = re.search(br_action_pattern, content)
        if match:
            team = match.group(1).strip()
            if team.lower() not in excluded_words and len(team) > 3:
                # V1.10: Validate team is in known clubs list
                if team in known_clubs or any(team.lower() == kc.lower() for kc in known_clubs):
                    return team
        
        # Pattern 6 (V1.8): CJK team names (Chinese/Japanese)
        # Match CJK team names without word boundaries
        # CJK characters don't use word boundaries like Latin scripts
        cjk_team_pattern = r'([\u4e00-\u9fff\u3040-\u30ff]+(?:\s+[\u4e00-\u9fff\u3040-\u30ff]+)*)'
        match = re.search(cjk_team_pattern, content)
        if match:
            team = match.group(1).strip()
            # Verify it's a known CJK team to avoid false positives
            cjk_teams = [c for c in known_clubs if any('\u4e00' <= ch <= '\u9fff' or '\u3040' <= ch <= '\u30ff' for ch in c)]
            if team in cjk_teams:
                return team
        
        # Pattern 7 (V1.8): Greek team names
        # Match Greek team names without word boundaries
        # Greek characters don't use word boundaries like Latin scripts
        greek_team_pattern = r'([\u0370-\u03FF]+(?:\s+[\u0370-\u03FF]+)*)'
        match = re.search(greek_team_pattern, content)
        if match:
            team = match.group(1).strip()
            # Verify it's a known Greek team to avoid false positives
            greek_teams = [c for c in known_clubs if any('\u0370' <= ch <= '\u03FF' for ch in c)]
            if team in greek_teams:
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
        # V1.6: Expanded with Portuguese/Spanish keywords for South American sources
        # Keywords to look for based on category
        # V1.7: Use centralized keywords lists for multi-language support (Greek, CJK, etc.)
        # V1.8: Fixed critical bug - changed self.CUP_KEYWORDS to self.CUP_ABSENCE_KEYWORDS
        category_keywords = {
            'INJURY': self.INJURY_KEYWORDS,
            'SUSPENSION': self.SUSPENSION_KEYWORDS,
            'NATIONAL_TEAM': self.NATIONAL_TEAM_KEYWORDS,
            'CUP_ABSENCE': self.CUP_ABSENCE_KEYWORDS,
            'YOUTH_CALLUP': self.YOUTH_CALLUP_KEYWORDS,
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
            
            # Bonus for segments with team names (European + South American)
            # V1.6: Added Brazilian, Argentine, and other South American clubs
            if re.search(r'\b(Arsenal|Chelsea|Liverpool|Manchester|Tottenham|Newcastle|West Ham|'
                        r'Milan|Inter|Juventus|Roma|Napoli|Real Madrid|Barcelona|Bayern|'
                        r'PSG|Dortmund|Ajax|Porto|Benfica|'
                        r'Flamengo|Palmeiras|Corinthians|São Paulo|Sao Paulo|Santos|Fluminense|Botafogo|'
                        r'Vasco|Grêmio|Gremio|Internacional|Cruzeiro|Atlético Mineiro|Atletico Mineiro|'
                        r'River Plate|Boca Juniors|Racing|Independiente|San Lorenzo|'
                        r'Olimpia|Motagua|Real España|Real Espana|Marathón|Marathon)\b', segment, re.IGNORECASE):
                score += 2
            
            # Bonus for segments that look like news headlines (contains verb-like patterns)
            # V1.6: Added Portuguese/Spanish verb patterns
            if re.search(r'\b(miss|ruled out|injured|suspended|called up|promoted|out for|'
                        r'sidelined|absent|returns|doubtful|uncertain|'
                        r'lesionado|machucado|suspenso|convocado|ausente|fora|contundido|'
                        r'desfalque|operação|cirurgia|recuperação|tratamento|'
                        r'baja|sancionado|expulsado|fuera|lesión)\b', segment, re.IGNORECASE):
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
