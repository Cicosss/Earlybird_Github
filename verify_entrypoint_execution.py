#!/usr/bin/env python3
"""
Verify what happens when entrypoints actually run.
This simulates the actual execution path of the entrypoints.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 80)
print("ENTRYPOINT EXECUTION VERIFICATION")
print("=" * 80)

# Test 1: Run run_bot.py directly and check log files
print("\n" + "=" * 80)
print("TEST 1: Run run_bot.py and check log files")
print("=" * 80)

# Clean up existing log files
for log_file in ["bot.log", "news_radar.log", "logs/telegram_monitor.log"]:
    try:
        if os.path.exists(log_file):
            os.remove(log_file)
            print(f"✅ Removed existing {log_file}")
    except Exception as e:
        print(f"⚠️  Could not remove {log_file}: {e}")

# Create a minimal test script that imports run_bot and logs something
test_script = """
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Import run_bot
import src.entrypoints.run_bot as run_bot

# Get the root logger
root_logger = logging.getLogger()

print("=== ROOT LOGGER STATE AFTER IMPORT ===")
print(f"Handlers: {len(root_logger.handlers)}")
for i, handler in enumerate(root_logger.handlers):
    print(f"  Handler {i}: {type(handler).__name__}")
    if hasattr(handler, 'baseFilename'):
        print(f"    File: {handler.baseFilename}")

# Try to log something
test_logger = logging.getLogger("test")
test_logger.info("Test message from run_bot import")

# Check if files were created
import os
for log_file in ["bot.log"]:
    if os.path.exists(log_file):
        size = os.path.getsize(log_file)
        print(f"\\n=== {log_file} ===")
        print(f"Size: {size} bytes")
        if size > 0:
            with open(log_file, "r") as f:
                content = f.read()
                print(f"Content (first 200 chars): {content[:200]}")
        else:
            print("(empty)")
"""

# Write the test script
with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
    f.write(test_script)
    test_script_path = f.name

try:
    # Run the test script
    print("\n🚀 Running test script...")
    result = subprocess.run(
        [sys.executable, test_script_path],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(Path(__file__).parent),
    )

    print(f"\n📊 Exit code: {result.returncode}")
    print("\n📝 STDOUT:")
    print(result.stdout)
    if result.stderr:
        print("\n📝 STDERR:")
        print(result.stderr)

    # Check log files
    print("\n📁 Log files after test:")
    for log_file in ["bot.log"]:
        if os.path.exists(log_file):
            size = os.path.getsize(log_file)
            print(f"   {log_file}: {size} bytes")
            if size > 0:
                with open(log_file, "r") as f:
                    content = f.read()
                    print(f"      Content (first 200 chars): {content[:200]}")
            else:
                print("      (empty)")
        else:
            print(f"   {log_file}: NOT CREATED")

finally:
    # Clean up test script
    try:
        os.remove(test_script_path)
    except:
        pass

# Test 2: Check what happens when we call logging.basicConfig() twice
print("\n" + "=" * 80)
print("TEST 2: Check logging.basicConfig() behavior when called twice")
print("=" * 80)

test_script2 = """
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# First call WITHOUT handlers
print("=== FIRST CALL (without handlers) ===")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

root_logger = logging.getLogger()
print(f"Handlers after first call: {len(root_logger.handlers)}")
for handler in root_logger.handlers:
    print(f"  - {type(handler).__name__}")

# Second call WITH handlers
print("\\n=== SECOND CALL (with handlers) ===")
from logging.handlers import RotatingFileHandler

_log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_log_formatter)
_file_handler = RotatingFileHandler("test_twice.log", maxBytes=5_000_000, backupCount=2)
_file_handler.setFormatter(_log_formatter)

logging.basicConfig(level=logging.INFO, handlers=[_console_handler, _file_handler])

root_logger = logging.getLogger()
print(f"Handlers after second call: {len(root_logger.handlers)}")
for handler in root_logger.handlers:
    print(f"  - {type(handler).__name__}")
    if hasattr(handler, 'baseFilename'):
        print(f"    File: {handler.baseFilename}")

# Try to log
test_logger = logging.getLogger("test")
test_logger.info("Test message")

# Check file
import os
if os.path.exists("test_twice.log"):
    size = os.path.getsize("test_twice.log")
    print(f"\\ntest_twice.log: {size} bytes")
    if size > 0:
        with open("test_twice.log", "r") as f:
            content = f.read()
            print(f"Content: {content}")
    else:
        print("(empty)")
else:
    print("\\ntest_twice.log: NOT CREATED")
"""

# Write the test script
with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
    f.write(test_script2)
    test_script2_path = f.name

try:
    # Run the test script
    print("\n🚀 Running test script 2...")
    result = subprocess.run(
        [sys.executable, test_script2_path],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(Path(__file__).parent),
    )

    print(f"\n📊 Exit code: {result.returncode}")
    print("\n📝 STDOUT:")
    print(result.stdout)
    if result.stderr:
        print("\n📝 STDERR:")
        print(result.stderr)

finally:
    # Clean up test script and log file
    try:
        os.remove(test_script2_path)
    except:
        pass
    try:
        os.remove("test_twice.log")
    except:
        pass

# Test 3: Check if the issue is with the launcher's subprocess handling
print("\n" + "=" * 80)
print("TEST 3: Check launcher subprocess handling")
print("=" * 80)

# Read the launcher code to understand how it handles stdout/stderr
with open("src/entrypoints/launcher.py", "r") as f:
    launcher_content = f.read()

# Find the subprocess call
import re

subprocess_pattern = r"subprocess\.(Popen|run)\([^)]+\)"
matches = re.findall(subprocess_pattern, launcher_content, re.DOTALL)

print(f"\n🔍 Found {len(matches)} subprocess calls in launcher.py")

# Look for stdout/stderr redirection
if "stdout=" in launcher_content or "stderr=" in launcher_content:
    print("✅ Launcher redirects stdout/stderr")
    if "subprocess.PIPE" in launcher_content:
        print("   Uses subprocess.PIPE")
    else:
        print("   Uses other redirection")
else:
    print("❌ Launcher does NOT redirect stdout/stderr")

# Check if launcher captures output to launcher_output.log
if "launcher_output.log" in launcher_content:
    print("✅ Launcher writes to launcher_output.log")
else:
    print("❌ Launcher does NOT write to launcher_output.log")

print("\n" + "=" * 80)
print("VERIFICATION COMPLETE")
print("=" * 80)
