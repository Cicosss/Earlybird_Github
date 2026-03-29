"""
EarlyBird Radar Light Enrichment Module V1.0

Arricchisce gli alert del News Radar con contesto dal database principale,
senza appesantire il flusso con chiamate FotMob complete.

Strategia "Light Enrichment":
1. Cerca match nelle prossime 48h per la squadra menzionata nell'alert
2. Se trovato: aggiungi contesto classifica (zona, posizione)
3. Se fine stagione (ultime 5 giornate): check biscotto
4. NON fa chiamate FotMob - usa solo dati già in DB o cache

Questo approccio:
- Mantiene il radar veloce e indipendente
- Aggiunge valore informativo agli alert
- Riusa l'infrastruttura esistente del bot principale

Requirements: Integrazione con news_radar.py
Author: EarlyBird AI
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Configuration
# FIX: Use ANALYSIS_WINDOW_HOURS from settings (72h) instead of hardcoded 48h
# This ensures Radar finds matches within the full 72-hour window as required
try:
    from config.settings import ANALYSIS_WINDOW_HOURS

    MATCH_LOOKAHEAD_HOURS = ANALYSIS_WINDOW_HOURS
except ImportError:
    # Fallback if settings not available
    MATCH_LOOKAHEAD_HOURS = 72  # Default to 72h (3 days)
    logger.warning("⚠️ [RADAR-ENRICH] Could not import ANALYSIS_WINDOW_HOURS, using default 72h")

END_OF_SEASON_ROUNDS = 5  # Ultime 5 giornate = fine stagione


@dataclass
class EnrichmentContext:
    """
    Contesto arricchito per un RadarAlert.

    Contiene informazioni aggiuntive estratte dal database
    senza fare chiamate API esterne.
    """

    # Match info
    match_id: Optional[str] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    match_time: Optional[datetime] = None
    league: Optional[str] = None

    # Classifica context
    team_zone: Optional[str] = None  # "Title Race", "Relegation", etc.
    team_position: Optional[int] = None
    total_teams: Optional[int] = None
    matches_remaining: Optional[int] = None

    # Biscotto context
    is_biscotto_suspect: bool = False
    biscotto_severity: str | None = None
    current_draw_odd: float | None = None

    # V3.0: StructuredAnalysis enrichment fields
    # These fields enable intelligent component communication
    motivation_home: Optional[str] = None  # "HIGH", "MEDIUM", "LOW", "NORMAL"
    motivation_away: Optional[str] = None  # "HIGH", "MEDIUM", "LOW", "NORMAL"
    match_importance: Optional[str] = None  # "CRITICAL", "IMPORTANT", "NORMAL", "LOW"
    opponent: Optional[str] = None  # Opponent team name (derived from home_team/away_team)
    competition: Optional[str] = None  # Competition name (mapped from league)
    match_date: Optional[str] = None  # Match date string (derived from match_time)

    # Metadata
    enrichment_source: str = "database"  # "database", "cache", "fotmob_light"

    def has_match(self) -> bool:
        """Check if a match was found."""
        return self.match_id is not None

    def is_end_of_season(self) -> bool:
        """Check if match is in end-of-season window."""
        if self.matches_remaining is None:
            return False
        return self.matches_remaining <= END_OF_SEASON_ROUNDS

    def format_context_line(self) -> str:
        """
        Format enrichment as a single line for alert summary.

        Returns:
            Formatted string like "📊 Prossima: Gala vs Fener (Zona Retrocessione, -3 dalla salvezza)"
        """
        if not self.has_match():
            return ""

        parts = []

        # Match info
        match_str = f"{self.home_team} vs {self.away_team}"

        # Zone info
        if self.team_zone and self.team_zone != "Unknown":
            zone_italian = self._translate_zone(self.team_zone)
            parts.append(zone_italian)

        # Position info
        if self.team_position and self.total_teams:
            parts.append(f"#{self.team_position}/{self.total_teams}")

        # End of season warning
        if self.is_end_of_season():
            parts.append(f"⚠️ Ultime {self.matches_remaining} giornate")

        # Biscotto warning
        if self.is_biscotto_suspect:
            parts.append(f"🍪 BISCOTTO ({self.biscotto_severity})")

        context_str = " | ".join(parts) if parts else ""

        if context_str:
            return f"📊 Prossima: {match_str} ({context_str})"
        else:
            return f"📊 Prossima: {match_str}"

    def _translate_zone(self, zone: str) -> str:
        """Translate zone to Italian."""
        translations = {
            "Title Race": "Lotta Scudetto",
            "European Spots": "Zona Europa",
            "Mid-Table": "Metà Classifica",
            "Danger Zone": "Zona Pericolo",
            "Relegation": "Zona Retrocessione",
            "Unknown": "Sconosciuto",
        }
        return translations.get(zone, zone)


class RadarLightEnricher:
    """
    Light enrichment per News Radar alerts.

    Cerca match nel database e aggiunge contesto senza chiamate API pesanti.
    Progettato per essere veloce e non bloccare il flusso del radar.
    """

    def __init__(self):
        """Initialize enricher."""
        self._db_available = False
        self._fotmob_available = False
        self._biscotto_available = False

        # Lazy import per evitare dipendenze circolari
        self._check_dependencies()

    def _check_dependencies(self) -> None:
        """Check which dependencies are available."""
        # Database
        try:
            from src.database.models import Match, SessionLocal

            self._db_available = True
        except ImportError:
            logger.warning("⚠️ [RADAR-ENRICH] Database not available")

        # FotMob (per contesto classifica se non in DB)
        try:
            from src.ingestion.data_provider import get_data_provider

            self._fotmob_available = True
        except ImportError:
            logger.warning("⚠️ [RADAR-ENRICH] FotMob provider not available")

        # Biscotto Engine
        try:
            from src.analysis.biscotto_engine import BiscottoSeverity, analyze_biscotto

            self._biscotto_available = True
        except ImportError:
            logger.warning("⚠️ [RADAR-ENRICH] Biscotto engine not available")

    def find_upcoming_match(
        self, team_name: str, hours: int = MATCH_LOOKAHEAD_HOURS
    ) -> dict | None:
        """
        Cerca una partita nelle prossime N ore per la squadra specificata.

        V12.4: Added active league scope filter to prevent non-active league
        matches (e.g., Portuguese Liga) from being enriched and triggering
        FotMob calls that result in 404 errors.

        Args:
            team_name: Nome della squadra (può essere parziale)
            hours: Finestra temporale in ore

        Returns:
            Dict con info match o None se non trovato
        """
        if not self._db_available or not team_name:
            return None

        # V12.4: Load active league keys for scope filtering
        active_league_keys: set[str] | None = None
        try:
            from src.ingestion.league_manager import get_all_active_league_keys

            active_league_keys = set(get_all_active_league_keys())
        except ImportError:
            logger.debug("[RADAR-ENRICH] league_manager not available, scope filter disabled")
        except Exception as e:
            logger.debug(f"[RADAR-ENRICH] Failed to load active leagues: {e}")

        try:
            from src.database.models import Match, SessionLocal

            db = SessionLocal()
            try:
                now = datetime.now(timezone.utc)
                # Rimuovi timezone per confronto con DB SQLite
                now_naive = now.replace(tzinfo=None)
                end_window = now_naive + timedelta(hours=hours)

                # Normalizza team name per ricerca
                team_lower = team_name.lower().strip()

                # Query matches nella finestra temporale
                matches = (
                    db.query(Match)
                    .filter(Match.start_time >= now_naive, Match.start_time <= end_window)
                    .all()
                )

                # Cerca match che coinvolge la squadra
                for match in matches:
                    # VPS FIX: Extract Match attributes safely to prevent session detachment
                    # This prevents "Trust validation error" when Match object becomes detached
                    # from session due to connection pool recycling under high load
                    home_team = getattr(match, "home_team", None)
                    away_team = getattr(match, "away_team", None)
                    match_id = getattr(match, "id", None)
                    start_time = getattr(match, "start_time", None)
                    league = getattr(match, "league", None)
                    current_draw_odd = getattr(match, "current_draw_odd", None)
                    opening_draw_odd = getattr(match, "opening_draw_odd", None)

                    home_lower = (home_team or "").lower()
                    away_lower = (away_team or "").lower()

                    # Match fuzzy: controlla se team_name è contenuto
                    if (
                        team_lower in home_lower
                        or home_lower in team_lower
                        or team_lower in away_lower
                        or away_lower in team_lower
                    ):
                        # V12.4: Active scope guard - skip matches from non-active leagues
                        if (
                            active_league_keys is not None
                            and league
                            and league not in active_league_keys
                        ):
                            logger.debug(
                                f"🚫 [SCOPE] Skipping match {home_team} vs {away_team} "
                                f"- league '{league}' not in active scope"
                            )
                            continue

                        logger.info(f"🔍 [RADAR-ENRICH] Found match: {home_team} vs {away_team}")

                        return {
                            "match_id": match_id,
                            "home_team": home_team,
                            "away_team": away_team,
                            "start_time": start_time,
                            "league": league,
                            "current_draw_odd": current_draw_odd,
                            "opening_draw_odd": opening_draw_odd,
                            "is_home": team_lower in home_lower,
                        }

                return None

            finally:
                db.close()

        except Exception as e:
            logger.error(f"❌ [RADAR-ENRICH] Error finding match: {e}")
            return None

    def get_team_context_light(self, team_name: str) -> dict:
        """
        Ottieni contesto classifica in modo "light".

        Prima prova la cache, poi FotMob se necessario.
        NON fa chiamate se non strettamente necessario.

        Args:
            team_name: Nome della squadra

        Returns:
            Dict con zone, position, matches_remaining
        """
        result = {
            "zone": "Unknown",
            "position": None,
            "total_teams": None,
            "matches_remaining": None,
            "source": "none",
        }

        if not team_name:
            return result

        # Prova FotMob (ha cache interna)
        if self._fotmob_available:
            try:
                from src.ingestion.data_provider import get_data_provider

                fotmob = get_data_provider()
                if fotmob:
                    context = fotmob.get_table_context(team_name)

                    if context and context.get("zone") != "Unknown":
                        result["zone"] = context.get("zone", "Unknown")
                        result["position"] = context.get("position")
                        result["total_teams"] = context.get("total_teams")
                        result["matches_remaining"] = context.get("matches_remaining")
                        result["source"] = "fotmob_cache"

                        logger.debug(f"📊 [RADAR-ENRICH] Context for {team_name}: {result['zone']}")
                        return result

            except Exception as e:
                logger.debug(f"⚠️ [RADAR-ENRICH] FotMob context failed: {e}")

        return result

    def check_biscotto_light(self, match_info: dict) -> tuple[bool, str | None]:
        """
        Check biscotto in modo light usando dati già disponibili.

        Args:
            match_info: Dict dal find_upcoming_match

        Returns:
            Tuple (is_suspect, severity_string)
        """
        if not self._biscotto_available:
            return False, None

        # Get team names from match info
        home_team = match_info.get("home_team", "")
        away_team = match_info.get("away_team", "")

        if not home_team or not away_team:
            logger.debug("⚠️ [RADAR-ENRICH] Missing team names in match_info")
            return False, None

        # Get context for BOTH teams (critical for mutual benefit detection)
        home_team_context = self.get_team_context_light(home_team)
        away_team_context = self.get_team_context_light(away_team)

        # Use matches_remaining from either team (should be the same)
        matches_remaining = home_team_context.get("matches_remaining")

        # Solo se fine stagione
        if matches_remaining is None or matches_remaining > END_OF_SEASON_ROUNDS:
            return False, None

        # Solo se abbiamo quote draw
        current_draw = match_info.get("current_draw_odd")
        if not current_draw:
            return False, None

        try:
            from src.analysis.biscotto_engine import analyze_biscotto

            # Crea motivation dict per AMBE le squadre
            home_motivation = {
                "zone": home_team_context.get("zone", "Unknown"),
                "position": home_team_context.get("position", 0),
                "total_teams": home_team_context.get("total_teams", 20),
                "matches_remaining": home_team_context.get("matches_remaining"),
            }

            away_motivation = {
                "zone": away_team_context.get("zone", "Unknown"),
                "position": away_team_context.get("position", 0),
                "total_teams": away_team_context.get("total_teams", 20),
                "matches_remaining": away_team_context.get("matches_remaining"),
            }

            analysis = analyze_biscotto(
                home_team=home_team,
                away_team=away_team,
                current_draw_odd=current_draw,
                opening_draw_odd=match_info.get("opening_draw_odd"),
                home_motivation=home_motivation,
                away_motivation=away_motivation,
                matches_remaining=matches_remaining,
                league_key=match_info.get("league"),
            )

            if analysis.is_suspect:
                return True, analysis.severity.value

            return False, None

        except Exception as e:
            logger.debug(f"⚠️ [RADAR-ENRICH] Biscotto check failed: {e}")
            return False, None

    def _derive_motivation_from_zone(self, zone: str) -> str:
        """
        Derive motivation level from team zone.

        This enables intelligent component communication by converting
        league position context into motivation levels that StructuredAnalysis
        can use for enrichment.

        Args:
            zone: Team zone (Title Race, Relegation, etc.)

        Returns:
            Motivation level: "HIGH", "MEDIUM", "LOW", or "NORMAL"
        """
        if not zone or zone == "Unknown":
            return "NORMAL"

        # High motivation zones
        if zone in ["Title Race", "Relegation"]:
            return "HIGH"

        # Medium motivation zones
        if zone in ["European Spots", "Danger Zone"]:
            return "MEDIUM"

        # Low motivation zones
        if zone == "Mid-Table":
            return "LOW"

        return "NORMAL"

    def _derive_match_importance(self, zone: str, matches_remaining: int | None) -> str:
        """
        Derive match importance from team context.

        This enables intelligent component communication by analyzing
        the strategic importance of the upcoming match.

        Args:
            zone: Team zone
            matches_remaining: Number of matches remaining in season

        Returns:
            Match importance: "CRITICAL", "IMPORTANT", "NORMAL", or "LOW"
        """
        # Critical: End of season in high-stakes zones
        if matches_remaining is not None and matches_remaining <= 3:
            if zone in ["Title Race", "Relegation", "Danger Zone"]:
                return "CRITICAL"

        # Important: High-stakes zones with few matches remaining
        if matches_remaining is not None and matches_remaining <= 10:
            if zone in ["Title Race", "Relegation", "Danger Zone", "European Spots"]:
                return "IMPORTANT"

        # Normal: Mid-season or mid-table
        if zone in ["Mid-Table", "Unknown"]:
            return "NORMAL"

        # Normal: Early season with many matches remaining
        if matches_remaining is not None and matches_remaining > 20:
            return "NORMAL"

        # Important: High-stakes zones during season
        if zone in ["Title Race", "Relegation", "Danger Zone", "European Spots"]:
            return "IMPORTANT"

        return "NORMAL"

    def enrich(self, affected_team: str) -> EnrichmentContext:
        """
        Arricchisci un alert con contesto dal database.

        Metodo principale da chiamare dal News Radar.

        V3.0: Enhanced to populate StructuredAnalysis fields with intelligent
        derivation from team context (zone, position, matches_remaining).

        Args:
            affected_team: Nome della squadra dall'alert

        Returns:
            EnrichmentContext con tutti i dati disponibili
        """
        context = EnrichmentContext()

        if not affected_team or affected_team == "Unknown":
            return context

        # Step 1: Cerca match nelle prossime 48h
        match_info = self.find_upcoming_match(affected_team)

        if not match_info:
            logger.debug(f"📭 [RADAR-ENRICH] No upcoming match for {affected_team}")
            return context

        # Popola info match
        context.match_id = match_info.get("match_id")
        context.home_team = match_info.get("home_team")
        context.away_team = match_info.get("away_team")
        context.match_time = match_info.get("start_time")
        context.league = match_info.get("league")
        context.current_draw_odd = match_info.get("current_draw_odd")

        # Step 2: Ottieni contesto classifica
        team_context = self.get_team_context_light(affected_team)

        context.team_zone = team_context.get("zone")
        context.team_position = team_context.get("position")
        context.total_teams = team_context.get("total_teams")
        context.matches_remaining = team_context.get("matches_remaining")
        context.enrichment_source = team_context.get("source", "database")

        # V3.0: NEW - Populate StructuredAnalysis enrichment fields
        # Derive motivation from team zone
        context.motivation_home = self._derive_motivation_from_zone(context.team_zone)

        # For away team motivation, we need to get their context too
        if context.away_team:
            away_team_context = self.get_team_context_light(context.away_team)
            context.motivation_away = self._derive_motivation_from_zone(
                away_team_context.get("zone")
            )

        # Derive match importance from team context
        context.match_importance = self._derive_match_importance(
            context.team_zone, context.matches_remaining
        )

        # Derive opponent from match info
        is_home = match_info.get("is_home", False)
        context.opponent = context.away_team if is_home else context.home_team

        # Map league to competition
        context.competition = context.league

        # Derive match date string from match_time
        if context.match_time:
            context.match_date = context.match_time.strftime("%Y-%m-%d")

        # Step 3: Check biscotto se fine stagione
        if context.is_end_of_season():
            is_suspect, severity = self.check_biscotto_light(match_info)
            context.is_biscotto_suspect = is_suspect
            context.biscotto_severity = severity

        logger.info(
            f"✨ [RADAR-ENRICH] Enriched {affected_team}: "
            f"{context.team_zone}, match in {context.match_time}, "
            f"motivation={context.motivation_home}, importance={context.match_importance}"
        )

        return context


# Singleton instance
_enricher_instance: RadarLightEnricher | None = None
_enricher_instance_init_lock = threading.Lock()  # Lock for thread-safe initialization


def get_radar_enricher() -> RadarLightEnricher:
    """
    Get singleton instance of RadarLightEnricher.

    V12.2: Fixed lazy initialization race condition.
    Multiple threads can safely call this function concurrently.

    Returns:
        RadarLightEnricher instance
    """
    global _enricher_instance

    if _enricher_instance is None:
        with _enricher_instance_init_lock:
            # Double-checked locking pattern for thread safety
            if _enricher_instance is None:
                _enricher_instance = RadarLightEnricher()
                logger.info("✅ [RADAR-ENRICH] Enricher initialized")

    return _enricher_instance


async def enrich_radar_alert_async(
    affected_team: str,
    team: str | None = None,
    opponent: str | None = None,
    competition: str | None = None,
    match_date: str | None = None,
) -> EnrichmentContext:
    """
    Async wrapper per l'enrichment (per compatibilità con news_radar async).

    V3.0: Enhanced to accept additional parameters for StructuredAnalysis integration.
    These parameters are accepted for API compatibility but are not used directly,
    as the enrichment system derives all needed information from team context.

    Args:
        affected_team: Nome della squadra dall'alert (required)
        team: Alias for affected_team (optional, for backward compatibility)
        opponent: Opponent team name (optional, not used - derived from DB)
        competition: Competition name (optional, not used - derived from DB)
        match_date: Match date string (optional, not used - derived from DB)

    Returns:
        EnrichmentContext con tutti i dati disponibili, including:
        - motivation_home/away: Derived from team zone
        - match_importance: Derived from zone and matches_remaining
        - opponent: Derived from match info
        - competition: Mapped from league
        - match_date: Derived from match_time
    """
    import asyncio

    # Use affected_team parameter (primary parameter)
    # team parameter is accepted but ignored (alias for compatibility)
    team_to_enrich = affected_team if affected_team else team

    if not team_to_enrich or team_to_enrich == "Unknown":
        return EnrichmentContext()

    enricher = get_radar_enricher()

    # Esegui in thread pool per non bloccare event loop
    # (le query DB sono sync)
    loop = asyncio.get_event_loop()
    context = await loop.run_in_executor(None, enricher.enrich, team_to_enrich)

    return context
