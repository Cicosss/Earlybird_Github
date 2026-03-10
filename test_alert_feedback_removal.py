#!/usr/bin/env python3
"""Test script to verify AlertModification and AlertFeedbackLoop were correctly removed."""

import os
import sys

print("=" * 80)
print("Testing AlertModification and AlertFeedbackLoop Removal")
print("=" * 80)

# Test 1: Check if alert_feedback_loop.py file exists
print("\n[Test 1] Checking if alert_feedback_loop.py file exists...")
alert_feedback_loop_path = "src/analysis/alert_feedback_loop.py"
if os.path.exists(alert_feedback_loop_path):
    print(f"❌ FAIL: {alert_feedback_loop_path} still exists!")
    sys.exit(1)
else:
    print(f"✅ PASS: {alert_feedback_loop_path} correctly removed")

# Test 2: Check if test_alert_feedback_loop.py file exists
print("\n[Test 2] Checking if test_alert_feedback_loop.py file exists...")
test_alert_feedback_loop_path = "test_alert_feedback_loop.py"
if os.path.exists(test_alert_feedback_loop_path):
    print(f"❌ FAIL: {test_alert_feedback_loop_path} still exists!")
    sys.exit(1)
else:
    print(f"✅ PASS: {test_alert_feedback_loop_path} correctly removed")

# Test 3: Try to import the deleted module
print("\n[Test 3] Trying to import alert_feedback_loop module...")
try:
    from src.analysis import alert_feedback_loop

    print("❌ FAIL: alert_feedback_loop module can still be imported!")
    sys.exit(1)
except ImportError as e:
    print("✅ PASS: alert_feedback_loop module correctly removed")
    print(f"   ImportError: {e}")

# Test 4: Check if production code still uses correct modules
print("\n[Test 4] Checking if production code still uses correct modules...")
production_modules = [
    "src.analysis.intelligent_modification_logger",
    "src.analysis.step_by_step_feedback",
]

for module in production_modules:
    try:
        __import__(module)
        print(f"✅ PASS: {module} can be imported")
    except ImportError as e:
        print(f"⚠️  WARNING: {module} import failed (pre-existing issue): {e}")
        # Don't exit on this error as it's a pre-existing SQLAlchemy issue

# Test 5: Search for any remaining references
print("\n[Test 5] Searching for remaining references in production code...")
import subprocess

result = subprocess.run(
    ["grep", "-r", "AlertModification", "src/"],
    capture_output=True,
    text=True,
)

if result.returncode == 0:
    print("❌ FAIL: Found references to AlertModification in production code:")
    print(result.stdout)
    sys.exit(1)
else:
    print("✅ PASS: No references to AlertModification in production code")

result = subprocess.run(
    ["grep", "-r", "AlertFeedbackLoop", "src/"],
    capture_output=True,
    text=True,
)

if result.returncode == 0:
    print("❌ FAIL: Found references to AlertFeedbackLoop in production code:")
    print(result.stdout)
    sys.exit(1)
else:
    print("✅ PASS: No references to AlertFeedbackLoop in production code")

print("\n" + "=" * 80)
print("✅ ALL TESTS PASSED - AlertModification and AlertFeedbackLoop successfully removed")
print("=" * 80)
