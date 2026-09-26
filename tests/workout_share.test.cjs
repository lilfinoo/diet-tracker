const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../copilot/js/workout-share.js'), 'utf8');

function harness(native = false) {
    const texts = [], downloads = [], shares = [], panels = [];
    const ctx = { fillRect() {}, drawImage() {}, beginPath() { panels.push('panel'); }, moveTo() {}, arcTo() {}, closePath() {}, fill() {},
        fillText: value => texts.push(value), measureText: value => ({ width: value.length * 25 }) };
    const c = { window: { Capacitor: native ? { isNativePlatform: () => true, getPlatform: () => 'ios', Plugins: {
        FitTrackerShare: { sharePNG: async value => { shares.push(value); return { status: 'shared' }; } }
    } } : undefined }, navigator: {}, Blob, File,
        URL: { createObjectURL: () => 'blob:card', revokeObjectURL() {} }, setTimeout: fn => { fn(); return 0; },
        FileReader: class { readAsDataURL() { this.result = 'data:image/png;base64,cG5n'; this.onload(); } },
        document: { createElement: tag => tag === 'a' ? { click() { downloads.push(this.download); } }
            : { getContext: () => ctx, toBlob: callback => callback(new Blob(['png'], { type: 'image/png' })) } }
    };
    vm.createContext(c); vm.runInContext(source, c);
    const summary = { session_id: 'test', workout_name: 'Treino concluído', duration_seconds: 600,
        exercises: [{ exercise_id: 1, name: 'Supino', best_set: { load_kg: 20, repetitions: 10 } }, { exercise_id: 2, name: 'Remada' }] };
    const draft = { mode: 'dark', infoPreset: 'full', selectedExerciseIds: new Set(['1']) };
    return { c, api: c.window.WorkoutShare, summary, draft, texts, downloads, shares, panels, ctx };
}

test('treino mantém PNG 9:16, exercícios selecionados e três opções de conteúdo', async () => {
    for (const preset of ['full', 'compact', 'minimal']) {
        const h = harness(); h.draft.infoPreset = preset;
        const artifact = await h.api.preparePNG(h.summary, h.draft);
        assert.equal(artifact.canvas.width, 1080); assert.equal(artifact.canvas.height, 1920);
        assert.ok(h.texts.includes('TREINO CONCLUÍDO'));
        assert.ok(h.texts.includes('Fit-Tracker.AI'));
        assert.equal(h.texts.includes('Supino'), preset === 'full');
        assert.ok(!h.texts.includes('Remada'));
        assert.equal((await h.api.sharePrepared(h.summary, h.draft)).status, 'download-started');
        assert.deepEqual(h.downloads, ['treino-card.png']);
    }
});

test('treino preserva compartilhamento nativo, web e cancelamento', async () => {
    const native = harness(true);
    await native.api.preparePNG(native.summary, native.draft);
    assert.equal((await native.api.sharePrepared(native.summary, native.draft)).status, 'shared');
    assert.equal(native.shares[0].base64, 'cG5n');
    const h = harness();
    await h.api.preparePNG(h.summary, h.draft);
    h.c.navigator = { canShare: () => true, share: async value => h.shares.push(value) };
    assert.equal((await h.api.sharePrepared(h.summary, h.draft)).status, 'shared');
    assert.equal(h.shares[0].files[0].type, 'image/png');
    h.c.navigator.share = async () => { throw Object.assign(new Error('cancelled'), { name: 'AbortError' }); };
    assert.equal((await h.api.sharePrepared(h.summary, h.draft)).status, 'cancelled');
    h.draft.selectedExerciseIds.add('2');
    await assert.rejects(h.api.sharePrepared(h.summary, h.draft), /Aguarde/);
});

test('transparente remove painel, mantém texto e invalida PNG anterior', async () => {
    const h = harness(); h.draft.mode = 'photo';
    await h.api.preparePNG(h.summary, h.draft);
    assert.equal(h.panels.length, 1);
    h.draft.transparent = true;
    await assert.rejects(h.api.sharePrepared(h.summary, h.draft), /Aguarde/);
    h.panels.length = 0; h.texts.length = 0;
    await h.api.preparePNG(h.summary, h.draft);
    assert.equal(h.panels.length, 0);
    assert.ok(h.ctx.shadowBlur > 0);
    assert.ok(h.texts.includes('Supino'));
    assert.equal((await h.api.sharePrepared(h.summary, h.draft)).status, 'download-started');
    h.draft.mode = 'dark';
    await h.api.preparePNG(h.summary, h.draft);
    assert.equal(h.panels.length, 1);
});
