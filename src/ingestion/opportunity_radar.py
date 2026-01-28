"""
EarlyBird Opportunity Radar - Narrative-First Intelligence

Scans high-authority local sports domains for specific narratives:
- B-Team / Reserves / Muletto
- Crisis / Unpaid Wages / Internal Conflict
- Key Player Returns

Triggers betting analysis ONLY for teams with detected narratives.

Uses DuckDuckGo (native) if available, falls back to Serper API.
"""
import os
import json
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from config.settings import SERPER_API_KEY

# Try to import search provider (DuckDuckGo)
try:
    from src.ingestion.search_provider import get_search_provider
    _DDG_AVAILABLE = True
except ImportError:
    _DDG_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============================================
# RADAR SOURCES - SUPER-LIST (Global + Local Insider)
# ============================================
RADAR_SOURCES = {
    "global": {
        "domains": ["flashscore.com", "onefootball.com", "sports.yahoo.com", "goal.com"],
        "keywords": ["second string", "reserves", "youthful side", "heavily rotated", 
                    "key players missing", "rested", "rotation expected", "B-team"],
        "language": "en"
    },
    "argentina": {
        "domains": ["ole.com.ar", "tycsports.com", "mundoalbiceleste.com", "espn.com.ar"],
        "keywords": ["equipo alternativo", "muletto", "rotación masiva", "guardará a los titulares",
                    "suplentes", "reservas", "juveniles", "crisis", "deuda"],
        "language": "es"
    },
    "brazil": {
        "domains": ["globoesporte.globo.com", "uol.com.br", "sambafoot.com", "lance.com.br"],
        "keywords": ["time misto", "poupados", "reservas", "força máxima", "desgaste físico",
                    "sub-20", "crise", "salários atrasados"],
        "language": "pt"
    },
    "turkey": {
        "domains": ["fanatik.com.tr", "turkish-football.com", "dailysabah.com", "fotomac.com.tr"],
        "keywords": ["rotasyon", "yedek ağırlıklı", "kadro dışı", "injury crisis",
                    "yedek kadro", "gençler", "B takımı", "kriz", "maaş"],
        "language": "tr"
    },
    "mexico": {
        "domains": ["mediotiempo.com", "espn.com.mx", "record.com.mx", "fmfstateofmind.com"],
        "keywords": ["rotation squad", "equipo alternativo", "descanso titulares",
                    "suplentes", "rotación", "juveniles"],
        "language": "es"
    },
    "greece": {
        "domains": ["agonasport.com", "greekcitytimes.com", "gazzetta.gr", "sport24.gr"],
        "keywords": ["rotation expected", "rested for europe", "reserves",
                    "εφεδρικοί", "ρεζέρβες", "κρίση"],
        "language": "en"
    },
    "portugal": {
        "domains": ["ojogo.pt", "abola.pt", "record.pt", "maisfutebol.iol.pt"],
        "keywords": ["suplentes", "reservas", "equipa B", "rotação",
                    "crise", "dívidas", "regresso"],
        "language": "pt"
    },
    "colombia": {
        "domains": ["eltiempo.com", "futbolred.com", "espn.com.co", "as.com"],
        "keywords": ["suplentes", "rotación", "juveniles", "nómina alterna",
                    "crisis", "deuda"],
        "language": "es"
    },
    "africa": {
        "domains": ["kingfut.com", "ghanasoccernet.com", "kickoff.com", "foot-africa.com"],
        "keywords": ["unpaid wages", "strike", "financial crisis", "second string",
                    "without key players", "player exodus", "debt"],
        "language": "en"
    },
    "asia": {
        "domains": ["scmp.com", "kleagueunited.com", "football-tribe.com", "the-afc.com"],
        "keywords": ["unpaid wages", "financial crisis", "second string", "rotation",
                    "key players missing", "youth team"],
        "language": "en"
    }
}

# Narrative types and their detection keywords (multi-language + global)
NARRATIVE_KEYWORDS = {
    "B_TEAM": [
        "second string", "reserves", "youthful side", "heavily rotated", "key players missing",
        "rotation expected", "rested", "B-team", "youth players", "fringe players",
        "squad rotation", "without key players", "youth team",
        "suplentes", "reservas", "equipo alternativo", "rotación", "juveniles",
        "equipo B", "canteranos", "nómina alterna", "muletto", "rotación masiva",
        "guardará a los titulares", "descanso titulares",
        "time misto", "reservas", "poupados", "sub-20", "time B", "garotos",
        "força máxima", "desgaste físico",
        "yedek kadro", "rotasyon", "gençler", "B takımı", "altyapı",
        "yedek ağırlıklı", "kadro dışı",
        "riserve", "turnover", "primavera", "seconde linee"
    ],
    "CRISIS": [
        "unpaid wages", "financial crisis", "strike", "debt", "internal conflict",
        "player exodus", "wage dispute", "ownership crisis", "bankruptcy",
        "crisis", "deuda", "conflicto", "paro", "salarios impagos", "problemas internos",
        "crise", "salários atrasados", "dívida", "conflito", "greve",
        "kriz", "maaş", "borç", "iç sorunlar", "grev",
        "crisi", "stipendi", "debiti", "conflitto interno"
    ],
    "KEY_RETURN": [
        "regresa", "vuelve", "recuperado", "disponible", "alta médica",
        "volta", "retorna", "recuperado", "liberado", "pronto",
        "döndü", "geri geldi", "iyileşti", "hazır",
        "returns", "back", "recovered", "fit again", "available",
        "rientra", "torna", "recuperato", "disponibile"
    ]
}

# State file for processed URLs
PROCESSED_URLS_FILE = Path("data/radar_processed_urls.json")


class OpportunityRadar:
    """
    Narrative-First Intelligence Scanner.
    
    Scans high-authority local domains for B-Team/Crisis narratives
    and triggers betting analysis for affected teams.
    """
    
    SERPER_URL = "https://google.serper.dev/search"
    
    def __init__(self):
        self.processed_urls = self._load_processed_urls()
        self._fotmob = None
        logger.info("🎯 Opportunity Radar initialized")
    
    @property
    def fotmob(self):
        """Lazy load FotMob provider."""
        if self._fotmob is None:
            from src.ingestion.data_provider import get_data_provider
            self._fotmob = get_data_provider()
        return self._fotmob
    
    def _load_processed_urls(self) -> Dict:
        """Load processed URLs from state file."""
        try:
            if PROCESSED_URLS_FILE.exists():
                with open(PROCESSED_URLS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
                    return {k: v for k, v in data.items() if v.get('timestamp', '') > cutoff}
            return {}
        except Exception as e:
            logger.warning(f"Could not load processed URLs: {e}")
            return {}
    
    def _save_processed_urls(self):
        """Save processed URLs to state file."""
        try:
            PROCESSED_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(PROCESSED_URLS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.processed_urls, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not save processed URLs: {e}")
    
    def _mark_url_processed(self, url: str, team: str, narrative_type: str):
        """Mark URL as processed."""
        self.processed_urls[url] = {
            'team': team,
            'type': narrative_type,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        self._save_processed_urls()

    def _build_search_query(self, region: str, config: Dict) -> str:
        """Build Serper search query for a region."""
        site_filter = " OR ".join([f"site:{d}" for d in config['domains'][:3]])
        keywords = " OR ".join([f'"{k}"' for k in config['keywords'][:4]])
        query = f"({site_filter}) ({keywords})"
        return query
    
    def _search_region(self, region: str, config: Dict) -> List[Dict]:
        """Search a specific region for narratives."""
        if _DDG_AVAILABLE:
            try:
                provider = get_search_provider()
                if provider.is_available():
                    logger.info(f"🔍 [DDG] Scanning {region.upper()}...")
                    
                    domains = config['domains'][:3]
                    keywords = config['keywords'][:4]
                    
                    ddg_results = provider.search_local_news(
                        team_name="",
                        domains=domains,
                        keywords=keywords,
                        num_results=5
                    )
                    
                    results = []
                    for item in ddg_results:
                        results.append({
                            'title': item.get('title', ''),
                            'snippet': item.get('snippet', ''),
                            'link': item.get('link', ''),
                            'source': item.get('source', 'DuckDuckGo'),
                            'region': region,
                            'language': config['language']
                        })
                    
                    logger.info(f"🔍 [{region.upper()}] Found {len(results)} results via DDG")
                    return results
            except Exception as e:
                logger.warning(f"DDG failed for {region}: {e}, falling back to Serper")
        
        if not SERPER_API_KEY or SERPER_API_KEY == "YOUR_SERPER_API_KEY":
            logger.warning("No search backend available")
            return []
        
        try:
            from src.processing.news_hunter import _SERPER_CREDITS_EXHAUSTED
            if _SERPER_CREDITS_EXHAUSTED:
                return []
        except ImportError as e:
            logger.debug(f"Could not import _SERPER_CREDITS_EXHAUSTED: {e}")
        
        query = self._build_search_query(region, config)
        
        headers = {
            'X-API-KEY': SERPER_API_KEY,
            'Content-Type': 'application/json'
        }
        
        payload = {
            "q": query,
            "tbs": "qdr:d",
            "num": 5,
            "gl": config['language'][:2] if len(config['language']) >= 2 else "us"
        }
        
        try:
            response = requests.post(self.SERPER_URL, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get('organic', []):
                results.append({
                    'title': item.get('title', ''),
                    'snippet': item.get('snippet', ''),
                    'link': item.get('link', ''),
                    'source': item.get('source', ''),
                    'region': region,
                    'language': config['language']
                })
            
            logger.info(f"🔍 [{region.upper()}] Found {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Search error for {region}: {e}")
            return []

    def _extract_narrative_with_ai(self, title: str, snippet: str) -> Optional[Dict]:
        """Use DeepSeek to extract team name and narrative type from news."""
        from src.analysis.analyzer import call_deepseek, extract_json_from_response
        
        prompt = f"""Analyze this football news headline and snippet.

TITLE: {title}
SNIPPET: {snippet}

TASK: Extract the football TEAM NAME and determine if this is about:
1. B_TEAM: Reserves, rotation, youth players, second string lineup
2. CRISIS: Unpaid wages, internal conflict, debt, strike
3. KEY_RETURN: Important player returning from injury/suspension

OUTPUT (strict JSON only):
{{
  "team": "Full Team Name (e.g., 'Boca Juniors', not just 'Boca')",
  "type": "B_TEAM" or "CRISIS" or "KEY_RETURN" or "NONE",
  "confidence": 0-10 (how certain you are this is about reserves/crisis/return),
  "summary": "One sentence summary in English of the narrative"
}}

RULES:
- If multiple teams mentioned, pick the one AFFECTED by the narrative
- If no clear B-Team/Crisis/Return narrative, set type to "NONE"
- Confidence 8+ means you're very sure about team AND narrative type
- Output ONLY JSON, no explanation"""

        try:
            messages = [
                {"role": "system", "content": "You extract football team names and narrative types from news. Output only JSON."},
                {"role": "user", "content": prompt}
            ]
            
            response_content, _ = call_deepseek(messages, include_reasoning=False)
            data = extract_json_from_response(response_content)
            
            team = data.get('team', '').strip()
            narrative_type = data.get('type', 'NONE')
            confidence = data.get('confidence', 0)
            summary = data.get('summary', '')
            
            if team and narrative_type != 'NONE' and confidence >= 7:
                logger.info(f"🎯 AI Extraction: {team} | {narrative_type} | Conf: {confidence}")
                return {
                    'team': team,
                    'type': narrative_type,
                    'confidence': confidence,
                    'summary': summary
                }
            
            return None
            
        except Exception as e:
            logger.error(f"AI extraction failed: {e}")
            return None
    
    def _resolve_team_name(self, team_name: str) -> Tuple[Optional[int], Optional[str]]:
        """Resolve team name to FotMob ID using fuzzy matching."""
        try:
            team_id, fotmob_name = self.fotmob.search_team_id(team_name)
            if team_id:
                logger.info(f"✅ Resolved: '{team_name}' → '{fotmob_name}' (ID: {team_id})")
                return team_id, fotmob_name
            return None, None
        except Exception as e:
            logger.error(f"Team resolution failed for '{team_name}': {e}")
            return None, None
    
    def _get_next_match_for_team(self, team_id: int, team_name: str) -> Optional[Dict]:
        """Get the next match for a team from FotMob."""
        try:
            team_data = self.fotmob.get_team_details(team_id)
            if not team_data:
                return None
            
            next_match = team_data.get('nextMatch')
            if not next_match:
                fixtures = team_data.get('fixtures', {})
                next_match = fixtures.get('allFixtures', {}).get('nextMatch')
            
            if not next_match:
                logger.info(f"⚠️ No upcoming match for {team_name}")
                return None
            
            opponent = next_match.get('opponent', {})
            match_time_str = next_match.get('utcTime', '')
            
            match_time = None
            if match_time_str:
                try:
                    match_time = datetime.fromisoformat(match_time_str.replace('Z', '+00:00'))
                except:
                    pass
            
            is_home = next_match.get('home', True)
            
            return {
                'match_id': next_match.get('id'),
                'opponent_name': opponent.get('name', 'Unknown'),
                'opponent_id': opponent.get('id'),
                'match_time': match_time,
                'is_home': is_home,
                'competition': next_match.get('tournament', {}).get('name', 'Unknown')
            }
            
        except Exception as e:
            logger.error(f"Error getting next match for {team_name}: {e}")
            return None
    
    def _find_or_create_match_in_db(self, team_name: str, match_info: Dict, narrative: Dict) -> Optional[str]:
        """Find existing match in DB or create a placeholder for radar-triggered analysis."""
        from src.database.models import Match, SessionLocal
        
        db = SessionLocal()
        try:
            is_home = match_info.get('is_home', True)
            opponent_name = match_info.get('opponent_name', 'Unknown')
            
            if is_home:
                home_team = team_name
                away_team = opponent_name
            else:
                home_team = opponent_name
                away_team = team_name
            
            existing = db.query(Match).filter(
                Match.home_team == home_team,
                Match.away_team == away_team
            ).first()
            
            if existing:
                logger.info(f"📋 Found existing match: {existing.id}")
                return existing.id
            
            match_id = f"radar_{home_team}_{away_team}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
            match_id = match_id.replace(' ', '_').lower()
            
            new_match = Match(
                id=match_id,
                home_team=home_team,
                away_team=away_team,
                league=match_info.get('competition', 'Unknown'),
                start_time=match_info.get('match_time') or datetime.now(timezone.utc) + timedelta(hours=48),
            )
            
            db.add(new_match)
            db.commit()
            
            logger.info(f"📝 Created radar match: {match_id}")
            return match_id
            
        except Exception as e:
            logger.error(f"DB error: {e}")
            db.rollback()
            return None
        finally:
            db.close()
    
    def trigger_pipeline(self, team_name: str, narrative_type: str, summary: str, url: str):
        """Trigger the betting analysis pipeline for a team with detected narrative."""
        logger.info(f"🚀 RADAR TRIGGER: {team_name} | {narrative_type}")
        logger.info(f"   📰 {summary}")
        
        team_id, canonical_name = self._resolve_team_name(team_name)
        if not team_id:
            logger.warning(f"⚠️ Could not resolve team: {team_name}")
            return
        
        match_info = self._get_next_match_for_team(team_id, canonical_name)
        if not match_info:
            logger.warning(f"⚠️ No upcoming match for {canonical_name}")
            return
        
        match_id = self._find_or_create_match_in_db(canonical_name, match_info, {
            'type': narrative_type,
            'summary': summary
        })
        
        if not match_id:
            logger.error(f"❌ Could not create match entry for {canonical_name}")
            return
        
        forced_narrative = self._build_forced_narrative(narrative_type, summary, url, canonical_name)
        
        try:
            import importlib
            main_module = importlib.import_module('src.main')
            analyze_fn = getattr(main_module, 'analyze_single_match', None)
            if analyze_fn:
                analyze_fn(match_id, forced_narrative=forced_narrative)
                logger.info(f"✅ Pipeline triggered for {canonical_name}")
            else:
                logger.warning("analyze_single_match not found in main.py")
        except ImportError:
            logger.warning("analyze_single_match not yet implemented in main.py")
        except Exception as e:
            logger.error(f"Pipeline trigger failed: {e}")
    
    def _build_forced_narrative(self, narrative_type: str, summary: str, url: str, team_name: str) -> str:
        """Build the forced narrative string for AI injection."""
        type_labels = {
            'B_TEAM': '🔄 MULETTO/RISERVE ALERT',
            'CRISIS': '⚠️ CRISI INTERNA ALERT', 
            'KEY_RETURN': '🔙 RITORNO CHIAVE ALERT'
        }
        
        label = type_labels.get(narrative_type, '📰 RADAR INTEL')
        
        narrative = f"""
{label} - RADAR DETECTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 TEAM: {team_name}
📊 TYPE: {narrative_type}
📝 INTEL: {summary}
🔗 SOURCE: {url}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚡ CRITICAL INTELLIGENCE - This narrative was detected by the Opportunity Radar.
Factor this HEAVILY into your analysis. This is PRE-MARKET intelligence.
"""
        return narrative
    
    def scan(self, regions: List[str] = None) -> List[Dict]:
        """Main scan method - searches all configured regions for narratives."""
        logger.info("🎯 OPPORTUNITY RADAR SCAN STARTING...")
        
        if regions is None:
            regions = list(RADAR_SOURCES.keys())
        
        triggered = []
        
        for region in regions:
            if region not in RADAR_SOURCES:
                logger.warning(f"Unknown region: {region}")
                continue
            
            config = RADAR_SOURCES[region]
            logger.info(f"🔍 Scanning {region.upper()}...")
            
            results = self._search_region(region, config)
            
            for result in results:
                url = result.get('link', '')
                
                if url in self.processed_urls:
                    continue
                
                title = result.get('title', '')
                snippet = result.get('snippet', '')
                
                text_lower = (title + ' ' + snippet).lower()
                has_narrative_keyword = any(
                    kw.lower() in text_lower 
                    for keywords in NARRATIVE_KEYWORDS.values() 
                    for kw in keywords
                )
                
                if not has_narrative_keyword:
                    continue
                
                extraction = self._extract_narrative_with_ai(title, snippet)
                
                if extraction and extraction.get('confidence', 0) >= 7:
                    team = extraction.get('team')
                    narrative_type = extraction.get('type')
                    summary = extraction.get('summary', '')
                    
                    if not team or not narrative_type:
                        logger.debug(f"Skipping extraction with missing team/type: {extraction}")
                        continue
                    
                    self._mark_url_processed(url, team, narrative_type)
                    
                    self.trigger_pipeline(team, narrative_type, summary, url)
                    
                    triggered.append({
                        'team': team,
                        'type': narrative_type,
                        'summary': summary,
                        'url': url,
                        'region': region
                    })
        
        logger.info(f"🎯 RADAR SCAN COMPLETE: {len(triggered)} opportunities triggered")
        return triggered


_radar_instance = None


def get_radar() -> OpportunityRadar:
    """Get or create the singleton radar instance."""
    global _radar_instance
    if _radar_instance is None:
        _radar_instance = OpportunityRadar()
    return _radar_instance


def run_radar_scan(regions: List[str] = None) -> List[Dict]:
    """Convenience function to run a radar scan."""
    radar = get_radar()
    return radar.scan(regions)
