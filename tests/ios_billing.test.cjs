const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../copilot/script.js'), 'utf8');
const notice = 'Assinaturas pelo iPhone estarão disponíveis após a integração com a App Store';
const tick = () => new Promise(resolve => setImmediate(resolve));

function harness(platform = 'ios', subscription = null) {
    const elements = new Map(), calls = [], opened = [], toasts = [];
    const options = [{ disabled: false }, { disabled: false }];
    let authenticated = 0;
    const plans = {
        provider_configured: true, provider_environment: 'production',
        plans: [
            { code: 'free', name: 'Gratuito', price_brl: 0, features: ['Registro de refeições'] },
            { code: 'premium_student', name: 'Premium mensal', price_brl: 30, features: ['Planos com IA'] },
            { code: 'premium_student_annual', name: 'Premium anual', price_brl: 240, discount_percent: 33, monthly_equivalent_brl: 20, features: [] },
        ],
    };
    const context = {
        API_BASE: 'https://api.example/api', currentUser: { plan_code: 'free', is_premium: Boolean(subscription) },
        window: { Capacitor: { getPlatform: () => platform }, location: { href: 'capacitor://localhost' }, confirm: () => true },
        document: { querySelectorAll: () => options },
        getElement(id) {
            if (!elements.has(id)) elements.set(id, { id, innerHTML: '', textContent: '' });
            return elements.get(id);
        },
        escapeHtml: value => String(value ?? ''),
        openAppModal: element => opened.push(element.id), closeAppModal() {},
        requireAuth() { authenticated++; return true; },
        showToast: (message, kind) => toasts.push({ message, kind }), checkAuthStatus: async () => {},
        fetch: async (url, init) => {
            calls.push({ url, init });
            const data = url.endsWith('/plans') ? plans
                : url.endsWith('/subscription') ? { subscription, pix_renewal_available_at: '2020-01-01' }
                : url.endsWith('/billing/cancel') ? { message: 'Assinatura cancelada.' }
                : { checkout_url: 'https://checkout.example/payment' };
            return { ok: true, json: async () => data };
        },
    };
    vm.createContext(context);
    vm.runInContext(source.slice(source.indexOf('const IOS_BILLING_NOTICE'), source.indexOf('function closePlansModal(')), context);
    return { context, elements, calls, opened, toasts, options, authenticated: () => authenticated };
}

test('iOS shows plan features without Asaas prices, discounts or checkout actions', async () => {
    const { context: c, elements } = harness();
    await c.openPlansModal();
    const html = elements.get('plansGrid').innerHTML;
    assert.match(html, /Premium mensal/);
    assert.match(html, /Planos com IA/);
    assert.match(html, /Grátis/);
    assert.match(html, /disabled>Indisponível no iPhone/);
    assert.doesNotMatch(html, /R\$|desconto|startBillingCheckout|Escolher pagamento/);
    assert.equal(elements.get('billingNotice').textContent, notice);
});

test('iOS blocks direct and stale checkout calls before authentication, UI changes or network', async () => {
    const h = harness();
    const button = { disabled: false };
    h.context.startBillingCheckout('premium_student', button);
    assert.equal(h.authenticated(), 0);
    assert.equal(vm.runInContext('pendingBillingCheckout', h.context), null);
    h.context.staleCheckout = { planCode: 'premium_student', button };
    vm.runInContext('pendingBillingCheckout = staleCheckout', h.context);
    for (const method of ['credit_card', 'pix']) await h.context.confirmBillingCheckout(method);
    assert.equal(button.disabled, false);
    assert.ok(h.options.every(option => !option.disabled));
    assert.equal(h.elements.size, 0);
    assert.equal(h.opened.length, 0);
    assert.equal(h.calls.length, 0);
    assert.equal(h.context.window.location.href, 'capacitor://localhost');
    assert.equal(h.toasts.length, 3);
    assert.ok(h.toasts.every(toast => toast.message === notice));
});

test('web retains Asaas prices and both payment methods with checkout redirect', async () => {
    for (const method of ['credit_card', 'pix']) {
        const h = harness('web');
        await h.context.openPlansModal();
        const html = h.elements.get('plansGrid').innerHTML;
        assert.match(html, /R\$ 30/);
        assert.match(html, /33% de desconto/);
        assert.match(html, /startBillingCheckout/);
        assert.match(h.elements.get('billingNotice').textContent, /Cartão renova/);
        const button = { disabled: false };
        h.context.startBillingCheckout('premium_student', button);
        assert.equal(h.authenticated(), 1);
        assert.ok(h.opened.includes('billingPaymentModal'));
        await h.context.confirmBillingCheckout(method);
        const checkout = h.calls.find(call => call.url.endsWith('/billing/checkout'));
        assert.equal(checkout.init.method, 'POST');
        assert.equal(checkout.init.credentials, 'include');
        assert.deepEqual(JSON.parse(checkout.init.body), { plan_code: 'premium_student', payment_method: method });
        assert.equal(h.context.window.location.href, 'https://checkout.example/payment');
    }
});

test('PIX renewal is available on web and suppressed on iOS while access stays visible', async () => {
    for (const platform of ['ios', 'web']) {
        const h = harness(platform, { provider: 'asaas_pix', status: 'active', plan_code: 'premium_student', current_period_end: '2030-01-01' });
        h.context.renderSubscriptionManagement(true);
        await tick();
        const html = h.elements.get('subscriptionManage').innerHTML;
        assert.match(html, /Acesso PIX/);
        assert.match(html, /Ativo até/);
        if (platform === 'ios') assert.doesNotMatch(html, /Renovar por PIX|startBillingCheckout|renovação abre/);
        else assert.match(html, /Renovar por PIX/);
    }
});

test('iOS retains cancellation of an existing Asaas subscription', async () => {
    const h = harness('ios', { provider: 'asaas', status: 'active', plan_code: 'premium_student', current_period_end: '2030-01-01' });
    h.context.renderSubscriptionManagement(true);
    await tick();
    assert.match(h.elements.get('subscriptionManage').innerHTML, /cancelMySubscription/);
    await h.context.cancelMySubscription();
    const cancellation = h.calls.find(call => call.url.endsWith('/billing/cancel'));
    assert.equal(cancellation.init.method, 'POST');
    assert.equal(cancellation.init.credentials, 'include');
    assert.ok(h.toasts.some(toast => toast.message === 'Assinatura cancelada.'));
    assert.ok(h.calls.every(call => !call.url.endsWith('/billing/checkout')));
});
