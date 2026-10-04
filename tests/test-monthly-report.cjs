const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('salary-planner-react.html', 'utf8');
const extract = (start,end) => source.slice(source.indexOf(start), source.indexOf(end,source.indexOf(start)));
const {monthlyReport,aggregateMonthlyReports} = vm.runInNewContext([
 extract('function summarizeNotes(', 'function upsertDetailedIncome('),
 extract('function monthlyCashflow(', 'function availableBankMovements('),
 extract('function bankMovementMatchesPeriod(', 'function repairMonthlyRecord('),
 '({monthlyReport,aggregateMonthlyReports})'
].join('\n'), {normalizeNote:note=>({...note}),roundMoney:value=>Math.round((Number(value)||0)*100)/100,months:['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']});
const saved={monthName:'Settembre',year:2026,freeCash:999999,investmentAllocation:888888,emergencyFundAllocation:100,notes:[
 ['Stipendio',1000.15],['Entrate aggiuntive',30.12],['Costo Fisso',200.23],['Costo Variabile',100.14],['Investimento',300.21],['Disinvestimento',50.34]
].map(([category,amount])=>({category,amount}))};
test('saved report recomputes six categories and net flows rather than old targets',()=>{
 const report=monthlyReport(saved);
 assert.equal(report.inflows,1080.61);
 assert.equal(report.outflows,600.58);
 assert.equal(report.net,480.03);
 assert.equal(report.netInvestments,249.87);
 assert.equal(report.notes.length,6);
});
test('report excludes foreign-month bank entries without altering saved data',()=>{
 const record={...saved,notes:[...saved.notes,{category:'Stipendio',amount:500,bankTransactionId:'other-month',transactionDate:'2026-08-31'}]};
 assert.equal(monthlyReport(record).net,480.03);
 assert.equal(record.notes.length,7);
});
test('overall totals sum months with cent precision including net disinvestment',()=>{
 const other={monthName:'Ottobre',year:2026,notes:[{category:'Disinvestimento',amount:20.11}]};
 const total=aggregateMonthlyReports([saved,other]);
 assert.equal(total.inflows,1100.72);
 assert.equal(total.outflows,600.58);
 assert.equal(total.net,500.14);
 assert.equal(total.netInvestments,229.76);
 assert.equal(total.emergencyFund,100);
 assert.equal(aggregateMonthlyReports([{notes:[],emergencyFundAllocation:0.10},{notes:[],emergencyFundAllocation:0.20}]).emergencyFund,0.30);
 assert.equal(aggregateMonthlyReports([]).net,0);
});

test('negative emergency allocations reduce saved totals and survive serialization',()=>{
 const records=JSON.parse(JSON.stringify([{notes:[],emergencyFundAllocation:100.25},{notes:[],emergencyFundAllocation:-30.15}]));
 const total=aggregateMonthlyReports(records);
 assert.equal(total.emergencyFund,70.10);
 assert.equal(total.net,0);
});
