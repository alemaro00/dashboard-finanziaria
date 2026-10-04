const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('salary-planner-react.html','utf8');
const start = source.indexOf('function monthlyCashflow(');
const end = source.indexOf('function availableBankMovements',start);
const monthlyCashflow = vm.runInNewContext(`${source.slice(start,end)}\nmonthlyCashflow`, {roundMoney:value=>Math.round((Number(value)||0)*100)/100});
test('all six categories determine cashflow independently of stale manual totals',()=>{
 const inputs={monthName:'Dicembre',income:99999,additionalIncome:99999,fixedCosts:99999,variableCosts:99999,decemberBonusNet:99999,investedCapital:99999,flexibleCashFunds:500,emergencyFundAllocation:100};
 const details={salary:1000.15,additionalIncome:30.12,fixedCosts:200.23,variableCosts:100.14,investments:300.21,disinvestments:50.34};
 const result=monthlyCashflow(inputs,details);
 assert.equal(result.inflows,1080.61);
 assert.equal(result.outflows,600.58);
 assert.equal(result.net,480.03);
 assert.equal(monthlyCashflow(inputs,{...details,investments:0,disinvestments:0}).net,729.90);
 assert.equal(monthlyCashflow(inputs,{...details,fixedCosts:0}).outflows,400.35);
 assert.equal(monthlyCashflow(inputs,{...details,variableCosts:0}).outflows,500.44);
 assert.equal(monthlyCashflow(inputs,{...details,salary:0}).inflows,80.46);
 assert.equal(monthlyCashflow(inputs,{...details,additionalIncome:0}).inflows,1050.49);
});
test('empty detailed entries give zero even with old manual values and bonuses',()=>{
 const result=monthlyCashflow({income:100,additionalIncome:20,decemberBonusNet:100,fixedCosts:200,variableCosts:30},{salary:0,additionalIncome:0,fixedCosts:0,variableCosts:0,investments:0,disinvestments:0});
 assert.equal(result.inflows,0);
 assert.equal(result.outflows,0);
 assert.equal(result.net,0);
});
test('expenses exceeding detailed income produce a negative balance',()=>{
 const result=monthlyCashflow({}, {salary:100,additionalIncome:20,fixedCosts:200,variableCosts:0,investments:0,disinvestments:0});
 assert.equal(result.net,-80);
});
