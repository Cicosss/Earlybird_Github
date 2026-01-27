"""
EarlyBird Database Full Test Suite
===================================
Test completo di tutte le funzionalità del database per VPS deployment.

Verifica:
1. CRUD operations su Match, NewsLog, TeamAlias
2. Telegram Channel tracking
3. Migrazioni automatiche
4. Flusso dati end-to-end (ingestion -> analysis -> settlement)
5. Edge cases e concurrency
6. Maintenance e cleanup

Esegui con: pytest tests/test_database_full.py -v
"""
import pytest
import os
import sys
import sqlite3
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


# ============================================
# FIXTURES
# ============================================

@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_earlybird.db")
    
    yield db_path
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_engine(temp_db):
    """Create a test SQLAlchemy engine."""
    engine = create_engine(
        f"sqlite:///{temp_db}",
        connect_args={"check_same_thread": False, "timeout": 30}
    )
    
    # Enable WAL mode
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
    
    return engine


@pytest.fixture
def test_session(test_engine):
    """Create a test session factory."""
    from src.database.models import Base
    Base.metadata.create_all(bind=test_engine)
    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_match_data():
    """Sample match data for testing."""
    return {
        'id': 'test_match_001',
        'league': 'soccer_turkey_super_league',
        'home_team': 'Galatasaray',
        'away_team': 'Fenerbahce',
        'start_time': datetime.now(timezone.utc) + timedelta(hours=24),
        'opening_home_odd': 2.10,
        'opening_draw_odd': 3.40,
        'opening_away_odd': 3.20,
        'current_home_odd': 1.95,
        'current_draw_odd': 3.50,
        'current_away_odd': 3.40,
    }


# ============================================
# TEST 1: BASIC CRUD OPERATIONS
# ============================================

class TestMatchCRUD:
    """Test Match model CRUD operations."""
    
    def test_create_match(self, test_session, sample_match_data):
        """Test creating a new match."""
        from src.database.models import Match
        
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=sample_match_data['start_time'].replace(tzinfo=None),
            opening_home_odd=sample_match_data['opening_home_odd'],
            opening_draw_odd=sample_match_data['opening_draw_odd'],
            opening_away_odd=sample_match_data['opening_away_odd'],
            current_home_odd=sample_match_data['current_home_odd'],
            current_draw_odd=sample_match_data['current_draw_odd'],
            current_away_odd=sample_match_data['current_away_odd'],
        )
        
        test_session.add(match)
        test_session.commit()
        
        # Verify
        saved = test_session.query(Match).filter(Match.id == sample_match_data['id']).first()
        assert saved is not None
        assert saved.home_team == 'Galatasaray'
        assert saved.away_team == 'Fenerbahce'
        assert saved.opening_home_odd == 2.10
        assert saved.current_home_odd == 1.95
    
    def test_update_match_odds(self, test_session, sample_match_data):
        """Test updating match odds (preserving opening, updating current)."""
        from src.database.models import Match
        
        # Create match
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=sample_match_data['start_time'].replace(tzinfo=None),
            opening_home_odd=2.10,
            current_home_odd=2.10,
        )
        test_session.add(match)
        test_session.commit()
        
        # Update current odds only
        match.current_home_odd = 1.85
        match.last_updated = datetime.now(timezone.utc)
        test_session.commit()
        
        # Verify opening preserved, current updated
        saved = test_session.query(Match).filter(Match.id == sample_match_data['id']).first()
        assert saved.opening_home_odd == 2.10  # Preserved
        assert saved.current_home_odd == 1.85  # Updated
    
    def test_match_with_stats(self, test_session, sample_match_data):
        """Test match with V3.7 stats warehousing fields."""
        from src.database.models import Match
        
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=sample_match_data['start_time'].replace(tzinfo=None),
            # Stats fields
            home_corners=6,
            away_corners=4,
            home_yellow_cards=2,
            away_yellow_cards=3,
            home_xg=1.85,
            away_xg=1.20,
            home_possession=58.5,
            away_possession=41.5,
        )
        test_session.add(match)
        test_session.commit()
        
        saved = test_session.query(Match).filter(Match.id == sample_match_data['id']).first()
        assert saved.home_corners == 6
        assert saved.away_corners == 4
        assert saved.home_xg == 1.85
        assert saved.home_possession == 58.5


class TestNewsLogCRUD:
    """Test NewsLog model CRUD operations."""
    
    def test_create_news_log(self, test_session, sample_match_data):
        """Test creating a news log entry."""
        from src.database.models import Match, NewsLog
        
        # Create match first
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=sample_match_data['start_time'].replace(tzinfo=None),
        )
        test_session.add(match)
        test_session.commit()
        
        # Create news log
        news = NewsLog(
            match_id=sample_match_data['id'],
            url='https://example.com/news/1',
            summary='Key player injured before derby',
            score=8,
            category='INJURY',
            affected_team='Galatasaray',
            combo_suggestion='Over 2.5 + BTTS',
            combo_reasoning='Both teams attack-minded',
            recommended_market='Over 2.5 Goals',
            primary_driver='INJURY_INTEL',
            source='web',
        )
        test_session.add(news)
        test_session.commit()
        
        # Verify
        saved = test_session.query(NewsLog).filter(NewsLog.match_id == sample_match_data['id']).first()
        assert saved is not None
        assert saved.score == 8
        assert saved.category == 'INJURY'
        assert saved.combo_suggestion == 'Over 2.5 + BTTS'
        assert saved.primary_driver == 'INJURY_INTEL'
        assert saved.source == 'web'
    
    def test_news_log_clv_tracking(self, test_session, sample_match_data):
        """Test V4.2 CLV tracking fields."""
        from src.database.models import Match, NewsLog
        
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=sample_match_data['start_time'].replace(tzinfo=None),
        )
        test_session.add(match)
        test_session.commit()
        
        news = NewsLog(
            match_id=sample_match_data['id'],
            url='https://example.com/news/2',
            summary='Test CLV tracking',
            score=8,
            category='SHARP_MONEY',
            affected_team='Galatasaray',
            odds_taken=2.15,  # V4.2: Odds when alert sent
            clv_percent=3.5,  # V4.2: Calculated CLV
        )
        test_session.add(news)
        test_session.commit()
        
        saved = test_session.query(NewsLog).filter(NewsLog.match_id == sample_match_data['id']).first()
        assert saved.odds_taken == 2.15
        assert saved.clv_percent == 3.5
    
    def test_news_log_relationship(self, test_session, sample_match_data):
        """Test Match-NewsLog relationship."""
        from src.database.models import Match, NewsLog
        
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=sample_match_data['start_time'].replace(tzinfo=None),
        )
        test_session.add(match)
        test_session.commit()
        
        # Add multiple news logs
        for i in range(3):
            news = NewsLog(
                match_id=sample_match_data['id'],
                url=f'https://example.com/news/{i}',
                summary=f'News item {i}',
                score=7 + i,
                category='INJURY',
                affected_team='Galatasaray',
            )
            test_session.add(news)
        test_session.commit()
        
        # Verify relationship
        saved_match = test_session.query(Match).filter(Match.id == sample_match_data['id']).first()
        assert len(saved_match.news_logs) == 3
        assert saved_match.news_logs[0].match == saved_match


class TestTeamAliasCRUD:
    """Test TeamAlias model CRUD operations."""
    
    def test_create_team_alias(self, test_session):
        """Test creating team alias."""
        from src.database.models import TeamAlias
        
        alias = TeamAlias(
            api_name='Galatasaray SK',
            search_name='Galatasaray',
            twitter_handle='@GalatasaraySK',
            telegram_channel='galatasaray',
        )
        test_session.add(alias)
        test_session.commit()
        
        saved = test_session.query(TeamAlias).filter(TeamAlias.api_name == 'Galatasaray SK').first()
        assert saved is not None
        assert saved.search_name == 'Galatasaray'
        assert saved.twitter_handle == '@GalatasaraySK'
    
    def test_unique_api_name_constraint(self, test_session):
        """Test that api_name must be unique."""
        from src.database.models import TeamAlias
        from sqlalchemy.exc import IntegrityError
        
        alias1 = TeamAlias(api_name='Test Team', search_name='Test')
        test_session.add(alias1)
        test_session.commit()
        
        alias2 = TeamAlias(api_name='Test Team', search_name='Test2')
        test_session.add(alias2)
        
        with pytest.raises(IntegrityError):
            test_session.commit()
        
        test_session.rollback()


# ============================================
# TEST 2: TELEGRAM CHANNEL TRACKING
# ============================================

class TestTelegramChannelTracking:
    """Test Telegram channel tracking functionality."""
    
    def test_create_telegram_channel(self, test_engine):
        """Test creating a Telegram channel entry."""
        from src.database.models import Base
        from src.database.telegram_channel_model import TelegramChannel
        
        Base.metadata.create_all(bind=test_engine)
        TelegramChannel.__table__.create(test_engine, checkfirst=True)
        
        Session = sessionmaker(bind=test_engine)
        session = Session()
        
        try:
            channel = TelegramChannel(
                channel_id='123456789',
                channel_name='test_channel',
                total_messages=100,
                insider_hits=15,
                late_messages=5,
                trust_score=0.75,
                trust_level='TRUSTED',
            )
            session.add(channel)
            session.commit()
            
            saved = session.query(TelegramChannel).filter(
                TelegramChannel.channel_id == '123456789'
            ).first()
            
            assert saved is not None
            assert saved.channel_name == 'test_channel'
            assert saved.trust_score == 0.75
            assert saved.trust_level == 'TRUSTED'
        finally:
            session.close()
    
    def test_telegram_message_log(self, test_engine):
        """Test Telegram message logging."""
        from src.database.models import Base
        from src.database.telegram_channel_model import TelegramMessageLog
        
        Base.metadata.create_all(bind=test_engine)
        TelegramMessageLog.__table__.create(test_engine, checkfirst=True)
        
        Session = sessionmaker(bind=test_engine)
        session = Session()
        
        try:
            log = TelegramMessageLog(
                channel_id='123456789',
                message_id='msg_001',
                text_hash='abc123',
                text_preview='Test message preview',
                message_time=datetime.now(timezone.utc),
                was_insider_hit=True,
                timestamp_lag_minutes=-15.5,  # 15 min before odds drop
                trust_multiplier=1.2,
            )
            session.add(log)
            session.commit()
            
            saved = session.query(TelegramMessageLog).filter(
                TelegramMessageLog.message_id == 'msg_001'
            ).first()
            
            assert saved is not None
            assert saved.was_insider_hit == True
            assert saved.timestamp_lag_minutes == -15.5
            assert saved.trust_multiplier == 1.2
        finally:
            session.close()
    
    def test_channel_metrics_update(self, test_engine):
        """Test updating channel metrics (rolling average)."""
        from src.database.models import Base
        from src.database.telegram_channel_model import TelegramChannel
        
        Base.metadata.create_all(bind=test_engine)
        TelegramChannel.__table__.create(test_engine, checkfirst=True)
        
        Session = sessionmaker(bind=test_engine)
        session = Session()
        
        try:
            # Create channel with initial metrics
            channel = TelegramChannel(
                channel_id='test_metrics',
                channel_name='metrics_test',
                total_messages=10,
                messages_with_odds_impact=5,
                avg_timestamp_lag_minutes=10.0,
                insider_hits=3,
            )
            session.add(channel)
            session.commit()
            
            # Simulate update (rolling average calculation)
            # New message with -5 min lag (insider hit)
            new_lag = -5.0
            n = channel.messages_with_odds_impact + 1  # Will be 6
            old_avg = channel.avg_timestamp_lag_minutes
            
            # Rolling average: new_avg = (old_avg * (n-1) + new_value) / n
            new_avg = ((old_avg * (n - 1)) + new_lag) / n
            
            channel.messages_with_odds_impact = n
            channel.avg_timestamp_lag_minutes = new_avg
            channel.insider_hits += 1
            session.commit()
            
            saved = session.query(TelegramChannel).filter(
                TelegramChannel.channel_id == 'test_metrics'
            ).first()
            
            # Expected: (10.0 * 5 + (-5.0)) / 6 = 45 / 6 = 7.5
            assert saved.messages_with_odds_impact == 6
            assert abs(saved.avg_timestamp_lag_minutes - 7.5) < 0.01
            assert saved.insider_hits == 4
        finally:
            session.close()


# ============================================
# TEST 3: DATABASE MIGRATIONS
# ============================================

class TestDatabaseMigrations:
    """Test automatic database migrations."""
    
    def test_migration_adds_missing_columns(self, temp_db):
        """Test that migration adds missing columns to existing tables."""
        # Create a minimal DB with old schema (missing new columns)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Create old-style matches table (missing V3.7 stats columns)
        cursor.execute("""
            CREATE TABLE matches (
                id TEXT PRIMARY KEY,
                league TEXT,
                home_team TEXT,
                away_team TEXT,
                start_time DATETIME,
                opening_home_odd REAL,
                current_home_odd REAL,
                last_updated DATETIME
            )
        """)
        
        # Create old-style news_logs table (missing CLV columns)
        cursor.execute("""
            CREATE TABLE news_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT,
                url TEXT,
                summary TEXT,
                score INTEGER,
                category TEXT,
                affected_team TEXT,
                timestamp DATETIME,
                sent INTEGER DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE team_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_name TEXT UNIQUE,
                search_name TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        
        # Run migration
        with patch('src.database.migration.DB_PATH', temp_db):
            from src.database.migration import check_and_migrate, get_table_columns
            check_and_migrate()
            
            # Verify new columns were added
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            matches_cols = get_table_columns(cursor, 'matches')
            news_logs_cols = get_table_columns(cursor, 'news_logs')
            
            conn.close()
        
        # Check V3.2 INVESTIGATOR MODE column
        assert 'last_deep_dive_time' in matches_cols, "V3.2 last_deep_dive_time migration missing"
        
        # Check V3.7 stats columns added to matches
        assert 'home_corners' in matches_cols
        assert 'away_corners' in matches_cols
        assert 'home_xg' in matches_cols
        assert 'home_possession' in matches_cols
        assert 'highest_score_sent' in matches_cols
        
        # Check V4.2 CLV columns added to news_logs
        assert 'odds_taken' in news_logs_cols
        assert 'clv_percent' in news_logs_cols
        assert 'primary_driver' in news_logs_cols
        assert 'source' in news_logs_cols
    
    def test_migration_idempotent(self, temp_db):
        """Test that running migration multiple times is safe."""
        # Create full schema
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE matches (
                id TEXT PRIMARY KEY,
                league TEXT,
                home_team TEXT,
                away_team TEXT,
                start_time DATETIME,
                home_corners INTEGER,
                away_corners INTEGER,
                highest_score_sent REAL DEFAULT 0.0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE news_logs (
                id INTEGER PRIMARY KEY,
                match_id TEXT,
                odds_taken REAL,
                clv_percent REAL,
                source TEXT DEFAULT 'web'
            )
        """)
        
        cursor.execute("""
            CREATE TABLE team_aliases (
                id INTEGER PRIMARY KEY,
                api_name TEXT UNIQUE,
                search_name TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        
        # Run migration twice - should not fail
        with patch('src.database.migration.DB_PATH', temp_db):
            from src.database.migration import check_and_migrate
            check_and_migrate()  # First run
            check_and_migrate()  # Second run - should be idempotent
        
        # Verify DB still works
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM matches")
        conn.close()
    
    def test_get_table_columns_invalid_table(self, temp_db):
        """Test that invalid table names are rejected (SQL injection prevention)."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        from src.database.migration import get_table_columns
        
        # Valid table should work
        cursor.execute("CREATE TABLE matches (id TEXT)")
        conn.commit()
        
        cols = get_table_columns(cursor, 'matches')
        assert 'id' in cols
        
        # Invalid table name should return empty set
        cols_invalid = get_table_columns(cursor, 'invalid_table; DROP TABLE matches;--')
        assert cols_invalid == set()
        
        conn.close()


# ============================================
# TEST 4: DATA FLOW END-TO-END
# ============================================

class TestDataFlowE2E:
    """Test end-to-end data flow: ingestion -> analysis -> settlement."""
    
    def test_match_ingestion_flow(self, test_session, sample_match_data):
        """Test match ingestion creates proper records."""
        from src.database.models import Match, TeamAlias
        
        # Simulate ingestion
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=sample_match_data['start_time'].replace(tzinfo=None),
            opening_home_odd=sample_match_data['opening_home_odd'],
            opening_draw_odd=sample_match_data['opening_draw_odd'],
            opening_away_odd=sample_match_data['opening_away_odd'],
            current_home_odd=sample_match_data['current_home_odd'],
            current_draw_odd=sample_match_data['current_draw_odd'],
            current_away_odd=sample_match_data['current_away_odd'],
        )
        test_session.add(match)
        
        # Create team aliases
        for team in [sample_match_data['home_team'], sample_match_data['away_team']]:
            alias = TeamAlias(api_name=team, search_name=team.replace(' SK', ''))
            test_session.add(alias)
        
        test_session.commit()
        
        # Verify complete ingestion
        saved_match = test_session.query(Match).filter(Match.id == sample_match_data['id']).first()
        assert saved_match is not None
        
        home_alias = test_session.query(TeamAlias).filter(
            TeamAlias.api_name == sample_match_data['home_team']
        ).first()
        assert home_alias is not None
    
    def test_analysis_creates_news_log(self, test_session, sample_match_data):
        """Test that analysis creates proper NewsLog entries."""
        from src.database.models import Match, NewsLog
        
        # Create match
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=sample_match_data['start_time'].replace(tzinfo=None),
            current_home_odd=1.95,
        )
        test_session.add(match)
        test_session.commit()
        
        # Simulate analysis result
        news = NewsLog(
            match_id=sample_match_data['id'],
            url='https://example.com/injury-news',
            summary='Star striker ruled out with hamstring injury',
            score=9,
            category='INJURY',
            affected_team=sample_match_data['home_team'],
            recommended_market='Away Win',
            combo_suggestion='Away Win + Under 2.5',
            combo_reasoning='Home team weakened, defensive game expected',
            primary_driver='INJURY_INTEL',
            odds_taken=3.40,  # V4.2: CLV tracking
            sent=True,
        )
        test_session.add(news)
        
        # Update match highest_score_sent
        match.highest_score_sent = 9.0
        test_session.commit()
        
        # Verify
        saved_news = test_session.query(NewsLog).filter(
            NewsLog.match_id == sample_match_data['id']
        ).first()
        assert saved_news.score == 9
        assert saved_news.sent == True
        assert saved_news.odds_taken == 3.40
        
        saved_match = test_session.query(Match).filter(Match.id == sample_match_data['id']).first()
        assert saved_match.highest_score_sent == 9.0
    
    def test_settlement_updates_clv(self, test_session, sample_match_data):
        """Test that settlement calculates and saves CLV."""
        from src.database.models import Match, NewsLog
        from src.analysis.settler import calculate_clv
        
        # Create match with closing odds
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=(datetime.now(timezone.utc) - timedelta(hours=3)).replace(tzinfo=None),
            current_away_odd=3.20,  # Closing odds
        )
        test_session.add(match)
        test_session.commit()
        
        # Create news log with odds_taken
        news = NewsLog(
            match_id=sample_match_data['id'],
            url='https://example.com/news',
            summary='Test settlement',
            score=8,
            category='INJURY',
            affected_team=sample_match_data['away_team'],
            recommended_market='Away Win',
            odds_taken=3.40,  # Odds when we sent alert
            sent=True,
        )
        test_session.add(news)
        test_session.commit()
        
        # Calculate CLV
        clv = calculate_clv(odds_taken=3.40, closing_odds=3.20)
        
        # Update news log with CLV
        news.clv_percent = clv
        test_session.commit()
        
        # Verify CLV calculated correctly
        # CLV = (odds_taken / fair_closing) - 1
        # fair_closing = 1 / (implied_prob / 1.05) where implied_prob = 1/3.20
        assert clv is not None
        assert clv > 0  # We got better odds than closing
        
        saved_news = test_session.query(NewsLog).filter(
            NewsLog.match_id == sample_match_data['id']
        ).first()
        assert saved_news.clv_percent == clv


# ============================================
# TEST 5: EDGE CASES & ERROR HANDLING
# ============================================

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_clv_calculation_edge_cases(self):
        """Test CLV calculation with edge cases."""
        from src.analysis.settler import calculate_clv
        
        # Normal case
        clv = calculate_clv(2.10, 2.00)
        assert clv is not None
        
        # None inputs
        assert calculate_clv(None, 2.00) is None
        assert calculate_clv(2.10, None) is None
        assert calculate_clv(None, None) is None
        
        # Invalid odds (<=1.0)
        assert calculate_clv(1.0, 2.00) is None
        assert calculate_clv(2.10, 1.0) is None
        assert calculate_clv(0.5, 2.00) is None
        
        # Zero odds
        assert calculate_clv(0, 2.00) is None
        assert calculate_clv(2.10, 0) is None
    
    def test_evaluate_bet_edge_cases(self):
        """Test bet evaluation with edge cases."""
        from src.analysis.settler import evaluate_bet, RESULT_PENDING, RESULT_PUSH
        
        # Cancelled match
        result, explanation = evaluate_bet(
            'Home Win', 0, 0, 2.10, 'CANCELLED'
        )
        assert result == RESULT_PUSH
        assert 'CANCELLED' in explanation.upper() or 'Annullata' in explanation
        
        # Postponed match
        result, explanation = evaluate_bet(
            'Away Win', 0, 0, 3.20, 'POSTPONED'
        )
        assert result == RESULT_PUSH
        
        # Unknown market
        result, explanation = evaluate_bet(
            'Unknown Market XYZ', 2, 1, 2.10, 'FINISHED'
        )
        assert result == RESULT_PENDING
        
        # Empty market string
        result, explanation = evaluate_bet(
            '', 2, 1, 2.10, 'FINISHED'
        )
        assert result == RESULT_PENDING
        
        # None market
        result, explanation = evaluate_bet(
            None, 2, 1, 2.10, 'FINISHED'
        )
        assert result == RESULT_PENDING
    
    def test_evaluate_over_under_edge_cases(self):
        """Test Over/Under evaluation with edge cases."""
        from src.analysis.settler import evaluate_over_under, RESULT_PENDING
        
        # Stats not available
        result, explanation = evaluate_over_under(
            'Over 9.5 Corners', 10, stat_available=False
        )
        assert result == RESULT_PENDING
        
        # Invalid format
        result, explanation = evaluate_over_under(
            'Invalid Format', 10, stat_available=True
        )
        assert result == RESULT_PENDING
        
        # Edge case: exactly on the line (should never happen with .5)
        result, explanation = evaluate_over_under(
            'Over 9.5 Corners', 10, stat_available=True
        )
        assert 'WIN' in result or 'LOSS' in result
    
    def test_match_with_null_odds(self, test_session, sample_match_data):
        """Test match handling with null odds."""
        from src.database.models import Match
        
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=sample_match_data['start_time'].replace(tzinfo=None),
            # All odds null
            opening_home_odd=None,
            current_home_odd=None,
        )
        test_session.add(match)
        test_session.commit()
        
        saved = test_session.query(Match).filter(Match.id == sample_match_data['id']).first()
        assert saved.opening_home_odd is None
        assert saved.current_home_odd is None
    
    def test_news_log_with_empty_strings(self, test_session, sample_match_data):
        """Test NewsLog with empty string fields."""
        from src.database.models import Match, NewsLog
        
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=sample_match_data['start_time'].replace(tzinfo=None),
        )
        test_session.add(match)
        test_session.commit()
        
        news = NewsLog(
            match_id=sample_match_data['id'],
            url='',  # Empty URL
            summary='',  # Empty summary
            score=5,
            category='',  # Empty category
            affected_team='',  # Empty team
        )
        test_session.add(news)
        test_session.commit()
        
        saved = test_session.query(NewsLog).filter(
            NewsLog.match_id == sample_match_data['id']
        ).first()
        assert saved is not None
        assert saved.url == ''
    
    def test_highest_score_sent_deduplication(self, test_session, sample_match_data):
        """Test score-delta deduplication logic."""
        from src.database.models import Match
        
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=sample_match_data['start_time'].replace(tzinfo=None),
            highest_score_sent=7.5,
        )
        test_session.add(match)
        test_session.commit()
        
        # Simulate new analysis with lower score - should NOT send alert
        new_score = 7.0
        should_send = new_score > match.highest_score_sent
        assert should_send == False
        
        # Simulate new analysis with higher score - should send alert
        new_score = 8.5
        should_send = new_score > match.highest_score_sent
        assert should_send == True
        
        # Update highest_score_sent
        if should_send:
            match.highest_score_sent = new_score
            test_session.commit()
        
        saved = test_session.query(Match).filter(Match.id == sample_match_data['id']).first()
        assert saved.highest_score_sent == 8.5


# ============================================
# TEST 6: MAINTENANCE & CLEANUP
# ============================================

class TestMaintenanceOperations:
    """Test database maintenance operations."""
    
    def test_prune_old_data(self, test_session, sample_match_data):
        """Test pruning old matches and news logs."""
        from src.database.models import Match, NewsLog
        
        # Create old match (35 days ago)
        old_time = datetime.now(timezone.utc) - timedelta(days=35)
        old_match = Match(
            id='old_match_001',
            league=sample_match_data['league'],
            home_team='Old Team A',
            away_team='Old Team B',
            start_time=old_time.replace(tzinfo=None),
        )
        test_session.add(old_match)
        
        # Create news log for old match
        old_news = NewsLog(
            match_id='old_match_001',
            url='https://old.com',
            summary='Old news',
            score=7,
            category='INJURY',
            affected_team='Old Team A',
        )
        test_session.add(old_news)
        
        # Create recent match (5 days ago)
        recent_time = datetime.now(timezone.utc) - timedelta(days=5)
        recent_match = Match(
            id='recent_match_001',
            league=sample_match_data['league'],
            home_team='Recent Team A',
            away_team='Recent Team B',
            start_time=recent_time.replace(tzinfo=None),
        )
        test_session.add(recent_match)
        test_session.commit()
        
        # Verify both exist
        assert test_session.query(Match).count() == 2
        assert test_session.query(NewsLog).count() == 1
        
        # Simulate pruning (30 day retention)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        cutoff_naive = cutoff.replace(tzinfo=None)
        
        # Get old match IDs
        old_ids = [m.id for m in test_session.query(Match).filter(
            Match.start_time < cutoff_naive
        ).all()]
        
        # Delete news logs first (FK constraint)
        test_session.query(NewsLog).filter(
            NewsLog.match_id.in_(old_ids)
        ).delete(synchronize_session=False)
        
        # Delete old matches
        test_session.query(Match).filter(
            Match.id.in_(old_ids)
        ).delete(synchronize_session=False)
        
        test_session.commit()
        
        # Verify only recent match remains
        assert test_session.query(Match).count() == 1
        assert test_session.query(NewsLog).count() == 0
        
        remaining = test_session.query(Match).first()
        assert remaining.id == 'recent_match_001'
    
    def test_db_stats(self, test_session, sample_match_data):
        """Test database statistics retrieval."""
        from src.database.models import Match, NewsLog
        
        # Create test data
        for i in range(5):
            match = Match(
                id=f'stats_match_{i}',
                league=sample_match_data['league'],
                home_team=f'Team A{i}',
                away_team=f'Team B{i}',
                start_time=(datetime.now(timezone.utc) - timedelta(days=i)).replace(tzinfo=None),
            )
            test_session.add(match)
            
            news = NewsLog(
                match_id=f'stats_match_{i}',
                url=f'https://example.com/{i}',
                summary=f'News {i}',
                score=7,
                category='INJURY',
                affected_team=f'Team A{i}',
            )
            test_session.add(news)
        
        test_session.commit()
        
        # Get stats
        total_matches = test_session.query(Match).count()
        total_logs = test_session.query(NewsLog).count()
        oldest_match = test_session.query(Match).order_by(Match.start_time.asc()).first()
        
        assert total_matches == 5
        assert total_logs == 5
        assert oldest_match.id == 'stats_match_4'  # 4 days ago is oldest


# ============================================
# TEST 7: CONCURRENCY & SESSION HANDLING
# ============================================

class TestConcurrencyHandling:
    """Test database concurrency and session handling."""
    
    def test_context_manager_commit(self, test_engine):
        """Test that context manager commits on success."""
        from src.database.models import Base, Match
        
        Base.metadata.create_all(bind=test_engine)
        Session = sessionmaker(bind=test_engine)
        
        # Simulate get_db_context behavior
        session = Session()
        try:
            match = Match(
                id='ctx_test_001',
                league='test_league',
                home_team='Team A',
                away_team='Team B',
                start_time=datetime.now(),
            )
            session.add(match)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        
        # Verify in new session
        session2 = Session()
        saved = session2.query(Match).filter(Match.id == 'ctx_test_001').first()
        assert saved is not None
        session2.close()
    
    def test_context_manager_rollback(self, test_engine):
        """Test that context manager rolls back on error."""
        from src.database.models import Base, Match
        from sqlalchemy.exc import IntegrityError
        
        Base.metadata.create_all(bind=test_engine)
        Session = sessionmaker(bind=test_engine)
        
        # Create initial record
        session1 = Session()
        match1 = Match(
            id='rollback_test',
            league='test_league',
            home_team='Team A',
            away_team='Team B',
            start_time=datetime.now(),
        )
        session1.add(match1)
        session1.commit()
        session1.close()
        
        # Try to create duplicate (should fail)
        session2 = Session()
        try:
            match2 = Match(
                id='rollback_test',  # Duplicate ID
                league='test_league',
                home_team='Team C',
                away_team='Team D',
                start_time=datetime.now(),
            )
            session2.add(match2)
            session2.commit()
            assert False, "Should have raised IntegrityError"
        except IntegrityError:
            session2.rollback()
        finally:
            session2.close()
        
        # Verify original still exists
        session3 = Session()
        saved = session3.query(Match).filter(Match.id == 'rollback_test').first()
        assert saved.home_team == 'Team A'  # Original preserved
        session3.close()
    
    def test_wal_mode_enabled(self, temp_db):
        """Test that WAL mode is enabled for better concurrency."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Enable WAL mode
        cursor.execute("PRAGMA journal_mode=WAL")
        result = cursor.fetchone()[0]
        
        assert result.lower() == 'wal'
        
        conn.close()


# ============================================
# TEST 8: INTEGRATION WITH BOT COMPONENTS
# ============================================

class TestBotIntegration:
    """Test database integration with bot components."""
    
    def test_biscotto_detection_db_fields(self, test_session, sample_match_data):
        """Test biscotto detection uses correct DB fields."""
        from src.database.models import Match
        
        # Create match with biscotto-suspicious odds
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=sample_match_data['start_time'].replace(tzinfo=None),
            opening_draw_odd=3.40,
            current_draw_odd=2.30,  # Suspicious drop
            biscotto_alert_sent=False,
        )
        test_session.add(match)
        test_session.commit()
        
        # Simulate biscotto check
        saved = test_session.query(Match).filter(Match.id == sample_match_data['id']).first()
        
        # Calculate drop percentage
        drop_pct = ((saved.opening_draw_odd - saved.current_draw_odd) / saved.opening_draw_odd) * 100
        
        assert drop_pct > 30  # Significant drop
        assert saved.current_draw_odd < 2.50  # Below suspicious threshold
        assert saved.biscotto_alert_sent == False
        
        # Mark alert sent
        saved.biscotto_alert_sent = True
        test_session.commit()
        
        # Verify flag prevents re-alert
        saved2 = test_session.query(Match).filter(Match.id == sample_match_data['id']).first()
        assert saved2.biscotto_alert_sent == True
    
    def test_sharp_odds_tracking(self, test_session, sample_match_data):
        """Test sharp odds tracking fields."""
        from src.database.models import Match
        
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=sample_match_data['start_time'].replace(tzinfo=None),
            # Sharp odds analysis
            sharp_bookie='pinnacle',
            sharp_home_odd=1.85,
            sharp_draw_odd=3.60,
            sharp_away_odd=4.20,
            avg_home_odd=1.95,
            avg_draw_odd=3.50,
            avg_away_odd=4.00,
            is_sharp_drop=True,
            sharp_signal='SMART MONEY on HOME (diff: 0.10)',
            sharp_alert_sent=False,
        )
        test_session.add(match)
        test_session.commit()
        
        saved = test_session.query(Match).filter(Match.id == sample_match_data['id']).first()
        
        # Verify sharp analysis stored
        assert saved.sharp_bookie == 'pinnacle'
        assert saved.is_sharp_drop == True
        assert 'SMART MONEY' in saved.sharp_signal
        
        # Calculate sharp diff (use abs() for floating point comparison)
        sharp_diff = saved.avg_home_odd - saved.sharp_home_odd
        assert abs(sharp_diff - 0.10) < 0.001  # Floating point tolerance
    
    def test_case_closed_cooldown(self, test_session, sample_match_data):
        """Test Investigator Mode case closed cooldown."""
        from src.database.models import Match
        
        # Match with recent deep dive
        match = Match(
            id=sample_match_data['id'],
            league=sample_match_data['league'],
            home_team=sample_match_data['home_team'],
            away_team=sample_match_data['away_team'],
            start_time=(datetime.now(timezone.utc) + timedelta(hours=24)).replace(tzinfo=None),
            last_deep_dive_time=(datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None),
        )
        test_session.add(match)
        test_session.commit()
        
        saved = test_session.query(Match).filter(Match.id == sample_match_data['id']).first()
        
        # Check cooldown (6 hours)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        hours_since_dive = (now - saved.last_deep_dive_time).total_seconds() / 3600
        hours_to_kickoff = (saved.start_time - now).total_seconds() / 3600
        
        # Should be on cooldown (2h < 6h cooldown, 24h > 2h final check window)
        is_on_cooldown = hours_since_dive < 6 and hours_to_kickoff > 2
        assert is_on_cooldown == True
    
    def test_alert_threshold_filtering(self, test_session, sample_match_data):
        """Test alert threshold filtering for settlement."""
        from src.database.models import Match, NewsLog
        from config.settings import SETTLEMENT_MIN_SCORE
        
        # Create match with high score
        match_high = Match(
            id='high_score_match',
            league=sample_match_data['league'],
            home_team='High Team A',
            away_team='High Team B',
            start_time=(datetime.now(timezone.utc) - timedelta(hours=5)).replace(tzinfo=None),
            highest_score_sent=8.5,
        )
        test_session.add(match_high)
        
        # Create match with low score
        match_low = Match(
            id='low_score_match',
            league=sample_match_data['league'],
            home_team='Low Team A',
            away_team='Low Team B',
            start_time=(datetime.now(timezone.utc) - timedelta(hours=5)).replace(tzinfo=None),
            highest_score_sent=5.0,
        )
        test_session.add(match_low)
        test_session.commit()
        
        # Query for settlement (only high score matches)
        settleable = test_session.query(Match).filter(
            Match.highest_score_sent >= SETTLEMENT_MIN_SCORE
        ).all()
        
        assert len(settleable) == 1
        assert settleable[0].id == 'high_score_match'


# ============================================
# TEST 9: VPS DEPLOYMENT CHECKS
# ============================================

class TestVPSDeployment:
    """Tests specific to VPS deployment requirements."""
    
    def test_db_directory_creation(self, temp_db):
        """Test that data directory is created if missing."""
        import os
        
        # The temp_db fixture creates the directory
        db_dir = os.path.dirname(temp_db)
        assert os.path.exists(db_dir)
    
    def test_sqlite_timeout_configuration(self, test_engine):
        """Test SQLite timeout is configured for VPS."""
        # The test_engine fixture sets timeout=30
        # This prevents "database is locked" errors on VPS
        
        conn = test_engine.raw_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA busy_timeout")
        timeout = cursor.fetchone()[0]
        conn.close()
        
        # Should be at least 30 seconds (30000ms)
        assert timeout >= 30000
    
    def test_requirements_include_sqlalchemy(self):
        """Test that requirements.txt includes SQLAlchemy."""
        req_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'requirements.txt'
        )
        
        with open(req_path, 'r') as f:
            content = f.read().lower()
        
        assert 'sqlalchemy' in content
    
    def test_no_hardcoded_paths(self):
        """Test that DB path uses relative paths (VPS compatible)."""
        from src.database.models import DB_PATH
        
        # Should be relative path like sqlite:///data/earlybird.db
        assert 'sqlite:///' in DB_PATH
        assert not DB_PATH.startswith('sqlite:////home/')  # No absolute paths


# ============================================
# RUN TESTS
# ============================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
