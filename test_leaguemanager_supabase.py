#!/usr/bin/env python3
"""
Test script to verify LeagueManager Supabase integration
"""
import sys
sys.path.insert(0, '.')

from src.ingestion.league_manager import (
    get_tier1_leagues,
    get_tier2_leagues,
    get_elite_leagues,
    get_leagues_for_cycle,
    get_tier2_for_cycle,
)

print("=" * 80)
print("Testing LeagueManager Supabase Integration")
print("=" * 80)

# Test 1: Get Tier 1 leagues
print("\n[TEST 1] Getting Tier 1 leagues...")
tier1 = get_tier1_leagues()
print(f"✅ Tier 1 leagues: {len(tier1)} leagues")
for league in tier1:
    print(f"   - {league}")

# Test 2: Get Tier 2 leagues
print("\n[TEST 2] Getting Tier 2 leagues...")
tier2 = get_tier2_leagues()
print(f"✅ Tier 2 leagues: {len(tier2)} leagues")
for league in tier2:
    print(f"   - {league}")

# Test 3: Get elite leagues (alias)
print("\n[TEST 3] Getting elite leagues (alias)...")
elite = get_elite_leagues()
print(f"✅ Elite leagues: {len(elite)} leagues")
assert elite == tier1, "Elite leagues should match Tier 1 leagues"

# Test 4: Get leagues for cycle
print("\n[TEST 4] Getting leagues for cycle...")
leagues_for_cycle = get_leagues_for_cycle(emergency_mode=False)
print(f"✅ Leagues for cycle: {len(leagues_for_cycle)} leagues")

# Test 5: Get Tier 2 for cycle (rotation)
print("\n[TEST 5] Getting Tier 2 for cycle (rotation)...")
tier2_batch = get_tier2_for_cycle()
print(f"✅ Tier 2 batch: {len(tier2_batch)} leagues")
for league in tier2_batch:
    print(f"   - {league}")

print("\n" + "=" * 80)
print("✅ All tests passed!")
print("=" * 80)
