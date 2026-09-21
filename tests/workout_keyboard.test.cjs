const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function viewportHarness() {
    const source = fs.readFileSync(path.join(__dirname, '../copilot/js/plans.js'), 'utf8');
    const classes = new Set(['show']);
    const properties = new Map();
    const scroll = { scrollTop: 0, getBoundingClientRect: () => ({ top: 8, bottom: 360 }) };
    const input = { matches: () => true, closest: () => scroll, getBoundingClientRect: () => ({ top: 340, bottom: 400 }) };
    const modal = {
        classList: { contains: name => classes.has(name), remove: name => classes.delete(name), toggle: (name, active) => active ? classes.add(name) : classes.delete(name) },
        style: { setProperty: (name, value) => properties.set(name, value), removeProperty: name => properties.delete(name) },
        contains: element => element === input,
    };
    let frame;
    const context = {
        window: { innerWidth: 390, innerHeight: 844, visualViewport: { height: 844, offsetTop: 0, scale: 1 } },
        document: { activeElement: null },
        workoutView: { session: { id: 1 } },
        byId: () => modal,
        requestAnimationFrame: fn => { frame = fn; return 1; },
    };
    vm.createContext(context);
    vm.runInContext(source.slice(source.indexOf('    let workoutViewportFrame'), source.indexOf('    function renderWorkoutDetail')), context);
    const update = () => { context.updateWorkoutVisualViewport(); frame(); };
    update();
    return { context, input, classes, properties, scroll, update };
}

test('iOS keyboard remains detected when both layout and visual viewport shrink', () => {
    const h = viewportHarness();
    h.context.document.activeElement = h.input;
    h.context.window.innerHeight = 390;
    h.context.window.visualViewport.height = 390;
    h.update();
    assert.ok(h.classes.has('has-workout-keyboard'));
    assert.equal(h.properties.get('--workout-viewport-height'), '390px');
    assert.equal(h.properties.get('--workout-entry-height'), '390px');
    assert.equal(h.scroll.scrollTop, 52);
});

test('Safari keyboard caps the entry card at half the original screen height', () => {
    const h = viewportHarness();
    h.context.document.activeElement = h.input;
    h.context.window.visualViewport.height = 500;
    h.context.window.visualViewport.offsetTop = 20;
    h.update();
    assert.ok(h.classes.has('has-workout-keyboard'));
    assert.equal(h.properties.get('--workout-entry-height'), '422px');
    assert.equal(h.properties.get('--workout-viewport-top'), '20px');
    h.context.window.visualViewport.height = 844;
    h.update();
    assert.ok(!h.classes.has('has-workout-keyboard'));
});

test('rotation resets the baseline and zoom is not mistaken for a keyboard', () => {
    const h = viewportHarness();
    h.context.window.innerWidth = 844;
    h.context.window.innerHeight = 390;
    h.context.window.visualViewport.height = 390;
    h.context.document.activeElement = h.input;
    h.update();
    assert.ok(!h.classes.has('has-workout-keyboard'));
    h.context.window.visualViewport.scale = 2;
    h.context.window.visualViewport.height = 195;
    h.update();
    assert.ok(!h.classes.has('has-workout-keyboard'));
    assert.ok(!h.properties.has('--workout-entry-height'));
});
