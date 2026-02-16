#!/usr/bin/env python3
"""
Compare logging configuration between src/main.py (works) and entry points (don't work).
"""

print("=" * 80)
print("LOGGING CONFIGURATION COMPARISON")
print("=" * 80)

# Read src/main.py
print("\n" + "=" * 80)
print("src/main.py (WORKS - earlybird_main.log has 2,073 bytes)")
print("=" * 80)

with open("src/main.py", "r") as f:
    main_content = f.read()

# Find logging configuration
main_config = []
for i, line in enumerate(main_content.split("\n"), 1):
    if (
        "logging.basicConfig(" in line
        or "logging.FileHandler(" in line
        or "logging.StreamHandler(" in line
    ):
        # Get context
        start = max(0, i - 3)
        end = min(len(main_content.split("\n")), i + 3)
        context = main_content.split("\n")[start:end]
        main_config.append((i, line.strip(), "\n".join(context)))
        break

if main_config:
    line_num, line_content, context = main_config[0]
    print(f"\n📝 Line {line_num}:")
    print(f"   {line_content}")
    print("\n   Context:")
    for ctx_line in context:
        print(f"      {ctx_line}")
else:
    print("\n❌ No logging.basicConfig() found in src/main.py")

# Read run_bot.py
print("\n" + "=" * 80)
print("src/entrypoints/run_bot.py (DOESN'T WORK - bot.log is 0 bytes)")
print("=" * 80)

with open("src/entrypoints/run_bot.py", "r") as f:
    bot_content = f.read()

# Find logging configuration
bot_config = []
for i, line in enumerate(bot_content.split("\n"), 1):
    if (
        "logging.basicConfig(" in line
        or "logging.FileHandler(" in line
        or "logging.StreamHandler(" in line
    ):
        # Get context
        start = max(0, i - 5)
        end = min(len(bot_content.split("\n")), i + 3)
        context = bot_content.split("\n")[start:end]
        bot_config.append((i, line.strip(), "\n".join(context)))

if bot_config:
    for line_num, line_content, context in bot_config:
        print(f"\n📝 Line {line_num}:")
        print(f"   {line_content}")
        print("\n   Context:")
        for ctx_line in context:
            marker = ">>> " if ctx_line.strip() == line_content else "    "
            print(f"      {marker}{ctx_line}")
else:
    print("\n❌ No logging configuration found in src/entrypoints/run_bot.py")

# Read run_news_radar.py
print("\n" + "=" * 80)
print("run_news_radar.py (DOESN'T WORK - news_radar.log is 0 bytes)")
print("=" * 80)

with open("run_news_radar.py", "r") as f:
    news_content = f.read()

# Find logging configuration
news_config = []
for i, line in enumerate(news_content.split("\n"), 1):
    if (
        "logging.basicConfig(" in line
        or "logging.FileHandler(" in line
        or "logging.StreamHandler(" in line
    ):
        # Get context
        start = max(0, i - 5)
        end = min(len(news_content.split("\n")), i + 3)
        context = news_content.split("\n")[start:end]
        news_config.append((i, line.strip(), "\n".join(context)))

if news_config:
    for line_num, line_content, context in news_config:
        print(f"\n📝 Line {line_num}:")
        print(f"   {line_content}")
        print("\n   Context:")
        for ctx_line in context:
            marker = ">>> " if ctx_line.strip() == line_content else "    "
            print(f"      {marker}{ctx_line}")
else:
    print("\n❌ No logging configuration found in run_news_radar.py")

# Read run_telegram_monitor.py
print("\n" + "=" * 80)
print("run_telegram_monitor.py (DOESN'T WORK - logs/telegram_monitor.log is 0 bytes)")
print("=" * 80)

with open("run_telegram_monitor.py", "r") as f:
    monitor_content = f.read()

# Find logging configuration
monitor_config = []
for i, line in enumerate(monitor_content.split("\n"), 1):
    if (
        "logging.basicConfig(" in line
        or "logging.FileHandler(" in line
        or "logging.StreamHandler(" in line
    ):
        # Get context
        start = max(0, i - 5)
        end = min(len(monitor_content.split("\n")), i + 3)
        context = monitor_content.split("\n")[start:end]
        monitor_config.append((i, line.strip(), "\n".join(context)))

if monitor_config:
    for line_num, line_content, context in monitor_config:
        print(f"\n📝 Line {line_num}:")
        print(f"   {line_content}")
        print("\n   Context:")
        for ctx_line in context:
            marker = ">>> " if ctx_line.strip() == line_content else "    "
            print(f"      {marker}{ctx_line}")
else:
    print("\n❌ No logging configuration found in run_telegram_monitor.py")

# Compare differences
print("\n" + "=" * 80)
print("DIFFERENCES ANALYSIS")
print("=" * 80)

print("""
KEY DIFFERENCES:

1. src/main.py:
   - Uses logging.FileHandler("earlybird_main.log")
   - Simple configuration
   - Works correctly

2. src/entrypoints/run_bot.py:
   - Uses RotatingFileHandler("bot.log", maxBytes=5_000_000, backupCount=2)
   - More complex configuration
   - Doesn't work

3. run_news_radar.py:
   - Uses logging.FileHandler("news_radar.log", encoding="utf-8")
   - Simple configuration
   - Doesn't work

4. run_telegram_monitor.py:
   - Uses RotatingFileHandler("logs/telegram_monitor.log", maxBytes=5_000_000, backupCount=3)
   - Uses LOGS_DIR from settings
   - Doesn't work

POTENTIAL ISSUES:

1. RotatingFileHandler vs FileHandler:
   - run_bot.py and run_telegram_monitor.py use RotatingFileHandler
   - src/main.py and run_news_radar.py use FileHandler
   - But run_news_radar.py doesn't work either

2. File paths:
   - run_telegram_monitor.py uses LOGS_DIR from settings
   - Others use relative paths
   - Maybe LOGS_DIR is wrong?

3. Encoding:
   - run_news_radar.py specifies encoding="utf-8"
   - Others don't
   - But it doesn't work either

4. Timing:
   - Maybe logging is configured at wrong time?
   - Need to check if there's a race condition
""")

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
