#!/usr/bin/env python3
"""
Direct verification of logging configuration issue.
This script directly tests if logging.basicConfig() is being called multiple times
and if the first call is preventing subsequent calls from working.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 80)
print("DIRECT LOGGING CONFIGURATION VERIFICATION")
print("=" * 80)

# Test 1: Check if supabase_provider calls logging.basicConfig at module level
print("\n" + "=" * 80)
print("TEST 1: Check supabase_provider logging configuration")
print("=" * 80)

import logging

# Get the current root logger state before any imports
root_logger = logging.getLogger()
initial_handlers = root_logger.handlers.copy()
print("\n📊 Initial root logger state:")
print(f"   Handlers: {len(initial_handlers)}")
for handler in initial_handlers:
    print(f"      - {type(handler).__name__}")

# Now import supabase_provider
print("\n📦 Importing src.database.supabase_provider...")

# Check root logger state after import
root_logger = logging.getLogger()
after_import_handlers = root_logger.handlers.copy()
print("\n📊 Root logger state AFTER importing supabase_provider:")
print(f"   Handlers: {len(after_import_handlers)}")
for handler in after_import_handlers:
    print(f"      - {type(handler).__name__}")

# Compare handlers
if len(after_import_handlers) > len(initial_handlers):
    print("\n⚠️  Handlers were ADDED during import!")
elif len(after_import_handlers) < len(initial_handlers):
    print("\n⚠️  Handlers were REMOVED during import!")
else:
    print("\n✅ No change in handlers")

# Test 2: Try to configure logging AFTER importing supabase_provider
print("\n" + "=" * 80)
print("TEST 2: Try to configure logging AFTER importing supabase_provider")
print("=" * 80)

# Create handlers
import io
from logging.handlers import RotatingFileHandler

# Create a StringIO to capture log output
log_capture = io.StringIO()
stream_handler = logging.StreamHandler(log_capture)
stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

file_handler = RotatingFileHandler("test_bot.log", maxBytes=5_000_000, backupCount=2)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

print("\n📝 Attempting to call logging.basicConfig() with handlers...")
print(f"   StreamHandler: {stream_handler}")
print(f"   FileHandler: {file_handler}")

# Try to configure logging
logging.basicConfig(level=logging.INFO, handlers=[stream_handler, file_handler])

# Check root logger state after basicConfig
root_logger = logging.getLogger()
after_config_handlers = root_logger.handlers.copy()
print("\n📊 Root logger state AFTER logging.basicConfig():")
print(f"   Handlers: {len(after_config_handlers)}")
for handler in after_config_handlers:
    print(f"      - {type(handler).__name__}")

# Check if our handlers were added
our_handlers = [h for h in after_config_handlers if h in [stream_handler, file_handler]]
print(
    f"\n🔍 Our handlers in root logger: {len(our_handlers)}/{len([stream_handler, file_handler])}"
)

if len(our_handlers) == len([stream_handler, file_handler]):
    print("✅ All our handlers were successfully added!")
else:
    print("❌ NOT all our handlers were added!")
    print(
        "   This suggests logging.basicConfig() was IGNORED because root logger was already configured"
    )

# Test 3: Try logging to see where messages go
print("\n" + "=" * 80)
print("TEST 3: Test logging to see where messages go")
print("=" * 80)

test_logger = logging.getLogger("test")
test_logger.info("Test message 1")
test_logger.info("Test message 2")

# Check captured output
captured = log_capture.getvalue()
print(f"\n📝 Captured in StringIO: {len(captured)} bytes")
if captured:
    print(f"   Content: {captured[:100]}")
else:
    print("   (empty)")

# Check file
try:
    with open("test_bot.log", "r") as f:
        file_content = f.read()
    print(f"\n📝 Written to test_bot.log: {len(file_content)} bytes")
    if file_content:
        print(f"   Content: {file_content[:100]}")
    else:
        print("   (empty)")
except FileNotFoundError:
    print("\n❌ test_bot.log was not created!")

# Test 4: Try with force=True
print("\n" + "=" * 80)
print("TEST 4: Try logging.basicConfig() with force=True")
print("=" * 80)

# Create new handlers
log_capture2 = io.StringIO()
stream_handler2 = logging.StreamHandler(log_capture2)
stream_handler2.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

file_handler2 = RotatingFileHandler("test_bot2.log", maxBytes=5_000_000, backupCount=2)
file_handler2.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

print("\n📝 Attempting to call logging.basicConfig() with force=True...")
print(f"   StreamHandler: {stream_handler2}")
print(f"   FileHandler: {file_handler2}")

# Try to configure logging with force=True
logging.basicConfig(level=logging.INFO, handlers=[stream_handler2, file_handler2], force=True)

# Check root logger state after basicConfig with force
root_logger = logging.getLogger()
after_force_config_handlers = root_logger.handlers.copy()
print("\n📊 Root logger state AFTER logging.basicConfig(force=True):")
print(f"   Handlers: {len(after_force_config_handlers)}")
for handler in after_force_config_handlers:
    print(f"      - {type(handler).__name__}")

# Check if our handlers were added
our_handlers2 = [h for h in after_force_config_handlers if h in [stream_handler2, file_handler2]]
print(
    f"\n🔍 Our handlers in root logger: {len(our_handlers2)}/{len([stream_handler2, file_handler2])}"
)

if len(our_handlers2) == len([stream_handler2, file_handler2]):
    print("✅ All our handlers were successfully added with force=True!")
else:
    print("❌ NOT all our handlers were added even with force=True!")

# Test logging again
test_logger.info("Test message 3 (with force=True)")
test_logger.info("Test message 4 (with force=True)")

# Check captured output
captured2 = log_capture2.getvalue()
print(f"\n📝 Captured in StringIO: {len(captured2)} bytes")
if captured2:
    print(f"   Content: {captured2[:100]}")
else:
    print("   (empty)")

# Check file
try:
    with open("test_bot2.log", "r") as f:
        file_content2 = f.read()
    print(f"\n📝 Written to test_bot2.log: {len(file_content2)} bytes")
    if file_content2:
        print(f"   Content: {file_content2[:100]}")
    else:
        print("   (empty)")
except FileNotFoundError:
    print("\n❌ test_bot2.log was not created!")

# Cleanup
print("\n" + "=" * 80)
print("CLEANUP")
print("=" * 80)
for log_file in ["test_bot.log", "test_bot2.log"]:
    try:
        os.remove(log_file)
        print(f"✅ Removed {log_file}")
    except FileNotFoundError:
        pass

print("\n" + "=" * 80)
print("VERIFICATION COMPLETE")
print("=" * 80)
