"""
EarlyBird Alpha Hunter - News-Driven Intelligence Loop (V12.0)
================================================================

This module implements the PARADIGM SHIFT from "Fixture-Driven" to "News-Driven" architecture.

OLD PARADIGM (Fixture-Driven):
1. Download ALL upcoming matches from Odds-API
2. For each match, search for news team-by-team
3. Analyze matches with news

NEW PARADIGM (News-Driven - "Alpha Hunter"):
1. Broad Discovery: Monitor news_sources with TRIGGER KEYWORDS (not team names)
2. Entity Extraction: When relevant article found, extract TEAM NAME
3. On-Demand Odds: Query Odds-API ONLY for that specific team
4. Save & Analyze: If match found, save to DB and pass to AnalysisEngine

BENEFITS:
- 99% reduction in Odds-API consumption (only fetch when signal confirmed)
- True "Alpha Hunter" - finds signals BEFORE matches are even on the radar
- More efficient - only analyzes matches with confirmed signals

Author: Lead Architect
Date: 2026-03-27
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from config.settings import (
    ALPHA_HUNTER_AI_FALLBACK_ENABLED,
    ALPHA_HUNTER_MIN_CONFIDENCE,
    MATCH_LOOKAHEAD_HOURS,
)
from src.database.models import Match, SessionLocal, TeamAlias
from src.version import get_version_with_module

logger = logging.getLogger(__name__)
logger.info(f"📦 {get_version_with_module('Alpha Hunter')}")

# ============================================
# TRIGGER KEYWORDS BY LANGUAGE
# ============================================
# Generic keywords that indicate betting-relevant news
# These are searched on news domains WITHOUT team names

TRIGGER_KEYWORDS = {
    # Injury-related (highest priority)
    "injury": [
        "lesión",
        "lesiones",  # Spanish
        "lesão",
        "lesões",  # Portuguese
        "blessure",
        "blessures",  # French
        "verletzung",
        "verletzungen",  # German
        "infortunio",
        "infortuni",  # Italian
        "kontuzja",
        "kontuzji",  # Polish
        "sakatlık",
        "sakatlıklar",  # Turkish
        "injury",
        "injured",
        "injuries",  # English
        "إصابة",  # Arabic
    ],
    # Squad/Lineup news
    "squad": [
        "convocados",
        "convocatoria",  # Spanish
        "escalação",
        "convocados",  # Portuguese
        "squad",
        "formazione",
        "kadro",  # Italian/Turkish
        "lineup",
        "starting xi",
        "once",  # English
        "skład",
        "składem",  # Polish
    ],
    # Absences/Out
    "absence": [
        "baja",
        "bajas",  # Spanish
        "desfalque",
        "desfalques",  # Portuguese
        "absent",
        "absence",
        "out",  # English
        "assente",
        "assenti",  # Italian
        "eksik",
        "yok",  # Turkish
        "nieobecny",
        "brak",  # Polish
    ],
    # Suspensions
    "suspension": [
        "suspended",
        "suspension",
        "sospeso",
        "squalificato",
        "suspendido",
        "expulsado",
    ],
    # Transfer/Market
    "transfer": [
        "transfer",
        "signing",
        "loan",
        "fichaje",
        "contratación",
        "contratação",
        "reforço",
    ],
}

# Flatten to single list for search
ALL_TRIGGER_KEYWORDS = [kw for kws in TRIGGER_KEYWORDS.values() for kw in kws]


# ============================================
# V12.6: LANGUAGE-AWARE KEYWORD PRIORITIZATION
# ============================================
# Maps language codes to their native football keywords for targeted discovery.
# Used by run_targeted_discovery() to build language-optimized search queries
# instead of mixing all languages in a single query (which wastes API quota).

_LANGUAGE_KEYWORDS: dict[str, list[str]] = {
    "es": [
        "lesión",
        "lesiones",
        "convocados",
        "convocatoria",
        "baja",
        "bajas",
        "suspendido",
        "expulsado",
        "fichaje",
        "contratación",
        "nómina",
        "alterna",
        "rotación",
        "descartado",
        "ausente",
    ],
    "pt": [
        "lesão",
        "lesões",
        "escalação",
        "desfalque",
        "desfalques",
        "convocados",
        "contratação",
        "reforço",
        "poupados",
        "reservas",
        "time misto",
        "desfalque confirmado",
    ],
    "en": [
        "injury",
        "injured",
        "injuries",
        "squad",
        "lineup",
        "starting xi",
        "absent",
        "absence",
        "out",
        "suspended",
        "suspension",
        "transfer",
        "signing",
        "loan",
        "ruled out",
        "sidelined",
    ],
    "tr": [
        "sakatlık",
        "sakatlıklar",
        "kadro",
        "yedek",
        "eksik",
        "yok",
        "transfer",
        "rotasyon",
    ],
    "pl": [
        "kontuzja",
        "kontuzji",
        "skład",
        "składem",
        "nieobecny",
        "brak",
        "absencja",
        "rezerwowy",
    ],
    "ro": [
        "accidentare",
        "echipa",
        "absent",
        "indisponibili",
        "rezervă",
    ],
    "it": [
        "infortunio",
        "infortuni",
        "formazione",
        "assente",
        "assenti",
        "sospeso",
        "squalificato",
        "escluso",
    ],
    "de": [
        "verletzung",
        "verletzungen",
        "aufstellung",
        "kader",
        "ausfall",
    ],
    "fr": [
        "blessure",
        "blessures",
        "composition",
        "absent",
        "forfait",
    ],
}

# Map league_key substrings to language codes for automatic detection
_LEAGUE_LANGUAGE_MAP: dict[str, str] = {
    "argentina": "es",
    "colombia": "es",
    "chile": "es",
    "uruguay": "es",
    "ecuador": "es",
    "peru": "es",
    "mexico": "es",
    "spain": "es",
    "brazil": "pt",
    "portugal": "pt",
    "turkey": "tr",
    "poland": "pl",
    "romania": "ro",
    "italy": "it",
    "germany": "de",
    "austria": "de",
    "france": "fr",
    "switzerland": "de",
    "greece": "en",
    "england": "en",
    "scotland": "en",
    "netherlands": "en",
    "belgium": "en",
    "norway": "en",
    "sweden": "en",
    "denmark": "en",
    "finland": "en",
    "usa": "en",
    "australia": "en",
    "japan": "en",
    "china": "en",
    "korea": "en",
    "saudi": "en",
}


@dataclass
class NewsSignal:
    """Represents a discovered news signal with extracted team entity."""

    title: str
    snippet: str
    url: str
    source: str
    discovered_at: datetime
    extracted_team: str | None = None
    extracted_league: str | None = None
    confidence: float = 0.0
    keywords_matched: list[str] = field(default_factory=list)
    raw_article: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchCandidate:
    """Represents a potential match found via on-demand odds fetch."""

    match_id: str
    home_team: str
    away_team: str
    league: str
    start_time: datetime
    home_odd: float | None = None
    draw_odd: float | None = None
    away_odd: float | None = None
    signal: NewsSignal | None = None


class AlphaHunter:
    """
    The Alpha Hunter Loop - News-Driven Intelligence.

    This class implements the new paradigm where:
    1. We search for TRIGGER KEYWORDS on news domains (not team names)
    2. When relevant news is found, we extract the team entity
    3. We query Odds-API on-demand for that team only
    4. If match found, we save and analyze

    This reduces Odds-API consumption by ~99% and makes the bot a true "Alpha Hunter".
    """

    def __init__(self):
        self.logger = logger
        self._team_cache: dict[str, list[str]] = {}  # league_key -> list of team names cache

    def run_broad_discovery(
        self,
        news_sources: list[dict[str, Any]],
        trigger_keywords: list[str] | None = None,
    ) -> list[NewsSignal]:
        """
        BROAD DISCOVERY: Search news sources with trigger keywords.

        Instead of searching for specific team names, we search for
        generic trigger keywords (injury, squad, absence, etc.)
        on the configured news domains.

        Args:
            news_sources: List of news source configs with 'domain' and 'league_key'
            trigger_keywords: Keywords to search for (default: ALL_TRIGGER_KEYWORDS)

        Returns:
            List of NewsSignal objects with extracted team entities
        """
        if not trigger_keywords:
            trigger_keywords = ALL_TRIGGER_KEYWORDS

        signals: list[NewsSignal] = []

        # Import search provider
        try:
            from src.ingestion.search_provider import get_search_provider

            provider = get_search_provider()
            if not provider.is_available():
                self.logger.warning("⚠️ Search provider not available for broad discovery")
                return signals
        except ImportError:
            self.logger.warning("⚠️ Search provider not available")
            return signals

        # Group sources by league for efficient searching
        sources_by_league: dict[str, list[str]] = {}
        for source in news_sources:
            league_key = source.get("league_key", "unknown")
            domain = source.get("domain", "")
            if domain:
                if league_key not in sources_by_league:
                    sources_by_league[league_key] = []
                sources_by_league[league_key].append(domain)

        # Build keyword clusters for search
        # We group keywords by category for more targeted searches
        keyword_clusters = self._build_keyword_clusters(trigger_keywords)

        self.logger.info(
            f"🔍 [ALPHA-HUNTER] Starting broad discovery with "
            f"{len(keyword_clusters)} keyword clusters"
        )

        # Search each league with keyword clusters
        for league_key, domains in sources_by_league.items():
            if not domains:
                continue

            for cluster_name, keywords in keyword_clusters.items():
                try:
                    # Build search query with site dorking
                    kw_string = " OR ".join(keywords[:4])  # Limit to 4 keywords per query
                    site_dork = " OR ".join([f"site:{d}" for d in domains[:3]])

                    query = f"({kw_string}) ({site_dork})"

                    self.logger.debug(f"🔍 [ALPHA-HUNTER] Searching {league_key}: {cluster_name}")

                    # Execute search
                    results = provider.search(query, num_results=5)

                    for item in results:
                        signal = self._process_search_result(item, league_key, keywords)
                        if signal and signal.extracted_team:
                            signals.append(signal)

                except Exception as e:
                    self.logger.warning(f"⚠️ [ALPHA-HUNTER] Search failed for {league_key}: {e}")
                    continue

        # V12.1: Silent Drop Mitigation - Warn if no signals found
        if not signals:
            self.logger.warning(
                "⚠️ [ALPHA-HUNTER] SILENT DROP DETECTED: Broad discovery returned 0 signals. "
                "This may indicate: (1) Search provider unavailable, (2) No news matching trigger keywords, "
                "(3) Entity extraction failing. Check search provider health."
            )

        self.logger.info(
            f"🎯 [ALPHA-HUNTER] Broad discovery found {len(signals)} signals with team entities"
        )

        return signals

    def _build_keyword_clusters(self, keywords: list[str]) -> dict[str, list[str]]:
        """
        Build keyword clusters for more targeted searches.

        Instead of searching all keywords at once, we group them
        by category for more precise results.
        """
        clusters = {}

        # Injury cluster (highest priority)
        injury_kw = TRIGGER_KEYWORDS.get("injury", [])
        if injury_kw:
            clusters["injury"] = [kw for kw in injury_kw if kw in keywords][:5]

        # Squad/Lineup cluster
        squad_kw = TRIGGER_KEYWORDS.get("squad", [])
        if squad_kw:
            clusters["squad"] = [kw for kw in squad_kw if kw in keywords][:5]

        # Absence cluster
        absence_kw = TRIGGER_KEYWORDS.get("absence", [])
        if absence_kw:
            clusters["absence"] = [kw for kw in absence_kw if kw in keywords][:5]

        # Combined cluster for broader search
        clusters["combined"] = keywords[:8]

        return clusters

    def _process_search_result(
        self,
        item: dict[str, Any],
        league_key: str,
        matched_keywords: list[str],
    ) -> NewsSignal | None:
        """
        Process a search result and extract team entity.

        This is the key function that extracts the team name from
        the article title/snippet without knowing it beforehand.
        """
        title = item.get("title", "")
        snippet = item.get("snippet", "") or item.get("summary", "")
        url = item.get("link", "") or item.get("url", "")
        source = item.get("source", "Unknown")

        if not title and not snippet:
            return None

        # Extract team entity using multiple strategies
        extracted_team = self._extract_team_entity(title, snippet, league_key)

        if not extracted_team:
            return None

        # Calculate confidence based on keyword matches
        confidence = self._calculate_confidence(title, snippet, matched_keywords)

        return NewsSignal(
            title=title,
            snippet=snippet,
            url=url,
            source=source,
            discovered_at=datetime.now(timezone.utc),
            extracted_team=extracted_team,
            extracted_league=league_key,
            confidence=confidence,
            keywords_matched=matched_keywords,
            raw_article=item,
        )

    def _extract_team_entity(self, title: str, snippet: str, league_key: str) -> str | None:
        """
        Extract team name from article title/snippet.

        Uses multiple strategies:
        1. Pattern matching against known teams in DB (TeamAlias)
        2. Capitalized word sequences (team names are often capitalized)
        3. Common team name patterns (FC, Club, AS, etc.)
        """
        text = f"{title} {snippet}".lower()

        # Strategy 1: Check against known teams in database
        known_teams = self._get_known_teams_for_league(league_key)
        for team in known_teams:
            if team.lower() in text:
                return team

        # Strategy 2: Pattern matching for capitalized sequences
        # Team names are often 2-3 capitalized words
        full_text = f"{title} {snippet}"
        cap_pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b"
        matches = re.findall(cap_pattern, full_text)

        # Filter out common non-team words
        non_team_words = {
            "the",
            "injury",
            "squad",
            "news",
            "report",
            "update",
            "latest",
            "player",
            "coach",
            "manager",
            "match",
            "game",
            "team",
            "club",
            "first",
            "second",
            "new",
            "old",
            "big",
            "major",
            "minor",
        }

        for match in matches:
            words = match.split()
            # Skip if too short or contains non-team words
            if len(words) < 2:
                continue
            if any(w.lower() in non_team_words for w in words):
                continue
            # Potential team name
            return match

        # Strategy 3: Look for common team name markers (prefixes & suffixes)
        # Prefixes: "AS Roma", "Real Madrid", "Dynamo Kyiv", "Club Brugge", "Atlético Madrid"
        # Suffixes: "Manchester United", "Bayern FC", "Wanderers FC", "Spartak Moscow"
        team_markers = (
            r"\b(?:(?:AS|AC|SC|CF|FK|SK|Real|Atlético|Inter|Rapid"
            r"|Dynamo|Spartak|Club)\s+\w+"
            r"|(?:\w+(?:\s+\w+){0,2})\s+"
            r"(?:FC|Club|United|City|Wanderers))\b"
        )
        suffix_matches = re.findall(team_markers, full_text, re.IGNORECASE)
        if suffix_matches:
            self.logger.debug(
                f"   Found {len(suffix_matches)} potential team suffixes: {suffix_matches}"
            )
            # Return the longest match — it's most likely the full team name
            return max(suffix_matches, key=len)

        # Strategy 4 (V12.1): AI Fallback - Smart Entity Extraction
        # Only trigger AI if text contains trigger keywords (cost guardrail)
        if ALPHA_HUNTER_AI_FALLBACK_ENABLED:
            text_lower = f"{title} {snippet}".lower()
            # Check if any trigger keyword is present (cost guardrail)
            if any(
                kw.lower() in text_lower for kw in ALL_TRIGGER_KEYWORDS[:20]
            ):  # Check first 20 keywords
                return self._extract_team_with_ai(title, snippet)

        return None

    def _extract_team_with_ai(self, title: str, snippet: str) -> str | None:
        """
        V12.1: Smart AI Entity Extraction using DeepSeek V3.

        This is the fallback when local extraction strategies fail.
        Only called when the text already contains trigger keywords (cost guardrail).

        Args:
            title: Article title
            snippet: Article snippet/text

        Returns:
            Team name extracted by AI, or None on failure
        """
        try:
            # Import DeepSeek provider
            from src.ingestion.deepseek_intel_provider import get_deepseek_provider

            provider = get_deepseek_provider()
            if not provider or not provider.is_available():
                self.logger.debug(
                    "🔍 [ALPHA-HUNTER] AI provider not available for entity extraction"
                )
                return None

            # Build minimal prompt for team extraction
            text = f"Title: {title}\nSnippet: {snippet[:500]}"
            prompt = f"""Identify the main professional football (soccer) team discussed in this text. Return ONLY the official team name as a plain string (e.g., "Galatasaray", "Barcelona", "Manchester United"), or 'UNKNOWN' if you cannot determine it.

Text:
{text}

Team name (or UNKNOWN):"""

            # Use standard model with short timeout
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError("AI extraction timed out")

            # Set 5 second timeout
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(5)

            try:
                messages = [{"role": "user", "content": prompt}]
                response = provider.call_standard_model(messages, max_tokens=50, temperature=0.1)
                signal.alarm(0)  # Cancel alarm
            except TimeoutError:
                signal.alarm(0)
                self.logger.warning("⚠️ [ALPHA-HUNTER] AI entity extraction timed out after 5s")
                return None
            except Exception as ai_error:
                signal.alarm(0)
                self.logger.warning(f"⚠️ [ALPHA-HUNTER] AI entity extraction failed: {ai_error}")
                return None

            if not response:
                return None

            # Parse response - expect single team name or UNKNOWN
            extracted = response.strip()
            if extracted.upper() == "UNKNOWN" or len(extracted) < 2:
                return None

            # Validate: should contain at least one capitalized word (team name pattern)
            if not any(c.isupper() for c in extracted[:3]):
                self.logger.debug(f"🔍 [ALPHA-HUNTER] AI returned invalid format: {extracted}")
                return None

            self.logger.info(f"🔍 [ALPHA-HUNTER] AI extracted team: {extracted}")
            return extracted

        except ImportError:
            self.logger.debug("🔍 [ALPHA-HUNTER] DeepSeek provider not available")
            return None
        except Exception as e:
            self.logger.warning(f"⚠️ [ALPHA-HUNTER] AI entity extraction error: {e}")
            return None

    def _get_known_teams_for_league(self, league_key: str) -> list[str]:
        """
        Get known team names for a league from TeamAlias cache.

        This is cached to avoid repeated DB queries.
        """
        cache_key = f"teams_{league_key}"

        if cache_key in self._team_cache:
            return self._team_cache[cache_key]

        db = SessionLocal()
        try:
            # Get all matches for this league and extract team names
            existing = (
                db.query(Match)
                .filter(Match.league == league_key)
                .filter(Match.start_time > datetime.now(timezone.utc))
                .all()
            )

            teams: list[str] = []
            for match in existing:
                home = getattr(match, "home_team", None)
                away = getattr(match, "away_team", None)
                if home:
                    teams.append(home)
                if away:
                    teams.append(away)

            # Also check TeamAlias table
            aliases = db.query(TeamAlias).all()
            for alias in aliases:
                api_name = getattr(alias, "api_name", None)
                search_name = getattr(alias, "search_name", None)
                if api_name:
                    teams.append(api_name)
                if search_name:
                    teams.append(search_name)

            # Deduplicate
            teams = list(set(teams))
            self._team_cache[cache_key] = teams
            return teams

        except Exception as e:
            self.logger.warning(f"⚠️ Failed to get known teams for {league_key}: {e}")
            return []
        finally:
            db.close()

    def _calculate_confidence(self, title: str, snippet: str, matched_keywords: list[str]) -> float:
        """
        Calculate confidence score for a news signal.

        Higher confidence for:
        - More keyword matches
        - Keywords in title (more important)
        - Multiple keyword categories
        """
        text_lower = f"{title} {snippet}".lower()
        title_lower = title.lower()

        base_confidence = 0.5

        # Count keyword matches
        keyword_count = sum(1 for kw in matched_keywords if kw.lower() in text_lower)
        title_keyword_count = sum(1 for kw in matched_keywords if kw.lower() in title_lower)

        # Boost for keywords in title
        confidence = base_confidence + (keyword_count * 0.05) + (title_keyword_count * 0.1)

        # Check for multiple categories
        categories_matched = 0
        for _category, keywords in TRIGGER_KEYWORDS.items():
            if any(kw.lower() in text_lower for kw in keywords):
                categories_matched += 1

        confidence += categories_matched * 0.05

        # Cap at 1.0
        return min(confidence, 1.0)

    @staticmethod
    def _get_language_for_league(league_key: str) -> str:
        """
        Detect language from league key using pattern matching.

        Args:
            league_key: League identifier (e.g., 'soccer_argentina_primera_division')

        Returns:
            Language code (e.g., 'es', 'pt', 'en')
        """
        if not league_key:
            return "en"
        league_lower = league_key.lower()
        for country_pattern, lang in _LEAGUE_LANGUAGE_MAP.items():
            if country_pattern in league_lower:
                return lang
        return "en"

    def run_targeted_discovery(
        self,
        team_name: str,
        league_key: str,
        domains: list[str],
        trigger_keywords: list[str] | None = None,
    ) -> list[NewsSignal]:
        """
        TARGETED DISCOVERY: Search for news about a specific team (V12.6).

        Unlike run_broad_discovery (which searches trigger keywords without team names),
        this method builds a targeted dork that includes:
        1. The specific team name in double quotes
        2. Language-prioritized keywords (native language first, then English)
        3. Site restrictions to Supabase domains

        This is the intelligent bridge between "we know the match" and
        "find relevant news for this match".

        Args:
            team_name: Team to search for (e.g., "Boca Juniors")
            league_key: League identifier (e.g., "soccer_argentina_primera_division")
            domains: List of domains from Supabase news_sources
            trigger_keywords: Optional keyword override (default: ALL_TRIGGER_KEYWORDS)

        Returns:
            List of NewsSignal objects with extracted team entity set to team_name
        """
        if not trigger_keywords:
            trigger_keywords = ALL_TRIGGER_KEYWORDS

        signals: list[NewsSignal] = []

        # Import search provider
        try:
            from src.ingestion.search_provider import get_search_provider

            provider = get_search_provider()
            if not provider.is_available():
                self.logger.warning("⚠️ Search provider not available for targeted discovery")
                return signals
        except ImportError:
            self.logger.warning("⚠️ Search provider not available")
            return signals

        if not domains:
            self.logger.warning(f"⚠️ [ALPHA-HUNTER] No domains for targeted discovery: {league_key}")
            return signals

        # Detect language from league
        language = self._get_language_for_league(league_key)

        self.logger.info(
            f'🎯 [ALPHA-HUNTER] Targeted discovery: "{team_name}" '
            f"in {league_key} (lang: {language}, domains: {len(domains)})"
        )

        # Build language-prioritized keyword sets
        native_kws = _LANGUAGE_KEYWORDS.get(language, [])
        en_kws = _LANGUAGE_KEYWORDS.get("en", [])

        # Cross-reference with TRIGGER_KEYWORDS categories to keep only relevant ones
        all_injury = [kw.lower() for kw in TRIGGER_KEYWORDS.get("injury", [])]
        all_absence = [kw.lower() for kw in TRIGGER_KEYWORDS.get("absence", [])]
        all_squad = [kw.lower() for kw in TRIGGER_KEYWORDS.get("squad", [])]
        all_suspension = [kw.lower() for kw in TRIGGER_KEYWORDS.get("suspension", [])]

        # Native language keywords filtered by trigger categories
        native_injury_absence = [
            kw for kw in native_kws if kw.lower() in all_injury + all_absence + all_suspension
        ]
        native_squad = [kw for kw in native_kws if kw.lower() in all_squad]

        # English fallback keywords
        en_injury_absence = [
            kw for kw in en_kws if kw.lower() in all_injury + all_absence + all_suspension
        ][:4]

        # Build site dork from domains (limit to 4 for query length)
        site_dork = " OR ".join([f"site:{d}" for d in domains[:4]])

        # Build queries (in priority order — stop on first results)
        queries: list[tuple[str, str]] = []  # (query_string, description)

        # Query 1: Team + Native injury/absence keywords + Domains
        if native_injury_absence:
            kw_str = " OR ".join(native_injury_absence[:5])
            q = f'"{team_name}" ({kw_str}) ({site_dork})'
            queries.append((q, f"native_{language}_injury"))

        # Query 2: Team + Native squad keywords + Domains
        if native_squad:
            kw_str = " OR ".join(native_squad[:4])
            q = f'"{team_name}" ({kw_str}) ({site_dork})'
            queries.append((q, f"native_{language}_squad"))

        # Query 3: Team + English keywords + Domains
        if en_injury_absence:
            kw_str = " OR ".join(en_injury_absence[:4])
            q = f'"{team_name}" ({kw_str}) ({site_dork})'
            queries.append((q, "en_fallback"))

        # Query 4: Broader fallback - team + mixed native+en keywords + domains
        mixed_kw = (native_injury_absence[:2] + en_injury_absence[:2])[:4]
        if mixed_kw:
            kw_str = " OR ".join(mixed_kw)
            q = f'"{team_name}" ({kw_str}) ({site_dork})'
            queries.append((q, "mixed_fallback"))

        # Execute queries in priority order, stop on first results
        for query, desc in queries:
            try:
                self.logger.info(f"🔍 [ALPHA-HUNTER] Targeted query ({desc}): {query[:100]}...")

                results = provider.search(query, num_results=5)

                for item in results:
                    signal = self._process_search_result(item, league_key, trigger_keywords)
                    if signal:
                        # We KNOW the team since we searched for it specifically
                        signal.extracted_team = team_name
                        # Boost confidence: targeted search is inherently more reliable
                        signal.confidence = max(signal.confidence, 0.65)
                        signals.append(signal)

                if signals:
                    self.logger.info(
                        f"🎯 [ALPHA-HUNTER] Found {len(signals)} signals "
                        f"for {team_name} via '{desc}' query"
                    )
                    break  # Found results, no need for more queries

            except Exception as e:
                self.logger.warning(f"⚠️ [ALPHA-HUNTER] Targeted search failed ({desc}): {e}")
                continue

        # V12.6: Log if no signals found
        if not signals:
            self.logger.info(
                f"📭 [ALPHA-HUNTER] Targeted discovery: 0 signals for "
                f'"{team_name}" in {league_key} (tried {len(queries)} queries)'
            )

        return signals

    def fetch_on_demand_odds(
        self, team_name: str, league_key: str, hours_ahead: int | None = None
    ) -> list[MatchCandidate]:
        """
        ON-DEMAND ODDS FETCHING: Query Odds-API for a specific team.

        This is the key function that replaces bulk fixture ingestion.
        We ONLY call Odds-API when we have a confirmed news signal.

        Args:
            team_name: Team name to search for
            league_key: League to search in
            hours_ahead: Hours ahead to search for matches (default: MATCH_LOOKAHEAD_HOURS from settings)

        Returns:
            List of MatchCandidate objects with odds data
        """
        # Use settings value if not specified
        if hours_ahead is None:
            hours_ahead = MATCH_LOOKAHEAD_HOURS
        candidates: list[MatchCandidate] = []

        try:
            from src.ingestion.ingest_fixtures import fetch_odds_for_team

            # Fetch odds for this specific team (on-demand)
            match = fetch_odds_for_team(team_name, league_key)

            if not match:
                self.logger.debug(
                    f"📊 [ALPHA-HUNTER] No match found for {team_name} in {league_key}"
                )
                return candidates

            # Convert Match to MatchCandidate
            start_time = match.start_time
            if start_time and start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)

            candidate = MatchCandidate(
                match_id=str(match.id) if match.id else f"{match.home_team}_{match.away_team}",
                home_team=match.home_team or "",
                away_team=match.away_team or "",
                league=match.league or league_key,
                start_time=start_time or datetime.now(timezone.utc),
                home_odd=match.current_home_odd,
                draw_odd=match.current_draw_odd,
                away_odd=match.current_away_odd,
            )
            candidates.append(candidate)

            self.logger.info(
                f"📊 [ALPHA-HUNTER] On-demand fetch found match: "
                f"{match.home_team} vs {match.away_team}"
            )

        except Exception as e:
            self.logger.error(f"❌ [ALPHA-HUNTER] On-demand odds fetch failed: {e}")

        return candidates

    def save_and_analyze(
        self,
        candidate: MatchCandidate,
        signal: NewsSignal,
        analysis_engine,
        fotmob,
        db_session,
    ) -> dict[str, Any]:
        """
        Save match to DB and pass to AnalysisEngine for full analysis.

        This is the final step in the Alpha Hunter loop:
        1. Save match to local SQLite DB
        2. Pass to AnalysisEngine with the news signal
        3. Return analysis result

        Args:
            candidate: MatchCandidate with odds data
            signal: NewsSignal that triggered this match
            analysis_engine: AnalysisEngine instance
            fotmob: FotMob provider
            db_session: Database session

        Returns:
            Analysis result dict
        """
        # Save match to DB if not exists
        existing = db_session.query(Match).filter(Match.id == candidate.match_id).first()

        if not existing:
            new_match = Match(
                id=candidate.match_id,
                league=candidate.league,
                home_team=candidate.home_team,
                away_team=candidate.away_team,
                start_time=candidate.start_time.replace(tzinfo=None),
                opening_home_odd=candidate.home_odd,
                current_home_odd=candidate.home_odd,
                opening_draw_odd=candidate.draw_odd,
                current_draw_odd=candidate.draw_odd,
                opening_away_odd=candidate.away_odd,
                current_away_odd=candidate.away_odd,
            )
            db_session.add(new_match)
            db_session.flush()
            match = new_match
            self.logger.info(
                f"💾 [ALPHA-HUNTER] Saved new match: {candidate.home_team} vs {candidate.away_team}"
            )
        else:
            match = existing
            # Update current odds
            if candidate.home_odd:
                existing.current_home_odd = candidate.home_odd
            if candidate.draw_odd:
                existing.current_draw_odd = candidate.draw_odd
            if candidate.away_odd:
                existing.current_away_odd = candidate.away_odd

        # Build forced narrative from signal
        forced_narrative = self._build_forced_narrative(signal)

        # Pass to AnalysisEngine with forced narrative
        result = analysis_engine.analyze_match(
            match=match,
            fotmob=fotmob,
            now_utc=datetime.now(timezone.utc),
            db_session=db_session,
            context_label="ALPHA_HUNTER",
            forced_narrative=forced_narrative,
        )

        return result

    def _build_forced_narrative(self, signal: NewsSignal) -> str:
        """
        Build forced narrative from news signal for AnalysisEngine.

        This bypasses the normal news hunting and uses the signal
        that triggered the match discovery.
        """
        keywords_str = ", ".join(signal.keywords_matched[:3])

        narrative = f"""🔍 [ALPHA HUNTER SIGNAL]
Source: {signal.source}
Team: {signal.extracted_team}
Confidence: {signal.confidence:.0%}
Keywords: {keywords_str}

Title: {signal.title}

{signal.snippet[:500]}
"""
        return narrative

    def run_alpha_hunter_loop(
        self,
        news_sources: list[dict[str, Any]],
        analysis_engine,
        fotmob,
        min_confidence: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Run the complete Alpha Hunter loop.

        This is the main entry point that orchestrates:
        1. Broad Discovery (search with trigger keywords)
        2. Entity Extraction (extract team names)
        3. On-Demand Odds (fetch only for confirmed signals)
        4. Save & Analyze (pass to AnalysisEngine)

        Args:
            news_sources: List of news source configs from Supabase
            analysis_engine: AnalysisEngine instance
            fotmob: FotMob provider
            min_confidence: Minimum confidence threshold (default: ALPHA_HUNTER_MIN_CONFIDENCE from settings)

        Returns:
            List of analysis results
        """
        # Use settings value if not specified
        if min_confidence is None:
            min_confidence = ALPHA_HUNTER_MIN_CONFIDENCE

        results: list[dict[str, Any]] = []

        self.logger.info("🎯 [ALPHA-HUNTER] Starting Alpha Hunter Loop...")

        # Step 1: Broad Discovery
        signals = self.run_broad_discovery(news_sources)

        if not signals:
            self.logger.info("📭 [ALPHA-HUNTER] No signals found in broad discovery")
            return results

        # Step 2 & 3: For each signal, fetch on-demand odds
        for signal in signals:
            if signal.confidence < min_confidence:
                self.logger.debug(
                    f"⏭️ [ALPHA-HUNTER] Skipping low confidence signal: "
                    f"{signal.extracted_team} ({signal.confidence:.1%})"
                )
                continue

            if not signal.extracted_team or not signal.extracted_league:
                continue

            self.logger.info(
                f"🎯 [ALPHA-HUNTER] Processing signal: {signal.extracted_team} "
                f"({signal.confidence:.0%}) from {signal.source}"
            )

            # Step 3: On-Demand Odds Fetch
            candidates = self.fetch_on_demand_odds(
                team_name=signal.extracted_team,
                league_key=signal.extracted_league,
            )

            if not candidates:
                self.logger.debug(
                    f"📊 [ALPHA-HUNTER] No upcoming matches for {signal.extracted_team}"
                )
                continue

            # Step 4: Save & Analyze
            db = SessionLocal()
            try:
                for candidate in candidates:
                    candidate.signal = signal

                    result = self.save_and_analyze(
                        candidate=candidate,
                        signal=signal,
                        analysis_engine=analysis_engine,
                        fotmob=fotmob,
                        db_session=db,
                    )
                    results.append(result)

                    if result.get("alert_sent"):
                        self.logger.info(
                            f"🚨 [ALPHA-HUNTER] Alert sent for "
                            f"{candidate.home_team} vs {candidate.away_team}"
                        )

                db.commit()
            except Exception as e:
                self.logger.error(f"❌ [ALPHA-HUNTER] Analysis failed: {e}")
                db.rollback()
            finally:
                db.close()

        self.logger.info(f"🎯 [ALPHA-HUNTER] Loop complete: {len(results)} matches analyzed")

        return results


# ============================================
# SINGLETON & CONVENIENCE FUNCTIONS
# ============================================

_alpha_hunter_instance: AlphaHunter | None = None


def get_alpha_hunter() -> AlphaHunter:
    """Get or create the singleton AlphaHunter instance."""
    global _alpha_hunter_instance
    if _alpha_hunter_instance is None:
        _alpha_hunter_instance = AlphaHunter()
    return _alpha_hunter_instance


def run_alpha_hunter(
    news_sources: list[dict[str, Any]],
    analysis_engine,
    fotmob,
    min_confidence: float = 0.6,
) -> list[dict[str, Any]]:
    """
    Convenience function to run the Alpha Hunter loop.

    Args:
        news_sources: List of news source configs
        analysis_engine: AnalysisEngine instance
        fotmob: FotMob provider
        min_confidence: Minimum confidence threshold

    Returns:
        List of analysis results
    """
    hunter = get_alpha_hunter()
    return hunter.run_alpha_hunter_loop(
        news_sources=news_sources,
        analysis_engine=analysis_engine,
        fotmob=fotmob,
        min_confidence=min_confidence,
    )
