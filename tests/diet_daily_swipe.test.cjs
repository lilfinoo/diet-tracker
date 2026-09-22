const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../copilot/script.js'), 'utf8');
const gestureSource = source.slice(
    source.indexOf('function closeDietDailyActions'),
    source.indexOf('function renderDietDailySlot')
);

function harness() {
    const outcomes = [];
    let now = 0;
    const context = {
        window: { lucide: null },
        document: {
            body: { appendChild() {} },
            querySelector: () => null,
            addEventListener() {},
            removeEventListener() {},
            createElement: () => ({})
        },
        performance: { now: () => now },
        requestAnimationFrame: callback => callback(),
        setTimeout: callback => { callback(); return 1; },
        reducedMotion: () => false,
        escapeHtml: String,
        dietDailyView: { slots: [] },
        dietDailyMutationSlotKey: null,
        dietDailyOptionsSlotKey: null,
        openDietDailyDifferent() {},
        toggleDietDailyOptions() {},
        setDietDailyOutcome: (slotKey, result) => outcomes.push({ slotKey, result })
    };
    vm.createContext(context);
    vm.runInContext(`let dietDailySwipeGesture = null; let dietDailyActionsTrigger = null; ${gestureSource}; this.api = { startDietDailySwipe, moveDietDailySwipe, endDietDailySwipe, cancelDietDailySwipe };`, context);
    return { api: context.api, outcomes, setNow: value => { now = value; } };
}

function card() {
    const classes = new Set();
    const styles = new Map();
    return {
        dataset: { slotKey: 'almoco' },
        classList: {
            add: (...names) => names.forEach(name => classes.add(name)),
            remove: (...names) => names.forEach(name => classes.delete(name)),
            toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name)
        },
        style: {
            setProperty: (name, value) => styles.set(name, value),
            removeProperty: name => styles.delete(name)
        },
        getBoundingClientRect: () => ({ width: 320 }),
        setPointerCapture() {},
        hasPointerCapture: () => false,
        classes,
        styles
    };
}

function pointer(surface, x, y, options = {}) {
    return {
        isPrimary: true,
        button: 0,
        pointerId: 1,
        clientX: x,
        clientY: y,
        currentTarget: surface,
        target: { closest: () => null },
        preventDefault() { this.prevented = true; },
        ...options
    };
}

function swipe(api, surface, dx, dy, setNow) {
    api.startDietDailySwipe(pointer(surface, 160, 200));
    setNow(300);
    const move = pointer(surface, 160 + dx, 200 + dy);
    api.moveDietDailySwipe(move);
    api.endDietDailySwipe(pointer(surface, 160 + dx, 200 + dy));
    return move;
}

test('swipe horizontal para a direita reutiliza o resultado skipped', () => {
    const { api, outcomes, setNow } = harness();
    const surface = card();
    const move = swipe(api, surface, 100, 4, setNow);
    assert.equal(move.prevented, true);
    assert.deepEqual(outcomes, [{ slotKey: 'almoco', result: 'skipped' }]);
    assert.equal(surface.classes.has('is-committing-right'), true);
});

test('swipe horizontal para a esquerda reutiliza o resultado consumed_planned', () => {
    const { api, outcomes, setNow } = harness();
    const surface = card();
    swipe(api, surface, -100, 3, setNow);
    assert.deepEqual(outcomes, [{ slotKey: 'almoco', result: 'consumed_planned' }]);
    assert.equal(surface.classes.has('is-committing-left'), true);
});

test('scroll vertical e gesto diagonal não são capturados nem disparam ações', () => {
    for (const [dx, dy] of [[5, 90], [90, 90]]) {
        const { api, outcomes, setNow } = harness();
        const move = swipe(api, card(), dx, dy, setNow);
        assert.equal(move.prevented, undefined);
        assert.deepEqual(outcomes, []);
    }
});

test('deslocamento horizontal curto move o card sem disparar ação', () => {
    const { api, outcomes, setNow } = harness();
    const move = swipe(api, card(), 40, 2, setNow);
    assert.equal(move.prevented, true);
    assert.deepEqual(outcomes, []);
});

test('gesto iniciado sobre um botão é ignorado', () => {
    const { api, outcomes, setNow } = harness();
    const surface = card();
    api.startDietDailySwipe(pointer(surface, 160, 200, { target: { closest: () => ({}) } }));
    setNow(300);
    api.moveDietDailySwipe(pointer(surface, 270, 200));
    api.endDietDailySwipe(pointer(surface, 270, 200));
    assert.deepEqual(outcomes, []);
});

test('card pendente expõe menu e reaproveita os fluxos existentes', () => {
    const pendingTemplate = source.slice(source.indexOf('function renderDietDailySlot'), source.indexOf('function renderDietDailyManualEntry'));
    assert.match(pendingTemplate, /openDietDailyActions/);
    assert.doesNotMatch(pendingTemplate, /diet-daily-primary/);
    assert.match(gestureSource, /openDietDailyDifferent\(slotKey\)/);
    assert.match(gestureSource, /toggleDietDailyOptions\(slotKey\)/);
    assert.match(source, /actionLabel: 'Desfazer'/);
    assert.match(source, /onAction: \(\) => resetDietDailySlot\(slotKey\)/);
});
