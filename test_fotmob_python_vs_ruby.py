#!/usr/bin/env python3
"""
Test comparativo tra Python requests e Ruby fotmob gem per FotMob API.
Questo script verifica se il problema 403 persiste.
"""

import requests
import json
import time
import random
from datetime import datetime

# User agents da rotare (stessi usati nel codice Python attuale)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

BASE_URL = "https://www.fotmob.com/api"

BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.fotmob.com/",
    "Origin": "https://www.fotmob.com",
}


def make_fotmob_request(url, attempt=1, max_attempts=3):
    """Simula il metodo _make_request del codice Python attuale."""
    for attempt in range(max_attempts):
        # Rotazione User-Agent
        headers = BASE_HEADERS.copy()
        headers["User-Agent"] = random.choice(USER_AGENTS)

        # Rate limiting (simulato)
        time.sleep(2.0 + random.uniform(0, 0.5))

        try:
            resp = requests.get(url, headers=headers, timeout=10)

            if resp.status_code == 200:
                return resp, True

            if resp.status_code == 403:
                if attempt < max_attempts - 1:
                    delay = 5 ** (attempt + 1)
                    print(f"⚠️  FotMob 403 - retrying in {delay}s ({attempt + 1}/{max_attempts})")
                    time.sleep(delay)
                    continue
                return resp, False

            if resp.status_code == 429:
                delay = 3 ** (attempt + 1)
                print(f"⚠️  FotMob rate limit (429). Waiting {delay}s...")
                time.sleep(delay)
                continue

            return resp, False

        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(2 ** (attempt + 1))

    return None, False


def test_search_endpoint():
    """Test dell'endpoint /search/suggest."""
    print("=" * 60)
    print("TEST 1: Python requests - /search/suggest")
    print("=" * 60)

    team_name = "Palermo"
    url = f"{BASE_URL}/search/suggest?term={team_name}"

    print(f"Testing: {url}")
    print(f"Time: {datetime.now().isoformat()}")

    resp, success = make_fotmob_request(url)

    if success and resp:
        print(f"✅ SUCCESS: Status {resp.status_code}")
        data = resp.json()
        teams = [
            s for group in data for s in group.get("suggestions", []) if s.get("type") == "team"
        ]
        print(f"Found {len(teams)} teams")
        if teams:
            print(f"First team: {teams[0].get('name')} (ID: {teams[0].get('id')})")
    elif resp:
        print(f"❌ FAILED: Status {resp.status_code}")
        print(f"Response preview: {resp.text[:200]}")
    else:
        print(f"❌ FAILED: No response")

    return success


def test_team_endpoint(team_id):
    """Test dell'endpoint /teams/{id}/details."""
    print("\n" + "=" * 60)
    print("TEST 2: Python requests - /teams/{id}/details")
    print("=" * 60)

    url = f"{BASE_URL}/teams/{team_id}/details"

    print(f"Testing: {url}")
    print(f"Time: {datetime.now().isoformat()}")

    resp, success = make_fotmob_request(url)

    if success and resp:
        print(f"✅ SUCCESS: Status {resp.status_code}")
        data = resp.json()
        team_name = data.get("details", {}).get("name", "Unknown")
        print(f"Team name: {team_name}")
    elif resp:
        print(f"❌ FAILED: Status {resp.status_code}")
        print(f"Response preview: {resp.text[:200]}")
    else:
        print(f"❌ FAILED: No response")

    return success


def test_match_endpoint():
    """Test dell'endpoint /matches."""
    print("\n" + "=" * 60)
    print("TEST 3: Python requests - /matches")
    print("=" * 60)

    date = "20260302"
    url = f"{BASE_URL}/matches?date={date}"

    print(f"Testing: {url}")
    print(f"Time: {datetime.now().isoformat()}")

    resp, success = make_fotmob_request(url)

    if success and resp:
        print(f"✅ SUCCESS: Status {resp.status_code}")
        data = resp.json()
        leagues = data.get("leagues", [])
        print(f"Found {len(leagues)} leagues")
    elif resp:
        print(f"❌ FAILED: Status {resp.status_code}")
        print(f"Response preview: {resp.text[:200]}")
    else:
        print(f"❌ FAILED: No response")

    return success


def main():
    """Main entry point."""
    print("=" * 60)
    print("FOTMOB PYTHON VS RUBY COMPARATIVE TEST")
    print("=" * 60)
    print(f"Test started at: {datetime.now().isoformat()}")
    print()

    results = []

    # Test 1: Search endpoint
    results.append(("Search endpoint", test_search_endpoint()))

    # Test 2: Team endpoint (usando ID Palermo 8540)
    results.append(("Team endpoint", test_team_endpoint(8540)))

    # Test 3: Matches endpoint
    results.append(("Matches endpoint", test_match_endpoint()))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")

    total = len(results)
    passed = sum(1 for _, success in results if success)

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! FotMob API is working with Python requests.")
        print("The 403 issue appears to be resolved or was temporary.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. The 403 issue may still exist.")


if __name__ == "__main__":
    main()
