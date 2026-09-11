const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const ctx = {Date, formatDate: value => value};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('copilot/js/body-evolution.js', 'utf8'), ctx);
const render = (points, metric = 'weight', latest_date = points.at(-1)?.date) => ctx.renderBodyEvolution({points, latest_date}, metric, new Date(2026, 8, 9));
test('0/1/2/many observations have distinct honest explanations and no missing zeros', () => {
    assert.match(render([]), /Sem registros de peso/);
    assert.doesNotMatch(render([{date:'2026-09-01',value:null}]), /0 kg|<svg/);
    const one = render([{date:'2026-09-01',value:70}]);
    assert.match(one, /Ponto inicial/);
    assert.doesNotMatch(one, /polyline/);
    assert.match(one, /Variação<\/small><strong>—/);
    const two = render([{date:'2026-09-01',value:70},{date:'2026-09-09',value:70}]);
    assert.match(two, /Sem alteração/);
    assert.match(two, /ainda não indica uma tendência consolidada/);
    const many = render(Array.from({length:45}, (_, i) => ({date:`2026-08-${String(i%28+1).padStart(2,'0')}`,value:70+i})).sort((a,b)=>a.date.localeCompare(b.date)));
    assert.match(many, /45 registros no período/);
});
test('fat is pp; every supported metric has the correct unit', () => {
    const points = [{date:'2026-09-01',value:20},{date:'2026-09-09',value:18.5}];
    assert.match(render(points,'body_fat'), /−1,5 p.p./);
    for (const metric of ['waist','chest','arm','thigh']) assert.match(render(points,metric), /18,5 cm/);
    assert.match(render(points,'muscle_mass'), /18,5 kg/);
});
test('horizontal spacing uses calendar dates and duplicate dates stay finite', () => {
    const html = render([{date:'2026-09-01',value:70},{date:'2026-09-02',value:71},{date:'2026-09-09',value:72}]);
    const xs = [...html.matchAll(/<circle cx="([^"]+)/g)].map(match=>Number(match[1]));
    assert.equal((xs[1]-xs[0])/(xs[2]-xs[0]), 1/8);
    assert.doesNotMatch(render([{date:'2026-09-01',value:70},{date:'2026-09-01',value:71}]), /NaN|Infinity/);
});
test('staleness uses latest available date for selected metric, not end of chosen period', () => {
    assert.match(render([], 'weight', '2026-08-01'), /há 39 dias/);
    assert.doesNotMatch(render([{date:'2026-01-01',value:70}], 'weight', '2026-09-01'), /há .* dias/);
});
