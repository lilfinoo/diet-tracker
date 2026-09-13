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
    window.formatDietPlanItem = formatDietPlanItem;
    window.formatDietPlanItemsText = formatDietPlanItemsText;
}

if (typeof window !== "undefined" && typeof window.fetch === "function" && !window.__csrfFetchPatched) {
    const originalFetch = window.fetch.bind(window);
    window.__csrfFetchPatched = true;
    window.fetch = function(input, init = {}) {
        const request = typeof input === "string" ? new Request(input, init) : new Request(input, init);
        const method = (request.method || "GET").toUpperCase();
        const unsafe = !["GET", "HEAD", "OPTIONS", "TRACE"].includes(method);
        const url = new URL(request.url, window.location.origin);
        const isApiRequest = url.origin === window.location.origin && url.pathname.startsWith("/api/");
        if (unsafe && isApiRequest && csrfToken) {
            const headers = new Headers(request.headers);
            if (!headers.has("X-CSRF-Token")) headers.set("X-CSRF-Token", csrfToken);
            return originalFetch(new Request(request, { headers }));
        }
        return originalFetch(request);
    };
}

function localDateInputValue(date = new Date()) {
    const offsetDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
    return offsetDate.toISOString().slice(0, 10);
}
