const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function harness() {
    let user = { id: 'uuid-a' };
    const calls = [];
    const monthly = { identifier: '$rc_monthly', presentedOfferingContext: { offeringIdentifier: 'default' }, product: { identifier: 'ai.fittracker.premium.monthly', priceString: 'R$ 20,00', introPrice: { price: 0, period: 'P1W', cycles: 1 } } };
    const sdk = {
        configure: async args => calls.push(['configure', args]),
        logIn: async args => calls.push(['logIn', args]),
        getOfferings: async () => ({ current: { availablePackages: [monthly, { product: { identifier: 'test_monthly' } }] } }),
        checkTrialOrIntroductoryPriceEligibility: async () => ({ [monthly.product.identifier]: { status: 2 } }),
        purchasePackage: async args => calls.push(['purchase', args]),
        restorePurchases: async () => calls.push(['restore']),
    };
    const context = { window: { Capacitor: { getPlatform: () => 'ios', registerPlugin: () => sdk } }, fetch: async (url, args) => {
        calls.push(['fetch', url, args]);
        return { ok: true, json: async () => url.endsWith('/config') ? { configured: true, public_api_key: 'appl_public' } : { is_premium: true } };
    } };
    vm.createContext(context);
    vm.runInContext(fs.readFileSync('copilot/js/native-billing.js', 'utf8'), context);
    return { billing: context.window.NativeBilling, calls, sdk, monthly, getUser: () => user, setUser: value => { user = value; } };
}
test('purchase identifies session UUID and confirms through server, without trusting client entitlement', async () => {
    const h = harness();
    const result = await h.billing.transaction('purchase', 'premium_student', '/api', h.getUser);
    assert.equal(result.is_premium, true);
    assert.equal(h.calls.find(c => c[0] === 'configure')[1].appUserID, 'uuid-a');
    assert.equal(h.calls.find(c => c[0] === 'purchase')[1].aPackage.product.identifier, 'ai.fittracker.premium.monthly');
    const sync = h.calls.find(c => c[1] === '/api/billing/revenuecat/sync');
    assert.equal(sync[2].method, 'POST');
    assert.equal(sync[2].credentials, 'include');
    assert.equal(sync[2].body, undefined);
});
test('restoration and switching accounts use current UUID', async () => {
    const h = harness();
    await h.billing.transaction('restore', null, '/api', h.getUser);
    h.setUser({ id: 'uuid-b' });
    await h.billing.transaction('restore', null, '/api', h.getUser);
    assert.equal(h.calls.filter(c => c[0] === 'restore').length, 2);
    assert.equal(h.calls.find(c => c[0] === 'logIn')[1].appUserID, 'uuid-b');
});
test('guests and account changes during purchase cannot sync to another user', async () => {
    const h = harness();
    h.setUser(null);
    await assert.rejects(h.billing.transaction('purchase', 'premium_student', '/api', h.getUser), /Entre novamente/);
    assert.equal(h.calls.length, 0);
    h.setUser({ id: 'uuid-a' });
    h.sdk.purchasePackage = async () => { h.setUser({ id: 'uuid-b' }); };
    await assert.rejects(h.billing.transaction('purchase', 'premium_student', '/api', h.getUser), /Entre novamente/);
    assert.equal(h.calls.filter(c => c[1]?.endsWith?.('/sync')).length, 0);
});
test('only eligible actual free seven-day offer is advertised', async () => {
    const h = harness();
    const offerings = await h.billing.offerings('/api', h.getUser);
    assert.equal(Object.keys(offerings.packages).length, 1);
    assert.equal(h.billing.hasSevenDayTrial(h.monthly, offerings.eligibility), true);
    assert.equal(h.billing.hasSevenDayTrial(h.monthly, {}), false);
    assert.equal(h.billing.hasSevenDayTrial({ product: { ...h.monthly.product, introPrice: { price: 1, period: 'P1W', cycles: 1 } } }, offerings.eligibility), false);
});
test('cancelled and pending purchases never sync or unlock access', async () => {
    const h = harness();
    h.sdk.purchasePackage = async () => { throw { code: '1', userInfo: { userCancelled: true } }; };
    await assert.rejects(h.billing.transaction('purchase', 'premium_student', '/api', h.getUser));
    assert.equal(h.billing.cancelled({ code: '1' }), true);
    assert.equal(h.billing.cancelled({ code: '20' }), false);
    assert.equal(h.calls.filter(c => c[1]?.endsWith?.('/sync')).length, 0);
});
