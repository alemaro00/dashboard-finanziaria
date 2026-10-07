const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('salary-planner-react.html', 'utf8');
const start = source.indexOf('function normalizeNote(');
const end = source.indexOf('function mergeValueMaps', start);
const helpers = vm.runInNewContext(`${source.slice(start, end)}\n({applyBankSplit, bankMovementAllocation, bankAllocationSignature, bankAmountCents, availableBankMovements, removeDetailedEntriesFromState, monthlyReport, groupReportNotes, cashAccountBalance, switchMonthlyPeriod})`, {
  normalizeCategory: v => v,
  roundMoney: v => Math.round((Number(v) + Number.EPSILON) * 100) / 100,
  months: ['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
});
const record = {id:'fixture-bank', amount:1000, currency:'EUR', date:'2026-10-01', recordType:'expense', bank:'Banca test', description:'Bonifico originale test'};
const fresh = () => ({monthName:'Ottobre',year:2026,notes:[],income:'0.00',additionalIncome:'0.00',fixedCosts:'0.00',variableCosts:'0.00',cashOpeningBalance:10,monthlyHistory:[],monthDrafts:{}});
const rows = () => [{id:'part-a',label:'Affitto',category:'Costo Fisso',amount:'200.00'}, {id:'part-b',label:'Acquisti',category:'Costo Variabile',amount:'800.00'}];
const apply = (state, parts=rows(), bank=record) => helpers.applyBankSplit(state, bank, parts, helpers.bankAllocationSignature(state.notes, bank.id));

test('split keeps immutable source, independent names and exact category totals', () => {
  const before = JSON.stringify(record);
  const result = apply(fresh());
  assert.equal(result.error,'');
  assert.equal(result.state.fixedCosts,'200.00');
  assert.equal(result.state.variableCosts,'800.00');
  assert.equal(result.state.notes.length,2);
  assert.equal(helpers.availableBankMovements([record],result.state.notes).length,0);
  for (const note of result.state.notes) {
    assert.equal(note.bankTransactionId,record.id);
    assert.equal(note.bankOriginalAmount,1000);
    assert.equal(note.originalBankDescription,record.description);
    assert.equal(note.transactionDate,record.date);
    assert.equal(note.bankSplitVersion,1);
  }
  assert.equal(JSON.stringify(record),before);
  assert.equal(helpers.cashAccountBalance(result.state),10);
});

test('removing one child returns only its amount, removing all returns whole movement', () => {
  let state = apply(fresh()).state;
  state = helpers.removeDetailedEntriesFromState(state,n => n.id==='part-a');
  const remaining = helpers.availableBankMovements([record],state.notes)[0];
  assert.equal(state.fixedCosts,'0.00');
  assert.equal(state.variableCosts,'800.00');
  assert.equal(state.notes[0].id,'part-b');
  assert.equal(remaining.amount,200);
  assert.equal(remaining.originalAmount,1000);
  assert.equal(remaining.allocatedAmount,800);
  assert.equal(remaining.description,record.description);
  state = apply(state,[]).state;
  assert.equal(state.notes.length,0);
  assert.equal(state.variableCosts,'0.00');
  assert.equal(helpers.availableBankMovements([record],state.notes)[0].amount,1000);
});

test('210 plus 800 is rejected; simultaneous 210 plus 790 rebalance is atomic', () => {
  const current = apply(fresh()).state;
  const invalid = rows(); invalid[0].amount='210';
  const rejected = apply(current,invalid);
  assert.match(rejected.error,/superano/);
  assert.equal(rejected.state,current);
  invalid[1].amount='790';
  const saved = apply(current,invalid);
  assert.equal(saved.error,'');
  assert.equal(saved.state.fixedCosts,'210.00');
  assert.equal(saved.state.variableCosts,'790.00');
  assert.equal(saved.state.notes.length,2);
  assert.equal(helpers.availableBankMovements([record],saved.state.notes).length,0);
});

test('same category different names stays separate in monthly report', () => {
  const parts = rows(); parts[0].category='Costo Variabile';
  const saved = apply(fresh(),parts).state;
  assert.equal(saved.fixedCosts,'0.00');
  assert.equal(saved.variableCosts,'1000.00');
  const report = helpers.monthlyReport(saved);
  assert.equal(report.outflows,1000);
  assert.equal(helpers.groupReportNotes(report.notes).length,2);
});

test('income split supports emoluments and extra income and correct deletion', () => {
  const income = {...record,recordType:'income'};
  const parts = rows(); parts[0].category='Stipendio'; parts[1].category='Entrate aggiuntive';
  let state = apply(fresh(),parts,income).state;
  assert.equal(state.income,'200.00');
  assert.equal(state.additionalIncome,'800.00');
  assert.equal(helpers.monthlyReport(state).inflows,1000);
  state = helpers.removeDetailedEntriesFromState(state,n => n.id==='part-b');
  assert.equal(state.income,'200.00');
  assert.equal(state.additionalIncome,'0.00');
  assert.equal(helpers.availableBankMovements([income],state.notes)[0].amount,800);
  const extraOnly = parts.map(p => ({...p,category:'Entrate aggiuntive'}));
  state = apply(state,extraOnly,income).state;
  assert.equal(state.income,'0.00');
  assert.equal(state.additionalIncome,'1000.00');
});

test('partial allocations and decimal amounts never round above original', () => {
  const tiny = {...record,amount:0.3};
  const parts = rows(); parts[0].amount='0.10'; parts[1].amount='0.20';
  const state = apply(fresh(),parts,tiny).state;
  assert.equal(helpers.availableBankMovements([tiny],state.notes).length,0);
  const partial = apply(fresh(),[rows()[0]]).state;
  assert.equal(helpers.availableBankMovements([record],partial.notes)[0].amount,800);
  for (const invalid of [NaN,Infinity,-1,0.001,'1.234','1e2',true]) assert.equal(helpers.bankAmountCents(invalid),null);
  assert.equal(helpers.bankAmountCents('0,10'),10);
});

test('invalid direction, amount, duplicate IDs and foreign currency are blocked', () => {
  for (const update of [{amount:0},{amount:-1},{amount:'200.001'},{label:''},{category:'Stipendio'}]) {
    const parts = rows(); Object.assign(parts[0],update);
    const state = fresh(); assert.equal(apply(state,parts).state,state);
  }
  const duplicated = rows(); duplicated[1].id=duplicated[0].id;
  assert.notEqual(apply(fresh(),duplicated).error,'');
  assert.notEqual(apply(fresh(),rows(),{...record,currency:'USD'}).error,'');
  const collision = fresh(); collision.notes=[{id:'part-a',category:'Costo Variabile',amount:1}];
  assert.notEqual(apply(collision).error,'');
});

test('stale editor and different month cannot overwrite newer classifications', () => {
  const initial = fresh(); const signature = helpers.bankAllocationSignature(initial.notes,record.id);
  const saved = apply(initial).state;
  assert.equal(helpers.applyBankSplit(saved,record,rows(),signature).state,saved);
  const nextMonth = {...initial,monthName:'Novembre'};
  assert.equal(apply(nextMonth).state,nextMonth);
});

test('JSON save/reload and history preserve part IDs, amounts and remaining balance', () => {
  const saved = apply(fresh(),[rows()[0]]).state;
  const restored = JSON.parse(JSON.stringify({...saved,monthlyHistory:[{...saved,monthlyHistory:undefined,monthDrafts:undefined}],monthDrafts:{'2026-ottobre':{notes:saved.notes}}}));
  assert.equal(restored.notes[0].id,'part-a');
  assert.equal(restored.monthlyHistory[0].notes[0].bankOriginalAmount,1000);
  assert.equal(restored.monthDrafts['2026-ottobre'].notes[0].amount,200);
  assert.equal(helpers.availableBankMovements([record],restored.notes)[0].amount,800);
  assert.equal(helpers.monthlyReport(restored.monthlyHistory[0]).outflows,200);
});

test('legacy single classification can be split while unrelated manual entries survive', () => {
  const state = fresh();
  state.notes=[{id:'old',bankTransactionId:record.id,category:'Costo Variabile',amount:1000,label:'Old'}, {id:'manual',category:'Costo Fisso',amount:7,label:'Other'}];
  state.variableCosts='1000.00'; state.fixedCosts='7.00';
  const saved = apply(state).state;
  assert.equal(saved.notes.length,3);
  assert.equal(saved.notes.find(n => n.id==='manual').amount,7);
  assert.equal(saved.variableCosts,'800.00');
  assert.equal(saved.fixedCosts,'207.00');
});

test('bank entry edits are routed through constrained split editor', () => {
  assert.match(source,/if \(entry.bankTransactionId\) \{\s+openBankSplit\(entry.bankTransactionId\);\s+return;/);
  assert.match(source,/note.bankTransactionId === record.id && !note.bankSplitVersion/);
  assert.match(source,/role="dialog" aria-modal="true"/);
  assert.match(source,/if \(event.key === "Escape"\)/);
  assert.match(source,/ReactDOM.createPortal\(/);
});

test('rename follows split immediately for both expense and income movements', () => {
  assert.match(source, />Dividi<\/button>\s*\{!isRenaming[^\n]*>Rinomina<\/button>/);
});

test('ordinary category button assigns only residual and a repeat does not duplicate', () => {
  let state = apply(fresh(),[rows()[0]]).state;
  const partial = helpers.availableBankMovements([record],state.notes)[0];
  const begin = source.indexOf('function classifyBankExpense(');
  const end = source.indexOf('function openBankSplit(',begin);
  const context = {...helpers,state,setState: fn => { state = fn(state); },setEntry: () => {},createEmptyEntry: () => ({}),
    bankMovementMatchesPeriod: () => true, crypto: {randomUUID: () => 'residual-part'}};
  vm.runInNewContext(`${source.slice(begin,end)}\nclassifyBankExpense(${JSON.stringify(partial)}, 'Costo Variabile');classifyBankExpense(${JSON.stringify(partial)}, 'Costo Variabile');`,context);
  assert.equal(state.notes.length,2);
  assert.equal(state.fixedCosts,'200.00');
  assert.equal(state.variableCosts,'800.00');
  assert.equal(state.notes[1].bankOriginalAmount,1000);
});
