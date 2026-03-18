"""
Test Suite for Injury Impact Integration V13.0

Verifica che:
1. Enum → string conversion funziona correttamente
2. Fuzzy matching per nomi corti funziona
3. Integrazione end-to-end funziona
4. Logica tattica che usa position/reason funziona
5. Nuove funzioni VerifiedData funzionano correttamente
"""

import os
import sys

import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.injury_impact_engine import (
    InjuryPlayerImpact,
    PlayerPosition,
    PlayerRole,
    TeamInjuryImpact,
)
from src.analysis.verification_layer import (
    LogicValidator,
    OptimizedResponseParser,
    PlayerImpact,
    VerificationRequest,
    VerifiedData,
)


class TestEnumToStringConversion:
    """Test Enum → string conversion in _get_player_details_from_injury_impact."""

    def setup_method(self):
        """Setup parser per ogni test."""
        self.parser = OptimizedResponseParser(
            home_team="Home Team",
            away_team="Away Team",
            referee_name="Referee",
            players=["John Smith", "Smith, John", "Lee, Min", "Kim, Young", "Li, Wei", "Park"],
        )

    def test_exact_match_enum_conversion(self):
        """Test che Enum vengono convertiti in stringhe per exact match."""
        # Crea dati di infortunio con Enum
        player = InjuryPlayerImpact(
            name="John Smith",
            position=PlayerPosition.FORWARD,
            role=PlayerRole.STARTER,
            impact_score=8.5,
            reason="injury",
            is_key_player=True,
        )

        team_impact = TeamInjuryImpact(
            team_name="Test Team",
            total_impact_score=8.5,
            missing_starters=1,
            missing_rotation=0,
            missing_backups=0,
            players=[player],
        )

        # Chiama la funzione
        result = self.parser._get_player_details_from_injury_impact("John Smith", team_impact)

        # Verifica che position e role siano stringhe, non Enum
        assert result is not None, "Dovrebbe trovare il giocatore"
        assert isinstance(result["position"], str), (
            f"position dovrebbe essere str, è {type(result['position'])}"
        )
        assert isinstance(result["role"], str), (
            f"role dovrebbe essere str, è {type(result['role'])}"
        )
        assert result["position"] == "forward", f"Atteso 'forward', ottenuto {result['position']}"
        assert result["role"] == "starter", f"Atteso 'starter', ottenuto {result['role']}"
        assert result["reason"] == "injury", f"Atteso 'injury', ottenuto {result['reason']}"

    def test_fuzzy_match_enum_conversion(self):
        """Test che Enum vengono convertiti in stringhe per fuzzy match."""
        # Crea dati di infortunio con Enum
        player = InjuryPlayerImpact(
            name="Smith, John",
            position=PlayerPosition.DEFENDER,
            role=PlayerRole.ROTATION,
            impact_score=6.0,
            reason="suspension",
            is_key_player=False,
        )

        team_impact = TeamInjuryImpact(
            team_name="Test Team",
            total_impact_score=6.0,
            missing_starters=0,
            missing_rotation=1,
            missing_backups=0,
            players=[player],
        )

        # Chiama la funzione con nome in formato diverso
        result = self.parser._get_player_details_from_injury_impact("John Smith", team_impact)

        # Verifica che position e role siano stringhe, non Enum
        assert result is not None, "Dovrebbe trovare il giocatore con fuzzy match"
        assert isinstance(result["position"], str), (
            f"position dovrebbe essere str, è {type(result['position'])}"
        )
        assert isinstance(result["role"], str), (
            f"role dovrebbe essere str, è {type(result['role'])}"
        )
        assert result["position"] == "defender", f"Atteso 'defender', ottenuto {result['position']}"
        assert result["role"] == "rotation", f"Atteso 'rotation', ottenuto {result['role']}"
        assert result["reason"] == "suspension", f"Atteso 'suspension', ottenuto {result['reason']}"

    def test_all_position_types(self):
        """Test che tutte le posizioni vengono convertite correttamente."""
        positions = [
            (PlayerPosition.GOALKEEPER, "goalkeeper"),
            (PlayerPosition.DEFENDER, "defender"),
            (PlayerPosition.MIDFIELDER, "midfielder"),
            (PlayerPosition.FORWARD, "forward"),
            (PlayerPosition.UNKNOWN, "unknown"),
        ]

        for enum_pos, expected_str in positions:
            player = InjuryPlayerImpact(
                name="Test Player",
                position=enum_pos,
                role=PlayerRole.STARTER,
                impact_score=7.0,
                reason="injury",
                is_key_player=True,
            )

            team_impact = TeamInjuryImpact(
                team_name="Test Team",
                total_impact_score=7.0,
                missing_starters=1,
                missing_rotation=0,
                missing_backups=0,
                players=[player],
            )

            result = self.parser._get_player_details_from_injury_impact("Test Player", team_impact)

            assert result is not None, f"Dovrebbe trovare il giocatore per {enum_pos}"
            assert result["position"] == expected_str, (
                f"Atteso {expected_str} per {enum_pos}, ottenuto {result['position']}"
            )

    def test_all_role_types(self):
        """Test che tutti i ruoli vengono convertiti correttamente."""
        roles = [
            (PlayerRole.STARTER, "starter"),
            (PlayerRole.ROTATION, "rotation"),
            (PlayerRole.BACKUP, "backup"),
            (PlayerRole.YOUTH, "youth"),
        ]

        for enum_role, expected_str in roles:
            player = InjuryPlayerImpact(
                name="Test Player",
                position=PlayerPosition.MIDFIELDER,
                role=enum_role,
                impact_score=7.0,
                reason="injury",
                is_key_player=True,
            )

            team_impact = TeamInjuryImpact(
                team_name="Test Team",
                total_impact_score=7.0,
                missing_starters=1,
                missing_rotation=0,
                missing_backups=0,
                players=[player],
            )

            result = self.parser._get_player_details_from_injury_impact("Test Player", team_impact)

            assert result is not None, f"Dovrebbe trovare il giocatore per {enum_role}"
            assert result["role"] == expected_str, (
                f"Atteso {expected_str} per {enum_role}, ottenuto {result['role']}"
            )


class TestFuzzyMatchingShortNames:
    """Test fuzzy matching per nomi corti."""

    def setup_method(self):
        """Setup parser per ogni test."""
        self.parser = OptimizedResponseParser(
            home_team="Home Team",
            away_team="Away Team",
            referee_name="Referee",
            players=["Lee, Min", "Kim, Young", "Li, Wei", "Park"],
        )

    def test_short_name_lee(self):
        """Test fuzzy matching per nome 'Lee' (3 caratteri)."""
        player = InjuryPlayerImpact(
            name="Lee, Min",
            position=PlayerPosition.FORWARD,
            role=PlayerRole.STARTER,
            impact_score=8.0,
            reason="injury",
            is_key_player=True,
        )

        team_impact = TeamInjuryImpact(
            team_name="Test Team",
            total_impact_score=8.0,
            missing_starters=1,
            missing_rotation=0,
            missing_backups=0,
            players=[player],
        )

        # Test con nome corto
        result = self.parser._get_player_details_from_injury_impact("Lee", team_impact)

        assert result is not None, "Dovrebbe trovare il giocatore con nome corto 'Lee'"
        assert result["position"] == "forward"

    def test_short_name_kim(self):
        """Test fuzzy matching per nome 'Kim' (3 caratteri)."""
        player = InjuryPlayerImpact(
            name="Kim, Young",
            position=PlayerPosition.MIDFIELDER,
            role=PlayerRole.STARTER,
            impact_score=7.5,
            reason="suspension",
            is_key_player=True,
        )

        team_impact = TeamInjuryImpact(
            team_name="Test Team",
            total_impact_score=7.5,
            missing_starters=1,
            missing_rotation=0,
            missing_backups=0,
            players=[player],
        )

        # Test con nome corto
        result = self.parser._get_player_details_from_injury_impact("Kim", team_impact)

        assert result is not None, "Dovrebbe trovare il giocatore con nome corto 'Kim'"
        assert result["position"] == "midfielder"

    def test_very_short_name(self):
        """Test fuzzy matching per nome molto corto (2 caratteri)."""
        player = InjuryPlayerImpact(
            name="Li, Wei",
            position=PlayerPosition.DEFENDER,
            role=PlayerRole.ROTATION,
            impact_score=6.0,
            reason="injury",
            is_key_player=False,
        )

        team_impact = TeamInjuryImpact(
            team_name="Test Team",
            total_impact_score=6.0,
            missing_starters=0,
            missing_rotation=1,
            missing_backups=0,
            players=[player],
        )

        # Test con nome molto corto
        result = self.parser._get_player_details_from_injury_impact("Li", team_impact)

        assert result is not None, "Dovrebbe trovare il giocatore con nome molto corto 'Li'"
        assert result["position"] == "defender"

    def test_short_name_no_match(self):
        """Test che nomi corti diversi non matchano."""
        player1 = InjuryPlayerImpact(
            name="Lee, Min",
            position=PlayerPosition.FORWARD,
            role=PlayerRole.STARTER,
            impact_score=8.0,
            reason="injury",
            is_key_player=True,
        )

        player2 = InjuryPlayerImpact(
            name="Kim, Young",
            position=PlayerPosition.MIDFIELDER,
            role=PlayerRole.STARTER,
            impact_score=7.5,
            reason="suspension",
            is_key_player=True,
        )

        team_impact = TeamInjuryImpact(
            team_name="Test Team",
            total_impact_score=15.5,
            missing_starters=2,
            missing_rotation=0,
            missing_backups=0,
            players=[player1, player2],
        )

        # Test con nome corto che non matcha
        result = self.parser._get_player_details_from_injury_impact("Park", team_impact)

        assert result is None, "Non dovrebbe trovare un giocatore con nome 'Park'"


class TestVerifiedDataNewFunctions:
    """Test nuove funzioni aggiunte alla classe VerifiedData."""

    def setup_method(self):
        """Setup VerifiedData per ogni test."""
        self.verified = VerifiedData()

    def test_get_players_by_position(self):
        """Test get_players_by_position."""
        # Aggiungi giocatori con diverse posizioni
        self.verified.home_player_impacts = [
            PlayerImpact(name="Player1", impact_score=8, position="goalkeeper", role="starter"),
            PlayerImpact(name="Player2", impact_score=7, position="defender", role="starter"),
            PlayerImpact(name="Player3", impact_score=6, position="defender", role="rotation"),
            PlayerImpact(name="Player4", impact_score=9, position="forward", role="starter"),
        ]

        # Test per difensori
        defenders = self.verified.get_players_by_position("home", "defender")
        assert len(defenders) == 2, f"Attesi 2 difensori, ottenuti {len(defenders)}"
        assert all(p.position == "defender" for p in defenders), "Tutti dovrebbero essere difensori"

        # Test per portieri
        goalkeepers = self.verified.get_players_by_position("home", "goalkeeper")
        assert len(goalkeepers) == 1, f"Atteso 1 portiere, ottenuti {len(goalkeepers)}"
        assert goalkeepers[0].name == "Player1"

        # Test per tutti
        all_players = self.verified.get_players_by_position("home", None)
        assert len(all_players) == 4, f"Attesi 4 giocatori, ottenuti {len(all_players)}"

    def test_has_critical_goalkeeper_missing(self):
        """Test has_critical_goalkeeper_missing."""
        # Test con portiere critico mancante
        self.verified.home_player_impacts = [
            PlayerImpact(name="GK1", impact_score=8, position="goalkeeper", role="starter"),
        ]
        assert self.verified.has_critical_goalkeeper_missing("home"), (
            "Dovrebbe rilevare portiere critico mancante"
        )

        # Test con portiere non critico
        self.verified.home_player_impacts = [
            PlayerImpact(name="GK2", impact_score=5, position="goalkeeper", role="backup"),
        ]
        assert not self.verified.has_critical_goalkeeper_missing("home"), (
            "Non dovrebbe rilevare portiere non critico"
        )

        # Test senza portieri
        self.verified.home_player_impacts = [
            PlayerImpact(name="DEF1", impact_score=8, position="defender", role="starter"),
        ]
        assert not self.verified.has_critical_goalkeeper_missing("home"), (
            "Non dovrebbe rilevare senza portieri"
        )

    def test_has_critical_defense_missing(self):
        """Test has_critical_defense_missing."""
        # Test con 2+ difensori critici mancanti
        self.verified.home_player_impacts = [
            PlayerImpact(name="DEF1", impact_score=7, position="defender", role="starter"),
            PlayerImpact(name="DEF2", impact_score=8, position="defender", role="starter"),
        ]
        assert self.verified.has_critical_defense_missing("home"), (
            "Dovrebbe rilevare difesa critica mancante"
        )

        # Test con 1 difensore critico
        self.verified.home_player_impacts = [
            PlayerImpact(name="DEF1", impact_score=7, position="defender", role="starter"),
        ]
        assert not self.verified.has_critical_defense_missing("home"), (
            "Non dovrebbe rilevare con solo 1 difensore"
        )

        # Test con 2 difensori non critici
        self.verified.home_player_impacts = [
            PlayerImpact(name="DEF1", impact_score=5, position="defender", role="rotation"),
            PlayerImpact(name="DEF2", impact_score=5, position="defender", role="rotation"),
        ]
        assert not self.verified.has_critical_defense_missing("home"), (
            "Non dovrebbe rilevare difensori non critici"
        )

    def test_get_position_impact_summary(self):
        """Test get_position_impact_summary."""
        self.verified.home_player_impacts = [
            PlayerImpact(name="GK1", impact_score=8, position="goalkeeper", role="starter"),
            PlayerImpact(name="DEF1", impact_score=7, position="defender", role="starter"),
            PlayerImpact(name="DEF2", impact_score=6, position="defender", role="rotation"),
            PlayerImpact(name="MID1", impact_score=5, position="midfielder", role="starter"),
            PlayerImpact(name="FWD1", impact_score=9, position="forward", role="starter"),
        ]

        summary = self.verified.get_position_impact_summary("home")

        assert summary["goalkeeper"] == 8.0, (
            f"Atteso 8.0 per goalkeeper, ottenuto {summary['goalkeeper']}"
        )
        assert summary["defender"] == 13.0, (
            f"Atteso 13.0 per defender, ottenuto {summary['defender']}"
        )
        assert summary["midfielder"] == 5.0, (
            f"Atteso 5.0 per midfielder, ottenuto {summary['midfielder']}"
        )
        assert summary["forward"] == 9.0, f"Atteso 9.0 per forward, ottenuto {summary['forward']}"

    def test_get_reason_impact_summary(self):
        """Test get_reason_impact_summary."""
        self.verified.home_player_impacts = [
            PlayerImpact(
                name="P1", impact_score=8, position="defender", role="starter", reason="injury"
            ),
            PlayerImpact(
                name="P2", impact_score=7, position="midfielder", role="starter", reason="injury"
            ),
            PlayerImpact(
                name="P3", impact_score=6, position="forward", role="starter", reason="suspension"
            ),
            PlayerImpact(
                name="P4", impact_score=5, position="defender", role="rotation", reason="suspension"
            ),
        ]

        summary = self.verified.get_reason_impact_summary("home")

        assert summary["injury"] == 15.0, f"Atteso 15.0 per injury, ottenuto {summary['injury']}"
        assert summary["suspension"] == 11.0, (
            f"Atteso 11.0 per suspension, ottenuto {summary['suspension']}"
        )


class TestTacticalLogicIntegration:
    """Test integrazione logica tattica con position/reason."""

    def setup_method(self):
        """Setup validator e dati per ogni test."""
        self.validator = LogicValidator()

    def test_critical_goalkeeper_detection_in_consistency_check(self):
        """Test che portiere critico mancante viene rilevato in _check_injury_market_consistency."""
        # Crea VerifiedData con portiere critico mancante
        verified = VerifiedData()
        verified.home_player_impacts = [
            PlayerImpact(
                name="GK1", impact_score=8, position="goalkeeper", role="starter", reason="injury"
            ),
        ]

        # Crea request per mercato Over
        request = VerificationRequest(
            match_id="test1",
            home_team="Home",
            away_team="Away",
            match_date="2024-01-01",
            league="Test League",
            suggested_market="Over 2.5 Goals",
            preliminary_score=75,
            home_missing_players=["GK1"],
            away_missing_players=[],
            home_injury_severity="HIGH",
            away_injury_severity="LOW",
        )

        # Chiama la funzione
        issues = self.validator._check_injury_market_consistency(request, verified)

        # Verifica che venga rilevato il portiere critico
        assert len(issues) > 0, "Dovrebbe rilevare problemi"
        assert any("portiere" in issue.lower() for issue in issues), (
            "Dovrebbe menzionare il portiere"
        )

    def test_critical_defense_detection_in_consistency_check(self):
        """Test che difesa critica mancante viene rilevata in _check_injury_market_consistency."""
        # Crea VerifiedData con difesa critica mancante
        verified = VerifiedData()
        verified.home_player_impacts = [
            PlayerImpact(
                name="DEF1", impact_score=7, position="defender", role="starter", reason="injury"
            ),
            PlayerImpact(
                name="DEF2", impact_score=8, position="defender", role="starter", reason="injury"
            ),
        ]

        # Crea request per mercato Over
        request = VerificationRequest(
            match_id="test2",
            home_team="Home",
            away_team="Away",
            match_date="2024-01-01",
            league="Test League",
            suggested_market="Over 2.5 Goals",
            preliminary_score=75,
            home_missing_players=["DEF1", "DEF2"],
            away_missing_players=[],
            home_injury_severity="HIGH",
            away_injury_severity="LOW",
        )

        # Chiama la funzione
        issues = self.validator._check_injury_market_consistency(request, verified)

        # Verifica che venga rilevata la difesa critica
        assert len(issues) > 0, "Dovrebbe rilevare problemi"
        assert any("difensor" in issue.lower() for issue in issues), (
            "Dovrebbe menzionare i difensori"
        )

    def test_position_impact_summary_in_consistency_check(self):
        """Test che riepilogo impatto per posizione viene usato in _check_injury_market_consistency."""
        # Crea VerifiedData con alto impatto difensivo
        verified = VerifiedData()
        verified.home_player_impacts = [
            PlayerImpact(
                name="GK1", impact_score=8, position="goalkeeper", role="starter", reason="injury"
            ),
            PlayerImpact(
                name="DEF1", impact_score=7, position="defender", role="starter", reason="injury"
            ),
            PlayerImpact(
                name="DEF2", impact_score=6, position="defender", role="rotation", reason="injury"
            ),
        ]

        # Crea request per mercato Over
        request = VerificationRequest(
            match_id="test3",
            home_team="Home",
            away_team="Away",
            match_date="2024-01-01",
            league="Test League",
            suggested_market="Over 2.5 Goals",
            preliminary_score=75,
            home_missing_players=["GK1", "DEF1", "DEF2"],
            away_missing_players=[],
            home_injury_severity="HIGH",
            away_injury_severity="LOW",
        )

        # Chiama la funzione
        issues = self.validator._check_injury_market_consistency(request, verified)

        # Verifica che venga rilevato l'alto impatto difensivo
        assert len(issues) > 0, "Dovrebbe rilevare problemi"
        assert any(
            "difensiv" in issue.lower() or "gol subiti" in issue.lower() for issue in issues
        ), "Dovrebbe menzionare impatto difensivo"

    def test_reason_impact_summary_in_consistency_check(self):
        """Test che riepilogo impatto per motivo viene usato in _check_injury_market_consistency."""
        # Crea VerifiedData con multiple squalifiche
        verified = VerifiedData()
        verified.home_player_impacts = [
            PlayerImpact(
                name="P1", impact_score=8, position="defender", role="starter", reason="suspension"
            ),
            PlayerImpact(
                name="P2",
                impact_score=7,
                position="midfielder",
                role="starter",
                reason="suspension",
            ),
        ]

        # Crea request per mercato Over
        request = VerificationRequest(
            match_id="test4",
            home_team="Home",
            away_team="Away",
            match_date="2024-01-01",
            league="Test League",
            suggested_market="Over 2.5 Goals",
            preliminary_score=75,
            home_missing_players=["P1", "P2"],
            away_missing_players=[],
            home_injury_severity="HIGH",
            away_injury_severity="LOW",
        )

        # Chiama la funzione
        issues = self.validator._check_injury_market_consistency(request, verified)

        # Verifica che vengano rilevate le squalifiche
        assert len(issues) > 0, "Dovrebbe rilevare problemi"
        assert any("squalific" in issue.lower() for issue in issues), (
            "Dovrebbe menzionare le squalifiche"
        )


class TestEndToEndIntegration:
    """Test integrazione end-to-end dell'injury impact V13.0."""

    def setup_method(self):
        """Setup parser per ogni test."""
        self.parser = OptimizedResponseParser(
            home_team="Home Team",
            away_team="Away Team",
            referee_name="Referee",
            players=["GK1", "DEF1", "MID1", "Lee, Min", "Kim, Young"],
        )

    def test_full_integration_with_injury_impact_engine(self):
        """Test integrazione completa con injury_impact_engine."""
        # Crea dati di infortunio completi
        players = [
            InjuryPlayerImpact(
                name="GK1",
                position=PlayerPosition.GOALKEEPER,
                role=PlayerRole.STARTER,
                impact_score=8.5,
                reason="injury",
                is_key_player=True,
            ),
            InjuryPlayerImpact(
                name="DEF1",
                position=PlayerPosition.DEFENDER,
                role=PlayerRole.STARTER,
                impact_score=7.0,
                reason="suspension",
                is_key_player=True,
            ),
            InjuryPlayerImpact(
                name="MID1",
                position=PlayerPosition.MIDFIELDER,
                role=PlayerRole.ROTATION,
                impact_score=5.0,
                reason="injury",
                is_key_player=False,
            ),
        ]

        team_impact = TeamInjuryImpact(
            team_name="Test Team",
            total_impact_score=20.5,
            missing_starters=2,
            missing_rotation=1,
            missing_backups=0,
            players=players,
        )

        # Test estrazione dettagli giocatore
        result = self.parser._get_player_details_from_injury_impact("GK1", team_impact)

        assert result is not None, "Dovrebbe trovare il giocatore"
        assert isinstance(result["position"], str), "position dovrebbe essere stringa"
        assert isinstance(result["role"], str), "role dovrebbe essere stringa"
        assert result["position"] == "goalkeeper"
        assert result["role"] == "starter"
        assert result["reason"] == "injury"

        # Test con nome in formato diverso
        result2 = self.parser._get_player_details_from_injury_impact("MID1", team_impact)

        assert result2 is not None, "Dovrebbe trovare il giocatore"
        assert result2["position"] == "midfielder"
        assert result2["role"] == "rotation"

    def test_multiple_teams_integration(self):
        """Test integrazione con multiple squadre."""
        # Crea dati per home team
        home_players = [
            InjuryPlayerImpact(
                name="Lee, Min",
                position=PlayerPosition.FORWARD,
                role=PlayerRole.STARTER,
                impact_score=8.0,
                reason="injury",
                is_key_player=True,
            ),
        ]

        home_impact = TeamInjuryImpact(
            team_name="Home Team",
            total_impact_score=8.0,
            missing_starters=1,
            missing_rotation=0,
            missing_backups=0,
            players=home_players,
        )

        # Crea dati per away team
        away_players = [
            InjuryPlayerImpact(
                name="Kim, Young",
                position=PlayerPosition.MIDFIELDER,
                role=PlayerRole.STARTER,
                impact_score=7.5,
                reason="suspension",
                is_key_player=True,
            ),
        ]

        away_impact = TeamInjuryImpact(
            team_name="Away Team",
            total_impact_score=7.5,
            missing_starters=1,
            missing_rotation=0,
            missing_backups=0,
            players=away_players,
        )

        # Test estrazione da home team con nome corto
        home_result = self.parser._get_player_details_from_injury_impact("Lee", home_impact)

        assert home_result is not None, "Dovrebbe trovare Lee con nome corto"
        assert home_result["position"] == "forward"

        # Test estrazione da away team con nome corto
        away_result = self.parser._get_player_details_from_injury_impact("Kim", away_impact)

        assert away_result is not None, "Dovrebbe trovare Kim con nome corto"
        assert away_result["position"] == "midfielder"
        assert away_result["reason"] == "suspension"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
