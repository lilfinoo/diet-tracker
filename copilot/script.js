// script.js

// Global variables
let currentUser = null;
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
let authCheckInFlight = null;
let lastAuthCheckAt = 0;
let billingReturnHandled = false;
let profileAchievementsState = { selected: [], achievements: [], badges: [], records: [], limit: 3, filter: 'all', savingToken: null };

// API Base URL
const API_BASE = '/api';
const PRIMARY_VIEWS = new Set(['diet', 'diet_plans', 'workout_plans', 'progress', 'stats']);
const VIEW_LABELS = {
    diet: 'Hoje', diet_plans: 'Dieta', workout_plans: 'Treino', progress: 'Progresso',
    measurements: 'Medidas', activities: 'Atividades', personalRecords: 'Recordes pessoais', achievements: 'Conquistas',
    stats: 'Perfil', chat: 'Assistente IA', professional: 'Área profissional'
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
    chat: '/app/assistente',
    professional: '/app/profissional'
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
function showToast(msg, tipo="success") {
    document.querySelectorAll('.toast:not(#globalLoading)').forEach((existing) => existing.remove());

    let toast = document.createElement("div");
    toast.className = "toast " + tipo;
    toast.innerText = msg;
    toast.setAttribute("role", tipo === "error" ? "alert" : "status");
    toast.setAttribute("aria-live", tipo === "error" ? "assertive" : "polite");
    document.body.appendChild(toast);

    const fluid = typeof Fluid !== "undefined" ? Fluid : null;
    if (fluid) {
        if (tipo === "success") fluid.haptic.tap();
        else if (tipo === "error") fluid.haptic.snap();
    }

    setTimeout(() => {
        toast.remove();
    }, 2900);
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
    initializeAudioFeatures();
    checkAuthStatus();
    setupAppStyleControls();
    bindTodayMacroControls();
    syncChoiceCards();
    initializeAchievementControls();
    initializeGoogleAuth();
    refreshDisplayedVersion();
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
        if (event.target === this) closeAuthModal();
    });
    
    setupPlanViewModals();


});

document.addEventListener('visibilitychange', () => {
    if (!document.hidden && currentUser && Date.now() - lastAuthCheckAt > 60_000) checkAuthStatus();
});

window.addEventListener('pageshow', () => {
    if (currentUser && Date.now() - lastAuthCheckAt > 60_000) checkAuthStatus();
});

window.Capacitor?.Plugins?.App?.addListener?.('appStateChange', ({ isActive }) => {
    if (isActive && currentUser && Date.now() - lastAuthCheckAt > 60_000) checkAuthStatus();
});

async function refreshDisplayedVersion() {
    try {
        const response = await window.fetchWithTimeout(`${API_BASE}/version`);
        if (!response.ok) return;
        const data = await response.json();
        const label = [data.version, data.commit && data.commit !== 'local' ? data.commit : ''].filter(Boolean).join(' · ');
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
            window.DietEntryFlow?.saved();
            showToast("Refeição registrada", "success");
            closeDietModal();
            if (currentTab === 'diet_plans') await refreshDietDailySurfaces();
            else await Promise.all([loadDietEntries({ showLoading: false }), loadTodayCardapio()]);
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

    const measurementIdRaw = document.getElementById("measurementId")?.value;
    const measurementId = Number(measurementIdRaw);
    const isEdit = Number.isInteger(measurementId) && measurementId > 0;

    const payload = {
        id: measurementIdRaw,
        date: document.getElementById("measurementDate").value,
        weight: parseNumber(document.getElementById("measurementWeight").value),
        height: parseNumber(document.getElementById("measurementHeight").value),
        body_fat: parseNumber(document.getElementById("measurementBodyFat").value),
        muscle_mass: parseNumber(document.getElementById("measurementMuscleMass").value),
        waist: parseNumber(document.getElementById("measurementWaist").value),
        chest: parseNumber(document.getElementById("measurementChest").value),
        arm: parseNumber(document.getElementById("measurementArm").value),
        thigh: parseNumber(document.getElementById("measurementThigh").value),
        notes: document.getElementById("measurementNotes").value
    };

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
        { id: 'dietStartDate', value: today },
        { id: 'dietEndDate', value: today },
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
async function checkAuthStatus() {
    if (authCheckInFlight) return authCheckInFlight;
    authCheckInFlight = (async () => {
    try {
        const response = await window.fetchWithTimeout(`${API_BASE}/check_session`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.logged_in) {
                if (data.csrf_token) setCsrfToken(data.csrf_token);
                setCurrentUser(data.user);
                window.analytics?.trackReturns(currentUser);
                showMainScreen();
            } else {
                setCsrfToken(null);
                setCurrentUser(null);
                window.clearWorkoutProgress?.();
                showMainScreen();
            }
        } else if (response.status === 401 || response.status === 403) {
            setCsrfToken(null);
            setCurrentUser(null);
            window.clearWorkoutProgress?.();
            showMainScreen();
        } else {
            showMainScreen();
            showToast('Não foi possível confirmar sua sessão agora.', 'info');
        }
    } catch (error) {
        console.error('Auth check failed:', error);
        showMainScreen();
    }
    handleBillingReturn();
    lastAuthCheckAt = Date.now();
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
function openAuthModal(reason = 'Entre para salvar seus dados e acompanhar sua evolução.', mode = 'login', intent = null) {
    const loginScreen = getElement('loginScreen');
    const context = getElement('authContext');
    if (context) context.textContent = reason;
    pendingAuthIntent = intent || { tab: currentTab };
    if (mode === 'register') showRegister();
    else showLogin();
    openAppModal(loginScreen);
}

function closeAuthModal() {
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
    try {
        const response = await window.fetchWithTimeout(`${API_BASE}/auth/config`);
        const config = response.ok ? await response.json() : {};
        legalVersions = config.legal || null;
        if (!config.google_client_id) return;
        getElement('googleAuthSection')?.classList.remove('hidden');
        getElement('googleHeaderButton')?.classList.remove('hidden');
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
        console.error('Google auth configuration failed:', error);
    }
}

async function startNativeGoogleSignIn() {
    const plugin = window.Capacitor?.Plugins?.FitTrackerGoogleAuth;
    if (!plugin?.signIn) {
        showAuthMessage('Atualize o app para concluir o login com Google. Você ainda pode entrar com e-mail e senha.', 'info');
        return;
    }
    setGoogleAuthPending(true, 'Abrindo suas contas Google...');
    try {
        const result = await plugin.signIn();
        if (!result?.idToken) throw new Error('O Google não devolveu uma credencial válida. Tente novamente.');
        await handleGoogleCredential({ credential: result.idToken });
    } catch (error) {
        if (error?.message !== 'cancelled') showAuthMessage(error.message || 'Não foi possível entrar com Google.', 'error');
    } finally {
        setGoogleAuthPending(false);
    }
}

function setGoogleAuthPending(pending, message = '') {
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
            getElement('googleUsernameForm')?.classList.remove('hidden');
            getElement('googleUsername')?.focus();
            showAuthMessage('Só falta escolher seu nome de usuário.', 'info');
            return;
        }
        if (!response.ok) throw new Error(data.error || 'Não foi possível entrar com Google. Tente novamente.');
        completeAuthentication(data.user, data.csrf_token);
    } catch (error) {
        showAuthMessage(error.message, 'error');
    } finally {
        authRequestInFlight = false;
        setGoogleAuthPending(false);
    }
}

async function finishGoogleSignup(event) {
    event.preventDefault();
    const username = getElement('googleUsername')?.value.trim();
    if (!googleSignupToken || !username) return;
    if (!getElement('googleTerms')?.checked || !getElement('googlePrivacy')?.checked || !legalVersions) {
        showAuthMessage('Aceite os Termos e a Política de Privacidade vigentes.', 'error');
        return;
    }
    setGoogleAuthPending(true, 'Concluindo cadastro...');
    try {
        const response = await fetch(`${API_BASE}/auth/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                signup_token: googleSignupToken,
                username,
                terms_accepted: true,
                terms_version: legalVersions.terms.version,
                privacy_accepted: true,
                privacy_version: legalVersions.privacy.version,
                ai_consent: Boolean(getElement('googleAiConsent')?.checked),
                ai_consent_version: legalVersions.ai.version,
                analytics: window.analytics?.context()
            })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Não foi possível concluir o cadastro.');
        googleSignupToken = null;
        getElement('googleUsernameForm')?.classList.add('hidden');
        completeAuthentication(data.user, data.csrf_token);
    } catch (error) {
        showAuthMessage(error.message, 'error');
    } finally {
        setGoogleAuthPending(false);
    }
}

function completeAuthentication(user, csrfToken = null) {
    setCurrentUser(user);
    setCsrfToken(csrfToken);
    closeAppModal(getElement('loginScreen'));
    const intent = pendingAuthIntent;
    const destination = intent?.tab || viewForPath() || currentTab;
    pendingAuthIntent = null;
    showMainScreen({ tab: destination, skipProfile: Boolean(intent?.resume) });
    if (intent?.resume) resumeAfterAuthentication(intent.resume, intent.requiresProfile);
    else checkUserProfile();
    showToast('Você entrou com sucesso.', 'success');
}

window.handleGoogleCredential = handleGoogleCredential;

Object.defineProperty(window, 'currentUser', { get: () => currentUser });
window.requireAuth = requireAuth;

function showMainScreen(options = {}) {
    const loginScreen = getElement('loginScreen');
    const mainScreen = getElement('mainScreen');
    getElement('dietTab')?.classList.toggle('today-authenticated', Boolean(currentUser));
    
    if (loginScreen?.classList.contains('show')) closeAppModal(loginScreen);
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
        const welcomeUser = getElement('welcomeUser');
        if (welcomeUser) welcomeUser.textContent = `Olá, ${username}`;
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
        window.loadNetworkInbox?.();
        const aiAccessLabel = getElement('homeAiAccessLabel');
        if (aiAccessLabel) {
            const remaining = Math.max(0, 3 - Number(currentUser.ai_trial_uses || 0));
            aiAccessLabel.textContent = currentUser.is_premium ? 'Premium' : `${remaining} ${remaining === 1 ? 'uso grátis' : 'usos grátis'}`;
        }


        const isAdmin = Boolean(currentUser.is_admin);
        const isProfessional = Boolean(currentUser.professional_entitled);
        getElement('adminPanelBtn')?.classList.toggle('hidden', !isAdmin);
        getElement('profileAdminLink')?.classList.toggle('hidden', !isAdmin);
        getElement('professionalPanelBtn')?.classList.toggle('hidden', !isProfessional);
        getElement('profileProfessionalDashboard')?.classList.toggle('hidden', !isProfessional);
        getElement('networkHeaderButton')?.classList.remove('hidden');
    } else {
        const welcomeUser = getElement('welcomeUser');
        if (welcomeUser) welcomeUser.textContent = 'Explore o Fit-Tracker.AI';
        ['headerUserInitial', 'homeUserInitial', 'profileUserInitial'].forEach(id => {
            const element = getElement(id);
            if (element) element.textContent = 'F';
        });
        getElement('networkHeaderButton')?.classList.add('hidden');
        const profileUserName = getElement('profileUserName');
        if (profileUserName) profileUserName.textContent = 'Conheça seu espaço';
        const profileMembership = getElement('profileMembership');
        if (profileMembership) profileMembership.textContent = 'Entre para acompanhar sua evolução';
        const profileBadges = getElement('profileBadges');
        if (profileBadges) profileBadges.innerHTML = '';
        const aiAccessLabel = getElement('homeAiAccessLabel');
        if (aiAccessLabel) aiAccessLabel.textContent = '3 usos grátis';
        getElement('adminPanelBtn')?.classList.add('hidden');
        getElement('profileAdminLink')?.classList.add('hidden');
        getElement('professionalPanelBtn')?.classList.add('hidden');
        getElement('profileProfessionalDashboard')?.classList.add('hidden');
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
    showTab(initialView, { history: 'replace' });
    if (currentUser) {
        if (!options.skipProfile) checkUserProfile();
        window.loadWorkoutTodayCard?.();
        if (window.loadActiveWorkoutDock) window.loadActiveWorkoutDock();
        if (window.loadOwnProfessionalRelationship) window.loadOwnProfessionalRelationship();
    } else {
        window.renderWorkoutTodayCard?.();
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
        if (hero) hero.innerHTML = `<div class="achievement-load-error"><strong>Não foi possível carregar</strong><p>${escapeHtml(error.message)}</p><button type="button" data-achievement-action="retry">Tentar novamente</button></div>`;
        if (catalog) catalog.innerHTML = '<div class="achievement-empty"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i><strong>Catálogo indisponível</strong><p>Use o botão acima para tentar novamente.</p></div>';
    }
}

function achievementCategoryIcon(category, hidden) {
    if (hidden) return 'fa-question';
    return {
        treino: 'fa-dumbbell',
        recorde: 'fa-trophy',
        meta: 'fa-bullseye',
        consistencia: 'fa-fire',
    }[category] || 'fa-award';
}

function tierLabel(tier) {
    return {
        bronze: 'Bronze',
        prata: 'Prata',
        ouro: 'Ouro',
        platina: 'Platina',
        elite: 'Elite',
        lendario: 'Lendária',
    }[tier] || 'Conquista';
}

function renderAchievementCard(item, selectedTokens) {
    const isUnlocked = Boolean(item.unlocked);
    const isSelected = selectedTokens.has(availableToken(item));
    const isSaving = Boolean(profileAchievementsState.savingToken);
    const isSavingThis = profileAchievementsState.savingToken === availableToken(item);
    const hiddenLocked = Boolean(item.hidden && !isUnlocked);
    const tier = item.tier || 'bronze';
    const progress = item.progress;
    const progressMarkup = !isUnlocked && progress
        ? `<div class="achievement-progress"><div><span>${escapeHtml(progress.current)} de ${escapeHtml(progress.target)}</span><strong>${escapeHtml(progress.percentage)}%</strong></div><i><span style="width:${Math.max(0, Math.min(100, Number(progress.percentage) || 0))}%"></span></i></div>`
        : '';
    const action = isUnlocked
        ? `<button type="button" class="achievement-pin-action${isSelected ? ' is-selected' : ''}" data-highlight-kind="achievement" data-highlight-code="${escapeHtml(item.code)}"${isSaving ? ' disabled' : ''}><i class="fas ${isSavingThis ? 'fa-spinner fa-spin' : (isSelected ? 'fa-check' : 'fa-thumbtack')}" aria-hidden="true"></i>${isSavingThis ? 'Salvando...' : (isSelected ? 'Fixada' : 'Fixar no perfil')}</button>`
        : '<span class="achievement-locked-label"><i class="fas fa-lock" aria-hidden="true"></i> Ainda bloqueada</span>';
    const date = isUnlocked
        ? `<time datetime="${escapeHtml(item.unlocked.unlocked_at)}">Conquistada em ${new Date(item.unlocked.unlocked_at).toLocaleDateString('pt-BR')}</time>`
        : '';
    return `
        <article class="achievement-card achievement-tier--${escapeHtml(tier)}${isUnlocked ? ' is-unlocked' : ' is-locked'}${hiddenLocked ? ' is-hidden' : ''}">
            <div class="achievement-medallion"><i class="fas ${achievementCategoryIcon(item.category, hiddenLocked)}" aria-hidden="true"></i></div>
            <div class="achievement-card__body">
                <div class="achievement-card__eyebrow"><span>${hiddenLocked ? 'Oculta' : escapeHtml(tierLabel(tier))}</span><small>${escapeHtml(item.category || 'geral')}</small></div>
                <h4>${escapeHtml(item.title)}</h4>
                <p>${escapeHtml(item.description)}</p>
                ${progressMarkup}
                ${date}
            </div>
            <footer>${action}</footer>
        </article>`;
}

function renderBadgeCard(item, selectedTokens) {
    const isSelected = selectedTokens.has(availableToken(item));
    const isSaving = Boolean(profileAchievementsState.savingToken);
    const isSavingThis = profileAchievementsState.savingToken === availableToken(item);
    const rank = item.badge_rank;
    return `
        <article class="achievement-card achievement-card--badge is-unlocked">
            <div class="achievement-medallion"><i class="fas ${item.code === 'pioneiro' ? 'fa-compass' : 'fa-infinity'}" aria-hidden="true"></i></div>
            <div class="achievement-card__body">
                <div class="achievement-card__eyebrow"><span>Insígnia</span><small>história</small></div>
                <h4>${escapeHtml(item.code === 'pioneiro' && rank ? `${item.title} #${rank}` : item.title)}</h4>
                <p>${escapeHtml(item.description || '')}</p>
                <time datetime="${escapeHtml(item.granted_at)}">Recebida em ${new Date(item.granted_at).toLocaleDateString('pt-BR')}</time>
            </div>
            <footer><button type="button" class="achievement-pin-action${isSelected ? ' is-selected' : ''}" data-highlight-kind="badge" data-highlight-code="${escapeHtml(item.code)}"${isSaving ? ' disabled' : ''}><i class="fas ${isSavingThis ? 'fa-spinner fa-spin' : (isSelected ? 'fa-check' : 'fa-thumbtack')}" aria-hidden="true"></i>${isSavingThis ? 'Salvando...' : (isSelected ? 'Fixada' : 'Fixar no perfil')}</button></footer>
        </article>`;
}

function renderAchievementsTab() {
    const selectedEl = getElement('profileHighlightsSelected');
    const availableEl = getElement('profileHighlightsAvailable');
    const badgesEl = getElement('badgesCatalog');
    const heroEl = getElement('achievementHero');
    const achievementsSection = getElement('achievementsCatalogSection');
    const badgesSection = getElement('badgesCatalogSection');
    if (!selectedEl || !availableEl || !badgesEl || !heroEl || !achievementsSection || !badgesSection) return;

    const selectedTokens = new Set(profileAchievementsState.selected.map(selectionToken));
    const unlockedCount = profileAchievementsState.achievements.filter(item => item.unlocked).length;
    heroEl.innerHTML = `<div><span class="content-kicker">Progresso reconhecido</span><h3>${unlockedCount} de ${profileAchievementsState.achievements.length} conquistas</h3><p>Marcos reais da sua rotina, sem rankings ou competição de força.</p></div><div class="achievement-hero__stats"><span><strong>${profileAchievementsState.badges.length}</strong> insígnias</span><span><strong>${profileAchievementsState.selected.length}</strong> fixadas</span></div>`;

    selectedEl.innerHTML = Array.from({ length: profileAchievementsState.limit }, (_, index) => {
        const selection = profileAchievementsState.selected[index];
        return selection
            ? `<button type="button" class="achievement-slot is-filled" data-highlight-kind="${escapeHtml(selection.kind)}" data-highlight-code="${escapeHtml(selection.code)}"${profileAchievementsState.savingToken ? ' disabled' : ''}><span>${index + 1}</span><strong>${escapeHtml(selectionLabel(selection))}</strong><small>Remover</small></button>`
            : `<div class="achievement-slot"><span>${index + 1}</span><strong>Espaço livre</strong><small>Fixe uma conquista</small></div>`;
    }).join('');

    const filter = profileAchievementsState.filter;
    const achievementItems = profileAchievementsState.achievements.filter(item => {
        if (filter === 'unlocked') return Boolean(item.unlocked);
        if (filter === 'progress') return !item.unlocked;
        return filter !== 'badges';
    });
    achievementsSection.classList.toggle('hidden', filter === 'badges');
    badgesSection.classList.toggle('hidden', !['all', 'badges'].includes(filter));
    availableEl.innerHTML = achievementItems.length
        ? achievementItems.map(item => renderAchievementCard(item, selectedTokens)).join('')
        : '<div class="achievement-empty"><i class="fas fa-award"></i><strong>Nenhum item neste filtro</strong><p>Continue acompanhando sua evolução.</p></div>';
    badgesEl.innerHTML = profileAchievementsState.badges.length
        ? profileAchievementsState.badges.map(item => renderBadgeCard(item, selectedTokens)).join('')
        : '<div class="achievement-empty"><i class="fas fa-shield"></i><strong>Nenhuma insígnia ainda</strong><p>Insígnias representam momentos únicos da sua história.</p></div>';

    document.querySelectorAll('[data-achievement-filter]').forEach(button => {
        button.classList.toggle('is-active', button.dataset.achievementFilter === filter);
    });
}

function setAchievementFilter(filter) {
    if (!['all', 'unlocked', 'progress', 'badges'].includes(filter)) return;
    profileAchievementsState.filter = filter;
    renderAchievementsTab();
}

function initializeAchievementControls() {
    const tab = getElement('achievementsTab');
    if (!tab || tab.dataset.controlsBound === '1') return;
    tab.dataset.controlsBound = '1';
    tab.addEventListener('click', (event) => {
        const filterButton = event.target.closest('[data-achievement-filter]');
        if (filterButton) {
            setAchievementFilter(filterButton.dataset.achievementFilter);
            return;
        }
        const retryButton = event.target.closest('[data-achievement-action="retry"]');
        if (retryButton) {
            loadAchievementsTab();
            return;
        }
        const highlightButton = event.target.closest('[data-highlight-kind][data-highlight-code]');
        if (highlightButton && !highlightButton.disabled) {
            toggleProfileHighlight(highlightButton.dataset.highlightKind, highlightButton.dataset.highlightCode);
        }
    });
}

async function openProfileHighlights() {
    showTab('achievements');
}

function closeProfileHighlights() {
    showTab('stats');
}

async function toggleProfileHighlight(kind, code) {
    if (profileAchievementsState.savingToken) return;
    const target = [...profileAchievementsState.achievements, ...profileAchievementsState.badges, ...profileAchievementsState.records]
        .find(item => item.kind === kind && item.code === code);
    if (!target || (kind === 'achievement' && !target.unlocked)) return;
    const token = `${kind}:${code}`;
    const previous = profileAchievementsState.selected.slice();
    const current = profileAchievementsState.selected.slice();
    const index = current.findIndex(item => selectionToken(item) === token);
    if (index >= 0) {
        current.splice(index, 1);
    } else {
        if (current.length >= profileAchievementsState.limit) {
            showToast('Você pode fixar no máximo 3 destaques.', 'error');
            return;
        }
        current.push({ kind, code });
    }
    profileAchievementsState.selected = current;
    profileAchievementsState.savingToken = token;
    renderAchievementsTab();
    try {
        await saveProfileHighlights({ silent: true });
    } catch (error) {
        profileAchievementsState.selected = previous;
        profileAchievementsState.savingToken = null;
        renderAchievementsTab();
        showToast(error.message, 'error');
    }
}

async function saveProfileHighlights(options = {}) {
    const response = await fetch(`${API_BASE}/profile/highlights`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ items: profileAchievementsState.selected }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Não foi possível salvar os destaques.');
    currentUser.profile_highlights = data.selected;
    profileAchievementsState = {
        selected: Array.isArray(data.selected)
            ? data.selected.map(item => ({ kind: item.target_kind, code: item.item?.code }))
            : [],
        achievements: profileAchievementsState.achievements,
        badges: profileAchievementsState.badges,
        records: profileAchievementsState.records,
        limit: Number(data.limit) || 3,
        filter: profileAchievementsState.filter,
        savingToken: null,
    };
    renderAchievementsTab();
    renderProfileBadges(currentUser);
    if (!options.silent) showToast(data.message, 'success');
    return data;
}

async function resumeAfterAuthentication(resume, requiresProfile) {
    if (!resume) return;
    if (!requiresProfile) {
        requestAnimationFrame(resume);
        return;
    }
    try {
        const response = await fetch(`${API_BASE}/profile`, { credentials: 'include' });
        const data = response.ok ? await response.json() : {};
        if (data.profile) {
            fillProfileForm(data.profile);
            requestAnimationFrame(resume);
            return;
        }
    } catch (error) {
        console.error('Profile check after authentication failed:', error);
    }
    pendingPostProfileResume = resume;
    pendingProfileRequiredFields = [];
    fillProfileForm(null);
    openAppModal(getElement('profileModal'));
}

async function requestProfileCompletion(resume, fields = {}) {
    pendingPostProfileResume = resume;
    pendingProfileRequiredFields = Object.keys(fields)
        .filter(field => field.startsWith('profile.'))
        .map(field => field.slice('profile.'.length));
    try {
        const response = await fetch(`${API_BASE}/profile`, { credentials: 'include' });
        const data = response.ok ? await response.json() : {};
        fillProfileForm(data.profile || null);
    } catch (error) {
        console.error('Profile load before resume failed:', error);
    }
    openAppModal(getElement('profileModal'));
    const message = Object.values(fields).filter(Boolean).join(' ');
    showToast(message || 'Complete seu perfil para continuar.', 'info');
}

function renderGuestPresentation(tabName) {
    const presentations = {
        diet: ['dietTableBody', 'Registre refeições e acompanhe seus macros', 'Crie uma conta para salvar seu diário alimentar e acompanhar metas personalizadas.'],
        diet_plans: ['dietPlansTableBody', 'Cardápios alinhados ao seu objetivo', 'Explore o questionário e crie planos alimentares personalizados com IA Premium.'],
        workout_plans: ['workoutPlansTableBody', 'Organize e execute seus treinos', 'Explore o gerador e salve planos para acompanhar cada sessão.'],
        measurements: ['measurementTableBody', 'Acompanhe sua evolução corporal', 'Entre para registrar peso, medidas e composição ao longo do tempo.'],
        stats: ['measurementTableBody', 'Seu espaço em um só lugar', 'Entre para acompanhar medidas, treinos, metas e conquistas.']
    };
    const presentation = presentations[tabName];
    if (presentation) {
        const container = getElement(presentation[0]);
        if (container) container.innerHTML = `<div class="guest-presentation guest-presentation--standalone"><i class="fas fa-lock-open"></i><div><strong>${presentation[1]}</strong><p>${presentation[2]}</p></div><button type="button" class="btn-primary" onclick="openAuthModal('Crie sua conta para salvar seus dados.', 'register')">Criar conta</button></div>`;
    }
    if (tabName === 'diet') {
        getElement('guestDailySummary')?.classList.remove('hidden');
        getElement('dailyMacroGrid')?.classList.add('hidden');
        const cardapio = getElement('todayCardapioBody');
        if (cardapio) cardapio.innerHTML = '<p class="today-muted">Entre para salvar suas refeições.</p><button type="button" class="today-food-primary" onclick="showAddDietModal()">Registrar refeição</button>';
    }
    if (tabName === 'diet_plans') renderDietCurrentPlanHub(null, null);
    if (tabName === 'diet_plans') document.querySelector('.fab--diet-plans')?.classList.add('hidden');
    if (tabName === 'workout_plans') document.querySelector('.fab--workout-plans')?.classList.add('hidden');

}

/**
 * Mostra mensagens de feedback
 * @param {string} message - Mensagem a ser exibida
 * @param {string} type - Tipo da mensagem (success, error, info)
 */
// Chat functions
let isRecording = false;
let recognition = null;
let lastAIResponse = '';
let isSendingChat = false;

function setChatPending(pending) {
    isSendingChat = pending;
    const button = getElement('chatSendButton');
    if (!button) return;
    button.disabled = pending;
    button.setAttribute('aria-busy', pending ? 'true' : 'false');
    button.innerHTML = pending
        ? '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>'
        : '<i class="fas fa-arrow-up" aria-hidden="true"></i>';
}

/**
 * Envia mensagem no chat
 */
async function sendChatMessage() {
    if (!requireAuth('Entre para conversar com o Assistente IA.', { premium: true })) return;
    if (isSendingChat) return;
    const input = getElement("chatInput");
    if (!input) return;

    const message = input.value.trim();
    if (!message) return;

    // Adiciona mensagem do usuário
    addMessageToChat(message, "user");
    input.value = "";
    setChatPending(true);
    
    // Mostra indicador de digitação
    showTypingIndicator();
    
    try {
        const response = await fetch(`${API_BASE}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            credentials: "include",
            body: JSON.stringify({ message: message })
        });
        
        if (response.ok) {
            let data = await response.json();
            if (response.status === 202 && data.job_id) data = await window.waitForAIJob(data);
            hideTypingIndicator();
            lastAIResponse = data.response; // Salva para reprodução de áudio
            addMessageToChat(data.response, "bot");
            if (window.handlePlanChatAction) window.handlePlanChatAction(data.action);
        } else {
            hideTypingIndicator();
            const errorData = await response.json();
            addMessageToChat(errorData.error || "Desculpe, ocorreu um erro. Tente novamente.", "bot");
        }
    } catch (error) {
        console.error("Chat error:", error);
        hideTypingIndicator();
        addMessageToChat("Erro de conexão. Verifique sua internet.", "bot");
    } finally {
        setChatPending(false);
    }
}

/**
 * Envia mensagem para a IA com o perfil do usuário (usado pelos botões rápidos)
 */
async function sendChatMessageWithProfile(message, intent) {
    if (isSendingChat) return;
    const chatMessages = getElement("chatMessages");
    if (!chatMessages) return;
    addMessageToChat(message, "user");
    setChatPending(true);
    showTypingIndicator();
    
    try {
        const response = await fetch(`${API_BASE}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ message, intent })
        });
        let data = await response.json();
        if (response.status === 202 && data.job_id) data = await window.waitForAIJob(data);
        hideTypingIndicator();
        if (response.ok && data.response) {
            addMessageToChat(data.response, "bot");
            lastAIResponse = data.response;
            if (window.handlePlanChatAction) window.handlePlanChatAction(data.action);
        } else {
            addMessageToChat(data.error || "Não foi possível concluir esta solicitação.", "bot");
        }
    } catch (error) {
        console.error("Chat error:", error);
        hideTypingIndicator();
        addMessageToChat("Erro de conexão com a IA.", "bot");
    } finally {
        setChatPending(false);
    }
}

// Adiciona classe correta para mensagens do chat
function addMessageToChat(message, sender) {
    const chatMessages = getElement("chatMessages");
    if (!chatMessages) return;
    const messageDiv = document.createElement("div");
    messageDiv.className = `chat-message ${sender === "bot" ? "bot-message" : "user-message"}`;
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas ${sender === "bot" ? "fa-robot" : "fa-user"}"></i>
        </div>
        <div class="message-content">${escapeHtml(message)}</div>
    `;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

/**
 * Mostra indicador de digitação
 */
function showTypingIndicator() {
    const chatMessages = getElement("chatMessages");
    if (!chatMessages) return;

    // Remove indicador anterior se existir
    hideTypingIndicator();

    const typingDiv = document.createElement("div");
    typingDiv.id = "typingIndicator";
    typingDiv.className = "chat-message bot-message";
    typingDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
            <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    
    chatMessages.appendChild(typingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

/**
 * Remove indicador de digitação
 */
function hideTypingIndicator() {
    const typingIndicator = getElement("typingIndicator");
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

// Audio features
function initializeAudioFeatures() {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
        const audioControls = document.querySelector('.audio-controls');
        if (audioControls) {
            audioControls.style.display = 'none';
        }
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'pt-BR';
    
    recognition.onstart = () => {
        isRecording = true;
        updateVoiceButton();
    };
    
    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        const chatInput = getElement('chatInput');
        if (chatInput) {
            chatInput.value = transcript;
            sendChatMessage();
        }
    };
    
    recognition.onerror = (event) => {
        console.error('Erro no reconhecimento de voz:', event.error);
        isRecording = false;
        updateVoiceButton();
    };
    
    recognition.onend = () => {
        isRecording = false;
        updateVoiceButton();
    };

    // Event listeners para botões de áudio
    addEventListenerSafe('voiceButton', 'click', toggleVoiceRecording);
    addEventListenerSafe('speakButton', 'click', speakLastResponse);
}

/**
 * Alterna gravação de voz
 */
function toggleVoiceRecording() {
    if (!recognition) return;
    
    if (isRecording) {
        recognition.stop();
    } else {
        recognition.start();
    }
}

/**
 * Atualiza visual do botão de voz
 */
function updateVoiceButton() {
    const button = getElement('voiceButton');
    if (!button) return;

    if (isRecording) {
        button.innerHTML = '⏹️';
        button.title = 'Parar gravação';
        button.setAttribute('aria-label', 'Parar gravação de voz');
        button.classList.add('recording');
    } else {
        button.innerHTML = '🎤';
        button.title = 'Falar com a IA';
        button.setAttribute('aria-label', 'Falar com a IA');
        button.classList.remove('recording');
    }
}

/**
 * Reproduz última resposta da IA
 */
function speakLastResponse() {
    if (!lastAIResponse || !('speechSynthesis' in window)) return;
    
    speechSynthesis.cancel();
    
    const cleanText = lastAIResponse
        .replace(/[🤖📱📊🍽️⚖️🎯✅💪🍎📈❓]/g, '')
        .replace(/\*\*(.*?)\*\*/g, '$1')
        .replace(/\n+/g, '. ');
    
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = 'pt-BR';
    utterance.rate = 0.9;
    
    const voices = speechSynthesis.getVoices();
    const ptVoice = voices.find(voice => voice.lang.includes('pt'));
    if (ptVoice) utterance.voice = ptVoice;
    
    const speakButton = getElement('speakButton');
    if (speakButton) {
        utterance.onstart = () => {
            speakButton.innerHTML = '⏸️';
            speakButton.title = 'Pausar reprodução';
            speakButton.setAttribute('aria-label', 'Pausar resposta da IA');
        };
        
        utterance.onend = () => {
            speakButton.innerHTML = '🔊';
            speakButton.title = 'Ouvir última resposta';
            speakButton.setAttribute('aria-label', 'Ouvir última resposta da IA');
        };
    }
    
    speechSynthesis.speak(utterance);
}

// Utility functions
function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString + 'T00:00:00'); // Adiciona T00:00:00 para evitar problemas de fuso horário
    return date.toLocaleDateString('pt-BR');
}

function formatDateTime(dateTimeString) {
    if (!dateTimeString) return '-';
    const date = new Date(dateTimeString);
    return date.toLocaleDateString('pt-BR') + ' ' + date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function getMealTypeLabel(mealType) {
    const labels = {
        'café': 'Café da Manhã',
        'lanche_manha': 'Lanche da Manhã',
        'almoço': 'Almoço',
        'lanche_tarde': 'Lanche da Tarde',
        'jantar': 'Jantar',
        'ceia': 'Ceia'
    };
    return labels[mealType] || mealType;
}

// Authentication functions
async function readAuthResponse(response) {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) return response.json();
    return {
        error: response.status >= 500
            ? `O servidor não conseguiu concluir a solicitação (erro ${response.status}).`
            : `Resposta inválida do servidor (erro ${response.status}).`
    };
}

async function handleLogin(e) {
    e.preventDefault();
    if (authRequestInFlight) return;
    const username = getElement("loginUsername").value.trim();
    const password = getElement("loginPassword").value.trim();

    if (!username || !password) {
        showAuthMessage("Preencha todos os campos", "error");
        return;
    }

    const submit = e.currentTarget.querySelector('button[type="submit"]');
    authRequestInFlight = true;
    if (submit) { submit.disabled = true; submit.textContent = 'Entrando...'; }
    try {
        const response = await window.fetchWithTimeout(`${API_BASE}/login`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            credentials: "include",
            body: JSON.stringify({ username, password })
        });

        const data = await readAuthResponse(response);
        if (response.ok && data.user) {
            setCurrentUser(data.user);
            if (data.csrf_token) setCsrfToken(data.csrf_token);
            const intent = pendingAuthIntent;
            const destination = intent?.tab || currentTab;
            pendingAuthIntent = null;
            showMainScreen({ tab: destination, skipProfile: Boolean(intent?.resume) });
            showToast(data.message, "success");
            if (intent?.resume) resumeAfterAuthentication(intent.resume, intent.requiresProfile);
        } else {
            showAuthMessage(data.error || "Não foi possível entrar.", "error");
        }
    } catch (error) {
        console.error("Login error:", error);
        showAuthMessage("Erro de conexão. Tente novamente.", "error");
    } finally {
        authRequestInFlight = false;
        if (submit) { submit.disabled = false; submit.textContent = 'Entrar'; }
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const name = getElement("registerName").value.trim();
    const email = getElement("registerEmail").value.trim();
    const username = getElement("registerUsername").value.trim();
    const password = getElement("registerPassword").value.trim();
    const confirmPassword = getElement("confirmPassword").value.trim();

    if (!name || !email || !username || !password || !confirmPassword) {
        showAuthMessage("Preencha todos os campos", "error");
        return;
    }

    if (password !== confirmPassword) {
        showAuthMessage("As senhas não coincidem", "error");
        return;
    }

    if (password.length < 8) {
        showAuthMessage("A senha deve ter pelo menos 8 caracteres", "error");
        return;
    }
    if (!getElement('registerTerms')?.checked || !getElement('registerPrivacy')?.checked || !legalVersions) {
        showAuthMessage('Aceite os Termos e a Política de Privacidade vigentes.', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/register`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            credentials: "include",
            body: JSON.stringify({
                username,
                name,
                email,
                password,
                terms_accepted: true,
                terms_version: legalVersions.terms.version,
                privacy_accepted: true,
                privacy_version: legalVersions.privacy.version,
                ai_consent: Boolean(getElement('registerAiConsent')?.checked),
                ai_consent_version: legalVersions.ai.version,
                analytics: window.analytics?.context()
            })
        });

        const data = await readAuthResponse(response);
        if (response.ok && data.user) {
            setCurrentUser(data.user);
            if (data.csrf_token) setCsrfToken(data.csrf_token);
            const intent = pendingAuthIntent;
            const destination = intent?.tab || currentTab;
            pendingAuthIntent = null;
            showMainScreen({ tab: destination, skipProfile: Boolean(intent?.resume) });
            showToast(data.message, "success");
            if (intent?.resume) resumeAfterAuthentication(intent.resume, intent.requiresProfile);
        } else {
            showAuthMessage(data.error || "Não foi possível criar a conta.", "error");
        }
    } catch (error) {
        console.error("Register error:", error);
        showAuthMessage("Erro de conexão. Tente novamente.", "error");
    }
}

async function openPrivacySettings() {
    if (!currentUser) return;
    try {
        const response = await fetch(`${API_BASE}/account/consents`, { credentials: 'include' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Não foi possível carregar os consentimentos.');
        legalVersions = data.versions;
        getElement('accountTerms').checked = Boolean(data.terms.accepted);
        getElement('accountPrivacy').checked = Boolean(data.privacy.accepted);
        getElement('accountAiConsent').checked = Boolean(data.ai.accepted);
        getElement('consentStatus').textContent = `Termos: ${data.terms.version || 'pendente'} | Privacidade: ${data.privacy.version || 'pendente'} | IA: ${data.ai.accepted ? data.ai.version : 'não autorizada'}`;
        openAppModal(getElement('privacySettingsModal'));
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function savePrivacySettings() {
    if (!legalVersions) return;
    try {
        const response = await fetch(`${API_BASE}/account/consents`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                terms_accepted: Boolean(getElement('accountTerms')?.checked),
                privacy_accepted: Boolean(getElement('accountPrivacy')?.checked),
                ai_consent: Boolean(getElement('accountAiConsent')?.checked),
            }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Não foi possível salvar as escolhas.');
        closeAppModal(getElement('privacySettingsModal'));
        showToast(data.message, 'success');
    } catch (error) {
        showToast(error.message, 'error');
    }
}

function openDeleteAccount() {
    if (!currentUser) return;
    getElement('deleteAccountUsername').value = '';
    getElement('deleteAccountPassword').value = '';
    getElement('deleteAccountConfirm').checked = false;
    getElement('deleteAccountPasswordGroup')?.classList.toggle('hidden', !currentUser.has_password);
    getElement('deleteGoogleNotice')?.classList.toggle('hidden', Boolean(currentUser.has_password));
    openAppModal(getElement('deleteAccountModal'));
}

async function deleteAccount() {
    if (!currentUser) return;
    if (!getElement('deleteAccountConfirm')?.checked) {
        showToast('Confirme que entendeu a exclusão definitiva.', 'error');
        return;
    }
    try {
        const response = await fetch(`${API_BASE}/account`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                username: getElement('deleteAccountUsername')?.value,
                password: getElement('deleteAccountPassword')?.value,
                confirm_delete: true,
            }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Não foi possível excluir a conta.');
        setCurrentUser(null);
        setCsrfToken(null);
        window.analytics?.clearAttribution();
        closeAppModal(getElement('deleteAccountModal'));
        window.clearWorkoutProgress?.();
        showMainScreen({ tab: 'diet' });
        showToast(data.message, 'success');
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function logout() {
    try {
        const response = await window.fetchWithTimeout(`${API_BASE}/logout`, {
            method: "POST",
            credentials: "include"
        });
        if (!response.ok) throw new Error('Não foi possível encerrar sua sessão. Tente novamente.');
        try { await window.Capacitor?.Plugins?.FitTrackerGoogleAuth?.signOut?.(); } catch (_error) { /* a sessão do backend já foi encerrada */ }
        setCurrentUser(null);
        setCsrfToken(null);
        window.clearWorkoutProgress?.();
        showMainScreen({ tab: 'diet' });
        showToast("Logout realizado com sucesso", "success");
    } catch (error) {
        console.error("Logout error:", error);
        showToast(error.message || 'Não foi possível encerrar sua sessão.', 'error');
    }
}

// Interface functions
// Interface functions
function showTab(tabName, options = {}) {
    if (['activities', 'personalRecords'].includes(tabName) && !currentUser) {
        openAuthModal('Entre para acessar seu histórico de atividades.', 'login', { tab: 'activities' });
        return false;
    }
    if (tabName === 'achievements' && !currentUser) {
        openAuthModal('Entre para acessar suas conquistas.', 'login', { tab: 'achievements' });
        return false;
    }
    if (tabName === 'chat' && !hasAiAccess()) {
        if (!currentUser) {
            openAuthModal('Entre para conhecer o Assistente IA. Este é um recurso Premium.', 'register', { tab: 'chat', premium: true });
            return false;
        }
        showToast('O Assistente IA está disponível no plano Premium.', 'info');
        openPlansModal();
        return false;
    }
    if (tabName === 'professional' && !currentUser?.professional_entitled) {
        showToast('A área profissional exige aprovação e assinatura profissional ativa.', 'info');
        return false;
    }

    // Remove active class from all nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active');
        btn.removeAttribute('aria-current');
    });
    
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.add('hidden');
    });
    
    const chatNavBtn = document.querySelector(`.nav-btn[onclick="showTab('chat')"]`);
    if (chatNavBtn) {
        chatNavBtn.style.display = '';
        chatNavBtn.classList.toggle('is-locked', !hasAiAccess());
    }

    // Show selected tab
    const selectedTab = document.getElementById(`${tabName}Tab`);
    if (!selectedTab) return false;
    selectedTab.classList.remove('hidden');
    
    // Add active class to clicked button
    const navTabName = tabName === 'chat'
        ? lastPrimaryTab
        : (['measurements', 'activities', 'personalRecords', 'achievements'].includes(tabName) ? 'progress' : tabName);
    const activeBtn = document.querySelector(`.nav-btn[data-app-view="${navTabName}"]`);
    if (activeBtn) {
        activeBtn.classList.add('active');
        activeBtn.setAttribute('aria-current', 'page');
    }
    
    const previousTab = currentTab;
    currentTab = tabName;
    if (PRIMARY_VIEWS.has(tabName)) lastPrimaryTab = tabName;
    document.body.dataset.activeTab = tabName;
    const routeStatus = getElement('routeStatus');
    if (routeStatus) routeStatus.textContent = `${VIEW_LABELS[tabName] || 'Seção'} aberta`;
    syncViewPath(tabName, options.history || 'push');
    window.scrollTo({ top: 0, behavior: 'instant' });
    
    if (!currentUser) {
        renderGuestPresentation(tabName);
        return true;
    }

    getElement('guestDailySummary')?.classList.add('hidden');
    getElement('dailyMacroGrid')?.classList.remove('hidden');
    if (tabName === 'diet') {
        loadDietEntries({ showLoading: previousTab !== 'diet' });
        loadTodayCardapio();
    } else if (tabName === 'measurements') {
        loadMeasurements();
        loadMeasurementSummary();
    } else if (tabName === 'progress') {
        window.loadProgressOverview?.();
    } else if (tabName === 'activities') {
        if (!options.exerciseProgress) window.loadWorkoutActivities?.();
    } else if (tabName === 'personalRecords') {
        window.loadPersonalRecords?.();
    } else if (tabName === 'achievements') {
        loadAchievementsTab();
    } else if (tabName === 'diet_plans') {
        loadDietDailyScreen();
    } else if (tabName === 'workout_plans') { // Carrega planos de treino
        loadWorkoutPlans();
    } else if (tabName === 'professional') {
        window.loadProfessionalDashboard?.();
    }
    return true;
}

function returnFromAssistant() {
    showTab(lastPrimaryTab || 'diet');
}

window.addEventListener('popstate', () => {
    const view = viewForPath();
    if (view) showTab(view, { history: 'none' });
});

async function openPlansModal() {
    window.analytics?.track('paywall_viewed', { surface: 'plans_modal' });
    openAppModal(getElement('plansModal'));
    const grid = getElement('plansGrid');
    try {
        const [plansResponse, applicationResponse] = await Promise.all([
            fetch(`${API_BASE}/plans`),
            currentUser ? fetch(`${API_BASE}/professional-application`, { credentials: 'include' }) : Promise.resolve(null)
        ]);
        const data = await plansResponse.json();
        const applicationData = applicationResponse && applicationResponse.ok ? await applicationResponse.json() : { application: null };
        if (!plansResponse.ok) throw new Error(data.error || 'Não foi possível carregar os planos.');
        window.__dtApplication = applicationData.application;
        const currentPlan = currentUser?.plan_code || 'free';
        grid.innerHTML = data.plans.map(plan => {
            const isCurrent = plan.code === currentPlan;
            let action;
            if (isCurrent) {
                action = '<button type="button" class="btn-primary" disabled>Seu plano atual</button>';
            } else if (plan.price_brl === 0) {
                action = '';
            } else if (plan.code === 'premium_student') {
                action = data.provider_configured
                    ? `<button type="button" class="btn-primary" onclick="startBillingCheckout('${plan.code}', this)">Escolher pagamento · R$ ${Number(plan.price_brl).toFixed(0)}</button>`
                    : '<button type="button" class="btn-primary" disabled>Pagamento em breve</button>';
            } else {
                action = professionalPlanAction(plan, data.provider_configured);
            }
            return `
            <article class="pricing-card${isCurrent ? ' is-current' : ''}">
                <h4>${escapeHtml(plan.name)}</h4>
                <p class="pricing-card__price"><strong>R$ ${Number(plan.price_brl).toFixed(0)}</strong><span>${plan.price_brl ? '/mês' : ''}</span></p>
                <ul>${(plan.features || []).map(feature => `<li><i class="fas fa-check" aria-hidden="true"></i>${escapeHtml(feature)}</li>`).join('')}</ul>
                ${action}
            </article>`;
        }).join('');
        renderSubscriptionManagement(data.provider_configured);
        getElement('billingNotice').textContent = data.provider_configured
            ? (data.provider_environment === 'sandbox'
                ? 'Ambiente de testes (Sandbox): nenhum valor real será movimentado.'
                : 'Cartão renova automaticamente. PIX libera 30 dias e não possui renovação automática.')
            : 'O pagamento será habilitado após a configuração do provedor.';
    } catch (error) {
        grid.innerHTML = `<p class="empty-state">${escapeHtml(error.message)}</p>`;
    }
}

function professionalPlanAction(plan, providerConfigured) {
    const application = window.__dtApplication;
    if (!currentUser) return '<button type="button" class="btn-secondary" onclick="closePlansModal(); openAuthModal(\'Entre para solicitar aprovação profissional.\', \'register\')">Entrar para solicitar</button>';
    if (!application || ['rejected'].includes(application.status)) {
        return `<button type="button" class="btn-secondary" onclick="showProfessionalRequestForm('${plan.code}')">Solicitar aprovação</button>`;
    }
    if (application.status === 'pending') {
        return `<p class="pricing-status">Análise em andamento${application.plan_code !== plan.code ? ` (plano: ${escapeHtml(application.plan_code)})` : ''}.</p>`;
    }
    if (!providerConfigured) return '<button type="button" class="btn-primary" disabled>Pagamento em breve</button>';
    return `<button type="button" class="btn-primary" onclick="startBillingCheckout('${plan.code}', this)">Escolher pagamento · R$ ${Number(plan.price_brl).toFixed(0)}</button>`;
}

function showProfessionalRequestForm(planCode) {
    const grid = getElement('plansGrid');
    grid.insertAdjacentHTML('beforeend', `
        <form id="professionalRequestForm" class="professional-request">
            <h4>Solicitar aprovação profissional</h4>
            <input type="hidden" name="plan_code" value="${escapeHtml(planCode)}">
            <label>Nome completo<input name="full_name" maxlength="120" required></label>
            <label>Profissão<select name="profession" required>
                <option value="personal_trainer">Personal trainer (CREF)</option>
                <option value="nutritionist">Nutricionista (CRN)</option>
            </select></label>
            <label>Número do registro<input name="registration_number" maxlength="40" required placeholder="Ex.: 000000-G/UF"></label>
            <div class="modal-actions">
                <button type="button" class="btn-secondary" onclick="this.closest('form').remove()">Cancelar</button>
                <button type="submit" class="btn-primary">Enviar solicitação</button>
            </div>
        </form>`);
    getElement('professionalRequestForm').addEventListener('submit', submitProfessionalApplication);
}

async function submitProfessionalApplication(event) {
    event.preventDefault();
    const form = event.target;
    const payload = Object.fromEntries(new FormData(form).entries());
    try {
        const response = await fetch(`${API_BASE}/professional-application`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Não foi possível enviar a solicitação.');
        showToast(data.message, 'success');
        openPlansModal();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

let pendingBillingCheckout = null;

function startBillingCheckout(planCode, button) {
    if (!requireAuth('Crie sua conta para assinar e desbloquear o plano Premium.', { mode: 'register' })) return;
    pendingBillingCheckout = { planCode, button };
    openAppModal(getElement('billingPaymentModal'));
}

function closeBillingPaymentModal() {
    closeAppModal(getElement('billingPaymentModal'));
    pendingBillingCheckout = null;
}

async function confirmBillingCheckout(paymentMethod) {
    if (!pendingBillingCheckout) return;
    const { planCode, button } = pendingBillingCheckout;
    if (button) button.disabled = true;
    document.querySelectorAll('#billingPaymentModal .billing-payment-options button').forEach(option => { option.disabled = true; });
    try {
        const response = await fetch(`${API_BASE}/billing/checkout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ plan_code: planCode, payment_method: paymentMethod })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Não foi possível iniciar o pagamento.');
        window.location.href = data.checkout_url;
    } catch (error) {
        if (button) button.disabled = false;
        document.querySelectorAll('#billingPaymentModal .billing-payment-options button').forEach(option => { option.disabled = false; });
        showToast(error.message, 'error');
    }
}

function renderSubscriptionManagement(providerConfigured) {
    const container = getElement('subscriptionManage');
    if (!container) return;
    container.innerHTML = '';
    if (!currentUser?.is_premium) return;
    fetch(`${API_BASE}/subscription`, { credentials: 'include' })
        .then(response => response.json())
        .then(data => {
            const subscription = data.subscription;
            if (!subscription || subscription.status !== 'active') return;
            const until = subscription.current_period_end ? new Date(subscription.current_period_end).toLocaleDateString('pt-BR') : null;
            const isPix = subscription.provider === 'asaas_pix';
            const renewalAvailable = data.pix_renewal_available_at && new Date(data.pix_renewal_available_at) <= new Date();
            const managementAction = isPix
                ? (renewalAvailable ? `<button type="button" class="btn-secondary" onclick="startBillingCheckout('${escapeHtml(subscription.plan_code)}', this)">Renovar por PIX</button>` : '')
                : (subscription.provider === 'asaas' && providerConfigured ? '<button type="button" class="btn-secondary" onclick="cancelMySubscription()">Cancelar assinatura</button>' : '');
            container.innerHTML = `
                <section class="subscription-manage">
                    <div><strong>${isPix ? 'Acesso PIX' : escapeHtml(subscription.plan_code)}</strong>${until ? `<small>Ativo até ${escapeHtml(until)}</small>` : ''}${isPix && !renewalAvailable ? '<small>A renovação abre nos últimos 7 dias.</small>' : ''}</div>
                    ${managementAction}
                </section>`;
        })
        .catch(() => {});
}

async function cancelMySubscription() {
    if (!window.confirm('Cancelar a assinatura? Você mantém o acesso até o fim do período já pago.')) return;
    try {
        const response = await fetch(`${API_BASE}/billing/cancel`, { method: 'POST', credentials: 'include' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Não foi possível cancelar.');
        showToast(data.message, 'success');
        await checkAuthStatus();
        openPlansModal();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

function closePlansModal() {
    closeAppModal(getElement('plansModal'));
}

function showLogin() {
    const loginForm = getElement("loginForm");
    const registerForm = getElement("registerForm");
    const loginTab = document.querySelector('.tab-btn:first-child');
    const registerTab = document.querySelector('.tab-btn:last-child');
    
    if (loginForm) loginForm.classList.remove('hidden');
    if (registerForm) registerForm.classList.add('hidden');
    if (loginTab) loginTab.classList.add('active');
    if (registerTab) registerTab.classList.remove('active');
}

function showRegister() {
    window.analytics?.track('signup_started', { surface: 'auth_modal' });
    const loginForm = getElement("loginForm");
    const registerForm = getElement("registerForm");
    const loginTab = document.querySelector('.tab-btn:first-child');
    const registerTab = document.querySelector('.tab-btn:last-child');
    
    if (loginForm) loginForm.classList.add('hidden');
    if (registerForm) registerForm.classList.remove('hidden');
    if (loginTab) loginTab.classList.remove('active');
    if (registerTab) registerTab.classList.add('active');
}

function clearForms() {
    const forms = ['loginForm', 'registerForm', 'dietForm', 'measurementForm', 'profileForm'];
    forms.forEach(formId => {
        const form = getElement(formId);
        if (form) {
            form.reset();
        }
    });
}

// Modal functions
let activeModal = null;
let modalTrigger = null;

function getModalFocusable(modal) {
    if (!modal) return [];
    const selector = "a[href], button:not([disabled]), input:not([disabled]):not([type='hidden']), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";
    return Array.from(modal.querySelectorAll(selector)).filter(element => {
        return !element.hidden && element.getAttribute("aria-hidden") !== "true" && element.getClientRects().length > 0;
    });
}

function updateModalBackground(modal) {
    document.querySelectorAll(".modal.modal--active").forEach(element => {
        element.classList.remove("modal--active");
    });
    document.querySelectorAll("[data-modal-background-inert]").forEach(element => {
        element.inert = false;
        delete element.dataset.modalBackgroundInert;
    });
    if (!modal) return;
    modal.classList.add("modal--active");

    const background = modal.parentElement === document.body
        ? [getElement("mainScreen")]
        : [document.querySelector(".app-header"), document.querySelector(".app-shell"), getElement("activeWorkoutDock")];
    document.querySelectorAll(".modal.show").forEach(otherModal => {
        if (otherModal !== modal) background.push(otherModal);
    });
    background.filter(Boolean).forEach(element => {
        element.inert = true;
        element.dataset.modalBackgroundInert = "true";
    });
}

function openAppModal(modal) {
    if (!modal) return;
    modalTrigger = document.activeElement;
    modal._modalTrigger = modalTrigger;
    modal._previousActiveModal = activeModal && activeModal !== modal ? activeModal : null;
    activeModal = modal;
    modal.classList.add("show");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    updateModalBackground(modal);
    const focusTarget = getModalFocusable(modal)[0];
    if (focusTarget) requestAnimationFrame(() => focusTarget.focus());

    const fluid = typeof Fluid !== "undefined" ? Fluid : null;
    if (fluid) {
        materializeModal(modal, fluid);
        bindSheetDrag(modal);
    }
}

function materializeModal(modal, fluid) {
    const content = modal.querySelector(".modal-content");
    if (!content) return;
    const reduced = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

    modal._fluidGen = (modal._fluidGen || 0) + 1;
    modal._fluidClosing = false;
    content.dataset.fluidMaterial = "true";

    if (reduced) {
        content.style.transform = "none";
        content.style.opacity = "";
        modal.style.opacity = "";
        return;
    }

    content.style.willChange = "transform, opacity";
    content.style.transform = "translate3d(0,26px,0) scale(0.96)";
    content.style.opacity = "0";
    modal.style.opacity = "0";
    requestAnimationFrame(() => {
        fluid.animate(content, { y: 0, scale: 1, opacity: 1 }, {
            response: 0.42,
            damping: 1.0,
            from: { y: 26, scale: 0.96, opacity: 0 }
        });
        fluid.animate(modal, { opacity: 1 }, { response: 0.32, damping: 1.0 });
    });
}

function finalizeModalClose(modal) {
    const content = modal.querySelector(".modal-content");
    if (content) {
        content.style.transform = "none";
        content.style.opacity = "";
        content.classList.remove("is-dragging");
    }
    modal.style.opacity = "";
    modal.classList.remove("show");
    modal.classList.remove("modal--active");
    modal.setAttribute("aria-hidden", "true");
    document.querySelectorAll(".modal.show").forEach(otherModal => {
        if (otherModal._previousActiveModal === modal) {
            otherModal._previousActiveModal = modal._previousActiveModal;
        }
    });
    if (activeModal === modal) {
        const previousModal = modal._previousActiveModal?.classList.contains("show") ? modal._previousActiveModal : null;
        activeModal = previousModal;
        document.body.classList.toggle("modal-open", Boolean(previousModal));
        updateModalBackground(previousModal);
        const trigger = modal._modalTrigger;
        if (trigger instanceof HTMLElement && !trigger.inert) trigger.focus();
        modalTrigger = previousModal?._modalTrigger || null;
    }
    modal._previousActiveModal = null;
    modal._modalTrigger = null;
}

function closeAppModal(modal) {
    if (!modal) return;
    if (modal.id === "dietModal" && window.DietEntryFlow?.canClose() === false) return false;
    if (modal.id === 'loginScreen' && !currentUser) pendingAuthIntent = null;
    const fluid = typeof Fluid !== "undefined" ? Fluid : null;
    const content = modal.querySelector(".modal-content");
    const gen = modal._fluidGen || 0;

    modal._fluidClosing = true;
    if (content) content.dataset.fluidMaterial = "true";

    const done = () => {
        // A newer open re-targeted this modal mid-close; do not yank it shut.
        if ((modal._fluidGen || 0) !== gen) return;
        finalizeModalClose(modal);
    };

    if (!fluid || !content || (typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches)) {
        done();
        return;
    }

    fluid.animate(content, { y: 26, scale: 0.96, opacity: 0 }, {
        response: 0.3,
        damping: 1.0,
        onComplete: done
    });
    fluid.animate(modal, { opacity: 0 }, { response: 0.28, damping: 1.0 });
}

document.addEventListener("keydown", function(event) {
    if (!activeModal) return;
    if (event.key === "Escape" && activeModal.dataset.modalLocked !== "true") {
        closeAppModal(activeModal);
        return;
    }
    if (event.key !== "Tab") return;

    const focusable = getModalFocusable(activeModal);
    if (!focusable.length) {
        event.preventDefault();
        activeModal.setAttribute("tabindex", "-1");
        activeModal.focus();
        return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || !activeModal.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !activeModal.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
    }
});

function showAddDietModal() {
    if (!requireAuth('Entre para registrar suas refeições.', { resume: showAddDietModal })) return;
    pendingDietDailyContext = null;
    const modal = getElement("dietModal");
    const title = getElement("dietModalTitle");
    const form = getElement("dietForm");
    
    if (title) title.textContent = "Registrar refeição";
    if (form) form.reset();
    modal?.querySelectorAll('details').forEach(detail => { detail.open = false; });
    if (getElement('precisionBadge')) getElement('precisionBadge').textContent = '';
    if (getElement('dietDate')) getElement('dietDate').disabled = false;
    if (getElement('dietMeal')) getElement('dietMeal').disabled = false;
    // Set today's date
    const dietDate = getElement("dietDate");
    if (dietDate) {
        dietDate.value = localDateInputValue();
    }
    syncChoiceCards();
    window.DietEntryFlow?.begin();
    openAppModal(modal);
}

function closeDietModal() {
    const modal = getElement("dietModal");
    if (closeAppModal(modal) === false) return;
    pendingDietDailyContext = null;
    clearForms();
}

function showAddMeasurementModal() {
    if (!requireAuth('Entre para registrar e acompanhar suas medidas.', { resume: showAddMeasurementModal })) return;
    const modal = getElement("measurementModal");
    const title = getElement("measurementModalTitle");
    const form = getElement("measurementForm");
    
    if (title) title.textContent = "Adicionar Medidas";
    if (form) form.reset();
    
    // Set today's date
    const measurementDate = getElement("measurementDate");
    if (measurementDate) {
        measurementDate.value = localDateInputValue();
    }
    openAppModal(modal);
}

function closeMeasurementModal() {
    const modal = getElement("measurementModal");
    closeAppModal(modal);
    clearForms();
}

function closeProfileModal() {
    pendingPostProfileResume = null;
    pendingProfileRequiredFields = [];
    const modal = getElement("profileModal");
    closeAppModal(modal);
}

function skipProfile() {
    pendingPostProfileResume = null;
    closeProfileModal();
}

function fillProfileForm(profile) {
    const values = {
        profileAge: profile?.age,
        profileGender: profile?.gender,
        profileGoal: profile?.goal,
        profileActivity: profile?.activity_level,
        profileRestrictions: profile?.dietary_restrictions,
        profileWeight: profile?.weight,
        profileHeight: profile?.height
    };
    Object.entries(values).forEach(([id, value]) => {
        const field = getElement(id);
        if (field) field.value = value ?? '';
    });
    syncChoiceCards();
}

async function openProfileEditor() {
    if (!requireAuth('Entre para configurar seu perfil e seus objetivos.', { resume: openProfileEditor })) return;
    try {
        const response = await fetch(`${API_BASE}/profile`, { credentials: 'include' });
        if (!response.ok) throw new Error('Não foi possível carregar o perfil.');
        const data = await response.json();
        fillProfileForm(data.profile);
        openAppModal(getElement('profileModal'));
    } catch (error) {
        showToast(error.message || 'Erro ao carregar perfil.', 'error');
    }
}

function closeViewDietPlanModal() {
    const modal = getElement("viewDietPlanModal");
    closeAppModal(modal);
}

function closeViewWorkoutPlanModal() {
    const modal = getElement("viewWorkoutPlanModal");
    if (window.invalidateWorkoutView) window.invalidateWorkoutView();
    closeAppModal(modal);
}

// Data functions
async function loadDietEntries(options = {}) {
    if (!currentUser) {
        renderGuestPresentation('diet');
        return;
    }
    if (options.showLoading !== false) showGlobalLoading();
    const todayOnly = currentTab === 'diet';
    const startDate = options.startDate || (todayOnly ? localDateInputValue() : getElement("dietStartDate")?.value);
    const endDate = options.endDate || (todayOnly ? localDateInputValue() : getElement("dietEndDate")?.value);
    const requestRange = { startDate: startDate || null, endDate: endDate || null };
    dietEntriesLoadRange = requestRange;
    
    try {
        let url = `${API_BASE}/diet`;
        const params = new URLSearchParams();
        if (startDate) params.append('start_date', startDate);
        if (endDate) params.append('end_date', endDate);
        if (params.toString()) url += '?' + params.toString();

        dietEntriesLoadPromise = fetch(url, { credentials: 'include' })
            .then(async (response) => {
                if (!response.ok) {
                    console.error('Failed to load diet entries');
                    return null;
                }
                return response.json();
            })
            .catch((error) => {
                console.error('Error loading diet entries:', error);
                return null;
            });

        const entries = await dietEntriesLoadPromise;
        if (entries) {
            dietEntries = entries;
            renderDietTable();
            renderTodayRecentMeals();
        }
    } catch (error) {
        console.error('Error loading diet entries:', error);
    } finally {
        if (dietEntriesLoadRange.startDate === requestRange.startDate && dietEntriesLoadRange.endDate === requestRange.endDate) {
            dietEntriesLoadPromise = null;
        }
        if (options.showLoading !== false) hideGlobalLoading();
    }
}

function setCurrentUser(user) {
    if (currentUser?.id !== user?.id) {
        clearMeasurements();
        window.DietEntryFlow?.reset();
        if (getElement("dietModal")?.classList.contains("show")) closeDietModal();
    }
    currentUser = user;
}

function clearMeasurements() {
    measurementAccountVersion += 1;
    measurementRequestToken += 1;
    measurementSummaryToken += 1;
    if (measurementLoading) hideGlobalLoading();
    measurementLoading = false;
    measurements = [];
    measurementHasMore = false;
    measurementRange = null;
    ['measurementTableBody', 'measurementSummary'].forEach(id => {
        const element = getElement(id);
        if (element) element.innerHTML = '';
    });
    ['measurementStartDate', 'measurementEndDate'].forEach(id => {
        const element = getElement(id);
        if (element) element.value = '';
    });
    if (getElement('bodyMetric')) getElement('bodyMetric').value = 'weight';
    if (getElement('bodyPeriod')) getElement('bodyPeriod').value = 'all';
    getElement('measurementForm')?.reset();
    const modal = getElement('measurementModal');
    if (modal?.classList.contains('show')) closeAppModal(modal);
}

async function loadMeasurements(loadMore = false) {
    if (!currentUser) {
        clearMeasurements();
        renderGuestPresentation('measurements');
        return;
    }
    const startDate = getElement("measurementStartDate")?.value || '';
    const endDate = getElement("measurementEndDate")?.value || '';
    const range = `${startDate}/${endDate}`;
    const append = loadMore === true && range === measurementRange;
    if (append && (measurementLoading || !measurementHasMore)) return;
    const token = ++measurementRequestToken;
    const accountVersion = measurementAccountVersion;
    if (!append) {
        measurements = [];
        measurementHasMore = false;
        measurementRange = range;
        getElement('measurementTableBody').innerHTML = '';
    }
    measurementLoading = true;
    showGlobalLoading();
    try {
        if (startDate && endDate && startDate > endDate) {
            throw new Error('A data inicial deve ser anterior ou igual à data final.');
        }
        const params = new URLSearchParams({ limit: '20' });
        if (startDate) params.set('start_date', startDate);
        if (endDate) params.set('end_date', endDate);
        if (append) params.set('offset', String(measurements.length));
        const response = await fetch(`${API_BASE}/measurements?${params}`, { credentials: 'include' });
        const data = await response.json();
        if (token !== measurementRequestToken || accountVersion !== measurementAccountVersion) return;
        if (!response.ok) throw new Error(data.error || 'Não foi possível carregar suas medidas.');
        const items = Array.isArray(data) ? data : (data.items || []);
        measurements = append ? [...measurements, ...items] : items;
        measurementHasMore = items.length >= 20;
        renderMeasurementTable();
    } catch (error) {
        if (token === measurementRequestToken && accountVersion === measurementAccountVersion) {
            showToast(error.message || 'Não foi possível carregar suas medidas.', 'error');
            const list = getElement('measurementTableBody');
            list?.insertAdjacentHTML('beforeend', `<div class="progress-feedback" role="alert"><p>${escapeHtml(error.message)}</p><button type="button" onclick="this.parentElement.remove(); loadMeasurements(${append});">Tentar novamente</button></div>`);
        }
    } finally {
        if (token === measurementRequestToken) {
            measurementLoading = false;
            hideGlobalLoading();
        }
    }
}

async function loadMeasurementSummary() {
    const summary = getElement('measurementSummary');
    if (!summary || !currentUser) {
        if (summary) summary.innerHTML = '';
        return;
    }
    summary.innerHTML = '<p role="status">Carregando evolução...</p>';
    const token = ++measurementSummaryToken;
    const accountVersion = measurementAccountVersion;
    try {
        const response = await fetch(`${API_BASE}/measurements/summary?${new URLSearchParams({
            metric: getElement('bodyMetric')?.value || 'weight',
            start_date: getElement('measurementStartDate')?.value || '',
            end_date: getElement('measurementEndDate')?.value || '',
        })}`, { credentials: 'include' });
        const data = await response.json();
        if (token !== measurementSummaryToken || accountVersion !== measurementAccountVersion) return;
        if (!response.ok) throw new Error(data.error || 'Não foi possível carregar o resumo.');
        summary.innerHTML = renderBodyEvolution(data, getElement('bodyMetric')?.value || 'weight');
    } catch (error) {
        if (token === measurementSummaryToken && accountVersion === measurementAccountVersion) {
            summary.innerHTML = `<div role="alert"><p class="session-inline-error">${escapeHtml(error.message)}</p><button type="button" onclick="loadMeasurementSummary()">Tentar novamente</button></div>`;
        }
    }
}

async function deleteDietPlan(id) {
    if (!confirm("Tem certeza que deseja excluir este plano de dieta?")) return;
    showToast("Excluindo plano de dieta...", "info");
    try {
        const response = await fetch(`${API_BASE}/diet_plans/${id}`, { method: "DELETE", credentials: 'include' });
        if (response.ok) {
            showToast("Plano de dieta excluído!", "success");
            loadDietPlans();
        } else {
            const errorData = await response.json();
            showToast(errorData.error || "Erro ao excluir plano de dieta!", "error");
        }
    } catch (e) {
        showToast("Erro de conexão ao excluir plano de dieta!", "error");
    }
}

function exerciseImagePath(_exerciseName, catalogKey) {
    const key = String(catalogKey || "");
    return key ? `${API_BASE}/exercise-media/${encodeURIComponent(key)}` : "";
}

function exerciseFallbackImagePath(catalogKey) {
    const path = window.EXERCISE_MEDIA?.[String(catalogKey || "")]?.image || "";
    return path && !path.startsWith("/") ? `/${path}` : path;
}

function exerciseImageMarkup(exercise, escapedName) {
    const imagePath = exerciseImagePath(exercise.name, exercise.catalog_key);
    const fallbackPath = exerciseFallbackImagePath(exercise.catalog_key);
    if (imagePath) {
        const fallback = fallbackPath && fallbackPath !== imagePath ? ` data-fallback-src="${escapeHtml(fallbackPath)}"` : "";
        return `<img class="exercise-demonstration-image" src="${escapeHtml(imagePath)}"${fallback} alt="Demonstração de ${escapedName}" loading="lazy">`;
    }
    return '<span class="exercise-image-placeholder" role="img" aria-label="Imagem não disponível"><i class="fas fa-dumbbell" aria-hidden="true"></i></span>';
}

document.addEventListener('error', event => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || !image.classList.contains('exercise-demonstration-image')) return;
    const fallbackPath = image.dataset.fallbackSrc;
    if (fallbackPath) {
        delete image.dataset.fallbackSrc;
        image.src = fallbackPath;
        return;
    }
    const placeholder = document.createElement('span');
    placeholder.className = 'exercise-image-placeholder';
    placeholder.setAttribute('role', 'img');
    placeholder.setAttribute('aria-label', 'Imagem não disponível');
    placeholder.innerHTML = '<i class="fas fa-dumbbell" aria-hidden="true"></i>';
    image.replaceWith(placeholder);
}, true);

async function deleteWorkoutPlan(id) {
    if (!confirm("Tem certeza que deseja excluir este plano de treino?")) return;
    showToast("Excluindo plano de treino...", "info");
    try {
        const response = await fetch(`${API_BASE}/workout_plans/${id}`, { method: "DELETE", credentials: 'include' });
        if (response.ok) {
            showToast("Plano de treino excluído!", "success");
            loadWorkoutPlans();
        } else {
            const errorData = await response.json();
            showToast(errorData.error || "Erro ao excluir plano de treino!", "error");
        }
    } catch (e) {
        showToast("Erro de conexão ao excluir plano de treino!", "error");
    }
}


// Rendering and Form functions
function mealIconClass(mealType) {
    const normalized = String(mealType || '').toLowerCase();
    if (normalized.includes('café') || normalized.includes('manha')) return 'fa-mug-hot';
    if (normalized.includes('almoço')) return 'fa-sun';
    if (normalized.includes('jantar') || normalized.includes('ceia')) return 'fa-moon';
    if (normalized.includes('lanche')) return 'fa-apple-whole';
    return 'fa-utensils';
}

function mealIconName(mealType) {
    const normalized = String(mealType || '').toLowerCase();
    if (normalized.includes('café') || normalized.includes('manha')) return 'coffee';
    if (normalized.includes('almoço')) return 'sun';
    if (normalized.includes('jantar') || normalized.includes('ceia')) return 'moon';
    if (normalized.includes('lanche')) return 'apple';
    return 'utensils';
}

let expandedTodayMacro = null;

function renderTodayMacroDetails() {
    const panel = getElement('todayMacroDetails');
    const section = getElement('todayNutrition');
    if (!panel || !section) return;
    const button = expandedTodayMacro
        ? section.querySelector(`[data-today-macro="${expandedTodayMacro}"]`)
        : null;
    section.querySelectorAll('[data-today-macro]').forEach(item => {
        const selected = item === button;
        item.classList.toggle('is-expanded', selected);
        item.setAttribute('aria-expanded', String(selected));
    });
    section.classList.toggle('has-expanded-macro', Boolean(button));
    panel.setAttribute('aria-hidden', String(!button));
    if (!button) return;

    const consumed = Number(button.dataset.consumed) || 0;
    const target = Number(button.dataset.target);
    const hasTarget = Number.isFinite(target) && target > 0;
    const unit = button.dataset.unit || '';
    const percentage = hasTarget ? Math.round((consumed / target) * 100) : null;
    const balance = hasTarget ? target - consumed : null;
    const balanceLabel = balance == null
        ? 'Meta não definida'
        : balance >= 0
            ? `Faltam ${Math.round(balance).toLocaleString('pt-BR')} ${unit}`
            : `Excedeu ${Math.round(Math.abs(balance)).toLocaleString('pt-BR')} ${unit}`;
    panel.className = `today-macro-details today-macro-details--${expandedTodayMacro}`;
    panel.querySelector('.today-macro-details__inner').innerHTML = `
        <span><small>Consumido</small><strong>${Math.round(consumed).toLocaleString('pt-BR')} ${unit}</strong></span>
        <span><small>Meta</small><strong>${hasTarget ? `${Math.round(target).toLocaleString('pt-BR')} ${unit}` : '—'}</strong></span>
        <span><small>Progresso</small><strong>${percentage == null ? '—' : `${percentage}%`}</strong></span>
        <span><small>Saldo</small><strong>${balanceLabel}</strong></span>`;
}

function bindTodayMacroControls() {
    const grid = document.querySelector('#todayNutrition .today-macro-grid');
    if (!grid) return;
    grid.addEventListener('click', event => {
        const button = event.target.closest('[data-today-macro]');
        if (!button) return;
        const macro = button.dataset.todayMacro;
        expandedTodayMacro = expandedTodayMacro === macro ? null : macro;
        renderTodayMacroDetails();
    });
}

function updateDailySummary() {
    const today = localDateInputValue();
    const hasDailyView = todayDietDay?.date === today;
    const entries = hasDailyView
        ? [
            ...(todayDietDay.manual_entries || []),
            ...(todayDietDay.slots || []).map(slot => slot.entry).filter(Boolean)
        ]
        : dietEntries.filter(entry => entry.date === today);
    const totals = hasDailyView ? todayDietDay.totals : entries.reduce((sum, entry) => ({
        calories: sum.calories + (Number(entry.calories) || 0),
        protein: sum.protein + (Number(entry.protein) || 0),
        carbs: sum.carbs + (Number(entry.carbs) || 0),
        fat: sum.fat + (Number(entry.fat) || 0)
    }), { calories: 0, protein: 0, carbs: 0, fat: 0 });
    const entryCount = entries.length;
    getElement('todayNutrition')?.classList.toggle('hidden', !entryCount || !currentUser);
    const count = getElement('todayMealCount');
    if (count) count.textContent = entryCount ? `${entryCount} ${entryCount === 1 ? 'refeição registrada' : 'refeições registradas'}` : 'Nenhuma refeição registrada';
    const nutritionCount = getElement('todayNutritionCount');
    if (nutritionCount) nutritionCount.textContent = entryCount ? `${entryCount} ${entryCount === 1 ? 'refeição' : 'refeições'}` : '';
    const planTargets = cardapioActivePlan?.nutrition_targets || {};
    const targetKeys = { calories: 'targetCalories', protein: 'targetProtein', carbs: 'targetCarbs', fat: 'targetFat' };
    const labels = { calories: 'kcal', protein: 'g', carbs: 'g', fat: 'g' };
    Object.entries(totals).forEach(([key, value]) => {
        const rounded = Math.round(value);
        const target = Number(hasDailyView ? todayDietDay.targets?.[key] : planTargets[targetKeys[key]]);
        const hasTarget = Number.isFinite(target) && target > 0;
        const valueElement = getElement(`today${key.charAt(0).toUpperCase()}${key.slice(1)}`);
        const targetElement = getElement(`today${key.charAt(0).toUpperCase()}${key.slice(1)}Target`);
        const progressElement = getElement(`today${key.charAt(0).toUpperCase()}${key.slice(1)}Progress`);
        const macroButton = document.querySelector(`[data-today-macro="${key}"]`);
        if (valueElement) valueElement.textContent = `${rounded.toLocaleString('pt-BR')} ${labels[key]}`;
        if (targetElement) {
            targetElement.textContent = hasTarget ? `de ${Math.round(target).toLocaleString('pt-BR')} ${labels[key]}` : '';
            targetElement.classList.toggle('hidden', !hasTarget);
        }
        if (progressElement) {
            const progress = hasTarget ? Math.min(Math.max((value / target) * 100, 0), 100) : 0;
            progressElement.style.setProperty('--macro-progress', `${progress}%`);
            progressElement.classList.toggle('is-unavailable', !hasTarget);
        }
        if (macroButton) {
            macroButton.dataset.consumed = String(Number(value) || 0);
            macroButton.dataset.target = hasTarget ? String(target) : '';
            macroButton.dataset.unit = labels[key];
        }
    });
    renderTodayMacroDetails();
}

function renderDietTable() {
    const container = getElement("dietTableBody");
    if (!container) return;

    updateDailySummary();
    if (!dietEntries.length) {
        container.innerHTML = `
            <div class="empty-state empty-state--compact">
                <span><i class="fas fa-utensils"></i></span>
                <div><strong>Nenhuma refeição neste período</strong><p>Registre sua primeira refeição para acompanhar os macros.</p></div>
            </div>`;
        return;
    }

    container.innerHTML = dietEntries.map(entry => `
        <article class="diary-meal-card">
            <span class="diary-meal-card__icon"><i class="fas ${mealIconClass(entry.meal_type)}"></i></span>
            <div class="diary-meal-card__content">
                <div><strong>${escapeHtml(getMealTypeLabel(entry.meal_type))}</strong><time datetime="${escapeHtml(entry.date)}">${formatDate(entry.date)}</time></div>
                <p>${escapeHtml(entry.description)}</p>
                <div class="diary-meal-card__macros"><span>${Math.round(Number(entry.protein) || 0)}g prot.</span><span>${Math.round(Number(entry.carbs) || 0)}g carb.</span><span>${Math.round(Number(entry.fat) || 0)}g gord.</span></div>
            </div>
            <div class="diary-meal-card__energy"><strong>${Math.round(Number(entry.calories) || 0)}</strong><small>kcal</small></div>
            <div class="entry-actions">
                <button type="button" onclick="editDietEntry(${Number(entry.id)})" class="entry-action" aria-label="Editar ${escapeHtml(getMealTypeLabel(entry.meal_type))}"><i class="fas fa-pen"></i></button>
                <button type="button" onclick="deleteDietEntry(${Number(entry.id)})" class="entry-action entry-action--danger" aria-label="Excluir ${escapeHtml(getMealTypeLabel(entry.meal_type))}"><i class="fas fa-trash"></i></button>
            </div>
        </article>`).join('');
}

function renderTodayRecentMeals() {
    const container = getElement('todayRecentMeals');
    if (!container) return;
    const today = localDateInputValue();
    const entries = dietEntries.filter(entry => entry.date === today).slice(0, 3);
    if (!entries.length) {
        container.innerHTML = '<div class="empty-state empty-state--compact"><span><i class="fas fa-utensils"></i></span><div><strong>Nenhuma refeição registrada</strong><p>Seu primeiro registro aparecerá aqui.</p></div></div>';
        return;
    }
    container.innerHTML = entries.map(entry => `<article class="diary-meal-card"><span class="diary-meal-card__icon"><i class="fas ${mealIconClass(entry.meal_type)}"></i></span><div class="diary-meal-card__content"><div><strong>${escapeHtml(getMealTypeLabel(entry.meal_type))}</strong></div><p>${escapeHtml(entry.description)}</p></div><div class="diary-meal-card__energy"><strong>${Math.round(Number(entry.calories) || 0)}</strong><small>kcal</small></div></article>`).join('');
}

function measurementMetric(label, value, unit = '') {
    if (value == null || value === '') return '';
    return `<div><small>${label}</small><strong>${escapeHtml(value)}${unit}</strong></div>`;
}

// --- CARDÁPIO DE HOJE (sincronizado com o plano de dieta) ---
let cardapioActivePlan = null;
let cardapioDay = 1;
let pendingDietDaySuggestion = null;
let todayDietDay = null;
let todayDietOptionsSlotKey = null;
let pendingDietDailyContext = null;
let todayDietMutationSlotKey = null;
let dietDailyView = null;
let dietDailyDate = null;
let dietDailyOptionsSlotKey = null;
let dietDailyMutationSlotKey = null;
let dietPlansLibraryLoaded = false;

function dietPlanItemText(item) {
    return window.formatDietPlanItem?.(item) || String(item || "");
}

function dietPlanItemsText(meal) {
    return window.formatDietPlanItemsText?.(meal) || (Array.isArray(meal?.items) ? meal.items.map(dietPlanItemText).filter(Boolean).join(", ") : (meal?.description || ""));
}

function dietPlanItemsRawText(meal) {
    const items = Array.isArray(meal?.items) ? meal.items.map((item) => {
        if (!item || typeof item !== "object") return String(item || "");
        const quantity = Number(item.quantity);
        return `${Number.isFinite(quantity) ? quantity : ""} ${item.unit || "g"} de ${item.name || item.foodId || "alimento"}`.trim();
    }).filter(Boolean) : [];
    return items.length ? items.join(", ") : (meal?.description || "");
}

function getStoredCardapioDay() {
    const stored = parseInt(localStorage.getItem("dietCardapioDay") || "1", 10);
    return [1, 2, 3].includes(stored) ? stored : 1;
}

function setStoredCardapioDay(day) {
    localStorage.setItem("dietCardapioDay", String(day));
}

function normalizeMealType(value) {
    const normalized = String(value || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    return normalized.replace(/\s+/g, " ").trim();
}

function cardapioMealTypeToEntry(mealType) {
    const norm = normalizeMealType(mealType);
    if (norm.includes("lanche") && norm.includes("tarde")) return "Lanche da tarde";
    if (norm.includes("lanche")) return "Lanche da manhã";
    if (norm.includes("cafe")) return "Café da manhã";
    if (norm.includes("almoco")) return "Almoço";
    if (norm.includes("jantar")) return "Jantar";
    if (norm.includes("ceia")) return "Ceia";
    return mealType || "Café da manhã";
}

async function loadTodayCardapio() {
    if (!currentUser) {
        cardapioActivePlan = null;
        todayDietDay = null;
        renderTodayCardapio(null, null);
        renderDietCurrentPlanHub(null, null);
        return;
    }
    const section = getElement("todayCardapioSection");
    if (!section) return;
    const today = localDateInputValue();
    cardapioDay = getStoredCardapioDay();

    let dailyResponse;
    let currentPlanResponse;
    try {
        [dailyResponse, currentPlanResponse] = await Promise.all([
            fetch(`${API_BASE}/diet/days/${encodeURIComponent(today)}`, { credentials: "include" }),
            fetch(`${API_BASE}/diet_plans/current`, { credentials: "include" })
        ]);
    } catch (error) {
        renderTodayCardapio(null, 'Sem conexão. Seu plano não foi removido. Reconecte e tente novamente.');
        renderDietCurrentPlanHub(cardapioActivePlan, 'Não foi possível carregar seu plano de dieta.');
        return;
    }
    if (currentPlanResponse.ok) {
        const currentPlanPayload = await currentPlanResponse.json();
        cardapioActivePlan = currentPlanPayload.plan || null;
        renderDietCurrentPlanHub(cardapioActivePlan, null);
    } else {
        renderDietCurrentPlanHub(cardapioActivePlan, 'Não foi possível carregar seu plano de dieta.');
    }
    if (!dailyResponse.ok) {
        renderTodayCardapio(null, 'Não foi possível carregar sua alimentação de hoje.');
        return;
    }
    todayDietDay = await dailyResponse.json();
    renderTodayCardapio(todayDietDay, null);
}

function editDailyNutritionTargets() {
    if (!requireAuth('Entre para editar metas e gerar um novo cardápio.', { premium: true, requiresProfile: true, resume: editDailyNutritionTargets })) return;
    if (!cardapioActivePlan) {
        if (window.openPlanWizard) window.openPlanWizard("diet");
        return;
    }
    if (window.openDietPlanWizardWithPlan) window.openDietPlanWizardWithPlan(cardapioActivePlan);
}

function renderTodayCardapio(dailyView, errorMessage) {
    const bodyEl = getElement('todayCardapioBody');
    if (!bodyEl) return;
    updateDailySummary();
    const register = '<button type="button" class="today-food-primary" onclick="showAddDietModal()">Registrar refeição</button>';
    if (errorMessage) {
        bodyEl.innerHTML = `<p role="alert">${escapeHtml(errorMessage)}</p><button type="button" class="text-button" onclick="loadTodayCardapio()">Tentar novamente</button>${register}`;
        return;
    }
    const slots = Array.isArray(dailyView?.slots) ? dailyView.slots : [];
    const slot = slots.find(item => item.result === 'pending');
    if (!slot) {
        const message = !dailyView?.plan ? 'Você pode registrar sua alimentação sem ter um plano.' : slots.length ? 'Todas as refeições planejadas de hoje já têm um resultado.' : 'Sem refeições previstas para hoje.';
        bodyEl.innerHTML = `<p class="today-muted">${message}</p>${register}`;
        return;
    }
    const alternatives = Array.isArray(slot.alternatives) ? slot.alternatives : [];
    const meal = alternatives.find(item => Number(item.id) === Number(slot.selected_plan_meal_id)) || alternatives[0];
    if (!meal) {
        bodyEl.innerHTML = `<p class="today-muted">Sem opção disponível para esta refeição.</p>${register}`;
        return;
    }
    const optionPosition = alternatives.findIndex(item => Number(item.id) === Number(meal.id)) + 1;
    const selectorOpen = todayDietOptionsSlotKey === slot.slot_key;
    const selector = selectorOpen ? `<div class="today-meal-options" aria-label="Alternativas de ${escapeHtml(slot.label)}">${alternatives.map((option, index) => `
        <button type="button" class="today-meal-option${Number(option.id) === Number(meal.id) ? ' is-selected' : ''}" onclick="selectTodayDietOption('${slot.slot_key}', ${Number(option.id)})" aria-pressed="${Number(option.id) === Number(meal.id)}">
            <strong>Opção ${index + 1}</strong><span>${escapeHtml(dietPlanItemsText(option))}</span>
        </button>`).join('')}</div>` : '';
    const mutating = todayDietMutationSlotKey === slot.slot_key;
    const disabled = mutating ? ' disabled' : '';
    const primaryLabel = mutating
        ? '<span class="today-action-spinner" aria-hidden="true"></span> Salvando...'
        : '<i data-lucide="check" aria-hidden="true"></i> Comi isso';
    bodyEl.innerHTML = `<div class="today-meal"><div class="today-meal__intro"><span class="today-meal__icon"><i data-lucide="${mealIconName(meal.meal_type)}" aria-hidden="true"></i></span><div><p class="today-muted">Opção ${optionPosition} de ${alternatives.length}</p><h3>${escapeHtml(slot.label || meal.meal_type)}</h3></div></div><p class="today-food-description">${escapeHtml(dietPlanItemsText(meal))}</p><button type="button" class="today-food-primary" onclick="quickLogDailyMeal('${slot.slot_key}', 'exact')"${disabled} aria-busy="${mutating}">${primaryLabel}</button><div class="today-food-secondary"><button type="button" class="text-button" onclick="quickLogDailyMeal('${slot.slot_key}', 'describe')"${disabled}>Comi diferente</button><button type="button" class="text-button diet-daily-skip" onclick="quickLogDailyMeal('${slot.slot_key}', 'skip')"${disabled}>Pular refeição</button>${alternatives.length > 1 ? `<button type="button" class="text-button" onclick="toggleTodayDietOptions('${slot.slot_key}')" aria-expanded="${selectorOpen}"${disabled}>Trocar opção</button>` : ''}</div>${selector}</div>`;
}

function renderDietCurrentPlanHub(plan, errorMessage) {
    const chipsEl = getElement('dietCurrentDayChips');
    const bodyEl = getElement('dietCurrentPlanBody');
    if (!chipsEl || !bodyEl) return;
    chipsEl.innerHTML = [1, 2, 3].map(day => `
        <button type="button" class="day-chip${day === cardapioDay ? ' is-active' : ''}" onclick="setCardapioDay(${day})" aria-pressed="${day === cardapioDay}">Dia ${day}</button>
    `).join('');
    if (errorMessage) {
        bodyEl.innerHTML = `<div class="empty-state empty-state--compact"><span><i class="fas fa-triangle-exclamation"></i></span><div><strong>Plano indisponível</strong><p>${escapeHtml(errorMessage)}</p></div><button type="button" class="btn-secondary" onclick="loadTodayCardapio()">Tentar novamente</button></div>`;
        return;
    }
    if (!plan?.meals?.length) {
        bodyEl.innerHTML = `<div class="empty-state empty-state--compact"><span><i class="fas fa-seedling"></i></span><div><strong>Nenhum plano ativo</strong><p>Crie ou selecione um plano alimentar para começar.</p></div><button type="button" class="btn-primary" data-plan-wizard="diet">Criar plano</button></div>`;
        return;
    }
    const meals = plan.meals
        .filter(meal => normalizeMealType(meal.day_of_week) === `dia ${cardapioDay}`)
        .sort((a, b) => (a.order || 0) - (b.order || 0));
    bodyEl.innerHTML = `
        <div class="cardapio-list">${meals.map(meal => `<article class="cardapio-item"><div class="cardapio-item__head"><span class="cardapio-item__icon"><i class="fas ${mealIconClass(meal.meal_type)}"></i></span><div class="cardapio-item__copy"><strong>${escapeHtml(meal.meal_type)}</strong><p>${escapeHtml(dietPlanItemsText(meal))}</p><div class="cardapio-item__macros"><span>${Math.round(Number(meal.calories) || 0)} kcal</span><span>${Math.round(Number(meal.protein) || 0)}g prot.</span></div></div><button type="button" class="entry-action" onclick="openEditPlanMealModal(${meal.id})" aria-label="Editar refeição do plano"><i class="fas fa-pen-to-square"></i></button></div></article>`).join('')}</div>
        <div class="cardapio-footer"><button type="button" class="btn-secondary" onclick="window.viewDietPlan?.(${Number(plan.id)})">Ver plano completo</button><button type="button" class="btn-secondary" onclick="openSuggestDietModal()"><i class="fas fa-wand-magic-sparkles"></i> Sugerir mudança</button><button type="button" class="btn-primary" onclick="editDailyNutritionTargets()">Ajustar plano</button></div>`;
}

function setCardapioDay(day) {
    if (![1, 2, 3].includes(Number(day))) return;
    setStoredCardapioDay(Number(day));
    cardapioDay = Number(day);
    renderDietCurrentPlanHub(cardapioActivePlan, null);
}

function findPlanMeal(mealId) {
    if (!cardapioActivePlan) return null;
    return (cardapioActivePlan.meals || []).find(meal => Number(meal.id) === Number(mealId)) || null;
}

function findTodayDietSlot(slotKey) {
    return (todayDietDay?.slots || []).find(slot => slot.slot_key === slotKey) || null;
}

function toggleTodayDietOptions(slotKey) {
    todayDietOptionsSlotKey = todayDietOptionsSlotKey === slotKey ? null : slotKey;
    renderTodayCardapio(todayDietDay, null);
}

async function selectTodayDietOption(slotKey, mealId) {
    if (todayDietMutationSlotKey) return;
    const slot = findTodayDietSlot(slotKey);
    if (!slot) return;
    todayDietMutationSlotKey = slotKey;
    renderTodayCardapio(todayDietDay, null);
    try {
        const response = await fetch(`${API_BASE}/diet/days/${encodeURIComponent(todayDietDay.date)}/slots/${encodeURIComponent(slotKey)}/selection`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ diet_plan_meal_id: mealId })
        });
        if (!response.ok) {
            const errorData = await response.json();
            showToast(errorData.error || "Não foi possível trocar a opção.", "error");
            return;
        }
        slot.selected_plan_meal_id = mealId;
        todayDietOptionsSlotKey = null;
        renderTodayCardapio(todayDietDay, null);
    } catch (error) {
        showToast("Erro de conexão!", "error");
    } finally {
        todayDietMutationSlotKey = null;
        renderTodayCardapio(todayDietDay, null);
    }
}

async function quickLogDailyMeal(slotKey, mode) {
    if (todayDietMutationSlotKey) return;
    const slot = findTodayDietSlot(slotKey);
    const meal = slot?.alternatives?.find(item => Number(item.id) === Number(slot.selected_plan_meal_id));
    if (!slot || !meal) {
        showToast("Refeição não encontrada.", "error");
        return;
    }
    const entryType = cardapioMealTypeToEntry(meal.meal_type);
    if (mode === "describe") {
        showAddDietModal();
        pendingDietDailyContext = { slotKey, mealId: meal.id };
    getElement('dietDate').disabled = true;
    getElement('dietMeal').disabled = true;
        getElement("dietDate").value = todayDietDay.date;
        getElement("dietMeal").value = entryType;
        getElement("dietDescription").value = "";
        syncChoiceCards();
        return;
    }
    todayDietMutationSlotKey = slotKey;
    renderTodayCardapio(todayDietDay, null);
    try {
        const response = await fetch(`${API_BASE}/diet/days/${encodeURIComponent(todayDietDay.date)}/slots/${encodeURIComponent(slotKey)}/outcome`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({
                result: mode === "skip" ? "skipped" : "consumed_planned",
                diet_plan_meal_id: meal.id
            })
        });
        if (response.ok) {
            showToast(mode === "skip" ? "Refeição marcada como pulada." : "Refeição registrada!", "success");
            await Promise.all([loadDietEntries({ showLoading: false }), loadTodayCardapio()]);
        } else {
            const errorData = await response.json();
            showToast(errorData.error || "Erro ao registrar!", "error");
        }
    } catch (error) {
        showToast("Erro de conexão!", "error");
    } finally {
        todayDietMutationSlotKey = null;
        if (todayDietDay) renderTodayCardapio(todayDietDay, null);
    }
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

function renderDietDailyAlternatives(slot, selectedMeal) {
    if (dietDailyOptionsSlotKey !== slot.slot_key) return '';
    return `<div class="diet-daily-options" aria-label="Alternativas de ${escapeHtml(slot.label)}">${(slot.alternatives || []).map(meal => `<button type="button" class="diet-daily-option${Number(meal.id) === Number(selectedMeal?.id) ? ' is-selected' : ''}" onclick="selectDietDailyOption('${slot.slot_key}', ${Number(meal.id)})" aria-pressed="${Number(meal.id) === Number(selectedMeal?.id)}"><span><strong>Opção ${Number(meal.option) || 1}</strong><small>Dia ${Number(meal.option) || 1}</small></span><p>${escapeHtml(dietPlanItemsText(meal))}</p><i data-lucide="check" aria-hidden="true"></i></button>`).join('')}</div>`;
}

function renderDietDailySlot(slot) {
    const meal = dailySlotSelectedMeal(slot);
    if (!meal) return '';
    const option = Number(meal.option) || 1;
    const busy = dietDailyMutationSlotKey === slot.slot_key ? ' disabled' : '';
    const title = escapeHtml(slot.label || meal.meal_type || 'Refeição');
    const plannedText = escapeHtml(dietPlanItemsText(slot.planned_snapshot || meal));
    const actual = slot.entry;
    const icon = mealIconName(slot.label || meal.meal_type);
    if (slot.result === 'skipped') {
        return `<article class="diet-daily-slot diet-daily-slot--compact"><span class="diet-daily-slot__icon"><i data-lucide="${icon}" aria-hidden="true"></i></span><div><h3>${title}</h3><p>Refeição pulada</p></div><span class="diet-daily-status diet-daily-status--skipped">Pulada</span><button type="button" class="text-button" onclick="resetDietDailySlot('${slot.slot_key}')"${busy}>Corrigir</button></article>`;
    }
    if (slot.result === 'consumed_planned') {
        return `<article class="diet-daily-slot diet-daily-slot--done"><header><span class="diet-daily-slot__icon"><i data-lucide="${icon}" aria-hidden="true"></i></span><div><h3>${title}</h3><p>Opção ${option} · Dia ${option}</p></div><span class="diet-daily-status diet-daily-status--done"><i data-lucide="check" aria-hidden="true"></i> Concluída</span></header><div class="diet-daily-actual"><span>Consumido</span><strong>${escapeHtml(actual?.description || plannedText)}</strong>${dailyMealMacros(actual)}</div><div class="diet-daily-slot__footer"><small>Conforme a opção planejada</small><div class="diet-daily-slot__record-actions"><button type="button" class="text-button" onclick="editDietEntry(${Number(actual?.id)})">Corrigir registro</button><button type="button" class="text-button diet-daily-skip" onclick="deleteDietEntry(${Number(actual?.id)})">Excluir registro</button></div></div></article>`;
    }
    if (slot.result === 'consumed_different') {
        return `<article class="diet-daily-slot diet-daily-slot--done"><header><span class="diet-daily-slot__icon"><i data-lucide="${icon}" aria-hidden="true"></i></span><div><h3>${title}</h3><p>Opção ${option} · Dia ${option}</p></div><span class="diet-daily-status diet-daily-status--done"><i data-lucide="check" aria-hidden="true"></i> Registrada</span></header><div class="diet-daily-actual"><span>Você consumiu</span><strong>${escapeHtml(actual?.description || 'Consumo registrado')}</strong>${dailyMealMacros(actual)}</div><div class="diet-daily-planned"><span>Estava previsto</span><p>${plannedText}</p></div><div class="diet-daily-slot__footer"><span></span><div class="diet-daily-slot__record-actions"><button type="button" class="text-button" onclick="editDietEntry(${Number(actual?.id)})">Corrigir registro</button><button type="button" class="text-button diet-daily-skip" onclick="deleteDietEntry(${Number(actual?.id)})">Excluir registro</button></div></div></article>`;
    }
    const alternatives = slot.alternatives || [];
    return `<article class="diet-daily-slot"><header><span class="diet-daily-slot__icon"><i data-lucide="${icon}" aria-hidden="true"></i></span><div><h3>${title}</h3><p>Opção ${option} de ${alternatives.length} · Dia ${option}</p></div><span class="diet-daily-status">Pendente</span></header><p class="diet-daily-slot__food">${escapeHtml(dietPlanItemsText(meal))}</p><button type="button" class="diet-daily-primary" onclick="setDietDailyOutcome('${slot.slot_key}', 'consumed_planned')"${busy}><i data-lucide="check" aria-hidden="true"></i> Comi isso</button><div class="diet-daily-secondary">${alternatives.length > 1 ? `<button type="button" class="text-button" onclick="toggleDietDailyOptions('${slot.slot_key}')" aria-expanded="${dietDailyOptionsSlotKey === slot.slot_key}"${busy}>Trocar opção</button>` : ''}<button type="button" class="text-button" onclick="openDietDailyDifferent('${slot.slot_key}')"${busy}>Comi diferente</button><button type="button" class="text-button diet-daily-skip" onclick="setDietDailyOutcome('${slot.slot_key}', 'skipped')"${busy}>Pulei</button></div>${renderDietDailyAlternatives(slot, meal)}</article>`;
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
    container.innerHTML = `${slots.map(renderDietDailySlot).join('')}${manual.length ? `<div class="diet-daily-additional"><h3>Outras refeições</h3>${manual.map(renderDietDailyManualEntry).join('')}</div>` : ''}`;
}

function renderDietDailyPlan() {
    const container = getElement('dietDailyPlan');
    if (!container) return;
    const plan = dietDailyView?.plan;
    if (!plan) {
        cardapioActivePlan = null;
        container.innerHTML = '<div><span class="eyebrow">Plano alimentar</span><h2 id="dietDailyPlanTitle">Sem plano atual</h2><p>O diário funciona normalmente sem um plano.</p></div><button type="button" class="btn-secondary" data-plan-wizard="diet">Criar plano alimentar</button>';
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
    dietDailyDate = dateValue;
    dietDailyOptionsSlotKey = null;
    updateDietDailyDateHeader();
    const container = getElement('dietDailyMealsBody');
    if (container) container.innerHTML = '<div class="diet-daily-empty"><span class="today-icon--spin"><i data-lucide="loader-circle" aria-hidden="true"></i></span><div><strong>Carregando seu dia</strong></div></div>';
    try {
        const response = await fetch(`${API_BASE}/diet/days/${encodeURIComponent(dietDailyDate)}`, { credentials: 'include' });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || 'Tente novamente em instantes.');
        }
        dietDailyView = await response.json();
        dietEntries = dailyViewEntries(dietDailyView);
        renderDietDailyMacros();
        renderDietDailyMeals();
        renderDietDailyPlan();
    } catch (error) {
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

function toggleDietDailyOptions(slotKey) {
    dietDailyOptionsSlotKey = dietDailyOptionsSlotKey === slotKey ? null : slotKey;
    renderDietDailyMeals();
}

async function selectDietDailyOption(slotKey, mealId) {
    if (dietDailyMutationSlotKey) return;
    dietDailyMutationSlotKey = slotKey;
    renderDietDailyMeals();
    try {
        const response = await fetch(`${API_BASE}/diet/days/${encodeURIComponent(dietDailyDate)}/slots/${encodeURIComponent(slotKey)}/selection`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
            body: JSON.stringify({ diet_plan_meal_id: mealId })
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || 'Não foi possível trocar a opção.');
        }
        dietDailyOptionsSlotKey = null;
        await refreshDietDailySurfaces();
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        dietDailyMutationSlotKey = null;
        if (dietDailyView) renderDietDailyMeals();
    }
}

function openDietDailyDifferent(slotKey) {
    const slot = (dietDailyView?.slots || []).find(item => item.slot_key === slotKey);
    const meal = dailySlotSelectedMeal(slot);
    if (!slot || !meal) return;
    showAddDietModal();
    pendingDietDailyContext = { slotKey, mealId: meal.id };
    getElement('dietDate').disabled = true;
    getElement('dietMeal').disabled = true;
    getElement('dietDate').value = dietDailyDate;
    getElement('dietMeal').value = cardapioMealTypeToEntry(meal.meal_type);
    getElement('dietDescription').value = '';
    syncChoiceCards();
}

async function setDietDailyOutcome(slotKey, result) {
    if (dietDailyMutationSlotKey) return;
    const slot = (dietDailyView?.slots || []).find(item => item.slot_key === slotKey);
    const meal = dailySlotSelectedMeal(slot);
    if (!slot || !meal) return;
    dietDailyMutationSlotKey = slotKey;
    renderDietDailyMeals();
    try {
        const response = await fetch(`${API_BASE}/diet/days/${encodeURIComponent(dietDailyDate)}/slots/${encodeURIComponent(slotKey)}/outcome`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
            body: JSON.stringify({ result, diet_plan_meal_id: meal.id })
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || 'Não foi possível atualizar a refeição.');
        }
        showToast(result === 'skipped' ? 'Refeição marcada como pulada.' : 'Refeição registrada!', 'success');
        await refreshDietDailySurfaces();
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        dietDailyMutationSlotKey = null;
        if (dietDailyView) renderDietDailyMeals();
    }
}

async function resetDietDailySlot(slotKey) {
    if (dietDailyMutationSlotKey) return;
    dietDailyMutationSlotKey = slotKey;
    try {
        const response = await fetch(`${API_BASE}/diet/days/${encodeURIComponent(dietDailyDate)}/slots/${encodeURIComponent(slotKey)}/outcome`, {
            method: 'DELETE', credentials: 'include'
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || 'Não foi possível reabrir a refeição.');
        }
        await refreshDietDailySurfaces();
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        dietDailyMutationSlotKey = null;
    }
}

async function refreshDietDailySurfaces() {
    await loadDietDailyScreen(dietDailyDate);
    if (dietDailyDate === localDateInputValue()) await loadTodayCardapio();
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
    const height = getElement("profileHeight")?.value;

    if (pendingProfileRequiredFields.length) {
        const values = {
            age: Number(age),
            gender,
            activity_level: activity,
            weight: Number(weight),
            height: Number(height)
        };
        const valid = {
            age: Number.isFinite(values.age) && values.age >= 18 && values.age <= 120,
            gender: Boolean(values.gender),
            activity_level: Boolean(values.activity_level),
            weight: Number.isFinite(values.weight) && values.weight >= 30 && values.weight <= 300,
            height: Number.isFinite(values.height) && values.height >= 120 && values.height <= 250
        };
        const firstMissing = pendingProfileRequiredFields.find(field => !valid[field]);
        if (firstMissing) {
            const focusTargets = {
                age: 'profileAge',
                gender: 'genderCards',
                activity_level: 'activityCards',
                weight: 'profileWeight',
                height: 'profileHeight'
            };
            showToast('Preencha os dados obrigatórios para gerar sua dieta.', 'error');
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
                height: height ? parseFloat(height) : null
            })
        });

        if (response.ok) {
            const resume = pendingPostProfileResume;
            pendingPostProfileResume = null;
            pendingProfileRequiredFields = [];
            closeAppModal(getElement("profileModal"));
            showToast("Perfil salvo com sucesso!", "success");
            if (resume) {
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
            else await Promise.all([loadDietEntries({ showLoading: false }), loadTodayCardapio()]);
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
    const startDate = getElement("dietStartDate");
    const endDate = getElement("dietEndDate");

    const today = localDateInputValue();
    if (startDate) startDate.value = today;
    if (endDate) endDate.value = today;
    
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
    return typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// --- 1. Press feedback: respond on pointer-down, cancel by dragging away ---
(function pressFeedback() {
    const PRESSABLE = ".btn, .nav-btn, .btn-close, .plan-card, .meal-card, .macro-card, .session-card, .exercise-card, .activity-card, .btn-view, .btn-add, .btn-edit, .btn-delete";

    document.addEventListener("pointerdown", (e) => {
        if (e.button !== undefined && e.button !== 0) return;
        if (reducedMotion()) return;
        const target = e.target;
        if (!(target instanceof Element)) return;
        const pressable = target.closest ? target.closest(PRESSABLE) : null;
        if (!pressable) return;

        pressable.classList.add("is-pressed");
        const gx = e.clientX;
        const gy = e.clientY;

        const release = () => {
            pressable.classList.remove("is-pressed");
            window.removeEventListener("pointerup", release);
            window.removeEventListener("pointercancel", release);
            window.removeEventListener("pointermove", onMove);
        };
        const onMove = (ev) => {
            // hysteresis: a 12px drag means it was a scroll/gesture, not a tap
            if (Math.hypot(ev.clientX - gx, ev.clientY - gy) > 12) release();
        };
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
        if (reducedMotion()) return;

        if (content.setPointerCapture) content.setPointerCapture(e.pointerId);
        baseY = e.clientY;
        lastY = e.clientY;
        lastT = performance.now();
        vel = 0;
        moved = false;
        content.classList.add("is-dragging");

        const onMove = (ev) => {
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
            content.classList.remove("is-dragging");
            if (content.releasePointerCapture && ev.pointerId !== undefined) {
                try { content.releasePointerCapture(ev.pointerId); } catch (err) {}
            }
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onUp);
            window.removeEventListener("pointercancel", onUp);

            const fluid = typeof Fluid !== "undefined" ? Fluid : null;
            if (!moved) {
                if (fluid) fluid.animate(content, { y: 0, scale: 1 }, { response: 0.3, damping: 1.0 });
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
            if (dismiss) {
                fluid.haptic.snap();
                fluid.animate(content, { y: height }, {
                    response: 0.34,
                    damping: 0.8,
                    velocity: { y: vel },
                    from: { y: finalDy, scale: 1, opacity: 1 },
                    onComplete() {
                        if (modal._fluidGen !== undefined) modal._fluidGen += 1; // invalidate any close
                        finalizeModalClose(modal);
                    }
                });
            } else {
                fluid.haptic.tap();
                fluid.animate(content, { y: 0 }, {
                    response: 0.3,
                    damping: 1.0,
                    velocity: { y: vel },
                    from: { y: finalDy, scale: 1, opacity: 1 }
                });
            }
        };

        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
        window.addEventListener("pointercancel", onUp);
    });
}
