"""EarlyBird Database Package

Database models, migrations, and connection management.
"""

# NOTE: Package-level exports removed to avoid loading heavy modules when importing from submodules.
# All imports should be done directly from modules:
# - from src.database.models import Match (not from src.database import Match)
# - from src.database.db import get_db_context (not from src.database import get_db_context)
# - from src.database.migration import check_and_migrate (not from src.database import check_and_migrate)

__all__ = []
