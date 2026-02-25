#!/usr/bin/env python3
"""Check Scrapling Response object structure."""

from scrapling.engines.toolbelt.custom import Response

print("All Response attributes:")
for a in dir(Response):
    if not a.startswith('__'):
        print(f"  {a}")

print("\n\nChecking for status-related attributes:")
print(f"  Has 'status': {hasattr(Response, 'status')}")
print(f"  Has 'status_code': {hasattr(Response, 'status_code')}")
print(f"  Has 'ok': {hasattr(Response, 'ok')}")
print(f"  Has 'successful': {hasattr(Response, 'successful')}")
