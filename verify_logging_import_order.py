#!/usr/bin/env python3
"""
Verification script to check import order and logging.basicConfig() calls.
This helps identify if supabase_provider is imported before logging configuration.
"""

import sys
import os
import importlib
import inspect
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 80)
print("LOGGING CONFIGURATION VERIFICATION")
print("=" * 80)

# Track which modules have been imported and their logging.basicConfig() calls
imported_modules = {}
logging_calls = {}

# Monkey-patch logging.basicConfig to track when it's called
import logging
original_basicConfig = logging.basicConfig

def tracking_basicConfig(**kwargs):
    # Get the caller's frame
    frame = inspect.currentframe()
    try:
        # Go up 2 frames to get the actual caller
        caller_frame = frame.f_back.f_back
        caller_file = caller_frame.f_code.co_filename
        caller_line = caller_frame.f_lineno
        caller_module = caller_frame.f_globals.get('__name__', 'unknown')
        
        call_info = {
            'file': caller_file,
            'line': caller_line,
            'module': caller_module,
            'kwargs': kwargs,
            'handlers': 'handlers' in kwargs,
            'force': kwargs.get('force', False)
        }
        
        key = f"{caller_file}:{caller_line}"
        logging_calls[key] = call_info
        
        print(f"\n📝 logging.basicConfig() called:")
        print(f"   File: {caller_file}")
        print(f"   Line: {caller_line}")
        print(f"   Module: {caller_module}")
        print(f"   Has handlers: {call_info['handlers']}")
        print(f"   Force: {call_info['force']}")
        if 'handlers' in kwargs:
            print(f"   Handlers: {kwargs['handlers']}")
        else:
            print(f"   Format: {kwargs.get('format', 'default')}")
            print(f"   Level: {kwargs.get('level', 'NOTSET')}")
    finally:
        frame.f_back.f_back
    
    # Call the original function
    return original_basicConfig(**kwargs)

# Replace logging.basicConfig with our tracking version
logging.basicConfig = tracking_basicConfig

print("\n" + "=" * 80)
print("TEST 1: Importing run_bot.py")
print("=" * 80)

# Clear previous calls
logging_calls = {}

try:
    # Import run_bot.py
    import src.entrypoints.run_bot as run_bot_module
    print(f"\n✅ Successfully imported run_bot.py")
    
    # Check if supabase_provider was imported
    if 'src.database.supabase_provider' in sys.modules:
        print(f"✅ supabase_provider WAS imported")
        # Get the module
        supabase_module = sys.modules['src.database.supabase_provider']
        # Check when it was imported relative to logging configuration
        print(f"   Module file: {supabase_module.__file__}")
    else:
        print(f"❌ supabase_provider was NOT imported")
    
    # Show all logging.basicConfig() calls
    print(f"\n📊 Total logging.basicConfig() calls: {len(logging_calls)}")
    for i, (key, call_info) in enumerate(logging_calls.items(), 1):
        print(f"\n   Call #{i}:")
        print(f"      File: {call_info['file']}")
        print(f"      Line: {call_info['line']}")
        print(f"      Module: {call_info['module']}")
        print(f"      Has handlers: {call_info['handlers']}")
        print(f"      Force: {call_info['force']}")
    
    # Check the order of calls
    if len(logging_calls) >= 2:
        print(f"\n🔍 Order Analysis:")
        calls_list = list(logging_calls.values())
        for i, call_info in enumerate(calls_list):
            if i == 0:
                print(f"   FIRST: {call_info['file']}:{call_info['line']} - Has handlers: {call_info['handlers']}")
            elif i == len(calls_list) - 1:
                print(f"   LAST: {call_info['file']}:{call_info['line']} - Has handlers: {call_info['handlers']}")
            else:
                print(f"   MIDDLE: {call_info['file']}:{call_info['line']} - Has handlers: {call_info['handlers']}")
        
        # Check if first call has no handlers
        if not calls_list[0]['handlers']:
            print(f"\n⚠️  PROBLEM IDENTIFIED: First logging.basicConfig() call has NO handlers!")
            print(f"   This means subsequent calls with handlers will be IGNORED by Python.")
        else:
            print(f"\n✅ First call has handlers, so subsequent configuration should work.")

except Exception as e:
    print(f"❌ Error importing run_bot.py: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("TEST 2: Importing run_news_radar.py")
print("=" * 80)

# Clear previous calls
logging_calls = {}

try:
    # Remove run_bot from sys.modules to start fresh
    if 'src.entrypoints.run_bot' in sys.modules:
        del sys.modules['src.entrypoints.run_bot']
    
    # Import run_news_radar.py
    import run_news_radar as news_radar_module
    print(f"\n✅ Successfully imported run_news_radar.py")
    
    # Check if supabase_provider was imported
    if 'src.database.supabase_provider' in sys.modules:
        print(f"✅ supabase_provider WAS imported")
    else:
        print(f"❌ supabase_provider was NOT imported")
    
    # Show all logging.basicConfig() calls
    print(f"\n📊 Total logging.basicConfig() calls: {len(logging_calls)}")
    for i, (key, call_info) in enumerate(logging_calls.items(), 1):
        print(f"\n   Call #{i}:")
        print(f"      File: {call_info['file']}")
        print(f"      Line: {call_info['line']}")
        print(f"      Module: {call_info['module']}")
        print(f"      Has handlers: {call_info['handlers']}")
        print(f"      Force: {call_info['force']}")
    
    # Check the order of calls
    if len(logging_calls) >= 2:
        print(f"\n🔍 Order Analysis:")
        calls_list = list(logging_calls.values())
        for i, call_info in enumerate(calls_list):
            if i == 0:
                print(f"   FIRST: {call_info['file']}:{call_info['line']} - Has handlers: {call_info['handlers']}")
            elif i == len(calls_list) - 1:
                print(f"   LAST: {call_info['file']}:{call_info['line']} - Has handlers: {call_info['handlers']}")
            else:
                print(f"   MIDDLE: {call_info['file']}:{call_info['line']} - Has handlers: {call_info['handlers']}")
        
        # Check if first call has no handlers
        if not calls_list[0]['handlers']:
            print(f"\n⚠️  PROBLEM IDENTIFIED: First logging.basicConfig() call has NO handlers!")
            print(f"   This means subsequent calls with handlers will be IGNORED by Python.")
        else:
            print(f"\n✅ First call has handlers, so subsequent configuration should work.")

except Exception as e:
    print(f"❌ Error importing run_news_radar.py: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("TEST 3: Importing run_telegram_monitor.py")
print("=" * 80)

# Clear previous calls
logging_calls = {}

try:
    # Remove previous modules from sys.modules to start fresh
    for mod in list(sys.modules.keys()):
        if 'run_news_radar' in mod or 'src.entrypoints.run_bot' in mod:
            del sys.modules[mod]
    
    # Import run_telegram_monitor.py
    import run_telegram_monitor as telegram_monitor_module
    print(f"\n✅ Successfully imported run_telegram_monitor.py")
    
    # Check if supabase_provider was imported
    if 'src.database.supabase_provider' in sys.modules:
        print(f"✅ supabase_provider WAS imported")
    else:
        print(f"❌ supabase_provider was NOT imported")
    
    # Show all logging.basicConfig() calls
    print(f"\n📊 Total logging.basicConfig() calls: {len(logging_calls)}")
    for i, (key, call_info) in enumerate(logging_calls.items(), 1):
        print(f"\n   Call #{i}:")
        print(f"      File: {call_info['file']}")
        print(f"      Line: {call_info['line']}")
        print(f"      Module: {call_info['module']}")
        print(f"      Has handlers: {call_info['handlers']}")
        print(f"      Force: {call_info['force']}")
    
    # Check the order of calls
    if len(logging_calls) >= 2:
        print(f"\n🔍 Order Analysis:")
        calls_list = list(logging_calls.values())
        for i, call_info in enumerate(calls_list):
            if i == 0:
                print(f"   FIRST: {call_info['file']}:{call_info['line']} - Has handlers: {call_info['handlers']}")
            elif i == len(calls_list) - 1:
                print(f"   LAST: {call_info['file']}:{call_info['line']} - Has handlers: {call_info['handlers']}")
            else:
                print(f"   MIDDLE: {call_info['file']}:{call_info['line']} - Has handlers: {call_info['handlers']}")
        
        # Check if first call has no handlers
        if not calls_list[0]['handlers']:
            print(f"\n⚠️  PROBLEM IDENTIFIED: First logging.basicConfig() call has NO handlers!")
            print(f"   This means subsequent calls with handlers will be IGNORED by Python.")
        else:
            print(f"\n✅ First call has handlers, so subsequent configuration should work.")

except Exception as e:
    print(f"❌ Error importing run_telegram_monitor.py: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("VERIFICATION COMPLETE")
print("=" * 80)
