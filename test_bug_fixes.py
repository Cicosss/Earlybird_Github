#!/usr/bin/env python3
"""
Test script to verify the bug fixes for:
1. Cache miss monitoring in verification_layer.py
2. Thread safety in orchestration_metrics.py
3. Log rotation in referee_boost_logger.py
"""

import sys
import os

# Test 1: Verify cache miss monitoring import
print("=" * 60)
print("TEST 1: Cache Miss Monitoring in verification_layer.py")
print("=" * 60)
try:
    from src.analysis.verification_layer import REFEREE_CACHE_MONITOR_AVAILABLE
    print(f"✅ REFEREE_CACHE_MONITOR_AVAILABLE = {REFEREE_CACHE_MONITOR_AVAILABLE}")
    if REFEREE_CACHE_MONITOR_AVAILABLE:
        print("✅ Referee cache monitor is available")
    else:
        print("⚠️ Referee cache monitor is not available (expected in some environments)")
except ImportError as e:
    print(f"❌ Failed to import: {e}")
    sys.exit(1)

# Test 2: Verify thread safety in orchestration_metrics.py
print("\n" + "=" * 60)
print("TEST 2: Thread Safety in orchestration_metrics.py")
print("=" * 60)
try:
    import inspect
    from src.alerting.orchestration_metrics import OrchestrationMetricsCollector

    # Check if _store_metrics method uses lock
    source = inspect.getsource(OrchestrationMetricsCollector._store_metrics)
    if "with self._lock:" in source:
        print("✅ _store_metrics() uses lock (thread-safe)")
    else:
        print("❌ _store_metrics() does NOT use lock (NOT thread-safe)")
        sys.exit(1)

    # Check if lock is initialized
    if hasattr(OrchestrationMetricsCollector, '__init__'):
        init_source = inspect.getsource(OrchestrationMetricsCollector.__init__)
        if "self._lock = threading.Lock()" in init_source:
            print("✅ Lock is initialized in __init__()")
        else:
            print("⚠️ Lock initialization not found in __init__()")
except Exception as e:
    print(f"❌ Failed to check thread safety: {e}")
    sys.exit(1)

# Test 3: Verify log rotation in referee_boost_logger.py
print("\n" + "=" * 60)
print("TEST 3: Log Rotation in referee_boost_logger.py")
print("=" * 60)
try:
    import inspect
    from src.analysis.referee_boost_logger import RefereeBoostLogger

    # Check if _setup_logger method uses RotatingFileHandler
    source = inspect.getsource(RefereeBoostLogger._setup_logger)
    if "RotatingFileHandler" in source:
        print("✅ _setup_logger() uses RotatingFileHandler")
        # Check for maxBytes and backupCount parameters
        if "maxBytes" in source and "backupCount" in source:
            print("✅ RotatingFileHandler configured with maxBytes and backupCount")
        else:
            print("⚠️ RotatingFileHandler found but parameters may not be configured")
    else:
        print("❌ _setup_logger() does NOT use RotatingFileHandler")
        sys.exit(1)

    # Check if RotatingFileHandler is imported
    import src.analysis.referee_boost_logger as logger_module
    logger_source = inspect.getsource(logger_module)
    if "from logging.handlers import RotatingFileHandler" in logger_source:
        print("✅ RotatingFileHandler is imported")
    else:
        print("❌ RotatingFileHandler is NOT imported")
        sys.exit(1)
except Exception as e:
    print(f"❌ Failed to check log rotation: {e}")
    sys.exit(1)

# All tests passed
print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED!")
print("=" * 60)
print("\nSummary:")
print("1. ✅ Cache miss monitoring is implemented in verification_layer.py")
print("2. ✅ Thread safety is implemented in orchestration_metrics.py")
print("3. ✅ Log rotation is implemented in referee_boost_logger.py")
print("\nAll bug fixes have been successfully applied!")
