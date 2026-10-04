const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('salary-planner-react.html', 'utf8');
const begin = source.indexOf('function removeDetailedEntriesFromState');
const end = source.indexOf('\n\n      function mergeValueMaps', begin);
const removeDetailedEntriesFromState = vm.runInNewContext(
  `${source.slice(begin, end)}\nremoveDetailedEntriesFromState`,
  {roundMoney: value => Math.round(((Number(value) || 0) + Number.EPSILON) * 100) / 100}
);

test('removing a linked fixed bank movement reduces the fixed monthly total', () => {
  const state = {
    fixedCosts: 130,
    variableCosts: 70,
    notes: [
      {id: 'bank-a', bankTransactionId: 'a', category: 'Costo Fisso', amount: 30},
      {id: 'manual', category: 'Costo Fisso', amount: 100},
      {id: 'bank-b', bankTransactionId: 'b', category: 'Costo Variabile', amount: 70}
    ]
  };
  const next = removeDetailedEntriesFromState(state, (_note, index) => index === 0);
  assert.equal(next.fixedCosts, '100.00');
  assert.equal(next.variableCosts, '70.00');
  assert.equal(next.notes.map(note => note.id).join(','), 'manual,bank-b');
});

test('removing a manual detail does not change the monthly macro totals', () => {
  const state = {
    fixedCosts: 130,
    variableCosts: 70,
    notes: [
      {id: 'bank-a', bankTransactionId: 'a', category: 'Costo Fisso', amount: 30},
      {id: 'manual', category: 'Costo Fisso', amount: 100}
    ]
  };
  const next = removeDetailedEntriesFromState(state, note => note.id === 'manual');
  assert.equal(next.fixedCosts, '130.00');
  assert.equal(next.variableCosts, '70.00');
});

test('reset removes every linked bank contribution from both monthly totals', () => {
  const state = {
    fixedCosts: 45,
    variableCosts: 80,
    notes: [
      {bankTransactionId: 'a', category: 'Costo Fisso', amount: 45},
      {bankTransactionId: 'b', category: 'Costo Variabile', amount: 80}
    ]
  };
  const next = removeDetailedEntriesFromState(state, () => true);
  assert.equal(next.fixedCosts, '0.00');
  assert.equal(next.variableCosts, '0.00');
  assert.equal(next.notes.length, 0);
});

const availableBegin = source.indexOf('function availableBankMovements');
const availableEnd = source.indexOf('\n\n      function removeDetailedEntriesFromState', availableBegin);
const availableBankMovements = vm.runInNewContext(
  `${source.slice(availableBegin, availableEnd)}\navailableBankMovements`
);

test('classified bank expenses move out of the window and return on removal', () => {
  const records = [
    {id: 'fixed', recordType: 'expense'},
    {id: 'variable', recordType: 'expense'},
    {id: 'income', recordType: 'income'}
  ];
  const state = {fixedCosts: 10, variableCosts: 20, notes: [
    {id: 'bank-fixed', bankTransactionId: 'fixed', category: 'Costo Fisso', amount: 10},
    {id: 'bank-variable', bankTransactionId: 'variable', category: 'Costo Variabile', amount: 20},
    {id: 'manual', category: 'Costo Variabile', amount: 5}
  ]};
  const ids = current => Array.from(availableBankMovements(records, current.notes), r => r.id);
  assert.deepEqual(ids(state), ['income']);
  const afterFixed = removeDetailedEntriesFromState(state, n => n.id === 'bank-fixed');
  assert.deepEqual(ids(afterFixed), ['fixed', 'income']);
  assert.equal(afterFixed.fixedCosts, '0.00');
  const afterVariable = removeDetailedEntriesFromState(afterFixed, n => n.id === 'bank-variable');
  assert.deepEqual(ids(afterVariable), ['fixed', 'variable', 'income']);
  assert.equal(afterVariable.variableCosts, '0.00');
  const afterManual = removeDetailedEntriesFromState(afterVariable, n => n.id === 'manual');
  assert.equal(afterManual.notes.length, 0);
  assert.deepEqual(ids(afterManual), ['fixed', 'variable', 'income']);
  assert.equal(records.length, 3);
});
