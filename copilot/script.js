// script.js

// Global variables
let currentUser = null;
let currentTab = 'diet';
let dietEntries = [];
let measurements = [];
let dietPlans = []; // NOVO: Para armazenar planos de dieta
let workoutPlans = []; // NOVO: Para armazenar planos de treino

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
    let toast = document.createElement("div");
    toast.className = "toast " + tipo;
    toast.innerText = msg;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// Mensagem para login/registro/perfil
function showAuthMessage(message, type = 'info') {
    const messageEl = getElement("authMessage");
    if (!messageEl) return;
    messageEl.textContent = message;
    messageEl.className = `message ${type}`;
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
    setTimeout(() => { el.textContent = ""; }, 4000);
}

// Loading global
function showGlobalLoading(msg="Carregando...") {
    let loading = document.getElementById("globalLoading");
    if (!loading) {
        loading = document.createElement("div");
        loading.id = "globalLoading";
        loading.className = "toast info";
        loading.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${msg}`;
        document.body.appendChild(loading);
    }
}
function hideGlobalLoading() {
    let loading = document.getElementById("globalLoading");
    if (loading) loading.remove();
}

// Adiciona listeners ao carregar a página
document.addEventListener('DOMContentLoaded', function() {
    setDefaultDates();
    initializeAudioFeatures();
    checkAuthStatus();

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

        const awesomplete = new Awesomplete(dietDescription, {
            minChars: 2,
            maxItems: 10,
            autoFirst: true
        });

        dietDescription.addEventListener("input", function() {
            const query = dietDescription.value.trim().toLowerCase();
            if (query.length < 2) return;
            awesomplete.list = alimentosList.filter(desc =>
                desc.toLowerCase().includes(query)
            );
        });

        dietDescription.addEventListener("awesomplete-selectcomplete", function(evt) {
            const selected = alimentosData.find(item => item.descricao === dietDescription.value);
            if (selected) {
                getElement("dietCalories").value = selected.calorias ?? "";
                getElement("dietProtein").value = selected.proteina ?? "";
                getElement("dietCarbs").value = selected.carboidrato ?? "";
                getElement("dietFat").value = selected.gordura ?? "";
                // A função updatePrecisionBadge não está definida no seu código,
                // mas se você a tiver em outro lugar, ela pode ser chamada aqui.
                // updatePrecisionBadge("manual"); 
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

    // Auth forms
    addEventListenerSafe("loginForm", "submit", handleLogin);
    addEventListenerSafe("registerForm", "submit", handleRegister);
    addEventListenerSafe("profileForm", "submit", handleProfileSubmit);

    // Chat functionality
    // O botão de enviar do chat não tem ID no HTML, vamos usar o onclick no HTML
    // ou dar um ID a ele (ex: sendChatBtn) e usar addEventListenerSafe("sendChatBtn", "click", sendChatMessage);
    // Por enquanto, o onclick no HTML é suficiente.

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

    // Botões rápidos do chat (NOVO)
    addEventListenerSafe("quickDietBtn", "click", function() {
        sendChatMessageWithProfile("Gere um plano de dieta personalizado para mim, considerando meu perfil.");
    });
    addEventListenerSafe("quickWorkoutBtn", "click", function() {
        sendChatMessageWithProfile("Gere um plano de treino personalizado para mim, considerando meu perfil.");
    });

    // Modal close events
    setupModalEvents();
    
    // NOVO: Adiciona eventos para os novos modais de visualização de planos
    setupPlanViewModals();

    addEventListenerSafe("generateMacrosBtn", "click", async function() {
        const btnText = getElement("generateMacrosBtnText");
        const btnLoading = getElement("generateMacrosLoading");
        if (btnText) btnText.classList.add("hidden");
        if (btnLoading) btnLoading.classList.remove("hidden");
        const description = getElement("dietDescription")?.value.trim();
        if (!description) {
            showDietMessage("Descreva os alimentos antes de gerar macros.", "error");
            if (btnText) btnText.classList.remove("hidden");
            if (btnLoading) btnLoading.classList.add("hidden");
            return;
        }
        try {
            const response = await fetch(`${API_BASE}/diet/ai_macros`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({ description })
            });
            const data = await response.json();
            if (response.ok) {
                getElement("dietCalories").value = data.calories || 0;
                getElement("dietProtein").value = data.protein || 0;
                getElement("dietCarbs").value = data.carbs || 0;
                getElement("dietFat").value = data.fat || 0;
                // Badge de precisão (se a função updatePrecisionBadge existir)
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
        meal_type: document.getElementById("dietMealType").value,
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
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            showToast("Dieta salva com sucesso!", "success");
            closeDietModal();
            loadDietEntries();
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
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            closeMeasurementModal();
            loadMeasurements();
            showToast(isEdit ? "Medidas atualizadas!" : "Medidas adicionadas!", "success");
            // Atualiza o peso e altura do perfil com os últimos valores registrados
            await fetch(`${API_BASE}/profile`, {
                method: "POST", // Ou PUT, dependendo da sua API
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({ 
                    weight: payload.weight,
                    height: payload.height
                })
            });
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

// NOVO: Configura eventos para os modais de visualização de planos
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
    const today = new Date().toISOString().split('T')[0];
    const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    
    const dateFields = [
        { id: 'dietStartDate', value: weekAgo },
        { id: 'dietEndDate', value: today },
        { id: 'measurementStartDate', value: weekAgo },
        { id: 'measurementEndDate', value: today },
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
                currentUser = data.user;
                showMainScreen();
            } else {
                showLoginScreen();
            }
        } else {
            showLoginScreen();
        }
    } catch (error) {
        console.error('Auth check failed:', error);
        showLoginScreen();
    }
}

// Screen management
function showLoginScreen() {
    const loginScreen = getElement('loginScreen');
    const mainScreen = getElement('mainScreen');
    
    if (loginScreen) loginScreen.classList.remove('hidden');
    if (mainScreen) mainScreen.classList.add('hidden');
    
    clearForms();
}

function showMainScreen() {
    const loginScreen = getElement('loginScreen');
    const mainScreen = getElement('mainScreen');
    
    if (loginScreen) loginScreen.classList.add('hidden');
    if (mainScreen) mainScreen.classList.remove('hidden');
    
    if (currentUser) {
        const welcomeUser = getElement('welcomeUser');
        if (welcomeUser) {
            welcomeUser.textContent = `Bem-vindo, ${currentUser.username}!`;
        }
        // Mostra o botão admin se for admin
        const adminBtn = getElement('adminPanelBtn');
        if (adminBtn) {
            if (currentUser && currentUser.is_admin) {
                adminBtn.classList.remove('hidden');
            } else {
                adminBtn.classList.add('hidden');
            }
        }
    }
    
    // NOVO: Define a visibilidade inicial da aba de chat
    const chatNavBtn = document.querySelector(`[onclick="showTab('chat')"]`);
    if (chatNavBtn) {
        if (currentUser && currentUser.is_admin) {
            chatNavBtn.style.display = ''; // Mostra
        } else {
            chatNavBtn.style.display = 'none'; // Oculta
        }
    }

    showTab('diet'); // Sempre começa na aba de dieta
    checkUserProfile();
}

/**
 * Mostra mensagens de feedback
 * @param {string} message - Mensagem a ser exibida
 * @param {string} type - Tipo da mensagem (success, error, info)
 */
// Chat functions
let chatHistory = [];
let isRecording = false;
let recognition = null;
let lastAIResponse = '';

/**
 * Envia mensagem no chat
 */
async function sendChatMessage() {
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
            // NOVO: Se a resposta da IA indica que um plano foi salvo, recarregue as listas
            if (data.response.includes("plano de dieta") && data.response.includes("salvo")) {
                loadDietPlans();
            }
            if (data.response.includes("plano de treino") && data.response.includes("salvo")) {
                loadWorkoutPlans();
            }
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
async function sendChatMessageWithProfile(message) {
    const chatMessages = getElement("chatMessages");
    if (!chatMessages) return;
    addMessageToChat(message, "user");
    showTypingIndicator();
    
    try {
        const response = await fetch(`${API_BASE}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ message })
        });
        const data = await response.json();
        hideTypingIndicator();
        if (response.ok && data.response) {
            addMessageToChat(data.response, "bot");
            lastAIResponse = data.response;
            // NOVO: Se a resposta da IA indica que um plano foi salvo, recarregue as listas
            if (data.response.includes("plano de dieta") && data.response.includes("salvo")) {
                loadDietPlans();
            }
            if (data.response.includes("plano de treino") && data.response.includes("salvo")) {
                loadWorkoutPlans();
            }
        } else {
            const errorData = await response.json();
            addMessageToChat(errorData.error || "Erro ao obter resposta da IA.", "bot");
        }
    } catch (e) {
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
        <div class="message-content">${message}</div>
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
        button.classList.add('recording');
    } else {
        button.innerHTML = '🎤';
        button.title = 'Falar com a IA';
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
        };
        
        utterance.onend = () => {
            speakButton.innerHTML = '🔊';
            speakButton.title = 'Ouvir última resposta';
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
            showMainScreen();
            showAuthMessage(data.message, "success");
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

    if (password.length < 6) {
        showAuthMessage("A senha deve ter pelo menos 6 caracteres", "error");
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
            showMainScreen();
            showAuthMessage(data.message, "success");
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
        showLoginScreen();
        showAuthMessage("Logout realizado com sucesso", "success");
    } catch (error) {
        console.error("Logout error:", error);
        currentUser = null;
        showLoginScreen();
    }
}

// Interface functions
// Interface functions
function showTab(tabName) {
    // Remove active class from all nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.add('hidden');
    });
    
    // Lógica para controlar a visibilidade da aba de chat
    const chatNavBtn = document.querySelector(`[onclick="showTab('chat')"]`);
    if (chatNavBtn) {
        if (currentUser && currentUser.is_admin) {
            chatNavBtn.style.display = ''; // Mostra o botão da aba
        } else {
            chatNavBtn.style.display = 'none'; // Oculta o botão da aba
            if (tabName === 'chat') {
                showTab('diet'); // Redireciona para aba padrão se não for admin
                return;
            }
        }
    }

    // Show selected tab
    const selectedTab = document.getElementById(`${tabName}Tab`);
    if (selectedTab) {
        selectedTab.classList.remove('hidden');
    }
    
    // Add active class to clicked button
    const activeBtn = document.querySelector(`[onclick="showTab('${tabName}')"]`);
    if (activeBtn) {
        activeBtn.classList.add('active');
    }
    
    currentTab = tabName;
    
    // Carrega os dados corretos para cada aba
    if (tabName === 'diet') {
        loadDietEntries();
    } else if (tabName === 'measurements') {
        loadMeasurements();
    } else if (tabName === 'stats') {
        loadStats();
    } else if (tabName === 'diet_plans') { // Carrega planos de dieta
        loadDietPlans();
    } else if (tabName === 'workout_plans') { // Carrega planos de treino
        loadWorkoutPlans();
    }
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
function showAddDietModal() {
    const modal = getElement("dietModal");
    const title = getElement("dietModalTitle");
    const form = getElement("dietForm");
    
    if (modal) modal.style.display = "block";
    if (title) title.textContent = "Adicionar Registro de Dieta";
    if (form) form.reset();
    
    // Set today's date
    const dietDate = getElement("dietDate");
    if (dietDate) {
        dietDate.value = new Date().toISOString().split('T')[0];
    }
}

function closeDietModal() {
    const modal = getElement("dietModal");
    if (modal) modal.style.display = "none";
    clearForms();
}

function showAddMeasurementModal() {
    const modal = getElement("measurementModal");
    const title = getElement("measurementModalTitle");
    const form = getElement("measurementForm");
    
    if (modal) modal.style.display = "block";
    if (title) title.textContent = "Adicionar Medidas";
    if (form) form.reset();
    
    // Set today's date
    const measurementDate = getElement("measurementDate");
    if (measurementDate) {
        measurementDate.value = new Date().toISOString().split('T')[0];
    }
}

function closeMeasurementModal() {
    const modal = getElement("measurementModal");
    if (modal) modal.style.display = "none";
    clearForms();
}

function closeProfileModal() {
    const modal = getElement("profileModal");
    if (modal) modal.style.display = "none";
}

function skipProfile() {
    closeProfileModal();
}

// NOVO: Funções para modais de visualização de planos
function closeViewDietPlanModal() {
    const modal = getElement("viewDietPlanModal");
    if (modal) modal.style.display = "none";
}

function closeViewWorkoutPlanModal() {
    const modal = getElement("viewWorkoutPlanModal");
    if (modal) modal.style.display = "none";
}

// Data functions
async function loadDietEntries() {
    showGlobalLoading();
    const startDate = getElement("dietStartDate")?.value;
    const endDate = getElement("dietEndDate")?.value;
    
    try {
        let url = `${API_BASE}/diet`;
        const params = new URLSearchParams();
        if (startDate) params.append('start_date', startDate);
        if (endDate) params.append('end_date', endDate);
        if (params.toString()) url += '?' + params.toString();
        
        const response = await fetch(url, {
            credentials: 'include'
        });
        
        if (response.ok) {
            dietEntries = await response.json();
            renderDietTable();
        } else {
            console.error('Failed to load diet entries');
        }
    } catch (error) {
        console.error('Error loading diet entries:', error);
    } finally {
        hideGlobalLoading();
    }
}

async function loadMeasurements() {
    showGlobalLoading();
    const startDate = getElement("measurementStartDate")?.value;
    const endDate = getElement("measurementEndDate")?.value;
    
    try {
        let url = `${API_BASE}/measurements`;
        const params = new URLSearchParams();
        if (startDate) params.append('start_date', startDate);
        if (endDate) params.append('end_date', endDate);
        if (params.toString()) url += '?' + params.toString();
        
        const response = await fetch(url, {
            credentials: 'include'
        });
        
        if (response.ok) {
            measurements = await response.json();
            renderMeasurementTable();
        } else {
            console.error('Failed to load measurements');
        }
    } catch (error) {
        console.error('Error loading measurements:', error);
    } finally {
        hideGlobalLoading();
    }
}

async function loadStats() {
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
                        <strong>Data:</strong> ${formatDate(m.date)}<br>
                        <strong>Peso:</strong> ${m.weight || 'N/A'} kg<br>
                        <strong>% Gordura:</strong> ${m.body_fat || 'N/A'}%
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

async function loadDashboard() {
    try {
        const res = await fetch('/api/admin_dashboard');
        if (!res.ok) throw new Error('Erro ao buscar dashboard');
        const data = await res.json();

        const dashboardStats = getElement('dashboardStats');
        if (dashboardStats) {
            dashboardStats.innerHTML = `
                <div class="dashboard-grid">
                    <div class="dashboard-card"><h2>${data.total_users}</h2><p>Usuários</p></div>
                    <div class="dashboard-card"><h2>${data.total_admins}</h2><p>Admins</p></div>
                    <div class="dashboard-card"><h2>${data.total_banned}</h2><p>Banidos</p></div>
                    <div class="dashboard-card"><h2>${data.total_diet_entries}</h2><p>Dietas</p></div>
                    <div class="dashboard-card"><h2>${data.total_measurements}</h2><p>Medidas</p></div>
                    <div class="dashboard-card"><h2>${data.total_chat_messages}</h2><p>Mensagens Chat</p></div>
                </div>
            `;
        }
    } catch (error) {
        console.error('Erro ao carregar dashboard:', error);
        const dashboardStats = getElement('dashboardStats');
        if (dashboardStats) {
            dashboardStats.innerHTML = '<p class="text-danger">Erro ao carregar estatísticas do dashboard</p>';
        }
    }
}

async function loadRecentActivity() {
    try {
        const res = await fetch('/api/admin/recent_activity');
        if (!res.ok) throw new Error('Erro ao buscar atividades');
        const activities = await res.json();

        const activityDiv = getElement('recentActivity');
        if (!activityDiv) return;

        if (activities.length === 0) {
            activityDiv.innerHTML = '<p>Nenhuma atividade recente.</p>';
            return;
        }

        activityDiv.innerHTML = activities.map(act => {
            let icon = '';
            let desc = '';
            if (act.type === 'user') {
                icon = '<i class="fas fa-user-plus"></i>';
                desc = `Novo usuário: <strong>${act.username}</strong>`;
            } else if (act.type === 'diet') {
                icon = '<i class="fas fa-utensils"></i>';
                desc = `Nova dieta de <strong>${act.username}</strong>: ${act.description}`;
            } else if (act.type === 'measurement') {
                icon = '<i class="fas fa-ruler"></i>';
                desc = `Nova medição de <strong>${act.username}</strong>`;
            } else if (act.type === 'chat') {
                icon = '<i class="fas fa-comments"></i>';
                desc = `Nova mensagem no chat de <strong>${act.username}</strong>`;
            }
            const date = new Date(act.created_at).toLocaleString('pt-BR');
            return `
                <div style="display: flex; align-items: center; gap: 1rem; padding: 0.5rem 0;">
                    <span style="font-size: 1.5rem;">${icon}</span>
                    <span>${desc}</span>
                    <span style="margin-left:auto; color:#64748b; font-size:0.9rem;">${date}</span>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('Erro ao carregar atividades:', error);
        const activityDiv = document.getElementById('recentActivity');
        if (activityDiv) activityDiv.innerHTML = '<p class="text-danger">Erro ao carregar atividades recentes</p>';
    }
}

// NOVO: Funções para carregar e renderizar Planos de Dieta
async function loadDietPlans() {
    showGlobalLoading("Carregando planos de dieta...");
    try {
        const response = await fetch(`${API_BASE}/diet_plans`, {
            credentials: 'include'
        });
        if (response.ok) {
            dietPlans = await response.json();
            renderDietPlansTable();
        } else {
            console.error('Failed to load diet plans');
            showToast("Erro ao carregar planos de dieta.", "error");
        }
    } catch (error) {
        console.error('Error loading diet plans:', error);
        showToast("Erro de conexão ao carregar planos de dieta.", "error");
    } finally {
        hideGlobalLoading();
    }
}

function renderDietPlansTable() {
    const tbody = getElement("dietPlansTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (dietPlans.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4">Nenhum plano de dieta encontrado. Peça um para a IA!</td></tr>';
        return;
    }

    dietPlans.forEach(plan => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${plan.title}</td>
            <td>${plan.description || '-'}
            <td>${formatDateTime(plan.created_at)}</td>
            <td>
                <button onclick="viewDietPlan(${plan.id})" class="btn-edit">
                    <i class="fas fa-eye"></i> Ver
                </button>
                <button onclick="deleteDietPlan(${plan.id})" class="btn-delete">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

async function viewDietPlan(id) {
    showGlobalLoading("Carregando detalhes do plano de dieta...");
    try {
        const response = await fetch(`${API_BASE}/diet_plans/${id}`, {
            credentials: 'include'
        });
        if (response.ok) {
            const plan = await response.json();
            const modal = getElement("viewDietPlanModal");
            const title = getElement("viewDietPlanTitle");
            const detailsDiv = getElement("viewDietPlanDetails");

            if (modal && title && detailsDiv) {
                title.textContent = plan.title;
                let htmlContent = `
                    <p><strong>Descrição:</strong> ${plan.description || 'N/A'}</p>
                    <p><strong>Criado em:</strong> ${formatDateTime(plan.created_at)}</p>
                `;

                if (plan.meals && plan.meals.length > 0) {
                    const mealsByDay = plan.meals.reduce((acc, meal) => {
                        const day = meal.day_of_week || 'Geral';
                        if (!acc[day]) acc[day] = [];
                        acc[day].push(meal);
                        return acc;
                    }, {});

                    for (const day in mealsByDay) {
                        htmlContent += `<div class="plan-details-section"><h4>${day}</h4><ul>`;
                        mealsByDay[day].sort((a, b) => (a.order || 0) - (b.order || 0)).forEach(meal => {
                            htmlContent += `
                                <li>
                                    <strong>${meal.meal_type}:</strong> ${meal.description}
                                    <br>
                                    (Cal: ${meal.calories || 0} | Prot: ${meal.protein || 0}g | Carb: ${meal.carbs || 0}g | Gord: ${meal.fat || 0}g)
                                    ${meal.notes ? `<br><em>Obs: ${meal.notes}</em>` : ''}
                                </li>
                            `;
                        });
                        htmlContent += `</ul></div>`;
                    }
                } else {
                    htmlContent += '<p>Nenhuma refeição detalhada para este plano.</p>';
                }
                detailsDiv.innerHTML = htmlContent;
                modal.style.display = "flex"; // Usa flex para centralizar
            }
        } else {
            console.error('Failed to load diet plan details');
            showToast("Erro ao carregar detalhes do plano de dieta.", "error");
        }
    } catch (error) {
        console.error('Error viewing diet plan:', error);
        showToast("Erro de conexão ao ver plano de dieta.", "error");
    } finally {
        hideGlobalLoading();
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

// NOVO: Funções para carregar e renderizar Planos de Treino
async function loadWorkoutPlans() {
    showGlobalLoading("Carregando planos de treino...");
    try {
        const response = await fetch(`${API_BASE}/workout_plans`, {
            credentials: 'include'
        });
        if (response.ok) {
            workoutPlans = await response.json();
            renderWorkoutPlansTable();
        } else {
            console.error('Failed to load workout plans');
            showToast("Erro ao carregar planos de treino.", "error");
        }
    } catch (error) {
        console.error('Error loading workout plans:', error);
        showToast("Erro de conexão ao carregar planos de treino.", "error");
    } finally {
        hideGlobalLoading();
    }
}

function renderWorkoutPlansTable() {
    const tbody = getElement("workoutPlansTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (workoutPlans.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4">Nenhum plano de treino encontrado. Peça um para a IA!</td></tr>';
        return;
    }

    workoutPlans.forEach(plan => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${plan.title}</td>
            <td>${plan.description || '-'}
            <td>${formatDateTime(plan.created_at)}</td>
            <td>
                <button onclick="viewWorkoutPlan(${plan.id})" class="btn-edit">
                    <i class="fas fa-eye"></i> Ver
                </button>
                <button onclick="deleteWorkoutPlan(${plan.id})" class="btn-delete">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

async function viewWorkoutPlan(id) {
    showGlobalLoading("Carregando detalhes do plano de treino...");
    try {
        const response = await fetch(`${API_BASE}/workout_plans/${id}`, {
            credentials: 'include'
        });
        if (response.ok) {
            const plan = await response.json();
            const modal = getElement("viewWorkoutPlanModal");
            const title = getElement("viewWorkoutPlanTitle");
            const detailsDiv = getElement("viewWorkoutPlanDetails");

            if (modal && title && detailsDiv) {
                title.textContent = plan.title;
                let htmlContent = `
                    <p><strong>Descrição:</strong> ${plan.description || 'N/A'}</p>
                    <p><strong>Criado em:</strong> ${formatDateTime(plan.created_at)}</p>
                `;

                if (plan.exercises && plan.exercises.length > 0) {
                    htmlContent += `<div class="plan-details-section"><h4>Exercícios</h4><ul>`;
                    plan.exercises.sort((a, b) => (a.order || 0) - (b.order || 0)).forEach(exercise => {
                        htmlContent += `
                            <li>
                                <strong>${exercise.name}:</strong> ${exercise.sets || 'N/A'} séries de ${exercise.reps || 'N/A'} repetições
                                ${exercise.weight ? ` (${exercise.weight})` : ''}
                                ${exercise.notes ? `<br><em>Obs: ${exercise.notes}</em>` : ''}
                            </li>
                        `;
                    });
                    htmlContent += `</ul></div>`;
                } else {
                    htmlContent += '<p>Nenhum exercício detalhado para este plano.</p>';
                }
                detailsDiv.innerHTML = htmlContent;
                modal.style.display = "flex"; // Usa flex para centralizar
            }
        } else {
            console.error('Failed to load workout plan details');
            showToast("Erro ao carregar detalhes do plano de treino.", "error");
        }
    } catch (error) {
        console.error('Error viewing workout plan:', error);
        showToast("Erro de conexão ao ver plano de treino.", "error");
    } finally {
        hideGlobalLoading();
    }
}

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
function renderDietTable() {
    const tbody = getElement("dietTableBody");
    if (!tbody) return;
    
    tbody.innerHTML = "";
    
    dietEntries.forEach(entry => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${formatDate(entry.date)}</td>
            <td>${getMealTypeLabel(entry.meal_type)}</td>
            <td>${entry.description}</td>
            <td>
              <span class="${entry.precision === 'alta' ? 'precision-high' : entry.precision === 'manual' ? 'precision-high' : entry.precision === 'moderada' ? 'precision-moderate' : 'precision-low'}">
                ${entry.calories || 0}
              </span>
            </td>
            <td>${entry.protein || 0}g</td>
            <td>${entry.carbs || 0}g</td>
            <td>${entry.fat || 0}g</td>
            <td>
                <button onclick="editDietEntry(${entry.id})" class="btn-edit">
                    <i class="fas fa-edit"></i>
                </button>
                <button onclick="deleteDietEntry(${entry.id})" class="btn-delete">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function renderMeasurementTable() {
    const tbody = getElement("measurementTableBody");
    if (!tbody) return;
    
    tbody.innerHTML = "";
    
    measurements.forEach(measurement => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${formatDate(measurement.date)}</td>
            <td>${measurement.weight || '-'}
            <td>${measurement.height || '-'}
            <td>${measurement.body_fat || '-'}
            <td>${measurement.muscle_mass || '-'}
            <td>${measurement.waist || '-'}
            <td>${measurement.chest || '-'}
            <td>${measurement.arm || '-'}
            <td>${measurement.thigh || '-'}
            <td>${measurement.notes || '-'}
            <td>
                <button onclick="editMeasurement(${measurement.id})" class="btn-edit">
                    <i class="fas fa-edit"></i>
                </button>
                <button onclick="deleteMeasurement(${measurement.id})" class="btn-delete">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
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
            closeProfileModal();
            showToast("Perfil salvo com sucesso!", "success");
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
    getElement("dietMealType").value = entry.meal_type;
    getElement("dietDescription").value = entry.description;
    getElement("dietNotes").value = entry.notes || "";
    
    // Preenche os campos de macros se existirem
    getElement("dietCalories").value = entry.calories || "";
    getElement("dietProtein").value = entry.protein || "";
    getElement("dietCarbs").value = entry.carbs || "";
    getElement("dietFat").value = entry.fat || "";

    getElement("dietModalTitle").textContent = "Editar Registro de Dieta";
    getElement("dietModal").style.display = "block";
}

async function deleteDietEntry(id) {
    if (!confirm("Tem certeza que deseja excluir esta refeição?")) return;
    showToast("Excluindo...", "info");
    try {
        const response = await fetch(`/api/diet/${id}`, { method: "DELETE", credentials: 'include' });
        if (response.ok) {
            showToast("Refeição excluída!", "success");
            loadDietEntries();
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
    getElement("measurementModal").style.display = "block";
}

async function deleteMeasurement(id) {
    if (!confirm("Tem certeza que deseja excluir esta medição?")) return;
    showToast("Excluindo...", "info");
    try {
        const response = await fetch(`/api/measurements/${id}`, { method: "DELETE", credentials: 'include' });
        if (response.ok) {
            showToast("Medição excluída!", "success");
            loadMeasurements();
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
    
    if (startDate) startDate.value = "";
    if (endDate) endDate.value = "";
    
    loadDietEntries();
}
function clearMeasurementFilters() {
    const startDate = getElement("measurementStartDate");
    const endDate = getElement("measurementEndDate");
    
    if (startDate) startDate.value = "";
    if (endDate) endDate.value = "";
    
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
                <p>Olá! 👋 Sou seu assistente fitness pessoal. Como admin, posso gerar planos de dieta e treino. Como posso ajudá-lo hoje?</p>
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
                // Mostrar modal de perfil se não existir
                setTimeout(() => {
                    const profileModal = getElement("profileModal");
                    if (profileModal) {
                        profileModal.style.display = "block";
                    }
                }, 1000);
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
