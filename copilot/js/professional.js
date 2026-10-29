(function () {
    "use strict";

    const state = {
        students: [],
        student: null,
        workoutPlans: [],
        exercises: [],
        editor: null,
        rosterEditId: null,
        inviteStudentId: null,
        owner: null,
        version: 0,
        saving: false,
        loadingStudent: null,
        publishing: new Set(),
        acceptingInvite: false
    };

    const byId = (id) => document.getElementById(id);
    const esc = (value) => escapeHtml(value == null ? "" : String(value));
    const asArray = (value) => Array.isArray(value) ? value : [];
    const segment = (value) => encodeURIComponent(String(value));

    async function api(path, options = {}) {
        const requestVersion = state.version;
        const response = await fetch(`${API_BASE}${path}`, {
            method: options.method || "GET",
            credentials: "include",
            headers: options.body === undefined ? {} : { "Content-Type": "application/json" },
            body: options.body === undefined ? undefined : JSON.stringify(options.body)
        });
        if (requestVersion !== state.version) throw new Error("A sessão mudou. Abra a área profissional novamente.");
        let data = {};
        try { data = await response.json(); } catch (error) { data = {}; }
        if (requestVersion !== state.version) throw new Error("A sessão mudou. Abra a área profissional novamente.");
        if (!response.ok) {
            const requestError = new Error(data.error || "Não foi possível concluir a solicitação.");
            requestError.status = response.status;
            requestError.fields = data.fields || {};
            throw requestError;
        }
        if (response.status === 202 && data.job_id) return window.waitForAIJob(data);
        return data;
    }



    function statusLabel(status) {
        return { draft: "Rascunho", published: "Publicado", archived: "Arquivado" }[status] || status;
    }

    function planCard(plan, type) {
        const offline = Boolean(state.student.is_offline);
        const isDraft = plan.status === "draft";
        return `<article class="professional-plan-card">
            <div><span class="plan-status plan-status--${esc(plan.status)}">${esc(statusLabel(plan.status))}</span><small>${plan.source === "ai" ? "IA Premium" : "Manual"}</small></div>
            <h4>${esc(plan.title)}</h4>
            <p>${esc(plan.description || "Sem descrição")}</p>
            <small>${Number(plan.days_count || plan.days_per_week || 0)} treinos · ${Number(plan.exercises_count || 0)} exercícios${plan.session_duration ? ` · ${Number(plan.session_duration)} min` : ""}</small>
            <small>${isDraft ? offline ? "Vincule o aluno ao app para enviar." : "Só você vê este rascunho." : plan.status === "published" ? "Disponível na biblioteca de treinos do aluno." : "Plano arquivado."}</small>
            <div class="professional-card-actions">
                <button type="button" class="btn-secondary" onclick="openProfessionalPlan('${type}', '${esc(plan.id)}')"><i class="fas fa-eye"></i> Abrir</button>
                ${isDraft ? `<button type="button" class="btn-secondary" onclick="editProfessionalPlan('${type}', '${esc(plan.id)}')"><i class="fas fa-pen"></i> Editar</button>${offline ? "" : `<button type="button" class="btn-primary" onclick="publishProfessionalPlan('${type}', '${esc(plan.id)}')"><i class="fas fa-paper-plane"></i> Enviar</button>`}` : ""}
            </div>
        </article>`;
    }

    async function loadProfessionalDashboard() {
        if (!hasAccess()) return;
        const requestVersion = state.version;
        state.loadingStudent = null;
        const dashboard = byId("professionalDashboard");
        const detail = byId("professionalStudentDetail");
        dashboard?.classList.remove("hidden");
        detail?.classList.add("hidden");
        const container = byId("professionalStudents");
        if (container) container.innerHTML = '<div class="plans-loading" role="status"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>Carregando alunos...</span></div>';
        try {
            const data = await api("/professional/students?limit=100");
            if (requestVersion !== state.version || state.loadingStudent !== null) return;
            state.students = data.items || [];
            renderProfessionalDashboard();
        } catch (error) {
            if (requestVersion === state.version && container) container.innerHTML = `<div class="empty-state"><p>${esc(error.message)}</p><button type="button" class="btn-secondary" onclick="loadProfessionalDashboard()">Tentar novamente</button></div>`;
        }
    }

    function renderProfessionalDashboard() {
        const stats = byId("professionalStats");
        const drafts = state.students.reduce((total, student) => total
            + Number(student.latest_workout_plan?.status === "draft"), 0);
        if (stats) stats.innerHTML = `
                            <article class="stat-card"><span class="stat-card__icon"><i class="fas fa-users"></i></span><div><small>Alunos acompanhados</small><strong>${state.students.length}</strong></div></article>
            <article class="stat-card"><span class="stat-card__icon stat-card__icon--blue"><i class="fas fa-file-pen"></i></span><div><small>Rascunhos recentes</small><strong>${drafts}</strong></div></article>`;
        const container = byId("professionalStudents");
        if (!container) return;
        if (!state.students.length) {
            container.innerHTML = '<div class="empty-state"><i class="fas fa-user-plus"></i><h3>Cadastre seu primeiro aluno</h3><p>Você pode gerenciar o perfil e os planos mesmo sem ele ter uma conta no app.</p><button class="btn-primary" onclick="openOfflineStudent()">Cadastrar aluno</button></div>';
            return;
        }
        container.innerHTML = state.students.map((student) => `
            <button type="button" class="professional-student-card" onclick="openProfessionalStudent('${esc(student.id)}')">
                <span class="professional-student-avatar">${student.avatar_url ? `<img src="${esc(student.avatar_url)}" alt="">` : esc(student.username.charAt(0).toUpperCase())}</span>
                <span><strong>${esc(student.username)}</strong><small>${student.is_offline ? "Cadastro do personal · sem conta no app" : esc(student.profile?.goal || "Objetivo não informado")}</small></span>
                <span class="professional-student-meta"><small>Última medida</small><strong>${student.latest_measurement?.weight ? `${esc(student.latest_measurement.weight)} kg` : "Sem registro"}</strong></span>
                <i class="fas fa-chevron-right"></i>
            </button>`).join("");
    }

    async function openProfessionalStudent(studentId) {
        if (!hasAccess()) return;
        const requestVersion = state.version;
        state.loadingStudent = studentId;
        const dashboard = byId("professionalDashboard");
        const detail = byId("professionalStudentDetail");
        dashboard?.classList.add("hidden");
        detail?.classList.remove("hidden");
        if (detail) detail.innerHTML = '<div class="plans-loading" role="status"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>Carregando aluno...</span></div>';
        try {
            const [student, workouts] = await Promise.all([
                api(`/professional/students/${segment(studentId)}`),
                api(`/professional/students/${segment(studentId)}/workout-plans`)
            ]);
            if (requestVersion !== state.version || state.loadingStudent !== studentId) return;
            state.student = student;
            state.workoutPlans = workouts;
            renderProfessionalStudent();
        } catch (error) {
            if (requestVersion === state.version && state.loadingStudent === studentId && detail) detail.innerHTML = `<div class="empty-state"><p>${esc(error.message)}</p><button class="btn-secondary" onclick="openProfessionalStudent('${esc(studentId)}')">Tentar novamente</button><button type="button" class="btn-secondary" onclick="loadProfessionalDashboard()">Voltar</button></div>`;
        }
    }

    function profileFact(label, value, suffix = "") {
        return `<article><small>${esc(label)}</small><strong>${value == null || value === "" ? "Não informado" : `${esc(value)} ${esc(suffix)}`}</strong></article>`;
    }

    function openOfflineStudent(studentId = null) {
        if (!hasAccess()) return;
        state.rosterEditId = studentId;
        const student = studentId ? state.student : null;
        const profile = student?.profile || {};
        byId("professionalStudentModalTitle").textContent = student ? "Editar aluno" : "Cadastrar aluno";
        byId("rosterName").value = student?.username || "";
        byId("rosterAge").value = profile.age ?? "";
        byId("rosterWeight").value = profile.weight ?? "";
        byId("rosterHeight").value = profile.height ?? "";
        byId("rosterGender").value = profile.gender || "";
        byId("rosterGoal").value = profile.goal || "";
        byId("rosterActivity").value = profile.activity_level || "";
        byId("professionalStudentMessage").textContent = "";
        openAppModal(byId("professionalStudentModal"));
    }

    function closeOfflineStudent() { if (!state.saving) closeAppModal(byId("professionalStudentModal")); }

    async function saveOfflineStudent(event) {
        event.preventDefault();
        if (state.saving || !hasAccess()) return;
        const body = {
            name: byId("rosterName").value.trim(),
            profile: {
                age: Number(byId("rosterAge").value),
                weight: Number(byId("rosterWeight").value),
                height: Number(byId("rosterHeight").value),
                gender: byId("rosterGender").value,
                goal: byId("rosterGoal").value.trim(),
                activity_level: byId("rosterActivity").value
            }
        };
        const message = byId("professionalStudentMessage");
        state.saving = true;
        setSaving(true);
        try {
            const path = state.rosterEditId
                ? `/professional/students/${segment(state.rosterEditId)}`
                : "/professional/students";
            const result = await api(path, { method: state.rosterEditId ? "PUT" : "POST", body });
            closeAppModal(byId("professionalStudentModal"));
            showToast(state.rosterEditId ? "Cadastro atualizado." : "Aluno cadastrado.", "success");
            await loadProfessionalDashboard();
            if (state.rosterEditId) openProfessionalStudent(result.student.id);
        } catch (error) {
            if (message) message.textContent = error.message;
        } finally { state.saving = false; setSaving(false); }
    }

    function openProfessionalInviteForStudent() {
        if (!state.student?.is_offline) return;
        state.inviteStudentId = state.student.id;
        openProfessionalInvite(true);
    }

    function openProfessionalInvite(forRosterStudent = false) {
        if (!hasAccess()) return;
        if (!forRosterStudent) state.inviteStudentId = null;
        byId("professionalInviteResult")?.classList.add("hidden");
        if (byId("professionalInviteMessage")) byId("professionalInviteMessage").textContent = "";
        openAppModal(byId("professionalInviteModal"));
    }

    function closeProfessionalInvite() { closeAppModal(byId("professionalInviteModal")); }

    async function generateProfessionalInvite() {
        if (!hasAccess() || byId("professionalInviteGenerate")?.disabled) return;
        const button = byId("professionalInviteGenerate");
        if (button) button.disabled = true;
        try {
            const invitePath = state.inviteStudentId
                ? `/professional/students/${segment(state.inviteStudentId)}/invitation`
                : "/professional/invitations";
            const data = await api(invitePath, { method: "POST", body: {} });
            const link = new URL(data.invite_path, window.location.origin).toString();
            byId("professionalInviteLink").value = link;
            byId("professionalInviteResult")?.classList.remove("hidden");
            if (byId("professionalInviteMessage")) byId("professionalInviteMessage").textContent = "Link criado. Ele expira em 7 dias.";
            if (state.inviteStudentId) await openProfessionalStudent(state.inviteStudentId);
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
        const text = `Olá! Use este link para criar ou acessar sua conta e aceitar meu acompanhamento no Fit-Tracker.AI:\n${byId("professionalInviteLink").value}`;
        window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener");
    }

    async function revokeProfessionalStudent() {
        if (!hasAccess() || !state.student || !window.confirm("Encerrar o vínculo com este aluno? Os planos publicados continuarão na conta dele.")) return;
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
    }

    async function createManualProfessionalPlan(type) {
        if (state.saving) return;
        if (!hasAccess() || !state.student || type !== "workout") return;
        try { await ensureExercises(); } catch (error) { showToast(error.message, "error"); return; }
        state.editor = { type, planId: null, questionnaire: defaultQuestionnaire(type), plan: null };
        renderProfessionalEditor();
        openAppModal(byId("professionalPlanEditorModal"));
    }

    async function editProfessionalPlan(type, planId) {
        if (!hasAccess() || !state.student || type !== "workout") return;
        try { await ensureExercises(); } catch (error) { showToast(error.message, "error"); return; }
        try {
            const plan = await api(`/professional/students/${segment(state.student.id)}/workout-plans/${segment(planId)}`);
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

    const goalLabels = { hypertrophy: "Hipertrofia", strength: "Força", conditioning: "Condicionamento", fat_loss: "Perda de gordura", mobility: "Mobilidade" };
    const experienceLabels = { beginner: "Iniciante", intermediate: "Intermediário", advanced: "Avançado" };
    const equipmentLabels = { barbell: "Barra", dumbbell: "Halteres", machine: "Máquina", cable: "Polia", bodyweight: "Peso corporal", bench: "Banco", kettlebell: "Kettlebell", resistance_band: "Elástico", pullup_bar: "Barra fixa", ez_bar: "Barra W", stability_ball: "Bola suíça", jump_rope: "Corda", elliptical: "Elíptico", stationary_bike: "Bicicleta ergométrica", "assisted": "Com assistência", "assisted (towel)": "Com assistência e toalha", "band": "Elástico", "barbell": "Barra", "body weight": "Peso corporal", "body weight (with resistance band)": "Peso corporal com elástico", "bosu ball": "Bola Bosu", "cable": "Polia", "dumbbell": "Halteres", "dumbbell (used as handles for deeper range)": "Halteres como apoio para maior amplitude", "dumbbell, exercise ball": "Halteres e bola suíça", "dumbbell, exercise ball, tennis ball": "Halteres, bola suíça e bola de tênis", "elliptical machine": "Elíptico", "ez barbell": "Barra W", "ez barbell, exercise ball": "Barra W e bola suíça", "hammer": "Marreta", "kettlebell": "Kettlebell", "leverage machine": "Máquina", "medicine ball": "Bola medicinal", "olympic barbell": "Barra olímpica", "resistance band": "Elástico", "roller": "Rolo", "rope": "Corda", "skierg machine": "Máquina SkiErg", "sled machine": "Trenó", "smith machine": "Máquina Smith", "stability ball": "Bola suíça", "stationary bike": "Bicicleta ergométrica", "stepmill machine": "Escada ergométrica", "tire": "Pneu", "trap bar": "Barra hexagonal", "upper body ergometer": "Ergômetro de braços", "weighted": "Com carga adicional", "wheel roller": "Roda abdominal" };

    function renderProfessionalEditor() {
        const editor = state.editor;
        editor.step = 0;
        editor.activeDay = 0;
        editor.dirty = false;
        byId("professionalPlanEditorTitle").textContent = editor.planId ? "Editar treino" : "Montar treino";
        byId("professionalPlanEditorKicker").textContent = "Estúdio de treinos";
        byId("professionalPlanEditorMessage").classList.remove("is-saving");
        byId("professionalPlanEditorMessage").textContent = "";
        byId("professionalBuilderContext").innerHTML = `<span>Plano de <strong>${esc(state.student.username)}</strong></span><span class="professional-app-status"><i class="fas fa-${state.student.is_offline ? "link" : "circle-check"}" aria-hidden="true"></i> ${state.student.is_offline ? "Aguardando vínculo com o app" : "Aluno vinculado ao app"}</span>`;
        byId("professionalPlanEditorBody").innerHTML = workoutEditorHtml(editor);
        updateProfessionalEditorStep();
        selectProfessionalDay(0);
    }

    function workoutEditorHtml(editor) {
        const questionnaire = editor.questionnaire;
        const plan = editor.plan || {};
        const dayCount = Number(plan.days?.length || questionnaire.days_per_week || 2);
        const days = plan.days?.length ? plan.days : Array.from({ length: dayCount }, () => ({ exercises: [] }));
        return `<section data-builder-step="0">
            <div class="professional-step-heading"><span class="content-kicker">01 · O ponto de partida</span><h4>Um plano com a cara do seu aluno.</h4><p>Defina o objetivo e a rotina. Na próxima etapa, você escolhe cada exercício.</p></div>
            <div class="professional-editor-basics">
                <label>Nome do plano<input id="editorTitle" maxlength="100" required value="${esc(plan.title || `Treino de ${state.student.username}`)}" placeholder="Ex.: Hipertrofia · Ciclo 1"></label>
                ${selectField("Objetivo", "editorGoal", questionnaire.goal, goalLabels)}
                ${selectField("Experiência do aluno", "editorExperience", questionnaire.experience_level, experienceLabels)}
                ${selectField("Treinos por semana", "editorDays", dayCount, { 1: "1 treino", 2: "2 treinos", 3: "3 treinos", 4: "4 treinos", 5: "5 treinos", 6: "6 treinos", 7: "7 treinos" }, 'onchange="professionalEditorDaysChanged()"')}
                ${selectField("Duração de cada treino", "editorDuration", questionnaire.session_duration, { 20: "20 minutos", 30: "30 minutos", 45: "45 minutos", 60: "60 minutos", 75: "75 minutos", 90: "90 minutos" })}
                <label class="professional-plan-description"><span>Orientações para o aluno <small>Opcional · aparece no plano</small></span><textarea id="editorDescription" rows="3" maxlength="1000" placeholder="Ex.: Priorize a execução e respeite os intervalos de descanso.">${esc(plan.description || "")}</textarea></label>
            </div>
            <div class="professional-delivery-note"><i class="fas fa-mobile-screen-button" aria-hidden="true"></i><div><strong>Do seu planejamento para o app do aluno</strong><p>Você monta e revisa aqui. Depois do envio, o aluno escolhe os dias da semana e ativa o plano no app.</p></div></div>
        </section>
        <section data-builder-step="1" hidden>
            <div class="professional-step-heading"><span class="content-kicker">02 · A prescrição</span><h4>Monte um dia de cada vez.</h4><p>Escolha um treino, adicione exercícios e ajuste a prescrição. A ordem da lista será a ordem no app.</p></div>
            <nav id="professionalDayTabs" class="professional-day-tabs" aria-label="Dias do plano"></nav>
            <div class="professional-builder-layout"><div id="professionalWorkoutDays" class="professional-editor-days">${days.map((day, index) => workoutDayHtml(day, index)).join("")}</div>
                <aside class="professional-catalog" aria-labelledby="professionalCatalogTitle"><span class="content-kicker">Biblioteca</span><h4 id="professionalCatalogTitle">Adicionar exercício</h4><p id="professionalCatalogTarget"></p>
                    <label class="professional-catalog-search">Buscar exercício<input id="professionalExerciseSearch" type="search" placeholder="Ex.: agachamento, supino…" oninput="filterProfessionalExercises()"></label>
                    ${selectField("Grupo muscular", "professionalMuscleFilter", "", { "": "Todos os grupos", ...Object.fromEntries([...new Set(state.exercises.map(item => item.primary_muscle).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pt-BR")).map(muscle => [muscle, muscle])) }, 'onchange="filterProfessionalExercises()"')}
                    <p id="professionalCatalogCount" class="professional-catalog-count" role="status"></p><div id="professionalCatalogResults"></div>
                </aside>
            </div>
        </section>
        <section data-builder-step="2" hidden><div class="professional-step-heading"><span class="content-kicker">03 · Tudo pronto?</span><h4>Confira o que o aluno vai receber.</h4><p>Revise os exercícios e as orientações antes de salvar ou enviar.</p></div><div id="professionalWorkoutReview"></div></section>`;
    }

    function workoutDayHtml(day, dayIndex) {
        const letter = String.fromCharCode(65 + dayIndex);
        return `<section class="professional-editor-day" data-day-index="${dayIndex}"${dayIndex ? " hidden" : ""}>
            <div class="professional-day-heading"><span class="professional-day-letter">${letter}</span><h4>Treino ${letter}</h4></div>
            <header><label>Nome do treino<input id="dayTitle-${dayIndex}" maxlength="100" required value="${esc(day.title || `Treino ${letter}`)}" oninput="refreshProfessionalDayTabs()" placeholder="Ex.: Inferiores A"></label><label><span>Foco do dia <small>Opcional</small></span><input id="dayFocus-${dayIndex}" maxlength="200" value="${esc(day.focus || "")}" placeholder="Ex.: Quadríceps e glúteos"></label></header>
            <div class="professional-exercise-rows">${asArray(day.exercises).map((exercise, index) => workoutExerciseHtml(exercise, index)).join("")}</div>
            <div class="professional-day-empty"${asArray(day.exercises).length ? " hidden" : ""}><i class="fas fa-dumbbell" aria-hidden="true"></i><strong>Vamos começar o treino ${letter}?</strong><p>Busque um exercício na biblioteca e toque em + para adicionar.</p></div>
            <button type="button" class="btn-secondary professional-add-exercise" onclick="focusProfessionalCatalog()"><i class="fas fa-plus" aria-hidden="true"></i> Buscar exercício para este treino</button>
        </section>`;
    }

    function workoutExerciseHtml(exercise, exerciseIndex) {
        return `<div class="professional-exercise-row" data-exercise-source="${esc(JSON.stringify(exercise))}">
            <div class="professional-exercise-heading"><span class="professional-exercise-number">${exerciseIndex + 1}</span><div><strong>${esc(exercise.name)}</strong><small>${esc(exercise.primary_muscle || "Exercício do plano")} · ${esc(equipmentLabels[String(exercise.equipment).toLowerCase()] || exercise.equipment || "Sem equipamento informado")}</small></div>
                <div class="professional-exercise-actions"><button type="button" class="btn-secondary" onclick="moveProfessionalExercise(this, -1)" aria-label="Mover ${esc(exercise.name)} para cima"><i class="fas fa-arrow-up" aria-hidden="true"></i></button><button type="button" class="btn-secondary" onclick="moveProfessionalExercise(this, 1)" aria-label="Mover ${esc(exercise.name)} para baixo"><i class="fas fa-arrow-down" aria-hidden="true"></i></button><button type="button" class="btn-secondary professional-remove" onclick="removeProfessionalExercise(this)" aria-label="Remover ${esc(exercise.name)}"><i class="fas fa-trash" aria-hidden="true"></i></button></div>
            </div>
            <select class="exercise-key" hidden><option value="${esc(exercise.catalog_key)}" data-exercise-name="${esc(exercise.name)}" selected>${esc(exercise.name)}</option></select>
            <div class="professional-prescription"><label>Séries<input class="exercise-sets" type="number" min="1" max="10" step="1" required value="${esc(exercise.sets ?? 3)}"></label><label>Repetições<input class="exercise-reps" maxlength="30" value="${esc(exercise.reps ?? "8-12")}" placeholder="Ex.: 8-12" required></label><label>Descanso (s)<input class="exercise-rest" type="number" min="0" max="600" step="1" required value="${esc(exercise.rest_seconds ?? 60)}"></label><label><span>Carga <small>Opcional</small></span><input class="exercise-weight" maxlength="50" value="${esc(exercise.weight || "")}" placeholder="Ex.: 20 kg"></label></div>
            <label class="professional-exercise-note"><span>Orientação de execução <small>Opcional</small></span><input class="exercise-notes" maxlength="500" value="${esc(exercise.notes || "")}" placeholder="Ex.: Controle a descida e evite compensar com o tronco."></label>
        </div>`;
    }

    function selectField(label, id, selected, options, attributes = "") {
        return `<label>${esc(label)}<select id="${id}" ${attributes}>${Object.entries(options).map(([value, text]) => `<option value="${esc(value)}"${String(selected) === value ? " selected" : ""}>${esc(text)}</option>`).join("")}</select></label>`;
    }

    function updateProfessionalEditorStep() {
        const step = state.editor.step;
        byId("professionalPlanEditorBody").querySelectorAll("[data-builder-step]").forEach(panel => { panel.hidden = Number(panel.dataset.builderStep) !== step; });
        byId("professionalPlanEditorForm").querySelectorAll("[data-builder-nav]").forEach(button => {
            if (Number(button.dataset.builderNav) === step) button.setAttribute("aria-current", "step");
            else button.removeAttribute("aria-current");
        });
        byId("professionalEditorBack").hidden = step === 0;
        byId("professionalEditorNext").hidden = step === 2;
        byId("professionalEditorNext").textContent = step === 0 ? "Montar treinos →" : "Revisar treino →";
        byId("professionalEditorSend").hidden = step !== 2 || state.student.is_offline;
        byId("professionalSaveNote").textContent = state.student.is_offline ? "Salve o rascunho. Para enviar, o aluno precisa aceitar seu convite." : "O rascunho fica visível só para você. Envie quando estiver pronto.";
    }

    function setProfessionalEditorStep(step) {
        if (!state.editor || state.saving || step < 0 || step > 2) return;
        if (step > 0 && !byId("editorTitle").value.trim()) {
            byId("professionalPlanEditorMessage").textContent = "Dê um nome ao plano para continuar.";
            byId("editorTitle").focus();
            return;
        }
        if (step === 2 && !validateProfessionalEditor()) return;
        state.editor.step = step;
        byId("professionalPlanEditorMessage").textContent = "";
        if (step === 2) renderProfessionalWorkoutReview();
        updateProfessionalEditorStep();
        const heading = byId("professionalPlanEditorBody").querySelector(`[data-builder-step="${step}"] h4`);
        if (heading) { heading.tabIndex = -1; heading.focus(); }
    }

    function refreshProfessionalDayTabs() {
        const days = Array.from(byId("professionalWorkoutDays").querySelectorAll(".professional-editor-day"));
        byId("professionalDayTabs").innerHTML = days.map((day, index) => {
            const count = day.querySelectorAll(".professional-exercise-row").length;
            return `<button type="button" aria-pressed="${index === state.editor.activeDay}" onclick="selectProfessionalDay(${index})"><span>${String.fromCharCode(65 + index)}</span><strong>${esc(byId(`dayTitle-${index}`).value || `Treino ${index + 1}`)}</strong><small>${count} ${count === 1 ? "exercício" : "exercícios"}</small></button>`;
        }).join("");
        byId("professionalCatalogTarget").textContent = `Adicionando em ${byId(`dayTitle-${state.editor.activeDay}`).value || `Treino ${state.editor.activeDay + 1}`}`;
    }

    function selectProfessionalDay(index) {
        state.editor.activeDay = index;
        byId("professionalWorkoutDays").querySelectorAll(".professional-editor-day").forEach((day, dayIndex) => { day.hidden = dayIndex !== index; });
        refreshProfessionalDayTabs();
        refreshProfessionalExercises();
        filterProfessionalExercises();
    }

    function focusProfessionalCatalog() {
        byId("professionalExerciseSearch").focus();
        byId("professionalExerciseSearch").scrollIntoView({ block: "nearest", behavior: "instant" });
    }

    const searchText = (value) => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    function filterProfessionalExercises(reset = true) {
        if (!state.editor) return;
        if (reset) state.editor.catalogLimit = 60;
        const query = searchText(byId("professionalExerciseSearch").value.trim());
        const muscle = byId("professionalMuscleFilter").value;
        const dayIndex = state.editor.activeDay;
        const day = byId("professionalWorkoutDays").querySelector(`[data-day-index="${dayIndex}"]`);
        const keys = new Set(Array.from(day?.querySelectorAll(".exercise-key") || []).map(input => input.value));
        const matches = state.exercises.filter(item => (!muscle || item.primary_muscle === muscle) && searchText(`${item.name} ${asArray(item.aliases).join(" ")} ${item.primary_muscle} ${equipmentLabels[String(item.equipment).toLowerCase()] || item.equipment}`).includes(query));
        const visibleCount = Math.min(state.editor.catalogLimit, matches.length);
        byId("professionalCatalogTarget").textContent = `Adicionando em ${byId(`dayTitle-${dayIndex}`).value || `Treino ${dayIndex + 1}`}`;
        byId("professionalCatalogCount").textContent = keys.size >= 12 ? "Limite de 12 exercícios neste treino. Remova um para adicionar outro." : `${matches.length} exercícios encontrados · ${visibleCount} exibidos`;
        byId("professionalCatalogResults").innerHTML = matches.length ? matches.slice(0, visibleCount).map(item => {
            const added = keys.has(item.catalog_key);
            return `<button type="button" class="professional-catalog-item" data-catalog-key="${esc(item.catalog_key)}" onclick="addProfessionalExercise(${dayIndex}, this.dataset.catalogKey)"${added || keys.size >= 12 ? " disabled" : ""} aria-label="${added ? "Já adicionado:" : "Adicionar"} ${esc(item.name)}"><div><strong>${esc(item.name)}</strong><small>${esc(item.primary_muscle || "Geral")} · ${esc(equipmentLabels[String(item.equipment).toLowerCase()] || item.equipment || "Livre")}</small></div><i class="fas fa-${added ? "check" : "plus"}" aria-hidden="true"></i></button>`;
        }).join("") + (matches.length > visibleCount ? '<button id="professionalCatalogMore" type="button" class="btn-secondary professional-catalog-more" onclick="showMoreProfessionalExercises()">Mostrar mais exercícios</button>' : "") : '<div class="professional-catalog-empty"><i class="fas fa-search" aria-hidden="true"></i><strong>Nenhum exercício encontrado</strong><p>Tente outro nome ou selecione todos os grupos musculares.</p></div>';
    }

    function showMoreProfessionalExercises() {
        state.editor.catalogLimit += 60;
        filterProfessionalExercises(false);
    }

    function addProfessionalExercise(dayIndex, key) {
        if (state.saving) return;
        const rows = byId("professionalWorkoutDays").querySelector(`[data-day-index="${dayIndex}"] .professional-exercise-rows`);
        const exercise = state.exercises.find(item => item.catalog_key === key);
        if (!rows || !exercise || rows.children.length >= 12 || Array.from(rows.querySelectorAll(".exercise-key")).some(input => input.value === key)) return;
        rows.insertAdjacentHTML("beforeend", workoutExerciseHtml(exercise, rows.children.length));
        state.editor.dirty = true;
        byId("professionalPlanEditorMessage").textContent = "";
        selectProfessionalDay(dayIndex);
        byId("professionalExerciseSearch").focus();
    }

    function refreshProfessionalExercises() {
        byId("professionalWorkoutDays").querySelectorAll(".professional-editor-day").forEach(day => {
            const rows = day.querySelectorAll(".professional-exercise-row");
            day.querySelector(".professional-day-empty").hidden = rows.length > 0;
            rows.forEach((row, index) => {
                row.querySelector(".professional-exercise-number").textContent = index + 1;
                const buttons = row.querySelectorAll(".professional-exercise-actions button");
                buttons[0].disabled = index === 0;
                buttons[1].disabled = index === rows.length - 1;
            });
            day.querySelector(".professional-add-exercise").hidden = rows.length >= 12;
        });
    }

    function moveProfessionalExercise(button, direction) {
        if (state.saving) return;
        const row = button.closest(".professional-exercise-row");
        const sibling = direction < 0 ? row.previousElementSibling : row.nextElementSibling;
        if (!sibling) return;
        if (direction < 0) row.parentElement.insertBefore(row, sibling);
        else row.parentElement.insertBefore(sibling, row);
        state.editor.dirty = true;
        refreshProfessionalExercises();
    }

    function removeProfessionalExercise(button) {
        if (state.saving) return;
        button.closest(".professional-exercise-row").remove();
        state.editor.dirty = true;
        selectProfessionalDay(state.editor.activeDay);
    }

    function professionalEditorDaysChanged() {
        if (!state.editor || state.saving) return;
        const count = Number(byId("editorDays").value);
        const container = byId("professionalWorkoutDays");
        const current = Array.from(container.querySelectorAll(".professional-editor-day"));
        if (current.slice(count).some(day => day.querySelectorAll(".professional-exercise-row").length) && !window.confirm("Diminuir a quantidade de treinos remove os últimos dias e seus exercícios. Continuar?")) {
            byId("editorDays").value = current.length;
            return;
        }
        current.slice(count).forEach(day => day.remove());
        for (let index = current.length; index < count; index += 1) container.insertAdjacentHTML("beforeend", workoutDayHtml({}, index));
        state.editor.dirty = true;
        selectProfessionalDay(Math.min(state.editor.activeDay, count - 1));
    }

    function collectEditorPayload() {
        const editor = state.editor;
        const days = Array.from(byId("professionalWorkoutDays").querySelectorAll(".professional-editor-day")).map((day, dayIndex) => ({
            code: String.fromCharCode(65 + dayIndex),
            title: day.querySelector(`[id="dayTitle-${dayIndex}"]`).value.trim(),
            focus: day.querySelector(`[id="dayFocus-${dayIndex}"]`).value.trim(),
            exercises: Array.from(day.querySelectorAll(".professional-exercise-row")).map(row => ({
                ...JSON.parse(row.dataset?.exerciseSource || "{}"),
                catalog_key: row.querySelector(".exercise-key").value,
                name: row.querySelector(".exercise-key").selectedOptions[0]?.dataset.exerciseName,
                sets: Number(row.querySelector(".exercise-sets").value || NaN), reps: row.querySelector(".exercise-reps").value.trim(),
                rest_seconds: Number(row.querySelector(".exercise-rest").value || NaN), weight: row.querySelector(".exercise-weight").value.trim(), notes: row.querySelector(".exercise-notes").value.trim()
            }))
        }));
        const daysPerWeek = Number(byId("editorDays").value);
        const original = editor.questionnaire;
        const defaultSplit = { 1: "full_body", 2: "full_body", 3: "abc", 4: "abcd", 5: "abcde", 6: "abc", 7: "full_body" }[daysPerWeek];
        return { questionnaire: { ...original, goal: byId("editorGoal").value, experience_level: byId("editorExperience").value, days_per_week: daysPerWeek, split_type: daysPerWeek === Number(original.days_per_week) ? original.split_type || defaultSplit : defaultSplit, session_duration: Number(byId("editorDuration").value) }, plan: { type: "workout_plan", title: byId("editorTitle").value.trim(), description: byId("editorDescription").value.trim(), days } };
    }

    function validateProfessionalEditor() {
        const payload = collectEditorPayload();
        let issue = !payload.plan.title ? { step: 0, message: "Dê um nome ao plano para continuar.", selector: "#editorTitle" } : null;
        payload.plan.days.forEach((day, index) => {
            if (issue) return;
            if (!day.exercises.length) issue = { step: 1, day: index, message: `Adicione pelo menos um exercício ao ${day.title || `treino ${index + 1}`}.`, selector: ".professional-add-exercise" };
            else if (!day.title) issue = { step: 1, day: index, message: `Dê um nome ao treino ${index + 1}.`, selector: `#dayTitle-${index}` };
            else if (day.exercises.some(item => !Number.isInteger(item.sets) || item.sets < 1 || item.sets > 10 || !item.reps || item.reps.length > 30 || !Number.isInteger(item.rest_seconds) || item.rest_seconds < 0 || item.rest_seconds > 600)) issue = { step: 1, day: index, message: `Confira ${day.title}: use de 1 a 10 séries, informe as repetições e um descanso entre 0 e 600 segundos.`, selector: "input:invalid" };
        });
        if (!issue) return true;
        state.editor.step = issue.step;
        updateProfessionalEditorStep();
        if (issue.day !== undefined) selectProfessionalDay(issue.day);
        byId("professionalPlanEditorMessage").textContent = issue.message;
        const scope = issue.day === undefined ? byId("professionalPlanEditorBody") : byId("professionalWorkoutDays").querySelector(`[data-day-index="${issue.day}"]`);
        scope.querySelector(issue.selector)?.focus();
        return false;
    }

    function renderProfessionalWorkoutReview() {
        const { plan, questionnaire } = collectEditorPayload();
        const exerciseCount = plan.days.reduce((count, day) => count + day.exercises.length, 0);
        byId("professionalWorkoutReview").innerHTML = `<div class="professional-review-summary"><span class="content-kicker">${esc(state.student.username)}</span><h4>${esc(plan.title)}</h4><p>${esc(plan.description || "Sem orientações gerais.")}</p><div class="professional-review-stats"><span><strong>${plan.days.length}</strong> treinos / semana</span><span><strong>${exerciseCount}</strong> exercícios</span><span><strong>${questionnaire.session_duration} min</strong> por treino</span><span>${esc(goalLabels[questionnaire.goal])} · ${esc(experienceLabels[questionnaire.experience_level])}</span></div></div>
            <div class="professional-review-days">${plan.days.map(day => `<section><h5>${esc(day.title)}</h5>${day.focus ? `<p>${esc(day.focus)}</p>` : ""}<ol>${day.exercises.map(item => `<li><strong>${esc(item.name)}</strong><span>${esc(item.sets)} × ${esc(item.reps)} · ${esc(item.rest_seconds)}s de descanso${item.weight ? ` · ${esc(item.weight)}` : ""}</span>${item.notes ? `<small>${esc(item.notes)}</small>` : ""}${item.effort_guidance ? `<small>${esc(item.effort_guidance)}</small>` : ""}</li>`).join("")}</ol></section>`).join("")}</div>
            <div class="professional-delivery-note${state.student.is_offline ? " is-offline" : ""}"><i class="fas fa-${state.student.is_offline ? "link" : "circle-check"}" aria-hidden="true"></i><div><strong>${state.student.is_offline ? "Salve agora. Envie depois do convite aceito." : "Pronto para chegar ao app."}</strong><p>${state.student.is_offline ? "Seu aluno ainda não está vinculado. Salve o rascunho, gere o convite no perfil do aluno e peça que ele aceite pelo site com a mesma conta do app." : "Ao enviar, o plano ficará disponível na biblioteca do aluno. No app, ele toca em Usar este plano, escolhe os dias e confirma a agenda."}</p></div></div>`;
    }

    async function saveProfessionalEditor(event, send = false) {
        event.preventDefault();
        if (state.saving || !hasAccess() || !state.editor || !state.student) return;
        if (send && (state.student.is_offline || state.editor.step !== 2)) return;
        if (!validateProfessionalEditor()) return;
        const editor = state.editor;
        const studentId = state.student.id;
        const path = `/professional/students/${segment(studentId)}/workout-plans`;
        const requestVersion = state.version;
        const message = byId("professionalPlanEditorMessage");
        let draftSaved = false;
        state.saving = true;
        setSaving(true);
        message.textContent = send ? "Salvando e enviando o treino…" : "Salvando rascunho…";
        try {
            const result = await api(`${path}${editor.planId ? `/${segment(editor.planId)}` : ""}`, { method: editor.planId ? "PUT" : "POST", body: collectEditorPayload() });
            editor.planId = result.plan?.id || editor.planId;
            editor.dirty = false;
            draftSaved = true;
            if (send) {
                try {
                    await api(`${path}/${segment(editor.planId)}/publish`, { method: "POST", body: {} });
                } catch (error) {
                    if (requestVersion !== state.version) throw error;
                    const confirmed = await api(`${path}/${segment(editor.planId)}`).catch(() => null);
                    if (confirmed?.status !== "published") throw error;
                }
                showToast("Treino enviado! O aluno já pode abrir o plano no app.", "success");
            } else showToast("Rascunho salvo. Você pode continuar depois pelo perfil do aluno.", "success");
            state.saving = false;
            closeAppModal(byId("professionalPlanEditorModal"));
            await openProfessionalStudent(studentId);
        } catch (error) {
            if (requestVersion === state.version) message.textContent = `${send && draftSaved ? "O rascunho está salvo. " : ""}${error.message}${Object.values(error.fields || {}).length ? ` ${Object.values(error.fields).join(" ")}` : ""}`;
        } finally {
            if (requestVersion === state.version) { state.saving = false; setSaving(false); refreshProfessionalExercises(); filterProfessionalExercises(); }
        }
    }

    function canCloseProfessionalEditor() {
        if (state.saving) return false;
        if (state.editor?.dirty && !window.confirm("Sair sem salvar as alterações deste treino?")) return false;
        if (state.editor) state.editor.dirty = false;
        return true;
    }

    function closeProfessionalPlanEditor() { closeAppModal(byId("professionalPlanEditorModal")); }

    async function openProfessionalPlan(type, planId) {
        if (!hasAccess() || !state.student) return;
        try {
            const plan = await api(`/professional/students/${segment(state.student.id)}/workout-plans/${segment(planId)}`);
            renderProfessionalPlanPreview(plan);
        } catch (error) { showToast(error.message, "error"); }
    }

    function renderProfessionalPlanPreview(plan) {
        const modal = byId("viewWorkoutPlanModal");
        const details = byId("viewWorkoutPlanDetails");
        const title = byId("viewWorkoutPlanTitle");
        if (title) title.textContent = plan.title;
        if (details) details.innerHTML = `<div class="professional-preview"><p>${esc(plan.description || "")}</p>${asArray(plan.days).map((day) => `<section><h4>${esc(day.title)}</h4><p>${esc(day.focus || "")}</p>${asArray(day.exercises).map((exercise) => `<article><strong>${esc(exercise.name)}</strong><span>${esc(exercise.sets)} × ${esc(exercise.reps)} · ${esc(exercise.rest_seconds)}s</span><small>${esc(exercise.notes || "")}</small></article>`).join("")}</section>`).join("")}</div>`;
        openAppModal(modal);
    }

    async function publishProfessionalPlan(type, planId) {
        if (!hasAccess() || !state.student || state.student.is_offline) return;
        if (state.publishing.has(planId)) return;
        if (!window.confirm("Enviar este treino ao app do aluno? Ele poderá escolher os dias e ativar o plano. Depois do envio, este plano não poderá mais ser editado.")) return;
        state.publishing.add(planId);
        try {
            await api(`/professional/students/${segment(state.student.id)}/workout-plans/${segment(planId)}/publish`, { method: "POST", body: {} });
            showToast("Treino enviado! O aluno pode escolher os dias e ativar o plano no app.", "success");
            openProfessionalStudent(state.student.id);
        } catch (error) { showToast(`${error.message} ${Object.values(error.fields || {}).join(" ")}`, "error"); } finally { state.publishing.delete(planId); }
    }

    async function handleInvitationFromUrl() {
        if (state.acceptingInvite) return;
        const params = new URLSearchParams(window.location.search);
        const token = params.get("invite");
        if (!token) return;
        if (!window.currentUser) {
            window.requireAuth?.("Entre ou crie sua conta para aceitar o convite do profissional.", { mode: "register", resume: handleInvitationFromUrl });
            return;
        }
        try {
            state.acceptingInvite = true;
            const details = await api(`/invitations/${segment(token)}`);
            if (!window.confirm(`Aceitar o acompanhamento de ${details.invitation.professional.username}? O profissional poderá consultar seus dados de acompanhamento e criar treinos para você.`)) return;
            await api(`/invitations/${segment(token)}/accept`, {
                method: "POST",
                body: {
                    data_sharing_consent: true,
                    data_sharing_consent_version: details.data_sharing_consent_version,
                },
            });
            const url = new URL(window.location.href);
            url.searchParams.delete("invite");
            window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
            showToast("Convite aceito.", "success");
        } catch (error) { showToast(error.message, "error"); } finally { state.acceptingInvite = false; }
    }


    function renderProfessionalStudent() {
        const student = state.student;
        const detail = byId("professionalStudentDetail");
        if (!student || !detail) return;
        detail.innerHTML = `<div class="professional-student-header"><button type="button" class="btn-secondary" onclick="loadProfessionalDashboard()">← Alunos</button><div><span class="content-kicker">${student.is_offline ? "Cadastro do personal" : "Aluno vinculado"}</span><h2>${esc(student.username)}</h2><p>${esc(student.profile?.goal || "Objetivo não informado")}</p></div>${student.is_offline ? `<button type="button" class="btn-secondary" onclick="openOfflineStudent('${esc(student.id)}')">Editar perfil</button><button type="button" class="btn-secondary" onclick="openProfessionalInviteForStudent()">Convidar para o app</button>` : `<button type="button" class="btn-secondary" onclick="revokeProfessionalStudent()">Desvincular</button>`}</div>
        <div class="professional-profile-grid">${profileFact("Idade", student.profile?.age, "anos")}${profileFact("Peso", student.profile?.weight, "kg")}${profileFact("Altura", student.profile?.height, "cm")}</div>
        <div class="professional-link-notice"><i class="fas fa-${student.is_offline ? "link" : "mobile-screen-button"}" aria-hidden="true"></i><p>${student.is_offline ? "Você já pode montar o treino. Para receber no app, o aluno precisa aceitar seu convite pelo site usando a mesma conta do aplicativo." : "Depois do envio, o aluno encontra o treino nos planos do app. Ele escolhe Usar este plano, seleciona os dias e confirma a agenda."}</p></div>
        <section class="professional-plan-section"><header><div><span class="content-kicker">Planejamento</span><h3>Planos de treino</h3></div><button type="button" class="btn-primary" onclick="createManualProfessionalPlan('workout')"><i class="fas fa-plus" aria-hidden="true"></i> Montar treino</button></header><p>Organize os dias, prescreva os exercícios e confira tudo antes de enviar.</p><div class="professional-plan-grid">${state.workoutPlans.length ? state.workoutPlans.map((plan) => planCard(plan, "workout")).join("") : '<div class="professional-plan-empty"><i class="fas fa-dumbbell" aria-hidden="true"></i><h4>O próximo treino começa aqui.</h4><p>Toque em Montar treino. Vamos guiar você do planejamento até a revisão para o aluno.</p></div>'}</div></section>`;
    }
    function hasAccess(user = window.currentUser) {
        return Boolean(user?.professional_entitled && ["workout", "both"].includes(user?.professional_scope) && !(window.Capacitor?.isNativePlatform?.()));
    }
    function setSaving(value) {
        byId("professionalPlanEditorMessage")?.classList.toggle("is-saving", value);
        ["professionalStudentForm", "professionalPlanEditorForm"].forEach((id) => {
            byId(id)?.querySelectorAll(id === "professionalPlanEditorForm" ? "button, input, select, textarea" : "button").forEach((control) => { control.disabled = value; });
        });
    }
    function sessionChanged(user) {
        if (state.owner !== user?.id || !hasAccess(user)) {
            state.owner = user?.id;
            state.version += 1;
            state.students = []; state.student = null; state.editor = null; state.exercises = [];
            state.saving = false;
            state.rosterEditId = null; state.inviteStudentId = null;
            ["professionalStats", "professionalStudents", "professionalStudentDetail"].forEach((id) => { if (byId(id)) byId(id).innerHTML = ""; });
            ["professionalPlanEditorBody", "professionalBuilderContext", "professionalWorkoutReview"].forEach((id) => { if (byId(id)) byId(id).innerHTML = ""; });
            ["professionalStudentModal", "professionalPlanEditorModal", "professionalInviteModal"].forEach((id) => { if (byId(id)) closeAppModal(byId(id)); });
        }
        if (!hasAccess(user)) byId("professionalTab")?.classList.add("hidden");
        byId("profileProfessionalDashboard")?.classList.toggle("hidden", !hasAccess(user));
    }
    window.ProfessionalWorkspace = { hasAccess, sessionChanged, canCloseEditor: canCloseProfessionalEditor, editorStep: () => state.editor?.step || 0 };


    Object.assign(window, { loadProfessionalDashboard, openProfessionalStudent, openOfflineStudent, closeOfflineStudent, saveOfflineStudent, openProfessionalInviteForStudent, openProfessionalInvite, closeProfessionalInvite, generateProfessionalInvite, copyProfessionalInvite, shareProfessionalInvite, revokeProfessionalStudent, createManualProfessionalPlan, editProfessionalPlan, setProfessionalEditorStep, selectProfessionalDay, refreshProfessionalDayTabs, filterProfessionalExercises, showMoreProfessionalExercises, focusProfessionalCatalog, moveProfessionalExercise, addProfessionalExercise, removeProfessionalExercise, professionalEditorDaysChanged, saveProfessionalEditor, closeProfessionalPlanEditor, openProfessionalPlan, publishProfessionalPlan });
    byId("professionalPlanEditorForm")?.addEventListener("submit", saveProfessionalEditor);
    byId("professionalPlanEditorForm")?.addEventListener("input", (event) => {
        if (state.editor && !state.saving && !["professionalExerciseSearch", "professionalMuscleFilter"].includes(event?.target?.id)) {
            state.editor.dirty = true;
            byId("professionalPlanEditorMessage").textContent = "";
        }
    });
    window.addEventListener("diettracker:auth-ready", (event) => { sessionChanged(event.detail?.user || window.currentUser); handleInvitationFromUrl(); });
    sessionChanged(window.currentUser);
}());
