#!/usr/bin/env python3
import sys

import requests

sys.stdout = open("/tmp/fotmob_simple.log", "w")
sys.stderr = sys.stdout

print("Starting simple test...")

try:
    resp = requests.get("https://www.fotmob.com/api/search/suggest?term=Palermo", timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Length: {len(resp.text)}")
    print("Test completed!")
except Exception as e:
    print(f"Error: {e}")

sys.stdout.close()
