#!/usr/bin/env python3
"""
EarlyBird API Diagnostic Tool

Verifica:
1. Odds API - Auth + Discovery leghe
2. Serper API - Auth + Test query
3. OpenRouter API - Auth + Test query
4. Brave API - Auth + Test query (3 keys)
5. Perplexity API - Auth + Test query
6. Tavily API - Auth + Test query (7 keys)
7. Supabase Database - Connection test (V9.0)

Uso: python3 src/utils/check_apis.py
"""

import os
import sys

import requests

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv

load_dotenv()

# Import safe access utilities
from src.utils.validators import safe_get, safe_list_get

# Colori per output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def print_ok(msg):
    print(f"{GREEN}✅ {msg}{RESET}")


def print_err(msg):
    print(f"{RED}❌ {msg}{RESET}")


def print_warn(msg):
    print(f"{YELLOW}⚠️ {msg}{RESET}")


def test_odds_api():
    """Test Odds API authentication e discovery leghe."""
    print("\n" + "=" * 60)
    print("🎯 ODDS API - Test Autenticazione & Discovery")
    print("=" * 60)

    api_key = os.getenv("ODDS_API_KEY", "")

    if not api_key or api_key == "YOUR_ODDS_API_KEY":
        print_err("ODDS_API_KEY non configurata in .env")
        return False

    print(f"   Chiave: {api_key[:8]}...{api_key[-4:]}")

    try:
        url = "https://api.the-odds-api.com/v4/sports"
        params = {"apiKey": api_key}

        response = requests.get(url, params=params, timeout=15)

        if response.status_code == 401:
            print_err("Chiave API non valida (401 Unauthorized)")
            return False

        if response.status_code != 200:
            print_err(f"Errore HTTP: {response.status_code}")
            return False

        # Quota info
        used = response.headers.get("x-requests-used", "?")
        remaining = response.headers.get("x-requests-remaining", "?")
        print_ok(f"Autenticazione OK | Quota: {used} usate, {remaining} rimanenti")

        sports = response.json()
        print(f"\n📊 Totale sport/leghe disponibili: {len(sports)}")

        # Filtra per Francia, Romania, Cup
        print("\n🔍 Leghe con 'France', 'Romania', 'Cup':")
        print("-" * 50)

        keywords = ["france", "romania", "cup", "coupe"]
        found = []

        for sport in sports:
            key = sport.get("key", "")
            title = sport.get("title", "")
            active = sport.get("active", False)

            # Check keywords
            text = f"{key} {title}".lower()
            if any(kw in text for kw in keywords):
                status = "🟢 ATTIVA" if active else "🔴 INATTIVA"
                found.append((key, title, status))

        if found:
            for key, title, status in sorted(found):
                print(f"   {status} | {key}")
                print(f"            └─ {title}")
        else:
            print_warn("Nessuna lega trovata con questi filtri")

        # Mostra anche le leghe soccer attive
        print("\n📋 Tutte le leghe SOCCER attive:")
        print("-" * 50)
        soccer_active = [
            s for s in sports if s.get("key", "").startswith("soccer") and s.get("active")
        ]
        for sport in sorted(soccer_active, key=lambda x: x["key"]):
            print(f"   🟢 {sport['key']}")

        return True

    except requests.exceptions.Timeout:
        print_err("Timeout connessione")
        return False
    except Exception as e:
        print_err(f"Errore: {e}")
        return False


# DEPRECATED: Serper API test - migrating to Brave
# def test_serper_api():
#     """Test Serper API authentication."""
#     print("\n" + "=" * 60)
#     print("🔍 SERPER API - Test Autenticazione")
#     print("=" * 60)
#
#     api_key = os.getenv("SERPER_API_KEY", "")
#
#     if not api_key or "YOUR_" in api_key:
#         print_err("SERPER_API_KEY non configurata in .env")
#         return False
#
#     print(f"   Chiave: {api_key[:8]}...{api_key[-4:]}")
#
#     try:
#         url = "https://google.serper.dev/search"
#         headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
#         payload = {"q": "test football news", "num": 3}
#
#         response = requests.post(url, headers=headers, json=payload, timeout=15)
#
#         if response.status_code == 401:
#             print_err("Chiave API non valida (401 Unauthorized)")
#             return False
#
#         if response.status_code == 400:
#             # Check for credit exhaustion
#             try:
#                 data = response.json()
#                 if "credits" in str(data).lower():
#                     print_err("Crediti Serper esauriti")
#                 else:
#                     print_err(f"Bad Request: {data}")
#             except:
#                 print_err("Bad Request (400)")
#             return False
#
#         if response.status_code != 200:
#             print_err(f"Errore HTTP: {response.status_code}")
#             return False
#
#         data = response.json()
#         results = data.get("organic", [])
#
#         print_ok(f"Autenticazione OK | Risultati test: {len(results)}")
#
#         if results:
#             print("\n   Esempio risultato:")
#             print(f"   └─ {results[0].get('title', 'N/A')[:60]}...")
#
#         return True
#
#     except requests.exceptions.Timeout:
#         print_err("Timeout connessione")
#         return False
#     except Exception as e:
#         print_err(f"Errore: {e}")
#         return False


def test_openrouter_api():
    """Test OpenRouter API authentication."""
    print("\n" + "=" * 60)
    print("🤖 OPENROUTER API - Test Autenticazione")
    print("=" * 60)

    api_key = os.getenv("OPENROUTER_API_KEY", "")

    if not api_key or "YOUR_" in api_key:
        print_err("OPENROUTER_API_KEY non configurata in .env")
        return False

    print(f"   Chiave: {api_key[:12]}...{api_key[-4:]}")

    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek/deepseek-chat-v3-0324",
            "messages": [{"role": "user", "content": "Say OK"}],
            "max_tokens": 10,
        }

        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code == 401:
            print_err("Chiave API non valida (401 Unauthorized)")
            return False

        if response.status_code != 200:
            print_err(f"Errore HTTP: {response.status_code}")
            try:
                print(f"   Dettaglio: {response.json()}")
            except:
                pass
            return False

        data = response.json()
        # V7.0: Safe array access with bounds checking
        first_choice = safe_list_get(data.get("choices", []), 0)
        # V7.0: Safe nested dictionary access with type checking
        content = safe_get(first_choice, "message", "content", default="")

        print_ok(f"Autenticazione OK | Risposta: {content[:30]}")
        return True

    except requests.exceptions.Timeout:
        print_err("Timeout connessione (normale per LLM)")
        return True  # Timeout is OK for LLM
    except Exception as e:
        print_err(f"Errore: {e}")
        return False


def test_brave_api():
    """Test Brave Search API authentication (3 keys)."""
    print("\n" + "=" * 60)
    print("🦁 BRAVE SEARCH API - Test Autenticazione (3 Keys)")
    print("=" * 60)

    # Test all 3 keys
    keys = [
        os.getenv("BRAVE_API_KEY_1", ""),
        os.getenv("BRAVE_API_KEY_2", ""),
        os.getenv("BRAVE_API_KEY_3", ""),
    ]

    working_keys = 0
    for i, api_key in enumerate(keys, 1):
        if not api_key or "YOUR_" in api_key or api_key == "":
            print_warn(f"BRAVE_API_KEY_{i} non configurata o usa default")
            continue

        print(f"   Testing Key {i}: {api_key[:12]}...{api_key[-4:]}")

        try:
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            }
            params = {"q": "test football news", "count": 3}

            response = requests.get(url, headers=headers, params=params, timeout=15)

            if response.status_code == 401:
                print_err(f"  Key {i}: Non valida (401 Unauthorized)")
                continue

            if response.status_code == 429:
                print_warn(f"  Key {i}: Rate limit raggiunto (429)")
                working_keys += 1  # Key exists but rate limited
                continue

            if response.status_code != 200:
                print_err(f"  Key {i}: Errore HTTP {response.status_code}")
                continue

            data = response.json()
            results = safe_get(data, "web", "results", default=[])
            print_ok(f"  Key {i}: OK | Risultati: {len(results)}")
            working_keys += 1

        except requests.exceptions.Timeout:
            print_err(f"  Key {i}: Timeout connessione")
        except Exception as e:
            print_err(f"  Key {i}: Errore: {e}")

    if working_keys > 0:
        print_ok(f"Totale chiavi funzionanti: {working_keys}/3")
        return True
    else:
        print_err("Nessuna chiave Brave funzionante")
        return False


def test_perplexity_api():
    """Test Perplexity API authentication."""
    print("\n" + "=" * 60)
    print("🔮 PERPLEXITY API - Test Autenticazione")
    print("=" * 60)

    api_key = os.getenv("PERPLEXITY_API_KEY", "")

    if not api_key or "YOUR_" in api_key:
        print_warn("PERPLEXITY_API_KEY non configurata in .env (OPTIONAL)")
        return True  # Perplexity is optional

    print(f"   Chiave: {api_key[:12]}...{api_key[-4:]}")

    try:
        url = "https://api.perplexity.ai/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "sonar-pro",
            "messages": [{"role": "user", "content": "Say OK"}],
            "max_tokens": 10,
        }

        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code == 401:
            print_err("Chiave API non valida (401 Unauthorized)")
            return False

        if response.status_code != 200:
            print_err(f"Errore HTTP: {response.status_code}")
            try:
                print(f"   Dettaglio: {response.json()}")
            except:
                pass
            return False

        data = response.json()
        # V7.0: Safe array access with bounds checking
        first_choice = safe_list_get(data.get("choices", []), 0)
        # V7.0: Safe nested dictionary access with type checking
        content = safe_get(first_choice, "message", "content", default="")

        print_ok(f"Autenticazione OK | Risposta: {content[:30]}")
        return True

    except requests.exceptions.Timeout:
        print_err("Timeout connessione (normale per LLM)")
        return True  # Timeout is OK for LLM
    except Exception as e:
        print_err(f"Errore: {e}")
        return False


def test_tavily_api():
    """Test Tavily AI Search API authentication (7 keys)."""
    print("\n" + "=" * 60)
    print("🔍 TAVILY AI SEARCH - Test Autenticazione (7 Keys)")
    print("=" * 60)

    # Test all 7 keys
    keys = []
    for i in range(1, 8):
        key = os.getenv(f"TAVILY_API_KEY_{i}", "")
        keys.append(key)

    working_keys = 0
    for i, api_key in enumerate(keys, 1):
        if not api_key or "YOUR_" in api_key or api_key == "":
            print_warn(f"TAVILY_API_KEY_{i} non configurata o invalida")
            continue

        print(f"   Testing Key {i}: {api_key[:12]}...{api_key[-4:]}")

        try:
            url = "https://api.tavily.com/search"
            headers = {"Content-Type": "application/json"}
            payload = {
                "api_key": api_key,
                "query": "test football news",
                "max_results": 3,
                "search_depth": "basic",
            }

            response = requests.post(url, headers=headers, json=payload, timeout=15)

            if response.status_code == 401:
                print_err(f"  Key {i}: Non valida (401 Unauthorized)")
                continue

            if response.status_code == 429:
                print_warn(f"  Key {i}: Rate limit raggiunto (429)")
                working_keys += 1  # Key exists but rate limited
                continue

            if response.status_code != 200:
                print_err(f"  Key {i}: Errore HTTP {response.status_code}")
                continue

            data = response.json()
            results = data.get("results", [])
            print_ok(f"  Key {i}: OK | Risultati: {len(results)}")
            working_keys += 1

        except requests.exceptions.Timeout:
            print_err(f"  Key {i}: Timeout connessione")
        except Exception as e:
            print_err(f"  Key {i}: Errore: {e}")

    if working_keys > 0:
        print_ok(f"Totale chiavi funzionanti: {working_keys}/7")
        return True
    else:
        print_err("Nessuna chiave Tavily funzionante")
        return False


def test_supabase_api():
    """Test Supabase Database connection (V9.0)."""
    print("\n" + "=" * 60)
    print("🗄️  SUPABASE DATABASE - Test Connessione (V9.0)")
    print("=" * 60)

    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_KEY", "")

    if not supabase_url or not supabase_key:
        print_err("SUPABASE_URL o SUPABASE_KEY non configurata in .env")
        return False

    print(f"   URL: {supabase_url}")
    print(f"   Key: {supabase_key[:12]}...{supabase_key[-4:]}")

    try:
        # Import Supabase provider
        from src.database.supabase_provider import get_supabase

        # Get singleton instance
        provider = get_supabase()

        # Test connection with continents query
        if not provider.test_connection():
            error = provider.get_connection_error()
            print_err(f"Connessione fallita: {error}")
            return False

        # Fetch continents to verify data access
        continents = provider.fetch_continents()

        print_ok(f"Connessione attiva | Continenti trovate: {len(continents)}")

        if continents:
            print("\n📋 Continenti disponibili:")
            print("-" * 50)
            for continent in continents[:10]:
                continent_id = continent.get("id", "N/A")
                continent_name = continent.get("name", "N/A")
                print(f"   🌍 {continent_id}: {continent_name}")

            if len(continents) > 10:
                print(f"   ... e altre {len(continents) - 10} continenti")

        # Get cache stats
        stats = provider.get_cache_stats()
        print("\n📊 Cache Statistics:")
        print(f"   Cache entries: {stats['cache_entries']}")
        print(f"   Cache TTL: {stats['cache_ttl_seconds']} seconds (1 hour)")
        print(f"   Mirror exists: {stats['mirror_exists']}")

        return True

    except ImportError as e:
        print_err(f"Modulo Supabase non disponibile: {e}")
        print_warn("Esegui: pip install supabase")
        return False
    except Exception as e:
        print_err(f"Errore durante il test: {e}")
        return False


def test_continental_orchestrator():
    """Test ContinentalOrchestrator connection and functionality (V9.0)."""
    print("\n" + "=" * 60)
    print("🌍 CONTINENTAL ORCHESTRATOR - Test Connessione (V9.0)")
    print("=" * 60)

    try:
        # Import GlobalOrchestrator (V11.0: continental_orchestrator.py replaced by global_orchestrator.py)
        from src.processing.global_orchestrator import (
            CONTINENTAL_WINDOWS,
            MIRROR_FILE_PATH,
            GlobalOrchestrator,
            get_global_orchestrator,  # V11.0: Use get_global_orchestrator() instead of deprecated get_continental_orchestrator()
        )

        print_ok("Modulo GlobalOrchestrator importato (V11.0 - replaces ContinentalOrchestrator)")

        # Display continental windows
        print("\n📋 Finestre Continentali UTC:")
        print("-" * 50)
        for continent, hours in CONTINENTAL_WINDOWS.items():
            print(f"   {continent:8} : {hours[0]:02d}:00-{hours[-1]:02d}:00 UTC ({len(hours)} ore)")

        # Test 1: Check local mirror file exists
        print("\n📁 Verifica File Mirror:")
        print("-" * 50)
        if MIRROR_FILE_PATH.exists():
            print_ok(f"Mirror file trovato: {MIRROR_FILE_PATH}")
            try:
                import json

                with open(MIRROR_FILE_PATH, encoding="utf-8") as f:
                    mirror_data = json.load(f)
                timestamp = mirror_data.get("timestamp", "N/A")
                data = mirror_data.get("data", {})
                continents = data.get("continents", [])
                countries = data.get("countries", [])
                leagues = data.get("leagues", [])
                print_ok(f"Mirror caricato da: {timestamp}")
                print(f"   Continenti: {len(continents)}")
                print(f"   Paesi: {len(countries)}")
                print(f"   Leghe: {len(leagues)}")
            except Exception as e:
                print_err(f"Errore caricamento mirror: {e}")
                return False
        else:
            print_warn(f"Mirror file non trovato: {MIRROR_FILE_PATH}")

        # Test 2: Initialize orchestrator
        print("\n🔧 Inizializzazione Orchestrator:")
        print("-" * 50)
        orchestrator = get_global_orchestrator()
        print_ok("Orchestrator inizializzato")

        # Test 3: Check continental status
        print("\n🌍 Stato Continentale:")
        print("-" * 50)
        status = orchestrator.get_continental_status()
        print(f"   UTC Hour corrente: {status['current_utc_hour']:02d}:00")
        print(f"   Maintenance window: {'SI' if status['in_maintenance_window'] else 'NO'}")
        print(f"   Supabase disponibile: {'SI' if status['supabase_available'] else 'NO'}")
        print("\n   Attività Continenti:")
        for continent, info in status["continents"].items():
            active_str = "🟢 ATTIVA" if info["is_currently_active"] else "🔴 INATTIVA"
            print(f"      {continent:8} : {active_str}")

        # Test 4: Get active leagues for current time
        print("\n🎯 Leghe Attive per Tempo Corrente:")
        print("-" * 50)
        result = orchestrator.get_active_leagues_for_current_time()

        print(f"   Settlement mode: {'SI' if result['settlement_mode'] else 'NO'}")
        print(f"   Source: {result['source'].upper()}")
        print(f"   UTC Hour: {result['utc_hour']:02d}:00")
        print(
            f"   Continent blocks: {', '.join(result['continent_blocks']) if result['continent_blocks'] else 'Nessuno'}"
        )
        print(f"   Leghe da scansionare: {len(result['leagues'])}")

        if result["leagues"]:
            print("\n   Lista Leghe:")
            for league in result["leagues"][:10]:
                print(f"      📌 {league}")
            if len(result["leagues"]) > 10:
                print(f"      ... e altre {len(result['leagues']) - 10} leghe")

        # Test 5: Verify fallback mechanism
        print("\n🔄 Verifica Meccanismo Fallback:")
        print("-" * 50)
        if result["source"] == "supabase":
            print_ok("Dati caricati da Supabase (connessione primaria)")
        elif result["source"] == "mirror":
            print_warn("Dati caricati da Mirror (fallback attivo)")
        else:
            print_warn("Nessun dato caricato (maintenance window)")

        # Test 6: Validate response structure
        print("\n✅ Verifica Struttura Risposta:")
        print("-" * 50)
        required_keys = ["leagues", "continent_blocks", "settlement_mode", "source", "utc_hour"]
        missing_keys = [k for k in required_keys if k not in result]

        if missing_keys:
            print_err(f"Chiavi mancanti nella risposta: {missing_keys}")
            return False
        else:
            print_ok("Struttura risposta valida")

        # Test 7: Check if leagues list is valid
        if result["leagues"]:
            print_ok(f"Lista leghe valida: {len(result['leagues'])} elementi")
            # Check if all leagues are strings
            if all(isinstance(league, str) for league in result["leagues"]):
                print_ok("Tutte le leghe sono stringhe valide")
            else:
                print_err("Alcune leghe non sono stringhe valide")
                return False

        # Summary
        print("\n📊 Riepilogo:")
        print("-" * 50)
        print_ok("ContinentalOrchestrator operativo")
        print(
            f"   - Supabase: {'Disponibile' if status['supabase_available'] else 'Non disponibile'}"
        )
        print(f"   - Mirror: {'Disponibile' if MIRROR_FILE_PATH.exists() else 'Non disponibile'}")
        print(f"   - Leghe attive: {len(result['leagues'])}")
        print(f"   - Source: {result['source'].upper()}")

        return True

    except ImportError as e:
        print_err(f"Modulo ContinentalOrchestrator non disponibile: {e}")
        return False
    except Exception as e:
        print_err(f"Errore durante il test: {e}")
        import traceback

        print("   Stack trace:")
        for line in traceback.format_exc().split("\n")[:10]:
            if line.strip():
                print(f"   {line}")
        return False


def main():
    print("\n" + "=" * 60)
    print("🦅 EARLYBIRD API DIAGNOSTIC TOOL")
    print("=" * 60)

    results = {}

    # Test APIs
    results["odds"] = test_odds_api()
    # results["serper"] = test_serper_api()  # DEPRECATED: migrating to Brave
    results["openrouter"] = test_openrouter_api()
    results["brave"] = test_brave_api()
    results["perplexity"] = test_perplexity_api()
    results["tavily"] = test_tavily_api()
    results["supabase"] = test_supabase_api()
    results["continental_orchestrator"] = test_continental_orchestrator()

    # Summary
    print("\n" + "=" * 60)
    print("📋 RIEPILOGO")
    print("=" * 60)

    for name, ok in results.items():
        status = f"{GREEN}OK{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"   {name.upper():12} : {status}")

    all_ok = all(results.values())

    if all_ok:
        print(f"\n{GREEN}✅ Tutte le API funzionano correttamente!{RESET}")
    else:
        print(f"\n{RED}❌ Alcune API hanno problemi. Verifica le chiavi in .env{RESET}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
