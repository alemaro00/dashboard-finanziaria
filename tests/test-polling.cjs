const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('salary-planner-react.html','utf8').match(/<script id="ibkr-connection-helpers">([\s\S]*?)<\/script>/)[1];
const ctx = {AbortController, setTimeout, clearTimeout, fetch};
vm.createContext(ctx); vm.runInContext(source,ctx);
function harness(fetchImpl, options={}) {
 let state={reachable:false,loading:true,data:null,error:''};
 const poller=ctx.createIbkrPoller({baseUrl:'',mode:'paper',fetchImpl,onState:v=>state=typeof v==='function'?v(state):v,intervalMs:60000,...options});
 return {poller, state:()=>state};
}
test('manual and automatic requests share a pending fetch',async()=>{
 let resolve, calls=0;
 const h=harness(()=>{calls++;return new Promise(r=>resolve=r)});
 const a=h.poller.refresh(),b=h.poller.refresh();
 assert.equal(a,b); assert.equal(calls,1);
 resolve({ok:true,json:async()=>({dataStatus:'synchronizing'})});
 await a; assert.equal(ctx.ibkrDataStatus(h.state()),'synchronizing'); h.poller.stop();
});
test('timeout preserves last snapshot as stale and allows recovery',async()=>{
 let fail=false;
 const h=harness((url,{signal})=>fail?new Promise((r,reject)=>signal.addEventListener('abort',()=>reject(new Error('abort')))) : Promise.resolve({ok:true,json:async()=>({dataStatus:'current'})}),{timeoutMs:10});
 await h.poller.refresh(); assert.equal(ctx.ibkrDataStatus(h.state()),'current');
 fail=true; await h.poller.refresh(); assert.equal(ctx.ibkrDataStatus(h.state()),'stale'); assert.match(h.state().error,/scaduto/);
 fail=false; await h.poller.refresh(); assert.equal(ctx.ibkrDataStatus(h.state()),'current'); h.poller.stop();
});
test('stop aborts pending request and prevents later updates',async()=>{
 let resolve;
 const h=harness(()=>new Promise(r=>resolve=r));
 const p=h.poller.refresh(); const before=h.state(); h.poller.stop();
 resolve({ok:true,json:async()=>({dataStatus:'current'})}); await p; assert.equal(h.state(),before);
});
test('missing status cannot label legacy or malformed snapshot current',async()=>{
 const h=harness(async()=>({ok:true,json:async()=>({status:'connected'})}));
 await h.poller.refresh(); assert.equal(ctx.ibkrDataStatus(h.state()),'disconnected'); h.poller.stop();
});
