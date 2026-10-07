# Prezzo di chiusura e P/L a chiusura — build92

Su richiesta dell'utente, la tabella delle posizioni IBKR Live usa ora esclusivamente
il prezzo di chiusura. Il runtime non importa più `liquidation_quotes` e non invia
richieste streaming BID/ASK. L'implementazione precedente resta solo come codice
storico e test fuori dal pacchetto compilato.

`closing_prices.py` richiede barre giornaliere `TRADES`, `useRTH=1`, `keepUpToDate=False`,
durata due settimane, tramite `reqHistoricalData`. Per le azioni/ETF conserva conId,
valuta e primaryExchange e imposta SMART. Nessun ordine, snapshot regolamentare,
acquisto di abbonamenti o provider esterno. Non usa `ADJUSTED_LAST`: le rettifiche
per dividendi sono appropriate allo storico del modello VaR/ES, non al prezzo
di chiusura visualizzato contro il costo di acquisto.

La data della barra è sempre visibile sotto il prezzo. Si escludono sedute future
o parziali usando fuso orario e liquidHours forniti da IBKR. Si include la giornata
corrente solo dopo la fine di tutti i segmenti della seduta ordinaria più venti
minuti di margine di pubblicazione. In assenza di calendario utilizzabile si
esclude conservativamente la giornata corrente; senza fuso si attendono i metadati.
Weekend/festivi usano l'ultima barra disponibile entro il limite. Si verifica
nuovamente ogni ora, anche dopo errori; nessun cambiamento del prezzo ogni minuto.

Per STK (azioni/ETF):

`P/L non realizzato a chiusura = quantità con segno × (chiusura − costo medio IBKR)`

Stesso prezzo per long e short; quantità frazionarie conservate. Il costo medio
proviene dalla posizione aggregata IBKR, non dai singoli lotti. Valuta del contratto.
Non è un prezzo di liquidazione attuale, né un utile garantito; escluse commissioni
di uscita. Il P/L e i totali attuali forniti da IBKR restano separati e invariati.
Altri tipi di contratto non producono una stima con una convenzione non verificata.

La serie è accettata solo dopo historicalDataEnd, senza errori, con prezzi finiti
positivi e date valide. L'avviso2188 non termina anticipatamente una richiesta:
IBKR può fornire barre completate anche senza dati fino al secondo corrente.
Timeout45secondi; generazioni distinte impediscono callback tardivi dopo reconnect.
Richieste seriali e cache RAM oraria; nessuna modifica ai dati finanziari salvati.

Prova diagnostica reale del7ottobre2026: stesso contratto IBKR corrente,
SMART/TRADES/RTH, `ready`, chiusura90.58USD del2026-10-06. Il codice2188 precede
la serie completata e non è un rifiuto di queste barre giornaliere.

Fonti primarie: [barre storiche IBKR](https://interactivebrokers.github.io/tws-api/historical_bars.html),
[campi prezzi IBKR](https://www.interactivebrokers.com/docs/web-api/v1/endpoints/market-data/market-data-fields).
