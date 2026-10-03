# TWS paper e validazione delle strategie — 10 settembre 2026

## Esito operativo

TWS era aperta in “Simulated Trading” ma senza socket API. Dopo l'attivazione da parte
dell'utente, la connessione loopback7497 ha completato l'handshake (server API157)
e restituito un singolo identificativo DU compatibile con il conto simulato osservato
nella finestra TWS. Nessuna password letta; nessun ordine o cancellazione broker inviati.
Non sono state disabilitate le protezioni Read-Only API.

La versione1.9.1 include un raccoglitore dati paper, uno screening delle regole e un
valutatore statistico. **Non include ancora un servizio capace di inviare ordini IBKR.**
Il requisito di strategie operative sul broker non è completato: gli esiti sotto non
superano i prerequisiti richiesti dall'utente per entrare in paper.

## Dati realmente ricevuti

| Strategia | Strumenti | Risposta API |
|---|---|---|
|Mean reversion|AAPL,1min,1mese|8190barre|
|Breakout|AAPL,5min,1mese|1638barre|
|Swing|AAPL,giornaliero,6anni|richiesta estesa dalla versione1.9.5; risultato dipendente dalla disponibilità IBKR|
|Momentum|SPY,QQQ,IWM,TLT,GLD,giornaliero,6anni|richiesta estesa dalla versione1.9.5; risultato dipendente dalla disponibilità IBKR|
|Scalping|tick/book consolidato|non acquisito; OHLC non usato come sostituto|
|Bitcoin spot|feed/permessi/venue specifici|non acquisito; nessun ETF o derivato sostitutivo|

Totale finale:12834barre OHLC, risposte complete senza errori per le otto finestre finali.
La prima raccolta di4176barre è stata ampliata. Una richiesta breakout3mesi è scaduta
ed è stata ripetuta con1mese; il campione incompleto non è stato usato per il calcolo.
I prezzi sono dati di mercato, non risultati delle strategie. Copie e metadati restano
nel Mac, esclusi da Git e non redistribuiti. La UI TWS segnala feed non consolidato:
non viene dichiarata idoneità per strategie microstrutturali.

Le serie intraday restano a1mese per richiesta: tentare anni di barre a1minuto tramite
un'unica richiesta TWS produce volumi elevati, soft throttling e possibili disconnessioni.
IBKR raccomanda richieste di poche migliaia di barre e un provider specializzato quando
il fabbisogno non è soddisfatto. La raccolta di dati intraday pluriennali richiede quindi
una pipeline paginata/licenziata distinta; non viene simulata aumentando solo la durata.

## Screening realmente eseguito

`research/bar_replay.py` richiama le regole di `research/strategies.py` senza addestrarle
o ottimizzarle. La raccolta precedente usava il70% come storia di riferimento e il30%
come holdout. Dalla versione1.9.4 ogni nuova raccolta produce tre segmenti cronologici
non sovrapposti:60% in-sample diagnostico,20% validation e20% out-of-sample finale.
Le regole restano identiche nei tre segmenti; non è ancora una validazione walk-forward
completa. Il report conserva conteggi per ogni tipo di segnale e il registro cronologico
di ogni decisione con data, strumento, azione, motivo e prezzo osservato.

Capitale modellato100000USD, ordine massimo2000USD, esposizione massima10000USD o
cap strategia inferiore; no leva/short/averaging. Decisione su barra chiusa, possibile
fill soltanto all'apertura della barra successiva se il prezzo limite lo consente.
Spread3bp per lato, slippage/impact10bp per lato, commissione max(1USD,10bp notional)
per fill. Partecipazione massima0,1% del volume barra; ordine non eseguibile cancellato
nel modello. Il volume completo della barra è un limite ex post, non liquidità osservata
all'apertura. Nessun partial fill inventato da OHLC. Costi raddoppiati ricalcolando l'intero
percorso; ranking momentum usa soltanto la storia disponibile nello stesso momento.

**Risultati di un modello ipotetico su dati storici, non eseguiti paper o rendimenti reali.**

| Strategia | Holdout UTC | Operazioni simulate chiuse | Variazione capitale del modello | Con costi doppi | Esito |
|---|---|---:|---:|---:|---|
|Mean reversion|31/08/2026 18:04–09/09/2026 20:00|0|0,000%|0,000%|23proposte non eseguite nel modello; evidenze insufficienti|
|Breakout|31/08/2026 18:05–09/09/2026 20:00|0|0,000%|0,000%|15proposte non eseguite nel modello; evidenze insufficienti|
|Swing|03/02/2026–09/09/2026|2|+0,187%|−0,053%|pochi trade; stress costi fallito|
|Momentum|03/02/2026–09/09/2026|7|−0,336%|−0,418%|risultato netto negativo; pochi trade|
|Scalping|—|—|da calcolare|da calcolare|dataset adeguato assente|
|Bitcoin|—|—|da calcolare|da calcolare|dataset adeguato assente|

Nessuna delle quattro simulazioni mantiene posizioni aperte al termine in questo run.
Le percentuali si riferiscono all'intero capitale simulato, in larga parte non investito,
e non sono annualizzate. Zero senza operazioni **non** significa rischio zero.

Limiti sostanziali: bid/ask e latenza non osservati, eventi non filtrati, corporate action
non certificate, universo ETF odierno (survivorship da affrontare), fill su barre,
calendario RTH modellato16:00NewYork (mezze giornate da normalizzare), posizioni marcate
a close, nessun confronto con eseguiti broker. Non si modificano regole/soglie per
inseguire il20% o rendere positivo il risultato. Esito attuale: **NO-GO ordini paper/live**.

## Che cosa significa “affidabilità”

`research/validation.py` calcola, quando esistono operazioni chiuse attribuibili e
riconciliate, P/L netto, expectancy, profit factor, win rate con intervallo Wilson95%,
intervallo95% dell'expectancy con block bootstrap e drawdown dell'equity fornita.
Gli intervalli descrivono il campione, non la probabilità di guadagnare in futuro.
Le serie devono includere costi e marks netti dei flussi; il chiamante deve attestare
provenienza/completezza. Non esiste una percentuale di “affidabilità” inventata.

Soglie preliminari di ricerca, non standard legali o garanzie:

| Strategia | Minimo operazioni chiuse | Minimo sessioni effettivamente osservate |
|---|---:|---:|
|Scalping|200|60|
|Mean reversion|100|60|
|Breakout|100|60|
|Swing|40|126|
|Momentum|24|252|
|Bitcoin|60|180|

Ulteriori gate: costi completi, qualità dati, riconciliazione, OOS indipendente,
stress, profitto netto, limite inferiore expectancy positivo, DD entro limite,
profitto con costi doppi e non dipendente da una sola operazione.
Tutti superati significa soltanto `ready_for_independent_review`. `live_enabled`
e `automatic_promotion` restano sempre false. Le evidenze sintetiche e quelle da barre
non soddisfano il gate “broker paper osservato”. Nessuna operazione manuale TWS viene
attribuita automaticamente a un bot per gonfiarne il campione.

## Uso nell'app

Aprire **Laboratorio strategie → Verifica paper e raccogli dati** con TWS paper aperta,
socket7497 e API abilitate. Il pulsante raccoglie dati e ricalcola lo screening; non
avvia bot. Un'altra raccolta è consentita dopo60secondi. “Ferma raccolta” interrompe
le richieste successive; non cancella ordini e non liquida posizioni.
Ogni scheda espone screening, requisiti e dati mancanti. I report persistono in
`~/Library/Application Support/Dashboard Finanziaria/paper-research/`.

Il menu nativo **Collega TWS paper — sola lettura** è distinto dal monitoraggio generico.
Il raccoglitore ammette soltanto127.0.0.1 e porte7497/4002, rifiuta account live/multipli/
non riconosciuti e blocca placeOrder/cancelOrder/reqGlobalCancel. Il prefisso DU e la porta
non sono attestazione crittografica; l'assenza della capability di esecuzione è il limite
tecnico effettivo di questa versione.

## Prossimo passaggio concreto

1. Estendere e normalizzare dataset intraday, eventi, corporate action e quote storiche.
2. Eseguire più finestre walk-forward/OOS e stress sui candidati, mantenendo un test
   finale mai usato per scegliere parametri. Rifiutare candidati non robusti.
3. Solo per candidati che superano queste prove: realizzare/verificare adapter paper
   separato, lifecycle ordini/stop, riconciliazione e account allowlist attestata.
4. Raccogliere eseguiti paper reali del simulatore IBKR per il periodo necessario e
   confrontarli con il modello. Ora non esistono eseguiti attribuiti a questi bot.
5. Eventuale live richiede revisione indipendente, gate normativi/operativi e ulteriore
   autorizzazione esplicita; nessun cambio account automatico è disponibile.

## Verifiche

86testPython +5testHTTP su broker fittizio +6testNode:97superati. Lint, mypy dei9moduli
nuovi, compilazione Python3.9 e build locale macOS verificati. Test nuovi includono
porte live, account multipli, NaN, no ordini, persistenza raccolta, campioni vuoti,
duplicati, costi, drawdown, no promozione automatica, esclusione dati futuri, no fill
sulla barra del segnale, prezzo limite e rifiuto scalping OHLC.

## Fonti ufficiali consultate il10/09/2026

- [Configurazione TWS API](https://www.interactivebrokers.com/campus/trading-lessons/installing-configuring-tws-for-the-api/?retakeFinal=1): socket, porte configurabili e Read-Only.
- [Paper Trading Account](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/): ambiente simulato e limiti del simulatore (top of book, order types, esecuzioni).
- [Limitazioni paper TWS API](https://www.interactivebrokers.com/docs/tws-api/doc/notes-limitations/limitations/paper-trading): differenze delle esecuzioni rispetto al live.

Strategia con uno specifico profilo di rischio e potenziale rendimento, senza garanzia di risultato. Il capitale investito può subire perdite, anche rilevanti.
