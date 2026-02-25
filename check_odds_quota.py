#!/usr/bin/env python3
"""Check Odds API quota for both keys"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

# Test both keys with detailed quota info
keys = [("Key 1", os.getenv("ODDS_API_KEY_1")), ("Key 2", os.getenv("ODDS_API_KEY_2"))]

for name, key in keys:
    print(f"\n{name}: {key[:8]}...{key[-4:]}")
    url = "https://api.the-odds-api.com/v4/sports"
    params = {"apiKey": key}
    response = requests.get(url, params=params, timeout=10)

    print(f"Status: {response.status_code}")
    print("Quota Headers:")
    print(f"  x-requests-used: {response.headers.get('x-requests-used', 'N/A')}")
    print(f"  x-requests-remaining: {response.headers.get('x-requests-remaining', 'N/A')}")
    print(f"  x-requests-limit: {response.headers.get('x-requests-limit', 'N/A')}")
