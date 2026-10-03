const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('salary-planner-react.html', 'utf8');
const begin = source.indexOf('function roundMoney');
const end = source.indexOf('\n\n      function detailGapTone', begin);
const helpers = vm.runInNewContext(`${source.slice(begin, end)}\n({roundMoney, money})`);

test('monthly amounts retain exact cents and always display two decimals', () => {
  assert.equal(helpers.roundMoney(0.1 + 0.2), 0.3);
  assert.match(helpers.money(164.93), /164,93/);
  assert.match(helpers.money(9), /9,00/);
});

test('bank-linked detailed entries preserve original identity and exact amount', () => {
  assert.match(source, /originalBankDescription: expense\.description/);
  assert.match(source, /readOnly=\{Boolean\(entry\.bankTransactionId\)\}/);
  assert.match(source, /Movimento originale: \{entry\.originalBankDescription\}/);
  assert.match(source, /bankingControl\("rename", \{ recordId: entry\.bankTransactionId/);
});

test('all requested monthly money inputs accept nine integer digits and cents', () => {
  for (const field of ['income', 'fixedCosts', 'variableCosts', 'emergencyFundAllocation', 'investedCapital', 'flexibleCashFunds']) {
    const pattern = new RegExp(`max="999999999\\.99" step="0\\.01" value=\\{state\\.${field}\\}`);
    assert.match(source, pattern);
  }
});
