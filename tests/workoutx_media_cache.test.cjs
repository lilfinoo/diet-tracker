const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../copilot/script.js'), 'utf8');
const start = source.indexOf('function exerciseImagePath(');
const end = source.indexOf('\nfunction exerciseFallbackImagePath(', start);

for (const platform of ['web', 'ios']) {
    test(`${platform} requests a new GIF URL after the Basic upgrade`, () => {
        const context = {
            API_BASE: 'https://fit.test/api',
            document: {documentElement: {dataset: {nativePlatform: platform}}},
        };
        vm.createContext(context);
        vm.runInContext(source.slice(start, end), context);
        const route = platform === 'ios' ? '/public/exercise-media/' : '/exercise-media/';
        assert.equal(context.exerciseImagePath('Supino', 'workoutx:0289'),
            `https://fit.test/api${route}workoutx%3A0289?v=workoutx-basic-20261006-2`);
        assert.equal(context.exerciseImagePath('Sem imagem', ''), '');
    });
}
