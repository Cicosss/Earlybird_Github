"""
EarlyBird Injury Impact Engine V1.0

Valuta l'impatto reale degli infortuni sulla rosa considerando:
- Ruolo del giocatore (titolare fisso vs riserva)
- Posizione (portiere, difensore, centrocampista, attaccante)
- Importanza relativa (capitano, top scorer, key player)

Il sistema calcola un "injury_impact_score" per entrambe le squadre
e produce un "differential" che influenza il punteggio finale dell'alert.

Logica:
- Se squadra A perde 2 titolari fissi e squadra B perde 2 riserve,
  il differential favorisce la scommessa CONTRO squadra A.
- Se entrambe perdono giocatori di pari importanza, il differential è neutro.

VPS Compatibility:
- Pure Python implementation, no external dependencies
- Stateless design - no file I/O or environment dependencies
- Thread-safe for concurrent match analysis
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PlayerRole(Enum):
    """Ruolo del giocatore nella gerarchia della rosa."""

    STARTER = "starter"  # Titolare fisso (11 iniziale)
    ROTATION = "rotation"  # Rotazione (gioca 50%+ partite)
    BACKUP = "backup"  # Riserva (gioca <50% partite)
    YOUTH = "youth"  # Primavera/giovane


class PlayerPosition(Enum):
    """Posizione in campo del giocatore."""

    GOALKEEPER = "goalkeeper"
    DEFENDER = "defender"
    MIDFIELDER = "midfielder"
    FORWARD = "forward"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class InjuryPlayerImpact:
    """
    Impatto di un singolo giocatore assente.

    ROOT CAUSE FIX: This dataclass is frozen and validates that position and role
    are never None during initialization. This prevents AttributeError crashes in
    to_dict() and _get_player_details_from_injury_impact().
    """

    name: str
    position: PlayerPosition
    role: PlayerRole
    impact_score: float  # 0.0 - 10.0
    reason: str  # Motivo assenza (injury, suspension, etc.)
    is_key_player: bool  # Capitano, top scorer, etc.

    def __post_init__(self):
        """
        Validate that position and role are not None after initialization.

        This is a ROOT CAUSE fix that prevents None values from ever being set,
        rather than just handling them defensively downstream.

        Raises:
            ValueError: If position or role is None
        """
        if self.position is None:
            raise ValueError(
                f"InjuryPlayerImpact.position cannot be None for player '{self.name}'. "
                "Use PlayerPosition.UNKNOWN if position is unknown."
            )
        if self.role is None:
            raise ValueError(
                f"InjuryPlayerImpact.role cannot be None for player '{self.name}'. "
                "Use PlayerRole.ROTATION if role is unknown."
            )
        if not isinstance(self.position, PlayerPosition):
            raise ValueError(
                f"InjuryPlayerImpact.position must be a PlayerPosition enum, "
                f"got {type(self.position)} for player '{self.name}'"
            )
        if not isinstance(self.role, PlayerRole):
            raise ValueError(
                f"InjuryPlayerImpact.role must be a PlayerRole enum, "
                f"got {type(self.role)} for player '{self.name}'"
            )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for serialization.

        ROOT CAUSE FIX: With validation in __post_init__, position and role
        are guaranteed to be valid PlayerPosition/PlayerRole enums, so we can
        safely call .value without None checks. This is defensive programming
        on top of the root cause fix.

        Returns:
            Dictionary with all fields serialized
        """
        return {
            "name": self.name,
            "position": self.position.value,
            "role": self.role.value,
            "impact_score": self.impact_score,
            "reason": self.reason,
            "is_key_player": self.is_key_player,
        }


@dataclass
class TeamInjuryImpact:
    """Impatto totale degli infortuni su una squadra."""

    team_name: str
    total_impact_score: float  # Somma degli impact_score
    missing_starters: int
    missing_rotation: int
    missing_backups: int
    key_players_out: list[str] = field(default_factory=list)
    defensive_impact: float = 0.0  # Impatto sulla difesa (0-10)
    offensive_impact: float = 0.0  # Impatto sull'attacco (0-10)
    players: list[InjuryPlayerImpact] = field(default_factory=list)

    @property
    def severity(self) -> str:
        """Classifica la severità dell'impatto."""
        if self.total_impact_score >= 15 or self.missing_starters >= 3:
            return "CRITICAL"
        elif self.total_impact_score >= 8 or self.missing_starters >= 2:
            return "HIGH"
        elif self.total_impact_score >= 4 or self.missing_starters >= 1:
            return "MEDIUM"
        else:
            return "LOW"

    @property
    def total_missing(self) -> int:
        """Total number of missing players."""
        return self.missing_starters + self.missing_rotation + self.missing_backups

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "team_name": self.team_name,
            "total_impact_score": self.total_impact_score,
            "missing_starters": self.missing_starters,
            "missing_rotation": self.missing_rotation,
            "missing_backups": self.missing_backups,
            "key_players_out": self.key_players_out,
            "defensive_impact": self.defensive_impact,
            "offensive_impact": self.offensive_impact,
            "severity": self.severity,
            "total_missing": self.total_missing,
            "players": [p.to_dict() for p in self.players],
        }


# ============================================
# POSITION DETECTION
# ============================================

# Keywords per identificare la posizione dal gruppo FotMob
POSITION_KEYWORDS = {
    PlayerPosition.GOALKEEPER: [
        "goalkeeper",
        "goalkeepers",
        "portiere",
        "portieri",
        "gk",
        "keeper",
    ],
    PlayerPosition.DEFENDER: [
        "defender",
        "defenders",
        "difensore",
        "difensori",
        "defence",
        "defense",
        "back",
        "backs",
        "cb",
        "rb",
        "lb",
        "fullback",
    ],
    PlayerPosition.MIDFIELDER: [
        "midfielder",
        "midfielders",
        "centrocampista",
        "centrocampisti",
        "midfield",
        "cm",
        "dm",
        "am",
        "winger",
    ],
    PlayerPosition.FORWARD: [
        "forward",
        "forwards",
        "attaccante",
        "attaccanti",
        "striker",
        "strikers",
        "attack",
        "cf",
        "st",
        "lw",
        "rw",
    ],
}


def detect_position_from_group(group_title: str) -> PlayerPosition:
    """
    Rileva la posizione dal titolo del gruppo FotMob.

    Args:
        group_title: Titolo del gruppo (es. "Goalkeepers", "Defenders")

    Returns:
        PlayerPosition enum
    """
    if not group_title:
        return PlayerPosition.UNKNOWN

    title_lower = group_title.lower().strip()

    for position, keywords in POSITION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in title_lower:
                return position

    return PlayerPosition.UNKNOWN


def detect_position_from_player_data(player: dict) -> PlayerPosition:
    """
    Rileva la posizione dai dati del giocatore FotMob.

    Args:
        player: Dict con dati giocatore da FotMob

    Returns:
        PlayerPosition enum
    """
    if not player or not isinstance(player, dict):
        return PlayerPosition.UNKNOWN

    # Prova campo 'position' o 'positionDescription'
    position_str = (
        player.get("position") or player.get("positionDescription") or player.get("role") or ""
    )

    if not position_str:
        return PlayerPosition.UNKNOWN

    position_lower = str(position_str).lower()

    for position, keywords in POSITION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in position_lower:
                return position

    return PlayerPosition.UNKNOWN


# ============================================
# ROLE DETECTION (Titolare vs Riserva)
# ============================================


def estimate_player_role(
    player: dict, group_index: int, player_index_in_group: int, total_in_group: int
) -> PlayerRole:
    """
    Stima il ruolo del giocatore (titolare/riserva) basandosi su:
    - Posizione nell'elenco (i primi sono solitamente titolari)
    - Statistiche se disponibili (presenze, minuti)
    - Flag specifici FotMob

    Args:
        player: Dict con dati giocatore
        group_index: Indice del gruppo nella rosa
        player_index_in_group: Posizione del giocatore nel gruppo
        total_in_group: Totale giocatori nel gruppo

    Returns:
        PlayerRole enum
    """
    # V4.6 FIX: Early return for invalid inputs
    # Handles edge case where total_in_group <= 0 (empty group or bad data)
    if total_in_group <= 0:
        return PlayerRole.BACKUP  # Safe default for invalid data

    if not player or not isinstance(player, dict):
        return PlayerRole.BACKUP

    # Check per giovani/primavera
    if player.get("isYouth") or player.get("isAcademy"):
        return PlayerRole.YOUTH

    # Check statistiche se disponibili
    stats = player.get("stats") or player.get("statistics") or {}
    if isinstance(stats, dict):
        appearances = stats.get("appearances") or stats.get("games") or 0
        minutes = stats.get("minutesPlayed") or stats.get("minutes") or 0

        # Se ha giocato molto, è titolare
        if appearances >= 15 or minutes >= 1000:
            return PlayerRole.STARTER
        elif appearances >= 8 or minutes >= 500:
            return PlayerRole.ROTATION
        elif appearances > 0:
            return PlayerRole.BACKUP

    # Euristica basata sulla posizione nell'elenco
    # FotMob ordina tipicamente per importanza/titolarità

    # Edge case: gruppo con un solo elemento
    if total_in_group == 1:
        # Unico giocatore nel gruppo = probabilmente titolare
        return PlayerRole.STARTER

    if player_index_in_group == 0:
        # Primo del gruppo = probabilmente titolare
        return PlayerRole.STARTER
    elif player_index_in_group == 1 and total_in_group <= 4:
        # Secondo in un gruppo piccolo = rotazione
        return PlayerRole.ROTATION
    elif player_index_in_group < total_in_group // 2:
        # Prima metà = rotazione
        return PlayerRole.ROTATION
    else:
        # Seconda metà = riserva
        return PlayerRole.BACKUP


# ============================================
# IMPACT SCORE CALCULATION
# ============================================

# Pesi per posizione (portiere ha impatto massimo se unico)
POSITION_WEIGHTS = {
    PlayerPosition.GOALKEEPER: 3.0,  # Portiere titolare = impatto critico
    PlayerPosition.DEFENDER: 2.0,  # Difensore centrale = alto impatto
    PlayerPosition.MIDFIELDER: 2.5,  # Centrocampista chiave = molto importante
    PlayerPosition.FORWARD: 2.5,  # Attaccante = molto importante
    PlayerPosition.UNKNOWN: 1.5,  # Default conservativo
}

# Pesi per ruolo
ROLE_WEIGHTS = {
    PlayerRole.STARTER: 3.0,  # Titolare fisso = impatto massimo
    PlayerRole.ROTATION: 1.5,  # Rotazione = impatto medio
    PlayerRole.BACKUP: 0.5,  # Riserva = impatto minimo
    PlayerRole.YOUTH: 0.2,  # Giovane = quasi nullo
}


def calculate_player_impact(
    player_name: str,
    position: PlayerPosition,
    role: PlayerRole,
    reason: str,
    is_key_player: bool = False,
) -> InjuryPlayerImpact:
    """
    Calcola l'impatto di un singolo giocatore assente.

    Formula: impact = position_weight * role_weight * key_player_bonus

    Args:
        player_name: Nome del giocatore
        position: Posizione in campo
        role: Ruolo nella rosa (titolare/riserva)
        reason: Motivo assenza
        is_key_player: Se è capitano/top scorer

    Returns:
        InjuryPlayerImpact con score calcolato
    """
    position_weight = POSITION_WEIGHTS.get(position, 1.5)
    role_weight = ROLE_WEIGHTS.get(role, 1.0)

    # Bonus per key player (capitano, top scorer)
    key_bonus = 1.5 if is_key_player else 1.0

    # Calcolo score (max teorico ~13.5 per portiere titolare key player)
    impact_score = position_weight * role_weight * key_bonus

    # Cap a 10.0
    impact_score = min(10.0, impact_score)

    return InjuryPlayerImpact(
        name=player_name,
        position=position,
        role=role,
        impact_score=round(impact_score, 2),
        reason=reason,
        is_key_player=is_key_player,
    )


# ============================================
# FINANCIAL DEPTH ANALYSIS (V12.8)
# ============================================


def parse_team_market_value(value: str) -> float:
    """
    Parse a financial string into millions (EUR).

    Handles formats like:
    - "€1.20bn"   -> 1200.0
    - "€500M"     -> 500.0
    - "€50M"      -> 50.0
    - "€500k"     -> 0.5
    - "£200M"     -> 200.0  (treated as EUR-equivalent)
    - "$300m"     -> 300.0

    Args:
        value: Financial string with currency symbol and magnitude suffix.

    Returns:
        Value in millions (EUR). Returns 0.0 if parsing fails.
    """
    if not value or not isinstance(value, str):
        return 0.0

    value = value.strip().replace(",", ".")

    # Try billions first (bn / B)
    bn_match = re.search(r"([\d.]+)\s*(?:bn|B|billion)", value, re.IGNORECASE)
    if bn_match:
        try:
            return float(bn_match.group(1)) * 1000.0
        except ValueError:
            return 0.0

    # Try millions (M / m / million)
    m_match = re.search(r"([\d.]+)\s*(?:M|million|mln)", value, re.IGNORECASE)
    if m_match:
        try:
            return float(m_match.group(1))
        except ValueError:
            return 0.0

    # Try thousands (k / K / thousand)
    k_match = re.search(r"([\d.]+)\s*(?:k|K|thousand)", value, re.IGNORECASE)
    if k_match:
        try:
            return float(k_match.group(1)) / 1000.0
        except ValueError:
            return 0.0

    # Fallback: try bare number (assume millions if >= 1)
    num_match = re.search(r"([\d.]+)", value)
    if num_match:
        try:
            return float(num_match.group(1))
        except ValueError:
            return 0.0

    return 0.0


def calculate_financial_depth_multiplier(value_millions: float) -> float:
    """
    Calculate a squad-depth multiplier based on total team market value.

    A wealthier team (higher market value) typically has a deeper bench,
    so losing a starter is less impactful. A poorer team has a shallow bench,
    amplifying the impact of each absence.

    Thresholds (linear interpolation between):
    - > 100M EUR -> 0.6  (deep bench mitigates injury loss)
    - ~ 20M EUR  -> 1.0  (neutral / base)
    - < 10M EUR  -> 1.4  (shallow bench amplifies loss)

    Args:
        value_millions: Total squad market value in millions EUR.
                        0.0 means "unknown / not provided".

    Returns:
        Multiplier in range [0.6, 1.4]. Returns 1.0 if data missing (value_millions <= 0).
    """
    if value_millions <= 0:
        return 1.0

    if value_millions >= 100.0:
        return 0.6
    elif value_millions <= 10.0:
        return 1.4
    elif value_millions <= 20.0:
        # Linear interpolation: 10M -> 1.4, 20M -> 1.0
        # slope = (1.0 - 1.4) / (20 - 10) = -0.04
        return 1.4 + (value_millions - 10.0) * (-0.04)
    else:
        # Linear interpolation: 20M -> 1.0, 100M -> 0.6
        # slope = (0.6 - 1.0) / (100 - 20) = -0.005
        return 1.0 + (value_millions - 20.0) * (-0.005)


# ============================================
# TEAM IMPACT AGGREGATION
# ============================================


def calculate_team_injury_impact(
    team_name: str,
    injuries: list[dict],
    squad_data: dict | None = None,
    key_players: list[str] | None = None,
    team_market_value: str | float | None = None,
) -> TeamInjuryImpact:
    """
    Calcola l'impatto totale degli infortuni su una squadra.

    Args:
        team_name: Nome della squadra
        injuries: Lista di infortuni da FotMob [{name, reason, status}]
        squad_data: Dati rosa completa da FotMob (opzionale, per ruoli)
        key_players: Lista nomi key players noti (opzionale)
        team_market_value: Valore rosa (string "€50M" or float in millions). V12.8.

    Returns:
        TeamInjuryImpact con analisi completa
    """
    if not injuries:
        return TeamInjuryImpact(
            team_name=team_name,
            total_impact_score=0.0,
            missing_starters=0,
            missing_rotation=0,
            missing_backups=0,
            key_players_out=[],
            defensive_impact=0.0,
            offensive_impact=0.0,
            players=[],
        )

    key_players_set = set(kp.lower() for kp in (key_players or []))
    player_impacts: list[InjuryPlayerImpact] = []

    # Mappa giocatori dalla rosa per ottenere posizione/ruolo
    player_info_map = _build_player_info_map(squad_data) if squad_data else {}

    for injury in injuries:
        if not isinstance(injury, dict):
            continue

        player_name = injury.get("name", "Unknown")
        if not player_name or player_name == "Unknown":
            continue

        reason = injury.get("reason", "Unknown")

        # Cerca info giocatore nella mappa
        player_info = player_info_map.get(player_name.lower(), {})

        position = player_info.get("position", PlayerPosition.UNKNOWN)
        role = player_info.get("role", PlayerRole.ROTATION)  # Default conservativo

        # Check se è key player
        is_key = player_name.lower() in key_players_set

        # Calcola impatto
        impact = calculate_player_impact(
            player_name=player_name,
            position=position,
            role=role,
            reason=reason,
            is_key_player=is_key,
        )

        player_impacts.append(impact)

    # Aggrega statistiche
    total_score = sum(p.impact_score for p in player_impacts)
    missing_starters = sum(1 for p in player_impacts if p.role == PlayerRole.STARTER)
    missing_rotation = sum(1 for p in player_impacts if p.role == PlayerRole.ROTATION)
    missing_backups = sum(
        1 for p in player_impacts if p.role in (PlayerRole.BACKUP, PlayerRole.YOUTH)
    )
    key_out = [p.name for p in player_impacts if p.is_key_player]

    # Calcola impatto difensivo/offensivo
    defensive_impact = sum(
        p.impact_score
        for p in player_impacts
        if p.position in (PlayerPosition.GOALKEEPER, PlayerPosition.DEFENDER)
    )
    offensive_impact = sum(
        p.impact_score
        for p in player_impacts
        if p.position in (PlayerPosition.FORWARD, PlayerPosition.MIDFIELDER)
    )

    # V12.8: Apply financial depth multiplier
    # Parse team_market_value (string like "€50M" or float in millions)
    if team_market_value is not None:
        if isinstance(team_market_value, str):
            value_millions = parse_team_market_value(team_market_value)
        elif isinstance(team_market_value, (int, float)):
            value_millions = float(team_market_value)
        else:
            value_millions = 0.0
    else:
        value_millions = 0.0

    depth_multiplier = calculate_financial_depth_multiplier(value_millions)
    if depth_multiplier != 1.0:
        total_score *= depth_multiplier
        defensive_impact *= depth_multiplier
        offensive_impact *= depth_multiplier
        logger.info(
            f"💰 V12.8 Financial Depth: {team_name} value={value_millions:.1f}M "
            f"-> multiplier={depth_multiplier:.2f}"
        )

    return TeamInjuryImpact(
        team_name=team_name,
        total_impact_score=round(total_score, 2),
        missing_starters=missing_starters,
        missing_rotation=missing_rotation,
        missing_backups=missing_backups,
        key_players_out=key_out,
        defensive_impact=round(defensive_impact, 2),
        offensive_impact=round(offensive_impact, 2),
        players=player_impacts,
    )


def _build_player_info_map(squad_data: dict) -> dict[str, dict]:
    """
    Costruisce una mappa nome_giocatore -> {position, role} dalla rosa FotMob.

    Args:
        squad_data: Dati rosa da FotMob

    Returns:
        Dict con chiave nome.lower() e valore {position, role}
    """
    player_map = {}

    if not squad_data or not isinstance(squad_data, dict):
        return player_map

    # FotMob structure: {'squad': [groups...]} o {'squad': {'squad': [groups...]}}
    squad_groups = squad_data.get("squad", [])
    if isinstance(squad_groups, dict):
        squad_groups = squad_groups.get("squad", [])

    if not isinstance(squad_groups, list):
        return player_map

    for group_idx, group in enumerate(squad_groups):
        if not isinstance(group, dict):
            continue

        group_title = group.get("title", "")
        group_position = detect_position_from_group(group_title)

        members = group.get("members", [])
        if not isinstance(members, list):
            continue

        total_in_group = len(members)

        for player_idx, player in enumerate(members):
            if not isinstance(player, dict):
                continue

            name = player.get("name", "")
            if not name:
                continue

            # Posizione: prima dal gruppo, poi dai dati giocatore
            position = group_position
            if position == PlayerPosition.UNKNOWN:
                position = detect_position_from_player_data(player)

            # Ruolo: stima basata su posizione e statistiche
            role = estimate_player_role(
                player=player,
                group_index=group_idx,
                player_index_in_group=player_idx,
                total_in_group=total_in_group,
            )

            player_map[name.lower()] = {"position": position, "role": role}

    return player_map


# ============================================
# DIFFERENTIAL CALCULATION
# ============================================


@dataclass
class InjuryDifferential:
    """Differenziale di impatto infortuni tra due squadre."""

    home_impact: TeamInjuryImpact
    away_impact: TeamInjuryImpact
    differential: float  # Positivo = home più colpita, Negativo = away più colpita
    score_adjustment: float  # Aggiustamento da applicare al punteggio alert
    summary: str  # Descrizione testuale

    @property
    def favors_home(self) -> bool:
        """True se gli infortuni favoriscono la squadra di casa."""
        return self.differential < 0  # Away più colpita = favorisce Home

    @property
    def favors_away(self) -> bool:
        """True se gli infortuni favoriscono la squadra ospite."""
        return self.differential > 0  # Home più colpita = favorisce Away

    @property
    def is_balanced(self) -> bool:
        """
        True se l'impatto è bilanciato tra le due squadre.

        Il threshold di 2.0 indica che la differenza di impatto tra le squadre
        è inferiore a 2.0 punti, il che suggerisce che nessuna squadra ha un
        vantaggio significativo dovuto agli infortuni. Questo valore è coerente
        con il threshold usato in _calculate_score_adjustment() per determinare
        se applicare un aggiustamento al punteggio.

        Returns:
            True se abs(differential) < 2.0, False altrimenti
        """
        return abs(self.differential) < 2.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "home_impact": self.home_impact.to_dict(),
            "away_impact": self.away_impact.to_dict(),
            "differential": self.differential,
            "score_adjustment": self.score_adjustment,
            "summary": self.summary,
            "favors_home": self.favors_home,
            "favors_away": self.favors_away,
            "is_balanced": self.is_balanced,
        }


def calculate_injury_differential(
    home_team: str,
    away_team: str,
    home_injuries: list[dict] | None = None,
    away_injuries: list[dict] | None = None,
    home_squad: dict | None = None,
    away_squad: dict | None = None,
    home_key_players: list[str] | None = None,
    away_key_players: list[str] | None = None,
    home_market_value: str | float | None = None,
    away_market_value: str | float | None = None,
) -> InjuryDifferential:
    """
    Calcola il differenziale di impatto infortuni tra due squadre.

    Args:
        home_team: Nome squadra casa
        away_team: Nome squadra ospite
        home_injuries: Lista infortuni casa (default: empty list)
        away_injuries: Lista infortuni ospite (default: empty list)
        home_squad: Rosa completa casa (opzionale)
        away_squad: Rosa completa ospite (opzionale)
        home_key_players: Key players casa (opzionale)
        away_key_players: Key players ospite (opzionale)
        home_market_value: Valore rosa casa (V12.8, opzionale)
        away_market_value: Valore rosa ospite (V12.8, opzionale)

    Returns:
        InjuryDifferential con analisi completa
    """
    # Normalize inputs
    home_injuries = home_injuries or []
    away_injuries = away_injuries or []

    # Validate team names
    if not home_team or not isinstance(home_team, str):
        logger.warning(f"Invalid home_team provided: {home_team}")
        home_team = "Unknown Home"

    if not away_team or not isinstance(away_team, str):
        logger.warning(f"Invalid away_team provided: {away_team}")
        away_team = "Unknown Away"

    # Calcola impatto per entrambe le squadre
    home_impact = calculate_team_injury_impact(
        team_name=home_team,
        injuries=home_injuries,
        squad_data=home_squad,
        key_players=home_key_players,
        team_market_value=home_market_value,
    )

    away_impact = calculate_team_injury_impact(
        team_name=away_team,
        injuries=away_injuries,
        squad_data=away_squad,
        key_players=away_key_players,
        team_market_value=away_market_value,
    )

    # Calcola differenziale (positivo = home più colpita)
    differential = home_impact.total_impact_score - away_impact.total_impact_score

    # Calcola aggiustamento punteggio
    # Range: -1.5 a +1.5 punti
    # Se differential > 0 (home più colpita), score_adjustment è positivo
    # L'applicazione context-aware avviene in analyzer.py basandosi sul mercato
    score_adjustment = _calculate_score_adjustment(differential, home_impact, away_impact)

    # Genera summary
    summary = _generate_differential_summary(home_impact, away_impact, differential)

    logger.info(
        f"⚖️ Injury Differential: {home_team} ({home_impact.severity}) vs "
        f"{away_team} ({away_impact.severity}) | Diff: {differential:+.2f} | "
        f"Score Adj: {score_adjustment:+.2f}"
    )

    return InjuryDifferential(
        home_impact=home_impact,
        away_impact=away_impact,
        differential=round(differential, 2),
        score_adjustment=round(score_adjustment, 2),
        summary=summary,
    )


def _calculate_score_adjustment(
    differential: float, home_impact: TeamInjuryImpact, away_impact: TeamInjuryImpact
) -> float:
    """
    Calcola l'aggiustamento del punteggio basato sul differenziale.

    Logica:
    - Se una squadra è molto più colpita, aumenta il valore della scommessa contro di essa
    - Range: -1.8 a +1.8 (base ±1.5 + bonus ±0.3 per severity CRITICAL)
    - Segno: positivo = favorisce away bet, negativo = favorisce home bet

    Args:
        differential: Differenza di impatto (home - away)
        home_impact: Impatto squadra casa
        away_impact: Impatto squadra ospite

    Returns:
        Aggiustamento punteggio
    """
    # Se differenziale è piccolo, nessun aggiustamento significativo
    if abs(differential) < 2.0:
        return 0.0

    # Scala lineare con cap
    # differential di 10 = adjustment di 1.5
    adjustment = (differential / 10.0) * 1.5

    # Cap a ±1.5
    adjustment = max(-1.5, min(1.5, adjustment))

    # Bonus extra se una squadra ha severity CRITICAL e l'altra no
    if home_impact.severity == "CRITICAL" and away_impact.severity in ("LOW", "MEDIUM"):
        adjustment += 0.3  # Favorisce away
    elif away_impact.severity == "CRITICAL" and home_impact.severity in ("LOW", "MEDIUM"):
        adjustment -= 0.3  # Favorisce home

    return adjustment


def _generate_differential_summary(
    home_impact: TeamInjuryImpact, away_impact: TeamInjuryImpact, differential: float
) -> str:
    """
    Genera un summary testuale del differenziale.

    Args:
        home_impact: Impatto squadra casa
        away_impact: Impatto squadra ospite
        differential: Differenziale calcolato

    Returns:
        Summary in italiano
    """
    parts = []

    # Home team summary
    if home_impact.missing_starters > 0:
        parts.append(f"🏠 {home_impact.team_name}: {home_impact.missing_starters} titolari assenti")
        if home_impact.key_players_out:
            parts.append(f"   ⭐ Key players: {', '.join(home_impact.key_players_out)}")
    elif home_impact.total_impact_score > 0:
        parts.append(
            f"🏠 {home_impact.team_name}: {len(home_impact.players)} assenti (impatto {home_impact.severity})"
        )
    else:
        parts.append(f"🏠 {home_impact.team_name}: rosa al completo")

    # Away team summary
    if away_impact.missing_starters > 0:
        parts.append(f"🚌 {away_impact.team_name}: {away_impact.missing_starters} titolari assenti")
        if away_impact.key_players_out:
            parts.append(f"   ⭐ Key players: {', '.join(away_impact.key_players_out)}")
    elif away_impact.total_impact_score > 0:
        parts.append(
            f"🚌 {away_impact.team_name}: {len(away_impact.players)} assenti (impatto {away_impact.severity})"
        )
    else:
        parts.append(f"🚌 {away_impact.team_name}: rosa al completo")

    # Verdict
    if abs(differential) < 2.0:
        parts.append("⚖️ Impatto bilanciato - nessun vantaggio significativo")
    elif differential > 0:
        parts.append(f"📊 Vantaggio {away_impact.team_name} (diff: {differential:+.1f})")
    else:
        parts.append(f"📊 Vantaggio {home_impact.team_name} (diff: {differential:+.1f})")

    return "\n".join(parts)


# ============================================
# PUBLIC API
# ============================================


def analyze_match_injuries(
    home_team: str,
    away_team: str,
    home_context: dict | None = None,
    away_context: dict | None = None,
    home_key_players: list[str] | None = None,
    away_key_players: list[str] | None = None,
) -> InjuryDifferential:
    """
    Analizza l'impatto degli infortuni per una partita.

    Funzione principale da chiamare dal main.py o analyzer.py.

    Args:
        home_team: Nome squadra casa
        away_team: Nome squadra ospite
        home_context: Context FotMob squadra casa (con 'injuries' e opzionalmente 'squad')
        away_context: Context FotMob squadra ospite
        home_key_players: Lista key players casa (opzionale)
        away_key_players: Lista key players ospite (opzionale)

    Returns:
        InjuryDifferential con analisi completa
    """
    # Estrai injuries dai context (safe access)
    home_injuries: list[dict] = []
    away_injuries: list[dict] = []
    home_squad: dict | None = None
    away_squad: dict | None = None
    home_market_value: str | float | None = None
    away_market_value: str | float | None = None

    if home_context and isinstance(home_context, dict):
        home_injuries = home_context.get("injuries") or []
        home_squad = home_context.get("squad")
        home_market_value = home_context.get("team_market_value")

    if away_context and isinstance(away_context, dict):
        away_injuries = away_context.get("injuries") or []
        away_squad = away_context.get("squad")
        away_market_value = away_context.get("team_market_value")

    return calculate_injury_differential(
        home_team=home_team,
        away_team=away_team,
        home_injuries=home_injuries,
        away_injuries=away_injuries,
        home_squad=home_squad,
        away_squad=away_squad,
        home_key_players=home_key_players,
        away_key_players=away_key_players,
        home_market_value=home_market_value,
        away_market_value=away_market_value,
    )


# ============================================
# MODULE EXPORTS
# ============================================

__all__ = [
    "PlayerRole",
    "PlayerPosition",
    "InjuryPlayerImpact",
    "TeamInjuryImpact",
    "InjuryDifferential",
    "detect_position_from_group",
    "detect_position_from_player_data",
    "estimate_player_role",
    "calculate_player_impact",
    "parse_team_market_value",
    "calculate_financial_depth_multiplier",
    "calculate_team_injury_impact",
    "calculate_injury_differential",
    "analyze_match_injuries",
]
