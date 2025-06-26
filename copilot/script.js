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

// Setup event listeners
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
    // Certifique-se de que o elemento 'sendButton' existe no seu HTML
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

    // Modal close events
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
    }
    
    showTab('diet');
    checkUserProfile();
}

/**
 * Mostra mensagens de feedback
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
 * Adiciona mensagem ao chat
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

// Authentication functions
async function handleLogin(e) {
    e.preventDefault();
    const username = getElement("loginUsername").value.trim();
    const password = getElement("loginPassword").value.trim();

    if (!username || !password) {
        showMessage("Preencha todos os campos", "error");
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
            showMessage(data.message, "success");
        } else {
            showMessage(data.error, "error");
        }
    } catch (error) {
        console.error("Login error:", error);
        showMessage("Erro de conexão. Tente novamente.", "error");
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const username = getElement("registerUsername").value.trim();
    const password = getElement("registerPassword").value.trim();
    const confirmPassword = getElement("confirmPassword").value.trim();

    if (!username || !password || !confirmPassword) {
        showMessage("Preencha todos os campos", "error");
        return;
    }

    if (password !== confirmPassword) {
        showMessage("As senhas não coincidem", "error");
        return;
    }

    if (password.length < 6) {
        showMessage("A senha deve ter pelo menos 6 caracteres", "error");
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
            showMessage(data.message, "success");
        } else {
            showMessage(data.error, "error");
        }
    } catch (error) {
        console.error("Register error:", error);
        showMessage("Erro de conexão. Tente novamente.", "error");
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
        showMessage("Logout realizado com sucesso", "success");
    } catch (error) {
        console.error("Logout error:", error);
        currentUser = null;
        showLoginScreen();
    }
}

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
    
    // Show selected tab
    const selectedTab = getElement(`${tabName}Tab`);
    if (selectedTab) {
        selectedTab.classList.remove('hidden');
    }
    
    // Add active class to clicked button
    const activeBtn = document.querySelector(`[onclick="showTab('${tabName}')"]`);
    if (activeBtn) {
        activeBtn.classList.add('active');
    }
    
    currentTab = tabName;
    
    // Load data for specific tabs
    if (tabName === 'diet') {
        loadDietEntries();
    } else if (tabName === 'measurements') {
        loadMeasurements();
    } else if (tabName === 'stats') {
        loadStats();
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

// Data functions
async function loadDietEntries() {
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
    }
}

async function loadMeasurements() {
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
            <td>${entry.calories || 0}</td>
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
            <td>${measurement.weight || '-'}</td>
            <td>${measurement.height || '-'}</td>
            <td>${measurement.body_fat || '-'}</td>
            <td>${measurement.muscle_mass || '-'}</td>
            <td>${measurement.waist || '-'}</td>
            <td>${measurement.chest || '-'}</td>
            <td>${measurement.arm || '-'}</td>
            <td>${measurement.thigh || '-'}</td>
            <td>${measurement.notes || '-'}</td>
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

async function handleDietSubmit(e) {
    e.preventDefault();
    
    const id = getElement("dietId")?.value;
    const date = getElement("dietDate")?.value;
    const mealType = getElement("dietMealType")?.value;
    const description = getElement("dietDescription")?.value.trim();
    const notes = getElement("dietNotes")?.value.trim();
    
    if (!date || !mealType || !description) {
        showMessage("Preencha todos os campos obrigatórios", "error");
        return;
    }
    
    try {
        const method = id ? "PUT" : "POST";
        const url = id ? `${API_BASE}/diet/${id}` : `${API_BASE}/diet`;
        
        const response = await fetch(url, {
            method: method,
            headers: {
                "Content-Type": "application/json"
            },
            credentials: "include",
            body: JSON.stringify({
                date: date,
                meal_type: mealType,
                description: description,
                notes: notes
            })
        });
        
        if (response.ok) {
            closeDietModal();
            loadDietEntries();
            showMessage(id ? "Registro atualizado!" : "Registro adicionado!", "success");
        } else {
            const data = await response.json();
            showMessage(data.error || "Erro ao salvar", "error");
        }
    } catch (error) {
        console.error("Diet submit error:", error);
        showMessage("Erro de conexão", "error");
    }
}

async function handleMeasurementSubmit(e) {
    e.preventDefault();
    
    const id = getElement("measurementId")?.value;
    const date = getElement("measurementDate")?.value;
    const weight = getElement("measurementWeight")?.value;
    const height = getElement("measurementHeight")?.value;
    const bodyFat = getElement("measurementBodyFat")?.value;
    const muscleMass = getElement("measurementMuscleMass")?.value;
    const waist = getElement("measurementWaist")?.value;
    const chest = getElement("measurementChest")?.value;
    const arm = getElement("measurementArm")?.value;
    const thigh = getElement("measurementThigh")?.value;
    const notes = getElement("measurementNotes")?.value.trim();
    
    if (!date) {
        showMessage("Data é obrigatória", "error");
        return;
    }
    
    try {
        const method = id ? "PUT" : "POST";
        const url = id ? `${API_BASE}/measurements/${id}` : `${API_BASE}/measurements`;
        
        const response = await fetch(url, {
            method: method,
            headers: {
                "Content-Type": "application/json"
            },
            credentials: "include",
            body: JSON.stringify({
                date: date,
                weight: weight ? parseFloat(weight) : null,
                height: height ? parseFloat(height) : null,
                body_fat: bodyFat ? parseFloat(bodyFat) : null,
                muscle_mass: muscleMass ? parseFloat(muscleMass) : null,
                waist: waist ? parseFloat(waist) : null,
                chest: chest ? parseFloat(chest) : null,
                arm: arm ? parseFloat(arm) : null,
                thigh: thigh ? parseFloat(thigh) : null,
                notes: notes
            })
        });
        
        if (response.ok) {
            closeMeasurementModal();
            loadMeasurements();
            showMessage(id ? "Medidas atualizadas!" : "Medidas adicionadas!", "success");
        } else {
            const data = await response.json();
            showMessage(data.error || "Erro ao salvar", "error");
        }
    } catch (error) {
        console.error("Measurement submit error:", error);
        showMessage("Erro de conexão", "error");
    }
}

async function handleProfileSubmit(e) {
    e.preventDefault();
    
    const age = getElement("profileAge")?.value;
    const gender = getElement("profileGender")?.value;
    const goal = getElement("profileGoal")?.value;
    const activity = getElement("profileActivity")?.value;
    const restrictions = getElement("profileRestrictions")?.value.trim();
    
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
                dietary_restrictions: restrictions
            })
        });
        
        if (response.ok) {
            closeProfileModal();
            showMessage("Perfil salvo com sucesso!", "success");
        } else {
            const data = await response.json();
            showMessage(data.error || "Erro ao salvar perfil", "error");
        }
    } catch (error) {
        console.error("Profile submit error:", error);
        showMessage("Erro de conexão", "error");
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
    
    getElement("dietModalTitle").textContent = "Editar Registro de Dieta";
    getElement("dietModal").style.display = "block";
}

async function deleteDietEntry(id) {
    if (!confirm("Tem certeza que deseja excluir este registro?")) return;
    
    try {
        const response = await fetch(`${API_BASE}/diet/${id}`, {
            method: "DELETE",
            credentials: "include"
        });
        
        if (response.ok) {
            loadDietEntries();
            showMessage("Registro excluído!", "success");
        } else {
            showMessage("Erro ao excluir", "error");
        }
    } catch (error) {
        console.error("Delete error:", error);
        showMessage("Erro de conexão", "error");
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
    
    try {
        const response = await fetch(`${API_BASE}/measurements/${id}`, {
            method: "DELETE",
            credentials: "include"
        });
        
        if (response.ok) {
            loadMeasurements();
            showMessage("Medição excluída!", "success");
        } else {
            showMessage("Erro ao excluir", "error");
        }
    } catch (error) {
        console.error("Delete error:", error);
        showMessage("Erro de conexão", "error");
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
                <p>Olá! 👋 Sou seu assistente fitness pessoal. Posso ajudar com dicas de nutrição, treino e uso do site. Como posso ajudá-lo hoje?</p>
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

// Carrega vozes quando disponíveis
if ('speechSynthesis' in window) {
    speechSynthesis.onvoiceschanged = function() {
        // Vozes disponíveis
    };
}
