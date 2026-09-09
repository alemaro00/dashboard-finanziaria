# Dashboard finanziaria IBKR Live + Paper

Dashboard locale in sola lettura per unire pianificazione finanziaria mensile,
monitoraggio IBKR Live/Paper e analisi consolidata del patrimonio.

## Funzioni principali

- Gestione mensile di entrate, costi, fondo emergenza, investimenti e flexible cash.
- Storico modificabile con ricalcolo automatico dei cumulati.
- Stato delle sessioni Trader Workstation Live e Paper in un'unica riga.
- Portafoglio IBKR Live con posizioni, P/L, liquidita', asset class e geografia.
- Investimenti illiquidi/non IBKR con valore attuale e P/L stimato.
- Wealth management con sei indicatori operativi, esposizioni, crescita YoY,
  profilo di rischio e Value at Risk parametrico.
- Memoria automatica su disco per mese aperto, storico, voci e bozze in compilazione.

## Avvio rapido

1. Apri Trader Workstation con il conto che vuoi monitorare.
2. Per Live usa la porta 7496; per Paper usa la porta 7497.
3. Abilita Socket Clients. Sul conto Live mantieni attiva Read-Only API.
4. Fai doppio clic su avvia-dashboard-ibkr.bat.
5. Lascia aperta la finestra del collegamento locale.
6. La dashboard si apre su http://127.0.0.1:8765/.

### macOS

L'app nativa si trova in `dist/Dashboard Finanziaria.app`. Aprila con un doppio clic:
avvia il servizio locale, mostra la dashboard in una finestra macOS e lo chiude quando
esci dall'app. Se TWS e' aperto, il collegamento Live/Paper avviene automaticamente.

Per ricreare l'app dopo un aggiornamento del progetto esegui:

```text
./scripts/build-macos-app.sh
```

`avvia-dashboard-mac.command` resta disponibile come avvio alternativo nel browser.
Al primo utilizzo prepara automaticamente l'ambiente Python e installa la libreria IBKR.

Per interrompere il collegamento, chiudi la finestra Terminale oppure premi `Ctrl+C`.

Puoi aprire soltanto Live, soltanto Paper oppure entrambe le sessioni. Il bridge prova
automaticamente a ricollegarsi. La dashboard e' una sola: non serve aprire anche il
file salary-planner-react.html con l'indirizzo file://.

Se TWS chiede di autorizzare una connessione API da 127.0.0.1, accettala.

SICUREZZA

- Il servizio HTTP ascolta esclusivamente sul computer locale: 127.0.0.1.
- Il bridge contiene soltanto funzioni di lettura.
- Non sono presenti funzioni per creare, modificare o cancellare ordini.
- Live e Paper sono mostrati in pannelli separati.
- Il Paper non modifica patrimonio o storico.
- Il patrimonio consolidato somma Net Liquidation del conto Live, fondo emergenza e flexible cash.
- Le posizioni Live non vengono sommate una seconda volta: sono gia' comprese nel Net Liquidation.
- Fondo emergenza e flexible cash entrano nel patrimonio consolidato soltanto dopo il
  salvataggio del mese nello Storico mensile. La bozza del mese resta comunque in memoria.
- Se un mese viene eliminato, tutti i cumulati successivi, il patrimonio storico e la
  liquidita' contabilizzata vengono ricalcolati automaticamente sui mesi rimasti.

BUDGET, VOCI DETTAGLIATE E CAPITAL ALLOCATION

- Costi fissi e variabili nell'Input del mese sono i target macro complessivi.
- Le voci dettagliate suddividono questi target senza sommarsi nuovamente al budget:
  servono a spiegare da quali costi, investimenti o disponibilita' e' formato il totale.
- La somma disponibile e' calcolata come stipendio netto piu' eventuale bonus,
  meno costi fissi, costi variabili e quota fondo emergenza del mese.
- In Capital Allocation, Patrimonio a fine mese coincide con la somma disponibile.
  Investimenti totali e Flexible cash funds sono i due target macro da allocare.
- Le formule di Input del mese, Fondo emergenza, Capital Allocation e Voci dettagliate
  sono disponibili passando il mouse sulla `i` accanto al titolo della sezione.
- Le quattro categorie delle Voci dettagliate sono Costo Fisso, Costo Variabile,
  Investimento e Flexible Cash. Le quattro celle gialle mostrano target macro, totale
  gia' dettagliato e importo ancora mancante; segnalano anche un eventuale eccesso.
- Durante l'inserimento di una voce, il riquadro sotto l'importo mostra in tempo reale
  quanto risultera' dettagliato e il gap residuo dopo il salvataggio della voce.
- Input del mese, Capital Allocation e Voci dettagliate formano un'unica sezione.
  Il pulsante Salva mese in fondo registra insieme tutti questi dati.
- Il Fondo emergenza si trova nella sezione Gestione delle finanze, prima
  dell'Input del mese, ed e' sempre visibile.
- Nello Storico mensile ogni riga puo' essere aperta per visualizzare input, allocazioni
  e singole voci. Il pulsante Modifica mese ricarica tutto nella sezione Input del mese.
- Salvando le modifiche, il mese selezionato viene sostituito senza duplicazioni anche
  quando vengono cambiati il mese o l'anno. Eliminando un mese si ricalcolano i cumulati.
- Gli input del mese sono una simulazione finche' non viene premuto Salva mese, ma ogni
  modifica viene conservata automaticamente e ripristinata alla successiva apertura.

WEALTH MANAGEMENT E PORTAFOGLIO

- Sotto il titolo Wealth management, la riga Stato account IBKR mostra in modo
  compatto lo stato Live e Paper di Trader Workstation e il pulsante Aggiorna.
- I sei indicatori principali sono: valore posizioni IBKR, investimenti illiquidi,
  P/L degli investimenti illiquidi, liquidita' IBKR, P/L non realizzato e P/L realizzato.
- Le tabelle Posizioni IBKR Live e Investimenti illiquidi sono raccolte nella stessa
  sezione, immediatamente dopo gli indicatori.
- I grafici mostrano esposizione per asset class, Continente e Paese; il cash IBKR
  compare nell'asset allocation separato per valuta ma non nelle analisi geografiche.
- La crescita YoY confronta il patrimonio con lo stesso mese dell'anno precedente,
  quando il dato storico e' disponibile.
- Il profilo di rischio usa una media ponderata per l'esposizione, su scala 0-100.
  Ogni asset class ha un peso: fondo emergenza 0; liquidita' 5; cash IBKR positivo
  e flexible cash 8; titoli di Stato 12; obbligazioni corporate/altre 30; Real
  Estate/REIT 45; fondi 50; ETF 55; indici e categorie non classificate 60;
  commodities 65; azioni, equity e passion assets 70; Forex 75; crypto 95;
  opzioni e derivati 100. Il risultato e' Prudente fino a 25, Moderato oltre 25
  e fino a 60, Dinamico oltre 60. Senza esposizioni mostra Non calcolabile; la `i`
  accanto all'indicatore riporta formula, pesi e soglie.
- Il Value at Risk parametrico e' una stima mensile al 99% basata sulla volatilita'
  dei rendimenti patrimoniali salvati e richiede almeno tre rilevazioni.

MEMORIA AUTOMATICA

- Non serve importare o esportare il mese. La dashboard salva automaticamente ogni
  modifica circa 350 millisecondi dopo l'inserimento.
- Vengono conservati il mese aperto, tutti gli input, le voci gia' aggiunte, la voce
  ancora in compilazione, il mese storico in modifica e lo stato dei pannelli.
- Alla chiusura dell'app viene inviato un ultimo salvataggio prima di fermare il servizio.
- I dati sono nel file `~/Library/Application Support/Dashboard Finanziaria/dashboard-state.json`.
- Al primo avvio la dashboard trasferisce automaticamente in questo file i dati gia'
  presenti nella precedente memoria del browser.
- `Salva mese` continua ad avere un significato preciso: conferma il periodo nello
  Storico mensile. Non e' necessario per conservare una bozza incompleta.

INVESTIMENTI ILLIQUIDI

- Una voce Investimento puo' essere una quota mensile destinata a IBKR oppure un
  investimento illiquido. Entrambe riconciliano il target Investimenti del mese.
- Usa Investimento illiquido / non presente su IBKR per real estate, private equity, CLO esterni,
  quadri, carte, orologi e altri asset non rilevati dal conto Interactive Brokers.
- Solo per un investimento illiquido si compilano categoria, dettaglio strumento, ticker,
  data e prezzo di acquisto, quantita', valuta, Paese e Continente.
- Capitale allocato indica quanto e' stato investito nel mese; Valore attuale stimato
  indica quanto vale oggi la posizione illiquida e puo' essere diverso dal costo.
- Dopo Salva mese, il valore dell'investimento illiquido entra nel portafoglio, nel patrimonio
  complessivo e nei grafici per asset class, Continente e Paese.
- Collegato a IBKR Live registra soltanto descrizione e importo destinato nel mese.
  Non crea una posizione, non entra nei grafici e non aumenta il patrimonio.
- Saldo, posizioni, valore di mercato, asset class e geografia IBKR provengono
  esclusivamente dal conto Live, evitando qualsiasi doppio conteggio.
- Caricando un mese storico, modificando il valore dell'investimento illiquido e salvandolo nuovamente,
  tutti i mesi e i cumulati successivi vengono ricalibrati.

CLASSIFICAZIONE DEL PORTAFOGLIO LIVE

- Quantita', prezzi, valori di mercato e P/L provengono direttamente da IBKR Live.
- Per ogni conId il bridge richiede i Contract Details a TWS una sola volta e legge
  security type, descrizione, stock type, sottostante e identificativi disponibili.
- L'asset class deriva prima di tutto dal security type IBKR. I dettagli distinguono,
  quando disponibili, azioni, ETF, REIT, obbligazioni e Titoli di Stato.
- Il Paese emittente viene letto dai metadati della descrizione del contratto. Se TWS
  non restituisce un campo Paese esplicito, il bridge usa il prefisso Paese dell'ISIN.
- Per opzioni e derivati la geografia viene ereditata dal contratto sottostante.
- Borsa di quotazione e valuta non vengono usate come Paese emittente, per evitare
  classificazioni geografiche fuorvianti.
- Le quote mensili collegate a IBKR non vengono usate come fallback: se un metadato
  non e' disponibile, la dashboard mostra Non classificato anziche' usare dati inseriti dall'utente.
- Esposizione per Continente usa otto macro-aree: Globale, Europa, Nord America
  (solo USA e Canada), Resto dell'America, Asia, Africa, Oceania e Antartide.
- Esposizione per Paese mostra il singolo Paese emittente o di domicilio del titolo.
- Per ETF e fondi il domicilio dell'emittente non equivale all'esposizione economica
  dei titoli sottostanti: per questa seconda analisi servirebbero i dati look-through.
- L'esposizione per asset class include anche il cash IBKR come Liquidita'.
- I grafici per Continente e per Paese considerano le posizioni aperte, non il cash.

GLOSSARIO DEI DATI MOSTRATI

NET LIQUIDATION VALUE (VALORE NETTO DI LIQUIDAZIONE)
E' la stima del valore complessivo del conto nella sua valuta base. Comprende la
liquidita' e il valore di mercato corrente delle posizioni, con gli effetti dei
profitti e delle perdite maturati. In termini pratici, indica quanto varrebbe il
conto se tutte le posizioni fossero valutate ai prezzi di mercato disponibili.
Non rappresenta necessariamente la somma immediatamente prelevabile: i prezzi
possono cambiare e possono esserci margini, regolamenti, commissioni o conversioni.

LIQUIDITA' TOTALE
E' il valore della componente cash registrata sul conto, riportata nella valuta
base. Puo' includere saldi in valute differenti convertiti da IBKR. Non coincide
sempre con il denaro gia' regolato, prelevabile o utilizzabile senza limitazioni.

FONDI DISPONIBILI
Indicano il capitale che IBKR considera ancora disponibile per aprire nuove
posizioni rispettando i requisiti di margine iniziale. Possono differire dalla
liquidita' totale e dal saldo prelevabile. Il valore dipende dal tipo di conto,
dalle posizioni aperte, dalla concentrazione del portafoglio e dalle regole di
margine applicate in quel momento.

BUYING POWER (CAPACITA' DI ACQUISTO)
E' una stima del controvalore massimo di strumenti finanziari acquistabili secondo
le regole di margine correnti. Nei conti a margine puo' essere superiore alla
liquidita' disponibile perche' incorpora la leva e quindi la possibilita' di usare
capitale finanziato dal broker. Non e' denaro posseduto, prelevabile o una cifra
che sia necessariamente prudente investire per intero.

P/L NON REALIZZATO
E' il profitto o la perdita teorica sulle posizioni ancora aperte, calcolato
confrontando il valore di mercato corrente con il costo medio. Diventa effettivo
solo quando la posizione viene chiusa e puo' cambiare continuamente con i prezzi.

P/L REALIZZATO
E' il profitto o la perdita generata dalle posizioni gia' chiuse. Il periodo di
riferimento e il momento di azzeramento possono dipendere dalle impostazioni e dai
criteri di IBKR/TWS. Per rendicontazione fiscale e dati definitivi bisogna usare gli
Activity Statement ufficiali, che riportano anche commissioni e criteri contabili.

POSIZIONI E RELATIVE COLONNE
- Posizione: ogni strumento finanziario attualmente presente nel conto.
- Quantita': numero di azioni, quote o contratti; un valore negativo puo' indicare
  una posizione short.
- Costo medio: costo medio attribuito da IBKR alla posizione ancora aperta. Per
  derivati, trasferimenti o operazioni societarie puo' seguire regole specifiche.
- Prezzo di mercato: ultimo prezzo disponibile per una singola unita' o contratto.
  Puo' essere in tempo reale, ritardato o non disponibile in base agli abbonamenti.
- Valore di mercato: valore corrente complessivo della posizione, determinato da
  quantita', prezzo e, quando previsto, moltiplicatore del contratto.

NOTA IMPORTANTE

I dati della dashboard servono al monitoraggio operativo. Possono essere ritardati,
stimati o aggiornati con frequenze differenti. Per saldi ufficiali, fiscalita',
commissioni e movimenti definitivi fanno fede TWS e gli Activity Statement IBKR.

Per interrompere il collegamento, chiudi la finestra del bridge oppure premi Ctrl+C.

## Stato e freschezza del collegamento

Lo stato dei dati e' distinto dal collegamento a TWS: Connessione,
Sincronizzazione, Dati aggiornati, Dati non aggiornati oppure Offline.
La connessione da sola non rende i dati aggiornati: sono necessari il completamento
iniziale del riepilogo e del download dell'account. Dopo una riconnessione i dati
finanziari vengono acquisiti nuovamente prima di essere considerati aggiornati.
La soglia di 300 secondi misura l'ultima ricezione del flusso account, non la
freschezza delle quotazioni di mercato. Metadati e handshake non azzerano questa eta'.

Ogni ambiente ha una sola richiesta HTTP alla volta, condivisa dal pulsante Aggiorna
e dal polling. Ogni richiesta ha un timeout di 8 secondi; il tentativo successivo
parte 5 secondi dopo il completamento. Un errore conserva la risposta precedente
come non aggiornata. Aggiorna insieme bridge e dashboard: un vecchio bridge senza
stato dati esplicito non viene considerato sincronizzato.

Verifiche locali senza connessione IBKR:

```sh
python3 -m unittest discover -s tests -p 'test_bridge*.py'
node --test tests/test-polling.cjs
```
