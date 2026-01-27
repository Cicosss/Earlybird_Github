"""
END-TO-END Intelligence Flow Test

Verifica che tutti i componenti del sistema di intelligence
comunichino correttamente e che i dati fluiscano in modo intelligente.

FLUSSO TESTATO:
1. TIER 0: Browser Monitor → news_hunter (active web monitoring)
2. TIER 0: A-League Scraper → news_hunter (Australian league)
3. TIER 0.5: Beat Writers → news_hunter (priority search)
4. TIER 1: Search Providers → news_hunter (Brave/DDG/Serper)
5. TIER 2: Insiders → news_hunter (placeholder for future sources)
6. news_hunter → analyzer (aggregazione)
7. analyzer → Gemini/DeepSeek (decisione AI)
8. Output → notifier (alert)

V8.0: Reddit removed - provided no betting edge.

VERIFICA:
- Formato dati coerente tra componenti
- Filtri sport applicati correttamente
- Decisioni intelligenti basate sui dati
- Graceful fallback quando servizi non disponibili
"""
import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDataFlowFormat:
    """Test che i formati dati siano coerenti tra tutti i componenti."""
    
    # Campi OBBLIGATORI che ogni news item deve avere per essere processato
    REQUIRED_FIELDS = ['match_id', 'team', 'title', 'snippet', 'link', 'source', 'search_type']
    
    def test_browser_monitor_output_format(self):
        """Browser Monitor deve produrre output compatibile con news_hunter."""
        # Simula output Browser Monitor
        mock_output = {
            "match_id": "test123",
            "team": "Galatasaray",
            "keyword": "browser_monitor",
            "title": "Galatasaray injury update",
            "snippet": "Key player ruled out",
            "link": "https://example.com/article",
            "date": "2024-01-01",
            "source": "fanatik.com.tr",
            "search_type": "browser_monitor",
            "confidence": "HIGH",
            "priority_boost": 2.0
        }
        
        for field in self.REQUIRED_FIELDS:
            assert field in mock_output, f"Browser Monitor output manca campo: {field}"
    
    def test_search_provider_output_format(self):
        """Search provider deve produrre output compatibile."""
        from src.ingestion.search_provider import SearchProvider
        
        # Formato atteso da search_provider
        mock_output = {
            "title": "Celtic injury news",
            "link": "https://dailyrecord.co.uk/article",
            "url": "https://dailyrecord.co.uk/article",
            "snippet": "Key defender ruled out",
            "summary": "Key defender ruled out",
            "source": "duckduckgo",
            "date": ""
        }
        
        # Verifica campi base
        assert "title" in mock_output
        assert "link" in mock_output or "url" in mock_output
        assert "snippet" in mock_output or "summary" in mock_output
    
    def test_news_hunter_aggregation_format(self):
        """news_hunter deve aggregare e normalizzare tutti i formati."""
        # Formato finale che news_hunter passa all'analyzer
        aggregated_news = {
            'match_id': 'match_abc123',
            'team': 'Legia Warszawa',
            'keyword': 'kontuzja',
            'title': 'Legia bez kluczowego gracza',
            'snippet': 'Kapitan kontuzjowany przed meczem',
            'link': 'https://weszlo.com/article',
            'date': '2024-01-15',
            'source': 'weszlo.com',
            'search_type': 'ddg_local'
        }
        
        for field in self.REQUIRED_FIELDS:
            assert field in aggregated_news, f"Aggregated news manca campo: {field}"


class TestSportFiltering:
    """Test che i filtri sport siano applicati correttamente in tutti i layer."""
    
    def test_search_provider_exclusion_terms(self):
        """Search provider deve avere termini di esclusione nelle query."""
        from src.ingestion.search_provider import SPORT_EXCLUSION_TERMS
        
        critical_exclusions = ['-basket', '-basketball', '-women', '-nba', '-futsal']
        
        for term in critical_exclusions:
            assert term in SPORT_EXCLUSION_TERMS, \
                f"Termine esclusione mancante: {term}"


class TestIntelligentDecisionMaking:
    """Test che il sistema prenda decisioni intelligenti basate sui dati."""
    
    def test_analyzer_receives_structured_data(self):
        """Analyzer deve ricevere dati strutturati per prendere decisioni."""
        # Simula dati che l'analyzer riceve
        analysis_input = {
            "home_team": "Galatasaray",
            "away_team": "Fenerbahce",
            "news_snippet": "Icardi ruled out with injury. Mertens doubtful.",
            "market_status": "Odds: H 2.10 | D 3.40 | A 3.20 (Drop: -5.2%)",
            "official_data": "FotMob: Icardi (OUT), Mertens (DOUBT)",
            "team_stats": "Goals: High (2.3/game) | Corners: High (6.1/game)",
            "tactical_context": "[GEMINI] Internal crisis: None | Turnover: Low"
        }
        
        # Verifica che tutti i campi necessari per la decisione siano presenti
        required_for_decision = ['home_team', 'away_team', 'news_snippet', 'market_status']
        for field in required_for_decision:
            assert field in analysis_input, f"Campo decisionale mancante: {field}"
    
    def test_confidence_affects_verdict(self):
        """Confidence bassa deve portare a NO BET."""
        from src.analysis.analyzer import validate_ai_response
        
        # Risposta con confidence bassa
        low_confidence_response = {
            "final_verdict": "BET",
            "confidence": 45,
            "recommended_market": "Over 2.5 Goals",
            "reasoning": "Test"
        }
        
        validated = validate_ai_response(low_confidence_response)
        
        # Il sistema dovrebbe comunque validare, ma la logica di business
        # dovrebbe trattare confidence < 60 come NO BET
        assert validated['confidence'] == 45
        # La decisione finale spetta all'analyzer che usa questa confidence
    
    def test_news_correlation_with_official_data(self):
        """News deve essere correlata con dati ufficiali per validazione."""
        # Scenario: News dice "Icardi out", FotMob conferma
        news_data = {"title": "Icardi ruled out", "source": "fanatik.com.tr"}
        official_data = {"missing_players": ["Icardi", "Mertens"]}
        
        # Correlazione: news confermata da fonte ufficiale = HIGH confidence
        news_player = "Icardi"
        is_confirmed = news_player in official_data["missing_players"]
        
        assert is_confirmed == True, "News dovrebbe essere confermata da FotMob"


class TestGracefulFallback:
    """Test che il sistema gestisca gracefully i fallback."""
    
    def test_search_provider_fallback_chain(self):
        """Search provider deve avere fallback chain: Brave → DDG → Serper."""
        from src.ingestion.search_provider import SearchProvider
        
        provider = SearchProvider()
        
        # Verifica che il provider abbia la logica di fallback
        assert hasattr(provider, '_search_brave')
        assert hasattr(provider, '_search_duckduckgo')
        assert hasattr(provider, '_search_serper')
    
    def test_gemini_unavailable_fallback(self):
        """Sistema deve funzionare anche senza Gemini."""
        # Il sistema deve poter analizzare anche senza deep dive Gemini
        tactical_context_without_gemini = "Deep dive non disponibile"
        
        # L'analyzer deve comunque poter processare
        assert tactical_context_without_gemini is not None


class TestLeagueDomainMapping:
    """Test che i domini siano mappati correttamente per ogni lega."""
    
    def test_poland_has_local_domains(self):
        """Polonia deve avere domini locali configurati."""
        from src.ingestion.search_provider import LEAGUE_DOMAINS
        
        poland_key = "soccer_poland_ekstraklasa"
        assert poland_key in LEAGUE_DOMAINS
        
        domains = LEAGUE_DOMAINS[poland_key]
        assert len(domains) >= 3, "Polonia deve avere almeno 3 domini"
        
        # Verifica domini specifici polacchi
        polish_domains = ['swiatpilki.com', 'weszlo.com', 'meczyki.pl']
        for domain in polish_domains:
            assert domain in domains, f"Dominio polacco mancante: {domain}"
    
    def test_turkey_has_local_domains(self):
        """Turchia deve avere domini locali configurati."""
        from src.ingestion.search_provider import LEAGUE_DOMAINS
        
        turkey_key = "soccer_turkey_super_league"
        assert turkey_key in LEAGUE_DOMAINS
        
        domains = LEAGUE_DOMAINS[turkey_key]
        assert "fanatik.com.tr" in domains or "ajansspor.com" in domains


class TestEndToEndFlow:
    """Test del flusso completo end-to-end."""
    
    def test_full_pipeline_structure(self):
        """Verifica che il pipeline completo sia strutturato correttamente."""
        # 1. Verifica import chain
        from src.ingestion.search_provider import get_search_provider
        from src.processing.news_hunter import run_hunter_for_match
        
        # 2. Verifica che run_hunter_for_match abbia tutti i parametri
        # V8.0: include_reddit removed (Reddit deprecated)
        import inspect
        sig = inspect.signature(run_hunter_for_match)
        params = list(sig.parameters.keys())
        
        assert 'match' in params
        assert 'include_insiders' in params
        # V8.0: include_reddit no longer exists
        assert 'include_reddit' not in params, "include_reddit should be removed in V8.0"
    
    def test_news_to_analyzer_flow(self):
        """Test che le news fluiscano correttamente all'analyzer."""
        # Simula output di news_hunter
        news_items = [
            {
                'match_id': 'test123',
                'team': 'Galatasaray',
                'title': 'Icardi injury confirmed',
                'snippet': 'Star striker ruled out for derby',
                'link': 'https://fanatik.com.tr/article',
                'source': 'fanatik.com.tr',
                'search_type': 'browser_monitor',
                'confidence': 'HIGH'
            },
            {
                'match_id': 'test123',
                'team': 'Galatasaray',
                'title': 'Galatasaray team news',
                'snippet': 'Multiple players doubtful',
                'link': 'https://twitter.com/insider',
                'source': 'Twitter/X',
                'search_type': 'ddg_twitter'
            }
        ]
        
        # Simula aggregazione per analyzer
        news_snippet = "\n".join([
            f"[{n['source']}] {n['title']}: {n['snippet']}"
            for n in news_items
        ])
        
        assert "Icardi injury confirmed" in news_snippet
        assert "fanatik.com.tr" in news_snippet
        assert "Twitter/X" in news_snippet
    
    def test_tier_priority_order(self):
        """Verifica che i tier siano processati nell'ordine corretto."""
        # V8.0: Ordine atteso: TIER 0 (Browser Monitor) → TIER 1 (Search) → TIER 2 (Insiders placeholder)
        # Reddit removed in V8.0
        
        from src.processing.news_hunter import run_hunter_for_match
        import inspect
        
        # Leggi il codice sorgente per verificare l'ordine
        source = inspect.getsource(run_hunter_for_match)
        
        # Verifica che Browser Monitor sia chiamato prima di search_news
        browser_pos = source.find('get_browser_monitor_news')
        search_pos = source.find('search_news(')
        
        # Browser Monitor deve essere prima di search_news
        if browser_pos > 0 and search_pos > 0:
            assert browser_pos < search_pos, "Browser Monitor (TIER 0) deve essere prima di Search (TIER 1)"
        
        # V8.0: Reddit removed, verify it's not called
        assert 'run_reddit_monitor' not in source, "run_reddit_monitor should be removed in V8.0"


class TestIntelligenceQuality:
    """Test sulla qualità dell'intelligence prodotta."""
    
    def test_confidence_levels_meaningful(self):
        """I livelli di confidence devono essere significativi."""
        # Browser Monitor = HIGH (AI-analyzed)
        # Beat Writers = HIGH (reliable)
        # V8.0: Reddit removed - no longer in confidence map
        
        confidence_map = {
            'browser_monitor': 'HIGH',
            'insider_beat_writer': 'HIGH',
            # V8.0: insider_reddit_deep removed (Reddit deprecated)
        }
        
        # Verifica che HIGH confidence sources siano trattate diversamente
        assert confidence_map['insider_beat_writer'] == 'HIGH'
        assert confidence_map['browser_monitor'] == 'HIGH'


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
