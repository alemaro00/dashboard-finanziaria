const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('salary-planner-react.html','utf8');
const start=source.indexOf('function groupReportNotes(');
const end=source.indexOf('function aggregateMonthlyReports(',start);
const group=vm.runInNewContext(`${source.slice(start,end)}\ngroupReportNotes`,{roundMoney:v=>Math.round((Number(v)||0)*100)/100});
test('repeated names aggregate within their category with exact cents and retain source records',()=>{
 const notes=[{id:'1',bankTransactionId:'a',category:'Costo Variabile',label:'Spesa',amount:6.76},{id:'2',bankTransactionId:'b',category:'Costo Variabile',label:' spesa ',amount:12.06},{id:'3',category:'Costo Fisso',label:'Spesa',amount:3.10}];
 const original=JSON.stringify(notes);
 const grouped=group(notes);
 assert.equal(grouped.length,2);
 assert.equal(grouped[0].amount,18.82);
 assert.equal(grouped[0].count,2);
 assert.equal(grouped[1].amount,3.10);
 assert.equal(JSON.stringify(notes),original);
 assert.equal(notes[1].bankTransactionId,'b');
});
test('different names stay distinct and empty reports stay empty',()=>{
 assert.equal(group([{category:'Costo Variabile',label:'Spesa',amount:1},{category:'Costo Variabile',label:'Spesa casa',amount:2}]).length,2);
 assert.equal(group([]).length,0);
});
test('monthly aggregated movements are sorted by amount descending with a stable Italian label tie-break',()=>{
 const grouped=group([
  {category:'Costo Variabile',label:'Ticket metro',amount:2.20},
  {category:'Costo Variabile',label:'Lenti a contatto',amount:38.46},
  {category:'Costo Variabile',label:'Flixbus',amount:23.98},
  {category:'Costo Variabile',label:'Bonus',amount:7},
  {category:'Costo Fisso',label:'Abbonamento',amount:38.46}
 ]);
 assert.deepEqual(Array.from(grouped, item=>item.amount),[38.46,38.46,23.98,7,2.20]);
 assert.deepEqual(Array.from(grouped.slice(0,2), item=>item.label),['Abbonamento','Lenti a contatto']);
});
