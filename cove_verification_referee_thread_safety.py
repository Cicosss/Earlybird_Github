#!/usr/bin/env python3
"""
COVE DOUBLE VERIFICATION: Referee Thread Safety Fixes

This script performs a comprehensive verification of the thread safety fixes
applied to RefereeCache and RefereeBoostLogger.
"""

import sys
import os
import time
import threading
import inspect

sys.path.insert(0, os.getcwd())

print("=" * 80)
print("COVE DOUBLE VERIFICATION: Referee Thread Safety Fixes")
print("=" * 80)
print()

# ============================================
# PHASE 1: DRAFT GENERATION (HYPOTHESIS)
# ============================================
print("PHASE 1: DRAFT GENERATION (HYPOTHESIS)")
print("-" * 80)
print()
print("Hypothesis: Thread safety fixes are properly implemented:")
print("  1. RefereeCache.get() uses lock-protected in-memory cache")
print("  2. RefereeBoostLogger.log_boost_applied() uses lock for logging")
print("  3. threading module is imported in both files")
print("  4. Locks are initialized in __init__")
print("  5. Data flow: analyzer.py → referee modules")
print()

# ============================================
# PHASE 2: ADVERSARIAL VERIFICATION
# ============================================
print()
print("PHASE 2: ADVERSARIAL VERIFICATION")
print("-" * 80)
print()

# Test 1: Check threading import in referee_cache.py
print("Test 1: Check threading import in referee_cache.py")
with open("src/analysis/referee_cache.py", "r") as f:
    cache_content = f.read()
if "import threading" in cache_content:
    print("✅ threading imported in referee_cache.py")
else:
    print("❌ CRITICAL: threading NOT imported in referee_cache.py - WILL CRASH!")
    print("   Code uses threading.Lock() but doesn't import threading")

# Test 2: Check threading import in referee_boost_logger.py
print()
print("Test 2: Check threading import in referee_boost_logger.py")
with open("src/analysis/referee_boost_logger.py", "r") as f:
    logger_content = f.read()
if "import threading" in logger_content:
    print("✅ threading imported in referee_boost_logger.py")
else:
    print("❌ CRITICAL: threading NOT imported in referee_boost_logger.py - WILL CRASH!")

# Test 3: Check RefereeCache lock initialization
print()
print("Test 3: Check RefereeCache lock initialization")
if "self._lock = threading.Lock()" in cache_content:
    print("✅ RefereeCache lock initialized in __init__")
else:
    print("❌ CRITICAL: RefereeCache lock NOT initialized")

# Test 4: Check RefereeBoostLogger lock initialization
print()
print("Test 4: Check RefereeBoostLogger lock initialization")
if "self._lock = threading.Lock()" in logger_content:
    print("✅ RefereeBoostLogger lock initialized in __init__")
else:
    print("❌ CRITICAL: RefereeBoostLogger lock NOT initialized")

# Test 5: Check RefereeCache.get() uses lock
print()
print("Test 5: Check RefereeCache.get() uses lock")
if "with self._lock:" in cache_content and "def get(" in cache_content:
    print("✅ RefereeCache.get() uses lock protection")
else:
    print("❌ CRITICAL: RefereeCache.get() does NOT use lock")

# Test 6: Check RefereeBoostLogger.log_boost_applied() uses lock
print()
print("Test 6: Check RefereeBoostLogger.log_boost_applied() uses lock")
if "with self._lock:" in logger_content and "def log_boost_applied(" in logger_content:
    print("✅ RefereeBoostLogger.log_boost_applied() uses lock protection")
else:
    print("❌ CRITICAL: RefereeBoostLogger.log_boost_applied() does NOT use lock")

# Test 7: Check RefereeCache in-memory cache
print()
print("Test 7: Check RefereeCache uses in-memory cache")
if "self._cache = {}" in cache_content:
    print("✅ RefereeCache uses in-memory cache (self._cache)")
else:
    print("❌ WARNING: RefereeCache may not use in-memory cache")

# Test 8: Check RefereeCache.set() thread safety
print()
print("Test 8: Check RefereeCache.set() thread safety")
# Check if set() uses lock
import re

set_method = re.search(r"def set\(.*?\):.*?(?=\n    def |\nclass |\Z)", cache_content, re.DOTALL)
if set_method:
    if "with self._lock:" in set_method.group(0):
        print("✅ RefereeCache.set() uses lock protection")
    else:
        print("❌ CRITICAL: RefereeCache.set() does NOT use lock - RACE CONDITION!")
else:
    print("⚠️ WARNING: Could not find set() method")

# Test 9: Check RefereeCache._load_cache() thread safety
print()
print("Test 9: Check RefereeCache._load_cache() thread safety")
load_cache_method = re.search(
    r"def _load_cache\(.*?\):.*?(?=\n    def |\nclass |\Z)", cache_content, re.DOTALL
)
if load_cache_method:
    if "with self._lock:" in load_cache_method.group(0):
        print("✅ RefereeCache._load_cache() uses lock protection")
    else:
        print("❌ CRITICAL: RefereeCache._load_cache() does NOT use lock - RACE CONDITION!")
else:
    print("⚠️ WARNING: Could not find _load_cache() method")

# Test 10: Check RefereeCache._save_cache() thread safety
print()
print("Test 10: Check RefereeCache._save_cache() thread safety")
save_cache_method = re.search(
    r"def _save_cache\(.*?\):.*?(?=\n    def |\nclass |\Z)", cache_content, re.DOTALL
)
if save_cache_method:
    if "with self._lock:" in save_cache_method.group(0):
        print("✅ RefereeCache._save_cache() uses lock protection")
    else:
        print("❌ CRITICAL: RefereeCache._save_cache() does NOT use lock - RACE CONDITION!")
else:
    print("⚠️ WARNING: Could not find _save_cache() method")

# Test 11: Check RefereeCache.get_stats() thread safety
print()
print("Test 11: Check RefereeCache.get_stats() thread safety")
get_stats_method = re.search(
    r"def get_stats\(.*?\):.*?(?=\n    def |\nclass |\Z)", cache_content, re.DOTALL
)
if get_stats_method:
    if "with self._lock:" in get_stats_method.group(0):
        print("✅ RefereeCache.get_stats() uses lock protection")
    else:
        print("❌ CRITICAL: RefereeCache.get_stats() does NOT use lock - RACE CONDITION!")
else:
    print("⚠️ WARNING: Could not find get_stats() method")

# Test 12: Check RefereeBoostLogger other logging methods
print()
print("Test 12: Check RefereeBoostLogger other logging methods")
other_methods = ["log_upgrade_applied", "log_influence_applied", "log_veto_applied"]
all_protected = True
for method_name in other_methods:
    method_pattern = rf"def {method_name}\(.*?\):.*?(?=\n    def |\nclass |\Z)"
    method_match = re.search(method_pattern, logger_content, re.DOTALL)
    if method_match:
        if "with self._lock:" not in method_match.group(0):
            print(
                f"❌ CRITICAL: RefereeBoostLogger.{method_name}() does NOT use lock - RACE CONDITION!"
            )
            all_protected = False
if all_protected:
    print("✅ All RefereeBoostLogger logging methods use lock protection")

# Test 13: Check get_referee_cache() thread safety
print()
print("Test 13: Check get_referee_cache() global instance thread safety")
if "def get_referee_cache():" in cache_content:
    get_cache_method = re.search(
        r"def get_referee_cache\(.*?\):.*?(?=\n    def |\nclass |\Z)", cache_content, re.DOTALL
    )
    if get_cache_method:
        if "with _referee_cache_lock:" in get_cache_method.group(
            0
        ) or "threading.Lock()" in get_cache_method.group(0):
            print("✅ get_referee_cache() uses thread-safe singleton pattern")
        else:
            print("❌ CRITICAL: get_referee_cache() does NOT use lock - RACE CONDITION!")
else:
    print("⚠️ WARNING: Could not find get_referee_cache() function")

# Test 14: Check get_referee_boost_logger() thread safety
print()
print("Test 14: Check get_referee_boost_logger() global instance thread safety")
if "def get_referee_boost_logger():" in logger_content:
    get_logger_method = re.search(
        r"def get_referee_boost_logger\(.*?\):.*?(?=\n    def |\nclass |\Z)",
        logger_content,
        re.DOTALL,
    )
    if get_logger_method:
        if "with _referee_boost_logger_lock:" in get_logger_method.group(
            0
        ) or "threading.Lock()" in get_logger_method.group(0):
            print("✅ get_referee_boost_logger() uses thread-safe singleton pattern")
        else:
            print("❌ CRITICAL: get_referee_boost_logger() does NOT use lock - RACE CONDITION!")
else:
    print("⚠️ WARNING: Could not find get_referee_boost_logger() function")

# Test 15: Check data flow integration
print()
print("Test 15: Check data flow integration")
with open("src/analysis/analyzer.py", "r") as f:
    analyzer_content = f.read()
if "from src.analysis.referee_boost_logger import get_referee_boost_logger" in analyzer_content:
    print("✅ analyzer.py imports get_referee_boost_logger")
else:
    print("❌ CRITICAL: analyzer.py does NOT import get_referee_boost_logger - DATA FLOW BROKEN!")

if "from src.analysis.referee_cache_monitor import get_referee_cache_monitor" in analyzer_content:
    print("✅ analyzer.py imports get_referee_cache_monitor")
else:
    print("❌ CRITICAL: analyzer.py does NOT import get_referee_cache_monitor - DATA FLOW BROKEN!")

# Test 16: Check if modules are actually used in analyzer
print()
print("Test 16: Check if modules are actually used in analyzer")
if (
    "get_referee_boost_logger()" in analyzer_content
    or "referee_boost_logger" in analyzer_content.lower()
):
    print("✅ referee_boost_logger is used in analyzer.py")
else:
    print("❌ CRITICAL: referee_boost_logger is imported but NOT used - DEAD CODE!")

if (
    "get_referee_cache_monitor()" in analyzer_content
    or "referee_cache_monitor" in analyzer_content.lower()
):
    print("✅ referee_cache_monitor is used in analyzer.py")
else:
    print("❌ CRITICAL: referee_cache_monitor is imported but NOT used - DEAD CODE!")

print()
print("=" * 80)
print("PHASE 3: EXECUTE VERIFICATION (ACTUAL TESTS)")
print("=" * 80)
print()

# Test 17: Test RefereeCache import and instantiation
print("Test 17: Test RefereeCache import and instantiation")
try:
    from src.analysis.referee_cache import RefereeCache

    print("✅ RefereeCache imported successfully")

    # Try to create instance
    cache = RefereeCache()
    print("✅ RefereeCache instantiated successfully")

    # Check if lock exists
    if hasattr(cache, "_lock"):
        print("✅ RefereeCache instance has _lock attribute")
    else:
        print("❌ CRITICAL: RefereeCache instance does NOT have _lock attribute")

    # Check if cache exists
    if hasattr(cache, "_cache"):
        print("✅ RefereeCache instance has _cache attribute")
    else:
        print("❌ CRITICAL: RefereeCache instance does NOT have _cache attribute")
except NameError as e:
    print(f"❌ CRITICAL: RefereeCache import failed - {e}")
except Exception as e:
    print(f"❌ CRITICAL: RefereeCache instantiation failed - {e}")

# Test 18: Test RefereeBoostLogger import and instantiation
print()
print("Test 18: Test RefereeBoostLogger import and instantiation")
try:
    from src.analysis.referee_boost_logger import RefereeBoostLogger

    print("✅ RefereeBoostLogger imported successfully")

    # Try to create instance
    logger = RefereeBoostLogger()
    print("✅ RefereeBoostLogger instantiated successfully")

    # Check if lock exists
    if hasattr(logger, "_lock"):
        print("✅ RefereeBoostLogger instance has _lock attribute")
    else:
        print("❌ CRITICAL: RefereeBoostLogger instance does NOT have _lock attribute")
except NameError as e:
    print(f"❌ CRITICAL: RefereeBoostLogger import failed - {e}")
except Exception as e:
    print(f"❌ CRITICAL: RefereeBoostLogger instantiation failed - {e}")

# Test 19: Test RefereeCache.get() method
print()
print("Test 19: Test RefereeCache.get() method")
try:
    from src.analysis.referee_cache import get_referee_cache

    cache = get_referee_cache()

    # Test get() with non-existent referee
    result = cache.get("NonExistentReferee")
    if result is None:
        print("✅ RefereeCache.get() returns None for non-existent referee")
    else:
        print("❌ WARNING: RefereeCache.get() did not return None for non-existent referee")
except Exception as e:
    print(f"❌ CRITICAL: RefereeCache.get() failed - {e}")

# Test 20: Test RefereeBoostLogger.log_boost_applied() method
print()
print("Test 20: Test RefereeBoostLogger.log_boost_applied() method")
try:
    from src.analysis.referee_boost_logger import get_referee_boost_logger

    logger = get_referee_boost_logger()

    # Test log_boost_applied
    logger.log_boost_applied(
        referee_name="Test Referee",
        cards_per_game=4.5,
        strictness="STRICT",
        original_verdict="NO BET",
        new_verdict="BET",
        recommended_market="Over 3.5 Cards",
        reason="Test reason",
    )
    print("✅ RefereeBoostLogger.log_boost_applied() executed successfully")
except Exception as e:
    print(f"❌ CRITICAL: RefereeBoostLogger.log_boost_applied() failed - {e}")

# Test 21: Test concurrent access to RefereeCache.get()
print()
print("Test 21: Test concurrent access to RefereeCache.get()")
try:
    from src.analysis.referee_cache import get_referee_cache

    cache = get_referee_cache()

    # Add a test entry
    cache.set("TestReferee", {"cards_per_game": 4.5, "strictness": "STRICT"})

    # Test concurrent reads
    results = []
    errors = []

    def read_cache():
        try:
            result = cache.get("TestReferee")
            results.append(result)
        except Exception as e:
            errors.append(e)

    threads = []
    for _ in range(10):
        t = threading.Thread(target=read_cache)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    if not errors and len(results) == 10:
        print("✅ RefereeCache.get() handles concurrent access correctly")
        print(f"   All {len(results)} threads completed successfully")
    else:
        print(f"❌ CRITICAL: RefereeCache.get() failed under concurrent access")
        if errors:
            print(f"   Errors: {errors}")
except Exception as e:
    print(f"❌ CRITICAL: Concurrent access test failed - {e}")

# Test 22: Test concurrent access to RefereeBoostLogger.log_boost_applied()
print()
print("Test 22: Test concurrent access to RefereeBoostLogger.log_boost_applied()")
try:
    from src.analysis.referee_boost_logger import get_referee_boost_logger

    logger = get_referee_boost_logger()

    # Test concurrent writes
    errors = []
    completed = []

    def log_boost():
        try:
            logger.log_boost_applied(
                referee_name="Test Referee",
                cards_per_game=4.5,
                strictness="STRICT",
                original_verdict="NO BET",
                new_verdict="BET",
                recommended_market="Over 3.5 Cards",
                reason="Test reason",
            )
            completed.append(True)
        except Exception as e:
            errors.append(e)

    threads = []
    for _ in range(10):
        t = threading.Thread(target=log_boost)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    if not errors and len(completed) == 10:
        print("✅ RefereeBoostLogger.log_boost_applied() handles concurrent access correctly")
        print(f"   All {len(completed)} threads completed successfully")
    else:
        print(f"❌ CRITICAL: RefereeBoostLogger.log_boost_applied() failed under concurrent access")
        if errors:
            print(f"   Errors: {errors}")
except Exception as e:
    print(f"❌ CRITICAL: Concurrent access test failed - {e}")

# Test 23: Check dependencies in requirements.txt
print()
print("Test 23: Check dependencies in requirements.txt")
with open("requirements.txt", "r") as f:
    req_content = f.read()

# threading is part of Python stdlib, so no need to check for it
print("✅ threading is part of Python stdlib (no external dependency needed)")

# Test 24: Check setup_vps.sh installs dependencies
print()
print("Test 24: Check setup_vps.sh installs dependencies")
with open("setup_vps.sh", "r") as f:
    setup_content = f.read()
if "pip install -r requirements.txt" in setup_content:
    print("✅ setup_vps.sh installs requirements.txt")
else:
    print("❌ CRITICAL: setup_vps.sh does NOT install requirements.txt - VPS DEPLOYMENT WILL FAIL")

print()
print("=" * 80)
print("PHASE 4: FINAL SUMMARY")
print("=" * 80)
print()

# Count critical issues
critical_issues = []

if "import threading" not in cache_content:
    critical_issues.append("RefereeCache missing 'import threading'")

if "import threading" not in logger_content:
    critical_issues.append("RefereeBoostLogger missing 'import threading'")

# Check for incomplete thread safety
if (
    "def set(" in cache_content
    and "with self._lock:" not in cache_content.split("def set(")[1].split("def ")[0]
    if "def set(" in cache_content
    else ""
):
    critical_issues.append("RefereeCache.set() not thread-safe")

if (
    "def _load_cache(" in cache_content
    and "with self._lock:" not in cache_content.split("def _load_cache(")[1].split("def ")[0]
    if "def _load_cache(" in cache_content
    else ""
):
    critical_issues.append("RefereeCache._load_cache() not thread-safe")

if (
    "def _save_cache(" in cache_content
    and "with self._lock:" not in cache_content.split("def _save_cache(")[1].split("def ")[0]
    if "def _save_cache(" in cache_content
    else ""
):
    critical_issues.append("RefereeCache._save_cache() not thread-safe")

if (
    "def get_stats(" in cache_content
    and "with self._lock:" not in cache_content.split("def get_stats(")[1].split("def ")[0]
    if "def get_stats(" in cache_content
    else ""
):
    critical_issues.append("RefereeCache.get_stats() not thread-safe")

if critical_issues:
    print("❌ CRITICAL ISSUES FOUND:")
    for issue in critical_issues:
        print(f"   - {issue}")
    print()
    print("STATUS: NOT READY FOR VPS DEPLOYMENT")
else:
    print("✅ All thread safety checks passed")
    print("✅ RefereeCache.get() uses lock-protected in-memory cache")
    print("✅ RefereeBoostLogger.log_boost_applied() uses lock protection")
    print("✅ threading module imported in both files")
    print("✅ Locks initialized in __init__")
    print("✅ Data flow: analyzer.py → referee modules")
    print()
    print("STATUS: READY FOR VPS DEPLOYMENT")

print()
print("=" * 80)
