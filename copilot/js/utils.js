if (typeof document !== "undefined" && window.Capacitor?.getPlatform?.() === "ios") {
    document.documentElement.dataset.nativePlatform = "ios";
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    })[character]);
}

function normalizeDietFoodName(value) {
    return String(value || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, " ").trim();
}

function dietQuantityLabel(value) {
    const rounded = Math.round(value * 10) / 10;
    return Number.isInteger(rounded) ? String(rounded) : String(rounded).replace(".", ",");
}

function dietDomesticMeasure(name, quantity, unit) {
    const normalized = normalizeDietFoodName(name);
    const grams = unit === "kg" ? quantity * 1000 : quantity;
    const milliliters = unit === "l" ? quantity * 1000 : quantity;
    const metric = unit === "kg" ? `${dietQuantityLabel(quantity)} kg` : unit === "l" ? `${dietQuantityLabel(quantity)} L` : `${dietQuantityLabel(quantity)} ${unit}`;
    const measure = (label, plural, size) => {
        const count = Math.max(0.5, Math.round((grams / size) * 2) / 2);
        return `${dietQuantityLabel(count)} ${count === 1 ? label : plural} de ${name} (${metric})`;
    };

    if (unit === "g" || unit === "kg") {
        if (/\b(arroz|macarrao|massa|cuscuz|pure)\b/.test(normalized)) return measure("colher de servir", "colheres de servir", 75);
        if (/\b(feijao|lentilha|grao|graos)\b/.test(normalized)) return measure("concha", "conchas", 80);
        if (/\b(aveia|granola|farinha|pasta de amendoim)\b/.test(normalized)) return measure("colher de sopa", "colheres de sopa", 15);
        if (/\b(azeite|oleo)\b/.test(normalized)) return measure("colher de sopa", "colheres de sopa", 13);
        if (/\b(frango|carne|peixe|bife)\b/.test(normalized)) return measure("porção do tamanho da palma da mão", "porções do tamanho da palma da mão", 100);
        if (/\b(ovo)\b/.test(normalized)) return measure("unidade", "unidades", 50);
        if (/\b(banana)\b/.test(normalized)) return measure("unidade", "unidades", 90);
        if (/\b(maca|pera|laranja)\b/.test(normalized)) return measure("unidade", "unidades", 130);
        if (/\b(pao)\b/.test(normalized)) return measure("fatia", "fatias", 30);
        if (/\b(queijo)\b/.test(normalized)) return measure("fatia", "fatias", 30);
        if (/\b(iogurte)\b/.test(normalized)) return measure("pote", "potes", 170);
        return `1 porção de ${name} (${metric})`;
    }
    if (unit === "ml" || unit === "l") {
        if (/\b(leite|bebida|suco)\b/.test(normalized)) {
            const count = Math.max(0.5, Math.round((milliliters / 200) * 2) / 2);
            return `${dietQuantityLabel(count)} ${count === 1 ? "copo" : "copos"} de ${name} (${metric})`;
        }
        return `1 porção de ${name} (${metric})`;
    }
    return "";
}

function formatDietPlanItem(item) {
    if (item && typeof item === "object") {
        const quantity = Number(item.quantity);
        const unit = String(item.unit || "").toLowerCase().trim();
        const name = String(item.name || item.foodId || "").trim();
        const domestic = name && Number.isFinite(quantity) ? dietDomesticMeasure(name, quantity, unit) : "";
        return domestic || [Number.isFinite(quantity) ? dietQuantityLabel(quantity) : "", unit, name].filter(Boolean).join(" ");
    }
    const text = String(item || "").trim();
    const match = text.match(/^\s*(\d+(?:[.,]\d+)?)\s*(g|kg|ml|l)\s*(?:de\s+)?(.+?)\s*$/i);
    if (!match) return text;
    const quantity = Number(match[1].replace(",", "."));
    const unit = match[2].toLowerCase();
    return dietDomesticMeasure(match[3], quantity, unit) || text;
}

function formatDietPlanItemsText(meal) {
    const items = Array.isArray(meal?.items) ? meal.items.map(formatDietPlanItem).filter(Boolean) : [];
    if (items.length) return items.join(", ");
    const description = String(meal?.description || "").trim();
    return description ? description.split(/[,;]+/).map((item) => formatDietPlanItem(item)).filter(Boolean).join(", ") : "";
}

let csrfToken = null;

function setCsrfToken(token) {
    csrfToken = token ? String(token) : null;
    window.csrfToken = csrfToken;
}

function getCsrfToken() {
    return csrfToken;
}

function wait(milliseconds) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function fetchWithTimeout(input, init = {}, timeoutMilliseconds = 15_000) {
    const controller = new AbortController();
    const externalSignal = init.signal || input?.signal;
    let timedOut = false;
    const cancel = () => controller.abort(externalSignal.reason);
    const cleanup = () => {
        window.clearTimeout(timeout);
        externalSignal?.removeEventListener('abort', cancel);
    };
    const timeout = window.setTimeout(() => {
        timedOut = true;
        controller.abort();
        cleanup();
    }, timeoutMilliseconds);
    if (externalSignal?.aborted) cancel();
    else externalSignal?.addEventListener('abort', cancel, { once: true });
    const requestError = error => {
        if (!timedOut) return error;
        const result = new Error('A solicitação demorou demais. Tente novamente.');
        result.name = 'TimeoutError';
        return result;
    };
    const withAbort = async operation => {
        let onAbort;
        try {
            return await Promise.race([
                Promise.resolve().then(() => {
                    if (controller.signal.aborted) throw controller.signal.reason;
                    return operation();
                }),
                new Promise((_, reject) => {
                    onAbort = () => reject(controller.signal.reason);
                    controller.signal.addEventListener('abort', onAbort, { once: true });
                })
            ]);
        } catch (error) {
            throw requestError(error);
        } finally {
            controller.signal.removeEventListener('abort', onAbort);
        }
    };
    try {
        const response = await withAbort(() => fetch(input, { ...init, signal: controller.signal }));
        // Keep the original Response (headers, URL and status) and the same deadline
        // until its body is consumed. Receiving headers alone does not finish a read.
        for (const method of ['json', 'text', 'blob', 'arrayBuffer', 'formData']) {
            if (typeof response[method] !== 'function') continue;
            const consume = response[method].bind(response);
            response[method] = async () => {
                try { return await withAbort(consume); }
                finally { cleanup(); }
            };
        }
        if (response.status === 204 || response.status === 205 || init.method === 'HEAD') cleanup();
        return response;
    } catch (error) {
        cleanup();
        throw error;
    }
}

const AppReadCache = (() => {
    const entries = new Map();
    const pending = new Map();
    let version = 0;
    let accountVersion = 0;
    const cancelled = () => new DOMException('Leitura substituída por uma atualização.', 'AbortError');
    return {
        get version() { return version; },
        get accountVersion() { return accountVersion; },
        peek(key) { return entries.get(key) || null; },
        read(key, loader, { ttl = 0, force = false } = {}) {
            const existing = pending.get(key);
            if (existing) return existing.promise;
            const cached = entries.get(key);
            if (!force && cached && Date.now() - cached.at < ttl) return Promise.resolve(cached.data);
            const controller = new AbortController();
            const request = { controller, promise: null };
            request.promise = Promise.resolve().then(() => {
                if (controller.signal.aborted) throw cancelled();
                return loader({ signal: controller.signal });
            }).then(data => {
                if (pending.get(key) !== request || controller.signal.aborted) throw cancelled();
                entries.set(key, { data, at: Date.now() });
                return data;
            }).catch(error => {
                if (controller.signal.aborted || pending.get(key) !== request) throw cancelled();
                throw error;
            }).finally(() => {
                if (pending.get(key) === request) pending.delete(key);
            });
            pending.set(key, request);
            return request.promise;
        },
        invalidate(prefix = '') {
            version += 1;
            for (const key of entries.keys()) if (key.startsWith(prefix)) entries.delete(key);
            for (const [key, request] of pending) {
                if (!key.startsWith(prefix)) continue;
                pending.delete(key);
                request.controller.abort();
            }
        },
        reset() { accountVersion += 1; this.invalidate(); }
    };
})();

async function readApiJson(url, { signal } = {}) {
    for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
            const response = await fetchWithTimeout(url, { credentials: 'include', signal });
            const data = await response.json();
            if (!response.ok) {
                const error = new Error(data.error || 'Não foi possível carregar agora.');
                error.status = response.status;
                throw error;
            }
            return data;
        } catch (error) {
            const transient = error.name !== 'AbortError' && (!error.status || error.status >= 500);
            if (attempt || !transient || signal?.aborted) throw error;
            await wait(1000);
            if (signal?.aborted) throw new DOMException('Leitura cancelada.', 'AbortError');
        }
    }
}

async function waitForAIJob(initial, timeoutMilliseconds = 10 * 60 * 1000, options = {}) {
    if (!initial?.job_id) return initial;
    const jobLabel = options.jobLabel || "plano";
    const statusUrl = initial.status_url || `/api/ai/tasks/${encodeURIComponent(initial.job_id)}`;
    const deadline = Date.now() + timeoutMilliseconds;
    options.onStatus?.("queued", initial);
    while (Date.now() < deadline) {
        let response;
        try {
            response = await fetch(statusUrl, { credentials: "include", cache: "no-store" });
        } catch (error) {
            const requestError = new Error(`Não foi possível verificar a geração do ${jobLabel} agora.`);
            requestError.code = "ai_job_check_failed";
            requestError.job = initial;
            throw requestError;
        }
        let data = {};
        try { data = await response.json(); } catch (error) { data = {}; }
        if (!response.ok) {
            const requestError = new Error(data.error || "Não foi possível consultar a tarefa de IA.");
            requestError.status = response.status;
            requestError.code = "ai_job_check_failed";
            requestError.job = initial;
            throw requestError;
        }
        if (data.status === "succeeded") return data.result;
        if (data.status === "failed") {
            const requestError = new Error(data.result?.error || data.error || "A tarefa de IA não foi concluída.");
            requestError.status = data.http_status || 503;
            requestError.data = data.result || data;
            requestError.fields = requestError.data?.fields && typeof requestError.data.fields === "object" ? requestError.data.fields : {};
            requestError.code = "ai_job_failed";
            requestError.job = initial;
            throw requestError;
        }
        options.onStatus?.(data.status || "running", data);
        await wait(Math.max(1000, Number(response.headers.get("Retry-After") || 2) * 1000));
    }
    const timeoutError = new Error("A criação ainda está em andamento. Verifique o resultado sem gerar outro treino.");
    timeoutError.code = "ai_job_timeout";
    timeoutError.job = initial;
    throw timeoutError;
}

if (typeof window !== "undefined") {
    window.waitForAIJob = waitForAIJob;
    window.fetchWithTimeout = fetchWithTimeout;
    window.AppReadCache = AppReadCache;
    window.readApiJson = readApiJson;
    if (window.Capacitor?.getPlatform?.() === 'ios') document.documentElement.dataset.nativePlatform = 'ios';
    window.formatDietPlanItem = formatDietPlanItem;
    window.formatDietPlanItemsText = formatDietPlanItemsText;
}

if (typeof window !== "undefined" && typeof window.fetch === "function" && !window.__csrfFetchPatched) {
    const originalFetch = window.fetch.bind(window);
    window.__csrfFetchPatched = true;
    window.fetch = async function(input, init = {}) {
        const configuredOrigin = window.FIT_TRACKER_CONFIG?.apiOrigin || document.querySelector('meta[name="fit-tracker-api-origin"]')?.content || window.location.origin;
        const configuredApiOrigin = (document.documentElement.dataset.nativePlatform === "ios" ? configuredOrigin : window.location.origin).replace(/\/$/, "");
        const inputUrl = new URL(typeof input === "string" ? input : input.url, window.location.origin);
        if (inputUrl.pathname.startsWith("/api/") && inputUrl.origin === window.location.origin && configuredApiOrigin !== window.location.origin) {
            const rewritten = `${configuredApiOrigin}${inputUrl.pathname}${inputUrl.search}`;
            input = input instanceof Request ? new Request(rewritten, input) : rewritten;
        }
        const request = new Request(input, init);
        const method = (request.method || "GET").toUpperCase();
        const unsafe = !["GET", "HEAD", "OPTIONS", "TRACE"].includes(method);
        const url = new URL(request.url, window.location.origin);
        const isApiRequest = url.pathname.startsWith("/api/") && (url.origin === window.location.origin || url.origin === configuredApiOrigin);
        let prepared = request;
        if (unsafe && isApiRequest) {
            const headers = new Headers(request.headers);
            if (csrfToken && !headers.has("X-CSRF-Token")) headers.set("X-CSRF-Token", csrfToken);
            if (window.AppOffline?.allowedMutation(url, method) && !headers.has("Idempotency-Key")) {
                headers.set("Idempotency-Key", window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`);
            }
            prepared = new Request(request, { headers });
        }
        const ownerVersion = AppReadCache.accountVersion;
        if (window.AppOffline?.allowedMutation(url, method) && navigator.onLine === false && !request.headers.has("X-Offline-Replay")) {
            return window.AppOffline.enqueue(prepared, url);
        }
        try {
            const response = await originalFetch(prepared);
            if (response.ok && unsafe && isApiRequest && ownerVersion === AppReadCache.accountVersion &&
                /^\/api\/(diet(?:\/|$)|diet_plans(?:\/|$)|profile(?:\/|$))/.test(url.pathname)) {
                AppReadCache.invalidate('diet:');
            }
            if (response.ok && isApiRequest && (!unsafe || /\/replacement_options(?:\?|$)/.test(url.pathname))) window.AppOffline?.saveSnapshot(url, response);
            if (response.ok && unsafe) window.AppOffline?.sync();
            return response;
        } catch (error) {
            if (window.AppOffline?.allowedMutation(url, method) && !request.signal?.aborted && !request.headers.has("X-Offline-Replay")) {
                return window.AppOffline.enqueue(prepared, url, "connection");
            }
            if (!unsafe && isApiRequest && window.AppOffline) {
                const cached = await window.AppOffline.readSnapshot(url);
                if (cached?.data) {
                    document.body.dataset.offline = "true";
                    window.updateOfflineStatus?.();
                    return new Response(JSON.stringify(cached.data), { status: 200, headers: { "Content-Type": "application/json", "X-FitTracker-Cache": "stale" } });
                }
            }
            throw error;
        }
    };
}

function localDateInputValue(date = new Date()) {
    const offsetDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
    return offsetDate.toISOString().slice(0, 10);
}
