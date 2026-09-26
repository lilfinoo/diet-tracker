const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../copilot/script.js'), 'utf8');
const slice = (start, end) => source.slice(source.indexOf(start), source.indexOf(end));

function harness() {
    const events = [], toasts = [], requests = [];
    const slot = { slot_key: 'almoco', result: 'pending', entry: null };
    const body = { innerHTML: '', contains: () => false, querySelectorAll: () => [{ dataset: { slotKey: 'almoco' }, closest: () => ({ classList: { add: () => events.push('animate') } }) }], querySelector: () => null };
    let mutation = null;
    const c = {
        API_BASE: '/api', window: { lucide: null }, document: { activeElement: { isConnected: true }, body: {} },
        todayDietDay: { date: '2026-09-26', plan: {}, slots: [slot], totals: { calories: 0, protein: 0, carbs: 0, fat: 0 } },
        getElement: () => body, reducedMotion: () => false,
        updateDailySummary: () => events.push('summary'), renderPersonalizedHomeIntro: () => false,
        escapeHtml: String, renderDietDailySlot: item => `<article>${item.result}</article>`,
        dietSurfaceDate: () => c.todayDietDay.date,
        dietSurfaceMutationKey: () => mutation, setDietSurfaceMutationKey: (_, value) => { mutation = value; },
        findDietSurfaceSlot: () => slot, dailySlotSelectedMeal: () => ({ id: 7 }),
        renderDietSurface: surface => { if (surface === 'home') c.renderTodayCardapio(c.todayDietDay); },
        refreshDietDailySurfaces: async () => { events.push('refresh'); },
        showToast: (message, type, options) => { toasts.push({ message, type, options, mutation }); },
        setTimeout: resolve => { events.push('timer'); resolve(); },
        fetch: async (url, options) => {
            requests.push({ url, options });
            return { ok: true, json: async () => ({ state: options.method === 'DELETE'
                ? { result: 'pending', entry: null }
                : { result: JSON.parse(options.body).result, entry: { calories: 500, protein: 30, carbs: 60, fat: 15 } } }) };
        }
    };
    vm.createContext(c);
    vm.runInContext(slice('function renderTodayCardapio', 'function renderDietCurrentPlanHub') +
        slice('async function animateHomeMealRemoval', 'async function refreshDietDailySurfaces'), c);
    return { c, slot, body, events, toasts, requests, mutation: () => mutation };
}

test('Home oculta consumidas, preserva puladas e informa conclusão sem pendências', () => {
    const { c, body } = harness();
    c.todayDietDay.slots = ['consumed_planned', 'consumed_different', 'skipped'].map(result => ({ result }));
    c.renderTodayCardapio(c.todayDietDay);
    assert.doesNotMatch(body.innerHTML, /consumed_/);
    assert.match(body.innerHTML, /skipped/);
    assert.match(body.innerHTML, /já foram tratadas/);
    c.todayDietDay.slots.push({ result: 'pending' });
    c.renderTodayCardapio(c.todayDietDay);
    assert.doesNotMatch(body.innerHTML, /já foram tratadas/);
    c.todayDietDay.slots = [];
    c.renderTodayCardapio(c.todayDietDay);
    assert.match(body.innerHTML, /Sem refeições previstas/);
});

test('confirmação atualiza gráficos antes da animação e da recarga; desfazer restaura totais', async () => {
    const h = harness(); let respond;
    const fetch = h.c.fetch;
    h.c.fetch = (...args) => new Promise(resolve => { respond = () => resolve(fetch(...args)); });
    const pending = h.c.setDietDailyOutcome('almoco', 'consumed_planned', 'home');
    assert.equal(h.slot.result, 'pending');
    assert.ok(!h.events.includes('animate'));
    h.events.length = 0;
    respond(); await pending;
    assert.deepEqual(h.events.slice(0, 4), ['summary', 'animate', 'timer', 'refresh']);
    assert.equal(h.c.todayDietDay.totals.calories, 500);
    assert.doesNotMatch(h.body.innerHTML, /consumed_planned/);
    assert.equal(h.toasts[0].mutation, null);
    assert.equal(h.toasts[0].options.duration, 5000);
    h.c.fetch = fetch;
    await h.toasts[0].options.onAction();
    assert.equal(h.slot.result, 'pending');
    assert.equal(h.c.todayDietDay.totals.calories, 0);
    assert.equal(h.requests[1].options.method, 'DELETE');
    assert.equal(h.requests[1].options.credentials, 'include');
    assert.match(h.body.innerHTML, /pending/);
});

test('falha no servidor mantém card e não oferece desfazer', async () => {
    const h = harness();
    h.c.fetch = async () => ({ ok: false, json: async () => ({ error: 'Falhou' }) });
    await h.c.setDietDailyOutcome('almoco', 'consumed_planned', 'home');
    assert.equal(h.slot.result, 'pending');
    assert.ok(!h.events.includes('animate'));
    assert.equal(h.toasts[0].type, 'error');
    assert.equal(h.mutation(), null);
});

test('desfazer guarda a data original e falha sem restaurar só na tela', async () => {
    const h = harness();
    await h.c.setDietDailyOutcome('almoco', 'consumed_planned', 'home');
    h.c.todayDietDay.date = '2026-09-27';
    await h.toasts[0].options.onAction();
    assert.match(h.requests[1].url, /2026-09-26/);
    assert.equal(h.slot.result, 'consumed_planned');
    h.c.fetch = async () => ({ ok: false, json: async () => ({ error: 'Falha ao desfazer' }) });
    await h.c.resetDietDailySlot('almoco', 'home');
    assert.equal(h.slot.result, 'consumed_planned');
    assert.equal(h.toasts.at(-1).type, 'error');
});

test('movimento reduzido dispensa animação e tela de dieta não ganha remoção', async () => {
    const h = harness(); h.c.reducedMotion = () => true;
    await h.c.setDietDailyOutcome('almoco', 'consumed_planned', 'home');
    assert.ok(!h.events.includes('animate'));
    const diet = harness();
    await diet.c.setDietDailyOutcome('almoco', 'consumed_planned', 'diet');
    assert.ok(!diet.events.includes('animate'));
    assert.deepEqual(Object.keys(diet.toasts[0].options), []);
});

test('pulada mantém corrigir no renderer compartilhado e oferece desfazer', async () => {
    const h = harness();
    await h.c.setDietDailyOutcome('almoco', 'skipped', 'home');
    assert.match(h.body.innerHTML, /skipped/);
    assert.ok(!h.events.includes('animate'));
    assert.equal(h.toasts[0].options.actionLabel, 'Desfazer');
    const renderer = slice('function renderDietDailySlot', 'function renderDietDailyManualEntry');
    assert.match(renderer, /resetDietDailySlot[^]*?Corrigir/);
});
