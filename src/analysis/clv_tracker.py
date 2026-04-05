"""
CLV (Closing Line Value) Tracker for EarlyBird V5.0

Monitors and reports on Closing Line Value - the gold standard metric
for validating betting edge. CLV > 0 means we're beating the market.

Key Insight: You can win bets by luck, but you can't beat the closing
line by luck. Positive CLV = real edge.

Features:
- Track CLV per bet, strategy, and league
- Generate CLV reports with statistical significance
- Identify which strategies have real edge vs lucky streaks
- Integration with optimizer for weight adjustments

References:
- Pinnacle: CLV is the best predictor of long-term profitability
- Industry benchmark: +2% CLV average = excellent edge
"""

import logging
import math
import statistics
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.database.db import get_db_context
from src.database.models import Match, NewsLog

logger = logging.getLogger(__name__)

# CLV Benchmarks (industry standards)
CLV_EXCELLENT_THRESHOLD = 2.0  # +2% CLV = excellent edge
CLV_GOOD_THRESHOLD = 0.5  # +0.5% CLV = good edge
CLV_MINIMUM_SAMPLE = 20  # Minimum bets for statistical relevance
CLV_CONFIDENCE_SAMPLE = 50  # Full confidence at 50+ bets


def _tavily_verify_line_movement(
    home_team: str, away_team: str, match_date: datetime, line_movement: str, clv_value: float
) -> str | None:
    """
    V7.0: Use Tavily to verify causes of line movement.

    Called during CLV analysis to understand why odds moved.

    V14.0: Intelligent priority system based on CLV significance:
    - Very significant (|CLV| >= 5%): Always call Tavily
    - Moderately significant (3% <= |CLV| < 5%): Call if budget allows
    - Just significant (2% <= |CLV| < 3%): Call only if budget is abundant (>80%)

    Args:
        home_team: Home team name
        away_team: Away team name
        match_date: Match date
        line_movement: Description of line movement (e.g., "Home odds dropped 2.1 → 1.8")
        clv_value: CLV value to determine priority

    Returns:
        Explanation of line movement cause or None

    Requirements: 7.3
    """
    try:
        from src.ingestion.tavily_budget import get_budget_manager
        from src.ingestion.tavily_provider import get_tavily_provider

        tavily = get_tavily_provider()
        budget = get_budget_manager()

        if not tavily or not tavily.is_available():
            return None

        if not budget:
            return None

        # V14.0: Intelligent priority system based on CLV significance
        clv_abs = abs(clv_value)
        status = budget.get_status()

        # Very significant CLV (>=5%): Always call
        if clv_abs >= 5.0:
            if not budget.can_call("settlement_clv"):
                logger.debug("📊 [CLV] Tavily budget limit reached for very significant CLV")
                return None

        # Moderately significant CLV (3-5%): Call if budget allows
        elif clv_abs >= 3.0:
            if not budget.can_call("settlement_clv"):
                logger.debug("📊 [CLV] Tavily budget limit reached for moderately significant CLV")
                return None

        # Just significant CLV (2-3%): Call only if budget is abundant (>80%)
        elif clv_abs >= 2.0:
            if status.is_disabled or status.is_degraded:
                logger.debug(
                    f"📊 [CLV] Skipping Tavily call for just significant CLV (budget at {status.usage_percentage:.1f}%)"
                )
                return None
            if not budget.can_call("settlement_clv"):
                logger.debug("📊 [CLV] Tavily budget limit reached for just significant CLV")
                return None
        else:
            # CLV < 2%: Don't call Tavily
            logger.debug(f"📊 [CLV] Skipping Tavily call for CLV {clv_value:.2f}% (<2%)")
            return None

        # Build query for line movement analysis
        date_str = match_date.strftime("%Y-%m-%d") if match_date else ""
        query = f"{home_team} vs {away_team} {date_str} odds movement betting line injury lineup"

        # V7.1: Use native Tavily news parameters for better filtering
        response = tavily.search(
            query=query,
            search_depth="basic",
            max_results=3,
            include_answer=True,
            topic="news",
            days=3,
        )

        if response:
            budget.record_call("settlement_clv")

            if response.answer:
                logger.info(
                    f"🔍 [CLV] Tavily found line movement cause for {home_team} vs {away_team} (CLV: {clv_value:+.2f}%)"
                )
                return response.answer[:400]

        return None

    except ImportError:
        logger.debug("⚠️ [CLV] Tavily not available")
        return None
    except Exception as e:
        logger.warning(f"⚠️ [CLV] Tavily line movement verification failed: {e}")
        return None


@dataclass
class CLVStats:
    """Statistics for CLV analysis."""

    total_bets: int
    bets_with_clv: int
    avg_clv: float
    median_clv: float
    positive_clv_rate: float  # % of bets with CLV > 0
    std_dev: float
    min_clv: float
    max_clv: float
    edge_quality: str  # "EXCELLENT", "GOOD", "MARGINAL", "NO_EDGE", "INSUFFICIENT_DATA"

    def to_dict(self) -> dict:
        return {
            "total_bets": self.total_bets,
            "bets_with_clv": self.bets_with_clv,
            "avg_clv": round(self.avg_clv, 2),
            "median_clv": round(self.median_clv, 2),
            "positive_clv_rate": round(self.positive_clv_rate, 1),
            "std_dev": round(self.std_dev, 2),
            "min_clv": round(self.min_clv, 2),
            "max_clv": round(self.max_clv, 2),
            "edge_quality": self.edge_quality,
        }


@dataclass
class StrategyEdgeReport:
    """Edge validation report for a strategy."""

    strategy_name: str
    clv_stats: CLVStats
    win_rate: float
    roi: float
    wins_with_positive_clv: int  # True edge
    wins_with_negative_clv: int  # Lucky
    losses_with_positive_clv: int  # Variance
    losses_with_negative_clv: int  # No edge
    is_validated: bool  # True if CLV confirms edge


class CLVTracker:
    """
    Tracks and analyzes Closing Line Value across all bets.

    CLV = (odds_taken / fair_closing_odds) - 1

    Where fair_closing_odds removes the bookmaker margin from closing odds.
    """

    def __init__(self, margin: float = 0.05):
        """
        Initialize CLV Tracker.

        Args:
            margin: Estimated bookmaker margin (default 5%)
        """
        self.margin = margin

    def calculate_clv(self, odds_taken: float, closing_odds: float) -> float | None:
        """
        Calculate CLV for a single bet.

        Args:
            odds_taken: Decimal odds when bet was placed
            closing_odds: Decimal odds at match start

        Returns:
            CLV as percentage, or None if invalid inputs
        """
        # Validate inputs
        if not odds_taken or not closing_odds:
            return None
        if odds_taken <= 1.0 or closing_odds <= 1.0:
            return None
        if math.isinf(odds_taken) or math.isinf(closing_odds):
            return None
        if math.isnan(odds_taken) or math.isnan(closing_odds):
            return None
        if odds_taken > 1000 or closing_odds > 1000:
            return None

        try:
            # Convert closing odds to implied probability
            implied_prob = 1.0 / closing_odds

            # Remove margin (proportional method)
            fair_prob = implied_prob / (1.0 + self.margin)

            # Clamp to valid range
            fair_prob = max(0.01, min(0.99, fair_prob))

            # Fair closing odds
            fair_closing_odds = 1.0 / fair_prob

            # CLV = how much better our odds were vs fair closing
            clv = ((odds_taken / fair_closing_odds) - 1.0) * 100

            return round(clv, 2)

        except (ZeroDivisionError, ValueError):
            return None

    def get_clv_stats(
        self, days_back: int = 30, strategy: str = None, league: str = None, min_score: float = 7.0
    ) -> CLVStats:
        """
        Get CLV statistics for a time period.

        Args:
            days_back: How many days to look back
            strategy: Filter by primary_driver (optional)
            league: Filter by league (optional)
            min_score: Minimum score threshold (default 7.0)

        Returns:
            CLVStats dataclass with analysis
        """
        with get_db_context() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

            # Build query
            query = (
                db.query(NewsLog)
                .join(Match)
                .filter(
                    NewsLog.sent == True, NewsLog.score >= min_score, Match.start_time >= cutoff
                )
            )

            if strategy:
                query = query.filter(NewsLog.primary_driver == strategy)

            if league:
                query = query.filter(Match.league == league)

            logs = query.all()

            # Extract CLV values
            clv_values: list[str] = []
            for log in logs:
                if log.clv_percent is not None:
                    clv_values.append(log.clv_percent)

            return self._calculate_stats(len(logs), clv_values)

    def _calculate_stats(self, total_bets: int, clv_values: list[float]) -> CLVStats:
        """Calculate statistics from CLV values."""

        if not clv_values:
            return CLVStats(
                total_bets=total_bets,
                bets_with_clv=0,
                avg_clv=0.0,
                median_clv=0.0,
                positive_clv_rate=0.0,
                std_dev=0.0,
                min_clv=0.0,
                max_clv=0.0,
                edge_quality="INSUFFICIENT_DATA",
            )

        n = len(clv_values)
        avg_clv = statistics.mean(clv_values)
        median_clv = statistics.median(clv_values)
        positive_count = sum(1 for c in clv_values if c > 0)
        positive_rate = (positive_count / n) * 100 if n > 0 else 0
        std_dev = statistics.stdev(clv_values) if n > 1 else 0.0

        # Determine edge quality
        if n < CLV_MINIMUM_SAMPLE:
            edge_quality = "INSUFFICIENT_DATA"
        elif avg_clv >= CLV_EXCELLENT_THRESHOLD:
            edge_quality = "EXCELLENT"
        elif avg_clv >= CLV_GOOD_THRESHOLD:
            edge_quality = "GOOD"
        elif avg_clv > 0:
            edge_quality = "MARGINAL"
        else:
            edge_quality = "NO_EDGE"

        return CLVStats(
            total_bets=total_bets,
            bets_with_clv=n,
            avg_clv=avg_clv,
            median_clv=median_clv,
            positive_clv_rate=positive_rate,
            std_dev=std_dev,
            min_clv=min(clv_values),
            max_clv=max(clv_values),
            edge_quality=edge_quality,
        )

    def get_strategy_edge_report(
        self, strategy: str, days_back: int = 30
    ) -> StrategyEdgeReport | None:
        """
        Generate edge validation report for a strategy.

        This is the KEY function - it tells you if a strategy has REAL edge
        or just got lucky.

        Args:
            strategy: Primary driver name (INJURY_INTEL, SHARP_MONEY, etc.)
            days_back: Lookback period

        Returns:
            StrategyEdgeReport or None if no data
        """
        with get_db_context() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

            # Get all sent alerts for this strategy
            logs = (
                db.query(NewsLog)
                .join(Match)
                .filter(
                    NewsLog.sent == True,
                    NewsLog.primary_driver == strategy,
                    Match.start_time >= cutoff,
                )
                .all()
            )

            if not logs:
                return None

            # Categorize bets
            clv_values: list[str] = []
            wins_positive_clv = 0
            wins_negative_clv = 0
            losses_positive_clv = 0
            losses_negative_clv = 0
            total_wins = 0
            total_profit = 0.0

            for log in logs:
                clv = log.clv_percent

                # Determine win/loss from category or other indicators
                # Note: This requires settlement data - we check if there's a pattern
                is_win = self._infer_outcome(log)

                if clv is not None:
                    clv_values.append(clv)

                    if is_win is True:
                        total_wins += 1
                        if clv > 0:
                            wins_positive_clv += 1
                        else:
                            wins_negative_clv += 1
                    elif is_win is False:
                        if clv > 0:
                            losses_positive_clv += 1
                        else:
                            losses_negative_clv += 1

            clv_stats = self._calculate_stats(len(logs), clv_values)

            # Calculate win rate and ROI
            settled_bets = (
                wins_positive_clv + wins_negative_clv + losses_positive_clv + losses_negative_clv
            )
            win_rate = (total_wins / settled_bets * 100) if settled_bets > 0 else 0.0

            # V13.0: Calculate actual ROI from settled bets
            # ROI = (total_return - total_stake) / total_stake * 100
            total_stake = settled_bets * 1.0  # Assume 1 unit per bet
            total_return = 0.0

            for log in logs:
                is_win = self._infer_outcome(log)
                if is_win is True:
                    # Get odds from database - use odds_at_alert first (V8.3)
                    odds = log.odds_at_alert or log.odds_taken or log.closing_odds or 1.0
                    if odds > 1.0:
                        total_return += odds

            roi = ((total_return - total_stake) / total_stake * 100) if total_stake > 0 else 0.0

            # Validate edge: positive CLV + reasonable win rate = real edge
            is_validated = (
                clv_stats.avg_clv > 0
                and clv_stats.bets_with_clv >= CLV_MINIMUM_SAMPLE
                and clv_stats.positive_clv_rate > 50
            )

            return StrategyEdgeReport(
                strategy_name=strategy,
                clv_stats=clv_stats,
                win_rate=win_rate,
                roi=roi,
                wins_with_positive_clv=wins_positive_clv,
                wins_with_negative_clv=wins_negative_clv,
                losses_with_positive_clv=losses_positive_clv,
                losses_with_negative_clv=losses_negative_clv,
                is_validated=is_validated,
            )

    def _infer_outcome(self, log: NewsLog) -> bool | None:
        """
        Infer bet outcome from NewsLog data.

        V13.0: Now uses the dedicated 'outcome' field that is populated
        by the settlement service, instead of fragile string matching on 'category'.

        Returns:
            True = win, False = loss, None = unknown/pending
        """
        # V13.0: Check for dedicated outcome field (populated by settlement service)
        if hasattr(log, "outcome") and log.outcome:
            outcome = log.outcome.upper()
            if outcome == "WIN":
                return True
            elif outcome == "LOSS":
                return False
            elif outcome == "PUSH":
                return None  # PUSH doesn't count as win/loss
            # PENDING or other values return None

        # Fallback: Check category for outcome hints (legacy support)
        # This is less reliable but provides backward compatibility
        category = (log.category or "").upper()
        if category in ("WIN", "WON"):
            return True
        elif category in ("LOSS", "LOST", "LOSE"):
            return False

        # Can't determine
        return None

    def generate_clv_report(self, days_back: int = 30) -> str:
        """
        Generate a human-readable CLV report.

        Args:
            days_back: Lookback period

        Returns:
            Formatted report string
        """
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append(f"📈 CLV ANALYSIS REPORT (Last {days_back} days)")
        lines.append("=" * 60)

        # Overall stats
        overall = self.get_clv_stats(days_back=days_back)
        lines.append("\n📊 OVERALL PERFORMANCE:")
        lines.append(f"   Total bets sent: {overall.total_bets}")
        lines.append(f"   Bets with CLV data: {overall.bets_with_clv}")
        lines.append(f"   Average CLV: {overall.avg_clv:+.2f}%")
        lines.append(f"   Median CLV: {overall.median_clv:+.2f}%")
        lines.append(f"   Positive CLV rate: {overall.positive_clv_rate:.1f}%")
        lines.append(f"   Edge Quality: {overall.edge_quality}")

        # Per-strategy breakdown
        strategies = ["INJURY_INTEL", "SHARP_MONEY", "MATH_VALUE", "CONTEXT_PLAY", "CONTRARIAN"]

        lines.append("\n📊 BY STRATEGY:")
        for strategy in strategies:
            stats = self.get_clv_stats(days_back=days_back, strategy=strategy)
            if stats.bets_with_clv > 0:
                emoji = "✅" if stats.avg_clv > 0 else "❌"
                lines.append(
                    f"   {emoji} {strategy}: {stats.avg_clv:+.2f}% CLV (n={stats.bets_with_clv})"
                )

        # Edge validation summary
        lines.append("\n🎯 EDGE VALIDATION:")
        for strategy in strategies:
            report = self.get_strategy_edge_report(strategy, days_back)
            if report and report.clv_stats.bets_with_clv >= 5:
                status = "✅ VALIDATED" if report.is_validated else "❌ NOT VALIDATED"
                lines.append(f"   {strategy}: {status}")
                lines.append(f"      Wins with +CLV (true edge): {report.wins_with_positive_clv}")
                lines.append(f"      Wins with -CLV (lucky): {report.wins_with_negative_clv}")
                lines.append(
                    f"      Losses with +CLV (variance): {report.losses_with_positive_clv}"
                )

        # V14.0: Significant line movements with explanations
        lines.append("\n🔍 SIGNIFICANT LINE MOVEMENTS (|CLV| ≥ 2%):")
        significant_movements = self.get_significant_line_movements(days_back=days_back)
        if significant_movements:
            for movement in significant_movements[:10]:  # Show top 10
                clv_emoji = "📈" if movement["clv"] > 0 else "📉"
                lines.append(f"\n   {clv_emoji} {movement['match']}")
                lines.append(f"      Strategy: {movement['strategy']}")
                lines.append(f"      Market: {movement['market']}")
                lines.append(f"      CLV: {movement['clv']:+.2f}%")
                lines.append(
                    f"      Odds: {movement['odds_at_alert']:.2f} → {movement['odds_at_kickoff']:.2f}"
                )
                if movement["line_movement_explanation"]:
                    lines.append(
                        f"      Explanation: {movement['line_movement_explanation'][:150]}..."
                    )
                else:
                    lines.append("      Explanation: Not available")
        else:
            lines.append("   No significant line movements found in this period.")

        lines.append("\n" + "=" * 60)

        return "\n".join(lines)

    def get_clv_for_optimizer(self, strategy: str, days_back: int = 30) -> dict:
        """
        Get CLV data formatted for optimizer weight adjustment.

        Args:
            strategy: Primary driver name
            days_back: Lookback period

        Returns:
            Dict with clv_avg, clv_positive_rate, sample_size, is_validated
        """
        stats = self.get_clv_stats(days_back=days_back, strategy=strategy)
        report = self.get_strategy_edge_report(strategy, days_back)

        return {
            "clv_avg": stats.avg_clv,
            "clv_positive_rate": stats.positive_clv_rate,
            "sample_size": stats.bets_with_clv,
            "edge_quality": stats.edge_quality,
            "is_validated": report.is_validated if report else False,
        }

    def get_significant_line_movements(
        self, strategy: str = None, days_back: int = 30, min_clv: float = 2.0
    ) -> list[dict]:
        """
        Get significant line movements with explanations.

        V14.0: Returns bets with |CLV| >= min_clv and their Tavily explanations.

        Args:
            strategy: Filter by primary_driver (optional)
            days_back: Lookback period
            min_clv: Minimum absolute CLV to consider significant (default 2.0%)

        Returns:
            List of dicts with match info, CLV, and line_movement_explanation
        """
        with get_db_context() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

            # Build query
            query = (
                db.query(NewsLog, Match)
                .join(Match)
                .filter(
                    NewsLog.sent == True,
                    NewsLog.clv_percent.isnot(None),
                    Match.start_time >= cutoff,
                )
            )

            # Filter by strategy if provided
            if strategy:
                query = query.filter(NewsLog.primary_driver == strategy)

            # Filter by significant CLV
            query = query.filter(
                (NewsLog.clv_percent >= min_clv) | (NewsLog.clv_percent <= -min_clv)
            )

            # Get results
            results = query.all()

            # Build list of significant movements
            movements: list[str] = []
            for news_log, match in results:
                movement = {
                    "match": f"{match.home_team} vs {match.away_team}",
                    "league": match.league,
                    "strategy": news_log.primary_driver,
                    "market": news_log.recommended_market,
                    "clv": news_log.clv_percent,
                    "odds_at_alert": news_log.odds_at_alert,
                    "odds_at_kickoff": news_log.odds_at_kickoff,
                    "match_date": match.start_time,
                    "line_movement_explanation": news_log.line_movement_explanation,
                }
                movements.append(movement)

            # Sort by absolute CLV (most significant first)
            movements.sort(key=lambda x: abs(x["clv"]), reverse=True)

            return movements


# Singleton instance
_clv_tracker: CLVTracker | None = None
_clv_tracker_lock = threading.Lock()


def get_clv_tracker() -> CLVTracker:
    """
    Get or create singleton CLV tracker instance (thread-safe).

    Uses double-check locking pattern to prevent race conditions
    when multiple threads access the singleton simultaneously.
    """
    global _clv_tracker
    if _clv_tracker is None:
        with _clv_tracker_lock:
            if _clv_tracker is None:  # Double-check pattern
                _clv_tracker = CLVTracker()
    return _clv_tracker
