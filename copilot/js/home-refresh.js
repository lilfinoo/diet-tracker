/* Pull-to-refresh orchestration for the Home. Native iOS owns the gesture; web gets a touch fallback. */
(() => {
    "use strict";

    const THRESHOLD = 72;
    const MAX_PULL = 112;
    const SETTLE_DISTANCE = 54;
    const EXCLUDED_SURFACES = ".modal-content, .plan-details-container, .plan-wizard__body, .workout-session-sheet__scroll, .replacement-panel, input, textarea, select";
    let refreshPromise = null;
    let resetTimer = null;
    let gesture = null;
    let initialized = false;

    const byId = id => document.getElementById(id);
    const isNativeIOS = () => document.documentElement.dataset.nativePlatform === "ios";
    const scrollRoot = () => document.scrollingElement || document.documentElement;
    const nativePlugin = () => window.Capacitor?.Plugins?.FitTrackerRefresh;

    function modalOpen() {
        return Boolean(document.querySelector(".modal.show")) || document.body.classList.contains("modal-open");
    }

    function eligible({ requireTop = true } = {}) {
        const home = byId("dietTab");
        if (!home || home.classList.contains("hidden") || document.body.dataset.activeTab !== "diet") return false;
        if (!window.currentUser || document.hidden || modalOpen()) return false;
        if (byId("viewWorkoutPlanModal")?.classList.contains("show")) return false;
        return !requireTop || (scrollRoot()?.scrollTop || window.scrollY || 0) <= 1;
    }

    function syncEligibility() {
        const enabled = eligible({ requireTop: false });
        document.body.classList.toggle("home-refresh-enabled", enabled);
        if (isNativeIOS()) nativePlugin()?.setEnabled?.({ enabled }).catch(() => {});
        if (!enabled && gesture) cancelGesture();
        return enabled;
    }

    function setPullDistance(distance) {
        const value = Math.max(0, Math.min(MAX_PULL, Number(distance) || 0));
        byId("dietTab")?.style.setProperty("--home-pull-distance", `${value}px`);
        byId("dietTab")?.style.setProperty("--home-pull-progress", String(Math.min(value / THRESHOLD, 1)));
    }

    function setState(state, message, { announce = false, retry = false } = {}) {
        const indicator = byId("homeRefreshIndicator");
        const label = byId("homeRefreshLabel");
        const retryButton = byId("homeRefreshRetry");
        if (indicator) {
            indicator.dataset.state = state;
            indicator.setAttribute("aria-hidden", state === "idle" ? "true" : "false");
        }
        if (label && message) label.textContent = message;
        if (retryButton) retryButton.hidden = !retry;
        document.body.dataset.homeRefreshState = state;
        if (announce && message) {
            const status = byId("homeRefreshStatus");
            if (status) status.textContent = message;
        }
    }

    function scheduleIdle(delay = 850) {
        clearTimeout(resetTimer);
        resetTimer = window.setTimeout(() => {
            setState("settling", "Atualização concluída");
            setPullDistance(0);
            window.setTimeout(() => setState("idle", "Puxe para atualizar"), 260);
        }, delay);
    }

    function contextIsCurrent(context) {
        return String(window.currentUser?.id || "") === context.owner
            && window.AppReadCache?.accountVersion === context.accountVersion
            && window.localDateInputValue?.() === context.date
            && Intl.DateTimeFormat().resolvedOptions().timeZone === context.timeZone;
    }

    async function refresh({ force = true, source = "manual", visual = true } = {}) {
        if (refreshPromise) return refreshPromise;
        if (!window.currentUser) return { ok: false, cancelled: true, reason: "auth" };
        if (["pull", "native", "retry"].includes(source) && !eligible({ requireTop: source !== "retry" })) {
            nativePlugin()?.end?.().catch(() => {});
            return { ok: false, cancelled: true, reason: "ineligible" };
        }

        const context = {
            owner: String(window.currentUser.id),
            accountVersion: window.AppReadCache?.accountVersion,
            date: window.localDateInputValue?.(),
            timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        };

        refreshPromise = (async () => {
            if (visual) {
                setPullDistance(SETTLE_DISTANCE);
                setState("refreshing", "Atualizando sua Home…", { announce: true });
            }
            if (navigator.onLine === false && visual) {
                if (visual) {
                    setState("offline", "Sem conexão — mostrando os últimos dados salvos", { announce: true, retry: true });
                    setPullDistance(0);
                }
                return { ok: false, offline: true };
            }

            const dietTask = Promise.resolve().then(() => window.loadTodayCardapio?.({ force, reportResult: true }));
            const workoutTask = Promise.resolve().then(() => window.loadWorkoutTodayCard?.(force, { reportResult: true }));
            const [dietSettled, workoutSettled] = await Promise.allSettled([dietTask, workoutTask]);

            if (!contextIsCurrent(context)) return { ok: false, cancelled: true, reason: "stale-context" };
            const diet = dietSettled.status === "fulfilled" ? dietSettled.value : { ok: false, error: dietSettled.reason };
            const workout = workoutSettled.status === "fulfilled" ? workoutSettled.value : { ok: false, error: workoutSettled.reason };
            const offline = navigator.onLine === false || document.body.dataset.offline === "true" || diet?.offline || workout?.offline;
            const successes = [diet, workout].filter(result => result?.ok).length;
            const result = { ok: successes === 2 && !offline, partial: successes === 1, offline, diet, workout };

            if (!visual) return result;
            if (modalOpen() || document.body.dataset.activeTab !== "diet") {
                clearTimeout(resetTimer);
                setPullDistance(0);
                setState("idle", "Puxe para atualizar");
                return result;
            }
            if (offline) {
                setState("offline", "Sem conexão — mostrando os últimos dados salvos", { announce: true, retry: true });
                setPullDistance(0);
            } else if (result.ok) {
                setState("success", "Home atualizada", { announce: true });
                scheduleIdle();
            } else if (result.partial) {
                const message = diet?.ok ? "Alimentação atualizada; treino não pôde ser atualizado" : "Treino atualizado; alimentação não pôde ser atualizada";
                setState("partial", message, { announce: true, retry: true });
                setPullDistance(0);
            } else {
                setState("error", "Não foi possível atualizar. Verifique sua conexão.", { announce: true, retry: true });
                setPullDistance(0);
            }
            return result;
        })();

        try { return await refreshPromise; }
        finally {
            refreshPromise = null;
            nativePlugin()?.end?.().catch(() => {});
            syncEligibility();
        }
    }

    function resistance(distance) {
        if (distance <= 0) return 0;
        return Math.min(MAX_PULL, distance * 0.48 + Math.sqrt(distance) * 1.6);
    }

    function cancelGesture() {
        gesture = null;
        document.documentElement.classList.remove("home-refresh-web-tracking");
        setState("settling", "Puxe para atualizar");
        setPullDistance(0);
        window.setTimeout(() => {
            if (!refreshPromise) setState("idle", "Puxe para atualizar");
        }, 260);
    }

    function onTouchStart(event) {
        if (isNativeIOS() || refreshPromise || !eligible() || event.touches.length !== 1) return;
        if (event.target.closest?.(EXCLUDED_SURFACES)) return;
        const touch = event.touches[0];
        gesture = { startX: touch.clientX, startY: touch.clientY, axis: null, distance: 0 };
    }

    function onTouchMove(event) {
        if (!gesture || event.touches.length !== 1) return;
        if (!eligible() || modalOpen()) { cancelGesture(); return; }
        const touch = event.touches[0];
        const dx = touch.clientX - gesture.startX;
        const dy = touch.clientY - gesture.startY;
        if (!gesture.axis && Math.max(Math.abs(dx), Math.abs(dy)) >= 10) {
            if (Math.abs(dx) >= Math.abs(dy) * 1.25 || dy < 0) { cancelGesture(); return; }
            if (dy >= Math.abs(dx) * 1.25) gesture.axis = "vertical";
        }
        if (gesture.axis !== "vertical") return;
        event.preventDefault();
        gesture.distance = resistance(dy);
        document.documentElement.classList.add("home-refresh-web-tracking");
        setPullDistance(gesture.distance);
        setState(gesture.distance >= THRESHOLD ? "armed" : "tracking", gesture.distance >= THRESHOLD ? "Solte para atualizar" : "Puxe para atualizar");
    }

    function onTouchEnd() {
        if (!gesture) return;
        const armed = gesture.axis === "vertical" && gesture.distance >= THRESHOLD;
        gesture = null;
        document.documentElement.classList.remove("home-refresh-web-tracking");
        if (armed) refresh({ force: true, source: "pull", visual: true });
        else cancelGesture();
    }

    function initialize() {
        if (initialized) return;
        initialized = true;
        byId("homeRefreshRetry")?.addEventListener("click", () => refresh({ force: true, source: "retry", visual: true }));
        if (!isNativeIOS()) {
            document.addEventListener("touchstart", onTouchStart, { passive: true });
            document.addEventListener("touchmove", onTouchMove, { passive: false });
            document.addEventListener("touchend", onTouchEnd, { passive: true });
            document.addEventListener("touchcancel", cancelGesture, { passive: true });
        }
        window.addEventListener("fittracker:native-refresh", () => refresh({ force: true, source: "native", visual: true }));
        window.addEventListener("fittracker:home-refresh-eligibility", syncEligibility);
        document.addEventListener("visibilitychange", syncEligibility);
        window.addEventListener("online", syncEligibility);
        window.addEventListener("offline", syncEligibility);
        syncEligibility();
    }

    window.HomeRefreshCoordinator = {
        refresh,
        syncEligibility,
        isRefreshing: () => Boolean(refreshPromise),
        current: () => refreshPromise,
        canStart: () => eligible(),
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, { once: true });
    else initialize();
})();
