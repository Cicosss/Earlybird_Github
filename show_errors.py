#!/usr/bin/env python3
"""
EarlyBird Error Viewer - Shows last N errors/warnings from log file.

Usage:
    python show_errors.py          # Shows last 50 errors/warnings
    python show_errors.py 100      # Shows last 100 errors/warnings
    python show_errors.py -f       # Follow mode (like tail -f)
"""
import sys
import os
import re
from collections import deque

LOG_FILE = "earlybird.log"

# Patterns to match
ERROR_PATTERN = re.compile(r'.*(ERROR|WARNING|CRITICAL).*', re.IGNORECASE)

def get_last_errors(n: int = 50) -> list:
    """Get last N errors/warnings from log file."""
    if not os.path.exists(LOG_FILE):
        print(f"❌ Log file not found: {LOG_FILE}")
        return []
    
    errors = deque(maxlen=n)
    
    with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if ERROR_PATTERN.search(line):
                # Color code based on severity
                if 'ERROR' in line or 'CRITICAL' in line:
                    errors.append(f"❌ {line.strip()}")
                elif 'WARNING' in line:
                    errors.append(f"⚠️ {line.strip()}")
    
    return list(errors)

def follow_errors():
    """Follow log file and print new errors in real-time."""
    import time
    
    if not os.path.exists(LOG_FILE):
        print(f"❌ Log file not found: {LOG_FILE}")
        return
    
    print(f"📡 Following {LOG_FILE} for errors/warnings... (Ctrl+C to stop)\n")
    
    with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
        # Go to end of file
        f.seek(0, 2)
        
        while True:
            line = f.readline()
            if line:
                if ERROR_PATTERN.search(line):
                    if 'ERROR' in line or 'CRITICAL' in line:
                        print(f"❌ {line.strip()}")
                    elif 'WARNING' in line:
                        print(f"⚠️ {line.strip()}")
            else:
                time.sleep(0.5)

def main():
    args = sys.argv[1:]
    
    # Follow mode
    if '-f' in args or '--follow' in args:
        try:
            follow_errors()
        except KeyboardInterrupt:
            print("\n👋 Stopped following.")
        return
    
    # Get count
    n = 50
    if args and args[0].isdigit():
        n = int(args[0])
    
    print(f"🔍 Ultimi {n} errori/warning da {LOG_FILE}:\n")
    print("=" * 80)
    
    errors = get_last_errors(n)
    
    if not errors:
        print("✅ Nessun errore/warning trovato!")
    else:
        for err in errors:
            print(err)
    
    print("=" * 80)
    print(f"\n📊 Totale: {len(errors)} errori/warning")
    
    # Summary by type
    error_count = sum(1 for e in errors if '❌' in e)
    warning_count = sum(1 for e in errors if '⚠️' in e)
    print(f"   ❌ Errori: {error_count}")
    print(f"   ⚠️ Warning: {warning_count}")

if __name__ == "__main__":
    main()
