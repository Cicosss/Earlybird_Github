#!/usr/bin/env python3
"""
Stress test for FotMob API simulating real-world usage intensity.
This test simulates the actual usage pattern from the production code.
"""

import requests
import time
import random
import json
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple

# Configuration matching production code
FOTMOB_MIN_REQUEST_INTERVAL = 2.0  # seconds
FOTMOB_JITTER_MIN = 0.0
FOTMOB_JITTER_MAX = 0.5
FOTMOB_MAX_RETRIES = 3
FOTMOB_REQUEST_TIMEOUT = 15

# User agents (same as production)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.fotmob.com/",
    "Origin": "https://www.fotmob.com",
}

# Test endpoints (simulating real usage)
ENDPOINTS = [
    ("search", "https://www.fotmob.com/api/search/suggest?term={term}"),
    ("team", "https://www.fotmob.com/api/teams/{team_id}/details"),
    ("match", "https://www.fotmob.com/api/matchDetails?matchId={match_id}"),
]

# Test data
TEAMS = [
    ("Palermo", "8540"),
    ("Juventus", "2488"),
    ("Milan", "2487"),
    ("Inter", "2581"),
    ("Roma", "2580"),
    ("Napoli", "2579"),
    ("Lazio", "2578"),
    ("Fiorentina", "2577"),
]

MATCHES = [
    "4193741",
    "4906263",
    "4906252",
]


class StressTestStats:
    """Track statistics during stress test."""

    def __init__(self):
        self.requests = 0
        self.successes = 0
        self.failures = 0
        self.status_codes = defaultdict(int)
        self.errors = defaultdict(int)
        self.start_time = None
        self.end_time = None
        self.timeline = []

    def record_request(self, url: str, status_code: int, success: bool, error: str = None):
        """Record a request result."""
        self.requests += 1
        self.status_codes[status_code] += 1

        if success:
            self.successes += 1
        else:
            self.failures += 1
            if error:
                self.errors[error] += 1

        self.timeline.append(
            {
                "request_num": self.requests,
                "url": url,
                "status_code": status_code,
                "success": success,
                "error": error,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def print_summary(self):
        """Print test summary."""
        duration = (
            (self.end_time - self.start_time).total_seconds()
            if self.end_time and self.start_time
            else 0
        )

        print("\n" + "=" * 60)
        print("STRESS TEST SUMMARY")
        print("=" * 60)
        print(f"Total Requests: {self.requests}")
        print(f"Successes: {self.successes} ({self.successes / self.requests * 100:.1f}%)")
        print(f"Failures: {self.failures} ({self.failures / self.requests * 100:.1f}%)")
        print(f"Duration: {duration:.1f}s")
        print(f"Requests/sec: {self.requests / duration:.2f}")
        print("\nStatus Codes:")
        for code, count in sorted(self.status_codes.items()):
            print(f"  {code}: {count} ({count / self.requests * 100:.1f}%)")

        if self.errors:
            print("\nErrors:")
            for error, count in sorted(self.errors.items(), key=lambda x: x[1], reverse=True):
                print(f"  {error}: {count}")

        print("\nTimeline (first 10 and last 10):")
        for entry in self.timeline[:10]:
            print(f"  #{entry['request_num']:3d}: {entry['status_code']} - {entry['url'][:50]}")
        if len(self.timeline) > 20:
            print("  ...")
            for entry in self.timeline[-10:]:
                print(f"  #{entry['request_num']:3d}: {entry['status_code']} - {entry['url'][:50]}")


def make_fotmob_request(url: str, stats: StressTestStats) -> bool:
    """Make a request to FotMob API with production-like behavior."""
    headers = BASE_HEADERS.copy()
    headers["User-Agent"] = random.choice(USER_AGENTS)

    for attempt in range(FOTMOB_MAX_RETRIES):
        try:
            # Rate limiting with jitter (same as production)
            if stats.requests > 0:
                jitter = random.uniform(FOTMOB_JITTER_MIN, FOTMOB_JITTER_MAX)
                required_interval = FOTMOB_MIN_REQUEST_INTERVAL + max(0, jitter)
                time.sleep(required_interval)

            resp = requests.get(url, headers=headers, timeout=FOTMOB_REQUEST_TIMEOUT)

            if resp.status_code == 200:
                stats.record_request(url, resp.status_code, True)
                return True

            if resp.status_code == 403:
                if attempt < FOTMOB_MAX_RETRIES - 1:
                    delay = 5 ** (attempt + 1)
                    print(
                        f"⚠️  Request #{stats.requests + 1}: 403 - retrying in {delay}s ({attempt + 1}/{FOTMOB_MAX_RETRIES})"
                    )
                    time.sleep(delay)
                    continue
                stats.record_request(url, resp.status_code, False, "403 Forbidden")
                print(f"❌ Request #{stats.requests + 1}: 403 Forbidden (max retries reached)")
                return False

            if resp.status_code == 429:
                delay = 3 ** (attempt + 1)
                print(f"⚠️  Request #{stats.requests + 1}: 429 Rate Limit - waiting {delay}s...")
                time.sleep(delay)
                continue

            stats.record_request(url, resp.status_code, False, f"HTTP {resp.status_code}")
            print(f"❌ Request #{stats.requests + 1}: HTTP {resp.status_code}")
            return False

        except requests.exceptions.Timeout:
            delay = 2 ** (attempt + 1)
            print(f"⚠️  Request #{stats.requests + 1}: Timeout - retrying in {delay}s")
            time.sleep(delay)

        except requests.exceptions.ConnectionError as e:
            delay = 2 ** (attempt + 1)
            print(f"⚠️  Request #{stats.requests + 1}: Connection Error - retrying in {delay}s")
            time.sleep(delay)

        except Exception as e:
            stats.record_request(url, 0, False, str(e))
            print(f"❌ Request #{stats.requests + 1}: {e}")
            return False

    stats.record_request(url, 0, False, "Max retries exceeded")
    return False


def run_stress_test(num_requests: int = 50):
    """Run stress test with specified number of requests."""
    stats = StressTestStats()
    stats.start_time = datetime.now()

    print("=" * 60)
    print("FOTMOB STRESS TEST")
    print("=" * 60)
    print(f"Target requests: {num_requests}")
    print(f"Request interval: {FOTMOB_MIN_REQUEST_INTERVAL}s (±{FOTMOB_JITTER_MAX}s)")
    print(f"Max retries: {FOTMOB_MAX_RETRIES}")
    print(f"Start time: {stats.start_time.isoformat()}")
    print()

    request_count = 0
    while request_count < num_requests:
        # Rotate through different endpoints and data
        endpoint_type, url_template = ENDPOINTS[request_count % len(ENDPOINTS)]

        if endpoint_type == "search":
            team_name, _ = TEAMS[request_count % len(TEAMS)]
            url = url_template.format(term=team_name)
        elif endpoint_type == "team":
            _, team_id = TEAMS[request_count % len(TEAMS)]
            url = url_template.format(team_id=team_id)
        elif endpoint_type == "match":
            match_id = MATCHES[request_count % len(MATCHES)]
            url = url_template.format(match_id=match_id)

        print(f"Request #{request_count + 1}/{num_requests}: {endpoint_type} - {url[:60]}...")

        success = make_fotmob_request(url, stats)

        if not success and stats.errors.get("403 Forbidden", 0) >= 3:
            print("\n" + "=" * 60)
            print("⚠️  ABORTING: Multiple 403 errors detected")
            print("=" * 60)
            break

        request_count += 1

    stats.end_time = datetime.now()
    stats.print_summary()

    # Check if we should recommend action
    if stats.errors.get("403 Forbidden", 0) > 0:
        print("\n" + "=" * 60)
        print("⚠️  RECOMMENDATION: 403 errors detected")
        print("=" * 60)
        print("FotMob is blocking requests. Consider:")
        print("1. Increasing request interval (e.g., 3-5s)")
        print("2. Using proxy rotation")
        print("3. Implementing Playwright with stealth")
        print("4. Testing Ruby fotmob gem as alternative")
    else:
        print("\n" + "=" * 60)
        print("✅ SUCCESS: No 403 errors detected")
        print("=" * 60)
        print("FotMob API is working with current rate limiting.")

    return stats


def main():
    """Main entry point."""
    import sys

    # Default: 50 requests (takes ~100 seconds at 2s interval)
    # Can be overridden with command line argument
    num_requests = int(sys.argv[1]) if len(sys.argv) > 1 else 50

    print(f"Starting stress test with {num_requests} requests...")
    print(f"Estimated duration: ~{num_requests * FOTMOB_MIN_REQUEST_INTERVAL:.0f} seconds")
    print()

    stats = run_stress_test(num_requests)

    # Save timeline to file for analysis
    with open("fotmob_stress_test_timeline.json", "w") as f:
        json.dump(stats.timeline, f, indent=2)

    print(f"\nTimeline saved to: fotmob_stress_test_timeline.json")

    # Exit with error code if 403 errors detected
    if stats.errors.get("403 Forbidden", 0) > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
