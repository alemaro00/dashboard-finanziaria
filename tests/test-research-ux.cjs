const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const source = fs.readFileSync('salary-planner-react.html', 'utf8');

test('strategy laboratory is the fourth distinct dashboard section', () => {
  assert.match(source, /href="#research-section"[\s\S]*?>04<[\s\S]*?Laboratorio strategie/);
  assert.match(source, /macro-section-shell macro-research/);
});

test('strategy laboratory explains the validation path in plain language', () => {
  for (const label of ['Premere un solo pulsante', 'Test automatico insieme', 'Simulare costi', 'Validazione futura']) {
    assert.match(source, new RegExp(label));
  }
  assert.match(source, /Affidabilità futura[\s\S]*?Da calcolare/i);
  assert.match(source, /Non è una previsione di rendimento/);
  assert.match(source, /Nessuna strategia gira continuamente/);
  assert.match(source, /Raccogli dati e prova strategie/);
  assert.doesNotMatch(source, />Metti questa strategia in pausa</);
  assert.match(source, /60% in-sample diagnostico, 20% validation e 20% out-of-sample finale/);
  assert.match(source, /Mostra segnali e decisioni di tutti e tre i segmenti/);
});

test('strategy results use full-width cards and responsive metrics', () => {
  assert.match(source, /\.research-grid\{display:grid;grid-template-columns:1fr/);
  assert.match(source, /@media \(max-width:700px\)[\s\S]*?\.research-steps,\.research-metrics\{grid-template-columns:1fr\}/);
});
