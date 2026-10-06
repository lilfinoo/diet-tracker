(function () {
    'use strict';
    const products = {
        premium_student: 'ai.fittracker.premium.monthly',
        premium_student_annual: 'ai.fittracker.premium.annual',
    };
    let purchases, configured = false, owner = null, queue = Promise.resolve(), busy = false, transactionOwner = null;
    function native() { return window.Capacitor?.getPlatform?.() === 'ios'; }
    function plugin() {
        if (!native()) throw new Error('Compras da Apple disponíveis somente no app para iPhone.');
        purchases ||= window.Capacitor?.Plugins?.Purchases || window.Capacitor?.registerPlugin?.('Purchases');
        if (!purchases) throw new Error('Atualize o app para habilitar as compras da Apple.');
        return purchases;
    }
    function assertOwner(id, getUser) {
        if (!id || getUser()?.id !== id) throw new Error('Entre novamente na sua conta para continuar.');
    }
    async function identify(id, api, getUser) {
        const next = queue.catch(() => {}).then(async () => {
            assertOwner(id, getUser);
            if (busy && transactionOwner !== id) throw new Error('Aguarde a operação de compra atual.');
            const sdk = plugin();
            if (!configured) {
                const response = await fetch(`${api}/billing/revenuecat/config`, { credentials: 'include' });
                const config = await response.json();
                if (!response.ok || !config.configured || !config.public_api_key?.startsWith('appl_')) {
                    throw new Error('As compras da Apple ainda não estão configuradas.');
                }
                assertOwner(id, getUser);
                await sdk.configure({ apiKey: config.public_api_key, appUserID: id });
                configured = true;
                owner = id;
            } else if (owner !== id) {
                await sdk.logIn({ appUserID: id });
                owner = id;
            }
            assertOwner(id, getUser);
            return sdk;
        });
        queue = next;
        return next;
    }
    async function offerings(api, getUser) {
        const id = getUser()?.id;
        if (!id) throw new Error('Entre na sua conta para ver os planos da App Store.');
        const sdk = await identify(id, api, getUser);
        const result = await sdk.getOfferings();
        assertOwner(id, getUser);
        const packages = result.current?.availablePackages || [];
        const selected = {};
        for (const [code, identifier] of Object.entries(products)) {
            const item = packages.find(item => item.product.identifier === identifier);
            if (item) selected[code] = item;
        }
        if (!Object.keys(selected).length) throw new Error('Os planos ainda não estão disponíveis na App Store. Tente novamente mais tarde.');
        let eligibility = {};
        try {
            eligibility = await sdk.checkTrialOrIntroductoryPriceEligibility({ productIdentifiers: Object.values(selected).map(item => item.product.identifier) });
        } catch (_) { /* Exibir o preço normal quando a elegibilidade não puder ser confirmada. */ }
        assertOwner(id, getUser);
        return { packages: selected, eligibility };
    }
    function hasSevenDayTrial(item, eligibility) {
        const intro = item?.product?.introPrice;
        return eligibility?.[item?.product?.identifier]?.status === 2 && intro?.price === 0 &&
            (intro.period === 'P1W' || intro.period === 'P7D') && intro.cycles === 1;
    }
    async function sync(api, id, getUser) {
        assertOwner(id, getUser);
        const response = await fetch(`${api}/billing/revenuecat/sync`, { method: 'POST', credentials: 'include' });
        const result = await response.json();
        assertOwner(id, getUser);
        if (!response.ok) throw new Error(result.error || 'Não foi possível confirmar a assinatura. Use Restaurar compras para tentar novamente.');
        return result;
    }
    async function transaction(kind, code, api, getUser) {
        if (busy) throw new Error('Aguarde a operação atual.');
        busy = true;
        transactionOwner = getUser()?.id;
        try {
            const id = getUser()?.id;
            const sdk = await identify(id, api, getUser);
            if (kind === 'restore') await sdk.restorePurchases();
            else {
                const result = await offerings(api, getUser);
                const item = result.packages[code];
                if (!item) throw new Error('Este plano não está disponível na App Store.');
                assertOwner(id, getUser);
                await sdk.purchasePackage({ aPackage: item });
            }
            return await sync(api, id, getUser);
        } finally { busy = false; transactionOwner = null; }
    }
    async function refresh(api, getUser) {
        if (!native() || busy || !getUser()?.id) return null;
        const id = getUser().id;
        await identify(id, api, getUser);
        return sync(api, id, getUser);
    }
    function cancelled(error) {
        return error?.userCancelled === true || error?.userInfo?.userCancelled === true || String(error?.code) === '1';
    }
    async function manage() {
        if (!native()) return;
        const bridge = window.Capacitor?.Plugins?.FitTrackerBilling || window.Capacitor?.registerPlugin?.('FitTrackerBilling');
        if (!bridge) throw new Error('Não foi possível abrir as assinaturas da Apple.');
        await bridge.manageSubscriptions();
    }
    window.NativeBilling = { native, offerings, hasSevenDayTrial, transaction, refresh, cancelled, manage };
})();
