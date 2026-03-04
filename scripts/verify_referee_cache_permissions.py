#!/usr/bin/env python3
"""
Verify referee cache file permissions for VPS deployment.

This script checks that all required directories and files for the referee
boost system have correct permissions for read/write operations on VPS.

Usage:
    python3 scripts/verify_referee_cache_permissions.py

Exit codes:
    0: All permissions are correct
    1: One or more permission issues found
"""

import os
import sys
from pathlib import Path


def verify_directory_permissions(dir_path: Path, description: str) -> bool:
    """
    Verify that a directory exists and has write permissions.

    Args:
        dir_path: Path to the directory
        description: Human-readable description of the directory

    Returns:
        True if permissions are correct, False otherwise
    """
    print(f"\n📁 Checking {description}: {dir_path}")

    # Check if directory exists
    if not dir_path.exists():
        print("   ⚠️  Directory does not exist, creating...")
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"   ✅ Created directory: {dir_path}")
        except PermissionError as e:
            print("   ❌ FAILED: Cannot create directory (permission denied)")
            print(f"      Error: {e}")
            return False
        except Exception as e:
            print("   ❌ FAILED: Unexpected error creating directory")
            print(f"      Error: {e}")
            return False

    # Check if it's actually a directory
    if not dir_path.is_dir():
        print("   ❌ FAILED: Path exists but is not a directory")
        return False

    # Check write permissions by creating a test file
    test_file = dir_path / ".permission_test"
    try:
        test_file.touch()
        test_file.unlink()
        print("   ✅ Write permissions OK")
    except PermissionError:
        print("   ❌ FAILED: No write permissions")
        return False
    except Exception as e:
        print("   ❌ FAILED: Unexpected error testing write permissions")
        print(f"      Error: {e}")
        return False

    # Check directory permissions
    stat_info = dir_path.stat()
    mode = oct(stat_info.st_mode)[-3:]
    print(f"   📋 Permissions: {mode}")

    # Warn if permissions are too restrictive
    if int(mode[0]) < 7:  # Owner should have read/write/execute
        print(f"   ⚠️  WARNING: Owner permissions may be too restrictive ({mode})")

    return True


def verify_file_permissions(file_path: Path, description: str, must_exist: bool = True) -> bool:
    """
    Verify that a file has correct permissions.

    Args:
        file_path: Path to the file
        description: Human-readable description of the file
        must_exist: If True, file must exist; if False, only check parent dir

    Returns:
        True if permissions are correct, False otherwise
    """
    print(f"\n📄 Checking {description}: {file_path}")

    if must_exist and not file_path.exists():
        print("   ⚠️  File does not exist (may be created on first run)")
        # Check if parent directory is writable
        parent = file_path.parent
        if not verify_directory_permissions(parent, f"parent directory for {description}"):
            return False
        return True

    if file_path.exists():
        # Check if it's actually a file
        if not file_path.is_file():
            print("   ❌ FAILED: Path exists but is not a file")
            return False

        # Check file permissions
        stat_info = file_path.stat()
        mode = oct(stat_info.st_mode)[-3:]
        print(f"   📋 Permissions: {mode}")

        # Check read permissions
        if not os.access(file_path, os.R_OK):
            print("   ❌ FAILED: No read permissions")
            return False
        else:
            print("   ✅ Read permissions OK")

        # Check write permissions
        if not os.access(file_path, os.W_OK):
            print("   ❌ FAILED: No write permissions")
            return False
        else:
            print("   ✅ Write permissions OK")

    return True


def main():
    """Main verification function."""
    print("=" * 70)
    print("REFEREE CACHE PERMISSIONS VERIFICATION")
    print("=" * 70)
    print("\nVerifying permissions for referee boost system directories and files...")

    all_passed = True

    # Verify cache directory
    cache_dir = Path("data/cache")
    if not verify_directory_permissions(cache_dir, "cache directory"):
        all_passed = False

    # Verify cache file
    cache_file = cache_dir / "referee_stats.json"
    if not verify_file_permissions(cache_file, "referee cache file", must_exist=False):
        all_passed = False

    # Verify metrics directory
    metrics_dir = Path("data/metrics")
    if not verify_directory_permissions(metrics_dir, "metrics directory"):
        all_passed = False

    # Verify metrics files
    cache_metrics_file = metrics_dir / "referee_cache_metrics.json"
    if not verify_file_permissions(cache_metrics_file, "cache metrics file", must_exist=False):
        all_passed = False

    influence_metrics_file = metrics_dir / "referee_influence_metrics.json"
    if not verify_file_permissions(
        influence_metrics_file, "influence metrics file", must_exist=False
    ):
        all_passed = False

    # Verify logs directory
    logs_dir = Path("logs")
    if not verify_directory_permissions(logs_dir, "logs directory"):
        all_passed = False

    # Verify log file
    log_file = logs_dir / "referee_boost.log"
    if not verify_file_permissions(log_file, "referee boost log file", must_exist=False):
        all_passed = False

    # Print summary
    print("\n" + "=" * 70)
    if all_passed:
        print("✅ ALL PERMISSIONS VERIFIED SUCCESSFULLY")
        print("=" * 70)
        print("\nThe referee boost system is ready for VPS deployment.")
        print("All required directories have correct read/write permissions.")
        return 0
    else:
        print("❌ PERMISSION VERIFICATION FAILED")
        print("=" * 70)
        print("\nSome directories or files have incorrect permissions.")
        print("Please fix the issues above before deploying to VPS.")
        print("\nCommon fixes:")
        print("  - Ensure the user running the bot owns the directories")
        print("  - Run: chmod -R 755 data/ logs/")
        print("  - Run: chown -R <user>:<group> data/ logs/")
        return 1


if __name__ == "__main__":
    sys.exit(main())
