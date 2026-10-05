# Informativa privacy — Dashboard Finanziaria

Ultimo aggiornamento: 5 ottobre 2026

## Ambito

Dashboard Finanziaria è un'applicazione personale e non commerciale. La funzione di collegamento bancario è destinata esclusivamente al titolare dell'applicazione e ai conti che egli autorizza esplicitamente tramite Enable Banking in modalità Production Restricted.

## Dati trattati

Quando il collegamento bancario è attivo, l'applicazione può ricevere gli identificativi dei conti autorizzati, i saldi, le valute e i movimenti disponibili tramite le API di Open Banking. Può inoltre conservare i dati tecnici strettamente necessari per gestire il consenso e la sincronizzazione.

Dashboard Finanziaria non richiede né conserva le credenziali di accesso alla banca. L'autenticazione e la Strong Customer Authentication avvengono sulle pagine o nelle applicazioni della banca.

## Finalità e modalità

I dati sono usati per mostrare e organizzare entrate, uscite e saldi nella dashboard personale. Il collegamento previsto è in sola lettura: non abilita pagamenti, bonifici o operazioni di investimento.

I dati applicativi sono conservati localmente sul dispositivo dell'utente. Le informazioni necessarie al collegamento transitano attraverso Enable Banking e la banca scelta, secondo le rispettive informative e condizioni.

Nella beta Mac installata gli archivi applicativi, bancari e la chiave PEM sono
cifrati con AES-256-GCM. La chiave locale è conservata nel Portachiavi del Mac,
non sincronizzata. L'avvio dai sorgenti senza helper Portachiavi non fornisce
questa cifratura: è una modalità di sviluppo, non una distribuzione protetta.
La cifratura non protegge da malware o da chi controlla l'account macOS sbloccato.
FileVault resta raccomandato per proteggere l'intero disco e i backup di sistema.

Il backup trasferibile, creato su richiesta, usa una password scelta dall'utente,
scrypt e AES-256-GCM. Include mesi, bozze e classificazioni, non chiavi private
né sessioni del provider. Password e file vanno conservati separatamente.

## Conservazione e cancellazione

I dati locali restano sul dispositivo finché l'utente non li elimina o disinstalla l'applicazione rimuovendone anche i dati. L'accesso bancario può essere revocato dal pannello Enable Banking o dalla banca. I periodi di conservazione applicati da Enable Banking e dalla banca sono disciplinati dalle loro informative.

Deselezionare un conto ferma le successive letture nella Dashboard, ma non cancella
lo storico né revoca il consenso presso la banca. «Dimentica dati bancari locali»
cancella la cache bancaria e le sessioni locali, non i mesi già salvati. Questi,
le bozze e il backup locale restano nella cartella dati della beta. Disinstallare
la sola app non cancella la cartella dati né le copie esportate. Per cancellazione
completa occorre eliminare separatamente archivi, copie e backup di sistema, e
revocare il consenso presso banca/provider. Non è promessa una cancellazione
fisica sicura da SSD o backup di terzi.

## Condivisione

I dati non sono venduti e non sono usati per pubblicità. I soggetti tecnici coinvolti nel collegamento sono Enable Banking e l'istituto finanziario autorizzato dall'utente.

## Sicurezza

La chiave privata dell'integrazione e gli eventuali token non devono essere inseriti nel codice pubblico o condivisi con altri utenti. La procedura guidata può leggere localmente il file PEM scelto dall'utente e lo consegna soltanto al servizio loopback sullo stesso computer; la chiave non viene restituita al frontend. È conservata fuori dal repository e dal pacchetto dell'app, con permessi privati sul dispositivo. L'accesso viene richiesto con il minimo insieme di permessi necessario.

## Contatti

Questa informativa descrive l'uso personale locale. Non costituisce un'informativa
completa per un servizio pubblico gestito: prima della pubblicazione il titolare
del servizio deve identificare soggetto e contatti, basi giuridiche, responsabili,
destinatari, trasferimenti, tempi di conservazione e modalità per esercitare i
diritti GDPR. Questi elementi dipendono dal modello contrattuale ancora da definire.

Per richieste relative ai dati trattati da Dashboard Finanziaria, scrivere all'indirizzo di contatto indicato nell'applicazione registrata nel pannello Enable Banking.

Le richieste relative all'autenticazione bancaria, ai dati detenuti dalla banca o al servizio Enable Banking devono essere rivolte anche al rispettivo fornitore.
