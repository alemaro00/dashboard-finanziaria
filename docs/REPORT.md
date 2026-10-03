# Dashboard Finanziaria — rapporto tecnico e decisione di prodotto

> Stato più recente: **1.9.1/build12 installata** dopo la richiesta di collegamento TWS paper.
> Handshake paper verificato,12834barre raccolte, screening holdout e stress costi
> calcolati per quattro strategie; scalping/BTC senza dataset adeguato.
> Nessun candidato supera i gate; ordini broker e promozione live non implementati/attivati.
> Dettagli e risultati: [PAPER_VALIDATION.md](PAPER_VALIDATION.md). Totale97test automatici superati.

> Aggiornamento successivo, 10 settembre 2026: dopo autorizzazione esplicita dell'utente,
> la versione **1.8.1/build10** è stata installata e riaperta in `/Applications/Dashboard Finanziaria.app`.
> Backup di app1.7 e dati in `.build/install-backups/20260910-130946/`.
> Verificati runtime Python di sistema, avvio nativo, rendering frontend nel browser,
> chiusura con conferma di salvataggio e preservazione semantica di dati e bozza.
> Aggiunto menu nativo per collegamento TWS in sola lettura su scelta dell'utente;
> non attivato durante il collaudo. Partenza sempre offline. Due nuovi test verificano
> serializzazione dei salvataggi e ripresa dopo errore: totale automatico **78**.
> I riferimenti sotto a mancata installazione e blocco del browser descrivono la verifica precedente;
> il collaudo visivo/accessibilità completo resta distinto dal rendering verificato.

**10 settembre 2026. Baseline precedente: commit0b2e8a1, working tree inizialmente pulito.**
Questo incremento evolve il repository esistente; non crea un nuovo prodotto da zero. Le modifiche sono locali, non pubblicate, non installate sopra la copia in `/Applications`. La richiesta di sei strategie del testo allegato prevale sulla precedente versione di cinque: Bitcoin spot è la sesta, esclusivamente simulata.

## Executive summary

La dashboard personale è riutilizzabile. Sono state corrette vulnerabilità HTTP/supply-chain individuate, migliorata la protezione dei salvataggi e aggiunto un laboratorio offline con sei strategie deterministiche, risk engine/ledger transazionale, allocator e strumenti di backtest. **Non è una piattaforma B2C pronta alla vendita, né un sistema di paper IBKR/live operativo.** I test verificano sicurezza e contabilità del software con dati sintetici; non dimostrano redditività.

Decisione netta: proseguire con prodotto A/B (budget e monitoraggio read-only) e ricerca locale; niente C/D pubblico o denaro reale finché gate quantitativi, legali, broker, privacy e operativi non sono soddisfatti. Il target20% netto resta sperimentale. Non è stato imposto alle strategie e non è mostrato come previsione.

Strategia con uno specifico profilo di rischio e potenziale rendimento, senza garanzia di risultato. Il capitale investito può subire perdite, anche rilevanti.

## Output richiesti: indice delle evidenze

| # | Output | Dove leggerlo |
|---|---|---|
|1|Executive summary|questo rapporto|
|2–3|Audit e gap analysis|[AUDIT.md](AUDIT.md)|
|4–5|Ricerca IBKR con date/fonti e normativa preliminare|[IBKR_COMPLIANCE.md](IBKR_COMPLIANCE.md)|
|6–8|Architettura corrente/target, trust boundaries, threat model e credenziali|[ARCHITECTURE_SECURITY.md](ARCHITECTURE_SECURITY.md), matrice credenziali IBKR_COMPLIANCE|
|9|Risk engine, ordine, ledger, audit, recovery|[RISK_ENGINE.md](RISK_ENGINE.md)|
|10–11|Sei strategie e confronto|[STRATEGIES_RESEARCH.md](STRATEGIES_RESEARCH.md)|
|12–13|Allocator e backtest/validazione/dataset|STRATEGIES_RESEARCH, moduli research|
|14–17|UX, abbonamenti, roadmap e registro rischi|[PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)|
|18–21|Modifiche, test/risultati, elementi non implementati|sezioni seguenti|
|22|Prossime dieci azioni ordinate|PRODUCT_ROADMAP, tabella conclusiva|

## Modifiche implementate

| Area | File | Risultato concreto |
|---|---|---|
|Protezione HTTP|local_security.py, ibkr_paper_bridge.py|Host/Origin esatti, anti DNS rebinding, Sec-Fetch-Site, CORS wildcard rimosso, CSRF per mutazioni, JSON/content-type/size/depth/finiteness, rate limit e timeout|
|Frontend/supply chain|vendor, scripts/build-web.cjs|React18.3.1 e React DOM18.3.1 locali; Babel7.28.5 solo build; licenze/hash versionati, CSP script-self senza eval nella pagina servita; build obsoleta rifiutata|
|Memoria esistente|ibkr_paper_bridge.py, HTML|JSON compatibile, fsync+rename, file0600, backup precedente; non sovrascrive file corrotto; frontend blocca autosave dopo load fallito|
|Broker|bridge, launcher|offline predefinito; monitor-readonly esplicito preserva letture esistenti; metodi ordine/cancellazione SDK bloccati; nessuna route ordine live|
|Quantità/valori|research/engine.py|Decimal, allowlist/valuta USD, identità locale e6strategie; BTC richiede strategia/consenso distinti; altri strumenti crypto/substituti respinti|
|Rischio/OMS simulato|engine.py|transazioni, riserve cash/esposizione incl pendenti, idempotenza persistente, limiti giorno/strategia/account/valuta/settore, quote fresche, no short, partial fill conservativi, pause/kill/cancel distinti|
|Persistenza ricerca|SQLite isolata schema1|audit hash chain+digest ledger, trigger append-only, tamper fail closed, rollback, riavvio pausato e riconciliazione richiesta, schema futuro rifiutato|
|Strategie|strategies.py|sei generatori deterministici,6catalog entries, tre varianti BTC, filtri/sizing/uscite spiegabili; tutti research_unvalidated|
|Allocator|allocator.py|Conservativa/Bilanciata/Dinamica, covariance/capacità/rischio/regime, matrice PSD, no leva, dati incompleti o strategie non validate lasciano cash|
|Percorso integrato|pipeline.py|segnale auditato→risk→simulatore; non accetta adapter esterno; script demo su DB temporanei|
|Backtest|backtest.py|quote/next observation, spread/slippage/commissioni/FX/interessi/data cost, nonfill/partial/reject/outage/weekend; metriche, walk-forward e bootstrap senza risultati inventati|
|UX|ResearchPanel nello stesso HTML|laboratorio chiuso inizialmente,6bot/costi/conteggi/motivi reali, null→Da calcolare, controlli e audit separati dal patrimonio; VaR basato su flussi sospeso|
|Verifiche|tests, pyproject, scripts/check_repository.py|test avversari, lint/type checks, controlli integrity/import/secret patterns; workflow CI configurato, non eseguito su GitHub|
|Build macOS|build-macos-app.sh|bundle locale1.8/build9 include moduli/frontend; deployment target compilatore13.0 coerente col plist; firma ad hoc verificata; non installato/distribuito|

## Verifiche eseguite e risultati

Tutte le fixture sono sintetiche. I test HTTP creano directory e porte temporanee e un fake SDK incapace di connessione broker. Server locale di QA avviato con `--broker-mode offline` e `DASHBOARD_DATA_DIR=/tmp/dashboard-fintech-audit-20260910`, nessun dato dell'utente. Nessuna password/account broker reale letto, nessun ordine inviato, nessuna chiamata commerciale o autorizzazione firmata.

| Verifica | Comando / perimetro | Risultato |
|---|---|---|
|Baseline|8test Python originali|8/8 passati prima degli edit applicativi|
|Unit/integration offline|python3 -m unittest discover -s tests -p 'test*.py'|**68/68 passati**: legacy8 preservati + sicurezza/risk/quant/pipeline|
|HTTP reale loopback|python3 tests/http_smoke.py|**4/4 passati**: CORS/rebinding, asset/CSP, CSRF/autosave,6bot e no live route|
|Polling frontend|node --test tests/test-polling.cjs|**4/4 passati**: dedup/timeout/stale/abort/legacy|
|Build JSX|node scripts/build-web.cjs|riuscita, dipendenze locali hash validate|
|Lint|ruff check .|passato (E9/F; non lint stilistico completo)|
|Type checking|mypy|passato su7moduli nuovi con check_untyped_defs; non modalità strict e non bridge SDK legacy|
|Compatibilità sintattica|Python3.9.6 compileall con cache temporanea|passata per backend/moduli/test/scripts; non test runtime IBKR3.9|
|SAST|Bandit su backend+research|0high/0medium;5low esaminati, descritti sotto|
|Dependency Python|pip-audit ibapi9.81.1.post1|nessuna vulnerabilità nota restituita il10/09/2026; non verifica funzionalità SDK attuale|
|Dependency frontend|OSV querybatch per React/React DOM/Babel versionati|nessun advisory restituito per i3pacchetti; non SBOM completo delle dipendenze incorporate|
|Controlli repository|scripts/check_repository.py|hash vendor, assenza import trasporti nel research, focused secret patterns: passati|
|Build macOS locale|NODE_BIN=... ./scripts/build-macos-app.sh|riuscita1.8; codesign --verify --deep --strict passato; otool minos13.0|
|Icona|iconutil nel build|rigenerazione fallisce in questo ambiente; fallback icona precedente conservata, build riuscita; fresh clone richiede fix icona|
|Diff|git diff --check|passato; nessun commit/push/merge/distribuzione in questo incarico|
|UI visuale|tentativo browser localhost8771|**non eseguita**: auto-review rifiuta per limite utilizzo account; non sostituita da test HTTP|
|CI remota|.github/workflows/local-checks.yml|configurata soltanto, non avviata/pubblicata|
|Performance storiche/backtest di mercato|dataset reali/licenze assenti|**da calcolare**, nessun CAGR/redditività storica dichiarati|

Totale test automatici eseguiti: **76 passati** (68Python+4HTTP+4Node). Non equivale a copertura100%, pen test, compliance o validazione quantitativa. Sono stati trovati e corretti durante integrazione: fixture BTC senza breakout effettivo, limiti ordine correttamente bloccanti nella pipeline, recovery time dal picco anziché dalla prima osservazione in perdita e riserve pendenti trasferite al budget del giorno successivo.

Cinque finding Bandit LOW: import subprocess, chiamata selettore Windows con script costante/no shell e percorso executable relativo (risolvere percorso fidato prima distribuzione Windows), best-effort stop SDK con except/pass preesistente, RNG seeded Monte Carlo non crittografico. Nessun finding high/medium nel perimetro scelto; non sono stati eliminati dal codice mediante soppressione indiscriminata. Secret scan locale è mirato e non sostituisce scansione completa della storia Git/CI. Nessuno scanner certifica l'assenza di vulnerabilità sconosciute.

## Non implementato e perché

| Elemento | Motivo concreto / requisito |
|---|---|
|Invio ordini IBKR paper|gate ricerca→paper non soddisfatto: dataset/costi/OOS e account/configurazione/accordi non verificati; non corretto abilitare un adapter solo perché porta7497|
|Qualunque live trading|vietato dall'incarico senza autorizzazione separata, nessun trasporto implementato; mancano anche gate normativi/contrattuali/operativi|
|BTC reale o paper broker|permessi/residenza/affiliata/route e minimi/precisioni/paper non attestati sul conto; soltanto BTC spot sintetico, nessuna sostituzione|
|Performance storiche e scelta variante migliore|nessun dataset licenziato/caricato; fixture non rappresentano mercato; target20% non dimostrato|
|Feed dati/ranking/eventi point-in-time|licenze provider, calendario/corporate action/delisting/FX e qualità da verificare; dati di contesto non inventati|
|IAM passkey/MFA multiutente, sessioni cloud, RBAC/RLS|MVP locale utente OS; hosting/identità e modello legale non scelti. Architettura documentata, non scaffold di login insicuro|
|Cifratura applicativa/KMS/backup cifrati|non esiste key lifecycle implementato; plaintext locale dichiarato. Non aggiunta crypto artigianale o chiave nello stesso DB|
|Audit davvero non alterabile|SQLite locale non resiste all'admin che ricostruisce tutto. Necessari collector/storage WORM e checkpoint firmati separati|
|Mobile iOS/Android|nessun client nativo precedente; contratto API/IAM e piattaforma da definire, responsive non dichiarato app mobile|
|Billing/entitlements commerciali|piani proposti, nessun prezzo/contratto/incasso senza decisione modello e preventivi|
|Transazioni/dividendi/commissioni ufficiali e P/L storico IBKR|richiedono statement/Flex/API licenziata e prove riconciliazione; snapshot account non sufficiente|
|Riconciliazione broker/outbox distribuito|soltanto ledger locale testato; nessun eseguito IBKR disponibile per contract testing|
|Pen test/SIEM/DR/Beta|servizi/contratti/infra non provisionati né autorizzati; baseline e runbook progettati|
|Installazione app1.8 e pubblicazione GitHub|incarico limita al repository/local safe work, non distribuzione; app nel Dock resta la versione precedente|
|Collaudo visivo/accessibilità|blocco strumento browser per limite account, da completare prima di rilascio|

I criteri relativi alla piena sicurezza B2C, isolamento infrastrutturale paper/live, audit WORM e beta **non risultano completati**. Dichiararli soddisfatti con sole classi locali, flag o test sintetici sarebbe scorretto. Il deliverable realizzato è una baseline locale verificata e una roadmap con gate concreti, non la piattaforma finale.

## Raccomandazione conclusiva

- **Già pronto per uso locale/test:** dashboard preesistente con hardening, backup compatibile e laboratorio di ricerca; usare build servita su localhost, completare QA visiva prima di installare questa build sopra l'app personale.
- **Utilizzabile in paper:** simulatore offline con dati sintetici e percorso segnale→rischio→ledger; **non** paper forward IBKR validato. Nessuna delle sei strategie è promossa.
- **Per beta:** QA desktop/mobile, cifratura/restore/concorrenza, identity/tenant se cloud, licenze/termini/privacy, firma/runtime packaging e pen test con remediation.
- **Per vendere:** qualificazione professionale A–D/MiFID/MiCA, accordi IBKR/dati, responsabilità/contratti/marketing, supporto e unit economics, privacy e resilienza adeguate.
- **Prima del trading reale:** tutte le condizioni precedenti, dati/OOS/forward solidi, paper isolato attestato, reconciler/OMS e controlli rischio indipendenti, on-call e audit esterno, approvazione separata esplicita; **NO-GO attuale**.
