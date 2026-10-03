# Prodotto, UX, abbonamenti e roadmap

10 settembre 2026. Tutto ciò che segue una fase locale è subordinato ai gate e non è stato distribuito. Priorità: protezione del capitale e dati, robustezza, controllo drawdown, poi rendimento netto corretto per rischio. Il20% non è obiettivo assegnato ai singoli bot né promessa di vendita.

Strategia con uno specifico profilo di rischio e potenziale rendimento, senza garanzia di risultato. Il capitale investito può subire perdite, anche rilevanti.

## UX

Preservate tre sezioni richiudibili: Stima stipendio, Gestione finanze (bozze/storico/riepilogo), Wealth management. Aggiunto un Laboratorio strategie separato e inizialmente chiuso, con sei schede e dicitura simulatore locale/live disabilitato. Spiegazioni e avvertenze disponibili senza confondere il patrimonio reale con cash/fill sintetici. Nessun indicatore di rendimento inventato: campi null mostrano Da calcolare. Nessun conto broker usato nei test. Nessun bottone compra/vendi reale, abilitazione live, leva o cambio limiti.

Controlli distinti: pausa nuove proposte simulate, annulla pendenti simulati, arresto emergenza. Nessuna liquidazione della posizione a seguito di un generico stop. Per produzione aggiungere conferma specifica della chiusura (conto, quantità, tipo ordine, stima commissioni/slippage, perdita e fiscalità), mandato, accessibilità e step-up autenticazione.

Snapshot bot: identità/orizzonte/rischio, stato, ultimo segnale e motivo, heartbeat solo se osservato, costi e conteggi realmente presenti. Performance storiche e capitale per bot restano non calcolati senza run valido. Audit/limiti/ordini tecnici raccolti in dettagli richiudibili; successivo design consumer deve tradurre i codici di blocco in azioni comprensibili senza far sembrare un errore di dati un invito a negoziare.

Mobile: CSS esistente e nuova griglia rispondono alla larghezza; non è un'app iOS/Android. Prima client mobile scegliere contratto API/IAM stabile, secure storage, biometria locale, session revoke e notifiche minimizzate. Test touch, lettori schermo, focus, contrasto, traduzioni e device reali prima di beta. Non memorizzare dati finanziari in cache PWA senza threat model offline. Collaudo browser locale tentato ma bloccato per limite utilizzo dello strumento: non dichiarato superato.

## Abbonamenti proposti, non attivati

| Piano | Conti / storico indicativo | Capacità | Restrizioni |
|---|---|---|---|
| Personale |manuale,1 profilo,24mesi|cashflow, patrimonio e export personale|nessun broker/trading; privacy e cancellazione facili|
| Analisi |1 broker autorizzato, storico esteso|read-only, analytics descrittive, report/alert|licenze dati separate e trasparenti; niente consulenza implicita|
| Laboratorio |1 conto paper approvato|strategie ammesse dal percorso formativo, fino a4, report di ricerca|accesso solo dopo comprensione e gate paper; nessuna garanzia di risultato|
| Ricerca avanzata |fino a3 conti consentiti dal broker|fino a6 strategie, limiti personalizzabili solo entro massimi, export ricerca/supporto prioritario|BTC consenso distinto; complessità/appropriatezza prevalgono sul pagamento; live non incluso automaticamente|

Sono ipotesi di packaging: quantità/retention devono essere allineate a contratti, capacità e privacy. Nessun prezzo pubblicato finché non ci sono preventivi. Nessuna strategia definita più redditizia perché nel piano più caro; upgrade non elude test, consenso o appropriatezza. Billing non implementato per evitare contratti/incassi involontari. Entitlements target applicati lato server in aggiunta a IAM, consenso e rischio, non solo nascondendo pulsanti.

Unit economics da quotare: ARPU netto di IVA/sconti/rimborsi meno cloud, storage/egress, dati display/non-display e licenze per username, pagamento/chargeback, supporto/on-call, security monitoring, audit/pen test, consulenza/compliance, assicurazione cyber/professionale. Costi fissi mensili/amortizzati separati da marginali; break-even utenti = fissi / contribution margin positivo. Testare scenari alto supporto, eventi mercato, conversione/churn e costo dati superiore al piano; nessuna marginalità inventata. Servizi broker/dati devono poter essere disattivati quando non sostenibili senza bloccare export/cancellazione dell'utente.

## Roadmap incrementale con criteri di accettazione

| Fase | Deliverable/file | Dipendenze/test | Rischio / accettazione e go/no-go | Escluso |
|---|---|---|---|---|
|0 Audit|AUDIT.md, inventario/baseline|README/git/test esistenti|nessuna modifica utente persa; stato documentato: eseguito|recupero chat/app account|
|1 Vulnerabilità|local_security.py, handler, vendor/build-web|test Origin/Host/CSRF/JSON, scan|cross-origin lettura negata; importi non finiti rifiutati; completo localmente con limiti documentati|certificazione ASVS/pen test|
|2 Cashflow/wealth|HTML/persistenza JSON, backup/permessi|roundtrip bozze, errore load, polling|no sovrascrittura corrupt; sospeso VaR da flussi; da aggiungere concurrency/migrazioni cifrate|fisco e statement ufficiali|
|3 Broker simulato|research/engine.py|fixture, SQLite atomico|nessun import rete, ledger separato: pronto per test|broker reale|
|4 Risk engine|engine.py/pipeline.py,RISK_ENGINE.md|idempotenza/reserve/limiti/faults|nessun submit operativo che elude il controllo; non production-ready|firma KMS distribuita|
|5 Strategy interface|strategies.py Signal/Context|bad input, stale, future, session|proposte senza capability broker; tutti unvalidated|AI esecutiva|
|6 Sei strategie|strategies.py, STRATEGIES_RESEARCH.md|ingresso/uscita/filtri e BTC3varianti|regole eseguibili; nessuna promozione senza dati|rendimenti garantiti e altri crypto|
|7 Backtest|backtest.py, dataset protocol|next observation/costi/nonfill/metriche/embargo|harness testato; dati reali mancanti => nessun risultato storico|scalping OHLC, ottimizzazione sul test|
|8 Dashboard bot|ResearchPanel/API snapshot+control|test API/build JSX; visual QA bloccata|sei bot/null corretti, controllo simulatore; beta dopo QA browser/mobile|annullamento/chiusura IBKR|
|9 Paper IBKR|adapter futuro separato|SDK ufficiale, account attestato, rete deny-live, dati/licenze, gate quant|NO-GO finché mancano contratto/account/gate; connettore read-only esistente non certifica paper execution|password raccolte, live|
|10 Riconciliazione|OMS/outbox/reconcile futuro|execId/permId/commissioni/snapshot restart|zero ordine reinviato in UNKNOWN, prove partial/cancel/reconnect|riavvio cieco|
|11 Beta chiusa|IAM/privacy/telemetria/supporto|contratti, installazione firmata, cifratura, QA|solo A/B o simulato con consensi, export/delete/recovery verificati|pubblico generalizzato C/D|
|12 Pen test|report indipendente/remediation|ASVS/MASVS scope, staging|no critical/high aperti, retest documentato|autocertificazione|
|13 Legale/contratti|accordi vendor/dati, perimetro A-D|IBKR, legale fintech/privacy, autorità ove necessario|go scritto per flussi/paesi e marketing, responsabilità definite|presunzione esenzione perché locale|
|14 Live eventuale|infrastruttura separata non presente|forward sufficiente, costi/slippage osservati, on-call, risk/mandato, approvazione utente|NO-GO attuale; capitale ridotto solo dopo autorizzazione separata|auto-promotion dal20%|

## Registro dei rischi

| ID | Rischio residuo | Priorità | Owner | Gate/mitigazione |
|---|---|---|---|---|
|R01|Prodotto confuso con servizio di investimento autorizzato|P0 per vendita|legale/product|modello A/B iniziale, qualificazione e contratti prima C/D|
|R02|Ricerca presentata come performance reale|P0|quant/product|null/da calcolare, provenance, dataset hash/OOS e disclosure|
|R03|Credenziali live/rete presenti nel paper|P0|security/trading|simulatore senza trasporto; futuro paper in VM dedicata e account attestato|
|R04|Plaintext locale e nessun IAM multiutente|P0 per cloud/P1 locale|security/privacy|non esporre loopback; Keychain/envelope/tenant IAM prima beta|
|R05|Admin riscrive/cancella audit SQLite|P0 per live|SRE/security|WORM/checkpoint firmato esterno e segregazione ruolo|
|R06|Fill modello troppo ottimistico/scalping non fattibile|P0 promozione|quant/data|L2, queue/latency/costi, no paper se edge assente|
|R07|SDK vecchio/callback incompatibili|P1|IBKR engineer|SDK ufficiale pin e matrice TWS/Gateway/API; prove offline/contrattuali|
|R08|Supporto BTC/spot venue/paper non confermato|P0 BTC collegato|IBKR/legale|solo BTC sintetico; nessun ETF sostitutivo automatico|
|R09|HTTP locale non adatto a pubblico/DoS|P0 cloud|architect/SRE|gateway/server production e IAM; no bind pubblico|
|R10|Conflitti multiwindow cashflow, backup unico|P1|full-stack/data|revisioni optimistic locking, backup cifrato/versioni e restore|
|R11|Mac package Python esterno/firma ad hoc/arm64|P1 beta|desktop/DevSecOps|runtime embedded/licenze, notarizzazione, Intel se richiesto, install test|
|R12|Collaudo browser non eseguibile nel turno|P1 rilascio|UX/QA|rieseguire prove visuali/touch/accessibilità; non distribuire prima|
|R13|Costo licenze/supporto erode margine|P1 vendita|product/finance|preventivi e unit economics, no pricing promesso|
|R14|Monitor P/L/FX/ETF domicilio ambiguo|P1|data/quant|metric provenance/periodo; Flex statements e look-through licenziato|
|R15|Mobile/IAM/passkey/payments non implementati|P1 beta commerciale|mobile/security|architettura contratto API prima sviluppo, nessun placeholder venduto|

## Dieci prossime azioni, in ordine

1. Completare QA browser delle quattro sezioni, salvataggio/riapertura e controlli laboratorio su desktop e touch, poi risolvere eventuali regressioni.
2. Revisione indipendente delle modifiche sicurezza e rischio con test avversari aggiuntivi; non installare la build di ricerca sopra l'app personale prima della verifica.
3. Progettare migrazione cashflow con backup cifrato/Keychain, revisioni per concorrenza e prova restore senza perdita bozze.
4. Ottenere da IBKR conferma scritta di architettura vendor/paesi/API/permessi, licenze dati e BTC/paper ZEROHASHE.
5. Definire con legale fintech/privacy il primo modello A/B, contratti, DPIA/retention e responsabilità; valutare MiCA per BTC.
6. Acquisire dataset licenziati point-in-time e calendar/event/FX/corporate-action pipeline con manifest verificabili.
7. Eseguire benchmark/OOS/walk-forward/sensibilità/costi raddoppiati per tutte6, scartando strategie non robuste; nessuna ottimizzazione per forzare20%.
8. Aggiornare SDK ufficiale e sviluppare adapter paper separato con egress deny-live, OMS/reconcile e forward test autorizzato.
9. Implementare IAM passkey/MFA, tenant RLS, KMS/WORM/monitoring e client mobile soltanto dopo decisione di beta/cloud.
10. Pen test e restore/incident drill, validazione contratti e unit economics; eventuale richiesta **separata** di valutazione live solo dopo tutti gate.
