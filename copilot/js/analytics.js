(function () {
    "use strict";

    const ANONYMOUS_ID_KEY = "dt_analytics_anonymous_id";
    const FIRST_TOUCH_KEY = "dt_analytics_first_touch";
    const RETURN_KEY_PREFIX = "dt_analytics_returned_";
    const UTM_FIELDS = ["utm_source", "utm_medium", "utm_campaign"];
    let memoryAnonymousId = null;

    function storageGet(key) {
        try { return localStorage.getItem(key); } catch (error) { return null; }
    }

    function storageSet(key, value) {
        try { localStorage.setItem(key, value); } catch (error) { /* Analytics remains best-effort. */ }
    }

    function clearAttribution() {
        memoryAnonymousId = null;
        try {
            localStorage.removeItem(ANONYMOUS_ID_KEY);
            localStorage.removeItem(FIRST_TOUCH_KEY);
            Object.keys(localStorage).filter((key) => key.startsWith(RETURN_KEY_PREFIX)).forEach((key) => localStorage.removeItem(key));
        } catch (error) { /* Local cleanup remains best-effort. */ }
    }

    function uuid() {
        if (window.crypto?.randomUUID) return window.crypto.randomUUID();
        const bytes = new Uint8Array(16);
        window.crypto.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
        return Array.from(bytes, (byte, index) => {
            const separator = [4, 6, 8, 10].includes(index) ? "-" : "";
            return separator + byte.toString(16).padStart(2, "0");
        }).join("");
    }

    function anonymousId() {
        if (memoryAnonymousId) return memoryAnonymousId;
        const stored = storageGet(ANONYMOUS_ID_KEY);
        if (/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(stored || "")) {
            memoryAnonymousId = stored.toLowerCase();
            return memoryAnonymousId;
        }
        memoryAnonymousId = uuid();
        storageSet(ANONYMOUS_ID_KEY, memoryAnonymousId);
        return memoryAnonymousId;
    }

    function firstTouch() {
        const stored = storageGet(FIRST_TOUCH_KEY);
        if (stored) {
            try {
                const parsed = JSON.parse(stored);
                if (parsed && typeof parsed === "object") return parsed;
            } catch (error) { /* Replace malformed local data below. */ }
        }
        const params = new URLSearchParams(window.location.search);
        const touch = {};
        UTM_FIELDS.forEach((field) => {
            const value = params.get(field);
            if (value) touch[field] = value.slice(0, 200);
        });
        if (Object.keys(touch).length) storageSet(FIRST_TOUCH_KEY, JSON.stringify(touch));
        return touch;
    }

    function context() {
        return { anonymous_id: anonymousId(), ...firstTouch() };
    }

    async function track(name, properties = {}) {
        const event = {
            name,
            anonymous_id: anonymousId(),
            properties: { ...properties, ...firstTouch() }
        };
        try {
            const response = await fetch("/api/analytics/events", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                keepalive: true,
                body: JSON.stringify({ events: [event] })
            });
            return response.ok;
        } catch (error) {
            return false;
        }
    }

    async function trackReturns(user) {
        if (!user?.id || !user.created_at) return;
        const ageDays = (Date.now() - new Date(user.created_at).getTime()) / 86400000;
        for (const day of [1, 7]) {
            if (ageDays < day) continue;
            const name = `returned_d${day}`;
            const key = `${RETURN_KEY_PREFIX}${name}_${user.id}_${anonymousId()}`;
            if (storageGet(key)) continue;
            if (await track(name, { account_age_days: Math.floor(ageDays) })) storageSet(key, "1");
        }
    }

    firstTouch();
    anonymousId();
    window.analytics = Object.freeze({ clearAttribution, context, track, trackReturns });
    const viewedKey = `dt_analytics_viewed_${new Date().toISOString().slice(0, 10)}`;
    if (!storageGet(viewedKey)) {
        track("app_viewed").then((accepted) => {
            if (accepted) storageSet(viewedKey, "1");
        });
    }
})();
