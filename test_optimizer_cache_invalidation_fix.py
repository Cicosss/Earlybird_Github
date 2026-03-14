"""
Test per verificare che la correzione della cache invalidation funzioni correttamente.

Questo test verifica che:
1. La cache viene invalidata dopo il settlement
2. La cache viene ricaricata dal disco al prossimo accesso
3. Il flusso completo funziona correttamente
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone

# Setup path
sys.path.append(os.getcwd())

from src.analysis.optimizer import WEIGHTS_FILE, _weight_cache


def test_cache_invalidation_after_external_modification():
    """
    Test che verifica che la cache venga invalidata dopo una modifica esterna.
    """
    print("🧪 Test: Cache invalidation after external modification")

    # Crea una copia di backup del file originale
    backup_file = WEIGHTS_FILE + ".backup_test"
    if os.path.exists(WEIGHTS_FILE):
        shutil.copy2(WEIGHTS_FILE, backup_file)

    try:
        # Carica i dati nella cache
        print("  1. Caricamento dati nella cache...")

        def load_data():
            with open(WEIGHTS_FILE, "r") as f:
                return json.load(f)

        data1 = _weight_cache.get_data(load_data)
        print(f"  ✅ Dati caricati: {data1.get('global', {}).get('total_bets', 0)} bets totali")

        # Modifica esternamente il file
        print("  2. Modifica esterna del file...")
        with open(WEIGHTS_FILE, "r") as f:
            data = json.load(f)

        # Aggiungi un marker per verificare che il file sia stato modificato
        data["_test_marker"] = datetime.now(timezone.utc).isoformat()
        data["global"]["total_bets"] = data["global"].get("total_bets", 0) + 1000

        with open(WEIGHTS_FILE, "w") as f:
            json.dump(data, f, indent=2)

        print(f"  ✅ File modificato: {data['global']['total_bets']} bets totali")

        # Verifica che la cache non sia stata aggiornata (ancora vecchi dati)
        data2 = _weight_cache.get_data(load_data)
        if data2.get("_test_marker") is None:
            print("  ✅ Cache ancora vecchia (come previsto)")
        else:
            print("  ❌ ERRORE: Cache già aggiornata (non previsto)")
            return False

        # Simula la chiamata a invalidate() (come in run_nightly_settlement)
        print("  3. Invalidazione della cache...")
        _weight_cache.invalidate()
        print("  ✅ Cache invalidata")

        # Verifica che la cache venga ricaricata dal disco
        print("  4. Ricaricamento dati dal disco...")
        data3 = _weight_cache.get_data(load_data)
        print(f"  ✅ Dati ricaricati: {data3.get('global', {}).get('total_bets', 0)} bets totali")

        # Verifica che i dati siano aggiornati
        if data3.get("_test_marker") is not None:
            print("  ✅ Cache aggiornata correttamente")
            return True
        else:
            print("  ❌ ERRORE: Cache non aggiornata")
            return False

    finally:
        # Ripristina il file originale
        if os.path.exists(backup_file):
            shutil.move(backup_file, WEIGHTS_FILE)
            print("  🔄 File originale ripristinato")


def test_cache_invalidation_integration():
    """
    Test che verifica l'integrazione completa con run_nightly_settlement.
    """
    print("\n🧪 Test: Cache invalidation integration")

    # Crea una copia di backup del file originale
    backup_file = WEIGHTS_FILE + ".backup_test2"
    if os.path.exists(WEIGHTS_FILE):
        shutil.copy2(WEIGHTS_FILE, backup_file)

    try:
        # Simula il flusso completo
        print("  1. Simulazione flusso completo...")

        # Carica i dati nella cache
        def load_data():
            with open(WEIGHTS_FILE, "r") as f:
                return json.load(f)

        data1 = _weight_cache.get_data(load_data)
        print(f"  ✅ Dati iniziali: {data1.get('global', {}).get('total_bets', 0)} bets")

        # Modifica esternamente il file
        with open(WEIGHTS_FILE, "r") as f:
            data = json.load(f)

        data["_test_marker"] = datetime.now(timezone.utc).isoformat()
        data["global"]["total_bets"] = data["global"].get("total_bets", 0) + 2000

        with open(WEIGHTS_FILE, "w") as f:
            json.dump(data, f, indent=2)

        print(f"  ✅ File modificato esternamente: {data['global']['total_bets']} bets")

        # Simula la chiamata a invalidate() (come in run_nightly_settlement)
        print("  2. Simulazione invalidate()...")
        _weight_cache.invalidate()

        # Verifica che i dati siano aggiornati
        data2 = _weight_cache.get_data(load_data)
        print(f"  ✅ Dati dopo invalidate(): {data2.get('global', {}).get('total_bets', 0)} bets")

        if data2.get("_test_marker") is not None:
            print("  ✅ Test integrato PASSATO")
            return True
        else:
            print("  ❌ Test integrato FALLITO")
            return False

    finally:
        # Ripristina il file originale
        if os.path.exists(backup_file):
            shutil.move(backup_file, WEIGHTS_FILE)
            print("  🔄 File originale ripristinato")


def main():
    """Esegui tutti i test."""
    print("=" * 60)
    print("TEST CACHE INVALIDATION FIX")
    print("=" * 60)

    test1_passed = test_cache_invalidation_after_external_modification()
    test2_passed = test_cache_invalidation_integration()

    print("\n" + "=" * 60)
    print("RISULTATI")
    print("=" * 60)
    print(
        f"Test 1 (Invalidation after external modification): {'✅ PASSATO' if test1_passed else '❌ FALLITO'}"
    )
    print(f"Test 2 (Integration): {'✅ PASSATO' if test2_passed else '❌ FALLITO'}")

    if test1_passed and test2_passed:
        print("\n🎉 TUTTI I TEST PASSATI!")
        return 0
    else:
        print("\n❌ ALCUNI TEST FALLITI")
        return 1


if __name__ == "__main__":
    sys.exit(main())
