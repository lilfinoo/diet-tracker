const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../copilot/js/home-refresh.js'), 'utf8');

function classList(initial = []) {
    const values = new Set(initial);
    return {
        add: (...items) => items.forEach(item => values.add(item)),
        remove: (...items) => items.forEach(item => values.delete(item)),
        contains: item => values.has(item),
        toggle(item, force) { if (force) values.add(item); else values.delete(item); return force; },
    };
}

function harness() {
    const nodes = new Map();
    const events = new Map();
    const makeNode = (id, classes = []) => ({
        id, hidden: false, textContent: '', dataset: {}, classList: classList(classes),
        style: { values: {}, setProperty(key, value) { this.values[key] = value; } },
        setAttribute(key, value) { this[key] = value; },
        addEventListener(type, listener) { this.listener = { type, listener }; },
    });
    nodes.set('dietTab', makeNode('dietTab'));
    nodes.set('homeRefreshIndicator', makeNode('homeRefreshIndicator'));
    nodes.set('homeRefreshLabel', makeNode('homeRefreshLabel'));
    nodes.set('homeRefreshRetry', makeNode('homeRefreshRetry'));
    nodes.set('homeRefreshStatus', makeNode('homeRefreshStatus'));

    let modal = false;
    const document = {
        readyState: 'complete', hidden: false,
        documentElement: { dataset: {}, classList: classList() },
        body: { dataset: { activeTab: 'diet', offline: 'false' }, classList: classList() },
        scrollingElement: { scrollTop: 0 },
        getElementById: id => nodes.get(id) || null,
        querySelector: selector => selector === '.modal.show' && modal ? {} : null,
        addEventListener(type, listener) { events.set(type, listener); },
    };
    const window = {
        currentUser: { id: 'alice' }, AppReadCache: { accountVersion: 2 },
        localDateInputValue: () => '2026-09-18', scrollY: 0,
        setTimeout, clearTimeout,
        addEventListener(type, listener) { events.set(type, listener); },
        loadTodayCardapio: async () => ({ ok: true }),
        loadWorkoutTodayCard: async () => ({ ok: true }),
    };
    const navigator = { onLine: true };
    const context = { window, document, navigator, Intl, Promise, setTimeout, clearTimeout, console };
    vm.createContext(context);
    vm.runInContext(source, context);
    return { window, document, navigator, nodes, setModal: value => { modal = value; } };
}

test('manual refresh is single-flight and requests each Home surface once', async () => {
    const { window } = harness();
    let dietCalls = 0, workoutCalls = 0, finishDiet, finishWorkout;
    window.loadTodayCardapio = () => { dietCalls++; return new Promise(resolve => { finishDiet = resolve; }); };
    window.loadWorkoutTodayCard = () => { workoutCalls++; return new Promise(resolve => { finishWorkout = resolve; }); };
    const first = window.HomeRefreshCoordinator.refresh({ visual: false });
    const second = window.HomeRefreshCoordinator.refresh({ visual: false });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(dietCalls, 1);
    assert.equal(workoutCalls, 1);
    finishDiet({ ok: true }); finishWorkout({ ok: true });
    assert.equal((await first).ok, true);
    assert.equal(await second, await first);
});

test('a failed secondary surface produces a partial result without discarding diet success', async () => {
    const { window } = harness();
    window.loadTodayCardapio = async () => ({ ok: true, data: { totals: { calories: 10 } } });
    window.loadWorkoutTodayCard = async () => ({ ok: false, error: 'network' });
    const result = await window.HomeRefreshCoordinator.refresh({ visual: false });
    assert.equal(result.ok, false);
    assert.equal(result.partial, true);
    assert.equal(result.diet.ok, true);
});

test('offline pull keeps current data and does not start network loaders', async () => {
    const { window, navigator, nodes } = harness();
    let calls = 0;
    window.loadTodayCardapio = window.loadWorkoutTodayCard = async () => { calls++; return { ok: true }; };
    navigator.onLine = false;
    const result = await window.HomeRefreshCoordinator.refresh({ source: 'pull', visual: true });
    assert.equal(result.offline, true);
    assert.equal(calls, 0);
    assert.equal(nodes.get('homeRefreshIndicator').dataset.state, 'offline');
});

test('modal and player surfaces make native/web refresh ineligible', () => {
    const { window, nodes, setModal } = harness();
    assert.equal(window.HomeRefreshCoordinator.canStart(), true);
    setModal(true);
    assert.equal(window.HomeRefreshCoordinator.canStart(), false);
    setModal(false);
    nodes.set('viewWorkoutPlanModal', { classList: classList(['show']) });
    assert.equal(window.HomeRefreshCoordinator.canStart(), false);
});
