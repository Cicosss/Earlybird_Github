"""
Test suite for league_manager.py - Tiered League Strategy

Tests:
- Tier classification
- Round-robin rotation
- Edge cases (empty lists, unknown leagues)
- Backward compatibility (ELITE_LEAGUES alias)
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.league_manager import (
    TIER_1_LEAGUES,
    TIER_2_LEAGUES,
    ELITE_LEAGUES,
    is_tier1_league,
    is_tier2_league,
    is_elite_league,
    is_niche_league,
    get_league_tier,
    get_league_priority,
    get_regions_for_league,
    get_leagues_for_cycle,
    get_tier2_for_cycle,
    get_elite_leagues,
    get_fallback_leagues,
    TIER_2_PER_CYCLE,
    # V4.3: Tier 2 Fallback System
    should_activate_tier2_fallback,
    get_tier2_fallback_batch,
    record_tier2_activation,
    reset_daily_tier2_stats,
    get_tier2_fallback_status,
    increment_cycle,
    TIER2_FALLBACK_BATCH_SIZE,
    TIER2_FALLBACK_COOLDOWN,
    TIER2_FALLBACK_DAILY_LIMIT,
    TIER2_DRY_CYCLES_THRESHOLD,
)


class TestTierClassification:
    """Test tier detection functions."""
    
    def test_tier1_detection(self):
        """Tier 1 leagues should be correctly identified."""
        assert is_tier1_league("soccer_turkey_super_league") is True
        assert is_tier1_league("soccer_argentina_primera_division") is True
        assert is_tier1_league("soccer_norway_eliteserien") is False
    
    def test_tier2_detection(self):
        """Tier 2 leagues detection - now enabled for Fallback System V4.3."""
        # Tier 2 is now enabled (8 leagues)
        assert is_tier2_league("soccer_norway_eliteserien") is True
        assert is_tier2_league("soccer_china_superleague") is True
        assert is_tier2_league("soccer_turkey_super_league") is False  # This is Tier 1
    
    def test_unknown_league(self):
        """Unknown leagues should return False for all tier checks."""
        assert is_tier1_league("soccer_unknown") is False
        assert is_tier2_league("soccer_unknown") is False
        assert is_niche_league("soccer_unknown") is False
        assert get_league_tier("soccer_unknown") == "OTHER"
    
    def test_get_league_tier_labels(self):
        """get_league_tier should return correct labels."""
        assert get_league_tier("soccer_turkey_super_league") == "TIER1"
        # Tier 2 now enabled - norway returns TIER2
        assert get_league_tier("soccer_norway_eliteserien") == "TIER2"
        assert get_league_tier("soccer_fake_league") == "OTHER"


class TestBackwardCompatibility:
    """Test backward compatibility with old code."""
    
    def test_elite_leagues_alias(self):
        """ELITE_LEAGUES should be alias for TIER_1_LEAGUES."""
        assert ELITE_LEAGUES == TIER_1_LEAGUES
    
    def test_is_elite_league_alias(self):
        """is_elite_league should work same as is_tier1_league."""
        for league in TIER_1_LEAGUES:
            assert is_elite_league(league) is True
        for league in TIER_2_LEAGUES:
            assert is_elite_league(league) is False
    
    def test_get_elite_leagues(self):
        """get_elite_leagues should return Tier 1 copy."""
        result = get_elite_leagues()
        assert result == TIER_1_LEAGUES
        # Should be a copy, not same object
        result.append("test")
        assert len(result) != len(TIER_1_LEAGUES)


class TestRoundRobin:
    """Test Tier 2 round-robin rotation."""
    
    def test_tier2_batch_size(self):
        """Each batch should have TIER_2_PER_CYCLE leagues."""
        # Reset state by importing fresh
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        batch = lm.get_tier2_for_cycle()
        # Tier 2 is now enabled (8 leagues)
        assert len(batch) == TIER_2_PER_CYCLE
        assert len(batch) == 3  # TIER_2_PER_CYCLE = 3
    
    def test_tier2_rotation_covers_all(self):
        """After enough cycles, all Tier 2 leagues should be covered."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        # Tier 2 is now enabled
        assert len(lm.TIER_2_LEAGUES) == 8
        
        seen = set()
        # Run enough cycles to cover all leagues
        cycles_needed = (len(TIER_2_LEAGUES) // TIER_2_PER_CYCLE) + 2
        
        for _ in range(cycles_needed):
            batch = lm.get_tier2_for_cycle()
            seen.update(batch)
        
        assert seen == set(TIER_2_LEAGUES)
    
    def test_tier2_all_valid(self):
        """All returned leagues should be valid Tier 2."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        batch = lm.get_tier2_for_cycle()
        for league in batch:
            assert league in TIER_2_LEAGUES


class TestCycleManagement:
    """Test get_leagues_for_cycle function."""
    
    def test_normal_mode(self):
        """Normal mode should return Tier1 + Tier2 batch."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        leagues = lm.get_leagues_for_cycle(emergency_mode=False)
        
        # Should have all Tier 1
        for t1 in TIER_1_LEAGUES:
            assert t1 in leagues
        
        # Tier 2 is now enabled - should have TIER_2_PER_CYCLE leagues
        tier2_count = sum(1 for l in leagues if l in TIER_2_LEAGUES)
        assert tier2_count == TIER_2_PER_CYCLE
    
    def test_emergency_mode(self):
        """Emergency mode should return only Tier 1."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        leagues = lm.get_leagues_for_cycle(emergency_mode=True)
        
        assert leagues == TIER_1_LEAGUES
        # No Tier 2
        for league in leagues:
            assert league not in TIER_2_LEAGUES


class TestRegions:
    """Test region mapping."""
    
    def test_latam_regions(self):
        """LATAM leagues should use us,eu regions."""
        assert get_regions_for_league("soccer_argentina_primera_division") == "us,eu"
        # brazil_serie_b not in LATAM_LEAGUES set, uses default
        assert get_regions_for_league("soccer_brazil_serie_b") in ["us,eu", "eu,uk"]
    
    def test_australia_regions(self):
        """Australia should use au,uk,eu regions."""
        assert get_regions_for_league("soccer_australia_aleague") == "au,uk,eu"
    
    def test_asia_regions(self):
        """Asia leagues should use eu,uk,au regions (or default if not in ASIA_LEAGUES)."""
        # ASIA_LEAGUES is currently empty (disabled), so these use default
        result = get_regions_for_league("soccer_china_superleague")
        assert result in ["eu,uk,au", "eu,uk"]  # Depends on ASIA_LEAGUES config
        
        result = get_regions_for_league("soccer_japan_j_league")
        assert result in ["eu,uk,au", "eu,uk"]
    
    def test_europe_default(self):
        """European leagues should use eu,uk regions."""
        assert get_regions_for_league("soccer_turkey_super_league") == "eu,uk"
        assert get_regions_for_league("soccer_norway_eliteserien") == "eu,uk"


class TestPriority:
    """Test league priority."""
    
    def test_tier1_higher_priority(self):
        """Tier 1 leagues should have higher priority than Tier 2 (when enabled)."""
        min_tier1 = min(get_league_priority(l) for l in TIER_1_LEAGUES)
        
        # Skip comparison if Tier 2 is disabled
        if len(TIER_2_LEAGUES) == 0:
            # Just verify Tier 1 has reasonable priority
            assert min_tier1 > 50
        else:
            max_tier2 = max(get_league_priority(l) for l in TIER_2_LEAGUES)
            assert min_tier1 > max_tier2
    
    def test_unknown_league_low_priority(self):
        """Unknown leagues should have low default priority."""
        assert get_league_priority("soccer_unknown") == 10


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_none_input(self):
        """Functions should handle None gracefully."""
        assert is_tier1_league(None) is False
        assert is_tier2_league(None) is False
        assert is_niche_league(None) is False
        assert get_league_tier(None) == "OTHER"
    
    def test_empty_string(self):
        """Functions should handle empty string."""
        assert is_tier1_league("") is False
        assert get_league_tier("") == "OTHER"
    
    def test_fallback_leagues(self):
        """Fallback should return Tier 1."""
        assert get_fallback_leagues() == TIER_1_LEAGUES


# ============================================
# TIER 2 FALLBACK SYSTEM TESTS (V4.3)
# ============================================
class TestTier2FallbackTriggerD:
    """Test Trigger D logic: alerts_sent == 0 AND (high_potential == 0 OR dry_cycles >= 2)."""
    
    def setup_method(self):
        """Reset state before each test."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        # Also reset via function
        reset_daily_tier2_stats()
    
    def test_trigger_d_no_alerts_no_high_potential(self):
        """Should activate when alerts=0 AND high_potential=0."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        # First cycle with no alerts and no high_potential
        result = lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=0)
        assert result is True, "Should activate when alerts=0 AND high_potential=0"
    
    def test_trigger_d_no_alerts_with_high_potential_first_cycle(self):
        """Should NOT activate on first dry cycle if high_potential > 0."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        # First cycle: alerts=0 but high_potential=2
        result = lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=2)
        assert result is False, "Should NOT activate on first dry cycle with high_potential"
    
    def test_trigger_d_dry_cycles_threshold(self):
        """Should activate after 2 consecutive dry cycles even with high_potential."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        # Simulate 2 dry cycles
        lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=5)  # dry_cycle=1
        result = lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=5)  # dry_cycle=2
        
        assert result is True, "Should activate after 2 dry cycles (threshold)"
    
    def test_trigger_d_reset_on_alert(self):
        """Dry cycles should reset when an alert is sent."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        # Build up dry cycles
        lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=5)  # dry=1
        
        # Alert sent - should reset
        result = lm.should_activate_tier2_fallback(alerts_sent=1, high_potential_count=0)
        assert result is False, "Should NOT activate when alerts > 0"
        
        # Verify dry cycles reset
        status = lm.get_tier2_fallback_status()
        assert status['consecutive_dry_cycles'] == 0, "Dry cycles should reset after alert"
    
    def test_with_alerts_never_activates(self):
        """Should never activate if alerts_sent > 0."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        result = lm.should_activate_tier2_fallback(alerts_sent=3, high_potential_count=0)
        assert result is False


class TestTier2FallbackRotation:
    """Test 3-league round-robin rotation."""
    
    def setup_method(self):
        """Reset state before each test."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
    
    def test_batch_size_is_3(self):
        """Each fallback batch should have exactly 3 leagues."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        batch = lm.get_tier2_fallback_batch()
        assert len(batch) == 3
        assert len(batch) == TIER2_FALLBACK_BATCH_SIZE
    
    def test_rotation_round_robin(self):
        """Batches should rotate through all 8 leagues."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        all_seen = set()
        batches = []
        
        # Get 3 batches (should cover all 8 leagues with some overlap)
        for _ in range(3):
            batch = lm.get_tier2_fallback_batch()
            batches.append(batch)
            all_seen.update(batch)
        
        # After 3 batches of 3, we should have seen all 8 leagues
        assert len(all_seen) == 8
        assert all_seen == set(TIER_2_LEAGUES)
    
    def test_batches_are_different(self):
        """Consecutive batches should be different."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        batch1 = lm.get_tier2_fallback_batch()
        batch2 = lm.get_tier2_fallback_batch()
        
        # Batches should be different (round-robin advances)
        assert batch1 != batch2
    
    def test_all_leagues_valid_tier2(self):
        """All returned leagues should be valid Tier 2 leagues."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        for _ in range(5):
            batch = lm.get_tier2_fallback_batch()
            for league in batch:
                assert league in TIER_2_LEAGUES


class TestTier2FallbackCooldown:
    """Test 3-cycle cooldown after activation."""
    
    def setup_method(self):
        """Reset state before each test."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
    
    def test_cooldown_blocks_immediate_reactivation(self):
        """Should not activate again within 3 cycles."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        # First activation
        lm.increment_cycle()
        result1 = lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=0)
        assert result1 is True
        lm.record_tier2_activation()
        
        # Immediate retry (same cycle) - should be blocked by cooldown
        lm.increment_cycle()
        result2 = lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=0)
        assert result2 is False, "Should be blocked by cooldown (1/3 cycles)"
        
        # After 2 cycles - still blocked
        lm.increment_cycle()
        result3 = lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=0)
        assert result3 is False, "Should be blocked by cooldown (2/3 cycles)"
    
    def test_cooldown_expires_after_3_cycles(self):
        """Should allow activation after 3 cycles."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        # First activation
        lm.increment_cycle()
        lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=0)
        lm.record_tier2_activation()
        
        # Wait 3 cycles
        for _ in range(3):
            lm.increment_cycle()
            # Keep dry cycles going
            lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=5)
        
        # 4th cycle - cooldown expired, should activate
        lm.increment_cycle()
        result = lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=0)
        assert result is True, "Should activate after cooldown expires"


class TestTier2FallbackDailyLimit:
    """Test max 3 activations per day."""
    
    def setup_method(self):
        """Reset state before each test."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
    
    def test_daily_limit_blocks_after_3(self):
        """Should block after 3 activations in a day."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        # Simulate 3 activations (with cooldown waits)
        for i in range(3):
            # Wait for cooldown
            for _ in range(4):
                lm.increment_cycle()
            
            result = lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=0)
            assert result is True, f"Activation {i+1} should succeed"
            lm.record_tier2_activation()
        
        # 4th attempt - should be blocked by daily limit
        for _ in range(4):
            lm.increment_cycle()
        
        result = lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=0)
        assert result is False, "Should be blocked by daily limit (3/3)"
        
        status = lm.get_tier2_fallback_status()
        assert status['activations_today'] == 3
    
    def test_daily_limit_is_3(self):
        """Daily limit should be configured as 3."""
        assert TIER2_FALLBACK_DAILY_LIMIT == 3


class TestTier2FallbackDailyReset:
    """Test daily reset of stats."""
    
    def test_reset_clears_counters(self):
        """reset_daily_tier2_stats should clear all counters."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        # Build up some state
        lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=0)
        lm.record_tier2_activation()
        
        # Reset
        lm.reset_daily_tier2_stats()
        
        status = lm.get_tier2_fallback_status()
        assert status['activations_today'] == 0
        assert status['consecutive_dry_cycles'] == 0
    
    def test_status_returns_correct_info(self):
        """get_tier2_fallback_status should return all relevant info."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        status = lm.get_tier2_fallback_status()
        
        # Check all expected keys exist
        assert 'current_cycle' in status
        assert 'consecutive_dry_cycles' in status
        assert 'activations_today' in status
        assert 'daily_limit' in status
        assert 'cooldown_remaining' in status
        assert 'last_activation_cycle' in status
        assert 'next_batch_preview' in status
        
        # Check types
        assert isinstance(status['daily_limit'], int)
        assert status['daily_limit'] == 3


class TestTier2FallbackEdgeCases:
    """Test edge cases and error handling."""
    
    def setup_method(self):
        """Reset state before each test."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
    
    def test_negative_alerts_treated_as_zero(self):
        """Negative alerts_sent should be treated safely."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        # Negative value - should not crash, treated as "no alerts"
        result = lm.should_activate_tier2_fallback(alerts_sent=-1, high_potential_count=0)
        # -1 > 0 is False, so it should proceed with dry cycle logic
        assert result is True  # No alerts, no high_potential
    
    def test_zero_high_potential_triggers(self):
        """Zero high_potential should trigger immediately."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        result = lm.should_activate_tier2_fallback(alerts_sent=0, high_potential_count=0)
        assert result is True
    
    def test_large_values_handled(self):
        """Large values should be handled without overflow."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        # Large alerts - should not activate
        result = lm.should_activate_tier2_fallback(alerts_sent=1000, high_potential_count=500)
        assert result is False
    
    def test_increment_cycle_safe(self):
        """increment_cycle should be safe to call multiple times."""
        import importlib
        import src.ingestion.league_manager as lm
        importlib.reload(lm)
        
        initial = lm.get_tier2_fallback_status()['current_cycle']
        
        for _ in range(100):
            lm.increment_cycle()
        
        final = lm.get_tier2_fallback_status()['current_cycle']
        assert final == initial + 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
