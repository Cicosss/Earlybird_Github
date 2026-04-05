#!/usr/bin/env python3
"""
Database Initialization Script

This script initializes the EarlyBird database by creating all required tables.
Safe to run multiple times (idempotent).

USAGE:
    python scripts/init_database.py
"""

import logging
import sys

# Add parent directory to path
sys.path.insert(0, "/home/linux/Earlybird_Github")

from src.database.models import init_db

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    """Main initialization function."""
    logger.info("=" * 80)
    logger.info("EarlyBird Database Initialization")
    logger.info("=" * 80)

    try:
        init_db()
        logger.info("✅ Database initialized successfully!")
        return 0
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
