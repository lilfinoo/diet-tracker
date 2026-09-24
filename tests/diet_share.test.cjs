const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../copilot/js/diet-share.js'), 'utf8');

function harness({ native = false, share = false, delayFirstBlob = false } = {}) {
    const drawings = [];
    const links = [];
    const shares = [];
    const texts = [];
    let heldBlob = null, blobCount = 0;
    const url = { createObjectURL: () => 'blob:photo', revokeObjectURL() {} };
    const context = {
        window: { Capacitor: native ? { isNativePlatform: () => true, getPlatform: () => 'ios', Plugins: {
            FitTrackerShare: { sharePNG: async arg => { shares.push(arg); return { status: 'cancelled' }; } },
        } } : undefined },
        URL: url, Blob, File, setTimeout: fn => { fn(); return 0; },
        navigator: share ? { canShare: () => true, share: async arg => { shares.push(arg); } } : {},
        document: { createElement: tag => tag === 'a' ? { click() { links.push(this.download); } } : (() => {
            const drawing = [];
            drawings.push(drawing);
            return { isConnected: true, width: 0, height: 0, getContext: () => ({
                drawImage: (...args) => drawing.push(args), fillRect() {}, fillText: value => texts.push(value),
                createLinearGradient: () => ({ addColorStop() {} }),
            }), toBlob: callback => {
                blobCount++;
                if (delayFirstBlob && blobCount === 1) heldBlob = callback;
                else callback(new Blob(['png'], { type: 'image/png' }));
            } };
        })() },
        Image: class { naturalWidth = 1200; naturalHeight = 800; set src(_) { queueMicrotask(() => this.onload()); } },
        FileReader: class { readAsDataURL() { this.result = 'data:image/png;base64,cG5n'; this.onload(); } },
    };
    vm.createContext(context); vm.runInContext(source, context);
    return { api: context.window.DietShare, context, drawings, links, shares, texts,
        releaseBlob: () => heldBlob(new Blob(['old'], { type: 'image/png' })),
        canvas: { isConnected: true, getContext: () => ({ drawImage() {} }) },
        file: new File(['photo'], 'photo.jpg', { type: 'image/jpeg' }),
        values: ['320', '25', '', '12'], framing: { scale: 1, x: 0, y: 0 } };
}

test('prévia 9:16 usa cover, limita deslocamento e mantém ausências como traço', async () => {
    const h = harness(); const states = [];
    await h.api.updatePreview(h.canvas, h.file, h.values, { scale: 1, x: 500, y: -500 }, (state) => states.push(state));
    assert.deepEqual(states, ['preparing', 'ready']);
    assert.equal(h.canvas.width, 1080); assert.equal(h.canvas.height, 1920);
    const [, x, y, width, height] = h.drawings[0][0];
    assert.ok(x <= 0 && x + width >= 1080);
    assert.ok(y <= 0 && y + height >= 1920);
    assert.ok(h.texts.includes('—'));
    await assert.rejects(h.api.sharePrepared(h.file, h.values, h.framing), /Aguarde/);
});

test('resultado assíncrono antigo não substitui enquadramento novo', async () => {
    const h = harness({ delayFirstBlob: true }); const states = [];
    const old = h.api.updatePreview(h.canvas, h.file, h.values, h.framing, state => states.push(state));
    await new Promise(resolve => setImmediate(resolve));
    await h.api.updatePreview(h.canvas, h.file, h.values, { scale: 2, x: 40, y: -30 }, state => states.push(state));
    h.releaseBlob(); await old;
    assert.equal(states.filter(state => state === 'ready').length, 1);
    assert.equal((await h.api.sharePrepared(h.file, h.values, { scale: 2, x: 40, y: -30 })).status, 'download-started');
});

test('trocar valores invalida o PNG anterior; navegador compartilha arquivo pronto', async () => {
    const h = harness({ share: true });
    await h.api.updatePreview(h.canvas, h.file, h.values, h.framing, () => {});
    await assert.rejects(h.api.sharePrepared(h.file, ['321', '25', '', '12'], h.framing), /Aguarde/);
    assert.equal((await h.api.sharePrepared(h.file, h.values, h.framing)).status, 'shared');
    assert.equal(h.shares[0].files[0].name, 'macros-card.png');
    h.context.navigator.share = async () => { throw Object.assign(new Error('cancelled'), { name: 'AbortError' }); };
    assert.equal((await h.api.sharePrepared(h.file, h.values, h.framing)).status, 'cancelled');
});

test('iOS usa plugin existente e navegador sem share baixa PNG', async () => {
    const ios = harness({ native: true });
    await ios.api.updatePreview(ios.canvas, ios.file, ios.values, ios.framing, () => {});
    assert.equal((await ios.api.sharePrepared(ios.file, ios.values, ios.framing)).status, 'cancelled');
    assert.equal(ios.shares[0].filename, 'macros-card.png');
    assert.equal(ios.shares[0].base64, 'cG5n');
    const web = harness();
    await web.api.updatePreview(web.canvas, web.file, web.values, web.framing, () => {});
    assert.equal((await web.api.sharePrepared(web.file, web.values, web.framing)).status, 'download-started');
    assert.deepEqual(web.links, ['macros-card.png']);
});
