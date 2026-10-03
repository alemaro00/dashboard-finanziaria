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
