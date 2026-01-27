#!/usr/bin/env python3
"""
🦅 EARLYBIRD V3.1 - HEADLESS LAUNCHER

Lightweight launcher for CLI + Telegram only (no web dashboard).

1. Check Environment & Database
2. Launch Telegram Monitor (background)
3. Launch Main Pipeline (foreground)

Usage:
    python go_live.py [--skip-reset]
"""
import os
import sys
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Process tracking
BACKGROUND_PROCESSES = []
SHUTDOWN_FLAG = False


def print_banner():
    print("\n" + "=" * 50)
    print("🦅 EARLYBIRD V3.1 - HEADLESS MODE")
    print("=" * 50)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50 + "\n")


def check_environment() -> bool:
    """Verify .env and required variables."""
    print("[1/3] 🔍 ENVIRONMENT CHECK")
    
    env_file = Path(".env")
    if not env_file.exists():
        print("   ❌ .env file not found!")
        return False
    
    from dotenv import load_dotenv
    load_dotenv()
    
    required = ["OPENROUTER_API_KEY", "ODDS_API_KEY", "SERPER_API_KEY", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = [v for v in required if not os.getenv(v) or os.getenv(v, "").startswith("your_")]
    
    if missing:
        print(f"   ❌ Missing: {', '.join(missing)}")
        return False
    
    print("   ✅ All required variables configured")
    
    # Check optional Telegram monitoring
    if os.getenv("TELEGRAM_API_ID") and os.getenv("TELEGRAM_API_HASH"):
        print("   ✅ Telegram monitoring enabled")
    else:
        print("   ⚠️  Telegram monitoring disabled (no API_ID/HASH)")
    
    return True


def init_database(skip_reset: bool = False) -> bool:
    """Initialize or reset database."""
    print("\n[2/3] 🗄️  DATABASE CHECK")
    
    try:
        sys.path.insert(0, '.')
        from src.database.models import init_db
        init_db()
        print("   ✅ Database ready")
        return True
    except Exception as e:
        print(f"   ❌ Database error: {e}")
        return False


def start_telegram_monitor() -> subprocess.Popen:
    """Start Telegram monitor in background."""
    if not os.getenv("TELEGRAM_API_ID"):
        return None
    
    if not Path("run_telegram_monitor.py").exists():
        return None
    
    try:
        process = subprocess.Popen(
            [sys.executable, "run_telegram_monitor.py"],
            stdout=open("telegram_monitor.log", "a"),
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid if os.name != 'nt' else None
        )
        BACKGROUND_PROCESSES.append(process)
        print(f"   ✅ Telegram Monitor started (PID: {process.pid})")
        return process
    except Exception as e:
        print(f"   ⚠️  Telegram Monitor failed: {e}")
        return None


def run_main_pipeline():
    """Run main pipeline in foreground."""
    print("\n" + "=" * 50)
    print("🎯 EARLYBIRD IS NOW LIVE (HEADLESS)")
    print("=" * 50)
    print("\n📝 Main Log:  tail -f earlybird.log")
    print("📱 TG Log:    tail -f telegram_monitor.log")
    print("\n⚠️  Press Ctrl+C to stop")
    print("=" * 50 + "\n")
    
    try:
        subprocess.run([sys.executable, "src/main.py"], check=False)
    except KeyboardInterrupt:
        pass


def cleanup():
    """Kill background processes."""
    global SHUTDOWN_FLAG
    if SHUTDOWN_FLAG:
        return
    SHUTDOWN_FLAG = True
    
    print("\n🛑 Shutting down...")
    
    for proc in BACKGROUND_PROCESSES:
        if proc and proc.poll() is None:
            try:
                if os.name != 'nt':
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                else:
                    proc.terminate()
                proc.wait(timeout=5)
            except Exception as e:
                print(f"   ⚠️  Error terminating process: {e}")
                try:
                    proc.kill()
                except Exception as kill_err:
                    print(f"   ⚠️  Error killing process: {kill_err}")
    
    print("✅ Stopped\n")


def signal_handler(signum, frame):
    cleanup()
    sys.exit(0)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="🦅 EarlyBird Headless Launcher")
    parser.add_argument("--skip-reset", action="store_true", help="Skip database reset")
    args = parser.parse_args()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print_banner()
    
    try:
        if not check_environment():
            sys.exit(1)
        
        if not init_database(args.skip_reset):
            sys.exit(1)
        
        print("\n[3/3] 🚀 STARTING PROCESSES")
        start_telegram_monitor()
        time.sleep(1)
        
        run_main_pipeline()
        
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
