"""EarlyBird Ingestion Package

Data ingestion from external sources (APIs, scrapers, etc.).
"""

# NOTE: Package-level exports removed to avoid loading heavy modules when importing from submodules.
# All imports should be done directly from modules:
# - from src.ingestion.brave_provider import BraveSearchProvider (not from src.ingestion import BraveSearchProvider)
# - from src.ingestion.data_provider import get_data_provider (not from src.ingestion import get_data_provider)
# - from src.ingestion.ingest_fixtures import ingest_fixtures (not from src.ingestion import ingest_fixtures)
# - from src.ingestion.league_manager import get_active_niche_leagues (not from src.ingestion import get_active_niche_leagues)
# - from src.ingestion.mediastack_provider import MediastackProvider (not from src.ingestion import MediastackProvider)
# - from src.ingestion.perplexity_provider import PerplexityProvider (not from src.ingestion import PerplexityProvider)
# - from src.ingestion.search_provider import SearchProvider (not from src.ingestion import SearchProvider)
# - from src.ingestion.tavily_provider import TavilyProvider (not from src.ingestion import TavilyProvider)

__all__ = []
