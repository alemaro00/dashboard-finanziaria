const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('salary-planner-react.html', 'utf8');
const start = source.indexOf('function upsertDetailedIncome');
const end = source.indexOf('function mergeValueMaps', start);
const {upsertDetailedIncome, availableBankMovements, detailedEntriesForCategory, removeDetailedEntriesFromState, bankMovementAllocation, bankAllocationSignature, applyBankSplit} = vm.runInNewContext(
  `${source.slice(start, end)}\n({upsertDetailedIncome, availableBankMovements, detailedEntriesForCategory, removeDetailedEntriesFromState, bankMovementAllocation, bankAllocationSignature, applyBankSplit})`,
  {roundMoney: value => Math.round(((Number(value) || 0) + Number.EPSILON) * 100) / 100,
    normalizeNote: n => n, months: ['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']}
);

test('salary and extra bank income move to details without duplication and return on removal', () => {
  const records = [{id:'salary',recordType:'income'}, {id:'extra',recordType:'income'}];
  const salary = {id:'bank-salary',bankTransactionId:'salary',category:'Stipendio',amount:2150.93};
  const extra = {id:'bank-extra',bankTransactionId:'extra',category:'Entrate aggiuntive',amount:45.19};
  let state = {income:0,additionalIncome:0,notes:[],fixedCosts:0,variableCosts:0};
  state = upsertDetailedIncome(state, salary);
  state = upsertDetailedIncome(state, salary);
  state = upsertDetailedIncome(state, extra);
  assert.equal(state.income, '2150.93');
  assert.equal(state.additionalIncome, '45.19');
  assert.equal(state.notes.length,2);
  assert.equal(availableBankMovements(records,state.notes).length,0);
  state = upsertDetailedIncome(state, {...salary,category:'Entrate aggiuntive'});
  assert.equal(state.income,'0.00');
  assert.equal(state.additionalIncome,'2196.12');
  state = removeDetailedEntriesFromState(state,n => n.id === 'bank-salary');
  assert.equal(state.additionalIncome,'45.19');
  assert.equal(availableBankMovements(records,state.notes)[0].id,'salary');
});

test('manual income can be renamed, edited and deleted without entering bank movements', () => {
  let state = {income:0,additionalIncome:0,notes:[]};
  state = upsertDetailedIncome(state,{id:'manual',category:'Stipendio',amount:10.45,label:'First'});
  state = upsertDetailedIncome(state,{id:'manual',category:'Stipendio',amount:20.99,label:'Renamed'});
  assert.equal(state.income,'20.99');
  assert.equal(state.notes[0].label,'Renamed');
  state = removeDetailedEntriesFromState(state,() => true);
  assert.equal(state.income,'0.00');
  assert.equal(state.notes.length,0);
  assert.equal(availableBankMovements([],state.notes).length,0);
});

test('category filtering keeps original indices for safe removal', () => {
  const notes = [{category:'Costo Variabile'},{category:'Stipendio'},{category:'Costo Fisso'},{category:'Costo Fisso'}];
  const rows = detailedEntriesForCategory(notes,'Costo Fisso');
  assert.deepEqual(Array.from(rows, row => row.index),[2,3]);
  assert.equal(detailedEntriesForCategory(notes,'Costo Variabile').length,1);
  assert.equal(detailedEntriesForCategory(notes,'Investimento').length,0);
});

test('credit becomes disinvestment and debit investment without changing salary or costs', () => {
  const a = source.indexOf('function classifyBankExpense(');
  const b = source.indexOf('async function saveBankRename(', a);
  for (const recordType of ['income', 'expense']) {
    let state = {monthName:'Settembre',year:2026,income:'100.00',additionalIncome:'20.00',fixedCosts:'30.00',variableCosts:'40.00',notes:[]};
    let category;
    const expectedCategory = recordType === "income" ? "Disinvestimento" : "Investimento";
    const record = {id:'movement',date:'2026-09-01',recordType,currency:'EUR',amount:123.45,description:'Original',customName:'Alias'};
    const context = {state:{monthName:"Settembre",year:2026}, bankMovementMatchesPeriod:(record,period) => record.date === "2026-09-01" && period.monthName === "Settembre", setEntry: fn => { category = fn({}).category; }, createEmptyEntry:()=>({}),
      setState: fn => {state = fn(state);}, normalizeNote: n=>n, upsertDetailedIncome, bankMovementAllocation, bankAllocationSignature, applyBankSplit};
    vm.runInNewContext(`${source.slice(a,b)}\nclassifyBankExpense(${JSON.stringify(record)}, ${JSON.stringify(expectedCategory)})`,context);
    assert.equal(category,expectedCategory);
    assert.equal(state.notes[0].category,expectedCategory);
    assert.equal(state.notes[0].bankRecordType,recordType);
    assert.equal(state.notes[0].label,'Alias');
    assert.equal(state.notes[0].originalBankDescription,'Original');
    assert.equal(state.income,'100.00');
    assert.equal(state.additionalIncome,'20.00');
    assert.equal(state.fixedCosts,'30.00');
    assert.equal(state.variableCosts,'40.00');
    assert.equal(availableBankMovements([record],state.notes).length,0);
    state = removeDetailedEntriesFromState(state,()=>true);
    assert.equal(availableBankMovements([record],state.notes).length,1);
  }
});

test('previous positive investment movements migrate to disinvestments without changing identity or amounts', () => {
  const a = source.indexOf('function normalizeNote(');
  const b = source.indexOf('function summarizeNotes(', a);
  const normalize = vm.runInNewContext(`${source.slice(a,b)}\nnormalizeNote`, {
    normalizeCategory: value => value,
    roundMoney: value => Math.round(Number(value) * 100) / 100
  });
  const note = {id:'bank-a',bankTransactionId:'a',bankRecordType:'income',category:'Investimento',amount:123.45,label:'Alias',originalBankDescription:'Original'};
  const migrated = normalize(note);
  assert.equal(migrated.category,'Disinvestimento');
  assert.equal(migrated.managementSource,'Bancario');
  assert.equal(migrated.currentValue,0);
  assert.equal(migrated.amount,123.45);
  assert.equal(migrated.bankTransactionId,'a');
  assert.equal(migrated.label,'Alias');
  assert.equal(note.category,'Investimento');
});
