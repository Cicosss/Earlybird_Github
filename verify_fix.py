#!/usr/bin/env python3
"""
Quick verification that the fix was applied correctly.

This script checks if the improved warning message is in the code.
"""

import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

# Read the file and check for the fix
file_path = Path("src/services/nitter_fallback_scraper.py")
content = file_path.read_text()

# Check for the improved warning message
if 'No active handles found for continent:' in content:
    print("✅ FIX VERIFIED: Improved warning message found in code")
    print("   Message includes continent name")
else:
    print("❌ FIX NOT FOUND: Improved warning message not in code")
    sys.exit(1)

# Check for INFO level instead of WARNING
if 'logger.info(f"ℹ️ [NITTER-CYCLE] No active handles found for continent:' in content:
    print("✅ FIX VERIFIED: Warning uses INFO level (logger.info)")
    print("   Severity reduced from WARNING to INFO")
else:
    print("❌ FIX NOT FOUND: Warning still uses WARNING level")
    sys.exit(1)

# Check for debug message
if 'logger.debug(f"   This is expected if no leagues are active in' in content:
    print("✅ FIX VERIFIED: Debug message added for context")
    print("   Provides additional information")
else:
    print("❌ FIX NOT FOUND: Debug message not added")
    sys.exit(1)

print("\n✅ ALL FIXES VERIFIED SUCCESSFULLY")
print("   The improved warning message is now in the code")
