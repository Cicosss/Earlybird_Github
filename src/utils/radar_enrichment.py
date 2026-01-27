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
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Configuration
MATCH_LOOKAHEAD_HOURS = 48  # Cerca partite nelle prossime 48h
END_OF_SEASON_ROUNDS = 5    # Ultime 5 giornate = fine stagione


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
    biscotto_severity: Optional[str] = None
    current_draw_odd: Optional[float] = None
    
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
            "Unknown": "Sconosciuto"
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
            from src.analysis.biscotto_engine import analyze_biscotto, BiscottoSeverity
            self._biscotto_available = True
        except ImportError:
            logger.warning("⚠️ [RADAR-ENRICH] Biscotto engine not available")
    
    def find_upcoming_match(
        self, 
        team_name: str, 
        hours: int = MATCH_LOOKAHEAD_HOURS
    ) -> Optional[Dict]:
        """
        Cerca una partita nelle prossime N ore per la squadra specificata.
        
        Args:
            team_name: Nome della squadra (può essere parziale)
            hours: Finestra temporale in ore
            
        Returns:
            Dict con info match o None se non trovato
        """
        if not self._db_available or not team_name:
            return None
        
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
                matches = db.query(Match).filter(
                    Match.start_time >= now_naive,
                    Match.start_time <= end_window
                ).all()
                
                # Cerca match che coinvolge la squadra
                for match in matches:
                    home_lower = (match.home_team or "").lower()
                    away_lower = (match.away_team or "").lower()
                    
                    # Match fuzzy: controlla se team_name è contenuto
                    if (team_lower in home_lower or 
                        home_lower in team_lower or
                        team_lower in away_lower or 
                        away_lower in team_lower):
                        
                        logger.info(f"🔍 [RADAR-ENRICH] Found match: {match.home_team} vs {match.away_team}")
                        
                        return {
                            "match_id": match.id,
                            "home_team": match.home_team,
                            "away_team": match.away_team,
                            "start_time": match.start_time,
                            "league": match.league,
                            "current_draw_odd": match.current_draw_odd,
                            "opening_draw_odd": match.opening_draw_odd,
                            "is_home": team_lower in home_lower
                        }
                
                return None
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ [RADAR-ENRICH] Error finding match: {e}")
            return None
    
    def get_team_context_light(self, team_name: str) -> Dict:
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
            "source": "none"
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
    
    def check_biscotto_light(
        self, 
        match_info: Dict, 
        team_context: Dict
    ) -> Tuple[bool, Optional[str]]:
        """
        Check biscotto in modo light usando dati già disponibili.
        
        Args:
            match_info: Dict dal find_upcoming_match
            team_context: Dict dal get_team_context_light
            
        Returns:
            Tuple (is_suspect, severity_string)
        """
        if not self._biscotto_available:
            return False, None
        
        # Solo se fine stagione
        matches_remaining = team_context.get("matches_remaining")
        if matches_remaining is None or matches_remaining > END_OF_SEASON_ROUNDS:
            return False, None
        
        # Solo se abbiamo quote draw
        current_draw = match_info.get("current_draw_odd")
        if not current_draw:
            return False, None
        
        try:
            from src.analysis.biscotto_engine import analyze_biscotto, BiscottoSeverity
            
            # Crea motivation dict dal context
            motivation = {
                "zone": team_context.get("zone", "Unknown"),
                "position": team_context.get("position", 0),
                "total_teams": team_context.get("total_teams", 20),
                "matches_remaining": matches_remaining
            }
            
            analysis = analyze_biscotto(
                home_team=match_info.get("home_team", ""),
                away_team=match_info.get("away_team", ""),
                current_draw_odd=current_draw,
                opening_draw_odd=match_info.get("opening_draw_odd"),
                home_motivation=motivation if match_info.get("is_home") else None,
                away_motivation=motivation if not match_info.get("is_home") else None,
                matches_remaining=matches_remaining,
                league_key=match_info.get("league")
            )
            
            if analysis.is_suspect:
                return True, analysis.severity.value
            
            return False, None
            
        except Exception as e:
            logger.debug(f"⚠️ [RADAR-ENRICH] Biscotto check failed: {e}")
            return False, None
    
    def enrich(self, affected_team: str) -> EnrichmentContext:
        """
        Arricchisci un alert con contesto dal database.
        
        Metodo principale da chiamare dal News Radar.
        
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
        
        # Step 3: Check biscotto se fine stagione
        if context.is_end_of_season():
            is_suspect, severity = self.check_biscotto_light(match_info, team_context)
            context.is_biscotto_suspect = is_suspect
            context.biscotto_severity = severity
        
        logger.info(
            f"✨ [RADAR-ENRICH] Enriched {affected_team}: "
            f"{context.team_zone}, match in {context.match_time}"
        )
        
        return context


# Singleton instance
_enricher_instance: Optional[RadarLightEnricher] = None


def get_radar_enricher() -> RadarLightEnricher:
    """
    Get singleton instance of RadarLightEnricher.
    
    Returns:
        RadarLightEnricher instance
    """
    global _enricher_instance
    
    if _enricher_instance is None:
        _enricher_instance = RadarLightEnricher()
        logger.info("✅ [RADAR-ENRICH] Enricher initialized")
    
    return _enricher_instance


async def enrich_radar_alert_async(affected_team: str) -> EnrichmentContext:
    """
    Async wrapper per l'enrichment (per compatibilità con news_radar async).
    
    Args:
        affected_team: Nome della squadra dall'alert
        
    Returns:
        EnrichmentContext con tutti i dati disponibili
    """
    import asyncio
    
    enricher = get_radar_enricher()
    
    # Esegui in thread pool per non bloccare event loop
    # (le query DB sono sync)
    loop = asyncio.get_event_loop()
    context = await loop.run_in_executor(None, enricher.enrich, affected_team)
    
    return context
