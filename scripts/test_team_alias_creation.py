#!/usr/bin/env python3
"""
Test TeamAlias Creation with Enrichment

This script tests the TeamAlias creation with automatic enrichment.
It creates a few test TeamAlias records to verify the enrichment system works.

USAGE:
    python scripts/test_team_alias_creation.py
"""

import logging
import sys

# Add parent directory to path
sys.path.insert(0, "/home/linux/Earlybird_Github")

from src.database.db import get_db_context
from src.database.models import TeamAlias
from src.database.team_alias_enrichment import enrich_team_alias_data, get_team_mapping_stats

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def test_enrichment_function():
    """Test the enrichment function directly."""
    logger.info("=" * 80)
    logger.info("Testing Enrichment Function")
    logger.info("=" * 80)

    test_teams = [
        "Manchester United FC",
        "Liverpool FC",
        "Chelsea FC",
        "Arsenal FC",
        "Galatasaray SK",
    ]

    for team_name in test_teams:
        logger.info(f"\nTesting team: {team_name}")
        enriched_data = enrich_team_alias_data(team_name)

        logger.info(f"  Twitter Handle: {enriched_data.get('twitter_handle')}")
        logger.info(f"  Telegram Channel: {enriched_data.get('telegram_channel')}")
        logger.info(f"  FotMob ID: {enriched_data.get('fotmob_id')}")
        logger.info(f"  Country: {enriched_data.get('country')}")
        logger.info(f"  League: {enriched_data.get('league')}")


def test_team_alias_creation():
    """Test creating TeamAlias records with enrichment."""
    logger.info("\n" + "=" * 80)
    logger.info("Testing TeamAlias Creation")
    logger.info("=" * 80)

    test_teams = [
        "Manchester United FC",
        "Liverpool FC",
        "Chelsea FC",
        "Arsenal FC",
        "Galatasaray SK",
    ]

    with get_db_context() as session:
        for team_name in test_teams:
            # Check if already exists
            existing = session.query(TeamAlias).filter(TeamAlias.api_name == team_name).first()
            if existing:
                logger.info(f"\n✓ TeamAlias already exists: {team_name}")
                logger.info(f"  Twitter Handle: {existing.twitter_handle}")
                logger.info(f"  Telegram Channel: {existing.telegram_channel}")
                logger.info(f"  FotMob ID: {existing.fotmob_id}")
                logger.info(f"  Country: {existing.country}")
                logger.info(f"  League: {existing.league}")
            else:
                # Create new TeamAlias with enrichment
                clean_name = team_name.replace(" FC", "").replace(" SK", "").replace(" Club", "")
                enriched_data = enrich_team_alias_data(team_name)

                alias = TeamAlias(
                    api_name=team_name,
                    search_name=clean_name,
                    twitter_handle=enriched_data.get("twitter_handle"),
                    telegram_channel=enriched_data.get("telegram_channel"),
                    fotmob_id=str(enriched_data.get("fotmob_id"))
                    if enriched_data.get("fotmob_id")
                    else None,
                    country=enriched_data.get("country"),
                    league=enriched_data.get("league"),
                )

                session.add(alias)

                # Log enrichment results
                enriched_fields = [k for k, v in enriched_data.items() if v is not None]
                if enriched_fields:
                    logger.info(f"\n✓ Created TeamAlias: {team_name}")
                    logger.info(f"  Enriched fields: {', '.join(enriched_fields)}")
                else:
                    logger.info(f"\n✓ Created TeamAlias: {team_name} (no enrichment data)")


def show_mapping_stats():
    """Show mapping statistics."""
    logger.info("\n" + "=" * 80)
    logger.info("Mapping Statistics")
    logger.info("=" * 80)

    stats = get_team_mapping_stats()
    logger.info(f"  Total Teams: {stats['total_teams']}")
    logger.info(f"  Twitter Handles: {stats['twitter_handles']}")
    logger.info(f"  Telegram Channels: {stats['telegram_channels']}")
    logger.info(f"  FotMob IDs: {stats['fotmob_ids']}")
    logger.info(f"  Countries: {stats['countries']}")
    logger.info(f"  Leagues: {stats['leagues']}")


def main():
    """Main test function."""
    try:
        # Test enrichment function
        test_enrichment_function()

        # Test TeamAlias creation
        test_team_alias_creation()

        # Show mapping stats
        show_mapping_stats()

        logger.info("\n" + "=" * 80)
        logger.info("✅ All tests completed successfully!")
        logger.info("=" * 80)
        return 0
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
