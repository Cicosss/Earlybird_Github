#!/usr/bin/env python3
"""
Verification Test for Prompt Signature Fixes
============================================

This test verifies that the three critical prompt builder functions
have been fixed to match the parameters being passed by the providers.

Critical Issues Fixed:
1. build_news_verification_prompt: 5 params (was 3)
2. build_biscotto_confirmation_prompt: 9 params (was 5)
3. build_match_context_enrichment_prompt: 5 params (was 3)

These fixes prevent runtime crashes when:
- Verifying news items
- Confirming biscotto signals
- Enriching match context
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ingestion.prompts import (
    build_news_verification_prompt,
    build_biscotto_confirmation_prompt,
    build_match_context_enrichment_prompt,
)


def test_build_news_verification_prompt():
    """Test build_news_verification_prompt with 5 parameters as used by providers."""
    print("\n" + "=" * 70)
    print("TEST 1: build_news_verification_prompt")
    print("=" * 70)

    try:
        # Parameters exactly as passed by deepseek_intel_provider, perplexity_provider,
        # and openrouter_fallback_provider
        prompt = build_news_verification_prompt(
            news_title="Player Injury Update",
            news_snippet="Star striker injured in training",
            team_name="Juventus",
            news_source="@juventusfc",
            match_context="Upcoming match vs AC Milan, critical for title race",
        )

        # Verify prompt contains all expected information
        assert "Player Injury Update" in prompt, "Missing news_title in prompt"
        assert "Star striker injured in training" in prompt, "Missing news_snippet in prompt"
        assert "Juventus" in prompt, "Missing team_name in prompt"
        assert "@juventusfc" in prompt, "Missing news_source in prompt"
        assert "title race" in prompt, "Missing match_context in prompt"

        print("✅ PASS: Function accepts 5 parameters correctly")
        print(f"✅ PASS: Prompt generated successfully ({len(prompt)} chars)")
        print(f"✅ PASS: All parameters properly included in prompt")
        return True

    except TypeError as e:
        print(f"❌ FAIL: TypeError - {e}")
        print("   This indicates the function signature is still incorrect")
        return False
    except Exception as e:
        print(f"❌ FAIL: Unexpected error - {e}")
        return False


def test_build_biscotto_confirmation_prompt():
    """Test build_biscotto_confirmation_prompt with 9 parameters as used by providers."""
    print("\n" + "=" * 70)
    print("TEST 2: build_biscotto_confirmation_prompt")
    print("=" * 70)

    try:
        # Parameters exactly as passed by deepseek_intel_provider, perplexity_provider,
        # and openrouter_fallback_provider
        prompt = build_biscotto_confirmation_prompt(
            home_team="Juventus",
            away_team="AC Milan",
            match_date="2026-03-15",
            league="Serie A",
            draw_odds=3.20,
            implied_prob=0.3125,
            odds_pattern="dropping",
            season_context="final matchday of the season",
            detected_factors="both teams safe from relegation, no European spots at stake",
        )

        # Verify prompt contains all expected information
        assert "Juventus" in prompt, "Missing home_team in prompt"
        assert "AC Milan" in prompt, "Missing away_team in prompt"
        assert "2026-03-15" in prompt, "Missing match_date in prompt"
        assert "Serie A" in prompt, "Missing league in prompt"
        assert "3.2" in prompt, "Missing draw_odds in prompt"
        assert "31.2%" in prompt, "Missing implied_prob in prompt"
        assert "dropping" in prompt, "Missing odds_pattern in prompt"
        assert "final matchday" in prompt, "Missing season_context in prompt"
        assert "safe from relegation" in prompt, "Missing detected_factors in prompt"

        print("✅ PASS: Function accepts 9 parameters correctly")
        print(f"✅ PASS: Prompt generated successfully ({len(prompt)} chars)")
        print(f"✅ PASS: All parameters properly included in prompt")
        return True

    except TypeError as e:
        print(f"❌ FAIL: TypeError - {e}")
        print("   This indicates the function signature is still incorrect")
        return False
    except Exception as e:
        print(f"❌ FAIL: Unexpected error - {e}")
        return False


def test_build_match_context_enrichment_prompt():
    """Test build_match_context_enrichment_prompt with 5 parameters as used by providers."""
    print("\n" + "=" * 70)
    print("TEST 3: build_match_context_enrichment_prompt")
    print("=" * 70)

    try:
        # Parameters exactly as passed by deepseek_intel_provider
        prompt = build_match_context_enrichment_prompt(
            home_team="Juventus",
            away_team="AC Milan",
            match_date="2026-03-15",
            league="Serie A",
            existing_context="Both teams coming off wins",
        )

        # Verify prompt contains all expected information
        assert "Juventus" in prompt, "Missing home_team in prompt"
        assert "AC Milan" in prompt, "Missing away_team in prompt"
        assert "2026-03-15" in prompt, "Missing match_date in prompt"
        assert "Serie A" in prompt, "Missing league in prompt"
        assert "coming off wins" in prompt, "Missing existing_context in prompt"

        print("✅ PASS: Function accepts 5 parameters correctly")
        print(f"✅ PASS: Prompt generated successfully ({len(prompt)} chars)")
        print(f"✅ PASS: All parameters properly included in prompt")
        return True

    except TypeError as e:
        print(f"❌ FAIL: TypeError - {e}")
        print("   This indicates the function signature is still incorrect")
        return False
    except Exception as e:
        print(f"❌ FAIL: Unexpected error - {e}")
        return False


def main():
    """Run all verification tests."""
    print("\n" + "=" * 70)
    print("PROMPT SIGNATURE FIXES VERIFICATION TEST")
    print("=" * 70)
    print("\nThis test verifies that the critical signature mismatches")
    print("have been fixed to prevent runtime crashes on VPS.")
    print("\nTesting functions with parameters exactly as passed by providers:")
    print("- deepseek_intel_provider")
    print("- perplexity_provider")
    print("- openrouter_fallback_provider")

    results = []

    # Run all tests
    results.append(test_build_news_verification_prompt())
    results.append(test_build_biscotto_confirmation_prompt())
    results.append(test_build_match_context_enrichment_prompt())

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    passed = sum(results)
    total = len(results)

    print(f"\nTests Passed: {passed}/{total}")

    if passed == total:
        print("\n✅ ALL TESTS PASSED!")
        print("\nThe signature mismatches have been successfully fixed.")
        print("The bot will NOT crash due to these issues on VPS deployment.")
        return 0
    else:
        print(f"\n❌ {total - passed} TEST(S) FAILED!")
        print("\nSome signature mismatches still exist.")
        print("The bot WILL crash on VPS deployment if not fixed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
