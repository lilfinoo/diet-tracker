// Global variables
let currentUser = null;
let currentTab = 'diet';
let dietEntries = [];
let measurements = [];

// API Base URL
const API_BASE = '/api';

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    checkAuthStatus();
    setupEventListeners();
    setDefaultDates();
});

// Setup event listeners
function setupEventListeners() {
    // Auth forms
    document.getElementById("loginForm").addEventListener("submit", handleLogin);
    document.getElementById("registerForm").addEventListener("submit", handleRegister);
    
    // Diet form
    document.getElementById("dietForm").addEventListener("submit", handleDietSubmit);
    
    // Measurement form
    document.getElementById("measurementForm").addEventListener("submit", handleMeasurementSubmit);
    
    // Chat send button
    document.getElementById("sendButton").addEventListener("click", sendChatMessage);

    // Close modals when clicking outside
    document.getElementById("dietModal").addEventListener("click", function(e) {
        if (e.target === this) closeDietModal();
    });
    document.getElementById("measurementModal").addEventListener("click", function(e) {
        if (e.target === this) closeMeasurementModal();
    });
    document.getElementById("profileModal").addEventListener("click", function(e) {
        if (e.target === this) {
            if (e.target.id === "profileModal") {
                closeProfileModal();
            }
        }
    });
}

// Set default dates
function setDefaultDates() {
    const today = new Date().toISOString().split('T')[0];
    const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    
    document.getElementById('dietStartDate').value = weekAgo;
    document.getElementById('dietEndDate').value = today;
    document.getElementById('measurementStartDate').value = weekAgo;
    document.getElementById('measurementEndDate').value = today;
    
    // Set modal dates to today
    document.getElementById('dietDate').value = today;
    document.getElementById('measurementDate').value = today;
}

// Check authentication status
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

// Authentication functions
function showLogin() {
    document.getElementById('loginForm').classList.remove('hidden');
    document.getElementById('registerForm').classList.add('hidden');
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-btn')[0].classList.add('active');
}

function showRegister() {
    document.getElementById('loginForm').classList.add('hidden');
    document.getElementById('registerForm').classList.remove('hidden');
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-btn')[1].classList.add('active');
}

async function handleLogin(e) {
    e.preventDefault();
    
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    
    try {
        const response = await fetch(`${API_BASE}/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({ username, password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentUser = data.user;
            showMessage('Login realizado com sucesso!', 'success');
            setTimeout(() => showMainScreen(), 1000);
        } else {
            showMessage(data.error || 'Erro no login', 'error');
        }
    } catch (error) {
        console.error('Login error:', error);
        showMessage('Erro de conexão', 'error');
    }
}

async function handleRegister(e) {
    e.preventDefault();
    
    const username = document.getElementById('registerUsername').value;
    const password = document.getElementById('registerPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;
    
    if (password !== confirmPassword) {
        showMessage('As senhas não coincidem', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({ username, password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentUser = data.user;
            showMessage('Conta criada com sucesso!', 'success');
            setTimeout(() => showMainScreen(), 1000);
        } else {
            showMessage(data.error || 'Erro ao criar conta', 'error');
        }
    } catch (error) {
        console.error('Register error:', error);
        showMessage('Erro de conexão', 'error');
    }
}

async function logout() {
    try {
        await fetch(`${API_BASE}/logout`, {
            method: 'POST',
            credentials: 'include'
        });
    } catch (error) {
        console.error('Logout error:', error);
    }
    
    currentUser = null;
    showLoginScreen();
}

// Screen management
function showLoginScreen() {
    document.getElementById('loginScreen').classList.remove('hidden');
    document.getElementById('mainScreen').classList.add('hidden');
    clearForms();
}

function showMainScreen() {
    document.getElementById('loginScreen').classList.add('hidden');
    document.getElementById('mainScreen').classList.remove('hidden');
    
    if (currentUser) {
        document.getElementById('welcomeUser').textContent = `Bem-vindo, ${currentUser.username}!`;
    }
    
    showTab('diet');
}

function showMessage(message, type) {
    const messageEl = document.getElementById("authMessage");
    console.log("Showing message:", message, type); // Adicionado para depuração
    messageEl.textContent = message;
    messageEl.className = `message ${type}`;
    messageEl.style.display = "block"; // Garante que o elemento esteja visível
    
    setTimeout(() => {
        messageEl.textContent = "";
        messageEl.className = "message";
        messageEl.style.display = "none"; // Oculta o elemento após o tempo
    }, 5000);
}

function clearForms() {
    document.getElementById('loginForm').reset();
    document.getElementById('registerForm').reset();
    document.getElementById('authMessage').textContent = '';
    document.getElementById('authMessage').className = 'message';
}

// Tab management
function showTab(tabName) {
    // Update navigation
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelector(`[onclick="showTab('${tabName}')"]`).classList.add('active');
    
    // Update content
    document.querySelectorAll('.tab-content').forEach(content => content.classList.add('hidden'));
    document.getElementById(`${tabName}Tab`).classList.remove('hidden');
    
    currentTab = tabName;
    
    // Load data for the active tab
    if (tabName === 'diet') {
        loadDietEntries();
    } else if (tabName === 'measurements') {
        loadMeasurements();
    } else if (tabName === 'stats') {
        loadStats();
    }
}

// Diet functions
async function loadDietEntries() {
    const startDate = document.getElementById('dietStartDate').value;
    const endDate = document.getElementById('dietEndDate').value;
    
    let url = `${API_BASE}/diet`;
    const params = new URLSearchParams();
    
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    
    if (params.toString()) {
        url += '?' + params.toString();
    }
    
    try {
        const response = await fetch(url, { credentials: 'include' });
        
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

function renderDietTable() {
    const tbody = document.getElementById('dietTableBody');
    
    if (dietEntries.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="empty-state">
                    <i class="fas fa-utensils"></i>
                    <h3>Nenhum registro encontrado</h3>
                    <p>Adicione seu primeiro registro de dieta</p>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = dietEntries.map(entry => `
        <tr>
            <td>${formatDate(entry.date)}</td>
            <td>${getMealTypeLabel(entry.meal_type)}</td>
            <td class="description-cell" title="${entry.description}">${entry.description}</td>
            <td>${entry.calories ? entry.calories + ' kcal' : '-'}</td>
            <td>${entry.protein ? entry.protein + 'g' : '-'}</td>
            <td>${entry.carbs ? entry.carbs + 'g' : '-'}</td>
            <td>${entry.fat ? entry.fat + 'g' : '-'}</td>
            <td class="table-actions">
                <button class="btn-edit" onclick="editDietEntry(${entry.id})">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn-delete" onclick="deleteDietEntry(${entry.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        </tr>
    `).join('');
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

function showAddDietModal() {
    document.getElementById('dietModalTitle').textContent = 'Adicionar Registro de Dieta';
    document.getElementById('dietForm').reset();
    document.getElementById('dietId').value = '';
    document.getElementById('dietDate').value = new Date().toISOString().split('T')[0];
    document.getElementById('dietModal').classList.add('show');
}

function editDietEntry(id) {
    const entry = dietEntries.find(e => e.id === id);
    if (!entry) return;
    
    document.getElementById("dietModalTitle").textContent = "Editar Registro de Dieta";
    document.getElementById("dietId").value = entry.id;
    document.getElementById("dietDate").value = entry.date;
    document.getElementById("dietMealType").value = entry.meal_type;
    document.getElementById("dietDescription").value = entry.description;
    document.getElementById("dietNotes").value = entry.notes || "";
    
    document.getElementById("dietModal").classList.add("show");
}

function closeDietModal() {
    document.getElementById('dietModal').classList.remove('show');
}

async function handleDietSubmit(e) {
    e.preventDefault();
    
    const formData = {
        date: document.getElementById('dietDate').value,
        meal_type: document.getElementById('dietMealType').value,
        description: document.getElementById('dietDescription').value,
        notes: document.getElementById('dietNotes').value
    };
    
    const dietId = document.getElementById('dietId').value;
    const isEdit = dietId !== '';
    
    try {
        const url = isEdit ? `${API_BASE}/diet/${dietId}` : `${API_BASE}/diet`;
        const method = isEdit ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify(formData)
        });
        
        if (response.ok) {
            closeDietModal();
            loadDietEntries();
            showMessage(isEdit ? 'Registro atualizado com sucesso!' : 'Registro adicionado com sucesso!', 'success');
        } else {
            const error = await response.json();
            showMessage(error.error || 'Erro ao salvar registro', 'error');
        }
    } catch (error) {
        console.error('Error saving diet entry:', error);
        showMessage("Erro de conexão", "error");
    }
}

async function deleteDietEntry(id) {
    if (!confirm("Tem certeza que deseja excluir este registro de dieta?")) return;
    
    try {
        const response = await fetch(`${API_BASE}/diet/${id}`, {
            method: "DELETE",
            credentials: "include"
        });
        
        if (response.ok) {
            loadDietEntries();
            showMessage("Registro excluído com sucesso!", "success");
        } else {
            const error = await response.json();
            showMessage(error.error || "Erro ao excluir registro", "error");
        }
    } catch (error) {
        console.error("Error deleting diet entry:", error);
        showMessage("Erro de conexão", "error");
    }
}

function clearDietFilters() {
    document.getElementById('dietStartDate').value = '';
    document.getElementById('dietEndDate').value = '';
    loadDietEntries();
}

// Measurement functions
async function loadMeasurements() {
    const startDate = document.getElementById('measurementStartDate').value;
    const endDate = document.getElementById('measurementEndDate').value;
    
    let url = `${API_BASE}/measurements`;
    const params = new URLSearchParams();
    
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    
    if (params.toString()) {
        url += '?' + params.toString();
    }
    
    try {
        const response = await fetch(url, { credentials: 'include' });
        
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

function renderMeasurementTable() {
    const tbody = document.getElementById('measurementTableBody');
    
    if (measurements.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="11" class="empty-state">
                    <i class="fas fa-weight"></i>
                    <h3>Nenhuma medida encontrada</h3>
                    <p>Adicione suas primeiras medidas</p>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = measurements.map(measurement => `
        <tr>
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
            <td class="table-actions">
                <button class="btn-edit" onclick="editMeasurement(${measurement.id})">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn-delete" onclick="deleteMeasurement(${measurement.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        </tr>
    `).join('');
}

function showAddMeasurementModal() {
    document.getElementById('measurementModalTitle').textContent = 'Adicionar Medidas';
    document.getElementById('measurementForm').reset();
    document.getElementById('measurementId').value = '';
    document.getElementById('measurementDate').value = new Date().toISOString().split('T')[0];
    document.getElementById('measurementModal').classList.add('show');
}

function editMeasurement(id) {
    const measurement = measurements.find(m => m.id === id);
    if (!measurement) return;
    
    document.getElementById('measurementModalTitle').textContent = 'Editar Medidas';
    document.getElementById('measurementId').value = measurement.id;
    document.getElementById('measurementDate').value = measurement.date;
    document.getElementById('measurementWeight').value = measurement.weight || '';
    document.getElementById('measurementHeight').value = measurement.height || '';
    document.getElementById('measurementBodyFat').value = measurement.body_fat || '';
    document.getElementById('measurementMuscleMass').value = measurement.muscle_mass || '';
    document.getElementById('measurementWaist').value = measurement.waist || '';
    document.getElementById('measurementChest').value = measurement.chest || '';
    document.getElementById('measurementArm').value = measurement.arm || '';
    document.getElementById('measurementThigh').value = measurement.thigh || '';
    document.getElementById('measurementNotes').value = measurement.notes || '';
    
    document.getElementById('measurementModal').classList.add('show');
}

function closeMeasurementModal() {
    document.getElementById('measurementModal').classList.remove('show');
}

async function handleMeasurementSubmit(e) {
    e.preventDefault();
    
    const id = document.getElementById('measurementId').value;
    const data = {
        date: document.getElementById('measurementDate').value,
        weight: document.getElementById('measurementWeight').value || null,
        height: document.getElementById('measurementHeight').value || null,
        body_fat: document.getElementById('measurementBodyFat').value || null,
        muscle_mass: document.getElementById('measurementMuscleMass').value || null,
        waist: document.getElementById('measurementWaist').value || null,
        chest: document.getElementById('measurementChest').value || null,
        arm: document.getElementById('measurementArm').value || null,
        thigh: document.getElementById('measurementThigh').value || null,
        notes: document.getElementById('measurementNotes').value || null
    };
    
    try {
        const url = id ? `${API_BASE}/measurements/${id}` : `${API_BASE}/measurements`;
        const method = id ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method,
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            closeMeasurementModal();
            loadMeasurements();
        } else {
            const error = await response.json();
            alert(error.error || 'Erro ao salvar medidas');
        }
    } catch (error) {
        console.error('Error saving measurement:', error);
        alert('Erro de conexão');
    }
}

async function deleteMeasurement(id) {
    if (!confirm('Tem certeza que deseja excluir esta medida?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/measurements/${id}`, {
            method: 'DELETE',
            credentials: 'include'
        });
        
        if (response.ok) {
            loadMeasurements();
        } else {
            alert('Erro ao excluir medida');
        }
    } catch (error) {
        console.error('Error deleting measurement:', error);
        alert('Erro de conexão');
    }
}

function clearMeasurementFilters() {
    document.getElementById('measurementStartDate').value = '';
    document.getElementById('measurementEndDate').value = '';
    loadMeasurements();
}

// Stats functions
async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/stats`, { credentials: 'include' });
        
        if (response.ok) {
            const stats = await response.json();
            renderStats(stats);
        } else {
            console.error('Failed to load stats');
        }
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

function renderStats(stats) {
    // Latest measurement
    const latestMeasurementEl = document.getElementById('latestMeasurement');
    if (stats.latest_measurement) {
        const m = stats.latest_measurement;
        latestMeasurementEl.innerHTML = `
            <strong>${formatDate(m.date)}</strong><br>
            ${m.weight ? `Peso: ${m.weight} kg<br>` : ''}
            ${m.height ? `Altura: ${m.height} cm<br>` : ''}
            ${m.body_fat ? `Gordura: ${m.body_fat}%<br>` : ''}
        `;
    } else {
        latestMeasurementEl.textContent = 'Nenhuma medida registrada';
    }
    
    // Total diet entries
    document.getElementById('totalDietEntries').textContent = stats.total_diet_entries;
    
    // Recent diet entries
    document.getElementById('recentDietEntries').textContent = stats.recent_diet_entries;
}

// Utility functions
function formatDate(dateString) {
    const date = new Date(dateString + 'T00:00:00');
    return date.toLocaleDateString('pt-BR');
}


// Profile functions
async function showProfileModal() {
    document.getElementById('profileModal').classList.add('show');
}

function skipProfile() {
    document.getElementById('profileModal').classList.remove('show');
    showMainScreen();
}

async function handleProfileSubmit(e) {
    e.preventDefault();
    
    const profileData = {
        age: document.getElementById('profileAge').value || null,
        gender: document.getElementById('profileGender').value || null,
        goal: document.getElementById('profileGoal').value || null,
        activity_level: document.getElementById('profileActivity').value || null,
        dietary_restrictions: document.getElementById('profileRestrictions').value || null
    };
    
    try {
        const response = await fetch(`${API_BASE}/profile`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify(profileData)
        });
        
        if (response.ok) {
            document.getElementById('profileModal').classList.remove('show');
            showMainScreen();
            // Enviar mensagem de boas-vindas personalizada
            setTimeout(() => {
                if (currentTab === 'chat') {
                    sendWelcomeMessage();
                }
            }, 1000);
        } else {
            alert('Erro ao salvar perfil');
        }
    } catch (error) {
        console.error('Error saving profile:', error);
        alert('Erro de conexão');
    }
}

// Chat functions
let chatHistory = [];

async function loadChatHistory() {
    try {
        const response = await fetch(`${API_BASE}/chat/history`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            chatHistory = data.messages;
            renderChatHistory();
        }
    } catch (error) {
        console.error('Error loading chat history:', error);
    }
}

function renderChatHistory() {
    const messagesContainer = document.getElementById('chatMessages');
    
    // Limpar mensagens existentes exceto a mensagem de boas-vindas
    const welcomeMessage = messagesContainer.querySelector('.bot-message');
    messagesContainer.innerHTML = '';
    if (welcomeMessage) {
        messagesContainer.appendChild(welcomeMessage);
    }
    
    // Renderizar histórico
    chatHistory.forEach(chat => {
        addMessageToChat(chat.message, 'user');
        addMessageToChat(chat.response, 'bot');
    });
    
    scrollChatToBottom();
}

async function handleChatSubmit(e) {
    e.preventDefault();
    
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Adicionar mensagem do usuário
    addMessageToChat(message, 'user');
    input.value = '';
    
    // Mostrar indicador de digitação
    showTypingIndicator();
    
    try {
        const response = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({ message })
        });
        
        const data = await response.json();
        
        // Remover indicador de digitação
        hideTypingIndicator();
        
        if (response.ok) {
            // Adicionar resposta da IA
            addMessageToChat(data.response, 'bot');
        } else {
            addMessageToChat('Desculpe, ocorreu um erro. Tente novamente.', 'bot');
        }
    } catch (error) {
        console.error('Chat error:', error);
        hideTypingIndicator();
        addMessageToChat('Erro de conexão. Verifique sua internet e tente novamente.', 'bot');
    }
}

function addMessageToChat(message, sender) {
    const messagesContainer = document.getElementById('chatMessages');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${sender}-message`;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.innerHTML = sender === 'bot' ? '<i class="fas fa-robot"></i>' : '<i class="fas fa-user"></i>';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    
    // Converter quebras de linha em parágrafos
    const paragraphs = message.split('\n').filter(p => p.trim());
    paragraphs.forEach(paragraph => {
        const p = document.createElement('p');
        p.textContent = paragraph;
        content.appendChild(p);
    });
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    
    messagesContainer.appendChild(messageDiv);
    scrollChatToBottom();
}

function showTypingIndicator() {
    const messagesContainer = document.getElementById('chatMessages');
    
    const typingDiv = document.createElement('div');
    typingDiv.className = 'chat-message bot-message typing-message';
    typingDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>
    `;
    
    messagesContainer.appendChild(typingDiv);
    scrollChatToBottom();
}

function hideTypingIndicator() {
    const typingMessage = document.querySelector('.typing-message');
    if (typingMessage) {
        typingMessage.remove();
    }
}

function scrollChatToBottom() {
    const messagesContainer = document.getElementById('chatMessages');
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function clearChat() {
    if (confirm('Tem certeza que deseja limpar o histórico do chat?')) {
        const messagesContainer = document.getElementById('chatMessages');
        messagesContainer.innerHTML = `
            <div class="chat-message bot-message">
                <div class="message-avatar">
                    <i class="fas fa-robot"></i>
                </div>
                <div class="message-content">
                    <p>Olá! 👋 Sou seu assistente fitness pessoal. Posso ajudar com dicas de nutrição, treino e uso do site. Como posso ajudá-lo hoje?</p>
                </div>
            </div>
        `;
        chatHistory = [];
    }
}

async function sendWelcomeMessage() {
    const welcomeMsg = "Olá! Vejo que você acabou de completar seu perfil. Que tal começarmos com algumas dicas personalizadas?";
    
    try {
        const response = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({ message: welcomeMsg })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            addMessageToChat(data.response, 'bot');
        }
    } catch (error) {
        console.error('Welcome message error:', error);
    }
}

// Update existing functions
const originalShowMainScreen = showMainScreen;
showMainScreen = function() {
    originalShowMainScreen();
    
    // Verificar se o usuário tem perfil
    checkUserProfile();
};

async function checkUserProfile() {
    try {
        const response = await fetch(`${API_BASE}/profile`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            if (!data.profile) {
                // Mostrar modal de perfil se não existir
                setTimeout(() => showProfileModal(), 500);
            }
        }
    } catch (error) {
        console.error('Error checking profile:', error);
    }
}

// Update tab switching to load chat history
const originalShowTab = showTab;
showTab = function(tabName) {
    originalShowTab(tabName);
    
    if (tabName === 'chat') {
        loadChatHistory();
    }
};

// Add event listeners
document.addEventListener('DOMContentLoaded', function() {
    // Existing event listeners...
    
    // Profile form
    document.getElementById('profileForm').addEventListener('submit', handleProfileSubmit);
    
    // Chat form
    document.getElementById('chatForm').addEventListener('submit', handleChatSubmit);
    
    // Close profile modal when clicking outside
    document.getElementById('profileModal').addEventListener('click', function(e) {
        if (e.target === this) {
            skipProfile();
        }
    });
});


// Variáveis globais para áudio
let isRecording = false;
let recognition = null;
let lastAIResponse = '';

// Inicializa funcionalidades de áudio
function initializeAudioFeatures() {
    // Verifica suporte para Web Speech API
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'pt-BR';
        
        recognition.onstart = function() {
            isRecording = true;
            updateVoiceButton();
            addChatMessage('🎤 Ouvindo... Fale agora!', true, true);
        };
        
        recognition.onresult = function(event) {
            const transcript = event.results[0][0].transcript;
            document.getElementById('chatInput').value = transcript;
            
            // Remove mensagem de "ouvindo"
            const messages = document.querySelectorAll('.typing-indicator');
            messages.forEach(msg => msg.remove());
            
            // Envia automaticamente a mensagem
            sendChatMessage();
        };
        
        recognition.onerror = function(event) {
            console.error('Erro no reconhecimento de voz:', event.error);
            addChatMessage('❌ Erro ao reconhecer voz. Tente novamente.', true);
            isRecording = false;
            updateVoiceButton();
        };
        
        recognition.onend = function() {
            isRecording = false;
            updateVoiceButton();
        };
        
        // Event listeners para botões de áudio
        document.getElementById('voiceButton').addEventListener('click', toggleVoiceRecording);
        document.getElementById('speakButton').addEventListener('click', speakLastResponse);
    } else {
        // Oculta botões se não há suporte
        document.querySelector('.audio-controls').style.display = 'none';
        console.log('Web Speech API não suportada neste navegador');
    }
}

// Alterna gravação de voz
function toggleVoiceRecording() {
    if (!recognition) return;
    
    if (isRecording) {
        recognition.stop();
    } else {
        recognition.start();
    }
}

// Atualiza visual do botão de voz
function updateVoiceButton() {
    const button = document.getElementById('voiceButton');
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

// Fala a última resposta da IA
function speakLastResponse() {
    if (!lastAIResponse) {
        addChatMessage('❌ Nenhuma resposta para reproduzir.', true);
        return;
    }
    
    // Verifica suporte para Speech Synthesis
    if ('speechSynthesis' in window) {
        // Para qualquer fala anterior
        speechSynthesis.cancel();
        
        // Limpa texto de emojis e formatação para melhor síntese
        const cleanText = lastAIResponse
            .replace(/[🤖📱📊🍽️⚖️🎯✅💪🍎📈❓]/g, '')
            .replace(/\*\*(.*?)\*\*/g, '$1')
            .replace(/\n+/g, '. ');
        
        const utterance = new SpeechSynthesisUtterance(cleanText);
        utterance.lang = 'pt-BR';
        utterance.rate = 0.9;
        utterance.pitch = 1;
        
        // Busca voz em português
        const voices = speechSynthesis.getVoices();
        const ptVoice = voices.find(voice => voice.lang.includes('pt'));
        if (ptVoice) {
            utterance.voice = ptVoice;
        }
        
        utterance.onstart = function() {
            document.getElementById('speakButton').innerHTML = '⏸️';
            document.getElementById('speakButton').title = 'Pausar reprodução';
        };
        
        utterance.onend = function() {
            document.getElementById('speakButton').innerHTML = '🔊';
            document.getElementById('speakButton').title = 'Ouvir última resposta';
        };
        
        speechSynthesis.speak(utterance);
    } else {
        addChatMessage('❌ Síntese de voz não suportada neste navegador.', true);
    }
}

// Atualiza função de envio de mensagem para salvar resposta da IA
async function sendChatMessage() {
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Adiciona mensagem do usuário
    addChatMessage(message, false);
    input.value = '';
    
    // Mostra indicador de digitação
    const typingIndicator = addChatMessage('🤖 Analisando seus dados...', true, true);
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: message })
        });
        
        const data = await response.json();
        
        // Remove indicador de digitação
        typingIndicator.remove();
        
        if (response.ok) {
            // Salva resposta para reprodução de áudio
            lastAIResponse = data.response;
            
            // Adiciona resposta da IA
            addChatMessage(data.response, true);
            
            // Mostra badge com resumo da análise
            if (data.analysis_summary) {
                const badge = `<div class="analysis-badge">📊 Analisados: ${data.analysis_summary.total_diet_entries} registros | Tendência: ${data.analysis_summary.weight_trend}</div>`;
                const lastMessage = document.querySelector('.ai-message:last-child .message-content');
                if (lastMessage) {
                    lastMessage.innerHTML += badge;
                }
            }
        } else {
            addChatMessage('❌ Desculpe, ocorreu um erro ao processar sua mensagem.', true);
        }
    } catch (error) {
        typingIndicator.remove();
        addChatMessage('❌ Erro de conexão. Tente novamente.', true);
        console.error('Erro no chat:', error);
    }
}

// Permite envio com Enter
document.addEventListener('DOMContentLoaded', function() {
    const chatInput = document.getElementById('chatInput');
    if (chatInput) {
        chatInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendChatMessage();
            }
        });
    }
    
    // Inicializa recursos de áudio
    initializeAudioFeatures();
});

// Carrega vozes quando disponíveis
if ('speechSynthesis' in window) {
    speechSynthesis.onvoiceschanged = function() {
        // Vozes carregadas
    };
}


// Chat functions
async function sendChatMessage() {
    const input = document.getElementById("chatInput");
    const message = input.value.trim();
    
    if (!message) return;
    
    // Add user message to chat
    addMessageToChat(message, "user");
    input.value = "";
    
    // Show typing indicator
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

function addMessageToChat(message, sender) {
    const chatMessages = document.getElementById("chatMessages");
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

function showTypingIndicator() {
    const chatMessages = document.getElementById("chatMessages");
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

function hideTypingIndicator() {
    const typingIndicator = document.getElementById("typingIndicator");
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

function clearChat() {
    const chatMessages = document.getElementById("chatMessages");
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

// Allow Enter key to send message
document.addEventListener("DOMContentLoaded", function() {
    const chatInput = document.getElementById("chatInput");
    if (chatInput) {
        chatInput.addEventListener("keypress", function(e) {
            if (e.key === "Enter") {
                sendChatMessage();
            }
        });
    }
});

