#!/usr/bin/env python3
"""
Fix paginated sources in Supabase that should use 'single' navigation_mode.

V12.6 Stabilization — Level 1: Config Fix

palembang.tribunnews.com/superball/ returns 147k+ chars of real content via
plain HTTP (AsyncFetcher). It does NOT need Playwright-based paginated scanning.
Forcing it through the paginated path causes it to fail within the 3s timeout,
triggering repeated [BROWSER-MONITOR] Scan failed warnings.

This script updates the Supabase news_sources table to set navigation_mode='single'
for the tribunnews source(s).

Usage:
    python src/utils/fix_paginated_sources.py          # Dry run (preview changes)
    python src/utils/fix_paginated_sources.py --apply   # Apply changes

Author: EarlyBird Team
Date: 2026-03-31
"""

import argparse
import logging
import sys
from pathlib import Path

# Setup path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

env_file = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Sources that should be changed from 'paginated' to 'single'
# Each entry: (URL substring to match, new navigation_mode)
FIXES = [
    ("palembang.tribunnews.com", "single"),
    ("96fmbauru.com.br", "single"),
]


def apply_fixes(dry_run: bool = True) -> int:
    """
    Update navigation_mode for sources in Supabase.

    Args:
        dry_run: If True, only preview changes without applying them.

    Returns:
        Number of sources updated (or would be updated in dry_run mode).
    """
    try:
        from src.database.supabase_provider import SupabaseProvider

        provider = SupabaseProvider()
        if not provider.is_connected():
            logger.error(f"❌ Supabase connection failed: {provider.get_connection_error()}")
            return 0

        # Fetch all news sources
        all_sources = provider.fetch_all_news_sources()
        if not all_sources:
            logger.warning("⚠️ No news sources found in Supabase")
            return 0

        logger.info(f"✅ Found {len(all_sources)} sources in Supabase")

        changes_applied = 0

        for src in all_sources:
            url = src.get("url", "") or src.get("domain", "")
            current_mode = src.get("navigation_mode", "single")
            source_id = src.get("id")

            if not url:
                continue

            # Check if this source matches any of our fixes
            for url_substring, new_mode in FIXES:
                if url_substring in url and current_mode != new_mode:
                    logger.info(
                        f"{'[DRY RUN] ' if dry_run else ''}"
                        f"Changing {url}: navigation_mode '{current_mode}' → '{new_mode}'"
                    )

                    if not dry_run and source_id:
                        try:
                            success = provider.update_news_source(
                                source_id, {"navigation_mode": new_mode}
                            )
                            if success:
                                logger.info(f"✅ Updated: {url}")
                                changes_applied += 1
                            else:
                                logger.warning(f"⚠️ No rows updated for: {url}")
                        except Exception as e:
                            logger.error(f"❌ Failed to update {url}: {e}")
                    else:
                        changes_applied += 1

                    break  # Only apply first matching fix

        if dry_run:
            logger.info(f"\n📋 DRY RUN: {changes_applied} source(s) would be updated.")
            logger.info("Run with --apply to apply changes.")
        else:
            logger.info(f"\n✅ {changes_applied} source(s) updated in Supabase.")

        return changes_applied

    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return 0
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Fix paginated sources in Supabase that should use 'single' navigation_mode"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (default is dry run mode)",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    if dry_run:
        logger.info("🔍 Running in DRY RUN mode (no changes will be made)")
    else:
        logger.info("⚠️ Running in APPLY mode (changes will be written to Supabase)")

    count = apply_fixes(dry_run=dry_run)
    sys.exit(0 if count >= 0 else 1)


if __name__ == "__main__":
    main()
