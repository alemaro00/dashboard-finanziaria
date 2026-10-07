const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('salary-planner-react.html', 'utf8');
const helper = source.slice(source.indexOf('function infoTipPlacement('), source.indexOf('function InfoTip('));
const context = vm.createContext({});
vm.runInContext(helper, context);
const place = context.infoTipPlacement;
const anchor = (left, top) => ({left, top, bottom:top+22, width:22});
test('info tips choose above at bottom and below at top', () => {
  assert.ok(place(anchor(200, 550), 180, 800, 600).top < 550);
  assert.ok(place(anchor(200, 12), 180, 800, 600).top > 34);
});
test('all edges and long content stay within viewport and scroll', () => {
  for (const [w,h] of [[800,600],[320,240],[200,80]]) {
    for (const a of [anchor(0,0),anchor(w-22,h-22),anchor(w/2,h/2)]) {
      const p = place(a, 1200,w,h);
      assert.ok(p.left>=0 && p.left+p.width<=w);
      assert.ok(p.top>=0 && p.top+Math.min(1200,p.maxHeight)<=h);
      assert.ok(p.maxHeight<1200);
    }
  }
});
test('all info tips use a body portal, scrolling and keyboard dismissal', () => {
  assert.match(source, /ReactDOM\.createPortal\([\s\S]*?document\.body/);
  assert.match(source, /position:fixed;z-index:10000/);
  assert.match(source, /overflow:auto;overscroll-behavior:contain/);
  assert.match(source, /event\.key === "Escape"/);
  assert.match(source, /aria-describedby=\{open \? id : undefined\}/);
  assert.doesNotMatch(source, /\.asset-info \.info-tip-content|\.info-tip:hover \.info-tip-content/);
});
