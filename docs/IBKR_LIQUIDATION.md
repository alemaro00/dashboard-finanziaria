# P/L di liquidazione stimato

**Implementazione storica fino alla build91, sostituita nella build92.**
La versione installata usa prezzi di chiusura, non BID/ASK: vedere
[IBKR_CLOSING_PRICES.md](IBKR_CLOSING_PRICES.md).

Posizioni IBKR Live usa il BID per chiudere una posizione long e l'ASK per
ricomprare una posizione short. Sostituisce la precedente valutazione storica ASK.
Quantità e costo medio provengono dalla posizione aperta IBKR, non dai singoli lotti.

Formula in valuta del contratto:

`quantità firmata × (prezzo del lato di chiusura × moltiplicatore − costo medio IBKR)`

Per STK il moltiplicatore è 1; OPT, FUT e FOP richiedono un moltiplicatore positivo.
Il costo medio unitario visualizzato è il costo IBKR diviso per il moltiplicatore.
Non sono stimati strumenti con convenzioni diverse né valori non finiti.
Il P/L attuale fornito da IBKR resta separato, senza alterare i suoi totali.

Le richieste sono streaming `reqMktData`, senza snapshot regolamentari a pagamento,
con `reqMarketDataType(3)`: IBKR può fornire dati live se autorizzati, altrimenti
ritardati. Sono riconosciuti dati live, ritardati, congelati e ritardati/congelati.
Se dopo 30 secondi non è arrivato alcun BID/ASK della nuova richiesta, viene
richiesto il tipo 4 (delayed frozen), per recuperare l'ultimo dato disponibile
anche a mercato chiuso. Dopo un'ora viene riprovato il tipo 3. Il tipo
effettivo resta quello dei callback IBKR, non quello richiesto.
La UI riporta “Last Update HH:MM”, orario di ricezione nella Dashboard (fuso Roma), non un
timestamp di borsa. Il ritardo preciso non è fornito da questi callback.

Quote mancanti, tipo sconosciuto o connessione interrotta non producono P/L.
Dopo un'ora lo stream viene cancellato e richiesto
nuovamente, con un nuovo identificatore e senza accettare callback del vecchio.
La richiesta non cambia l'orario originale dell'ultima quotazione. Durante questa
attesa il P/L attuale è nullo ma l'ultima stima resta visibile, esplicitamente
etichettata come non attuale. Non è un prezzo eseguibile garantito. Le nuove
richieste sono limitate a una ogni ora per contratto (eccetto il recupero iniziale
del dato congelato); i tick intermedi validi non cambiano prezzo né orario.
Tick invalidi e cambi di tipo invalidano comunque i dati per sicurezza. Gli errori di
permessi non generano questo rinnovo automatico.
Per azioni/ETF la richiesta usa SMART mantenendo conId, valuta e primaryExchange
originali: il mercato di quotazione non viene usato come feed diretto. Dopo60s
senza alcun nuovo BID/ASK del recupero congelato, lo stato diventa unavailable
con motivo noquotes, non pending infinito. Tick validi successivi recuperano lo
stato automaticamente; nuovi tentativi restano orari. Nessun ripiego su LAST.
Nessun ripiego su LAST, ASK per long o BID per short.
Le quote ritardate/congelate sono esplicitamente indicate come non in tempo reale.
Un cambio di tipo invalida il precedente BID/ASK. Le richieste vengono cancellate
quando la posizione si chiude. Limite di 90 stream, richieste cadenzate.

La stima non garantisce il prezzo di esecuzione, non include commissioni di uscita,
slippage o conversione valutaria. Il collegamento rimane in sola lettura: nessun
ordine, modifica di ordine o acquisto di abbonamenti ai dati di mercato.

Fonti: [tipi di dati IBKR](https://interactivebrokers.github.io/tws-api/market_data_type.html),
[tick BID/ASK](https://interactivebrokers.github.io/tws-api/tick_types.html),
[dati ritardati](https://interactivebrokers.github.io/tws-api/delayed_data.html).

Build91: formule concise distinte nelle note VaR/ES;159test Python e58Node superati.
Verifica reale iniziale: TWS10.52.0d beta negozia protocollo226, storico risk
funzionante ma richieste quote SMART/NASDAQ e reqPositions di client diagnostico
senza risposta. Avviso interno TWS diagnostics upload e successivo No Internet
connection nella finestra login; nessun invio diagnostico effettuato dall'agente.
Riavvio normale TWS autorizzato esplicitamente dall'utente. Nessun acquisto,
ordine, cambio permessi o impostazione TWS.

Esito finale build91: TWS riavviata e ricollegata normalmente, conto corrente e
VaR/ES ready. Nessun nuovo BID/ASK positivo ricevuto dal feed SMART anche dopo
recupero type4; UI TWS non fornisce BID/ASK, nessun P/L inventato. Prove storiche
BID/ASK rifiutate con162, No market data permissions for ISLAND STK; richieste
streaming IEX/NASDAQ in modalità live rifiutate10089 (ulteriore sottoscrizione
API richiesta; delayed disponibile). Non dimostra che ogni dato ritardato sia
a pagamento: le barre ADJUSTED_LAST per rischio funzionano. Valore numerico di
liquidazione non verificabile senza BID/ASK autorizzati. Configurazione account,
eventuale Market Data API Acknowledgement e acquisti richiedono azione utente.
Nessuna modifica al protocollo della Beta: la prova diagnostica opzionale178
resta isolata, non applicata al runtime. Dati personali salvati invariati.
