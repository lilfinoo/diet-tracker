const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../copilot/script.js'), 'utf8');

function optionsHarness(reduced = false) {
    const animations = [], panels = [];
    const document = { activeElement: null, createElement: () => ({ content: { firstElementChild: panel() } }) };
    const trigger = { focus() { document.activeElement = this; } };
    function panel() {
        const option = { focus() { document.activeElement = this; } };
        return {
            inert: false, option, keydown: null,
            contains: node => node === option,
            closest: () => card,
            querySelector: () => option,
            addEventListener(_, callback) { this.keydown = callback; },
            remove() { const index = panels.indexOf(this); if (index >= 0) panels.splice(index, 1); }
        };
    }
    const card = { dataset: { slotKey: 'lunch' }, querySelector: () => trigger, appendChild: node => panels.push(node) };
    const container = { querySelectorAll: selector => selector === '[data-slot-key]' ? [card] : [...panels] };
    let key = null, renders = 0;
    const context = {
        document, window: { Fluid: { stop() {}, animate(node, target, options) { animations.push({ node, target, options }); } } },
        reducedMotion: () => reduced, getElement: () => container,
        dietSurfaceOptionsKey: () => key, setDietSurfaceOptionsKey: (_, value) => { key = value; },
        findDietSurfaceSlot: () => ({}), dailySlotSelectedMeal: () => ({}), renderDietDailyAlternatives: () => '<div></div>',
        renderDietSurface: () => { renders++; }
    };
    vm.createContext(context);
    vm.runInContext(source.slice(source.indexOf('function toggleDietDailyOptions'), source.indexOf('async function selectDietDailyOption')), context);
    return { context, document, trigger, panels, animations, key: () => key, renders: () => renders };
}

test('meal alternatives preserve the card, focus the first option and Escape returns focus during entrance', () => {
    const h = optionsHarness();
    h.context.toggleDietDailyOptions('lunch', 'home');
    const panel = h.panels[0];
    assert.equal(h.document.activeElement, panel.option);
    let prevented = false;
    panel.keydown({ key: 'Escape', preventDefault() { prevented = true; }, stopPropagation() {} });
    assert.equal(prevented, true);
    assert.equal(h.key(), null);
    assert.equal(h.document.activeElement, h.trigger);
    assert.equal(panel.inert, true);
    h.animations.at(-1).options.onComplete();
    assert.equal(h.panels.length, 0);
    assert.equal(h.renders(), 0);
});

test('reopening meal alternatives cannot let an old close remove the new panel; reduced motion closes instantly', () => {
    const h = optionsHarness();
    h.context.toggleDietDailyOptions('lunch');
    h.context.toggleDietDailyOptions('lunch');
    const close = h.animations.at(-1).options.onComplete;
    h.context.toggleDietDailyOptions('lunch');
    const current = h.panels.at(-1);
    close();
    assert.ok(h.panels.includes(current));
    assert.equal(current.inert, false);
    const reduced = optionsHarness(true);
    reduced.context.toggleDietDailyOptions('lunch');
    reduced.context.toggleDietDailyOptions('lunch');
    assert.equal(reduced.panels.length, 0);
    assert.equal(reduced.document.activeElement, reduced.trigger);
});

test('scoped press feedback ignores disabled controls and clears on scroll or reduced motion change', () => {
    const listeners = new Map(), classes = new Set();
    const scope = { contains: () => true };
    class Control {
        disabled = false;
        closest(selector) { return selector.startsWith('#dietTab') ? scope : this; }
        matches() { return this.disabled; }
        classList = { add: value => classes.add(value), remove: (...values) => values.forEach(value => classes.delete(value)) };
    }
    let press;
    const context = { Element: Control, reducedMotion: () => false,
        document: { addEventListener(_, callback) { press = callback; } },
        window: { addEventListener: (name, callback) => listeners.set(name, callback), removeEventListener: name => listeners.delete(name) }
    };
    vm.createContext(context);
    vm.runInContext(source.slice(source.indexOf('(function pressFeedback()'), source.indexOf('// --- 2. Bottom sheet')), context);
    const control = new Control();
    const event = { target: control, button: 0, clientX: 0, clientY: 0 };
    press(event);
    assert.ok(classes.has('is-action-pressed'));
    listeners.get('pointermove')({ clientX: 13, clientY: 0 });
    assert.equal(classes.size, 0);
    press(event);
    listeners.get('fittracker:reduced-motion')();
    assert.equal(classes.size, 0);
    assert.equal(listeners.size, 0);
    control.disabled = true;
    press(event);
    assert.equal(classes.size, 0);
});
