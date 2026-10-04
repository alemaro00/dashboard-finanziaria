const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const source = fs.readFileSync('salary-planner-react.html', 'utf8');

test('beta exposes only the two authorized collapsible sections', () => {
  assert.match(source, /href="#finance-section"[\s\S]*?>01<[\s\S]*?Gestione delle finanze/);
  assert.match(source, /href="#wealth-section"[\s\S]*?>02<[\s\S]*?Wealth management/);
  assert.match(source, /Dashboard finanziaria <span className="beta-badge">Beta<\/span>/);
  assert.doesNotMatch(source, /salary-section|Stima stipendio netto da RAL/);
  assert.doesNotMatch(source, /research-section|Laboratorio strategie/);
});

test('beta preserves the original complete-dashboard color system', () => {
  assert.match(source, /--accent:#d7b46a/);
  assert.match(source, /\.macro-finance\{--macro-accent:#d7b46a/);
  assert.match(source, /\.macro-wealth\{--macro-accent:#a482ef/);
  assert.match(source, /border:1px solid #c0a25e/);
  assert.match(source, /grid-template-columns:repeat\(2,1fr\)/);
  assert.doesNotMatch(source, /macro-salary|macro-research/);
});

test('salary-category cashflow remains independent from the removed salary estimator', () => {
  assert.match(source, /value: "Stipendio", label: "Stipendio"/);
  assert.doesNotMatch(source, /calculateIrpef|salaryEstimate|grossSalary/);
});
