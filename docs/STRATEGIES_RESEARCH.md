# Sei strategie e protocollo quantitativo

Versione di ricerca locale, 10 settembre 2026. Implementazione: `research/strategies.py`, `allocator.py`, `backtest.py`; esecuzione di ordini simulati nel solo `research/engine.py`. Le regole sono ipotesi, non strategie validate. Catalogo API `/api/research/strategies` riproduce parametri dal codice. Nessuna performance storica è stata calcolata: tutte le metriche di efficacia sono **da calcolare**.

Strategia con uno specifico profilo di rischio e potenziale rendimento, senza garanzia di risultato. Il capitale investito può subire perdite, anche rilevanti.

## Contratto comune e parametri

Ogni strategia riceve `MarketFrame` di barre chiuse ordinate UTC, quote bid/ask e sizes, latenza e fonte, frequenza di annualizzazione, calendario/sessione, disponibilità, completezza, evento e regime. `StrategyContext` contiene equity, posizione long e high-water mark, perdite giornaliere/settimanali, drawdown, ingressi/cancellazioni, cooldown, stato connessione/riconciliazione e consenso BTC distinto. Restituisce `Signal` ENTER/EXIT/HOLD/BLOCKED con motivo, peso target, prezzo limite, stop proposto e `research_unvalidated`. Nessuna credenziale, chiamata API o decisione live.

L'adattatore dati deve garantire barre veramente chiuse, eventi noti al timestamp, universo point-in-time, sessioni e calendario. Timestamp non futuro, history non troppo vecchia, dati non finiti/crossed o conteggi invalidi producono BLOCKED. Nessuna conversione forex implicita. Il simulatore operativo restringe ulteriormente gli strumenti a una allowlist di fixture e valuta USD: i ticker del codice non sono raccomandazioni né universo B2C approvato.

Sizing comune: `min(max_weight, max_weight * target_vol / realized_vol, risk_per_trade / (stop_distance / price))`; stop distance = `max(stop_atr * ATR14, 0.2% del prezzo)`. Risk engine a valle riduce/rifiuta ulteriormente; il budget per strategia non aumenta per inseguire un rendimento. Le soglie iniziali sono parametri sperimentali conservativi da preregistrare e testare, non limiti validati. Non usare valori di paper fill per calibrare automaticamente il live.

Uscite comuni: proposta su perdita/drawdown oltre limite, invalidazione trend, price/trailing stop, time stop e risk-off. Una posizione aperta non genera ulteriori ingressi: niente averaging down. Dati incerti bloccano anche le proposte di esecuzione; lo stop software non protegge durante outage. Non chiudere posizioni reali senza autorizzazione separata. Per intraday uscita proposta a ≤300 secondi dalla fine sessione, nessun ingresso in quella finestra.

## Confronto e budget di ricerca

| ID / nome | Orizzonte | Rischio | Peso max | Vol target | Rischio/trade | Loss day | DD max | Spread max | Staleness | Time stop |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| scalping / Micro-momentum controllato | tick, secondi | alto operativo | 3% | 6% | 0,05% | 0,2% | 2% | 3 bp | 1 s | 120 s |
| mean_reversion / Ritorno alla media intraday | 1 min | medio-alto | 10% | 8% | 0,1% | 0,5% | 5% | 8 bp | 5 s | 2 ore |
| breakout / Breakout di sessione | 5 min | medio-alto | 10% | 10% | 0,15% | 0,5% | 6% | 8 bp | 5 s | 6,5 ore e fine sessione |
| swing / Trend diversificato swing | 1 giorno | medio | 20% | 10% | 0,2% | 1% | 10% | 15 bp | 30 s | 30 giorni |
| momentum / Momentum e riserva di liquidità | daily, rebalance sett./mensile | moderato | 25% | 8% | 0,2% | 1% | 10% | 15 bp | 30 s | 90 giorni |
| bitcoin / Bitcoin trend e regime | 4h + filtro daily | medio-alto/alto | 5% | 8% | 0,1% | 0,5% | 8% | 20 bp | 5 s | 28 giorni |

Pesi sul capitale di riferimento; percentuali annualizzate della volatilità sono obiettivi di sizing, non volatilità garantita. Limiti account e allocator prevalgono; differenze fra soglie segnale e risk engine vengono risolte scegliendo il vincolo più restrittivo. Il codice attuale del risk engine usa anche un cap USD assoluto, non assume che il 5% BTC sia sempre spendibile.

## 1. Micro-momentum controllato

Razionale: domanda/offerta sbilanciata e breve persistenza del flusso possono produrre movimento futuro; ipotesi da falsificare al netto dei costi e della coda. Universo ristretto ETF/large/mega-cap liquidi; esclusi crypto, derivati, strumenti sottili. Feed obbligatorio tick + L2 affidabile (`tick_l2` e completezza), mai proxy OHLC. Orari: sessione ufficiale aperta e dati/eventi validi. Sospensione se latenza >100ms, spread>3bp, cancellazioni≥20, volume/volatilità invalidi, news o feed incompleto.

Pseudocodice: verifiche comuni → `imbalance=(bid_size-ask_size)/(bid_size+ask_size)` → momentum ultimi 5 intervalli → ENTER se imbalance≥0,30 e momentum in bp>2×costo roundtrip stimato; EXIT se imbalance≤0 o momentum≤0. Stop 1,5ATR, trailing e time stop120s, max10 ingressi/sessione; nessun take-profit ottimizzato. Il book corrente non simula posizione nella coda: per la promozione servono profondità/eventi sequenziati e modello fill specifico. Rifiutare se costi, pacing/OER, latenza o OOS eliminano il vantaggio. Nessun forward IBKR abilitato oggi.

## 2. Ritorno alla media intraday

Razionale: in regime laterale gli scostamenti temporanei da una media ponderata possono rientrare; trend persistenti invalidano l'ipotesi. ETF/large/mega-cap; long-only. Usa ultime30 barre precedenti: VWAP locale ponderato per volume di close (approssimazione dichiarata, non VWAP tick di sessione), sd e z-score della chiusura corrente. ENTER se z<−2, deviazione MA5/MA30<0,3%, gap ultima open/close precedente<1%, volume attuale≥0,5×medio. EXIT se z≥−0,25 o stop comune. Stop2ATR, max3 ingressi, time stop2h/fine sessione. Trend forte, eventi societari/macro e gap anomali bloccano ingressi; filtro eventi deve essere alimentato da sorgente licenziata, non da supposizioni dell'AI.

## 3. Breakout di sessione

Razionale: superamento di range con espansione e volume può identificare persistenza intraday. Implementata variante rolling range di20 barre precedenti, **non** opening range ufficiale: opening range resta variante futura con calendario esplicito. ENTER se close>massimo high precedente+0,1ATR, volume>1,5×medio e range barra>ATR. EXIT sotto MA5 o stop2ATR/trailing/fine sessione. Max2 ingressi/sessione; niente averaging down, stop strutturale da validare rispetto al range. Falsi breakout e sessioni con news sono scenari di stress obbligatori.

## 4. Trend diversificato swing

Razionale: persistenza intermedia con riduzione del rischio quando il trend si invalida. Variante daily implementata; 4h resta una distinta parametrizzazione da testare. ENTER se prezzo>MA20>MA60 e oltre massimo delle20 barre precedenti; EXIT prezzo<MA20 o MA20≤MA60. Stop/trailing3ATR e time stop30giorni. Uno strumento per segnale; diversificazione e rischio account affidati all'allocator. Ridurre a cash con risk-off, non leva. Gestire overnight/gap, corporate actions e delisting nel dataset.

## 5. Momentum e riserva di liquidità

Razionale: momentum relativo con trend assoluto può selezionare esposizioni persistenti e aumentare cash quando mancano opportunità. Solo ETF di categorie azionario USA/Europa/globale, bond, oro/monetario: ticker, UCITS, negoziabilità retail e costi da scegliere con dati e permessi; nessuna sostituzione automatica. Ranking point-in-time fornito esplicitamente, non calcolato sul solo strumento. ENTER a rebalance quando rank≤3, prezzo>MA126 e prezzo>close126periodi prima. EXIT a rebalance se rank>3 o prezzo<MA126, oltre stop/risk-off comuni. Vol targeting, max25%/strategia,3ATR,time stop90giorni. Frequenza settimanale/mensile dal calendario esterno. Niente ribilanciamenti continui per aumentare turnover.

## 6. Bitcoin trend e regime

Bitcoin presenta elevata volatilità e può subire perdite rapide e rilevanti. Questa strategia ha uno specifico profilo di rischio e un potenziale rendimento, senza garanzia di risultato.

Soltanto BTC spot; ETH/altcoin, ETF/ETN, futures/CFD e sostituzioni implicite sono rifiutati. Long-only senza leva; consenso BTC separato nel simulatore. Tre varianti implementate:

1. `trend`: filtro daily positivo + prezzo>MA60, MA20>MA60 e momentum20barre positivo.
2. `breakout`: filtro daily positivo + prezzo>MA60 e massimo20barre precedenti+0,1ATR.
3. `multi_timeframe`: filtro daily positivo + prezzo>MA60, momentum6/42/60barre 4h positivi. È multi-orizzonte su 4h+daily; feed1h aggiuntivo rimane da validare separatamente.

Uscita invalidazione filtro lungo/MA20, stop3ATR/trailing,time stop28giorni, loss week≥1,5%, day≥0,5%, DD≥8%; max1 ingresso e cooldown dopo3 perdite consecutive fino a revisione esplicita dei dati di contesto. Peso≤5%, ridotto dalla volatilità; vol>100% annualizzata sospende ingressi. Non aumentare quota BTC per compensare altre strategie. Scegliere variante sulla robustezza OOS/costi/stress, **nessuna variante vincitrice selezionata qui**.

24/7 non significa broker sempre disponibile: usare stato venue per notte/weekend/festività/manutenzione TWS e fornitore custodia, staleness e riconciliazione dopo restart. Il backtest simula riduzione liquidità weekend50%, raddoppio costo variabile weekend, outage, reject e partial fills. Soglie di quantità e prezzo del simulatore non sono minimi IBKR confermati. Disponibilità IBIE/zerohash, API/route, ordini/precisioni/minimi/commissioni e paper richiedono verifiche descritte in IBKR_COMPLIANCE.md. BTC resta sintetico.

## Eventi broker e ciclo operativo: specifica comune alle sei strategie

Per l'adattatore futuro: solo ordini LMT con price collar e TIF permesso per contratto. Le cinque strategie su titoli potranno usare DAY dove supportato; BTC richiede conferma LMT/TIF della route, senza copiare le regole equity. `nextValidId` inizializza identificativi, `openOrder`/`orderStatus` rappresentano lo stato, `execDetails` deduplica eseguiti, report commissioni arricchisce il ledger, `error` classifica reject/pacing/connessione. Eventi account/position e snapshot end concorrono alla riconciliazione. Aggiornamento SDK può cambiare callback commissioni: test contrattuali prima di adozione.

Partial fill: contabilizzare quantità cumulativa/costo, riservare residuo, non duplicare fill. Reject: audit, nessun retry cieco, nuova decisione rischio se correzione. Disconnessione/riavvio: blocco nuovi intenti, stato UNKNOWN per invio incerto, riconciliare broker prima di riattivare. Pause/cancel/close distinti. Log: strategy/version, signal ID, data lineage, motivo e limiti, decisione rischio, intent e execution IDs redatti; notifiche per blocco anomalo/fill/reject/outage, mai push contenenti token o dati finanziari completi. Le API effettive non sono implementate nel simulatore e non sono state contattate.

## Portfolio allocator

Input: volatilità annualizzata, drawdown, capacità/liquidità per strategia, valuta/settore, eleggibilità validata e regime; matrice completa simmetrica PSD; capitale, cash disponibile ed esposizioni preesistenti con breakdown riconciliato. Missing/nonfinite => blocked. Candidati non validati restano cash; flag `validated` nei fixture non è processo di promozione di produzione.

| Profilo | Esposizione max | Vol target | DD gate | Strategie max | Universo |
|---|---:|---:|---:|---:|---|
| Conservativa |35%|5%|6%|2|momentum,swing|
| Bilanciata |60%|8%|10%|4|precedenti+mean reversion,breakout|
| Dinamica |80%|12%|12%|6|tutte, BTC con permesso separato|

Pesi inversi alla volatilità, cap strategia/capacità/currency/sector, riserva cash, scaling al rischio portafoglio. Correlazioni negative non creano bonus di rischio; holdings esistenti imputati conservativamente a vol100% senza covariance propria (può annullare nuova allocazione). È una proposta di capitale, non ordine o ottimizzazione completa. Account multi-valuta, beta/covariance look-through e transazioni FX richiedono dati; modello locale esecutivo ammette solo USD. Nessuna leva e nessuna modifica dei segnali in base al profilo commerciale.

## Backtest: codice e limiti

`backtest.run` è un calcolatore di scenari su un singolo strumento e quote, non una porta verso OMS/broker. Callback vede soltanto prefisso dati; proposte timestamp esatto e expiry, fill solo osservazione successiva e dopo latenza. Cross del limit necessario, quantità condivisa/partecipazione, nonfill, partial commission minimo, spread bid/ask, slippage/impact avversi, outage/reject, FX point-in-time e data costs. Mark finale al bid senza chiusura inventata. Le proposte di backtest sono ipotesi contabili e non autorizzazioni di trading; per esercitare il percorso operativo usare `ResearchEngine.submit/process` con tutti i limiti. Non usare il calcolatore standalone come paper execution service.

Default commission10bp + minimo1 per partial fill, slippage5bp e impact5bp, latenza1s, partecipazione1%, nonfill25% sono **scenari conservativi**, non tariffario IBKR o calibrazione statistica. Le commissioni del simulatore OMS sono separate e dichiarate nei Limits. Per BTC usare costi venue più fee FX/eventuale IVA, non default equity. La variabile annual_financing_rate è riservata: nessuna leva/finanziamento ammesso, costo finanziamento zero; cash interest e daily data cost sono parametrizzabili. Nessuna imposta inventata. Dataset devono attestare corporate action normalizzate, delisting e universo point-in-time; il codice rifiuta flag corporate actions non verificato, ma non può certificare la veridicità dell'input.

Metriche implementate: CAGR netto sul tempo trascorso, rendimento aritmetico annualizzato, volatilità, Sharpe zero rf, Sortino MAR0, DD, Calmar, recovery, profit factor/expectancy/win rate/rapporto win-loss da trade netti forniti; turnover e benchmark correlation se dati allineati. Frequenza equity uniforme verificata, no inf per statistiche indefinite. Exposure/correlazioni strategia/costi dettagliati/parameter stability richiedono pipeline multiasset e feed; campi non disponibili non diventano zero rendimento.

## Dataset e validazione da eseguire con licenze

- Ricerca: serie point-in-time daily/4h/minuti con aggiustamenti espliciti, cessazioni e calendario; universo inclusivo delisting, dati non scelti dopo i risultati.
- Scalping: tick e profondità sequenziata, bid/ask e size, eventi trade, clock e latenza osservata. OHLC insufficienti => no-go. Valutare dati exchange diretti o provider specializzato (es. Databento come candidato, non ancora selezionato/contrattualizzato), confermando copertura/licenze e mantenendo esecuzione IBKR distinta.
- BTC: spot stesso venue o differenze documentate; weekend, bear market, fasi laterali, liquidità estrema, gap/outage; evitare confronto spot vs ETP come equivalenti.
- Store separati research/backtest/live/execution, dataset manifest con hash/versione/origine/licenza/timezone/calendar e timestamp as-of. Nessun dataset reale incluso qui.

Protocollo preregistrato: in-sample60%, validation20%, OOS20% cronologici come ipotesi iniziale, embargo coerente col lookback/holding, stress period definiti prima dell'analisi, benchmark passivo net cost comparabile. Walk-forward rolling (`walk_forward_windows`) mantiene OOS disgiunti; parametri selezionati su train/validation, mai sui test. Bootstrap moving block seeded (`bootstrap_drawdowns`) quantifica distribuzione drawdown sintetica, non certezza probabilistica. Griglia sensibilità ±10/20%, controllo numero tentativi, costi2x, slippage2x, latenza5x, feed missing/reject/outage/restart; report tutti i periodi e varianti incluse quelle fallite. Latency e fill observation non hanno proxy di coda affidabile: scalping non promosso senza evidenza aggiuntiva.

Promozione ricerca→paper IBKR: report netto positivo OOS, parametri stabili, nessun dominio di pochi trade, DD compatibile, stress robusti e IBKR/dati/contratti verificati. Forward minimo proposto 8–12 settimane intraday e ≥6 mesi swing/momentum, da estendere per numero trade e copertura regimi; BTC include weekend e incidenti. Sono criteri iniziali da motivare, non scorciatoie temporali. Paper→live richiede tutti i gate legali/operativi, confronto fill/latency/slippage/reject e autorizzazione esplicita separata. Il20% non è criterio sufficiente e non compare nella UX come previsione.

Il target20% netto è un obiettivo di ricerca del portafoglio: nessuna evidenza attuale dimostra che sia raggiungibile entro i limiti. Non propongo un rendimento alternativo numerico senza dati. Se richiede leva/DD oltre budget, rifiutare la configurazione e ridurre l'obiettivo.
