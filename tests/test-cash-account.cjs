const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('salary-planner-react.html','utf8');
const part=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)));
const {cashAccountBalance,summarizeNotes}=vm.runInNewContext([
 part('function cashAccountBalance(', 'function readableBankAccountCount('),
 part('function monthPeriodKey(', 'function repairMonthlyRecord('),
 part('function summarizeNotes(', 'function upsertDetailedIncome('),
 '({cashAccountBalance,summarizeNotes})'
].join('\n'),{months:['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre'],normalizeNote:n=>n,roundMoney:v=>Math.round((Number(v)||0)*100)/100});
const note=(id,category,amount)=>({id,category,amount,accountId:'cash'});
test('manual incomes, expenses, investments and disinvestments adjust cash with cents',()=>{
 const state={monthName:'Ottobre',year:2026,cashOpeningBalance:100,notes:[note('1','Stipendio',50.10),note('2','Entrate aggiuntive',10.20),note('3','Costo Fisso',20.10),note('4','Costo Variabile',5.20),note('5','Investimento',30),note('6','Disinvestimento',7.30)]};
 assert.equal(cashAccountBalance(state),112.30);
 assert.equal(cashAccountBalance({...state,notes:state.notes.filter(n=>n.id!=='4')}),117.50);
});
test('withdrawal credits cash once, never counts as personal income or expense',()=>{
 const withdrawal={...note('bank-x','Prelievo cash',50),bankTransactionId:'x',transactionDate:'2026-10-02'};
 const state={monthName:'Ottobre',year:2026,cashOpeningBalance:100,notes:[withdrawal,withdrawal]};
 assert.equal(cashAccountBalance(state),150);
 assert.equal(summarizeNotes(state.notes).fixedCosts,0);
 assert.equal(summarizeNotes(state.notes).salary,0);
 assert.equal(cashAccountBalance({...state,notes:[]}),100);
});
test('drafts override saved months and current notes override drafts across restart',()=>{
 const state={monthName:'Ottobre',year:2026,cashOpeningBalance:100,notes:[note('oct','Costo Variabile',20)],monthlyHistory:[{monthName:'Settembre',year:2026,notes:[note('sep','Costo Variabile',10)]},{monthName:'Ottobre',year:2026,notes:[note('oct','Costo Variabile',99)]},{monthName:'Novembre',year:2026,notes:[note('future','Costo Variabile',100)]}],monthDrafts:{'2026-settembre':{notes:[note('sep','Costo Variabile',15)]},'2026-ottobre':{notes:[note('oct','Costo Variabile',50)]}}};
 assert.equal(cashAccountBalance(JSON.parse(JSON.stringify(state))),65);
});
test('legacy manual entries and ordinary bank costs do not silently change cash',()=>{
 assert.equal(cashAccountBalance({monthName:'Ottobre',year:2026,cashOpeningBalance:100,notes:[{id:'legacy',category:'Costo Variabile',amount:20},{id:'bank',bankTransactionId:'b',category:'Costo Fisso',amount:30}]}),100);
});
