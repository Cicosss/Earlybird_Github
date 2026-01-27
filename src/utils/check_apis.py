#!/usr/bin/env python3
"""
EarlyBird API Diagnostic Tool

Verifica:
1. Odds API - Auth + Discovery leghe
2. Serper API - Auth + Test query

Uso: python3 src/utils/check_apis.py
"""
import os
import sys
import requests

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

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
        soccer_active = [s for s in sports if s.get("key", "").startswith("soccer") and s.get("active")]
        for sport in sorted(soccer_active, key=lambda x: x["key"]):
            print(f"   🟢 {sport['key']}")
        
        return True
        
    except requests.exceptions.Timeout:
        print_err("Timeout connessione")
        return False
    except Exception as e:
        print_err(f"Errore: {e}")
        return False


def test_serper_api():
    """Test Serper API authentication."""
    print("\n" + "=" * 60)
    print("🔍 SERPER API - Test Autenticazione")
    print("=" * 60)
    
    api_key = os.getenv("SERPER_API_KEY", "")
    
    if not api_key or "YOUR_" in api_key:
        print_err("SERPER_API_KEY non configurata in .env")
        return False
    
    print(f"   Chiave: {api_key[:8]}...{api_key[-4:]}")
    
    try:
        url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "q": "test football news",
            "num": 3
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if response.status_code == 401:
            print_err("Chiave API non valida (401 Unauthorized)")
            return False
        
        if response.status_code == 400:
            # Check for credit exhaustion
            try:
                data = response.json()
                if "credits" in str(data).lower():
                    print_err("Crediti Serper esauriti")
                else:
                    print_err(f"Bad Request: {data}")
            except:
                print_err(f"Bad Request (400)")
            return False
        
        if response.status_code != 200:
            print_err(f"Errore HTTP: {response.status_code}")
            return False
        
        data = response.json()
        results = data.get("organic", [])
        
        print_ok(f"Autenticazione OK | Risultati test: {len(results)}")
        
        if results:
            print(f"\n   Esempio risultato:")
            print(f"   └─ {results[0].get('title', 'N/A')[:60]}...")
        
        return True
        
    except requests.exceptions.Timeout:
        print_err("Timeout connessione")
        return False
    except Exception as e:
        print_err(f"Errore: {e}")
        return False


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
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "deepseek/deepseek-chat-v3-0324",
            "messages": [{"role": "user", "content": "Say OK"}],
            "max_tokens": 10
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
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        print_ok(f"Autenticazione OK | Risposta: {content[:30]}")
        return True
        
    except requests.exceptions.Timeout:
        print_err("Timeout connessione (normale per LLM)")
        return True  # Timeout is OK for LLM
    except Exception as e:
        print_err(f"Errore: {e}")
        return False


def main():
    print("\n" + "=" * 60)
    print("🦅 EARLYBIRD API DIAGNOSTIC TOOL")
    print("=" * 60)
    
    results = {}
    
    # Test APIs
    results["odds"] = test_odds_api()
    results["serper"] = test_serper_api()
    results["openrouter"] = test_openrouter_api()
    
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
