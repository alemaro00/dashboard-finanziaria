# Audit iniziale — 10 settembre 2026

Baseline Git: main, 0b2e8a1, al primo controllo working tree pulito. Nessun AGENTS.md trovato nel progetto o nei genitori controllati. Letti README, requirements, launcher, build, sorgente macOS, HTTP handler, persistenza e test prima delle modifiche applicative. Nessun segreto/account reale letto o broker contattato durante audit. I file dei dati dell'utente non sono input dei test.

## Architettura esistente

Un singolo HTML React 18 + JSX compilato da Babel nel browser, caricato da CDN non versionate esattamente; backend Python stdlib ThreadingHTTPServer + ibapi==9.81.1.post1. Wrapper macOS Cocoa/WKWebView avvia /usr/bin/python3 e backend sulla 8766; launcher browser 8765; TWS socket Live 7496 e Paper 7497. JSON atomico dashboard-state.json e localStorage (bozze, storico, interfaccia). Nessun database, migrazione SQL, account applicativo o tenant. Il binario app precedente è arm64 e dipende da Python esterno: non è un pacchetto autonomo per qualunque Mac.

## Gap analysis prima delle correzioni

| Area | Classe | Evidenza / conseguenza |
|---|---|---|
| Cashflow, storico, patrimonio | riutilizzabile con modifiche | React esistente preservabile; normalizzazione frontend, backend valida poco lo schema |
| Snapshot e freschezza IBKR | riutilizzabile con modifiche | 8 test Python offline passano; handshake distinto dalla freschezza, callback read-only |
| HTTP locale | vulnerabile | CORS *, GET finanziari senza filtro Origin/Host: sito esterno può leggere dati; POST prefix Origin non confronta origine esatta |
| Memoria | vulnerabile | JSON plaintext, permessi dipendenti da umask, nessun backup/versionamento; errore load abilita save e può sovrascrivere stato recuperabile |
| Browser supply chain | vulnerabile | React/Babel CDN dinamici eseguiti con accesso ai dati; nessuna CSP |
| Segreti | incompleta | nessun secret broker salvato dall'app; TWS mantiene login; nessun vault o IAM |
| Paper/live | da riprogettare | stesso processo avvia automaticamente entrambi; lettura sola ma inadatto a servizio paper isolato |
| IAM/tenant/consensi | assente | single-user OS, nessuna passkey/MFA/RBAC; non vendibile come B2C multiutente |
| Ordini/OMS/risk engine/bot | assente | nessuna route ordine né placeOrder applicativa; la classe SDK ereditata espone metodi che vanno bloccati esplicitamente |
| Strategie/backtest/allocator | assente | nessun dataset storico verificato; nessuna performance dimostrabile |
| Audit | assente | log console; nessun registro transazionale/tamper evidence |
| Build/distribuzione | incompleta | firma ad hoc, Python esterno, arm64, iconutil fallback; non notarizzata |
| Test/lint/types/CI | incompleta | 8 test Python passano; 4 test Node disponibili ma node non in PATH; nessun lint/type config, nessun test HTTP/UI |
| Mobile | assente | CSS responsive riutilizzabile; nessun client mobile nativo né autenticazione remota |
| Abbonamenti/operatività | assente | nessun billing, entitlement, monitoraggio, recovery, supporto |

## Debito e discrepanze

- VaR basato sulle variazioni del patrimonio è influenzato da versamenti/prelievi: non è VaR di un portafoglio valutato mark-to-market. Disabilitare la cifra fino a rendimenti depurati dai flussi.
- I pesi asset class del profilo di rischio sono euristiche non calibrate, non adeguatezza MiFID né misura probabilistica.
- P/L realizzato TWS e storico fiscale delle chiusure non coincidono: activity statements necessari.
- SDK PyPI 9.81 molto precedente alla documentazione attuale; aggiornamento richiede SDK ufficiale, compatibilità callback e test contrattuali. Non dichiarato vulnerabile senza advisory verificato.
- Fonte JSX monolitica preservata per ridurre regressioni; compilazione anticipata e dipendenze locali sono primo passo, estrazione componenti successiva.
- Stato UI su localStorage non protegge da accesso al dispositivo compromesso; neppure localhost è autenticazione utente.

## Assunzioni e gate

MVP locale single-user; esattamente sei strategie del testo allegato inclusa BTC spot simulata. Nessun uso di credenziali o trasmissione ordini IBKR; nessuna installazione/distribuzione dell'app aggiornata in questo incarico. Ricerca sintetica è test del software, non paper forward validato. Conservare cashflow in formato compatibile, nuovo database solo per laboratorio. Le aree non implementate sono esplicitate nel rapporto finale, non dichiarate risolte da configurazioni fittizie.
