# Distribuzione su altri computer

## Regola fondamentale

Non condividere mai la cartella dati dell’utente, la chiave
`enable-banking.pem`, gli identificativi di sessione o gli archivi contenenti
movimenti reali. Il pacchetto dell’app deve contenere soltanto codice e risorse.
Ogni utente configura la propria applicazione Enable Banking dalla procedura
guidata.

## macOS

La build locale attuale crea `Beta Dashboard Finanziaria.app` e uno ZIP, ma è
firmata ad hoc, compilata per Apple Silicon e usa Python di sistema. È adatta a
sviluppo e test sul Mac corrente, non ancora alla distribuzione pubblica.

Per consegnarla in modo affidabile a terzi occorre:

1. incorporare un runtime Python e tutte le dipendenze, senza dipendere dalla
   configurazione del computer destinatario;
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
Python, dipendenze, Node.js per la prima compilazione e OpenSSL. Non è un installer
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

Per spostare i dati personali fra due propri computer, chiudere l’app e copiare con
un canale cifrato il solo archivio necessario dalla cartella dati della relativa
edizione. Il file contiene informazioni finanziarie sensibili e deve essere
protetto durante il trasferimento e cancellato dal supporto temporaneo.

Non trasferire la configurazione bancaria a un altro utente. Sul nuovo computer è
preferibile configurare nuovamente Enable Banking e autorizzare i conti. Prima di
una migrazione pubblica va aggiunta all’interfaccia una funzione di esportazione e
importazione cifrata: il JSON in chiaro non è adatto a essere inviato via email o
caricato su servizi condivisi.

## Checklist prima della pubblicazione

- Nessun dato reale, segreto o chiave nel repository e nel pacchetto.
- Firma e verifica del pacchetto sulla piattaforma destinataria.
- Runtime e dipendenze inclusi e inventariati.
- Informativa privacy e condizioni d’uso accessibili prima del collegamento bancario.
- Procedura di cancellazione dati e revoca del consenso documentata.
- Test su profilo utente pulito e senza ambiente di sviluppo.
- Canale aggiornamenti firmato, rollback e checksum pubblicati.
