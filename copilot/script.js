Warning: truncated output (original token count: 53214)
Total output lines: 4615

// script.js

// Global variables
let currentUser = null;
let currentProfile = null;
let currentTab = 'diet';
let lastPrimaryTab = 'diet';
let dietEntries = [];
let dietEntriesLoadPromise = null;
let dietEntriesLoadRange = { startDate: null, endDate: null };
let measurements = [];
let measurementHasMore = false;
let measurementRequestToken = 0;
let measurementSummaryToken = 0;
let measurementAccountVersion = 0;
let measurementLoading = false;
let measurementRange = null;
let pendingAuthIntent = null;
let pendingPostProfileResume = null;
let pendingProfileRequiredFields = [];
let googleSignupToken = null;
let legalVersions = null;
let authMessageTimer = null;
let authRequestInFlight = false;
let nativeGoogleInFlight = false;
let pendingSessionUser = null;
let sessionConfirmationInFlight = false;
let authCheckInFlight = null;
let lastAuthCheckAt = 0;
let authState = 'unknown';
let pendingOnboardingDestination = null;
let mandatoryOnboarding = false;
let homeRequestVersion = 0;
let dietScreenRequestVersion = 0;
let resumeInFlight = null;
let lastResumeAt = 0;
let googleAuthReady = null;
let secondaryOwner = null;
let audioInitialized = false;
let billingReturnHandled = false;
let profileAchievementsState = { selected: [], achievements: [], badges: [], records: [], limit: 3, filter: 'all', savingToken: null };
let appBootCompleted = false;
const APP_VERSION = 'v1.1.2';

// API Base URL. The native shell is local, so only its API calls use Render.
const configuredApiOrigin = window.FIT_TRACKER_CONFIG?.apiOrigin || document.querySelector('meta[name="fit-tracker-api-origin"]')?.content || window.location.origin;
const API_ORIGIN = (document.documentElement.dataset.nativePlatform === 'ios' ? configuredApiOrigin : window.location.origin).replace(/\/$/, '');
const API_BASE = `${API_ORIGIN}/api`;
window.FIT_TRACKER_API_ORIGIN = API_ORIGIN;
const PRIMARY_VIEWS = new Set(['diet', 'diet_plans', 'workout_plans', 'progress', 'stats']);
const VIEW_LABELS = {
    diet: 'Hoje', diet_plans: 'Dieta', workout_plans: 'Treino', progress: 'Progresso',
    measurements: 'Medidas', activities: 'Atividades', personalRecords: 'Recordes pessoais', achievements: 'Conquistas',
    stats: 'Perfil', chat: 'Assistente IA'
};
const VIEW_PATHS = Object.freeze({
    diet: '/app/hoje',
    diet_plans: '/app/dieta',
    workout_plans: '/app/treino',
    progress: '/app/progresso',
    stats: '/app/perfil',
    measurements: '/app/progresso/medidas',
    activities: '/app/progresso/atividades',
    personalRecords: '/app/progresso/prs',
    achievements: '/app/progresso/conquistas',
    chat: '/app/assistente'
});
const PATH_VIEWS = Object.freeze(Object.fromEntries(
    Object.entries(VIEW_PATHS).map(([view, path]) => [path, view])
));

function viewForPath(pathname = window.location.pathname) {
    if (pathname === '/' || pathname === '/app' || pathname === '/app/') return 'diet';
    return PATH_VIEWS[pathname.replace(/\/$/, '')] || null;
}

function pathForView(view) {
    return VIEW_PATHS[view] || VIEW_PATHS.diet;
}

function syncViewPath(view, mode = 'push') {
    if (mode === 'none') return;
    const url = new URL(window.location.href);
    const nextPath = pathForView(view);
    const nextUrl = `${nextPath}${url.search}${url.hash}`;
    const currentUrl = `${url.pathname}${url.search}${url.hash}`;
    if (nextUrl === currentUrl) return;
    const method = mode === 'replace' ? 'replaceState' : 'pushState';
    window.history[method]({ view }, '', nextUrl);
}

// Utilitário para buscar elementos DOM
function getElement(id) {
    const element = document.getElementById(id);
    if (!element) {
        console.warn(`Elemento com ID '${id}' não encontrado`);
    }    
    return element;
}

// Adiciona um event listener apenas se o elemento existir
function addEventListenerSafe(id, event, handler) {
    const el = getElement(id);
    if (el) {
        el.addEventListener(event, handler);
    }
}
// Toast global para feedback visual
function showToast(msg, tipo="success", options = {}) {
    document.querySelectorAll('.toast:not(#globalLoading)').forEach((existing) => existing.remove());

    let toast = document.createElement("div");
    toast.className = "toast " + tipo;
    const message = document.createElement("span");
    message.textContent = msg;
    toast.appendChild(message);
    toast.setAttribute("role", tipo === "error" ? "alert" : "status");
    toast.setAttribute("aria-live", tipo === "error" ? "assertive" : "polite");
    if (options.actionLabel && typeof options.onAction === "function") {
        const action = document.createElement("button");
        action.type = "button";
        action.className = "toast__action";
        action.textContent = options.actionLabel;
        action.addEventListener("click", () => {
            clearTimeout(dismissTimer);
            toast.remove();
            options.onAction();
        });
        toast.appendChild(action);
    }
    document.body.appendChild(toast);

    const fluid = typeof Fluid !== "undefined" ? Fluid : null;
    if (fluid) {
        if (tipo === "success") fluid.haptic.tap();
        else if (tipo === "error") fluid.haptic.snap();
    }

    const dismissTimer = setTimeout(() => {
        toast.remove();
    }, options.duration || 2900);
}

// Mensagem para login/registro/perfil
function showAuthMessage(message, type = 'info') {
    const messageEl = getElement("authMessage");
    if (!messageEl) return;
    messageEl.textContent = message;
    messageEl.className = `message ${type}`;
    messageEl.setAttribute("role", type === "error" ? "alert" : "status");
    messageEl.setAttribute("aria-live", type === "error" ? "assertive" : "polite");
    messageEl.style.display = "block";
    if (authMessageTimer) clearTimeout(authMessageTimer);
    authMessageTimer = setTimeout(() => {
        messageEl.textContent = "";
        messageEl.className = "message";
        messageEl.style.display = "none";
        authMessageTimer = null;
    }, 5000);
}

// Mensagem para modal de dieta/medidas
function showDietMessage(msg, type="info") {
    let el = getElement("dietMessage");
    if (!el) {
        el = document.createElement("div");
        el.id = "dietMessage";
        el.className = "modal-message";
        // Adiciona ao modal de dieta, se existir
        const dietModalContent = getElement("dietModal")?.querySelector(".modal-content");
        if (dietModalContent) {
            dietModalContent.prepend(el);
        } else {
            document.body.appendChild(el); // Fallback
        }
    }
    el.textContent = msg;
    el.className = "modal-message " + type;
    el.setAttribute("role", type === "error" ? "alert" : "status");
    el.setAttribute("aria-live", type === "error" ? "assertive" : "polite");
    setTimeout(() => { el.textContent = ""; }, 4000);
}

// Loading global
function showGlobalLoading(msg="Carregando...") {
    let loading = document.getElementById("globalLoading");
    if (!loading) {
        loading = document.createElement("div");
        loading.id = "globalLoading";
        loading.className = "toast info";
        loading.setAttribute("role", "status");
        loading.setAttribute("aria-live", "polite");
        loading.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${msg}`;
        document.body.appendChild(loading);
    }
}
function hideGlobalLoading() {
    let loading = document.getElementById("globalLoading");
    if (loading) loading.remove();
}

async function downscaleImageFile(file, maxSize = 1024) {
    if (!file || !/^image\//i.test(file.type || '')) throw new Error("Arquivo de imagem inválido");
    if (file.size > 12 * 1024 * 1024) throw new Error("A imagem é muito grande");
    const dataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        const timeout = setTimeout(() => { reader.abort(); reject(new Error("Tempo excedido ao ler a foto")); }, 15000);
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error("Falha ao ler o arquivo"));
        reader.onloadend = () => clearTimeout(timeout);
        reader.readAsDataURL(file);
    });
    const img = await new Promise((resolve, reject) => {
        const image = new Image();
        const timeout = setTimeout(() => reject(new Error("Tempo excedido ao decodificar a imagem")), 15000);
        image.onload = () => { clearTimeout(timeout); resolve(image); };
        image.onerror = () => { clearTimeout(timeout); reject(new Error("Falha ao decodificar a imagem")); };
        image.src = dataUrl;
    });
    let width = img.naturalWidth || img.width;
    let height = img.naturalHeight || img.height;
    const scale = Math.min(1, maxSize / Math.max(width, height));
    if (scale < 1) {
        width = Math.max(1, Math.round(width * scale));
        height = Math.max(1, Math.round(height * scale));
    }
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Seu dispositivo não consegue processar esta foto");
    ctx.drawImage(img, 0, 0, width, height);
    const out = canvas.toDataURL("image/jpeg", 0.8);
    return { dataUrl: out, base64: out.split(",")[1] };
}

// Foto selecionada para gerar macros por imagem (base64 já reduzido).

// --- CONTROLES VISUAIS (cards de escolha, steppers, chips de data, revelar senha) ---
function bindChoiceCardGrid(gridId, targetId) {
    const grid = getElement(gridId);
    const target = getElement(targetId);
    if (!grid || !target) return;
    const cards = Array.from(grid.querySelectorAll(".choice-card"));

    function selectCard(card, focus = false) {
        const value = card.dataset.value;
        if (!value) return;
        target.value = value;
        cards.forEach(candidate => {
            const selected = candidate === card;
            candidate.classList.toggle("is-active", selected);
            candidate.setAttribute("aria-checked", selected ? "true" : "false");
            candidate.tabIndex = selected ? 0 : -1;
        });
        target.dispatchEvent(new Event("change", { bubbles: true }));
        if (focus) card.focus();
    }

    cards.forEach((card, index) => {
        card.tabIndex = index === 0 ? 0 : -1;
        card.addEventListener("click", function() {
            selectCard(card);
        });
        card.addEventListener("keydown", function(event) {
            const keys = ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"];
            if (!keys.includes(event.key)) return;
            event.preventDefault();
            const direction = ["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 1;
            const nextIndex = event.key === "Home" ? 0
                : event.key === "End" ? cards.length - 1
                : (cards.indexOf(card) + direction + cards.length) % cards.length;
            selectCard(cards[nextIndex], true);
        });
    });
}

function syncChoiceCardGrid(gridId, targetId) {
    const grid = getElement(gridId);
    const target = getElement(targetId);
    if (!grid || !target) return;
    const value = target.value || "";
    grid.querySelectorAll(".choice-card").forEach(card => {
        const active = card.dataset.value === value;
        card.classList.toggle("is-active", active);
        card.setAttribute("aria-checked", active ? "true" : "false");
        card.tabIndex = active ? 0 : -1;
    });
    if (!value) {
        const firstCard = grid.querySelector(".choice-card");
        if (firstCard) firstCard.tabIndex = 0;
    }
}

function bindStepper(stepperEl) {
    const input = stepperEl.querySelector("input");
    if (!input) return;
    const minus = stepperEl.querySelector(".stepper__minus");
    const plus = stepperEl.querySelector(".stepper__plus");
    const stepAttr = stepperEl.dataset.step;
    const step = stepAttr != null ? parseFloat(stepAttr) : (input.step ? parseFloat(input.step) : 1) || 1;
    const min = input.min != null && input.min !== "" ? parseFloat(input.min) : -Infinity;
    const max = input.max != null && input.max !== "" ? parseFloat(input.max) : Infinity;

    function adjust(delta) {
        let current = parseFloat(input.value);
        if (Number.isNaN(current)) current = 0;
        let next = current + delta * step;
        if (step < 1) next = Math.round(next * 10) / 10;
        if (next < min) next = min;
        if (next > max) next = max;
        input.value = next;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (minus) minus.addEventListener("click", () => adjust(-1));
    if (plus) plus.addEventListener("click", () => adjust(1));
}

function bindFieldReveal() {
    document.querySelectorAll(".field-reveal").forEach(button => {
        button.addEventListener("click", function() {
            const target = getElement(button.dataset.revealTarget);
            if (!target) return;
            const show = target.type === "password";
            target.type = show ? "text" : "password";
            button.setAttribute("aria-label", show ? "Ocultar senha" : "Mostrar senha");
            button.innerHTML = show ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>';
        });
    });
}

function setupAppStyleControls() {
    bindChoiceCardGrid("genderCards", "profileGender");
    bindChoiceCardGrid("goalCards", "profileGoal");
    bindChoiceCardGrid("activityCards", "profileActivity");
    document.querySelectorAll(".stepper").forEach(bindStepper);
    bindFieldReveal();
}

function syncChoiceCards() {
    syncChoiceCardGrid("genderCards", "profileGender");
    syncChoiceCardGrid("goalCards", "profileGoal");
    syncChoiceCardGrid("activityCards", "profileActivity");
}

// Adiciona listeners ao carregar a página
document.addEventListener('DOMContentLoaded', function() {
    setDefaultDates();
    bootApp();
    setupAppStyleControls();
    bindTodayMacroControls();
    syncChoiceCards();
    initializeAchievementControls();
    addEventListenerSafe('googleUsernameForm', 'submit', finishGoogleSignup);

    // Formulário de dieta
    const dietForm = document.getElementById("dietForm");
    if (dietForm) {
        dietForm.addEventListener('invalid', event => {
            const details = event.target.closest('details');
            if (details) details.open = true;
        }, true);
        dietForm.addEventListener("submit", async function(e) {
            e.preventDefault();
            await handleDietFormSubmit();
        });
    }

    // Formulário de medidas
    const measurementForm = document.getElementById("measurementForm");
    if (measurementForm) {
        measurementForm.addEventListener("submit", async function(e) {
            e.preventDefault();
            await handleMeasurementFormSubmit();
        });
    }

    // Formulário de edição de refeição do plano
    const editPlanMealForm = document.getElementById("editPlanMealForm");
    if (editPlanMealForm) {
        editPlanMealForm.addEventListener("submit", async function(e) {
            e.preventDefault();
            await handleEditPlanMealSubmit(e);
        });
    }

    // Auth forms
    addEventListenerSafe("loginForm", "submit", handleLogin);
    addEventListenerSafe("registerForm", "submit", handleRegister);
    addEventListenerSafe("profileForm", "submit", handleProfileSubmit);

    // Chat input - Enter key
    const chatInput = getElement("chatInput");
    if (chatInput) {
        chatInput.addEventListener("keypress", function(e) {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendChatMessage();
            }
        });
    }

    // Os atalhos abrem o questionário guiado sem disparar uma geração pelo chat.
    addEventListenerSafe("quickDietBtn", "click", function() {
        if (window.openPlanWizard) window.openPlanWizard("diet");
    });
    addEventListenerSafe("quickWorkoutBtn", "click", function() {
        if (window.openPlanWizard) window.openPlanWizard("workout");
    });

    // Modal close events
    setupModalEvents();
    getElement('loginScreen')?.addEventListener('click', function(event) {
        if (!currentUser && document.body.dataset.authRequired === 'true') return;
        if (event.target === this) closeAuthModal();
    });
    
    setupPlanViewModals();


});

function setAppBootState(state, message) {
    const screen = getElement('appBootScreen');
    const label = getElement('appBootMessage');
    if (!screen) return;
    document.body.dataset.bootState = state;
    screen.classList.toggle('is-error', state === 'error');
    screen.classList.toggle('is-offline', state === 'offline' || state === 'offline-empty');
    if (label && message) label.textContent = message;
}

function finishAppBoot() {
    if (appBootCompleted) return;
    appBootCompleted = true;
    getElement('appBootScreen')?.setAttribute('hidden', '');
}

function updateOfflineStatus() {
    const status = getElement('offlineStatus');
    if (!status) return;
    const offline = navigator.onLine === false || document.body.dataset.offline === 'true';
    status.hidden = !offline;
    status.setAttribute('aria-label', offline ? 'Sem conexão. Dados serão sincronizados quando a internet voltar.' : '');
}

async function bootApp() {
    setAppBootState('loading', navigator.onLine === false ? 'Verificando dados salvos neste dispositivo...' : 'Confirmando sua sessão...');
    const cachedAuth = await window.AppOffline?.readSnapshot(`${API_BASE}/check_session`, 'anonymous');
    if (navigator.onLine === false) {
        if (cachedAuth?.data?.logged_in && cachedAuth.data.user) {
            setCsrfToken(null);
            setCurrentUser(cachedAuth.data.user);
            authState = 'authenticated';
            document.body.dataset.authState = authState;
            document.body.dataset.offline = 'true';
            updateOfflineStatus();
            finishAuthenticatedRoute(viewForPath() || 'diet', { offline: true });
            const status = getElement('authSessionStatus');
            if (status) status.textContent = 'Modo offline: seus registros serão sincronizados quando a conexão voltar.';
            finishAppBoot();
        } else {
            setAppBootState('offline-empty', 'Conecte-se uma vez para carregar sua conta neste dispositivo.');
            getElement('appBootRetry')?.addEventListener('click', () => { setAppBootState('loading', 'Tentando conectar...'); bootApp(); }, { once: true });
            openAuthLanding();
        }
        return;
    }
    await checkAuthStatus({ boot: true });
    if (authState !== 'unknown') {
        setAppBootState(currentUser ? 'connected' : 'session-expired', currentUser ? 'Conectado.' : 'Entre para continuar.');
        document.body.dataset.offline = 'false';
        updateOfflineStatus();
        finishAppBoot();
        return;
    }
    if (cachedAuth?.data?.logged_in && cachedAuth.data.user) {
        setAppBootState('offline', 'Servidor indisponível. Exibindo seus últimos dados sincronizados.');
        setCsrfToken(null);
        setCurrentUser(cachedAuth.data.user);
        authState = 'authenticated';
        document.body.dataset.authState = authState;
        document.body.dataset.offline = 'true';
        updateOfflineStatus();
        finishAuthenticatedRoute(viewForPath() || 'diet', { offline: true });
        const status = getElement('authSessionStatus');
        if (status) status.textContent = 'Servidor indisponível. Exibindo seus últimos dados sincronizados.';
        finishAppBoot();
    } else {
        setAppBootState('error', 'Não foi possível iniciar agora.');
        getElement('appBootRetry')?.addEventListener('click', () => { setAppBootState('loading', 'Tentando conectar...'); bootApp(); }, { once: true });
    }
}

async function resumeApp() {
    if (nativeGoogleInFlight || authRequestInFlight || pendingSessionUser) return;
    if (document.hidden || navigator.onLine === false || resumeInFlight || Date.now() - lastResumeAt < 1000) return resumeInFlight;
    resumeInFlight = (async () => {
        if (authState === 'unknown' || Date.now() - lastAuthCheckAt > 60_000) await checkAuthStatus({ resume: true });
        if (!currentUser) return;
        await window.resumeWorkoutSession?.();
        if (currentTab === 'diet') {
            if (window.HomeRefreshCoordinator) await window.HomeRefreshCoordinator.refresh({ force: false, source: 'resume', visual: false });
            else await Promise.all([loadTodayCardapio(), window.loadWorkoutTodayCard?.()]);
        }
    })();
    try { await resumeInFlight; }
    catch (error) { if (error.name !== 'AbortError') console.warn('App resume:', error); }
    finally { resumeInFlight = null; lastResumeAt = Date.now(); }
}

document.addEventListener('visibilitychange', () => { if (!document.hidden) resumeApp(); });
window.addEventListener('pageshow', event => { if (event.persisted) resumeApp(); });
window.addEventListener('online', resumeApp);
window.addEventListener('online', () => { document.body.dataset.offline = 'false'; updateOfflineStatus(); });
window.addEventListener('offline', updateOfflineStatus);
window.addEventListener('fittracker:offline-queued', updateOfflineStatus);
window.addEventListener('fittracker:offline-synced', () => {
    if (navigator.onLine !== false) document.body.dataset.offline = 'false';
    updateOfflineStatus();
});

function scheduleSecondaryLoads(skipProfile = false) {
    const owner = currentUser?.id || 'guest';
    if (secondaryOwner === owner) return;
    secondaryOwner = owner;
    requestAnimationFrame(() => requestAnimationFrame(() => {
        const run = () => {
            if (secondaryOwner !== owner || (currentUser?.id || 'guest') !== owner) return;
            refreshDisplayedVersion();
            if (currentUser) {
                if (!skipProfile) checkUserProfile();
                window.preloadProgressOverview?.();
                    }
        };
        if (window.requestIdleCallback) window.requestIdleCallback(run, { timeout: 2000 });
        else setTimeout(run, 500);
    }));
}

async function refreshDisplayedVersion() {
    try {
        const response = await window.fetchWithTimeout(`${API_BASE}/version`);
        if (!response.ok) return;
        const data = await response.json();
        const label = [APP_VERSION, data.commit && data.commit !== 'local' ? data.commit : ''].filter(Boolean).join(' · ');
        document.querySelectorAll('.app-version').forEach((element) => { element.textContent = label; });
    } catch (_error) {
        // A versão estática continua visível quando a rede ainda não está disponível.
    }
}

// --- FUNÇÕES PRINCIPAIS ---

async function handleDietFormSubmit() {
    if (window.DietEntryFlow && !window.DietEntryFlow.canSave()) return;
    const owner = currentUser?.id;
    const flowRevision = window.DietEntryFlow?.revision();
    const ownsDraft = () => owner === currentUser?.id && flowRevision === window.DietEntryFlow?.revision();
    const btn = document.getElementById("dietSaveBtn");
    if (btn.disabled) return;
    const loading = document.getElementById("dietSaveLoading");
    btn.disabled = true;
    loading.classList.remove("hidden");
    window.DietEntryFlow?.lockSaving(true);

    // Coleta os dados do formulário
    const dietIdRaw = document.getElementById("dietId").value;
    const dietId = Number(dietIdRaw);
    const isEdit = Number.isInteger(dietId) && dietId > 0;

    // Função auxiliar para converter campos numéricos
    function parseNumber(val) {
        return val && val !== "" ? Number(val) : null;
    }

    const payload = {
        id: dietIdRaw,
        date: document.getElementById("dietDate").value,
        meal_type: document.getElementById("dietMeal").value,
        description: document.getElementById("dietDescription").value,
        calories: parseNumber(document.getElementById("dietCalories").value),
        protein: parseNumber(document.getElementById("dietProtein").value),
        carbs: parseNumber(document.getElementById("dietCarbs").value),
        fat: parseNumber(document.getElementById("dietFat").value),
        notes: document.getElementById("dietNotes").value
    };

    const dailyContext = !isEdit ? pendingDietDailyContext : null;
    const url = dailyContext
        ? `${API_BASE}/diet/days/${encodeURIComponent(payload.date)}/slots/${encodeURIComponent(dailyContext.slotKey)}/outcome`
        : (isEdit ? `/api/diet/${dietId}` : "/api/diet");
    const method = dailyContext || isEdit ? "PUT" : "POST";
    const requestPayload = dailyContext ? {
        result: "consumed_different",
        diet_plan_meal_id: dailyContext.mealId,
        entry: payload
    } : payload;

    try {
        const response = await fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify(requestPayload)
        });

        if (!ownsDraft()) return;
        if (response.ok) {
            const data = await response.json();
            if (!ownsDraft()) return;
            invalidateHomeMealReads();
            window.DietEntryFlow?.saved();
            if (dailyContext?.surface === 'home') {
                applyHomeMealOutcome(dailyContext.slotKey, payload.date, data.state);
                animateHomeMealRemoval(dailyContext.slotKey);
                renderTodayCardapio(todayDietDay);
            } else if (todayDietDay && data.entry) {
                applyHomeDietEntry(data.entry);
            }
            closeDietModal();
            refreshHomeMealsInBackground();
            if (dailyContext?.surface === 'home') {
                showToast('Refeição registrada!', 'success', {
                    actionLabel: 'Desfazer', duration: 5000,
                    onAction: () => resetDietDailySlot(dailyContext.slotKey, 'home', payload.date)
                });
            } else showToast("Refeição registrada", "success");
        } else {
            const errorData = await response.json();
            if (ownsDraft()) showDietMessage(errorData.error || "Não foi possível salvar. Tente novamente.", "error");
        }
    } catch (e) {
        if (ownsDraft()) showDietMessage("Erro de conexão. Seu preenchimento foi mantido. Tente salvar novamente.", "error");
    } finally {
        if (ownsDraft()) {
            btn.disabled = false;
            loading.classList.add("hidden");
            window.DietEntryFlow?.lockSaving(false);
        }
    }
}

// Salva a medição; os valores atuais são derivados pelo servidor.
async function handleMeasurementFormSubmit() {
    const accountVersion = measurementAccountVersion;
    const btn = document.getElementById("measurementSaveBtn");
    const loading = document.getElementById("measurementSaveLoading");
    btn.disabled = true;
    loading.classList.remove("hidden");

    function parseNumber(val) {
        return val && val !== "" ? Number(val) : null;
    }
    function parseHeight(val) {
        if (!val || val === "") return null;
        const number = Number(String(val).trim().replace(',', '.'));
        if (!Number.isFinite(number) || number <= 0) return NaN;
        return number <= 3 ? Math.round(number * 1000) / 10 : number;
    }

    const measurementIdRaw = document.getElementById("measurementId")?.value;
    const measurementId = Number(measurementIdRaw);
    const isEdit = Number.isInteger(measurementId) && measurementId > 0;

    const payload = {
        id: measurementIdRaw,
        date: document.getElementById("measurementDate").value,
        weight: parseNumber(document.getElementById("measurementWeight").value),
        height: parseHeight(document.getElementById("measurementHeight").value),
        body_fat: parseNumber(document.getElementById("measurementBodyFat").value),
        muscle_mass: parseNumber(document.getElementById("measurementMuscleMass").value),
        waist: parseNumber(document.getElementById("measurementWaist").value),
        chest: parseNumber(document.getElementById("measurementChest").value),
        arm: parseNumber(document.getElementById("measurementArm").value),
        thigh: parseNumber(document.getElementById("measurementThigh").value),
        notes: document.getElementById("measurementNotes").value
    };
    if (document.getElementById("measurementHeight").value && !Number.isFinite(payload.height)) {
        showToast("Altura inválida. Use centímetros ou metros, como 180 ou 1,80.", "error");
        btn.disabled = false;
        loading.classList.add("hidden");
        return;
    }

    try {
        const url = isEdit ? `/api/measurements/${measurementId}` : "/api/measurements";
        const method = isEdit ? "PUT" : "POST";
        const response = await fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify(payload)
        });

        if (accountVersion !== measurementAccountVersion) return;
        if (response.ok) {
            closeMeasurementModal();
            await Promise.all([loadMeasurements(), loadMeasurementSummary()]);
            if (accountVersion !== measurementAccountVersion) return;
            showToast(isEdit ? "Medidas atualizadas!" : "Medidas adicionadas!", "success");

        } else {
            const data = await response.json();
            showToast(data.error || "Erro ao salvar", "error");
        }
    } catch (error) {
        console.error("Measurement submit error:", error);
        showToast("Erro de conexão", "error");
    } finally {
        btn.disabled = false;
        loading.classList.add("hidden");
    }
}

// Setup event listeners
/**
 * Configura eventos de modais com verificação de existência
 */
function setupModalEvents() {
    const modals = [
        { id: "dietModal", closeFunc: closeDietModal },
        { id: "measurementModal", closeFunc: closeMeasurementModal },
        { id: "profileModal", closeFunc: closeProfileModal }
    ];

    modals.forEach(modal => {
        const element = getElement(modal.id);
        if (element) {
            element.addEventListener("click", function(e) {
                if (e.target === this) {
                    if (modal.id === "profileModal" && mandatoryOnboarding) return;
                    modal.closeFunc();
                }
            });
        }
    });
}

function setupPlanViewModals() {
    const viewDietPlanModal = getElement("viewDietPlanModal");
    if (viewDietPlanModal) {
        viewDietPlanModal.addEventListener("click", function(e) {
            if (e.target === this) {
                closeViewDietPlanModal();
            }
        });
    }
    const viewWorkoutPlanModal = getElement("viewWorkoutPlanModal");
    if (viewWorkoutPlanModal) {
        viewWorkoutPlanModal.addEventListener("click", function(e) {
            if (e.target === this) {
                closeViewWorkoutPlanModal();
            }
        });
    }
}


// Set default dates
function setDefaultDates() {
    const today = localDateInputValue();
    const weekAgo = localDateInputValue(new Date(Date.now() - 7 * 24 * 60 * 60 * 1000));
    
    const dateFields = [
        { id: 'measurementStartDate', value: '' },
        { id: 'measurementEndDate', value: '' },
        { id: 'dietDate', value: today },
        { id: 'measurementDate', value: today }
    ];

    dateFields.forEach(field => {
        const element = getElement(field.id);
        if (element) {
            element.value = field.value;
        }
    });
}

// Authentication functions
function hasCompletedOnboarding(user = currentUser) {
    return Boolean(user?.profile_complete || user?.onboarding_status === 'complete');
}

function userNeedsOnboarding(user = currentUser) {
    return Boolean(user && !hasCompletedOnboarding(user));
}

function setAuthRequired(required) {
    document.body.dataset.authRequired = required ? 'true' : 'false';
}

function setOnboardingRequired(required) {
    mandatoryOnboarding = Boolean(required);
    document.body.dataset.onboardingRequired = mandatoryOnboarding ? 'true' : 'false';
}

function profileTimezoneValue(profile = null) {
    return profile?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}

function normalizeNaturalHeight(value) {
    if (value == null || value === '') return null;
    const number = Number(String(value).trim().replace(',', '.'));
    if (!Number.isFinite(number) || number <= 0) return NaN;
    return number <= 3 ? Math.round(number * 1000) / 10 : number;
}

function missingOnboardingFieldsFromForm() {
    const values = {
        goal: getElement("profileGoal")?.value,
        activity_level: getElement("profileActivity")?.value,
        age: Number(getElement("profileAge")?.value),
        gender: getElement("profileGender")?.value,
        weight: Number(getElement("profileWeight")?.value),
        height: normalizeNaturalHeight(getElement("profileHeight")?.value)
    };
    const valid = {
        goal: Boolean(values.goal),
        activity_level: ["sedentario", "leve", "moderado", "intenso"].includes(String(values.activity_level || '').toLowerCase()),
        age: Number.isFinite(values.age) && values.age >= 18 && values.age <= 120,
        gender: Boolean(values.gender),
        weight: Number.isFinite(values.weight) && values.weight >= 30 && values.weight <= 300,
        height: Number.isFinite(values.height) && values.height >= 120 && values.height <= 250
    };
    return Object.keys(valid).filter(field => !valid[field]);
}

async function openRequiredOnboarding(destination = null) {
    if (!currentUser) return;
    pendingOnboardingDestination = destination || pendingOnboardingDestination || viewForPath() || currentTab || 'diet';
    setAuthRequired(false);
    setOnboardingRequired(true);
    const mainScreen = getElement('mainScreen');
    if (mainScreen) mainScreen.classList.add('hidden');
    const status = getElement('authSessionStatus');
    if (status) status.textContent = 'Complete seu perfil para preparar sua Home.';
    try {
        const response = await fetch(`${API_BASE}/profile`, { credentials: 'include' });
        const data = response.ok ? await response.json() : {};
        fillProfileForm(data.profile || null);
    } catch (error) {
        console.error('Profile load before onboarding failed:', error);
        fillProfileForm(null);
    }
    openAppModal(getElement('profileModal'));
}

function finishAuthenticatedRoute(destination = null, options = {}) {
    setAuthRequired(false);
    if (userNeedsOnboarding()) {
        openRequiredOnboarding(destination);
        return;
    }
    setOnboardingRequired(false);
    showMainScreen({ tab: destination || viewForPath() || currentTab || 'diet', ...options });
}

function openAuthLanding() {
    setCurrentUser(null);
    setCsrfToken(null);
    authState = 'guest';
    document.body.dataset.authState = authState;
    setAuthRequired(true);
    setOnboardingRequired(false);
    getElement('mainScreen')?.classList.add('hidden');
    const status = getElement('authSessionStatus');
    if (status) status.innerHTML = '';
    openAuthModal('Comece em poucos segundos.', 'choice', { tab: 'diet' });
}

async function checkAuthStatus(options = {}) {
    if (authCheckInFlight) return authCheckInFlight;
    const ownerVersion = window.AppReadCache?.accountVersion;
    const wasUnknown = authState === 'unknown';
    authCheckInFlight = (async () => {
        try {
            const response = await window.fetchWithTimeout(`${API_BASE}/check_session`, { credentials: 'include' });
            const data = await response.json();
            if (ownerVersion !== window.AppReadCache?.accountVersion) return;
            if (!response.ok && response.status !== 401 && !(response.status === 403 && data.logged_in === false)) throw new Error('Não foi possível confirmar sua sessão agora.');
            const previousOwner = currentUser?.id;
            setCsrfToken(data.logged_in ? data.csrf_token : null);
            setCurrentUser(data.logged_in ? data.user : null);
            authState = currentUser ? 'authenticated' : 'guest';
            document.body.dataset.authState = authState;
            const status = getElement('authSessionStatus');
            if (status) status.innerHTML = '';
            if (!currentUser) window.clearWorkoutProgress?.();
            if (currentUser) window.analytics?.trackReturns(currentUser);
            if (!currentUser) {
                openAuthLanding();
            } else if (userNeedsOnboarding()) {
                await openRequiredOnboarding(viewForPath() || currentTab || 'diet');
            } else if (wasUnknown || previousOwner !== currentUser?.id) {
                finishAuthenticatedRoute(viewForPath() || currentTab || 'diet');
            } else if (!options.resume) {
                showMainScreen({ tab: currentTab, refreshOnly: true });
            }
            lastAuthCheckAt = Date.now();
            handleBillingReturn();
        } catch (error) {
            if (ownerVersion !== window.AppReadCache?.accountVersion || error.name === 'AbortError') return;
            if (authState === 'unknown') {
                const status = getElement('authSessionStatus');
                if (status) status.innerHTML = '<span>Não foi possível confirmar sua sessão.</span> <button type="button" class="text-button" onclick="checkAuthStatus()">Tentar novamente</button>';
            }
        }
    })();
    try { return await authCheckInFlight; }
    finally { authCheckInFlight = null; }
}

function removeQueryParameter(name) {
    const url = new URL(window.location.href);
    url.searchParams.delete(name);
    const nextUrl = `${url.pathname}${url.search}${url.hash}`;
    window.history.replaceState(window.history.state, '', nextUrl);
}

function handleBillingReturn() {
    if (billingReturnHandled) return;
    const status = new URLSearchParams(window.location.search).get('billing');
    if (!['success', 'cancel', 'expired'].includes(status)) return;
    billingReturnHandled = true;
    const messages = {
        success: currentUser?.is_premium
            ? 'Pagamento confirmado. Seu plano já está ativo.'
            : 'Pagamento enviado. A confirmação pode levar alguns instantes.',
        cancel: 'Pagamento cancelado. Nenhuma nova assinatura foi ativada.',
        expired: 'A sessão de pagamento expirou. Inicie uma nova assinatura para continuar.'
    };
    showToast(messages[status], status === 'success' ? 'success' : 'info');
    removeQueryParameter('billing');
}

// Screen management
function openAuthModal(reason = 'Entre para salvar seus dados e acompanhar sua evolução.', mode = 'choice', intent = null) {
    initializeGoogleAuth();
    const loginScreen = getElement('loginScreen');
    const context = getElement('authContext');
    if (context) context.textContent = reason;
    pendingAuthIntent = intent || { tab: currentTab };
    if (mode === 'register') showRegister();
    else if (mode === 'login') showLogin();
    else showAuthChoice();
    openAppModal(loginScreen);
}

function closeAuthModal() {
    if (!currentUser && document.body.dataset.authRequired === 'true') return;
    pendingAuthIntent = null;
    closeAppModal(getElement('loginScreen'));
    if (viewForPath() !== currentTab) syncViewPath(currentTab, 'replace');
}

function requireAuth(reason, options = {}) {
    if (currentUser) {
        if (options.premium && !hasAiAccess()) {
            showToast('Este recurso utiliza IA e está disponível no plano Premium.', 'info');
            openPlansModal();
            return false;
        }
        return true;
    }
    const premiumNotice = options.premium ? ' A geração com IA é um recurso Premium.' : '';
    openAuthModal(`${reason}${premiumNotice}`, options.mode || 'register', {
        tab: currentTab,
        premium: Boolean(options.premium),
        requiresProfile: Boolean(options.requiresProfile),
        resume: options.resume || null
    });
    return false;
}

function hasAiAccess() {
    return Boolean(currentUser?.is_premium || (currentUser && Number(currentUser.ai_trial_uses || 0) < 3));
}

async function initializeGoogleAuth() {
    if (googleAuthReady) return googleAuthReady;
    googleAuthReady = (async () => {
    try {
        const response = await window.fetchWithTimeout(`${API_BASE}/auth/config`);
        const config = response.ok ? await response.json() : {};
        legalVersions = config.legal || null;
        if (!config.google_client_id) return;
        getElement('googleAuthSection')?.classList.remove('hidden');
        getElement('googleHeaderButton')?.classList.remove('hidden');
        getElement('authChoiceGoogleButton')?.classList.remove('hidden');
        if (window.Capacitor?.getPlatform?.() === 'ios') {
            getElement('googleSignInButton')?.replaceChildren();
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'google-native-signin';
            button.textContent = 'Continuar com Google';
            button.addEventListener('click', startNativeGoogleSignIn);
            getElement('googleSignInButton')?.append(button);
            return;
        }
        const script = document.createElement('script');
        script.src = 'https://accounts.google.com/gsi/client';
        script.async = true;
        script.defer = true;
        script.onload = () => {
            google.accounts.id.initialize({
                client_id: config.google_client_id,
                callback: handleGoogleCredential,
                ux_mode: 'popup',
                cancel_on_tap_outside: false
            });
            google.accounts.id.renderButton(getElement('googleSignInButton'), {
                theme: 'outline', size: 'large', width: 320, text: 'continue_with'
            });
        };
        script.onerror = () => showAuthMessage('Não foi possível carregar o login do Google. Use e-mail e senha ou tente novamente.', 'error');
        document.head.appendChild(script);
    } catch (error) {
        googleAuthReady = null;
        console.error('Google auth configuration failed:', error);
    }
    })();
    return googleAuthReady;
}

function startAuthChoiceGoogle() {
    if (window.Capacitor?.getPlatform?.() === 'ios') {
        startNativeGoogleSignIn();
        return;
    }
    showLogin();
    getElement('googleSignInButton')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    showAuthMessage('Toque no botão oficial do Google abaixo para continuar.', 'info');
}

async function startNativeGoogleSignIn() {
    if (nativeGoogleInFlight || authRequestInFlight || sessionConfirmationInFlight) return;
    const plugin = window.Capacitor?.Plugins?.FitTrackerGoogleAuth;
    if (!plugin?.signIn) {
        showAuthMessage('Atualize o app para concluir o login com Google. Você ainda pode entrar com e-mail e senha.', 'info');
        return;
    }
    nativeGoogleInFlight = true;
    console.info('[Auth]', { stage: 'native_start' });
    setGoogleAuthPending(true, 'Abrindo suas contas Google...');
    try {
        const result = await plugin.signIn();
        if (!result?.idToken) throw new Error('O Google não devolveu uma credencial válida. Tente novamente.');
        await handleGoogleCredential({ credential: result.idToken });
    } catch (error) {
        console.info('[Auth]', { stage: error?.message === 'cancelled' ? 'native_cancelled' : 'native_failed' });
        if (error?.message !== 'cancelled') showAuthMessage(error.message || 'Não foi possível entrar com Google.', 'error');
    } finally {
        nativeGoogleInFlight = false;
        setGoogleAuthPending(false);
    }
}

function setGoogleAuthPending(pending, message = '') {
    pending = pending || nativeGoogleInFlight || authRequestInFlight || sessionConfirmationInFlight;
    document.querySelectorAll('#authChoiceGoogleButton, #googleHeaderButton, .google-native-signin').forEach(button => { button.disabled = pending; });
    const section = getElement('googleAuthSection');
    const submit = getElement('googleSignupSubmit');
    section?.setAttribute('aria-busy', String(pending));
    if (submit) {
        submit.disabled = pending;
        submit.textContent = pending ? 'Concluindo...' : 'Concluir cadastro';
    }
    if (pending && message) showAuthMessage(message, 'info');
}

function openAuthWithGoogle() {
    openAuthModal('Entre com sua conta Google em um toque.', 'login');
    if (window.Capacitor?.getPlatform?.() === 'ios') {
        startNativeGoogleSignIn();
        return;
    }
    if (window.google?.accounts?.id) {
        try { google.accounts.id.prompt(); } catch (error) { /* o modal oficial permanece como caminho alternativo */ }
    }
}

async function handleGoogleCredential(result) {
    if (authRequestInFlight) return;
    authRequestInFlight = true;
    setGoogleAuthPending(true, 'Entrando com Google...');
    console.info('[Auth]', { stage: 'google_backend_start' });
    try {
        const response = await window.fetchWithTimeout(`${API_BASE}/auth/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ credential: result.credential })
        });
        const data = await response.json().catch(() => ({}));
        if (response.status === 409 && data.code === 'username_required') {
            window.analytics?.track('signup_started', { surface: 'google_auth' });
            googleSignupToken = data.signup_token;
            getElement('authChoicePanel')?.classList.add('hidden');
            document.querySelector('.login-tabs')?.classList.add('hidden');
            getElement('loginForm')?.classList.add('hidden');
            getElement('registerForm')?.classList.add('hidden');
            getElement('googleAuthSection')?.classList.add('hidden');
            getElement('googleSignupStep')?.classList.remove('hidden');
            getElement('googleUsername')?.focus();
            return;
        }
        if (!response.ok) throw new Error(data.error || 'Não foi possível entrar com Google. Tente novamente.');
        console.info('[Auth]', { stage: 'google_backend_accepted' });
        await completeAuthentication(data.user, data.csrf_token);
    } catch (error) {
        showAuthMessage(error.message, 'error');
    } finally {
        authRequestInFlight = false;
        setGoogleAuthPending(false);
    }
}

async function finishGoogleSignup(event) {
    event.preventDefault();
    if (authRequestInFlight || nativeGoogleInFlight || sessionConfirmationInFlight) return;
    const username = getElement('googleUsername')?.value.trim();
    if (!googleSignupToken || !username) return;
    if (!legalVersions) {
        showAuthMessage('Não foi possível preparar o cadastro. Tente novamente.', 'error');
        return;
    }
    setGoogleAuthPending(true, 'Concluindo cadastro...');
    authRequestInFlight = true;
    try {
        const response = await fetch(`${API_BASE}/auth/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                signup_token: googleSignupToken,
                username,
                ai_consent: Boolean(getElement('googleAiConsent')?.checked),
                ai_consent_version: legalVersions.ai.version,
                analytics: window.analytics?.context()
            })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Não foi possível concluir o cadastro.');
        googleSignupToken = null;
        getElement('googleSignupStep')?.classList.add('hidden');
        await completeAuthentication(data.user, data.csrf_token);
    } catch (error) {
        showAuthMessage(error.message, 'error');
    } finally {
        authRequestInFlight = false;
        setGoogleAuthPending(false);
    }
}

async function completeAuthentication(user, csrfToken = null) {
    if (sessionConfirmationInFlight) return;
    pendingSessionUser = user;
    sessionConfirmationInFlight = true;
    setGoogleAuthPending(true, 'Confirmando sua sessão...');
    console.info('[Auth]', { stage: 'session_confirmation' });
    const accountVersion = window.AppReadCache.accountVersion;
    try {
        const session = await window.confirmAuthSession(API_BASE, user);
        await window.AppOffline?.saveSnapshot(`${API_BASE}/check_session`, new Response(JSON.stringify(session), { headers: { 'Content-Type': 'application/json' } }), String(session.user.id), () => accountVersion === window.AppReadCache.accountVersion);
        if (accountVersion !== window.AppReadCache.accountVersion || pendingSessionUser !== user) return;
        setCurrentUser(session.user);
        setCsrfToken(session.csrf_token);
        document.body.dataset.offline = 'false';
        updateOfflineStatus();
        pendingSessionUser = null;
        console.info('[Auth]', { stage: 'session_confirmed' });
    } catch (error) {
        if (accountVersion !== window.AppReadCache.accountVersion || pendingSessionUser !== user) return;
        console.info('[Auth]', { stage: 'session_failed', category: error?.code || (error?.name === 'TimeoutError' ? 'timeout' : 'network_error') });
        showAuthMessage(error.message || 'Não foi possível confirmar sua sessão.', 'error');
        clearTimeout(authMessageTimer);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'text-button';
        button.textContent = 'Confirmar sessão novamente';
        button.addEventListener('click', async () => {
            button.disabled = true;
            try { await completeAuthentication(pendingSessionUser); }
            finally { button.disabled = false; }
        });
        getElement('authMessage')?.append(button);
        if (error.code === 'session_account_mismatch') {
            const signOut = document.createElement('button');
            signOut.type = 'button';
            signOut.className = 'text-button';
            signOut.textContent = 'Sair dessa sessão';
            signOut.addEventListener('click', async () => {
                signOut.disabled = true;
                try {
                    const response = await window.fetchWithTimeout(`${API_BASE}/logout`, {
                        method: 'POST', credentials: 'include',
                        headers: { 'X-CSRF-Token': error.sessionCsrfToken },
                    });
                    if (!response.ok) throw new Error('Não foi possível sair. Tente novamente.');
                    await window.AppOffline?.clearAuth();
                    pendingSessionUser = null;
                    setCurrentUser(null);
                    setCsrfToken(null);
                    showAuthMessage('Entre usando o método original da sua conta.', 'info');
                } catch (_error) { showAuthMessage('Não foi possível sair. Tente novamente.', 'error'); }
                finally { signOut.disabled = false; }
            });
            getElement('authMessage')?.append(signOut);
        }
        return;
    } finally {
        sessionConfirmationInFlight = false;
        setGoogleAuthPending(false);
    }
    closeAppModal(getElement('loginScreen'));
    const intent = pendingAuthIntent;
    const destination = intent?.tab || viewForPath() || currentTab;
    pendingAuthIntent = null;
    finishAuthenticatedRoute(destination, { skipProfile: Boolean(intent?.resume) });
    window.AppOffline?.sync();
    if (!userNeedsOnboarding() && intent?.resume) resumeAfterAuthentication(intent.resume, intent.requiresProfile);
    showToast('Você entrou com sucesso.', 'success');
}

window.handleGoogleCredential = handleGoogleCredential;

Object.defineProperty(window, 'currentUser', { get: () => currentUser });
window.requireAuth = requireAuth;

function showMainScreen(options = {}) {
    authState = currentUser ? 'authenticated' : 'guest';
    document.body.dataset.authState = authState;
    const loginScreen = getElement('loginScreen');
    const mainScreen = getElement('mainScreen');
    getElement('dietTab')?.classList.toggle('today-authenticated', Boolean(currentUser));
    
    if (!options.refreshOnly && loginScreen?.classList.contains('show')) closeAppModal(loginScreen);
    if (mainScreen) mainScreen.classList.remove('hidden');
    
    const homeDate = getElement('homeDate');
    if (homeDate) {
        const formatted = new Intl.DateTimeFormat('pt-BR', {
            weekday: 'long',
            day: '2-digit',
            month: 'long'
        }).format(new Date());
        homeDate.textContent = formatted.charAt(0).toUpperCase() + formatted.slice(1);
    }

    if (currentUser) {
        const username = currentUser.username || 'Usuário';
        const initial = username.trim().charAt(0).toUpperCase() || 'U';
        ['headerUserInitial', 'homeUserInitial', 'profileUserInitial'].forEach(id => {
            const element = getElement(id);
            if (element) element.textContent = initial;
        });
        const profileUserName = getElement('profileUserName');
        if (profileUserName) profileUserName.textContent = username;
        const profileMembership = getElement('profileMembership');
        if (profileMembership) profileMembership.textContent = currentUser.is_premium ? 'Membro Premium' : 'Plano gratuito';
        renderProfileBadges(currentUser);
        window.applyCurrentUserAvatar?.(currentUser.avatar_url);


        const isAdmin = Boolean(currentUser.is_admin);
        getElement('adminPanelBtn')?.classList.toggle('hidden', !isAdmin);
        getElement('profileAdminLink')?.classList.toggle('hidden', !isAdmin);
    } else {
        ['headerUserInitial', 'homeUserInitial', 'profileUserInitial'].forEach(id => {
            const element = getElement(id);
            if (element) element.textContent = 'F';
        });
        const profileUserName = getElement('profileUserName');
        if (profileUserName) profileUserName.textContent = 'Conheça seu espaço';
        const profileMembership = getElement('profileMembership');
        if (profileMembership) profileMembership.textContent = 'Entre para acompanhar sua evolução';
        const profileBadges = getElement('profileBadges');
        if (profileBadges) profileBadges.innerHTML = '';
        getElement('adminPanelBtn')?.classList.add('hidden');
        getElement('profileAdminLink')?.classList.add('hidden');
        if (window.clearActiveWorkoutDock) window.clearActiveWorkoutDock();
    }

    getElement('guestAuthActions')?.classList.toggle('hidden', Boolean(currentUser));
    getElement('userHeaderButton')?.classList.toggle('hidden', !currentUser);
    const showHeaderPill = !currentUser;
    getElement('premiumHeaderPill')?.classList.toggle('hidden', !showHeaderPill);
    getElement('profileLoginAction')?.classList.toggle('hidden', Boolean(currentUser));
    getElement('profileLogoutAction')?.classList.toggle('hidden', !currentUser);
    getElement('editProfileBtn')?.classList.toggle('hidden', !currentUser);
    getElement('profileGuestPanel')?.classList.toggle('hidden', Boolean(currentUser));
    getElement('profileAuthenticatedContent')?.classList.toggle('hidden', !currentUser);
    getElement('progressGuestPanel')?.classList.toggle('hidden', Boolean(currentUser));
    getElement('progressAuthenticatedContent')?.classList.toggle('hidden', !currentUser);

    const chatNavBtn = document.querySelector(`.nav-btn[onclick="showTab('chat')"]`);
    if (chatNavBtn) {
        chatNavBtn.style.display = '';
        chatNavBtn.classList.toggle('is-locked', !hasAiAccess());
        chatNavBtn.setAttribute('aria-label', hasAiAccess() ? 'Assistente IA' : 'Assistente IA, recurso Premium');
    }

    const initialView = options.tab || viewForPath() || 'diet';
    if (!options.refreshOnly) showTab(initialView, { history: 'replace' });
    if (currentUser) {
        scheduleSecondaryLoads(options.skipProfile);
    } else {
        window.renderWorkoutTodayCard?.();
        scheduleSecondaryLoads(true);
    }
    window.dispatchEvent(new CustomEvent('diettracker:auth-ready', { detail: { user: currentUser } }));
}

function formatProfileHighlightLabel(highlight) {
    const item = highlight?.item || highlight;
    if (!item) return 'Destaque';
    if ((highlight?.target_kind || item.kind) === 'achievement') return item.title || 'Conquista';
    if ((highlight?.target_kind || item.kind) === 'badge') {
        const rank = item.badge_rank || item.badge?.badge_rank;
        if (item.code === 'pioneiro' && rank) return `${item.title} #${rank}`;
        return item.title || 'Insígnia';
    }
    return item.title || 'Destaque';
}

function renderProfileBadges(user) {
    const profileBadges = getElement('profileBadges');
    if (!profileBadges) return;
    const highlights = Array.isArray(user.profile_highlights) ? user.profile_highlights.slice(0, 3) : [];
    if (!highlights.length) {
        profileBadges.classList.add('hidden');
        return;
    }
    profileBadges.classList.remove('hidden');
    profileBadges.innerHTML = highlights.map(highlight => `<span class="profile-badge">${escapeHtml(formatProfileHighlightLabel(highlight))}</span>`).join('');
}

function selectionToken(item) {
    return `${item.kind}:${item.code}`;
}

function availableToken(item) {
    return `${item.kind}:${item.code}`;
}

function selectionLabel(selection) {
    const item = [...profileAchievementsState.achievements, ...profileAchievementsState.badges, ...profileAchievementsState.records].find(entry => availableToken(entry) === selectionToken(selection));
    if (item) return formatProfileHighlightLabel(item);
    return selection.kind === 'badge' ? selection.code : selection.code;
}

async function loadAchievementsTab() {
    if (!currentUser) return;
    const hero = getElement('achievementHero');
    const catalog = getElement('profileHighlightsAvailable');
    const badges = getElement('badgesCatalog');
    if (hero) hero.innerHTML = '<div class="plans-loading"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>Calculando sua trajetória...</span></div>';
    if (catalog) catalog.innerHTML = '<div class="plans-loading"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>Carregando conquistas...</span></div>';
    if (badges) badges.innerHTML = '';
    try {
        const response = await fetch(`${API_BASE}/progress/achievements`, { credentials: 'include' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Não foi possível carregar as conquistas.');
        if (!Array.isArray(data.items) || !Array.isArray(data.badges) || !Array.isArray(data.selected)) {
            throw new Error('O catálogo recebido está desatualizado. Recarregue a página.');
        }
        profileAchievementsState = {
            selected: data.selected.map(item => ({ kind: item.target_kind, code: item.item?.code })),
            achievements: data.items.map(item => ({ kind: 'achievement', ...item })),
            badges: data.badges.map(item => ({ kind: 'badge', ...item })),
            records: (data.personal_records || []).map(item => ({ kind: 'personal_record', code: String(item.id), title: item.exercise_name, ...item })),
            limit: Number(data.highlight_limit) || 3,
            filter: profileAchievementsState.filter || 'all',
            savingToken: null,
        };
        renderAchievementsTab();
    } catch (error) {
        if (hero) hero.innerHTML = `<div class="achievement-load-error"><strong>Não foi possível carre…23214 tokens truncated…   return setDietDailyOutcome(slotKey, mode === 'skip' ? 'skipped' : 'consumed_planned', 'home');
}

function dietDailyDateObject(value) {
    return new Date(`${value || localDateInputValue()}T12:00:00`);
}

function dietDailyDateText(value) {
    const today = localDateInputValue();
    if (value === today) return 'Hoje';
    const yesterday = dietDailyDateObject(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (value === localDateInputValue(yesterday)) return 'Ontem';
    return dietDailyDateObject(value).toLocaleDateString('pt-BR', {
        weekday: 'long', day: '2-digit', month: 'long'
    });
}

function dailySlotSelectedMeal(slot) {
    return (slot?.alternatives || []).find(meal => Number(meal.id) === Number(slot.selected_plan_meal_id))
        || slot?.alternatives?.[0]
        || null;
}

function dailyViewEntries(view = dietDailyView) {
    return [
        ...(view?.slots || []).map(slot => slot.entry).filter(Boolean),
        ...(view?.manual_entries || [])
    ];
}

function renderDietDailyMacros() {
    const container = getElement('dietDailyMacros');
    if (!container) return;
    const entries = dailyViewEntries();
    container.classList.remove('hidden');
    if (!entries.length) {
        container.innerHTML = '<header><span>Resumo do dia</span><small>Os macros aparecem após o primeiro registro.</small></header>';
        return;
    }
    const totals = dietDailyView?.totals || {};
    const targets = dietDailyView?.targets || {};
    const definitions = [
        ['calories', 'Calorias', 'kcal', 'flame'],
        ['protein', 'Proteínas', 'g', 'beef'],
        ['carbs', 'Carboidratos', 'g', 'wheat'],
        ['fat', 'Gorduras', 'g', 'droplet']
    ];
    container.innerHTML = `<header><span>Resumo do dia</span><small>${entries.length} ${entries.length === 1 ? 'registro' : 'registros'}</small></header><div class="diet-daily-macro-grid">${definitions.map(([key, label, unit, icon]) => {
        const value = Number(totals[key]) || 0;
        const target = Number(targets[key]);
        const hasTarget = Number.isFinite(target) && target > 0;
        const progress = hasTarget ? Math.min((value / target) * 100, 100) : 0;
        return `<article class="diet-daily-macro diet-daily-macro--${key}"><span class="diet-daily-macro__icon"><i data-lucide="${icon}" aria-hidden="true"></i></span><div><small>${label}</small><strong>${Math.round(value).toLocaleString('pt-BR')} ${unit}</strong>${hasTarget ? `<span>de ${Math.round(target).toLocaleString('pt-BR')} ${unit}</span>` : ''}</div>${hasTarget ? `<i class="diet-daily-macro__progress"><span style="width:${progress}%"></span></i>` : ''}</article>`;
    }).join('')}</div>`;
}

function dailyMealMacros(entry) {
    if (!entry) return '';
    const parts = [
        `${Math.round(Number(entry.calories) || 0)} kcal`,
        `${Math.round(Number(entry.protein) || 0)}g P`,
        `${Math.round(Number(entry.carbs) || 0)}g C`,
        `${Math.round(Number(entry.fat) || 0)}g G`
    ];
    return `<p class="diet-daily-slot__macros">${parts.join(' · ')}</p>`;
}

function dietSurfaceOptionsKey(surface) {
    return surface === 'home' ? todayDietOptionsSlotKey : dietDailyOptionsSlotKey;
}

function setDietSurfaceOptionsKey(surface, slotKey) {
    if (surface === 'home') todayDietOptionsSlotKey = slotKey;
    else dietDailyOptionsSlotKey = slotKey;
}

function renderDietDailyAlternatives(slot, selectedMeal, surface = 'diet') {
    if (dietSurfaceOptionsKey(surface) !== slot.slot_key) return '';
    return `<div class="diet-daily-options" aria-label="Alternativas de ${escapeHtml(slot.label)}">${(slot.alternatives || []).map(meal => `<button type="button" class="diet-daily-option${Number(meal.id) === Number(selectedMeal?.id) ? ' is-selected' : ''}" onclick="selectDietDailyOption('${slot.slot_key}', ${Number(meal.id)}, '${surface}')" aria-pressed="${Number(meal.id) === Number(selectedMeal?.id)}"><span><strong>Opção ${Number(meal.option) || 1}</strong><small>Dia ${Number(meal.option) || 1}</small></span><p>${escapeHtml(dietPlanItemsText(meal))}</p><i data-lucide="check" aria-hidden="true"></i></button>`).join('')}</div>`;
}

function closeDietDailyActions(immediate = false) {
    const overlay = document.querySelector('.diet-daily-actions-overlay');
    if (overlay) closeAppModal(overlay, { immediate });
}

function openDietDailyActions(slotKey, trigger) {
    const surface = trigger?.closest('[data-diet-surface]')?.dataset.dietSurface || 'diet';
    const slot = findDietSurfaceSlot(slotKey, surface);
    if (!slot || slot.result !== 'pending') return;
    closeDietDailyActions(true);

    const overlay = document.createElement('div');
    overlay.className = 'diet-daily-actions-overlay';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.innerHTML = `<div class="diet-daily-actions-sheet" role="dialog" aria-modal="true" aria-labelledby="dietDailyActionsTitle">
        <span class="diet-daily-actions-sheet__handle" aria-hidden="true"></span>
        <header><div><small>Opções da refeição</small><h3 id="dietDailyActionsTitle">${escapeHtml(slot.label || 'Refeição')}</h3></div><button type="button" class="diet-daily-actions-sheet__close" aria-label="Fechar"><i data-lucide="x" aria-hidden="true"></i></button></header>
        <button type="button" class="diet-daily-actions-sheet__item" data-action="consumed"><span><i data-lucide="check" aria-hidden="true"></i></span><div><strong>Marcar como consumida</strong><small>Registrar a opção planejada</small></div></button>
        <button type="button" class="diet-daily-actions-sheet__item" data-action="skip"><span><i data-lucide="forward" aria-hidden="true"></i></span><div><strong>Pular refeição</strong><small>Manter o dia atualizado</small></div></button>
        <button type="button" class="diet-daily-actions-sheet__item" data-action="different"><span><i data-lucide="utensils" aria-hidden="true"></i></span><div><strong>Comi diferente</strong><small>Registrar outra refeição consumida</small></div><i data-lucide="chevron-right" aria-hidden="true"></i></button>
        <button type="button" class="diet-daily-actions-sheet__item" data-action="options"${(slot.alternatives || []).length > 1 ? '' : ' disabled'}><span><i data-lucide="repeat-2" aria-hidden="true"></i></span><div><strong>Trocar opção</strong><small>${(slot.alternatives || []).length > 1 ? 'Ver alternativas desta refeição' : 'Nenhuma alternativa disponível'}</small></div><i data-lucide="chevron-right" aria-hidden="true"></i></button>
    </div>`;
    overlay.addEventListener('click', event => {
        if (event.target === overlay || event.target.closest('.diet-daily-actions-sheet__close')) {
            closeDietDailyActions();
            return;
        }
        const action = event.target.closest('[data-action]')?.dataset.action;
        if (action === 'consumed' || action === 'skip') {
            closeDietDailyActions(true);
            setDietDailyOutcome(slotKey, action === 'skip' ? 'skipped' : 'consumed_planned', surface);
        } else if (action === 'different') {
            closeDietDailyActions(true);
            openDietDailyDifferent(slotKey, surface);
        } else if (action === 'options') {
            closeDietDailyActions(true);
            toggleDietDailyOptions(slotKey, surface);
        }
    });
    document.body.appendChild(overlay);
    overlay.classList.add('is-open');
    openAppModal(overlay);
    overlay._modalTrigger = trigger || overlay._modalTrigger;
    window.lucide?.createIcons?.();
}

function startDietDailySwipe(event) {
    const surface = event.currentTarget.dataset.dietSurface || 'diet';
    if (!event.isPrimary || event.button > 0 || dietSurfaceMutationKey(surface)) return;
    if (event.target.closest('button, a, input, select, textarea, label')) return;
    const card = event.currentTarget;
    dietDailySwipeGesture = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        deltaX: 0,
        deltaY: 0,
        axis: null,
        startedAt: performance.now(),
        slotKey: card.dataset.slotKey,
        surface,
        card
    };
}

function moveDietDailySwipe(event) {
    const gesture = dietDailySwipeGesture;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    gesture.deltaX = event.clientX - gesture.startX;
    gesture.deltaY = event.clientY - gesture.startY;
    const x = Math.abs(gesture.deltaX);
    const y = Math.abs(gesture.deltaY);
    if (!gesture.axis && Math.max(x, y) >= 10) {
        if (x >= y * 1.35) {
            gesture.axis = 'horizontal';
            gesture.card.setPointerCapture?.(event.pointerId);
        } else if (y >= x * 1.2) {
            cancelDietDailySwipe(event);
            return;
        }
    }
    if (gesture.axis !== 'horizontal') return;
    event.preventDefault();
    const width = gesture.card.getBoundingClientRect?.().width || 320;
    const limit = Math.min(132, width * 0.4);
    const translated = Math.max(-limit, Math.min(limit, gesture.deltaX));
    const threshold = Math.min(112, Math.max(78, width * 0.28));
    gesture.card.style.setProperty('--diet-swipe-x', `${translated}px`);
    gesture.card.classList.toggle('is-swiping-right', translated > 0);
    gesture.card.classList.toggle('is-swiping-left', translated < 0);
    gesture.card.classList.toggle('is-swipe-ready', Math.abs(gesture.deltaX) >= threshold);
    gesture.card.parentElement?.classList.toggle('is-swiping-right', translated > 0);
    gesture.card.parentElement?.classList.toggle('is-swiping-left', translated < 0);
}

function endDietDailySwipe(event) {
    const gesture = dietDailySwipeGesture;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    gesture.deltaX = event.clientX - gesture.startX;
    gesture.deltaY = event.clientY - gesture.startY;
    const elapsed = Math.max(performance.now() - gesture.startedAt, 1);
    const velocity = Math.abs(gesture.deltaX) / elapsed * 1000;
    const width = gesture.card.getBoundingClientRect?.().width || 320;
    const threshold = Math.min(112, Math.max(78, width * 0.28));
    const horizontal = gesture.axis === 'horizontal' && Math.abs(gesture.deltaX) >= Math.abs(gesture.deltaY) * 1.35;
    const commits = horizontal && (Math.abs(gesture.deltaX) >= threshold || (Math.abs(gesture.deltaX) >= 52 && velocity >= 700));
    cancelDietDailySwipe(event);
    if (!commits) return;

    const result = gesture.deltaX > 0 ? 'skipped' : 'consumed_planned';
    if (gesture.surface === 'home') {
        setDietDailyOutcome(gesture.slotKey, result, gesture.surface);
        return;
    }
    gesture.card.classList.add(gesture.deltaX > 0 ? 'is-committing-right' : 'is-committing-left');
    gesture.card.parentElement?.classList.add(gesture.deltaX > 0 ? 'is-committing-right' : 'is-committing-left');
    const complete = () => setDietDailyOutcome(gesture.slotKey, result, gesture.surface);
    if (reducedMotion()) complete();
    else setTimeout(complete, 160);
}

function cancelDietDailySwipe(event) {
    const gesture = dietDailySwipeGesture;
    if (!gesture || (event && gesture.pointerId !== event.pointerId)) return;
    dietDailySwipeGesture = null;
    gesture.card.classList.remove('is-swiping-right', 'is-swiping-left', 'is-swipe-ready');
    gesture.card.parentElement?.classList.remove('is-swiping-right', 'is-swiping-left', 'is-committing-right', 'is-committing-left');
    gesture.card.style.removeProperty('--diet-swipe-x');
    if (gesture.card.hasPointerCapture?.(gesture.pointerId)) gesture.card.releasePointerCapture(gesture.pointerId);
}

function renderDietDailySlot(slot, surface = 'diet') {
    const meal = dailySlotSelectedMeal(slot);
    if (!meal) return '';
    const option = Number(meal.option) || 1;
    const saving = dietSurfaceMutationKey(surface) === slot.slot_key;
    const busy = saving ? ' disabled' : '';
    const title = escapeHtml(slot.label || meal.meal_type || 'Refeição');
    const plannedText = escapeHtml(dietPlanItemsText(slot.planned_snapshot || meal));
    const actual = slot.entry;
    const icon = mealIconName(slot.label || meal.meal_type);
    if (slot.result === 'skipped') {
        return `<article class="diet-daily-slot diet-daily-slot--compact"><span class="diet-daily-slot__icon"><i data-lucide="${icon}" aria-hidden="true"></i></span><div><h3>${title}</h3><p>Refeição pulada</p></div><span class="diet-daily-status diet-daily-status--skipped">Pulada</span><button type="button" class="text-button" onclick="resetDietDailySlot('${slot.slot_key}', '${surface}')"${busy}>Corrigir</button></article>`;
    }
    if (slot.result === 'consumed_planned') {
        return `<article class="diet-daily-slot diet-daily-slot--done"><header><span class="diet-daily-slot__icon"><i data-lucide="${icon}" aria-hidden="true"></i></span><div><h3>${title}</h3><p>Opção ${option} · Dia ${option}</p></div><span class="diet-daily-status diet-daily-status--done"><i data-lucide="check" aria-hidden="true"></i> Concluída</span></header><div class="diet-daily-actual"><span>Consumido</span><strong>${escapeHtml(actual?.description || plannedText)}</strong>${dailyMealMacros(actual)}</div><div class="diet-daily-slot__footer"><small>Conforme a opção planejada</small><div class="diet-daily-slot__record-actions"><button type="button" class="text-button" onclick="editDietEntry(${Number(actual?.id)})">Corrigir registro</button><button type="button" class="text-button diet-daily-skip" onclick="deleteDietEntry(${Number(actual?.id)})">Excluir registro</button></div></div></article>`;
    }
    if (slot.result === 'consumed_different') {
        return `<article class="diet-daily-slot diet-daily-slot--done"><header><span class="diet-daily-slot__icon"><i data-lucide="${icon}" aria-hidden="true"></i></span><div><h3>${title}</h3><p>Opção ${option} · Dia ${option}</p></div><span class="diet-daily-status diet-daily-status--done"><i data-lucide="check" aria-hidden="true"></i> Registrada</span></header><div class="diet-daily-actual"><span>Você consumiu</span><strong>${escapeHtml(actual?.description || 'Consumo registrado')}</strong>${dailyMealMacros(actual)}</div><div class="diet-daily-planned"><span>Estava previsto</span><p>${plannedText}</p></div><div class="diet-daily-slot__footer"><span></span><div class="diet-daily-slot__record-actions"><button type="button" class="text-button" onclick="editDietEntry(${Number(actual?.id)})">Corrigir registro</button><button type="button" class="text-button diet-daily-skip" onclick="deleteDietEntry(${Number(actual?.id)})">Excluir registro</button></div></div></article>`;
    }
    const alternatives = slot.alternatives || [];
    return `<div class="diet-daily-swipe"><div class="diet-daily-swipe__action diet-daily-swipe__action--skip" aria-hidden="true"><i data-lucide="forward" aria-hidden="true"></i><span>Pular refeição</span></div><div class="diet-daily-swipe__action diet-daily-swipe__action--consumed" aria-hidden="true"><span>Marcar como consumida</span><i data-lucide="check" aria-hidden="true"></i></div><article class="diet-daily-slot diet-daily-slot__surface${saving ? ' is-saving' : ''}" aria-busy="${saving}" data-slot-key="${slot.slot_key}" data-diet-surface="${surface}" onpointerdown="startDietDailySwipe(event)" onpointermove="moveDietDailySwipe(event)" onpointerup="endDietDailySwipe(event)" onpointercancel="cancelDietDailySwipe(event)"><header><span class="diet-daily-slot__icon"><i data-lucide="${icon}" aria-hidden="true"></i></span><div><h3>${title}</h3><p>${alternatives.length > 1 ? `Opção ${option} de ${alternatives.length}` : 'Refeição planejada'}</p></div><div class="diet-daily-slot__header-actions"><button type="button" class="diet-daily-more" onclick="openDietDailyActions('${slot.slot_key}', this)" aria-label="Mais opções para ${title}" aria-haspopup="dialog"${busy}><i data-lucide="ellipsis" aria-hidden="true"></i></button></div></header><p class="diet-daily-slot__food">${escapeHtml(dietPlanItemsText(meal))}</p>${dailyMealMacros(meal)}<div class="diet-daily-slot__saving" role="status">${saving ? 'Salvando refeição…' : ''}</div><div class="diet-daily-swipe__hint" aria-hidden="true"><span><i data-lucide="arrow-left" aria-hidden="true"></i> Consumida</span><span>Pular <i data-lucide="arrow-right" aria-hidden="true"></i></span></div>${renderDietDailyAlternatives(slot, meal, surface)}</article></div>`;
}

function renderDietDailyManualEntry(entry) {
    return `<article class="diet-daily-manual"><span class="diet-daily-slot__icon"><i data-lucide="${mealIconName(entry.meal_type)}" aria-hidden="true"></i></span><div><span>Registro adicional</span><h3>${escapeHtml(getMealTypeLabel(entry.meal_type))}</h3><p>${escapeHtml(entry.description)}</p>${dailyMealMacros(entry)}</div><div class="diet-daily-manual__actions"><button type="button" class="text-button" onclick="editDietEntry(${Number(entry.id)})">Corrigir</button><button type="button" class="text-button diet-daily-skip" onclick="deleteDietEntry(${Number(entry.id)})">Excluir</button></div></article>`;
}

function renderDietDailyMeals(errorMessage = '') {
    const container = getElement('dietDailyMealsBody');
    if (!container) return;
    if (errorMessage) {
        container.innerHTML = `<div class="diet-daily-empty" role="alert"><strong>Não foi possível carregar o diário.</strong><p>${escapeHtml(errorMessage)}</p><button type="button" class="btn-secondary" onclick="loadDietDailyScreen()">Tentar novamente</button></div>`;
        return;
    }
    const slots = dietDailyView?.slots || [];
    const manual = dietDailyView?.manual_entries || [];
    if (!slots.length && !manual.length) {
        container.innerHTML = '<div class="diet-daily-empty"><span class="diet-daily-slot__icon"><i data-lucide="utensils" aria-hidden="true"></i></span><div><strong>Nenhuma refeição registrada</strong><p>Use “Registrar outra refeição” quando quiser adicionar o que consumiu.</p></div></div>';
        return;
    }
    container.innerHTML = `${slots.map(slot => renderDietDailySlot(slot, 'diet')).join('')}${manual.length ? `<div class="diet-daily-additional"><h3>Outras refeições</h3>${manual.map(renderDietDailyManualEntry).join('')}</div>` : ''}`;
}

function renderDietDailyPlan() {
    const container = getElement('dietDailyPlan');
    if (!container) return;
    const plan = dietDailyView?.plan;
    if (!plan) {
        cardapioActivePlan = null;
        container.innerHTML = '<div><span class="eyebrow">Plano alimentar</span><h2 id="dietDailyPlanTitle">Sem plano atual</h2><p>O diário funciona normalmente sem um plano.</p></div><button type="button" class="btn-primary" data-plan-wizard="diet"><i class="fas fa-plus" aria-hidden="true"></i> Criar plano alimentar</button>';
        return;
    }
    cardapioActivePlan = plan;
    container.innerHTML = `<div><span class="eyebrow">Plano alimentar atual</span><h2 id="dietDailyPlanTitle">${escapeHtml(plan.title || 'Seu plano alimentar')}</h2></div><div class="diet-daily-plan__actions"><button type="button" class="text-button" onclick="window.viewDietPlan?.(${Number(plan.id)})">Ver plano</button><button type="button" class="text-button" onclick="editDailyNutritionTargets()">Editar plano</button><button type="button" class="text-button" onclick="toggleDietPlansLibrary(true)">Meus planos</button></div>`;
}

function updateDietDailyDateHeader() {
    const value = dietDailyDate || localDateInputValue();
    const input = getElement('dietDailyDate');
    if (input) input.value = value;
    const label = getElement('dietDailyDateLabel');
    if (label) label.textContent = dietDailyDateText(value);
    getElement('dietDailyTodayButton')?.classList.toggle('hidden', value === localDateInputValue());
}

async function loadDietDailyScreen(dateValue = dietDailyDate || localDateInputValue()) {
    if (!currentUser) {
        renderGuestPresentation('diet_plans');
        return;
    }
    const owner = currentUser.id;
    const revision = ++dietScreenRequestVersion;
    dietDailyDate = dateValue;
    dietDailyOptionsSlotKey = null;
    updateDietDailyDateHeader();
    const container = getElement('dietDailyMealsBody');
    if (container && dietDailyView?.date !== dateValue) container.innerHTML = '<div class="diet-daily-empty"><span class="today-icon--spin"><i data-lucide="loader-circle" aria-hidden="true"></i></span><div><strong>Carregando seu dia</strong></div></div>';
    try {
        const data = await loadDietDay(dateValue);
        if (owner !== currentUser?.id || revision !== dietScreenRequestVersion || dietDailyDate !== dateValue) return;
        dietDailyView = data;
        dietEntries = dailyViewEntries(dietDailyView);
        renderDietDailyMacros();
        renderDietDailyMeals();
        renderDietDailyPlan();
    } catch (error) {
        if (error.name === 'AbortError' || owner !== currentUser?.id || revision !== dietScreenRequestVersion) return;
        dietDailyView = null;
        getElement('dietDailyMacros')?.classList.add('hidden');
        renderDietDailyMeals(error.message);
        const planContainer = getElement('dietDailyPlan');
        if (planContainer) planContainer.innerHTML = '<div><span class="eyebrow">Plano alimentar</span><h2 id="dietDailyPlanTitle">Plano indisponível</h2><p>Tente carregar o diário novamente.</p></div>';
    }
}

function changeDietDailyDate(offset) {
    const next = dietDailyDateObject(dietDailyDate || localDateInputValue());
    next.setDate(next.getDate() + Number(offset || 0));
    loadDietDailyScreen(localDateInputValue(next));
}

function selectDietDailyDate(value = localDateInputValue()) {
    if (!value) return;
    loadDietDailyScreen(value);
}

function openDietDailyCalendar() {
    const input = getElement('dietDailyDate');
    if (typeof input?.showPicker === 'function') input.showPicker();
    else input?.focus();
}

function showAddDietModalForDailyDate() {
    showAddDietModal();
    if (!getElement('dietModal')?.classList.contains('show')) return;
    getElement('dietDate').value = dietDailyDate || localDateInputValue();
}

function toggleDietDailyOptions(slotKey, surface = 'diet') {
    const opening = dietSurfaceOptionsKey(surface) !== slotKey;
    const container = getElement(surface === 'home' ? 'todayCardapioBody' : 'dietDailyMealsBody');
    const card = Array.from(container?.querySelectorAll('[data-slot-key]') || [])
        .find(node => node.dataset.slotKey === slotKey);
    setDietSurfaceOptionsKey(surface, opening ? slotKey : null);
    if (!card) { renderDietSurface(surface); return; }
    container.querySelectorAll('.diet-daily-options').forEach(panel => {
        if (panel.contains(document.activeElement)) (panel._returnFocus || panel.closest('[data-slot-key]')?.querySelector('.diet-daily-more'))?.focus({ preventScroll: true });
        panel.inert = true;
        window.Fluid?.stop(panel);
        if (window.Fluid && !reducedMotion()) {
            window.Fluid.animate(panel, { y: -4, opacity: 0 }, { duration: 140, onComplete: () => panel.remove() });
        } else panel.remove();
    });
    if (!opening) return;
    const slot = findDietSurfaceSlot(slotKey, surface);
    if (!slot) return;
    const template = document.createElement('template');
    template.innerHTML = renderDietDailyAlternatives(slot, dailySlotSelectedMeal(slot), surface);
    const panel = template.content.firstElementChild;
    panel._returnFocus = card.querySelector('.diet-daily-more');
    panel.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        event.preventDefault();
        event.stopPropagation();
        toggleDietDailyOptions(slotKey, surface);
    });
    card.appendChild(panel);
    panel.querySelector('button')?.focus({ preventScroll: true });
    window.Fluid?.animate(panel, { y: 0, opacity: 1 }, { from: { y: reducedMotion() ? 0 : 5, opacity: 0 }, duration: 160 });
    window.lucide?.createIcons?.();
}

async function selectDietDailyOption(slotKey, mealId, surface = 'diet') {
    if (dietSurfaceMutationKey(surface)) return;
    const slot = findDietSurfaceSlot(slotKey, surface);
    if (!slot) return;
    const returnFocus = Boolean(document.activeElement?.closest('.diet-daily-options'));
    setDietSurfaceMutationKey(surface, slotKey);
    renderDietSurface(surface);
    try {
        const response = await fetch(`${API_BASE}/diet/days/${encodeURIComponent(dietSurfaceDate(surface))}/slots/${encodeURIComponent(slotKey)}/selection`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
            body: JSON.stringify({ diet_plan_meal_id: mealId })
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || 'Não foi possível trocar a opção.');
        }
        slot.selected_plan_meal_id = mealId;
        setDietSurfaceOptionsKey(surface, null);
        await refreshDietDailySurfaces(surface === 'home');
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        setDietSurfaceMutationKey(surface, null);
        renderDietSurface(surface);
        if (returnFocus && document.activeElement === document.body) {
            const container = getElement(surface === 'home' ? 'todayCardapioBody' : 'dietDailyMealsBody');
            Array.from(container?.querySelectorAll('[data-slot-key]') || [])
                .find(node => node.dataset.slotKey === slotKey)?.querySelector('.diet-daily-more')?.focus({ preventScroll: true });
        }
    }
}

function openDietDailyDifferent(slotKey, surface = 'diet') {
    const slot = findDietSurfaceSlot(slotKey, surface);
    const meal = dailySlotSelectedMeal(slot);
    if (!slot || !meal) return;
    showAddDietModal();
    pendingDietDailyContext = { slotKey, mealId: meal.id, surface };
    getElement('dietDate').disabled = true;
    getElement('dietMeal').disabled = true;
    getElement('dietDate').value = dietSurfaceDate(surface);
    getElement('dietMeal').value = cardapioMealTypeToEntry(meal.meal_type);
    getElement('dietDescription').value = '';
    syncChoiceCards();
}

function animateHomeMealRemoval(slotKey) {
    const card = Array.from(getElement('todayCardapioBody')?.querySelectorAll('[data-home-slot-key]') || [])
        .find(node => node.dataset.homeSlotKey === slotKey);
    if (!card || !window.Fluid || reducedMotion()) return;
    const hadFocus = card.contains(document.activeElement);
    card._homeLeaving = true;
    card.inert = true;
    window.Fluid.animate(card, { y: -8, opacity: 0 }, {
        duration: 140,
        onComplete() {
            if (!card._homeLeaving) return;
            card.remove();
            if (hadFocus) focusHomeMeal();
        }
    });
}

function invalidateHomeMealReads() {
    homeRequestVersion++;
    dietScreenRequestVersion++;
    window.AppReadCache.invalidate('diet:');
}

function refreshHomeMealsInBackground() {
    // The write is already confirmed. Read failures must not turn it into a save error.
    void refreshDietDailySurfaces(true).catch(() => {});
}

function applyHomeMealOutcome(slotKey, date, state) {
    if (todayDietDay?.date !== date) return;
    const slot = findDietSurfaceSlot(slotKey, 'home');
    if (!slot) return;
    const previous = slot.entry;
    const entry = state?.entry || null;
    for (const key of ['calories', 'protein', 'carbs', 'fat']) {
        todayDietDay.totals[key] = (Number(todayDietDay.totals[key]) || 0)
            - (Number(previous?.[key]) || 0) + (Number(entry?.[key]) || 0);
    }
    Object.assign(slot, state || { result: 'pending', entry: null });
    dietEntries = dailyViewEntries(todayDietDay);
    updateDailySummary();
    renderTodayRecentMeals();
}

function applyHomeDietEntry(entry) {
    const slot = todayDietDay.slots?.find(item => item.entry?.id === entry.id);
    if (slot && entry.date === todayDietDay.date) {
        applyHomeMealOutcome(slot.slot_key, entry.date, { ...slot, entry });
        return;
    }
    const entries = todayDietDay.manual_entries ||= [];
    const index = entries.findIndex(item => item.id === entry.id);
    const previous = index >= 0 ? entries[index] : slot?.entry;
    if (index >= 0) entries.splice(index, 1);
    if (slot) Object.assign(slot, { result: 'pending', entry: null });
    const current = entry.date === todayDietDay.date ? entry : null;
    if (current) entries.push(current);
    for (const key of ['calories', 'protein', 'carbs', 'fat']) {
        todayDietDay.totals[key] = (Number(todayDietDay.totals[key]) || 0)
            - (Number(previous?.[key]) || 0) + (Number(current?.[key]) || 0);
    }
    dietEntries = dailyViewEntries(todayDietDay);
    renderTodayCardapio(todayDietDay);
    renderTodayRecentMeals();
}

function focusHomeMeal(slotKey) {
    if (document.activeElement !== document.body && document.activeElement?.isConnected) return;
    const body = getElement('todayCardapioBody');
    const card = Array.from(body?.querySelectorAll('[data-slot-key]') || []).find(node => node.dataset.slotKey === slotKey);
    (card?.querySelector('button:not(:disabled)') || body?.querySelector('button:not(:disabled)'))?.focus({ preventScroll: true });
}

async function setDietDailyOutcome(slotKey, result, surface = 'diet') {
    if (dietSurfaceMutationKey(surface)) return;
    const slot = findDietSurfaceSlot(slotKey, surface);
    const meal = dailySlotSelectedMeal(slot);
    if (!slot || !meal || slot.result !== 'pending') return;
    const date = dietSurfaceDate(surface);
    const restoreFocus = surface === 'home' && getElement('todayCardapioBody')?.contains(document.activeElement);
    const owner = currentUser?.id;
    let saved = false;
    setDietSurfaceMutationKey(surface, slotKey);
    if (surface === 'home') invalidateHomeMealReads();
    renderDietSurface(surface);
    try {
        const response = await fetch(`${API_BASE}/diet/days/${encodeURIComponent(date)}/slots/${encodeURIComponent(slotKey)}/outcome`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
            body: JSON.stringify({ result, diet_plan_meal_id: meal.id })
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || 'Não foi possível atualizar a refeição.');
        }
        if (owner !== currentUser?.id) return;
        if (surface === 'home') {
            const data = await response.json();
            if (owner !== currentUser?.id) return;
            if (data.state?.result !== result) throw new Error('Não foi possível confirmar a refeição. Tente atualizar o dia.');
            applyHomeMealOutcome(slotKey, date, data.state);
            if (result === 'consumed_planned' && todayDietDay?.date === date) animateHomeMealRemoval(slotKey);
        }
        saved = true;
        if (surface !== 'home') await refreshDietDailySurfaces();
    } catch (error) {
        if (owner === currentUser?.id) showToast(error.message, 'error');
    } finally {
        if (owner !== currentUser?.id) return;
        setDietSurfaceMutationKey(surface, null);
        renderDietSurface(surface);
        if (restoreFocus) focusHomeMeal(slotKey);
    }
    if (saved) {
        if (surface === 'home') refreshHomeMealsInBackground();
        showToast(result === 'skipped' ? 'Refeição marcada como pulada.' : 'Refeição registrada!', 'success',
            result === 'skipped' || surface === 'home' ? {
                actionLabel: 'Desfazer', duration: 5000,
                onAction: () => resetDietDailySlot(slotKey, surface, date)
            } : {});
    }
}

async function resetDietDailySlot(slotKey, surface = 'diet', date = dietSurfaceDate(surface)) {
    if (dietSurfaceMutationKey(surface)) return;
    const owner = currentUser?.id;
    let saved = false;
    setDietSurfaceMutationKey(surface, slotKey);
    if (surface === 'home') invalidateHomeMealReads();
    try {
        const response = await fetch(`${API_BASE}/diet/days/${encodeURIComponent(date)}/slots/${encodeURIComponent(slotKey)}/outcome`, {
            method: 'DELETE', credentials: 'include'
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || 'Não foi possível reabrir a refeição.');
        }
        if (owner !== currentUser?.id) return;
        if (surface === 'home') {
            const data = response.status === 204 ? null : await response.json();
            if (owner !== currentUser?.id) return;
            applyHomeMealOutcome(slotKey, date, data?.state);
        }
        saved = true;
        if (surface !== 'home') await refreshDietDailySurfaces();
    } catch (error) {
        if (owner === currentUser?.id) showToast(error.message, 'error');
    } finally {
        if (owner !== currentUser?.id) return;
        setDietSurfaceMutationKey(surface, null);
        renderDietSurface(surface);
        if (surface === 'home') focusHomeMeal(slotKey);
    }
    if (saved && surface === 'home') refreshHomeMealsInBackground();
}

async function refreshDietDailySurfaces(includeHome = false) {
    window.AppReadCache.invalidate('diet:');
    await Promise.all([
        loadDietDailyScreen(dietDailyDate || localDateInputValue()),
        includeHome || dietDailyDate === localDateInputValue() ? loadTodayCardapio({ force: true }) : Promise.resolve()
    ]);
}

async function toggleDietPlansLibrary(show) {
    const library = getElement('dietPlansLibrary');
    if (!library) return;
    library.classList.toggle('hidden', !show);
    if (!show || dietPlansLibraryLoaded) return;
    dietPlansLibraryLoaded = true;
    await window.loadDietPlans?.();
}

async function openEditPlanMealModal(mealId) {
    const meal = findPlanMeal(mealId);
    if (!meal) return;
    getElement("editPlanMealId").value = meal.id;
    getElement("editPlanMealDescription").value = dietPlanItemsRawText(meal);
    getElement("editPlanMealNotes").value = meal.notes || "";
    getElement("editPlanMealTitle").textContent = `Editar ${meal.meal_type}`;
    openAppModal(getElement("editPlanMealModal"));
}

function closeEditPlanMealModal() {
    closeAppModal(getElement("editPlanMealModal"));
}

async function handleEditPlanMealSubmit(e) {
    e.preventDefault();
    const mealId = getElement("editPlanMealId").value;
    const description = getElement("editPlanMealDescription").value.trim();
    const notes = getElement("editPlanMealNotes").value.trim();
    if (!description) {
        showToast("A descrição da refeição é obrigatória.", "error");
        return;
    }
    try {
        const response = await fetch(`${API_BASE}/diet_plans/${cardapioActivePlan.id}/meals/${mealId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ description, notes })
        });
        if (response.ok) {
            closeEditPlanMealModal();
            showToast("Refeição do plano atualizada!", "success");
            loadDietPlans();
            loadTodayCardapio();
        } else {
            const errorData = await response.json();
            showToast(errorData.error || "Erro ao atualizar!", "error");
        }
    } catch (error) {
        showToast("Erro de conexão!", "error");
    }
}

function openSuggestDietModal() {
    pendingDietDaySuggestion = null;
    getElement("suggestDietFeedback").value = "";
    getElement("suggestDietFeedback").disabled = false;
    getElement("suggestDietPreview").classList.add("hidden");
    getElement("suggestDietApplyBtn").classList.add("hidden");
    getElement("suggestDietGenerateBtn").classList.remove("hidden");
    openAppModal(getElement("suggestDietModal"));
}

function closeSuggestDietModal() {
    closeAppModal(getElement("suggestDietModal"));
}

async function generateDietDaySuggestion() {
    const feedback = getElement("suggestDietFeedback").value.trim();
    if (!feedback) {
        showToast("Descreva a mudança desejada.", "error");
        return;
    }
    const generateBtn = getElement("suggestDietGenerateBtn");
    generateBtn.disabled = true;
    generateBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Gerando...';
    try {
        const response = await fetch(`${API_BASE}/diet_plans/${cardapioActivePlan.id}/suggest`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ day: cardapioDay, feedback })
        });
        if (response.ok) {
            let data = await response.json();
            if (response.status === 202 && data.job_id) data = await window.waitForAIJob(data);
            pendingDietDaySuggestion = data.meals;
            const previewEl = getElement("suggestDietPreview");
            previewEl.innerHTML = data.meals.map(meal => `
                <article class="suggest-meal">
                    <div><strong>${escapeHtml(meal.meal_type)}</strong><p>${escapeHtml(dietPlanItemsText(meal))}</p></div>
                    <div class="cardapio-item__macros"><span>${Math.round(Number(meal.calories) || 0)} kcal</span><span>${Math.round(Number(meal.protein) || 0)}g prot.</span></div>
                </article>`).join('');
            previewEl.classList.remove("hidden");
            getElement("suggestDietApplyBtn").classList.remove("hidden");
            getElement("suggestDietGenerateBtn").classList.add("hidden");
            getElement("suggestDietFeedback").disabled = true;
        } else {
            const errorData = await response.json();
            showToast(errorData.error || "Erro ao gerar sugestão!", "error");
        }
    } catch (error) {
        showToast("Erro de conexão!", "error");
    } finally {
        generateBtn.disabled = false;
    }
}

async function applyDietDaySuggestion() {
    const meals = pendingDietDaySuggestion;
    if (!Array.isArray(meals) || !meals.length) return;
    const applyBtn = getElement("suggestDietApplyBtn");
    applyBtn.disabled = true;
    try {
        const response = await fetch(`${API_BASE}/diet_plans/${cardapioActivePlan.id}/days/${cardapioDay}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ meals })
        });
        if (response.ok) {
            closeSuggestDietModal();
            showToast("Cardápio do dia atualizado!", "success");
            loadDietPlans();
            loadTodayCardapio();
        } else {
            const errorData = await response.json();
            showToast(errorData.error || "Erro ao aplicar!", "error");
        }
    } catch (error) {
        showToast("Erro de conexão!", "error");
    } finally {
        applyBtn.disabled = false;
    }
}

function renderMeasurementTable() {
    const container = getElement("measurementTableBody");
    if (!container) return;

    if (!measurements.length) {
        container.innerHTML = `
            <div class="empty-state">
                <span><i class="fas fa-ruler-combined"></i></span>
                <div><strong>Nenhuma medição encontrada</strong><p>Registre uma medição ou ajuste o período selecionado.</p><button type="button" onclick="showAddMeasurementModal()">Nova medição</button><button type="button" onclick="clearMeasurementFilters()">Limpar período</button></div>
            </div>`;
        return;
    }

    container.innerHTML = measurements.map(measurement => `
        <article class="measurement-card">
            <header><div><span class="measurement-card__date"><i class="far fa-calendar"></i> ${formatDate(measurement.date)}</span><h3>${measurement.weight != null ? `${escapeHtml(measurement.weight)} kg` : 'Medição corporal'}</h3></div><div class="entry-actions"><button type="button" onclick="editMeasurement(${Number(measurement.id)})" class="entry-action" aria-label="Editar medição"><i class="fas fa-pen"></i></button><button type="button" onclick="deleteMeasurement(${Number(measurement.id)})" class="entry-action entry-action--danger" aria-label="Excluir medição"><i class="fas fa-trash"></i></button></div></header>
            <div class="measurement-card__metrics">
                ${measurementMetric('Altura', measurement.height, ' cm')}
                ${measurementMetric('Gordura', measurement.body_fat, '%')}
                ${measurementMetric('Massa muscular', measurement.muscle_mass, ' kg')}
                ${measurementMetric('Cintura', measurement.waist, ' cm')}
                ${measurementMetric('Peito', measurement.chest, ' cm')}
                ${measurementMetric('Braço', measurement.arm, ' cm')}
                ${measurementMetric('Coxa', measurement.thigh, ' cm')}
            </div>
            ${measurement.notes ? `<p class="measurement-card__notes"><i class="far fa-note-sticky"></i> ${escapeHtml(measurement.notes)}</p>` : ''}
        </article>`).join('');

    if (measurementHasMore) {
        container.insertAdjacentHTML('beforeend', `<div class="profile-load-more"><button type="button" onclick="loadMeasurements(true)">Carregar mais</button></div>`);
    }
}


async function handleProfileSubmit(e) {
    e.preventDefault();

    const age = getElement("profileAge")?.value;
    const gender = getElement("profileGender")?.value;
    const goal = getElement("profileGoal")?.value;
    const activity = getElement("profileActivity")?.value;
    const restrictions = getElement("profileRestrictions")?.value.trim();
    const weight = getElement("profileWeight")?.value;
    const height = normalizeNaturalHeight(getElement("profileHeight")?.value);
    const timezone = getElement("profileTimezone")?.value || profileTimezoneValue();

    if (pendingProfileRequiredFields.length || mandatoryOnboarding) {
        const requiredFields = mandatoryOnboarding ? missingOnboardingFieldsFromForm() : pendingProfileRequiredFields;
        const values = {
            goal,
            age: Number(age),
            gender,
            activity_level: activity,
            weight: Number(weight),
            height
        };
        const valid = {
            goal: Boolean(values.goal),
            age: Number.isFinite(values.age) && values.age >= 18 && values.age <= 120,
            gender: Boolean(values.gender),
            activity_level: Boolean(values.activity_level),
            weight: Number.isFinite(values.weight) && values.weight >= 30 && values.weight <= 300,
            height: Number.isFinite(values.height) && values.height >= 120 && values.height <= 250
        };
        const firstMissing = requiredFields.find(field => !valid[field]);
        if (firstMissing) {
            const focusTargets = {
                goal: 'goalCards',
                age: 'profileAge',
                gender: 'genderCards',
                activity_level: 'activityCards',
                weight: 'profileWeight',
                height: 'profileHeight'
            };
            showToast(mandatoryOnboarding ? 'Complete os dados mínimos para preparar sua Home.' : 'Preencha os dados obrigatórios para gerar sua dieta.', 'error');
            getElement(focusTargets[firstMissing])?.focus();
            return;
        }
    }

    try {
        const response = await fetch(`${API_BASE}/profile`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            credentials: "include",
            body: JSON.stringify({
                age: age ? parseInt(age) : null,
                gender: gender,
                goal: goal,
                activity_level: activity,
                dietary_restrictions: restrictions,
                weight: weight ? parseFloat(weight) : null,
                height: height,
                timezone
            })
        });

        if (response.ok) {
            const data = await response.json().catch(() => ({}));
            if (data.profile && currentUser) {
                currentProfile = data.profile;
                currentUser = {
                    ...currentUser,
                    onboarding_status: data.onboarding_status,
                    profile_missing_fields: data.profile_missing_fields || [],
                    profile_complete: Boolean(data.profile_complete)
                };
                window.currentUser = currentUser;
            }
            const resume = pendingPostProfileResume;
            pendingPostProfileResume = null;
            pendingProfileRequiredFields = [];
            const wasMandatory = mandatoryOnboarding;
            setOnboardingRequired(false);
            closeAppModal(getElement("profileModal"));
            showToast("Perfil salvo com sucesso!", "success");
            if (wasMandatory) {
                showMainScreen({ tab: pendingOnboardingDestination || 'diet', skipProfile: true });
                pendingOnboardingDestination = null;
                renderPersonalizedHomeIntro(data.profile);
                await Promise.all([loadTodayCardapio({ force: true }), window.loadWorkoutTodayCard?.(true)]);
            } else if (resume) {
                requestAnimationFrame(resume);
            }
        } else {
            const data = await response.json();
            showToast(data.error || "Erro ao salvar perfil", "error");
        }
    } catch (error) {
        console.error("Profile submit error:", error);
        showToast("Erro de conexão", "error");
    }
}

// Edit and Delete functions
async function editDietEntry(id) {
    const entry = dietEntries.find(e => e.id === id);
    if (!entry) return;
    
    getElement("dietId").value = entry.id;
    getElement("dietDate").value = entry.date;
    getElement("dietMeal").value = entry.meal_type;
    getElement("dietDescription").value = entry.description;
    getElement("dietNotes").value = entry.notes || "";
    
    // Preenche os campos de macros se existirem
    getElement("dietCalories").value = entry.calories ?? "";
    getElement("dietProtein").value = entry.protein ?? "";
    getElement("dietCarbs").value = entry.carbs ?? "";
    getElement("dietFat").value = entry.fat ?? "";
    getElement("dietDate").disabled = Boolean(entry.daily_meal_state_id);
    getElement("dietMeal").disabled = Boolean(entry.daily_meal_state_id);

    pendingDietDailyContext = null;
    window.DietEntryFlow?.begin(true);
    syncChoiceCards();
    openAppModal(getElement("dietModal"));
}

async function deleteDietEntry(id) {
    if (!confirm("Tem certeza que deseja excluir esta refeição?")) return;
    showToast("Excluindo...", "info");
    try {
        const response = await fetch(`/api/diet/${id}`, { method: "DELETE", credentials: 'include' });
        if (response.ok) {
            showToast("Refeição excluída!", "success");
            if (currentTab === 'diet_plans') await refreshDietDailySurfaces();
            else await loadTodayCardapio({ force: true });
        } else {
            const errorData = await response.json();
            showToast(errorData.error || "Erro ao excluir!", "error");
        }
    } catch (e) {
        showToast("Erro de conexão!", "error");
    }
}

async function editMeasurement(id) {
    const measurement = measurements.find(m => m.id === id);
    if (!measurement) return;
    
    getElement("measurementId").value = measurement.id;
    getElement("measurementDate").value = measurement.date;
    getElement("measurementWeight").value = measurement.weight || "";
    getElement("measurementHeight").value = measurement.height || "";
    getElement("measurementBodyFat").value = measurement.body_fat || "";
    getElement("measurementMuscleMass").value = measurement.muscle_mass || "";
    getElement("measurementWaist").value = measurement.waist || "";
    getElement("measurementChest").value = measurement.chest || "";
    getElement("measurementArm").value = measurement.arm || "";
    getElement("measurementThigh").value = measurement.thigh || "";
    getElement("measurementNotes").value = measurement.notes || "";
    
    getElement("measurementModalTitle").textContent = "Editar Medidas";
    openAppModal(getElement("measurementModal"));
}

async function deleteMeasurement(id) {
    const accountVersion = measurementAccountVersion;
    if (!confirm("Tem certeza que deseja excluir esta medição?")) return;
    showToast("Excluindo...", "info");
    try {
        const response = await fetch(`/api/measurements/${id}`, { method: "DELETE", credentials: 'include' });
        if (accountVersion !== measurementAccountVersion) return;
        if (response.ok) {
            showToast("Medição excluída!", "success");
            await Promise.all([loadMeasurements(), loadMeasurementSummary()]);
        } else {
            const errorData = await response.json();
            showToast(errorData.error || "Erro ao excluir!", "error");
        }
    } catch (e) {
        showToast("Erro de conexão!", "error");
    }
}

// Filter and Chat functions
function clearDietFilters() {
    loadDietEntries();
}
function clearMeasurementFilters() {
    setBodyPeriod('all');
}

function clearChat() {
    renderChatWelcome();
}

function renderChatWelcome() {
    const chatMessages = getElement("chatMessages");
    if (!chatMessages) return;
    
    chatMessages.innerHTML = `
        <div class="chat-message bot-message">
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-content">
                <p>Olá! 👋 Sou seu assistente fitness pessoal. Posso gerar planos de dieta e treino. Como posso ajudá-lo hoje?</p>
            </div>
        </div>
    `;
}

async function loadChatHistory() {
    renderChatWelcome();
    if (!currentUser || !currentUser.is_premium) return;

    try {
        const response = await fetch(`${API_BASE}/chat/history`, { credentials: 'include' });
        if (!response.ok) return;

        const history = await response.json();
        if (!history.length) return;

        const chatMessages = getElement("chatMessages");
        chatMessages.innerHTML = '';
        history.forEach((entry) => {
            addMessageToChat(entry.message, 'user');
            addMessageToChat(entry.response, 'bot');
        });
    } catch (error) {
        console.error('Error loading chat history:', error);
    }
}

async function checkUserProfile() {
    try {
        const response = await fetch(`${API_BASE}/profile`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            if (!data.profile) {
                setTimeout(() => {
                    if (!currentUser) return;
                    const profileModal = getElement("profileModal");
                    if (profileModal) {
                        openAppModal(profileModal);
                    }
                }, 1000);
            } else {
                fillProfileForm(data.profile);
            }
        }
    } catch (error) {
        console.error('Error checking profile:', error);
    }
}

// --- SUGESTÕES PENDENTES (REMOVIDAS PARA ESTE ESCOPO) ---
// As funções loadPendingDietSuggestions, loadPendingWorkoutSuggestions,
async function loadPendingDietSuggestions() {
    const container = getElement('pendingDietSuggestions');
    if (!container) return;
    // container.innerHTML = '<div class="pending-loading">Carregando sugestões...</div>';
    // try {
    //     const res = await fetch(`${API_BASE}/suggestions/diet`, { credentials: 'include' });
    //     if (!res.ok) throw new Error('Erro ao buscar sugestões');
    //     const suggestions = await res.json();
    //     if (!Array.isArray(suggestions) || suggestions.length === 0) {
    //         container.innerHTML = '<div class="pending-empty">Nenhuma sugestão pendente.</div>';
    //         return;
    //     }
    //     container.innerHTML = suggestions.map(renderSuggestionCard('diet')).join('');
    // } catch (e) {
    //     container.innerHTML = '<div class="pending-error">Erro ao carregar sugestões.</div>';
    // }
}

async function loadPendingWorkoutSuggestions() {
    const container = getElement('pendingWorkoutSuggestions');
    if (!container) return;
    // container.innerHTML = '<div class="pending-loading">Carregando sugestões...</div>';
    // try {
    //     const res = await fetch(`${API_BASE}/suggestions/workout`, { credentials: 'include' });
    //     if (!res.ok) throw new Error('Erro ao buscar sugestões');
    //     const suggestions = await res.json();
    //     if (!Array.isArray(suggestions) || suggestions.length === 0) {
    //         container.innerHTML = '<div class="pending-empty">Nenhuma sugestão pendente.</div>';
    //         return;
    //     }
    //     container.innerHTML = suggestions.map(renderSuggestionCard('workout')).join('');
    // } catch (e) {
    //     container.innerHTML = '<div class="pending-error">Erro ao carregar sugestões.</div>';
    // }
}
// renderSuggestionCard, handleApproveSuggestion, handleEditSuggestion,
// handleCancelSuggestion, removeSuggestionCard foram removidas pois
// não há backend para elas neste escopo.

// Chamar ao carregar as abas (ajustado para os novos planos)
// Esta função showTab já foi definida acima, esta é apenas uma nota.
// A lógica de carregamento de planos já está dentro da showTab.

// ============================================================================
// Fluid UI — Apple-style interaction layer
// ============================================================================
// Instant press feedback (pointer-down), bottom-sheet drag-to-dismiss with
// momentum projection + velocity handoff, and reduced-motion awareness.
function reducedMotion() {
    return window.Fluid?.reducedMotion() ?? (typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches);
}

// --- 1. Press feedback: respond on pointer-down, cancel by dragging away ---
(function pressFeedback() {
    const PRESSABLE = ".btn, .nav-btn, .btn-close, .plan-card, .meal-card, .macro-card, .session-card, .exercise-card, .activity-card, .btn-view, .btn-add, .btn-edit, .btn-delete";
    const SCOPE = "#dietTab, #diet_plansTab, #workout_plansTab, #dietModal, #viewWorkoutPlanModal, .diet-daily-actions-overlay";

    document.addEventListener("pointerdown", (e) => {
        if (e.button !== undefined && e.button !== 0) return;
        if (reducedMotion()) return;
        const target = e.target;
        if (!(target instanceof Element)) return;
        const scoped = target.closest(SCOPE);
        const pressable = target.closest(scoped ? 'button, a[href], summary' : PRESSABLE);
        if (!pressable || (scoped && !scoped.contains(pressable)) || pressable.matches(':disabled, [aria-disabled="true"]')) return;

        pressable.classList.add(scoped ? "is-action-pressed" : "is-pressed");
        const gx = e.clientX;
        const gy = e.clientY;

        const release = () => {
            pressable.classList.remove("is-pressed", "is-action-pressed");
            window.removeEventListener("blur", release);
            window.removeEventListener("fittracker:reduced-motion", release);
            window.removeEventListener("pointerup", release);
            window.removeEventListener("pointercancel", release);
            window.removeEventListener("pointermove", onMove);
        };
        const onMove = (ev) => {
            // hysteresis: a 12px drag means it was a scroll/gesture, not a tap
            if (Math.hypot(ev.clientX - gx, ev.clientY - gy) > 12) release();
        };
        window.addEventListener("blur", release);
        window.addEventListener("fittracker:reduced-motion", release);
        window.addEventListener("pointerup", release);
        window.addEventListener("pointercancel", release);
        window.addEventListener("pointermove", onMove);
    }, true);
})();

// --- 2. Bottom sheet: drag-to-dismiss (mobile), momentum + velocity snap ---
function bindSheetDrag(modal) {
    const content = modal.querySelector(".modal-content");
    if (!content || content.dataset.fluidDragBound === "1") return;
    if (typeof matchMedia === "undefined" || !matchMedia("(max-width: 600px)").matches) return;
    content.dataset.fluidDragBound = "1";

    if (!content.querySelector(".sheet-drag-handle")) {
        const handle = document.createElement("div");
        handle.className = "sheet-drag-handle";
        content.prepend(handle);
    }

    let baseY = 0;
    let lastY = 0;
    let lastT = 0;
    let vel = 0;
    let moved = false;

    content.addEventListener("pointerdown", (e) => {
        if (e.button !== undefined && e.button !== 0) return;
        const fromHandle = e.target.closest && e.target.closest(".sheet-drag-handle, .modal-header");
        if (!fromHandle) return;
        if (e.target.closest && e.target.closest("button, input, select, textarea, a, .btn-close")) return;
        if (reducedMotion() || modal.dataset.modalLocked === "true") return;
        window.Fluid?.stop(content);

        if (content.setPointerCapture) content.setPointerCapture(e.pointerId);
        baseY = e.clientY;
        lastY = e.clientY;
        lastT = performance.now();
        vel = 0;
        moved = false;
        content.classList.add("is-dragging");

        const onMove = (ev) => {
            if (ev.pointerId !== e.pointerId) return;
            if (reducedMotion()) { onCancel(ev); return; }
            const dy = ev.clientY - baseY;
            if (dy > 0) moved = true;
            const now = performance.now();
            const dt = Math.max(now - lastT, 8);
            vel = (ev.clientY - lastY) / (dt / 1000);
            lastY = ev.clientY;
            lastT = now;
            content.style.transform = "translate3d(0," + dy + "px,0) scale(1)";
        };
        const onUp = (ev) => {
            if (ev.pointerId !== e.pointerId) return;
            content.classList.remove("is-dragging");
            if (content.releasePointerCapture && ev.pointerId !== undefined) {
                try { content.releasePointerCapture(ev.pointerId); } catch (err) {}
            }
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onUp);
            window.removeEventListener("pointercancel", onCancel);
            window.removeEventListener('fittracker:reduced-motion', cancelMotion);
            modal._cancelDrag = null;

            const fluid = typeof Fluid !== "undefined" ? Fluid : null;
            if (!moved) {
                if (fluid) fluid.animate(content, { y: 0, scale: 1 }, { duration: 180 });
                return;
            }
            if (!fluid) {
                closeAppModal(modal);
                return;
            }

            const height = content.offsetHeight || 400;
            const finalDy = ev.clientY - baseY;
            const projected = finalDy + fluid.project(vel);
            const dismiss = projected > height * 0.3 || vel > 700;
            if (dismiss && closeAppModal(modal) !== false) return;
            fluid.animate(content, { y: 0, scale: 1, opacity: 1 }, {
                duration: 180, from: { y: finalDy, scale: 1, opacity: 1 }
            });
        };

        const onCancel = (ev) => {
            if (ev.pointerId !== e.pointerId) return;
            moved = false;
            content.style.transform = '';
            onUp(ev);
        };
        const cancelMotion = () => onCancel(e);
        modal._cancelDrag = cancelMotion;
        window.addEventListener('fittracker:reduced-motion', cancelMotion);
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
        window.addEventListener("pointercancel", onCancel);
    });
}
