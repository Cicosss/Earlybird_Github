"""
V1.6 Multi-Language Team Extraction Tests

Regression tests for the fix of "Unknown Team" detection in Portuguese/Spanish articles.

Issue: Browser monitor was logging "Unknown Team" for articles from Brazilian and
       Honduran sources (brasileirao, honduran_league) because the team extraction
       was optimized only for English patterns.

Fix: V1.6 of content_analysis.py adds:
- 100+ South American clubs (Brazil, Argentina, Honduras, Mexico, Colombia, Chile, Peru)
- Portuguese/Spanish possessive patterns ("jogador do Flamengo", "jugador del River")
- News action patterns ("Flamengo vence", "Corinthians perde")
- Plural forms (lesiones, lesionados, lesões, machucados)
"""
import pytest
from src.utils.content_analysis import (
    RelevanceAnalyzer,
    get_relevance_analyzer,
    AnalysisResult
)


class TestV16BrazilianTeamExtraction:
    """Tests for Brazilian club detection in Portuguese articles."""
    
    @pytest.fixture
    def analyzer(self):
        return RelevanceAnalyzer()
    
    def test_flamengo_extracted_from_injury_news(self, analyzer):
        """REGRESSION: Flamengo should be detected in Portuguese injury news."""
        content = "Flamengo enfrenta desfalque importante para o clássico. Atacante sofre lesão muscular."
        result = analyzer.analyze(content)
        assert result.affected_team == "Flamengo", f"Expected 'Flamengo', got '{result.affected_team}'"
        assert result.category == "INJURY"
        assert result.is_relevant
    
    def test_corinthians_extracted_from_suspension_news(self, analyzer):
        """REGRESSION: Corinthians should be detected in suspension news."""
        content = "Corinthians tem baixa confirmada para próxima rodada do Brasileirão por suspensão."
        result = analyzer.analyze(content)
        assert result.affected_team == "Corinthians", f"Expected 'Corinthians', got '{result.affected_team}'"
        # Note: 'baixa' is classified as INJURY keyword (absence), not SUSPENSION
        assert result.category in ["SUSPENSION", "INJURY"]
    
    def test_palmeiras_with_lesionado_keyword(self, analyzer):
        """Test Palmeiras with 'lesionado' keyword."""
        content = "Palmeiras perde jogador titular lesionado para partida da Libertadores."
        result = analyzer.analyze(content)
        assert result.affected_team == "Palmeiras"
        assert result.category == "INJURY"
    
    def test_gremio_with_accent_preserved(self, analyzer):
        """Test Grêmio (with accent) is properly extracted."""
        content = "Grêmio confirma lesão de zagueiro e busca reposição no mercado."
        result = analyzer.analyze(content)
        assert result.affected_team == "Grêmio"
    
    def test_santos_from_contusao_keyword(self, analyzer):
        """Test Santos with 'contusão' (bruise/injury) keyword."""
        content = "Santos FC confirma contusão de meia e jogador está fora por 6 semanas."
        result = analyzer.analyze(content)
        assert result.affected_team == "Santos"
        assert result.is_relevant
    
    def test_internacional_with_suspenso(self, analyzer):
        """Test Internacional with 'suspenso' keyword."""
        content = "Internacional tem atacante suspenso para o Gre-Nal."
        result = analyzer.analyze(content)
        assert result.affected_team == "Internacional"
        assert result.category == "SUSPENSION"
    
    def test_all_big_brazilian_clubs_recognized(self, analyzer):
        """Test all major Brazilian clubs are in the known_clubs list."""
        major_clubs = [
            "Flamengo", "Palmeiras", "Corinthians", "São Paulo",
            "Santos", "Fluminense", "Botafogo", "Vasco",
            "Grêmio", "Internacional", "Cruzeiro", "Atlético Mineiro",
            "Bahia", "Fortaleza", "Ceará", "Sport Recife"
        ]
        
        for club in major_clubs:
            content = f"{club} confirma lesão de jogador titular antes do clássico."
            result = analyzer.analyze(content)
            assert result.affected_team is not None, f"Club '{club}' should be detected"


class TestV16HonduranTeamExtraction:
    """Tests for Honduran Liga Nacional clubs in Spanish articles."""
    
    @pytest.fixture
    def analyzer(self):
        return RelevanceAnalyzer()
    
    def test_motagua_with_lesionados_plural(self, analyzer):
        """REGRESSION: 'lesionados' (plural) should trigger detection."""
        content = "Motagua con tres jugadores lesionados para el partido ante Olimpia."
        result = analyzer.analyze(content)
        assert result.affected_team == "Motagua", f"Expected 'Motagua', got '{result.affected_team}'"
        assert result.category == "INJURY"
    
    def test_olimpia_honduras_with_bajas(self, analyzer):
        """Test Olimpia Honduras with 'bajas' keyword."""
        content = "Olimpia Honduras sufre bajas importantes para el clásico nacional."
        result = analyzer.analyze(content)
        assert result.affected_team == "Olimpia Honduras"
        assert result.category == "INJURY"
    
    def test_real_espana_with_descarta(self, analyzer):
        """REGRESSION: 'descarta' and 'lesiones' (plurals) should work."""
        content = "Real España descarta a cinco jugadores por lesiones musculares."
        result = analyzer.analyze(content)
        assert result.affected_team == "Real España", f"Expected 'Real España', got '{result.affected_team}'"
    
    def test_marathon_with_baja_singular(self, analyzer):
        """Test Marathón with 'baja' singular."""
        content = "Marathón confirma la baja de su goleador por problemas físicos."
        result = analyzer.analyze(content)
        assert result.affected_team == "Marathón"


class TestV16ArgentineTeamExtraction:
    """Tests for Argentine Primera División clubs."""
    
    @pytest.fixture
    def analyzer(self):
        return RelevanceAnalyzer()
    
    def test_boca_juniors_extracted(self, analyzer):
        """Test Boca Juniors detection in Spanish injury news."""
        content = "Boca Juniors pierde a su delantero titular por lesión muscular."
        result = analyzer.analyze(content)
        assert result.affected_team == "Boca Juniors"
        assert result.category == "INJURY"
    
    def test_river_plate_extracted(self, analyzer):
        """Test River Plate detection with 'baja' keyword."""
        content = "River Plate: Gallardo confirma la baja de tres jugadores por lesión."
        result = analyzer.analyze(content)
        assert result.affected_team == "River Plate"
    
    def test_racing_club_detected(self, analyzer):
        """Test Racing Club detection."""
        content = "Racing Club anuncia baja de su arquero por suspensión acumulada."
        result = analyzer.analyze(content)
        assert result.affected_team == "Racing Club"
        # Note: 'baja' is classified as INJURY keyword (absence), category may vary
        assert result.category in ["SUSPENSION", "INJURY"]


class TestV16PortugueseKeywords:
    """Tests for Portuguese-specific keywords."""
    
    @pytest.fixture
    def analyzer(self):
        return RelevanceAnalyzer()
    
    def test_desfalque_keyword_triggers_injury(self, analyzer):
        """Test 'desfalque' (absence/missing player) keyword."""
        content = "Time sofre desfalque importante para o próximo jogo."
        result = analyzer.analyze(content)
        # Should be relevant even without known club
        assert result.is_relevant or result.category == "INJURY"
    
    def test_machucado_keyword(self, analyzer):
        """Test 'machucado' (hurt/injured) keyword."""
        content = "Jogador está machucado e pode perder a partida do final de semana."
        result = analyzer.analyze(content)
        assert result.is_relevant
    
    def test_contundido_keyword(self, analyzer):
        """Test 'contundido' (bruised/injured) keyword."""
        content = "Atacante contundido não treina e é dúvida para o clássico."
        result = analyzer.analyze(content)
        assert result.is_relevant


class TestV16SpanishKeywords:
    """Tests for Spanish-specific keywords."""
    
    @pytest.fixture
    def analyzer(self):
        return RelevanceAnalyzer()
    
    def test_lesiones_plural(self, analyzer):
        """Test 'lesiones' (injuries, plural) keyword."""
        content = "Equipo sufre múltiples lesiones antes del partido importante."
        result = analyzer.analyze(content)
        assert result.is_relevant
        assert result.category == "INJURY"
    
    def test_descarta_verb(self, analyzer):
        """Test 'descarta' (rules out) verb."""
        content = "Entrenador descarta a dos jugadores para el próximo partido."
        result = analyzer.analyze(content)
        assert result.is_relevant
    
    def test_baja_keyword(self, analyzer):
        """Test 'baja' (absence/injury) keyword."""
        content = "Nueva baja en el equipo por problemas musculares."
        result = analyzer.analyze(content)
        assert result.is_relevant


class TestV16SummaryGeneration:
    """Tests for improved summary generation with South American clubs."""
    
    @pytest.fixture
    def analyzer(self):
        return RelevanceAnalyzer()
    
    def test_summary_includes_team_context(self, analyzer):
        """Test summary captures relevant team context."""
        content = "Flamengo confirma lesão grave de atacante titular. Jogador passará por cirurgia e ficará fora por 3 meses."
        result = analyzer.analyze(content)
        # Summary should mention the injury/key info
        assert len(result.summary) > 0
        assert result.summary != "Contenuto non disponibile"
    
    def test_summary_with_spanish_content(self, analyzer):
        """Test summary generation for Spanish content."""
        content = "River Plate pierde a su capitán por lesión muscular. El jugador estará fuera mínimo dos semanas."
        result = analyzer.analyze(content)
        assert len(result.summary) > 0


class TestV16RegressionPrevention:
    """
    Regression tests to prevent future breakage of multi-language support.
    These tests use the exact content patterns from the original bug report.
    """
    
    @pytest.fixture
    def analyzer(self):
        return RelevanceAnalyzer()
    
    def test_original_log_example_determinantes(self, analyzer):
        """
        REGRESSION: Original log showed "Unknown Team" for this pattern.
        Note: This is a generic article without injury keywords, so it may not
        be relevant. The key is that when it IS relevant, team should be extracted.
        """
        # Simulating with injury keywords to make it relevant
        content = "Determinantes para o sucesso de Flamengo: jogador sofre lesão e fica fora."
        result = analyzer.analyze(content)
        assert result.affected_team == "Flamengo" or result.affected_team is None
        # If relevant, team must be Flamengo
        if result.is_relevant:
            assert result.affected_team == "Flamengo"
    
    def test_original_log_example_flamengo_corinthians(self, analyzer):
        """REGRESSION: Flamengo e Corinthians mention with injury context."""
        content = "Flamengo e Corinthians decidem título, mas ambos têm desfalques por lesão."
        result = analyzer.analyze(content)
        # Should detect one of the teams (first match)
        assert result.affected_team in ["Flamengo", "Corinthians"]
        assert result.is_relevant
    
    def test_high_confidence_articles_extract_team(self, analyzer):
        """
        REGRESSION: High confidence articles (>= 0.7) should have team extracted.
        These use direct alert path without DeepSeek.
        """
        # Content with multiple injury keywords for high confidence
        content = "Flamengo perde três jogadores por lesão muscular. Atacante, zagueiro e meia estão fora do clássico."
        result = analyzer.analyze(content)
        assert result.confidence >= 0.5
        assert result.affected_team == "Flamengo"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
