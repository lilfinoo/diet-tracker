const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const source = fs.readFileSync('copilot/script.js', 'utf8');
const flow = source.slice(source.indexOf('function initializeAppleAuth()'), source.indexOf('async function startNativeGoogleSignIn()'));
function harness({ failChallenge = false, cancel = false, signup = false } = {}) {
    const calls = [], messages = [], elements = new Map();
    const element = id => {
        if (!elements.has(id)) elements.set(id, { classList: { add() {}, remove() {} }, focus() {} });
        return elements.get(id);
    };
    const context = {
        Uint8Array, Array, JSON, Error, nativeAppleInFlight: false, nativeGoogleInFlight: false,
        authRequestInFlight: false, sessionConfirmationInFlight: false, API_BASE: '/api',
        googleSignupToken: null, socialSignupProvider: 'google',
        document: { querySelector: () => element('tabs'), querySelectorAll: () => [] },
        getElement: element, setGoogleAuthPending() {}, showAuthMessage: message => messages.push(message),
        completeAuthentication: async user => calls.push(['complete', user]),
        window: { crypto: webcrypto, Capacitor: { getPlatform: () => 'ios', Plugins: { FitTrackerAppleAuth: { signIn: async options => {
            calls.push(['native', options]);
            if (cancel) throw new Error('cancelled');
            return { idToken: 'credential', authorizationCode: 'authorization', displayName: 'Apple user' };
        } } } }, fetchWithTimeout: async (url, options) => {
            calls.push([url, JSON.parse(options.body)]);
            if (url.endsWith('challenge')) return { ok: !failChallenge, json: async () => ({ nonce: 'server-generated-nonce-01234567890123456789' }) };
            return { ok: !signup, status: signup ? 409 : 200, json: async () => signup ? { code: 'username_required', signup_token: 'signup' } : { user: { id: 'account' } } };
        } }
    };
    vm.createContext(context); vm.runInContext(flow, context);
    return { context, calls, messages };
}
test('Apple challenge precedes native prompt and forwards matching secure nonce plus authorization code', async () => {
    const { context, calls } = harness(); await context.startNativeAppleSignIn();
    assert.equal(calls[0][0], '/api/auth/apple/challenge');
    assert.equal(calls[1][1].nonce, 'server-generated-nonce-01234567890123456789');
    assert.equal(calls[2][1].nonce, calls[1][1].nonce);
    assert.equal(calls[2][1].authorization_code, 'authorization');
    assert.equal(calls[3][0], 'complete');
    assert.equal(context.nativeAppleInFlight, false);
});
test('failed challenge never opens native prompt or sends credential', async () => {
    const { context, calls, messages } = harness({ failChallenge: true }); await context.startNativeAppleSignIn();
    assert.equal(calls.length, 1); assert.equal(messages.length, 1);
});
test('cancelled Apple prompt never posts credential and leaves buttons ready', async () => {
    const { context, calls, messages } = harness({ cancel: true }); await context.startNativeAppleSignIn();
    assert.equal(calls.length, 2); assert.equal(messages.length, 0); assert.equal(context.nativeAppleInFlight, false);
});
test('Apple signup retains provider so username completion goes to Apple endpoint', async () => {
    const { context } = harness({ signup: true }); await context.startNativeAppleSignIn();
    assert.equal(context.socialSignupProvider, 'apple'); assert.equal(context.googleSignupToken, 'signup');
    const finish = source.slice(source.indexOf('async function finishGoogleSignup('), source.indexOf('async function completeAuthentication('));
    assert.ok(finish.includes('/auth/${socialSignupProvider}'));
});
