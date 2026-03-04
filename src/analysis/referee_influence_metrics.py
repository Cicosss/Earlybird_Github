"""
Referee Influence Metrics Module

Tracks and reports metrics on how referee intelligence influences betting decisions:
- Boost application frequency
- Decision changes (NO BET → BET, market upgrades)
- Confidence adjustments
- Market-specific influence (Goals, Corners, Winner)
- Referee effectiveness rankings

Usage:
    from src.analysis.referee_influence_metrics import get_referee_influence_metrics

    metrics = get_referee_influence_metrics()
    metrics.record_boost_applied(
        referee_name="Michael Oliver",
        cards_per_game=5.2,
        original_verdict="NO BET",
        new_verdict="BET",
        confidence_before=70,
        confidence_after=80
    )

    # Get summary
    summary = metrics.get_summary()
    print(f"Total boosts applied: {summary['total_boosts']}")
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Metrics file location
METRICS_DIR = Path("data/metrics")
INFLUENCE_METRICS_FILE = METRICS_DIR / "referee_influence_metrics.json"


class RefereeInfluenceMetrics:
    """
    Metrics tracker for referee influence on betting decisions.

    Tracks how referee intelligence affects decisions and provides
    analytics for system optimization.
    """

    def __init__(self, metrics_file: Path = INFLUENCE_METRICS_FILE):
        self.metrics_file = metrics_file
        self._lock = Lock()
        self._metrics = self._load_metrics()

    def _load_metrics(self) -> Dict[str, Any]:
        """Load metrics from file."""
        if not self.metrics_file.exists():
            return self._create_empty_metrics()

        try:
            with open(self.metrics_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load referee influence metrics: {e}")
            return self._create_empty_metrics()

    def _create_empty_metrics(self) -> Dict[str, Any]:
        """Create empty metrics structure."""
        return {
            "total_analyses": 0,
            "total_boosts_applied": 0,
            "total_upgrades_applied": 0,
            "total_influences_applied": 0,
            "total_vetoes_applied": 0,
            "boosts_by_type": {
                "boost_no_bet_to_bet": 0,
                "upgrade_cards_line": 0,
                "influence_goals": 0,
                "influence_corners": 0,
                "influence_winner": 0,
                "veto_cards": 0,
            },
            "confidence_changes": {
                "total_increase": 0.0,
                "total_decrease": 0.0,
                "avg_increase": 0.0,
                "avg_decrease": 0.0,
                "increase_count": 0,
                "decrease_count": 0,
            },
            "referee_stats": defaultdict(
                lambda: {
                    "boosts_applied": 0,
                    "upgrades_applied": 0,
                    "influences_applied": 0,
                    "total_confidence_change": 0.0,
                    "avg_confidence_change": 0.0,
                    "matches_analyzed": 0,
                }
            ),
            "market_influence": {
                "cards": {"boosts": 0, "upgrades": 0, "vetoes": 0, "avg_confidence_change": 0.0},
                "goals": {"influences": 0, "avg_confidence_change": 0.0},
                "corners": {"influences": 0, "avg_confidence_change": 0.0},
                "winner": {"influences": 0, "avg_confidence_change": 0.0},
            },
            "decision_changes": {"no_bet_to_bet": 0, "market_upgrades": 0, "confidence_only": 0},
            "last_updated": None,
        }

    def _save_metrics(self):
        """Save metrics to file."""
        try:
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            # Convert defaultdict to dict for JSON serialization
            metrics_to_save = self._metrics.copy()
            metrics_to_save["referee_stats"] = dict(self._metrics["referee_stats"])
            with open(self.metrics_file, "w", encoding="utf-8") as f:
                json.dump(metrics_to_save, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save referee influence metrics: {e}")

    def record_analysis(
        self,
        referee_name: str,
        cards_per_game: Optional[float] = None,
        has_referee_data: bool = False,
    ):
        """
        Record an analysis event (with or without referee data).

        Args:
            referee_name: Name of the referee
            cards_per_game: Average cards per game (optional)
            has_referee_data: Whether referee data was available
        """
        with self._lock:
            self._metrics["total_analyses"] += 1

            if has_referee_data and referee_name:
                # Initialize referee stats if not exists (fix for KeyError)
                if referee_name not in self._metrics["referee_stats"]:
                    self._metrics["referee_stats"][referee_name] = {
                        "boosts_applied": 0,
                        "upgrades_applied": 0,
                        "influences_applied": 0,
                        "total_confidence_change": 0.0,
                        "avg_confidence_change": 0.0,
                        "matches_analyzed": 0,
                    }
                self._metrics["referee_stats"][referee_name]["matches_analyzed"] += 1

            self._metrics["last_updated"] = datetime.now(timezone.utc).isoformat()
            self._save_metrics()

    def record_boost_applied(
        self,
        referee_name: str,
        cards_per_game: float,
        boost_type: str,
        original_verdict: str,
        new_verdict: str,
        confidence_before: Optional[float] = None,
        confidence_after: Optional[float] = None,
        market_type: Optional[str] = None,
    ):
        """
        Record a boost application.

        Args:
            referee_name: Name of the referee
            cards_per_game: Average cards per game
            boost_type: Type of boost (boost_no_bet_to_bet, upgrade_cards_line, etc.)
            original_verdict: Original verdict
            new_verdict: New verdict
            confidence_before: Confidence before boost
            confidence_after: Confidence after boost
            market_type: Type of market (cards, goals, corners, winner)
        """
        with self._lock:
            self._metrics["total_boosts_applied"] += 1

            # Track by type
            if boost_type in self._metrics["boosts_by_type"]:
                self._metrics["boosts_by_type"][boost_type] += 1

            # Track decision changes
            if original_verdict == "NO BET" and new_verdict == "BET":
                self._metrics["decision_changes"]["no_bet_to_bet"] += 1
            elif "upgrade" in boost_type.lower():
                self._metrics["decision_changes"]["market_upgrades"] += 1
            elif original_verdict == new_verdict:
                self._metrics["decision_changes"]["confidence_only"] += 1

            # Track confidence changes
            if confidence_before is not None and confidence_after is not None:
                delta = confidence_after - confidence_before
                if delta > 0:
                    self._metrics["confidence_changes"]["total_increase"] += delta
                    self._metrics["confidence_changes"]["increase_count"] += 1
                    self._metrics["confidence_changes"]["avg_increase"] = (
                        self._metrics["confidence_changes"]["total_increase"]
                        / self._metrics["confidence_changes"]["increase_count"]
                    )
                elif delta < 0:
                    self._metrics["confidence_changes"]["total_decrease"] += abs(delta)
                    self._metrics["confidence_changes"]["decrease_count"] += 1
                    self._metrics["confidence_changes"]["avg_decrease"] = (
                        self._metrics["confidence_changes"]["total_decrease"]
                        / self._metrics["confidence_changes"]["decrease_count"]
                    )

            # Track referee stats
            # Initialize referee stats if not exists (fix for KeyError)
            if referee_name not in self._metrics["referee_stats"]:
                self._metrics["referee_stats"][referee_name] = {
                    "boosts_applied": 0,
                    "upgrades_applied": 0,
                    "influences_applied": 0,
                    "total_confidence_change": 0.0,
                    "avg_confidence_change": 0.0,
                    "matches_analyzed": 0,
                }

            # Now increment the stats
            self._metrics["referee_stats"][referee_name]["boosts_applied"] += 1
            if confidence_before is not None and confidence_after is not None:
                delta = confidence_after - confidence_before
                self._metrics["referee_stats"][referee_name]["total_confidence_change"] += delta
                self._metrics["referee_stats"][referee_name]["avg_confidence_change"] = (
                    self._metrics["referee_stats"][referee_name]["total_confidence_change"]
                    / self._metrics["referee_stats"][referee_name]["boosts_applied"]
                )

            # Track market influence
            if market_type and market_type in self._metrics["market_influence"]:
                if "upgrade" in boost_type.lower():
                    self._metrics["market_influence"][market_type]["upgrades"] += 1
                elif "veto" in boost_type.lower():
                    self._metrics["market_influence"][market_type]["vetoes"] += 1
                elif "influence" in boost_type.lower():
                    self._metrics["market_influence"][market_type]["influences"] += 1
                else:
                    self._metrics["market_influence"][market_type]["boosts"] += 1

                if confidence_before is not None and confidence_after is not None:
                    delta = confidence_after - confidence_before
                    # Update average confidence change for market
                    market_data = self._metrics["market_influence"][market_type]
                    total_influences = (
                        market_data.get("boosts", 0)
                        + market_data.get("upgrades", 0)
                        + market_data.get("influences", 0)
                    )
                    if total_influences > 0:
                        current_avg = market_data.get("avg_confidence_change", 0.0)
                        market_data["avg_confidence_change"] = (
                            current_avg * (total_influences - 1) + delta
                        ) / total_influences

            self._metrics["last_updated"] = datetime.now(timezone.utc).isoformat()
            self._save_metrics()

    def record_influence_applied(
        self,
        referee_name: str,
        cards_per_game: float,
        influence_type: str,
        market_type: str,
        confidence_before: float,
        confidence_after: float,
    ):
        """
        Record an influence application on non-cards markets.

        Args:
            referee_name: Name of the referee
            cards_per_game: Average cards per game
            influence_type: Type of influence (influence_goals, influence_corners, etc.)
            market_type: Type of market (goals, corners, winner)
            confidence_before: Confidence before influence
            confidence_after: Confidence after influence
        """
        with self._lock:
            self._metrics["total_influences_applied"] += 1

            # Track by type
            if influence_type in self._metrics["boosts_by_type"]:
                self._metrics["boosts_by_type"][influence_type] += 1

            # Track confidence changes
            delta = confidence_after - confidence_before
            if delta > 0:
                self._metrics["confidence_changes"]["total_increase"] += delta
                self._metrics["confidence_changes"]["increase_count"] += 1
                self._metrics["confidence_changes"]["avg_increase"] = (
                    self._metrics["confidence_changes"]["total_increase"]
                    / self._metrics["confidence_changes"]["increase_count"]
                )
            elif delta < 0:
                self._metrics["confidence_changes"]["total_decrease"] += abs(delta)
                self._metrics["confidence_changes"]["decrease_count"] += 1
                self._metrics["confidence_changes"]["avg_decrease"] = (
                    self._metrics["confidence_changes"]["total_decrease"]
                    / self._metrics["confidence_changes"]["decrease_count"]
                )

            # Track referee stats
            # Initialize referee stats if not exists (fix for KeyError)
            if referee_name not in self._metrics["referee_stats"]:
                self._metrics["referee_stats"][referee_name] = {
                    "boosts_applied": 0,
                    "upgrades_applied": 0,
                    "influences_applied": 0,
                    "total_confidence_change": 0.0,
                    "avg_confidence_change": 0.0,
                    "matches_analyzed": 0,
                }

            # Now increment the stats
            self._metrics["referee_stats"][referee_name]["influences_applied"] += 1

            # Track market influence
            if market_type in self._metrics["market_influence"]:
                self._metrics["market_influence"][market_type]["influences"] += 1
                # Update average confidence change
                market_data = self._metrics["market_influence"][market_type]
                total_influences = market_data.get("influences", 0)
                if total_influences > 0:
                    current_avg = market_data.get("avg_confidence_change", 0.0)
                    market_data["avg_confidence_change"] = (
                        current_avg * (total_influences - 1) + delta
                    ) / total_influences

            self._metrics["last_updated"] = datetime.now(timezone.utc).isoformat()
            self._save_metrics()

    def record_veto_applied(self, referee_name: str, cards_per_game: float, market_type: str):
        """
        Record a veto application by lenient referee.

        Args:
            referee_name: Name of the referee
            cards_per_game: Average cards per game
            market_type: Type of market (cards)
        """
        with self._lock:
            self._metrics["total_vetoes_applied"] += 1

            # Track by type
            self._metrics["boosts_by_type"]["veto_cards"] += 1

            # Track market influence
            if market_type in self._metrics["market_influence"]:
                self._metrics["market_influence"][market_type]["vetoes"] += 1

            self._metrics["last_updated"] = datetime.now(timezone.utc).isoformat()
            self._save_metrics()

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of referee influence metrics.

        Returns:
            Dict with summary metrics
        """
        with self._lock:
            total = self._metrics["total_analyses"]
            boosts = self._metrics["total_boosts_applied"]
            influences = self._metrics["total_influences_applied"]
            vetoes = self._metrics["total_vetoes_applied"]

            boost_rate = (boosts + influences) / total if total > 0 else 0.0

            return {
                "total_analyses": total,
                "total_interventions": boosts + influences + vetoes,
                "total_boosts_applied": boosts,
                "total_upgrades_applied": self._metrics["total_upgrades_applied"],
                "total_influences_applied": influences,
                "total_vetoes_applied": vetoes,
                "intervention_rate": boost_rate,
                "boosts_by_type": self._metrics["boosts_by_type"].copy(),
                "decision_changes": self._metrics["decision_changes"].copy(),
                "confidence_changes": self._metrics["confidence_changes"].copy(),
                "market_influence": self._metrics["market_influence"].copy(),
                "last_updated": self._metrics["last_updated"],
            }

    def get_referee_rankings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get referee rankings by influence effectiveness.

        Args:
            limit: Maximum number of referees to return

        Returns:
            List of referee stats sorted by total interventions
        """
        with self._lock:
            referee_list = []
            for name, stats in self._metrics["referee_stats"].items():
                total_interventions = (
                    stats["boosts_applied"]
                    + stats["upgrades_applied"]
                    + stats["influences_applied"]
                )
                referee_list.append(
                    {
                        "name": name,
                        "total_interventions": total_interventions,
                        "boosts_applied": stats["boosts_applied"],
                        "upgrades_applied": stats["upgrades_applied"],
                        "influences_applied": stats["influences_applied"],
                        "matches_analyzed": stats["matches_analyzed"],
                        "avg_confidence_change": stats["avg_confidence_change"],
                    }
                )

            return sorted(referee_list, key=lambda x: x["total_interventions"], reverse=True)[
                :limit
            ]

    def get_market_influence_summary(self) -> Dict[str, Any]:
        """
        Get summary of influence by market type.

        Returns:
            Dict with market-specific influence metrics
        """
        with self._lock:
            return self._metrics["market_influence"].copy()

    def reset_metrics(self):
        """Reset all metrics to zero."""
        with self._lock:
            self._metrics = self._create_empty_metrics()
            self._save_metrics()
            logger.info("Referee influence metrics reset")

    def print_summary(self):
        """Print metrics summary to console."""
        summary = self.get_summary()
        rankings = self.get_referee_rankings(5)

        print("\n" + "=" * 70)
        print("REFEREE INFLUENCE METRICS")
        print("=" * 70)
        print(f"Total Analyses: {summary['total_analyses']}")
        print(f"Total Interventions: {summary['total_interventions']}")
        print(f"Intervention Rate: {summary['intervention_rate']:.2%}")
        print("\nBreakdown:")
        print(f"  Boosts Applied: {summary['total_boosts_applied']}")
        print(f"  Upgrades Applied: {summary['total_upgrades_applied']}")
        print(f"  Influences Applied: {summary['total_influences_applied']}")
        print(f"  Vetoes Applied: {summary['total_vetoes_applied']}")
        print("\nDecision Changes:")
        print(f"  NO BET → BET: {summary['decision_changes']['no_bet_to_bet']}")
        print(f"  Market Upgrades: {summary['decision_changes']['market_upgrades']}")
        print(f"  Confidence Only: {summary['decision_changes']['confidence_only']}")
        print("\nConfidence Changes:")
        print(f"  Avg Increase: {summary['confidence_changes']['avg_increase']:.2f}%")
        print(f"  Avg Decrease: {summary['confidence_changes']['avg_decrease']:.2f}%")
        print("\nTop Referees by Influence:")
        for i, ref in enumerate(rankings, 1):
            print(f"  {i}. {ref['name']}: {ref['total_interventions']} interventions")
        print("=" * 70 + "\n")


# Global metrics instance
_referee_influence_metrics = None
_referee_influence_metrics_lock = Lock()


def get_referee_influence_metrics() -> RefereeInfluenceMetrics:
    """
    Get the global referee influence metrics instance.

    Returns:
        RefereeInfluenceMetrics instance
    """
    global _referee_influence_metrics
    with _referee_influence_metrics_lock:
        if _referee_influence_metrics is None:
            _referee_influence_metrics = RefereeInfluenceMetrics()
    return _referee_influence_metrics
