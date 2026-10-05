const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../salary-planner-react.html'), 'utf8');
const begin = source.indexOf('const queueStateSave =');
const end = source.indexOf('\n        const [backupPassword', begin);
function queue(fetch) {
  const context = {fetch, AbortController, setTimeout, clearTimeout,
    persistenceQueue: {current: Promise.resolve()}, ibkrBridgeBaseUrl: 'http://localhost'};
  return vm.runInNewContext(source.slice(begin, end) + '\nqueueStateSave', context);
}
test('an older pending autosave finishes before the final native save', async () => {
  const bodies = [];
  let finishFirst;
  const save = queue(async (_url, options) => {
    bodies.push(JSON.parse(options.body));
    if (bodies.length === 1) await new Promise(resolve => { finishFirst = resolve; });
    return {ok: true};
  });
  const first = save({draft: 'older'});
  const final = save({draft: 'latest'});
  await new Promise(setImmediate);
  assert.deepEqual(bodies, [{draft: 'older'}]);
  finishFirst();
  await Promise.all([first, final]);
  assert.deepEqual(bodies, [{draft: 'older'}, {draft: 'latest'}]);
});
test('a failed save rejects and a later retry can still save', async () => {
  let calls = 0;
  const save = queue(async () => ({ok: ++calls > 1}));
  await assert.rejects(save({draft: 'first'}), /Salvataggio non riuscito/);
  await save({draft: 'retry'});
  assert.equal(calls, 2);
});
