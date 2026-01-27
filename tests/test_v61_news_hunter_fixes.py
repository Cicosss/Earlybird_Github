"""
Test V6.1 News Hunter Fixes

Verifica i fix applicati in V6.1:
1. Rimozione import json inutilizzato
2. DDG fallback per funzioni Serper-only
3. Rimozione duplicazione beat writers in search_insiders
4. Null check per match in run_hunter_for_match
5. Aggiunta egypt a COUNTRY_TO_LANG
6. Unificazione freshness tags
"""
import pytest
import inspect
from datetime import datetime, timezone


class TestV61ImportCleanup:
    """Test rimozione import inutilizzati."""
    
    def test_json_not_imported(self):
        """Verifica che json non sia più importato in news_hunter."""
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        # json non deve essere importato direttamente
        assert 'import json' not in content, "import json dovrebbe essere rimosso"


class TestV61DDGFallback:
    """Test DDG fallback per funzioni precedentemente Serper-only."""
    
    def test_search_twitter_rumors_uses_cache_v70(self):
        """V7.0: search_twitter_rumors deve usare Twitter Intel Cache invece di DDG/Serper."""
        from src.processing.news_hunter import search_twitter_rumors
        
        source = inspect.getsource(search_twitter_rumors)
        # V7.0: Non usa più search backend, usa la cache
        assert '_TWITTER_INTEL_CACHE_AVAILABLE' in source, "Deve verificare disponibilità cache"
        assert 'get_twitter_intel_cache' in source, "Deve usare get_twitter_intel_cache"
        assert '[CACHE]' in source, "Deve loggare quando usa cache"
        # Non deve più chiamare search_twitter o costruire query site:twitter.com
        assert 'search_twitter(' not in source, "Non deve chiamare search_twitter (broken)"
        assert '_get_search_backend' not in source, "Non deve usare search backend per Twitter"
    
    def test_search_dynamic_country_supports_ddg(self):
        """search_dynamic_country deve supportare DDG come backend primario."""
        from src.processing.news_hunter import search_dynamic_country
        
        source = inspect.getsource(search_dynamic_country)
        assert '_get_search_backend' in source, "Deve usare _get_search_backend"
        assert 'get_search_provider' in source, "Deve usare get_search_provider per DDG"
    
    def test_search_exotic_league_supports_ddg(self):
        """search_exotic_league deve supportare DDG come backend primario."""
        from src.processing.news_hunter import search_exotic_league
        
        source = inspect.getsource(search_exotic_league)
        assert '_get_search_backend' in source, "Deve usare _get_search_backend"
        assert 'get_search_provider' in source, "Deve usare get_search_provider per DDG"
    
    # V8.0: search_reddit_deep removed - test deprecated
    # def test_search_reddit_deep_supports_ddg(self):
    #     """search_reddit_deep deve supportare DDG come backend primario."""
    #     ...


class TestV8RedditRemoval:
    """V8.0: Test che Reddit sia stato rimosso correttamente."""
    
    def test_reddit_disabled_in_settings(self):
        """REDDIT_ENABLED deve essere False."""
        from config.settings import REDDIT_ENABLED
        assert REDDIT_ENABLED == False, "REDDIT_ENABLED deve essere False in V8.0"
    
    def test_search_insiders_returns_empty(self):
        """search_insiders deve ritornare lista vuota (placeholder)."""
        from src.processing.news_hunter import search_insiders
        
        result = search_insiders("Test Team", "soccer_turkey_super_league", "match_123")
        assert result == [], "search_insiders deve ritornare lista vuota in V8.0"
    
    def test_get_reddit_sources_returns_empty(self):
        """get_reddit_sources deve ritornare lista vuota."""
        from src.processing.sources_config import get_reddit_sources
        
        result = get_reddit_sources("soccer_turkey_super_league")
        assert result == [], "get_reddit_sources deve ritornare lista vuota in V8.0"
    
    def test_get_target_subreddits_returns_empty(self):
        """get_target_subreddits deve ritornare struttura vuota."""
        from src.processing.sources_config import get_target_subreddits
        
        result = get_target_subreddits("soccer_turkey_super_league")
        assert result == {"general": [], "teams": [], "keywords": []}, \
            "get_target_subreddits deve ritornare struttura vuota in V8.0"
    
    def test_run_hunter_no_include_reddit_param(self):
        """run_hunter_for_match non deve avere parametro include_reddit."""
        from src.processing.news_hunter import run_hunter_for_match
        import inspect
        
        sig = inspect.signature(run_hunter_for_match)
        params = list(sig.parameters.keys())
        assert 'include_reddit' not in params, "include_reddit deve essere rimosso in V8.0"


class TestV61BeatWriterDeduplication:
    """Test rimozione duplicazione beat writers."""
    
    def test_search_insiders_no_beat_writers_call(self):
        """
        search_insiders NON deve chiamare search_beat_writers.
        Beat writers sono già cercati in TIER 0.5 (search_beat_writers_priority).
        V8.0: search_insiders ora è un placeholder vuoto.
        """
        from src.processing.news_hunter import search_insiders
        
        source = inspect.getsource(search_insiders)
        
        # Non deve chiamare search_beat_writers (la funzione, non il commento)
        assert 'search_beat_writers(' not in source, \
            "search_insiders non deve chiamare search_beat_writers"
    
    def test_search_insiders_is_placeholder(self):
        """V8.0: search_insiders è ora un placeholder per future fonti."""
        from src.processing.news_hunter import search_insiders
        
        source = inspect.getsource(search_insiders)
        assert 'return []' in source, "search_insiders deve ritornare lista vuota"


class TestV61NullCheck:
    """Test null check per match."""
    
    def test_run_hunter_for_match_handles_none(self):
        """run_hunter_for_match deve gestire match=None senza crash."""
        from src.processing.news_hunter import run_hunter_for_match
        
        result = run_hunter_for_match(None)
        assert result == [], "Deve ritornare lista vuota per match=None"
    
    def test_run_hunter_for_match_has_null_check(self):
        """run_hunter_for_match deve avere un null check esplicito."""
        from src.processing.news_hunter import run_hunter_for_match
        
        source = inspect.getsource(run_hunter_for_match)
        assert 'if match is None' in source, "Deve avere null check esplicito"


class TestV61CountryToLang:
    """Test completezza COUNTRY_TO_LANG."""
    
    def test_egypt_in_country_to_lang(self):
        """COUNTRY_TO_LANG deve includere egypt."""
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        assert "'egypt': 'ar'" in content, "egypt deve essere mappato ad 'ar'"


class TestV61FreshnessTags:
    """Test unificazione freshness tags."""
    
    def test_no_recent_tag(self):
        """Non deve usare il tag '⏰ RECENT' (non supportato da decay_v2)."""
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        # RECENT non deve essere usato come tag
        assert '⏰ RECENT' not in content, "Tag RECENT non deve essere usato"
    
    def test_no_warning_stale_tag(self):
        """Non deve usare '⚠️ STALE' (deve essere '📜 STALE')."""
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        # ⚠️ STALE non deve essere usato
        assert '⚠️ STALE' not in content, "Deve usare 📜 STALE, non ⚠️ STALE"
    
    def test_unified_tags_used(self):
        """Deve usare i tag unificati: 🔥 FRESH, ⏰ AGING, 📜 STALE."""
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        assert '🔥 FRESH' in content, "Deve usare tag FRESH"
        assert '⏰ AGING' in content, "Deve usare tag AGING"
        assert '📜 STALE' in content, "Deve usare tag STALE"
    
    def test_freshness_tags_match_decay_v2(self):
        """
        I tag devono corrispondere a quelli di apply_news_decay_v2.
        
        V1.1 FIX: Tags are now TIME-BASED (not decay-based) for consistency
        with news_hunter.py:
        - < 60 min = FRESH
        - 60-360 min = AGING  
        - > 360 min = STALE
        """
        from src.analysis.market_intelligence import apply_news_decay_v2
        
        # Test che decay_v2 restituisca i tag attesi basati su TEMPO (non decay_factor)
        # V1.1: Cambiato da decay-based a time-based per consistenza
        
        _, tag_fresh = apply_news_decay_v2(10.0, 5)    # 5 min -> FRESH (< 60)
        _, tag_fresh_30 = apply_news_decay_v2(10.0, 30)  # 30 min -> FRESH (< 60)
        _, tag_aging = apply_news_decay_v2(10.0, 120)  # 2 hours -> AGING (60-360)
        _, tag_stale = apply_news_decay_v2(10.0, 400)  # 6h40m -> STALE (> 360)
        
        assert tag_fresh == '🔥 FRESH', f"Expected FRESH for 5min, got {tag_fresh}"
        assert tag_fresh_30 == '🔥 FRESH', f"Expected FRESH for 30min, got {tag_fresh_30}"
        assert tag_aging == '⏰ AGING', f"Expected AGING for 120min, got {tag_aging}"
        assert tag_stale == '📜 STALE', f"Expected STALE for 400min, got {tag_stale}"


class TestV61EdgeCases:
    """Test edge cases per i fix V6.1."""
    
    def test_search_twitter_rumors_empty_team(self):
        """search_twitter_rumors deve gestire team vuoto."""
        from src.processing.news_hunter import search_twitter_rumors
        
        # Non deve crashare con team vuoto
        result = search_twitter_rumors("", "soccer_argentina_primera_division", "match_123")
        assert isinstance(result, list), "Deve ritornare una lista"
    
    # V8.0: search_reddit_deep removed
    # def test_search_reddit_deep_no_subreddits(self):
    #     """search_reddit_deep deve gestire league senza subreddits."""
    #     ...
    
    def test_search_insiders_returns_list(self):
        """search_insiders deve sempre ritornare una lista."""
        from src.processing.news_hunter import search_insiders
        
        result = search_insiders("Test Team", "soccer_unknown_league", "match_123")
        assert isinstance(result, list), "Deve ritornare una lista"
    
    def test_search_insiders_returns_empty_v8(self):
        """V8.0: search_insiders deve ritornare lista vuota (placeholder)."""
        from src.processing.news_hunter import search_insiders
        
        result = search_insiders("Test Team", "soccer_turkey_super_league", "match_123")
        assert result == [], "V8.0: search_insiders deve ritornare lista vuota"


class TestV61Integration:
    """Test di integrazione per verificare il flusso completo."""
    
    def test_backend_detection_works(self):
        """_get_search_backend deve funzionare correttamente."""
        from src.processing.news_hunter import _get_search_backend
        
        backend = _get_search_backend()
        assert backend in ['ddg', 'serper', 'none'], f"Backend non valido: {backend}"
    
    def test_all_search_functions_importable(self):
        """Tutte le funzioni di ricerca devono essere importabili."""
        from src.processing.news_hunter import (
            search_twitter_rumors,
            search_dynamic_country,
            search_exotic_league,
            # V8.0: search_reddit_deep removed (Reddit deprecated)
            search_insiders,
            search_beat_writers_priority,
            search_news_local,
            run_hunter_for_match
        )
        
        # Se arriviamo qui, tutti gli import sono OK
        assert True


# ============================================
# V7.0 TWITTER INTEL CACHE TESTS
# ============================================

class TestV70TwitterIntelCache:
    """Test V7.0: Twitter search via Intel Cache instead of broken site:twitter.com."""
    
    def test_search_twitter_rumors_uses_cache_import(self):
        """Verifica che news_hunter importi TwitterIntelCache."""
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        # Deve importare la cache
        assert 'twitter_intel_cache' in content, "Deve importare twitter_intel_cache"
        assert '_TWITTER_INTEL_CACHE_AVAILABLE' in content, "Deve avere flag disponibilità"
    
    def test_search_twitter_rumors_no_site_dork(self):
        """Verifica che search_twitter_rumors non usi più site:twitter.com."""
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        # Trova la funzione search_twitter_rumors
        import re
        func_match = re.search(
            r'def search_twitter_rumors\([^)]+\):[^}]+?(?=\ndef |\nclass |\Z)',
            content,
            re.DOTALL
        )
        
        if func_match:
            func_body = func_match.group()
            # Non deve più usare site:twitter.com nella query
            assert 'site:twitter.com' not in func_body, \
                "search_twitter_rumors non deve più usare site:twitter.com (broken)"
    
    def test_search_twitter_rumors_returns_list_always(self):
        """search_twitter_rumors deve sempre ritornare una lista."""
        from src.processing.news_hunter import search_twitter_rumors
        
        # Test con vari input
        result1 = search_twitter_rumors("Galatasaray", "soccer_turkey_super_league", "match_1")
        result2 = search_twitter_rumors("", "soccer_argentina_primera_division", "match_2")
        result3 = search_twitter_rumors("Unknown Team", "unknown_league", "match_3")
        
        assert isinstance(result1, list), "Deve ritornare lista"
        assert isinstance(result2, list), "Deve ritornare lista per team vuoto"
        assert isinstance(result3, list), "Deve ritornare lista per league sconosciuta"
    
    def test_beat_writers_priority_no_site_dork(self):
        """Verifica che search_beat_writers_priority non usi più site:twitter.com."""
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        # Trova la funzione search_beat_writers_priority
        import re
        func_match = re.search(
            r'def search_beat_writers_priority\([^)]+\):[^}]+?(?=\ndef |\nclass |\Z)',
            content,
            re.DOTALL
        )
        
        if func_match:
            func_body = func_match.group()
            # Non deve più usare site:twitter.com nella query
            assert 'site:twitter.com' not in func_body, \
                "search_beat_writers_priority non deve più usare site:twitter.com (broken)"
    
    def test_beat_writers_priority_returns_list(self):
        """search_beat_writers_priority deve sempre ritornare una lista."""
        from src.processing.news_hunter import search_beat_writers_priority
        
        result = search_beat_writers_priority("Test Team", "soccer_unknown_league", "match_123")
        assert isinstance(result, list), "Deve ritornare una lista"
