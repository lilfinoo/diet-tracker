const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const read = name => fs.readFileSync(path.join(__dirname, '../copilot', name), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function harness(network = async () => new Response('{}'), oldVersion = 0) {
    const stores = new Map(['snapshots', 'outbox', 'media'].map(name => [name, new Map()]));
    stores.get('outbox').set('pending', { id: 'pending', account: 'alice' });
    stores.get('media').set('photo', { id: 'photo', blob: new Blob(['photo']) });
    stores.get('snapshots').set('/api/profile', { key: '/api/profile', data: { private: true } });
    const resultRequest = value => {
        const request = { result: value };
        queueMicrotask(() => request.onsuccess?.());
        return request;
    };
    const database = {
        objectStoreNames: { contains: name => stores.has(name) },
        transaction(name) {
            const transaction = { objectStore: () => ({
                put(value) { stores.get(name).set(value.key || value.id, structuredClone(value)); },
                get(key) { return resultRequest(stores.get(name).get(key)); },
                delete(key) { stores.get(name).delete(key); },
                clear() { stores.get(name).clear(); },
                index: () => ({ getAll: account => resultRequest([...stores.get(name).values()].filter(item => item.account === account)) }),
            }) };
            setTimeout(() => transaction.oncomplete?.(), 0);
            return transaction;
        },
    };
    const indexedDB = { open(_name, version) {
        const request = { result: database, transaction: database.transaction('snapshots') };
        setTimeout(() => {
            if (oldVersion < version) request.onupgradeneeded?.({ oldVersion });
            request.onsuccess?.();
        }, 0);
        return request;
    } };
    const events = new Map(), logs = [];
    const window = {
        currentUser: null, fetch: network, indexedDB, setTimeout, clearTimeout,
        location: { origin: 'capacitor://localhost' },
        Capacitor: { getPlatform: () => 'ios' },
        addEventListener(name, handler) { events.set(name, handler); },
        dispatchEvent() {},
    };
    const document = { documentElement: { dataset: {} }, body: { dataset: {} },
        querySelector: () => ({ content: 'https://api.example' }), };
    const context = { window, document, indexedDB, navigator: { onLine: true },
        fetch: (...args) => window.fetch(...args), URL, Request, Response, Headers,
        AbortController, DOMException, Blob, FormData, Date, setTimeout, clearTimeout,
        console: { info: (...args) => logs.push(args), error: (...args) => logs.push(args) } };
    vm.createContext(context);
    vm.runInContext(read('js/utils.js'), context);
    vm.runInContext(read('js/offline.js'), context);
    return { window, context, stores, events, logs };
}
const session = (id = 'alice') => ({ logged_in: true, user: { id }, csrf_token: 'csrf' });
const response = data => new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } });

test('confirmation uses the network, credentials and an eight-second deadline', async () => {
    let options;
    const { window } = harness(async () => response(session()));
    let deadline;
    window.setTimeout = (callback, milliseconds) => { deadline = milliseconds; return setTimeout(callback, milliseconds); };
    // Observe the options before the fetch wrapper consumes the custom flag.
    const original = window.fetch;
    window.fetch = (input, init) => { options = init; return original(input, init); };
    const result = await window.confirmAuthSession('https://api.example/api', { id: 'alice' });
    assert.equal(result.user.id, 'alice');
    assert.equal(options.fitTrackerNetworkOnly, true);
    assert.equal(options.credentials, 'include');
    assert.equal(options.cache, 'no-store');
    assert.equal(deadline, 8000);
});

test('confirmation rejects missing session, missing CSRF and a different account', async () => {
    for (const data of [{ logged_in: false }, { ...session(), csrf_token: '' }, session('bob')]) {
        const { window } = harness(async () => response(data));
        await assert.rejects(window.confirmAuthSession('https://api.example/api', { id: 'alice' }));
    }
});

test('confirmation times out instead of waiting indefinitely', async () => {
    const { window } = harness(() => new Promise(() => {}));
    window.setTimeout = (callback, milliseconds) => setTimeout(callback, milliseconds === 8000 ? 10 : milliseconds);
    await assert.rejects(window.confirmAuthSession('https://api.example/api', { id: 'alice' }), { name: 'TimeoutError' });
});

test('an old cached session never confirms a fresh login during network failure', async () => {
    const { window } = harness(async () => { throw new TypeError('Failed to fetch'); });
    await window.AppOffline.saveSnapshot('https://api.example/api/check_session', response(session()));
    assert.ok(await window.AppOffline.readSnapshot('https://api.example/api/check_session', 'anonymous'));
    await assert.rejects(window.confirmAuthSession('https://api.example/api', { id: 'alice' }));
});

test('snapshot upgrade invalidates old snapshots but preserves pending uploads and operations', async () => {
    const { window, stores } = harness(undefined, 1);
    await window.AppOffline.readSnapshot('https://api.example/api/profile');
    assert.equal(stores.get('snapshots').size, 0);
    assert.ok(stores.get('outbox').has('pending'));
    assert.ok(stores.get('media').has('photo'));
});

test('persistent data is separated by account and logout removes offline authentication', async () => {
    const { window } = harness();
    const url = 'https://api.example/api/profile';
    window.currentUser = { id: 'alice' };
    await window.AppOffline.saveSnapshot(url, response({ profile: { age: 30 } }));
    window.currentUser = { id: 'bob' };
    assert.equal(await window.AppOffline.readSnapshot(url), undefined);
    await window.AppOffline.saveSnapshot(url, response({ profile: { age: 40 } }));
    assert.equal((await window.AppOffline.readSnapshot(url, 'alice')).data.profile.age, 30);
    assert.equal((await window.AppOffline.readSnapshot(url, 'bob')).data.profile.age, 40);
    await window.AppOffline.saveSnapshot('https://api.example/api/check_session', response(session('bob')));
    const auth = await window.AppOffline.readSnapshot('https://api.example/api/check_session', 'anonymous');
    assert.equal(auth.data.csrf_token, null);
    await window.AppOffline.clearAuth();
    assert.equal(await window.AppOffline.readSnapshot('https://api.example/api/check_session', 'anonymous'), undefined);
});

test('a delayed response after account switch cannot enter another account cache', async () => {
    let resolve;
    const { window, stores } = harness(() => new Promise(done => { resolve = done; }));
    window.currentUser = { id: 'alice' };
    const pending = window.fetch('https://api.example/api/profile', { credentials: 'include' });
    await tick();
    window.currentUser = { id: 'bob' };
    window.AppReadCache.reset();
    resolve(response({ profile: { age: 30 } }));
    await pending;
    assert.ok(!stores.get('snapshots').has('bob:/api/profile'));
    assert.ok(!stores.get('snapshots').has('alice:/api/profile'));
});

test('API errors retain their status and diagnostics never include query or response bodies', async () => {
    for (const status of [401, 403, 500]) {
        const { window, logs } = harness(async () => new Response('{"email":"private@example.com"}', { status }));
        const result = await window.fetch('https://api.example/api/profile?credential=secret');
        assert.equal(result.status, status);
        const encoded = JSON.stringify(logs);
        assert.ok(encoded.includes(String(status)));
        assert.ok(!encoded.includes('secret'));
        assert.ok(!encoded.includes('private@example.com'));
    }
});

test('uncaught exceptions report sanitized location and details', () => {
    const { events, logs } = harness();
    events.get('unhandledrejection')({ reason: new Error('token=secret email@example.com https://api.example/api/profile?password=secret') });
    const encoded = JSON.stringify(logs);
    assert.ok(encoded.includes('unhandled_rejection'));
    assert.ok(!encoded.includes('secret'));
    assert.ok(!encoded.includes('email@example.com'));
});

test('native login blocks repeated taps, handles cancellation and allows the next attempt', async () => {
    let resolve, nativeCalls = 0, backendCalls = 0;
    const context = {
        nativeGoogleInFlight: false, authRequestInFlight: false, sessionConfirmationInFlight: false,
        window: { Capacitor: { Plugins: { FitTrackerGoogleAuth: { signIn: () => {
            nativeCalls++; return new Promise(done => { resolve = done; });
        } } } } },
        console: { info() {} }, setGoogleAuthPending() {}, showAuthMessage() {},
        handleGoogleCredential: async () => { backendCalls++; },
    };
    vm.createContext(context);
    const source = read('script.js');
    const start = source.indexOf('async function startNativeGoogleSignIn(');
    vm.runInContext(source.slice(start, source.indexOf('\n}', start) + 2), context);
    const pending = context.startNativeGoogleSignIn();
    await context.startNativeGoogleSignIn();
    assert.equal(nativeCalls, 1);
    resolve({ idToken: 'token' }); await pending;
    assert.equal(backendCalls, 1);
    context.window.Capacitor.Plugins.FitTrackerGoogleAuth.signIn = async () => { throw new Error('cancelled'); };
    await context.startNativeGoogleSignIn();
    assert.equal(context.nativeGoogleInFlight, false);
    context.window.Capacitor.Plugins.FitTrackerGoogleAuth.signIn = async () => ({ idToken: 'token' });
    await context.startNativeGoogleSignIn();
    assert.equal(backendCalls, 2);
});

test('failed confirmation keeps authentication open and retry only checks the session', async () => {
    let confirmations = 0, success = 0, persisted = 0, close = 0;
    const buttons = [];
    const context = {
        pendingSessionUser: null, sessionConfirmationInFlight: false, API_BASE: 'https://api.example/api',
        pendingAuthIntent: { tab: 'diet' }, currentTab: 'diet', authMessageTimer: null,
        document: { body: { dataset: {} }, createElement: () => {
            const button = { addEventListener(_name, handler) { this.click = handler; } };
            buttons.push(button); return button;
        } },
        window: { AppReadCache: { accountVersion: 0 },
            confirmAuthSession: async () => { confirmations++; if (confirmations === 1) throw new Error('Failed to fetch'); return session(); },
            AppOffline: { saveSnapshot: async (_url, response) => {
                assert.equal((await response.json()).user.id, 'alice'); persisted++;
            }, sync() {} },
        },
        Response, console: { info() {} }, setGoogleAuthPending() {}, clearTimeout,
        showAuthMessage() {}, getElement: () => ({ append() {} }),
        setCurrentUser(user) { assert.equal(persisted, 1); this.currentUser = user; },
        setCsrfToken() {}, updateOfflineStatus() {},
        closeAppModal() { close++; }, viewForPath: () => 'diet',
        finishAuthenticatedRoute() { success++; }, userNeedsOnboarding: () => false,
        showToast() {},
    };
    vm.createContext(context);
    const source = read('script.js');
    const start = source.indexOf('async function completeAuthentication(');
    vm.runInContext(source.slice(start, source.indexOf('\n}', start) + 2), context);
    await context.completeAuthentication({ id: 'alice' }, 'csrf');
    assert.equal(success, 0); assert.equal(close, 0); assert.equal(persisted, 0);
    assert.equal(context.pendingSessionUser.id, 'alice');
    await buttons[0].click();
    assert.equal(confirmations, 2); assert.equal(success, 1); assert.equal(close, 1);
    assert.equal(context.pendingSessionUser, null);
});

test('offline boot restores a persisted confirmed login, but not after logout', async () => {
    const { window, context } = harness();
    await window.AppOffline.saveSnapshot('https://api.example/api/check_session', response(session()));
    // Reload the storage module to force a persistent read, not an in-memory hit.
    vm.runInContext(read('js/offline.js'), context);
    let rendered = 0, guest = 0;
    Object.assign(context, {
        API_BASE: 'https://api.example/api', authState: 'unknown', currentUser: null,
        setAppBootState() {}, setCsrfToken() {},
        setCurrentUser(user) { context.currentUser = user; },
        updateOfflineStatus() {}, viewForPath: () => 'diet',
        finishAuthenticatedRoute() { rendered++; }, finishAppBoot() {},
        openAuthLanding() { guest++; }, getElement: () => ({ addEventListener() {} }),
    });
    context.navigator.onLine = false;
    const source = read('script.js');
    const start = source.indexOf('async function bootApp(');
    vm.runInContext(source.slice(start, source.indexOf('\n}', start) + 2), context);
    await context.bootApp();
    assert.equal(rendered, 1); assert.equal(context.currentUser.id, 'alice');
    await window.AppOffline.clearAuth(); context.currentUser = null;
    await context.bootApp();
    assert.equal(rendered, 1); assert.equal(guest, 1);
});

test('failed plan refresh retains known data and displays retry for 401, 403 and 500', async () => {
    for (const kind of ['diet', 'workout']) for (const status of [401, 403, 500]) {
        const element = { children: [{}], innerHTML: 'known plan', setAttribute() {},
            insertAdjacentHTML(_where, html) { this.innerHTML += html; } };
        const context = {
            window: { currentUser: { id: 'alice' } }, byId: () => element,
            workoutAccount: () => 'alice', dietPlans: [{ id: 1 }], workoutPlans: [{ id: 1 }],
            loadWorkoutTodayCard: async () => {}, workoutTodayError: '',
            apiRequest: async () => { throw new Error(`HTTP ${status}`); },
            renderPlanList() { element.innerHTML = 'known plan'; },
            renderFilteredWorkoutPlans() { element.innerHTML = 'known plan'; },
            esc: value => String(value),
        };
        vm.createContext(context);
        const source = read('js/plans.js');
        const name = kind === 'diet' ? 'loadDietPlans' : 'loadWorkoutPlans';
        const start = source.indexOf(`async function ${name}(`);
        vm.runInContext(source.slice(start, source.indexOf('\n    }', start) + 6), context);
        await context[name]();
        assert.ok(element.innerHTML.includes('known plan'));
        assert.ok(element.innerHTML.includes(`HTTP ${status}`));
        assert.ok(element.innerHTML.includes('Tentar novamente'));
    }
});
