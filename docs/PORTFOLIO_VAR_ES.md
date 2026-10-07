# VaR ed Expected Shortfall: 95%, un giorno

Modello normale del portafoglio IBKR attuale, non ricostruzione del portafoglio
effettivamente posseduto in passato. Nessun rendimento è ricavato dal bilancio
personale. Investimenti illiquidi esclusi esplicitamente; strumenti IBKR diversi
da STK (azioni/ETF) bloccano la stima, non sono omessi. La valuta base deve essere
EUR; saldi in EUR sono costanti nel modello. La liquidità estera, anche negativa,
è inclusa con esposizione al cambio. Sono esclusi rischi di credito, liquidità,
controparte, tassazione e costi futuri di esecuzione.

Per ogni posizione si richiedono barre IBKR ADJUSTED_LAST giornaliere (rettificate
per dividendi e frazionamenti) attraverso SMART, mantenendo il conId originale
e l'eventuale primaryExchange, non il feed diretto del mercato di quotazione.
Modalità dati 3 (ritardata gratuita ove autorizzata): nessun acquisto. L'avviso
2188 non interrompe la richiesta; si attende historicalDataEnd e si esclude
comunque la giornata corrente dal calcolo. Le richieste mode+data sono serializzate
con il campionamento BID/ASK. Per ogni valuta non EUR, MIDPOINT EUR/valuta su
IDEALPRO, invertito per ottenere EUR per unità di valuta. Le chiusure storiche
sono convertite con cambi dello stesso giorno, non con il cambio corrente.
Esposizione corrente = quantità firmata × prezzo TWS × cambio corrente.

Si tenta una richiesta di 10 Y; su errore non relativo ai permessi si tenta 5 Y.
Una risposta decennale parziale può comunque fornire una finestra valida di 5 anni.
Solo date comuni completate, niente interpolazione. Per scegliere 10 oppure 5 anni
si richiedono: copertura del confine iniziale (tolleranza 10 giorni), almeno
200 osservazioni per anno, nessun intervallo comune superiore a 10 giorni e
ultimo dato entro 7 giorni. Questi sono controlli tecnici di copertura, non una
certificazione del calendario o della qualità del fornitore. Eventuali festività
dei mercati e asincronia delle chiusure possono influire sul campione.
Non si fabbricano cinque anni per titoli con vita più breve.

Scenario giornaliero: somma delle esposizioni correnti × rendimenti storici
semplici rettificati in EUR. Usare le date comuni incorpora le correlazioni;
non si sommano i VaR dei singoli asset. Pesi correnti ipoteticamente costanti,
non strategia buy-and-hold né portafoglio storico reale.

Con media campionaria del P/L μ e deviazione standard campionaria s:

* VaR95 = Φ⁻¹(0,95) × s − μ = 1,644853627 × s − μ.
* ES95 = φ(Φ⁻¹(0,95)) / 0,05 × s − μ = 2,062712808 × s − μ.

Importi in EUR; percentuali rispetto al Net Liquidation positivo del conto.
Valori negativi non vengono troncati: indicano una coda stimata ancora in guadagno,
non un guadagno garantito. La normalità può sottostimare code pesanti, gap e crisi.
Non rappresenta una misura regolamentare o una previsione certa.

Richieste seriali, timeout 45 secondi, limite 50 serie, cache solo in memoria
per la giornata di Roma; errori di permessi non ripetuti nella stessa sessione/giornata.
Nessun abbonamento acquistato, nessuno snapshot regolamentare, nessun ordine.
La composizione viene ricontrollata e cambi di quantità/liquidità sospendono una
stima precedente. Il ricalcolo usa prezzi/saldi correnti TWS, distinto dal prezzo
di liquidazione campionato ogni ora. Dopo cambio permessi occorre ricollegare TWS.

Fonti: [IBKR, barre storiche e rettifiche](https://interactivebrokers.github.io/tws-api/historical_bars.html),
[IBKR, limiti dello storico](https://interactivebrokers.github.io/tws-api/historical_limitations.html),
[MathWorks, ES normale al 95%](https://www.mathworks.com/help/risk/expectedshortfall.html).

Verifica del 7 ottobre 2026, build87: TWS collegata e conto corrente; lo storico
ADJUSTED_LAST del titolo attualmente detenuto è stato rifiutato con codice162,
«No market data permissions for NASDAQ STK». VaR/ES reali non disponibili per
questo account. Formule e pipeline verificati con fixture offline, non con una
serie storica autorizzata dell'account. Nessun acquisto o ampliamento dei permessi.

Correzione build88: prova reale del 7 ottobre. Stesso conId, NASDAQ diretto
rifiutato con162; SMART ha restituito2511 barre ADJUSTED_LAST dal10/10/2016
al06/10/2026. EUR/USD IDEALPRO ha restituito2592 barre dal10/10/2016
al07/10/2026 (ultimo giorno escluso dal modello). Client9.81 incompatibile
con le fractional size rules di IDEALPRO (10285); aggiornato alla distribuzione
ufficiale IBKR10.50.02 e callback errorTime gestito.
Archivio ufficiale verificato tramite SHA256; nessun account
identificativo, saldo o storico privato trasmesso a fornitori esterni.

Build89: il pacchetto ufficiale impone protobuf5.29.5, vulnerabile a
CVE-2026-0994. Il wheel in vendor conserva tutti i file API originali: solo
METADATA (Requires-Dist protobuf5.29.6) e RECORD sono rigenerati da
scripts/build-ibkr-wheel.py. Manifest vendor/SHA256.json blocca il wheel.
L'archivio sorgente ufficiale è scaricabile da
https://interactivebrokers.github.io/downloads/twsapi_macunix.1050.02.zip
(SHA256673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3).
Codice API GPL-3.0-or-later: verificare obblighi di licenza prima di distribuire
pubblicamente. Nessuna modifica al codice API; patch protobuf di manutenzione.

Verifica finale build89 installata: stato ready,10anni,2510rendimenti giornalieri
dal10/10/2016 al06/10/2026; VaR0,06273710287923506EUR,
ES0,0787186947975259EUR. Confermati anche visivamente nell'app.
Impronte di storico mensile, classificazioni, bozze, archivio bancario e chiave
invariate prima/dopo.156test Python,57Node e7HTTP superati; runtime congelato
con cifratura/backup e pip check superati. Audit dipendenze: nessuna vulnerabilità
nota nei pacchetti verificabili; ibapi ufficiale10.50.2 non presente nel database
PyPI e quindi saltato, non dichiarato privo di vulnerabilità.

Fonti aggiuntive: [IBKR, modalità ritardata](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-delayed/introduction),
[IBKR, codici2188/10285](https://www.interactivebrokers.com/docs/tws-api/doc/error-handling/error-codes),
[IBKR, distribuzione ufficiale del client](https://interactivebrokers.github.io/).
