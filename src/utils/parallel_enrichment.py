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
import logging
import concurrent.futures
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, Callable

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_MAX_WORKERS = 4  # Bilanciato per rate limiting FotMob
DEFAULT_TIMEOUT_SECONDS = 30  # Timeout per singola chiamata
TOTAL_TIMEOUT_SECONDS = 45  # Timeout totale per tutte le chiamate


@dataclass
class EnrichmentResult:
    """
    Risultato dell'enrichment parallelizzato per un match.
    
    Contiene tutti i dati raccolti dalle varie fonti,
    con fallback a valori vuoti se una fonte fallisce.
    """
    # Team contexts (injuries, motivation, fatigue)
    home_context: Dict[str, Any] = field(default_factory=dict)
    away_context: Dict[str, Any] = field(default_factory=dict)
    
    # Turnover risk
    home_turnover: Optional[Dict[str, Any]] = None
    away_turnover: Optional[Dict[str, Any]] = None
    
    # Referee info
    referee_info: Optional[Dict[str, Any]] = None
    
    # Stadium and weather
    stadium_coords: Optional[Tuple[float, float]] = None
    weather_impact: Optional[Dict[str, Any]] = None
    
    # Team stats (goals, cards, corners)
    home_stats: Dict[str, Any] = field(default_factory=dict)
    away_stats: Dict[str, Any] = field(default_factory=dict)
    
    # Tactical insights
    tactical: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    enrichment_time_ms: int = 0
    failed_calls: list = field(default_factory=list)
    successful_calls: int = 0
    
    def has_injuries(self) -> bool:
        """Check if any team has injuries."""
        home_injuries = self.home_context.get('injuries', [])
        away_injuries = self.away_context.get('injuries', [])
        return bool(home_injuries) or bool(away_injuries)
    
    def has_high_turnover(self) -> bool:
        """Check if any team has HIGH turnover risk."""
        home_high = (
            self.home_turnover is not None and 
            self.home_turnover.get('risk_level') == 'HIGH'
        )
        away_high = (
            self.away_turnover is not None and 
            self.away_turnover.get('risk_level') == 'HIGH'
        )
        return home_high or away_high
    
    def get_summary(self) -> str:
        """Get human-readable summary of enrichment."""
        parts = []
        
        if self.has_injuries():
            home_count = len(self.home_context.get('injuries', []))
            away_count = len(self.away_context.get('injuries', []))
            parts.append(f"Injuries: H={home_count}, A={away_count}")
        
        if self.has_high_turnover():
            parts.append("HIGH TURNOVER detected")
        
        if self.referee_info and self.referee_info.get('name'):
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
    timeout: int = TOTAL_TIMEOUT_SECONDS
) -> EnrichmentResult:
    """
    Esegue enrichment parallelizzato per un match.
    
    Riduce il tempo di elaborazione da ~15s a ~3-4s parallelizzando
    le chiamate FotMob indipendenti.
    
    Args:
        fotmob: FotMobProvider instance
        home_team: Nome squadra casa (già validato)
        away_team: Nome squadra trasferta (già validato)
        match_start_time: Orario partita per weather (opzionale)
        weather_provider: Funzione get_match_weather (opzionale)
        max_workers: Numero massimo di thread paralleli
        timeout: Timeout totale in secondi
        
    Returns:
        EnrichmentResult con tutti i dati raccolti
        
    Thread Safety:
        - FotMob ha già rate limiting thread-safe interno
        - Ogni chiamata è indipendente (no shared state)
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
        ('home_context', fotmob.get_full_team_context, (home_team,)),
        ('away_context', fotmob.get_full_team_context, (away_team,)),
        ('home_turnover', fotmob.get_turnover_risk, (home_team,)),
        ('away_turnover', fotmob.get_turnover_risk, (away_team,)),
        ('referee_info', fotmob.get_referee_info, (home_team,)),
        ('stadium_coords', fotmob.get_stadium_coordinates, (home_team,)),
        ('home_stats', fotmob.get_team_stats, (home_team,)),
        ('away_stats', fotmob.get_team_stats, (away_team,)),
        ('tactical', fotmob.get_tactical_insights, (home_team, away_team)),
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
        
        # Raccogli risultati con timeout
        try:
            for future in concurrent.futures.as_completed(future_to_key, timeout=timeout):
                key = future_to_key[future]
                try:
                    value = future.result(timeout=DEFAULT_TIMEOUT_SECONDS)
                    
                    # Assegna al campo corretto
                    if key == 'home_context':
                        result.home_context = value or {}
                    elif key == 'away_context':
                        result.away_context = value or {}
                    elif key == 'home_turnover':
                        result.home_turnover = value
                    elif key == 'away_turnover':
                        result.away_turnover = value
                    elif key == 'referee_info':
                        result.referee_info = value
                    elif key == 'stadium_coords':
                        result.stadium_coords = value
                    elif key == 'home_stats':
                        result.home_stats = value or {}
                    elif key == 'away_stats':
                        result.away_stats = value or {}
                    elif key == 'tactical':
                        result.tactical = value or {}
                    
                    result.successful_calls += 1
                    logger.debug(f"✅ [PARALLEL] {key} completed")
                    
                except concurrent.futures.TimeoutError:
                    logger.warning(f"⚠️ [PARALLEL] {key} timed out")
                    result.failed_calls.append(key)
                except Exception as e:
                    logger.warning(f"⚠️ [PARALLEL] {key} failed: {e}")
                    result.failed_calls.append(key)
                    
        except concurrent.futures.TimeoutError:
            logger.warning(f"⚠️ [PARALLEL] Total timeout ({timeout}s) exceeded")
            # Cancella i future rimanenti
            for future in future_to_key:
                future.cancel()
    
    # Fase 2: Weather (dipende da stadium_coords) - sequenziale
    if result.stadium_coords and weather_provider and match_start_time:
        try:
            lat, lon = result.stadium_coords
            result.weather_impact = weather_provider(lat, lon, match_start_time)
            if result.weather_impact:
                result.successful_calls += 1
                logger.debug(f"✅ [PARALLEL] weather completed")
        except Exception as e:
            logger.warning(f"⚠️ [PARALLEL] weather failed: {e}")
            result.failed_calls.append('weather')
    
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


def enrich_match_sequential(
    fotmob,
    home_team: str,
    away_team: str,
    match_start_time: Optional[datetime] = None,
    weather_provider: Optional[Callable] = None
) -> EnrichmentResult:
    """
    Fallback sequenziale per enrichment (per debug o rate limiting).
    
    Stesso output di enrich_match_parallel ma eseguito in serie.
    Utile per confronto performance o quando il parallelismo causa problemi.
    """
    import time
    start_time = time.time()
    
    result = EnrichmentResult()
    
    if not fotmob or not home_team or not away_team:
        return result
    
    logger.info(f"🐢 [SEQUENTIAL] Starting enrichment for {home_team} vs {away_team}")
    
    # Esecuzione sequenziale con try/except per ogni chiamata
    try:
        result.home_context = fotmob.get_full_team_context(home_team) or {}
        result.successful_calls += 1
    except Exception as e:
        logger.warning(f"home_context failed: {e}")
        result.failed_calls.append('home_context')
    
    try:
        result.away_context = fotmob.get_full_team_context(away_team) or {}
        result.successful_calls += 1
    except Exception as e:
        logger.warning(f"away_context failed: {e}")
        result.failed_calls.append('away_context')
    
    try:
        result.home_turnover = fotmob.get_turnover_risk(home_team)
        result.successful_calls += 1
    except Exception as e:
        logger.warning(f"home_turnover failed: {e}")
        result.failed_calls.append('home_turnover')
    
    try:
        result.away_turnover = fotmob.get_turnover_risk(away_team)
        result.successful_calls += 1
    except Exception as e:
        logger.warning(f"away_turnover failed: {e}")
        result.failed_calls.append('away_turnover')
    
    try:
        result.referee_info = fotmob.get_referee_info(home_team)
        result.successful_calls += 1
    except Exception as e:
        logger.warning(f"referee_info failed: {e}")
        result.failed_calls.append('referee_info')
    
    try:
        result.stadium_coords = fotmob.get_stadium_coordinates(home_team)
        result.successful_calls += 1
    except Exception as e:
        logger.warning(f"stadium_coords failed: {e}")
        result.failed_calls.append('stadium_coords')
    
    try:
        result.home_stats = fotmob.get_team_stats(home_team) or {}
        result.successful_calls += 1
    except Exception as e:
        logger.warning(f"home_stats failed: {e}")
        result.failed_calls.append('home_stats')
    
    try:
        result.away_stats = fotmob.get_team_stats(away_team) or {}
        result.successful_calls += 1
    except Exception as e:
        logger.warning(f"away_stats failed: {e}")
        result.failed_calls.append('away_stats')
    
    try:
        result.tactical = fotmob.get_tactical_insights(home_team, away_team) or {}
        result.successful_calls += 1
    except Exception as e:
        logger.warning(f"tactical failed: {e}")
        result.failed_calls.append('tactical')
    
    # Weather (dipende da stadium_coords)
    if result.stadium_coords and weather_provider and match_start_time:
        try:
            lat, lon = result.stadium_coords
            result.weather_impact = weather_provider(lat, lon, match_start_time)
            result.successful_calls += 1
        except Exception as e:
            logger.warning(f"weather failed: {e}")
            result.failed_calls.append('weather')
    
    elapsed_ms = int((time.time() - start_time) * 1000)
    result.enrichment_time_ms = elapsed_ms
    
    logger.info(f"🐢 [SEQUENTIAL] Completed in {elapsed_ms}ms")
    
    return result
