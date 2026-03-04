"""
Test Alert Pipeline - End-to-End Trace & Repair

This script simulates the complete data flow from AI analysis to Telegram alert delivery.
It tests each stage of the pipeline to identify the exact point of failure.

Created: 2026-03-01
Purpose: Debug "Last Mile Architecture Resolution - Alert Delivery Failure"
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from unittest.mock import Mock

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================
# MOCK DATA - Simulate AI Response
# ============================================

MOCK_AI_RESPONSE_JSON = {
    "final_verdict": "BET",
    "confidence": 95,
    "confidence_breakdown": {
        "news_weight": 35,
        "odds_weight": 20,
        "form_weight": 20,
        "injuries_weight": 20,
    },
    "recommended_market": "WINNER",
    "primary_market": "1",
    "primary_driver": "INJURY_INTEL",
    "combo_suggestion": "Home Win + Over 2.5 Goals",
    "combo_reasoning": "Team has strong attack and opponent has weak defense",
    "reasoning": "Assenza confermata da FotMob, il mercato non ha ancora reagito. Key player out for away team.",
}

MOCK_AI_RESPONSE_WITH_MARKDOWN = f"""
Here's my analysis:

{json.dumps(MOCK_AI_RESPONSE_JSON, indent=2)}

This is a strong bet opportunity.
"""

# ============================================
# TEST STAGE 1: AI Parser
# ============================================


def test_stage_1_ai_parser():
    """
    Test Stage 1: AI Response Parsing

    Verify that the parser can extract JSON from AI response.
    """
    logger.info("=" * 80)
    logger.info("STAGE 1: AI Response Parsing")
    logger.info("=" * 80)

    try:
        from src.utils.ai_parser import extract_json

        # Test with clean JSON
        logger.info("\n[Test 1.1] Parsing clean JSON response...")
        clean_json = json.dumps(MOCK_AI_RESPONSE_JSON)
        result = extract_json(clean_json)
        logger.info("✅ Clean JSON parsed successfully")
        logger.info(f"   - final_verdict: {result.get('final_verdict')}")
        logger.info(f"   - confidence: {result.get('confidence')}")
        logger.info(f"   - recommended_market: {result.get('recommended_market')}")
        logger.info(f"   - primary_market: {result.get('primary_market')}")
        logger.info(f"   - combo_suggestion: {result.get('combo_suggestion')}")
        logger.info(f"   - combo_reasoning: {result.get('combo_reasoning')}")
        logger.info(f"   - reasoning: {result.get('reasoning')}")

        # Test with markdown-wrapped JSON
        logger.info("\n[Test 1.2] Parsing markdown-wrapped JSON response...")
        result2 = extract_json(MOCK_AI_RESPONSE_WITH_MARKDOWN)
        logger.info("✅ Markdown-wrapped JSON parsed successfully")
        logger.info(f"   - final_verdict: {result2.get('final_verdict')}")
        logger.info(f"   - confidence: {result2.get('confidence')}")

        # Verify all required fields are present
        required_fields = [
            "final_verdict",
            "confidence",
            "recommended_market",
            "primary_market",
            "combo_suggestion",
            "combo_reasoning",
            "reasoning",
        ]
        missing_fields = [f for f in required_fields if f not in result2]

        if missing_fields:
            logger.error(f"❌ Missing required fields: {missing_fields}")
            return False
        else:
            logger.info("✅ All required fields present")

        return True

    except Exception as e:
        logger.error(f"❌ Stage 1 FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


# ============================================
# TEST STAGE 2: Analyzer Response Validation
# ============================================


def test_stage_2_analyzer_validation():
    """
    Test Stage 2: Analyzer Response Validation

    Verify that the analyzer's validate_ai_response function works correctly.
    """
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 2: Analyzer Response Validation")
    logger.info("=" * 80)

    try:
        from src.analysis.analyzer import validate_ai_response

        logger.info("\n[Test 2.1] Validating AI response structure...")
        validated = validate_ai_response(MOCK_AI_RESPONSE_JSON)

        logger.info("✅ Response validated successfully")
        logger.info(f"   - final_verdict: {validated.get('final_verdict')}")
        logger.info(f"   - confidence: {validated.get('confidence')}")
        logger.info(f"   - recommended_market: {validated.get('recommended_market')}")
        logger.info(f"   - primary_market: {validated.get('primary_market')}")
        logger.info(f"   - combo_suggestion: {validated.get('combo_suggestion')}")
        logger.info(f"   - combo_reasoning: {validated.get('combo_reasoning')}")
        logger.info(f"   - reasoning: {validated.get('reasoning')}")

        # Test with incomplete response
        logger.info("\n[Test 2.2] Testing with incomplete response...")
        incomplete_response = {"final_verdict": "BET", "confidence": 80}
        validated_incomplete = validate_ai_response(incomplete_response)

        logger.info("✅ Incomplete response handled with defaults")
        logger.info(
            f"   - recommended_market (default): {validated_incomplete.get('recommended_market')}"
        )
        logger.info(f"   - primary_market (default): {validated_incomplete.get('primary_market')}")
        logger.info(f"   - reasoning (default): {validated_incomplete.get('reasoning')}")

        return True

    except Exception as e:
        logger.error(f"❌ Stage 2 FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


# ============================================
# TEST STAGE 3: NewsLog Creation
# ============================================


def test_stage_3_newslog_creation():
    """
    Test Stage 3: NewsLog Object Creation

    Verify that a NewsLog object can be created with the parsed AI response.
    """
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 3: NewsLog Object Creation")
    logger.info("=" * 80)

    try:
        from src.database.models import Match, NewsLog

        # Create mock match object
        mock_match = Mock(spec=Match)
        mock_match.id = 1
        mock_match.home_team = "Roma"
        mock_match.away_team = "Lazio"
        mock_match.league = "Serie A"
        mock_match.start_time = datetime.now(timezone.utc)

        logger.info("\n[Test 3.1] Creating NewsLog object...")

        # Create NewsLog with all fields from AI response
        newslog = NewsLog(
            match_id=mock_match.id,
            url="https://example.com/news/article",
            summary=MOCK_AI_RESPONSE_JSON["reasoning"],
            score=9.5,
            category="HIGH_CONFIDENCE_BET",
            affected_team="Roma",
            combo_suggestion=MOCK_AI_RESPONSE_JSON["combo_suggestion"],
            combo_reasoning=MOCK_AI_RESPONSE_JSON["combo_reasoning"],
            recommended_market=MOCK_AI_RESPONSE_JSON["primary_market"],
            primary_driver=MOCK_AI_RESPONSE_JSON["primary_driver"],
            odds_taken=1.85,
            confidence=MOCK_AI_RESPONSE_JSON.get("confidence", 85),  # V11.1: AI confidence (0-100)
            confidence_breakdown=json.dumps(MOCK_AI_RESPONSE_JSON["confidence_breakdown"]),
            is_convergent=False,
            convergence_sources=None,
        )

        logger.info("✅ NewsLog object created successfully")
        logger.info(f"   - ID: {newslog.id}")
        logger.info(f"   - match_id: {newslog.match_id}")
        logger.info(f"   - summary: {newslog.summary[:50]}...")
        logger.info(f"   - score: {newslog.score}")
        logger.info(f"   - category: {newslog.category}")
        logger.info(f"   - recommended_market: {newslog.recommended_market}")
        logger.info(f"   - combo_suggestion: {newslog.combo_suggestion}")
        logger.info(f"   - combo_reasoning: {newslog.combo_reasoning}")
        logger.info(f"   - primary_driver: {newslog.primary_driver}")

        return True

    except Exception as e:
        logger.error(f"❌ Stage 3 FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


# ============================================
# TEST STAGE 4: Betting Quant Decision
# ============================================


def test_stage_4_betting_quant():
    """
    Test Stage 4: Betting Quant Decision Logic

    Verify that the BettingQuant evaluates the bet correctly.
    """
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 4: Betting Quant Decision Logic")
    logger.info("=" * 80)

    try:
        from src.core.betting_quant import BettingQuant
        from src.database.models import Match, NewsLog

        # Create mock match object
        mock_match = Mock(spec=Match)
        mock_match.id = 1
        mock_match.home_team = "Roma"
        mock_match.away_team = "Lazio"
        mock_match.league = "Serie A"
        mock_match.current_home_odd = 1.85
        mock_match.opening_home_odd = 2.10
        mock_match.current_away_odd = 4.20
        mock_match.opening_away_odd = 3.80
        mock_match.current_draw_odd = 3.60
        mock_match.opening_draw_odd = 3.50

        # Create mock analysis (NewsLog)
        mock_analysis = Mock(spec=NewsLog)
        mock_analysis.summary = MOCK_AI_RESPONSE_JSON["reasoning"]
        mock_analysis.recommended_market = MOCK_AI_RESPONSE_JSON["recommended_market"]
        mock_analysis.combo_suggestion = MOCK_AI_RESPONSE_JSON["combo_suggestion"]
        mock_analysis.combo_reasoning = MOCK_AI_RESPONSE_JSON["combo_reasoning"]

        logger.info("\n[Test 4.1] Creating BettingQuant instance...")
        quant = BettingQuant(league_avg=1.35, league_key="serie_a")

        logger.info("\n[Test 4.2] Evaluating bet...")
        decision = quant.evaluate_bet(
            match=mock_match,
            analysis=mock_analysis,
            home_scored=1.8,
            home_conceded=1.2,
            away_scored=1.2,
            away_conceded=1.5,
            market_odds={
                "home": mock_match.current_home_odd,
                "draw": mock_match.current_draw_odd,
                "away": mock_match.current_away_odd,
                "over_25": 1.90,
                "under_25": 1.90,
                "btts": 1.85,
            },
            ai_prob=0.95,  # 95% confidence from AI
        )

        logger.info("✅ Bet evaluation completed")
        logger.info(f"   - should_bet: {decision.should_bet}")
        logger.info(f"   - verdict: {decision.verdict}")
        logger.info(f"   - confidence: {decision.confidence}")
        logger.info(f"   - recommended_market: {decision.recommended_market}")
        logger.info(f"   - primary_market: {decision.primary_market}")
        logger.info(f"   - math_prob: {decision.math_prob}")
        logger.info(f"   - implied_prob: {decision.implied_prob}")
        logger.info(f"   - edge: {decision.edge}")
        logger.info(f"   - kelly_stake: {decision.kelly_stake}")
        logger.info(f"   - final_stake: {decision.final_stake}")
        logger.info(f"   - veto_reason: {decision.veto_reason}")

        if not decision.should_bet:
            logger.warning(f"⚠️ BettingQuant decided NOT to bet: {decision.veto_reason}")
        else:
            logger.info("✅ BettingQuant approved the bet")

        return decision.should_bet

    except Exception as e:
        logger.error(f"❌ Stage 4 FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


# ============================================
# TEST STAGE 5: Notifier Message Construction
# ============================================


def test_stage_5_notifier_construction():
    """
    Test Stage 5: Notifier Message Construction

    Verify that the notifier can build the Telegram message correctly.
    """
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 5: Notifier Message Construction")
    logger.info("=" * 80)

    try:
        from src.alerting.notifier import _build_bet_section, _clean_ai_text

        # Create mock data
        recommended_market = MOCK_AI_RESPONSE_JSON["primary_market"]
        combo_suggestion = MOCK_AI_RESPONSE_JSON["combo_suggestion"]
        combo_reasoning = MOCK_AI_RESPONSE_JSON["combo_reasoning"]
        math_edge = {"market": "HOME", "edge": 12.5, "kelly_stake": 3.2}
        financial_risk = None

        logger.info("\n[Test 5.1] Building bet section...")
        bet_section = _build_bet_section(
            recommended_market=recommended_market,
            combo_suggestion=combo_suggestion,
            combo_reasoning_clean=_clean_ai_text(combo_reasoning),
            math_edge=math_edge,
            financial_risk=financial_risk,
        )

        logger.info("✅ Bet section built successfully")
        logger.info(f"   Bet section content:\n{bet_section}")

        # Test AI text cleaning
        logger.info("\n[Test 5.2] Testing AI text cleaning...")
        dirty_text = "Assenza confermata da FotMob. Leggi la fonte: https://example.com/news"
        clean_text = _clean_ai_text(dirty_text)
        logger.info(f"   Original: {dirty_text}")
        logger.info(f"   Cleaned: {clean_text}")

        if "https://" in clean_text:
            logger.warning("⚠️ URL still present in cleaned text")
        else:
            logger.info("✅ URL removed from cleaned text")

        return True

    except Exception as e:
        logger.error(f"❌ Stage 5 FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


# ============================================
# TEST STAGE 6: Complete Alert Sending (Dry Run)
# ============================================


def test_stage_6_complete_alert_dry_run():
    """
    Test Stage 6: Complete Alert Sending (Dry Run)

    Simulate the complete alert sending flow without actually sending to Telegram.
    """
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 6: Complete Alert Sending (Dry Run)")
    logger.info("=" * 80)

    try:
        from unittest.mock import patch

        from src.database.models import Match

        # Create mock match object
        mock_match = Mock(spec=Match)
        mock_match.id = 1
        mock_match.home_team = "Roma"
        mock_match.away_team = "Lazio"
        mock_match.league = "Serie A"
        mock_match.start_time = datetime.now(timezone.utc)
        mock_match.current_home_odd = 1.85
        mock_match.opening_home_odd = 2.10
        mock_match.current_away_odd = 4.20
        mock_match.opening_away_odd = 3.80
        mock_match.current_draw_odd = 3.60
        mock_match.opening_draw_odd = 3.50

        # Prepare alert data
        news_summary = MOCK_AI_RESPONSE_JSON["reasoning"]
        news_url = "https://example.com/news/article"
        score = 9.5
        league = "Serie A"
        combo_suggestion = MOCK_AI_RESPONSE_JSON["combo_suggestion"]
        combo_reasoning = MOCK_AI_RESPONSE_JSON["combo_reasoning"]
        recommended_market = MOCK_AI_RESPONSE_JSON["primary_market"]

        logger.info("\n[Test 6.1] Simulating send_alert call...")
        logger.info(f"   Match: {mock_match.home_team} vs {mock_match.away_team}")
        logger.info(f"   League: {league}")
        logger.info(f"   Score: {score}/10")
        logger.info(f"   Market: {recommended_market}")
        logger.info(f"   Combo: {combo_suggestion}")
        logger.info(f"   News Summary: {news_summary[:100]}...")

        # Mock the actual Telegram API call
        with patch("src.alerting.notifier._send_telegram_request") as mock_send:
            # Create a mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_send.return_value = mock_response

            # Import and call send_alert
            from src.alerting.notifier import send_alert

            send_alert(
                match_obj=mock_match,
                news_summary=news_summary,
                news_url=news_url,
                score=score,
                league=league,
                combo_suggestion=combo_suggestion,
                combo_reasoning=combo_reasoning,
                recommended_market=recommended_market,
                math_edge={"market": "HOME", "edge": 12.5, "kelly_stake": 3.2},
                market_warning=None,  # V11.1 FIX: Explicitly pass market_warning (None for test)
            )

            # Verify the mock was called
            if mock_send.called:
                logger.info("✅ Telegram API was called (mocked)")

                # Get the payload that would have been sent
                call_args = mock_send.call_args
                url = call_args[0][0]
                payload = call_args[0][1]

                logger.info(f"   URL: {url}")
                logger.info(f"   Chat ID: {payload.get('chat_id')}")
                logger.info(f"   Message length: {len(payload.get('text', ''))} chars")
                logger.info(f"   Parse mode: {payload.get('parse_mode')}")

                # Check if message contains key elements
                message = payload.get("text", "")

                key_elements = {
                    "Match name": "Roma" in message and "Lazio" in message,
                    "Score": f"{score}/10" in message,
                    "Market": recommended_market in message,
                    "Combo": combo_suggestion in message,
                    "News summary": news_summary[:50] in message,
                    "Link": news_url in message,
                }

                logger.info("\n[Test 6.2] Checking message content...")
                all_present = True
                for element, present in key_elements.items():
                    status = "✅" if present else "❌"
                    logger.info(f"   {status} {element}: {present}")
                    if not present:
                        all_present = False

                if all_present:
                    logger.info("✅ All key elements present in message")
                else:
                    logger.warning("⚠️ Some key elements missing from message")

                return all_present
            else:
                logger.error("❌ Telegram API was NOT called")
                return False

    except Exception as e:
        logger.error(f"❌ Stage 6 FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


# ============================================
# MAIN TEST RUNNER
# ============================================


def main():
    """
    Run all test stages and report results.
    """
    logger.info("\n" + "=" * 80)
    logger.info("EARLYBIRD ALERT PIPELINE TEST")
    logger.info("Testing complete data flow from AI response to Telegram alert")
    logger.info("=" * 80)

    results = {}

    # Run all test stages
    results["Stage 1: AI Parser"] = test_stage_1_ai_parser()
    results["Stage 2: Analyzer Validation"] = test_stage_2_analyzer_validation()
    results["Stage 3: NewsLog Creation"] = test_stage_3_newslog_creation()
    results["Stage 4: Betting Quant"] = test_stage_4_betting_quant()
    results["Stage 5: Notifier Construction"] = test_stage_5_notifier_construction()
    results["Stage 6: Complete Alert (Dry Run)"] = test_stage_6_complete_alert_dry_run()

    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)

    all_passed = True
    for stage, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status} - {stage}")
        if not passed:
            all_passed = False

    logger.info("\n" + "=" * 80)
    if all_passed:
        logger.info("🎉 ALL TESTS PASSED - Alert pipeline is working correctly!")
    else:
        logger.error("❌ SOME TESTS FAILED - Alert pipeline has issues!")
        logger.error("Review the logs above to identify the exact point of failure.")
    logger.info("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
