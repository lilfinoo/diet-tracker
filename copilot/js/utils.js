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
