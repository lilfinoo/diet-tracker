const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../copilot/script.js'), 'utf8');

// Execute the production functions with a minimal DOM and controllable network.
function harness() {
    const elements = new Map();
    const element = id => {
        if (!elements.has(id)) elements.set(id, {
            value: '', innerHTML: '', textContent: '', disabled: false,
            classList: { contains: () => false, add() {}, remove() {} },
            removeAttribute() {}, setAttribute() {},
            reset() { this.value = ''; }, insertAdjacentHTML(_, html) { this.innerHTML += html; },
        });
        return elements.get(id);
    };
    const calls = [];
    const context = {
        console, URLSearchParams, Date, API_BASE: '/api', currentUser: null,
        measurements: [], measurementHasMore: false, measurementRequestToken: 0,
        measurementSummaryToken: 0, measurementAccountVersion: 0,
        measurementLoading: false, measurementRange: null,
        getElement: element, document: { getElementById: element },
        showGlobalLoading() {}, hideGlobalLoading() {}, showToast() {},
        closeAppModal() {}, closeMeasurementModal() {}, renderGuestPresentation() {},
        escapeHtml: value => String(value ?? ''), formatDate: value => value,
        measurementMetric: () => '', confirm: () => true, setCsrfToken() {},
        showMainScreen() {}, window: {},
        fetch: async (url, options) => { calls.push({url, options}); return context.respond(url, options); },
        respond: () => ({ok: true, json: async () => []}),
    };
    context.window.fetchWithTimeout = (...args) => context.fetch(...args);
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../copilot/js/body-evolution.js"), "utf8"), context);
    for (const name of ['setCurrentUser', 'clearMeasurements', 'loadMeasurements',
        'loadMeasurementSummary', 'renderMeasurementTable',
        'handleMeasurementFormSubmit', 'deleteMeasurement', 'logout']) {
        const start = source.search(new RegExp(`^(?:async )?function ${name}\\(`, 'm'));
        assert.ok(start >= 0, name);
        // Top-level function closing braces are unindented in script.js.
        const end = source.indexOf('\n}', start) + 2;
        vm.runInContext(source.slice(start, end), context);
    }
    context.setCurrentUser({id: 'alice'});
    return {context, element, calls};
}
const response = data => ({ok: true, json: async () => data});
const page = (start, count) => Array.from({length: count}, (_, i) => ({id: start + i, weight: 70, date: '2026-08-10'}));
const summary = change => ({latest_date: '2026-08-08', points: [
    {value: 70 - change, date: '2026-08-01'}, {value: 70, date: '2026-08-08'},
]});

test('refresh replaces the first page; load more retains filters and avoids duplicate clicks', async () => {
    const {context: c, element: el, calls} = harness();
    el('measurementStartDate').value = '2026-08-01';
    el('measurementEndDate').value = '2026-08-31';
    c.respond = () => response(page(1, 20));
    await c.loadMeasurements();
    let resolve;
    c.respond = () => new Promise(r => resolve = r);
    const pending = c.loadMeasurements(true);
    await c.loadMeasurements(true);
    assert.equal(calls.length, 2);
    const url = new URL(calls[1].url, 'https://test.invalid');
    assert.equal(url.searchParams.get('offset'), '20');
    assert.equal(url.searchParams.get('start_date'), '2026-08-01');
    assert.equal(url.searchParams.get('end_date'), '2026-08-31');
    resolve(response(page(21, 2)));
    await pending;
    assert.equal(c.measurements.length, 22);
    assert.equal(c.measurementHasMore, false);
    c.respond = () => response(page(90, 1));
    await c.loadMeasurements();
    assert.equal(c.measurements[0].id, 90);
    assert.equal(c.measurements.length, 1);
    assert.ok(!calls.at(-1).url.includes('offset'));
});

test('changing filters invalidates an older in-flight page', async () => {
    const {context: c, element: el} = harness();
    let resolve;
    c.respond = () => new Promise(r => resolve = r);
    const pending = c.loadMeasurements();
    el('measurementStartDate').value = '2026-08-20';
    c.respond = () => response(page(50, 1));
    await c.loadMeasurements();
    resolve(response(page(1, 20)));
    await pending;
    assert.equal(c.measurements[0].id, 50);
    assert.equal(c.measurements.length, 1);
});

test('logout and account switch discard measurements and delayed list and summary responses', async () => {
    const {context: c, element: el} = harness();
    c.respond = () => response(page(1, 20));
    await c.loadMeasurements();
    const pending = [];
    c.respond = () => new Promise(resolve => pending.push(resolve));
    const requests = [c.loadMeasurements(true), c.loadMeasurementSummary()];
    c.respond = () => response({});
    await c.logout();
    assert.equal(c.measurements.length, 0);
    c.setCurrentUser({id: 'bob'});
    pending[0](response(page(21, 1)));
    pending[1](response(summary(0)));
    await Promise.all(requests);
    assert.equal(c.measurements.length, 0);
    assert.equal(el('measurementTableBody').innerHTML, '');
    assert.equal(el('measurementSummary').innerHTML, '');
    c.respond = () => response(page(100, 1));
    await c.loadMeasurements();
    assert.equal(c.measurements[0].id, 100);
    c.setCurrentUser({id: 'carol'});
    assert.equal(c.measurements.length, 0);
});

test('stable weight is neutral; sparse metrics retain their own dates; missing weight is not zero', async () => {
    const {context: c, element: el} = harness();
    c.respond = () => response(summary(0));
    await c.loadMeasurementSummary();
    const html = el('measurementSummary').innerHTML;
    assert.match(html, /Sem alteração/);
    assert.doesNotMatch(html, /delta--down|delta--up|arrow-down|arrow-up/);
    assert.match(html, /2026-08-08/);

    const sparse = summary(0);
    sparse.points = [];
    c.respond = () => response(sparse);
    await c.loadMeasurementSummary();
    assert.match(el('measurementSummary').innerHTML, /Sem registros de peso/);
    assert.doesNotMatch(el('measurementSummary').innerHTML, /Sem alteração/);
});

test('create, edit and delete refresh first page and summary', async () => {
    const {context: c, element: el, calls} = harness();
    c.respond = url => response(url.includes('/summary?') ? summary(1) : page(1, 20));
    await c.loadMeasurements();
    el('measurementDate').value = '2026-08-10';
    for (const id of ['', '1']) {
        el('measurementId').value = id;
        const before = calls.length;
        await c.handleMeasurementFormSubmit();
        const batch = calls.slice(before);
        assert.equal(batch[0].options.method, id ? 'PUT' : 'POST');
        assert.ok(batch.some(call => call.url === '/api/measurements?limit=20'));
        assert.ok(batch.some(call => call.url.startsWith('/api/measurements/summary?')));
        assert.equal(c.measurements.length, 20);
    }
    const before = calls.length;
    await c.deleteMeasurement(1);
    assert.ok(calls.slice(before).some(call => call.url.startsWith('/api/measurements/summary?')));
    assert.ok(calls.slice(before).some(call => call.url === '/api/measurements?limit=20'));
});

test('summary refresh ignores an older response, and empty/error states can recover', async () => {
    const {context: c, element: el} = harness();
    let resolve;
    c.respond = () => new Promise(r => resolve = r);
    const pending = c.loadMeasurementSummary();
    c.respond = () => response(summary(1));
    await c.loadMeasurementSummary();
    resolve(response(summary(-2)));
    await pending;
    assert.match(el('measurementSummary').innerHTML, /\+1 kg/);
    c.respond = () => response({latest_date: null});
    await c.loadMeasurementSummary();
    assert.match(el('measurementSummary').innerHTML, /Sem registros de peso/);
    c.respond = () => ({ok: false, json: async () => ({error: 'Falha de teste'})});
    await c.loadMeasurementSummary();
    assert.match(el('measurementSummary').innerHTML, /Falha de teste/);
    const first = summary(0);
    first.points = [first.points[1]];
    c.respond = () => response(first);
    await c.loadMeasurementSummary();
    assert.match(el('measurementSummary').innerHTML, /70 kg/);
    assert.doesNotMatch(el('measurementSummary').innerHTML, /measurement-summary__delta/);
});

test('invalid dates do not fetch; a failed page can be retried without losing earlier rows', async () => {
    const {context: c, element: el, calls} = harness();
    el('measurementStartDate').value = '2026-08-20';
    el('measurementEndDate').value = '2026-08-01';
    await c.loadMeasurements();
    assert.equal(calls.length, 0);
    assert.equal(c.measurementLoading, false);
    el('measurementEndDate').value = '';
    c.respond = () => response(page(1, 20));
    await c.loadMeasurements();
    c.respond = () => { throw new Error('offline'); };
    await c.loadMeasurements(true);
    assert.equal(c.measurements.length, 20);
    c.respond = () => response([]);
    await c.loadMeasurements(true);
    assert.equal(c.measurements.length, 20);
    assert.equal(c.measurementHasMore, false);
});

test('saving an old measurement never copies its body values into the profile', async () => {
    const {context: c, element: el, calls} = harness();
    el('measurementId').value = '1';
    el('measurementDate').value = '2026-01-01';
    el('measurementWeight').value = '95';
    el('measurementHeight').value = '175';
    c.respond = url => response(url.includes('/summary?') ? summary(0) : page(1, 1));
    await c.handleMeasurementFormSubmit();
    const writes = calls.filter(call => call.options?.method);
    assert.equal(writes.length, 1);
    assert.equal(writes[0].url, '/api/measurements/1');
    assert.equal(writes[0].options.method, 'PUT');
    assert.equal(JSON.parse(writes[0].options.body).weight, 95);
});

test('deleting an activity refreshes profile highlights after reconciliation', async () => {
    const {context: c} = harness();
    c.document.addEventListener = () => {};
    c.window.confirm = () => true;
    let rendered;
    c.renderProfileBadges = user => { rendered = user.profile_highlights; };
    c.currentUser.profile_highlights = [{item: {code: 'removed-record'}}];
    c.respond = url => response(url === '/api/profile/highlights' ? {selected: []} : {});
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../copilot/js/progress.js'), 'utf8'), c);
    await c.window.deleteWorkoutActivity(1);
    assert.equal(c.currentUser.profile_highlights.length, 0);
    assert.equal(rendered.length, 0);
});

test('metric and period changes discard old charts and send independent filters', async () => {
    const {context: c, element: el, calls} = harness();
    let resolve;
    c.respond = () => new Promise(r => resolve = r);
    const old = c.loadMeasurementSummary();
    el('bodyMetric').value = 'body_fat';
    el('measurementStartDate').value = '2026-08-01';
    el('measurementEndDate').value = '2026-08-31';
    c.respond = () => response({points: [{date:'2026-08-05',value:20}],latest_date:'2026-08-05'});
    await c.loadMeasurementSummary();
    resolve(response(summary(3)));
    await old;
    assert.match(el('measurementSummary').innerHTML, /Gordura/);
    assert.doesNotMatch(el('measurementSummary').innerHTML, /kg/);
    const url = new URL(calls.at(-1).url, 'https://test.invalid');
    assert.equal(url.searchParams.get('metric'), 'body_fat');
    assert.equal(url.searchParams.get('start_date'), '2026-08-01');
    assert.equal(url.searchParams.get('end_date'), '2026-08-31');
});
