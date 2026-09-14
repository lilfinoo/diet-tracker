(function () {
    "use strict";

    const byId = (id) => document.getElementById(id);
    const esc = (value) => escapeHtml(value == null ? "" : String(value));
    const asArray = (value) => Array.isArray(value) ? value : [];

    async function api(path, options = {}) {
        const response = await window.fetchWithTimeout(`${API_BASE}${path}`, {
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
        return `<article class="activity-history-card" data-activity-id="${esc(activity.id)}" role="button" tabindex="0" aria-label="Abrir atividade ${esc(activity.workout_name)}"><div class="activity-history-card__icon"><i class="fas fa-dumbbell" aria-hidden="true"></i></div><div><span>${utcDate(activity.completed_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</span><h3>${esc(activity.workout_name)}</h3><p>${esc(durationLabel(activity.duration_seconds))} · ${esc(activity.exercises_performed)} exercícios · ${esc(activity.sets_performed)} séries</p>${records}</div><span class="activity-history-card__open" aria-hidden="true"><i class="fas fa-chevron-right"></i></span></article>`;
    }

    function renderActivities(items) {
        const container = byId("activitiesList");
        if (!container) return;
        if (!items.length) {
            container.innerHTML = '<div class="plans-empty"><i class="fas fa-person-running" aria-hidden="true"></i><h3>Seu histórico começa no próximo treino</h3><p>Finalize uma sessão para ela aparecer automaticamente aqui.</p><button type="button" data-progress-action="go-training">Ver meus treinos</button></div>';
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

    let activities = [];
    let activitiesHasMore = false;
    let activitiesLoading = false;
    let activitiesToken = 0;
    let exerciseKeyOpen = null;
    const number = value => Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 2 });
    const dateLabel = value => new Date(`${value}T12:00:00`).toLocaleDateString("pt-BR");
    const retry = (message, action) => `<div class="progress-feedback" role="alert"><p>${esc(message)}</p><button type="button" data-progress-action="${action}">Tentar novamente</button></div>`;

    async function loadActivities(loadMore = false) {
        const container = byId("activitiesList");
        if (!container || !currentUser) return;
        if (loadMore && (activitiesLoading || !activitiesHasMore)) return;
        const request = ++activitiesToken;
        const token = progressRequestToken;
        const offset = loadMore ? activities.length : 0;
        if (!loadMore) {
            byId('activitiesTab')?.classList.remove('showing-performance');
            exerciseKeyOpen = null;
            byId('exerciseProgressPanel')?.classList.add('hidden');
            container.classList.remove('hidden');
            activities = [];
            container.innerHTML = '<div class="plans-loading"><span>Carregando atividades...</span></div>';
        } else {
            const button = container.querySelector('[data-progress-action="more-activities"]');
            if (button) { button.disabled = true; button.textContent = 'Carregando...'; }
        }
        activitiesLoading = true;
        try {
            const result = await api(`/activities?limit=20&offset=${offset}`);
            if (token !== progressRequestToken || request !== activitiesToken) return;
            const items = asArray(result.items);
            const firstNewId = items.find(item => !activities.some(existing => existing.id === item.id))?.id;
            activities = loadMore ? [...activities, ...items.filter(item => !activities.some(existing => existing.id === item.id))] : items;
            activitiesHasMore = Boolean(result.has_more);
            renderActivities(activities);
            if (activitiesHasMore) container.insertAdjacentHTML('beforeend', '<div class="profile-load-more"><button type="button" data-progress-action="more-activities">Carregar mais atividades</button></div>');
            if (loadMore && firstNewId != null) container.querySelector(`[data-activity-id="${firstNewId}"]`)?.focus();
        } catch (error) {
            if (token !== progressRequestToken || request !== activitiesToken) return;
            if (loadMore) renderActivities(activities);
            else container.innerHTML = '';
            container.insertAdjacentHTML('beforeend', retry(error.message, loadMore ? 'more-activities' : 'retry-activities'));
        } finally {
            if (request === activitiesToken) activitiesLoading = false;
        }
    }

    function recordLabel(record) {
        const types = {
            max_load: ['Carga', 'fa-weight-hanging', 'kg'],
            reps_at_load: ['Repetições', 'fa-repeat', 'repetições'],
            estimated_1rm: ['Força estimada', 'fa-chart-line', 'kg estimados'],
        };
        const kind = types[record.metric_type] ? record.metric_type : 'max_load';
        const [label, icon, unit] = types[kind];
        const value = record.new_value ?? record.load_kg;
        const gain = kind === 'reps_at_load' && record.previous_value != null ? `<small>+${number(value - record.previous_value)} reps com ${number(record.load_kg)} kg</small>` : '';
        return `<span class="record-kind record-kind--${kind}"><i class="fas ${icon}" aria-hidden="true"></i>${label}</span><span class="record-comparison">${record.previous_value != null ? `${number(record.previous_value)} → ` : ''}${number(value)} ${unit}</span>${gain}<small class="record-context">${kind === 'reps_at_load' ? `Com ${number(record.load_kg)} kg` : `${number(record.load_kg)} kg × ${esc(record.repetitions)} repetições`}${kind === 'estimated_1rm' ? ' · estimativa, não uma carga testada' : ''}${record.is_initial ? ' · primeira marca registrada' : ''}</small>`;
    }

    async function loadPersonalRecords() {
        const container = byId("personalRecordsList");
        if (!container || !currentUser) return;
        container.innerHTML = '<div class="plans-loading"><i class="fas fa-spinner fa-spin"></i><span>Carregando recordes...</span></div>';
        const token = progressRequestToken;
        try {
            const [records, highlights] = await Promise.all([
                api("/progress/personal-records?limit=100"),
                api("/profile/highlights"),
            ]);
            if (token !== progressRequestToken) return;
            const selected = new Set(asArray(highlights.selected)
                .filter((item) => item.target_kind === "personal_record")
                .map((item) => String(item.item?.code)));
            const items = asArray(records.items);
            container.innerHTML = items.length ? items.map((record) => {
                const pinned = selected.has(String(record.id));
                return `<article class="achievement-card is-unlocked"><div class="achievement-medallion"><i class="fas fa-trophy"></i></div><div class="achievement-card__body"><div class="achievement-card__eyebrow"><span>${record.is_initial ? "Primeiro recorde" : "Novo recorde"}</span><small>${utcDate(record.achieved_at).toLocaleDateString("pt-BR")}</small></div><h4>${esc(record.exercise_name)}</h4><p>${recordLabel(record)}</p></div><footer><button type="button" class="achievement-pin-action${pinned ? " is-selected" : ""}" data-record-pin="${esc(record.id)}"><i class="fas ${pinned ? "fa-check" : "fa-thumbtack"}"></i>${pinned ? "Fixado" : "Fixar no perfil"}</button></footer></article>`;
            }).join("") : '<div class="plans-empty"><i class="fas fa-trophy"></i><h3>Seu primeiro recorde está próximo</h3><p>Finalize um exercício com carga e repetições válidas.</p><button type="button" data-progress-action="go-training">Ver meus treinos</button></div>';
        } catch (error) {
            if (token !== progressRequestToken) return;
            container.innerHTML = retry(error.message, 'retry-records');
        }
    }

    async function toggleRecordPin(recordId) {
        try {
            const highlights = await api("/profile/highlights");
            const items = asArray(highlights.selected).map((item) => ({
                kind: item.target_kind,
                code: String(item.item?.code),
            }));
            const index = items.findIndex((item) => item.kind === "personal_record" && item.code === String(recordId));
            if (index >= 0) items.splice(index, 1);
            else {
                if (items.length >= Number(highlights.limit || 3)) throw new Error("Você pode fixar no máximo 3 destaques.");
                items.push({ kind: "personal_record", code: String(recordId) });
            }
            const result = await api("/profile/highlights", { method: "PUT", body: { items } });
            currentUser.profile_highlights = result.selected;
            renderProfileBadges(currentUser);
            showToast(index >= 0 ? "PR removido do perfil." : "PR fixado no perfil.", "success");
            loadPersonalRecords();
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    async function deleteActivity(activityId) {
        if (!activityId || !window.confirm("Excluir esta atividade do histórico? Esta ação não pode ser desfeita.")) return;
        const token = progressRequestToken;
        try {
            await api(`/activities/${encodeURIComponent(activityId)}`, { method: "DELETE" });
            if (token !== progressRequestToken) return;
            showToast("Atividade excluída.", "success");
            window.closeAppModal?.(byId("viewWorkoutPlanModal"));
            window.loadWorkoutActivities?.();
            window.loadProgressOverview?.();
            const highlights = await api("/profile/highlights");
            if (token !== progressRequestToken || !currentUser) return;
            currentUser.profile_highlights = highlights.selected;
            renderProfileBadges(currentUser);
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    function goalForm(kind, value = '', exerciseKey = '', exerciseName = '', firstWeekly = false) {
        const weekly = kind === 'weekly';
        return `<form class="progress-goal-form" data-goal-kind="${kind}" data-exercise-key="${esc(exerciseKey)}"><label>${weekly ? 'Treinos por semana' : `Meta de carga para ${esc(exerciseName)} (kg)`}<input name="target" type="text" inputmode="${weekly ? 'numeric' : 'decimal'}" value="${esc(value)}" required autocomplete="off" aria-describedby="${weekly ? 'weekly' : 'exercise'}GoalHelp"></label><small id="${weekly ? 'weekly' : 'exercise'}GoalHelp">${weekly ? firstWeekly ? 'De 1 a 14 treinos. Sua primeira meta vale nesta semana.' : 'De 1 a 14 treinos. Alterações valem na próxima segunda-feira.' : 'Informe uma carga maior que sua melhor marca. Exemplo: 27,5 kg.'}</small><p class="session-inline-error" role="alert" data-goal-error></p><div><button type="submit">Salvar meta</button><button type="button" data-progress-action="close-goal-form">Cancelar</button></div></form>`;
    }

    const progressIcon = name => `<i data-lucide="${name}" aria-hidden="true"></i>`;

    function renderWeekly(weekly) {
        const current = weekly?.current || {};
        const percentage = current.target ? Math.min(100, (current.completed / current.target) * 100) : 0;
        return `<article class="rhythm-card"><header>${progressIcon('dumbbell')}<h4>Treinos</h4></header><div class="rhythm-value"><strong aria-label="${esc(current.completed || 0)} de ${esc(current.target ?? 'nenhuma meta')} treinos">${esc(current.completed || 0)}<small>/${esc(current.target ?? '—')}</small></strong><span class="rhythm-ring${current.fulfilled ? ' is-complete' : ''}" style="--fill:${percentage}%" role="img" aria-label="${current.target ? `${esc(current.completed)} de ${esc(current.target)} treinos` : 'Sem meta definida'}">${progressIcon(current.fulfilled ? 'check' : 'dumbbell')}</span></div><p>${!current.target ? 'Sem meta definida' : current.fulfilled ? 'Meta cumprida' : 'Em andamento'}</p><button type="button" class="progress-text-action" data-progress-action="edit-weekly" aria-expanded="false" aria-controls="weeklyGoalEditor">${current.target ? 'Editar meta' : 'Definir meta'}${progressIcon('chevron-right')}</button></article>`;
    }

    function renderWeeklyEditor(weekly) {
        const current = weekly?.current || {};
        const scheduled = weekly?.scheduled_goal;
        const target = scheduled?.target_sessions || current.target || weekly?.suggestion?.target_sessions || 3;
        return `${scheduled ? `<p class="weekly-scheduled" role="status">${progressIcon('calendar-days')}<span>Nova meta: <strong>${esc(scheduled.target_sessions)} treinos por semana</strong> a partir de ${dateLabel(scheduled.effective_week_start)}.</span></p>` : ''}<div id="weeklyGoalEditor" class="hidden">${goalForm('weekly', target, '', '', !current.target)}</div>`;
    }

    function renderFoodRhythm(consistency, current) {
        const days = asArray(consistency?.days);
        const weekStart = current.week_start;
        const count = days.filter(day => day.date >= weekStart && day.diet_tracked).length;
        const markers = weekStart ? Array.from({length: 7}, (_, index) => {
            const date = new Date(`${weekStart}T12:00:00`);
            date.setDate(date.getDate() + index);
            const key = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
            const day = days.find(item => item.date === key);
            const status = key > consistency.end_date ? 'future' : day?.diet_tracked ? 'tracked' : day?.diet_states?.includes('pending') ? 'pending' : 'unknown';
            const labels = {future:'Dia futuro', tracked:'Acompanhado', pending:'Pendente', unknown:'Sem informação'};
            const symbols = {future:'·', tracked:'✓', pending:'○', unknown:'—'};
            return `<span class="food-day food-day--${status}" role="img" aria-label="${dateLabel(key)}: ${labels[status]}" title="${dateLabel(key)}: ${labels[status]}"><small>${['S','T','Q','Q','S','S','D'][index]}</small><b aria-hidden="true">${symbols[status]}</b></span>`;
        }).join('') : '';
        return `<article class="rhythm-card"><header>${progressIcon('utensils')}<h4>Alimentação</h4></header><strong class="food-count">${count}<small> ${count === 1 ? 'dia' : 'dias'}</small></strong><p>Acompanhados na semana</p><div class="food-week">${markers}</div><button type="button" class="progress-text-action" data-progress-action="view-consistency">Ver dias${progressIcon('chevron-right')}</button></article>`;
    }

    const dietStateLabels = {
        consumed_planned: 'Consumido conforme planejado', consumed_different: 'Diferente do planejado',
        skipped: 'Pulado', pending: 'Pendente', no_information: 'Sem informação',
        recorded_unclassified: 'Registro alimentar sem classificação de adesão',
    };
    let consistencyDays = [];

    function consistencyDayDescription(day) {
        return `${dateLabel(day.date)}. ${day.workout ? 'Treino concluído' : 'Sem treino registrado'}. Alimentação: ${asArray(day.diet_states).map(state => dietStateLabels[state]).join(', ')}.`;
    }

    function renderConsistencyCalendar(data) {
        consistencyDays = asArray(data?.days);
        if (!consistencyDays.length) return '';
        const trainingDays = consistencyDays.filter(day => day.workout).length;
        const foodDays = consistencyDays.filter(day => day.diet_tracked).length;
        return `<section class="constancy-calendar" aria-label="Calendário de constância"><h3>Constância dia a dia</h3><p>${dateLabel(data.start_date)} a ${dateLabel(data.end_date)}</p><p><strong>${trainingDays} dias com treino · ${foodDays} dias com acompanhamento alimentar</strong></p><p>T = treino · A = acompanhamento alimentar · P = apenas pendente · — = sem informação alimentar. Toque no dia para ver os estados.</p><div class="constancy-days"><span>Seg</span><span>Ter</span><span>Qua</span><span>Qui</span><span>Sex</span><span>Sáb</span><span>Dom</span>${consistencyDays.map(day => `<button type="button" data-constancy-date="${esc(day.date)}" aria-label="${esc(consistencyDayDescription(day))}" aria-pressed="false" aria-controls="constancyDayDetail"><span>${esc(day.date.slice(8))}/${esc(day.date.slice(5,7))}</span><strong><span class="${day.workout ? 'has-workout' : ''}">${day.workout ? 'T' : '·'}</span> <span class="${day.diet_tracked ? 'has-diet' : ''}">${day.diet_tracked ? 'A' : day.diet_states.includes('pending') ? 'P' : '—'}</span></strong></button>`).join('')}</div><div id="constancyDayDetail" aria-live="polite"><p>Selecione um dia. Dias sem informação não significam que você deixou de seguir a dieta.</p></div><p>O acompanhamento indica um resultado informado, inclusive quando a refeição foi pulada; não mede adesão ao plano.</p><div class="constancy-actions"><button type="button" data-progress-action="go-training">Ver treinos</button><button type="button" data-progress-action="go-diet">Acompanhar alimentação</button></div></section>`;
    }

    function renderConsistencyHistory(weekly) {
        const labels = {fulfilled: 'Cumprida', unfulfilled: 'Encerrada sem cumprir', in_progress: 'Em andamento', no_goal: 'Sem meta'};
        return `<details class="constancy-weeks"><summary>Metas nas últimas 8 semanas</summary><p>Semanas sem meta não são avaliadas. A semana em andamento ainda pode ser cumprida.</p><ul>${asArray(weekly?.history).slice().reverse().map(week => `<li><span>Semana de ${dateLabel(week.week_start)}<small>${esc(week.completed)} treinos${week.target == null ? '' : ` · meta ${esc(week.target)}`}</small></span><strong class="week-${esc(week.status)}">${labels[week.status] || 'Sem meta'}</strong></li>`).join('')}</ul></details>`;
    }

    let performanceOptions = [];
    let performanceItems = [];
    let performanceHasMore = false;
    let performanceLoading = false;
    let performanceRequest = 0;
    let overviewRequest = 0;
    let overviewCache = null;
    let overviewPromise = null;
    const OVERVIEW_CACHE_MS = 60_000;

    function performanceSets(session) {
        if (!session?.sets?.length) return '<p>Séries não informadas nesta sessão antiga.</p>';
        return `<p>${session.sets.length} ${session.sets.length === 1 ? 'série registrada' : 'séries registradas'}</p><ul class="performance-sets">${session.sets.map((set, index) => `<li>Série ${index + 1}: <strong>${set.load_kg == null ? 'Carga não informada' : `${number(set.load_kg)} kg`} × ${esc(set.repetitions)} repetições</strong>${set.is_warmup ? ' · aquecimento' : ''}</li>`).join('')}</ul>`;
    }

    function performanceDate(session) {
        return session.local_date ? dateLabel(session.local_date) : utcDate(session.completed_at).toLocaleDateString('pt-BR');
    }

    function renderBodyPreview(body) {
        const key = ['weight', 'body_fat', 'waist', 'chest', 'arm', 'thigh', 'muscle_mass'].find(field => body?.metrics?.[field]?.latest);
        if (!key) return `<article class="change-card"><span class="change-icon">${progressIcon('ruler')}</span><div><h4>Evolução corporal</h4><p>Sua primeira medição será o ponto inicial.</p><button type="button" class="progress-text-action" data-progress-action="go-body">Registrar medidas${progressIcon('chevron-right')}</button></div></article>`;
        const metric = body.metrics[key];
        const [label, unit] = bodyMetrics[key];
        const deltaUnit = key === 'body_fat' ? 'p.p.' : unit;
        const age = Math.floor((new Date().setHours(0,0,0,0) - new Date(`${metric.latest.date}T00:00:00`)) / 86400000);
        return `<article class="change-card"><span class="change-icon">${progressIcon('ruler')}</span><div><h4>${label} <small>· últimas medições</small></h4><strong class="body-preview-value">${metric.previous ? `${number(metric.previous.value)} → ` : ''}${number(metric.latest.value)} <small>${unit}</small></strong><p>${metric.previous ? `${metric.change === 0 ? 'Sem alteração' : `${metric.change > 0 ? '+' : '−'}${number(Math.abs(metric.change))} ${deltaUnit}`} · ${dateLabel(metric.previous.date)} → ${dateLabel(metric.latest.date)}` : `${dateLabel(metric.latest.date)} · ponto inicial`}</p>${age > 30 ? '<p class="progress-stale">Dado há mais de 30 dias</p>' : ''}<button type="button" class="progress-text-action" data-progress-action="go-body">Ver medidas${progressIcon('chevron-right')}</button></div></article>`;
    }

    function compactPerformanceSets(sets) {
        if (!sets.length) return '<p>Séries não informadas</p>';
        const groups = new Map();
        sets.forEach(set => {
            const key = JSON.stringify([set.load_kg, set.repetitions, Boolean(set.is_warmup)]);
            const group = groups.get(key) || {...set, count: 0};
            group.count += 1;
            groups.set(key, group);
        });
        const items = Array.from(groups.values());
        return `<div class="compact-sets">${items.slice(0,2).map(set => `<p><strong>${set.count} × ${esc(set.repetitions)} reps</strong> · ${set.load_kg == null ? 'carga não informada' : `${number(set.load_kg)} kg`}${set.is_warmup ? ' · aquecimento' : ''}</p>`).join('')}${items.length > 2 ? '<p>Mais séries no detalhe</p>' : ''}</div>`;
    }

    function renderRecentPerformance(recent) {
        if (!recent) return `<article class="change-card"><span class="change-icon">${progressIcon('activity')}</span><div><h4>Performance</h4><p>Seu próximo treino começa este histórico.</p><button type="button" class="progress-text-action" data-progress-action="go-training">Ver treino${progressIcon('chevron-right')}</button></div></article>`;
        const session = recent.sessions.items[0];
        return `<article class="change-card"><span class="change-icon">${progressIcon('activity')}</span><div><h4>${esc(recent.name)}</h4><p>Recente · ${performanceDate(session)} · ${session.sets.length} ${session.sets.length === 1 ? 'série' : 'séries'}</p>${compactPerformanceSets(session.sets)}<p class="compact-record">Recorde histórico: <strong>${recent.max_load_kg == null ? 'não registrado' : `${number(recent.max_load_kg)} kg`}</strong></p><button type="button" class="progress-text-action" data-progress-action="go-performance">Ver exercício${progressIcon('chevron-right')}</button></div></article>`;
    }

    function renderProgressOverview(result) {
        const container = byId("workoutProgressOverview");
        if (!container) return;
        performanceOptions = asArray(result.performance?.exercises);
        const current = result.weekly?.current || {};
        const goal = result.exercise_goal;
        container.innerHTML = `<section class="evolution-section"><h3>Seu ritmo</h3><div class="rhythm-grid">${renderWeekly(result.weekly)}${renderFoodRhythm(result.consistency, current)}</div>${renderWeeklyEditor(result.weekly)}</section><section class="evolution-section"><h3>Suas mudanças</h3>${renderBodyPreview(result.body)}${renderRecentPerformance(result.performance?.recent)}</section><section class="evolution-section progress-next"><h3>Próximo passo</h3><p>${!current.target ? 'Defina um ritmo que funcione para você.' : current.fulfilled ? 'Meta cumprida. Organize seu próximo treino.' : `Falta${current.target - current.completed === 1 ? '' : 'm'} ${Math.max(0, current.target - current.completed)} treino${current.target - current.completed === 1 ? '' : 's'} nesta semana.`}</p><button type="button" class="progress-primary-action" data-progress-action="${current.target ? 'go-training' : 'edit-weekly'}"${current.target ? '' : ' aria-expanded="false" aria-controls="weeklyGoalEditor"'}>${progressIcon(current.target ? 'dumbbell' : 'target')}${current.target ? 'Ver meu treino' : 'Definir meta'}${progressIcon('chevron-right')}</button><button type="button" class="progress-text-action" data-progress-action="go-diet">${progressIcon('utensils')}Acompanhar alimentação</button></section>${goal ? `<details class="progress-goal-detail"><summary>${progressIcon('target')}Meta de exercício · ${esc(goal.exercise_name)}</summary><p>Melhor carga: ${goal.current_max_load == null ? 'não registrada' : `${number(goal.current_max_load)} kg`} · meta ${number(goal.target_load_kg)} kg</p><details class="goal-cancel"><summary>Cancelar meta</summary><p>Seu histórico será preservado.</p><button type="button" data-cancel-goal="${esc(goal.id)}">Confirmar cancelamento</button><p data-cancel-error role="alert"></p></details></details>` : ''}<details class="evolution-consistency"><summary>${progressIcon('calendar-days')}Constância por dia e semana</summary><p class="food-legend">✓ Acompanhado · ○ Pendente · — Sem informação · · Futuro. Acompanhamento não é adesão ao plano.</p>${renderConsistencyCalendar(result.consistency)}${renderConsistencyHistory(result.weekly)}</details>`;
    }

    async function loadProgressOverview() {
        const container = byId("workoutProgressOverview");
        if (!container || !currentUser) return;
        const ownerId = String(currentUser.id);
        const fresh = overviewCache && overviewCache.ownerId === ownerId && Date.now() - overviewCache.at < OVERVIEW_CACHE_MS;
        if (fresh) {
            renderProgressOverview(overviewCache.data);
            return overviewCache.data;
        }
        if (!overviewCache || overviewCache.ownerId !== ownerId) {
            container.innerHTML = '<div class="plans-loading"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>Calculando progresso...</span></div>';
        } else {
            container.setAttribute("aria-busy", "true");
            container.insertAdjacentHTML("afterbegin", '<p class="progress-refresh" role="status">Atualizando…</p>');
        }
        if (overviewPromise) return overviewPromise;
        const token = progressRequestToken;
        const request = ++overviewRequest;
        overviewPromise = (async () => {
        try {
            const result = await api("/progress/overview?view=summary");
            if (token !== progressRequestToken || request !== overviewRequest) return;
            overviewCache = { ownerId, at: Date.now(), data: result };
            renderProgressOverview(result);
            return result;
        } catch (error) {
            if (token !== progressRequestToken || request !== overviewRequest) return;
            if (overviewCache?.ownerId === ownerId) {
                renderProgressOverview(overviewCache.data);
                container.insertAdjacentHTML("afterbegin", retry(error.message, 'retry-overview'));
            } else container.innerHTML = retry(error.message, 'retry-overview');
        } finally {
            if (request === overviewRequest) {
                overviewPromise = null;
                container.removeAttribute("aria-busy");
            }
        }
        })();
        return overviewPromise;
    }

    function openExerciseGoalForm(exerciseKey, exerciseName, trigger) {
        byId('exerciseGoalEditor')?.remove();
        const parent = trigger?.closest('li');
        if (!parent) return;
        parent.insertAdjacentHTML('beforeend', `<div id="exerciseGoalEditor">${goalForm('exercise', '', exerciseKey, exerciseName)}</div>`);
        byId('exerciseGoalEditor').querySelector('input').focus();
    }

    async function saveGoal(form) {
        if (form.dataset.saving) return;
        const raw = form.elements.target.value.trim().replace(',', '.');
        const target = Number(raw);
        const weekly = form.dataset.goalKind === 'weekly';
        const error = form.querySelector('[data-goal-error]');
        error.textContent = '';
        if (!/^\d+(?:\.\d{1,2})?$/.test(raw) || !Number.isFinite(target) || target <= 0 || (weekly ? !Number.isInteger(target) || target > 14 : target > 100000)) {
            error.textContent = weekly ? 'Informe um número inteiro de 1 a 14.' : 'Informe uma carga válida, como 27,5.';
            form.elements.target.focus();
            return;
        }
        const token = progressRequestToken;
        form.dataset.saving = 'true';
        form.querySelectorAll('button').forEach(button => button.disabled = true);
        try {
            await api(weekly ? '/progress/weekly' : '/progress/exercise-goals', {
                method: weekly ? 'PUT' : 'POST',
                body: weekly ? { target_sessions: target, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' } : { exercise_key: form.dataset.exerciseKey, target_load_kg: target },
            });
            if (token !== progressRequestToken) return;
            showToast(weekly ? 'Meta semanal salva.' : 'Meta de exercício criada.', 'success');
            if (!weekly) {
                form.innerHTML = '<p role="status">Meta criada. Acompanhe seu avanço em Progresso.</p><button type="button" data-progress-action="close-goal-form">Fechar</button>';
                form.querySelector('button').focus();
            }
            overviewCache = null;
            await loadProgressOverview();
            if (weekly) byId('workoutProgressOverview')?.querySelector('[data-progress-action="edit-weekly"]')?.focus();
        } catch (requestError) {
            if (token === progressRequestToken) error.textContent = requestError.message;
        } finally {
            delete form.dataset.saving;
            form.querySelectorAll('button').forEach(button => button.disabled = false);
        }
    }

    async function cancelExerciseGoal(button) {
        const token = progressRequestToken;
        const error = button.parentElement.querySelector('[data-cancel-error]');
        button.disabled = true;
        error.textContent = '';
        try {
            await api(`/progress/exercise-goals/${encodeURIComponent(button.dataset.cancelGoal)}`, { method: 'DELETE' });
            if (token !== progressRequestToken) return;
            overviewCache = null;
            await loadProgressOverview();
            byId('workoutProgressOverview')?.querySelector('[data-progress-action="go-activities"]')?.focus();
            showToast('Meta cancelada. Seu histórico foi preservado.', 'success');
        } catch (requestError) {
            if (token === progressRequestToken) error.textContent = requestError.message;
        } finally { button.disabled = false; }
    }

    function renderPerformanceSessions(result) {
        const target = byId('performanceResults');
        const recent = performanceItems[0];
        target.innerHTML = `<div class="performance-comparison"><article><h3>Resultado recente</h3>${recent ? `<p>${performanceDate(recent)}</p>${performanceSets(recent)}` : '<p>Nenhuma sessão registrada.</p>'}</article><article><h3>Recorde histórico</h3><p>Maior carga válida, sem aquecimento</p><strong>${result.max_load_kg == null ? 'Ainda não registrado' : `${number(result.max_load_kg)} kg`}</strong></article></div><h3>Evolução por sessão</h3><p>Todas as sessões registradas, mesmo sem recorde. Compare cargas e repetições com o contexto de cada série.</p><ol class="performance-sessions">${performanceItems.map(session => `<li><details><summary>${performanceDate(session)} · ${session.sets.length ? `${session.sets.length} séries` : 'séries não informadas'}</summary>${performanceSets(session)}</details></li>`).join('')}</ol>${performanceHasMore ? '<button type="button" data-progress-action="more-performance">Carregar mais sessões</button>' : ''}<details class="performance-records"><summary>Entender os recordes pessoais deste exercício</summary><p>Um recorde é sua melhor marca registrada; o resultado da última sessão pode ser menor.</p>${asArray(result.records).slice().reverse().map(record => `<article><p>${utcDate(record.achieved_at).toLocaleDateString('pt-BR')}</p>${recordLabel(record)}</article>`).join('') || '<p>Nenhum recorde válido ainda. Suas sessões continuam no histórico acima.</p>'}</details>`;
    }

    async function loadExerciseSessions(more = false) {
        if (more && (performanceLoading || !performanceHasMore)) return;
        const key = exerciseKeyOpen;
        if (!key) return;
        const request = ++performanceRequest;
        const token = progressRequestToken;
        performanceLoading = true;
        if (!more) {
            performanceItems = [];
            performanceHasMore = false;
            byId('performanceResults').innerHTML = '<p role="status">Carregando sessões...</p>';
        } else {
            byId('performanceResults').querySelector('[data-progress-action="more-performance"]')?.setAttribute('disabled', '');
            byId('performanceResults').querySelector('.progress-feedback')?.remove();
        }
        try {
            const result = await api(`/progress/exercises/${encodeURIComponent(key)}?view=sessions&limit=20&offset=${more ? performanceItems.length : 0}`);
            if (token !== progressRequestToken || request !== performanceRequest || key !== exerciseKeyOpen) return;
            performanceItems = more ? [...performanceItems, ...asArray(result.sessions?.items)] : asArray(result.sessions?.items);
            performanceHasMore = Boolean(result.sessions?.has_more);
            renderPerformanceSessions(result);
            if (more) byId('performanceResults').querySelectorAll('.performance-sessions summary')[performanceItems.length - result.sessions.items.length]?.focus();
        } catch (error) {
            if (token !== progressRequestToken || request !== performanceRequest || key !== exerciseKeyOpen) return;
            if (!more) byId('performanceResults').innerHTML = '';
            byId('performanceResults').querySelector('[data-progress-action="more-performance"]')?.removeAttribute('disabled');
            byId('performanceResults').insertAdjacentHTML('beforeend', retry(error.message, more ? 'more-performance' : 'retry-performance'));
        } finally {
            if (request === performanceRequest) performanceLoading = false;
        }
    }

    async function openExerciseProgress(exerciseKey) {
        showTab("activities", {exerciseProgress: true});
        byId('activitiesTab')?.classList.add('showing-performance');
        exerciseKeyOpen = exerciseKey || null;
        const token = progressRequestToken;
        const request = ++performanceRequest;
        const panel = byId("exerciseProgressPanel");
        panel.classList.remove("hidden");
        byId("activitiesList")?.classList.add("hidden");
        panel.innerHTML = '<p role="status">Carregando exercícios...</p>';
        try {
            if (!performanceOptions.length) {
                const result = await api('/progress/exercises');
                if (token !== progressRequestToken || request !== performanceRequest) return;
                performanceOptions = asArray(result.items);
            }
            if (!exerciseKeyOpen) exerciseKeyOpen = performanceOptions[0]?.key;
            panel.innerHTML = `<button type="button" class="back-button" data-progress-action="close-exercise">Voltar às atividades</button><h2>Performance</h2><label class="performance-selector">Exercício<select id="performanceExercise">${performanceOptions.map(item => `<option value="${esc(item.key)}"${item.key === exerciseKeyOpen ? ' selected' : ''}>${esc(item.name)}</option>`).join('')}</select></label><div id="performanceResults" aria-live="polite"></div>`;
            if (exerciseKeyOpen) await loadExerciseSessions();
            else byId('performanceResults').innerHTML = '<p>Conclua um exercício para começar seu histórico.</p><button type="button" data-progress-action="go-training">Ver treinos</button>';
        } catch (error) {
            if (token !== progressRequestToken || request !== performanceRequest) return;
            panel.innerHTML = `<button type="button" data-progress-action="close-exercise">Voltar às atividades</button>${retry(error.message, 'retry-exercise')}`;
        }
    }

    document.addEventListener('change', event => {
        if (event.target.id !== 'performanceExercise') return;
        exerciseKeyOpen = event.target.value;
        loadExerciseSessions();
    });

    document.addEventListener("click", (event) => {
        const deleteActivityButton = event.target.closest("[data-activity-delete-id]");
        if (deleteActivityButton) {
            deleteActivity(deleteActivityButton.dataset.activityDeleteId);
            return;
        }
        const recordPin = event.target.closest("[data-record-pin]");
        if (recordPin) {
            toggleRecordPin(recordPin.dataset.recordPin);
            return;
        }
        const activity = event.target.closest("[data-activity-id]");
        if (activity) window.openWorkoutActivity?.(activity.dataset.activityId);
        const action = event.target.closest("[data-progress-action]")?.dataset.progressAction;
        const cancelGoal = event.target.closest('[data-cancel-goal]');
        if (cancelGoal && !cancelGoal.disabled) cancelExerciseGoal(cancelGoal);
        const calendarDay = event.target.closest('[data-constancy-date]');
        if (calendarDay) {
            const day = consistencyDays.find(item => item.date === calendarDay.dataset.constancyDate);
            if (day) {
                byId('workoutProgressOverview').querySelectorAll('[data-constancy-date]').forEach(button => button.setAttribute('aria-pressed', String(button === calendarDay)));
                const source = day.diet_source === 'legacy_adherence' ? 'Histórico alimentar antigo.' : day.diet_source === 'manual_entry' ? 'Registro manual; adesão ao plano não informada.' : '';
                byId('constancyDayDetail').innerHTML = `<h4>${dateLabel(day.date)}</h4><p>${day.workout ? 'Treino concluído' : 'Sem treino registrado'}</p><ul>${day.diet_states.map(state => `<li>${dietStateLabels[state]}</li>`).join('')}</ul><p>${source}</p>`;
            }
        }
        if (action === 'go-diet') showTab('diet_plans');
        if (action === 'go-body') showTab('measurements');
        if (action === 'go-performance') openExerciseProgress(performanceOptions[0]?.key);
        if (action === 'more-performance') loadExerciseSessions(true);
        if (action === 'retry-performance') loadExerciseSessions();
        if (action === 'go-training') showTab('workout_plans');
        if (action === 'go-activities') showTab('activities');
        if (action === 'retry-activities') loadActivities();
        if (action === 'more-activities') loadActivities(true);
        if (action === 'retry-records') loadPersonalRecords();
        if (action === 'retry-overview') loadProgressOverview();
        if (action === 'retry-exercise') openExerciseProgress(exerciseKeyOpen);
        if (action === 'close-goal-form') {
            const editor = event.target.closest('#exerciseGoalEditor');
            if (editor) {
                const trigger = editor.parentElement.querySelector('[data-workout-action="set-exercise-goal"]');
                editor.remove();
                trigger?.focus();
            } else {
                byId('weeklyGoalEditor')?.classList.add('hidden');
                const triggers = byId('workoutProgressOverview')?.querySelectorAll('[data-progress-action="edit-weekly"]');
                triggers?.forEach(button => button.setAttribute('aria-expanded', 'false'));
                const trigger = triggers?.[0];
                trigger?.focus();
            }
        }
        if (action === 'view-consistency') {
            const details = byId('workoutProgressOverview').querySelector('.evolution-consistency');
            details.open = true;
            details.querySelector('summary').focus();
            details.scrollIntoView({block: 'start'});
        }
        if (action === 'edit-weekly') {
            const editor = byId('weeklyGoalEditor');
            editor?.classList.remove('hidden');
            byId('workoutProgressOverview').querySelectorAll('[data-progress-action="edit-weekly"]').forEach(button => button.setAttribute('aria-expanded', 'true'));
            editor?.querySelector('input')?.focus();
        }
        if (action === "close-exercise") {
            exerciseKeyOpen = null;
            performanceRequest += 1;
            byId("exerciseProgressPanel")?.classList.add("hidden");
            byId("activitiesList")?.classList.remove("hidden");
            loadActivities();
        }
    });

    document.addEventListener('submit', event => {
        const form = event.target.closest('[data-goal-kind]');
        if (!form) return;
        event.preventDefault();
        saveGoal(form);
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
        activitiesToken += 1;
        activities = [];
        consistencyDays = [];
        performanceOptions = [];
        performanceItems = [];
        performanceRequest += 1;
        overviewRequest += 1;
        overviewCache = null;
        overviewPromise = null;
        activitiesHasMore = false;
        activitiesLoading = false;
        exerciseKeyOpen = null;
        byId('activitiesList')?.replaceChildren();
        byId('activitiesList')?.classList.remove('hidden');
        byId('personalRecordsList')?.replaceChildren();
        byId('exerciseGoalEditor')?.remove();
        byId('activitiesTab')?.classList.remove('showing-performance');
        const overview = byId("workoutProgressOverview");
        if (overview) overview.replaceChildren();
        const panel = byId("exerciseProgressPanel");
        if (panel) panel.classList.add("hidden");
    }

    window.openExerciseGoalForm = openExerciseGoalForm;
    window.renderProgressRecord = recordLabel;
    window.loadWorkoutActivities = loadActivities;
    window.loadProgressOverview = loadProgressOverview;
    window.invalidateProgressOverview = () => { overviewCache = null; };
    window.loadPersonalRecords = loadPersonalRecords;
    window.openExerciseProgress = openExerciseProgress;
    window.clearWorkoutProgress = clearWorkoutProgress;
    window.deleteWorkoutActivity = deleteActivity;
})();
