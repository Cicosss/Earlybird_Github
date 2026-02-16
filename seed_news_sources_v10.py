#!/usr/bin/env python3
"""
Autonomous Granular Seeding - Multi-Source Expansion V10.1

This script parses intelligence sources and seeds them into Supabase with:
- Path Fidelity: Preserves full domain paths for league-specific sources
- Geographic Veto: Processes only LATAM, ASIA, and AFRICA
- Tier Identification: Classifies leagues as Tier A (main) or Tier B (second divisions)
- Smart UPSERT: Uses (league_id, domain) as unique key
"""

import logging

# Setup path
import os
import re
import sys
from typing import Any
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

try:
    from src.database.supabase_provider import get_supabase
except ImportError:
    print("ERROR: Could not import Supabase provider")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ============================================
# RAW DATA TO BE INTEGRATED
# ============================================
RAW_SOURCES = [
    # LATAM - Peru
    {
        "continent": "LATAM",
        "country": "Peru",
        "league": "Liga 2 (Segunda División de Perú)",
        "source_name": "FutbolPeruano.com – Liga 2",
        "url": "https://www.futbolperuano.com/liga-2/noticias/",
        "tier": "Tier B",
    },
    {
        "continent": "LATAM",
        "country": "Peru",
        "league": "Liga 2 (Segunda División de Perú)",
        "source_name": "Liga2.pe (sito ufficiale)",
        "url": "https://liga2.pe",
        "tier": "Tier B",
    },
    # LATAM - Chile
    {
        "continent": "LATAM",
        "country": "Chile",
        "league": "Primera B de Chile (Liga de Ascenso)",
        "source_name": "PrimeraBChile.cl",
        "url": "https://primerabchile.cl/primera-b-chile/",
        "tier": "Tier B",
    },
    {
        "continent": "LATAM",
        "country": "Chile",
        "league": "Primera B de Chile",
        "source_name": "Enascenso.cl",
        "url": "https://enascenso.cl",
        "tier": "Tier B",
    },
    # LATAM - Uruguay
    {
        "continent": "LATAM",
        "country": "Uruguay",
        "league": "Segunda División Profesional (Uruguay)",
        "source_name": "La Web Deportiva Uruguaya – 2da División",
        "url": "https://www.lawebdeportivauruguaya.com.uy/category/futbol-uruguayo/2da-division/",
        "tier": "Tier B",
    },
    {
        "continent": "LATAM",
        "country": "Uruguay",
        "league": "Segunda División Profesional (Uruguay)",
        "source_name": "FútbolUy (Montevideo.com.uy)",
        "url": "https://www.montevideo.com.uy/categoria/Deportes-94",
        "tier": "Tier B",
    },
    # LATAM - Colombia
    {
        "continent": "LATAM",
        "country": "Colombia",
        "league": "Categoría Primera B (Torneo BetPlay)",
        "source_name": "Colombia.com – Torneo de Ascenso",
        "url": "https://www.colombia.com/futbol/",
        "tier": "Tier B",
    },
    # LATAM - Ecuador
    {
        "continent": "LATAM",
        "country": "Ecuador",
        "league": "Serie B de Ecuador",
        "source_name": "FutbolEcuador.com – Serie B",
        "url": "https://www.futbolecuador.com/etiqueta/serie-b",
        "tier": "Tier B",
    },
    # LATAM - Panama
    {
        "continent": "LATAM",
        "country": "Panama",
        "league": "Liga Panameña de Fútbol (LPF)",
        "source_name": "LPF – Liga Panameña de Fútbol (sito ufficiale)",
        "url": "https://lpf.com.pa",
        "tier": "Tier A",
    },
    # LATAM - Brazil
    {
        "continent": "LATAM",
        "country": "Brazil",
        "league": "Campeonato Brasileiro Série B",
        "source_name": "FutebolInterior – Brasileirão Série B",
        "url": "https://www.futebolinterior.com.br/ultimas-noticias/",
        "tier": "Tier B",
    },
    # ASIA - China
    {
        "continent": "ASIA",
        "country": "China",
        "league": "China League One (Chinese Jia League)",
        "source_name": "Wild East Football – China League One",
        "url": "https://wildeastfootball.org/topics/competitions/china-league-one/",
        "tier": "Tier B",
    },
    # ASIA - Japan
    {
        "continent": "ASIA",
        "country": "Japan",
        "league": "J2 League",
        "source_name": "DailySports – J.League 2",
        "url": "https://dailysports.net/tournaments/japan-j-league-2/",
        "tier": "Tier B",
    },
    # ASIA - Thailand
    {
        "continent": "ASIA",
        "country": "Thailand",
        "league": "Thai League 2",
        "source_name": "Thai League (sito ufficiale)",
        "url": "https://thaileague.co.th",
        "tier": "Tier B",
    },
    {
        "continent": "ASIA",
        "country": "Thailand",
        "league": "Thai League 2",
        "source_name": "FootyStats – Thai League 2",
        "url": "https://footystats.org/thailand/thai-league-2",
        "tier": "Tier B",
    },
    # ASIA - Turkey
    {
        "continent": "ASIA",
        "country": "Turkey",
        "league": "TFF 1. Lig",
        "source_name": "DailySports – Turkey 1. Lig",
        "url": "https://dailysports.net/news/football/",
        "tier": "Tier B",
    },
    # ASIA - Malaysia
    {
        "continent": "ASIA",
        "country": "Malaysia",
        "league": "Malaysia Premier League (storica seconda serie) & leghe nazionali",
        "source_name": "SoccerDesk – Malaysia Premier League",
        "url": "https://www.soccerdesk.com/football/malaysia/premier-league",
        "tier": "Tier B",
    },
    # ASIA - India
    {
        "continent": "ASIA",
        "country": "India",
        "league": "I-League (secondo livello India)",
        "source_name": "Times of India – I-League",
        "url": "https://timesofindia.indiatimes.com/sports/football/i-league",
        "tier": "Tier B",
    },
    {
        "continent": "ASIA",
        "country": "India",
        "league": "I-League",
        "source_name": "NDTV Sports – I-League",
        "url": "https://sports.ndtv.com/ileague/news",
        "tier": "Tier B",
    },
    {
        "continent": "ASIA",
        "country": "India",
        "league": "I-League",
        "source_name": "The Bridge – I-League",
        "url": "https://thebridge.in/i-league",
        "tier": "Tier B",
    },
    # AFRICA - Tunisia
    {
        "continent": "AFRICA",
        "country": "Tunisia",
        "league": "Ligue 1 Professionnelle & Ligue 2",
        "source_name": "Kawarji.com",
        "url": "https://www.kawarji.com/actualites",
        "tier": "Tier A",
    },
    # AFRICA - Algeria
    {
        "continent": "AFRICA",
        "country": "Algeria",
        "league": "Ligue 1 & competizioni algerine",
        "source_name": "Le Buteur",
        "url": "https://www.lebuteur.com/article/index?cat=26",
        "tier": "Tier A",
    },
    # AFRICA - Morocco
    {
        "continent": "AFRICA",
        "country": "Morocco",
        "league": "Botola Pro & competizioni marocchine",
        "source_name": "Hesport",
        "url": "https://www.hesport.com",
        "tier": "Tier A",
    },
    # AFRICA - Ghana
    {
        "continent": "AFRICA",
        "country": "Ghana",
        "league": "Ghana Premier League & Division One",
        "source_name": "GHANAsoccernet",
        "url": "https://ghanasoccernet.com",
        "tier": "Tier A",
    },
    {
        "continent": "AFRICA",
        "country": "Ghana",
        "league": "Ghana Premier League",
        "source_name": "GHPL Live",
        "url": "https://www.ghanaleaguelive.com",
        "tier": "Tier A",
    },
    {
        "continent": "AFRICA",
        "country": "Ghana",
        "league": "Premier League & Division One (regolamentazione)",
        "source_name": "Ghana Football Association",
        "url": "https://www.ghanafa.org",
        "tier": "Tier A",
    },
    # AFRICA - Nigeria
    {
        "continent": "AFRICA",
        "country": "Nigeria",
        "league": "Nigeria Premier Football League (NPFL)",
        "source_name": "Nigeria Premier Football League (sito ufficiale)",
        "url": "https://npfl.com.ng",
        "tier": "Tier A",
    },
    {
        "continent": "AFRICA",
        "country": "Nigeria",
        "league": "NPFL & calciatori nigeriani",
        "source_name": "Soccernet.ng – NPFL",
        "url": "https://soccernet.ng/category/npfl",
        "tier": "Tier A",
    },
    # AFRICA - Egypt
    {
        "continent": "AFRICA",
        "country": "Egypt",
        "league": "Egyptian Premier League & coppe",
        "source_name": "FilGoal.com",
        "url": "https://www.filgoal.com/articles",
        "tier": "Tier A",
    },
    # AFRICA - South Africa
    {
        "continent": "AFRICA",
        "country": "South Africa",
        "league": "Premier Soccer League (PSL)",
        "source_name": "iDiski Times",
        "url": "https://www.idiskitimes.co.za/category/local/",
        "tier": "Tier A",
    },
]


# ============================================
# LEAGUE MAPPING TO ODDS-API KEYS
# ============================================
LEAGUE_API_KEY_MAPPING = {
    # Peru
    "Liga 2 (Segunda División de Perú)": "soccer_peru_liga_2",
    # Chile
    "Primera B de Chile (Liga de Ascenso)": "soccer_chile_primera_b",
    "Primera B de Chile": "soccer_chile_primera_b",
    # Uruguay
    "Segunda División Profesional (Uruguay)": "soccer_uruguay_segunda_division",
    # Colombia
    "Categoría Primera B (Torneo BetPlay)": "soccer_colombia_primera_b",
    # Ecuador
    "Serie B de Ecuador": "soccer_ecuador_serie_b",
    # Panama
    "Liga Panameña de Fútbol (LPF)": "soccer_panama_lpf",
    # Brazil
    "Campeonato Brasileiro Série B": "soccer_brazil_serie_b",
    # China
    "China League One (Chinese Jia League)": "soccer_china_league_one",
    # Japan
    "J2 League": "soccer_japan_j2_league",
    # Thailand
    "Thai League 2": "soccer_thailand_thai_league_2",
    # Turkey
    "TFF 1. Lig": "soccer_turkey_first_lig",
    # Malaysia
    "Malaysia Premier League (storica seconda serie) & leghe nazionali": "soccer_malaysia_premier_league",
    # India
    "I-League (secondo livello India)": "soccer_india_i_league",
    "I-League": "soccer_india_i_league",
    # Tunisia
    "Ligue 1 Professionnelle & Ligue 2": "soccer_tunisia_ligue_professionnelle_1",
    # Algeria
    "Ligue 1 & competizioni algerine": "soccer_algeria_ligue_professionnelle_1",
    # Morocco
    "Botola Pro & competizioni marocchine": "soccer_morocco_botola_pro",
    # Ghana
    "Ghana Premier League & Division One": "soccer_ghana_premier_league",
    "Ghana Premier League": "soccer_ghana_premier_league",
    "Premier League & Division One (regolamentazione)": "soccer_ghana_premier_league",
    # Nigeria
    "Nigeria Premier Football League (NPFL)": "soccer_nigeria_professional_football_league",
    "NPFL & calciatori nigeriani": "soccer_nigeria_professional_football_league",
    # Egypt
    "Egyptian Premier League & coppe": "soccer_egypt_premier_league",
    # South Africa
    "Premier Soccer League (PSL)": "soccer_south_africa_psl",
}


# ============================================
# URL NORMALIZATION
# ============================================
def normalize_url(url: str) -> str:
    """
    Normalize URL by stripping protocols, www, and trailing slashes.
    Preserves full path for league-specific sources.

    Args:
        url: Raw URL string

    Returns:
        Normalized domain/path string
    """
    # Strip protocol
    url = re.sub(r"^https?://", "", url)

    # Strip www.
    url = re.sub(r"^www\.", "", url)

    # Strip trailing slash
    url = url.rstrip("/")

    return url


# ============================================
# DATABASE OPERATIONS
# ============================================
def find_or_create_continent(supabase, continent_name: str) -> dict[str, Any] | None:
    """
    Find or create a continent.

    Args:
        supabase: SupabaseProvider instance
        continent_name: Continent name (LATAM, ASIA, AFRICA)

    Returns:
        Continent record or None
    """
    continents = supabase.fetch_continents()

    for continent in continents:
        if continent.get("name") == continent_name:
            logger.info(f"✓ Found continent: {continent_name}")
            return continent

    logger.warning(f"✗ Continent not found: {continent_name}")
    return None


def find_or_create_country(supabase, continent_id: str, country_name: str) -> dict[str, Any] | None:
    """
    Find or create a country.

    Args:
        supabase: SupabaseProvider instance
        continent_id: Continent UUID
        country_name: Country name

    Returns:
        Country record or None
    """
    countries = supabase.fetch_countries(continent_id)

    for country in countries:
        if country.get("name") == country_name:
            logger.info(f"  ✓ Found country: {country_name}")
            return country

    # Country not found, try to create it
    logger.warning(f"  ✗ Country not found: {country_name} - attempting to create")

    # Map country names to ISO codes
    COUNTRY_ISO_MAPPING = {
        "Ecuador": "EC",
        "Panama": "PA",
        "Thailand": "TH",
        "Malaysia": "MY",
        "India": "IN",
    }

    iso_code = COUNTRY_ISO_MAPPING.get(country_name)
    if not iso_code:
        logger.error(f"    ✗ No ISO code mapping for country: {country_name}")
        return None

    try:
        new_country = {
            "id": str(uuid4()),
            "continent_id": continent_id,
            "name": country_name,
            "iso_code": iso_code,
        }

        # Insert into Supabase
        response = supabase._client.table("countries").insert(new_country).execute()

        if response.data:
            logger.info(f"  ✓ Created country: {country_name} ({iso_code})")
            return response.data[0]
        else:
            logger.error(f"    ✗ Failed to create country: {country_name}")
            return None

    except Exception as e:
        logger.error(f"    ✗ Error creating country {country_name}: {e}")
        return None


def find_or_create_league(
    supabase, country_id: str, league_name: str, tier: str
) -> dict[str, Any] | None:
    """
    Find or create a league.

    Args:
        supabase: SupabaseProvider instance
        country_id: Country UUID
        league_name: League name
        tier: Tier classification (Tier A or Tier B)

    Returns:
        League record or None
    """
    # Get API key first
    api_key = LEAGUE_API_KEY_MAPPING.get(league_name)
    if not api_key:
        logger.warning(f"    ✗ No API key mapping for league: {league_name}")
        return None

    # Try to find existing league by API key (more reliable than tier_name match)
    try:
        response = supabase._client.table("leagues").select("*").eq("api_key", api_key).execute()

        if response.data and len(response.data) > 0:
            logger.info(f"    ✓ Found league by API key: {league_name} ({api_key})")
            return response.data[0]
    except Exception as e:
        logger.debug(f"    Debug: Could not query leagues by API key: {e}")

    # Fallback: Try to find by tier_name
    leagues = supabase.fetch_leagues(country_id)

    for league in leagues:
        if league.get("tier_name") == league_name:
            logger.info(f"    ✓ Found league by tier_name: {league_name}")
            return league

    # Create new league
    priority = 1 if tier == "Tier A" else 2

    try:
        new_league = {
            "id": str(uuid4()),
            "country_id": country_id,
            "api_key": api_key,
            "tier_name": league_name,
            "priority": priority,
            "is_active": False,  # Default to inactive, can be activated later
        }

        # Insert into Supabase
        response = supabase._client.table("leagues").insert(new_league).execute()

        if response.data:
            logger.info(f"    ✓ Created league: {league_name} ({api_key})")
            return response.data[0]
        else:
            logger.error(f"    ✗ Failed to create league: {league_name}")
            return None

    except Exception as e:
        # Check if it's a duplicate key error (league already exists)
        if "duplicate key" in str(e).lower() or "23505" in str(e):
            # Try to fetch the existing league again
            try:
                response = (
                    supabase._client.table("leagues").select("*").eq("api_key", api_key).execute()
                )
                if response.data and len(response.data) > 0:
                    logger.info(
                        f"    ✓ Found existing league (duplicate error): {league_name} ({api_key})"
                    )
                    return response.data[0]
            except Exception as retry_e:
                logger.error(f"    ✗ Error fetching existing league after duplicate: {retry_e}")

        logger.error(f"    ✗ Error creating league {league_name}: {e}")
        return None


def upsert_news_source(supabase, league_id: str, domain: str, source_name: str) -> bool:
    """
    Upsert a news source using (league_id, domain) as unique key.

    Args:
        supabase: SupabaseProvider instance
        league_id: League UUID
        domain: Normalized domain/path
        source_name: Source name for description

    Returns:
        True if successful, False otherwise
    """
    try:
        # Check if source already exists
        existing_sources = supabase.fetch_sources(league_id)

        for source in existing_sources:
            if source.get("domain") == domain:
                logger.info(f"      ✓ Source already exists: {domain}")
                return True

        # Insert new source
        new_source = {
            "id": str(uuid4()),
            "league_id": league_id,
            "domain": domain,
            "language_iso": "en",  # Default to English, can be updated later
            "is_active": True,
        }

        response = supabase._client.table("news_sources").insert(new_source).execute()

        if response.data:
            logger.info(f"      ✓ Created source: {domain}")
            return True
        else:
            logger.error(f"      ✗ Failed to create source: {domain}")
            return False

    except Exception as e:
        logger.error(f"      ✗ Error upserting source {domain}: {e}")
        return False


# ============================================
# MAIN SEEDING LOGIC
# ============================================
def main():
    """Main seeding function."""
    logger.info("=" * 80)
    logger.info("AUTONOMOUS GRANULAR SEEDING - MULTI-SOURCE EXPANSION V10.1")
    logger.info("=" * 80)

    # Get Supabase provider
    supabase = get_supabase()

    if not supabase.is_connected():
        logger.error("✗ Supabase connection failed")
        return

    logger.info("✓ Connected to Supabase")

    # Track statistics
    stats = {
        "total": len(RAW_SOURCES),
        "processed": 0,
        "skipped": 0,
        "created": 0,
        "existing": 0,
        "errors": 0,
    }

    # Track results for report
    results = []

    # Process each source
    for i, source_data in enumerate(RAW_SOURCES, 1):
        continent_name = source_data["continent"]
        country_name = source_data["country"]
        league_name = source_data["league"]
        source_name = source_data["source_name"]
        url = source_data["url"]
        tier = source_data["tier"]

        logger.info(f"\n[{i}/{len(RAW_SOURCES)}] Processing: {source_name}")

        # Geographic Veto: Skip non-LATAM/ASIA/AFRICA
        if continent_name not in ["LATAM", "ASIA", "AFRICA"]:
            logger.warning(f"  ✗ Skipped (geographic veto): {continent_name}")
            stats["skipped"] += 1
            continue

        # Find or create continent
        continent = find_or_create_continent(supabase, continent_name)
        if not continent:
            logger.error(f"  ✗ Failed to find continent: {continent_name}")
            stats["errors"] += 1
            results.append(
                {
                    "continent": continent_name,
                    "country": country_name,
                    "league": f"{league_name} ({tier})",
                    "source": normalize_url(url),
                    "status": "ERROR - Continent not found",
                }
            )
            continue

        # Find or create country
        country = find_or_create_country(supabase, continent["id"], country_name)
        if not country:
            logger.error(f"  ✗ Failed to find country: {country_name}")
            stats["errors"] += 1
            results.append(
                {
                    "continent": continent_name,
                    "country": country_name,
                    "league": f"{league_name} ({tier})",
                    "source": normalize_url(url),
                    "status": "ERROR - Country not found",
                }
            )
            continue

        # Find or create league
        league = find_or_create_league(supabase, country["id"], league_name, tier)
        if not league:
            logger.error(f"  ✗ Failed to find/create league: {league_name}")
            stats["errors"] += 1
            results.append(
                {
                    "continent": continent_name,
                    "country": country_name,
                    "league": f"{league_name} ({tier})",
                    "source": normalize_url(url),
                    "status": "ERROR - League not found/created",
                }
            )
            continue

        # Upsert news source
        domain = normalize_url(url)
        success = upsert_news_source(supabase, league["id"], domain, source_name)

        if success:
            stats["processed"] += 1
            # Check if it was created or already existed
            existing_sources = supabase.fetch_sources(league["id"])
            was_existing = any(s.get("domain") == domain for s in existing_sources)

            if was_existing:
                stats["existing"] += 1
                status = "EXISTING"
            else:
                stats["created"] += 1
                status = "CREATED"

            results.append(
                {
                    "continent": continent_name,
                    "country": country_name,
                    "league": f"{league_name} ({tier})",
                    "source": domain,
                    "status": status,
                }
            )
        else:
            stats["errors"] += 1
            results.append(
                {
                    "continent": continent_name,
                    "country": country_name,
                    "league": f"{league_name} ({tier})",
                    "source": domain,
                    "status": "ERROR - Upsert failed",
                }
            )

    # Generate execution report
    logger.info("\n" + "=" * 80)
    logger.info("EXECUTION REPORT")
    logger.info("=" * 80)
    logger.info(f"Total sources: {stats['total']}")
    logger.info(f"Processed: {stats['processed']}")
    logger.info(f"Skipped: {stats['skipped']}")
    logger.info(f"Created: {stats['created']}")
    logger.info(f"Existing: {stats['existing']}")
    logger.info(f"Errors: {stats['errors']}")

    # Print detailed results table
    logger.info("\n" + "=" * 80)
    logger.info("DETAILED RESULTS TABLE")
    logger.info("=" * 80)
    logger.info(
        f"{'Continent':<12} {'Country':<12} {'League (Tier)':<40} {'Source':<50} {'Status':<10}"
    )
    logger.info("-" * 124)

    for result in results:
        continent = result["continent"]
        country = result["country"]
        league = result["league"][:38] + ".." if len(result["league"]) > 40 else result["league"]
        source = result["source"][:48] + ".." if len(result["source"]) > 50 else result["source"]
        status = result["status"]

        logger.info(f"{continent:<12} {country:<12} {league:<40} {source:<50} {status:<10}")

    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info(f"GRANULAR SEEDING COMPLETE: {stats['processed']} specialized sources integrated")
    logger.info("=" * 80)

    # Refresh mirror to include new data
    logger.info("\nRefreshing local mirror...")
    supabase.update_mirror(force=True)
    logger.info("✓ Mirror updated")


if __name__ == "__main__":
    main()
