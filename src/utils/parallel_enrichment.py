"""
EarlyBird Parallel Enrichment Module V1.0

Parallelizza le chiamate di enrichment FotMob per ridurre il tempo
di elaborazione da ~15s a ~3-4s per match.

Architettura:
- ThreadPoolExecutor per chiamate I/O-bound (HTTP requests)
- Gestione dipendenze (weather dipende da stadium_coords)
- Timeout per-future per evitare blocchi
- Fallback graceful se una chiamata fallisce

Chiamate parallelizzate:
- get_full_team_context(home)
- get_full_team_context(away)
- get_turnover_risk(home)
- get_turnover_risk(away)
- get_referee_info(home)
- get_stadium_coordinates(home)
- get_team_stats(home)
- get_team_stats(away)
- get_tactical_insights(home, away)

Chiamate sequenziali (dipendenze):
- get_match_weather() -> dipende da stadium_coords

V1.0: Initial implementation
"""

import concurrent.futures
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Configuration
# V6.2: Reduced from 4 to 1 to prevent burst requests that trigger FotMob anti-bot detection
# Sequential execution ensures proper request spacing and reduces 403 errors
DEFAULT_MAX_WORKERS = 1
DEFAULT_TIMEOUT_SECONDS = 30  # Timeout per singola chiamata
TOTAL_TIMEOUT_SECONDS = (
    90  # Timeout totale per tutte le chiamate (was 45 - increased for retries and backoff)
)


@dataclass
class EnrichmentResult:
    """
    Risultato dell'enrichment parallelizzato per un match.

    Contiene tutti i dati raccolti dalle varie fonti,
    con fallback a valori vuoti se una fonte fallisce.
    """

    # Team contexts (injuries, motivation, fatigue)
    home_context: dict[str, Any] = field(default_factory=dict)
    away_context: dict[str, Any] = field(default_factory=dict)

    # Turnover risk
    home_turnover: dict[str, Any] | None = None
    away_turnover: dict[str, Any] | None = None

    # Referee info
    referee_info: dict[str, Any] | None = None

    # Stadium and weather
    stadium_coords: tuple[float, float] | None = None
    weather_impact: dict[str, Any] | None = None

    # Team stats (goals, cards, corners)
    home_stats: dict[str, Any] = field(default_factory=dict)
    away_stats: dict[str, Any] = field(default_factory=dict)

    # Tactical insights
    tactical: dict[str, Any] = field(default_factory=dict)

    # Metadata
    enrichment_time_ms: int = 0
    failed_calls: list[str] = field(default_factory=list)
    successful_calls: int = 0
    error_details: dict[str, str] = field(default_factory=dict)  # Maps task key to error message

    def has_injuries(self) -> bool:
        """Check if any team has injuries."""
        home_injuries = self.home_context.get("injuries", [])
        away_injuries = self.away_context.get("injuries", [])
        return bool(home_injuries) or bool(away_injuries)

    def has_high_turnover(self) -> bool:
        """Check if any team has HIGH turnover risk."""
        home_high = (
            self.home_turnover is not None and self.home_turnover.get("risk_level") == "HIGH"
        )
        away_high = (
            self.away_turnover is not None and self.away_turnover.get("risk_level") == "HIGH"
        )
        return home_high or away_high

    def get_summary(self) -> str:
        """Get human-readable summary of enrichment."""
        parts: list[str] = []

        if self.has_injuries():
            home_count = len(self.home_context.get("injuries", []))
            away_count = len(self.away_context.get("injuries", []))
            parts.append(f"Injuries: H={home_count}, A={away_count}")

        if self.has_high_turnover():
            parts.append("HIGH TURNOVER detected")

        if self.referee_info and self.referee_info.get("name"):
            parts.append(f"Referee: {self.referee_info['name']}")

        if self.weather_impact:
            parts.append(f"Weather: {self.weather_impact.get('status', 'OK')}")

        return " | ".join(parts) if parts else "No significant findings"


def enrich_match_parallel(
    fotmob,
    home_team: str,
    away_team: str,
    match_start_time: Optional[datetime] = None,
    weather_provider: Optional[Callable] = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    timeout: int = TOTAL_TIMEOUT_SECONDS,
) -> EnrichmentResult:
    """
    V6.2: Esegue enrichment sequenziale per un match (precedentemente parallelizzato).

    ⚠️ IMPORTANTE: Nonostante il nome "parallel", questa funzione esegue SEQUENZIALMENTE
    per prevenire burst requests che triggerano l'anti-bot detection di FotMob (errori 403).

    Cambiamenti V6.2:
    - Passato da parallelo a sequenziale per prevenire burst requests
    - Ridotto max_workers da 4 a 1 per evitare errori 403 FotMob
    - Le chiamate sono ora eseguite una alla volta con rate limiting appropriato
    - Aggiunto early exit se >50% dei task fallisce per migliorare performance su VPS
    - Aggiunto campo error_details per migliorare debug su VPS

    Args:
        fotmob: FotMobProvider instance
        home_team: Nome squadra casa (già validato)
        away_team: Nome squadra trasferta (già validato)
        match_start_time: Orario partita per weather (opzionale)
        weather_provider: Funzione get_match_weather (opzionale)
        max_workers: Numero massimo di thread paralleli (default: 1 per esecuzione sequenziale)
        timeout: Timeout totale in secondi

    Returns:
        EnrichmentResult con tutti i dati raccolti, incluso error_details per debugging

    Thread Safety:
        - FotMob ha già rate limiting thread-safe interno
        - Ogni chiamata è indipendente (no shared state)
        - V6.2: Esecuzione sequenziale previene race conditions e burst requests

    Performance:
        - Early exit se >50% dei task fallisce per evitare spreco di tempo
        - Timeout configurabili per evitare blocchi
    """
    import time

    start_time = time.time()

    result = EnrichmentResult()

    # Validazione input
    if not fotmob:
        logger.warning("⚠️ [PARALLEL] FotMob provider not available")
        return result

    if not home_team or not away_team:
        logger.warning("⚠️ [PARALLEL] Missing team names")
        return result

    logger.info(f"⚡ [PARALLEL] Starting enrichment for {home_team} vs {away_team}")

    # Definizione task paralleli
    # Ogni task è una tupla: (key, callable, args)
    parallel_tasks = [
        ("home_context", fotmob.get_full_team_context, (home_team,)),
        ("away_context", fotmob.get_full_team_context, (away_team,)),
        ("home_turnover", fotmob.get_turnover_risk, (home_team,)),
        ("away_turnover", fotmob.get_turnover_risk, (away_team,)),
        ("referee_info", fotmob.get_referee_info, (home_team,)),
        ("stadium_coords", fotmob.get_stadium_coordinates, (home_team,)),
        ("home_stats", fotmob.get_team_stats, (home_team,)),
        ("away_stats", fotmob.get_team_stats, (away_team,)),
        ("tactical", fotmob.get_tactical_insights, (home_team, away_team)),
    ]

    # Fase 1: Esecuzione parallela
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tutti i task
        future_to_key = {}
        for key, func, args in parallel_tasks:
            try:
                future = executor.submit(func, *args)
                future_to_key[future] = key
            except Exception as e:
                logger.warning(f"⚠️ [PARALLEL] Failed to submit {key}: {e}")
                result.failed_calls.append(key)
                result.error_details[key] = f"Submit failed: {str(e)}"

        # Raccogli risultati con timeout
        try:
            for future in concurrent.futures.as_completed(future_to_key, timeout=timeout):
                key = future_to_key[future]
                try:
                    value = future.result(timeout=DEFAULT_TIMEOUT_SECONDS)

                    # Assegna al campo corretto
                    if key == "home_context":
                        result.home_context = value or {}
                    elif key == "away_context":
                        result.away_context = value or {}
                    elif key == "home_turnover":
                        result.home_turnover = value
                    elif key == "away_turnover":
                        result.away_turnover = value
                    elif key == "referee_info":
                        result.referee_info = value
                    elif key == "stadium_coords":
                        result.stadium_coords = value
                    elif key == "home_stats":
                        result.home_stats = value or {}
                    elif key == "away_stats":
                        result.away_stats = value or {}
                    elif key == "tactical":
                        result.tactical = value or {}

                    result.successful_calls += 1
                    logger.debug(f"✅ [PARALLEL] {key} completed")

                except concurrent.futures.TimeoutError:
                    logger.warning(f"⚠️ [PARALLEL] {key} timed out")
                    result.failed_calls.append(key)
                    result.error_details[key] = (
                        "TimeoutError: Task timed out after {DEFAULT_TIMEOUT_SECONDS}s"
                    )
                except Exception as e:
                    logger.warning(f"⚠️ [PARALLEL] {key} failed: {e}")
                    result.failed_calls.append(key)
                    result.error_details[key] = f"{type(e).__name__}: {str(e)}"

        except concurrent.futures.TimeoutError:
            logger.warning(f"⚠️ [PARALLEL] Total timeout ({timeout}s) exceeded")
            # Cancella i future rimanenti
            for future in future_to_key:
                future.cancel()

    # Early exit mechanism: if >50% of parallel tasks failed, skip weather phase
    # This prevents wasting time on weather lookup when most enrichment data is unavailable
    total_parallel_tasks = len(parallel_tasks)
    if total_parallel_tasks > 0:
        failure_rate = len(result.failed_calls) / total_parallel_tasks
        if failure_rate > 0.5:
            logger.warning(
                f"⚠️ [PARALLEL] Early exit: {failure_rate * 100:.0f}% of tasks failed "
                f"({len(result.failed_calls)}/{total_parallel_tasks}), skipping weather phase"
            )
            # Skip weather phase if >50% failures
            weather_provider = None

    # Fase 2: Weather (dipende da stadium_coords) - sequenziale
    if result.stadium_coords and weather_provider and match_start_time:
        try:
            lat, lon = result.stadium_coords
            result.weather_impact = weather_provider(lat, lon, match_start_time)
            if result.weather_impact:
                result.successful_calls += 1
                logger.debug("✅ [PARALLEL] weather completed")
        except Exception as e:
            logger.warning(f"⚠️ [PARALLEL] weather failed: {e}")
            result.failed_calls.append("weather")
            result.error_details["weather"] = f"{type(e).__name__}: {str(e)}"

    # Calcola tempo totale
    elapsed_ms = int((time.time() - start_time) * 1000)
    result.enrichment_time_ms = elapsed_ms

    # Log summary
    total_tasks = len(parallel_tasks) + (1 if weather_provider else 0)
    logger.info(
        f"⚡ [PARALLEL] Completed in {elapsed_ms}ms: "
        f"{result.successful_calls}/{total_tasks} successful"
    )

    if result.failed_calls:
        logger.warning(f"⚠️ [PARALLEL] Failed calls: {result.failed_calls}")

    return result
