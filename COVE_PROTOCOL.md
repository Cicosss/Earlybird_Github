# Protocollo CoVe (Chain of Verification)

## Descrizione
Il protocollo CoVe (Chain of Verification) è un metodo per eliminare le allucinazioni nelle risposte AI attraverso un processo in 4 fasi di verifica incrociata.

## Quando usare questo protocollo
Attiva questo protocollo quando l'utente scrive `cove` seguito da una domanda.

---

## FASE 1: Generazione Bozza (Draft)
Genera una risposta preliminare basata sulla tua conoscenza immediata. Trattala come una 'ipotesi' NON verificata.

---

## FASE 2: Verifica Avversariale (Cross-Examination)
Analizza la bozza della FASE 1 con scetticismo ESTREMO. Identifica:
1. **Fatti** (date, numeri, versioni)
2. **Codice** (sintassi, parametri, import)
3. **Logica**

Per ognuno, formula domande volte a SMENTIRE la bozza (es. 'Siamo sicuri che .sort() funzioni così?').

---

## FASE 3: Esecuzione Verifiche
Rispondi alle domande della FASE 2 in modo indipendente, basandoti SOLO sulla tua conoscenza pre-addestrata (ignora la bozza).

Se c'è discrepanza, scrivi esplicitamente: **[CORREZIONE NECESSARIA: Dettaglio dell'errore]**.

---

## FASE 4: Risposta Finale (Canonical)
Ignora completamente la bozza della FASE 1.
Scrivi la risposta DEFINITIVA e corretta, basata solo sulle verità emerse nella FASE 3.

---

## Esempio di Applicazione

### Domanda: "Scrivi il codice Python per ordinare una lista di dizionari in base alla chiave 'age' usando il metodo .sort() ma restituendo una nuova lista senza modificare l'originale."

#### FASE 1 (Bozza):
```python
new_list = my_list.sort(key=lambda x: x['age'])
```

#### FASE 2 (Verifica):
- Il metodo `.sort()` restituisce una nuova lista o modifica in-place?
- Se restituisce None, cosa succede a `new_list`?

#### FASE 3 (Esecuzione Verifiche):
**[CORREZIONE NECESSARIA: Il metodo `.sort()` modifica la lista in-place e restituisce `None`, non una nuova lista]**

#### FASE 4 (Risposta Finale):
```python
new_list = sorted(my_list, key=lambda x: x['age'])
```

---

## Note Importanti
- **NON saltare nessuna fase**: Tutte e 4 le fasi sono obbligatorie
- **Sii scettico**: Nella FASE 2, metti in dubbio TUTTO nella bozza
- **Documenta le correzioni**: Usa il formato `**[CORREZIONE NECESSARIA: ...]**` per ogni errore trovato
- **Ignora la bozza nella FASE 4**: La risposta finale deve basarsi SOLO sulle verifiche della FASE 3
