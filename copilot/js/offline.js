/* Persistent offline snapshots, mutations and media for the native/web shell. */
(() => {
    "use strict";

    const DB_NAME = "fittracker-offline";
    const DB_VERSION = 1;
    const STORES = { snapshots: "snapshots", outbox: "outbox", media: "media" };
    const configuredOrigin = window.FIT_TRACKER_CONFIG?.apiOrigin || document.querySelector('meta[name="fit-tracker-api-origin"]')?.content || window.location.origin;
    const API_ORIGIN = (document.documentElement.dataset.nativePlatform === "ios" ? configuredOrigin : window.location.origin).replace(/\/$/, "");
    const memorySnapshots = new Map();
    let dbPromise = null;
    let syncing = null;

    function accountId() {
        return String(window.currentUser?.id || "anonymous");
    }

    function keyFor(key, userId = accountId()) {
        return `${userId}:${key}`;
    }

    function openDb() {
        if (dbPromise) return dbPromise;
        if (!window.indexedDB) return Promise.resolve(null);
        dbPromise = new Promise((resolve) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);
            request.onupgradeneeded = () => {
                const database = request.result;
                if (!database.objectStoreNames.contains(STORES.snapshots)) database.createObjectStore(STORES.snapshots, { keyPath: "key" });
                if (!database.objectStoreNames.contains(STORES.outbox)) {
                    const store = database.createObjectStore(STORES.outbox, { keyPath: "id" });
                    store.createIndex("account", "account", { unique: false });
                }
                if (!database.objectStoreNames.contains(STORES.media)) database.createObjectStore(STORES.media, { keyPath: "id" });
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => resolve(null);
        });
        return dbPromise;
    }

    function requestResult(request) {
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error || new Error("Offline storage unavailable"));
        });
    }

    async function put(storeName, value) {
        const database = await openDb();
        if (!database) return false;
        try {
            const transaction = database.transaction(storeName, "readwrite");
            transaction.objectStore(storeName).put(value);
            await new Promise((resolve, reject) => {
                transaction.oncomplete = resolve;
                transaction.onerror = () => reject(transaction.error);
                transaction.onabort = () => reject(transaction.error);
            });
            return true;
        } catch (_error) {
            return false;
        }
    }

    async function get(storeName, key) {
        const database = await openDb();
        if (!database) return null;
        try {
            const transaction = database.transaction(storeName, "readonly");
            return await requestResult(transaction.objectStore(storeName).get(key));
        } catch (_error) {
            return null;
        }
    }

    async function remove(storeName, key) {
        const database = await openDb();
        if (!database) return;
        try {
            const transaction = database.transaction(storeName, "readwrite");
            transaction.objectStore(storeName).delete(key);
        } catch (_error) { /* Storage cleanup is best effort. */ }
    }

    function isApiUrl(url) {
        return url.origin === API_ORIGIN && url.pathname.startsWith("/api/");
    }

    function allowedMutation(url, method) {
        if (!["POST", "PUT", "PATCH", "DELETE"].includes(method) || !isApiUrl(url)) return false;
        if (/\/api\/(login|register|auth|chat|billing|connections|profiles|professional|ai\/)/.test(url.pathname)) return false;
        if (url.pathname.endsWith("/replacement_options")) return false;
        return /^\/api\/(diet(?:\/|$)|measurements(?:\/|$)|profile\/avatar(?:\/|$)|workout_sessions(?:\/|$)|workout_plans\/\d+\/days\/\d+\/sessions$)/.test(url.pathname);
    }

    function jsonResponse(data, status = 202) {
        return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
    }

    async function serializeBody(request) {
        const contentType = request.headers.get("content-type") || "";
        if (contentType.includes("multipart/form-data")) {
            const form = await request.clone().formData();
            const entries = [];
            for (const [name, value] of form.entries()) {
                if (typeof value === "string") entries.push({ name, type: "text", value });
                else entries.push({ name, type: "blob", value, filename: value.name || "upload", mime: value.type || "application/octet-stream" });
            }
            return { type: "form", entries };
        }
        return { type: "text", value: await request.clone().text() };
    }

    async function restoreBody(body) {
        if (!body || body.type !== "form") return body?.value;
        const form = new FormData();
        body.entries.forEach((entry) => {
            if (entry.type === "blob") form.append(entry.name, entry.value, entry.filename);
            else form.append(entry.name, entry.value);
        });
        return form;
    }

    async function enqueue(request, url, reason = "offline") {
        const body = await serializeBody(request);
        const id = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        const item = {
            id,
            account: accountId(),
            url: url.toString(),
            method: request.method,
            headers: Array.from(request.headers.entries()).filter(([name]) => {
                const normalized = name.toLowerCase();
                return normalized !== "content-length" && !(body.type === "form" && normalized === "content-type");
            }),
            body,
            createdAt: Date.now(),
            reason,
        };
        await put(STORES.outbox, item);
        window.dispatchEvent(new CustomEvent("fittracker:offline-queued", { detail: item }));
        return jsonResponse({ queued: true, operation_id: id, message: "Salvo neste dispositivo. Será sincronizado quando a conexão voltar." });
    }

    async function saveSnapshot(url, response) {
        if (!response.ok || response.status === 204) return;
        let data;
        try { data = await response.clone().json(); } catch (_error) { return; }
        const userId = String(data.user?.id || data.profile?.user_id || window.currentUser?.id || "anonymous");
        const key = new URL(url).pathname + new URL(url).search;
        const safeData = key.endsWith("/check_session") && data.user ? { ...data, csrf_token: null } : data;
        const snapshot = { key: keyFor(key, userId), userId, key, data: safeData, savedAt: Date.now() };
        await put(STORES.snapshots, snapshot);
        memorySnapshots.set(snapshot.key, snapshot);
        if (key.endsWith("/check_session") && data.user) {
            const authSnapshot = { ...snapshot, key: keyFor(key, "anonymous"), userId: "anonymous" };
            await put(STORES.snapshots, authSnapshot);
            memorySnapshots.set(authSnapshot.key, authSnapshot);
        }
    }

    async function readSnapshot(url, userId = accountId()) {
        const key = new URL(url).pathname + new URL(url).search;
        return memorySnapshots.get(keyFor(key, userId)) || await get(STORES.snapshots, keyFor(key, userId));
    }

    async function listOutbox(userId = accountId()) {
        const database = await openDb();
        if (!database) return [];
        try {
            const transaction = database.transaction(STORES.outbox, "readonly");
            const items = await requestResult(transaction.objectStore(STORES.outbox).index("account").getAll(userId));
            return items.sort((a, b) => a.createdAt - b.createdAt);
        } catch (_error) { return []; }
    }

    async function sync() {
        if (syncing || navigator.onLine === false || !window.currentUser) return syncing;
        syncing = (async () => {
            const items = await listOutbox();
            for (const item of items) {
                if (navigator.onLine === false) break;
                const headers = new Headers(item.headers || []);
                headers.set("Idempotency-Key", item.id);
                headers.set("X-Offline-Replay", "1");
                if (window.csrfToken) headers.set("X-CSRF-Token", window.csrfToken);
                try {
                    const response = await window.fetch(item.url, { method: item.method, headers, body: await restoreBody(item.body), credentials: "include" });
                    if (!response.ok && response.status >= 400 && response.status < 500 && response.status !== 409) {
                        await remove(STORES.outbox, item.id);
                        window.dispatchEvent(new CustomEvent("fittracker:offline-failed", { detail: { item, status: response.status } }));
                        continue;
                    }
                    if (response.status === 409) {
                        await remove(STORES.outbox, item.id);
                        window.dispatchEvent(new CustomEvent("fittracker:offline-synced", { detail: item }));
                        continue;
                    }
                    if (!response.ok) break;
                    await remove(STORES.outbox, item.id);
                    window.dispatchEvent(new CustomEvent("fittracker:offline-synced", { detail: item }));
                } catch (_error) { break; }
            }
        })();
        try { return await syncing; } finally { syncing = null; }
    }

    window.AppOffline = {
        API_ORIGIN,
        isApiUrl,
        allowedMutation,
        enqueue,
        saveSnapshot,
        readSnapshot,
        listOutbox,
        sync,
        async saveMedia(id, blob, metadata = {}) {
            return put(STORES.media, { id: keyFor(id), account: accountId(), blob, metadata, savedAt: Date.now() });
        },
        async getMedia(id) { return get(STORES.media, keyFor(id)); },
        async removeMedia(id) { return remove(STORES.media, keyFor(id)); },
    };

    window.addEventListener("online", sync);
    window.addEventListener("pageshow", () => sync());
})();
