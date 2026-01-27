"""
EarlyBird Test Configuration V2.0

Configurazione centralizzata per pytest con:
- Path setup automatico
- Fixtures condivise per mock data realistici
- Log capture per verificare eventi di sistema
- Database in-memory per test isolati
- Markers per categorizzazione test

Usage:
    # Usa fixture per match mock
    def test_analysis(mock_match):
        result = analyze(mock_match)
        assert result.score > 0
    
    # Usa log capture
    def test_fallback_logged(log_capture):
        trigger_fallback()
        assert log_capture.contains("Tavily fallback")
    
    # Usa database isolato
    def test_db_operation(isolated_db):
        isolated_db.add(Match(...))
        assert isolated_db.query(Match).count() == 1

Run specific test categories:
    pytest -m unit          # Solo unit test veloci
    pytest -m integration   # Solo integration test
    pytest -m "not slow"    # Escludi test lenti
"""
import sys
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field

import pytest

# ============================================
# PATH SETUP
# ============================================

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


# ============================================
# PYTEST MARKERS
# ============================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated)")
    config.addinivalue_line("markers", "integration: Integration tests (may use real services)")
    config.addinivalue_line("markers", "slow: Slow tests (API calls, heavy computation)")
    config.addinivalue_line("markers", "regression: Regression tests for bug fixes")
    config.addinivalue_line("markers", "e2e: End-to-end tests")


# ============================================
# LOG CAPTURE FIXTURE
# ============================================

@dataclass
class CapturedLog:
    """Single captured log entry."""
    level: str
    message: str
    logger_name: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __str__(self) -> str:
        return f"[{self.level}] {self.message}"


class LogCapture:
    """
    Captures log messages during test execution.
    
    Usage:
        def test_something(log_capture):
            do_something_that_logs()
            
            # Check if specific message was logged
            assert log_capture.contains("expected message")
            
            # Check log level
            assert log_capture.contains("error occurred", level="ERROR")
            
            # Get all warnings
            warnings = log_capture.get_by_level("WARNING")
            assert len(warnings) == 2
            
            # Check pattern
            assert log_capture.contains_pattern(r"Tavily.*fallback")
    """
    
    def __init__(self):
        self.logs: List[CapturedLog] = []
        self._handler: Optional[logging.Handler] = None
    
    def capture(self, record: logging.LogRecord) -> None:
        """Capture a log record."""
        self.logs.append(CapturedLog(
            level=record.levelname,
            message=record.getMessage(),
            logger_name=record.name,
        ))
    
    def contains(self, substring: str, level: Optional[str] = None) -> bool:
        """
        Check if any log message contains the substring.
        
        Args:
            substring: Text to search for (case-insensitive)
            level: Optional log level filter (e.g., "WARNING", "ERROR")
        """
        substring_lower = substring.lower()
        for log in self.logs:
            if level and log.level != level:
                continue
            if substring_lower in log.message.lower():
                return True
        return False
    
    def contains_pattern(self, pattern: str, level: Optional[str] = None) -> bool:
        """
        Check if any log message matches a regex pattern.
        
        Args:
            pattern: Regex pattern to match
            level: Optional log level filter
        """
        import re
        regex = re.compile(pattern, re.IGNORECASE)
        for log in self.logs:
            if level and log.level != level:
                continue
            if regex.search(log.message):
                return True
        return False
    
    def get_by_level(self, level: str) -> List[CapturedLog]:
        """Get all logs at a specific level."""
        return [log for log in self.logs if log.level == level]
    
    def get_all(self) -> List[CapturedLog]:
        """Get all captured logs."""
        return self.logs.copy()
    
    def clear(self) -> None:
        """Clear all captured logs."""
        self.logs.clear()
    
    def format_all(self) -> str:
        """Format all logs for debugging."""
        if not self.logs:
            return "(no logs captured)"
        return "\n".join(str(log) for log in self.logs)
    
    def assert_logged(self, substring: str, level: Optional[str] = None, msg: str = "") -> None:
        """
        Assert that a message was logged. Raises AssertionError if not.
        
        Args:
            substring: Text that should appear in logs
            level: Optional level filter
            msg: Custom error message
        """
        if not self.contains(substring, level):
            level_info = f" at level {level}" if level else ""
            error_msg = f"Expected log containing '{substring}'{level_info} not found.\n"
            error_msg += f"Captured logs:\n{self.format_all()}"
            if msg:
                error_msg = f"{msg}\n{error_msg}"
            raise AssertionError(error_msg)
    
    def assert_not_logged(self, substring: str, level: Optional[str] = None, msg: str = "") -> None:
        """Assert that a message was NOT logged."""
        if self.contains(substring, level):
            level_info = f" at level {level}" if level else ""
            error_msg = f"Unexpected log containing '{substring}'{level_info} was found.\n"
            error_msg += f"Captured logs:\n{self.format_all()}"
            if msg:
                error_msg = f"{msg}\n{error_msg}"
            raise AssertionError(error_msg)


class LogCaptureHandler(logging.Handler):
    """Logging handler that captures to LogCapture."""
    
    def __init__(self, capture: LogCapture):
        super().__init__()
        self.capture = capture
    
    def emit(self, record: logging.LogRecord) -> None:
        self.capture.capture(record)


@pytest.fixture
def log_capture():
    """
    Fixture that captures all log messages during a test.
    
    Usage:
        def test_fallback_is_logged(log_capture):
            # Trigger something that should log
            trigger_tavily_fallback()
            
            # Verify the log
            assert log_capture.contains("Tavily fallback")
            log_capture.assert_logged("fallback", level="WARNING")
    """
    capture = LogCapture()
    handler = LogCaptureHandler(capture)
    handler.setLevel(logging.DEBUG)
    
    # Attach to root logger to capture everything
    root_logger = logging.getLogger()
    original_level = root_logger.level
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)
    
    yield capture
    
    # Cleanup
    root_logger.removeHandler(handler)
    root_logger.setLevel(original_level)


# ============================================
# MOCK DATA FIXTURES
# ============================================

@pytest.fixture
def mock_match_data() -> Dict[str, Any]:
    """
    Realistic match data dict for testing.
    
    Represents a typical match from the database with all fields populated.
    """
    now = datetime.now(timezone.utc)
    return {
        'id': 'test_match_12345',
        'league': 'soccer_italy_serie_a',
        'home_team': 'Inter Milan',
        'away_team': 'AC Milan',
        'start_time': now + timedelta(hours=24),
        'opening_home_odd': 2.10,
        'opening_draw_odd': 3.40,
        'opening_away_odd': 3.20,
        'current_home_odd': 1.95,
        'current_draw_odd': 3.50,
        'current_away_odd': 3.40,
        'opening_over_2_5': 1.85,
        'opening_under_2_5': 1.95,
        'current_over_2_5': 1.80,
        'current_under_2_5': 2.00,
    }


@pytest.fixture
def mock_match(mock_match_data):
    """
    Mock Match object for testing.
    
    Returns a MagicMock that behaves like a Match database object.
    """
    match = MagicMock()
    for key, value in mock_match_data.items():
        setattr(match, key, value)
    return match


@pytest.fixture
def mock_news_item() -> Dict[str, Any]:
    """
    Realistic news item from news_hunter.
    
    Represents a typical news discovery with all required fields.
    """
    now = datetime.now(timezone.utc)
    return {
        'match_id': 'test_match_12345',
        'team': 'Inter Milan',
        'keyword': 'injury',
        'title': 'Lautaro Martinez ruled out for Derby della Madonnina',
        'snippet': 'Inter striker Lautaro Martinez will miss the Milan derby due to a hamstring injury sustained in training.',
        'link': 'https://football-italia.net/inter-lautaro-injury',
        'date': now.isoformat(),
        'source': 'football-italia.net',
        'search_type': 'ddg_local',
        'confidence': 'HIGH',
        'priority_boost': 1.0,
        'minutes_old': 45,
        'freshness_tag': '🔥 FRESH',
    }


@pytest.fixture
def mock_news_items(mock_news_item) -> List[Dict[str, Any]]:
    """List of mock news items for batch testing."""
    items = [mock_news_item.copy()]
    
    # Add a second news item
    item2 = mock_news_item.copy()
    item2['title'] = 'AC Milan confirm Leao fit for derby'
    item2['team'] = 'AC Milan'
    item2['snippet'] = 'Rafael Leao has recovered from his knock and will be available for the derby.'
    item2['confidence'] = 'MEDIUM'
    items.append(item2)
    
    return items


@pytest.fixture
def mock_verification_request() -> Dict[str, Any]:
    """
    Mock VerificationRequest data for testing verification layer.
    """
    return {
        'match_id': 'test_match_12345',
        'home_team': 'Inter Milan',
        'away_team': 'AC Milan',
        'match_date': '2026-01-15',
        'league': 'soccer_italy_serie_a',
        'preliminary_score': 8.2,
        'suggested_market': 'Over 2.5 Goals',
        'home_missing_players': ['Lautaro Martinez', 'Nicolò Barella'],
        'away_missing_players': [],
        'home_injury_severity': 'HIGH',
        'away_injury_severity': 'LOW',
        'home_injury_impact': 15.0,
        'away_injury_impact': 0.0,
    }


@pytest.fixture
def mock_analysis_result() -> Dict[str, Any]:
    """
    Mock analysis result from analyzer.py.
    """
    return {
        'final_verdict': 'BET',
        'confidence': 78,
        'recommended_market': 'Over 2.5 Goals',
        'primary_market': '1',
        'primary_driver': 'INJURY_INTEL',
        'combo_suggestion': 'Inter Win + Over 2.5',
        'combo_reasoning': 'Milan missing key defenders, Inter strong at home',
        'reasoning': 'High-value opportunity based on injury intel and market inefficiency.',
    }


@pytest.fixture
def mock_fotmob_context() -> Dict[str, Any]:
    """
    Mock FotMob team context data.
    """
    return {
        'injuries': [
            {'name': 'Lautaro Martinez', 'status': 'injured', 'reason': 'Hamstring'},
            {'name': 'Nicolò Barella', 'status': 'doubtful', 'reason': 'Knock'},
        ],
        'form': 'WWDWL',
        'goals_scored': 12,
        'goals_conceded': 5,
        'corners_per_game': 6.2,
        'cards_per_game': 2.1,
    }


@pytest.fixture
def mock_tavily_response() -> Dict[str, Any]:
    """
    Mock Tavily API response for verification layer tests.
    """
    return {
        'answer': 'Inter Milan will be without Lautaro Martinez (hamstring) and Nicolò Barella (knock) for the derby.',
        'results': [
            {
                'title': 'Inter injury update',
                'url': 'https://football-italia.net/inter-injuries',
                'content': 'Lautaro Martinez ruled out, Barella doubtful.',
                'score': 0.95,
            }
        ],
        'provider': 'tavily',
    }


# ============================================
# DATABASE FIXTURES
# ============================================

@pytest.fixture
def isolated_db():
    """
    Isolated in-memory database for testing.
    
    Creates a fresh SQLite database in memory that is destroyed after the test.
    
    Usage:
        def test_db_operation(isolated_db):
            from src.database.models import Match
            
            match = Match(id='test', home_team='A', away_team='B', ...)
            isolated_db.add(match)
            isolated_db.commit()
            
            result = isolated_db.query(Match).filter_by(id='test').first()
            assert result is not None
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.database.models import Base
    
    # Create in-memory database
    engine = create_engine('sqlite:///:memory:', echo=False)
    Base.metadata.create_all(engine)
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    yield session
    
    # Cleanup
    session.close()
    engine.dispose()


@pytest.fixture
def sample_matches(isolated_db):
    """
    Pre-populated database with sample matches.
    
    Returns the session with 3 matches already inserted.
    """
    from src.database.models import Match
    from datetime import datetime, timezone, timedelta
    
    now = datetime.now(timezone.utc)
    
    matches = [
        Match(
            id='match_1',
            league='soccer_italy_serie_a',
            home_team='Inter Milan',
            away_team='AC Milan',
            start_time=now + timedelta(hours=24),
            opening_home_odd=2.10,
            current_home_odd=1.95,
        ),
        Match(
            id='match_2',
            league='soccer_england_premier_league',
            home_team='Liverpool',
            away_team='Manchester United',
            start_time=now + timedelta(hours=48),
            opening_home_odd=1.80,
            current_home_odd=1.75,
        ),
        Match(
            id='match_3',
            league='soccer_spain_la_liga',
            home_team='Real Madrid',
            away_team='Barcelona',
            start_time=now + timedelta(hours=72),
            opening_home_odd=2.50,
            current_home_odd=2.40,
        ),
    ]
    
    for match in matches:
        isolated_db.add(match)
    isolated_db.commit()
    
    return isolated_db


# ============================================
# API MOCK FIXTURES
# ============================================

@pytest.fixture
def mock_tavily_provider():
    """
    Mock Tavily provider that returns controlled responses.
    
    Usage:
        def test_verification(mock_tavily_provider):
            mock_tavily_provider.set_response({'answer': 'test'})
            result = verify_alert(request)
            assert mock_tavily_provider.call_count == 1
    """
    class MockTavilyProvider:
        def __init__(self):
            self._response = {'answer': 'Mock response', 'results': []}
            self._should_fail = False
            self._call_count = 0
        
        def set_response(self, response: Dict) -> None:
            self._response = response
        
        def set_failure(self, should_fail: bool = True) -> None:
            self._should_fail = should_fail
        
        @property
        def call_count(self) -> int:
            return self._call_count
        
        def search(self, query: str, **kwargs) -> Optional[Dict]:
            self._call_count += 1
            if self._should_fail:
                return None
            return self._response
        
        def is_available(self) -> bool:
            return not self._should_fail
    
    return MockTavilyProvider()


@pytest.fixture
def mock_perplexity_provider():
    """Mock Perplexity provider for fallback testing."""
    class MockPerplexityProvider:
        def __init__(self):
            self._response = {'answer': 'Perplexity fallback response'}
            self._should_fail = False
            self._call_count = 0
        
        def set_response(self, response: Dict) -> None:
            self._response = response
        
        def set_failure(self, should_fail: bool = True) -> None:
            self._should_fail = should_fail
        
        @property
        def call_count(self) -> int:
            return self._call_count
        
        def query(self, prompt: str, **kwargs) -> Optional[Dict]:
            self._call_count += 1
            if self._should_fail:
                return None
            return self._response
        
        def is_available(self) -> bool:
            return not self._should_fail
    
    return MockPerplexityProvider()


# ============================================
# VALIDATION HELPERS
# ============================================

@pytest.fixture
def validators():
    """
    Import validators module for easy access in tests.
    
    Usage:
        def test_news_validation(validators, mock_news_item):
            result = validators.validate_news_item(mock_news_item)
            assert result.is_valid
    """
    from src.utils import validators as v
    return v


# ============================================
# CLEANUP FIXTURES
# ============================================

@pytest.fixture(autouse=True)
def reset_global_state():
    """
    Auto-reset global state between tests.
    
    Clears caches and resets counters that might leak between tests.
    """
    yield
    
    # Reset browser monitor discoveries
    try:
        from src.processing.news_hunter import _browser_monitor_discoveries, _browser_monitor_lock
        with _browser_monitor_lock:
            _browser_monitor_discoveries.clear()
    except ImportError:
        pass
    
    # Reset AI response stats
    try:
        from src.analysis.analyzer import reset_ai_response_stats
        reset_ai_response_stats()
    except (ImportError, AttributeError):
        pass
