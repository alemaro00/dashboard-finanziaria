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
- Application ID, chiave PEM, sessioni, conti e movimenti non sono inclusi nel
  pacchetto dell’app. La chiave e i file locali hanno permessi riservati all’utente.
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

- I dati locali non sono cifrati dall’app: dipendono dalla cifratura del disco e
  dalla sicurezza dell’account del sistema operativo. Attivare FileVault su macOS e
  BitLocker/Device Encryption su Windows.
- Chi controlla l’account del sistema operativo può leggere i dati dell’app.
- La disponibilità e la completezza bancaria dipendono dal provider, dalla banca e
  dalla validità del consenso.
- La distribuzione attuale non è ancora notarizzata su macOS né pacchettizzata e
  firmata come MSIX su Windows.
- Per un prodotto multiutente realmente “un clic” servirebbe un backend gestito. Ciò
  trasferirebbe dati e responsabilità privacy fuori dal dispositivo e richiederebbe
  una progettazione legale, operativa e di sicurezza distinta; non va introdotto
  implicitamente nella versione locale.
