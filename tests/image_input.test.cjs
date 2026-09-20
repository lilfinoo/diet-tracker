const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../copilot/js/image-input.js'), 'utf8');

function harness(camera, platform = 'ios') {
    const input = { value: 'old', clicks: 0, click() { this.clicks += 1; } };
    class TestFile {
        constructor(parts, name, options) { this.parts = parts; this.name = name; this.type = options.type; }
    }
    const context = {
        window: { Capacitor: { Plugins: { Camera: camera }, getPlatform: () => platform, isNativePlatform: () => platform !== 'web' } },
        document: { documentElement: { dataset: { nativePlatform: platform } }, getElementById: () => input },
        fetch: async () => ({ ok: true, blob: async () => new Blob(['image'], { type: 'image/jpeg' }) }),
        Blob,
        File: TestFile,
    };
    vm.createContext(context);
    vm.runInContext(source, context);
    return { picker: context.window.FitTrackerImagePicker, input };
}

test('iOS camera uses the current Capacitor API and returns its image file', async () => {
    const calls = [];
    const { picker, input } = harness({
        checkPermissions: async () => ({ camera: 'prompt' }),
        requestPermissions: async options => { calls.push(['permission', options]); return { camera: 'granted' }; },
        takePhoto: async options => { calls.push(['take', options]); return { webPath: 'capacitor://photo.jpg' }; },
    });
    let received;
    const file = await picker.open({ inputId: 'photo', source: 'CAMERA', onFile: image => { received = image; } });
    assert.equal(file, received);
    assert.equal(file.type, 'image/jpeg');
    assert.equal(calls[0][0], 'permission');
    assert.equal(calls[0][1].permissions[0], 'camera');
    assert.equal(calls[1][0], 'take');
    assert.equal(input.clicks, 0);
});

test('cancelling the native camera does not open the browser fallback', async () => {
    const { picker, input } = harness({
        requestPermissions: async () => ({ camera: 'granted' }),
        takePhoto: async () => { throw new Error('User cancelled photos app'); },
    });
    assert.equal(await picker.open({ inputId: 'photo', source: 'CAMERA' }), null);
    assert.equal(input.clicks, 0);
});

test('a denied camera permission reports an actionable error', async () => {
    const { picker } = harness({ requestPermissions: async () => ({ camera: 'denied' }) });
    await assert.rejects(picker.open({ inputId: 'photo', source: 'CAMERA' }), error => {
        assert.equal(error.code, 'permission_denied'); return /ajustes do dispositivo/.test(error.message);
    });
});
test('permissão já concedida abre sem solicitar novamente', async () => {
    let requests = 0, takes = 0;
    const { picker } = harness({
        checkPermissions: async () => ({ camera: 'granted' }),
        requestPermissions: async () => { requests++; return { camera: 'granted' }; },
        takePhoto: async () => { takes++; return { uri: 'camera://photo.jpg' }; },
    });
    await picker.open({ inputId: 'photo', source: 'CAMERA' });
    assert.equal(requests, 0); assert.equal(takes, 1);
});
test('câmera indisponível usa código estável e não abre fallback', async () => {
    const { picker, input } = harness({
        checkPermissions: async () => ({ camera: 'granted' }),
        takePhoto: async () => { throw Object.assign(new Error('No camera available'), { code: 'OS-PLUG-CAMR-0007' }); },
    });
    await assert.rejects(picker.open({ inputId: 'photo', source: 'CAMERA' }), error => error.code === 'camera_unavailable');
    assert.equal(input.clicks, 0);
});
test('fototeca aceita acesso limitado e usa chooseFromGallery', async () => {
    let chosen = 0;
    const { picker } = harness({
        checkPermissions: async () => ({ photos: 'limited' }),
        chooseFromGallery: async () => { chosen++; return { results: [{ uri: 'photos://image.jpg' }] }; },
    }, 'android');
    await picker.open({ inputId: 'photo', source: 'PHOTOS' }); assert.equal(chosen, 1);
});
test('negação nativa da fototeca é normalizada', async () => {
    const { picker } = harness({
        checkPermissions: async () => ({ photos: 'granted' }),
        chooseFromGallery: async () => { throw Object.assign(new Error('denied'), { code: 'OS-PLUG-CAMR-0005' }); },
    });
    await assert.rejects(picker.open({ inputId: 'photo', source: 'PHOTOS' }), error => error.code === 'permission_denied');
});
test('web usa o input de arquivo sem chamar plugin nativo', async () => {
    let takes = 0;
    const { picker, input } = harness({ takePhoto: async () => { takes++; } }, 'web');
    await picker.open({ inputId: 'photo', source: 'CAMERA' });
    assert.equal(input.clicks, 1); assert.equal(takes, 0);
});
