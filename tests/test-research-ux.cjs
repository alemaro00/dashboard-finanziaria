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

test('both beta sections share the blue visual system', () => {
  assert.match(source, /\.macro-finance,\.macro-wealth\{--macro-accent:#69c8ee/);
  assert.match(source, /grid-template-columns:repeat\(2,1fr\)/);
  assert.doesNotMatch(source, /macro-salary|macro-research/);
});

test('salary-category cashflow remains independent from the removed salary estimator', () => {
  assert.match(source, /value: "Stipendio", label: "Stipendio"/);
  assert.doesNotMatch(source, /calculateIrpef|salaryEstimate|grossSalary/);
});
