#!/usr/bin/env python3
"""Quick test of FotMob API with Python requests."""

import requests
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.fotmob.com/",
}

print("Testing FotMob API with Python requests...")
print("=" * 60)

# Test 1: Search
print("\n1. Testing /search/suggest?term=Palermo")
resp = requests.get("https://www.fotmob.com/api/search/suggest?term=Palermo", headers=headers, timeout=10)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    teams = [s for group in data for s in group.get("suggestions", []) if s.get("type") == "team"]
    print(f"✅ Found {len(teams)} teams")
    if teams:
        print(f"   First: {teams[0].get('name')} (ID: {teams[0].get('id')})")
else:
    print(f"❌ Failed: {resp.text[:200]}")

# Test 2: Team details
print("\n2. Testing /teams/8540/details")
resp = requests.get("https://www.fotmob.com/api/teams/8540/details", headers=headers, timeout=10)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    team_name = data.get("details", {}).get("name", "Unknown")
    print(f"✅ Team name: {team_name}")
else:
    print(f"❌ Failed: {resp.text[:200]}")

print("\n" + "=" * 60)
print("Test completed!")
