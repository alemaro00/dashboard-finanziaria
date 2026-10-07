# Ripartizione dei movimenti bancari — Beta build 96

## Uso

- **Dividi**, accanto al movimento da classificare, apre la ripartizione.
- Ogni quota ha nome, categoria e importo indipendenti. **Aggiungi quota** crea un'altra riga; **Usa residuo** completa la riga con quanto resta dopo le altre.
- Uscite: costi fissi, costi variabili o investimenti. Entrate: emolumenti, entrate extra o disinvestimenti. Due quote possono avere la stessa categoria e nomi diversi.
- **Salva quote** applica tutte le modifiche insieme. **Annulla** o Escape non modifica le classificazioni. Le righe dell'editor non sono salvate finché non si conferma.
- **Ripartisci**, nella voce dettagliata, riapre tutte le quote dello stesso movimento, anche quelle in altre categorie. Per aumentare una quota interamente assegnata bisogna ridurre un'altra nella stessa finestra.
- **Rimuovi** elimina soltanto quella quota dalla classificazione: il suo importo torna da assegnare, senza duplicare il bonifico. Nell'editor, **Togli** ha effetto solo alla conferma; togliendo tutte le quote e salvando torna disponibile l'intero movimento.
- Le quote seguono il normale salvataggio automatico. **Salva mese / Salva modifiche** aggiorna il resoconto mensile; il backup protetto conserva gli identificativi e la ripartizione.

Esempio: bonifico da 1.000 €, 200 € fissi “Affitto” e 800 € variabili “Acquisti”. Rimuovendo Affitto tornano disponibili 200 € sotto il riferimento del bonifico originale; Acquisti resta a 800 €. 210 + 800 è bloccato; 210 + 790 è valido.

## Invarianti

Il record nell'archivio bancario non viene modificato dallo split. Ogni quota ha un ID proprio e conserva `bankTransactionId`, `bankOriginalAmount`, `bankRecordType`, `transactionDate`, `originalBankDescription` e `bankSplitVersion: 1`.

I confronti usano centesimi interi, non una tolleranza sui float. Quote positive con massimo due decimali, nomi da 1 a 120 caratteri, massimo 50 quote. Non si sommano più dell'originale; una ripartizione parziale lascia visibile solo il residuo. Le classificazioni non EUR restano bloccate, senza conversioni implicite.

L'editor verifica la firma delle quote correnti per non sovrascrivere una modifica intervenuta nel frattempo. I pulsanti di categoria ricalcolano il residuo sullo stato più recente: doppi clic non duplicano la classificazione. Rinominare il movimento nell'archivio non sovrascrive i nomi delle quote versionate.

Prima di salvare o importare un backup, il backend verifica totale, centesimi, categorie, ID, mese e riferimenti. Se il movimento è ancora nell'archivio, il totale incorporato deve coincidere con quello bancario. Dopo la rimozione dell'archivio o sul Mac di destinazione, il backup mantiene il totale originale incorporato e coerente tra le quote. Le vecchie classificazioni non versionate restano compatibili; vengono versionate quando si ripartiscono.

Corrente, bozze e mesi salvati sono copie di periodi, non quote ulteriori dello stesso movimento: i controlli sono separati per ciascun periodo. I conti Cash, il saldo bancario e le posizioni IBKR non sono modificati dalla ripartizione di una normale entrata/uscita bancaria. La categoria storica Prelievo cash non è offerta nell'editor.

## Verifiche

Test frontend: split, residuo, rimozione, riclassificazione, blocco e ribilanciamento, doppio clic, entrate, precisione, mese, ID, nomi e serializzazione. Test Python/HTTP: validazione e rifiuto del salvataggio oltre il totale senza sovrascrivere lo stato valido. Prova grafica su dati sintetici isolati: 200 fissi + 800 variabili; rifiuto di 210 + 800; rimozione della sola quota fissa; 700 emolumenti + 300 extra; salvataggio mese e ricarica. Nessuna classificazione personale cambiata per queste prove.
