# Deterministic risk engine e OMS simulato

Implementazione locale: `research/engine.py` + `pipeline.py`, SQLite schema1 (versioni future rifiutate), identità fissa `local-research`, capitale sintetico100000 USD. Nessun socket/ibapi/client HTTP, nessun parametro ambiente live, nessuna password o token broker. Non è un OMS di produzione certificato. L'HTTP non espone submit/process; propone solo snapshot, catalogo e controlli del simulatore. Il flag `live_enabled:false` è informativo: il blocco effettivo deriva dall'assenza di un trasporto live.

Strategia con uno specifico profilo di rischio e potenziale rendimento, senza garanzia di risultato. Il capitale investito può subire perdite, anche rilevanti.

## Modelli e invarianti

`Order`: chiave idempotente, account fisso, strategyID fra6, symbol allowlist, BUY/SELL, quantità e limit Decimal, valuta USD. Rifiuta NaN/Infinity/bool/negativi, precisione non supportata, short involontari, account diversi, BTC fuori dalla sua strategia e sostituzione BTC con ETF. L'allowlist attuale SPY/QQQ/IWM/TLT/GLD/AAPL/MSFT/BTC identifica fixture di software e non strumenti raccomandati o idonei per un retail italiano.

`Quote`: bid/ask, size, timestamp, latenza, reliable/event_blocked/available booleani. Fail closed su prezzi crossed, quote stale/future, liquidità bassa, spread/latency. Incrementi1 unità per equity e1e-8 BTC sono scelte della simulazione, **non** metadati negoziazione IBKR confermati.

Ordine operativo simulato: `evaluate` → `record_signal` → proposta → `ResearchEngine.submit` → transazione/rischio/audit → accepted/blocked → `process` su osservazione successiva → nuova verifica/rischio → partial/filled. Nessuna interfaccia pubblica che esegua fill senza controlli. Il calcolatore `backtest.run` è contabilità controfattuale separata priva di capability di esecuzione: non va usato come servizio ordini.

## Limiti implementati

| Controllo | Default account sintetico | Regola |
|---|---:|---|
| Singolo ordine |2000 USD|notional=quantity×limit; rifiuto sopra cap|
| Esposizione account |50000 USD|posizioni+BUY pendenti+proposta|
| Strategia |10000 USD e cap percentuale StrategySpec|applica min dei cap; quote aggiornate per posizioni|
| Strumento |10000 USD e20% equity|somma posizione e residui pendenti|
| Settore |25000 USD|un unico bucket ignoto conservativo, non look-through inventato|
| Valuta |50000 USD|solo USD, altre valute rifiutate|
| Giornaliero |20000 USD notional /30 ordini|accettati e ordini pendenti trascinati nel nuovo giorno; cancellati non liberano budget giornaliero|
| Turnover |50% equity|notional prenotato, no moltiplicazioni da retry|
| Loss day |1000 USD o loss% strategia se inferiore|equity con bid marks affidabili|
| Drawdown |8% o DD strategia inferiore|da massimo equity osservato|
| Bitcoin |consenso distinto, cap5% da spec, weekly loss1,5%|no altra crypto/strumento sostitutivo; revoca cancella residui simulati BTC|
| Spread |15bp o spec inferiore|sul bid, ulteriori soglie scalping|
| Slippage |5bp avversi|mai fill fuori dal prezzo limite|
| Price collar |30bp|limit vs mid valido|
| Latenza |500ms, scalping100ms|dato oltre soglia bloccato|
| Freshness |5s o spec inferiore|timestamp futuro/stale, portafoglio senza marks => blocco|
| Liquidità |size≥100, partecipazione10%|budget di quote condiviso fra ordini e dedup per timestamp|
| Cancellazioni |20 al giorno|blocca nuovi ingressi oltre budget; cancellazione emergenza resta possibile|
| Commissioni simulate |1USD +10bp/fill|riserva costo fino a20 partial fill; costo scalato alla quantità|

Limiti di segnale (time stop, massime entrate, cooldown, rischio per trade, filtri eventi) sono applicati dalle sei strategie; il risk engine verifica indipendentemente account/quote/esposizioni/finanziamento. Gap da colmare prima di paper collegato: attestazione della qualità dei dati, registrazione firmata parametri strategia, lifecycle stop/expiry e calendario venue, portfolio marks continui, rischio per settore look-through e FX reali, quote/provenienza server-authoritative. Un chiamante Python che modifica codice o storage con privilegi amministrativi è fuori dal modello di protezione single-user; il target execution separato deve usare autorizzazioni/capability non disponibili ai produttori di segnali.

## Ordini, riserve, recovery

- Chiave idempotenza persiste across restart. Stessa chiave/stesso contenuto restituisce ordine precedente; contenuto diverso rifiutato. Commit atomico di stato/ordine/audit e rollback se il disco/audit fallisce.
- Pending BUY consuma cash+commissioni e cap; pending SELL riserva quantità posseduta dalla stessa strategia; niente posizione short né vendita della quota di un'altra strategia.
- Fill possibile solo dopo fill_delay0,25s e successiva quote; partecipazione condivisa, arrotondamento quantità conservativo, quote ripetuta non crea doppio fill; budget20 eventi parziali poi cancellazione locale esplicita nel log.
- Capitale iniziale sintetico e ledger cash long-only: nessun prestito per fee. Prezzo ask+slippage/bid−slippage, mai migliore inventato. P/L realizzato aggregate cost basis include acquisto/fee; P/L per bot non disponibile resta null, non inventato.
- Riavvio impone pausa e `reconciliation_required`. Riconciliazione locale verifica integrità hash/ledger, cash e quantità per strategia; non equivale a riconciliazione IBKR di ordini esterni.
- Pausa blocca nuovi ordini, **non** fill di pendenti già accettati. Kill globale o strategia blocca esecuzioni simulate; cancel_pending è diverso e non vende posizioni. Kill resta persistente e non è resettabile via API. Nessuna funzione close_positions live o simulata nella UI.
- I limiti giornalieri/settimanali si riferiscono al primo mark osservato nella finestra UTC: non sostituiscono un equity snapshot ufficiale a mezzanotte. DD da high water contribuisce al controllo overnight; calendar/mark service serve prima di paper collegato.

## Audit e confini della garanzia

Schema: `state(tenant,data)`, `orders(tenant,id,data)` con primary key composta, `audit(seq,tenant,body,previous,hash)`. Body contiene evento, dettaglio, timestamp di registrazione e digest dello stato e ordini. Hash SHA256 collega record precedenti; trigger impediscono UPDATE/DELETE accidentali sull'audit. Rileva cancellazione audit con ledger presente e modifiche out-of-band a stato/ordini. SQL parametrizzato. File0600 e directory nuova0700; non cifratura.

**Tamper evident locale, non immutabile assoluto**: amministratore può ricostruire l'intero DB/catena o cancellare tutto. Produzione richiede storage WORM con collector indipendente, checkpoint firmato fuori dal DB, ruoli separati e retention legale. Non introdotto un segreto hardcoded per simulare una garanzia inesistente. Successo test hash non è certificazione non ripudiabilità.

## Test e criteri di promozione

Test offline coprono importi invalidi, account/asset vietati, stale/future, eventi/spread/liquidità/latency, idempotenza/concorrenza, partial/dedup, limiti aggregati e carry overnight, no short, pause/kill/cancel, revoca BTC, restart/reconcile, ledger/audit tamper, schema futuro, rollback del commit. Pipeline test dimostra segnale ENTER bloccato da pausa rischio e dati incerti senza ordine.

Prima di paper IBKR: dataset verificati, manifest strategia e prova OOS/stress, adapter compatibile col conto e SDK ufficiale, contratto broker/dati e ambiente paper attestato, parser esecuzioni/commissioni, outbox idempotente e test disconnessione/ripartenza. Prima di live: aggiungere tutti gate legali/operativi e autorizzazione separata; nessun flag del presente codice può abilitarlo.
