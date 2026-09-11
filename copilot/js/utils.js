function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    })[character]);
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

async function waitForAIJob(initial, timeoutMilliseconds = 10 * 60 * 1000) {
    if (!initial?.job_id) return initial;
    const statusUrl = initial.status_url || `/api/ai/tasks/${encodeURIComponent(initial.job_id)}`;
    const deadline = Date.now() + timeoutMilliseconds;
    while (Date.now() < deadline) {
        const response = await fetch(statusUrl, { credentials: "include", cache: "no-store" });
        let data = {};
        try { data = await response.json(); } catch (error) { data = {}; }
        if (!response.ok) {
            const requestError = new Error(data.error || "Não foi possível consultar a tarefa de IA.");
            requestError.status = response.status;
            throw requestError;
        }
        if (data.status === "succeeded") return data.result;
        if (data.status === "failed") {
            const requestError = new Error(data.result?.error || data.error || "A tarefa de IA não foi concluída.");
            requestError.status = data.http_status || 503;
            requestError.data = data.result || data;
            throw requestError;
        }
        await wait(Math.max(1000, Number(response.headers.get("Retry-After") || 2) * 1000));
    }
    throw new Error("A tarefa continua sendo processada. Você pode fechar esta tela e consultar o resultado mais tarde.");
}

if (typeof window !== "undefined") window.waitForAIJob = waitForAIJob;

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
