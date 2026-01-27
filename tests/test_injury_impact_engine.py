"""
Test per Injury Impact Engine V5.3.1

Verifica:
1. Calcolo impatto singolo giocatore
2. Aggregazione impatto squadra
3. Calcolo differenziale tra squadre
4. Edge cases (liste vuote, None, dati mancanti)
5. Regression test per bug noti
6. Context-aware score adjustment (V5.3.1)
"""
import pytest
from src.analysis.injury_impact_engine import (
    PlayerRole,
    PlayerPosition,
    PlayerImpact,
    TeamInjuryImpact,
    InjuryDifferential,
    detect_position_from_group,
    detect_position_from_player_data,
    estimate_player_role,
    calculate_player_impact,
    calculate_team_injury_impact,
    calculate_injury_differential,
    analyze_match_injuries,
    _build_player_info_map
)


class TestPositionDetection:
    """Test per rilevamento posizione giocatore."""
    
    def test_detect_goalkeeper_from_group(self):
        """Rileva portiere dal titolo gruppo."""
        assert detect_position_from_group("Goalkeepers") == PlayerPosition.GOALKEEPER
        assert detect_position_from_group("Portieri") == PlayerPosition.GOALKEEPER
        assert detect_position_from_group("GK") == PlayerPosition.GOALKEEPER
    
    def test_detect_defender_from_group(self):
        """Rileva difensore dal titolo gruppo."""
        assert detect_position_from_group("Defenders") == PlayerPosition.DEFENDER
        assert detect_position_from_group("Difensori") == PlayerPosition.DEFENDER
        assert detect_position_from_group("Defence") == PlayerPosition.DEFENDER
    
    def test_detect_midfielder_from_group(self):
        """Rileva centrocampista dal titolo gruppo."""
        assert detect_position_from_group("Midfielders") == PlayerPosition.MIDFIELDER
        assert detect_position_from_group("Centrocampisti") == PlayerPosition.MIDFIELDER
    
    def test_detect_forward_from_group(self):
        """Rileva attaccante dal titolo gruppo."""
        assert detect_position_from_group("Forwards") == PlayerPosition.FORWARD
        assert detect_position_from_group("Strikers") == PlayerPosition.FORWARD
        assert detect_position_from_group("Attaccanti") == PlayerPosition.FORWARD
    
    def test_detect_unknown_from_empty(self):
        """Gruppo vuoto o None ritorna UNKNOWN."""
        assert detect_position_from_group("") == PlayerPosition.UNKNOWN
        assert detect_position_from_group(None) == PlayerPosition.UNKNOWN
        assert detect_position_from_group("Coaches") == PlayerPosition.UNKNOWN
    
    def test_detect_position_from_player_data(self):
        """Rileva posizione dai dati giocatore."""
        assert detect_position_from_player_data({'position': 'Goalkeeper'}) == PlayerPosition.GOALKEEPER
        assert detect_position_from_player_data({'positionDescription': 'Central Defender'}) == PlayerPosition.DEFENDER
        assert detect_position_from_player_data({'role': 'Striker'}) == PlayerPosition.FORWARD
    
    def test_detect_position_from_player_data_none(self):
        """Dati giocatore None o vuoti."""
        assert detect_position_from_player_data(None) == PlayerPosition.UNKNOWN
        assert detect_position_from_player_data({}) == PlayerPosition.UNKNOWN
        assert detect_position_from_player_data({'name': 'Test'}) == PlayerPosition.UNKNOWN


class TestRoleEstimation:
    """Test per stima ruolo giocatore (titolare/riserva)."""
    
    def test_first_player_is_starter(self):
        """Primo giocatore del gruppo è titolare."""
        role = estimate_player_role(
            player={'name': 'Test'},
            group_index=0,
            player_index_in_group=0,
            total_in_group=4
        )
        assert role == PlayerRole.STARTER
    
    def test_youth_player_detected(self):
        """Giocatore giovane rilevato."""
        role = estimate_player_role(
            player={'name': 'Test', 'isYouth': True},
            group_index=0,
            player_index_in_group=0,
            total_in_group=4
        )
        assert role == PlayerRole.YOUTH
    
    def test_high_appearances_is_starter(self):
        """Molte presenze = titolare."""
        role = estimate_player_role(
            player={'name': 'Test', 'stats': {'appearances': 20}},
            group_index=0,
            player_index_in_group=3,
            total_in_group=4
        )
        assert role == PlayerRole.STARTER
    
    def test_medium_appearances_is_rotation(self):
        """Presenze medie = rotazione."""
        role = estimate_player_role(
            player={'name': 'Test', 'stats': {'appearances': 10}},
            group_index=0,
            player_index_in_group=3,
            total_in_group=4
        )
        assert role == PlayerRole.ROTATION
    
    def test_last_player_is_backup(self):
        """Ultimo giocatore del gruppo è riserva."""
        role = estimate_player_role(
            player={'name': 'Test'},
            group_index=0,
            player_index_in_group=3,
            total_in_group=4
        )
        assert role == PlayerRole.BACKUP
    
    def test_none_player_returns_backup(self):
        """Giocatore None ritorna BACKUP (safe default)."""
        role = estimate_player_role(
            player=None,
            group_index=0,
            player_index_in_group=0,
            total_in_group=4
        )
        assert role == PlayerRole.BACKUP


class TestPlayerImpactCalculation:
    """Test per calcolo impatto singolo giocatore."""
    
    def test_starter_goalkeeper_high_impact(self):
        """Portiere titolare ha impatto alto."""
        impact = calculate_player_impact(
            player_name="Donnarumma",
            position=PlayerPosition.GOALKEEPER,
            role=PlayerRole.STARTER,
            reason="Injury",
            is_key_player=False
        )
        assert impact.impact_score >= 8.0  # 3.0 * 3.0 = 9.0
        assert impact.role == PlayerRole.STARTER
    
    def test_backup_forward_low_impact(self):
        """Attaccante riserva ha impatto basso."""
        impact = calculate_player_impact(
            player_name="Backup Striker",
            position=PlayerPosition.FORWARD,
            role=PlayerRole.BACKUP,
            reason="Injury",
            is_key_player=False
        )
        assert impact.impact_score <= 2.0  # 2.5 * 0.5 = 1.25
    
    def test_key_player_bonus(self):
        """Key player ha bonus."""
        impact_normal = calculate_player_impact(
            player_name="Player",
            position=PlayerPosition.MIDFIELDER,
            role=PlayerRole.STARTER,
            reason="Injury",
            is_key_player=False
        )
        impact_key = calculate_player_impact(
            player_name="Captain",
            position=PlayerPosition.MIDFIELDER,
            role=PlayerRole.STARTER,
            reason="Injury",
            is_key_player=True
        )
        assert impact_key.impact_score > impact_normal.impact_score
    
    def test_impact_capped_at_10(self):
        """Impact score non supera 10."""
        impact = calculate_player_impact(
            player_name="Super Player",
            position=PlayerPosition.GOALKEEPER,
            role=PlayerRole.STARTER,
            reason="Injury",
            is_key_player=True
        )
        assert impact.impact_score <= 10.0


class TestTeamInjuryImpact:
    """Test per calcolo impatto squadra."""
    
    def test_empty_injuries_zero_impact(self):
        """Lista infortuni vuota = impatto zero."""
        impact = calculate_team_injury_impact(
            team_name="Test FC",
            injuries=[],
            squad_data=None
        )
        assert impact.total_impact_score == 0.0
        assert impact.missing_starters == 0
        assert impact.severity == "LOW"
    
    def test_none_injuries_zero_impact(self):
        """Injuries None = impatto zero (no crash)."""
        impact = calculate_team_injury_impact(
            team_name="Test FC",
            injuries=None,
            squad_data=None
        )
        assert impact.total_impact_score == 0.0
    
    def test_multiple_injuries_aggregated(self):
        """Più infortuni vengono aggregati."""
        injuries = [
            {'name': 'Player1', 'reason': 'Injury'},
            {'name': 'Player2', 'reason': 'Suspension'},
            {'name': 'Player3', 'reason': 'Injury'}
        ]
        impact = calculate_team_injury_impact(
            team_name="Test FC",
            injuries=injuries,
            squad_data=None
        )
        assert len(impact.players) == 3
        assert impact.total_impact_score > 0
    
    def test_severity_critical_with_many_starters(self):
        """Severity CRITICAL con molti titolari assenti."""
        # Simula 3 titolari assenti con squad_data che li identifica come starter
        squad_data = {
            'squad': [
                {
                    'title': 'Midfielders',
                    'members': [
                        {'name': 'Player1', 'stats': {'appearances': 20}},
                        {'name': 'Player2', 'stats': {'appearances': 18}},
                        {'name': 'Player3', 'stats': {'appearances': 15}},
                    ]
                }
            ]
        }
        injuries = [
            {'name': 'Player1', 'reason': 'Injury'},
            {'name': 'Player2', 'reason': 'Injury'},
            {'name': 'Player3', 'reason': 'Injury'}
        ]
        impact = calculate_team_injury_impact(
            team_name="Test FC",
            injuries=injuries,
            squad_data=squad_data
        )
        assert impact.missing_starters >= 3
        assert impact.severity == "CRITICAL"
    
    def test_key_players_tracked(self):
        """Key players vengono tracciati."""
        injuries = [
            {'name': 'Messi', 'reason': 'Injury'},
            {'name': 'Unknown', 'reason': 'Injury'}
        ]
        impact = calculate_team_injury_impact(
            team_name="Test FC",
            injuries=injuries,
            squad_data=None,
            key_players=['Messi', 'Ronaldo']
        )
        assert 'Messi' in impact.key_players_out
        assert 'Unknown' not in impact.key_players_out
    
    def test_invalid_injury_dict_skipped(self):
        """Injury dict invalido viene saltato."""
        injuries = [
            {'name': 'Valid', 'reason': 'Injury'},
            'invalid_string',
            None,
            {'no_name_key': 'test'}
        ]
        impact = calculate_team_injury_impact(
            team_name="Test FC",
            injuries=injuries,
            squad_data=None
        )
        assert len(impact.players) == 1  # Solo 'Valid'


class TestInjuryDifferential:
    """Test per calcolo differenziale tra squadre."""
    
    def test_balanced_injuries_zero_differential(self):
        """Infortuni bilanciati = differenziale ~0."""
        diff = calculate_injury_differential(
            home_team="Home FC",
            away_team="Away FC",
            home_injuries=[{'name': 'Player1', 'reason': 'Injury'}],
            away_injuries=[{'name': 'Player2', 'reason': 'Injury'}]
        )
        assert abs(diff.differential) < 5.0  # Tolleranza
    
    def test_home_more_injured_positive_differential(self):
        """Home più colpita = differenziale positivo."""
        diff = calculate_injury_differential(
            home_team="Home FC",
            away_team="Away FC",
            home_injuries=[
                {'name': 'Player1', 'reason': 'Injury'},
                {'name': 'Player2', 'reason': 'Injury'},
                {'name': 'Player3', 'reason': 'Injury'}
            ],
            away_injuries=[]
        )
        assert diff.differential > 0
        assert diff.favors_away is True
        assert diff.favors_home is False
    
    def test_away_more_injured_negative_differential(self):
        """Away più colpita = differenziale negativo."""
        diff = calculate_injury_differential(
            home_team="Home FC",
            away_team="Away FC",
            home_injuries=[],
            away_injuries=[
                {'name': 'Player1', 'reason': 'Injury'},
                {'name': 'Player2', 'reason': 'Injury'},
                {'name': 'Player3', 'reason': 'Injury'}
            ]
        )
        assert diff.differential < 0
        assert diff.favors_home is True
        assert diff.favors_away is False
    
    def test_score_adjustment_capped(self):
        """Score adjustment è limitato a ±1.5."""
        diff = calculate_injury_differential(
            home_team="Home FC",
            away_team="Away FC",
            home_injuries=[{'name': f'Player{i}', 'reason': 'Injury'} for i in range(10)],
            away_injuries=[]
        )
        assert -1.8 <= diff.score_adjustment <= 1.8  # Con bonus può arrivare a 1.8
    
    def test_empty_injuries_both_teams(self):
        """Nessun infortunio = differenziale 0."""
        diff = calculate_injury_differential(
            home_team="Home FC",
            away_team="Away FC",
            home_injuries=[],
            away_injuries=[]
        )
        assert diff.differential == 0.0
        assert diff.score_adjustment == 0.0
    
    def test_none_injuries_no_crash(self):
        """Injuries None non causa crash."""
        diff = calculate_injury_differential(
            home_team="Home FC",
            away_team="Away FC",
            home_injuries=None,
            away_injuries=None
        )
        assert diff.differential == 0.0


class TestAnalyzeMatchInjuries:
    """Test per funzione principale analyze_match_injuries."""
    
    def test_with_context_dicts(self):
        """Funziona con context dict completi."""
        home_context = {
            'injuries': [{'name': 'Player1', 'reason': 'Injury'}],
            'squad': None
        }
        away_context = {
            'injuries': [],
            'squad': None
        }
        diff = analyze_match_injuries(
            home_team="Home FC",
            away_team="Away FC",
            home_context=home_context,
            away_context=away_context
        )
        assert diff.home_impact.team_name == "Home FC"
        assert diff.away_impact.team_name == "Away FC"
    
    def test_with_none_context(self):
        """Funziona con context None."""
        diff = analyze_match_injuries(
            home_team="Home FC",
            away_team="Away FC",
            home_context=None,
            away_context=None
        )
        assert diff.differential == 0.0
    
    def test_with_key_players(self):
        """Key players vengono considerati."""
        home_context = {
            'injuries': [{'name': 'Messi', 'reason': 'Injury'}]
        }
        diff = analyze_match_injuries(
            home_team="Home FC",
            away_team="Away FC",
            home_context=home_context,
            away_context=None,
            home_key_players=['Messi']
        )
        assert 'Messi' in diff.home_impact.key_players_out


class TestBuildPlayerInfoMap:
    """Test per costruzione mappa giocatori."""
    
    def test_build_from_squad_data(self):
        """Costruisce mappa da squad_data."""
        squad_data = {
            'squad': [
                {
                    'title': 'Goalkeepers',
                    'members': [
                        {'name': 'Keeper1'},
                        {'name': 'Keeper2'}
                    ]
                },
                {
                    'title': 'Defenders',
                    'members': [
                        {'name': 'Defender1'}
                    ]
                }
            ]
        }
        player_map = _build_player_info_map(squad_data)
        
        assert 'keeper1' in player_map
        assert player_map['keeper1']['position'] == PlayerPosition.GOALKEEPER
        assert 'defender1' in player_map
        assert player_map['defender1']['position'] == PlayerPosition.DEFENDER
    
    def test_build_from_none(self):
        """None ritorna mappa vuota."""
        assert _build_player_info_map(None) == {}
    
    def test_build_from_empty(self):
        """Dict vuoto ritorna mappa vuota."""
        assert _build_player_info_map({}) == {}
    
    def test_nested_squad_structure(self):
        """Gestisce struttura annidata {'squad': {'squad': [...]}}."""
        squad_data = {
            'squad': {
                'squad': [
                    {
                        'title': 'Forwards',
                        'members': [{'name': 'Striker1'}]
                    }
                ]
            }
        }
        player_map = _build_player_info_map(squad_data)
        assert 'striker1' in player_map
        assert player_map['striker1']['position'] == PlayerPosition.FORWARD


class TestEdgeCases:
    """Test per edge cases e regression."""
    
    def test_injury_with_empty_name(self):
        """Injury con nome vuoto viene saltato."""
        injuries = [
            {'name': '', 'reason': 'Injury'},
            {'name': 'Valid', 'reason': 'Injury'}
        ]
        impact = calculate_team_injury_impact(
            team_name="Test FC",
            injuries=injuries
        )
        assert len(impact.players) == 1
    
    def test_injury_with_none_name(self):
        """Injury con nome None viene saltato."""
        injuries = [
            {'name': None, 'reason': 'Injury'},
            {'name': 'Valid', 'reason': 'Injury'}
        ]
        impact = calculate_team_injury_impact(
            team_name="Test FC",
            injuries=injuries
        )
        assert len(impact.players) == 1
    
    def test_division_by_zero_avoided(self):
        """Nessuna divisione per zero."""
        # total_in_group = 0 non dovrebbe causare crash
        role = estimate_player_role(
            player={'name': 'Test'},
            group_index=0,
            player_index_in_group=0,
            total_in_group=0
        )
        # Non deve crashare, ritorna un ruolo valido
        assert role in PlayerRole
    
    def test_severity_property(self):
        """Severity property funziona correttamente."""
        impact = TeamInjuryImpact(
            team_name="Test",
            total_impact_score=20.0,
            missing_starters=4,
            missing_rotation=0,
            missing_backups=0,
            key_players_out=[],
            defensive_impact=10.0,
            offensive_impact=10.0,
            players=[]
        )
        assert impact.severity == "CRITICAL"
    
    def test_differential_summary_generated(self):
        """Summary viene generato correttamente."""
        diff = calculate_injury_differential(
            home_team="Home FC",
            away_team="Away FC",
            home_injuries=[{'name': 'Player1', 'reason': 'Injury'}],
            away_injuries=[]
        )
        assert diff.summary is not None
        assert len(diff.summary) > 0
        assert "Home FC" in diff.summary


class TestIntegrationWithAnalyzer:
    """
    Test di integrazione per verificare che l'injury impact engine
    si integri correttamente con l'analyzer.
    
    REGRESSION: Verifica che il differenziale venga calcolato correttamente
    quando una squadra ha più titolari assenti dell'altra.
    """
    
    def test_starter_vs_backup_differential(self):
        """
        REGRESSION TEST: 2 titolari assenti vs 2 riserve assenti
        deve produrre un differenziale significativo.
        
        Scenario: Home perde 2 titolari, Away perde 2 riserve
        Expected: differential > 0 (home più colpita), score_adjustment > 0 (favorisce away)
        """
        # Home: 2 titolari (simulati con stats alte)
        home_squad = {
            'squad': [
                {
                    'title': 'Midfielders',
                    'members': [
                        {'name': 'Star1', 'stats': {'appearances': 25}},
                        {'name': 'Star2', 'stats': {'appearances': 22}},
                        {'name': 'Backup1', 'stats': {'appearances': 5}},
                    ]
                }
            ]
        }
        home_injuries = [
            {'name': 'Star1', 'reason': 'Injury'},
            {'name': 'Star2', 'reason': 'Injury'}
        ]
        
        # Away: 2 riserve (simulati con stats basse)
        away_squad = {
            'squad': [
                {
                    'title': 'Midfielders',
                    'members': [
                        {'name': 'AwayStarter', 'stats': {'appearances': 20}},
                        {'name': 'AwayBackup1', 'stats': {'appearances': 3}},
                        {'name': 'AwayBackup2', 'stats': {'appearances': 2}},
                    ]
                }
            ]
        }
        away_injuries = [
            {'name': 'AwayBackup1', 'reason': 'Injury'},
            {'name': 'AwayBackup2', 'reason': 'Injury'}
        ]
        
        diff = calculate_injury_differential(
            home_team="Home FC",
            away_team="Away FC",
            home_injuries=home_injuries,
            away_injuries=away_injuries,
            home_squad=home_squad,
            away_squad=away_squad
        )
        
        # Home ha perso 2 titolari, Away ha perso 2 riserve
        # Il differenziale deve essere positivo (home più colpita)
        assert diff.differential > 0, f"Expected positive differential, got {diff.differential}"
        assert diff.home_impact.missing_starters == 2, f"Expected 2 home starters missing, got {diff.home_impact.missing_starters}"
        assert diff.away_impact.missing_starters == 0, f"Expected 0 away starters missing, got {diff.away_impact.missing_starters}"
        
        # Score adjustment deve favorire away (positivo)
        assert diff.score_adjustment >= 0, f"Expected non-negative score_adjustment, got {diff.score_adjustment}"
        
        # Severity check
        assert diff.home_impact.severity in ("HIGH", "CRITICAL"), f"Expected HIGH/CRITICAL severity for home, got {diff.home_impact.severity}"
        assert diff.away_impact.severity == "LOW", f"Expected LOW severity for away, got {diff.away_impact.severity}"
    
    def test_goalkeeper_absence_high_impact(self):
        """
        REGRESSION TEST: Portiere titolare assente deve avere impatto critico.
        """
        home_squad = {
            'squad': [
                {
                    'title': 'Goalkeepers',
                    'members': [
                        {'name': 'MainKeeper', 'stats': {'appearances': 30}},
                        {'name': 'BackupKeeper', 'stats': {'appearances': 2}},
                    ]
                }
            ]
        }
        home_injuries = [{'name': 'MainKeeper', 'reason': 'Injury'}]
        
        diff = calculate_injury_differential(
            home_team="Home FC",
            away_team="Away FC",
            home_injuries=home_injuries,
            away_injuries=[],
            home_squad=home_squad,
            away_squad=None
        )
        
        # Portiere titolare assente = impatto alto
        assert diff.home_impact.total_impact_score >= 8.0, f"Expected high impact for GK, got {diff.home_impact.total_impact_score}"
        assert diff.home_impact.defensive_impact >= 8.0, f"Expected high defensive impact, got {diff.home_impact.defensive_impact}"
    
    def test_context_dict_format_compatibility(self):
        """
        REGRESSION TEST: Verifica compatibilità con il formato context
        passato da main.py (dict con chiave 'injuries').
        """
        # Formato esatto usato in main.py
        home_context = {
            'injuries': [
                {'name': 'Player1', 'reason': 'Knee injury', 'status': 'Out'},
                {'name': 'Player2', 'reason': 'Suspended', 'status': 'Out'}
            ],
            'squad': None,  # Può essere None
            'fatigue': {'level': 'LOW'}  # Altri campi ignorati
        }
        away_context = {
            'injuries': [],
            'squad': None
        }
        
        # Non deve crashare
        diff = analyze_match_injuries(
            home_team="Home FC",
            away_team="Away FC",
            home_context=home_context,
            away_context=away_context
        )
        
        assert diff is not None
        assert len(diff.home_impact.players) == 2
        assert len(diff.away_impact.players) == 0


class TestContextAwareAdjustment:
    """
    Test V5.3.1: Context-aware score adjustment.
    
    Verifica che l'adjustment venga applicato correttamente
    in base al mercato raccomandato.
    """
    
    def test_score_adjustment_raw_value(self):
        """
        REGRESSION TEST: score_adjustment deve essere il valore RAW
        (positivo se Home più colpita, negativo se Away più colpita).
        L'inversione context-aware avviene in analyzer.py.
        """
        # Home ha 3 infortuni, Away 0
        diff = calculate_injury_differential(
            home_team="Home FC",
            away_team="Away FC",
            home_injuries=[
                {'name': 'Player1', 'reason': 'Injury'},
                {'name': 'Player2', 'reason': 'Injury'},
                {'name': 'Player3', 'reason': 'Injury'}
            ],
            away_injuries=[]
        )
        
        # Home più colpita = differential positivo
        assert diff.differential > 0
        # score_adjustment deve essere positivo (raw value)
        assert diff.score_adjustment > 0
    
    def test_no_btts_adjustment_field(self):
        """
        REGRESSION TEST: btts_adjustment è stato rimosso (dead code).
        InjuryDifferential non deve avere questo campo.
        """
        diff = calculate_injury_differential(
            home_team="Home FC",
            away_team="Away FC",
            home_injuries=[{'name': 'Player1', 'reason': 'Injury'}],
            away_injuries=[]
        )
        
        # btts_adjustment non deve esistere
        assert not hasattr(diff, 'btts_adjustment')
    
    def test_edge_case_single_player_group(self):
        """
        REGRESSION TEST: Gruppo con un solo giocatore deve essere STARTER.
        Fix per edge case total_in_group <= 1.
        """
        role = estimate_player_role(
            player={'name': 'Solo Player'},
            group_index=0,
            player_index_in_group=0,
            total_in_group=1
        )
        assert role == PlayerRole.STARTER
    
    def test_edge_case_empty_group(self):
        """
        REGRESSION TEST: Gruppo vuoto (total_in_group=0) non deve crashare.
        V4.6 FIX: Con total_in_group=0 (dato invalido), ritorna BACKUP come safe default.
        """
        role = estimate_player_role(
            player={'name': 'Ghost Player'},
            group_index=0,
            player_index_in_group=0,
            total_in_group=0
        )
        # V4.6: Con input invalido (total_in_group=0), ritorna BACKUP come safe default
        assert role == PlayerRole.BACKUP


class TestAnalyzerIntegrationScenarios:
    """
    Test scenari reali per verificare che l'injury impact
    funzioni correttamente con diversi mercati.
    
    Questi test documentano il comportamento atteso quando
    analyzer.py applica l'adjustment context-aware.
    """
    
    def test_home_bet_home_injured_scenario(self):
        """
        Scenario: Bet su Home (1), Home ha 3 titolari assenti.
        Expected: score_adjustment positivo (Home più colpita)
        In analyzer.py: adjustment invertito → score DIMINUISCE
        """
        diff = calculate_injury_differential(
            home_team="Juventus",
            away_team="Milan",
            home_injuries=[
                {'name': 'Vlahovic', 'reason': 'Injury'},
                {'name': 'Chiesa', 'reason': 'Injury'},
                {'name': 'Bremer', 'reason': 'Injury'}
            ],
            away_injuries=[]
        )
        
        # Raw adjustment positivo (Home più colpita)
        assert diff.score_adjustment > 0
        # In analyzer.py con market="1": adjustment = -raw → negativo → score diminuisce
        # Questo è corretto: stiamo scommettendo su Home ma Home è indebolita
    
    def test_away_bet_home_injured_scenario(self):
        """
        Scenario: Bet su Away (2), Home ha 3 titolari assenti.
        Expected: score_adjustment positivo (Home più colpita)
        In analyzer.py: adjustment NON invertito → score AUMENTA
        """
        diff = calculate_injury_differential(
            home_team="Juventus",
            away_team="Milan",
            home_injuries=[
                {'name': 'Vlahovic', 'reason': 'Injury'},
                {'name': 'Chiesa', 'reason': 'Injury'},
                {'name': 'Bremer', 'reason': 'Injury'}
            ],
            away_injuries=[]
        )
        
        # Raw adjustment positivo (Home più colpita)
        assert diff.score_adjustment > 0
        # In analyzer.py con market="2": adjustment = raw → positivo → score aumenta
        # Questo è corretto: stiamo scommettendo su Away e Home è indebolita
    
    def test_balanced_injuries_no_adjustment(self):
        """
        Scenario: Entrambe le squadre hanno infortuni simili.
        Expected: adjustment ~0, nessun impatto sul punteggio.
        """
        diff = calculate_injury_differential(
            home_team="Inter",
            away_team="Napoli",
            home_injuries=[
                {'name': 'Player1', 'reason': 'Injury'},
                {'name': 'Player2', 'reason': 'Injury'}
            ],
            away_injuries=[
                {'name': 'Player3', 'reason': 'Injury'},
                {'name': 'Player4', 'reason': 'Injury'}
            ]
        )
        
        # Differential dovrebbe essere piccolo
        assert abs(diff.differential) < 5.0
        # Se differential < 2.0, score_adjustment è 0
        # Altrimenti è proporzionale ma piccolo
