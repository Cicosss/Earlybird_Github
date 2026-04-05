#!/usr/bin/env python3
"""
Stress test for FotMob API - writes to file instead of stdout
Simulates real-world usage intensity from production code.
"""

import requests
import time
import random
import json
from datetime import datetime
from collections import defaultdict

# Configuration
FOTMOB_MIN_REQUEST_INTERVAL = 2.0
FOTMOB_JITTER_MIN = 0.0
FOTMOB_JITTER_MAX = 0.5
FOTMOB_MAX_RETRIES = 3
FOTMOB_REQUEST_TIMEOUT = 15

# User agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.fotmob.com/",
    "Origin": "https://www.fotmob.com",
}

# Test data
TEAMS = [
    ("Palermo", "8540"),
    ("Juventus", "2488"),
    ("Milan", "2487"),
    ("Inter", "2581"),
    ("Roma", "2580"),
    ("Napoli", "2579"),
    ("Lazio", "2578"),
]


class StressTestStats:
    def __init__(self):
        self.requests = 0
        self.successes = 0
        self.failures = 0
        self.status_codes = defaultdict(int)
        self.errors = defaultdict(int)
        self.start_time = None
        self.end_time = None
        self.timeline = []

    def record_request(self, url, status_code, success, error=None):
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


def make_fotmob_request(url, stats, log_file):
    headers = BASE_HEADERS.copy()
    headers["User-Agent"] = random.choice(USER_AGENTS)

    for attempt in range(FOTMOB_MAX_RETRIES):
        try:
            if stats.requests > 0:
                jitter = random.uniform(FOTMOB_JITTER_MIN, FOTMOB_JITTER_MAX)
                required_interval = FOTMOB_MIN_REQUEST_INTERVAL + max(0, jitter)
                time.sleep(required_interval)

            resp = requests.get(url, headers=headers, timeout=FOTMOB_REQUEST_TIMEOUT)

            if resp.status_code == 200:
                stats.record_request(url, resp.status_code, True)
                log_file.write(f"✅ Request #{stats.requests}: 200 OK - {url[:60]}...\n")
                log_file.flush()
                return True

            if resp.status_code == 403:
                if attempt < FOTMOB_MAX_RETRIES - 1:
                    delay = 5 ** (attempt + 1)
                    log_file.write(
                        f"⚠️  Request #{stats.requests + 1}: 403 - retrying in {delay}s ({attempt + 1}/{FOTMOB_MAX_RETRIES})\n"
                    )
                    log_file.flush()
                    time.sleep(delay)
                    continue
                stats.record_request(url, resp.status_code, False, "403 Forbidden")
                log_file.write(
                    f"❌ Request #{stats.requests + 1}: 403 Forbidden (max retries reached)\n"
                )
                log_file.flush()
                return False

            if resp.status_code == 429:
                delay = 3 ** (attempt + 1)
                log_file.write(
                    f"⚠️  Request #{stats.requests + 1}: 429 Rate Limit - waiting {delay}s...\n"
                )
                log_file.flush()
                time.sleep(delay)
                continue

            stats.record_request(url, resp.status_code, False, f"HTTP {resp.status_code}")
            log_file.write(f"❌ Request #{stats.requests + 1}: HTTP {resp.status_code}\n")
            log_file.flush()
            return False

        except requests.exceptions.Timeout:
            delay = 2 ** (attempt + 1)
            log_file.write(f"⚠️  Request #{stats.requests + 1}: Timeout - retrying in {delay}s\n")
            log_file.flush()
            time.sleep(delay)

        except Exception as e:
            stats.record_request(url, 0, False, str(e))
            log_file.write(f"❌ Request #{stats.requests + 1}: {e}\n")
            log_file.flush()
            return False

    stats.record_request(url, 0, False, "Max retries exceeded")
    return False


def run_stress_test(num_requests, log_file):
    stats = StressTestStats()
    stats.start_time = datetime.now()

    log_file.write("=" * 60 + "\n")
    log_file.write("FOTMOB STRESS TEST\n")
    log_file.write("=" * 60 + "\n")
    log_file.write(f"Target requests: {num_requests}\n")
    log_file.write(f"Request interval: {FOTMOB_MIN_REQUEST_INTERVAL}s (±{FOTMOB_JITTER_MAX}s)\n")
    log_file.write(f"Start time: {stats.start_time.isoformat()}\n\n")
    log_file.flush()

    request_count = 0
    while request_count < num_requests:
        team_name, team_id = TEAMS[request_count % len(TEAMS)]
        url = f"https://www.fotmob.com/api/teams/{team_id}/details"

        log_file.write(
            f"Request #{request_count + 1}/{num_requests}: team - {team_name} (ID: {team_id})\n"
        )
        log_file.flush()

        success = make_fotmob_request(url, stats, log_file)

        if not success and stats.errors.get("403 Forbidden", 0) >= 3:
            log_file.write("\n" + "=" * 60 + "\n")
            log_file.write("⚠️  ABORTING: Multiple 403 errors detected\n")
            log_file.write("=" * 60 + "\n")
            log_file.flush()
            break

        request_count += 1

    stats.end_time = datetime.now()

    # Print summary
    duration = (stats.end_time - stats.start_time).total_seconds()

    log_file.write("\n" + "=" * 60 + "\n")
    log_file.write("STRESS TEST SUMMARY\n")
    log_file.write("=" * 60 + "\n")
    log_file.write(f"Total Requests: {stats.requests}\n")
    log_file.write(
        f"Successes: {stats.successes} ({stats.successes / stats.requests * 100:.1f}%)\n"
    )
    log_file.write(f"Failures: {stats.failures} ({stats.failures / stats.requests * 100:.1f}%)\n")
    log_file.write(f"Duration: {duration:.1f}s\n")
    log_file.write(f"Requests/sec: {stats.requests / duration:.2f}\n\n")
    log_file.write("Status Codes:\n")
    for code, count in sorted(stats.status_codes.items()):
        log_file.write(f"  {code}: {count} ({count / stats.requests * 100:.1f}%)\n")

    if stats.errors:
        log_file.write("\nErrors:\n")
        for error, count in sorted(stats.errors.items(), key=lambda x: x[1], reverse=True):
            log_file.write(f"  {error}: {count}\n")

    if stats.errors.get("403 Forbidden", 0) > 0:
        log_file.write("\n" + "=" * 60 + "\n")
        log_file.write("⚠️  RECOMMENDATION: 403 errors detected\n")
        log_file.write("=" * 60 + "\n")
        log_file.write("FotMob is blocking requests.\n")
    else:
        log_file.write("\n" + "=" * 60 + "\n")
        log_file.write("✅ SUCCESS: No 403 errors detected\n")
        log_file.write("=" * 60 + "\n")
        log_file.write("FotMob API is working with current rate limiting.\n")

    log_file.flush()

    # Save timeline
    with open("fotmob_stress_test_timeline.json", "w") as f:
        json.dump(stats.timeline, f, indent=2)

    log_file.write(f"\nTimeline saved to: fotmob_stress_test_timeline.json\n")
    log_file.flush()

    return stats


def main():
    import sys

    num_requests = int(sys.argv[1]) if len(sys.argv) > 1 else 20

    with open("/tmp/fotmob_stress_test.log", "w") as log_file:
        stats = run_stress_test(num_requests, log_file)

    # Print summary to stdout at the end
    with open("/tmp/fotmob_stress_test.log", "r") as f:
        print(f.read())

    # Exit with error code if 403 errors detected
    if stats.errors.get("403 Forbidden", 0) > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
