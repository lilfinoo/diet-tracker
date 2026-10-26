const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../copilot/admin.html'), 'utf8');
const source = html.slice(html.indexOf("    const API = '/api';"), html.indexOf('    function rangeForDays('))
    + html.slice(html.indexOf('    async function loadAll()'), html.indexOf('    async function runAdminAction('));
const json = (data = {}, status = 200) => new Response(JSON.stringify(data), {status, headers: {'content-type': 'application/json'}});

function harness(fetch, {expireRequests = false} = {}) {
    const elements = new Map();
    const delays = [];
    const document = {
        getElementById(id) {
            if (!elements.has(id)) elements.set(id, {hidden: false, disabled: false, textContent: '', classList: {add() {}, remove() {}}});
            return elements.get(id);
        },
        querySelector: () => ({id: 'overview'}),
    };
    const context = {
        document, fetch, Response, AbortController, TypeError, Intl,
        console: {warn() {}, error() {}},
        setTimeout(fn, ms) {
            delays.push(ms);
            if (ms === 1000 || ms === 2000 || (expireRequests && ms === 20000)) return setTimeout(fn, 0);
            return {cancelled: false};
        },
        clearTimeout(id) { if (typeof id === 'object' && 'cancelled' in id) id.cancelled = true; else clearTimeout(id); },
    };
    vm.createContext(context);
    vm.runInContext(source + '\nasync function loadAnalytics() { return api("/admin/analytics"); }', context);
    return {context, elements, delays};
}

test('empty 503 on session recovers before requesting analytics', async () => {
    const calls = [];
    const {context, elements, delays} = harness(async (url, options) => {
        calls.push(url);
        assert.equal(options.credentials, 'include');
        assert.equal(options.cache, 'no-store');
        if (calls.length === 1) return new Response('', {status: 503});
        return json(url.endsWith('check_session') ? {logged_in: true, csrf_token: 'token'} : {});
    });
    await context.loadAll();
    assert.deepEqual(calls, ['/api/check_session', '/api/check_session', '/api/admin/analytics']);
    assert.equal(elements.get('loadStatus').hidden, true);
    assert.equal(elements.get('refreshBtn').disabled, false);
    assert.ok(delays.includes(1000));
});

test('GET retries network failure and HTML 200 wake interstitial', async () => {
    let calls = 0;
    const {context, delays} = harness(async () => {
        calls++;
        if (calls === 1) throw new TypeError('Load failed');
        if (calls === 2) return new Response('<html>Service waking up</html>', {headers: {'content-type': 'text/html'}});
        return json({ready: true});
    });
    assert.equal((await context.api('/check_session')).ready, true);
    assert.equal(calls, 3);
    assert.ok(delays.includes(1000));
    assert.ok(delays.includes(2000));
});

test('GET times out each attempt and stops after three attempts', async () => {
    let calls = 0;
    const {context, delays} = harness((url, {signal}) => {
        calls++;
        return new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Timed out', 'AbortError'))));
    }, {expireRequests: true});
    await assert.rejects(context.api('/check_session'), {name: 'AbortError'});
    assert.equal(calls, 3);
    assert.equal(delays.filter(ms => ms === 20000).length, 3);
});

test('401 does not retry and reports expired session', async () => {
    let calls = 0;
    const {context} = harness(async () => { calls++; return json({}, 401); });
    await assert.rejects(context.api('/check_session'), /sessão expirou/);
    assert.equal(calls, 1);
});

for (const failure of ['503', 'network']) {
    test(`mutation ${failure} never repeats and preserves CSRF and credentials`, async () => {
        let calls = 0;
        const {context} = harness(async (url, options) => {
            calls++;
            assert.equal(options.credentials, 'include');
            assert.equal(options.headers['X-CSRF-Token'], 'csrf');
            assert.equal(options.headers['Content-Type'], 'application/json');
            assert.equal(options.body, '{"enabled":true}');
            if (failure === 'network') throw new TypeError('Load failed');
            return new Response('', {status: 503});
        });
        context.setCsrfToken('csrf');
        await assert.rejects(context.api('/admin/users/id/ban', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{"enabled":true}'}));
        assert.equal(calls, 1);
    });
}

test('exhausted failure leaves persistent banner; manual refresh recovers', async () => {
    let failing = true;
    let calls = 0;
    const {context, elements} = harness(async url => {
        calls++;
        if (failing) throw new TypeError('Load failed');
        return json(url.endsWith('check_session') ? {logged_in: true} : {});
    });
    await context.loadAll();
    assert.equal(calls, 3);
    assert.equal(elements.get('loadStatus').hidden, false);
    assert.match(elements.get('loadStatus').textContent, /Clique em Atualizar/);
    assert.equal(elements.get('refreshBtn').disabled, false);
    failing = false;
    await context.loadAll();
    assert.equal(calls, 5);
    assert.equal(elements.get('loadStatus').hidden, true);
});
