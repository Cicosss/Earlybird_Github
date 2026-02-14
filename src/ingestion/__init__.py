"""EarlyBird Ingestion Package

Data ingestion from external sources (APIs, scrapers, etc.).
"""

from .data_provider import get_data_provider
from .ingest_fixtures import ingest_fixtures
from .league_manager import get_active_niche_leagues, is_elite_league
from .search_provider import SearchProvider, get_search_provider
from .brave_provider import BraveSearchProvider, get_brave_provider
from .tavily_provider import TavilyProvider, get_tavily_provider
from .perplexity_provider import PerplexityProvider, get_perplexity_provider
from .mediastack_provider import MediastackProvider, get_mediastack_provider

__all__ = [
    "get_data_provider",
    "ingest_fixtures",
    "get_active_niche_leagues",
    "is_elite_league",
    "SearchProvider",
    "get_search_provider",
    "BraveSearchProvider",
    "get_brave_provider",
    "TavilyProvider",
    "get_tavily_provider",
    "PerplexityProvider",
    "get_perplexity_provider",
    "MediastackProvider",
    "get_mediastack_provider",
]
