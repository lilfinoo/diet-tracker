const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function harness(reduced = false) {
    let change;
    let now = 0;
    let nextTimer = 0;
    const timers = new Map();
    const frames = [];
    const query = { matches: reduced, addEventListener(_, callback) { change = callback; } };
    const c = { window: { matchMedia: () => query }, performance: { now: () => now },
        setTimeout(fn) { timers.set(++nextTimer, fn); return nextTimer; }, clearTimeout(id) { timers.delete(id); },
        getComputedStyle: () => ({ opacity: '1' }), requestAnimationFrame: callback => frames.push(callback) };
    vm.createContext(c);
    vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../copilot/fluid.js'), 'utf8'), c);
    return { api: c.window.Fluid, timeout() { [...timers.values()].forEach(fn => fn()); }, frame(time) { now = time; frames.splice(0).forEach(fn => fn(time)); }, reduce() { query.matches = true; change(); } };
}
test('close during entrance replaces the old completion and finishes exactly once', () => {
    const h = harness(), node = { style: {} }; let opened = 0, closed = 0;
    h.api.animate(node, { opacity: 1, y: 0 }, { duration: 280, from: { opacity: 0, y: 16 }, onComplete: () => opened++ });
    h.frame(0); h.frame(40);
    const midway = node.style.opacity;
    h.api.animate(node, { opacity: 0, y: 16 }, { duration: 180, onComplete: () => closed++ });
    assert.equal(node.style.opacity, midway);
    h.frame(50); h.frame(230); h.frame(500);
    assert.equal(opened, 0); assert.equal(closed, 1); assert.equal(h.api._activeCount(), 0);
});
test('reopening cancels the pending close callback', () => {
    const h = harness(), node = { style: {} }; let closed = 0;
    h.api.animate(node, { opacity: 0 }, { duration: 180, onComplete: () => closed++ });
    h.frame(0); h.frame(50);
    h.api.animate(node, { opacity: 1 }, { duration: 280 });
    h.frame(60); h.frame(340);
    assert.equal(closed, 0); assert.equal(node.style.opacity, '1');
});
test('reduced motion at start and during movement runs callbacks without leaving active work', () => {
    for (const initiallyReduced of [true, false]) {
        const h = harness(initiallyReduced), first = { style: {} }, second = { style: {} }; let closed = 0;
        h.api.animate(first, { opacity: 0 }, { duration: 180, onComplete() { closed++; h.api.stop(second); } });
        if (!initiallyReduced) {
            h.api.animate(second, { opacity: 0 }, { duration: 180 });
            h.frame(0); h.reduce(); h.frame(1000);
        }
        assert.equal(closed, 1); assert.equal(h.api._activeCount(), 0); assert.equal(first.style.opacity, '0');
    }
});
test('retargeting a spring updates its completion callback too', () => {
    const h = harness(), node = { style: {} }; let old = 0, latest = 0;
    h.api.animate(node, { opacity: 1 }, { from: { opacity: 0 }, onComplete: () => old++ });
    h.api.animate(node, { opacity: 0 }, { onComplete: () => latest++ });
    h.reduce();
    assert.equal(old, 0); assert.equal(latest, 1);
});

test('a throttled frame cannot leave a close pending, and its callback runs only once', () => {
    const h = harness(), node = { style: {} }; let closed = 0;
    h.api.animate(node, { opacity: 0 }, { duration: 180, onComplete: () => closed++ });
    h.timeout(); h.frame(1000); h.timeout();
    assert.equal(closed, 1); assert.equal(h.api._activeCount(), 0);
});
