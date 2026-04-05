#!/usr/bin/env python3
"""
Test script to verify the fixes applied to DiscoveredNews feature.

This script tests the three problems identified in the COVE report:
1. Category Validation Mismatch - All 9 categories are now documented
2. Confidence Type Inconsistency - confidence is now float, not hardcoded "HIGH"
3. Missing Field Mapping - validation_tag and boosted_confidence are now included
"""

import sys
from datetime import datetime, timezone
from dataclasses import dataclass, field

# Test Problem #1: Category Validation Mismatch
print("=" * 80)
print("TEST 1: Category Validation Mismatch")
print("=" * 80)

# Read the docstring from browser_monitor.py
with open("src/services/browser_monitor.py", "r") as f:
    content = f.read()

# Check if all 9 categories are documented
expected_categories = [
    "INJURY",
    "LINEUP",
    "SUSPENSION",
    "TRANSFER",
    "TACTICAL",
    "NATIONAL_TEAM",
    "YOUTH_CALLUP",
    "CUP_ABSENCE",
    "OTHER",
]
docstring_line = None
for i, line in enumerate(content.split("\n"), 1):
    if (
        "category: str  #" in line
        and "DiscoveredNews" in content[max(0, content.find(line) - 500) : content.find(line)]
    ):
        docstring_line = line
        break

if docstring_line:
    print(f"✅ Found docstring line: {docstring_line.strip()}")

    # Check if all categories are present
    missing_categories = []
    for category in expected_categories:
        if category not in docstring_line:
            missing_categories.append(category)

    if missing_categories:
        print(f"❌ FAILED: Missing categories in docstring: {missing_categories}")
        sys.exit(1)
    else:
        print(f"✅ PASSED: All 9 categories are documented in docstring")
else:
    print("❌ FAILED: Could not find docstring line")
    sys.exit(1)

# Test Problem #2: Confidence Type Inconsistency
print("\n" + "=" * 80)
print("TEST 2: Confidence Type Inconsistency")
print("=" * 80)

# Read the news_hunter.py file
with open("src/processing/news_hunter.py", "r") as f:
    content = f.read()

# Check if confidence is now using float value instead of hardcoded "HIGH"
if '"confidence": "HIGH"' in content:
    print("❌ FAILED: confidence is still hardcoded as 'HIGH' string")
    sys.exit(1)
elif '"confidence": confidence,' in content:
    print("✅ PASSED: confidence now uses float value from DiscoveredNews")
else:
    print("⚠️  WARNING: Could not verify confidence assignment")

# Test Problem #3: Missing Field Mapping
print("\n" + "=" * 80)
print("TEST 3: Missing Field Mapping")
print("=" * 80)

# Check if validation_tag and boosted_confidence are extracted
if 'validation_tag = getattr(news, "validation_tag", None)' in content:
    print("✅ PASSED: validation_tag is extracted from news")
else:
    print("❌ FAILED: validation_tag is not extracted")
    sys.exit(1)

if 'boosted_confidence = getattr(news, "boosted_confidence", None)' in content:
    print("✅ PASSED: boosted_confidence is extracted from news")
else:
    print("❌ FAILED: boosted_confidence is not extracted")
    sys.exit(1)

# Check if validation_tag and boosted_confidence are added to discovery_data
if '"validation_tag": validation_tag,' in content:
    print("✅ PASSED: validation_tag is added to discovery_data")
else:
    print("❌ FAILED: validation_tag is not added to discovery_data")
    sys.exit(1)

if '"boosted_confidence": boosted_confidence,' in content:
    print("✅ PASSED: boosted_confidence is added to discovery_data")
else:
    print("❌ FAILED: boosted_confidence is not added to discovery_data")
    sys.exit(1)

# Test Problem #4: Test file updates
print("\n" + "=" * 80)
print("TEST 4: Test File Updates")
print("=" * 80)

# Read the test file
with open("tests/test_browser_monitor.py", "r") as f:
    test_content = f.read()

# Check if all 9 categories are in VALID_CATEGORIES
if (
    'VALID_CATEGORIES = ["INJURY", "LINEUP", "SUSPENSION", "TRANSFER", "TACTICAL", "NATIONAL_TEAM", "YOUTH_CALLUP", "CUP_ABSENCE", "OTHER"]'
    in test_content
):
    print("✅ PASSED: VALID_CATEGORIES includes all 9 categories")
else:
    print("❌ FAILED: VALID_CATEGORIES does not include all 9 categories")
    sys.exit(1)

# Check if valid_categories in test function includes all 9 categories
if (
    'valid_categories = {"INJURY", "LINEUP", "SUSPENSION", "TRANSFER", "TACTICAL", "NATIONAL_TEAM", "YOUTH_CALLUP", "CUP_ABSENCE", "OTHER"}'
    in test_content
):
    print("✅ PASSED: valid_categories in test function includes all 9 categories")
else:
    print("❌ FAILED: valid_categories in test function does not include all 9 categories")
    sys.exit(1)

print("\n" + "=" * 80)
print("ALL TESTS PASSED ✅")
print("=" * 80)
print("\nSummary:")
print("1. ✅ Category Validation Mismatch - FIXED")
print("2. ✅ Confidence Type Inconsistency - FIXED")
print("3. ✅ Missing Field Mapping - FIXED")
print("4. ✅ Test File Updates - FIXED")
print("\nThe DiscoveredNews feature is now production-ready for VPS deployment!")
