const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const source = fs.readFileSync('salary-planner-react.html', 'utf8');

test('live position table shows completed closing price, session date and closing PnL, never bid/ask', () => {
  const liveTable = source.slice(source.indexOf('>Posizioni IBKR Live<'), source.indexOf('>Posizioni IBKR Live<') + 5500);
  assert.match(liveTable, /Costo medio unitario/);
  assert.match(liveTable, /Prezzo di chiusura/);
  assert.match(liveTable, /P\/L non realizzato a chiusura/);
  assert.match(liveTable, /position\.averageEntryPrice/);
  assert.match(liveTable, /position\.closingPrice == null/);
  assert.match(liveTable, /position\.closingDate/);
  assert.doesNotMatch(liveTable, />Chiusura \{position\.closingDate/);
  assert.doesNotMatch(liveTable, /liquidationSide|BID|ASK|Last Update/);
  assert.doesNotMatch(liveTable, /Ricevuta:|Ultima quotazione disponibile|Aggiornamento automatico in corso/);
  assert.match(liveTable, /position\.closingPnl == null/);
  assert.doesNotMatch(liveTable, /accountMoney\(position\.marketPrice|accountMoney\(position\.unrealizedPnl/);
});

test('risk tooltips show separate concise normal-model formulas in EUR', () => {
  assert.match(source, /VaR₉₅ = 1,644854 × σ − μ/);
  assert.match(source, /ES₉₅ = 2,062713 × σ − μ/);
  assert.match(source, /P\/L = Σ\(valore attuale dell’esposizione × rendimento giornaliero in EUR\)/);
  assert.match(source, /Importo già in euro, non da moltiplicare nuovamente/);
});

test('VaR and ES display euro currency with the existing two-decimal money formatter', () => {
  assert.match(source, /Number\.isFinite\(portfolioRisk\[metric\.key\]\) \? money\(portfolioRisk\[metric\.key\]\) : "Non disponibile"/);
  assert.doesNotMatch(source, /precise\(portfolioRisk\[metric\.key\], 6\)/);
});

test('negative bank movements retain variable classification without a cash withdrawal button', () => {
  assert.doesNotMatch(source, /classifyBankExpense\(record, "Prelievo cash"\)|>Prelievo cash<\/button>/);
  assert.match(source, /classifyBankExpense\(record, "Costo Variabile"\)/);
  assert.match(source, /note\.category === "Prelievo cash"/);
});

test('live assets have an information tip and omit technical market provenance text', () => {
  const liveTable = source.slice(source.indexOf('>Posizioni IBKR Live<'), source.indexOf('>Posizioni IBKR Live<') + 5500);
  assert.match(liveTable, /<InfoTip label=\{position\.symbol\}>\{position\.description\}/);
  assert.match(liveTable, /position\.investmentDetail/);
  assert.doesNotMatch(liveTable, /Stima su quotazione non in tempo reale|Geografia:|position\.classificationSource|position\.geographySource/);
});

test('wealth omits duplicate allocation and places the live badge beside positions', () => {
  assert.doesNotMatch(source, /Allocazione investimenti per asset class|Stima di chiusura: BID per long/);
  assert.match(source, />Posizioni IBKR Live<\/div>\s*<span className="badge status-line">/);
  assert.equal((source.match(/posizioni Live`/g) || []).length, 1);
  assert.match(source, /Esposizione per asset class/);
});

test('wealth has one IBKR refresh and historical risk cannot use personal budget changes', () => {
  const wealth = source.slice(source.indexOf('id="wealth-section"'));
  assert.equal((wealth.match(/>\s*Aggiorna IBKR\s*</g) || []).length, 1);
  assert.doesNotMatch(wealth, />Aggiorna da IBKR</);
  assert.match(wealth, /refreshIbkr\("paper"\);\s*refreshIbkr\("live"\);/);
  assert.match(wealth, /chiusura dell’ultima seduta completata viene verificata ogni ora/);
  assert.match(wealth, /Value at Risk/);
  assert.match(wealth, /Expected Shortfall/);
  assert.match(wealth, /95% · 1 giorno/);
  assert.match(wealth, /portfolioRisk\?\.status === "ready"/);
  assert.match(wealth, /Posizioni attuali e liquidità estera, incluse correlazioni e cambi/);
  assert.doesNotMatch(source, /parametricVarAmount|parametricVarPct|const monthlyReturns = wealthSeries/);
});

test('banking has one main refresh action and compact setup with bank-independent renewal', () => {
  assert.doesNotMatch(source, />Verifica collegamento<|>Dimentica dati bancari locali<|>Scegli i conti da leggere<|Rinnova \{connection\.bank\}/);
  assert.match(source, /Premi “Aggiorna movimenti” per caricare le nuove operazioni/);
  assert.match(source, /ancora da classificare/);
  assert.match(source, /<summary>Gestisci banche e conti<\/summary>/);
  assert.doesNotMatch(source, /Scegli il Paese e la banca\.|Per rinnovare, seleziona una banca già collegata\.|<summary>[^\n]*Gestisci conti collegati/);
  assert.match(source, /connection\.bank === bankSetup\.bank && connection\.country === bankSetup\.country\) \? "Rinnova accesso" : "Collega banca"/);
  assert.match(source, /Rimuovi dati bancari dal Mac<\/button><button[^>]*[\s\S]*?>Aggiorna elenco banche/);
  assert.match(source, /I mesi salvati e le voci già classificate restano/);
  assert.match(source, /open=\{Boolean\([^\n]*banking\.data\?\.selectionRequired/);
  assert.match(source, /Salva conti e carica movimenti/);
});

test('legal links appear once in the app footer outside collapsible sections', () => {
  const footer = source.match(/<footer className="small" aria-label="Informazioni legali"[^>]*>([\s\S]*?)<\/footer>/);
  assert.ok(footer);
  assert.match(footer[1], /ibkrBridgeBaseUrl\}\/privacy/);
  assert.match(footer[1], /ibkrBridgeBaseUrl\}\/terms/);
  assert.equal((source.match(/>Informativa privacy<\/a>/g) || []).length, 1);
  assert.equal((source.match(/>Condizioni e limiti del servizio<\/a>/g) || []).length, 1);
  assert.ok(footer.index > source.lastIndexOf('</section>'));
});

test('beta exposes only the two authorized collapsible sections', () => {
  assert.match(source, /href="#finance-section"[\s\S]*?>01<[\s\S]*?Gestione delle finanze/);
  assert.match(source, /href="#wealth-section"[\s\S]*?>02<[\s\S]*?Wealth management/);
  assert.match(source, /Dashboard finanziaria <span className="beta-badge">Beta<\/span>/);
  assert.doesNotMatch(source, /salary-section|Stima stipendio netto da RAL/);
  assert.doesNotMatch(source, /research-section|Laboratorio strategie/);
});

test('beta preserves the original complete-dashboard color system', () => {
  assert.match(source, /--accent:#d7b46a/);
  assert.match(source, /\.macro-finance\{--macro-accent:#d7b46a/);
  assert.match(source, /\.macro-wealth\{--macro-accent:#a482ef/);
  assert.match(source, /border:1px solid #c0a25e/);
  assert.match(source, /grid-template-columns:repeat\(2,1fr\)/);
  assert.doesNotMatch(source, /macro-salary|macro-research/);
});

test('only the month selector receives the native-control size correction', () => {
  assert.match(source, /\.monthly-period-fields select\{[\s\S]*?height:36px;min-height:36px;[\s\S]*?font-size:13px/);
  assert.doesNotMatch(source, /\.monthly-period-fields input,\.monthly-period-fields select\{[^}]*height:/);
});

test('salary-category cashflow remains independent from the removed salary estimator', () => {
  assert.match(source, /value: "Stipendio", label: "Stipendio"/);
  assert.doesNotMatch(source, /calculateIrpef|salaryEstimate|grossSalary/);
});
