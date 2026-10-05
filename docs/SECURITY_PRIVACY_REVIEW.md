# Verifica sicurezza, privacy e persistenza

Data della verifica: 5 ottobre 2026.

## Confini e dati

- Il servizio HTTP ascolta soltanto su `127.0.0.1`.
- Host e Origin vengono validati contro la porta loopback effettiva; le mutazioni
  richiedono JSON e token CSRF.
- Il callback bancario ammette soltanto una navigazione GET verso l’esatto endpoint
  loopback configurato. `state` è confrontato in tempo costante e scade dopo venti
  minuti.
- L’integrazione espone esclusivamente AIS in lettura: non esistono rotte di
  pagamento o di invio ordini.
- Chiave PEM, configurazione personale salvata, sessioni, conti e movimenti non
  sono inclusi nel pacchetto dell’app. La chiave e i file locali hanno permessi
  riservati all’utente. Resta nel codice un Application ID legacy non segreto,
  usato soltanto per compatibilità con una chiave già presente sul Mac: non concede
  accesso senza la relativa chiave e non va usato per onboarding pubblico.
- Il frontend riceve solo identificativi conto mascherati; la chiave privata non
  viene mai restituita dal servizio locale.

## Configurazione bancaria

- La chiave viene scelta con un file picker del browser locale, limitata per
  dimensione, validata come PEM e provata tramite una firma RSA prima del salvataggio.
- L’Application ID è validato e conservato separatamente dalla chiave.
- Le banche disponibili sono lette da Enable Banking per Paese; non sono limitate a
  nomi codificati nell’interfaccia.
- Il ritorno dell’autorizzazione viene elaborato automaticamente dal listener locale;
  l’utente non copia più URL contenenti `code` e `state`.
- È disponibile la cancellazione locale di sessioni, conti e movimenti bancari senza
  eliminare lo storico mensile già salvato.

## Salvataggio e recuperabilità

- La bozza corrente viene salvata automaticamente dopo le modifiche e nuovamente
  quando la finestra viene nascosta o chiusa.
- Le scritture usano un file temporaneo, `fsync` e sostituzione atomica.
- Prima di sostituire uno stato valido viene scritto
  `dashboard-state.json.bak`; stato e backup hanno permessi `0600`.
- Un file corrente corrotto non viene sovrascritto automaticamente, così resta
  disponibile per un recupero manuale.
- `Salva mese` inserisce o sostituisce un solo periodo identificato da mese e anno;
  i test verificano isolamento fra mesi, centesimi, modifica e passaggio al mese
  successivo.

## Rischi residui

- Nella beta Mac installata gli archivi e la chiave PEM sono cifrati con
  AES-256-GCM e chiave casuale di 256 bit nel Portachiavi (non sincronizzata).
  Scritture e backup locali sono atomici; un Portachiavi non disponibile provoca
  un errore, non un ripiego in chiaro. I vecchi archivi bancari sono migrati al primo
  avvio e lo stato/backup alla prima scrittura. Le copie esterne precedenti non
  vengono modificate. La modalità sorgenti senza helper resta non cifrata.
  FileVault è comunque raccomandato; malware nello stesso account resta un rischio.
- Chi controlla l’account del sistema operativo può leggere i dati dell’app.
- La disponibilità e la completezza bancaria dipendono dal provider, dalla banca e
  dalla validità del consenso.
- La distribuzione attuale non è ancora notarizzata su macOS né pacchettizzata e
  firmata come MSIX su Windows.
- Per un prodotto multiutente realmente “un clic” servirebbe un backend gestito. Ciò
  trasferirebbe dati e responsabilità privacy fuori dal dispositivo e richiederebbe
  una progettazione legale, operativa e di sicurezza distinta; non va introdotto
  implicitamente nella versione locale.

## Correzioni del 5 ottobre

- Autorizzazione pendente scade visivamente dopo 20 minuti e può essere annullata.
- State anche sugli errori bancari, consumo prima dello scambio e blocco replay.
- Durata consenso interpretata in secondi, come previsto dall'API; limite della banca.
- Preferenza DECOUPLED solo per metodi personali senza credenziali raccolte dall'app.
  Non tutte le banche supportano push; redirect/SCA restano sotto controllo bancario.
- Conferma locale dei conti prima di leggere saldi/movimenti di un nuovo consenso.
- Nessuna perdita automatica dello storico importato al rinnovo; riferimenti scoped
  per conto e compatibilità con gli ID già classificati.
- Risposta 429 provoca attesa locale di cinque minuti; dati conservati. Elenco banche
  in cache per un'ora per ridurre richieste ripetute.
- Redirect HTTP dell'API bloccati per non inoltrare Authorization a un altro host;
  TLS verificato con CA incorporate. Errori del provider non riportano il JSON grezzo.
- Firma RSA in memoria, senza dipendenza da OpenSSL esterno né chiavi in argomenti.
- Backup portabile scrypt (N=32768,r=8,p=1), salt16, AES-256-GCM nonce12, password
  minima12; importazione verificata prima della scrittura e conferma sostituzione.
- Il frontend non scrive più l'intero stato finanziario nel localStorage; rimuove
  la vecchia copia dopo il salvataggio riuscito. Preferenze UI non sensibili restano.
- Runtime Python/dipendenze incorporati; ambiente figlio ridotto, nessun PYTHONPATH
  ereditato. Navigazione interna limitata al loopback della beta.

## Conformità: cosa non è certificato

Questi controlli tecnici non sono una certificazione di sicurezza o conformità.
Per offrire AIS a terzi occorre definire con un provider autorizzato il modello
contrattuale/regolamentare, la responsabilità del consenso e le condizioni PSD2.
La chiave di una applicazione pubblica non va incorporata nei client: richiederebbe
un servizio backend separato, un progetto esplicito, gestione incidenti e segreti.

GDPR: definire titolare/responsabili e basi giuridiche (il consenso AIS non sostituisce
automaticamente una base giuridica per ogni trattamento), minimizzazione, informative,
diritti, conservazione, trasferimenti e valutazione DPIA se necessaria. DORA dipende
dal ruolo dell'entità; non è automaticamente soddisfatto da un'app locale.
Prima del lancio occorrono revisione legale, test indipendenti e prove su altri Mac.

Fonti primarie: [API Enable Banking](https://enablebanking.com/docs/api/reference/),
[PSD2](https://eur-lex.europa.eu/legal-content/en/ALL/?uri=CELEX%3A32015L2366),
[SCA AIS](https://eur-lex.europa.eu/eli/reg_del/2022/2360/oj/eng),
[GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng/),
[DORA](https://eur-lex.europa.eu/legal-content/ENG/ALL/?uri=CELEX%3A32022R2554).
