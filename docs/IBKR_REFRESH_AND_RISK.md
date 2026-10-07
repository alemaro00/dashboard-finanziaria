# Aggiornamento IBKR e rischio storico

La Beta offre un unico pulsante «Aggiorna IBKR» nello stato account. Rilegge gli
snapshot Live e Paper dal bridge locale, cioè i dati già ricevuti da TWS tramite
il collegamento in sola lettura. Non richiede un nuovo accesso alla banca e non
forza un nuovo prezzo: la verifica del prezzo di chiusura resta oraria. Non garantisce che
TWS o il mercato abbiano nel frattempo fornito valori diversi.

Il precedente «Aggiorna da IBKR» faceva la stessa lettura per il solo conto Live;
è stato eliminato dalla tabella per evitare ambiguità.

La precedente voce «Rischio storico del portafoglio» è stata sostituita nella
build87 da VaR/ES parametrici al 95% su un giorno, usando composizione attuale e
rendimenti storici dei singoli fattori: vedere PORTFOLIO_VAR_ES.md. Questa stima
non richiede i flussi passati dell'utente, perché non ricostruisce i suoi rendimenti
effettivi. Dalla build88 lo storico viene richiesto attraverso SMART, conservando
l'identità del contratto; il rifiuto del feed diretto NASDAQ non è interpretato
come assenza di ogni storico autorizzato. Dalla build92 si visualizzano prezzi
di chiusura, non BID/ASK.

La ricostruzione del rischio del portafoglio effettivamente detenuto in passato
resta non disponibile. Per descrivere
le oscillazioni dei rendimenti servirebbe una serie temporale di valori degli
investimenti, con flussi esterni datati e rendimenti corretti per tali flussi.
I mesi del bilancio personale e le posizioni correnti non forniscono questa
serie. Un deposito non è un profitto. Non viene mostrata una previsione delle
perdite né un VaR dedotto dalle variazioni del patrimonio personale. Il vecchio
calcolo interno, già non visualizzato, è stato rimosso perché non isolava i flussi.

Il punteggio per asset class è invece un indicatore orientativo con pesi
convenzionali della Dashboard; non è rischio storico, né valutazione MiFID.

Riferimento metodologico: [CFA Institute, Portfolio Performance Evaluation](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/portfolio-performance-evaluation),
[GIPS, flussi esterni nei rendimenti](https://www.cfainstitute.org/-/media/documents/code/gips/2020-gips-standards-asset-owners.pdf).
