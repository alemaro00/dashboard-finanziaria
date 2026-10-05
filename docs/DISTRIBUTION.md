# Distribuzione su altri computer

## Regola fondamentale

Non condividere mai la cartella dati dell’utente, la chiave
`enable-banking.pem`, gli identificativi di sessione o gli archivi contenenti
movimenti reali. Il pacchetto dell’app deve contenere soltanto codice e risorse.
Ogni utente configura la propria applicazione Enable Banking dalla procedura
guidata.

## macOS

La build locale attuale crea `Beta Dashboard Finanziaria.app` e uno ZIP, ma è
firmata ad hoc, compilata per Apple Silicon e incorpora Python e dipendenze. È adatta a
sviluppo e test sul Mac corrente, non ancora alla distribuzione pubblica.

Per consegnarla in modo affidabile a terzi occorre:

1. verificare il runtime incorporato su un Mac destinatario pulito, senza Python
   o strumenti di sviluppo;
2. produrre un binario universale `arm64 + x86_64`, oppure due pacchetti distinti;
3. attivare Hardened Runtime e firmare app, eseguibili e librerie con un certificato
   Apple Developer ID Application;
4. inviare lo ZIP/DMG al servizio notarile Apple e applicare lo staple del ticket;
5. provare installazione, primo avvio, aggiornamento e rimozione su un account macOS
   pulito senza strumenti di sviluppo;
6. distribuire il DMG/ZIP notarizzato tramite un canale HTTPS con checksum SHA-256.

La semplice copia della `.app` attuale può funzionare solo su un Mac simile a quello
di sviluppo e può essere bloccata da Gatekeeper. Non chiedere agli utenti di
disattivare le protezioni di macOS.

## Windows

Una `.app` macOS non può essere trasferita o eseguita su Windows. Il file
`avvia-dashboard-ibkr.bat` è un launcher per sviluppatori: richiede sorgenti,
Python, dipendenze e Node.js per la prima compilazione. Non è un installer
per utenti finali.

Per una vera versione Windows occorre creare un wrapper desktop Windows, includere
il runtime Python e il frontend già compilato, quindi produrre un pacchetto MSIX.
Per la distribuzione pubblica le opzioni consigliate sono:

- Microsoft Store: firma del pacchetto gestita dallo Store e aggiornamenti integrati;
- distribuzione diretta: MSIX firmato con un certificato attendibile o con Azure
  Artifact Signing, più un canale di aggiornamento verificato.

Vanno testati almeno Windows 10 e 11, WebView2, firewall locale, callback loopback,
percorsi dati per utente, aggiornamenti e disinstallazione. Un pacchetto non firmato
o autofirmato è adeguato soltanto a test controllati e può essere bloccato da
SmartScreen.

## Trasferire i propri dati

Per spostare i propri dati:

1. aprire «Backup e trasferimento dati», inserire una password di almeno 12
   caratteri e scegliere «Esporta backup protetto»;
2. trasferire il `.dfbackup` al proprio nuovo computer; conservare la password
   separatamente (non è recuperabile);
3. nella nuova beta aprire la stessa sezione, inserire la password e scegliere
   «Importa backup protetto», confermando la sostituzione dei dati locali;
4. configurare e autorizzare nuovamente i conti: il backup non contiene chiavi né
   sessioni bancarie. La lettura riprende soltanto dopo conferma dei conti.

Non copiare i JSON cifrati della cartella dati fra Mac: sono legati al Portachiavi
del Mac di origine. Usare sempre il backup protetto portabile. Non importare il
proprio backup sul computer di un altro utente.

Non trasferire la configurazione bancaria a un altro utente. Sul nuovo computer è
preferibile configurare nuovamente Enable Banking e autorizzare i conti. Il backup
portabile non include tali segreti; un JSON in chiaro non va inviato via email.

## Build e firma riproducibili

Creare `.build/freeze-env` con Python 3.12 arm64 e installare
`requirements-build.txt`. Eseguire `INSTALL_APP=0 zsh scripts/build-macos-app.sh`:
produce app, ZIP e checksum in `dist/`, senza installazione. Il pacchetto contiene
runtime Python, CA TLS, dipendenze e informative; non contiene archivi utente.
`NODE_BIN` può indicare Node soltanto per la compilazione sul Mac sviluppatore;
Node, Python e OpenSSL non sono richiesti al destinatario.

Per la release pubblica impostare `PUBLIC_RELEASE=1`, `SIGN_IDENTITY` all'identità
Developer ID Application e `NOTARY_PROFILE` al profilo precedentemente registrato
nel Portachiavi con `notarytool store-credentials`. Il processo firma i binari
interni prima del bundle, usa timestamp e Hardened Runtime, invia ad Apple, applica
e verifica il ticket e controlla Gatekeeper prima di installare/pubblicare lo ZIP.
Non inserire password Apple o chiavi nel repository o in argomenti della build.

Senza Developer ID la build è ad hoc per test locali, senza Hardened Runtime:
non viene introdotto un entitlement per disattivare la library validation. La
release pubblica è bloccata in assenza di identità e profilo notarile. Sul Mac
attuale non risultano identità di firma valide; nessuna notarizzazione effettuata.
La build attuale è arm64/macOS13+, non è destinata ai Mac Intel.

Verificare anche le licenze delle dipendenze prima della distribuzione, in
particolare IB API Non-Commercial/Commercial per `ibapi`. I metadati e le licenze
disponibili dei pacchetti sono inclusi nel runtime; non sostituiscono l'accordo
di licenza eventualmente necessario per l'uso commerciale.

La distribuzione del solo software locale ad altri utenti non abilita la lettura
dei loro conti con la tua applicazione Restricted. Per onboarding pubblico semplice
serve accordo con Enable Banking/provider AIS e backend con chiave privata non
distribuita. Questo passo non è implementato né autorizzato implicitamente.

Riferimenti: [distribuzione notarizzata Apple](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution),
[runtime PyInstaller](https://www.pyinstaller.org/en/stable/usage.html),
[API e condizioni Enable Banking](https://enablebanking.com/docs/api/reference/).

## Checklist prima della pubblicazione

- Nessun dato reale, segreto o chiave nel repository e nel pacchetto.
- Firma e verifica del pacchetto sulla piattaforma destinataria.
- Runtime e dipendenze inclusi e inventariati.
- Informativa privacy e condizioni d’uso accessibili prima del collegamento bancario.
- Procedura di cancellazione dati e revoca del consenso documentata.
- Test su profilo utente pulito e senza ambiente di sviluppo.
- Canale aggiornamenti firmato, rollback e checksum pubblicati.
