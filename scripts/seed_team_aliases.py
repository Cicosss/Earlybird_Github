#!/usr/bin/env python3
"""
TeamAlias Seeding Script

This script seeds/enriches existing TeamAlias records with missing data:
- Twitter handles
- Telegram channels
- FotMob IDs
- Country information
- League information

USAGE:
    python scripts/seed_team_aliases.py [--dry-run] [--verbose]

OPTIONS:
    --dry-run: Show what would be changed without making changes
    --verbose: Show detailed information for each team
"""

import argparse
import logging
import sys
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, "/home/linux/Earlybird_Github")

from src.database.db import get_db_context
from src.database.models import TeamAlias
from src.database.team_alias_enrichment import (
    enrich_team_alias_data,
    get_team_mapping_stats,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_existing_team_aliases() -> List[TeamAlias]:
    """
    Get all existing TeamAlias records from database.

    Returns:
        List of TeamAlias objects
    """
    with get_db_context() as session:
        aliases = session.query(TeamAlias).all()
        return aliases


def analyze_missing_fields(aliases: List[TeamAlias]) -> Dict[str, int]:
    """
    Analyze which fields are missing from TeamAlias records.

    Args:
        aliases: List of TeamAlias objects

    Returns:
        Dictionary with counts of missing fields
    """
    missing = {
        "twitter_handle": 0,
        "telegram_channel": 0,
        "fotmob_id": 0,
        "country": 0,
        "league": 0,
    }

    for alias in aliases:
        if not alias.twitter_handle:
            missing["twitter_handle"] += 1
        if not alias.telegram_channel:
            missing["telegram_channel"] += 1
        if not alias.fotmob_id:
            missing["fotmob_id"] += 1
        if not alias.country:
            missing["country"] += 1
        if not alias.league:
            missing["league"] += 1

    return missing


def enrich_team_alias(
    alias: TeamAlias, enriched_data: Dict, dry_run: bool = False, verbose: bool = False
) -> Tuple[bool, Dict[str, str]]:
    """
    Enrich a single TeamAlias with missing data.

    Args:
        alias: TeamAlias object to enrich
        enriched_data: Dictionary with enriched data
        dry_run: If True, don't make changes
        verbose: If True, show detailed information

    Returns:
        Tuple of (was_updated, changes_dict)
    """
    changes = {}
    was_updated = False

    # Check each field
    if not alias.twitter_handle and enriched_data.get("twitter_handle"):
        changes["twitter_handle"] = enriched_data["twitter_handle"]
        was_updated = True

    if not alias.telegram_channel and enriched_data.get("telegram_channel"):
        changes["telegram_channel"] = enriched_data["telegram_channel"]
        was_updated = True

    if not alias.fotmob_id and enriched_data.get("fotmob_id"):
        changes["fotmob_id"] = str(enriched_data["fotmob_id"])
        was_updated = True

    if not alias.country and enriched_data.get("country"):
        changes["country"] = enriched_data["country"]
        was_updated = True

    if not alias.league and enriched_data.get("league"):
        changes["league"] = enriched_data["league"]
        was_updated = True

    # Apply changes if not dry run
    if was_updated and not dry_run:
        for field, value in changes.items():
            setattr(alias, field, value)

    return was_updated, changes


def seed_team_aliases(dry_run: bool = False, verbose: bool = False) -> None:
    """
    Main seeding function.

    Args:
        dry_run: If True, show what would be changed without making changes
        verbose: If True, show detailed information for each team
    """
    logger.info("=" * 80)
    logger.info("TeamAlias Seeding Script")
    logger.info("=" * 80)

    if dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
    else:
        logger.info("LIVE MODE - Changes will be applied to database")

    logger.info("")

    # Get mapping statistics
    logger.info("Mapping Statistics:")
    stats = get_team_mapping_stats()
    for key, value in stats.items():
        logger.info(f"  {key.replace('_', ' ').title()}: {value}")
    logger.info("")

    # Get existing TeamAlias records
    logger.info("Loading existing TeamAlias records...")
    aliases = get_existing_team_aliases()
    logger.info(f"Found {len(aliases)} TeamAlias records in database")
    logger.info("")

    # Analyze missing fields
    logger.info("Analyzing missing fields:")
    missing = analyze_missing_fields(aliases)
    for field, count in missing.items():
        percentage = (count / len(aliases)) * 100 if aliases else 0
        logger.info(
            f"  {field.replace('_', ' ').title()}: {count}/{len(aliases)} ({percentage:.1f}%)"
        )
    logger.info("")

    # Enrich each TeamAlias
    logger.info("Enriching TeamAlias records...")
    logger.info("")

    updated_count = 0
    no_data_count = 0
    already_complete_count = 0

    for alias in aliases:
        # Get enriched data for this team
        enriched_data = enrich_team_alias_data(alias.api_name)

        # Check if any enrichment data is available
        has_enrichment_data = any(enriched_data.values())

        if not has_enrichment_data:
            no_data_count += 1
            if verbose:
                logger.info(f"  ❌ {alias.api_name}: No enrichment data available")
            continue

        # Enrich the TeamAlias
        was_updated, changes = enrich_team_alias(alias, enriched_data, dry_run, verbose)

        if was_updated:
            updated_count += 1
            if verbose:
                logger.info(f"  ✅ {alias.api_name}: Updated {len(changes)} fields")
                for field, value in changes.items():
                    logger.info(f"      - {field}: {value}")
        else:
            already_complete_count += 1
            if verbose:
                logger.info(f"  ℹ️  {alias.api_name}: Already complete")

    # Summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("Summary:")
    logger.info("=" * 80)
    logger.info(f"  Total TeamAlias records: {len(aliases)}")
    logger.info(f"  Records to update: {updated_count}")
    logger.info(f"  Records already complete: {already_complete_count}")
    logger.info(f"  Records with no enrichment data: {no_data_count}")
    logger.info("")

    if dry_run:
        logger.info("DRY RUN COMPLETE - No changes were made to the database")
        logger.info("Run without --dry-run to apply the changes")
    else:
        logger.info("SEEDING COMPLETE - Changes have been applied to the database")

    logger.info("=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Seed TeamAlias records with missing data")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be changed without making changes"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Show detailed information for each team"
    )

    args = parser.parse_args()

    try:
        seed_team_aliases(dry_run=args.dry_run, verbose=args.verbose)
    except Exception as e:
        logger.error(f"Error during seeding: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
