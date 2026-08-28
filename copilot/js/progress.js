(function () {
    "use strict";

    const byId = (id) => document.getElementById(id);
    const esc = (value) => escapeHtml(value == null ? "" : String(value));
    const asArray = (value) => Array.isArray(value) ? value : [];

    async function api(path, options = {}) {
        const response = await fetch(`${API_BASE}${path}`, {
            method: options.method || "GET",
            credentials: "include",
            headers: options.body === undefined ? {} : { "Content-Type": "application/json" },
            body: options.body === undefined ? undefined : JSON.stringify(options.body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Não foi possível carregar seu progresso.");
        return data;
    }

    function utcDate(value) {
        const text = String(value || "");
        return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(text) ? text : `${text}Z`);
    }

    function durationLabel(seconds) {
        const minutes = Math.max(0, Math.round(Number(seconds || 0) / 60));
        if (minutes < 60) return `${minutes}min`;
        const hours = Math.floor(minutes / 60);
        const rest = minutes % 60;
        return rest ? `${hours}h${String(rest).padStart(2, "0")}` : `${hours}h`;
    }

    function dayLabel(date) {
        const today = new Date();
        const local = new Date(date.getFullYear(), date.getMonth(), date.getDate());
        const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
        const difference = Math.round((start - local) / 86400000);
        if (difference === 0) return "Hoje";
        if (difference === 1) return "Ontem";
        return date.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });
    }

    function renderActivityCard(activity) {
        const records = activity.personal_record_count
            ? `<span class="activity-pr"><i class="fas fa-trophy" aria-hidden="true"></i>${esc(activity.personal_record_count)} PR</span>`
            : "";
        return `<article class="activity-history-card" data-activity-id="${esc(activity.id)}" role="button" tabindex="0" aria-label="Abrir atividade ${esc(activity.workout_name)}"><div class="activity-history-card__icon"><i class="fas fa-dumbbell" aria-hidden="true"></i></div><div><span>${utcDate(activity.completed_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</span><h3>${esc(activity.workout_name)}</h3><p>${esc(durationLabel(activity.duration_seconds))} · ${esc(activity.exercises_performed)} exercícios · ${esc(activity.sets_performed)} séries</p>${records}</div><button type="button" class="activity-history-card__open" aria-label="Abrir atividade ${esc(activity.workout_name)}"><i class="fas fa-chevron-right" aria-hidden="true"></i></button></article>`;
    }

    function renderActivities(items) {
        const container = byId("activitiesList");
        if (!container) return;
        if (!items.length) {
            container.innerHTML = '<div class="plans-empty"><i class="fas fa-person-running" aria-hidden="true"></i><h3>Seu histórico começa no próximo treino</h3><p>Finalize uma sessão para ela aparecer automaticamente aqui.</p></div>';
            return;
        }
        const groups = new Map();
        items.forEach((item) => {
            const date = utcDate(item.completed_at);
            const key = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
            if (!groups.has(key)) groups.set(key, { date, items: [] });
            groups.get(key).items.push(item);
        });
        container.innerHTML = Array.from(groups.values()).map((group) => `<section class="activity-date-group"><h3>${esc(dayLabel(group.date))}</h3><div>${group.items.map(renderActivityCard).join("")}</div></section>`).join("");
    }

    async function loadActivities() {
        const container = byId("activitiesList");
        if (!container || !currentUser) return;
        container.innerHTML = '<div class="plans-loading"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>Carregando atividades...</span></div>';
        const token = progressRequestToken;
        try {
            const result = await api("/activities?limit=50");
            if (token !== progressRequestToken) return;
            renderActivities(asArray(result.items));
        } catch (error) {
            if (token !== progressRequestToken) return;
            container.innerHTML = `<p class="session-inline-error">${esc(error.message)}</p>`;
        }
    }

    async function deleteActivity(activityId) {
        if (!activityId || !window.confirm("Excluir esta atividade do histórico? Esta ação não pode ser desfeita.")) return;
        try {
            await api(`/activities/${encodeURIComponent(activityId)}`, { method: "DELETE" });
            showToast("Atividade excluída.", "success");
            window.closeAppModal?.(byId("viewWorkoutPlanModal"));
            window.loadWorkoutActivities?.();
            window.loadProgressOverview?.();
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    function renderWeekly(weekly) {
        const current = weekly?.current || {};
        if (!current.target) {
            const suggestion = weekly?.suggestion?.target_sessions || 3;
            return `<article class="progress-weekly-card"><div><span>Meta semanal</span><h3>Defina seu ritmo</h3><p>Escolha quantos treinos deseja concluir por semana.</p></div><div class="progress-weekly-form"><input type="number" min="1" max="14" value="${esc(suggestion)}" id="weeklyGoalTarget" aria-label="Treinos por semana"><button type="button" data-progress-action="save-weekly">Salvar meta</button></div></article>`;
        }
        const percentage = Math.min(100, (current.completed / current.target) * 100);
        return `<article class="progress-weekly-card"><div><span>Meta semanal</span><h3>${esc(current.completed)} / ${esc(current.target)} treinos</h3><p>${current.fulfilled ? "Meta da semana concluída." : "Cada atividade concluída aproxima você da meta."}</p></div><div class="progress-weekly-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${esc(current.target)}" aria-valuenow="${esc(current.completed)}"><i style="width:${percentage}%"></i></div><footer><strong><i class="fas fa-fire" aria-hidden="true"></i> ${esc(current.streak)} semanas</strong><button type="button" data-progress-action="edit-weekly">Alterar para próxima semana</button></footer></article>`;
    }

    function renderProgressOverview(result) {
        const container = byId("workoutProgressOverview");
        if (!container) return;
        const goal = result.exercise_goal;
        const recentPr = asArray(result.recent_personal_records)[0];
        const achievement = asArray(result.recent_achievements)[0];
        container.innerHTML = `<div class="progress-section-heading"><span>Seu progresso</span><h3>Consistência que pode ser medida</h3></div>${renderWeekly(result.weekly)}<div class="progress-mini-grid"><article><i class="fas fa-bullseye" aria-hidden="true"></i><span>Meta de exercício</span>${goal ? `<strong>${esc(goal.exercise_name)}</strong><p>${esc(goal.current_max_load || 0)} / ${esc(goal.target_load_kg)} kg</p>` : "<strong>Nenhuma meta ativa</strong><p>Defina uma meta pelo detalhe de uma atividade.</p>"}</article><article><i class="fas fa-trophy" aria-hidden="true"></i><span>PR recente</span>${recentPr ? `<strong>${esc(recentPr.exercise_name)}</strong><p>${esc(recentPr.load_kg)} kg × ${esc(recentPr.repetitions)}</p>` : "<strong>Construa seu histórico</strong><p>O primeiro resultado cria sua baseline.</p>"}</article><article><i class="fas fa-award" aria-hidden="true"></i><span>Achievement recente</span>${achievement ? `<strong>${esc(achievement.title)}</strong><p>${esc(achievement.description)}</p>` : "<strong>Primeiro Passo</strong><p>Conclua um treino para começar.</p>"}</article></div>`;
    }

    async function loadProgressOverview() {
        const container = byId("workoutProgressOverview");
        if (!container || !currentUser) return;
        container.innerHTML = '<div class="plans-loading"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>Calculando progresso...</span></div>';
        const token = progressRequestToken;
        try {
            const result = await api("/progress/overview");
            if (token !== progressRequestToken) return;
            renderProgressOverview(result);
        } catch (error) {
            if (token !== progressRequestToken) return;
            container.innerHTML = `<p class="session-inline-error">${esc(error.message)}</p>`;
        }
    }

    async function saveWeeklyGoal(target) {
        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
        try {
            await api("/progress/weekly", { method: "PUT", body: { target_sessions: Number(target), timezone } });
            showToast("Meta semanal salva.", "success");
            loadProgressOverview();
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    async function openExerciseProgress(exerciseKey) {
        showTab("activities");
        const panel = byId("exerciseProgressPanel");
        const list = byId("activitiesList");
        if (!panel) return;
        panel.classList.remove("hidden");
        if (list) list.classList.add("hidden");
        panel.innerHTML = '<div class="plans-loading"><i class="fas fa-spinner fa-spin"></i><span>Carregando exercício...</span></div>';
        try {
            const result = await api(`/progress/exercises/${encodeURIComponent(exerciseKey)}`);
            const records = asArray(result.records).filter((item) => item.is_highlighted || item.metric_type === "max_load").slice(-8).reverse();
            panel.innerHTML = `<button type="button" class="back-button" data-progress-action="close-exercise"><i class="fas fa-arrow-left"></i> Atividades</button><span class="content-kicker">Histórico do exercício</span><h2>${esc(result.exercise_name)}</h2><div class="exercise-progress-hero"><small>Maior carga</small><strong>${esc(result.max_load_kg)} kg</strong></div><h3>Evolução recente</h3><ol>${records.map((record) => `<li><i class="fas fa-trophy"></i><div><strong>${esc(record.load_kg)} kg × ${esc(record.repetitions)}</strong><span>${utcDate(record.achieved_at).toLocaleDateString("pt-BR")}</span></div></li>`).join("") || "<li>Nenhum recorde além da baseline.</li>"}</ol>`;
        } catch (error) {
            panel.innerHTML = `<p class="session-inline-error">${esc(error.message)}</p>`;
        }
    }

    document.addEventListener("click", (event) => {
        const deleteActivityButton = event.target.closest("[data-activity-delete-id]");
        if (deleteActivityButton) {
            deleteActivity(deleteActivityButton.dataset.activityDeleteId);
            return;
        }
        const activity = event.target.closest("[data-activity-id]");
        if (activity) window.openWorkoutActivity?.(activity.dataset.activityId);
        const action = event.target.closest("[data-progress-action]")?.dataset.progressAction;
        if (action === "save-weekly") saveWeeklyGoal(byId("weeklyGoalTarget")?.value);
        if (action === "edit-weekly") {
            const target = window.prompt("Nova meta semanal (válida a partir da próxima segunda-feira):", "3");
            if (target != null) saveWeeklyGoal(target);
        }
        if (action === "close-exercise") {
            byId("exerciseProgressPanel")?.classList.add("hidden");
            byId("activitiesList")?.classList.remove("hidden");
            loadActivities();
        }
    });

    let progressRequestToken = 0;

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        const activity = event.target.closest?.("[data-activity-id]");
        if (!activity || event.target.closest("[data-activity-delete-id]")) return;
        if (event.target !== activity) return;
        event.preventDefault();
        window.openWorkoutActivity?.(activity.dataset.activityId);
    });

    function clearWorkoutProgress() {
        progressRequestToken += 1;
        const overview = byId("workoutProgressOverview");
        if (overview) overview.replaceChildren();
        const panel = byId("exerciseProgressPanel");
        if (panel) panel.classList.add("hidden");
    }

    window.loadWorkoutActivities = loadActivities;
    window.loadProgressOverview = loadProgressOverview;
    window.openExerciseProgress = openExerciseProgress;
    window.clearWorkoutProgress = clearWorkoutProgress;
    window.deleteWorkoutActivity = deleteActivity;
})();
