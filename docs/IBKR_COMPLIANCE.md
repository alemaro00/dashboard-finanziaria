# Interactive Brokers e perimetro normativo preliminare

Data della ricerca: **10 settembre 2026**. Fonti primarie consultate online in questa data; le date degli atti o comunicati sono indicate dove disponibili. Le pagine API sono documenti evolutivi: la data di consultazione non equivale alla data di pubblicazione. Questo documento è una base tecnica per una verifica professionale, non un parere legale né un'autorizzazione del broker.

**Strategia con uno specifico profilo di rischio e potenziale rendimento, senza garanzia di risultato. Il capitale investito può subire perdite, anche rilevanti.**

## Decisione proposta

Conservare la dashboard personale e il connettore locale esistenti. Per l'MVP usare dati sintetici o dataset autorizzati con esecuzione simulata; successivamente un processo IBKR paper separato, previa validazione quantitativa e autorizzazione dell'utente. Per una produzione B2C proporre una Web API ufficialmente autorizzata per il modello commerciale scelto, con partner regolamentato quando richiesto. Non trasformare il bridge domestico in un server multiutente condiviso.

La richiesta comprende sei strategie: Bitcoin è la sesta, con permessi e budget separati. Il target del 20% è soltanto un obiettivo sperimentale e non una previsione. Nessuna strategia ha qui risultati di rendimento verificati.

## Legenda e assunzioni

- **Fatto verificato:** supportato da una fonte primaria collegata.
- **Interpretazione:** valutazione tecnica/prodotto o ipotesi di qualificazione giuridica, da validare.
- **Assunzione di progetto:** scelta prudenziale per procedere localmente, non un fatto sul conto dell'utente.
- **IBKR:** punto da confermare con API Integration, Compliance o l'affiliata competente.
- **Legale fintech:** punto da verificare con un professionista sul servizio concreto.
- **Privacy:** punto da verificare con consulente privacy/DPO, se designato.
- **Autorità:** eventuale confronto con CONSOB, Banca d'Italia, Garante o altra autorità competente, dopo la definizione del modello.

Assumiamo utenti iniziali maggiorenni residenti in Italia, nessuna custodia di fondi da parte della Dashboard, nessun prelievo o trasferimento disposto dall'app, nessuna raccolta delle password IBKR, nessun servizio di investimento al pubblico durante sviluppo e test. La residenza e l'affiliata effettive del conto non sono state verificate e non sono state usate credenziali reali.

## Stato di partenza e implicazioni

Il README descrive un'app personale: React in HTML, bridge Python HTTP locale/ibapi, JSON su disco, finestra macOS WKWebView, lettura di TWS Live e Paper. Non documenta IAM multiutente o autorizzazione commerciale. La presenza di due pannelli Live/Paper non dimostra isolamento tecnico: un processo capace di aprire entrambi i socket non è un ambiente paper incapace di raggiungere il live.

**Scelta progettuale:** il laboratorio di ricerca deve restare privo di credenziali e trasporti broker. L'eventuale adattatore paper va collocato in un processo e ambiente separato con allowlist di account, network e capacità. Le porte standard (7496/7497 TWS, 4001/4002 Gateway) sono convenzioni configurabili, non attestazioni dell'ambiente. Un prefisso dell'account o una checkbox nell'interfaccia non sostituiscono l'isolamento di rete e la verifica dell'identità del conto.

## Verifica IBKR

### Connessione, autenticazione e sessioni

| Area | Fatto verificato e fonte | Conseguenza progettuale / verifica residua |
|---|---|---|
| TWS API e IB Gateway | IBKR offre l'API socket per TWS/Gateway a retail, professionisti, advisor e sviluppatori terzi. [Panoramica API](https://www.interactivebrokers.com/docs) | Riutilizzare il parser di account/posizioni; testare una versione API supportata con la versione TWS concordata. Il pacchetto 9.81 presente all'audit non è una baseline sufficiente per nuove funzionalità senza matrice di compatibilità. |
| Login locale | TWS/Gateway gestiscono login, 2FA e riavvio/ri-autenticazione; la documentazione distingue ri-autenticazione giornaliera e settimanale. [Sessioni TWS](https://www.interactivebrokers.com/docs/tws-api/doc/tws-settings/daily-weekly-reauthentication) | Login eseguito dall'utente nell'app ufficiale; nessuna automazione della password. Scheduler e riconciliazione devono tollerare manutenzione, sospensione del Mac e perdita della sessione. |
| Web API consumer / vendor | La documentazione distingue accesso individuale e vendor terzo; per questi ultimi indica approvazione Compliance, onboarding e accordo Web API, con OAuth 1.0a nel percorso descritto. [Web API](https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/) | Non promettere OAuth2 self-service universale. Presentare a IBKR entità societaria, demo, paesi e operazioni richieste prima di scegliere il flusso definitivo. |
| OAuth2 | La pagina attuale lo descrive per organizzazioni autorizzate, financial advisor e introducing broker; accesso Trading/Account Management in funzione degli scope concessi. [OAuth2](https://www.interactivebrokers.com/docs/web-api/authentication/oauth-2/introduction) | Preferenza per autorizzazione ufficiale revocabile, ma soltanto nello schema approvato per questo vendor. Non riutilizzare API di account management per aggirare l'onboarding trading. |
| Concorrenza sessioni | Una username ha una sola brokerage session attiva fra piattaforme. Alcune funzioni portfolio appartengono alla sessione esterna read-only; gli endpoint `/iserver` richiedono la brokerage session. [Sessioni Web](https://www.interactivebrokers.com/docs/web-api/trading/trading-sessions-in-the-web-api) | Mostrare conflitti di sessione senza riconnessione aggressiva; non confondere connessione, autenticazione, autorizzazione e freschezza dei dati. |
| Più account | Username, permessi e account sono entità distinte; advisor/introducing broker hanno strutture e onboarding dedicati. [Account Management](https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-account-management/) | Nessun fan-out da una username retail a clienti indipendenti. ACL tenant/account e mappatura del mandato obbligatorie. |
| Paper | L'ambiente paper ha meccanismi simulati e comportamenti di esecuzione differenti dal live. [Paper Trading](https://www.interactivebrokers.com/docs/tws-api/doc/notes-limitations/limitations/paper-trading) | Serve per verificare il funzionamento, non per dimostrare eseguibilità o rendimento. Non promuovere automaticamente dopo un test positivo. |

### Dati, ordini e limiti

| Area | Fatto verificato | Controllo richiesto |
|---|---|---|
| Quote e abbonamenti | La maggior parte dei titoli richiede L1 per i dati API; Forex e crypto sono eccezioni indicate da IBKR. [Requisiti dati](https://www.interactivebrokers.com/docs/general/market-data-subscriptions/introduction) | Ogni quotazione deve riportare fonte, timestamp, valuta, qualità e delayed/live. Un errore di abbonamento blocca i segnali dipendenti da quel dato. |
| Tick-by-tick | Limite simultaneo pari al 5% delle market data lines; non più di una richiesta sullo stesso strumento ogni 15 secondi. [Tick-by-tick](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-live/tick-by-tick-data/introduction) | Universo scalping ristretto, stream condiviso per consumer autorizzati del medesimo utente; nessuna deduzione di microstruttura da OHLC. |
| Market depth | L2 è un flusso distinto dalle quote watchlist; disponibilità, tipo e frequenza dei tick dipendono da prodotto e contratto. [Limiti live](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-live/live-data-limitations) | Confermare abbonamenti L2 e profondità effettiva per mercato. Book vuoto, incompleto, desincronizzato o senza sequence recovery => scalping sospeso. |
| Pacing TWS | La documentazione corrente indica massimo richieste/secondo = **market data lines / 2**. 50 è il caso tipico di 100 linee, non un limite universale da assumere. [Pacing TWS](https://www.interactivebrokers.com/docs/tws-api/doc/pacing-limitations/introduction) | Rate limiter condiviso per sessione con margine operativo, priorità alle riconciliazioni/cancellazioni e budget per strategia. Nessun moltiplicatore basato sul numero di bot. |
| Storico small bars | Per barre fino a 30 secondi: evitare richiesta identica entro 15 s, almeno 6 richieste stesso contratto/exchange/tick in 2 s, oltre 60 richieste in 10 min; BID_ASK pesa doppio. [Pacing storico](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-data-limitations/pacing-violations-for-small-bars-30-secs-or-less) | Cache, coda e backoff; dataset ricerca separato. Verificare disponibilità storica, rettifiche e strumenti cessati prima di backtest. |
| Pacing Web | 10 richieste/s globali, limiti ulteriori per endpoint; ordini/trade/PnL 1 richiesta/5 s e storico massimo 5 richieste concorrenti nella pagina attuale. 429 può portare a blocchi IP. [Pacing Web](https://ibkrcampus.com/docs/web-api/v1/pacing-limitations) | Scheduler endpoint-aware, jitter e niente retry di invio ordine incerto. La fonte corrente indica penalty box 15 minuti; la pagina Campus precedente ne indica 10: trattarlo come configurazione del broker, non SLA. |
| WebSocket | Le quote watchlist sono snapshot temporali; i flussi vanno rinnovati, la pagina prescrive nuova richiesta dopo 10 minuti prima della scadenza a 15. [Market data WebSocket](https://www.interactivebrokers.com/docs/web-api/v1/ws/market-data/market-data-request) | Watchlist WebSocket non prova la disponibilità di un feed tick/order-book adatto allo scalping. |
| OER | IBKR monitora il rapporto di attività ordine rispetto alle esecuzioni, distinto dal pacing API. [Order Efficiency Ratio](https://ibkrcampus.com/docs/general/order-types/notes-limitations/order-efficiency-ratio) | Contare invii, modifiche, cancellazioni, eseguiti e rifiuti. Richiedere a IBKR formula/soglie applicate alla specifica struttura; non pubblicare una soglia universale non verificata. |
| Tipi ordine | I tipi supportati variano fra prodotto e API; il catalogo non implica che ogni combinazione sia disponibile. [Order Types](https://www.interactivebrokers.com/campus/?p=195739&post_type=ibkr-api-page) | MVP limit long-only; stop/exit simulati non vanno descritti come stop nativi garantiti. Ogni combinazione va verificata in TWS paper sul contratto scelto. |
| Eventi | La documentazione separa ordini aperti, stato ordine, esecuzioni e commissioni. [TWS API](https://www.interactivebrokers.com/docs/tws-api/doc/introduction) | Progetto OMS: `nextValidId`, `openOrder`, `orderStatus`, `execDetails`, report commissioni compatibile con API, `error`, snapshot posizioni. Persistenza idempotente per execution ID; gestire partial fill, reject e cancellazione concorrente. |

**Interpretazione operativa:** uno stato ordine non è un libro contabile completo. A riavvio, non reinviare intenti incerti: acquisire ordini aperti/completati, esecuzioni e posizioni, riconciliare account + conId + valuta + identificativi, poi riabilitare. Per dividendi, commissioni definitive, transazioni pregresse e rendicontazione usare anche statement/Flex autorizzati; non ricostruire il P/L annuale dalla sola variabile giornaliera TWS. Conservare periodo e metodologia del P/L nell'interfaccia.

### Dati professionali, uso commerciale e redistribuzione

**Fatti:** abbonamenti e status professionale/non professionale hanno regole specifiche; le fee dati sono per username. [Market Data Pricing](https://www.interactivebrokers.com/en/pricing/market-data-pricing.php). L'accordo sottoscrittore distingue i diritti d'uso e non concede automaticamente redistribuzione. [Accordo dati IBKR](https://www.interactivebrokers.com/Universal/servlet/Registration_v2.formSampleView?file=IBISAgreement.html).

**Decisione:** non riversare le quote di un abbonamento retail in un database condiviso tra clienti. Prima del B2C ottenere conferma scritta per display, non-display/algoritmi, caching, derivati analitici, conservazione storica, uso mobile, report esportabili e condivisione. Il fatto che l'API sia gratuita non rende gratuite le licenze dati, l'hosting, l'assistenza o gli accordi vendor. Costi commerciali ancora **da quotare**, senza stime presentate come tariffe IBKR.

## Cinque architetture a confronto

La tabella è una **valutazione progettuale**, non una certificazione IBKR.

| Opzione | Sicurezza e credenziali | Scalabilità / affidabilità | UX e costi | B2C, rischio normativo e operativo |
|---|---|---|---|---|
| 1. TWS sul dispositivo utente | Password/2FA restano in TWS; socket solo loopback, accessi minimi | Scala per dispositivo; dipende da PC acceso, rete, riavvii e utente | Setup manuale, TWS visibile; costo dati per utente, supporto elevato | Buona prova personale; distribuzione commerciale da approvare. Il PC compromesso può agire nella sessione. |
| 2. IB Gateway sul dispositivo/server dell'utente | Sessione sotto controllo utente; nessuna password al vendor; host dedicato e cifrato | Più leggero di una workstation completa; autenticazione e manutenzione persistono | Setup più tecnico; costi macchina/VPS, patching e assistenza | Adatto a utenti esperti. Server controllato dall'utente non equivale a infrastruttura multiutente autorizzata; no aggiramento 2FA. |
| 3. Connector locale Dashboard | Riusa il bridge; capability ristrette, binding loopback, separazione read-only/paper, IPC autenticato | Molte installazioni indipendenti; contratti API/versioni uniformi, aggiornamenti firmati necessari | UX migliore con diagnostica guidata; costo principale supporto client e firma/distribuzione | **MVP raccomandato dopo hardening**. Nessun esonero legale solo perché l'ordine parte dal dispositivo. |
| 4. Web API con autorizzazione ufficiale | Token revocabili e scope autorizzati; vault e KMS; niente password broker | Migliore percorso web/mobile; sessioni/pacing per utente restano vincoli | Onboarding centrale più semplice dopo approvazione; costi vendor/compliance da quotare | **Target B2C condizionato** a contratto, disponibilità schema OAuth e perimetro legale. Responsabilità token e tenant in capo alla piattaforma. |
| 5. Infrastruttura centralizzata | Isolamento tenant, egress policy, credenziali per mandato, HSM/KMS e doppio controllo | Scalabile solo con modello broker consentito; failure domain e recovery complessi | UX continua ma costi cloud, audit, on-call e sicurezza maggiori | **No-go oggi**. Richiede approvazione IBKR e struttura regolamentare coerente, non pooling di login retail. |

MVP locale: nessun broker nel processo dei test; simulatore per tutti i flussi; eventuale paper IBKR isolato e attivato esplicitamente dopo ricerca. Produzione: modello A/B iniziale con IAM e licenze; C/D soltanto dopo validazione legale e accordo IBKR. Directa resta fuori dal percorso critico.

## Bitcoin spot: verifica separata

**Fatto aggiornato:** il comunicato IBIE del **31 marzo 2026** annuncia crypto spot per investitori individuali EEA eleggibili, incluso BTC, e precisa che disponibilità varia per residenza e affiliata. Non è corretto assumere indisponibilità generale in Italia; non è neppure dimostrata l'abilitazione del conto concreto. [Comunicato IBIE](https://www.interactivebrokers.ie/en/general/about/mediaRelations/3-31-2026.php).

L'addendum IBIE richiede conto IBIE, permesso crypto, accettazione contratti e onboarding zerohash. Indica **zerohash europe B.V.** e distingue trasmissione da parte di IBIE da esecuzione/custodia. [Addendum crypto IBIE](https://ndcdyn.interactivebrokers.com/Universal/servlet/Registration_v2.formSampleView?formdb=4871).

La documentazione contratti API prevede `CRYPTO`, USD, route differenziate PAXOS/ZEROHASH/**ZEROHASHE per IBIE** e conId diversi per sede; Web API richiede identificazione con exchange attraverso `conidEx`. Non hardcodare gli esempi di conId come verità universale. [Contratti crypto](https://www.interactivebrokers.com/docs/general/contracts/cryptocurrency).

| Punto | Evidenza / stato | Gate prima di un adattatore Bitcoin collegato |
|---|---|---|
| Residenza Italia / conto | EEA potenzialmente eleggibile; conto effettivo non verificato | Conferma IBIE e permessi dell'account; no auto-enablement |
| Esecuzione/custodia | Per il prodotto IBIE la documentazione indica zerohash europe B.V. | Conservare soggetto giuridico e versione accordo; confermare flusso di saldo crypto distinto |
| TWS/Gateway/Web | Contratti API documentati; nessuna connessione effettuata | Matrice versioni, route e funzioni per account; approvazione commerciale Dashboard separata |
| Ordini | Catalogo crypto: LMT; MKT con vincoli di quantità/TIF; BUY market usa cashQty, market IOC; LMT DAY/GTC/IOC, anche Minutes in TWS | Per Dashboard ammettere solo LMT dopo contract test; non simulare supporto di stop nativi non documentati. [Catalogo crypto](https://www.interactivebrokers.com/campus/?p=195739&post_type=ibkr-api-page) |
| Precisione/minimo | Precisione quantità, minimo nozionale e price increment specifici non verificati per ZEROHASHE | Richiedere metadati contratto/market rules e conferma IBKR; usare Decimal; rifiutare se mancanti, mai inventare tick/lot |
| Commissioni | IBIE pubblica 0,18% fino a USD 100k mensili, poi 0,15%/0,12%; minimo USD 1,75 con cap del minimo all'1% del controvalore | Modello conservativo + eventuale IVA e costi FX; verificare condizioni del conto. [Commissioni IBIE](https://www.interactivebrokers.ie/en/pricing/commissions-crypto-assets.php) |
| Spread | Assenza di markup aggiunto non significa spread bid/ask nullo | Registrare spread osservato e slippage; dati mancanti => blocco |
| Orari | Il comunicato EEA annuncia 24/7; sessione API e manutenzioni restano dipendenze | Calendario effettivo della route, heartbeat notturno/weekend, staleness e on-call; nessuna promessa di disponibilità continua |
| Market data | Crypto indicata fra eccezioni senza sottoscrizione addizionale nel documento dati | Verificare qualità, volume, profondità e diritti commerciali; gratis non significa redistribuibile |
| Paper BTC | Non ottenuta evidenza sufficiente di supporto paper spot **ZEROHASHE per questo account/API** | **Resta simulata** finché IBKR conferma e i test autorizzati passano; nessuna sostituzione automatica con ETP/derivati |
| Partial fill/reject | Requisito del nostro OMS, da testare sul venue | Eseguiti cumulativi idempotenti, gestione residuo/scadenza, nessun retry cieco |
| Riavvio/outage | Requisito del nostro sistema | Bloccare entrate; riconciliare ordini/posizioni e saldi prima della ripartenza; stop software indisponibili durante outage |
| Distribuzione consumer | Lancio retail IBIE non autorizza questo vendor | Approvazione scritta per third party/automatismi, analisi MiCA e privacy |

Il catalogo generale menziona per alcuni programmi Crypto Basic/Crypto Plus orari diversi: non applicarli automaticamente a IBIE. [Lezione IBKR](https://www.interactivebrokers.com/campus/trading-lessons/trading-cryptocurrency-in-ibkr-desktop/?retakeFinal=1). Alternative ETP/ETF/ETN hanno struttura, costi, orari e rischi differenti; futures/CFD introducono ulteriori rischi e restano esclusi. Nessuna alternativa è attivata implicitamente.

## Analisi normativa preliminare

### Fatti verificati e interpretazioni da validare

| Quadro | Fatto verificato / fonte | Interpretazione per il prodotto e owner |
|---|---|---|
| MiFID II | Definizioni e servizi nell'art. 4/Allegato I; art. 24 su condotta/informazioni, art. 25 su adeguatezza/appropriatezza. Consultato consolidamento 6 giugno 2026. [MiFID II](https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX%3A02014L0065-20260606) | Consiglio personalizzato, discrezionalità e trasmissione ordini possono cambiare il perimetro anche se il broker custodisce i fondi. **Legale fintech**: qualificare ogni flusso e mandato. |
| Italia | CONSOB distingue soggetti abilitati e attività riservate verso il pubblico. [Operatori finanziari](https://www.consob.it/web/investor-education/operatori-finanziari) | Un disclaimer, una conferma manuale o il nome “software” non risolvono da soli la riserva di attività. **Legale/Autorità**: autorizzazione propria o partner, registri e paese di prestazione. |
| RTO/esecuzione/gestione | CONSOB descrive ricezione/trasmissione, esecuzione e gestione discrezionale come servizi distinti. [ACF servizi](https://www.acf.consob.it/approfondimento-servizi-di-investimento) | Mappare chi decide strumento, tempo, quantità, cancellazione e capitale. **Legale**: identificare responsabile effettivo anche nel connettore locale. |
| Robo/copy/social trading | ESMA, 30 marzo 2023, tratta qualificazione, costi/marketing, product governance, adeguatezza/appropriatezza e incentivi. [Briefing copy trading](https://www.esma.europa.eu/press-news/esma-news/esma-provides-guidance-supervision-copy-trading-services) | Non introdurre copy/social trading in questa versione. Se introdotti, analisi distinta; il follower che autorizza genericamente un bot non equivale necessariamente a conferma di ogni ordine. |
| Bitcoin/MiCA | MiCA art. 59/60 regola accesso ai servizi crypto. ESMA Q&A 2463, risposta 7 aprile 2025, richiede qualificazione caso per caso dell'autotrading crypto. [MiCA](https://eur-lex.europa.eu/eli/reg/2023/1114/2024-01-09/eng), [Q&A ESMA](https://www.esma.europa.eu/publications-data/questions-answers/2463) | BTC spot richiede analisi CASP distinta dagli strumenti MiFID. **Legale/IBKR**: servizi effettivi, paesi, mandato, outsourcing; non assumere copertura della Dashboard dalla licenza del broker. |
| GDPR | Informativa, minimizzazione, liceità e accountability; la DPIA va svolta prima di trattamenti con rischio elevato. [Garante GDPR](https://www.garanteprivacy.it/it/regolamentoue), [DPIA](https://www.garanteprivacy.it/it/valutazione-d-impatto-della-protezione-dei-dati-dpia-) | **Privacy**: definire titolare/responsabili, finalità e basi giuridiche, DPIA per profilazione finanziaria, trasferimenti extra SEE, art. 22 per decisioni automatizzate significative; non usare consenso come base universale. |
| Data breach | Notifica al Garante entro 72 ore dalla conoscenza se ricorrono i presupposti di rischio; comunicazione agli interessati per rischio elevato, salvo eccezioni. [Garante principi e breach](https://www.garanteprivacy.it/home/principi-fondamentali-del-trattamento) | Incident register, triage legale/privacy, timeline e prove; niente promessa di notifica indiscriminata o di recupero garantito. |
| AI Act | Reg. 2024/1689 adotta classificazione per uso; fra i casi finanziari dell'Allegato III vi sono creditworthiness e determinati impieghi assicurativi. [AI Act](https://eur-lex.europa.eu/eli/reg/2024/1689/oj?locale=en) | Non classificare automaticamente ogni bot come alto rischio, né dichiararlo esente. **Legale**: ruolo provider/deployer, intended use, alfabetizzazione, trasparenza e calendario applicabile con modifiche vigenti al lancio. |
| AI e investimento | ESMA 30 maggio 2024 mantiene responsabilità e doveri MiFID anche con strumenti AI. [Statement ESMA](https://www.esma.europa.eu/sites/default/files/2024-05/ESMA35-335435667-5924__Public_Statement_on_AI_and_investment_services.pdf) | AI soltanto analisi/spiegazione: niente token, modifica limiti, firma/esecuzione o promozione live. Supervisione umana non puramente formale. |
| DORA | Applicabile dal 17 gennaio 2025 alle entità nel relativo perimetro; include governance di servizi ICT e registri degli accordi. [Banca d'Italia DORA](https://www.bancaditalia.it/media/notizie/2025/Comunicazione-sulle-tempistiche-di-trasmissione-dei-registri-informazioni.pdf) | Non tutte le startup software sono entità finanziarie DORA. Obblighi contrattuali ICT possono derivare da partnership; **legale/SRE**: classificazione, incidenti, test resilienza, outsourcing e exit strategy. |
| NIS2 | Ambito per settori/dimensione/eccezioni, e coordinamento con atti settoriali come DORA. [NIS2](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32022L2555), [d.lgs. 138/2024](https://www.normattiva.it/eli/id/2024/10/01/24G00155/CONSOLIDATED/) | **Legale/ACN ove necessario**: verificare attività effettiva, dimensione, soggetto e comunicazioni; non dedurre applicabilità dalla parola fintech. |
| AML/KYC | La disciplina riguarda soggetti obbligati e verifica clientela. Il nuovo AMLR si applica in generale dal 10 luglio 2027. [Direttiva AML](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32015L0849), [AMLR art. 90](https://eur-lex.europa.eu/eli/reg/2024/1624) | **Legale/partner**: verificare d.lgs. 231/2007 e obblighi del servizio; il KYC IBKR non elimina automaticamente eventuali obblighi propri. Non raccogliere documenti d'identità “per sicurezza” prima di definirne base e necessità. |
| Consumer/abbonamenti | Diritti contrattuali a distanza; la direttiva 2023/2673 modifica il quadro dei servizi finanziari a distanza dal 19 giugno 2026. [Consumer rights](https://eur-lex.europa.eu/eli/dir/2011/83/oj/eng), [2023/2673](https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ%3AL_202302673) | **Legale**: contratto digitale vs finanziario, recepimento italiano, recesso/rinnovi/rimborsi. UX con cancellazione comprensibile, costi completi, nessun dark pattern. |
| Marketing/MAR | MAR art. 20 richiede presentazione obiettiva e disclosure interessi/conflitti per raccomandazioni diffuse. [MAR](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32014R0596) | Segnali pubblici non sono automaticamente fuori da ogni norma. Rendimenti netti documentati, metodologia e periodi completi; no target 20% in promozione, no cherry-picking né premium “più redditizio”. |

### Modelli A–D

Le valutazioni nella tabella sono **interpretazioni preliminari** del servizio ipotizzato; richiedono validazione professionale sui flussi definitivi e sul contratto. Non costituiscono una conclusione circa autorizzazioni necessarie o esenzioni.

| Modello | Funzioni e valore | Complessità/responsabilità | Rischio e possibili autorizzazioni | Informativa/consenso/accordi | Go / no-go |
|---|---|---|---|---|---|
| A. Dashboard senza broker | Budget, storico, patrimonio inserito manualmente; utile anche senza trading | Bassa rispetto agli altri; correttezza calcoli e protezione dati | Inferiore se mero strumento contabile, senza raccomandazioni personalizzate; GDPR/consumer restano | Termini software, finalità dati e retention; consenso separato per marketing; nessun accordo trading | Go per sviluppo locale; beta solo con hardening, privacy, test e contratto verificati |
| B. Broker read-only | Aggregazione saldi/posizioni, analytics descrittive, rendicontazione | Media; riconciliazione, freschezza, licenze e token | Non assumere gestione/consulenza; personalizzazione prescrittiva può cambiarla | Accesso revocabile in sola lettura, minimi scope e nessun trasferimento; accordo IBKR per vendor e licenze dati | MVP commerciale preferibile dopo approvazioni, IAM e pen test; no-go con login retail condivisi |
| C. Segnali con conferma manuale | Ricerca spiegabile, proposta ordine controllata | Alta; errori di segnale, costi, conflitti e comprensione utente | Possibile consulenza e/o RTO secondo personalizzazione e flusso; appropriatezza/adeguatezza secondo servizio | Conferma per singolo ordine con conto, prezzo, quantità, costi, rischio; mandato/accordo broker; conservazione evidenze | No-go al pubblico prima di qualificazione legale e approvazione commerciale, anche se c'è un pulsante conferma |
| D. Trading automatico | Esecuzione entro mandato, supervisione bot, rischio centrale | Molto alta; discrezionalità, outage, incidenti, custodia token, on-call | Possibile gestione di portafogli, RTO/esecuzione; per BTC anche perimetro MiCA; partner/licenza da definire | Mandato granulare/revocabile, scope trading distinto, valutazioni richieste, strategia/versione/limiti, audit esterno | No-go reale: necessario iter legale/IBKR, forward paper, controlli operativi, pen test, approvazione separata dell'utente |

Un abbonamento più caro non sostituisce esperienza o valutazioni richieste. Un profilo rischio calcolato con pesi asset class non costituisce valutazione MiFID dell'utente. Un cambio da A/B a C/D è una decisione di modello di business che richiede nuova valutazione, non un semplice feature flag.

## Privacy, credenziali e consenso: requisiti per la produzione

Questa è una **specifica target**, non una dichiarazione di implementazione già conclusa.

| Oggetto | Chi può usarlo / dove decifrato | Memoria, rotazione e revoca | Compromissione e misura richiesta |
|---|---|---|---|
| Password IBKR | Solo client ufficiale IBKR; Dashboard non la raccoglie | Nessuna copia nei nostri processi, JSON, log o backup | Compromissione dispositivo: sospendere connector, revocare sessioni nel broker e ripristinare host affidabile |
| Token broker autorizzato | Solo execution/read connector con identità workload distinta; vault + envelope encryption KMS | Decifratura soltanto nel processo dedicato per richiesta/sessione strettamente necessaria; TTL provider, revoca immediata quando richiesta, rotazione chiavi secondo policy | Dump DB non dovrebbe contenere token decifrabili; host connector compromesso può comunque usare token in memoria: disattivare egress, revocare broker, riconciliare |
| Chiave privata OAuth/firma servizio | KMS/HSM dove supportato, policy per servizio/ambiente, mai AI o frontend | Operazioni di firma limitate, audit, rotazione con overlap controllato | Admin DB senza diritto KMS non può decifrare; admin cloud/KMS combinato rimane rischio: separazione ruoli, doppio controllo, accesso temporaneo |
| Dati finanziari cloud | Servizi applicativi autorizzati per tenant, DEK per tenant, TLS | Dati in memoria durante elaborazione; minimizzazione e retention configurata dopo analisi legale | DB compromesso: ciphertext + metadati limitati; isolamento tenant non si ottiene soltanto aggiungendo tenant_id |
| Dati locali | Utente OS; futuro Keychain per chiavi, protezione file e disco cifrato | Evitare backup in chiaro e copie involontarie; export esplicito | Il JSON locale non va descritto come cifrato se non lo è; FileVault protegge disco spento, non processo compromesso |
| Audit | Collector append-only indipendente, storage immutabile con retention/hold autorizzati, checkpoint firmati | Nessun segreto o narrativa sensibile non necessaria; scadenza e distruzione sotto policy | Una hash chain locale rileva alterazioni rispetto a un checkpoint fidato, ma un admin può riscriverla integralmente: **non è WORM/non alterabile** |

Per B2C definire passkey/MFA e recupero account resistente al social engineering, sessioni brevi per azioni privilegiate, revoca dispositivi, RBAC/ABAC e verifica tenant lato server. Biometria resta sul dispositivo: non acquisire template biometrici. Il supporto non deve vedere token o impersonare liberamente utenti. Nessuna chiave deve essere inviata a un modello AI.

Registro consensi/mandati: soggetto, tenant, account, finalità, versione informativa, capacità concessa, strategia/versione, limiti, timestamp, dispositivo e revoca. Distinguere base contrattuale/privacy, marketing, lettura broker e mandato di trading. La revoca arresta nuove operazioni; **pausa, annullamento ordini e chiusura posizioni sono azioni distinte**. Chiusura richiede ulteriore conferma con effetti su slippage, perdite e fiscalità.

Retention da approvare per categoria: bozze/storico scelti dall'utente; log tecnici brevi e minimizzati; evidenze ordini/consensi per gli obblighi effettivamente applicabili; backup con finestra di scadenza e cancellazione documentata. Export/cancellazione devono rispettare eventuali legal hold. Pianificare DPA, subprocessor register, trasferimenti extra SEE, DPIA e risposta a richieste interessati prima della beta cloud.

## Gate contrattuali e operativi ancora aperti

| ID | Domanda o evidenza mancante | Owner | Blocca |
|---|---|---|---|
| I1 | Schema OAuth ammesso per entità vendor, prodotti, paesi e scope minimi; tempi/costi accordo | IBKR Integration/Compliance | B2C collegato |
| I2 | Uso commerciale connector locale, supporto account indipendenti, responsabilità e naming | IBKR + legale fintech | Distribuzione del connector |
| I3 | Licenze display/non-display, storico, export e redistribuzione, eventuali fee per utente | IBKR/exchange/data provider | Dati reali condivisi |
| I4 | BTC ZEROHASHE: account eligible, API/versioni, minimi/precisione, paper, orari e permessi | IBIE API Support | Paper BTC collegato e qualsiasi live |
| L1 | Qualificazione A/B/C/D, MiFID/MiCA, partner o autorizzazione propria, paesi di servizio | Legale fintech, poi autorità ove opportuno | Vendita C/D |
| L2 | Appropriatezza/adeguatezza, product governance, costi/conflitti/marketing, reclami | Legale/compliance | Beta di servizi regolamentati |
| P1 | Titolare/responsabili, DPIA, basi, retention, trasferimenti e DPO | Privacy | Cloud multiutente |
| S1 | IAM, cifratura, segregazione, WORM indipendente, restore drill e pen test con remediation | Security/SRE | Beta esterna |
| Q1 | Dataset licenziati, costi, OOS/walk-forward/stress e forward testing | Quant/data engineer | Promozione da ricerca a paper IBKR |
| O1 | Fill/partial/reject/outage/restart testati, egress isolamento paper attestato, on-call | Trading/SRE | Paper collegato; poi eventuale live |

Non sono stati richiesti contratti, contattati terzi, utilizzati account reali o raccolte credenziali. I risultati storici restano **da calcolare**. L'assenza di accesso a dati/licenze non autorizza a sostituirli con performance simulate presentate come reali.

## Raccomandazione netta

Proseguire sul prodotto esistente con un laboratorio locale isolato e la dashboard personale. Considerare una beta B2C iniziale soltanto per A/B dopo privacy, sicurezza, approvazioni broker/dati e verifica dei termini. Mantenere C/D e BTC collegato bloccati finché i gate pertinenti non hanno prove documentate. Il superamento dei test software e un backtest vicino al 20% non rendono il prodotto autorizzato, sicuro per denaro reale o quantitativamente validato.
