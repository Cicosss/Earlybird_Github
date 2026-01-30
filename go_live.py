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
    
    # Required variables for main pipeline
    required = ["OPENROUTER_API_KEY", "ODDS_API_KEY", "SERPER_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = [v for v in required if not os.getenv(v) or os.getenv(v, "").startswith("your_")]
    
    if missing:
        print(f"   ❌ Missing: {', '.join(missing)}")
        return False
    
    print("   ✅ All required variables configured")
    
    # Check optional Telegram monitoring (user client for squad scraping)
    if os.getenv("TELEGRAM_API_ID") and os.getenv("TELEGRAM_API_HASH"):
        print("   ✅ Telegram monitoring enabled (user client)")
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
    if not os.getenv("TELEGRAM_API_ID") or not os.getenv("TELEGRAM_API_HASH"):
        print("   ⚠️  Telegram Monitor disabled (missing API_ID/HASH)")
        return None
    
    if not Path("run_telegram_monitor.py").exists():
        print("   ⚠️  Telegram Monitor script not found")
        return None
    
    try:
        # Open log file with proper context management
        log_file = open("telegram_monitor.log", "a")
        process = subprocess.Popen(
            [sys.executable, "run_telegram_monitor.py"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid if os.name != 'nt' else None
        )
        # Store file handle for cleanup
        process.log_file = log_file
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
        result = subprocess.run([sys.executable, "src/main.py"], check=False)
        # Check if main pipeline exited with error
        if result.returncode != 0:
            print(f"\n⚠️  Main pipeline exited with code {result.returncode}")
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n❌ Error running main pipeline: {e}")


def cleanup():
    """Kill background processes and close file handles."""
    global SHUTDOWN_FLAG
    if SHUTDOWN_FLAG:
        return
    SHUTDOWN_FLAG = True
    
    print("\n🛑 Shutting down...")
    
    for proc in BACKGROUND_PROCESSES:
        if proc and proc.poll() is None:
            try:
                # Try graceful termination first
                if os.name != 'nt':
                    # Unix: kill process group
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    except (ProcessLookupError, OSError):
                        # Process might already be gone
                        pass
                else:
                    # Windows: terminate process
                    proc.terminate()
                
                # Wait for process to terminate (with timeout handling)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if graceful termination failed
                    try:
                        if os.name != 'nt':
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        else:
                            proc.kill()
                    except (ProcessLookupError, OSError):
                        pass
            except Exception as e:
                print(f"   ⚠️  Error terminating process: {e}")
        
        # Close log file handle if exists
        if hasattr(proc, 'log_file') and proc.log_file:
            try:
                proc.log_file.close()
            except Exception as e:
                print(f"   ⚠️  Error closing log file: {e}")
    
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
