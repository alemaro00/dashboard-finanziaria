const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('salary-planner-react.html','utf8');
const start = source.indexOf('function readableBankAccountCount(');
const end = source.indexOf('function availableBankMovements(',start);
const count = vm.runInNewContext(`${source.slice(start,end)}\nreadableBankAccountCount`);
const snapshot = {configured:true,authorizationRequired:false,lastSync:'2026-10-04T12:00:00Z',accounts:[{id:'eur'},{id:'usd'},{id:'eur'},{id:'blocked',readable:false},{}]};
test('counts distinct readable accounts, not banks or duplicate identifiers',()=>assert.equal(count(snapshot),2));
test('deselected accounts are not counted as actively readable',()=>assert.equal(count({...snapshot,accounts:[{id:'a',selected:false},{id:'b',selected:true}]}),1));
test('does not count configured accounts without successful access or after an error',()=>{
 for(const data of [undefined,{...snapshot,configured:false},{...snapshot,lastSync:null},{...snapshot,authorizationRequired:true},{...snapshot,error:'Access expired'}]) assert.equal(count(data),0);
});
