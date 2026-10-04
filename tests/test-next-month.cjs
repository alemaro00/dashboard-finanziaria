const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('salary-planner-react.html', 'utf8');
const months = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'];
const periodStart = source.indexOf('function nextMonth(');
const periodEnd = source.indexOf('function sortMonthlyHistory', periodStart);
const helperStart = source.indexOf('function removeDetailedEntriesFromState(');
const helperEnd = source.indexOf('function mergeValueMaps', helperStart);
const helpers = vm.runInNewContext(`${source.slice(helperStart, helperEnd)}\n({switchMonthlyPeriod, monthPeriodKey, repairMonthlyRecord, bankMovementMatchesPeriod})`, {months, normalizeNote: note => ({...note}), roundMoney: value => Math.round((Number(value) || 0) * 100) / 100});
const start = source.indexOf('function startNextMonth(');
const end = source.indexOf('function loadSnapshot', start);

for (const [monthName, year, expectedMonth, expectedYear] of [['Settembre', 2026, 'Ottobre', 2026], ['Dicembre', 2026, 'Gennaio', 2027]]) {
  test(`next month resets monthly inputs and preserves saved ${monthName} data`, () => {
    let current = {monthName, year, income: 2000, additionalIncome: 150, fixedCosts: 600, variableCosts: 90,
      emergencyFundAllocation: 50, investedCapital: 100, flexibleCashFunds: 30,
      decemberBonusNet: 500, emergencyFundTarget: 6000,
      notes: [{category: 'Costo Fisso', amount: 600, bankTransactionId: 'a', transactionDate:'2026-09-01'}], monthlyHistory: []};
    const before = structuredClone(current);
    let entryCleared = false;
    let renameCleared = false;
    const context = {months, state: current, editingMonthId: 'old',
      buildSnapshot: () => structuredClone(current),
      persistMonthSnapshot: snapshot => {current = {...current, monthlyHistory: [snapshot]};},
      setState: updater => {current = updater(current);}, setEditingMonthId: () => {},
      createEmptyEntry: () => ({}), setEntry: () => {entryCleared = true;},
      navigateMonth: (month, year) => {current = helpers.switchMonthlyPeriod(current, month, year, {}); entryCleared = true; renameCleared = true;},
      setBankRename: value => {renameCleared = value.id === '' && value.value === '';}};
    vm.runInNewContext(`${source.slice(periodStart, periodEnd)}\n${source.slice(start, end)}\nstartNextMonth()`, context);
    assert.equal(current.monthName, expectedMonth);
    assert.equal(current.year, expectedYear);
    for (const field of ['income', 'additionalIncome', 'fixedCosts', 'variableCosts', 'emergencyFundAllocation', 'investedCapital', 'flexibleCashFunds', 'decemberBonusNet']) assert.equal(Number(current[field]), 0);
    assert.equal(current.notes.length, 0);
    assert.deepEqual(current.monthlyHistory[0], before);
    assert.equal(current.emergencyFundTarget, 6000);
    assert.ok(entryCleared && renameCleared);
  });
}


test('changing months preserves unsaved classifications, inputs and entry drafts through restart', () => {
  const original = {monthName:'Settembre',year:2026,income:'1500.53',additionalIncome:'45.92',fixedCosts:'23.04',variableCosts:'10.12',notes:[{id:'bank-a',bankTransactionId:'a',transactionDate:'2026-09-01',category:'Costo Fisso',amount:23.04}],monthlyHistory:[],emergencyFundTarget:6000};
  let next = helpers.switchMonthlyPeriod(original,'Ottobre',2026,{label:'Unfinished',amount:'7.93'});
  assert.equal(next.notes.length,0);
  assert.equal(Number(next.income),0);
  assert.equal(next.monthlyHistory.length,0);
  next = {...next,variableCosts:'82.45',notes:[{id:'manual',category:'Costo Variabile',amount:82.45}]};
  next = JSON.parse(JSON.stringify(next));
  let restored = helpers.switchMonthlyPeriod(next,'Settembre',2026,{});
  assert.equal(restored.income,'1500.53');
  assert.equal(restored.additionalIncome,'45.92');
  assert.equal(restored.notes[0].bankTransactionId,'a');
  assert.equal(restored.monthDrafts['2026-settembre'].entry.label,'Unfinished');
  restored = helpers.switchMonthlyPeriod(restored,'Ottobre',2026,{});
  assert.equal(restored.variableCosts,'82.45');
  assert.equal(restored.notes[0].id,'manual');
  assert.equal(original.monthDrafts,undefined);
});

test('saved destination restores only its own data and never carries notes from another month', () => {
  const current = {monthName:'Settembre',year:2026,income:900,notes:[{id:'old'}],monthlyHistory:[{id:'2026-ottobre',monthName:'Ottobre',year:2026,baseIncome:2000,additionalIncome:50,investmentAllocation:100,flexibleCashAllocation:20,notes:[{id:'saved'}]}]};
  const next = helpers.switchMonthlyPeriod(current,'Ottobre',2026,{});
  assert.equal(next.income,2000);
  assert.equal(next.additionalIncome,50);
  assert.equal(next.investedCapital,100);
  assert.equal(next.notes.length,1);
  assert.equal(next.notes[0].id,'saved');
  const empty = helpers.switchMonthlyPeriod(next,'Ottobre',2027,{});
  assert.equal(empty.notes.length,0);
  assert.equal(Number(empty.additionalIncome),0);
});

test('latest draft takes precedence over older saved history', () => {
  const current = {monthName:'Novembre',year:2026,notes:[],monthlyHistory:[{monthName:'Ottobre',year:2026,baseIncome:100,notes:[{id:'old'}]}],monthDrafts:{'2026-ottobre':{income:'200.12',notes:[]}}};
  const next = helpers.switchMonthlyPeriod(current,'Ottobre',2026,{});
  assert.equal(next.income,'200.12');
  assert.equal(next.notes.length,0);
});


test('foreign bank movements are removed from August totals, preserved for recovery, and correction is idempotent', () => {
  const record = {monthName:'Agosto',year:2026,income:1500,additionalIncome:20,fixedCosts:130,variableCosts:75,notes:[
    {id:'september',bankTransactionId:'s',transactionDate:'2026-09-03',category:'Costo Fisso',amount:30},
    {id:'last-year',bankTransactionId:'y',transactionDate:'2025-08-01',category:'Costo Variabile',amount:25},
    {id:'salary',bankTransactionId:'salary',transactionDate:'2026-09-28',category:'Stipendio',amount:1500},
    {id:'august',bankTransactionId:'a',transactionDate:'2026-08-05',category:'Costo Variabile',amount:50},
    {id:'manual',category:'Costo Fisso',amount:100}
  ]};
  const repaired = helpers.repairMonthlyRecord(record);
  assert.equal(repaired.fixedCosts,'100.00');
  assert.equal(repaired.variableCosts,'50.00');
  assert.equal(repaired.income,'0.00');
  assert.deepEqual(Array.from(repaired.notes,n=>n.id),['august','manual']);
  assert.equal(repaired.excludedBankNotes.length,3);
  assert.equal(helpers.repairMonthlyRecord(repaired),repaired);
  assert.equal(record.notes.length,5);
});

test('repairing saved history recalculates cashflow and net worth without double-counting extra income', () => {
  const repaired = helpers.repairMonthlyRecord({monthName:'Agosto',year:2026,baseIncome:1000,income:1100,additionalIncome:100,fixedCosts:50,variableCosts:10,emergencyFundAllocation:20,notes:[{id:'wrong',bankTransactionId:'w',transactionDate:'2026-09-01',category:'Costo Fisso',amount:50}]},true);
  assert.equal(repaired.baseIncome,1000);
  assert.equal(repaired.income,1100);
  assert.equal(repaired.freeCash,1090);
  assert.equal(repaired.currentNetWorth,1070);
});

test('bank dates must match both year and month; missing dates fail closed', () => {
  const period = {monthName:'Agosto',year:2026};
  assert.equal(helpers.bankMovementMatchesPeriod({date:'2026-08-01'},period),true);
  for(const date of ['2026-09-01','2025-08-01','', 'invalid']) assert.equal(helpers.bankMovementMatchesPeriod({date},period),false);
});
