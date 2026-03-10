"""
Test Three-Level Fallback System

Tests three-level fallback system: DeepSeek → Tavily → Claude 3 Haiku
"""

import logging

from src.services.intelligence_router import get_intelligence_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_intelligence_router_initialization():
    """Test that IntelligenceRouter initializes correctly."""
    logger.info("Testing IntelligenceRouter initialization...")

    router = get_intelligence_router()
    assert router is not None, "IntelligenceRouter should be initialized"
    assert router.is_available(), "IntelligenceRouter should be available"

    logger.info("✅ IntelligenceRouter initialized successfully")
    logger.info(f"   Active provider: {router.get_active_provider_name()}")


def test_deep_dive_analysis():
    """Test deep dive analysis with three-level fallback."""
    logger.info("Testing deep dive analysis...")

    router = get_intelligence_router()

    result = router.get_match_deep_dive(
        home_team="Juventus",
        away_team="AC Milan",
        match_date="2024-03-10",
    )

    assert result is not None, "Deep dive should return a result"
    assert "internal_crisis" in result, "Result should contain internal_crisis"
    assert "turnover_risk" in result, "Result should contain turnover_risk"
    assert "referee_intel" in result, "Result should contain referee_intel"
    assert "biscotto_potential" in result, "Result should contain biscotto_potential"
    assert "injury_impact" in result, "Result should contain injury_impact"

    logger.info("✅ Deep dive analysis successful")
    logger.info(f"   Internal crisis: {result.get('internal_crisis')}")
    logger.info(f"   Turnover risk: {result.get('turnover_risk')}")
    logger.info(f"   Biscotto potential: {result.get('biscotto_potential')}")


def test_news_verification():
    """Test news verification with three-level fallback."""
    logger.info("Testing news verification...")

    router = get_intelligence_router()

    result = router.verify_news_item(
        news_title="Juan Cabal injured",
        news_snippet="Juan Cabal has a knee injury and will miss next match",
        team_name="Juventus",
        news_source="Twitter",
        match_context="vs AC Milan on 2024-03-10",
    )

    assert result is not None, "News verification should return a result"
    assert "verification_status" in result, "Result should contain verification_status"

    logger.info("✅ News verification successful")
    logger.info(f"   Verification status: {result.get('verification_status')}")


def test_betting_stats():
    """Test betting stats retrieval with three-level fallback."""
    logger.info("Testing betting stats retrieval...")

    router = get_intelligence_router()

    result = router.get_betting_stats(
        home_team="Juventus",
        away_team="AC Milan",
        match_date="2024-03-10",
        league="Serie A",
    )

    assert result is not None, "Betting stats should return a result"
    assert "corners_signal" in result, "Result should contain corners_signal"

    logger.info("✅ Betting stats retrieval successful")
    logger.info(f"   Corners signal: {result.get('corners_signal')}")


def test_biscotto_confirmation():
    """Test biscotto confirmation with three-level fallback."""
    logger.info("Testing biscotto confirmation...")

    router = get_intelligence_router()

    result = router.confirm_biscotto(
        home_team="Juventus",
        away_team="AC Milan",
        match_date="2024-03-10",
        league="Serie A",
        draw_odds=3.50,
        implied_prob=28.57,
        odds_pattern="DRIFT",
        season_context="End of season, both teams safe from relegation",
        detected_factors=["Low motivation", "Friendly atmosphere"],
    )

    assert result is not None, "Biscotto confirmation should return a result"
    assert "biscotto_confirmed" in result, "Result should contain biscotto_confirmed"

    logger.info("✅ Biscotto confirmation successful")
    logger.info(f"   Biscotto confirmed: {result.get('biscotto_confirmed')}")
    logger.info(f"   Confidence boost: {result.get('confidence_boost')}")


def run_all_tests():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("Running Three-Level Fallback Tests")
    logger.info("=" * 60)

    try:
        test_intelligence_router_initialization()
        test_deep_dive_analysis()
        test_news_verification()
        test_betting_stats()
        test_biscotto_confirmation()

        logger.info("=" * 60)
        logger.info("✅ All tests passed!")
        logger.info("=" * 60)
        return True
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ Test failed: {e}")
        logger.error("=" * 60)
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
