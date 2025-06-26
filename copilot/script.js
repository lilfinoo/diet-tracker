// Global variables
let currentUser = null;
let currentTab = 'diet';
let dietEntries = [];
let measurements = [];

// API Base URL
const API_BASE = '/api';

/**
 * Função utilitária para buscar elementos DOM com verificação de existência
 * @param {string} id - ID do elemento
 * @returns {HTMLElement|null} - Elemento encontrado ou null
 */
function getElement(id) {
    const element = document.getElementById(id);
    if (!element) {
        console.warn(`Elemento com ID '${id}' não encontrado`);
    }
    return element;
}

/**
 * Função utilitária para adicionar event listeners com verificação
 * @param {string} id - ID do elemento
 * @param {string} event - Tipo do evento
 * @param {function} handler - Função handler
 */
function addEventListenerSafe(id, event, handler) {
    const element = getElement(id);
    if (element) {
        element.addEventListener(event, handler);
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    checkAuthStatus();
    setupEventListeners();
    setDefaultDates();
    initializeAudioFeatures();
});

// Setup event listeners - CORRIGIDO para evitar erros de elementos null
function setupEventListeners() {
    // Auth forms
    addEventListenerSafe("loginForm", "submit", handleLogin);
    addEventListenerSafe("registerForm", "submit", handleRegister);
    
    // Diet form
    addEventListenerSafe("dietForm", "submit", handleDietSubmit);
    
    // Measurement form
    addEventListenerSafe("measurementForm", "submit", handleMeasurementSubmit);
    
    // Profile form
    addEventListenerSafe("profileForm", "submit", handleProfileSubmit);
    
    // Chat functionality
    addEventListenerSafe("chatForm", "submit", handleChatSubmit);
    addEventListenerSafe("sendButton", "click", sendChatMessage);
    
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

    // Modal close events - CORRIGIDO
    setupModalEvents();
}

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

// Set default dates - MELHORADO
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

// Authentication functions - MANTIDO mas com melhorias de error handling
async function checkAuthStatus() {
    try {
        const response = await fetch(`${API_BASE}/profile`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const user = await response.json();
            currentUser = user;
            showMainScreen();
        } else {
            showLoginScreen();
        }
    } catch (error) {
        console.error('Auth check failed:', error);
        showLoginScreen();
    }
}

// Screen management - MELHORADO com verificações
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
    }
    
    showTab('diet');
    checkUserProfile();
}

/**
 * Mostra mensagens de feedback - MELHORADO
 * @param {string} message - Mensagem a ser exibida
 * @param {string} type - Tipo da mensagem (success, error, info)
 */
function showMessage(message, type = 'info') {
    const messageEl = getElement("authMessage");
    if (!messageEl) return;

    messageEl.textContent = message;
    messageEl.className = `message ${type}`;
    messageEl.style.display = "block";
    
    // Auto-hide após 5 segundos
    setTimeout(() => {
        messageEl.textContent = "";
        messageEl.className = "message";
        messageEl.style.display = "none";
    }, 5000);
}

// Chat functions - CORRIGIDO e OTIMIZADO
let chatHistory = [];
let isRecording = false;
let recognition = null;
let lastAIResponse = '';

/**
 * Envia mensagem no chat - FUNÇÃO PRINCIPAL CORRIGIDA
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
        } else {
            hideTypingIndicator();
            addMessageToChat("Desculpe, ocorreu um erro. Tente novamente.", "bot");
        }
    } catch (error) {
        console.error("Chat error:", error);
        hideTypingIndicator();
        addMessageToChat("Erro de conexão. Verifique sua internet.", "bot");
    }
}

/**
 * Adiciona mensagem ao chat - MELHORADO
 */
function addMessageToChat(message, sender) {
    const chatMessages = getElement("chatMessages");
    if (!chatMessages) return;

    const messageDiv = document.createElement("div");
    messageDiv.className = `chat-message ${sender}-message`;
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas ${sender === 'user' ? 'fa-user' : 'fa-robot'}"></i>
        </div>
        <div class="message-content">
            <p>${message}</p>
        </div>
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

// Audio features - INICIALIZAÇÃO SEGURA
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

// Utility functions mantidas
function formatDate(dateString) {
    const date = new Date(dateString + 'T00:00:00');
    return date.toLocaleDateString('pt-BR');
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

// Placeholder functions para manter compatibilidade (implemente conforme necessário)
async function handleLogin(e) { /* implementar */ }
async function handleRegister(e) { /* implementar */ }
async function handleDietSubmit(e) { /* implementar */ }
async function handleMeasurementSubmit(e) { /* implementar */ }
async function handleProfileSubmit(e) { /* implementar */ }
async function handleChatSubmit(e) { 
    e.preventDefault();
    sendChatMessage();
}

function showTab(tabName) { /* implementar navegação entre abas */ }
function showLogin() { /* implementar */ }
function showRegister() { /* implementar */ }
function clearForms() { /* implementar */ }
function closeDietModal() { /* implementar */ }
function closeMeasurementModal() { /* implementar */ }
function closeProfileModal() { /* implementar */ }
function checkUserProfile() { /* implementar */ }

// Carrega vozes quando disponíveis
if ('speechSynthesis' in window) {
    speechSynthesis.onvoiceschanged = function() {
        // Vozes disponíveis
    };
}
