(function () {
    "use strict";

    const state = {
        students: [],
        student: null,
        workoutPlans: [],
        dietPlans: [],
        exercises: [],
        editor: null,
        exportText: ""
    };

    const byId = (id) => document.getElementById(id);
    const esc = (value) => escapeHtml(value == null ? "" : String(value));
    const asArray = (value) => Array.isArray(value) ? value : [];
    const segment = (value) => encodeURIComponent(String(value));

    async function api(path, options = {}) {
        const response = await fetch(`${API_BASE}${path}`, {
            method: options.method || "GET",
            credentials: "include",
            headers: options.body === undefined ? {} : { "Content-Type": "application/json" },
            body: options.body === undefined ? undefined : JSON.stringify(options.body)
        });
        let data = {};
        try { data = await response.json(); } catch (error) { data = {}; }
        if (!response.ok) {
            const requestError = new Error(data.error || "Não foi possível concluir a solicitação.");
            requestError.status = response.status;
            requestError.fields = data.fields || {};
            throw requestError;
        }
        return data;
    }

    function statusLabel(status) {
        return { draft: "Rascunho", published: "Publicado", archived: "Arquivado" }[status] || status;
    }

    function planCard(plan, type) {
        const studentId = state.student.id;
        const isDraft = plan.status === "draft";
        return `<article class="professional-plan-card">
            <div><span class="plan-status plan-status--${esc(plan.status)}">${esc(statusLabel(plan.status))}</span><small>${plan.source === "ai" ? "IA Premium" : "Manual"}</small></div>
            <h4>${esc(plan.title)}</h4>
            <p>${esc(plan.description || "Sem descrição")}</p>
            <div class="professional-card-actions">
                <button type="button" class="btn-secondary" onclick="openProfessionalPlan('${type}', '${esc(plan.id)}')"><i class="fas fa-eye"></i> Abrir</button>
                ${isDraft ? `<button type="button" class="btn-secondary" onclick="editProfessionalPlan('${type}', '${esc(plan.id)}')"><i class="fas fa-pen"></i> Editar</button><button type="button" class="btn-primary" onclick="publishProfessionalPlan('${type}', '${esc(plan.id)}')"><i class="fas fa-paper-plane"></i> Enviar</button>` : ""}
                ${isDraft && type === "diet" ? `<button type="button" class="btn-secondary" onclick="suggestProfessionalDietChange('${esc(plan.id)}')"><i class="fas fa-wand-magic-sparkles"></i> Sugerir mudança</button>` : ""}
                <button type="button" class="btn-secondary" onclick="exportProfessionalPlan('${type}', '${esc(plan.id)}', '${esc(studentId)}')"><i class="fab fa-whatsapp"></i></button>
            </div>
        </article>`;
    }

    async function loadProfessionalDashboard() {
        if (!window.currentUser?.is_professional) return;
        const dashboard = byId("professionalDashboard");
        const detail = byId("professionalStudentDetail");
        dashboard?.classList.remove("hidden");
        detail?.classList.add("hidden");
        const container = byId("professionalStudents");
        if (container) container.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Carregando alunos...</div>';
        try {
            const data = await api("/professional/students?limit=100");
            state.students = data.items || [];
            renderProfessionalDashboard();
        } catch (error) {
            if (container) container.innerHTML = `<div class="empty-state"><p>${esc(error.message)}</p></div>`;
        }
    }

    function renderProfessionalDashboard() {
        const stats = byId("professionalStats");
        const drafts = state.students.reduce((total, student) => total
            + Number(student.latest_workout_plan?.status === "draft")
            + Number(student.latest_diet_plan?.status === "draft"), 0);
        if (stats) stats.innerHTML = `
            <article class="stat-card"><span class="stat-card__icon"><i class="fas fa-users"></i></span><div><small>Alunos ativos</small><strong>${state.students.length}</strong></div></article>
            <article class="stat-card"><span class="stat-card__icon stat-card__icon--blue"><i class="fas fa-file-pen"></i></span><div><small>Rascunhos recentes</small><strong>${drafts}</strong></div></article>`;
        const container = byId("professionalStudents");
        if (!container) return;
        if (!state.students.length) {
            container.innerHTML = '<div class="empty-state"><i class="fas fa-user-plus"></i><h3>Convide seu primeiro aluno</h3><p>O aluno continuará usando a conta normal e autorizará seu acesso pelo link.</p><button class="btn-primary" onclick="openProfessionalInvite()">Gerar convite</button></div>';
            return;
        }
        container.innerHTML = state.students.map((student) => `
            <button type="button" class="professional-student-card" onclick="openProfessionalStudent('${esc(student.id)}')">
                <span class="professional-student-avatar">${esc(student.username.charAt(0).toUpperCase())}</span>
                <span><strong>${esc(student.username)}</strong><small>${esc(student.profile?.goal || "Objetivo não informado")}</small></span>
                <span class="professional-student-meta"><small>Última medida</small><strong>${student.latest_measurement?.weight ? `${esc(student.latest_measurement.weight)} kg` : "Sem registro"}</strong></span>
                <i class="fas fa-chevron-right"></i>
            </button>`).join("");
    }

    async function openProfessionalStudent(studentId) {
        showTab("professional");
        const dashboard = byId("professionalDashboard");
        const detail = byId("professionalStudentDetail");
        dashboard?.classList.add("hidden");
        detail?.classList.remove("hidden");
        if (detail) detail.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Carregando aluno...</div>';
        try {
            const [student, workouts, diets] = await Promise.all([
                api(`/professional/students/${segment(studentId)}`),
                api(`/professional/students/${segment(studentId)}/workout-plans`),
                api(`/professional/students/${segment(studentId)}/diet-plans`)
            ]);
            state.student = student;
            state.workoutPlans = workouts;
            state.dietPlans = diets;
            renderProfessionalStudent();
        } catch (error) {
            if (detail) detail.innerHTML = `<div class="empty-state"><p>${esc(error.message)}</p><button class="btn-secondary" onclick="loadProfessionalDashboard()">Voltar</button></div>`;
        }
    }

    function renderProfessionalStudent() {
        const student = state.student;
        const detail = byId("professionalStudentDetail");
        if (!student || !detail) return;
        const measurements = asArray(student.measurements).slice(0, 4);
        detail.innerHTML = `
            <div class="professional-student-header">
                <button type="button" class="back-button" onclick="loadProfessionalDashboard()"><i class="fas fa-arrow-left"></i></button>
                <span class="professional-student-avatar professional-student-avatar--large">${esc(student.username.charAt(0).toUpperCase())}</span>
                <div><span class="content-kicker">Aluno ativo</span><h2>${esc(student.username)}</h2><p>${esc(student.profile?.goal || "Perfil ainda incompleto")}</p></div>
                <button type="button" class="btn-secondary professional-revoke" onclick="revokeProfessionalStudent()"><i class="fas fa-link-slash"></i> Desvincular</button>
            </div>
            <div class="professional-profile-grid">
                ${profileFact("Idade", student.profile?.age, "anos")}${profileFact("Peso", student.profile?.weight, "kg")}${profileFact("Altura", student.profile?.height, "cm")}${profileFact("Atividade", student.profile?.activity_level)}
            </div>
            <section class="professional-plan-section">
                <header><div><span class="content-kicker content-kicker--blue">Treinos</span><h3>Planos de treino</h3></div><div class="professional-create-actions"><button class="btn-secondary" onclick="createManualProfessionalPlan('workout')"><i class="fas fa-plus"></i> Manual</button><button class="btn-primary" onclick="openProfessionalPlanWizard('workout', '${esc(student.id)}')"><i class="fas fa-wand-magic-sparkles"></i> Gerar com IA</button></div></header>
                <div class="professional-plan-grid">${state.workoutPlans.length ? state.workoutPlans.map((plan) => planCard(plan, "workout")).join("") : emptyPlan("treino")}</div>
            </section>
            <section class="professional-plan-section">
                <header><div><span class="content-kicker">Alimentação</span><h3>Planos alimentares</h3></div><div class="professional-create-actions"><button class="btn-secondary" onclick="createManualProfessionalPlan('diet')"><i class="fas fa-plus"></i> Manual</button><button class="btn-primary" onclick="openProfessionalPlanWizard('diet', '${esc(student.id)}')"><i class="fas fa-wand-magic-sparkles"></i> Gerar com IA</button></div></header>
                <div class="professional-plan-grid">${state.dietPlans.length ? state.dietPlans.map((plan) => planCard(plan, "diet")).join("") : emptyPlan("alimentar")}</div>
            </section>
            <section class="professional-plan-section"><header><div><span class="content-kicker">Evolução</span><h3>Medidas recentes</h3></div></header><div class="professional-measure-grid">${measurements.length ? measurements.map(renderMeasurement).join("") : '<p class="muted">O aluno ainda não registrou medidas.</p>'}</div></section>`;
    }

    function profileFact(label, value, suffix = "") {
        return `<article><small>${esc(label)}</small><strong>${value == null || value === "" ? "Não informado" : `${esc(value)} ${esc(suffix)}`}</strong></article>`;
    }

    function renderMeasurement(item) {
        return `<article><small>${esc(new Date(`${item.date}T12:00:00`).toLocaleDateString("pt-BR"))}</small><strong>${item.weight ? `${esc(item.weight)} kg` : "Sem peso"}</strong><span>${item.body_fat ? `${esc(item.body_fat)}% gordura` : ""}</span></article>`;
    }

    const emptyPlan = (label) => `<div class="empty-state empty-state--compact"><p>Nenhum plano ${label} criado.</p></div>`;

    function openProfessionalInvite() {
        byId("professionalInviteResult")?.classList.add("hidden");
        if (byId("professionalInviteMessage")) byId("professionalInviteMessage").textContent = "";
        openAppModal(byId("professionalInviteModal"));
    }

    function closeProfessionalInvite() { closeAppModal(byId("professionalInviteModal")); }

    async function generateProfessionalInvite() {
        const button = byId("professionalInviteGenerate");
        if (button) button.disabled = true;
        try {
            const data = await api("/professional/invitations", { method: "POST", body: {} });
            const link = new URL(data.invite_path, window.location.origin).toString();
            byId("professionalInviteLink").value = link;
            byId("professionalInviteResult")?.classList.remove("hidden");
            if (byId("professionalInviteMessage")) byId("professionalInviteMessage").textContent = "Link criado. Ele expira em 7 dias.";
        } catch (error) {
            if (byId("professionalInviteMessage")) byId("professionalInviteMessage").textContent = error.message;
        } finally {
            if (button) button.disabled = false;
        }
    }

    async function copyText(text) {
        if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
        const textarea = document.createElement("textarea");
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
    }

    function copyProfessionalInvite() {
        copyText(byId("professionalInviteLink").value).then(() => showToast("Link copiado.", "success"));
    }

    function shareProfessionalInvite() {
        const text = `Olá! Use este link para criar ou acessar sua conta e aceitar meu acompanhamento no Diet Tracker:\n${byId("professionalInviteLink").value}`;
        window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener");
    }

    async function revokeProfessionalStudent() {
        if (!state.student || !window.confirm("Encerrar o vínculo com este aluno? Os planos publicados continuarão na conta dele.")) return;
        try {
            await api(`/professional/students/${segment(state.student.id)}`, { method: "DELETE" });
            showToast("Vínculo encerrado.", "success");
            loadProfessionalDashboard();
        } catch (error) { showToast(error.message, "error"); }
    }

    async function ensureExercises() {
        if (state.exercises.length) return state.exercises;
        state.exercises = await api("/professional/exercises");
        return state.exercises;
    }

    function defaultQuestionnaire(type) {
        if (type === "workout") return { goal: "hypertrophy", experience_level: "beginner", days_per_week: 2, split_type: "full_body", session_duration: 45, equipment: ["full_gym"], limitations: "", priorities: "", avoid_exercises: "" };
        return { goal: "general_health", meals_per_day: 3, diet_pattern: "omnivore", training_days_per_week: 3, change_pace: "conservative", allergies: [], intolerances: [], disliked_foods: [], preferred_foods: [], available_ingredients: [], custom_targets: { calories: null, protein: null, carbs: null, fat: null }, budget: "moderate", prep_minutes: 30, notes: "" };
    }

    async function createManualProfessionalPlan(type) {
        if (!state.student) return;
        if (type === "workout") await ensureExercises();
        state.editor = { type, planId: null, questionnaire: defaultQuestionnaire(type), plan: null };
        renderProfessionalEditor();
        openAppModal(byId("professionalPlanEditorModal"));
    }

    async function editProfessionalPlan(type, planId) {
        if (type === "workout") await ensureExercises();
        try {
            const plan = await api(`/professional/students/${segment(state.student.id)}/${type === "workout" ? "workout-plans" : "diet-plans"}/${segment(planId)}`);
            state.editor = {
                type,
                planId,
                questionnaire: plan.questionnaire || plan.questionnaire_data || defaultQuestionnaire(type),
                plan
            };
            renderProfessionalEditor();
            openAppModal(byId("professionalPlanEditorModal"));
        } catch (error) { showToast(error.message, "error"); }
    }

    function renderProfessionalEditor() {
        const editor = state.editor;
        const title = byId("professionalPlanEditorTitle");
        if (title) title.textContent = `${editor.planId ? "Editar" : "Criar"} plano ${editor.type === "workout" ? "de treino" : "alimentar"}`;
        const body = byId("professionalPlanEditorBody");
        if (!body) return;
        body.innerHTML = editor.type === "workout" ? workoutEditorHtml(editor) : dietEditorHtml(editor);
    }

    function workoutEditorHtml(editor) {
        const questionnaire = editor.questionnaire;
        const plan = editor.plan || {};
        const dayCount = Number(plan.days?.length || questionnaire.days_per_week || 2);
        const days = plan.days || Array.from({ length: dayCount }, (_, index) => ({ code: String.fromCharCode(65 + index), title: `Treino ${String.fromCharCode(65 + index)}`, focus: "", exercises: [{}] }));
        return `<div class="professional-editor-basics">
            ${inputField("Título", "editorTitle", plan.title || "Plano de treino")}${inputField("Descrição", "editorDescription", plan.description || "")}
            ${selectField("Objetivo", "editorGoal", questionnaire.goal, { hypertrophy: "Hipertrofia", strength: "Força", conditioning: "Condicionamento", fat_loss: "Perda de gordura", mobility: "Mobilidade" })}
            ${selectField("Experiência", "editorExperience", questionnaire.experience_level, { beginner: "Iniciante", intermediate: "Intermediário", advanced: "Avançado" })}
            ${selectField("Dias por semana", "editorDays", dayCount, { 2: "2 dias", 3: "3 dias", 4: "4 dias", 5: "5 dias", 6: "6 dias" }, 'onchange="professionalEditorDaysChanged()"')}
            ${selectField("Duração", "editorDuration", questionnaire.session_duration, { 20: "20 min", 30: "30 min", 45: "45 min", 60: "60 min", 75: "75 min", 90: "90 min" })}
        </div><div id="professionalWorkoutDays" class="professional-editor-days">${days.map((day, dayIndex) => workoutDayHtml(day, dayIndex)).join("")}</div>`;
    }

    function workoutDayHtml(day, dayIndex) {
        const exercises = asArray(day.exercises).length ? day.exercises : [{}];
        return `<section class="professional-editor-day" data-day-index="${dayIndex}"><header>${inputField("Nome do dia", `dayTitle-${dayIndex}`, day.title || `Treino ${dayIndex + 1}`)}${inputField("Foco", `dayFocus-${dayIndex}`, day.focus || "")}</header><div class="professional-exercise-rows">${exercises.map((exercise, exerciseIndex) => workoutExerciseHtml(exercise, dayIndex, exerciseIndex)).join("")}</div><button type="button" class="btn-secondary" onclick="addProfessionalExercise(${dayIndex})"><i class="fas fa-plus"></i> Exercício</button></section>`;
    }

    function workoutExerciseHtml(exercise, dayIndex, exerciseIndex) {
        const options = state.exercises.map((item) => `<option value="${esc(item.catalog_key)}"${item.catalog_key === exercise.catalog_key ? " selected" : ""}>${esc(item.name)} · ${esc(item.equipment)}</option>`).join("");
        return `<div class="professional-exercise-row" data-exercise-index="${exerciseIndex}"><label>Exercício<select class="exercise-key"><option value="">Selecione</option>${options}</select></label><label>Séries<input class="exercise-sets" type="number" min="1" max="10" value="${esc(exercise.sets || 3)}"></label><label>Repetições<input class="exercise-reps" value="${esc(exercise.reps || "8-12")}"></label><label>Descanso (s)<input class="exercise-rest" type="number" min="0" max="600" value="${esc(exercise.rest_seconds ?? 60)}"></label><label>Carga<input class="exercise-weight" value="${esc(exercise.weight || "")}"></label><label>Observação<input class="exercise-notes" value="${esc(exercise.notes || "")}"></label><button type="button" class="icon-add-button professional-remove" onclick="removeProfessionalExercise(this)" aria-label="Remover"><i class="fas fa-trash"></i></button></div>`;
    }

    function dietEditorHtml(editor) {
        const questionnaire = editor.questionnaire;
        const plan = editor.plan || {};
        const mealCount = Number(questionnaire.meals_per_day || plan.meals_per_day || 3);
        return `<div class="professional-editor-basics">
            ${inputField("Título", "editorTitle", plan.title || "Plano alimentar")}${inputField("Descrição", "editorDescription", plan.description || "")}
            ${selectField("Objetivo", "editorGoal", questionnaire.goal, { general_health: "Saúde geral", fat_loss: "Perda de gordura", muscle_gain: "Ganho de massa", maintenance: "Manutenção" })}
            ${selectField("Refeições por dia", "editorMealCount", mealCount, { 3: "3 refeições", 4: "4 refeições", 5: "5 refeições" }, 'onchange="professionalEditorMealsChanged()"')}
            ${inputField("Meta calórica (opcional)", "editorCalories", questionnaire.custom_targets?.calories || "", "number")}${inputField("Proteína (g, opcional)", "editorProtein", questionnaire.custom_targets?.protein || "", "number")}
        </div><div id="professionalDietDays" class="professional-editor-days">${[1, 2, 3].map((day) => dietDayHtml(day, mealsForDay(plan, day, mealCount))).join("")}</div>`;
    }

    function mealsForDay(plan, day, count) {
        const existing = asArray(plan.meals).filter((meal) => meal.day_of_week === `Dia ${day}`);
        return existing.length ? existing : Array.from({ length: count }, (_, index) => ({ meal_type: `Refeição ${index + 1}`, items: [], calories: 0, protein: 0, carbs: 0, fat: 0 }));
    }

    function dietDayHtml(day, meals) {
        return `<section class="professional-editor-day" data-diet-day="${day}"><header><h4>Dia ${day}</h4></header><div class="professional-meal-rows">${meals.map((meal, index) => dietMealHtml(meal, index)).join("")}</div></section>`;
    }

    function dietMealHtml(meal, index) {
        return `<div class="professional-meal-row" data-meal-index="${index}">${inputField("Refeição", "", meal.meal_type, "text", "meal-type")}${inputField("Alimentos (um por linha)", "", asArray(meal.items).join("\n") || meal.description || "", "textarea", "meal-items")}${inputField("Calorias", "", meal.calories ?? 0, "number", "meal-calories")}${inputField("Proteína", "", meal.protein ?? 0, "number", "meal-protein")}${inputField("Carboidratos", "", meal.carbs ?? 0, "number", "meal-carbs")}${inputField("Gorduras", "", meal.fat ?? 0, "number", "meal-fat")}${inputField("Preparo", "", meal.prep_instructions || "", "text", "meal-prep")}</div>`;
    }

    function inputField(label, id, value, type = "text", className = "") {
        const identity = id ? ` id="${id}"` : "";
        if (type === "textarea") return `<label>${esc(label)}<textarea${identity} class="${esc(className)}" rows="3">${esc(value)}</textarea></label>`;
        return `<label>${esc(label)}<input${identity} class="${esc(className)}" type="${type}" value="${esc(value)}"></label>`;
    }

    function selectField(label, id, selected, options, attributes = "") {
        return `<label>${esc(label)}<select id="${id}" ${attributes}>${Object.entries(options).map(([value, text]) => `<option value="${esc(value)}"${String(selected) === value ? " selected" : ""}>${esc(text)}</option>`).join("")}</select></label>`;
    }

    function addProfessionalExercise(dayIndex) {
        const rows = byId("professionalWorkoutDays")?.querySelector(`[data-day-index="${dayIndex}"] .professional-exercise-rows`);
        if (!rows) return;
        rows.insertAdjacentHTML("beforeend", workoutExerciseHtml({}, dayIndex, rows.children.length));
    }

    function removeProfessionalExercise(button) {
        const rows = button.closest(".professional-exercise-rows");
        if (rows?.children.length > 1) button.closest(".professional-exercise-row")?.remove();
    }

    function professionalEditorDaysChanged() {
        if (!state.editor || state.editor.type !== "workout") return;
        const count = Number(byId("editorDays").value);
        const container = byId("professionalWorkoutDays");
        if (!container) return;
        const current = Array.from(container.querySelectorAll(".professional-editor-day"));
        if (current.length > count) current.slice(count).forEach((day) => day.remove());
        for (let index = current.length; index < count; index += 1) container.insertAdjacentHTML("beforeend", workoutDayHtml({}, index));
    }

    function professionalEditorMealsChanged() {
        if (!state.editor || state.editor.type !== "diet") return;
        const count = Number(byId("editorMealCount").value);
        byId("professionalDietDays").innerHTML = [1, 2, 3].map((day) => dietDayHtml(day, mealsForDay({}, day, count))).join("");
    }

    function collectEditorPayload() {
        const editor = state.editor;
        if (editor.type === "workout") {
            const days = Array.from(byId("professionalWorkoutDays").querySelectorAll(".professional-editor-day")).map((day, dayIndex) => ({
                code: String.fromCharCode(65 + dayIndex),
                title: day.querySelector(`[id="dayTitle-${dayIndex}"]`).value,
                focus: day.querySelector(`[id="dayFocus-${dayIndex}"]`).value,
                exercises: Array.from(day.querySelectorAll(".professional-exercise-row")).map((row) => ({ catalog_key: row.querySelector(".exercise-key").value, sets: Number(row.querySelector(".exercise-sets").value), reps: row.querySelector(".exercise-reps").value, rest_seconds: Number(row.querySelector(".exercise-rest").value), weight: row.querySelector(".exercise-weight").value, notes: row.querySelector(".exercise-notes").value }))
            }));
            const daysPerWeek = Number(byId("editorDays").value);
            const original = editor.questionnaire || defaultQuestionnaire("workout");
            const defaultSplit = daysPerWeek === 2 ? "full_body" : daysPerWeek === 3 ? "abc" : daysPerWeek === 4 ? "abcd" : daysPerWeek === 5 ? "abcde" : "abc";
            const split = daysPerWeek === Number(original.days_per_week) ? original.split_type : defaultSplit;
            return { questionnaire: { ...original, goal: byId("editorGoal").value, experience_level: byId("editorExperience").value, days_per_week: daysPerWeek, split_type: split, session_duration: Number(byId("editorDuration").value) }, plan: { type: "workout_plan", title: byId("editorTitle").value, description: byId("editorDescription").value, days } };
        }
        const mealCount = Number(byId("editorMealCount").value);
        const days = Array.from(byId("professionalDietDays").querySelectorAll(".professional-editor-day")).map((day) => ({ meals: Array.from(day.querySelectorAll(".professional-meal-row")).map((row) => ({ meal_type: row.querySelector(".meal-type").value, items: row.querySelector(".meal-items").value.split("\n").map((item) => item.trim()).filter(Boolean), calories: Number(row.querySelector(".meal-calories").value), protein: Number(row.querySelector(".meal-protein").value), carbs: Number(row.querySelector(".meal-carbs").value), fat: Number(row.querySelector(".meal-fat").value), prep: row.querySelector(".meal-prep").value, prep_minutes: 30, substitutions: [] })) }));
        const calories = byId("editorCalories").value;
        const protein = byId("editorProtein").value;
        const original = state.editor.questionnaire || defaultQuestionnaire("diet");
        return { questionnaire: { ...original, goal: byId("editorGoal").value, meals_per_day: mealCount, custom_targets: { ...(original.custom_targets || {}), calories: calories ? Number(calories) : null, protein: protein ? Number(protein) : null } }, plan: { type: "diet_plan", title: byId("editorTitle").value, description: byId("editorDescription").value, days } };
    }

    async function saveProfessionalEditor(event) {
        event.preventDefault();
        const editor = state.editor;
        if (!editor || !state.student) return;
        const resource = editor.type === "workout" ? "workout-plans" : "diet-plans";
        const path = `/professional/students/${segment(state.student.id)}/${resource}${editor.planId ? `/${segment(editor.planId)}` : ""}`;
        const message = byId("professionalPlanEditorMessage");
        try {
            await api(path, { method: editor.planId ? "PUT" : "POST", body: collectEditorPayload() });
            closeProfessionalPlanEditor();
            showToast("Rascunho salvo.", "success");
            openProfessionalStudent(state.student.id);
        } catch (error) {
            if (message) message.textContent = `${error.message}${Object.values(error.fields || {}).length ? ` ${Object.values(error.fields).join(" ")}` : ""}`;
        }
    }

    function closeProfessionalPlanEditor() { closeAppModal(byId("professionalPlanEditorModal")); }

    async function openProfessionalPlan(type, planId) {
        try {
            const plan = await api(`/professional/students/${segment(state.student.id)}/${type === "workout" ? "workout-plans" : "diet-plans"}/${segment(planId)}`);
            if (type === "workout") renderProfessionalPlanPreview(plan, "workout");
            else renderProfessionalPlanPreview(plan, "diet");
        } catch (error) { showToast(error.message, "error"); }
    }

    function renderProfessionalPlanPreview(plan, type) {
        const modal = byId(type === "workout" ? "viewWorkoutPlanModal" : "viewDietPlanModal");
        const details = byId(type === "workout" ? "viewWorkoutPlanDetails" : "viewDietPlanDetails");
        const title = byId(type === "workout" ? "viewWorkoutPlanTitle" : "viewDietPlanTitle");
        if (title) title.textContent = plan.title;
        if (details) details.innerHTML = `<div class="professional-preview"><p>${esc(plan.description || "")}</p>${type === "workout" ? asArray(plan.days).map((day) => `<section><h4>${esc(day.title)}</h4><p>${esc(day.focus || "")}</p>${asArray(day.exercises).map((exercise) => `<article><strong>${esc(exercise.name)}</strong><span>${esc(exercise.sets)} x ${esc(exercise.reps)} · ${esc(exercise.rest_seconds)}s</span><small>${esc(exercise.notes || "")}</small></article>`).join("")}</section>`).join("") : [1, 2, 3].map((day) => `<section><h4>Dia ${day}</h4>${asArray(plan.meals).filter((meal) => meal.day_of_week === `Dia ${day}`).map((meal) => `<article><strong>${esc(meal.meal_type)}</strong><span>${esc(asArray(meal.items).join(", ") || meal.description)}</span><small>${esc(meal.calories)} kcal · P ${esc(meal.protein)}g · C ${esc(meal.carbs)}g · G ${esc(meal.fat)}g</small></article>`).join("")}</section>`).join("")}</div>`;
        openAppModal(modal);
    }

    async function publishProfessionalPlan(type, planId) {
        if (!window.confirm("Enviar este plano para a conta do aluno? Depois disso, novas edições devem ser feitas em outra revisão.")) return;
        try {
            await api(`/professional/students/${segment(state.student.id)}/${type === "workout" ? "workout-plans" : "diet-plans"}/${segment(planId)}/publish`, { method: "POST", body: {} });
            showToast("Plano enviado ao aluno.", "success");
            openProfessionalStudent(state.student.id);
        } catch (error) { showToast(`${error.message} ${Object.values(error.fields || {}).join(" ")}`, "error"); }
    }

    async function suggestProfessionalDietChange(planId) {
        const rawDay = window.prompt("Qual dia deseja ajustar? Informe 1, 2 ou 3.", "1");
        if (rawDay == null) return;
        const day = Number(rawDay);
        if (![1, 2, 3].includes(day)) {
            showToast("Escolha um dia entre 1 e 3.", "error");
            return;
        }
        const feedback = window.prompt("Descreva a mudança desejada.", "");
        if (!feedback?.trim()) return;
        try {
            showToast("Gerando uma sugestão que preserva metas e restrições...", "info");
            const base = `/professional/students/${segment(state.student.id)}/diet-plans/${segment(planId)}`;
            const suggestion = await api(`${base}/suggest`, { method: "POST", body: { day, feedback } });
            const preview = suggestion.meals.map((meal) => `${meal.meal_type}: ${asArray(meal.items).join(", ")} (${meal.calories} kcal)`).join("\n\n");
            if (!window.confirm(`Sugestão para o Dia ${day}:\n\n${preview}\n\nAplicar esta mudança ao rascunho?`)) return;
            await api(`${base}/days/${day}`, { method: "PUT", body: { meals: suggestion.meals } });
            showToast("Sugestão aplicada ao rascunho.", "success");
            openProfessionalStudent(state.student.id);
        } catch (error) {
            showToast(`${error.message} ${Object.values(error.fields || {}).join(" ")}`, "error");
        }
    }

    async function exportProfessionalPlan(type, planId) {
        try {
            const plan = await api(`/professional/students/${segment(state.student.id)}/${type === "workout" ? "workout-plans" : "diet-plans"}/${segment(planId)}`);
            state.exportText = type === "workout" ? formatWorkout(plan) : formatDiet(plan);
            byId("professionalExportText").value = state.exportText;
            openAppModal(byId("professionalExportModal"));
        } catch (error) { showToast(error.message, "error"); }
    }

    function formatWorkout(plan) {
        const lines = [`*${plan.title.toUpperCase()}*`, plan.description || "", ""];
        asArray(plan.days).forEach((day) => {
            lines.push(`*${day.title}*${day.focus ? ` - ${day.focus}` : ""}`);
            asArray(day.exercises).forEach((exercise, index) => {
                lines.push(`${index + 1}. ${exercise.name}`, `${exercise.sets} séries x ${exercise.reps}`, `Descanso: ${exercise.rest_seconds}s${exercise.weight ? ` | Carga: ${exercise.weight}` : ""}`);
                if (exercise.notes) lines.push(`Obs.: ${exercise.notes}`);
            });
            lines.push("");
        });
        return lines.join("\n").trim();
    }

    function formatDiet(plan) {
        const lines = [`*${plan.title.toUpperCase()}*`, plan.description || "", ""];
        [1, 2, 3].forEach((day) => {
            lines.push(`*DIA ${day}*`);
            asArray(plan.meals).filter((meal) => meal.day_of_week === `Dia ${day}`).forEach((meal) => {
                lines.push(`*${meal.meal_type}*`, asArray(meal.items).join(", ") || meal.description, `${meal.calories} kcal | P ${meal.protein}g | C ${meal.carbs}g | G ${meal.fat}g`);
            });
            lines.push("");
        });
        return lines.join("\n").trim();
    }

    function closeProfessionalExport() { closeAppModal(byId("professionalExportModal")); }
    function copyProfessionalExport() { copyText(byId("professionalExportText").value).then(() => showToast("Plano copiado.", "success")); }
    function shareProfessionalExport() { window.open(`https://wa.me/?text=${encodeURIComponent(byId("professionalExportText").value)}`, "_blank", "noopener"); }

    async function handleInvitationFromUrl() {
        const params = new URLSearchParams(window.location.search);
        const token = params.get("invite");
        if (!token) return;
        if (!window.currentUser) {
            window.requireAuth?.("Entre ou crie sua conta para aceitar o convite do profissional.", { mode: "register", resume: handleInvitationFromUrl });
            return;
        }
        try {
            const details = await api(`/invitations/${segment(token)}`);
            if (!window.confirm(`Aceitar o acompanhamento de ${details.invitation.professional.username}? O profissional poderá consultar seus dados e criar planos para você.`)) return;
            await api(`/invitations/${segment(token)}/accept`, { method: "POST", body: {} });
            window.history.replaceState({}, "", window.location.pathname);
            showToast("Convite aceito.", "success");
        } catch (error) { showToast(error.message, "error"); }
    }

    async function loadOwnProfessionalRelationship() {
        const button = byId("profileProfessionalRelationship");
        if (!window.currentUser || !button) return;
        try {
            const data = await api("/professional-relationship");
            button.classList.toggle("hidden", !data.relationship);
            if (data.relationship && byId("profileProfessionalName")) {
                byId("profileProfessionalName").textContent = `Personal: ${data.relationship.professional.username}`;
            }
        } catch (error) {
            button.classList.add("hidden");
        }
    }

    async function revokeOwnProfessionalRelationship() {
        if (!window.confirm("Encerrar o vínculo com seu personal? Os planos já publicados continuarão disponíveis.")) return;
        try {
            await api("/professional-relationship", { method: "DELETE" });
            byId("profileProfessionalRelationship")?.classList.add("hidden");
            showToast("Vínculo profissional encerrado.", "success");
        } catch (error) { showToast(error.message, "error"); }
    }

    byId("professionalPlanEditorForm")?.addEventListener("submit", saveProfessionalEditor);
    window.addEventListener("diettracker:auth-ready", handleInvitationFromUrl);

    Object.assign(window, {
        loadProfessionalDashboard,
        openProfessionalStudent,
        openProfessionalInvite,
        closeProfessionalInvite,
        generateProfessionalInvite,
        copyProfessionalInvite,
        shareProfessionalInvite,
        revokeProfessionalStudent,
        createManualProfessionalPlan,
        editProfessionalPlan,
        closeProfessionalPlanEditor,
        addProfessionalExercise,
        removeProfessionalExercise,
        professionalEditorDaysChanged,
        professionalEditorMealsChanged,
        openProfessionalPlan,
        publishProfessionalPlan,
        suggestProfessionalDietChange,
        exportProfessionalPlan,
        closeProfessionalExport,
        copyProfessionalExport,
        shareProfessionalExport,
        loadOwnProfessionalRelationship,
        revokeOwnProfessionalRelationship
    });
}());
