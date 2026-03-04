#!/usr/bin/env python3
"""
Python wrapper to execute the FotMob Ruby test script.
This allows us to test the Ruby fotmob gem from within the Python project.
"""

import subprocess
import sys
from pathlib import Path


def run_ruby_test():
    """Execute the Ruby test script and capture its output."""
    ruby_script = Path(__file__).parent / "test_fotmob_ruby.rb"

    if not ruby_script.exists():
        print(f"❌ ERROR: Ruby script not found at {ruby_script}")
        return False

    print("=" * 60)
    print("FOTMOB RUBY TEST - PYTHON WRAPPER")
    print("=" * 60)
    print(f"Executing Ruby script: {ruby_script}")
    print()

    try:
        # Run the Ruby script and capture output
        result = subprocess.run(
            ["ruby", str(ruby_script)], capture_output=True, text=True, timeout=30
        )

        # Print stdout
        if result.stdout:
            print(result.stdout)

        # Print stderr if there's any error output
        if result.stderr:
            print("\n" + "=" * 60)
            print("STDERR OUTPUT:")
            print("=" * 60)
            print(result.stderr)

        # Check exit code
        print("\n" + "=" * 60)
        print(f"Ruby script exited with code: {result.returncode}")
        print("=" * 60)

        if result.returncode == 0:
            print("✅ Ruby script executed successfully")
            return True
        else:
            print("❌ Ruby script failed with non-zero exit code")
            return False

    except subprocess.TimeoutExpired:
        print("❌ ERROR: Ruby script timed out after 30 seconds")
        return False
    except FileNotFoundError:
        print("❌ ERROR: Ruby is not installed or not in PATH")
        print("Install Ruby with: sudo apt-get install ruby ruby-dev")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def main():
    """Main entry point."""
    success = run_ruby_test()

    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)

    if success:
        print("The Ruby test completed successfully.")
        print("Check the output above to see if FotMob requests succeeded or failed.")
    else:
        print("The Ruby test failed to execute.")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
