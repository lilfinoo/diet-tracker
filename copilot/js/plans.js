Warning: truncated output (original token count: 80000)
Total output lines: 4989

(function () {
    "use strict";

    let dietPlans = [];
    let workoutPlans = [];
    let workoutTodayState = null;
    let workoutTodayError = "";
    let startingTodayWorkout = false;
    let workoutCurrentPlan = null;
    let workoutCurrentDecision = null;
    const WEEKDAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
    const WEEKDAY_FULL_LABELS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

    const DIET_GOALS = {
        fat_loss: "Perder gordura",
        muscle_gain: "Ganhar massa",
        maintenance: "Manter o peso",
        general_health: "Saúde e bem-estar"
    };
    const DIET_PATTERNS = {
        omnivore: "Onívora",
        vegetarian: "Vegetariana",
        vegan: "Vegana",
        pescatarian: "Pescetariana"
    };
    const BUDGETS = {
        economical: "Econômico",
        moderate: "Moderado",
        flexible: "Flexível"
    };
    const CHANGE_PACES = {
        conservative: "Gradual (recomendado)",
        moderate: "Mais rápida"
    };
    const INGREDIENT_POOL = [];
    let ingredientPoolLoading = null;
    const WORKOUT_GOALS = {
        hypertrophy: "Hipertrofia",
        strength: "Força",
        conditioning: "Condicionamento",
        fat_loss: "Perda de gordura",
        mobility: "Mobilidade"
    };
    const EXPERIENCE_LEVELS = {
        beginner: "Iniciante",
        intermediate: "Intermediário",
        advanced: "Avançado"
    };
    const SPLIT_TYPES = {
        full_body: "Corpo inteiro",
        abc: "ABC",
        upper_lower: "Superior / inferior",
        abcd: "ABCD",
        abcde: "ABCDE"
    };
    const SPLITS_BY_DAYS = {
        2: ["full_body", "upper_lower"],
        3: ["full_body", "upper_lower", "abc"],
        4: ["full_body", "upper_lower", "abc", "abcd"],
        5: ["full_body", "upper_lower", "abc", "abcd", "abcde"],
        6: ["full_body", "upper_lower", "abc", "abcd", "abcde"]
    };
    const WORKOUT_EQUIPMENT = {
        full_gym: "Academia completa",
        bodyweight: "Peso corporal",
        dumbbell: "Halteres",
        barbell: "Barra e anilhas",
        machine: "Máquinas",
        cable: "Cabos",
        resistance_band: "Faixas elásticas",
        bench: "Banco",
        pull_up_bar: "Barra fixa",
        cardio_machine: "Máquina de cardio",
        outdoor: "Área externa"
    };
    const CATALOG_EQUIPMENT_LABELS = {
        pullup_bar: "Barra fixa",
        elliptical: "Elíptico",
        stationary_bike: "Bicicleta ergométrica",
        treadmill: "Esteira",
        jump_rope: "Corda",
        ez_bar: "Barra EZ",
        sliders: "Discos deslizantes",
        stability_ball: "Bola suíça",
        Barbell: "Barra e anilhas",
        Cable: "Cabos",
        Dumbbell: "Halteres",
        "Body Weight": "Peso corporal",
        Band: "Faixas elásticas",
        Kettlebell: "Kettlebell",
        Weighted: "Carga adicional",
        "Skierg Machine": "Ergômetro de esqui"
    };
    const WIZARD_STEPS = {
        diet: ["Base", "Cuidados", "Revisão"],
        workout: ["Rotina", "Estrutura", "Revisão"]
    };
    const FIELD_STEPS = {
        diet: {
            goal: 0,
            meals_per_day: 0,
            diet_pattern: 0,
            training_days_per_week: 1,
            change_pace: 2,
            target_calories: 2,
            target_protein: 2,
            target_carbs: 2,
            target_fat: 2,
            custom_targets: 2,
            nutrition_targets: 2,
            allergies: 1,
            intolerances: 1,
            disliked_foods: 1,
            preferred_foods: 1,
            budget: 2,
            prep_minutes: 2,
            available_ingredients: 2,
            notes: 2
        },
        workout: {
            goal: 0,
            experience_level: 0,
            days_per_week: 0,
            split_type: 2,
            session_duration: 1,
            equipment: 1,
            limitations: 2,
            priorities: 2,
            avoid_exercises: 2
        }
    };

    function defaultDietAnswers() {
        return {
            goal: "",
            meals_per_day: "3",
            diet_pattern: "omnivore",
            training_days_per_week: "3",
            change_pace: "conservative",
            allergies: "",
            intolerances: "",
            disliked_foods: "",
            preferred_foods: "",
            budget: "moderate",
            prep_minutes: "30",
            available_ingredients: "",
            target_calories: "",
            target_protein: "",
            target_carbs: "",
            target_fat: "",
            notes: ""
        };
    }

    function defaultWorkoutAnswers() {
        return {
            goal: "",
            experience_level: "beginner",
            days_per_week: "3",
            split_type: "full_body",
            session_duration: "45",
            equipment: ["bodyweight"],
            limitations: "",
            priorities: "",
            avoid_exercises: ""
        };
    }

    const wizardMemory = {
        diet: { step: 0, answers: defaultDietAnswers(), error: "", fieldErrors: {}, generating: false, preferencesOpen: false, customizationOpen: false, targetsOpen: false, ingredientDraft: "" },
        workout: { step: 0, answers: defaultWorkoutAnswers(), error: "", fieldErrors: {}, generating: false }
    };
    const dietView = { plan: null, selectedDay: 0, adherence: null, adherenceDate: null };
    const dietShoppingState = { planId: null, people: 1, hideAvailable: false, checked: new Set(), substitutions: new Map() };
    const workoutView = {
        plan: null,
        days: [],
        selectedDay: 0,
        editMode: false,
        activeExerciseId: null,
        playerScreen: "exercise",
        skippedExerciseIds: new Set(),
        completedSetCounts: new Map(),
        completingExerciseIds: new Set(),
        session: null,
        sessionLoading: false,
        openingExecution: false,
        sessionError: "",
        actionFeedback: "",
        pendingReplacementMedia: null,
        pendingAction: "",
        completedSummary: null,
        summaryOrigin: "workout",
        shareOpen: false,
        shareDraft: null,
        sharePhotoToken: 0,
        setDrafts: new Map(),
        draftSaveTimers: new Map(),
        draftRevisions: new Map(),
        draftError: "",
        mutationRevision: 0,
        rest: null,
        sessionSheetExpanded: false,
        setEntryMode: "closed",
        activeSetIndex: null,
        lastConfirmedSet: null,
        correctionSetIndex: null,
        setEntryError: "",
        replacementPanels: new Map(),
        exerciseCatalog: [],
        addExerciseOpen: false,
        catalogLoading: false,
        requestToken: 0,
        viewVersion: 0
    };
    let activeWorkoutSummary = null;
    let activeWizardType = null;
    let workoutGesture = null;
    let ignoreNextWorkoutSheetClick = false;
    let workoutTimerInterval = null;
    let workoutRestInterval = null;
    let workoutSyncInterval = null;
    let workoutRecommendationTimer = null;
    let activeDockRequestToken = 0;
    const sessionWrites = new Map();
    const sessionLocks = new Set();
    const workoutMediaLoads = new Map();
    let workoutTodayOwner = "";
    let workoutTodayAt = 0;
    let workoutTodayPromise = null;

    function workoutAccount() {
        return `${window.currentUser?.id || ""}:${window.AppReadCache?.accountVersion || 0}`;
    }

    function workoutContextCurrent(account, version, sessionId) {
        return account === workoutAccount() && version === workoutView.viewVersion
            && (sessionId == null || isCurrentWorkoutSession(sessionId));
    }

    function queueSessionWrite(sessionId, task) {
        const key = `${workoutAccount()}:${sessionId}`;
        const previous = sessionWrites.get(key) || Promise.resolve();
        const result = previous.catch(() => {}).then(task);
        sessionWrites.set(key, result);
        result.finally(() => {
            if (sessionWrites.get(key) === result) sessionWrites.delete(key);
        }).catch(() => {});
        return result;
    }

    function invalidateWorkoutReads() {
        workoutTodayAt = 0;
        window.AppReadCache?.invalidate("workout:");
        window.invalidateProgressOverview?.();
    }

    function resetWorkoutAccount() {
        invalidateWorkoutView();
        resetWorkoutExecutionState();
        workoutView.session = null;
        workoutView.plan = null;
        workoutView.days = [];
        workoutMediaLoads.clear();
        workoutView.completedSummary = null;
        workoutView.shareOpen = false;
        workoutView.shareDraft = null;
        workoutView.sharePhotoToken += 1;
        workoutTodayOwner = "";
        workoutTodayState = null;
        workoutTodayPromise = null;
        workoutTodayAt = 0;
        workoutTodayError = "";
        workoutPlans = [];
        dietPlans = [];
        window.WorkoutShare?.reset();
        clearActiveWorkoutDock();
        const modal = byId("viewWorkoutPlanModal");
        if (modal?.classList.contains("show")) closeAppModal(modal);
        ["viewWorkoutPlanDetails", "workoutTodayCard", "workoutPlansTableBody", "workoutPlanHub", "dietPlansTableBody"].forEach(id => {
            const element = byId(id);
            if (element) element.replaceChildren();
        });
    }

    function beginSessionMutation(action, sessionId) {
        const lock = `${workoutAccount()}:${sessionId}`;
        if (workoutView.pendingAction || sessionLocks.has(lock)) return null;
        sessionLocks.add(lock);
        workoutView.pendingAction = action;
        workoutView.mutationRevision += 1;
        activeDockRequestToken += 1;
        cancelWorkoutPlayerGesture();
        return lock;
    }

    function endSessionMutation(lock, action, account, version) {
        sessionLocks.delete(lock);
        invalidateWorkoutReads();
        if (workoutContextCurrent(account, version) && workoutView.pendingAction === action) {
            workoutView.pendingAction = "";
        }
    }

    function closeReplacementPanel(exerciseId) {
        const key = String(exerciseId);
        workoutView.replacementPanels.get(key)?.controller?.abort();
        workoutView.replacementPanels.delete(key);
    }

    function clearReplacementPanels() {
        workoutView.replacementPanels.forEach((panel) => panel.controller?.abort());
        workoutView.replacementPanels.clear();
    }

    function cancelWorkoutDraftTimers() {
        workoutView.draftSaveTimers.forEach((timer) => window.clearTimeout(timer));
        workoutView.draftSaveTimers.clear();
    }

    function byId(id) {
        return document.getElementById(id);
    }

    function esc(value) {
        return escapeHtml(value == null ? "" : String(value));
    }

    function asArray(value) {
        return Array.isArray(value) ? value : [];
    }

    function parseTextList(value) {
        return String(value || "")
            .split(/[,\n;]/)
            .map((item) => item.trim())
            .filter(Boolean);
    }

    function labelFor(labels, value, fallback) {
        return labels[value] || fallback || value || "Não informado";
    }

    function apiSegment(value) {
        return encodeURIComponent(String(value));
    }

    async function apiRequest(path, options = {}) {
        if ((!options.method || options.method === "GET") && /^\/(workout_sessions|workouts|workout_plans)/.test(path) && window.readApiJson) {
            return window.readApiJson(`${API_BASE}${path}`, {signal: options.signal});
        }
        const fetchOptions = {
            method: options.method || "GET",
            credentials: "include",
            headers: {}
        };
        const timed = options.timeout || (/^\/(workout_sessions|workouts|workout_plans)/.test(path) ? 15000 : 0);
        const controller = new AbortController();
        const abort = () => controller.abort(options.signal?.reason);
        if (options.signal?.aborted) abort();
        else options.signal?.addEventListener("abort", abort, { once: true });
        fetchOptions.signal = controller.signal;
        let timedOut = false;
        const timer = timed ? window.setTimeout(() => { timedOut = true; controller.abort(); }, timed) : null;
        if (options.body !== undefined) {
            fetchOptions.headers["Content-Type"] = "application/json";
            fetchOptions.body = JSON.stringify(options.body);
        }

        let response;
        let data = {};
        try {
            response = await fetch(`${API_BASE}${path}`, fetchOptions);
            data = await response.json().catch(() => ({}));
        } catch (error) {
            if (options.signal?.aborted) throw error;
            const connectionError = new Error(timedOut
                ? "A solicitação demorou demais. Verifique a sessão antes de tentar novamente."
                : options.offlineMessage || "Sem conexão. Seus registros continuam neste dispositivo. Tente novamente quando a conexão voltar.");
            connectionError.cause = error;
            connectionError.code = timedOut ? "timeout" : "offline";
            throw connectionError;
        } finally {
            window.clearTimeout(timer);
            options.signal?.removeEventListener("abort", abort);
        }
        if (!response.ok) {
            const fieldMessages = data.fields && typeof data.fields === "object"
                ? Object.values(data.fields).filter(Boolean)
                : [];
            const fallback = response.status === 401
                ? "Sua sessão expirou. Entre novamente para continuar."
                : "Não foi possível concluir a solicitação.";
            const requestError = new Error(data.error || data.message || fieldMessages[0] || fallback);
            requestError.status = response.status;
            requestError.fields = data.fields && typeof data.fields === "object" ? data.fields : {};
            requestError.data = data;
            throw requestError;
        }
        if (response.status === 202 && data.job_id) {
            options.onQueued?.(data);
            return window.waitForAIJob(data, options.jobTimeoutMilliseconds, {
                onStatus: options.onJobStatus,
                jobLabel: options.jobLabel
            });
        }
        return data;
    }

    function workoutDraftStorageKey(sessionId) {
        const userId = window.currentUser?.id || "anonymous";
        return `fittracker.workout-draft.v1.${userId}.${sessionId}`;
    }

    function readLocalWorkoutDraft(sessionId) {
        if (!sessionId) return null;
        try {
            const parsed = JSON.parse(localStorage.getItem(workoutDraftStorageKey(sessionId)) || "null");
            return parsed && typeof parsed === "object" ? parsed : null;
        } catch (error) {
            return null;
        }
    }

    function persistWorkoutDraftLocally(sessionId) {
        if (!sessionId) return;
        const sets = Object.fromEntries(workoutView.setDrafts.entries());
        try {
            localStorage.setItem(workoutDraftStorageKey(sessionId), JSON.stringify({
                sets,
                rest: workoutView.rest,
                activeExerciseId: workoutView.activeExerciseId,
                playerScreen: workoutView.playerScreen,
                skippedExerciseIds: Array.from(workoutView.skippedExerciseIds),
                completedSetCounts: Object.fromEntries(workoutView.completedSetCounts.entries()),
                updatedAt: new Date().toISOString(),
            }));
        } catch (error) {
            // The server autosave remains available when browser storage is unavailable.
        }
    }

    function clearLocalWorkoutDraft(sessionId) {
        if (!sessionId) return;
        try {
            localStorage.removeItem(workoutDraftStorageKey(sessionId));
        } catch (error) {
            // Nothing else is required when storage is unavailable.
        }
    }

    function resetWorkoutExecutionState() {
        workoutView.actionFeedback = "";
        workoutView.pendingReplacementMedia = null;
        cancelWorkoutDraftTimers();
        workoutView.draftRevisions.clear();
        workoutView.lastField = null;
        workoutView.draftError = "";
        workoutView.uncertainMutation = null;
        workoutView.setDrafts.clear();
        workoutView.skippedExerciseIds.clear();
        workoutView.completedSetCounts.clear();
        workoutView.completingExerciseIds.clear();
        workoutView.activeExerciseId = null;
        workoutView.playerScreen = "exercise";
        workoutView.rest = null;
        workoutView.sessionSheetExpanded = false;
        workoutView.setEntryMode = "closed";
        workoutView.activeSetIndex = null;
        workoutView.lastConfirmedSet = null;
        workoutView.correctionSetIndex = null;
        workoutView.setEntryError = "";
    }

    function hydrateWorkoutDrafts(session) {
        if (!session?.id) return;
        const completedIds = new Set(asArray(session.completed_exercise_ids).map(String));
        const local = readLocalWorkoutDraft(session.id);
        const serverSets = session.draft_sets && typeof session.draft_sets === "object" ? session.draft_sets : {};
        const localSets = local?.sets && typeof local.sets === "object" ? local.sets : {};
        workoutView.setDrafts.clear();
        workoutView.skippedExerciseIds = new Set(asArray(local?.skippedExerciseIds).map(String));
        completedIds.forEach((exerciseId) => workoutView.skippedExerciseIds.delete(exerciseId));
        workoutView.completedSetCounts = new Map(
            Object.entries(local?.completedSetCounts || {}).map(([exerciseId, count]) => [String(exerciseId), Number(count) || 0])
        );
        const localExerciseId = local?.activeExerciseId == null ? null : String(local.activeExerciseId);
        const validLocalExercise = asArray(selectedWorkoutDay()?.exercises).some((exercise) => String(exercise.id) === localExerciseId);
        workoutView.activeExerciseId = validLocalExercise ? localExerciseId : null;
        workoutView.playerScreen = local?.playerScreen === "finish" && validLocalExercise ? "finish" : "exercise";
        workoutView.setEntryMode = "closed";
        workoutView.sessionSheetExpanded = false;
        workoutView.activeSetIndex = null;
        workoutView.lastConfirmedSet = null;
        workoutView.correctionSetIndex = null;
        workoutView.setEntryError = "";
        Object.entries({ ...serverSets, ...localSets }).forEach(([exerciseId, sets]) => {
            if (!completedIds.has(String(exerciseId)) && Array.isArray(sets)) {
                workoutView.setDrafts.set(String(exerciseId), sets);
            }
        });
        workoutView.rest = local?.rest?.endsAt > Date.now() ? local.rest : null;
        persistWorkoutDraftLocally(session.id);
    }

    async function saveWorkoutDraftToServer(sessionId, exerciseId, sets) {
        if (!sessionId || !exerciseId) return;
        const account = workoutAccount();
        const version = workoutView.viewVersion;
        const key = String(exerciseId);
        const revision = workoutView.draftRevisions.get(key);
        const snapshot = JSON.parse(JSON.stringify(sets));
        try {
            await queueSessionWrite(sessionId, async () => {
                if (!workoutContextCurrent(account, version, sessionId)
                    || workoutView.draftRevisions.get(key) !== revision
                    || completedWorkoutExerciseIds().has(key)
                    || workoutView.pendingAction?.startsWith("complete-")
                    || ["finish", "cancel"].includes(workoutView.pendingAction)) return;
                await apiRequest(`/workout_sessions/${apiSegment(sessionId)}/exercises/${apiSegment(exerciseId)}/draft`, {
                    method: "PUT", body: { sets: snapshot },
                });
                if (workoutContextCurrent(account, version, sessionId)
                    && workoutView.draftRevisions.get(key) === revision) workoutView.draftError = "";
            });
        } catch (error) {
            if (workoutContextCurrent(account, version, sessionId) && !workoutView.pendingAction
                && !completedWorkoutExerciseIds().has(key) && workoutView.draftRevisions.get(key) === revision) {
                workoutView.draftError = "Registro salvo neste dispositivo. A sincronização será retomada com conexão.";
                updateWorkoutPlayerFeedback();
            }
        }
    }

    function scheduleWorkoutDraftSave(exerciseId) {
        const sessionId = workoutView.session?.id;
        if (!sessionId || !exerciseId) return;
        persistWorkoutDraftLocally(sessionId);
        const key = String(exerciseId);
        workoutView.draftRevisions.set(key, (workoutView.draftRevisions.get(key) || 0) + 1);
        const snapshot = JSON.parse(JSON.stringify(asArray(workoutView.setDrafts.get(key))));
        window.clearTimeout(workoutView.draftSaveTimers.get(key));
        workoutView.draftSaveTimers.set(key, window.setTimeout(() => {
            workoutView.draftSaveTimers.delete(key);
            saveWorkoutDraftToServer(sessionId, exerciseId, snapshot);
        }, 500));
    }

    function clearWorkoutExerciseDraft(sessionId, exerciseId) {
        const key = String(exerciseId);
        window.clearTimeout(workoutView.draftSaveTimers.get(key));
        workoutView.draftSaveTimers.delete(key);
        workoutView.draftRevisions.set(key, (workoutView.draftRevisions.get(key) || 0) + 1);
        workoutView.setDrafts.delete(key);
        persistWorkoutDraftLocally(sessionId);
    }

    async function syncWorkoutDrafts() {
        const sessionId = workoutView.session?.id;
        if (!sessionId || !navigator.onLine) return;
        cancelWorkoutDraftTimers();
        await Promise.all(Array.from(workoutView.setDrafts, ([exerciseId, sets]) => saveWorkoutDraftToServer(sessionId, exerciseId, asArray(sets))));
    }

    function invalidAttributes(name, state) {
        if (!state.fieldErrors[name]) return "";
        return ` aria-invalid="true" aria-describedby="wizard-error-${esc(name)}"`;
    }

    function fieldError(name, state) {
        const message = state.fieldErrors[name];
        return message ? `<p id="wizard-error-${esc(name)}" class="wizard-field-error"><i class="fas fa-circle-exclamation" aria-hidden="true"></i> ${esc(message)}</p>` : "";
    }

    function selectOptions(options, selected) {
        return Object.entries(options).map(([value, label]) => (
            `<option value="${esc(value)}"${String(selected) === value ? " selected" : ""}>${esc(label)}</option>`
        )).join("");
    }

    function radioCards(name, options, selected, state, compact = false) {
        const invalid = Boolean(state.fieldErrors[name]);
        return `<div class="wizard-choice-grid${compact ? " wizard-choice-grid--compact" : ""}"${invalid ? ` aria-describedby="wizard-error-${esc(name)}"` : ""}>${Object.entries(options).map(([value, label]) => `
            <label class="wizard-choice">
                <input type="radio" name="${esc(name)}" value="${esc(value)}"${String(selected) === value ? " checked" : ""}${invalidAttributes(name, state)}>
                <span class="wizard-choice__surface"><span>${esc(label)}</span><i class="fas fa-check" aria-hidden="true"></i></span>
            </label>
        `).join("")}</div>${fieldError(name, state)}`;
    }

    function checkboxCards(name, options, selectedValues, state) {
        const selected = new Set(asArray(selectedValues));
        const invalid = Boolean(state.fieldErrors[name]);
        return `<div class="wizard-check-grid"${invalid ? ` aria-describedby="wizard-error-${esc(name)}"` : ""}>${Object.entries(options).map(([value, label]) => `
            <label class="wizard-check">
                <input type="checkbox" name="${esc(name)}" value="${esc(value)}"${selected.has(value) ? " checked" : ""}${invalidAttributes(name, state)}>
                <span class="wizard-check__surface"><i class="fas fa-check" aria-hidden="true"></i><span>${esc(label)}</span></span>
            </label>
        `).join("")}</div>${fieldError(name, state)}`;
    }

    function workoutEquipmentPicker(state) {
        const selected = new Set(asArray(state.answers.equipment));
        const detailedEquipment = Object.fromEntries(
            Object.entries(WORKOUT_EQUIPMENT).filter(([value]) => value !== "full_gym")
        );
        const mode = state.equipmentMode || (selected.has("full_gym") ? "full_gym" : "bodyweight");
        const customOpen = mode === "custom";
        return `
            <div class="workout-equipment-modes wizard-choice-grid wizard-choice-grid--compact"${state.fieldErrors.equipment ? ' aria-describedby="wizard-error-equipment"' : ""}>
                ${[
                    ["full_gym", "Academia completa"],
                    ["bodyweight", "Só peso corporal"],
                    ["custom", "Personalizar"],
                ].map(([value, label]) => `
                    <label class="wizard-choice">
                        <input type="radio" name="equipment_mode" value="${value}"${mode === value ? " checked" : ""}>
                        <span class="wizard-choice__surface"><span>${label}</span><i class="fas fa-check" aria-hidden="true"></i></span>
                    </label>
                `).join("")}
            </div>
            ${customOpen ? `<div class="wizard-equipment-details"><span>Selecione o que você tem disponível</span>${checkboxCards("equipment", detailedEquipment, state.answers.equipment, state)}</div>` : fieldError("equipment", state)}`;
    }

    function loadIngredientPool() {
        if (INGREDIENT_POOL.length || ingredientPoolLoading) return ingredientPoolLoading;
        ingredientPoolLoading = fetch("/minha-pasta/alimentos.json")
            .then((response) => (response.ok ? response.json() : []))
            .then((data) => {
                (Array.isArray(data) ? data : []).forEach((item) => {
                    const name = item && item.descricao ? String(item.descricao).trim() : "";
                    if (name && INGREDIENT_POOL.indexOf(name) === -1) INGREDIENT_POOL.push(name);
                });
            })
            .catch(() => {})
            .finally(() => { ingredientPoolLoading = null; });
        return ingredientPoolLoading;
    }

    function parseIngredientTokens(value) {
        return String(value || "").split(";").map((item) => item.trim()).filter(Boolean);
    }

    function ingredientLastToken(value) {
        const tokens = parseIngredientTokens(value);
        return tokens.length ? tokens[tokens.length - 1] : "";
    }

    function ingredientChipsMarkup(value) {
        const tokens = parseIngredientTokens(value);
        if (!tokens.length) return "";
        return tokens.map((token) => `
            <span class="ingredient-chip"><span>${esc(token)}</span><button type="button" class="ingredient-chip__remove" data-remove-ingredient="${esc(token)}" aria-label="Remover ${esc(token)}"><i class="fas fa-xmark" aria-hidden="true"></i></button></span>
        `).join("");
    }

    function ingredientOptions(query) {
        const q = String(query || "").toLowerCase();
        const matches = q ? INGREDIENT_POOL.filter((name) => name.toLowerCase().indexOf(q) !== -1) : INGREDIENT_POOL;
        return matches.slice(0, 30).map((name) => `<option value="${esc(name)}"></option>`).join("");
    }

    function addIngredient(value) {
        const state = wizardMemory[activeWizardType];
        if (!state || activeWizardType !== "diet") return false;
        const answers = state.answers;
        const token = String(value || "").trim().replace(/^;+|;+$/g, "");
        if (!token) return false;
        const tokens = parseIngredientTokens(answers.available_ingredients);
        if (token.length > 80) {
            state.fieldErrors.available_ingredients = "Cada ingrediente deve ter até 80 caracteres.";
            return false;
        }
        if (tokens.indexOf(token) !== -1) return false;
        if (tokens.length >= 24) {
            state.fieldErrors.available_ingredients = "Você pode informar no máximo 24 ingredientes.";
            return false;
        }
        tokens.push(token);
        answers.available_ingredients = tokens.join("; ");
        delete state.fieldErrors.available_ingredients;
        state.ingredientDraft = "";
        const chips = byId("ingredient-chips");
        if (chips) chips.innerHTML = ingredientChipsMarkup(answers.available_ingredients);
        return true;
    }

    function commitIngredientDraft(state) {
        if (!state?.ingredientDraft?.trim()) return true;
        const added = addIngredient(state.ingredientDraft);
        if (added) state.ingredientDraft = "";
        return added;
    }

    function removeIngredient(value) {
        const state = wizardMemory[activeWizardType];
        if (!state) return;
        const tokens = parseIngredientTokens(state.answers.available_ingredients).filter((token) => token !== String(value));
        state.answers.available_ingredients = tokens.join("; ");
        delete state.fieldErrors.available_ingredients;
        const chips = byId("ingredient-chips");
        if (chips) chips.innerHTML = ingredientChipsMarkup(state.answers.available_ingredients);
    }

    function renderDietStep(state) {
        const answers = state.answers;
        if (state.step === 0) {
            return `
                <div class="wizard-step-heading" tabindex="-1"><h4>Qual é a base do seu plano?</h4><p>Escolha só o essencial. Você poderá personalizar os detalhes na revisão.</p></div>
                <div class="wizard-field"><label for="wizard-diet-goal">Objetivo principal</label><select id="wizard-diet-goal" name="goal"${invalidAttributes("goal", state)}><option value="">Selecione um objetivo</option>${selectOptions(DIET_GOALS, answers.goal)}</select>${fieldError("goal", state)}</div>
                <fieldset class="wizard-fieldset"><legend>Refeições por dia</legend>${radioCards("meals_per_day", { 3: "3 refeições", 4: "4 refeições", 5: "5 refeições" }, answers.meals_per_day, state, true)}</fieldset>
                <div class="wizard-field"><label for="wizard-diet-pattern">Padrão alimentar</label><select id="wizard-diet-pattern" name="diet_pattern"${invalidAttributes("diet_pattern", state)}>${selectOptions(DIET_PATTERNS, answers.diet_pattern)}</select>${fieldError("diet_pattern", state)}</div>`;
        }
        if (state.step === 1) {
            return `
                <div class="wizard-step-heading" tabindex="-1"><h4>Rotina e cuidados</h4><p>Essas informações ajudam a ajustar as quantidades e evitar alimentos inadequados.</p></div>
                <div class="wizard-field"><label for="wizard-training-days">Treinos por semana</label><select id="wizard-training-days" name="training_days_per_week"${invalidAttributes("training_days_per_week", state)}>${selectOptions({ 0: "Não treino", 1: "1 dia", 2: "2 dias", 3: "3 dias", 4: "4 dias", 5: "5 dias", 6: "6 dias", 7: "7 dias" }, answers.training_days_per_week)}</select>${fieldError("training_days_per_week", state)}</div>
                <div class="diet-profile-note" role="note"><strong>Restrições alimentares</strong><p>Alergias e intolerâncias são gerenciadas no seu perfil para que todos os planos respeitem as mesmas informações.</p><button type="button" class="text-button" data-wizard-action="open-profile">Editar perfil</button></div>
                <details class="diet-wizard-disclosure" data-diet-preferences${state.preferencesOpen || Boolean(state.fieldErrors.disliked_foods || state.fieldErrors.preferred_foods) ? " open" : ""}>
                    <summary>Preferências alimentares <span>opcional</span><i class="fas fa-chevron-down" aria-hidden="true"></i></summary>
                    <div class="diet-wizard-disclosure__content">
                        <div class="wizard-field"><label for="wizard-disliked-foods">Alimentos que não gosta</label><input id="wizard-disliked-foods" name="disliked_foods" value="${esc(answers.disliked_foods)}" placeholder="Ex.: berinjela, coentro" maxlength="970"${invalidAttributes("disliked_foods", state)}>${fieldError("disliked_foods", state)}</div>
                        <div class="wizard-field"><label for="wizard-preferred-foods">Alimentos preferidos</label><input id="wizard-preferred-foods" name="preferred_foods" value="${esc(answers.preferred_foods)}" placeholder="Ex.: arroz, frango, banana" maxlength="970"${invalidAttributes("preferred_foods", state)}>${fieldError("preferred_foods", state)}</div>
                    </div>
                </details>`;
        }
        const customizationOpen = state.customizationOpen || Boolean(state.fieldErrors.budget || state.fieldErrors.prep_minutes || state.fieldErrors.available_ingredients || state.fieldErrors.notes);
        const targetsOpen = state.targetsOpen || Boolean(state.fieldErrors.change_pace || state.fieldErrors.target_calories || state.fieldErrors.target_protein || state.fieldErrors.target_carbs || state.fieldErrors.target_fat || state.fieldErrors.custom_targets || state.fieldErrors.nutrition_targets);
        return `
            <div class="wizard-step-heading" tabindex="-1"><h4>Confira seu plano</h4><p>Revise o essencial. Os ajustes opcionais ficam disponíveis abaixo.</p></div>
            ${renderWizardReview("diet", answers)}
            <details class="diet-wizard-disclosure" data-diet-customization${customizationOpen ? " open" : ""}>
                <summary>Personalizar preparo <span>opcional</span><i class="fas fa-chevron-down" aria-hidden="true"></i></summary>
                <div class="diet-wizard-disclosure__content">
                    <fieldset class="wizard-fieldset"><legend>Orçamento</legend>${radioCards("budget", BUDGETS, answers.budget, state, true)}</fieldset>
                    <div class="wizard-field"><label for="wizard-prep-minutes">Tempo máximo de preparo</label><select id="wizard-prep-minutes" name="prep_minutes"${invalidAttributes("prep_minutes", state)}>${selectOptions({ 15: "Até 15 min", 30: "Até 30 min", 45: "Até 45 min", 60: "Até 60 min" }, answers.prep_minutes)}</select>${fieldError("prep_minutes", state)}</div>
                    <div class="wizard-field wizard-field--ingredients">
                        <label for="wizard-ingredient-input">Ingredientes disponíveis <span>opcional</span></label>
                        <div class="ingredient-picker">
                            <input id="wizard-ingredient-input" name="available_ingredients" list="wizard-ingredient-options" placeholder="Digite e pressione Enter" autocomplete="off" maxlength="160" value="${esc(state.ingredientDraft || "")}"${invalidAttributes("available_ingredients", state)}>
                            <datalist id="wizard-ingredient-options">${ingredientOptions(ingredientLastToken(state.ingredientDraft || ""))}</datalist>
                            <button type="button" class="ingredient-add" data-add-ingredient aria-label="Adicionar ingrediente"><i class="fas fa-plus" aria-hidden="true"></i></button>
                        </div>
                        <div class="ingredient-chips" id="ingredient-chips">${ingredientChipsMarkup(answers.available_ingredients)}</div>
                        <small class="wizard-field-hint">A IA prioriza esses ingredientes, quando possível.</small>
                        ${fieldError("available_ingredients", state)}
                    </div>
                    <div class="wizard-field"><label for="wizard-diet-notes">Observações finais <span>opcional</span></label><textarea id="wizard-diet-notes" name="notes" rows="3" maxlength="500" placeholder="Conte algo importante sobre sua rotina."${invalidAttributes("notes", state)}>${esc(answers.notes)}</textarea><small class="wizard-character-count">${String(answers.notes || "").length}/500</small>${fieldError("notes", state)}</div>
                </div>
            </details>
            <details class="diet-wizard-disclosure" data-diet-targets${targetsOpen ? " open" : ""}>
                <summary>Metas e ritmo <span>opcional</span><i class="fas fa-chevron-down" aria-hidden="true"></i></summary>
                <div class="diet-wizard-disclosure__content">
                    ${["fat_loss", "muscle_gain"].includes(answers.goal) ? `<fieldset class="wizard-fieldset"><legend>Velocidade para atingir o objetivo</legend>${radioCards("change_pace", CHANGE_PACES, answers.change_pace, state, true)}<small class="wizard-field-hint">${answers.goal === "fat_loss" ? "Gradual reduz cerca de 10% das calorias; mais rápida, 15%." : "Gradual aumenta cerca de 5% das calorias; mais rápida, 8%."}</small></fieldset>` : `<p class="wizard-field-hint">As calorias serão calculadas automaticamente para este objetivo.</p>`}
                    <p class="wizard-field-hint">Campos vazios são calculados com seu perfil, atividade, treinos e objetivo.</p>
                    ${fieldError("custom_targets", state)}${fieldError("nutrition_targets", state)}
                    <div class="wizard-field-grid">
                        <div class="wizard-field"><label for="wizard-target-calories">Calorias por dia</label><input id="wizard-target-calories" name="target_calories" type="number" min="800" max="7000" step="1" value="${esc(answers.target_calories)}" placeholder="Automático"${invalidAttributes("target_calories", state)}>${fieldError("target_calories", state)}</div>
                        <div class="wizard-field"><label for="wizard-target-protein">Proteína (g)</label><input id="wizard-target-protein" name="target_protein" type="number" min="20" max="500" step="1" value="${esc(answers.target_protein)}" placeholder="Automático"${invalidAttributes("target_protein", state)}>${fieldError("target_protein", state)}</div>
                        <div class="wizard-field"><label for="wizard-target-carbs">Carboidratos (g)</label><input id="wizard-target-carbs" name="target_carbs" type="number" min="20" max="1200" step="1" value="${esc(answers.target_carbs)}" placeholder="Automático"${invalidAttributes("target_carbs", state)}>${fieldError("target_carbs", state)}</div>
                        <div class="wizard-field"><label for="wizard-target-fat">Gorduras (g)</label><input id="wizard-target-fat" name="target_fat" type="number" min="15" max="300" step="1" value="${esc(answers.target_fat)}" placeholder="Automático"${invalidAttributes("target_fat", state)}>${fieldError("target_fat", state)}</div>
                    </div>
                </div>
            </details>`;
    }

    function compatibleSplits(days) {
        const values = SPLITS_BY_DAYS[Number(days)] || [];
        return values.reduce((result, value) => {
            result[value] = SPLIT_TYPES[value];
            return result;
        }, {});
    }

    function workoutSplitCards(state) {
        const options = compatibleSplits(state.answers.days_per_week);
        const invalid = Boolean(state.fieldErrors.split_type);
        return `<div class="wizard-choice-grid wizard-choice-grid--compact"${invalid ? ' aria-describedby="wizard-error-split_type"' : ""}>${Object.entries(options).map(([value, label]) => `
            <label class="wizard-choice">
                <input type="radio" name="split_type" value="${esc(value)}"${state.answers.split_type === value ? " checked" : ""}${invalidAttributes("split_type", state)}>
                <span class="wizard-choice__surface"><span>${esc(label)}</span><i class="fas fa-check" aria-hidden="true"></i></span>
            </label>
        `).join("")}</div>${fieldError("split_type", state)}`;
    }

    function workoutRecommendationFingerprint(state) {
        const answers = state.answers;
        return JSON.stringify({
            goal: answers.goal,
            experience_level: answers.experience_level,
            days_per_week: answers.days_per_week,
            session_duration: answers.session_duration,
            equipment: asArray(answers.equipment).slice().sort()
        });
    }

    function workoutFallbackSplit(state) {
        const compatible = SPLITS_BY_DAYS[Number(state.answers.days_per_week)] || ["full_body"];
        return compatible.includes("full_body") ? "full_body" : compatible[0];
    }

    function scheduleWorkoutRecommendation(delay = 150) {
        window.clearTimeout(workoutRecommendationTimer);
        const state = wizardMemory.workout;
        const token = (state.recommendationToken || 0) + 1;
        const fingerprint = workoutRecommendationFingerprint(state);
        state.recommendationToken = token;
        state.recommendationFingerprint = fingerprint;
        state.recommendationStatus = "loading";
        state.recommendation = null;

        const waitForDelay = new Promise((resolve) => {
            workoutRecommendationTimer = window.setTimeout(resolve, delay);
        });
        const waitForTimeout = new Promise((resolve) => window.setTimeout(() => resolve({ timeout: true }), 10000));
        state.recommendationPromise = (async () => {
            await waitForDelay;
            if (activeWizardType !== "workout" || state.step !== 1 || state.recommendationToken !== token || !window.currentUser) return;
            renderWizard({ preserveFocus: true });
            try {
                const response = await Promise.race([
                    apiRequest("/workout_plans/recommendation", {
                        method: "POST",
                        body: buildWizardPayload("workout")
                    }),
                    waitForTimeout
                ]);
                if (state.recommendationToken !== token || state.recommendationFingerprint !== fingerprint) return;
                if (response?.timeout) {
                    state.recommendationStatus = "fallback";
                    state.recommendationMessage = "Não foi possível sugerir uma divisão agora. Você pode ajustar depois.";
                    if (state.splitMode !== "manual") state.answers.split_type = workoutFallbackSplit(state);
                    renderWizard({ preserveFocus: true });
                    return;
                }
                state.recommendation = response;
                state.recommendationStatus = "ready";
                state.recommendationMessage = "";
                if (state.splitMode !== "manual") state.answers.split_type = response.recommended_split;
            } catch (error) {
                if (state.recommendationToken !== token || state.recommendationFingerprint !== fingerprint) return;
                state.recommendationStatus = "fallback";
                state.recommendationMessage = "Não foi possível sugerir uma divisão agora. Você pode ajustar depois.";
                if (state.splitMode !== "manual") state.answers.split_type = workoutFallbackSplit(state);
            }
            if (state.recommendationToken === token) renderWizard({ preserveFocus: true });
        })();
        return state.recommendationPromise;
    }

    function renderWorkoutStep(state) {
        const answers = state.answers;
        if (state.step === 0) {
            return `
                <div class="wizard-step-heading" tabindex="-1"><h4>Sua rotina</h4><p>Escolha um objetivo e uma frequência que caiba de verdade na sua semana.</p></div>
                <div class="wizard-field"><label for="wizard-workout-goal">Objetivo principal</label><select id="wizard-workout-goal" name="goal"${invalidAttributes("goal", state)}><option value="">Selecione um objetivo</option>${selectOptions(WORKOUT_GOALS, answers.goal)}</select>${fieldError("goal", state)}</div>
                <div class="wizard-field-row">
                    <fieldset class="wizard-fieldset"><legend>Experiência</legend>${radioCards("experience_level", EXPERIENCE_LEVELS, answers.experience_level, state, true)}</fieldset>
                    <fieldset class="wizard-fieldset"><legend>Dias por semana</legend>${radioCards("days_per_week", { 2: "2", 3: "3", 4: "4", 5: "5", 6: "6" }, answers.days_per_week, state, true)}</fieldset>
                </div>`;
        }
        if (state.step === 1) {
            return `
                <div class="wizard-step-heading" tabindex="-1"><h4>Tempo e equipamentos</h4><p>Vamos adaptar seu treino à sua disponibilidade.</p></div>
                <div class="wizard-field"><label for="wizard-session-duration">Duração por sessão</label><select id="wizard-session-duration" name="session_duration"${invalidAttributes("session_duration", state)}>${selectOptions({ 20: "20 minutos", 30: "30 minutos", 45: "45 minutos", 60: "60 minutos", 75: "75 minutos", 90: "90 minutos" }, answers.session_duration)}</select>${fieldError("session_duration", state)}</div>
                <fieldset class="wizard-fieldset"><legend>Onde você vai treinar?</legend><p class="wizard-field-hint">Escolha uma opção ou personalize o que você tem disponível.</p>${workoutEquipmentPicker(state)}</fieldset>
                <p class="workout-recommendation-status${state.recommendationStatus === "fallback" ? " is-warning" : ""}" role="status">${state.recommendationStatus === "loading" ? '<i class="fas fa-hourglass-half" aria-hidden="true"></i> Ajustando a estrutura do seu treino...' : esc(state.recommendationMessage || "")}</p>`;
        }
        const advancedOpen = state.advancedOpen || Boolean(state.fieldErrors.split_type || state.fieldErrors.priorities || state.fieldErrors.avoid_exercises);
        const splitMode = state.splitMode === "manual" ? "manual" : "automatic";
        return `
            <div class="wizard-step-heading" tabindex="-1"><h4>Confira seu treino</h4><p>Você pode ajustar os detalhes antes de gerar.</p></div>
            ${renderWizardReview("workout", answers)}
            <div class="wizard-field"><label for="wizard-limitations">Limitações ou dores <span>opcional</span></label><textarea id="wizard-limitations" name="limitations" rows="3" maxlength="500" placeholder="Ex.: desconforto no joelho direito"${invalidAttributes("limitations", state)}>${esc(answers.limitations)}</textarea><small class="wizard-field-hint">Interrompa movimentos que causem dor. O plano não substitui avaliação profissional.</small>${fieldError("limitations", state)}</div>
            <details class="workout-advanced" data-workout-advanced${advancedOpen ? " open" : ""}>
                <summary>Ajustes opcionais <i class="fas fa-chevron-down" aria-hidden="true"></i></summary>
                <div class="workout-advanced__content">
                    <fieldset class="wizard-fieldset"><legend>Divisão semanal</legend>
                        ${radioCards("split_mode", { automatic: "Automática", manual: "Escolher divisão" }, splitMode, state, true)}
                        ${splitMode === "manual" ? workoutSplitCards(state) : '<p class="wizard-field-hint">Vamos escolher a divisão mais adequada com base na sua rotina e equipamentos.</p>'}
                    </fieldset>
                    <div class="wizard-field"><label for="wizard-priorities">Regiões prioritárias <span>opcional</span></label><textarea id="wizard-priorities" name="priorities" rows="3" maxlength="300" placeholder="Ex.: costas e glúteos"${invalidAttributes("priorities", state)}>${esc(answers.priorities)}</textarea>${fieldError("priorities", state)}</div>
                    <div class="wizard-field"><label for="wizard-avoid-exercises">Exercícios que prefere evitar <span>opcional</span></label><input id="wizard-avoid-exercises" name="avoid_exercises" value="${esc(answers.avoid_exercises)}" maxlength="300" placeholder="Ex.: agachamento livre"${invalidAttributes("avoid_exercises", state)}>${fieldError("avoid_exercises", state)}</div>
                </div>
            </details>`;
    }

    function renderWizardReview(type, answers) {
        const rows = type === "diet"
            ? [
                ["Objetivo", labelFor(DIET_GOALS, answers.goal)],
                ["Formato", `${answers.meals_per_day} refeições · ${labelFor(DIET_PATTERNS, answers.diet_pattern).toLowerCase()}`],
                ["Rotina", `${answers.training_days_per_week} treino(s) por semana`],
                ["Cuidados", "Restrições gerenciadas no perfil"],
                ["Preparo", `${labelFor(BUDGETS, answers.budget)}, até ${answers.prep_minutes} min`],
                ["Metas", ["fat_loss", "muscle_gain"].includes(answers.goal) ? `Ritmo ${labelFor(CHANGE_PACES, answers.change_pace).toLowerCase()}` : "Calculadas automaticamente"]
            ]
            : [
                ["Objetivo", labelFor(WORKOUT_GOALS, answers.goal)],
                ["Rotina", `${answers.days_per_week} dias, ${answers.session_duration} min por sessão`],
                ["Experiência", labelFor(EXPERIENCE_LEVELS, answers.experience_level)],
                ["Equipamentos", asArray(answers.equipment).map((value) => labelFor(WORKOUT_EQUIPMENT, value, value)).join(", ")]
            ];
        return `
            <aside class="wizard-review" aria-label="Resumo das respostas">
                <div class="wizard-review__title"><i class="fas fa-clipboard-check" aria-hidden="true"></i><div><strong>Pronto para gerar</strong><span>Revise o resumo ou volte para ajustar qualquer etapa.</span></div></div>
                ${type === "diet" ? `<div class="wizard-review__actions"><button type="button" class="text-button" data-wizard-edit-step="0">Editar base</button><button type="button" class="text-button" data-wizard-edit-step="1">Editar cuidados</button><button type="button" class="text-button" data-wizard-edit-step="2">Editar ajustes</button></div>` : ""}
                <dl>${rows.map(([term, description]) => `<div><dt>${esc(term)}</dt><dd>${esc(description)}</dd></div>`).join("")}</dl>
            </aside>`;
    }

    function workoutGenerationMarkup(state) {
        const checking = Boolean(state.pendingGenerationJob);
        return `
            <section class="workout-generation-state" role="status" aria-live="polite">
                <span class="workout-generation-state__icon"><i class="fas ${checking ? "fa-rotate" : "fa-hourglass-half"}" aria-hidden="true"></i></span>
                <h4>${checking ? "Seu treino ainda está sendo criado" : "Criando seu treino..."}</h4>
                <p>${checking ? "Verifique o resultado para continuar de onde parou, sem gerar outro treino." : (state.generationStatus === "queued" ? "Seu pedido está na fila. Estamos preparando sua rotina." : "Estamos montando sua rotina com base nas suas escolhas.")}</p>
                ${checking ? '<button type="button" class="btn-primary" data-wizard-action="check-generation">Verificar resultado</button>' : `<dl><div><dt>Objetivo</dt><dd>${esc(labelFor(WORKOUT_GOALS, state.answers.goal))}</dd></div><div><dt>Rotina</dt><dd>${esc(`${state.answers.days_per_week} dias · ${state.answers.session_duration} min`)}</dd></div></dl>`}
            </section>`;
    }

    function dietGenerationMarkup(state) {
        const checking = Boolean(state.pendingGenerationJob);
        return `
            <section class="diet-generation-state" role="status" aria-live="polite">
                <span class="diet-generation-state__icon"><i class="fas ${checking ? "fa-rotate" : "fa-spinner fa-spin"}" aria-hidden="true"></i></span>
                <h4>${checking ? "Seu plano ainda está sendo criado" : "Criando seu plano alimentar..."}</h4>
                <p>${checking ? "Verifique o resultado para continuar sem gerar outro plano." : (state.generationStatus === "queued" ? "Seu pedido está na fila. Estamos preparando seu cardápio." : "Estamos montando seus dias com base nas suas escolhas.")}</p>
                ${checking ? '<button type="button" class="btn-primary" data-wizard-action="check-generation">Verificar resultado</button>' : `<dl><div><dt>Objetivo</dt><dd>${esc(labelFor(DIET_GOALS, state.answers.goal))}</dd></div><div><dt>Formato</dt><dd>${esc(`${state.answers.meals_per_day} refeições`)}</dd></div></dl>`}
            </section>`;
    }

    function capturedWizardFocus() {
        const current = document.activeElement;
        if (!current?.closest?.("#guidedPlanModal")) return null;
        return { id: current.id, name: current.name, value: current.value };
    }

    function restoreWizardFocus(focus) {
        if (!focus) return;
        requestAnimationFrame(() => {
            const target = (focus.id && byId(focus.id))
                || (focus.name && document.querySelector(`#guidedPlanModal [name="${CSS.escape(focus.name)}"][value="${CSS.escape(focus.value || "")}"]`))
                || document.querySelector(`#guidedPlanModal [name="${CSS.escape(focus.name || "")}"]`);
            target?.focus?.({ preventScroll: true });
        });
    }

    function renderWizard(options = {}) {
        if (activeWizardType === "diet") loadIngredientPool();
        if (!activeWizardType) return;
        const type = activeWizardType;
        const state = wizardMemory[type];
        const modal = byId("guidedPlanModal");
        const stepContainer = byId("planWizardStep");
        if (!modal || !stepContainer) return;
        const focus = options.preserveFocus ? capturedWizardFocus() : null;

        const isDiet = type === "diet";
        modal.classList.toggle("plan-wizard-modal--workout", !isDiet);
        modal.classList.toggle("plan-wizard-modal--diet", isDiet);
        modal.classList.toggle("is-generating", Boolean(state.generating));
        byId("planWizardTitle").textContent = isDiet ? "Criar plano alimentar" : "Criar treino";
        byId("planWizardDescription").textContent = isDiet
            ? "Três dias rotativos alinhados às suas preferências."
            : `Etapa ${state.step + 1} de 3`;
        byId("planWizardKicker").textContent = `Etapa ${state.step + 1} de 3`;
        byId("planWizardIcon").className = `plan-wizard__icon${isDiet ? "" : " plan-wizard__icon--workout"}`;
        byId("planWizardIcon").innerHTML = `<i class="fas ${isDiet ? "fa-apple-alt" : "fa-dumbbell"}" aria-hidden="true"></i>`;

        const steps = WIZARD_STEPS[type];
        byId("planWizardSteps").innerHTML = steps.map((label, index) => {
            const status = index < state.step ? "complete" : index === state.step ? "active" : "";
            const current = index === state.step ? ' aria-current="step"' : "";
            return `<li class="${status}"${current}><span>${index < state.step ? '<i class="fas fa-check" aria-hidden="true"></i>' : index + 1}</span><small>${esc(label)}</small></li>`;
        }).join("");
        byId("planWizardProgressBar").style.width = `${((state.step + 1) / steps.length) * 100}%`;
        stepContainer.innerHTML = state.generating || state.pendingGenerationJob
            ? (isDiet ? dietGenerationMarkup(state) : workoutGenerationMarkup(state))
            : (isDiet ? renderDietStep(state) : renderWorkoutStep(state));
        stepContainer.setAttribute("aria-busy", state.generating ? "true" : "false");

        const errorElement = byId("planWizardError");
        if (state.error) {
            if (state.uncertainSubmission) {
                errorElement.innerHTML = `${esc(state.error)} <button type="button" class="text-button" data-wizard-action="open-generation-library">Ver meus planos</button>`;
            } else errorElement.textContent = state.error;
            errorElement.classList.remove("hidden");
        } else {
            errorElement.textContent = "";
            errorElement.classList.add("hidden");
        }

        const backButton = byId("planWizardBack");
        backButton.classList.toggle("hidden", state.step === 0);
        const nextLabel = byId("planWizardNextLabel");
        const nextIcon = byId("planWizardNextIcon");
        if (state.generating) {
            nextLabel.textContent = isDiet ? "Criando plano..." : "Criando seu treino...";
            nextIcon.className = isDiet ? "fas fa-spinner fa-spin" : "fas fa-hourglass-half";
        } else if (state.step === 2) {
            nextLabel.textContent = isDiet ? "Gerar plano alimentar" : "Gerar plano";
            nextIcon.className = "fas fa-wand-magic-sparkles";
        } else if (state.step === 1) {
            nextLabel.textContent = "Revisar";
            nextIcon.className = "fas fa-arrow-right";
        } else {
            nextLabel.textContent = "Continuar";
            nextIcon.className = "fas fa-arrow-right";
        }

        const actions = modal.querySelector(".plan-wizard__actions");
        actions?.classList.toggle("hidden", Boolean(state.generating || state.pendingGenerationJob));

        modal.dataset.modalLocked = state.generating ? "true" : "false";
        const form = byId("guidedPlanForm");
        form.querySelectorAll("input, select, textarea, button").forEach((control) => {
            control.disabled = state.generating;
        });
        if (options.focusHeading) {
            requestAnimationFrame(() => stepContainer.querySelector(".wizard-step-heading")?.focus());
        }
        if (!isDiet && !state.generating && !state.pendingGenerationJob) {
            stepContainer.querySelector("[data-workout-advanced]")?.addEventListener("toggle", (event) => {
                state.advancedOpen = event.currentTarget.open;
            });
        }
        if (isDiet && !state.generating && !state.pendingGenerationJob) {
            stepContainer.querySelector("[data-diet-preferences]")?.addEventListener("toggle", (event) => {
                state.preferencesOpen = event.currentTarget.open;
            });
            stepContainer.querySelector("[data-diet-customization]")?.addEventListener("toggle", (event) => {
                state.customizationOpen = event.currentTarget.open;
            });
            stepContainer.querySelector("[data-diet-targets]")?.addEventListener("toggle", (event) => {
                state.targetsOpen = event.currentTarget.open;
            });
        }
        restoreWizardFocus(focus);
    }

    function workoutWizardOwnerKey() {
        return `user:${window.currentUser?.id || "anonymous"}`;
    }

    function missingDietProfileFields(profile) {
        const required = {
            age: "Informe sua idade.",
            gender: "Informe o sexo usado no cálculo nutricional.",
            activity_level: "Informe seu nível de atividade.",
            weight: "Informe seu peso.",
            height: "Informe sua altura."
        };
        return Object.fromEntries(Object.entries(required).filter(([field]) => {
            const value = profile?.[field];
            if (value == null || value === "") return true;
            if (field === "age") return !Number.isFinite(Number(value)) || Number(value) < 18 || Number(value) > 120;
            if (field === "weight") return !Number.isFinite(Number(value)) || Number(value) < 30 || Number(value) > 300;
            if (field === "height") return !Number.isFinite(Number(value)) || Number(value) < 120 || Number(value) > 250;
            if (field === "activity_level") return !["sedentario", "leve", "moderado", "intenso"].includes(String(value).toLowerCase());
            if (field === "gender") return !["masculino", "homem", "male", "feminino", "mulher", "female"].includes(String(value).toLowerCase());
            return false;
        }).map(([field, message]) => [`profile.${field}`, message]));
    }

    async function ensureDietProfileBeforeWizard() {
        if (!window.currentUser) return true;
        try {
            const response = await fetch(`${API_BASE}/profile`, { credentials: "include" });
            if (!response.ok) throw new Error("Não foi possível verificar seu perfil.");
            const data = await response.json();
            const fields = missingDietProfileFields(data.profile);
            if (Object.keys(fields).length) {
                window.requestProfileCompletion?.(() => openPlanWizard("diet"), f…50000 tokens truncated…t result = await apiRequest(`/workout_plans/${apiSegment(workoutView.plan.id)}/exercises/${apiSegment(exercise.id)}`, {
                method: "PATCH",
                body: { catalog_key: catalogKey }
            });
            applyWorkoutPlanUpdate(result, dayId);
            showToast("Exercício substituído no plano.", "success");
        } catch (error) {
            panel.applying = "";
            panel.error = error.message;
            renderWorkoutDetail({ preserveScroll: true, focusSelector: `#replacement-panel-${exercise.id}` });
        }
    }

    async function toggleAddPlanExercise() {
        if (workoutView.session || !workoutView.editMode) return;
        workoutView.addExerciseOpen = !workoutView.addExerciseOpen;
        if (!workoutView.addExerciseOpen || workoutView.exerciseCatalog.length) {
            renderWorkoutDetail({ preserveScroll: true });
            return;
        }
        workoutView.catalogLoading = true;
        renderWorkoutDetail({ preserveScroll: true });
        try {
            const result = await apiRequest(`/workout_plans/${apiSegment(workoutView.plan.id)}/exercises/catalog`);
            workoutView.exerciseCatalog = asArray(result.items);
        } catch (error) {
            workoutView.addExerciseOpen = false;
            showToast(error.message, "error");
        } finally {
            workoutView.catalogLoading = false;
            renderWorkoutDetail({ preserveScroll: true });
        }
    }

    async function addPlanExercise() {
        const day = selectedWorkoutDay();
        if (!day?.id || !workoutView.editMode || workoutView.pendingAction) return;
        const exerciseName = byId("workoutAddExerciseName")?.value?.trim() || "";
        const catalogItem = workoutView.exerciseCatalog.find((item) => String(item.name).toLocaleLowerCase() === exerciseName.toLocaleLowerCase());
        const payload = {
            catalog_key: catalogItem?.key || null,
            name: exerciseName,
            sets: Number(byId("workoutAddSets")?.value),
            reps: byId("workoutAddReps")?.value,
            rest_seconds: Number(byId("workoutAddRest")?.value)
        };
        workoutView.pendingAction = "add-exercise";
        renderWorkoutDetail({ preserveScroll: true });
        try {
            const result = await apiRequest(`/workout_plans/${apiSegment(workoutView.plan.id)}/days/${apiSegment(day.id)}/exercises`, {
                method: "POST",
                body: payload
            });
            workoutView.pendingAction = "";
            applyWorkoutPlanUpdate(result, day.id);
            showToast("Exercício adicionado ao treino.", "success");
        } catch (error) {
            workoutView.pendingAction = "";
            showToast(error.message, "error");
            renderWorkoutDetail({ preserveScroll: true });
        }
    }

    async function deletePlanExercise(exerciseId) {
        const exercise = findSelectedExercise(exerciseId);
        const dayId = selectedWorkoutDay()?.id;
        if (!exercise || !workoutView.editMode || workoutView.pendingAction || !window.confirm(`Remover ${exercise.name} deste plano?`)) return;
        workoutView.pendingAction = `delete-${exercise.id}`;
        try {
            const result = await apiRequest(`/workout_plans/${apiSegment(workoutView.plan.id)}/exercises/${apiSegment(exercise.id)}`, { method: "DELETE" });
            workoutView.pendingAction = "";
            applyWorkoutPlanUpdate(result, dayId);
            showToast("Exercício removido do plano.", "success");
        } catch (error) {
            workoutView.pendingAction = "";
            showToast(error.message, "error");
        }
    }

    function selectSessionExercise(exerciseId) {
        const exercises = asArray(selectedWorkoutDay()?.exercises);
        if (!exercises.some((exercise) => String(exercise.id) === String(exerciseId))) return;
        const currentId = document.querySelector("[data-workout-exercise-card]")?.dataset.exerciseId;
        if (currentId && workoutView.setEntryMode === "review" && !completedWorkoutExerciseIds().has(String(currentId))) captureWorkoutSetDraft(currentId);
        workoutView.activeExerciseId = String(exerciseId);
        workoutView.actionFeedback = "";
        workoutView.playerScreen = "exercise";
        workoutView.sessionSheetExpanded = false;
        workoutView.setEntryMode = "closed";
        workoutView.activeSetIndex = null;
        workoutView.correctionSetIndex = null;
        workoutView.setEntryError = "";
        persistWorkoutDraftLocally(workoutView.session?.id);
        renderWorkoutDetail({ focusSelector: "#currentExerciseTitle" });
    }

    function openWorkoutFinishCard() {
        const exercises = asArray(selectedWorkoutDay()?.exercises);
        if (!workoutView.session || !exercises.length || workoutView.pendingAction || workoutView.uncertainMutation) return false;
        const currentId = document.querySelector("[data-workout-exercise-card]")?.dataset.exerciseId;
        if (currentId && workoutView.setEntryMode === "review" && !completedWorkoutExerciseIds().has(String(currentId))) captureWorkoutSetDraft(currentId);
        if (!exercises.some((exercise) => String(exercise.id) === String(workoutView.activeExerciseId))) {
            workoutView.activeExerciseId = String(exercises[exercises.length - 1].id);
        }
        workoutView.playerScreen = "finish";
        workoutView.sessionSheetExpanded = false;
        workoutView.setEntryMode = "closed";
        persistWorkoutDraftLocally(workoutView.session.id);
        renderWorkoutDetail({ focusSelector: "#workoutFinishCardTitle" });
        return true;
    }

    function returnFromWorkoutFinishCard() {
        const exercises = asArray(selectedWorkoutDay()?.exercises);
        if (!workoutView.session || !exercises.length || workoutView.pendingAction || workoutView.uncertainMutation) return false;
        if (!exercises.some((exercise) => String(exercise.id) === String(workoutView.activeExerciseId))) {
            workoutView.activeExerciseId = String(exercises[exercises.length - 1].id);
        }
        workoutView.playerScreen = "exercise";
        workoutView.sessionSheetExpanded = false;
        workoutView.setEntryMode = "closed";
        persistWorkoutDraftLocally(workoutView.session.id);
        renderWorkoutDetail({ focusSelector: "#currentExerciseTitle" });
        return true;
    }

    function navigateSessionExercise(direction) {
        const exercises = asArray(selectedWorkoutDay()?.exercises);
        if (workoutView.playerScreen === "finish") return direction < 0 ? returnFromWorkoutFinishCard() : false;
        const currentIndex = exercises.findIndex((exercise) => String(exercise.id) === String(workoutView.activeExerciseId));
        const target = exercises[currentIndex + direction];
        if (!target && direction > 0 && currentIndex === exercises.length - 1) return openWorkoutFinishCard();
        if (!target) return false;
        selectSessionExercise(target.id);
        return true;
    }

    function skipSessionExercise(exerciseId) {
        if (!workoutView.session || completedWorkoutExerciseIds().has(String(exerciseId))) return;
        if (workoutView.setEntryMode === "review") captureWorkoutSetDraft(exerciseId);
        workoutView.skippedExerciseIds.add(String(exerciseId));
        const nextExercise = firstPendingWorkoutExercise(asArray(selectedWorkoutDay()?.exercises), completedWorkoutExerciseIds());
        workoutView.activeExerciseId = nextExercise ? String(nextExercise.id) : String(exerciseId);
        workoutView.playerScreen = nextExercise ? "exercise" : "finish";
        workoutView.sessionSheetExpanded = false;
        workoutView.setEntryMode = "closed";
        workoutView.activeSetIndex = null;
        workoutView.correctionSetIndex = null;
        workoutView.rest = null;
        persistWorkoutDraftLocally(workoutView.session.id);
        renderWorkoutDetail({ focusSelector: nextExercise ? "#currentExerciseTitle" : "#workoutFinishCardTitle" });
    }

    function resumeSessionExercise(exerciseId) {
        workoutView.skippedExerciseIds.delete(String(exerciseId));
        workoutView.activeExerciseId = String(exerciseId);
        workoutView.playerScreen = "exercise";
        workoutView.sessionSheetExpanded = false;
        workoutView.setEntryMode = "closed";
        workoutView.activeSetIndex = null;
        workoutView.correctionSetIndex = null;
        persistWorkoutDraftLocally(workoutView.session?.id);
        renderWorkoutDetail({ focusSelector: "#currentExerciseTitle" });
    }

    async function setWorkoutSetCompleted(row, exerciseId, completed) {
        if (!row || !exerciseId || workoutView.pendingAction) return;
        const load = row.querySelector("[data-workout-set-load]")?.value.trim() || "";
        const repetitions = row.querySelector("[data-workout-set-repetitions]")?.value.trim() || "";
        if (completed && load && !repetitions) {
            showToast("Informe as repetições ou deixe carga e repetições vazias.", "error");
            row.querySelector("[data-workout-set-repetitions]")?.focus();
            return;
        }
        workoutView.actionFeedback = completed ? "Série registrada neste dispositivo." : "Série reaberta neste dispositivo.";
        row.dataset.workoutSetCompleted = String(completed);
        row.classList.toggle("is-complete", completed);
        captureWorkoutSetDraft(exerciseId);
        if (completed) {
            workoutView.lastConfirmedSet = { exerciseId: String(exerciseId), index: Number(row.dataset.workoutSetIndex) };
            startWorkoutRest(displayedExercise(findSelectedExercise(exerciseId)).exercise.rest_seconds, exerciseId);
        } else {
            workoutView.rest = null;
            persistWorkoutDraftLocally(workoutView.session?.id);
            renderWorkoutDetail({ preserveScroll: true });
        }
    }

    function removeWorkoutSet(row, exerciseId) {
        const rows = Array.from(row?.parentElement?.querySelectorAll(".workout-set-row") || []);
        if (!row || !exerciseId || rows.length <= 1 || row.dataset.workoutSetCompleted === "true") return;
        captureWorkoutSetDraft(exerciseId);
        const drafts = asArray(workoutView.setDrafts.get(String(exerciseId)));
        drafts.splice(Number(row.dataset.workoutSetIndex), 1);
        workoutView.setDrafts.set(String(exerciseId), drafts);
        scheduleWorkoutDraftSave(exerciseId);
        renderWorkoutDetail({ preserveScroll: true });
    }

    async function completeWorkoutExercise(exerciseId) {
        const exercise = findSelectedExercise(exerciseId), session = workoutView.session;
        const key = String(exerciseId);
        if (!exercise || !session || workoutView.pendingAction || workoutView.uncertainMutation || workoutView.completingExerciseIds.has(key) || completedWorkoutExerciseIds().has(key)) return false;
        workoutView.actionFeedback = "";
        workoutView.sessionError = "";
        let sets;
        try { sets = performedSetsFromView(exercise.id); }
        catch (error) {
            workoutView.sessionError = error.message;
            workoutView.sessionSheetExpanded = true;
            workoutView.setEntryMode = "review";
            renderWorkoutDetail({preserveScroll: true});
            const field = document.querySelector(`[data-workout-set-index="${error.index}"] [data-workout-set-${error.field}]`);
            field?.setAttribute("aria-invalid", "true");
            field?.focus({preventScroll: true});
            updateWorkoutVisualViewport();
            return false;
        }
        const draftBefore = asArray(workoutView.setDrafts.get(key)).map(set => ({ ...set }));
        const optimisticIds = new Set(completedWorkoutExerciseIds());
        optimisticIds.add(key);
        workoutView.completingExerciseIds.add(key);
        workoutView.session = { ...session, completed_exercise_ids: [...optimisticIds] };
        workoutView.completedSetCounts.set(key, sets.length);
        workoutView.skippedExerciseIds.delete(key);
        clearWorkoutExerciseDraft(session.id, exercise.id);
        closeReplacementPanel(exercise.id);
        const next = firstPendingWorkoutExercise(asArray(selectedWorkoutDay()?.exercises), optimisticIds);
        workoutView.activeExerciseId = next ? String(next.id) : key;
        workoutView.playerScreen = next ? "exercise" : "finish";
        workoutView.sessionSheetExpanded = false;
        workoutView.setEntryMode = "closed";
        workoutView.activeSetIndex = null;
        workoutView.correctionSetIndex = null;
        workoutView.rest = null;
        workoutView.draftError = "";
        persistWorkoutDraftLocally(session.id);
        renderWorkoutDetail({ preserveScroll: true });

        const account = workoutAccount(), version = workoutView.viewVersion;
        try {
            const result = await queueSessionWrite(session.id, () => apiRequest(`/workout_sessions/${apiSegment(session.id)}/exercises/${apiSegment(exercise.id)}/complete`, {method: "POST", body: {sets}}));
            if (!workoutContextCurrent(account, version, session.id)) return true;
            if (result.session) {
                const localIds = completedWorkoutExerciseIds();
                workoutView.session = {
                    ...result.session,
                    completed_exercise_ids: [...new Set([...asArray(result.session.completed_exercise_ids).map(String), ...localIds])]
                };
                activeWorkoutSummary = { ...activeWorkoutSummary, session: workoutView.session };
                workoutView.actionFeedback = "Exercício confirmado.";
            } else if (result.queued) {
                workoutView.sessionError = "Concluído neste dispositivo. Aguardando sincronização.";
            }
            invalidateWorkoutReads();
            return true;
        } catch (error) {
            if (!workoutContextCurrent(account, version, session.id)) return false;
            if (["timeout", "offline"].includes(error.code)) {
                if (draftBefore.length) workoutView.setDrafts.set(key, draftBefore);
                workoutView.sessionError = "Concluído neste dispositivo. Aguardando sincronização.";
                persistWorkoutDraftLocally(session.id);
                renderWorkoutDetail({ preserveScroll: true });
                return true;
            }
            const restoredIds = completedWorkoutExerciseIds();
            restoredIds.delete(key);
            workoutView.session = { ...workoutView.session, completed_exercise_ids: [...restoredIds] };
            workoutView.completedSetCounts.delete(key);
            if (draftBefore.length) workoutView.setDrafts.set(key, draftBefore);
            workoutView.activeExerciseId = key;
            workoutView.playerScreen = "exercise";
            workoutView.sessionSheetExpanded = true;
            workoutView.setEntryMode = "review";
            workoutView.sessionError = error.message || "Não foi possível concluir este exercício.";
            persistWorkoutDraftLocally(session.id);
            renderWorkoutDetail({ preserveScroll: true });
            return false;
        } finally {
            workoutView.completingExerciseIds.delete(key);
            if (workoutContextCurrent(account, version, session.id)) {
                byId("viewWorkoutPlanDetails")?.setAttribute("aria-busy", String(Boolean(workoutView.pendingAction || workoutView.completingExerciseIds.size)));
                updateWorkoutPlayerFeedback();
            }
        }
    }

    async function finishWorkoutSession() {
        const session = workoutView.session;
        if (!session || workoutView.pendingAction || workoutView.uncertainMutation || workoutView.completingExerciseIds.size) return;
        const exercises = asArray(selectedWorkoutDay()?.exercises);
        const completedIds = completedWorkoutExerciseIds();
        const progressState = workoutExecutionProgress(exercises, completedIds);
        const finishState = workoutFinishState(exercises, completedIds);
        const provisionalSummary = workoutCompletionSnapshot(selectedWorkoutDay(), exercises, progressState, finishState);
        let completedSummary;
        const succeeded = await performSessionMutation("finish", `/workout_sessions/${apiSegment(session.id)}/finish`, {method: "POST"}, result => {
            workoutView.session = null;
            workoutView.completedSummary = {
                ...provisionalSummary,
                ...(result.summary || {}),
                skipped_exercises: finishState.skippedExercises.map((exercise) => ({ id: exercise.id, name: displayedExercise(exercise).exercise.name })),
                skipped_count: finishState.skippedExercises.length,
                completion_state: result.summary?.completion_state || finishState.completionState,
                sync_pending: Boolean(result.queued),
                weekly_progress: result.weekly_progress,
                exercise_goals_reached: asArray(result.exercise_goals_reached),
                achievements_unlocked: asArray(result.achievements_unlocked),
            };
            completedSummary = workoutView.completedSummary;
            workoutView.summaryOrigin = "workout";
            workoutView.shareOpen = false;
            workoutView.shareDraft = null;
            workoutView.sharePhotoToken += 1;
            resetWorkoutExecutionState();
            clearLocalWorkoutDraft(session.id);
            clearActiveWorkoutDock();
            workoutView.replacementPanels.clear();
            window.invalidateProgressOverview?.();
            showToast(result.queued ? "Finalização salva. O histórico será sincronizado quando a conexão voltar." : "Treino finalizado. Excelente trabalho!", result.queued ? "info" : "success");
        });
        if (!succeeded || workoutView.completedSummary !== completedSummary) return;
        const title = byId('completedWorkoutTitle');
        title?.focus({ preventScroll: true });
        const summary = title?.closest('.completed-workout-summary');
        if (summary && !completedSummary.sync_pending) {
            window.Fluid?.animate(summary, { y: 0, opacity: 1 }, {
                duration: 200, from: { y: 6, opacity: 0 }
            });
        }
    }

    async function cancelWorkoutSession() {
        const session = workoutView.session;
        if (!session || workoutView.pendingAction || workoutView.uncertainMutation) return;
        if (!window.confirm("Cancelar o treino atual? Todo progresso desta sessão será apagado.")) return;
        await performSessionMutation("cancel", `/workout_sessions/${apiSegment(session.id)}`, {method: "DELETE"}, () => {
            workoutView.session = null;
            resetWorkoutExecutionState();
            clearLocalWorkoutDraft(session.id);
            clearReplacementPanels();
            clearActiveWorkoutDock();
        });
    }

    async function deleteWorkoutActivity(activityId) {
        if (!activityId || !window.confirm("Excluir esta atividade do histórico? Esta ação não pode ser desfeita.")) return;
        showGlobalLoading("Excluindo atividade...");
        try {
            await apiRequest(`/activities/${apiSegment(activityId)}`, { method: "DELETE" });
            workoutView.completedSummary = null;
            workoutView.shareOpen = false;
            workoutView.shareDraft = null;
            workoutView.sharePhotoToken += 1;
            workoutView.summaryOrigin = "workout";
            closeViewWorkoutPlanModal();
            showTab("activities");
            window.loadWorkoutActivities?.();
            window.invalidateProgressOverview?.();
            window.loadProgressOverview?.();
            showToast("Atividade excluída.", "success");
        } catch (error) {
            showToast(error.message, "error");
        } finally {
            hideGlobalLoading();
        }
    }

    function trapWizardFocus(event) {
        const modal = byId("guidedPlanModal");
        if (!modal?.classList.contains("show")) return;
        const state = activeWizardType ? wizardMemory[activeWizardType] : null;
        if (event.key === "Escape") {
            event.preventDefault();
            event.stopImmediatePropagation();
            if (!state?.generating) closePlanWizard();
            return;
        }
        if (event.key !== "Tab") return;
        const focusable = Array.from(modal.querySelectorAll("button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])"))
            .filter((element) => element.offsetParent !== null);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }

    function tabIndexFromKey(event, currentIndex, total) {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) || total < 2) return null;
        if (event.key === "Home") return 0;
        if (event.key === "End") return total - 1;
        const direction = event.key === "ArrowRight" ? 1 : -1;
        return (currentIndex + direction + total) % total;
    }

    function workoutGestureAllowed(gesture) {
        return !workoutView.pendingAction && !workoutView.uncertainMutation && !workoutView.replacementPanels.size
            && (!gesture || workoutContextCurrent(gesture.account, gesture.version, gesture.sessionId));
    }

    function workoutGestureHasTarget(screen, exerciseId, direction) {
        const exercises = asArray(selectedWorkoutDay()?.exercises);
        if (screen === "finish") return direction < 0 && exercises.length > 0;
        const currentIndex = exercises.findIndex((exercise) => String(exercise.id) === String(exerciseId));
        if (currentIndex < 0) return false;
        return Boolean(exercises[currentIndex + direction]) || (direction > 0 && currentIndex === exercises.length - 1);
    }

    function startWorkoutPlayerGesture(event) {
        if (!event.isPrimary) { cancelWorkoutPlayerGesture(); return; }
        if (event.button > 0 || !workoutView.session || !workoutGestureAllowed()) return;
        const stage = event.target.closest(".current-exercise-stage--player");
        if (!stage) return;
        const handle = event.target.closest(".workout-sheet-handle");
        if (event.target.closest(".workout-quick-set-layer")) return;
        if (event.target.closest(".workout-session-sheet") && !handle) return;
        if (!handle && event.target.closest("button, input, select, textarea, label, a, summary, details")) return;
        workoutGesture = {pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, deltaX: 0, deltaY: 0,
            axis: handle ? "vertical" : null, moved: false, handle: Boolean(handle), expanded: workoutView.setEntryMode === "review",
            screen: workoutView.playerScreen, exerciseId: workoutView.activeExerciseId,
            account: workoutAccount(), version: workoutView.viewVersion, sessionId: workoutView.session.id,
            stage, sheet: stage.querySelector(".workout-session-sheet")};
        stage.setPointerCapture?.(event.pointerId);
    }

    function moveWorkoutPlayerGesture(event) {
        const g = workoutGesture;
        if (!g || g.pointerId !== event.pointerId) return;
        if (!workoutGestureAllowed(g)) { cancelWorkoutPlayerGesture(); return; }
        g.deltaX = event.clientX - g.startX; g.deltaY = event.clientY - g.startY;
        const x = Math.abs(g.deltaX), y = Math.abs(g.deltaY);
        if (!g.axis && Math.max(x,y) >= 12) {
            if (x >= y * 1.3) g.axis = "horizontal";
            else if (y >= x * 1.3) g.axis = "vertical";
        }
        if (!g.axis) return;
        g.moved = Math.max(x,y) >= 12;
        if (g.screen === "finish" && g.axis === "vertical") return;
        event.preventDefault();
        if (g.axis === "horizontal") {
            const direction = g.deltaX < 0 ? 1 : -1;
            const hasTarget = workoutGestureHasTarget(g.screen, g.exerciseId, direction);
            g.stage.style.setProperty("--player-preview-offset", g.deltaX >= 0 ? "-100%" : "100%");
            const translated = hasTarget ? g.deltaX * .55 : g.deltaX * .16;
            g.stage.style.setProperty("--player-swipe-x", `${Math.max(-110, Math.min(110, translated))}px`);
            g.stage.classList.add("is-player-dragging");
        } else if (g.sheet && g.handle && workoutView.setEntryMode === "review") {
            const peek = parseFloat(getComputedStyle(g.stage).getPropertyValue("--sheet-peek")) || 76;
            const collapsed = Math.max(0,g.sheet.offsetHeight-peek);
            g.sheet.style.transform = `translateY(${Math.max(0,Math.min(collapsed,(g.expanded ? 0 : collapsed)+g.deltaY))}px)`;
            g.sheet.classList.add("is-dragging");
        }
    }

    function endWorkoutPlayerGesture(event) {
        const g = workoutGesture;
        if (!g || g.pointerId !== event.pointerId) return;
        const allowed = workoutGestureAllowed(g);
        cancelWorkoutPlayerGesture(event);
        if (!allowed || !g.moved) return;
        if (g.handle) { ignoreNextWorkoutSheetClick = true; setTimeout(() => { ignoreNextWorkoutSheetClick = false; },400); }
        if (g.screen === "finish" && g.axis === "vertical") return;
        if (g.axis === "vertical" && Math.abs(g.deltaY) >= 44) {
            if (g.deltaY < 0) setWorkoutEntryMode(workoutView.setEntryMode === "review" ? "review" : "quick");
            else setWorkoutEntryMode("closed");
            return;
        }
        if (g.axis !== "horizontal" || Math.abs(g.deltaX) < 58 || Math.abs(g.deltaX) < Math.abs(g.deltaY)*1.3) return;
        const swipeLeft = g.deltaX < 0;
        const direction = swipeLeft ? 1 : -1;
        if (!workoutGestureHasTarget(g.screen, g.exerciseId, direction)) return;
        g.stage.classList.add(swipeLeft ? "is-player-committing-left" : "is-player-committing-right");
        g.stage.style.setProperty("--player-preview-offset", swipeLeft ? "100%" : "-100%");
        g.stage.style.setProperty("--player-swipe-x", swipeLeft ? "-110%" : "110%");
        const finish = () => {
            if (direction > 0) {
                // Advancing is the user's lightweight confirmation that this exercise is done.
                // Completion renders optimistically before its request resolves, so the swipe stays fluid.
                completeWorkoutExercise(g.exerciseId);
                return;
            }
            navigateSessionExercise(direction);
        };
        const frame = callback => {
            if (typeof requestAnimationFrame === "function") requestAnimationFrame(callback);
            else if (typeof window.requestAnimationFrame === "function") window.requestAnimationFrame(callback);
            else setTimeout(callback, 0);
        };
        frame(() => frame(finish));
    }

    function cancelWorkoutPlayerGesture(event) {
        const g = workoutGesture;
        if (!g || (event && g.pointerId !== event.pointerId)) return;
        workoutGesture = null;
        g.stage.classList.remove("is-player-dragging", "is-player-committing-left", "is-player-committing-right");
        g.stage.style.removeProperty("--player-preview-offset");
        g.stage.style.removeProperty("--player-swipe-x");
        g.sheet?.classList.remove("is-dragging");
        if (g.sheet) g.sheet.style.transform = "";
        if (g.stage.hasPointerCapture?.(g.pointerId)) g.stage.releasePointerCapture(g.pointerId);
    }

    async function resumeWorkoutSession() {
        if (!window.currentUser || document.hidden || workoutView.pendingAction) return;
        cancelWorkoutPlayerGesture();
        await loadActiveWorkoutDock(true);
        if (!workoutView.uncertainMutation) await syncWorkoutDrafts();
    }

    function initializePlanExperience() {
        const form = byId("guidedPlanForm");
        form?.addEventListener("submit", handleWizardSubmit);
        form?.addEventListener("input", handleWizardInput);
        form?.addEventListener("change", handleWizardInput);
        form?.addEventListener("keydown", handleWizardKeydown);
        form?.addEventListener("click", (event) => {
            handleIngredientClick(event);
            const action = event.target.closest("[data-wizard-action]")?.dataset.wizardAction;
            if (action === "close") closePlanWizard();
            if (action === "open-profile") window.openProfileEditor?.();
            if (action === "check-generation") {
                if (activeWizardType === "diet") checkDietGeneration();
                else checkWorkoutGeneration();
            }
            if (action === "open-generation-library") {
                const type = activeWizardType;
                closePlanWizard();
                showTab(type === "diet" ? "diet_plans" : "workout_plans");
                if (type === "diet") loadDietPlans();
                else loadWorkoutPlans();
            }
            const editStep = event.target.closest("[data-wizard-edit-step]")?.dataset.wizardEditStep;
            if (editStep != null && activeWizardType === "diet") {
                const state = wizardMemory.diet;
                state.step = Math.max(0, Math.min(2, Number(editStep)));
                state.error = "";
                state.fieldErrors = {};
                renderWizard({ focusHeading: true });
            }
            if (action === "back" && activeWizardType) {
                const state = wizardMemory[activeWizardType];
                if (!state.generating && state.step > 0) {
                    state.step -= 1;
                    state.error = "";
                    state.fieldErrors = {};
                    renderWizard({ focusHeading: true });
                }
            }
        });
        byId("guidedPlanModal")?.addEventListener("click", (event) => {
            if (event.target === event.currentTarget) closePlanWizard();
        });
        document.addEventListener("keydown", trapWizardFocus, true);
        if (!workoutTimerInterval) workoutTimerInterval = window.setInterval(updateWorkoutTimer, 1000);
        if (!workoutRestInterval) workoutRestInterval = window.setInterval(updateWorkoutRestTimer, 1000);
        if (!workoutSyncInterval) {
            workoutSyncInterval = window.setInterval(() => {
                if (window.currentUser && !document.hidden && !workoutView.pendingAction && !workoutView.uncertainMutation && !byId("mainScreen")?.classList.contains("hidden")) loadActiveWorkoutDock();
            }, 30000);
        }
        document.addEventListener("visibilitychange", () => { if (document.hidden) cancelWorkoutPlayerGesture(); });
        window.visualViewport?.addEventListener("resize", updateWorkoutVisualViewport);
        window.visualViewport?.addEventListener("scroll", updateWorkoutVisualViewport);
        window.addEventListener("resize", updateWorkoutVisualViewport);
        byId("viewWorkoutPlanDetails")?.addEventListener("focusin", updateWorkoutVisualViewport);
        byId("viewWorkoutPlanDetails")?.addEventListener("focusout", updateWorkoutVisualViewport);
        window.addEventListener("pagehide", () => persistWorkoutDraftLocally(workoutView.session?.id));
        byId("activeWorkoutDock")?.addEventListener("click", openActiveWorkout);
        ["workoutGoalFilter", "workoutExperienceFilter", "workoutDaysFilter"].forEach((id) => {
            byId(id)?.addEventListener("change", renderFilteredWorkoutPlans);
        });

        document.addEventListener("click", async (event) => {
            const wizardTrigger = event.target.closest("[data-plan-wizard]");
            if (wizardTrigger) {
                event.preventDefault();
                openPlanWizard(wizardTrigger.dataset.planWizard);
                return;
            }
            const workoutTodayAction = event.target.closest("[data-workout-today-action]");
            if (workoutTodayAction) {
                const action = workoutTodayAction.dataset.workoutTodayAction;
                if (action === 'start-today' || action === 'continue-today') await openWorkoutTodayExecution();
                if (action === "open-plan") window.openWorkoutTodayPlan?.();
                if (action === "open-activity" && workoutTodayState?.completed_session?.id) {
                    openWorkoutActivity(workoutTodayState.completed_session.id);
                }
                if (action === "create-workout") openPlanWizard("workout");
                if (action === "open-plans") window.showTab?.("workout_plans");
                if (action === "retry") loadWorkoutTodayCard(true);
                return;
            }
            const retryPlanList = event.target.closest("[data-retry-plan-list]");
            if (retryPlanList) {
                if (retryPlanList.dataset.retryPlanList === "diet") loadDietPlans();
                else loadWorkoutPlans();
                return;
            }
            const workoutWeekday = event.target.closest("[data-workout-weekday]");
            if (workoutWeekday) {
                const weekday = Number(workoutWeekday.dataset.workoutWeekday);
                const current = new Set(window.workoutCurrentWeekdays || []);
                if (current.has(weekday)) current.delete(weekday);
                else current.add(weekday);
                window.workoutCurrentWeekdays = Array.from(current).sort((a, b) => a - b);
                renderWorkoutCurrentModal();
                return;
            }
            if (event.target.closest("[data-workout-current-save]")) {
                saveWorkoutCurrentPlan();
                return;
            }
            if (event.target.closest("[data-workout-current-adapt]")) {
                applyWorkoutCurrentPlanChange("adapt");
                return;
            }
            const clickedCard = event.target.closest(".plan-card[data-plan-action=\"view\"]");
            if (clickedCard && !event.target.closest("button, a, input, select, textarea")) {
                const { planAction: action, planType: type, planId: id } = clickedCard.dataset;
                if (action === "view") {
                    if (type === "diet") await viewDietPlan(id);
                    else await viewWorkoutPlan(id);
                }
                return;
            }
            const planAction = event.target.closest("[data-plan-action]");
            if (!planAction) return;
            const { planAction: action, planType: type, planId: id } = planAction.dataset;
            if (action === "view") {
                if (type === "diet") await viewDietPlan(id);
                else await viewWorkoutPlan(id);
            }
            if (action === "adjust") {
                if (type === "diet") await adjustDietPlan(id);
                else openWorkoutCurrentModal(id);
            }
            if (action === "set-current" && type === "workout") {
                openWorkoutCurrentModal(id);
            }
            if (action === "set-current" && type === "diet") setCurrentDietPlan(id);
            if (action === "delete") deletePlan(type, id);
        });
        document.addEventListener("keydown", (event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            const workoutTodayAction = event.target.closest?.("[data-workout-today-action]");
            if (!workoutTodayAction || event.target !== workoutTodayAction) return;
            event.preventDefault();
            workoutTodayAction.click();
        });

        byId("dietPlansTableBody")?.addEventListener("keydown", async (event) => {
            const card = event.target.closest('.plan-card[data-plan-action="view"]');
            if (!card) return;
            if (event.target.closest("button, a, input, select, textarea")) return;
            if (event.key !== "Enter" && event.key !== " ") return;
            event.preventDefault();
            const { planType: type, planId: id } = card.dataset;
            if (type === "diet") await viewDietPlan(id);
            else await viewWorkoutPlan(id);
        });

        byId("workoutPlansTableBody")?.addEventListener("keydown", async (event) => {
            const card = event.target.closest('.plan-card[data-plan-action="view"]');
            if (!card) return;
            if (event.target.closest("button, a, input, select, textarea")) return;
            if (event.key !== "Enter" && event.key !== " ") return;
            event.preventDefault();
            const { planType: type, planId: id } = card.dataset;
            if (type === "diet") await viewDietPlan(id);
            else await viewWorkoutPlan(id);
        });

        byId("viewDietPlanDetails")?.addEventListener("click", (event) => {
            if (event.target.closest('[data-diet-action="shopping-list"]')) { openShoppingList(); return; }
            if (event.target.closest('[data-diet-action="set-current"]')) {
                setCurrentDietPlan();
                return;
            }
            const tab = event.target.closest("[data-diet-day-index]");
            if (!tab) return;
            const index = Number(tab.dataset.dietDayIndex);
            if (!Number.isInteger(index)) return;
            dietView.selectedDay = index;
            renderDietDetail();
            requestAnimationFrame(() => byId(`diet-day-tab-${index}`)?.focus());
        });
        byId("shoppingListDetails")?.addEventListener("change", (event) => {
            if (event.target.id === "shoppingPeople") { dietShoppingState.people = Number(event.target.value) || 1; renderShoppingList(); return; }
            if (event.target.id === "shoppingHideAvailable") { dietShoppingState.hideAvailable = event.target.checked; renderShoppingList(); return; }
            const check = event.target.closest("[data-shopping-check]");
            if (check) { const key = check.dataset.shoppingCheck; if (check.checked) dietShoppingState.checked.add(key); else dietShoppingState.checked.delete(key); renderShoppingList(); }
        });
        byId("shoppingListDetails")?.addEventListener("click", (event) => {
            if (event.target.closest('[data-shopping-action="share"]')) { shareShoppingList(); return; }
            const substitute = event.target.closest("[data-shopping-substitute]");
            const restore = event.target.closest("[data-shopping-restore]");
            if (substitute) { const item = collectShoppingItems(dietView.plan).find((entry) => entry.key === substitute.dataset.shoppingSubstitute); const options = item && SHOPPING_SUBSTITUTIONS[shoppingNormalize(item.name)]; if (options?.length) dietShoppingState.substitutions.set(item.key, options[0]); renderShoppingList(); }
            if (restore) { dietShoppingState.substitutions.delete(restore.dataset.shoppingRestore); renderShoppingList(); }
        });
        byId("viewDietPlanDetails")?.addEventListener("keydown", (event) => {
            const tab = event.target.closest("[data-diet-day-index]");
            if (!tab) return;
            const index = tabIndexFromKey(event, Number(tab.dataset.dietDayIndex), groupDietMeals(dietView.plan || {}).length);
            if (index == null) return;
            event.preventDefault();
            dietView.selectedDay = index;
            renderDietDetail();
            requestAnimationFrame(() => byId(`diet-day-tab-${index}`)?.focus());
        });

        byId("viewWorkoutPlanDetails")?.addEventListener("click", async (event) => {
            const control = event.target.closest("[data-workout-action]");
            if (!control) return;
            const action = control.dataset.workoutAction;
            if ((workoutView.pendingAction || workoutView.uncertainMutation) && !["retry-session", "close-active-workout"].includes(action)) return;
            if (action === "retry-open-plan") { await viewWorkoutPlan(control.dataset.planId, control.dataset.dayId || null, control.dataset.openIntent || "plan"); return; }
            if (action === "retry-exercise-media") { retryWorkoutExerciseMedia(); return; }
            const exerciseId = control.dataset.exerciseId || control.closest("[data-exercise-id]")?.dataset.exerciseId;
            if (action === "select-day") {
                const index = Number(control.dataset.dayIndex);
                if (!Number.isInteger(index) || index === workoutView.selectedDay) return;
                workoutView.viewVersion += 1;
                workoutView.selectedDay = index;
                workoutView.session = null;
                workoutView.sessionError = "";
                workoutView.pendingAction = "";
                renderWorkoutDetail();
                await loadActiveWorkoutSession();
                requestAnimationFrame(() => byId(`workout-day-tab-${index}`)?.focus());
            } else if (action === "start-session") {
                await startWorkoutSession();
            } else if (action === "use-current-plan") {
                openWorkoutCurrentModal(workoutView.plan.id);
            } else if (action === "enter-plan-edit") {
                setWorkoutPlanEditMode(true);
            } else if (action === "exit-plan-edit") {
                setWorkoutPlanEditMode(false);
            } else if (action === "close-active-workout") {
                closeViewWorkoutPlanModal();
            } else if (action === "select-session-exercise") {
                selectSessionExercise(exerciseId);
            } else if (action === "previous-session-exercise") {
                navigateSessionExercise(-1);
            } else if (action === "next-session-exercise") {
                navigateSessionExercise(1);
            } else if (action === "open-finish-card" || action === "finish-session") {
                openWorkoutFinishCard();
            } else if (action === "return-from-finish") {
                returnFromWorkoutFinishCard();
            } else if (action === "toggle-session-sheet") {
                if (ignoreNextWorkoutSheetClick) {
                    ignoreNextWorkoutSheetClick = false;
                    return;
                }
                setWorkoutSheetExpanded(workoutView.setEntryMode === "closed");
            } else if (action === "close-set-entry") {
                setWorkoutEntryMode("closed");
            } else if (action === "review-sets") {
                setWorkoutEntryMode("review");
            } else if (action === "correct-last-set") {
                const last = workoutView.lastConfirmedSet;
                if (last && String(last.exerciseId) === String(workoutView.activeExerciseId)) {
                    setWorkoutEntryMode("quick", { index: last.index, correction: true });
                }
            } else if (action === "confirm-quick-set") {
                confirmWorkoutQuickSet(exerciseId);
            } else if (action === "confirm-empty-set") {
                confirmWorkoutQuickSet(workoutView.activeExerciseId, { discardPartial: true });
            } else if (action === "add-quick-set") {
                const activeId = String(workoutView.activeExerciseId);
                const drafts = asArray(workoutView.setDrafts.get(activeId)).map(item => ({ ...item }));
                const exercise = findSelectedExercise(activeId);
                while (drafts.length < workoutPlannedSetCount(exercise)) drafts.push({ load_kg: "", repetitions: "", is_warmup: false, completed: false });
                if (drafts.length >= 20) return;
                drafts.push({ load_kg: "", repetitions: "", is_warmup: false, completed: false });
                workoutView.setDrafts.set(activeId, drafts);
                workoutView.activeSetIndex = drafts.length - 1;
                workoutView.correctionSetIndex = null;
                scheduleWorkoutDraftSave(activeId);
                renderWorkoutDetail({ preserveScroll: true, focusSelector: '[data-workout-quick-load], [data-workout-quick-repetitions]' });
            } else if (action === "replacement-options") {
                await openReplacementOptions(exerciseId);
            } else if (action === "permanent-replacement-options") {
                await openPermanentReplacementOptions(exerciseId);
            } else if (action === "show-more-replacements") {
                const panel = workoutView.replacementPanels.get(String(exerciseId));
                if (!panel) return;
                panel.expanded = true;
                renderWorkoutDetail({ preserveScroll: true, focusSelector: `#replacement-panel-${exerciseId}` });
            } else if (action === "close-replacements") {
                closeReplacementPanel(exerciseId);
                const triggerAction = workoutView.editMode ? "permanent-replacement-options" : "replacement-options";
                renderWorkoutDetail({ preserveScroll: true, focusSelector: `[data-workout-action="${triggerAction}"][data-exercise-id="${exerciseId}"]` });
            } else if (action === "apply-replacement") {
                await applyReplacement(exerciseId, control.dataset.catalogKey);
            } else if (action === "apply-permanent-replacement") {
                await applyPermanentReplacement(exerciseId, control.dataset.catalogKey);
            } else if (action === "toggle-add-exercise") {
                await toggleAddPlanExercise();
            } else if (action === "add-plan-exercise") {
                await addPlanExercise();
            } else if (action === "delete-plan-exercise") {
                await deletePlanExercise(exerciseId);
            } else if (action === "restore-exercise") {
                await restoreExercise(exerciseId);
            } else if (action === "complete-exercise") {
                await completeWorkoutExercise(exerciseId, {
                    startRest: true,
                    restSeconds: displayedExercise(findSelectedExercise(exerciseId)).exercise.rest_seconds,
                });
            } else if (action === "toggle-set-complete") {
                const row = control.closest(".workout-set-row");
                if (!row) return;
                const completed = row.dataset.workoutSetCompleted !== "true";
                await setWorkoutSetCompleted(row, exerciseId, completed);
            } else if (action === "complete-current-set") {
                const row = control.closest("[data-workout-exercise-card]")?.querySelector(`.workout-set-row[data-workout-set-index="${control.dataset.workoutSetIndex}"]`);
                await setWorkoutSetCompleted(row, exerciseId, true);
            } else if (action === "remove-set") {
                removeWorkoutSet(control.closest(".workout-set-row"), exerciseId);
            } else if (action === "skip-exercise") {
                skipSessionExercise(exerciseId);
            } else if (action === "resume-exercise") {
                resumeSessionExercise(exerciseId);
            } else if (action === "adjust-rest") {
                adjustWorkoutRest(Number(control.dataset.restSeconds));
            } else if (action === "skip-rest") {
                workoutView.rest = null;
                persistWorkoutDraftLocally(workoutView.session?.id);
                renderWorkoutDetail({ preserveScroll: true });
            } else if (action === "retry-session") {
                if (workoutView.uncertainMutation) await workoutView.uncertainMutation();
                else await loadActiveWorkoutSession();
            } else if (action === "confirm-finish-session") {
                await finishWorkoutSession();
            } else if (action === "cancel-session") {
                await cancelWorkoutSession();
            } else if (action === "add-set") {
                const rows = control.closest(".workout-set-entry")?.querySelector(".workout-set-entry__rows");
                const order = rows?.children.length + 1;
                if (rows && order <= 20) {
                    rows.insertAdjacentHTML("beforeend", workoutSetRowMarkup(order));
                    captureWorkoutSetDraft(exerciseId || control.closest("[data-exercise-id]")?.dataset.exerciseId);
                }
            } else if (action === "open-workout-share") {
                workoutShareDraft(workoutView.completedSummary);
                workoutView.shareOpen = true;
                renderWorkoutDetail({ focusSelector: ".workout-share-header h3" });
            } else if (action === "back-to-summary") {
                workoutView.shareOpen = false;
                window.WorkoutShare?.reset();
                renderWorkoutDetail({ focusSelector: '[data-workout-action="open-workout-share"]' });
            } else if (action === "set-share-mode") {
                const draft = workoutShareDraft(workoutView.completedSummary);
                const newMode = control.dataset.shareMode;
                if (newMode === "photo" || newMode === "dark") {
                    draft.mode = newMode;
                    renderWorkoutDetail({ preserveScroll: true, focusSelector: `[data-workout-action="set-share-mode"][data-share-mode="${newMode}"]` });
                }
            } else if (action === "set-share-panel") {
                workoutShareDraft(workoutView.completedSummary).transparent = control.dataset.sharePanel === "transparent";
                renderWorkoutDetail({ preserveScroll: true, focusSelector: `[data-workout-action="set-share-panel"][data-share-panel="${control.dataset.sharePanel}"]` });
            } else if (["set-share-photo-scale", "set-share-photo-offset-x", "set-share-photo-offset-y"].includes(action)) {
                // The input event already updates the preview without replacing the slider.
            } else if (action === "set-share-info-preset") {
                const draft = workoutShareDraft(workoutView.completedSummary);
                const preset = control.dataset.infoPreset;
                if (["full", "compact", "minimal"].includes(preset)) {
                    draft.infoPreset = preset;
                    renderWorkoutDetail({ preserveScroll: true, focusSelector: `[data-workout-action="set-share-info-preset"][data-info-preset="${preset}"]` });
                }
            } else if (action === "toggle-share-exercise") {
                const draft = workoutShareDraft(workoutView.completedSummary);
                const key = String(exerciseId);
                if (draft.selectedExerciseIds.has(key)) draft.selectedExerciseIds.delete(key);
                else draft.selectedExerciseIds.add(key);
                renderWorkoutDetail({ preserveScroll: true, focusSelector: `[data-workout-action="toggle-share-exercise"][data-exercise-id="${key}"]` });
            } else if (action === "choose-share-photo") {
                byId("workoutSharePhotoInput")?.click();
            } else if (action === "remove-share-photo") {
                workoutView.sharePhotoToken += 1;
                workoutShareDraft(workoutView.completedSummary).photoDataUrl = null;
                renderWorkoutDetail({ preserveScroll: true, focusSelector: '[data-workout-action="choose-share-photo"]' });
            } else if (action === "share-workout-card") {
                await shareWorkoutCard(workoutView.completedSummary);
            } else if (action === "view-exercise-progress") {
                closeViewWorkoutPlanModal();
                window.openExerciseProgress?.(control.dataset.exerciseKey);
            } else if (action === "set-exercise-goal") {
                await createExerciseGoalFromSummary(control.dataset.exerciseKey, control.dataset.exerciseName, control);
            } else if (action === "delete-activity") {
                await deleteWorkoutActivity(workoutView.completedSummary?.session_id);
            } else if (action === "close-summary") {
                const fromActivities = workoutView.summaryOrigin === "activities";
                workoutView.completedSummary = null;
                workoutView.shareOpen = false;
                workoutView.shareDraft = null;
                workoutView.sharePhotoToken += 1;
                workoutView.summaryOrigin = "workout";
                if (fromActivities) {
                    closeViewWorkoutPlanModal();
                    showTab("activities");
                } else {
                    renderWorkoutDetail();
                }
            }
        });
        byId("viewWorkoutPlanDetails")?.addEventListener("change", async (event) => {
            if (event.target.id === "workoutSharePhotoInput") {
                const file = event.target.files?.[0];
                if (!file) return;
                const token = ++workoutView.sharePhotoToken;
                const sessionId = workoutView.completedSummary?.session_id;
                if (!file.type.startsWith("image/")) {
                    showToast("Selecione um arquivo de imagem.", "error");
                    return;
                }
                if (file.size > 15 * 1024 * 1024) {
                    showToast("A foto deve ter no máximo 15 MB.", "error");
                    return;
                }
                try {
                    const image = await downscaleImageFile(file, 1600);
                    if (
                        token !== workoutView.sharePhotoToken
                        || !workoutView.shareOpen
                        || String(workoutView.completedSummary?.session_id) !== String(sessionId)
                    ) return;
                    workoutShareDraft(workoutView.completedSummary).photoDataUrl = image.dataUrl;
                    renderWorkoutDetail({ preserveScroll: true, focusSelector: '[data-workout-action="choose-share-photo"]' });
                } catch (error) {
                    showToast(error.message || "Não foi possível carregar a foto.", "error");
                }
            } else if (event.target.matches("[data-workout-action]")) {
                const action = event.target.dataset.workoutAction;
                if (action?.startsWith("set-share-") && workoutView.shareOpen && !event.target.matches('input[type="range"]')) {
                    renderWorkoutDetail({ preserveScroll: true, focusSelector: `[data-workout-action="${action}"]` });
                }
            }
        });
        byId("viewWorkoutPlanDetails")?.addEventListener("input", (event) => {
            if (event.target.matches("[data-workout-quick-load], [data-workout-quick-repetitions]")) {
                const layer = event.target.closest("[data-workout-set-index]");
                const index = Number(layer?.dataset.workoutSetIndex);
                const field = event.target.hasAttribute("data-workout-quick-load") ? "load_kg" : "repetitions";
                event.target.removeAttribute("aria-invalid");
                updateWorkoutQuickSetDraft(field, event.target.value.trim(), workoutView.activeExerciseId, index);
                return;
            }
            if (event.target.matches("[data-workout-set-load], [data-workout-set-repetitions], [data-workout-set-warmup]")) {
                const exerciseId = event.target.closest("[data-workout-exercise-card]")?.dataset.exerciseId;
                event.target.removeAttribute("aria-invalid");
                captureWorkoutSetDraft(exerciseId);
                return;
            }
            const action = event.target.dataset?.workoutAction;
            if (!action || !workoutView.shareOpen || !workoutView.completedSummary) return;
            const draft = workoutShareDraft(workoutView.completedSummary);
            const value = Number(event.target.value);
            if (action === "set-share-photo-scale") {
                draft.photoScale = Math.max(0.5, Math.min(2, value / 100));
            } else if (action === "set-share-photo-offset-x") {
                draft.photoOffsetX = Math.max(-300, Math.min(300, value));
            } else if (action === "set-share-photo-offset-y") {
                draft.photoOffsetY = Math.max(-300, Math.min(300, value));
            } else {
                return;
            }
            const label = event.target.closest('.workout-share-slider')?.querySelector('small');
            if (label) label.textContent = action === 'set-share-photo-scale' ? `${draft.photoScale.toFixed(1)}x` : `${value}px`;
            syncWorkoutSharePreview();
        });
        byId("viewWorkoutPlanDetails")?.addEventListener("keydown", async (event) => {
            if (event.key === "Enter" && event.target.matches("[data-workout-quick-repetitions]")) {
                event.preventDefault();
                confirmWorkoutQuickSet(workoutView.activeExerciseId);
                return;
            }
            const tab = event.target.closest('[data-workout-action="select-day"]');
            if (!tab) return;
            const index = tabIndexFromKey(event, Number(tab.dataset.dayIndex), workoutView.days.length);
            if (index == null) return;
            event.preventDefault();
            workoutView.viewVersion += 1;
            workoutView.selectedDay = index;
            workoutView.session = null;
            workoutView.sessionError = "";
            workoutView.pendingAction = "";
            renderWorkoutDetail();
            await loadActiveWorkoutSession();
            requestAnimationFrame(() => byId(`workout-day-tab-${index}`)?.focus());
        });
        byId("viewWorkoutPlanDetails")?.addEventListener("focusin", event => {
            const field = event.target;
            if (!field.matches("[data-workout-set-load], [data-workout-set-repetitions], [data-workout-quick-load], [data-workout-quick-repetitions]")) return;
            workoutView.lastField = {exerciseId: String(workoutView.activeExerciseId), index: field.closest("[data-workout-set-index]").dataset.workoutSetIndex, field: field.hasAttribute("data-workout-set-load") || field.hasAttribute("data-workout-quick-load") ? "load" : "repetitions"};
        });
        byId("viewWorkoutPlanDetails")?.addEventListener("pointerdown", startWorkoutPlayerGesture);
        byId("viewWorkoutPlanDetails")?.addEventListener("pointermove", moveWorkoutPlayerGesture);
        byId("viewWorkoutPlanDetails")?.addEventListener("pointerup", endWorkoutPlayerGesture);
        byId("viewWorkoutPlanDetails")?.addEventListener("pointercancel", cancelWorkoutPlayerGesture);
        byId("viewWorkoutPlanDetails")?.addEventListener("lostpointercapture", cancelWorkoutPlayerGesture);
    }

    window.openPlanWizard = openPlanWizard;
    window.buildPlanWizardPayload = buildWizardPayload;
    window.openDietPlanWizardWithPlan = openDietPlanWizardWithPlan;
    window.handlePlanChatAction = handlePlanChatAction;
    window.loadDietPlans = loadDietPlans;
    window.loadWorkoutPlans = loadWorkoutPlans;
    window.loadWorkoutTodayCard = loadWorkoutTodayCard;
    window.resetWorkoutAccount = resetWorkoutAccount;
    window.renderWorkoutTodayCard = renderWorkoutTodayCard;
    window.openWorkoutTodayPlan = openWorkoutTodayPlan;
    window.openWorkoutCurrentModal = openWorkoutCurrentModal;
    window.toggleWorkoutPlansLibrary = toggleWorkoutPlansLibrary;
    window.viewDietPlan = viewDietPlan;
    window.openShoppingList = openShoppingList;
    window.closeShoppingListModal = closeShoppingListModal;
    window.viewWorkoutPlan = viewWorkoutPlan;
    window.openWorkoutActivity = openWorkoutActivity;
    window.loadActiveWorkoutDock = loadActiveWorkoutDock;
    window.resumeWorkoutSession = resumeWorkoutSession;
    window.clearActiveWorkoutDock = clearActiveWorkoutDock;
    window.invalidateWorkoutView = invalidateWorkoutView;

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initializePlanExperience);
    else initializePlanExperience();
})();
