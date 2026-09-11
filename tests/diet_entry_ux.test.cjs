const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../copilot/js/diet-entry.js'), 'utf8');
function harness() {
    const nodes = new Map();
    function node(id) {
        if (!nodes.has(id)) nodes.set(id, { id, value: '', textContent: '', hidden: false, disabled: false, dataset: {}, listeners: {}, classList: { add() {}, remove() {} },
            addEventListener(event, fn) { this.listeners[event] = fn; }, focus() {}, removeAttribute(key) { delete this[key]; },
            checkValidity: () => true, reportValidity() {}, querySelector: () => ({ scrollTop: 0 }),
            reset() { for (const n of nodes.values()) n.value = ''; } });
        return nodes.get(id);
    }
    const steps = [1, 2, 3, 4].map(n => Object.assign(node('step' + n), { dataset: { dietStep: String(n) } }));
    const methods = ['text', 'photo'].map(n => Object.assign(node(n), { dataset: { dietMethod: n } }));
    const c = { window: {}, currentUser: { id: 'alice' }, API_BASE: '/api', confirm: () => true, calls: [],
        document: { getElementById: node, querySelectorAll: s => s === '[data-diet-step]' ? steps : methods, addEventListener: (_, fn) => { c.ready = fn; } },
        downscaleImageFile: async () => ({ base64: 'photo', dataUrl: 'data:image/jpeg;base64,photo' }),
        respond: async () => ({ ok: true, json: async () => ({ description: 'Arroz e feijão', calories: 100, protein: 0, carbs: null, fat: 1 }) }),
        fetch: async (url, options) => { c.calls.push({ url, options }); return c.respond(); } };
    vm.createContext(c); vm.runInContext(source, c); c.ready(); c.flow = c.window.DietEntryFlow; c.node = node;
    c.closeDietModal = () => { c.closed = c.flow.canClose(); };
    c.click = id => node(id).listeners.click();
    c.input = (id, value) => { node(id).value = value; node('dietForm').listeners.input({ target: node(id) }); };
    c.upload = () => node('dietPhotoInput').listeners.change({ target: { files: [{ type: 'image/heic' }] } });
    c.flow.begin(); return c;
}
test('análise preserva texto original, zero e ausência; só revisão fica ativa', async () => {
    const c = harness(); c.click('text'); c.input('dietSourceText', 'Meu almoço'); await c.flow.analyze();
    assert.equal(c.node('dietSourceText').value, 'Meu almoço'); assert.equal(c.node('dietDescription').value, 'Arroz e feijão');
    assert.equal(c.node('dietProtein').value, 0); assert.equal(c.node('dietCarbs').value, '');
    assert.equal(c.node('step3').hidden, false); assert.equal(c.node('step2').inert, true);
});
test('foto sem texto envia string vazia e MIME convertido', async () => {
    const c = harness(); c.click('photo'); await c.upload(); await c.flow.analyze();
    const body = JSON.parse(c.calls[0].options.body); assert.equal(body.description, ''); assert.equal(body.image.mime_type, 'image/jpeg');
    assert.equal(c.calls[0].options.credentials, 'include');
});
test('trocar caminho ou remover foto não mantém miniatura antiga na revisão', async () => {
    const c = harness(); c.click('photo'); await c.upload(); await c.flow.analyze();
    assert.equal(c.node('dietReviewPhoto').hidden, false);
    c.click('dietFlowBack'); c.click('dietPhotoRemove'); c.input('dietSourceText', 'Café'); c.click('dietFlowManual');
    assert.equal(c.node('dietReviewPhoto').hidden, true); assert.equal(c.node('dietCalories').value, '');
});
test('digitar complemento durante conversão não descarta foto', async () => {
    const c = harness(); c.click('photo'); let done; c.downscaleImageFile = () => new Promise(r => { done = r; });
    const pending = c.upload(); c.input('dietSourceText', 'Sem açúcar'); assert.equal(c.node('dietFlowNext').disabled, true);
    done({ base64: 'photo', dataUrl: 'data:image/jpeg;base64,photo' }); await pending; await c.flow.analyze();
    const body = JSON.parse(c.calls[0].options.body); assert.equal(body.description, 'Sem açúcar'); assert.ok(body.image);
});
test('corrigir descrição exige recalcular ou limpar nutrientes', async () => {
    const c = harness(); c.click('text'); c.input('dietSourceText', 'Almoço'); await c.flow.analyze(); c.input('dietDescription', 'Só arroz');
    assert.equal(c.node('dietFlowNext').textContent, 'Recalcular'); assert.equal(c.flow.canSave(), false);
    c.click('dietFlowManual'); assert.equal(c.node('dietCalories').value, ''); assert.equal(c.node('dietDescription').value, 'Só arroz');
});
test('aceita resultado assíncrono da fila', async () => {
    const c = harness(); c.click('text'); c.input('dietSourceText', 'Arroz');
    c.respond = async () => ({ ok: true, status: 202, json: async () => ({ job_id: 'job' }) });
    c.window.waitForAIJob = async () => ({ description: 'Arroz cozido', calories: 50 }); await c.flow.analyze();
    assert.equal(c.node('dietDescription').value, 'Arroz cozido'); assert.equal(c.node('dietFat').value, '');
});
for (const reason of ['alterar', 'fechar', 'conta']) test(`ignora resposta atrasada após ${reason} e bloqueia análise duplicada`, async () => {
    const c = harness(); c.click('text'); c.input('dietSourceText', 'Arroz'); let done;
    c.respond = () => new Promise(r => { done = r; }); const pending = c.flow.analyze(); await c.flow.analyze(); assert.equal(c.calls.length, 1);
    if (reason === 'alterar') c.input('dietSourceText', 'Feijão');
    if (reason === 'fechar') c.flow.canClose();
    if (reason === 'conta') { c.currentUser = { id: 'bob' }; c.flow.reset(); }
    done({ ok: true, json: async () => ({ description: 'Resposta velha', calories: 30 }) }); await pending;
    assert.notEqual(c.node('dietDescription').value, 'Resposta velha');
});
for (const status of [403, 429, 503]) test(`erro ${status} permite manual sem perder texto`, async () => {
    const c = harness(); c.click('text'); c.input('dietSourceText', 'Banana');
    c.respond = async () => ({ ok: false, status, json: async () => ({ error: 'Indisponível' }) });
    await c.flow.analyze(); c.click('dietFlowManual'); assert.equal(c.node('dietDescription').value, 'Banana'); assert.equal(c.node('dietCalories').value, '');
});
test('identificação ausente não inventa alimento e exige descrição manual', async () => {
    const c = harness(); c.click('photo'); await c.upload(); c.respond = async () => ({ ok: true, json: async () => ({ calories: 20 }) });
    await c.flow.analyze(); c.click('dietFlowManual'); c.click('dietFlowNext'); assert.equal(c.node('dietDescription').value, ''); assert.equal(c.node('step3').hidden, false);
});
test('edição inicia na revisão e preserva contexto bloqueado e zero', () => {
    const c = harness(); c.node('dietDescription').value = 'Café'; c.node('dietCalories').value = 0; c.node('dietMeal').disabled = true; c.flow.begin(true);
    assert.equal(c.node('step3').hidden, false); assert.equal(c.node('dietCalories').value, 0); assert.equal(c.node('dietMeal').disabled, true); assert.equal(c.calls.length, 0);
});
test('fechar usa confirmação contextual, permite continuar e descartar sem diálogo nativo', () => {
    const c = harness(); c.confirm = () => { throw Error('Não usar confirmação nativa'); };
    c.click('text'); c.input('dietSourceText', 'Banana');
    assert.equal(c.flow.canClose(), false); assert.equal(c.node('dietDiscardPanel').hidden, false);
    assert.equal(c.node('dietForm').hidden, true); c.click('dietKeepDraft');
    assert.equal(c.node('dietSourceText').value, 'Banana'); assert.equal(c.node('dietFlowBack').disabled, false);
    c.flow.canClose(); c.click('dietDiscardDraft'); assert.equal(c.closed, true); assert.equal(c.node('dietSourceText').value, '');
});
test('voltar preserva texto e fechar sem alterações é imediato', () => {
    const c = harness(); assert.equal(c.flow.canClose(), true); c.click('text'); c.input('dietSourceText', 'Banana');
    c.click('dietFlowBack'); assert.equal(c.node('step1').hidden, false); c.click('text');
    assert.equal(c.node('dietSourceText').value, 'Banana');
});

function savingHarness(entryId = '', daily = null) {
    const c = harness();
    Object.assign(c, { pendingDietDailyContext: daily, currentTab: 'diet',
        showToast() {}, showDietMessage(text) { c.error = text; },
        closeDietModal() { c.closed = true; c.flow.canClose(); },
        loadDietEntries: async () => {}, loadTodayCardapio: async () => {}, refreshDietDailySurfaces: async () => {} });
    const script = fs.readFileSync(require('node:path').join(__dirname, '../copilot/script.js'), 'utf8');
    const start = script.indexOf('async function handleDietFormSubmit()');
    vm.runInContext(script.slice(start, script.indexOf('\n}', start) + 2), c);
    c.node('dietId').value = entryId; c.node('dietDescription').value = 'Café'; c.node('dietCalories').value = '0';
    c.node('dietDate').value = '2026-09-10'; c.node('dietMeal').value = 'Café da manhã';
    c.flow.begin(true); c.click('dietFlowNext');
    return c;
}
for (const kind of ['novo', 'editar', 'planejado']) test(`salvar ${kind} usa endpoint existente e preserva zero e ausência`, async () => {
    const c = savingHarness(kind === 'editar' ? '7' : '', kind === 'planejado' ? { slotKey: 'cafe', mealId: 9 } : null);
    await c.handleDietFormSubmit(); const request = c.calls[0]; const body = JSON.parse(request.options.body);
    const entry = body.entry || body;
    assert.equal(request.options.credentials, 'include'); assert.equal(entry.calories, 0); assert.equal(entry.protein, null);
    assert.equal(request.options.method, kind === 'novo' ? 'POST' : 'PUT');
    assert.equal(request.url, kind === 'novo' ? '/api/diet' : kind === 'editar' ? '/api/diet/7' : '/api/diet/days/2026-09-10/slots/cafe/outcome');
    if (kind === 'planejado') assert.equal(body.result, 'consumed_different');
    assert.equal(c.closed, true);
});
test('salvamento duplicado bloqueado e resposta após troca de conta ignorada', async () => {
    const c = savingHarness(); let done; c.respond = () => new Promise(r => { done = r; });
    const pending = c.handleDietFormSubmit(); await c.handleDietFormSubmit(); assert.equal(c.calls.length, 1);
    c.flow.reset(); c.currentUser = { id: 'bob' }; done({ ok: true }); await pending; assert.notEqual(c.closed, true);
});
test('falha ao salvar mantém rascunho e libera nova tentativa', async () => {
    const c = savingHarness(); c.respond = async () => { throw Error('offline'); }; await c.handleDietFormSubmit();
    assert.equal(c.node('dietDescription').value, 'Café'); assert.equal(c.node('dietSaveBtn').disabled, false);
    assert.equal(c.node('dietForm').inert, false); assert.ok(c.error);
});
