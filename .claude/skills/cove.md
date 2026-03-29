---
name: cove
description: Elimina le allucinazioni dell'AI attraverso un rigoroso processo di verifica in 4 fasi
user_invocable: true
---

# COVE - Chain of Verification Mode

## Attivazione
Invoca questa skill con `/cove` seguito dalla tua domanda o task.

## Descrizione
Elimina le allucinazioni dell'AI attraverso un rigoroso processo di verifica in 4 fasi.

## Quando Usare
- Quando l'accuratezza è critica
- Per verificare fatti, codice, parametri, date, numeri
- Per domande tecniche e task di programmazione
- Per fact-checking e ragionamento logico
- In situazioni dove le allucinazioni potrebbero causare problemi

---

## PROTOCOLLO COVE (4 Fasi OBBLIGATORIE)

### FASE 1: Generazione Bozza (Draft)
Genera una risposta preliminare basata sulla tua conoscenza immediata.
**IMPORTANTE**: Trattala come una 'ipotesi' NON verificata.

### FASE 2: Verifica Avversariale (Cross-Examination)
Analizza la bozza della FASE 1 con scetticismo ESTREMO. Identifica:

1. **Fatti** (date, numeri, versioni)
2. **Codice** (sintassi, parametri, import)
3. **Logica**

Per ognuno, formula domande volte a SMENTIRE la bozza.
Esempi: "Siamo sicuri che .sort() funzioni così?", "Questa API esiste davvero?", "La versione è corretta?"

### FASE 3: Esecuzione Verifiche
Rispondi alle domande della FASE 2 in modo INDIPENDENTE, basandoti SOLO sulla tua conoscenza pre-addestrata.
**IGNORA completamente la bozza della FASE 1.**

Se c'è discrepanza, scrivi esplicitamente:
> **[CORREZIONE NECESSARIA: Dettaglio dell'errore]**

### FASE 4: Risposta Finale (Canonical)
Ignora completamente la bozza della FASE 1.
Scrivi la risposta DEFINITIVA e corretta, basata SOLO sulle verità emerse nella FASE 3.

---

## Output Richiesto

Ogni risposta COVE deve seguire questo formato:

```
## [FASE 1] Bozza Preliminare
<risposta non verificata>

## [FASE 2] Verifica Avversariale
Domande critiche:
- Domanda 1?
- Domanda 2?
- ...

## [FASE 3] Verifiche Indipendenti
Verifica 1: <risposta basata su conoscenza pre-addestrata>
Verifica 2: <risposta basata su conoscenza pre-addestrata>
**[CORREZIONE NECESSARIA: ...]** (se applicabile)

## [FASE 4] Risposta Definitiva
<risposta corretta e verificata>

## Correzioni Applicate
- <lista delle correzioni trovate, se presenti>
```

---

## Esempio

**Domanda**: "Come ordinare una lista in Python in modo decreescente?"

### [FASE 1] Bozza Preliminare
Usa `list.sort(reverse=True)` o `sorted(list, reverse=True)`.

### [FASE 2] Verifica Avversariale
- `.sort()` modifica in-place o restituisce una nuova lista?
- `sorted()` funziona su qualsiasi iterable?
- Il parametro si chiama davvero `reverse`?

### [FASE 3] Verifiche Indipendenti
- `.sort()`: Metodo delle liste che modifica in-place, restituisce `None`. Confermato.
- `sorted()`: Funzione built-in che restituisce una nuova lista. Funziona su qualsiasi iterable. Confermato.
- Il parametro è `reverse=True` per entrambi. Confermato.

### [FASE 4] Risposta Definitiva
Per ordinare in modo decrescente:
- `lista.sort(reverse=True)` - modifica in-place, restituisce None
- `sorted(lista, reverse=True)` - restituisce nuova lista

### Correzioni Applicate
Nessuna correzione necessaria.
