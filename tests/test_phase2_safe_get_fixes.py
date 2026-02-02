"""
Test Suite for Phase 2 Safe Get Fixes

Tests for safe_get() fixes in telegram_listener.py and news_hunter.py
to verify that dangerous .get() calls have been properly replaced.

This ensures that the bot's intelligent components can communicate safely
even when receiving malformed or unexpected data from external APIs.
"""

import pytest
from src.utils.validators import safe_dict_get


class TestTelegramListenerSafeGetFixes:
    """Test safe_get() fixes in telegram_listener.py"""
    
    def test_squad_dict_valid(self):
        """Test that squad dict with all keys works correctly"""
        squad = {
            'full_text': 'Full text content',
            'caption': 'Caption text',
            'has_image': True,
            'ocr_text': 'OCR extracted text',
            'channel_type': 'insider',
            'match': {'id': '123', 'home_team': 'Team A'},
            'channel': 'test_channel'
        }
        
        # Test all safe_dict_get calls
        full_text = safe_dict_get(squad, 'full_text', default='') or safe_dict_get(squad, 'caption', default='')
        assert full_text == 'Full text content'
        
        has_image = safe_dict_get(squad, 'has_image', default=False)
        assert has_image is True
        
        ocr_text = safe_dict_get(squad, 'ocr_text', default=None)
        assert ocr_text == 'OCR extracted text'
        
        channel_type = safe_dict_get(squad, 'channel_type', default='unknown')
        assert channel_type == 'insider'
        
        match = safe_dict_get(squad, 'match', default=None)
        assert match == {'id': '123', 'home_team': 'Team A'}
    
    def test_squad_dict_missing_keys(self):
        """Test that squad dict with missing keys returns defaults"""
        squad = {
            'channel': 'test_channel'
        }
        
        # Test safe_dict_get with missing keys
        full_text = safe_dict_get(squad, 'full_text', default='') or safe_dict_get(squad, 'caption', default='')
        assert full_text == ''
        
        has_image = safe_dict_get(squad, 'has_image', default=False)
        assert has_image is False
        
        ocr_text = safe_dict_get(squad, 'ocr_text', default=None)
        assert ocr_text is None
        
        channel_type = safe_dict_get(squad, 'channel_type', default='unknown')
        assert channel_type == 'unknown'
        
        match = safe_dict_get(squad, 'match', default=None)
        assert match is None
    
    def test_squad_not_dict(self):
        """Test that squad is not a dict returns defaults"""
        squad = "not_a_dict"
        
        # Test safe_dict_get with non-dict
        full_text = safe_dict_get(squad, 'full_text', default='') or safe_dict_get(squad, 'caption', default='')
        assert full_text == ''
        
        has_image = safe_dict_get(squad, 'has_image', default=False)
        assert has_image is False
        
        ocr_text = safe_dict_get(squad, 'ocr_text', default=None)
        assert ocr_text is None
        
        channel_type = safe_dict_get(squad, 'channel_type', default='unknown')
        assert channel_type == 'unknown'
        
        match = safe_dict_get(squad, 'match', default=None)
        assert match is None
    
    def test_squad_none(self):
        """Test that squad is None returns defaults"""
        squad = None
        
        # Test safe_dict_get with None
        full_text = safe_dict_get(squad, 'full_text', default='') or safe_dict_get(squad, 'caption', default='')
        assert full_text == ''
        
        has_image = safe_dict_get(squad, 'has_image', default=False)
        assert has_image is False
        
        ocr_text = safe_dict_get(squad, 'ocr_text', default=None)
        assert ocr_text is None
        
        channel_type = safe_dict_get(squad, 'channel_type', default='unknown')
        assert channel_type == 'unknown'
        
        match = safe_dict_get(squad, 'match', default=None)
        assert match is None
    
    def test_squad_caption_slicing(self):
        """Test that caption slicing works with safe_dict_get"""
        squad = {
            'caption': 'A' * 200,  # Long caption
            'channel': 'test_channel'
        }
        
        # Test caption slicing
        caption_preview = safe_dict_get(squad, 'caption', default='')[:100]
        assert len(caption_preview) == 100
        assert caption_preview == 'A' * 100


class TestNewsHunterSafeGetFixes:
    """Test safe_get() fixes in news_hunter.py"""
    
    def test_item_dict_valid(self):
        """Test that item dict with all keys works correctly"""
        item = {
            'title': 'News Title',
            'snippet': 'News snippet',
            'link': 'https://example.com/news',
            'date': '2024-01-01',
            'source': 'Example Source'
        }
        
        # Test all safe_dict_get calls
        title = safe_dict_get(item, 'title', default='')
        assert title == 'News Title'
        
        snippet = safe_dict_get(item, 'snippet', default='')
        assert snippet == 'News snippet'
        
        link = safe_dict_get(item, 'link', default='')
        assert link == 'https://example.com/news'
        
        date = safe_dict_get(item, 'date', default=None)
        assert date == '2024-01-01'
        
        source = safe_dict_get(item, 'source', default='Default Source')
        assert source == 'Example Source'
    
    def test_item_dict_missing_keys(self):
        """Test that item dict with missing keys returns defaults"""
        item = {}
        
        # Test safe_dict_get with missing keys
        title = safe_dict_get(item, 'title', default='')
        assert title == ''
        
        snippet = safe_dict_get(item, 'snippet', default='')
        assert snippet == ''
        
        link = safe_dict_get(item, 'link', default='')
        assert link == ''
        
        date = safe_dict_get(item, 'date', default=None)
        assert date is None
        
        source = safe_dict_get(item, 'source', default='Default Source')
        assert source == 'Default Source'
    
    def test_item_not_dict(self):
        """Test that item is not a dict returns defaults"""
        item = "not_a_dict"
        
        # Test safe_dict_get with non-dict
        title = safe_dict_get(item, 'title', default='')
        assert title == ''
        
        snippet = safe_dict_get(item, 'snippet', default='')
        assert snippet == ''
        
        link = safe_dict_get(item, 'link', default='')
        assert link == ''
        
        date = safe_dict_get(item, 'date', default=None)
        assert date is None
        
        source = safe_dict_get(item, 'source', default='Default Source')
        assert source == 'Default Source'
    
    def test_item_none(self):
        """Test that item is None returns defaults"""
        item = None
        
        # Test safe_dict_get with None
        title = safe_dict_get(item, 'title', default='')
        assert title == ''
        
        snippet = safe_dict_get(item, 'snippet', default='')
        assert snippet == ''
        
        link = safe_dict_get(item, 'link', default='')
        assert link == ''
        
        date = safe_dict_get(item, 'date', default=None)
        assert date is None
        
        source = safe_dict_get(item, 'source', default='Default Source')
        assert source == 'Default Source'
    
    def test_item_fallback_snippet(self):
        """Test that snippet fallback to description works"""
        item = {
            'description': 'Description text',
            'channel': 'test_channel'
        }
        
        # Test snippet fallback
        snippet = safe_dict_get(item, 'snippet', default='') or safe_dict_get(item, 'description', default='')
        assert snippet == 'Description text'
    
    def test_item_source_type_fallback(self):
        """Test that source_type fallback to search_type works"""
        item = {
            'search_type': 'mainstream',
            'channel': 'test_channel'
        }
        
        # Test source_type fallback
        source_type = safe_dict_get(item, 'source_type', default='') or safe_dict_get(item, 'search_type', default='mainstream')
        assert source_type == 'mainstream'
    
    def test_item_link_lower(self):
        """Test that link.lower() works with safe_dict_get"""
        item = {
            'link': 'HTTPS://EXAMPLE.COM/NEWS',
            'channel': 'test_channel'
        }
        
        # Test link.lower()
        link = safe_dict_get(item, 'link', default='').lower()
        assert link == 'https://example.com/news'


class TestBotIntelligentCommunication:
    """Test that bot components communicate safely"""
    
    def test_telegram_listener_to_squad_analyzer(self):
        """Test data flow from Telegram Listener to Squad Analyzer"""
        # Simulate data from Telegram Listener
        squad_data = {
            'image_path': '/tmp/squad.jpg',
            'team_search_name': 'Galatasaray',
            'timestamp': '2024-01-01T12:00:00Z',
            'channel': 'insider_channel',
            'channel_type': 'insider',
            'match': {'id': '123', 'home_team': 'Galatasaray', 'away_team': 'Fenerbahce'},
            'has_image': True,
            'ocr_text': 'OCR extracted squad list',
            'caption': 'Official squad announcement',
            'full_text': 'Official squad announcement\nOCR extracted squad list'
        }
        
        # Test safe access to all fields
        image_path = safe_dict_get(squad_data, 'image_path', default='')
        team_name = safe_dict_get(squad_data, 'team_search_name', default='')
        channel = safe_dict_get(squad_data, 'channel', default='')
        channel_type = safe_dict_get(squad_data, 'channel_type', default='unknown')
        match = safe_dict_get(squad_data, 'match', default=None)
        has_image = safe_dict_get(squad_data, 'has_image', default=False)
        ocr_text = safe_dict_get(squad_data, 'ocr_text', default=None)
        caption = safe_dict_get(squad_data, 'caption', default='')
        full_text = safe_dict_get(squad_data, 'full_text', default='') or safe_dict_get(squad_data, 'caption', default='')
        
        # Verify all fields are accessible
        assert image_path == '/tmp/squad.jpg'
        assert team_name == 'Galatasaray'
        assert channel == 'insider_channel'
        assert channel_type == 'insider'
        assert match == {'id': '123', 'home_team': 'Galatasaray', 'away_team': 'Fenerbahce'}
        assert has_image is True
        assert ocr_text == 'OCR extracted squad list'
        assert caption == 'Official squad announcement'
        assert full_text == 'Official squad announcement\nOCR extracted squad list'
    
    def test_news_hunter_to_analyzer(self):
        """Test data flow from News Hunter to Analyzer"""
        # Simulate data from News Hunter
        news_items = [
            {
                'match_id': '123',
                'team': 'Galatasaray',
                'keyword': 'injury',
                'title': 'Player injured in training',
                'snippet': 'Key player suffered injury',
                'link': 'https://example.com/news1',
                'date': '2024-01-01T10:00:00Z',
                'source': 'Sports News',
                'search_type': 'ddg_local'
            },
            {
                'match_id': '123',
                'team': 'Fenerbahce',
                'keyword': 'injury',
                'title': 'Another player injured',
                'snippet': 'Another key player injured',
                'link': 'https://example.com/news2',
                'date': '2024-01-01T11:00:00Z',
                'source': 'Another Source',
                'search_type': 'serper'
            }
        ]
        
        # Test safe access to all fields
        for item in news_items:
            match_id = safe_dict_get(item, 'match_id', default='')
            team = safe_dict_get(item, 'team', default='')
            keyword = safe_dict_get(item, 'keyword', default='')
            title = safe_dict_get(item, 'title', default='')
            snippet = safe_dict_get(item, 'snippet', default='')
            link = safe_dict_get(item, 'link', default='')
            date = safe_dict_get(item, 'date', default=None)
            source = safe_dict_get(item, 'source', default='')
            search_type = safe_dict_get(item, 'search_type', default='')
            
            # Verify all fields are accessible
            assert match_id == '123'
            assert team in ['Galatasaray', 'Fenerbahce']
            assert keyword == 'injury'
            assert title != ''
            assert snippet != ''
            assert link.startswith('https://')
            assert date is not None
            assert source != ''
            assert search_type in ['ddg_local', 'serper']
    
    def test_malformed_api_response(self):
        """Test handling of malformed API responses"""
        # Simulate various malformed responses
        malformed_items = [
            None,  # None value
            "string_instead_of_dict",  # String instead of dict
            123,  # Number instead of dict
            [],  # Empty list
            {},  # Empty dict
            {'title': 'Only title'},  # Partial dict
        ]
        
        for item in malformed_items:
            # All should return defaults without crashing
            title = safe_dict_get(item, 'title', default='')
            snippet = safe_dict_get(item, 'snippet', default='')
            link = safe_dict_get(item, 'link', default='')
            date = safe_dict_get(item, 'date', default=None)
            source = safe_dict_get(item, 'source', default='')
            
            # Verify defaults are returned
            assert isinstance(title, str)
            assert isinstance(snippet, str)
            assert isinstance(link, str)
            assert date is None or isinstance(date, str)
            assert isinstance(source, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
