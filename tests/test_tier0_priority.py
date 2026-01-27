"""
Test TIER 0 Priority Sorting (V4.5)

Verifica che le news vengano ordinate correttamente per priority_boost e confidence,
assicurando che le fonti TIER 0 (A-League, Beat Writers) appaiano per prime nel dossier AI.
"""
import pytest


def _get_news_priority(item):
    """Replica della funzione di ordinamento in main.py"""
    boost = item.get('priority_boost') or 0
    conf_order = {'VERY_HIGH': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
    conf = conf_order.get(item.get('confidence', 'LOW'), 0)
    return (boost, conf)


class TestTier0PrioritySorting:
    """Test suite per l'ordinamento TIER 0"""
    
    def test_empty_list(self):
        """Lista vuota non deve causare errori"""
        items = []
        sorted_items = sorted(items, key=_get_news_priority, reverse=True)
        assert len(sorted_items) == 0
    
    def test_none_priority_boost(self):
        """None in priority_boost deve essere trattato come 0"""
        items = [
            {'title': 'A', 'priority_boost': None, 'confidence': 'MEDIUM'},
            {'title': 'B', 'priority_boost': 2.0, 'confidence': 'VERY_HIGH'},
        ]
        sorted_items = sorted(items, key=_get_news_priority, reverse=True)
        assert sorted_items[0]['title'] == 'B'
    
    def test_missing_confidence(self):
        """Confidence mancante deve essere trattato come LOW"""
        items = [
            {'title': 'A', 'priority_boost': 1.0},  # No confidence
            {'title': 'B', 'priority_boost': 1.0, 'confidence': 'HIGH'},
        ]
        sorted_items = sorted(items, key=_get_news_priority, reverse=True)
        assert sorted_items[0]['title'] == 'B'
    
    def test_tier0_order(self):
        """TIER 0 sources devono apparire per prime"""
        items = [
            {'title': 'Reddit', 'priority_boost': None, 'confidence': 'LOW'},
            {'title': 'A-League', 'priority_boost': 2.0, 'confidence': 'VERY_HIGH'},
            {'title': 'Beat Writer', 'priority_boost': 1.5, 'confidence': 'HIGH'},
            {'title': 'DDG', 'priority_boost': None, 'confidence': 'MEDIUM'},
        ]
        sorted_items = sorted(items, key=_get_news_priority, reverse=True)
        expected_order = ['A-League', 'Beat Writer', 'DDG', 'Reddit']
        actual_order = [i['title'] for i in sorted_items]
        assert actual_order == expected_order
    
    def test_same_boost_different_confidence(self):
        """A parità di boost, confidence più alta vince"""
        items = [
            {'title': 'A', 'priority_boost': 1.5, 'confidence': 'MEDIUM'},
            {'title': 'B', 'priority_boost': 1.5, 'confidence': 'HIGH'},
        ]
        sorted_items = sorted(items, key=_get_news_priority, reverse=True)
        assert sorted_items[0]['title'] == 'B'
    
    def test_invalid_confidence_value(self):
        """Confidence non valido deve essere trattato come 0"""
        items = [
            {'title': 'A', 'priority_boost': 1.0, 'confidence': 'INVALID'},
            {'title': 'B', 'priority_boost': 1.0, 'confidence': 'LOW'},
        ]
        sorted_items = sorted(items, key=_get_news_priority, reverse=True)
        # LOW (1) > INVALID (0)
        assert sorted_items[0]['title'] == 'B'


class TestALeagueScraperEdgeCases:
    """Test edge cases per A-League Scraper"""
    
    def test_empty_team_name(self):
        """Team name vuoto deve ritornare lista vuota"""
        from src.ingestion.aleague_scraper import search_aleague_news
        result = search_aleague_news('', 'test_match')
        assert result == []
    
    def test_whitespace_team_name(self):
        """Team name con solo spazi deve ritornare lista vuota"""
        from src.ingestion.aleague_scraper import search_aleague_news
        result = search_aleague_news('   ', 'test_match')
        assert result == []
    
    def test_extract_team_mentions_none(self):
        """_extract_team_mentions con None deve ritornare False"""
        from src.ingestion.aleague_scraper import _extract_team_mentions
        assert _extract_team_mentions(None, 'Sydney FC') == False
        assert _extract_team_mentions('Some text', None) == False
        assert _extract_team_mentions('', '') == False
    
    def test_has_injury_content_none(self):
        """_has_injury_content con None deve ritornare False"""
        from src.ingestion.aleague_scraper import _has_injury_content
        assert _has_injury_content(None) == False
        assert _has_injury_content('') == False


class TestBeatWritersIntegration:
    """Test integrazione Beat Writers"""
    
    def test_get_beat_writers_unknown_league(self):
        """League sconosciuta deve ritornare lista vuota"""
        from src.processing.sources_config import get_beat_writers
        result = get_beat_writers('soccer_unknown_league')
        assert result == []
    
    def test_get_beat_writer_by_handle(self):
        """Lookup beat writer per handle"""
        from src.processing.sources_config import get_beat_writer_by_handle
        
        # Con @
        writer = get_beat_writer_by_handle('@ALeagues', 'soccer_australia_aleague')
        assert writer is not None
        assert writer.outlet == 'A-Leagues'
        
        # Senza @
        writer = get_beat_writer_by_handle('TyCSports', 'soccer_argentina_primera_division')
        assert writer is not None
        
        # Non esistente
        writer = get_beat_writer_by_handle('@NonExistent', 'soccer_australia_aleague')
        assert writer is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
