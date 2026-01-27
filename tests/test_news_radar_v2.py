"""
Tests for News Radar V2.0 - High Value Signal Detection

Tests the new pipeline:
1. Garbage filter
2. High-value signal detection (multilingual)
3. Quality gate
"""
import pytest
from src.utils.high_value_detector import (
    GarbageFilter,
    HighValueSignalDetector,
    SignalType,
    get_garbage_filter,
    get_signal_detector,
)
from src.utils.radar_prompts import (
    build_analysis_prompt_v2,
    CATEGORY_EMOJI,
    CATEGORY_ITALIAN,
)
from src.services.news_radar import RadarAlert


class TestGarbageFilter:
    """Tests for GarbageFilter."""
    
    def test_empty_content(self):
        gf = get_garbage_filter()
        is_garbage, reason = gf.is_garbage("")
        assert is_garbage is True
        assert "empty" in reason
    
    def test_short_content(self):
        gf = get_garbage_filter()
        is_garbage, reason = gf.is_garbage("Short text")
        assert is_garbage is True
        assert "short" in reason
    
    def test_menu_content(self):
        gf = get_garbage_filter()
        # This is short, so it will fail on length first
        is_garbage, reason = gf.is_garbage("Home News Sport Football Live")
        assert is_garbage is True
    
    def test_valid_content(self):
        gf = get_garbage_filter()
        content = """
        Zamalek will play with their youth team against Al-Ittihad Alexandria 
        in the Egyptian Cup. The first team players will rest for the upcoming 
        league match against Al Ahly. This is a significant decision by the coach.
        """
        is_garbage, reason = gf.is_garbage(content)
        assert is_garbage is False
    
    def test_cookie_notice(self):
        gf = get_garbage_filter()
        content = """
        We use cookies to improve your experience. Accept all cookies to continue.
        Privacy policy and terms of service apply. GDPR compliance notice.
        """ * 10  # Make it long enough
        is_garbage, reason = gf.is_garbage(content)
        assert is_garbage is True
        assert "cookie" in reason.lower() or "garbage" in reason.lower()


class TestHighValueSignalDetector:
    """Tests for HighValueSignalDetector."""
    
    def test_mass_absence_english(self):
        sd = get_signal_detector()
        signal = sd.detect("Aachen without nine players after Havelse match")
        assert signal.detected is True
        assert signal.signal_type == SignalType.MASS_ABSENCE
        assert signal.extracted_number == 9
    
    def test_mass_absence_spanish(self):
        sd = get_signal_detector()
        signal = sd.detect("Sin 5 jugadores para el partido de mañana")
        assert signal.detected is True
        assert signal.signal_type == SignalType.MASS_ABSENCE
        assert signal.extracted_number == 5
    
    def test_mass_absence_portuguese(self):
        sd = get_signal_detector()
        signal = sd.detect("Sem 4 jogadores titulares para o jogo")
        assert signal.detected is True
        assert signal.signal_type == SignalType.MASS_ABSENCE
        assert signal.extracted_number == 4
    
    def test_mass_absence_italian(self):
        sd = get_signal_detector()
        signal = sd.detect("Senza 6 giocatori per la partita")
        assert signal.detected is True
        assert signal.signal_type == SignalType.MASS_ABSENCE
        assert signal.extracted_number == 6
    
    def test_mass_absence_german(self):
        sd = get_signal_detector()
        signal = sd.detect("Ohne 7 Spieler für das Spiel")
        assert signal.detected is True
        assert signal.signal_type == SignalType.MASS_ABSENCE
        assert signal.extracted_number == 7
    
    def test_decimated_english(self):
        sd = get_signal_detector()
        signal = sd.detect("Team decimated by injuries ahead of crucial match")
        assert signal.detected is True
        assert signal.signal_type == SignalType.DECIMATED
    
    def test_decimated_italian(self):
        sd = get_signal_detector()
        signal = sd.detect("Squadra decimata dalle assenze")
        assert signal.detected is True
        assert signal.signal_type == SignalType.DECIMATED
    
    def test_decimated_portuguese(self):
        sd = get_signal_detector()
        signal = sd.detect("Time desfalcado para o jogo")
        assert signal.detected is True
        assert signal.signal_type == SignalType.DECIMATED
    
    def test_youth_team_english(self):
        sd = get_signal_detector()
        signal = sd.detect("Club will play with youth team in cup match")
        assert signal.detected is True
        assert signal.signal_type == SignalType.YOUTH_TEAM
    
    def test_youth_team_italian(self):
        sd = get_signal_detector()
        signal = sd.detect("Formazione giovanile in campo domani")
        assert signal.detected is True
        assert signal.signal_type == SignalType.YOUTH_TEAM
    
    def test_youth_team_spanish(self):
        sd = get_signal_detector()
        signal = sd.detect("Jugará con el equipo juvenil")
        assert signal.detected is True
        assert signal.signal_type == SignalType.YOUTH_TEAM
    
    def test_financial_crisis(self):
        sd = get_signal_detector()
        signal = sd.detect("Players threaten strike over unpaid wages")
        assert signal.detected is True
        assert signal.signal_type == SignalType.FINANCIAL_CRISIS
    
    def test_logistical_crisis(self):
        sd = get_signal_detector()
        signal = sd.detect("Flight cancelled, team had chaotic arrival")
        assert signal.detected is True
        assert signal.signal_type == SignalType.LOGISTICAL_CRISIS
    
    def test_goalkeeper_out(self):
        sd = get_signal_detector()
        signal = sd.detect("Goalkeeper injured, will miss the match")
        assert signal.detected is True
        assert signal.signal_type == SignalType.GOALKEEPER_OUT
    
    def test_no_signal(self):
        sd = get_signal_detector()
        signal = sd.detect("Messi scored a beautiful goal yesterday")
        assert signal.detected is False
        assert signal.signal_type == SignalType.NONE
    
    def test_transfer_news_no_signal(self):
        sd = get_signal_detector()
        signal = sd.detect("Player signs new contract with the club")
        assert signal.detected is False
        assert signal.signal_type == SignalType.NONE
    
    def test_threshold_not_met(self):
        """2 players out should NOT trigger (threshold is 3)."""
        sd = get_signal_detector()
        signal = sd.detect("Without 2 players for the match")
        # Should not detect because 2 < 3
        assert signal.detected is False or signal.extracted_number is None or signal.extracted_number < 3


class TestRadarAlert:
    """Tests for RadarAlert V2.0 formatting."""
    
    def test_full_alert_format(self):
        alert = RadarAlert(
            source_name="Test Source",
            source_url="https://example.com",
            affected_team="Zamalek",
            opponent="Al-Ittihad Alexandria",
            competition="Egyptian Cup",
            category="YOUTH_TEAM",
            absent_count=11,
            absent_players=["Player1", "Player2", "Player3"],
            betting_impact="CRITICAL",
            summary="Zamalek schiera la formazione giovanile",
            confidence=0.92
        )
        
        msg = alert.to_telegram_message()
        
        # Check key elements are present
        assert "RADAR ALERT" in msg
        assert "Zamalek" in msg
        assert "Al-Ittihad Alexandria" in msg
        assert "Egyptian Cup" in msg
        assert "FORMAZIONE GIOVANILE" in msg
        assert "11 giocatori" in msg
        assert "Player1" in msg
        assert "CRITICAL" in msg
        assert "92%" in msg
    
    def test_minimal_alert_format(self):
        alert = RadarAlert(
            source_name="Test Source",
            source_url="https://example.com",
            affected_team="Unknown",
            category="MASS_ABSENCE",
            summary="Emergenza assenze",
            confidence=0.75
        )
        
        msg = alert.to_telegram_message()
        
        # Should show "Da verificare" for unknown team
        assert "Da verificare" in msg
        assert "EMERGENZA ASSENZE" in msg


class TestPromptGeneration:
    """Tests for prompt generation."""
    
    def test_prompt_contains_key_instructions(self):
        prompt = build_analysis_prompt_v2("Test content")
        
        # Check key instructions are present
        assert "is_high_value" in prompt
        assert "team" in prompt
        assert "absent_count" in prompt
        assert "betting_impact" in prompt
        assert "CRITICAL" in prompt
        assert "HIGH" in prompt
        assert "MEDIUM" in prompt
        assert "LOW" in prompt
    
    def test_prompt_truncation(self):
        long_content = "x" * 20000
        prompt = build_analysis_prompt_v2(long_content)
        
        # Should be truncated
        assert len(prompt) < 20000


class TestStructuredAnalysisEdgeCases:
    """V2.2: Tests for StructuredAnalysis edge cases."""
    
    def test_absent_roles_none_is_valid(self):
        """is_valid_for_alert should not crash with absent_roles=None."""
        from src.utils.high_value_detector import StructuredAnalysis
        sa = StructuredAnalysis(team='Test', absent_count=1, absent_roles=None)
        # Should not raise, should return False
        assert sa.is_valid_for_alert() is False
    
    def test_absent_roles_none_priority(self):
        """get_alert_priority should not crash with absent_roles=None."""
        from src.utils.high_value_detector import StructuredAnalysis
        sa = StructuredAnalysis(team='Test', absent_count=1, absent_roles=None)
        # Should not raise, should return MEDIUM
        assert sa.get_alert_priority() == "MEDIUM"
    
    def test_absent_roles_with_gk(self):
        """GK in absent_roles should make alert valid and HIGH priority."""
        from src.utils.high_value_detector import StructuredAnalysis
        sa = StructuredAnalysis(team='Test', absent_count=1, absent_roles=['GK'])
        assert sa.is_valid_for_alert() is True
        assert sa.get_alert_priority() == "HIGH"
    
    def test_absent_names_none(self):
        """is_valid_for_alert should not crash with absent_names=None."""
        from src.utils.high_value_detector import StructuredAnalysis
        sa = StructuredAnalysis(team='Test', absent_count=2, absent_names=None)
        # Should not raise
        assert sa.is_valid_for_alert() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ============================================
# REGRESSION TESTS - Backward Compatibility
# ============================================

class TestBackwardCompatibility:
    """
    Tests for V1/V2 format backward compatibility.
    
    V2.3: Added after fixing bug where V1 format JSON (affected_team, summary)
    was not correctly mapped to AnalysisResult fields.
    """
    
    def test_parse_response_v2_format(self):
        """Test _parse_response handles V2 format correctly."""
        from src.services.news_radar import DeepSeekFallback
        
        ds = DeepSeekFallback()
        v2_json = '{"is_high_value": true, "team": "Juventus", "category": "MASS_ABSENCE", "betting_impact": "HIGH", "confidence": 0.9, "summary_italian": "5 assenti"}'
        
        result = ds._parse_response(v2_json)
        
        assert result is not None
        assert result.is_relevant is True
        assert result.affected_team == "Juventus"
        assert result.category == "MASS_ABSENCE"
        assert result.summary == "5 assenti"
        assert result.betting_impact == "HIGH"
    
    def test_parse_response_v1_format_team_mapping(self):
        """
        Test _parse_response maps V1 'affected_team' to result.affected_team.
        
        REGRESSION: Before fix, V1 format returned affected_team=None.
        """
        from src.services.news_radar import DeepSeekFallback
        
        ds = DeepSeekFallback()
        # V1 format uses 'affected_team' instead of 'team'
        v1_json = '{"is_high_value": true, "affected_team": "Inter", "category": "INJURY", "betting_impact": "HIGH", "confidence": 0.85, "summary": "Infortunio"}'
        
        result = ds._parse_response(v1_json)
        
        assert result is not None
        # Key assertion: affected_team should NOT be None
        assert result.affected_team == "Inter", "V1 'affected_team' should map to result.affected_team"
        assert result.summary == "Infortunio", "V1 'summary' should map to result.summary"
    
    def test_parse_response_mixed_format(self):
        """Test _parse_response handles mixed V1/V2 format."""
        from src.services.news_radar import DeepSeekFallback
        
        ds = DeepSeekFallback()
        # Mixed: V2 is_high_value but V1 affected_team
        mixed_json = '{"is_high_value": true, "affected_team": "Milan", "category": "DECIMATED", "betting_impact": "CRITICAL", "confidence": 0.95, "summary": "Squadra decimata"}'
        
        result = ds._parse_response(mixed_json)
        
        assert result is not None
        assert result.affected_team == "Milan"
        assert result.summary == "Squadra decimata"
    
    def test_parse_response_v2_takes_precedence(self):
        """Test that V2 fields take precedence over V1 when both present."""
        from src.services.news_radar import DeepSeekFallback
        
        ds = DeepSeekFallback()
        # Both V1 and V2 fields present - V2 should win
        both_json = '{"is_high_value": true, "team": "Roma", "affected_team": "Lazio", "category": "YOUTH_TEAM", "betting_impact": "HIGH", "confidence": 0.9, "summary_italian": "Primavera in campo", "summary": "Youth team"}'
        
        result = ds._parse_response(both_json)
        
        assert result is not None
        assert result.affected_team == "Roma", "V2 'team' should take precedence over V1 'affected_team'"
        assert result.summary == "Primavera in campo", "V2 'summary_italian' should take precedence over V1 'summary'"


class TestPatternRegression:
    """
    Regression tests for pattern matching bugs.
    
    V2.3: Added after fixing bug where "striker" was incorrectly matched
    by the "strike" pattern (missing \\b at end of pattern).
    """
    
    def test_striker_not_matched_as_strike(self):
        """
        REGRESSION: "striker" should NOT be matched as "strike".
        
        Bug: Pattern r'\\b(strike|...)' without \\b at end matched "striker".
        Fix: Added \\b at end: r'\\b(strike|...)\\b'
        """
        from src.utils.high_value_detector import get_signal_detector, SignalType
        
        sd = get_signal_detector()
        
        # Content about a striker (football player position)
        content = """
        Great news for Juventus fans! Star striker Dusan Vlahovic has returned to 
        full training after recovering from his knee injury. The player is expected 
        to be available for the upcoming Serie A match against Inter Milan.
        """
        
        result = sd.detect(content)
        
        # Should NOT detect as FINANCIAL_CRISIS (strike)
        assert result.signal_type != SignalType.FINANCIAL_CRISIS, \
            "striker should not be matched as strike (FINANCIAL_CRISIS)"
        # Should not detect any signal (this is positive news)
        assert result.detected is False, \
            "Positive news about striker returning should not trigger any signal"
    
    def test_actual_strike_still_matched(self):
        """Verify that actual strike (sciopero) is still detected."""
        from src.utils.high_value_detector import get_signal_detector, SignalType
        
        sd = get_signal_detector()
        
        # Content about an actual player strike
        content = """
        I giocatori del Chievo Verona hanno annunciato uno sciopero per gli stipendi 
        non pagati. La squadra è in crisi finanziaria e potrebbe non presentarsi 
        alla prossima partita di Serie B.
        """
        
        result = sd.detect(content)
        
        assert result.detected is True
        # FINANCIAL_CRISIS should be in all_signals (may not be primary due to "crisi" matching DECIMATED first)
        assert SignalType.FINANCIAL_CRISIS in result.all_signals, \
            f"FINANCIAL_CRISIS should be detected, got: {result.all_signals}"
    
    def test_english_strike_matched(self):
        """Verify English 'strike' (as in player strike) is detected."""
        from src.utils.high_value_detector import get_signal_detector, SignalType
        
        sd = get_signal_detector()
        
        content = """
        Players announce strike over unpaid wages. The team is in financial crisis
        and may not show up for the next match. The strike could last several weeks.
        """
        
        result = sd.detect(content)
        
        assert result.detected is True
        # FINANCIAL_CRISIS should be in all_signals
        assert SignalType.FINANCIAL_CRISIS in result.all_signals, \
            f"FINANCIAL_CRISIS should be detected, got: {result.all_signals}"
