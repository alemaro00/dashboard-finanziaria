# Dashboard Finanziaria Beta

Applicazione locale macOS dedicata a due sole aree:

1. **Gestione delle finanze personali**
2. **Wealth management**

La beta mantiene i dati e l’identità dell’app completa, ma non espone né avvia la
stima dello stipendio netto o il laboratorio strategie. La versione completa resta
recuperabile dal tag Git annotato `v1.13.28-completa` (`bccef26`).

## Scope della beta

### Gestione delle finanze personali

- Sei categorie: Costi fissi, Costi variabili, Investimenti, Disinvestimenti,
  Stipendio ed Entrate aggiuntive.
- Importi arrotondati ai centesimi.
- Bozze isolate per mese e anno e storico persistente modificabile.
- Movimenti bancari importati in sola lettura, con identità originale conservata e
  nome personalizzato separato.
- Classificazione dei movimenti nelle voci dettagliate senza duplicazioni; `Rimuovi`
  restituisce il singolo movimento alla finestra di classificazione.
- Voci manuali modificabili ed eliminabili.
- Conto Cash con entrate, uscite e prelievi manuali senza doppio conteggio.
- Quota fondo emergenza positiva o negativa.
- Resoconto dei mesi salvati aggregato solo per nome e categoria; i movimenti
  originali rimangono distinti nella modifica del mese.

### Wealth management

- Conto e posizioni Interactive Brokers in sola lettura.
- Conti e movimenti Enable Banking in sola lettura.
- Investimenti illiquidi/manuali, patrimonio consolidato, liquidità, esposizioni e
  profilo di rischio.
- Nessuna funzione per creare, modificare o cancellare ordini broker.

## Architettura ridotta

La build distribuita contiene:

- `salary-planner-react.html` e il frontend compilato in `web-build/`;
- `ibkr_paper_bridge.py`, servizio HTTP locale su `127.0.0.1`;
- `enable_banking_sync.py`, integrazione bancaria di sola lettura;
- `local_security.py`, controlli Host/Origin, CSRF, payload e rate limit;
- SDK IBKR necessario al monitoraggio read-only;
- wrapper nativo macOS in `macos/DashboardFinanziaria.m`.

Non contiene `research/`, `paper_data.py` o lo script demo. Le rispettive rotte HTTP
sono ritirate e restituiscono `404`. Il sorgente storico può restare nel branch per
confronto e audit, ma non è inizializzato dal servizio né incluso nell’app.

## Dati e compatibilità

Lo stato continua a essere salvato in:

`~/Library/Application Support/Dashboard Finanziaria/dashboard-state.json`

La beta non rinomina il file, non cambia bundle identifier e non esegue migrazioni
distruttive. Prima di ogni scrittura il servizio conserva anche
`dashboard-state.json.bak`; stato e backup hanno permessi privati. I vecchi campi
delle funzioni rimosse sono tollerati e conservati quando presenti, senza essere
mostrati o usati nei calcoli correnti.

## Avvio locale

Requisiti: Python 3.9+, Node.js e le dipendenze di `requirements.txt`.

```sh
node scripts/build-web.cjs
python3 ibkr_paper_bridge.py --no-browser --broker-mode offline
```

Aprire `http://127.0.0.1:8765/`. L’avvio predefinito è offline. Il monitoraggio IBKR
si abilita esplicitamente con `--broker-mode monitor-readonly`; non esistono percorsi
di invio ordini.

## Build macOS

```sh
NODE_BIN=/percorso/a/node ./scripts/build-macos-app.sh
```

Lo script compila, firma ad hoc, crea lo ZIP di distribuzione e sostituisce la stessa
`/Applications/Dashboard Finanziaria.app`. Mantiene:

- bundle identifier `it.alemaro.dashboard-finanziaria`;
- nome e percorso dell’app;
- directory dati dell’utente;
- collegamento Dock esistente.

La beta è versione `1.14.0`, build `57`, e mostra chiaramente `Beta` nell’interfaccia.

## Verifica

Tutti i test usano fixture sintetiche e directory temporanee. Non richiedono conti,
consensi bancari o dati personali.

```sh
node scripts/build-web.cjs
python3 -m unittest discover -s tests -p 'test*.py'
node --test tests/test-*.cjs
python3 tests/http_smoke.py
python3 scripts/check_repository.py
.build/check-env/bin/ruff check .
.build/check-env/bin/mypy
.build/check-env/bin/bandit -r research local_security.py ibkr_paper_bridge.py -ll
.build/check-env/bin/pip-audit --no-deps --disable-pip -r requirements.txt
```

I controlli coprono formule, centesimi, categorie, classificazione/rimozione dei
movimenti, deduplicazione, Cash, isolamento mesi, aggregazione resoconti,
salvataggio/ripristino, backup, sicurezza HTTP, disconnessioni e sola lettura IBKR.

## Limiti concreti

- Enable Banking dipende da configurazione e disponibilità del provider; la beta non
  crea consensi durante test o build.
- IBKR richiede TWS configurata in read-only e può mostrare dati non aggiornati o
  disconnessi; in quel caso l’interfaccia segnala lo stato senza inventare valori.
- Le valute IBKR sono visualizzate con i dati disponibili; non viene eseguita una
  conversione FX implicita per colmare dati mancanti.
- Gli investimenti illiquidi usano valori inseriti manualmente e non quotazioni
  certificate.
- La beta non è uno strumento fiscale, non offre consulenza finanziaria e non esegue
  trading.

Per privacy, non aggiungere al repository archivi di backup, movimenti, saldi,
identificativi conto o chiavi.
