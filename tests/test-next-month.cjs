const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('salary-planner-react.html', 'utf8');
const months = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'];
const periodStart = source.indexOf('function nextMonth(');
const periodEnd = source.indexOf('function sortMonthlyHistory', periodStart);
const start = source.indexOf('function startNextMonth(');
const end = source.indexOf('function loadSnapshot', start);

for (const [monthName, year, expectedMonth, expectedYear] of [['Settembre', 2026, 'Ottobre', 2026], ['Dicembre', 2026, 'Gennaio', 2027]]) {
  test(`next month resets monthly inputs and preserves saved ${monthName} data`, () => {
    let current = {monthName, year, income: 2000, fixedCosts: 600, variableCosts: 90,
      emergencyFundAllocation: 50, investedCapital: 100, flexibleCashFunds: 30,
      decemberBonusNet: 500, emergencyFundTarget: 6000,
      notes: [{category: 'Costo Fisso', amount: 600, bankTransactionId: 'a'}], monthlyHistory: []};
    const before = structuredClone(current);
    let entryCleared = false;
    let renameCleared = false;
    const context = {months, state: current, editingMonthId: 'old',
      buildSnapshot: () => structuredClone(current),
      persistMonthSnapshot: snapshot => {current = {...current, monthlyHistory: [snapshot]};},
      setState: updater => {current = updater(current);}, setEditingMonthId: () => {},
      createEmptyEntry: () => ({}), setEntry: () => {entryCleared = true;},
      setBankRename: value => {renameCleared = value.id === '' && value.value === '';}};
    vm.runInNewContext(`${source.slice(periodStart, periodEnd)}\n${source.slice(start, end)}\nstartNextMonth()`, context);
    assert.equal(current.monthName, expectedMonth);
    assert.equal(current.year, expectedYear);
    for (const field of ['income', 'fixedCosts', 'variableCosts', 'emergencyFundAllocation', 'investedCapital', 'flexibleCashFunds', 'decemberBonusNet']) assert.equal(Number(current[field]), 0);
    assert.equal(current.notes.length, 0);
    assert.deepEqual(current.monthlyHistory[0], before);
    assert.equal(current.emergencyFundTarget, 6000);
    assert.ok(entryCleared && renameCleared);
  });
}
