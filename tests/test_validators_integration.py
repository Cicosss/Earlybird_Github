"""
Test di Integrazione per Validatori

Verifica che i validatori funzionino correttamente con dati reali
prodotti dai componenti del sistema EarlyBird.

Questi test usano dati nel formato esatto prodotto da:
- news_hunter (news items)
- browser_monitor (discoveries)
- verification_layer (requests/results)
- analyzer (analysis results)

Requirements: Self-Check Protocol compliance
"""
import pytest
from datetime import datetime, timezone, timedelta


class TestNewsHunterIntegration:
    """Test validatori con output reale di news_hunter."""
    
    def test_browser_monitor_discovery_format(self):
        """
        Verifica che il formato discovery di browser_monitor sia valido.
        Questo è il formato prodotto da register_browser_monitor_discovery().
        """
        from src.utils.validators import validate_news_item
        
        now = datetime.now(timezone.utc)
        
        # Formato esatto prodotto da register_browser_monitor_discovery
        discovery = {
            'match_id': None,  # Pre-matching
            'team': 'Galatasaray',
            'title': 'Icardi ruled out for derby',
            'snippet': 'Star striker will miss the match due to injury',
            'link': 'https://fanatik.com.tr/article',
            'source': 'fanatik.com.tr',
            'date': now.isoformat(),
            'freshness_tag': '🔥 FRESH',
            'minutes_old': 15,
            'keyword': 'browser_monitor',
            'search_type': 'browser_monitor',
            'confidence': 'HIGH',
            'category': 'INJURY',
            'priority_boost': 2.0,
            'source_type': 'browser_monitor',
            'league_key': 'soccer_turkey_super_league',
            'gemini_confidence': 0.85,
            'discovered_at': now.isoformat(),
        }
        
        # Deve essere valido con allow_null_match_id
        result = validate_news_item(discovery, allow_null_match_id=True)
        assert result.is_valid, f"Browser monitor discovery invalido: {result.errors}"
    
    def test_beat_writer_cache_format(self):
        """
        Verifica formato output di search_beat_writers_priority().
        """
        from src.utils.validators import validate_news_item
        
        # Formato esatto prodotto da search_beat_writers_priority
        beat_writer_result = {
            'match_id': 'test_match_123',
            'team': 'River Plate',
            'keyword': 'beat_writer_priority',
            'title': '@GastonEdul: Borja no viaja a Mendoza',
            'snippet': 'El delantero no fue convocado para el partido',
            'link': 'https://twitter.com/GastonEdul',
            'date': '',
            'source': '@GastonEdul',
            'search_type': 'beat_writer_cache',
            'confidence': 'HIGH',
            'priority_boost': 1.5,
            'source_type': 'beat_writer',
            'topics': ['injury', 'lineup'],
            'beat_writer_name': 'Gastón Edul',
            'beat_writer_outlet': 'TyC Sports',
            'beat_writer_specialty': 'River Plate',
            'beat_writer_reliability': 'HIGH',
        }
        
        result = validate_news_item(beat_writer_result)
        assert result.is_valid, f"Beat writer result invalido: {result.errors}"
    
    def test_ddg_local_search_format(self):
        """
        Verifica formato output di ricerca DDG locale.
        """
        from src.utils.validators import validate_news_item
        
        # Formato prodotto da search_news con DDG
        ddg_result = {
            'match_id': 'test_match_456',
            'team': 'Legia Warszawa',
            'keyword': 'kontuzja',
            'title': 'Legia bez kluczowego gracza',
            'snippet': 'Kapitan kontuzjowany przed meczem ligowym',
            'link': 'https://weszlo.com/article/123',
            'date': '2026-01-13',
            'source': 'weszlo.com',
            'search_type': 'ddg_local',
        }
        
        result = validate_news_item(ddg_result)
        assert result.is_valid, f"DDG local result invalido: {result.errors}"
    
    def test_exotic_league_search_format(self):
        """
        Verifica formato output per leghe esotiche (search_type dinamico).
        """
        from src.utils.validators import validate_news_item
        
        # Formato prodotto da search_exotic_league_news
        exotic_result = {
            'match_id': 'test_match_789',
            'team': 'Melbourne Victory',
            'keyword': 'aleagues_official',
            'title': 'Ins and Outs: Melbourne Victory vs Sydney FC',
            'snippet': 'Key defender ruled out with hamstring injury',
            'link': 'https://aleagues.com.au/article',
            'date': '2026-01-13',
            'source': 'aleagues.com.au',
            'search_type': 'exotic_aleagues_official',  # Dinamico
        }
        
        result = validate_news_item(exotic_result)
        assert result.is_valid, f"Exotic league result invalido: {result.errors}"
        # Non deve avere warning per search_type exotic_*
        search_warnings = [w for w in result.warnings if 'search_type' in w]
        assert len(search_warnings) == 0, f"Warning inatteso per exotic search_type: {search_warnings}"


class TestVerificationLayerIntegration:
    """Test validatori con dati reali del Verification Layer."""
    
    def test_verification_request_from_match(self):
        """
        Verifica formato VerificationRequest creato da create_verification_request_from_match().
        """
        from src.utils.validators import validate_verification_request
        
        # Formato prodotto da create_verification_request_from_match
        request_data = {
            'match_id': 'abc123def456',
            'home_team': 'Inter Milan',
            'away_team': 'AC Milan',
            'match_date': '2026-01-15',
            'league': 'soccer_italy_serie_a',
            'preliminary_score': 8.5,
            'suggested_market': 'Over 2.5 Goals',
            'home_missing_players': ['Lautaro Martinez', 'Nicolò Barella'],
            'away_missing_players': ['Theo Hernandez'],
            'home_injury_severity': 'HIGH',
            'away_injury_severity': 'MEDIUM',
            'home_injury_impact': 17.0,
            'away_injury_impact': 8.0,
            'fotmob_home_goals_avg': 2.1,
            'fotmob_away_goals_avg': 1.8,
            'fotmob_referee_name': 'Daniele Orsato',
            'home_form_last5': 'WWDWL',
            'away_form_last5': 'WDWDL',
        }
        
        result = validate_verification_request(request_data)
        assert result.is_valid, f"Verification request invalido: {result.errors}"
    
    def test_verification_result_confirm(self):
        """
        Verifica formato VerificationResult con status CONFIRM.
        """
        from src.utils.validators import validate_verification_result
        
        result_data = {
            'status': 'confirm',
            'original_score': 8.5,
            'adjusted_score': 8.2,
            'score_adjustment_reason': 'Lieve riduzione per form recente',
            'original_market': 'Over 2.5 Goals',
            'recommended_market': None,
            'alternative_markets': ['BTTS', 'Over 9.5 Corners'],
            'inconsistencies': [],
            'overall_confidence': 'HIGH',
            'reasoning': 'Alert confermato. Dati FotMob coerenti con news.',
            'rejection_reason': None,
        }
        
        result = validate_verification_result(result_data)
        assert result.is_valid, f"Verification result CONFIRM invalido: {result.errors}"
    
    def test_verification_result_reject(self):
        """
        Verifica formato VerificationResult con status REJECT.
        """
        from src.utils.validators import validate_verification_result
        
        result_data = {
            'status': 'reject',
            'original_score': 8.0,
            'adjusted_score': 0.0,
            'score_adjustment_reason': 'Respinto per incongruenze critiche',
            'original_market': 'Over 2.5 Goals',
            'recommended_market': None,
            'alternative_markets': [],
            'inconsistencies': [
                'News dice 3 assenti ma FotMob ne mostra 7',
                'Form recente suggerisce Under, non Over',
            ],
            'overall_confidence': 'HIGH',
            'reasoning': 'Alert respinto per incongruenze tra news e dati ufficiali.',
            'rejection_reason': 'Incongruenze critiche tra fonti',
        }
        
        result = validate_verification_result(result_data)
        assert result.is_valid, f"Verification result REJECT invalido: {result.errors}"
    
    def test_verification_result_change_market(self):
        """
        Verifica formato VerificationResult con status CHANGE_MARKET.
        """
        from src.utils.validators import validate_verification_result
        
        result_data = {
            'status': 'change_market',
            'original_score': 8.0,
            'adjusted_score': 7.5,
            'score_adjustment_reason': 'Mercato modificato per H2H',
            'original_market': 'Over 2.5 Goals',
            'recommended_market': 'Over 9.5 Corners',
            'alternative_markets': ['Over 4.5 Cards'],
            'inconsistencies': ['H2H mostra media 2.1 gol, non supporta Over 2.5'],
            'overall_confidence': 'MEDIUM',
            'reasoning': 'H2H suggerisce mercato corners invece di goals.',
            'rejection_reason': None,
        }
        
        result = validate_verification_result(result_data)
        assert result.is_valid, f"Verification result CHANGE_MARKET invalido: {result.errors}"


class TestAnalyzerIntegration:
    """Test validatori con output reale dell'Analyzer."""
    
    def test_analyzer_bet_response(self):
        """
        Verifica formato risposta analyzer con verdict BET.
        """
        from src.utils.validators import validate_analysis_result
        
        # Formato prodotto da validate_ai_response
        analysis = {
            'final_verdict': 'BET',
            'confidence': 78,
            'recommended_market': 'Over 2.5 Goals',
            'primary_market': '1',
            'primary_driver': 'INJURY_INTEL',
            'combo_suggestion': 'Inter Win + Over 2.5',
            'combo_reasoning': 'Milan missing key defenders, Inter strong at home with 2.3 goals/game',
            'reasoning': 'High-value opportunity. Key absences for Milan create attacking space.',
        }
        
        result = validate_analysis_result(analysis)
        assert result.is_valid, f"Analysis BET invalido: {result.errors}"
    
    def test_analyzer_no_bet_response(self):
        """
        Verifica formato risposta analyzer con verdict NO BET.
        """
        from src.utils.validators import validate_analysis_result
        
        analysis = {
            'final_verdict': 'NO BET',
            'confidence': 45,
            'recommended_market': None,
            'primary_market': None,
            'primary_driver': 'MATH_VALUE',
            'combo_suggestion': None,
            'combo_reasoning': None,
            'reasoning': 'Insufficient edge. News already priced into market.',
        }
        
        result = validate_analysis_result(analysis)
        assert result.is_valid, f"Analysis NO BET invalido: {result.errors}"
    
    def test_analyzer_monitor_response(self):
        """
        Verifica formato risposta analyzer con verdict MONITOR.
        """
        from src.utils.validators import validate_analysis_result
        
        analysis = {
            'final_verdict': 'MONITOR',
            'confidence': 62,
            'recommended_market': 'Over 2.5 Goals',
            'primary_market': None,
            'primary_driver': 'CONTEXT_PLAY',
            'combo_suggestion': None,
            'combo_reasoning': None,
            'reasoning': 'Potential value but need confirmation. Monitor for lineup news.',
        }
        
        result = validate_analysis_result(analysis)
        assert result.is_valid, f"Analysis MONITOR invalido: {result.errors}"


class TestAlertPayloadIntegration:
    """Test validatori con payload alert reali."""
    
    def test_telegram_alert_payload(self):
        """
        Verifica formato payload per send_alert().
        """
        from src.utils.validators import validate_alert_payload
        
        # Formato usato da send_alert in notifier.py
        payload = {
            'home_team': 'Inter Milan',
            'away_team': 'AC Milan',
            'league': 'soccer_italy_serie_a',
            'score': 8,
            'news_summary': '🔴 INJURY ALERT: Lautaro Martinez ruled out for derby. Key striker missing.',
            'news_url': 'https://football-italia.net/article',
            'recommended_market': 'Over 2.5 Goals',
            'combo_suggestion': 'Inter Win + Over 2.5',
        }
        
        result = validate_alert_payload(payload)
        assert result.is_valid, f"Alert payload invalido: {result.errors}"


class TestEdgeCasesIntegration:
    """Test edge case con dati reali."""
    
    def test_news_item_with_unicode_characters(self):
        """News con caratteri unicode (turco, polacco, etc.)."""
        from src.utils.validators import validate_news_item
        
        news = {
            'match_id': 'test_123',
            'team': 'Galatasaray',
            'keyword': 'sakatlık',
            'title': 'Galatasaray\'da Icardi şoku! Sakatlığı açıklandı',
            'snippet': 'Yıldız forvet derbi öncesi kadro dışı kaldı',
            'link': 'https://fanatik.com.tr/haber',
            'date': '2026-01-13',
            'source': 'fanatik.com.tr',
            'search_type': 'ddg_local',
        }
        
        result = validate_news_item(news)
        assert result.is_valid, f"News con unicode invalido: {result.errors}"
    
    def test_news_item_with_very_long_snippet(self):
        """News con snippet molto lungo (troncato)."""
        from src.utils.validators import validate_news_item
        
        long_snippet = "A" * 5000  # 5000 caratteri
        
        news = {
            'match_id': 'test_123',
            'team': 'Test Team',
            'title': 'Test Title',
            'snippet': long_snippet,
            'link': 'https://test.com',
            'source': 'test.com',
            'search_type': 'ddg_local',
        }
        
        result = validate_news_item(news)
        assert result.is_valid, f"News con snippet lungo invalido: {result.errors}"
    
    def test_verification_request_with_empty_missing_players(self):
        """VerificationRequest con liste giocatori vuote."""
        from src.utils.validators import validate_verification_request
        
        request = {
            'match_id': 'test_123',
            'home_team': 'Team A',
            'away_team': 'Team B',
            'match_date': '2026-01-15',
            'league': 'soccer_test_league',
            'preliminary_score': 7.5,
            'suggested_market': 'Over 2.5 Goals',
            'home_missing_players': [],  # Vuota
            'away_missing_players': [],  # Vuota
            'home_injury_severity': 'NONE',
            'away_injury_severity': 'NONE',
        }
        
        result = validate_verification_request(request)
        assert result.is_valid, f"Request con liste vuote invalido: {result.errors}"


# Marker per test di integrazione
pytestmark = pytest.mark.integration
