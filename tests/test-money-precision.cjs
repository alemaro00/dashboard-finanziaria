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

test('risk amounts round to two decimals and show the euro symbol rather than EUR', () => {
  assert.match(helpers.money(0.06273710287923506), /^0,06\s*€$/);
  assert.match(helpers.money(0.0787186947975259), /^0,08\s*€$/);
  assert.match(helpers.money(12), /^12,00\s*€$/);
});

test('IBKR closing prices and quantities display exactly six decimals without changing other precision', () => {
  const begin = source.indexOf('function precise(');
  const end = source.indexOf('\n\n      function numberOrFallback', begin);
  const precise = vm.runInNewContext(`${source.slice(begin, end)}\nprecise`);
  assert.equal(precise(90.58, 6, 6), '90,580000');
  assert.equal(precise(0.0013, 6, 6), '0,001300');
  assert.equal(precise(0.12345678, 6, 6), '0,123457');
  assert.equal(precise(90.58, 6), '90,58');
  assert.match(source, /precise\(position\.closingPrice, 6, 6\)/);
  assert.equal((source.match(/precise\(position\.quantity, 6, 6\)/g) || []).length, 2);
});

test('bank-linked detailed entries preserve original identity and exact amount', () => {
  assert.match(source, /originalBankDescription: expense\.description/);
  assert.match(source, /readOnly=\{Boolean\(entry\.bankTransactionId\)\}/);
  assert.match(source, /Movimento originale: \{entry\.originalBankDescription\}/);
  assert.match(source, /openBankSplit\(entry\.bankTransactionId\)/);
  assert.match(source, /originalBankDescription: record\.description/);
  assert.match(source, /bankOriginalAmount: \(record\.originalAmount \?\? record\.amount\)/);
});

test('all requested monthly money inputs accept nine integer digits and cents', () => {
  for (const field of ['emergencyFundAllocation']) {
    const pattern = new RegExp(`max="999999999\\.99" step="0\\.01" value=\\{state\\.${field}\\}`);
    assert.match(source, pattern);
  }
});
