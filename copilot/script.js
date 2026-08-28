// script.js

// Global variables
let currentUser = null;
let currentTab = 'diet';
let dietEntries = [];
let dietEntriesLoadPromise = null;
let dietEntriesLoadRange = { startDate: null, endDate: null };
let measurements = [];
let measurementHasMore = false;
let measurementRequestToken = 0;
let pendingAuthIntent = null;
let pendingPostProfileResume = null;
let googleSignupToken = null;
let profileAchievementsState = { selected: [], achievements: [], badges: [], limit: 3, filter: 'all', savingToken: null };

// API Base URL
const API_BASE = '/api';

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
    setTimeout(() => {
        messageEl.textContent = "";
        messageEl.className = "message";
        messageEl.style.display = "none";
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
    const dataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error("Falha ao ler o arquivo"));
        reader.readAsDataURL(file);
    });
    const img = await new Promise((resolve, reject) => {
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = () => reject(new Error("Falha ao decodificar a imagem"));
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
    if (ctx) ctx.drawImage(img, 0, 0, width, height);
    const out = canvas.toDataURL("image/jpeg", 0.8);
    return { dataUrl: out, base64: out.split(",")[1] };
}

// Foto selecionada para gerar macros por imagem (base64 já reduzido).
let dietPhoto = null;

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

function syncDietDateChips() {
    const chips = getElement("dietDateChips");
    const dateInput = getElement("dietDate");
    if (!chips || !dateInput) return;
    const current = dateInput.value || "";
    chips.querySelectorAll(".chip-btn").forEach(btn => {
        const offset = parseInt(btn.dataset.dayOffset || "0", 10);
        const targetDate = localDateInputValue(new Date(Date.now() + offset * 24 * 60 * 60 * 1000));
        btn.classList.toggle("is-active", current === targetDate);
    });
}

function bindDietDateChips() {
    const chips = getElement("dietDateChips");
    const dateInput = getElement("dietDate");
    if (!chips || !dateInput) return;
    chips.querySelectorAll(".chip-btn").forEach(btn => {
        btn.addEventListener("click", function() {
            const offset = parseInt(btn.dataset.dayOffset || "0", 10);
            const targetDate = new Date(Date.now() + offset * 24 * 60 * 60 * 1000);
            dateInput.value = localDateInputValue(targetDate);
            chips.querySelectorAll(".chip-btn").forEach(c => c.classList.toggle("is-active", c === btn));
            dateInput.dispatchEvent(new Event("change", { bubbles: true }));
        });
    });
    dateInput.addEventListener("change", syncDietDateChips);
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
    bindChoiceCardGrid("mealTypeCards", "dietMeal");
    document.querySelectorAll(".stepper").forEach(bindStepper);
    bindDietDateChips();
    bindFieldReveal();
}

function syncChoiceCards() {
    syncChoiceCardGrid("genderCards", "profileGender");
    syncChoiceCardGrid("goalCards", "profileGoal");
    syncChoiceCardGrid("activityCards", "profileActivity");
    syncChoiceCardGrid("mealTypeCards", "dietMeal");
}

// Adiciona listeners ao carregar a página
document.addEventListener('DOMContentLoaded', function() {
    setDefaultDates();
    initializeAudioFeatures();
    checkAuthStatus();
    setupAppStyleControls();
    syncChoiceCards();
    initializeAchievementControls();
    initializeGoogleAuth();
    addEventListenerSafe('googleUsernameForm', 'submit', finishGoogleSignup);

    // Autocomplete local para descrição dos alimentos
    const dietDescription = getElement("dietDescription");
    if (dietDescription) {
        let alimentosList = [];
        let alimentosData = [];
        // Verifique o caminho correto para seu arquivo JSON
        fetch("minha-pasta/alimentos.json") 
            .then(res => res.json())
            .then(data => {
                alimentosData = data.filter(item => item.descricao);
                alimentosList = alimentosData.map(item => item.descricao);
            })
            .catch(error => console.error("Erro ao carregar alimentos.json:", error));

        const awesomplete = window.Awesomplete ? new Awesomplete(dietDescription, {
            minChars: 2,
            maxItems: 10,
            autoFirst: true
        }) : null;

        dietDescription.addEventListener("input", function() {
            const query = dietDescription.value.trim().toLowerCase();
            if (query.length < 2) return;
            if (!awesomplete) return;
            awesomplete.list = alimentosList.filter(desc =>
                desc.toLowerCase().includes(query)
            );
        });

        dietDescription.addEventListener("awesomplete-selectcomplete", function() {
            const selected = alimentosData.find(item => item.descricao === dietDescription.value);
            if (selected) {
                getElement("dietCalories").value = selected.calorias ?? "";
                getElement("dietProtein").value = selected.proteina ?? "";
                getElement("dietCarbs").value = selected.carboidrato ?? "";
                getElement("dietFat").value = selected.gordura ?? "";
            }
        });
    }

    // Formulário de dieta
    const dietForm = document.getElementById("dietForm");
    if (dietForm) {
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

    addEventListenerSafe("dietPhotoBtn", "click", function() {
        getElement("dietPhotoInput")?.click();
    });

    addEventListenerSafe("dietPhotoInput", "change", async function(e) {
        const file = e.target.files && e.target.files[0];
        if (!file) return;
        try {
            const result = await downscaleImageFile(file, 1024);
            dietPhoto = { data: result.base64, mime_type: file.type || "image/jpeg" };
            const preview = getElement("dietPhotoPreview");
            if (preview) preview.classList.remove("hidden");
            const img = getElement("dietPhotoPreviewImg");
            if (img) img.src = result.dataUrl;
        } catch (error) {
            dietPhoto = null;
            showDietMessage("Não foi possível carregar a foto.", "error");
        }
    });

    addEventListenerSafe("dietPhotoRemove", "click", function() {
        dietPhoto = null;
        const input = getElement("dietPhotoInput");
        if (input) input.value = "";
        const preview = getElement("dietPhotoPreview");
        if (preview) preview.classList.add("hidden");
        const img = getElement("dietPhotoPreviewImg");
        if (img) img.removeAttribute("src");
    });

    addEventListenerSafe("generateMacrosBtn", "click", async function() {
        const btnText = getElement("generateMacrosBtnText");
        const btnLoading = getElement("generateMacrosLoading");
        if (btnText) btnText.classList.add("hidden");
        if (btnLoading) btnLoading.classList.remove("hidden");
        const description = getElement("dietDescription")?.value.trim();
        if (!description && !dietPhoto) {
            showDietMessage("Descreva o alimento ou envie uma foto para gerar macros.", "error");
            if (btnText) btnText.classList.remove("hidden");
            if (btnLoading) btnLoading.classList.add("hidden");
            return;
        }
        try {
            const body = { description: description || null };
            if (dietPhoto) body.image = dietPhoto;
            const response = await fetch(`${API_BASE}/diet/ai_macros`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify(body)
            });
            const data = await response.json();
            if (response.ok) {
                getElement("dietCalories").value = data.calories || 0;
                getElement("dietProtein").value = data.protein || 0;
                getElement("dietCarbs").value = data.carbs || 0;
                getElement("dietFat").value = data.fat || 0;
                const badge = getElement('precisionBadge');
                if (badge) {
                    badge.textContent = data.precision === "alta" ? "Alta precisão"
                        : data.precision === "moderada" ? "Precisão moderada"
                        : "Baixa precisão";
                    badge.className = data.precision === "alta" ? "precision-high"
                        : data.precision === "moderada" ? "precision-moderate"
                        : "precision-low";
                }
                if (data.precision === "baixa") {
                    showDietMessage("Descrição vaga! Os valores são estimados. Edite se necessário.", "info");
                }
            } else {
                showDietMessage(data.error || "Erro ao gerar macros", "error");
            }
        } catch (error) {
            showDietMessage("Erro ao gerar macros", "error");
        }
        if (btnText) btnText.classList.remove("hidden");
        if (btnLoading) btnLoading.classList.add("hidden");
    });
});

// --- FUNÇÕES PRINCIPAIS ---

async function handleDietFormSubmit() {
    const btn = document.getElementById("dietSaveBtn");
    const loading = document.getElementById("dietSaveLoading");
    btn.disabled = true;
    loading.classList.remove("hidden");

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

    const url = isEdit ? `/api/diet/${dietId}` : "/api/diet";
    const method = isEdit ? "PUT" : "POST";

    try {
        const response = await fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            showToast("Dieta salva com sucesso!", "success");
            closeDietModal();
            loadDietEntries({ showLoading: false });
            loadTodayCardapio();
        } else {
            const errorData = await response.json();
            showToast(errorData.error || "Erro ao salvar dieta!", "error");
        }
    } catch (e) {
        showToast("Erro de conexão!", "error");
    } finally {
        btn.disabled = false;
        loading.classList.add("hidden");
    }
}

// Atualiza o peso do perfil ao salvar uma nova medida
async function handleMeasurementFormSubmit() {
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

        if (response.ok) {
            closeMeasurementModal();
            loadMeasurements();
            showToast(isEdit ? "Medidas atualizadas!" : "Medidas adicionadas!", "success");
            const profileUpdate = {};
            if (payload.weight != null) profileUpdate.weight = payload.weight;
            if (payload.height != null) profileUpdate.height = payload.height;
            if (Object.keys(profileUpdate).length) {
                await fetch(`${API_BASE}/profile`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    credentials: "include",
                    body: JSON.stringify(profileUpdate)
                });
            }
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
        { id: "profileModal", closeFunc: closeProfileModal },
        { id: "exerciseCreditsModal", closeFunc: closeExerciseCredits }
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
    try {
        const response = await fetch(`${API_BASE}/check_session`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.logged_in) {
                if (data.csrf_token) setCsrfToken(data.csrf_token);
                currentUser = data.user;
                showMainScreen();
            } else {
                setCsrfToken(null);
                currentUser = null;
                showMainScreen();
            }
        } else {
            setCsrfToken(null);
            showMainScreen();
        }
    } catch (error) {
        console.error('Auth check failed:', error);
        setCsrfToken(null);
        showMainScreen();
    }
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
}

function requireAuth(reason, options = {}) {
    if (currentUser) {
        if (options.premium && !hasAiAccess()) {
            showToast('Este recurso utiliza IA e está disponível no plano Premium.', 'info');
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
        const response = await fetch(`${API_BASE}/auth/config`);
        const config = response.ok ? await response.json() : {};
        if (!config.google_client_id) return;
        getElement('googleAuthSection')?.classList.remove('hidden');
        getElement('googleHeaderButton')?.classList.remove('hidden');
        const script = document.createElement('script');
        script.src = 'https://accounts.google.com/gsi/client';
        script.async = true;
        script.defer = true;
        script.onload = () => {
            google.accounts.id.initialize({
                client_id: config.google_client_id,
                callback: handleGoogleCredential
            });
            google.accounts.id.renderButton(getElement('googleSignInButton'), {
                theme: 'outline', size: 'large', width: 320, text: 'continue_with'
            });
        };
        document.head.appendChild(script);
    } catch (error) {
        console.error('Google auth configuration failed:', error);
    }
}

function openAuthWithGoogle() {
    openAuthModal('Entre com sua conta Google em um toque.', 'login');
    if (window.google?.accounts?.id) {
        try { google.accounts.id.prompt(); } catch (error) { /* o modal oficial permanece como caminho alternativo */ }
    }
}

async function handleGoogleCredential(result) {
    try {
        const response = await fetch(`${API_BASE}/auth/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ credential: result.credential })
        });
        const data = await response.json().catch(() => ({}));
        if (response.status === 409 && data.code === 'username_required') {
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
    }
}

async function finishGoogleSignup(event) {
    event.preventDefault();
    const username = getElement('googleUsername')?.value.trim();
    if (!googleSignupToken || !username) return;
    try {
        const response = await fetch(`${API_BASE}/auth/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ signup_token: googleSignupToken, username })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Não foi possível concluir o cadastro.');
        googleSignupToken = null;
        getElement('googleUsernameForm')?.classList.add('hidden');
        completeAuthentication(data.user, data.csrf_token);
    } catch (error) {
        showAuthMessage(error.message, 'error');
    }
}

function completeAuthentication(user, csrfToken = null) {
    currentUser = user;
    setCsrfToken(csrfToken);
    closeAppModal(getElement('loginScreen'));
    showMainScreen({ skipProfile: true });
    checkUserProfile();
    showToast('Você entrou com sucesso.', 'success');
}

window.handleGoogleCredential = handleGoogleCredential;

Object.defineProperty(window, 'currentUser', { get: () => currentUser });
window.requireAuth = requireAuth;

function showMainScreen(options = {}) {
    const loginScreen = getElement('loginScreen');
    const mainScreen = getElement('mainScreen');
    
    if (loginScreen?.classList.contains('show')) closeAppModal(loginScreen);
    if (mainScreen) mainScreen.classList.remove('hidden');
    
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
        const aiAccessLabel = getElement('homeAiAccessLabel');
        if (aiAccessLabel) {
            const remaining = Math.max(0, 3 - Number(currentUser.ai_trial_uses || 0));
            aiAccessLabel.textContent = currentUser.is_premium ? 'Premium' : `${remaining} ${remaining === 1 ? 'uso grátis' : 'usos grátis'}`;
        }
        const homeDate = getElement('homeDate');
        if (homeDate) {
            const formatted = new Intl.DateTimeFormat('pt-BR', {
                weekday: 'long',
                day: '2-digit',
                month: 'long'
            }).format(new Date());
            homeDate.textContent = formatted.charAt(0).toUpperCase() + formatted.slice(1);
        }

        const isAdmin = Boolean(currentUser.is_admin);
        const isProfessional = Boolean(currentUser.is_professional);
        getElement('adminPanelBtn')?.classList.toggle('hidden', !isAdmin);
        getElement('profileAdminLink')?.classList.toggle('hidden', !isAdmin);
        getElement('professionalPanelBtn')?.classList.toggle('hidden', !isProfessional);
    } else {
        const welcomeUser = getElement('welcomeUser');
        if (welcomeUser) welcomeUser.textContent = 'Explore o Fit-Tracker.AI';
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
        const aiAccessLabel = getElement('homeAiAccessLabel');
        if (aiAccessLabel) aiAccessLabel.textContent = '3 usos grátis';
        getElement('adminPanelBtn')?.classList.add('hidden');
        getElement('profileAdminLink')?.classList.add('hidden');
        getElement('professionalPanelBtn')?.classList.add('hidden');
        if (window.clearActiveWorkoutDock) window.clearActiveWorkoutDock();
    }

    getElement('guestAuthActions')?.classList.toggle('hidden', Boolean(currentUser));
    getElement('userHeaderButton')?.classList.toggle('hidden', !currentUser);
    const showHeaderPill = currentUser?.is_premium !== true;
    getElement('premiumHeaderPill')?.classList.toggle('hidden', !showHeaderPill);
    getElement('profileUpgradePill')?.classList.toggle('hidden', !(currentUser && !currentUser.is_premium));
    getElement('profileLoginAction')?.classList.toggle('hidden', Boolean(currentUser));
    getElement('profileLogoutAction')?.classList.toggle('hidden', !currentUser);
    getElement('editProfileBtn')?.classList.toggle('hidden', !currentUser);
    getElement('profileGuestPanel')?.classList.toggle('hidden', Boolean(currentUser));
    getElement('profileAuthenticatedContent')?.classList.toggle('hidden', !currentUser);

    const chatNavBtn = document.querySelector(`.nav-btn[onclick="showTab('chat')"]`);
    if (chatNavBtn) {
        chatNavBtn.style.display = '';
        chatNavBtn.classList.toggle('is-locked', !hasAiAccess());
        chatNavBtn.setAttribute('aria-label', hasAiAccess() ? 'Assistente IA' : 'Assistente IA, recurso Premium');
    }

    showTab(options.tab || 'diet');
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
    const item = [...profileAchievementsState.achievements, ...profileAchievementsState.badges].find(entry => availableToken(entry) === selectionToken(selection));
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
    const target = [...profileAchievementsState.achievements, ...profileAchievementsState.badges]
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
    fillProfileForm(null);
    openAppModal(getElement('profileModal'));
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
        if (cardapio) cardapio.innerHTML = '<div class="guest-presentation"><i class="fas fa-calendar-day"></i><div><strong>Seu cardápio diário organizado</strong><p>Crie uma conta para gerar planos e acompanhar as refeições de cada dia.</p></div></div>';
    }
    if (tabName === 'stats') {
        const latest = getElement('latestMeasurement');
        if (latest) latest.innerHTML = '<strong>Seu histórico em um só lugar</strong><span>Entre para acompanhar medidas, treinos, metas e conquistas.</span>';
        const total = getElement('totalDietEntries');
        const recent = getElement('recentDietEntries');
        if (total) total.textContent = '—';
        if (recent) recent.textContent = '—';
        const recentActivities = getElement('profileRecentActivities');
        if (recentActivities) recentActivities.innerHTML = '<div class="guest-presentation"><i class="fas fa-person-running"></i><div><strong>Atividades recentes</strong><p>Entre para ver seus treinos e progresso.</p></div></div>';
    }
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

/**
 * Envia mensagem no chat
 */
async function sendChatMessage() {
    if (!requireAuth('Entre para conversar com o Assistente IA.', { premium: true })) return;
    const input = getElement("chatInput");
    if (!input) return;

    const message = input.value.trim();
    if (!message) return;

    // Adiciona mensagem do usuário
    addMessageToChat(message, "user");
    input.value = "";
    
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
            const data = await response.json();
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
    }
}

/**
 * Envia mensagem para a IA com o perfil do usuário (usado pelos botões rápidos)
 */
async function sendChatMessageWithProfile(message, intent) {
    const chatMessages = getElement("chatMessages");
    if (!chatMessages) return;
    addMessageToChat(message, "user");
    showTypingIndicator();
    
    try {
        const response = await fetch(`${API_BASE}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ message, intent })
        });
        const data = await response.json();
        hideTypingIndicator();
        if (response.ok && data.response) {
            addMessageToChat(data.response, "bot");
            lastAIResponse = data.response;
            if (window.handlePlanChatAction) window.handlePlanChatAction(data.action);
        }
    } catch (error) {
        console.error("Chat error:", error);
        hideTypingIndicator();
        addMessageToChat("Erro de conexão com a IA.", "bot");
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
async function handleLogin(e) {
    e.preventDefault();
    const username = getElement("loginUsername").value.trim();
    const password = getElement("loginPassword").value.trim();

    if (!username || !password) {
        showAuthMessage("Preencha todos os campos", "error");
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/login`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            credentials: "include",
            body: JSON.stringify({ username, password })
        });

        const data = await response.json();
        if (response.ok) {
            currentUser = data.user;
            if (data.csrf_token) setCsrfToken(data.csrf_token);
            const intent = pendingAuthIntent;
            const destination = intent?.tab || currentTab;
            pendingAuthIntent = null;
            showMainScreen({ tab: destination, skipProfile: Boolean(intent?.resume) });
            showToast(data.message, "success");
            if (intent?.resume) resumeAfterAuthentication(intent.resume, intent.requiresProfile);
        } else {
            showAuthMessage(data.error, "error");
        }
    } catch (error) {
        console.error("Login error:", error);
        showAuthMessage("Erro de conexão. Tente novamente.", "error");
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const username = getElement("registerUsername").value.trim();
    const password = getElement("registerPassword").value.trim();
    const confirmPassword = getElement("confirmPassword").value.trim();

    if (!username || !password || !confirmPassword) {
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

    try {
        const response = await fetch(`${API_BASE}/register`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            credentials: "include",
            body: JSON.stringify({ username, password })
        });

        const data = await response.json();
        if (response.ok) {
            currentUser = data.user;
            if (data.csrf_token) setCsrfToken(data.csrf_token);
            const intent = pendingAuthIntent;
            const destination = intent?.tab || currentTab;
            pendingAuthIntent = null;
            showMainScreen({ tab: destination, skipProfile: Boolean(intent?.resume) });
            showToast(data.message, "success");
            if (intent?.resume) resumeAfterAuthentication(intent.resume, intent.requiresProfile);
        } else {
            showAuthMessage(data.error, "error");
        }
    } catch (error) {
        console.error("Register error:", error);
        showAuthMessage("Erro de conexão. Tente novamente.", "error");
    }
}

async function logout() {
    try {
        await fetch(`${API_BASE}/logout`, {
            method: "POST",
            credentials: "include"
        });
        currentUser = null;
        setCsrfToken(null);
        window.clearWorkoutProgress?.();
        showMainScreen({ tab: 'diet' });
        showToast("Logout realizado com sucesso", "success");
    } catch (error) {
        console.error("Logout error:", error);
        currentUser = null;
        setCsrfToken(null);
        window.clearWorkoutProgress?.();
        showMainScreen({ tab: 'diet' });
    }
}

// Interface functions
// Interface functions
function showTab(tabName) {
    if (tabName === 'activities' && !currentUser) {
        openAuthModal('Entre para acessar seu histórico de atividades.', 'login', { tab: 'activities' });
        return;
    }
    if (tabName === 'achievements' && !currentUser) {
        openAuthModal('Entre para acessar suas conquistas.', 'login', { tab: 'achievements' });
        return;
    }
    if (tabName === 'chat' && !hasAiAccess()) {
        if (!currentUser) {
            openAuthModal('Entre para conhecer o Assistente IA. Este é um recurso Premium.', 'register', { tab: 'chat', premium: true });
            return;
        }
        showToast('O Assistente IA está disponível no plano Premium.', 'info');
        return;
    }
    if (tabName === 'professional' && !currentUser?.is_professional) {
        showToast('A área profissional precisa ser habilitada por um administrador.', 'info');
        return;
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
    if (selectedTab) {
        selectedTab.classList.remove('hidden');
    }
    
    // Add active class to clicked button
    const navTabName = ['measurements', 'activities', 'achievements'].includes(tabName) ? 'stats' : tabName;
    const activeBtn = document.querySelector(`.nav-btn[onclick="showTab('${navTabName}')"]`);
    if (activeBtn) {
        activeBtn.classList.add('active');
        activeBtn.setAttribute('aria-current', 'page');
    }
    
    currentTab = tabName;
    document.body.dataset.activeTab = tabName;
    window.scrollTo({ top: 0, behavior: 'instant' });
    
    if (!currentUser) {
        renderGuestPresentation(tabName);
        return;
    }

    getElement('guestDailySummary')?.classList.add('hidden');
    getElement('dailyMacroGrid')?.classList.remove('hidden');
    if (tabName === 'diet') {
        loadDietEntries();
        loadTodayCardapio();
    } else if (tabName === 'measurements') {
        loadMeasurements();
    } else if (tabName === 'stats') {
        loadStats();
        loadMeasurementSummary();
        window.loadProgressOverview?.();
        loadRecentActivities();
    } else if (tabName === 'activities') {
        window.loadWorkoutActivities?.();
    } else if (tabName === 'achievements') {
        loadAchievementsTab();
    } else if (tabName === 'diet_plans') { // Carrega planos de dieta
        loadDietPlans();
    } else if (tabName === 'workout_plans') { // Carrega planos de treino
        loadWorkoutPlans();
    } else if (tabName === 'professional') {
        window.loadProfessionalDashboard?.();
    }
}

async function openPlansModal() {
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
                    ? `<button type="button" class="btn-primary" onclick="startBillingCheckout('${plan.code}', this)">Assinar por R$ ${Number(plan.price_brl).toFixed(0)}/mês</button>`
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
            ? 'Cartão renova automaticamente. No PIX, uma nova cobrança é gerada todo mês.'
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
    return `<button type="button" class="btn-primary" onclick="startBillingCheckout('${plan.code}', this)">Assinar por R$ ${Number(plan.price_brl).toFixed(0)}/mês</button>`;
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

async function startBillingCheckout(planCode, button) {
    if (!requireAuth('Crie sua conta para assinar e desbloquear o plano Premium.', { mode: 'register' })) return;
    if (button) button.disabled = true;
    try {
        const response = await fetch(`${API_BASE}/billing/checkout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ plan_code: planCode, payment_method: choosePaymentMethod() })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Não foi possível iniciar o pagamento.');
        window.location.href = data.checkout_url;
    } catch (error) {
        if (button) button.disabled = false;
        showToast(error.message, 'error');
    }
}

function choosePaymentMethod() {
    return window.confirm('Usar cartão de crédito (renovação automática)?\n\nOK = Cartão\nCancelar = PIX mensal') ? 'credit_card' : 'pix';
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
            container.innerHTML = `
                <section class="subscription-manage">
                    <div><strong>${escapeHtml(subscription.plan_code)}</strong>${until ? `<small>Ativo até ${escapeHtml(until)}</small>` : ''}</div>
                    ${providerConfigured ? '<button type="button" class="btn-secondary" onclick="cancelMySubscription()">Cancelar assinatura</button>' : ''}
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
    document.querySelectorAll("[data-modal-background-inert]").forEach(element => {
        element.inert = false;
        delete element.dataset.modalBackgroundInert;
    });
    if (!modal) return;

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
    modal.setAttribute("aria-hidden", "true");
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
    const modal = getElement("dietModal");
    const title = getElement("dietModalTitle");
    const form = getElement("dietForm");
    
    if (title) title.textContent = "Adicionar Registro de Dieta";
    if (form) form.reset();
    dietPhoto = null;
    const photoInput = getElement("dietPhotoInput");
    if (photoInput) photoInput.value = "";
    const photoPreview = getElement("dietPhotoPreview");
    if (photoPreview) photoPreview.classList.add("hidden");
    const photoImg = getElement("dietPhotoPreviewImg");
    if (photoImg) photoImg.removeAttribute("src");
    
    // Set today's date
    const dietDate = getElement("dietDate");
    if (dietDate) {
        dietDate.value = localDateInputValue();
    }
    syncDietDateChips();
    syncChoiceCards();
    openAppModal(modal);
}

function closeDietModal() {
    const modal = getElement("dietModal");
    closeAppModal(modal);
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

function safeExternalUrl(value) {
    try {
        const url = new URL(String(value || ""));
        return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
    } catch (error) {
        return "#";
    }
}

function openExerciseCredits() {
    const container = getElement('exerciseCreditsList');
    const entries = Object.values(window.EXERCISE_MEDIA || {});
    if (!container) return;

    const grouped = new Map();
    entries.forEach(entry => {
        const group = grouped.get(entry.image) || { ...entry, names: [] };
        group.names.push(entry.name);
        grouped.set(entry.image, group);
    });
    const credits = Array.from(grouped.values()).sort((left, right) => left.names[0].localeCompare(right.names[0], 'pt-BR'));
    container.innerHTML = credits.length ? credits.map(entry => {
        const authorUrl = safeExternalUrl(entry.author_url);
        const sourceUrl = safeExternalUrl(entry.object_url || entry.derivative_source_url || entry.source_url);
        const author = escapeHtml(entry.author || 'wger community');
        return `
            <article class="exercise-credit-card">
                <img src="${escapeHtml(entry.image)}" alt="" loading="lazy">
                <div class="exercise-credit-card__body">
                    <h4>${entry.names.map(escapeHtml).join(', ')}</h4>
                    <p>Imagem por ${authorUrl === '#' ? `<strong>${author}</strong>` : `<a href="${escapeHtml(authorUrl)}" target="_blank" rel="noopener noreferrer">${author}</a>`}${entry.license_title ? ` · ${escapeHtml(entry.license_title)}` : ''}</p>
                    <div class="exercise-credit-card__links">
                        <a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Fonte da imagem <i class="fas fa-arrow-up-right-from-square"></i></a>
                        <a href="${escapeHtml(safeExternalUrl(entry.license_url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(entry.license || 'Creative Commons')}</a>
                        ${entry.is_ai_generated ? '<span><i class="fas fa-wand-magic-sparkles"></i> Gerada por IA</span>' : ''}
                    </div>
                </div>
            </article>`;
    }).join('') : '<div class="empty-state"><strong>Nenhuma mídia externa importada.</strong></div>';
    openAppModal(getElement('exerciseCreditsModal'));
}

function closeExerciseCredits() {
    closeAppModal(getElement('exerciseCreditsModal'));
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
    const startDate = getElement("dietStartDate")?.value;
    const endDate = getElement("dietEndDate")?.value;
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

async function loadMeasurements() {
    if (!currentUser) {
        renderGuestPresentation('measurements');
        return;
    }
    showGlobalLoading();
    const startDate = getElement("measurementStartDate")?.value;
    const endDate = getElement("measurementEndDate")?.value;
    const token = ++measurementRequestToken;
    
    try {
        let url = `${API_BASE}/measurements`;
        const params = new URLSearchParams();
        if (startDate) params.append('start_date', startDate);
        if (endDate) params.append('end_date', endDate);
        params.append('limit', '20');
        if (measurements.length && !startDate && !endDate) params.append('offset', String(measurements.length));
        if (params.toString()) url += '?' + params.toString();
        
        const response = await fetch(url, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            const items = Array.isArray(data) ? data : (data.items || []);
            if (token !== measurementRequestToken) return;
            if (params.has('offset') && measurements.length) {
                measurements = [...measurements, ...items];
            } else {
                measurements = items;
            }
            measurementHasMore = items.length >= 20;
            renderMeasurementTable();
        } else {
            console.error('Failed to load measurements');
        }
    } catch (error) {
        console.error('Error loading measurements:', error);
    } finally {
        if (token === measurementRequestToken) hideGlobalLoading();
    }
}

async function loadMeasurementSummary() {
    const summary = getElement('measurementSummary');
    if (!summary || !currentUser) {
        if (summary) summary.innerHTML = '';
        return;
    }
    try {
        const response = await fetch(`${API_BASE}/measurements?limit=2`, { credentials: 'include' });
        if (!response.ok) { summary.innerHTML = ''; return; }
        const data = await response.json();
        const items = Array.isArray(data) ? data : (data.items || []);
        if (!items.length) {
            summary.innerHTML = '<div class="measurement-summary__empty"><i class="fas fa-ruler-combined"></i><div><strong>Nenhuma medição ainda</strong><p>Registre a primeira para acompanhar sua evolução.</p></div><button type="button" onclick="showAddMeasurementModal()">Adicionar medição</button></div>';
            return;
        }
        const latest = items[0];
        const previous = items[1];
        const weightDiff = latest.weight != null && previous?.weight != null ? (latest.weight - previous.weight).toFixed(1) : null;
        summary.innerHTML = `
            <div class="measurement-summary__hero">
                <div><small>Peso atual</small><strong>${escapeHtml(latest.weight)} kg</strong></div>
                ${weightDiff ? `<div class="measurement-summary__delta ${Number(weightDiff) > 0 ? 'measurement-summary__delta--up' : 'measurement-summary__delta--down'}"><i class="fas fa-${Number(weightDiff) > 0 ? 'arrow-up' : 'arrow-down'}"></i> ${weightDiff.replace('-', '−')} kg</div>` : ''}
            </div>
            <div class="measurement-summary__meta">
                ${latest.body_fat != null ? `<span>${escapeHtml(latest.body_fat)}% gordura</span>` : ''}
                ${latest.muscle_mass != null ? `<span>${escapeHtml(latest.muscle_mass)} kg massa</span>` : ''}
                <span>${formatDate(latest.date)}</span>
            </div>
        `;
    } catch (error) {
        summary.innerHTML = '';
    }
}

async function loadRecentActivities() {
    const container = getElement('profileRecentActivities');
    if (!container || !currentUser) {
        if (container) container.innerHTML = '';
        return;
    }
    container.innerHTML = '<div class="plans-loading"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>Carregando atividades...</span></div>';
    try {
        const response = await fetch(`${API_BASE}/activities?limit=3`, { credentials: 'include' });
        if (!response.ok) { container.innerHTML = ''; return; }
        const data = await response.json();
        const items = Array.isArray(data) ? data : (data.items || []);
        if (!items.length) {
            container.innerHTML = '<div class="profile-recent-activities__empty"><i class="fas fa-person-running"></i><p>Nenhuma atividade registrada ainda.</p></div>';
            return;
        }
        container.innerHTML = items.map(activity => {
            const completedAt = new Date(activity.completed_at);
            const time = completedAt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
            const duration = Math.round(Number(activity.duration_seconds || 0) / 60);
            return `<article class="profile-recent-card" onclick="showTab('activities')" role="button" tabindex="0">
                <div class="profile-recent-card__icon"><i class="fas fa-dumbbell"></i></div>
                <div><strong>${escapeHtml(activity.workout_name)}</strong><p>${time} · ${duration}min · ${activity.exercises_performed || 0} exercícios</p></div>
                <i class="fas fa-chevron-right" aria-hidden="true"></i>
            </article>`;
        }).join('');
    } catch (error) {
        container.innerHTML = '';
    }
}

async function loadStats() {
    if (!currentUser) {
        renderGuestPresentation('stats');
        return;
    }
    try {
        const response = await fetch(`${API_BASE}/stats`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const stats = await response.json();
            
            const latestMeasurement = getElement("latestMeasurement");
            const totalDietEntries = getElement("totalDietEntries");
            const recentDietEntries = getElement("recentDietEntries");
            
            if (latestMeasurement) {
                if (stats.latest_measurement) {
                    const m = stats.latest_measurement;
                    latestMeasurement.innerHTML = `
                        <strong>${m.weight != null ? `${escapeHtml(m.weight)} kg` : 'Sem peso'}</strong>
                        <span>${m.body_fat != null ? `${escapeHtml(m.body_fat)}% de gordura` : 'Composição não informada'} · ${formatDate(m.date)}</span>
                    `;
                } else {
                    latestMeasurement.textContent = "Nenhuma medição registrada";
                }
            }
            
            if (totalDietEntries) {
                totalDietEntries.textContent = stats.total_diet_entries || 0;
            }
            
            if (recentDietEntries) {
                recentDietEntries.textContent = stats.recent_diet_entries || 0;
            }
        }
    } catch (error) {
        console.error('Error loading stats:', error);
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
    return window.EXERCISE_MEDIA?.[String(catalogKey || "")]?.image || "";
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
    return 'fa-bowl-food';
}

function updateDailySummary() {
    const today = localDateInputValue();
    const totals = dietEntries.filter(entry => entry.date === today).reduce((sum, entry) => ({
        calories: sum.calories + (Number(entry.calories) || 0),
        protein: sum.protein + (Number(entry.protein) || 0),
        carbs: sum.carbs + (Number(entry.carbs) || 0),
        fat: sum.fat + (Number(entry.fat) || 0)
    }), { calories: 0, protein: 0, carbs: 0, fat: 0 });
    Object.entries(totals).forEach(([key, value]) => {
        const rounded = Math.round(value);
        const valueElement = getElement(`today${key.charAt(0).toUpperCase()}${key.slice(1)}`);
        const progressElement = getElement(`today${key.charAt(0).toUpperCase()}${key.slice(1)}Progress`);
        if (valueElement) valueElement.textContent = key === 'calories' ? rounded.toLocaleString('pt-BR') : `${rounded} g`;
        if (progressElement) progressElement.style.width = `${Math.min((value / dailyNutritionTargets[key]) * 100, 100)}%`;
    });
}

function renderDietTable() {
    const container = getElement("dietTableBody");
    if (!container) return;

    updateDailySummary();
    if (!dietEntries.length) {
        container.innerHTML = `
            <div class="empty-state empty-state--compact">
                <span><i class="fas fa-bowl-food"></i></span>
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

function measurementMetric(label, value, unit = '') {
    if (value == null || value === '') return '';
    return `<div><small>${label}</small><strong>${escapeHtml(value)}${unit}</strong></div>`;
}

// --- CARDÁPIO DE HOJE (sincronizado com o plano de dieta) ---
let cardapioActivePlan = null;
let cardapioDay = 1;
let cardapioTodayEntries = [];
let pendingDietDaySuggestion = null;
let dailyNutritionTargets = { calories: 2200, protein: 160, carbs: 220, fat: 70 };

function dietPlanItemText(item) {
    if (!item || typeof item !== "object") return String(item || "");
    const quantity = Number(item.quantity);
    const amount = Number.isFinite(quantity) ? quantity : "";
    return `${amount} ${item.unit || "g"} de ${item.name || item.foodId || "alimento"}`.trim();
}

function dietPlanItemsText(meal) {
    return Array.isArray(meal.items) ? meal.items.map(dietPlanItemText).filter(Boolean).join(", ") : (meal.description || "");
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
    if (norm.includes("cafe") || norm.includes("manha")) return "Café da manhã";
    if (norm.includes("almoco")) return "Almoço";
    if (norm.includes("jantar")) return "Jantar";
    if (norm.includes("lanche") && norm.includes("tarde")) return "Lanche da tarde";
    if (norm.includes("lanche")) return "Lanche da manhã";
    if (norm.includes("ceia")) return "Ceia";
    return mealType || "Café da manhã";
}

function cardapioTodayEntryKeys() {
    const keys = new Set();
    cardapioTodayEntries.forEach(entry => {
        keys.add(`${entry.date}|${normalizeMealType(entry.meal_type)}`);
    });
    return keys;
}

async function loadTodayCardapio() {
    if (!currentUser) {
        cardapioActivePlan = null;
        renderTodayCardapio(null, null);
        return;
    }
    const section = getElement("todayCardapioSection");
    if (!section) return;
    const today = localDateInputValue();
    cardapioDay = getStoredCardapioDay();

    const plansRes = await fetch(`${API_BASE}/diet_plans`, { credentials: 'include' });
    if (dietEntriesLoadPromise && dietEntriesLoadRange.startDate === today && dietEntriesLoadRange.endDate === today) {
        const entries = await dietEntriesLoadPromise;
        cardapioTodayEntries = Array.isArray(entries) ? entries.slice() : [];
    } else if (dietEntriesLoadRange.startDate === today && dietEntriesLoadRange.endDate === today && Array.isArray(dietEntries)) {
        cardapioTodayEntries = dietEntries.slice();
    } else {
        const entriesRes = await fetch(`${API_BASE}/diet?start_date=${today}&end_date=${today}`, { credentials: 'include' });
        cardapioTodayEntries = entriesRes.ok ? await entriesRes.json() : [];
    }

    if (!plansRes.ok) {
        renderTodayCardapio(null, 'Não foi possível carregar seu plano de dieta.');
        return;
    }
    const plans = await plansRes.json();
    if (!plans.length) {
        cardapioActivePlan = null;
        setDailyNutritionTargets(null);
        renderTodayCardapio(null, null);
        return;
    }
    const latestPlanId = plans[0].id;
    const planRes = await fetch(`${API_BASE}/diet_plans/${latestPlanId}`, { credentials: 'include' });
    if (!planRes.ok) {
        renderTodayCardapio(null, 'Não foi possível carregar o cardápio do plano.');
        return;
    }
    cardapioActivePlan = await planRes.json();
    setDailyNutritionTargets(cardapioActivePlan.nutrition_targets);
    renderTodayCardapio(cardapioActivePlan, null);
}

function setDailyNutritionTargets(targets) {
    dailyNutritionTargets = targets ? {
        calories: Number(targets.targetCalories) || 2200,
        protein: Number(targets.targetProtein) || 160,
        carbs: Number(targets.targetCarbs) || 220,
        fat: Number(targets.targetFat) || 70
    } : { calories: 2200, protein: 160, carbs: 220, fat: 70 };
    const labels = { calories: "kcal", protein: "g", carbs: "g", fat: "g" };
    Object.entries(dailyNutritionTargets).forEach(([key, value]) => {
        const targetElement = getElement(`today${key.charAt(0).toUpperCase()}${key.slice(1)}Target`);
        if (targetElement) targetElement.textContent = `de ${Math.round(value).toLocaleString("pt-BR")} ${labels[key]}`;
    });
    updateDailySummary();
}

function editDailyNutritionTargets() {
    if (!requireAuth('Entre para editar metas e gerar um novo cardápio.', { premium: true, requiresProfile: true, resume: editDailyNutritionTargets })) return;
    if (!cardapioActivePlan) {
        if (window.openPlanWizard) window.openPlanWizard("diet");
        return;
    }
    if (window.openDietPlanWizardWithPlan) window.openDietPlanWizardWithPlan(cardapioActivePlan);
}

function renderTodayCardapio(plan, errorMessage) {
    const chipsEl = getElement("todayDayChips");
    const bodyEl = getElement("todayCardapioBody");
    if (!chipsEl || !bodyEl) return;

    const chips = [1, 2, 3].map(day => `
        <button type="button" class="day-chip${day === cardapioDay ? ' is-active' : ''}" onclick="setCardapioDay(${day})" aria-pressed="${day === cardapioDay}">Dia ${day}</button>
    `).join('');
    chipsEl.innerHTML = chips;

    if (errorMessage) {
        bodyEl.innerHTML = `<div class="empty-state empty-state--compact"><span><i class="fas fa-triangle-exclamation"></i></span><div><strong>Cardápio indisponível</strong><p>${escapeHtml(errorMessage)}</p></div></div>`;
        return;
    }
    if (!plan || !plan.meals || !plan.meals.length) {
        bodyEl.innerHTML = `<div class="empty-state empty-state--compact"><span><i class="fas fa-seedling"></i></span><div><strong>Sem plano de dieta</strong><p>Crie um plano guiado e acompanhe suas refeições do dia.</p></div><button type="button" class="btn-primary" data-plan-wizard="diet"><i class="fas fa-wand-magic-sparkles"></i> Criar plano</button></div>`;
        return;
    }

    const dayMeals = plan.meals
        .filter(meal => normalizeMealType(meal.day_of_week) === `dia ${cardapioDay}`)
        .sort((a, b) => (a.order || 0) - (b.order || 0));

const doneKeys = cardapioTodayEntryKeys();

    const pendingMeals = [];
    const doneMeals = [];
    dayMeals.forEach(meal => {
        const entryType = cardapioMealTypeToEntry(meal.meal_type);
        const isDone = doneKeys.has(`${localDateInputValue()}|${normalizeMealType(entryType)}`);
        (isDone ? doneMeals : pendingMeals).push({ meal, entryType });
    });

    const itemMarkup = ({ meal }) => {
        const items = dietPlanItemsText(meal);
        return `
            <article class="cardapio-item">
                <div class="cardapio-item__head">
                    <span class="cardapio-item__icon"><i class="fas ${mealIconClass(meal.meal_type)}"></i></span>
                    <div class="cardapio-item__copy">
                        <strong>${escapeHtml(meal.meal_type)}</strong>
                        <p>${escapeHtml(items)}</p>
                        <div class="cardapio-item__macros"><span>${Math.round(Number(meal.calories) || 0)} kcal</span><span>${Math.round(Number(meal.protein) || 0)}g prot.</span><span>${Math.round(Number(meal.carbs) || 0)}g carb.</span><span>${Math.round(Number(meal.fat) || 0)}g gord.</span></div>
                    </div>
                    <span class="cardapio-item__status" aria-hidden="true"><i class="far fa-circle"></i></span>
                </div>
                <div class="cardapio-item__actions">
                    <button type="button" class="btn-quick" onclick="quickLogPlanMeal(${meal.id}, 'exact')"><i class="fas fa-check"></i> Comi exatamente</button>
                    <button type="button" class="btn-quick btn-quick--soft" onclick="quickLogPlanMeal(${meal.id}, 'describe')"><i class="fas fa-pen"></i> Descrevi diferente</button>
                    <button type="button" class="entry-action" onclick="openEditPlanMealModal(${meal.id})" aria-label="Editar refeição do plano"><i class="fas fa-pen-to-square"></i></button>
                </div>
            </article>`;
    };

    const pendingMarkup = pendingMeals.map(itemMarkup).join('');
    const bodyInner = doneMeals.length
        ? `<div class="cardapio-progress"><i class="fas fa-check-circle"></i> ${doneMeals.length} de ${dayMeals.length} refeições de hoje registradas</div>`
        : '';

    bodyEl.innerHTML = `
        ${bodyInner}\n
        ${pendingMeals.length
            ? `<div class="cardapio-list">${pendingMarkup}</div>`
            : dayMeals.length
                ? `<div class="empty-state empty-state--compact empty-state--all-done"><span><i class="fas fa-circle-check"></i></span><div><strong>Cardápio de hoje concluído</strong><p>Todas as refeições foram registradas.</p></div></div>`
                : `<div class="empty-state empty-state--compact"><span><i class="fas fa-utensils"></i></span><div><strong>Este dia está vazio</strong><p>Escolha outro dia da rotação.</p></div></div>`}
        <div class="cardapio-footer">
            <button type="button" class="btn-secondary" onclick="openSuggestDietModal()"><i class="fas fa-wand-magic-sparkles"></i> Sugerir mudanças</button>
            <button type="button" class="btn-add" onclick="showAddDietModal()"><i class="fas fa-plus"></i> Adicionar refeição</button>
        </div>`;
}

function setCardapioDay(day) {
    if (![1, 2, 3].includes(Number(day))) return;
    setStoredCardapioDay(Number(day));
    cardapioDay = Number(day);
    renderTodayCardapio(cardapioActivePlan, null);
}

function findPlanMeal(mealId) {
    if (!cardapioActivePlan) return null;
    return (cardapioActivePlan.meals || []).find(meal => Number(meal.id) === Number(mealId)) || null;
}

async function quickLogPlanMeal(mealId, mode) {
    const meal = findPlanMeal(mealId);
    if (!meal) {
        showToast("Refeição não encontrada.", "error");
        return;
    }
    const entryType = cardapioMealTypeToEntry(meal.meal_type);
    if (mode === "describe") {
        showAddDietModal();
        getElement("dietMeal").value = entryType;
        const items = dietPlanItemsText(meal);
        getElement("dietDescription").value = items;
        syncChoiceCards();
        return;
    }
    try {
        const response = await fetch(`${API_BASE}/diet`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({
                date: localDateInputValue(),
                meal_type: entryType,
                description: dietPlanItemsText(meal),
                calories: meal.calories,
                protein: meal.protein,
                carbs: meal.carbs,
                fat: meal.fat,
                notes: meal.notes
            })
        });
        if (response.ok) {
            showToast("Refeição registrada!", "success");
            loadDietEntries({ showLoading: false });
            loadTodayCardapio();
        } else {
            const errorData = await response.json();
            showToast(errorData.error || "Erro ao registrar!", "error");
        }
    } catch (error) {
        showToast("Erro de conexão!", "error");
    }
}

async function openEditPlanMealModal(mealId) {
    const meal = findPlanMeal(mealId);
    if (!meal) return;
    getElement("editPlanMealId").value = meal.id;
    getElement("editPlanMealDescription").value = dietPlanItemsText(meal);
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
            const data = await response.json();
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
                <div><strong>Nenhuma medição encontrada</strong><p>Adicione uma medição para iniciar seu histórico.</p></div>
                <button type="button" class="btn-primary" onclick="showAddMeasurementModal()">Adicionar medição</button>
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
        container.insertAdjacentHTML('beforeend', `<div class="profile-load-more"><button type="button" onclick="loadMeasurements()">Carregar mais</button></div>`);
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
            closeAppModal(getElement("profileModal"));
            showToast("Perfil salvo com sucesso!", "success");
            if (pendingPostProfileResume) {
                const resume = pendingPostProfileResume;
                pendingPostProfileResume = null;
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
    getElement("dietCalories").value = entry.calories || "";
    getElement("dietProtein").value = entry.protein || "";
    getElement("dietCarbs").value = entry.carbs || "";
    getElement("dietFat").value = entry.fat || "";

    getElement("dietModalTitle").textContent = "Editar Registro de Dieta";
    syncDietDateChips();
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
            loadDietEntries({ showLoading: false });
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
    if (!confirm("Tem certeza que deseja excluir esta medição?")) return;
    showToast("Excluindo...", "info");
    try {
        const response = await fetch(`/api/measurements/${id}`, { method: "DELETE", credentials: 'include' });
        if (response.ok) {
            showToast("Medição excluída!", "success");
            measurements = [];
            measurementHasMore = false;
            loadMeasurements();
            loadMeasurementSummary();
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
    const startDate = getElement("measurementStartDate");
    const endDate = getElement("measurementEndDate");
    
    if (startDate) startDate.value = "";
    if (endDate) endDate.value = "";
    measurements = [];
    measurementHasMore = false;
    loadMeasurements();
}

function clearChat() {
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
