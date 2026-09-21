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
        stability_ball: "Bola suíça"
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
        sessionError: "",
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
    let professionalWizardContext = null;
    let workoutTimerInterval = null;
    let workoutRestInterval = null;
    let workoutSyncInterval = null;
    let workoutRecommendationTimer = null;
    let activeDockRequestToken = 0;
    const sessionWrites = new Map();
    const sessionLocks = new Set();
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
                <p class="workout-recommendation-status${state.recommendationStatus === "fallback" ? " is-warning" : ""}" role="status">${state.recommendationStatus === "loading" ? '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Ajustando a estrutura do seu treino...' : esc(state.recommendationMessage || "")}</p>`;
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
                <span class="workout-generation-state__icon"><i class="fas ${checking ? "fa-rotate" : "fa-spinner fa-spin"}" aria-hidden="true"></i></span>
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
            nextIcon.className = "fas fa-spinner fa-spin";
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

    function workoutWizardOwnerKey(context) {
        return context?.studentId ? `student:${context.studentId}` : `user:${window.currentUser?.id || "anonymous"}`;
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

    async function ensureDietProfileBeforeWizard(context) {
        if (context?.studentId || !window.currentUser) return true;
        try {
            const response = await fetch(`${API_BASE}/profile`, { credentials: "include" });
            if (!response.ok) throw new Error("Não foi possível verificar seu perfil.");
            const data = await response.json();
            const fields = missingDietProfileFields(data.profile);
            if (Object.keys(fields).length) {
                window.requestProfileCompletion?.(() => openPlanWizard("diet", context), fields);
                return false;
            }
        } catch (error) {
            showToast("Complete seu perfil básico antes de gerar o plano alimentar.", "info");
        }
        return true;
    }

    function openPlanWizard(type, context = null, options = {}) {
        if (type !== "diet" && type !== "workout") return;
        if (type === "workout" && !window.requireAuth?.("Entre para criar seu treino.", {
            premium: true,
            resume: () => openPlanWizard(type, context)
        })) return;
        if (type === "diet" && !window.requireAuth?.("Entre para criar seu plano alimentar.", {
            premium: true,
            requiresProfile: true,
            resume: () => openPlanWizard(type, context)
        })) return;
        if (type === "diet" && !options.skipProfileCheck && !context?.studentId) {
            ensureDietProfileBeforeWizard(context).then((ready) => {
                if (ready) openPlanWizard(type, context, { skipProfileCheck: true });
            });
            return;
        }
        if (type === "workout") {
            const ownerKey = workoutWizardOwnerKey(context);
            if (wizardMemory.workout.ownerKey && wizardMemory.workout.ownerKey !== ownerKey) {
                wizardMemory.workout = { step: 0, answers: defaultWorkoutAnswers(), error: "", fieldErrors: {}, generating: false, ownerKey };
            } else wizardMemory.workout.ownerKey = ownerKey;
        }
        if (type === "diet") {
            const ownerKey = workoutWizardOwnerKey(context);
            if (wizardMemory.diet.ownerKey && wizardMemory.diet.ownerKey !== ownerKey) {
                wizardMemory.diet = { step: 0, answers: defaultDietAnswers(), error: "", fieldErrors: {}, generating: false, preferencesOpen: false, customizationOpen: false, targetsOpen: false, ingredientDraft: "", ownerKey };
            } else wizardMemory.diet.ownerKey = ownerKey;
        }
        professionalWizardContext = context;
        activeWizardType = type;
        const modal = byId("guidedPlanModal");
        if (!modal) return;
        renderWizard();
        modal.setAttribute("aria-hidden", "false");
        openAppModal(modal);
        requestAnimationFrame(() => byId("planWizardStep")?.querySelector(".wizard-step-heading")?.focus());
    }

    function openProfessionalPlanWizard(type, studentId) {
        wizardMemory[type] = {
            step: 0,
            answers: type === "diet" ? defaultDietAnswers() : defaultWorkoutAnswers(),
            error: "",
            fieldErrors: {},
            generating: false,
            ...(type === "diet" ? { preferencesOpen: false, customizationOpen: false, targetsOpen: false, ingredientDraft: "" } : {}),
            ownerKey: type === "workout" ? `student:${studentId}` : undefined
        };
        openPlanWizard(type, { type, studentId });
    }

    function openDietPlanWizardWithPlan(plan) {
        const questionnaire = plan?.questionnaire || {};
        const customTargets = questionnaire.custom_targets || {};
        const answers = defaultDietAnswers();
        Object.assign(answers, {
            goal: questionnaire.goal || answers.goal,
            meals_per_day: String(questionnaire.meals_per_day || answers.meals_per_day),
            diet_pattern: questionnaire.diet_pattern || answers.diet_pattern,
            training_days_per_week: String(questionnaire.training_days_per_week ?? answers.training_days_per_week),
            change_pace: questionnaire.change_pace || answers.change_pace,
            allergies: "",
            intolerances: "",
            disliked_foods: asArray(questionnaire.disliked_foods).join(", "),
            preferred_foods: asArray(questionnaire.preferred_foods).join(", "),
            budget: questionnaire.budget || answers.budget,
            prep_minutes: String(questionnaire.prep_minutes || answers.prep_minutes),
            available_ingredients: asArray(questionnaire.available_ingredients).join("; "),
            target_calories: customTargets.calories ?? "",
            target_protein: customTargets.protein ?? "",
            target_carbs: customTargets.carbs ?? "",
            target_fat: customTargets.fat ?? "",
            notes: questionnaire.notes || ""
        });
        wizardMemory.diet = { step: 2, answers, error: "", fieldErrors: {}, generating: false, preferencesOpen: false, customizationOpen: false, targetsOpen: false, ingredientDraft: "", ownerKey: workoutWizardOwnerKey(null) };
        openPlanWizard("diet");
    }

    function closePlanWizard() {
        if (!activeWizardType || wizardMemory[activeWizardType].generating) return;
        const modal = byId("guidedPlanModal");
        if (!modal) return;
        modal.setAttribute("aria-hidden", "true");
        closeAppModal(modal);
    }

    function validateTextList(value, fieldLabel) {
        const items = parseTextList(value);
        if (items.length > 12) return `${fieldLabel}: informe no máximo 12 itens.`;
        if (items.some((item) => item.length > 80)) return `${fieldLabel}: resuma cada item em até 80 caracteres.`;
        return "";
    }

    function validateWizardStep(type, step) {
        const answers = wizardMemory[type].answers;
        const errors = {};
        if (type === "diet") {
            if (step === 0) {
                if (!DIET_GOALS[answers.goal]) errors.goal = "Selecione seu objetivo principal.";
                if (!["3", "4", "5"].includes(String(answers.meals_per_day))) errors.meals_per_day = "Escolha quantas refeições deseja.";
                if (!DIET_PATTERNS[answers.diet_pattern]) errors.diet_pattern = "Selecione um padrão alimentar.";
            } else if (step === 1) {
                if (!Array.from({ length: 8 }, (_, index) => String(index)).includes(String(answers.training_days_per_week))) errors.training_days_per_week = "Escolha entre 0 e 7 dias.";
                const fields = {
                    disliked_foods: "Alimentos evitados",
                    preferred_foods: "Alimentos preferidos"
                };
                Object.entries(fields).forEach(([field, label]) => {
                    const message = validateTextList(answers[field], label);
                    if (message) errors[field] = message;
                });
            } else {
                if (["fat_loss", "muscle_gain"].includes(answers.goal) && !CHANGE_PACES[answers.change_pace]) errors.change_pace = "Selecione uma velocidade.";
                if (!BUDGETS[answers.budget]) errors.budget = "Selecione uma faixa de orçamento.";
                if (!["15", "30", "45", "60"].includes(String(answers.prep_minutes))) errors.prep_minutes = "Selecione o tempo de preparo.";
                const ingredients = parseIngredientTokens(answers.available_ingredients);
                const ingredientMessage = ingredients.length > 24 || ingredients.some((item) => item.length > 80)
                    ? "Ingredientes: informe no máximo 24 itens de até 80 caracteres."
                    : "";
                if (ingredientMessage) errors.available_ingredients = ingredientMessage;
                if (String(answers.notes || "").length > 500) errors.notes = "Resuma as observações em até 500 caracteres.";
                const targetLimits = { target_calories: [800, 7000], target_protein: [20, 500], target_carbs: [20, 1200], target_fat: [15, 300] };
                Object.entries(targetLimits).forEach(([field, [minimum, maximum]]) => {
                    if (answers[field] === "") return;
                    const value = Number(answers[field]);
                    if (!Number.isFinite(value) || value < minimum || value > maximum) errors[field] = `Informe um valor entre ${minimum} e ${maximum}.`;
                });
            }
        } else if (step === 0) {
            if (!WORKOUT_GOALS[answers.goal]) errors.goal = "Selecione seu objetivo principal.";
            if (!EXPERIENCE_LEVELS[answers.experience_level]) errors.experience_level = "Selecione seu nível de experiência.";
            if (!SPLITS_BY_DAYS[Number(answers.days_per_week)]) errors.days_per_week = "Escolha entre 2 e 6 dias.";
        } else if (step === 1) {
            if (!asArray(SPLITS_BY_DAYS[Number(answers.days_per_week)]).includes(answers.split_type)) errors.split_type = "Escolha uma divisão compatível.";
            if (!["20", "30", "45", "60", "75", "90"].includes(String(answers.session_duration))) errors.session_duration = "Selecione a duração da sessão.";
            if (!asArray(answers.equipment).length) errors.equipment = "Selecione ao menos um equipamento.";
        } else {
            if (String(answers.limitations || "").length > 500) errors.limitations = "Resuma as limitações em até 500 caracteres.";
            if (String(answers.priorities || "").length > 300) errors.priorities = "Resuma as prioridades em até 300 caracteres.";
            if (String(answers.avoid_exercises || "").length > 300) errors.avoid_exercises = "Resuma os exercícios em até 300 caracteres.";
        }
        return errors;
    }

    function validateAllWizardSteps(type) {
        return [0, 1, 2].reduce((allErrors, step) => Object.assign(allErrors, validateWizardStep(type, step)), {});
    }

    function firstErrorStep(type, errors) {
        const steps = Object.keys(errors).map((field) => FIELD_STEPS[type][field]).filter((step) => Number.isInteger(step));
        return steps.length ? Math.min(...steps) : wizardMemory[type].step;
    }

    function buildWizardPayload(type) {
        const answers = wizardMemory[type].answers;
        if (type === "diet") {
            return {
                goal: answers.goal,
                meals_per_day: Number(answers.meals_per_day),
                diet_pattern: answers.diet_pattern,
                training_days_per_week: Number(answers.training_days_per_week),
                change_pace: answers.change_pace,
                allergies: parseTextList(answers.allergies),
                intolerances: parseTextList(answers.intolerances),
                disliked_foods: parseTextList(answers.disliked_foods),
                preferred_foods: parseTextList(answers.preferred_foods),
                budget: answers.budget,
                prep_minutes: Number(answers.prep_minutes),
                available_ingredients: parseIngredientTokens(answers.available_ingredients),
                custom_targets: {
                    calories: answers.target_calories === "" ? null : Number(answers.target_calories),
                    protein: answers.target_protein === "" ? null : Number(answers.target_protein),
                    carbs: answers.target_carbs === "" ? null : Number(answers.target_carbs),
                    fat: answers.target_fat === "" ? null : Number(answers.target_fat)
                },
                notes: String(answers.notes || "").trim()
            };
        }
        return {
            goal: answers.goal,
            experience_level: answers.experience_level,
            days_per_week: Number(answers.days_per_week),
            split_type: answers.split_type,
            session_duration: Number(answers.session_duration),
            equipment: asArray(answers.equipment),
            limitations: String(answers.limitations || "").trim(),
            priorities: String(answers.priorities || "").trim(),
            avoid_exercises: String(answers.avoid_exercises || "").trim()
        };
    }

    function showWizardErrors(type, errors, message) {
        const state = wizardMemory[type];
        state.fieldErrors = errors;
        state.step = firstErrorStep(type, errors);
        state.error = message;
        renderWizard();
        requestAnimationFrame(() => byId("planWizardError")?.focus());
    }

    async function waitForWorkoutRecommendation(state) {
        if (state.recommendationStatus !== "loading" || !state.recommendationPromise) return;
        await state.recommendationPromise;
        if (state.recommendationStatus === "loading") {
            state.recommendationStatus = "fallback";
            state.recommendationMessage = "Não foi possível sugerir uma divisão agora. Você pode ajustar depois.";
            if (state.splitMode !== "manual") state.answers.split_type = workoutFallbackSplit(state);
        }
    }

    async function completeGeneratedPlan(type, result) {
        const planId = result.plan_id || result.plan?.id;
        const professionalContext = professionalWizardContext;
        wizardMemory[type] = {
            step: 0,
            answers: type === "diet" ? defaultDietAnswers() : defaultWorkoutAnswers(),
            error: "",
            fieldErrors: {},
            generating: false
        };
        closePlanWizard();
        professionalWizardContext = null;
        showToast(professionalContext ? "Rascunho criado para revisão." : type === "diet" ? "Plano alimentar criado!" : "Plano de treino criado!", "success");
        if (professionalContext) {
            window.openProfessionalStudent?.(professionalContext.studentId);
            return;
        }
        showTab(type === "diet" ? "diet_plans" : "workout_plans");
        if (!planId) return;
        const opened = type === "diet" ? await viewDietPlan(planId) : await viewWorkoutPlan(planId);
        if (!opened) showToast("Seu plano foi criado. Abra-o em Meus planos para continuar.", "info");
    }

    async function checkWorkoutGeneration() {
        const state = wizardMemory.workout;
        const job = state.pendingGenerationJob;
        if (!job || state.generating) return;
        state.generating = true;
        state.pendingGenerationJob = null;
        state.error = "";
        renderWizard();
        try {
            const result = await window.waitForAIJob(job, undefined, {
                jobLabel: "treino",
                onStatus: (status) => {
                    state.generationStatus = status;
                    if (state.generating) renderWizard();
                }
            });
            await completeGeneratedPlan("workout", result);
        } catch (error) {
            state.generating = false;
            if (error.code === "ai_job_timeout" || error.code === "ai_job_check_failed") {
                state.pendingGenerationJob = error.job || job;
                state.error = error.message;
                renderWizard();
                return;
            }
            showWizardErrors("workout", error.fields || error.data?.fields || {}, error.message);
        }
    }

    async function checkDietGeneration() {
        const state = wizardMemory.diet;
        const job = state.pendingGenerationJob;
        if (!job || state.generating) return;
        state.generating = true;
        state.pendingGenerationJob = null;
        state.error = "";
        renderWizard();
        try {
            const result = await window.waitForAIJob(job, undefined, {
                jobLabel: "plano alimentar",
                onStatus: (status) => {
                    state.generationStatus = status;
                    if (state.generating) renderWizard();
                }
            });
            await completeGeneratedPlan("diet", result);
        } catch (error) {
            state.generating = false;
            if (error.code === "ai_job_timeout" || error.code === "ai_job_check_failed") {
                state.pendingGenerationJob = error.job || job;
                state.error = error.message;
                renderWizard();
                return;
            }
            showWizardErrors("diet", error.fields || error.data?.fields || {}, error.message);
        }
    }

    async function generatePlan(type) {
        const state = wizardMemory[type];
        const errors = validateAllWizardSteps(type);
        if (Object.keys(errors).length) {
            showWizardErrors(type, errors, "Revise os campos destacados antes de gerar o plano.");
            return;
        }
        if (!window.currentUser) {
            closePlanWizard();
            window.requireAuth?.(`Entre para gerar seu plano de ${type === "diet" ? "dieta" : "treino"}.`, {
                premium: true,
                requiresProfile: type === "diet",
                resume: () => openPlanWizard(type)
            });
            return;
        }
        if (!window.requireAuth?.(`Entre para gerar seu plano de ${type === "diet" ? "dieta" : "treino"}.`, { premium: true })) return;

        state.generating = true;
        state.pendingGenerationJob = null;
        state.generationJob = null;
        state.uncertainSubmission = false;
        renderWizard();
        if (type === "workout") {
            try {
                await waitForWorkoutRecommendation(state);
            } catch (error) {
                state.generating = false;
                state.error = error.message;
                renderWizard();
                return;
            }
        }
        window.analytics?.track("plan_generation_requested", {
            plan_type: type,
            surface: professionalWizardContext ? "professional" : "self_service"
        });
        let result;
        try {
            const path = professionalWizardContext
                ? `/professional/students/${apiSegment(professionalWizardContext.studentId)}/${type === "diet" ? "diet-plans" : "workout-plans"}/generate`
                : `/${type === "diet" ? "diet_plans" : "workout_plans"}/generate`;
            result = await apiRequest(path, {
                method: "POST",
                body: buildWizardPayload(type),
                offlineMessage: `Sem conexão. Não foi possível confirmar se o plano de ${type === "diet" ? "alimentação" : "treino"} foi criado.`,
                jobLabel: type === "diet" ? "plano alimentar" : "treino",
                onQueued: (job) => {
                    state.generationJob = job;
                    state.generationStatus = "queued";
                    if (state.generating) renderWizard();
                },
                onJobStatus: (status) => {
                    state.generationStatus = status;
                    if (state.generating) renderWizard();
                }
            });
        } catch (error) {
            state.generating = false;
            const serverFields = error.fields && typeof error.fields === "object"
                ? error.fields
                : (error.data?.fields && typeof error.data.fields === "object" ? error.data.fields : {});
            const profileFields = Object.fromEntries(Object.entries(serverFields).filter(([field]) => field.startsWith("profile.")));
            if (type === "diet" && Object.keys(profileFields).length) {
                if (professionalWizardContext) {
                    const details = Object.values(profileFields).filter(Boolean).join(" ");
                    showWizardErrors(type, {}, `O aluno precisa completar o perfil antes da geração. ${details}`.trim());
                    return;
                }
                const context = professionalWizardContext;
                closePlanWizard();
                window.requestProfileCompletion?.(() => {
                    openPlanWizard(type, context);
                    generatePlan(type);
                }, profileFields);
                return;
            }
            if (error.code === "ai_job_timeout" || error.code === "ai_job_check_failed") {
                state.pendingGenerationJob = error.job || state.generationJob;
                state.error = error.message;
                renderWizard();
                return;
            }
            if (error.code === "offline" && !state.generationJob) state.uncertainSubmission = true;
            showWizardErrors(type, serverFields, error.message);
            return;
        }
        await completeGeneratedPlan(type, result);
    }

    function handleWizardInput(event) {
        if (!activeWizardType) return;
        const control = event.target;
        if (!control.name) return;
        const state = wizardMemory[activeWizardType];
        if (state.error) state.error = "";
        if (control.id === "wizard-ingredient-input") {
            state.ingredientDraft = control.value;
            if (control.value.trim().length <= 80) delete state.fieldErrors.available_ingredients;
            const options = byId("wizard-ingredient-options");
            if (options) options.innerHTML = ingredientOptions(ingredientLastToken(control.value));
            return;
        }
        if (activeWizardType === "workout" && control.name === "equipment_mode") {
            const current = asArray(state.answers.equipment);
            if (state.equipmentMode === "custom") state.customEquipment = current;
            else if (!asArray(state.customEquipment).length && !current.includes("full_gym")) state.customEquipment = current;
            state.equipmentMode = control.value;
            if (control.value === "full_gym") state.answers.equipment = ["full_gym"];
            else if (control.value === "bodyweight") state.answers.equipment = ["bodyweight"];
            else state.answers.equipment = asArray(state.customEquipment).length ? asArray(state.customEquipment) : ["bodyweight"];
            delete state.fieldErrors.equipment;
            if (state.step === 1) scheduleWorkoutRecommendation(0);
            renderWizard({ preserveFocus: true });
            return;
        }
        if (activeWizardType === "workout" && control.name === "split_mode") {
            state.splitMode = control.value;
            state.advancedOpen = true;
            if (control.value === "automatic") {
                state.answers.split_type = state.recommendation?.recommended_split || workoutFallbackSplit(state);
                delete state.fieldErrors.split_type;
            }
            renderWizard({ preserveFocus: true });
            return;
        }
        if (control.type === "checkbox") {
            const current = new Set(asArray(state.answers[control.name]));
            if (control.checked) current.add(control.value);
            else current.delete(control.value);
            state.answers[control.name] = Array.from(current);
            if (activeWizardType === "workout" && control.name === "equipment") state.customEquipment = state.answers.equipment.slice();
        } else {
            state.answers[control.name] = control.value;
        }
        delete state.fieldErrors[control.name];

        if (activeWizardType === "workout" && ["days_per_week", "experience_level"].includes(control.name)) {
            state.splitMode = "automatic";
        }
        if (activeWizardType === "workout" && control.name === "days_per_week") {
            const compatible = SPLITS_BY_DAYS[Number(state.answers.days_per_week)] || [];
            if (!compatible.includes(state.answers.split_type)) state.answers.split_type = compatible[0] || "full_body";
        }
        if (activeWizardType === "workout" && ["days_per_week", "experience_level", "split_type", "session_duration", "equipment"].includes(control.name)) {
            if (control.name === "split_type") {
                state.splitMode = "manual";
                state.advancedOpen = true;
            }
            if (state.step === 1) scheduleWorkoutRecommendation();
        }
        if (control.name === "notes") {
            const count = byId("planWizardStep")?.querySelector(".wizard-character-count");
            if (count) count.textContent = `${control.value.length}/500`;
        }
    }

    function handleWizardKeydown(event) {
        const control = event.target;
        if (!activeWizardType || control.id !== "wizard-ingredient-input") return;
        if (event.key === "Enter" || event.key === ";") {
            event.preventDefault();
            if (addIngredient(control.value)) control.value = "";
        }
    }

    function handleIngredientClick(event) {
        const addButton = event.target.closest("[data-add-ingredient]");
        if (addButton) {
            const input = byId("wizard-ingredient-input");
            if (input) {
                const added = addIngredient(input.value);
                if (added) input.value = "";
                else if (wizardMemory.diet.fieldErrors.available_ingredients) renderWizard({ preserveFocus: true });
                byId("wizard-ingredient-input")?.focus();
            }
            return;
        }
        const removeButton = event.target.closest("[data-remove-ingredient]");
        if (removeButton) removeIngredient(removeButton.dataset.removeIngredient);
    }

    async function handleWizardSubmit(event) {
        event.preventDefault();
        if (!activeWizardType) return;
        const state = wizardMemory[activeWizardType];
        if (state.generating) return;
        if (activeWizardType === "diet" && state.step === 2 && state.ingredientDraft?.trim()) {
            if (!commitIngredientDraft(state)) {
                state.error = "Revise os ingredientes destacados para continuar.";
                renderWizard({ preserveFocus: true });
                requestAnimationFrame(() => byId("wizard-ingredient-input")?.focus({ preventScroll: true }));
                return;
            }
        }
        const errors = validateWizardStep(activeWizardType, state.step);
        if (Object.keys(errors).length) {
            state.fieldErrors = { ...state.fieldErrors, ...errors };
            state.error = "Revise os campos destacados para continuar.";
            renderWizard();
            requestAnimationFrame(() => byId("planWizardError")?.focus());
            return;
        }
        state.fieldErrors = {};
        state.error = "";
        if (state.step < 2) {
            state.step += 1;
            renderWizard({ focusHeading: true });
            if (activeWizardType === "workout" && state.step === 1) scheduleWorkoutRecommendation(0);
            return;
        }
        await generatePlan(activeWizardType);
    }

    function handlePlanChatAction(action) {
        if (!action || typeof action !== "object") return;
        if (action.type === "open_diet_plan_questionnaire") openPlanWizard("diet");
        if (action.type === "open_workout_questionnaire") openPlanWizard("workout");
    }

    function planLoadingMarkup(message) {
        return `<div class="plans-loading" role="status"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>${esc(message)}</span></div>`;
    }

    function renderPlanList(type, plans) {
        const container = byId(type === "diet" ? "dietPlansTableBody" : "workoutPlansTableBody");
        if (!container) return;
        document.querySelector(`.fab--${type}-plans`)?.classList.toggle("hidden", !plans.length);
        if (!plans.length) {
            const isDiet = type === "diet";
            container.innerHTML = `
                <div class="plans-empty">
                    <i class="fas ${isDiet ? "fa-seedling" : "fa-dumbbell"}" aria-hidden="true"></i>
                    <h3>${isDiet ? "Seu próximo plano começa aqui" : "Pronto para começar?"}</h3>
                    <p>${isDiet ? "Crie três dias de refeições alinhados à sua rotina e preferências." : "Monte uma semana de treinos adequada ao seu objetivo e aos equipamentos disponíveis."}</p>
                    <button type="button" class="btn-primary" data-plan-wizard="${type}"><i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i> ${isDiet ? "Criar plano alimentar" : "Criar plano de treino"}</button>
                </div>`;
            return;
        }

        const isDiet = type === "diet";
        container.innerHTML = plans.map((plan) => {
            const count = isDiet ? plan.meals_count : plan.exercises_count;
            const countLabel = isDiet ? "refeições" : "exercícios";
            const fallback = isDiet ? "Plano alimentar personalizado para sua rotina." : "Treino personalizado para sua evolução.";
            const currentBadge = plan.is_current ? '<span class="plan-current-pill"><i class="fas fa-star" aria-hidden="true"></i> Plano atual</span>' : "";
            const adjustLabel = isDiet ? (plan.is_current ? "Ajustar" : "Usar plano") : "Ajustar agenda";
            const adjustAction = isDiet && !plan.is_current ? "set-current" : "adjust";
            return `
                <article class="plan-card plan-card--${type} plan-card--clickable" role="button" tabindex="0" aria-label="Abrir ${isDiet ? "plano alimentar" : "plano de treino"} ${esc(plan.title || "")}" data-plan-action="view" data-plan-type="${type}" data-plan-id="${esc(plan.id)}">
                    <div class="plan-card__icon"><i class="fas ${isDiet ? "fa-apple-alt" : "fa-dumbbell"}" aria-hidden="true"></i></div>
                    <div class="plan-card__body">
                        <div class="plan-card__topline"><span class="plan-type">${isDiet ? "Plano alimentar" : "Plano de treino"}</span>${currentBadge}<span class="plan-count"><i class="fas ${isDiet ? "fa-utensils" : "fa-dumbbell"}" aria-hidden="true"></i> ${esc(count || 0)} ${countLabel}</span></div>
                        <h3>${esc(plan.title || (isDiet ? "Plano alimentar" : "Plano de treino"))}</h3>
                        <p>${esc(plan.description || fallback)}</p>
                        <span class="plan-date"><i class="far fa-calendar" aria-hidden="true"></i> Criado em ${esc(formatDateTime(plan.created_at))}</span>
                    </div>
                    <div class="plan-card__actions">
                        <button type="button" data-plan-action="${adjustAction}" data-plan-type="${type}" data-plan-id="${esc(plan.id)}" class="btn-adjust"><i class="fas ${isDiet && !plan.is_current ? "fa-check" : "fa-sliders"}" aria-hidden="true"></i> ${adjustLabel}</button>
                        <button type="button" data-plan-action="delete" data-plan-type="${type}" data-plan-id="${esc(plan.id)}" class="btn-delete plan-delete" aria-label="Excluir ${isDiet ? "plano alimentar" : "plano de treino"}"><i class="fas fa-trash" aria-hidden="true"></i></button>
                    </div>
                </article>`;
        }).join("");
    }

    function renderFilteredWorkoutPlans() {
        const goal = byId("workoutGoalFilter")?.value || "";
        const experience = byId("workoutExperienceFilter")?.value || "";
        const days = byId("workoutDaysFilter")?.value || "";
        const filtered = workoutPlans.filter((plan) => (
            (!goal || plan.goal === goal)
            && (!experience || plan.experience_level === experience)
            && (!days || String(plan.days_per_week) === days)
        ));
        renderPlanList("workout", filtered);
    }

    function suggestedWorkoutWeekdays(daysPerWeek) {
        const count = Math.max(1, Math.min(7, Number(daysPerWeek) || 3));
        const presets = {
            1: [0],
            2: [0, 3],
            3: [0, 2, 4],
            4: [0, 1, 3, 5],
            5: [0, 1, 2, 3, 4],
            6: [0, 1, 2, 3, 4, 5],
            7: [0, 1, 2, 3, 4, 5, 6],
        };
        return presets[count] || presets[3];
    }

    function workoutCurrentPlanDays() {
        const plan = workoutCurrentPlan;
        if (!plan) return [];
        const dayCount = Array.isArray(plan.days) ? plan.days.length : Number(plan.days_count || plan.days_per_week || 3);
        return suggestedWorkoutWeekdays(dayCount);
    }

    function renderWorkoutCurrentModal() {
        const modalBody = byId("workoutCurrentModalBody");
        const title = byId("workoutCurrentModalTitle");
        const subtitle = byId("workoutCurrentModalSubtitle");
        if (!modalBody || !workoutCurrentPlan) return;
        const selected = new Set(window.workoutCurrentWeekdays || []);
        const dayCount = Array.isArray(workoutCurrentPlan.days) ? workoutCurrentPlan.days.length : Number(workoutCurrentPlan.days_count || workoutCurrentPlan.days_per_week || 3);
        const selectedCount = selected.size;
        const isValidSelection = selectedCount > 0;
        if (title) title.textContent = workoutTodayState?.current_plan_id === workoutCurrentPlan.id ? "Ajustar agenda" : "Definir plano principal";
        if (subtitle) {
            subtitle.textContent = workoutTodayState?.current_plan_id === workoutCurrentPlan.id
                ? "A nova seleção vale imediatamente e atualiza o treino de hoje."
                : "Escolha os dias da semana deste treino para começar hoje.";
        }
        modalBody.innerHTML = `
            <section class="workout-current-modal__plan">
                <span class="content-kicker">Plano de treino</span>
                <h4>${esc(workoutCurrentPlan.title || "Plano de treino")}</h4>
                <p>${esc(workoutCurrentPlan.description || "Treino principal do dia a dia.")}</p>
                <small>${esc(dayCount)} dias por semana</small>
            </section>
            <p class="workout-current-modal__status${isValidSelection ? " is-valid" : " is-invalid"}" aria-live="polite">
                ${esc(selectedCount)} dias selecionados${selectedCount !== dayCount ? ` de ${esc(dayCount)} previstos` : ""}
            </p>
            <section class="workout-current-modal__days" aria-label="Selecionar dias da semana">
                ${WEEKDAY_FULL_LABELS.map((label, weekday) => `
                    <button type="button" class="workout-current-day${selected.has(weekday) ? " is-selected" : ""}" data-workout-weekday="${weekday}" aria-pressed="${selected.has(weekday)}">
                        <strong>${label}</strong>
                        <small>${WEEKDAY_LABELS[weekday]}</small>
                    </button>
                `).join("")}
            </section>
            <p class="workout-current-modal__hint">Se você mudar a quantidade de dias, o app vai pedir para adaptar o treino atual.</p>
        `;
        const saveButton = byId("workoutCurrentModal").querySelector("[data-workout-current-save]");
        if (saveButton) {
            saveButton.disabled = !isValidSelection;
            saveButton.setAttribute("aria-disabled", String(!isValidSelection));
        }
    }

    function renderWorkoutCurrentDecisionModal() {
        const body = byId("workoutCurrentDecisionBody");
        const subtitle = byId("workoutCurrentDecisionSubtitle");
        if (!body || !workoutCurrentDecision || !workoutCurrentPlan) return;
        const { weekdays, dayCount } = workoutCurrentDecision;
        const selectedCount = weekdays.length;
        if (subtitle) {
            subtitle.textContent = `Seu treino atual tem ${dayCount} dias, mas você selecionou ${selectedCount}.`;
        }
        body.innerHTML = `
            <section class="workout-current-modal__plan">
                <span class="content-kicker">Confirmação</span>
                <h4>${esc(workoutCurrentPlan.title || "Plano de treino")}</h4>
                <p>Essa agenda muda a estrutura semanal do treino.</p>
                <small>${esc(selectedCount)} dias escolhidos, ${esc(dayCount)} dias no plano original</small>
            </section>
            <p class="workout-current-modal__status is-invalid" aria-live="polite">Escolha uma ação para continuar</p>
        `;
    }

    function openWorkoutCurrentDecisionModal() {
        renderWorkoutCurrentDecisionModal();
        openAppModal(byId("workoutCurrentDecisionModal"));
    }

    async function applyWorkoutCurrentPlanChange(mode) {
        if (!workoutCurrentPlan || !workoutCurrentDecision) return;
        const weekdays = Array.from(new Set(workoutCurrentDecision.weekdays || [])).sort((a, b) => a - b);
        const endpoints = {
            adapt: { path: `/workout_plans/${apiSegment(workoutCurrentPlan.id)}/current/adapt`, method: "POST" },
            current: { path: `/workout_plans/${apiSegment(workoutCurrentPlan.id)}/current`, method: "PUT" },
        };
        const endpoint = endpoints[mode] || endpoints.current;
        try {
            const result = await apiRequest(endpoint.path, {
                method: endpoint.method,
                body: { weekdays },
            });
            if (workoutView.plan && String(workoutView.plan.id) === String(result.plan_id || workoutCurrentPlan.id)) {
                workoutView.plan.is_current = true;
                renderWorkoutDetail({ preserveScroll: true });
            }
            showToast(result.message || "Agenda atualizada.", "success");
            closeAppModal(byId("workoutCurrentDecisionModal"));
            closeAppModal(byId("workoutCurrentModal"));
            workoutCurrentDecision = null;
            await Promise.all([
                loadWorkoutPlans(),
                loadWorkoutTodayCard(true),
            ]);
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    function openWorkoutCurrentModal(planId) {
        const plan = workoutPlans.find((item) => String(item.id) === String(planId));
        if (!plan) return;
        workoutCurrentPlan = plan;
        workoutCurrentDecision = null;
        window.workoutCurrentWeekdays = workoutTodayState?.current_plan_id === plan.id
            ? (workoutTodayState.week || []).filter((item) => item.day_id).sort((left, right) => left.weekday - right.weekday).map((item) => item.weekday)
            : suggestedWorkoutWeekdays(plan.days_count || plan.days_per_week || 3);
        renderWorkoutCurrentModal();
        openAppModal(byId("workoutCurrentModal"));
    }

    async function saveWorkoutCurrentPlan() {
        if (!workoutCurrentPlan) return;
        const weekdays = Array.from(new Set(window.workoutCurrentWeekdays || [])).sort((a, b) => a - b);
        const dayCount = Array.isArray(workoutCurrentPlan.days) ? workoutCurrentPlan.days.length : Number(workoutCurrentPlan.days_count || workoutCurrentPlan.days_per_week || 3);
        if (!weekdays.length) {
            showToast("Selecione ao menos um dia.", "error");
            renderWorkoutCurrentModal();
            return;
        }
        workoutCurrentDecision = { weekdays, dayCount };
        if (weekdays.length !== dayCount) {
            openWorkoutCurrentDecisionModal();
            return;
        }
        await applyWorkoutCurrentPlanChange("current");
    }

    async function loadDietPlans() {
        if (!window.currentUser) {
            const container = byId("dietPlansTableBody");
            if (container) container.innerHTML = '<div class="guest-presentation guest-presentation--standalone"><i class="fas fa-utensils"></i><div><strong>Cardápios alinhados ao seu objetivo</strong><p>Explore o questionário e gere planos personalizados com IA Premium.</p></div></div>';
            return [];
        }
        const container = byId("dietPlansTableBody");
        const owner = workoutAccount();
        if (container) {
            container.setAttribute("aria-busy", "true");
            if (!container.children.length) container.innerHTML = planLoadingMarkup("Carregando planos alimentares...");
        }
        try {
            const result = await apiRequest("/diet_plans");
            if (owner !== workoutAccount()) return [];
            dietPlans = Array.isArray(result) ? result : [];
            renderPlanList("diet", dietPlans);
            return dietPlans;
        } catch (error) {
            if (owner !== workoutAccount()) return [];
            if (dietPlans.length) renderPlanList("diet", dietPlans);
            if (container) {
                const feedback = `<div class="plans-empty" role="alert"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i><h3>Não foi possível atualizar os planos</h3><p>${esc(error.message)}</p><button type="button" class="btn-secondary" data-retry-plan-list="diet">Tentar novamente</button></div>`;
                if (dietPlans.length) container.insertAdjacentHTML('beforeend', feedback);
                else container.innerHTML = feedback;
            }
            return [];
        } finally {
            container?.setAttribute("aria-busy", "false");
        }
    }

    async function loadWorkoutPlans() {
        if (!window.currentUser) {
            const container = byId("workoutPlansTableBody");
            if (container) container.innerHTML = '<div class="guest-presentation guest-presentation--standalone"><i class="fas fa-dumbbell"></i><div><strong>Organize e execute seus treinos</strong><p>Explore o gerador e salve planos para acompanhar cada sessão.</p></div></div>';
            workoutTodayState = null;
            renderWorkoutTodayCard();
            return [];
        }
        const container = byId("workoutPlansTableBody");
        const owner = workoutAccount();
        if (container) {
            container.setAttribute("aria-busy", "true");
            if (!container.children.length) container.innerHTML = planLoadingMarkup("Carregando planos de treino...");
        }
        try {
            try {
                await loadWorkoutTodayCard();
                workoutTodayError = "";
            } catch (error) {
                workoutTodayError = error.message;
            }
            const plansResult = await apiRequest("/workout_plans");
            if (owner !== workoutAccount()) return [];
            workoutPlans = Array.isArray(plansResult) ? plansResult : [];
            renderFilteredWorkoutPlans();
            window.renderWorkoutTodayCard?.();
            return workoutPlans;
        } catch (error) {
            if (owner !== workoutAccount()) return [];
            if (workoutPlans.length) renderFilteredWorkoutPlans();
            if (container) {
                const feedback = `<div class="plans-empty" role="alert"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i><h3>Não foi possível atualizar os planos</h3><p>${esc(error.message)}</p><button type="button" class="btn-secondary" data-retry-plan-list="workout">Tentar novamente</button></div>`;
                if (workoutPlans.length) container.insertAdjacentHTML('beforeend', feedback);
                else container.innerHTML = feedback;
            }
            return [];
        } finally {
            container?.setAttribute("aria-busy", "false");
        }
    }

    function renderWorkoutTodayCard() {
        renderWorkoutPlanHub();
        const container = byId("workoutTodayCard");
        if (!container) return;
        byId('dietTab')?.classList.toggle('today-workout-priority', Boolean(window.currentUser) && ['active', 'scheduled'].includes(workoutTodayState?.state));
        if (!window.currentUser) {
            container.innerHTML = '<p class="today-muted">Entre para acompanhar seu treino.</p>';
            return;
        }
        if (!workoutTodayState) {
            if (workoutTodayError) {
                container.innerHTML = `<article class="workout-today-card__shell"><div><span class="content-kicker">Treino do dia</span><h3>Não foi possível atualizar</h3><p>${esc(workoutTodayError)}</p></div><button type="button" class="btn-secondary" data-workout-today-action="retry">Tentar novamente</button></article>`;
                return;
            }
            container.innerHTML = `
                <article class="workout-today-card__shell">
                    <div class="plans-loading"><i data-lucide="loader-circle" class="today-icon--spin" aria-hidden="true"></i><span>Carregando seu treino de hoje...</span></div>
                </article>`;
            return;
        }
        const state = workoutTodayState.state || "unconfigured";
        const day = workoutTodayState.current_day;
        const name = day?.title || workoutTodayState.current_plan?.title || 'Treino de hoje';
        const operational = ['active', 'scheduled'].includes(state);
        if (operational) {
            const firstExercise = asArray(day?.exercises)[0];
            const action = state === 'active' ? 'open-plan' : 'start-today';
            const actionLabel = state === 'active' ? 'Continuar treino' : 'Iniciar treino';
            const preview = firstExercise ? `<figure class="today-workout-preview" role="button" tabindex="0" data-workout-today-action="${action}" aria-label="${actionLabel}: ${esc(name)}">${exerciseImageMarkup(firstExercise, true)}<figcaption>${esc(firstExercise.name)}</figcaption></figure>` : "";
            container.innerHTML = `<div class="today-workout">${preview}<div class="today-workout__head"><span class="today-workout__icon"><i data-lucide="dumbbell" aria-hidden="true"></i></span><div><span class="today-muted">${state === 'active' ? 'Treino em andamento' : 'Treino de hoje'}</span><h2>${esc(name)}</h2></div></div><button type="button" class="btn-primary" data-workout-today-action="${state === 'active' ? 'open-plan' : 'start-today'}">${state === 'active' ? 'Continuar treino' : 'Iniciar treino'} <i data-lucide="arrow-right" aria-hidden="true"></i></button></div>`;
        } else {
            const label = { completed: 'Treino concluído', partial: 'Treino finalizado parcialmente', rest: 'Hoje é descanso', unconfigured: 'Seu treino ainda não está configurado. Acesse Treino.' }[state] || 'Treino indisponível';
            container.innerHTML = `<div class="today-workout-status"><span>${esc(label)}</span>${['completed', 'partial'].includes(state) ? '<button type="button" class="text-button" data-workout-today-action="open-activity">Ver resumo</button>' : ''}</div>`;
        }
    }

    function toggleWorkoutPlansLibrary(forceOpen) {
        const library = byId("workoutPlansLibrary");
        if (!library) return;
        const shouldOpen = typeof forceOpen === "boolean" ? forceOpen : library.classList.contains("hidden");
        library.classList.toggle("hidden", !shouldOpen);
        if (shouldOpen) {
            requestAnimationFrame(() => {
                library.scrollIntoView({ behavior: "smooth", block: "start" });
                byId("workoutPlansLibraryTitle")?.focus?.({ preventScroll: true });
            });
        }
    }

    function workoutHubExerciseMarkup(exercise, index) {
        const prescription = [
            exercise.sets ? `${exercise.sets} séries` : "",
            exercise.reps ? `${exercise.reps} reps` : "",
            exercise.rest_seconds ? `${exercise.rest_seconds}s descanso` : "",
        ].filter(Boolean).join(" · ");
        return `<li class="workout-hub-exercise"><span>${esc(exercise.order || index + 1)}</span><div><strong>${esc(exercise.name || "Exercício")}</strong><small>${esc(prescription || exercise.primary_muscle || "Ver prescrição")}</small></div></li>`;
    }

    function renderWorkoutPlanHub() {
        const container = byId("workoutPlanHub");
        if (!container) return;
        if (!window.currentUser) {
            container.innerHTML = '<article class="workout-today-card__shell workout-today-card__shell--guest"><div><span class="content-kicker">Treino de hoje</span><h3>Organize sua rotina de treino</h3><p>Entre para ver sua sessão, registrar séries e acompanhar a evolução.</p></div></article>';
            return;
        }
        if (!workoutTodayState) {
            container.innerHTML = workoutTodayError
                ? `<article class="workout-today-card__shell"><div><span class="content-kicker">Treino de hoje</span><h3>Não foi possível atualizar</h3><p>${esc(workoutTodayError)}</p></div><button type="button" class="btn-secondary" data-workout-today-action="retry">Tentar novamente</button></article>`
                : '<article class="workout-today-card__shell"><div class="plans-loading"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>Carregando seu treino...</span></div></article>';
            return;
        }
        const state = workoutTodayState.state || "unconfigured";
        const plan = workoutTodayState.current_plan;
        const day = workoutTodayState.current_day || workoutTodayState.next_day;
        const exercises = asArray(day?.exercises);
        const isNextWorkout = state === "rest";
        const stateCopy = {
            active: ["Treino em andamento", "Continue de onde parou"],
            scheduled: ["Treino de hoje", "Sua sessão está pronta"],
            completed: ["Treino concluído", "Sessão salva no histórico"],
            partial: ["Treino finalizado", "Sessão parcial salva"],
            rest: ["Hoje é descanso", "Próximo treino"],
            unconfigured: ["Comece por aqui", "Nenhum plano principal"],
        }[state] || ["Treino", "Sua sessão"];
        const actionLabel = {
            active: "Continuar treino",
            scheduled: "Iniciar treino",
            completed: "Ver resumo",
            partial: "Ver resumo",
            rest: "Ver próximo treino",
            unconfigured: "Criar plano de treino",
        }[state] || "Abrir treino";
        const action = state === "unconfigured"
            ? "create-workout"
            : (["completed", "partial"].includes(state) ? "open-activity" : "open-plan");
        const week = asArray(workoutTodayState.week);
        const dayTitle = day?.title || (state === "unconfigured" ? "Seu primeiro treino começa com um plano" : plan?.title || "Treino indisponível");
        container.innerHTML = `
            <article class="workout-hub-hero workout-hub-hero--${esc(state)}">
                <header class="workout-hub-hero__header">
                    <div><span class="workout-hub-state"><i class="fas ${state === "completed" ? "fa-circle-check" : state === "active" ? "fa-circle-play" : "fa-dumbbell"}" aria-hidden="true"></i> ${esc(stateCopy[0])}</span><small>${esc(stateCopy[1])}</small><h3>${esc(dayTitle)}</h3>${day?.focus ? `<p>${esc(day.focus)}</p>` : ""}</div>
                    ${plan?.session_duration ? `<span class="workout-hub-duration"><i class="fas fa-clock" aria-hidden="true"></i>${esc(plan.session_duration)} min</span>` : ""}
                </header>
                <button type="button" class="btn-primary workout-hub-primary" data-workout-today-action="${action}">${esc(actionLabel)} <i class="fas fa-arrow-right" aria-hidden="true"></i></button>
                ${exercises.length ? `<details class="workout-hub-details"><summary><span class="workout-hub-details__show"><i class="fas fa-list-check" aria-hidden="true"></i> Mostrar detalhes</span><span class="workout-hub-details__hide"><i class="fas fa-chevron-up" aria-hidden="true"></i> Ocultar detalhes</span><small>${esc(exercises.length)} exercícios</small></summary><section class="workout-hub-sequence" aria-labelledby="workoutHubSequenceTitle"><div class="workout-hub-section-title"><div><span>Sequência</span><h4 id="workoutHubSequenceTitle">${isNextWorkout ? "Exercícios do próximo treino" : "Exercícios da sessão"}</h4></div></div><ol>${exercises.map(workoutHubExerciseMarkup).join("")}</ol></section></details>` : state === "unconfigured" ? '<p class="workout-hub-empty-copy">Crie um plano adequado ao seu objetivo ou escolha um plano que você já salvou.</p>' : ""}
            </article>
            ${week.length ? `<section class="workout-hub-section workout-hub-week" aria-labelledby="workoutHubWeekTitle"><div class="workout-hub-section-title"><div><span>Visão semanal</span><h3 id="workoutHubWeekTitle">Sua semana</h3></div></div><div class="workout-today-card__week">${week.map(item => `<span class="workout-today-card__day${item.active ? " is-active" : ""}${item.day_id ? " is-planned" : ""}"><strong>${esc(item.label)}</strong><small>${item.day_title ? esc(item.day_title) : "Descanso"}</small></span>`).join("")}</div></section>` : ""}
            ${plan ? `<section class="workout-hub-section workout-hub-plan" aria-labelledby="workoutHubPlanTitle"><div class="workout-hub-plan__copy"><span class="content-kicker">Plano atual</span><h3 id="workoutHubPlanTitle">${esc(plan.title || "Plano de treino")}</h3><p>${esc(plan.description || "Seu plano principal para esta rotina.")}</p><div class="workout-hub-plan__meta">${plan.days_count || plan.days_per_week ? `<span><i class="fas fa-calendar-week" aria-hidden="true"></i>${esc(plan.days_count || plan.days_per_week)} dias</span>` : ""}${plan.exercises_count ? `<span><i class="fas fa-list-check" aria-hidden="true"></i>${esc(plan.exercises_count)} exercícios</span>` : ""}</div></div><div class="workout-hub-plan__actions"><button type="button" class="btn-secondary" data-workout-today-action="open-plan">Ver plano</button><button type="button" class="text-button" onclick="window.openWorkoutCurrentModal?.(${Number(plan.id)})">Ajustar agenda</button></div></section>` : ""}
            <section class="workout-hub-library-link" aria-label="Planejamento de treino"><div><span class="content-kicker">Planejamento</span><h3>Meus planos</h3><p>Consulte sua biblioteca, troque o plano principal ou crie outro.</p></div><button type="button" class="btn-secondary" onclick="toggleWorkoutPlansLibrary(true)">Abrir biblioteca</button></section>`;
    }

    async function loadWorkoutTodayCard(forceFetch = false, options = {}) {
        const reported = (data, refreshed = false) => options.reportResult
            ? { ok: !workoutTodayError, data, error: workoutTodayError || null, refreshed,
                offline: navigator.onLine === false || document.body.dataset.offline === "true" }
            : data;
        const container = byId("workoutTodayCard");
        if (!container) return options.reportResult ? { ok: false, skipped: true, reason: "missing-surface" } : null;
        if (!window.currentUser) {
            workoutTodayState = null;
            renderWorkoutTodayCard();
            return options.reportResult ? { ok: false, skipped: true, reason: "guest" } : null;
        }
        const owner = `${workoutAccount()}:${new Date().toLocaleDateString("en-CA")}:${Intl.DateTimeFormat().resolvedOptions().timeZone}`;
        if (workoutTodayOwner !== owner) {
            workoutTodayState = null;
            workoutTodayAt = 0;
            workoutTodayPromise = null;
            workoutTodayOwner = owner;
        }
        if (workoutTodayState && !forceFetch && Date.now() - workoutTodayAt < 30000) {
            renderWorkoutTodayCard();
            return reported(workoutTodayState, false);
        }
        if (workoutTodayPromise) return reported(await workoutTodayPromise, true);
        if (!workoutTodayState) renderWorkoutTodayCard();
        const revision = workoutView.mutationRevision;
        const promise = (async () => {
            try {
                const loader = ({ signal } = {}) => apiRequest("/workouts/today", { signal });
                const result = window.AppReadCache
                    ? await window.AppReadCache.read(`workout:today:${owner}`, loader, { ttl: 30000, force: forceFetch })
                    : await loader();
                if (owner !== workoutTodayOwner || revision !== workoutView.mutationRevision) return workoutTodayState;
                workoutTodayState = result;
                workoutTodayAt = Date.now();
                workoutTodayError = "";
                activeWorkoutSummary = result.state === "active" && result.session
                    ? { session: result.session, plan: result.current_plan, day: result.current_day }
                    : null;
                renderActiveWorkoutDock();
            } catch (error) {
                if (owner === workoutTodayOwner && error.name !== "AbortError") workoutTodayError = error.message;
            }
            if (owner === workoutTodayOwner) renderWorkoutTodayCard();
            return workoutTodayState;
        })();
        workoutTodayPromise = promise;
        try { return reported(await promise, true); }
        finally { if (workoutTodayPromise === promise) workoutTodayPromise = null; }
    }

    async function openWorkoutTodayPlan() {
        const state = workoutTodayState || await loadWorkoutTodayCard(true);
        if (!state?.current_plan_id) {
            window.showTab?.("workout_plans");
            return;
        }
        const dayId = state.current_day?.id || state.next_day?.id || null;
        await viewWorkoutPlan(state.current_plan_id, dayId);
    }

    async function deletePlan(type, id) {
        const label = type === "diet" ? "plano alimentar" : "plano de treino";
        if (!window.confirm(`Tem certeza que deseja excluir este ${label}?`)) return;
        try {
            await apiRequest(`/${type === "diet" ? "diet_plans" : "workout_plans"}/${apiSegment(id)}`, { method: "DELETE" });
            showToast(`${type === "diet" ? "Plano alimentar" : "Plano de treino"} excluído!`, "success");
            if (type === "diet") await loadDietPlans();
            else await loadWorkoutPlans();
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    function groupDietMeals(plan) {
        const groups = new Map();
        asArray(plan.meals).forEach((meal) => {
            const day = String(meal?.day_of_week || "Geral");
            if (!groups.has(day)) groups.set(day, []);
            groups.get(day).push(meal || {});
        });
        return Array.from(groups, ([name, meals]) => ({
            name,
            meals: meals.slice().sort((a, b) => Number(a.order || 0) - Number(b.order || 0))
        }));
    }

    function renderMealMacros(meal) {
        const values = [
            [meal.calories, "kcal"],
            [meal.protein, "g proteína"],
            [meal.carbs, "g carbo"],
            [meal.fat, "g gordura"]
        ];
        return `<div class="meal-macros" aria-label="Macronutrientes estimados">${values.map(([value, label]) => `<span><b>${esc(value ?? "—")}</b><small>${esc(label)}</small></span>`).join("")}</div>`;
    }

    function dietNutritionTotals(meals) {
        return asArray(meals).reduce((totals, meal) => {
            ["calories", "protein", "carbs", "fat"].forEach((nutrient) => {
                const value = Number(meal?.[nutrient]);
                if (Number.isFinite(value)) totals[nutrient] += value;
            });
            return totals;
        }, { calories: 0, protein: 0, carbs: 0, fat: 0 });
    }

    function renderDietNutritionSummary(totals, targets, label) {
        const nutrients = [
            ["calories", "targetCalories", "Calorias", "kcal", "fa-fire"],
            ["protein", "targetProtein", "Proteínas", "g", "fa-drumstick-bite"],
            ["carbs", "targetCarbs", "Carboidratos", "g", "fa-wheat-awn"],
            ["fat", "targetFat", "Gorduras", "g", "fa-droplet"]
        ];
        return `<section class="diet-nutrition-summary" aria-label="${esc(label)}">
            <header><div><span>Resumo nutricional</span><h4>${esc(label)}</h4></div><small>Estimativas do cardápio</small></header>
            <div class="diet-nutrition-grid">${nutrients.map(([key, targetKey, name, unit, icon]) => {
                const value = Math.round(Number(totals[key]) || 0);
                const target = Math.round(Number(targets?.[targetKey]) || 0);
                const percentage = target ? Math.round((value / target) * 100) : 0;
                const progress = Math.min(Math.max(percentage, 0), 100);
                const status = target && Math.abs(percentage - 100) <= 10 ? " na-meta" : "";
                return `<article class="diet-nutrition-stat${status}">
                    <div><i class="fas ${icon}" aria-hidden="true"></i><span>${name}</span></div>
                    <strong>${value}<small>${unit}</small></strong>
                    <p>${target ? `Meta: ${target} ${unit} · ${percentage}%` : "Sem meta definida"}</p>
                    <span class="diet-nutrition-progress"><i style="width:${progress}%"></i></span>
                </article>`;
            }).join("")}</div>
        </section>`;
    }

    function renderSubstitutions(substitutions) {
        const safeSubstitutions = asArray(substitutions);
        if (!safeSubstitutions.length) return "";
        return `
            <div class="meal-substitutions">
                <strong><i class="fas fa-shuffle" aria-hidden="true"></i> Substituições</strong>
                <ul>${safeSubstitutions.map((substitution) => {
                    if (!substitution || typeof substitution !== "object") return `<li>${esc(substitution)}</li>`;
                    const alternatives = asArray(substitution.alternatives).map(esc).join(" ou ");
                    return `<li><span>${esc(substitution.replace || "Item")}</span><i class="fas fa-arrow-right" aria-hidden="true"></i>${alternatives || "Sem alternativa informada"}</li>`;
                }).join("")}</ul>
            </div>`;
    }

    function renderMealCard(meal, index) {
        const items = asArray(meal.items).map((item) => window.formatDietPlanItem?.(item) || String(item || "")).filter((item) => item.trim());
        const prepMinutes = meal.prep_minutes != null ? `${esc(meal.prep_minutes)} min` : "";
        return `
            <article class="meal-card meal-card--detailed">
                <header class="meal-card__header">
                    <span class="meal-card__order">${index + 1}</span>
                    <div><span class="meal-card__eyebrow">Refeição ${index + 1}</span><h5>${esc(meal.meal_type || "Refeição")}</h5></div>
                    ${prepMinutes ? `<span class="meal-prep-time"><i class="far fa-clock" aria-hidden="true"></i> ${prepMinutes}</span>` : ""}
                </header>
                ${items.length
                    ? `<ul class="meal-items">${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`
                    : `<p class="meal-description">${esc(window.formatDietPlanItemsText?.(meal) || meal.description || "Descrição não informada.")}</p>`}
                <div class="meal-macro-heading"><span>Macros estimados</span><small>valores aproximados</small></div>
                ${renderMealMacros(meal)}
                ${meal.prep_instructions ? `<div class="meal-preparation"><strong><i class="fas fa-kitchen-set" aria-hidden="true"></i> Como preparar</strong><p>${esc(meal.prep_instructions)}</p></div>` : ""}
                ${renderSubstitutions(meal.substitutions)}
                ${meal.notes ? `<p class="plan-note"><i class="fas fa-lightbulb" aria-hidden="true"></i> ${esc(meal.notes)}</p>` : ""}
            </article>`;
    }

    const SHOPPING_CATEGORIES = [
        ["Hortifruti", ["banana", "maçã", "maca", "mamão", "mamao", "tomate", "alface", "cenoura", "batata", "abacate", "fruta", "verdura", "legume"]],
        ["Proteínas", ["ovo", "frango", "carne", "peixe", "atum", "tofu", "proteína", "proteina"]],
        ["Grãos e cereais", ["arroz", "aveia", "pão", "pao", "quinoa", "macarrão", "macarrao", "granola", "farinha"]],
        ["Laticínios", ["leite", "iogurte", "queijo", "requeijão", "requeijao"]],
        ["Outros", []]
    ];
    const SHOPPING_SUBSTITUTIONS = {
        banana: ["Maçã", "Mamão"], maçã: ["Banana", "Mamão"], maca: ["Banana", "Mamão"],
        arroz: ["Quinoa", "Batata"], frango: ["Peixe", "Tofu"], peixe: ["Frango", "Tofu"],
        leite: ["Bebida vegetal", "Iogurte natural"], iogurte: ["Leite", "Bebida vegetal"],
        pão: ["Tapioca", "Aveia"], pao: ["Tapioca", "Aveia"]
    };

    function shoppingNormalize(value) {
        return String(value || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, " ").trim();
    }

    function parseShoppingItem(raw) {
        if (raw && typeof raw === "object") {
            const name = String(raw.name || raw.foodId || "").trim();
            const quantity = Number(raw.quantity);
            return { name, quantity: Number.isFinite(quantity) ? quantity : null, unit: String(raw.unit || "").trim() };
        }
        const text = String(raw || "").trim();
        const match = text.match(/^([0-9]+(?:[.,][0-9]+)?)\s*(kg|g|mg|ml|l|un(?:idade)?s?|unid\.?|xícaras?|colheres?|fatias?|porções?)\s+(?:de\s+)?(.+)$/i);
        if (match) return { name: match[3].trim(), quantity: Number(match[1].replace(",", ".")), unit: match[2].toLowerCase().replace("unidades", "un").replace("unidade", "un").replace("unid.", "un") };
        const simple = text.match(/^([0-9]+(?:[.,][0-9]+)?)\s+(.+)$/);
        if (simple && /\b(ovo|banana|maca|maçã|laranja|fatia|unidade)\b/i.test(simple[2])) return { name: simple[2].trim(), quantity: Number(simple[1].replace(",", ".")), unit: "un" };
        return { name: text, quantity: null, unit: "" };
    }

    function collectShoppingItems(plan) {
        const items = new Map();
        groupDietMeals(plan).forEach((group) => asArray(group.meals).forEach((meal) => asArray(meal.items).forEach((raw) => {
            const parsed = parseShoppingItem(raw);
            if (!parsed.name) return;
            const key = `${shoppingNormalize(parsed.name)}|${shoppingNormalize(parsed.unit)}`;
            const current = items.get(key) || { ...parsed, key, sources: 0 };
            if (current.quantity != null && parsed.quantity != null) current.quantity += parsed.quantity;
            else if (parsed.quantity != null && current.quantity == null) current.quantity = parsed.quantity;
            current.sources += 1;
            items.set(key, current);
        })));
        return Array.from(items.values());
    }

    function shoppingCategory(name) {
        const normalized = shoppingNormalize(name);
        return SHOPPING_CATEGORIES.find(([, terms]) => terms.some((term) => normalized.includes(shoppingNormalize(term))))?.[0] || "Outros";
    }

    function shoppingAvailable(plan) {
        return asArray(plan?.questionnaire?.available_ingredients).map(shoppingNormalize).filter(Boolean);
    }

    function renderShoppingList() {
        const details = byId("shoppingListDetails");
        const plan = dietView.plan;
        if (!details || !plan) return;
        const people = Math.max(1, Math.min(5, Number(dietShoppingState.people) || 1));
        dietShoppingState.people = people;
        const available = shoppingAvailable(plan);
        const items = collectShoppingItems(plan).map((item) => ({ ...item, available: available.some((value) => value === shoppingNormalize(item.name) || value.includes(shoppingNormalize(item.name)) || shoppingNormalize(item.name).includes(value)) }));
        const groups = new Map();
        items.forEach((item) => { if (dietShoppingState.hideAvailable && item.available) return; const category = shoppingCategory(item.name); if (!groups.has(category)) groups.set(category, []); groups.get(category).push(item); });
        const text = groups.size ? Array.from(groups, ([category, group]) => `${category}\n${group.map((item) => `${dietShoppingState.checked.has(item.key) ? "[x]" : "[ ]"} ${dietShoppingState.substitutions.get(item.key) || item.name}: ${item.quantity != null ? `${(item.quantity * people).toLocaleString("pt-BR")} ${item.unit}` : "conforme receita"}${item.available ? " (já disponível)" : ""}`).join("\n")}`).join("\n\n") : "Nenhum item para comprar.";
        details.innerHTML = `<div class="shopping-list-controls"><label for="shoppingPeople">Pessoas<select id="shoppingPeople">${[1,2,3,4,5].map((n) => `<option value="${n}" ${n === people ? "selected" : ""}>${n}</option>`).join("")}</select></label><label class="shopping-toggle"><input type="checkbox" id="shoppingHideAvailable" ${dietShoppingState.hideAvailable ? "checked" : ""}> Ocultar o que já tenho</label><button type="button" class="btn-secondary" data-shopping-action="share"><i class="fas fa-share-nodes"></i> Compartilhar</button></div><p class="shopping-list-meta">Lista consolidada para ${people} pessoa(s). Itens marcados ficam salvos nesta sessão.</p>${groups.size ? Array.from(groups, ([category, group]) => `<section class="shopping-category"><h4>${esc(category)}</h4><ul>${group.map((item) => { const key = esc(item.key); const substitute = dietShoppingState.substitutions.get(item.key); const label = substitute || item.name; return `<li class="shopping-item ${dietShoppingState.checked.has(item.key) ? "is-checked" : ""}"><label><input type="checkbox" data-shopping-check="${key}" ${dietShoppingState.checked.has(item.key) ? "checked" : ""}><span>${esc(label)}</span><small>${item.quantity != null ? `${esc((item.quantity * people).toLocaleString("pt-BR"))} ${esc(item.unit)}` : "Conforme receita"}${item.available ? " · Já disponível" : ""}</small></label>${substitute ? `<button type="button" class="shopping-substitute" data-shopping-restore="${key}">Restaurar</button>` : (SHOPPING_SUBSTITUTIONS[shoppingNormalize(item.name)] ? `<button type="button" class="shopping-substitute" data-shopping-substitute="${key}">Substituir</button>` : "")}</li>`; }).join("")}</ul></section>`).join("") : "<p class=\"plan-details-empty\">Nenhum ingrediente encontrado neste plano.</p>"}<textarea class="shopping-share-text" readonly aria-label="Texto da lista de compras">${esc(text)}</textarea>`;
    }

    function openShoppingList() {
        if (!dietView.plan) return;
        if (String(dietShoppingState.planId) !== String(dietView.plan.id)) { dietShoppingState.planId = dietView.plan.id; dietShoppingState.people = 1; dietShoppingState.hideAvailable = false; dietShoppingState.checked = new Set(); dietShoppingState.substitutions = new Map(); }
        renderShoppingList();
        openAppModal(byId("shoppingListModal"));
    }

    function closeShoppingListModal() { closeAppModal(byId("shoppingListModal")); }

    async function shareShoppingList() {
        const text = byId("shoppingListDetails")?.querySelector(".shopping-share-text")?.value || "Lista de compras";
        if (navigator.share) { await navigator.share({ title: "Lista de compras", text }).catch(() => {}); return; }
        try { await navigator.clipboard.writeText(text); showToast("Lista copiada para compartilhar.", "success"); } catch { showToast("Não foi possível copiar a lista.", "error"); }
    }

    function renderDietDetail() {
        const plan = dietView.plan;
        const details = byId("viewDietPlanDetails");
        if (!plan || !details) return;
        const groups = groupDietMeals(plan);
        if (dietView.selectedDay >= groups.length) dietView.selectedDay = 0;
        const targets = plan.nutrition_targets || {};
        const currentAction = plan.is_current
            ? '<span class="plan-current-pill"><i class="fas fa-star" aria-hidden="true"></i> Plano atual</span>'
            : '<button type="button" class="btn-primary plan-use-current" data-diet-action="set-current"><i class="fas fa-check" aria-hidden="true"></i> Usar este plano</button>';
        const summary = `
            <section class="plan-summary">
                <div class="plan-summary__icon"><i class="fas fa-apple-alt" aria-hidden="true"></i></div>
                <div><span>Plano alimentar</span><p>${esc(plan.description || "Uma rotina alimentar organizada para você.")}</p></div>
                <small><i class="far fa-calendar" aria-hidden="true"></i> ${esc(formatDateTime(plan.created_at))}</small>
            </section><div class="plan-current-action">${currentAction}<button type="button" class="btn-secondary" data-diet-action="shopping-list"><i class="fas fa-cart-shopping"></i> Lista de compras</button><button type="button" class="btn-secondary" onclick="openPlanReviewRequest('diet', '${esc(plan.id)}')"><i class="fas fa-user-check"></i> Solicitar revisão profissional</button>${plan.professional_review ? `<span class="professional-review-badge"><i class="fas fa-shield-check"></i> Revisado por ${esc(plan.professional_review.professional?.username || "profissional")}</span>` : ""}</div>`;
        if (!groups.length) {
            details.innerHTML = `${summary}<div class="plan-details-empty">Nenhuma refeição detalhada para este plano.</div>`;
            return;
        }
        const averageTotals = groups.reduce((totals, group) => {
            const dayTotals = dietNutritionTotals(group.meals);
            Object.keys(totals).forEach((key) => { totals[key] += dayTotals[key] / groups.length; });
            return totals;
        }, { calories: 0, protein: 0, carbs: 0, fat: 0 });
        const nutritionOverview = renderDietNutritionSummary(averageTotals, targets, "Média diária do plano");
        const tabs = `
            <div class="plan-day-tabs" role="tablist" aria-label="Dias do plano alimentar">
                ${groups.map((group, index) => `<button type="button" role="tab" id="diet-day-tab-${index}" aria-controls="diet-day-panel-${index}" aria-selected="${index === dietView.selectedDay}" tabindex="${index === dietView.selectedDay ? "0" : "-1"}" class="plan-day-tab${index === dietView.selectedDay ? " active" : ""}" data-diet-day-index="${index}"><span>Dia ${index + 1}</span><strong>${esc(group.name)}</strong><small>${Math.round(dietNutritionTotals(group.meals).calories)} kcal</small></button>`).join("")}
            </div>`;
        const sections = groups.map((group, index) => `
            <section id="diet-day-panel-${index}" role="tabpanel" aria-labelledby="diet-day-tab-${index}" class="plan-details-section diet-day-panel${index === dietView.selectedDay ? "" : " hidden"}">
                <div class="plan-section-title"><span><i class="far fa-calendar-check" aria-hidden="true"></i> ${esc(group.name)}</span><small>${group.meals.length} refeição(ões)</small></div>
                ${renderDietNutritionSummary(dietNutritionTotals(group.meals), targets, `Totais de ${group.name}`)}
                <div class="meal-list">${group.meals.map(renderMealCard).join("")}</div>
            </section>`).join("");
        details.innerHTML = `${summary}${nutritionOverview}${tabs}${sections}`;
    }

    async function viewDietPlan(id) {
        showGlobalLoading("Carregando detalhes do plano alimentar...");
        try {
            const plan = await apiRequest(`/diet_plans/${apiSegment(id)}`);
            dietView.plan = plan;
            dietView.selectedDay = 0;
            dietView.plan.professional_review = await apiRequest(`/diet_plans/${apiSegment(id)}/professional-review`).then((result) => result.professional_review).catch(() => null);
            const title = byId("viewDietPlanTitle");
            if (title) title.textContent = plan.title || "Plano de Dieta";
            renderDietDetail();
            openAppModal(byId("viewDietPlanModal"));
            return plan;
        } catch (error) {
            showToast(error.message, "error");
            return null;
        } finally {
            hideGlobalLoading();
        }
    }

    async function adjustDietPlan(id) {
        showGlobalLoading("Carregando plano para ajuste...");
        try {
            const plan = await apiRequest(`/diet_plans/${apiSegment(id)}`);
            openDietPlanWizardWithPlan(plan);
        } catch (error) {
            showToast(error.message, "error");
        } finally {
            hideGlobalLoading();
        }
    }

    async function setCurrentDietPlan(id = dietView.plan?.id) {
        if (!id) return;
        try {
            const result = await apiRequest(`/diet_plans/${apiSegment(id)}/current`, { method: "PUT" });
            if (dietView.plan && String(dietView.plan.id) === String(id)) {
                dietView.plan = { ...dietView.plan, ...result.plan, is_current: true };
                renderDietDetail();
            }
            await loadDietPlans();
            window.loadTodayCardapio?.();
            showToast("Plano alimentar definido como atual.", "success");
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    function normalizedWorkoutDays(plan) {
        const days = asArray(plan.days);
        if (days.length) {
            return days.map((day, index) => ({
                ...(day || {}),
                title: day?.title || `Treino ${index + 1}`,
                code: day?.code || String(index + 1),
                exercises: asArray(day?.exercises)
            }));
        }
        if (asArray(plan.exercises).length) {
            return [{ id: null, code: "A", title: "Treino A", focus: "Plano anterior", order: 1, exercises: asArray(plan.exercises) }];
        }
        return [];
    }

    function selectedWorkoutDay() {
        return workoutView.days[workoutView.selectedDay] || null;
    }

    function workoutOverrideFor(exerciseId) {
        return asArray(workoutView.session?.overrides).find((override) => String(override.workout_exercise_id) === String(exerciseId));
    }

    function displayedExercise(exercise) {
        const override = workoutOverrideFor(exercise.id);
        if (!override) return { exercise, override: null };
        return {
            exercise: { ...exercise, ...override, id: exercise.id },
            override
        };
    }

    function completedWorkoutExerciseIds() {
        return new Set(asArray(workoutView.session?.completed_exercise_ids).map(String));
    }

    function workoutElapsedSeconds(startedAt) {
        if (!startedAt) return 0;
        const value = String(startedAt);
        const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`;
        const started = new Date(normalized).getTime();
        return Number.isFinite(started) ? Math.max(0, Math.floor((Date.now() - started) / 1000)) : 0;
    }

    function formatWorkoutElapsed(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const remainder = seconds % 60;
        return [hours, minutes, remainder].map((value) => String(value).padStart(2, "0")).join(":");
    }

    function updateWorkoutTimer() {
        document.querySelectorAll("[data-workout-elapsed]").forEach((timer) => {
            const startedAt = timer.dataset.workoutStartedAt || workoutView.session?.started_at || activeWorkoutSummary?.session?.started_at;
            timer.textContent = formatWorkoutElapsed(workoutElapsedSeconds(startedAt));
        });
    }

    function renderActiveWorkoutDock() {
        const dock = byId("activeWorkoutDock");
        if (!dock) return;
        const summary = activeWorkoutSummary;
        dock.classList.toggle("hidden", !summary?.session);
        if (!summary?.session) return;
        const title = byId("activeWorkoutDockTitle");
        const timer = byId("activeWorkoutDockTimer");
        if (title) title.textContent = summary.day?.title || summary.plan?.title || "Treino atual";
        if (timer) timer.dataset.workoutStartedAt = summary.session.started_at || "";
        updateWorkoutTimer();
    }

    function clearActiveWorkoutDock() {
        activeDockRequestToken += 1;
        activeWorkoutSummary = null;
        renderActiveWorkoutDock();
    }

    async function loadActiveWorkoutDock(force = false) {
        if (!window.currentUser) {
            clearActiveWorkoutDock();
            return;
        }
        const token = ++activeDockRequestToken;
        const account = workoutAccount();
        const version = workoutView.viewVersion;
        const revision = workoutView.mutationRevision;
        if (workoutView.pendingAction || workoutView.uncertainMutation || workoutGesture || document.visibilityState === "hidden") return;
        let result;
        try {
            const loader = ({ signal } = {}) => apiRequest("/workout_sessions/active", { signal });
            result = window.AppReadCache
                ? await window.AppReadCache.read(`workout:active:${account}`, loader, { ttl: 30000, force })
                : await loader();
        } catch (error) {
            if (token === activeDockRequestToken && revision === workoutView.mutationRevision && workoutContextCurrent(account, version) && workoutView.session && error.name !== "AbortError") {
                workoutView.sessionError = error.message;
                renderWorkoutDetail({ preserveScroll: true });
            }
            return;
        }
        if (token !== activeDockRequestToken || !workoutContextCurrent(account, version)
            || revision !== workoutView.mutationRevision || workoutView.pendingAction || workoutView.uncertainMutation || workoutGesture
            || byId("mainScreen")?.classList.contains("hidden")) return;
        activeWorkoutSummary = result;
        renderActiveWorkoutDock();
        const modalOpen = byId("viewWorkoutPlanModal")?.classList.contains("show");
        if (!modalOpen || !workoutView.session) return;
        if (result?.session && String(result.session.id) === String(workoutView.session.id)) {
            const changed = JSON.stringify(workoutView.session) !== JSON.stringify(result.session);
            workoutView.session = result.session;
            hydrateWorkoutDrafts(result.session);
            if (changed) renderWorkoutDetail({ preserveScroll: true });
        } else if (!result?.session) {
            workoutView.session = null;
            workoutView.replacementPanels.clear();
            renderWorkoutDetail({ preserveScroll: true });
        } else if (String(result.session.id) !== String(workoutView.session.id)) {
            workoutView.session = null;
            workoutView.replacementPanels.clear();
            closeViewWorkoutPlanModal();
            showToast("Outro treino está em andamento. Use o atalho para continuar.", "info");
        }
    }

    async function openActiveWorkout() {
        const summary = activeWorkoutSummary;
        if (!summary?.session || !summary.plan?.id) return;
        await viewWorkoutPlan(summary.plan.id, summary.day?.id);
    }

    async function openWorkoutActivity(activityId) {
        showGlobalLoading("Carregando atividade...");
        try {
            const result = await apiRequest(`/activities/${apiSegment(activityId)}`);
            workoutView.editMode = false;
            workoutView.session = null;
            workoutView.completedSummary = {
                ...result.activity,
                achievements_unlocked: asArray(result.achievements),
            };
            workoutView.summaryOrigin = "activities";
            workoutView.shareOpen = false;
            workoutView.shareDraft = null;
            const title = byId("viewWorkoutPlanTitle");
            if (title) title.textContent = "Atividade";
            renderWorkoutDetail();
            openAppModal(byId("viewWorkoutPlanModal"));
        } catch (error) {
            showToast(error.message, "error");
        } finally {
            hideGlobalLoading();
        }
    }

    function createExerciseGoalFromSummary(exerciseKey, exerciseName, trigger) {
        window.openExerciseGoalForm?.(exerciseKey, exerciseName, trigger);
    }

    function isCurrentWorkoutSession(sessionId) {
        return String(workoutView.session?.id || "") === String(sessionId || "");
    }

    function invalidateWorkoutView() {
        persistWorkoutDraftLocally(workoutView.session?.id);
        cancelWorkoutDraftTimers();
        cancelWorkoutPlayerGesture();
        workoutView.viewVersion += 1;
        workoutView.requestToken += 1;
        workoutView.pendingAction = "";
        workoutView.editMode = false;
        workoutView.addExerciseOpen = false;
        clearReplacementPanels();
    }

    function exerciseImage(exercise) {
        return typeof exerciseImagePath === "function"
            ? exerciseImagePath(exercise?.name, exercise?.catalog_key)
            : "";
    }

    async function preloadWorkoutAssets(day) {
        const exercises = asArray(day?.exercises);
        const activeIndex = exercises.findIndex((exercise) => String(exercise.id) === String(workoutView.activeExerciseId));
        const start = workoutView.session ? Math.max(activeIndex, 0) : 0;
        const preload = exercises.slice(start, start + 2);
        await Promise.all(preload.map((original) => {
            const exercise = displayedExercise(original).exercise;
            const src = exerciseImage(exercise);
            if (!src) return Promise.resolve();
            return new Promise((resolve) => {
                const image = new Image();
                image.onload = () => {
                    if (!image.decode) return resolve();
                    image.decode().catch(() => {}).finally(resolve);
                };
                image.onerror = resolve;
                image.src = src;
            });
        }));
    }

    async function preloadReplacementOptions(day, session) {
        if (!session || navigator.onLine === false) return;
        const account = workoutAccount();
        const payload = replacementPayload();
        await Promise.allSettled(asArray(day?.exercises).map(async (exercise) => {
            const key = String(exercise.id);
            const cacheKey = `workout:options:${account}:${session.id}:${key}:${JSON.stringify(session.overrides)}`;
            const cached = window.AppReadCache?.peek(cacheKey);
            if (cached && Date.now() - cached.at < 60000) return;
            const path = `/workout_sessions/${apiSegment(session.id)}/exercises/${apiSegment(key)}/replacement_options`;
            const result = await apiRequest(path, { method: "POST", body: payload, timeout: 30000 });
            if (window.AppReadCache) await window.AppReadCache.read(cacheKey, () => result, { ttl: 60000, force: true });
        }));
    }

    function exerciseImageMarkup(exercise, eager = false) {
        const imagePath = exerciseImage(exercise);
        if (imagePath) {
            const fallbackPath = typeof exerciseFallbackImagePath === "function"
                ? exerciseFallbackImagePath(exercise?.catalog_key)
                : "";
            const fallback = fallbackPath && fallbackPath !== imagePath ? ` data-fallback-src="${esc(fallbackPath)}"` : "";
            return `<img class="exercise-demonstration-image" src="${esc(imagePath)}"${fallback} alt="Demonstração de ${esc(exercise?.name || "exercício")}" loading="${eager ? "eager" : "lazy"}" decoding="async" width="768" height="1024">`;
        }
        return '<span class="exercise-image-placeholder" role="img" aria-label="Imagem não disponível"><i class="fas fa-dumbbell" aria-hidden="true"></i></span>';
    }

    function equipmentLabel(value) {
        return labelFor({ ...WORKOUT_EQUIPMENT, ...CATALOG_EQUIPMENT_LABELS }, value, value || "Equipamento livre");
    }

    function renderReplacementPanel(exercise, panel) {
        if (!panel) return "";
        const permanent = panel.mode === "permanent";
        const panelId = `replacement-panel-${esc(exercise.id)}`;
        const currentExercise = displayedExercise(exercise).exercise;
        const replacementOptions = asArray(panel.options);
        const visibleOptions = panel.expanded ? replacementOptions : replacementOptions.slice(0, 3);
        if (panel.loading) {
            return `<section id="${panelId}" class="replacement-panel" tabindex="-1" aria-live="polite"><button type="button" class="replacement-close" data-workout-action="close-replacements" data-exercise-id="${esc(exercise.id)}" aria-label="Fechar alternativas">×</button><div class="replacement-panel__loading"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>Buscando alternativas seguras...</span></div></section>`;
        }
        return `
            <section id="${panelId}" class="replacement-panel" tabindex="-1" aria-labelledby="replacement-title-${esc(exercise.id)}">
                <div class="replacement-panel__header">
                    <div><span>${permanent ? "Alteração permanente" : "Somente nesta sessão"}</span><h6 id="replacement-title-${esc(exercise.id)}">Trocar ${esc(currentExercise.name || exercise.name)}</h6><p>Melhores opções compatíveis para continuar o treino.</p></div>
                    <button type="button" class="replacement-close" data-workout-action="close-replacements" data-exercise-id="${esc(exercise.id)}" aria-label="Fechar alternativas"><i class="fas fa-xmark" aria-hidden="true"></i></button>
                </div>
                ${panel.error ? `<p class="session-inline-error" role="alert">${esc(panel.error)}</p><button type="button" data-workout-action="${panel.mode === "permanent" ? "permanent-replacement-options" : "replacement-options"}" data-exercise-id="${esc(exercise.id)}">Tentar novamente</button>` : ""}
                ${panel.message ? `<p class="replacement-message">${esc(panel.message)}</p>` : ""}
                <div class="replacement-options">
                    ${visibleOptions.map((option) => {
                        const matchItems = [
                            option.primary_muscle && option.primary_muscle === currentExercise.primary_muscle && '<span><i class="fas fa-bullseye" aria-hidden="true"></i> Mesmo músculo</span>',
                            option.movement_pattern && option.movement_pattern === currentExercise.movement_pattern && '<span><i class="fas fa-arrows-rotate" aria-hidden="true"></i> Mesmo movimento</span>',
                            option.equipment && option.equipment === currentExercise.equipment && '<span><i class="fas fa-dumbbell" aria-hidden="true"></i> Mesmo equipamento</span>'
                        ].filter(Boolean);
                        const matches = (matchItems.length ? matchItems : ['<span><i class="fas fa-check" aria-hidden="true"></i> Movimento compatível</span>']).join("");
                        const reason = String(option.rationale || "Mantém o foco do exercício original.").replace(/_/g, " ");
                        return `
                        <article class="replacement-option">
                            ${exerciseImageMarkup(option)}
                            <div class="replacement-option__body"><h6>${esc(option.name)}</h6><p>${esc(reason)}</p><div class="replacement-option__matches">${matches}</div><span class="replacement-option__equipment"><i class="fas fa-dumbbell" aria-hidden="true"></i> ${esc(equipmentLabel(option.equipment))}</span></div>
                            <button type="button" class="replacement-apply" data-workout-action="${permanent ? "apply-permanent-replacement" : "apply-replacement"}" data-exercise-id="${esc(exercise.id)}" data-catalog-key="${esc(option.catalog_key)}"${panel.applying === option.catalog_key ? " disabled" : ""}>${panel.applying === option.catalog_key ? '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Aplicando' : permanent ? "Trocar no plano" : "Trocar por este"}</button>
                        </article>`;
                    }).join("")}
                </div>
                ${!panel.expanded && replacementOptions.length > 3 ? `<button type="button" class="replacement-show-more" data-workout-action="show-more-replacements" data-exercise-id="${esc(exercise.id)}"><i class="fas fa-chevron-down" aria-hidden="true"></i> Ver mais alternativas</button>` : ""}
                ${!panel.error && !replacementOptions.length ? '<div class="replacement-empty"><i class="fas fa-circle-info" aria-hidden="true"></i><span>Nenhuma alternativa disponível para os equipamentos do plano.</span></div>' : ""}
            </section>`;
    }

    function renderExerciseCard(originalExercise, index) {
        const { exercise, override } = displayedExercise(originalExercise);
        const active = Boolean(workoutView.session);
        const editing = !active && workoutView.editMode;
        const panel = workoutView.replacementPanels.get(String(originalExercise.id));
        const order = originalExercise.order || index + 1;
        const detailChips = [
            exercise.primary_muscle && `<span><i class="fas fa-bullseye" aria-hidden="true"></i>${esc(exercise.primary_muscle)}</span>`,
            exercise.equipment && `<span><i class="fas fa-dumbbell" aria-hidden="true"></i>${esc(equipmentLabel(exercise.equipment))}</span>`,
            exercise.difficulty && `<span><i class="fas fa-signal" aria-hidden="true"></i>${esc(labelFor(EXPERIENCE_LEVELS, exercise.difficulty, exercise.difficulty))}</span>`
        ].filter(Boolean).join("");
        return `
            <article class="exercise-card session-exercise-card${override ? " exercise-card--overridden" : ""}">
                <span class="exercise-card__number">${esc(order)}</span>
                <figure class="exercise-card__image">${exerciseImageMarkup(exercise)}</figure>
                <div class="exercise-card__content">
                    <div class="exercise-card__title-row"><div>${override ? '<span class="session-override-badge"><i class="fas fa-shuffle" aria-hidden="true"></i> Substituição de hoje</span>' : ""}<h5>${esc(exercise.name || "Exercício")}</h5>${exercise.movement_pattern ? `<small>${esc(exercise.movement_pattern)}</small>` : ""}</div></div>
                    <div class="exercise-card__prescription"><strong>${esc(exercise.sets ?? "—")} <small>séries</small></strong><span>×</span><strong>${esc(exercise.reps ?? "—")} <small>reps</small></strong>${exercise.rest_seconds ? `<strong>${esc(exercise.rest_seconds)}s <small>descanso</small></strong>` : ""}</div>
                    ${detailChips ? `<div class="exercise-meta">${detailChips}</div>` : ""}
                    ${exercise.weight ? `<p class="exercise-guidance"><i class="fas fa-weight-hanging" aria-hidden="true"></i><span><strong>Carga</strong>${esc(exercise.weight)}</span></p>` : ""}
                    ${exercise.effort_guidance ? `<p class="exercise-guidance"><i class="fas fa-gauge-high" aria-hidden="true"></i><span><strong>Esforço</strong>${esc(exercise.effort_guidance)}</span></p>` : ""}
                    ${exercise.notes ? `<p class="plan-note"><i class="fas fa-info-circle" aria-hidden="true"></i> ${esc(exercise.notes)}</p>` : ""}
                </div>
                ${active
                    ? `<div class="exercise-session-actions"><button type="button" class="machine-busy-button" data-workout-action="replacement-options" data-exercise-id="${esc(originalExercise.id)}" aria-expanded="${Boolean(panel)}" aria-controls="replacement-panel-${esc(originalExercise.id)}"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i> Máquina ocupada</button>${override ? `<button type="button" class="restore-exercise-button" data-workout-action="restore-exercise" data-exercise-id="${esc(originalExercise.id)}"${workoutView.pendingAction === `restore-${originalExercise.id}` ? " disabled" : ""}><i class="fas fa-rotate-left" aria-hidden="true"></i> Restaurar original</button>` : ""}</div>`
                    : editing
                        ? `<div class="workout-edit-actions"><button type="button" data-workout-action="permanent-replacement-options" data-exercise-id="${esc(originalExercise.id)}" aria-expanded="${Boolean(panel)}" aria-controls="replacement-panel-${esc(originalExercise.id)}"><i class="fas fa-shuffle" aria-hidden="true"></i> Substituir</button><button type="button" class="workout-remove-exercise" data-workout-action="delete-plan-exercise" data-exercise-id="${esc(originalExercise.id)}"><i class="fas fa-trash" aria-hidden="true"></i> Remover</button></div>`
                        : ""}
                ${active || editing ? renderReplacementPanel(originalExercise, panel) : ""}
            </article>`;
    }

    function renderAddExercisePanel(day) {
        if (!workoutView.editMode || !workoutView.addExerciseOpen) return "";
        if (workoutView.catalogLoading) return '<div class="workout-add-panel"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Carregando exercícios compatíveis...</div>';
        const existingKeys = new Set(asArray(day.exercises).map((exercise) => exercise.catalog_key));
        const options = asArray(workoutView.exerciseCatalog).filter((item) => !existingKeys.has(item.key));
        return `<section class="workout-add-panel" aria-label="Adicionar exercício">
            <div class="workout-add-panel__heading"><div><span>Editar plano</span><h5>Adicionar exercício</h5></div><button type="button" data-workout-action="toggle-add-exercise" aria-label="Fechar"><i class="fas fa-xmark" aria-hidden="true"></i></button></div>
            ${options.length ? `<div class="workout-add-fields">
                <label>Exercício<input id="workoutAddExerciseName" list="workoutAddExerciseOptions" maxlength="100" placeholder="Digite ou escolha uma opção"><datalist id="workoutAddExerciseOptions">${options.map((item) => `<option value="${esc(item.name)}">${esc(equipmentLabel(item.equipment))}</option>`).join("")}</datalist><small>Você também pode cadastrar um nome personalizado.</small></label>
                <label>Séries<input id="workoutAddSets" type="number" min="1" max="10" value="3"></label>
                <label>Repetições<input id="workoutAddReps" maxlength="30" value="8-12"></label>
                <label>Descanso<input id="workoutAddRest" type="number" min="0" max="600" value="60"></label>
            </div><button type="button" class="btn-primary workout-add-save" data-workout-action="add-plan-exercise"${workoutView.pendingAction === "add-exercise" ? " disabled" : ""}><i class="fas fa-plus" aria-hidden="true"></i> ${workoutView.pendingAction === "add-exercise" ? "Adicionando..." : "Adicionar ao treino"}</button>` : '<p class="replacement-empty">Todos os exercícios compatíveis já estão neste treino.</p>'}
        </section>`;
    }

    function workoutSetRowMarkup(order, values = {}, current = false) {
        const completed = Boolean(values.completed);
        return `<div class="workout-set-row${completed ? " is-complete" : ""}${current ? " is-current" : ""}" data-workout-set-completed="${completed}" data-workout-set-index="${order - 1}"><strong><small>Série</small>${esc(order)}</strong><label><span>Carga (kg)</span><input type="text" inputmode="decimal" value="${esc(values.load_kg || "")}" data-workout-set-load aria-label="Carga total da série ${esc(order)} em kg"></label><label><span>Repetições</span><input type="text" inputmode="numeric" value="${esc(values.repetitions || "")}" data-workout-set-repetitions aria-label="Repetições da série ${esc(order)}"></label><label class="workout-set-warmup"><input type="checkbox" data-workout-set-warmup${values.is_warmup ? " checked" : ""}><span>Aquecimento</span></label><button type="button" class="workout-set-complete" data-workout-action="toggle-set-complete" aria-pressed="${completed}" aria-label="${completed ? "Reabrir" : "Concluir"} série ${esc(order)}"><i class="fas ${completed ? "fa-check" : "fa-circle"}" aria-hidden="true"></i><span>${completed ? "Feita" : "Marcar"}</span></button>${!completed ? `<button type="button" class="workout-set-remove" data-workout-action="remove-set" aria-label="Remover série ${esc(order)}"><i class="fas fa-minus" aria-hidden="true"></i></button>` : ""}</div>`;
    }

    function workoutSetDraftAt(exerciseId, index, minimumCount = index + 1) {
        const key = String(exerciseId);
        const drafts = asArray(workoutView.setDrafts.get(key)).map(item => ({ ...item }));
        while (drafts.length < minimumCount) {
            drafts.push({ load_kg: "", repetitions: "", is_warmup: false, completed: false });
        }
        workoutView.setDrafts.set(key, drafts);
        return drafts[index];
    }

    function firstPendingWorkoutSetIndex(exerciseId, count) {
        const drafts = asArray(workoutView.setDrafts.get(String(exerciseId)));
        return Array.from({ length: count }, (_, index) => index).find(index => !drafts[index]?.completed);
    }

    function setWorkoutEntryMode(mode, options = {}) {
        if (!['closed', 'quick', 'review'].includes(mode) || workoutView.pendingAction) return;
        const exercise = findSelectedExercise(workoutView.activeExerciseId);
        if (!exercise) return;
        const count = Math.max(workoutPlannedSetCount(exercise), asArray(workoutView.setDrafts.get(String(exercise.id))).length);
        workoutView.setEntryMode = mode;
        workoutView.sessionSheetExpanded = mode === 'review';
        workoutView.setEntryError = "";
        if (mode === 'quick') {
            const requested = Number(options.index);
            const pending = firstPendingWorkoutSetIndex(exercise.id, count);
            workoutView.activeSetIndex = Number.isInteger(requested) && requested >= 0 && requested < count
                ? requested
                : (pending == null ? count : pending);
            workoutView.correctionSetIndex = options.correction ? workoutView.activeSetIndex : null;
        } else {
            workoutView.correctionSetIndex = null;
        }
        persistWorkoutDraftLocally(workoutView.session?.id);
        const focusSelector = mode === 'quick'
            ? (displayedExercise(exercise).exercise.weight ? '[data-workout-quick-load]' : '[data-workout-quick-repetitions]')
            : mode === 'review' ? '#workoutSetEntryTitle' : '.workout-sheet-handle';
        renderWorkoutDetail({ preserveScroll: true, focusSelector });
    }

    function updateWorkoutQuickSetDraft(field, value, exerciseId, index) {
        if (!exerciseId || !Number.isInteger(index) || index < 0) return;
        const exercise = findSelectedExercise(exerciseId);
        const count = Math.max(workoutPlannedSetCount(exercise), index + 1);
        const draft = workoutSetDraftAt(exerciseId, index, count);
        draft[field] = value;
        workoutView.setEntryError = "";
        const reviewRow = document.querySelector(`.workout-set-row[data-workout-set-index="${index}"]`);
        const reviewField = field === 'load_kg'
            ? reviewRow?.querySelector('[data-workout-set-load]')
            : reviewRow?.querySelector('[data-workout-set-repetitions]');
        if (reviewField) reviewField.value = value;
        scheduleWorkoutDraftSave(exerciseId);
    }

    function renderWorkoutQuickSetEntry(originalExercise, exercise, setCount) {
        if (workoutView.setEntryMode !== 'quick') return "";
        const exerciseId = String(originalExercise.id);
        const drafts = asArray(workoutView.setDrafts.get(exerciseId));
        const requestedIndex = workoutView.correctionSetIndex ?? workoutView.activeSetIndex;
        const index = Number.isInteger(requestedIndex) ? requestedIndex : (firstPendingWorkoutSetIndex(exerciseId, setCount) ?? setCount);
        const correcting = workoutView.correctionSetIndex != null && index < setCount;
        const last = workoutView.lastConfirmedSet?.exerciseId === exerciseId ? workoutView.lastConfirmedSet : null;
        const rest = workoutView.rest?.endsAt > Date.now()
            ? `<div class="workout-quick-rest" role="timer"><span><i class="fas fa-hourglass-half" aria-hidden="true"></i> Descanso</span><strong data-workout-rest-compact>${formatRestRemaining((workoutView.rest.endsAt - Date.now()) / 1000)}</strong><div><button type="button" data-workout-action="adjust-rest" data-rest-seconds="30">+30s</button><button type="button" data-workout-action="skip-rest">Pular</button></div></div>`
            : "";
        if (index >= setCount) {
            const completed = drafts.filter(item => item?.completed).length;
            return `<section class="workout-quick-set-layer is-open is-checkpoint" aria-labelledby="workoutQuickSetTitle" data-workout-set-index="${setCount}">
                <header><div><small>Séries previstas concluídas</small><h3 id="workoutQuickSetTitle" tabindex="-1">${esc(completed)} de ${esc(setCount)} séries confirmadas</h3></div><button type="button" data-workout-action="close-set-entry" aria-label="Fechar registro de séries"><i class="fas fa-chevron-down" aria-hidden="true"></i></button></header>
                ${rest}
                <div class="workout-quick-checkpoint"><i class="fas fa-check-double" aria-hidden="true"></i><p>Revise os registros ou avance quando estiver pronto.</p></div>
                <div class="workout-quick-secondary">${last ? `<button type="button" data-workout-action="correct-last-set"><i class="fas fa-pen" aria-hidden="true"></i> Corrigir série ${last.index + 1}</button>` : ""}<button type="button" data-workout-action="add-quick-set"><i class="fas fa-plus" aria-hidden="true"></i> Adicionar série</button><button type="button" data-workout-action="review-sets"><i class="fas fa-list" aria-hidden="true"></i> Revisar todas</button></div>
                <button type="button" class="workout-quick-primary" data-workout-action="complete-exercise" data-exercise-id="${esc(originalExercise.id)}"><i class="fas fa-arrow-right" aria-hidden="true"></i> Concluir exercício e avançar</button>
            </section>`;
        }
        const values = drafts[index] || {};
        const error = workoutView.setEntryError
            ? `<div class="workout-quick-error" role="alert">${esc(workoutView.setEntryError)}${values.load_kg && !values.repetitions ? '<button type="button" data-workout-action="confirm-empty-set">Continuar sem registrar valores</button>' : ""}</div>`
            : "";
        return `<section class="workout-quick-set-layer is-open${correcting ? " is-correcting" : ""}" aria-labelledby="workoutQuickSetTitle" data-workout-set-index="${index}">
            <header><div><small>${correcting ? "Corrigir registro" : `Série ${index + 1} de ${setCount}`}</small><h3 id="workoutQuickSetTitle" tabindex="-1">${correcting ? `Série ${index + 1}` : `Registrar Série ${index + 1}`}</h3></div><button type="button" data-workout-action="close-set-entry" aria-label="Fechar registro de séries"><i class="fas fa-chevron-down" aria-hidden="true"></i></button></header>
            <div class="workout-quick-goals" aria-label="Metas da série"><span><small>Meta de carga</small><strong>${esc(exercise.weight || "Sem carga definida")}</strong></span><span><small>Meta de repetições</small><strong>${esc(exercise.reps || "Sem meta definida")}</strong></span><span><small>Descanso</small><strong>${esc(exercise.rest_seconds ? `${exercise.rest_seconds}s` : "Sem descanso")}</strong></span></div>
            ${rest}
            <div class="workout-quick-fields"><label><span>Carga <small>kg</small></span><input type="text" inputmode="decimal" autocomplete="off" enterkeyhint="next" value="${esc(values.load_kg || "")}" data-workout-quick-load aria-label="Carga da série ${index + 1} em kg"></label><label><span>Repetições</span><input type="text" inputmode="numeric" autocomplete="off" enterkeyhint="done" value="${esc(values.repetitions || "")}" data-workout-quick-repetitions aria-label="Repetições da série ${index + 1}"></label></div>
            ${error}
            <p class="workout-quick-optional">O registro é opcional. Você pode confirmar a série com os campos vazios.</p>
            <div class="workout-quick-secondary">${last && (!correcting || last.index !== index) ? `<button type="button" data-workout-action="correct-last-set"><i class="fas fa-pen" aria-hidden="true"></i> Corrigir série ${last.index + 1}</button>` : ""}<button type="button" data-workout-action="review-sets"><i class="fas fa-list" aria-hidden="true"></i> Revisar todas</button></div>
            <button type="button" class="workout-quick-primary" data-workout-action="confirm-quick-set" data-exercise-id="${esc(originalExercise.id)}">${correcting ? '<i class="fas fa-check" aria-hidden="true"></i> Salvar correção' : `<i class="fas fa-check" aria-hidden="true"></i> Confirmar série ${index + 1}`}</button>
        </section>`;
    }

    function confirmWorkoutQuickSet(exerciseId, options = {}) {
        const exercise = findSelectedExercise(exerciseId);
        if (!exercise || workoutView.setEntryMode !== 'quick') return false;
        const setCount = Math.max(workoutPlannedSetCount(exercise), asArray(workoutView.setDrafts.get(String(exerciseId))).length);
        const index = workoutView.correctionSetIndex ?? workoutView.activeSetIndex;
        if (!Number.isInteger(index) || index < 0 || index >= setCount) return false;
        const draft = workoutSetDraftAt(exerciseId, index, setCount);
        if (options.discardPartial) {
            draft.load_kg = "";
            draft.repetitions = "";
        }
        const repetitions = String(draft.repetitions || "").trim();
        const load = String(draft.load_kg || "").trim();
        if (load && !repetitions) {
            workoutView.setEntryError = "Informe as repetições ou continue sem registrar valores.";
            renderWorkoutDetail({ preserveScroll: true, focusSelector: '[data-workout-quick-repetitions]' });
            return false;
        }
        if (repetitions && (!Number.isInteger(Number(repetitions)) || Number(repetitions) < 1 || Number(repetitions) > 1000)) {
            workoutView.setEntryError = "Informe repetições entre 1 e 1000.";
            renderWorkoutDetail({ preserveScroll: true, focusSelector: '[data-workout-quick-repetitions]' });
            return false;
        }
        const normalizedLoad = load.replace(',', '.');
        if (load && (!Number.isFinite(Number(normalizedLoad)) || Number(normalizedLoad) < 0 || Number(normalizedLoad) > 100000)) {
            workoutView.setEntryError = "Informe uma carga válida.";
            renderWorkoutDetail({ preserveScroll: true, focusSelector: '[data-workout-quick-load]' });
            return false;
        }
        const correcting = workoutView.correctionSetIndex != null;
        draft.completed = true;
        workoutView.setEntryError = "";
        if (!correcting) workoutView.lastConfirmedSet = { exerciseId: String(exerciseId), index };
        workoutView.correctionSetIndex = null;
        const next = firstPendingWorkoutSetIndex(exerciseId, setCount);
        workoutView.activeSetIndex = next == null ? setCount : next;
        scheduleWorkoutDraftSave(exerciseId);
        if (!correcting) {
            const seconds = Math.min(600, Math.max(0, Number(displayedExercise(exercise).exercise.rest_seconds) || 0));
            workoutView.rest = seconds ? { duration: seconds, endsAt: Date.now() + seconds * 1000, exerciseId: String(exerciseId) } : null;
        }
        persistWorkoutDraftLocally(workoutView.session?.id);
        renderWorkoutDetail({ preserveScroll: true, focusSelector: workoutView.activeSetIndex < setCount ? '[data-workout-quick-load], [data-workout-quick-repetitions]' : '#workoutQuickSetTitle' });
        return true;
    }

    function captureWorkoutSetDraft(exerciseId) {
        const rows = Array.from(document.querySelectorAll(".workout-set-row"));
        if (!exerciseId || !rows.length) return;
        workoutView.setDrafts.set(String(exerciseId), rows.map((row) => ({
            load_kg: row.querySelector("[data-workout-set-load]")?.value.trim() || "",
            repetitions: row.querySelector("[data-workout-set-repetitions]")?.value.trim() || "",
            is_warmup: Boolean(row.querySelector("[data-workout-set-warmup]")?.checked),
            completed: row.dataset.workoutSetCompleted === "true",
        })));
        scheduleWorkoutDraftSave(exerciseId);
    }

    function formatRestRemaining(seconds) {
        const safe = Math.max(0, Math.ceil(seconds));
        return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
    }

    function renderWorkoutRest(nextStep = "Próxima série") {
        if (!workoutView.rest?.endsAt || workoutView.rest.endsAt <= Date.now()) return "";
        const remaining = (workoutView.rest.endsAt - Date.now()) / 1000;
        return `<section class="workout-rest" role="timer" aria-live="polite"><div class="workout-rest__clock"><small><i class="fas fa-hourglass-half" aria-hidden="true"></i> Descanso</small><strong id="workoutRestTime">${formatRestRemaining(remaining)}</strong><span>${esc(nextStep)}</span></div><div class="workout-rest__actions"><button type="button" data-workout-action="adjust-rest" data-rest-seconds="30"><i class="fas fa-plus" aria-hidden="true"></i>30s</button><button type="button" class="workout-rest-skip" data-workout-action="skip-rest">Pular descanso</button></div></section>`;
    }

    function startWorkoutRest(seconds, exerciseId) {
        const duration = Math.max(0, Math.min(600, Number(seconds) || 0));
        if (!duration) return;
        workoutView.rest = { duration, endsAt: Date.now() + duration * 1000, exerciseId: String(exerciseId) };
        persistWorkoutDraftLocally(workoutView.session?.id);
        renderWorkoutDetail({ preserveScroll: true });
    }

    function setWorkoutSheetExpanded(expanded) {
        if (workoutView.pendingAction) return;
        setWorkoutEntryMode(expanded ? 'quick' : 'closed');
    }

    function workoutPlayerFeedbackMarkup() {
        const message = workoutView.pendingAction ? "Salvando…" : workoutView.sessionError || workoutView.draftError || "";
        return `<div class="workout-player-feedback" data-workout-feedback role="${workoutView.sessionError ? "alert" : "status"}"${message ? "" : " hidden"}>${esc(message)}${workoutView.sessionError && !workoutView.pendingAction ? '<button type="button" data-workout-action="retry-session">Verificar e tentar novamente</button>' : ""}</div>`;
    }

    function updateWorkoutPlayerFeedback() {
        document.querySelectorAll("[data-workout-feedback]").forEach((element) => {
            const template = document.createElement("template");
            template.innerHTML = workoutPlayerFeedbackMarkup();
            patchWorkoutNode(element, template.content.firstElementChild);
        });
    }

    function adjustWorkoutRest(seconds) {
        if (!workoutView.rest) return;
        const remaining = workoutView.rest.endsAt - Date.now() + Number(seconds) * 1000;
        if (remaining <= 0) workoutView.rest = null;
        else workoutView.rest.endsAt = Date.now() + Math.min(600000, remaining);
        persistWorkoutDraftLocally(workoutView.session?.id);
        renderWorkoutDetail({ preserveScroll: true });
    }

    function updateWorkoutRestTimer() {
        if (!workoutView.rest) return;
        const remaining = workoutView.rest.endsAt - Date.now();
        if (remaining <= 0) {
            workoutView.rest = null;
            persistWorkoutDraftLocally(workoutView.session?.id);
            navigator.vibrate?.(150);
            renderWorkoutDetail({ preserveScroll: true });
            return;
        }
        const timer = byId("workoutRestTime");
        if (timer) timer.textContent = formatRestRemaining(remaining / 1000);
        document.querySelectorAll("[data-workout-rest-compact]").forEach((element) => {
            element.textContent = formatRestRemaining(remaining / 1000);
        });
    }

    function performedSetsFromView(exerciseId) {
        if (workoutView.setEntryMode === 'review') captureWorkoutSetDraft(exerciseId);
        return asArray(workoutView.setDrafts.get(String(exerciseId))).flatMap((item, index) => {
            const loadValue = item.load_kg;
            const repetitionsValue = item.repetitions;
            if (!loadValue && !repetitionsValue) return [];
            const repetitions = Number(repetitionsValue);
            const load = loadValue === "" ? null : Number(String(loadValue).replace(",", "."));
            if (!Number.isInteger(repetitions) || repetitions < 1 || repetitions > 1000) {
                throw Object.assign(new Error("Informe repetições válidas para cada série preenchida."), {field: "repetitions", index});
            }
            if (load !== null && (!Number.isFinite(load) || load < 0 || load > 100000)) {
                throw Object.assign(new Error("Informe uma carga válida para cada série preenchida."), {field: "load", index});
            }
            return [{ repetitions, load_kg: load, is_warmup: Boolean(item.is_warmup) }];
        });
    }

    function workoutPlannedSetCount(exercise) {
        return Math.min(20, Math.max(1, Number(displayedExercise(exercise).exercise.sets) || 1));
    }

    function workoutExecutionProgress(exercises, completedIds) {
        let completedSets = 0;
        let totalSets = 0;
        exercises.forEach((exercise) => {
            const id = String(exercise.id);
            const drafts = asArray(workoutView.setDrafts.get(id));
            const planned = Math.max(workoutPlannedSetCount(exercise), drafts.length);
            totalSets += planned;
            completedSets += completedIds.has(id)
                ? (workoutView.completedSetCounts.get(id) ?? planned)
                : drafts.filter((set) => set.completed).length;
        });
        const completedExercises = exercises.filter((exercise) => completedIds.has(String(exercise.id))).length;
        const skippedExercises = exercises.filter((exercise) => workoutView.skippedExerciseIds.has(String(exercise.id))).length;
        return { completedSets, totalSets, completedExercises, skippedExercises };
    }

    function firstPendingWorkoutExercise(exercises, completedIds) {
        return exercises.find((exercise) => (
            !completedIds.has(String(exercise.id))
            && !workoutView.skippedExerciseIds.has(String(exercise.id))
        ));
    }

    function workoutFinishState(exercises, completedIds = completedWorkoutExerciseIds()) {
        const completedExercises = exercises.filter((exercise) => completedIds.has(String(exercise.id)));
        const skippedExercises = exercises.filter((exercise) => workoutView.skippedExerciseIds.has(String(exercise.id)));
        const unresolvedExercises = exercises.filter((exercise) => (
            !completedIds.has(String(exercise.id))
            && !workoutView.skippedExerciseIds.has(String(exercise.id))
        ));
        return {
            completedExercises,
            skippedExercises,
            unresolvedExercises,
            completionState: exercises.length && completedExercises.length === exercises.length ? "complete" : "partial",
        };
    }

    function workoutFinishPreviewMarkup(finishState, progressState) {
        const partial = finishState.completionState === "partial";
        return `<div class="workout-finish-preview__content"><span><i class="fas ${partial ? "fa-flag" : "fa-check"}" aria-hidden="true"></i></span><small>${partial ? "Treino parcial" : "Treino completo"}</small><strong>Revisar e finalizar</strong><p>${finishState.completedExercises.length} concluído(s) · ${progressState.completedSets} série(s)</p></div>`;
    }

    function workoutCompletionSnapshot(day, exercises, progressState, finishState) {
        const completedIds = completedWorkoutExerciseIds();
        return {
            id: workoutView.session?.id,
            session_id: workoutView.session?.id,
            workout_name: day?.title || workoutView.plan?.title || "Treino",
            plan_name: workoutView.plan?.title || "Treino",
            started_at: workoutView.session?.started_at,
            completed_at: new Date().toISOString(),
            duration_seconds: workoutElapsedSeconds(workoutView.session?.started_at),
            exercises_performed: finishState.completedExercises.length,
            total_exercises: exercises.length,
            sets_performed: progressState.completedSets,
            volume_total_kg: null,
            completion_state: finishState.completionState,
            personal_records: [],
            exercises: exercises.filter((exercise) => completedIds.has(String(exercise.id))).map((exercise) => {
                const shown = displayedExercise(exercise).exercise;
                return {
                    exercise_id: exercise.id,
                    name: shown.name,
                    catalog_key: shown.catalog_key,
                    sets_performed: workoutView.completedSetCounts.get(String(exercise.id)) || 0,
                    sets: [],
                    best_set: null,
                    personal_records: [],
                };
            }),
        };
    }

    function renderActiveWorkout(day) {
        const exercises = asArray(day.exercises);
        const completedIds = completedWorkoutExerciseIds();
        const progressState = workoutExecutionProgress(exercises, completedIds);
        const resolvedCount = progressState.completedExercises + progressState.skippedExercises;
        const readyToFinish = Boolean(exercises.length) && resolvedCount === exercises.length;
        const defaultExercise = firstPendingWorkoutExercise(exercises, completedIds);
        const selectedExercise = exercises.find((item) => String(item.id) === String(workoutView.activeExerciseId));
        const currentOriginal = selectedExercise || (readyToFinish ? exercises[exercises.length - 1] : defaultExercise || exercises[0]);
        if (currentOriginal && String(workoutView.activeExerciseId || "") !== String(currentOriginal.id)) {
            workoutView.activeExerciseId = String(currentOriginal.id);
        }
        const showFinishCard = workoutView.playerScreen === "finish";
        const finishState = workoutFinishState(exercises, completedIds);
        const exerciseProgress = exercises.length ? Math.round((resolvedCount / exercises.length) * 100) : 0;
        const timer = formatWorkoutElapsed(workoutElapsedSeconds(workoutView.session?.started_at));
        const toolbar = `
            <header class="active-workout-toolbar">
                <div class="active-workout-status"><span><i class="fas fa-circle" aria-hidden="true"></i> Sessão em andamento</span><strong>${esc(day.title)}</strong></div>
                <div class="active-workout-timer" aria-label="Duração atual do treino"><small><i class="fas fa-stopwatch" aria-hidden="true"></i> Duração</small><time data-workout-elapsed data-workout-started-at="${esc(workoutView.session?.started_at || "")}">${timer}</time></div>
                <div class="active-workout-progress" aria-label="${progressState.completedExercises} de ${exercises.length} exercícios e ${progressState.completedSets} de ${progressState.totalSets} séries realizadas"><span><b>${progressState.completedExercises}</b> de ${exercises.length} exercícios</span><small>${progressState.completedSets} de ${progressState.totalSets} séries</small><div aria-hidden="true"><i style="width:${exerciseProgress}%"></i></div></div>
                <button type="button" class="active-workout-exit" data-workout-action="close-active-workout"><i class="fas fa-chevron-down" aria-hidden="true"></i> Sair</button>
            </header>`;
        const queue = exercises.map((item, index) => {
            const id = String(item.id);
            const done = completedIds.has(id);
            const skipped = workoutView.skippedExerciseIds.has(id);
            const active = currentOriginal && id === String(currentOriginal.id);
            const shown = displayedExercise(item).exercise;
            return `<li class="${done ? "is-complete" : skipped ? "is-skipped" : active ? "is-current" : ""}"><button type="button" data-workout-action="select-session-exercise" data-exercise-id="${esc(item.id)}"${active ? ' aria-current="step"' : ""}><span>${done ? '<i class="fas fa-check" aria-hidden="true"></i>' : skipped ? '<i class="fas fa-forward" aria-hidden="true"></i>' : index + 1}</span><strong>${esc(shown.name)}</strong><small>${done ? "Concluído" : skipped ? "Pulado" : active ? "Agora" : "Próximo"}</small></button></li>`;
        }).join("");
        if (showFinishCard || !currentOriginal) {
            const previousExercise = currentOriginal ? displayedExercise(currentOriginal).exercise : null;
            const partial = finishState.completionState === "partial";
            const pendingCopy = finishState.unresolvedExercises.length
                ? `${finishState.unresolvedExercises.length} ainda não concluído(s)`
                : finishState.skippedExercises.length
                    ? `${finishState.skippedExercises.length} pulado(s)`
                    : "Todos os exercícios concluídos";
            return `
                <section class="active-workout-shell active-workout-shell--immersive">
                    <article class="current-exercise-stage current-exercise-stage--player workout-finish-card" data-workout-player-card data-workout-card-kind="finish">
                        ${previousExercise ? `<figure class="current-exercise-preview current-exercise-preview--previous" aria-hidden="true">${exerciseImageMarkup(previousExercise, true)}</figure>` : ""}
                        ${toolbar}
                        <div class="current-exercise-content--overlay workout-finish-card__surface">
                            <span class="workout-finish-card__icon"><i class="fas ${partial ? "fa-flag" : "fa-trophy"}" aria-hidden="true"></i></span>
                            <div class="workout-finish-card__heading"><small>${partial ? "Treino parcial" : "Treino completo"}</small><h3 id="workoutFinishCardTitle" tabindex="-1">Revise e finalize sua sessão</h3><p>${esc(pendingCopy)}. Cargas e repetições são opcionais.</p></div>
                            <div class="workout-finish-card__metrics" aria-label="${finishState.completedExercises.length} exercícios concluídos, ${finishState.skippedExercises.length} pulados, ${finishState.unresolvedExercises.length} não concluídos e ${progressState.completedSets} séries registradas">
                                <span><strong>${finishState.completedExercises.length}</strong><small>Concluídos</small></span>
                                <span><strong>${finishState.skippedExercises.length}</strong><small>Pulados</small></span>
                                <span><strong>${finishState.unresolvedExercises.length}</strong><small>Pendentes</small></span>
                                <span><strong>${progressState.completedSets}</strong><small>Séries</small></span>
                            </div>
                            <div class="workout-finish-card__actions">
                                <button type="button" class="finish-workout-button active-workout-finish" data-workout-action="confirm-finish-session"${workoutView.pendingAction === "finish" ? " disabled" : ""}>${workoutView.pendingAction === "finish" ? '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Finalizando...' : '<i class="fas fa-flag-checkered" aria-hidden="true"></i> Confirmar finalização'}</button>
                                <button type="button" class="workout-finish-back" data-workout-action="return-from-finish"><i class="fas fa-arrow-left" aria-hidden="true"></i> Voltar ao último exercício</button>
                            </div>
                            <details class="active-workout-queue"><summary><span>Revisar sequência</span><strong>${resolvedCount}/${exercises.length}</strong></summary><ol>${queue}</ol></details>
                        </div>
                        ${workoutPlayerFeedbackMarkup()}
                    </article>
                </section>`;
        }

        const currentId = String(currentOriginal.id);
        const { exercise, override } = displayedExercise(currentOriginal);
        const panel = workoutView.replacementPanels.get(currentId);
        const currentIndex = exercises.indexOf(currentOriginal);
        const previousOriginal = exercises[currentIndex - 1];
        const nextOriginal = exercises[currentIndex + 1];
        const previousExercise = previousOriginal ? displayedExercise(previousOriginal).exercise : null;
        const nextExercise = nextOriginal ? displayedExercise(nextOriginal).exercise : null;
        const exerciseDone = completedIds.has(currentId);
        const exerciseSkipped = workoutView.skippedExerciseIds.has(currentId);
        const details = [
            exercise.primary_muscle && `<span><i class="fas fa-bullseye" aria-hidden="true"></i>${esc(exercise.primary_muscle)}</span>`,
            exercise.equipment && `<span><i class="fas fa-dumbbell" aria-hidden="true"></i>${esc(equipmentLabel(exercise.equipment))}</span>`,
            exercise.rest_seconds && `<span><i class="fas fa-hourglass-half" aria-hidden="true"></i>${esc(exercise.rest_seconds)}s descanso</span>`
        ].filter(Boolean).join("");
        const plannedSets = workoutPlannedSetCount(currentOriginal);
        const setDraft = asArray(workoutView.setDrafts.get(currentId));
        const setCount = Math.max(plannedSets, setDraft.length);
        const currentSetIndex = firstPendingWorkoutSetIndex(currentId, setCount);
        const setRows = Array.from(
            { length: setCount },
            (_, index) => workoutSetRowMarkup(index + 1, setDraft[index], index === currentSetIndex)
        ).join("");
        const nextStep = currentSetIndex == null
            ? "Próximo exercício"
            : `Próxima: ${exercise.name} · série ${currentSetIndex + 1} de ${setCount}`;
        const nextAction = nextOriginal ? "next-session-exercise" : "open-finish-card";
        const nextLabel = nextOriginal ? "Próximo exercício" : "Revisar e finalizar treino";
        const navigation = `<nav class="current-exercise-navigation" aria-label="Navegação entre exercícios"><button type="button" data-workout-action="previous-session-exercise" aria-label="Exercício anterior"${currentIndex <= 0 ? " disabled" : ""}><i class="fas fa-arrow-left" aria-hidden="true"></i> Anterior</button><span>${currentIndex + 1} de ${exercises.length}</span><button type="button" data-workout-action="${nextAction}" aria-label="${nextLabel}">${nextOriginal ? "Próximo" : "Revisar"} <i class="fas fa-arrow-right" aria-hidden="true"></i></button></nav>`;
        const sheetExpanded = workoutView.setEntryMode === 'review';
        const currentSeriesLabel = currentSetIndex == null ? `${setCount} de ${setCount}` : `${currentSetIndex + 1} de ${setCount}`;
        const plannedLoad = exercise.weight || "Conforme orientação";
        const completeSetLabel = currentSetIndex == null
            ? '<i class="fas fa-check-double" aria-hidden="true"></i> Séries concluídas'
            : `<i class="fas fa-check" aria-hidden="true"></i> Concluir série ${currentSetIndex + 1}`;
        const completeExerciseLabel = workoutView.pendingAction === `complete-${currentOriginal.id}`
            ? '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Salvando...'
            : '<i class="fas fa-check" aria-hidden="true"></i> Salvar e concluir';
        const stateContent = exerciseDone
            ? `<div class="current-exercise-resolved is-complete"><i class="fas fa-circle-check" aria-hidden="true"></i><div><strong>Exercício concluído</strong><p>As séries registradas já foram salvas.</p></div></div>`
            : exerciseSkipped
                ? `<div class="current-exercise-resolved is-skipped"><i class="fas fa-forward" aria-hidden="true"></i><div><strong>Exercício pulado</strong><p>Ele não será contado como concluído.</p></div><button type="button" data-workout-action="resume-exercise" data-exercise-id="${esc(currentOriginal.id)}">Retomar exercício</button></div>`
                : `<section class="workout-set-entry" aria-labelledby="workoutSetEntryTitle">
                    <div class="workout-set-entry__heading"><div><small>Registro opcional</small><h4 id="workoutSetEntryTitle">Carga e repetições por série</h4></div><button type="button" data-workout-action="add-set"><i class="fas fa-plus" aria-hidden="true"></i> Adicionar série</button></div>
                    <div class="workout-set-entry__rows">${setRows}</div>
                    <button type="button" class="complete-current-set-button" data-workout-action="complete-current-set" data-exercise-id="${esc(currentOriginal.id)}" data-workout-set-index="${currentSetIndex == null ? "" : esc(currentSetIndex)}"${currentSetIndex == null || workoutView.pendingAction ? " disabled" : ""}>${completeSetLabel}</button>
                    <p>O registro é opcional. Você também pode concluir o exercício sem preencher todas as séries.</p>
                </section>`;
        return `
            <section class="active-workout-shell active-workout-shell--immersive">
                <article class="current-exercise-stage current-exercise-stage--player${exerciseDone ? " is-completed-view" : exerciseSkipped ? " is-skipped-view" : ""}${workoutView.setEntryMode === 'quick' ? " has-quick-set" : ""}" data-workout-player-card data-workout-card-kind="exercise" data-workout-exercise-card data-exercise-id="${esc(currentOriginal.id)}">
                    <figure class="current-exercise-media">${exerciseImageMarkup(exercise, true)}</figure>
                    ${previousExercise ? '<figure class="current-exercise-preview current-exercise-preview--previous" aria-hidden="true"></figure>' : ""}
                    ${nextExercise ? '<figure class="current-exercise-preview current-exercise-preview--next" aria-hidden="true"></figure>' : ""}
                    ${!nextExercise ? `<div class="current-exercise-preview current-exercise-preview--next workout-finish-preview" aria-hidden="true">${workoutFinishPreviewMarkup(finishState, progressState)}</div>` : ""}
                    ${toolbar}
                    ${navigation}
                    <div class="current-exercise-content current-exercise-content--overlay">
                        <span class="current-exercise-kicker">Exercício ${currentIndex + 1} de ${exercises.length}</span>
                        ${override ? '<span class="session-override-badge"><i class="fas fa-shuffle" aria-hidden="true"></i> Substituição desta sessão</span>' : ""}
                        <div class="current-exercise-title-row"><h3 id="currentExerciseTitle" tabindex="-1">${esc(exercise.name)}</h3></div>
                        <div class="workout-player-tools">
                            <div class="workout-player-prescription">
                                <span><small>Carga</small><strong>${esc(plannedLoad)}</strong></span>
                                <span><small>Reps</small><strong>${esc(exercise.reps ?? "—")}</strong></span>
                                <span><small>Série</small><strong>${esc(currentSeriesLabel)}</strong></span>
                            </div>
                            ${!exerciseDone && !exerciseSkipped ? `<button type="button" class="replace-current-exercise-button replace-current-exercise-button--visible" data-workout-action="replacement-options" data-exercise-id="${esc(currentOriginal.id)}" aria-expanded="${Boolean(panel)}" aria-controls="replacement-panel-${esc(currentOriginal.id)}"><span aria-hidden="true">⇄</span> Trocar exercício</button>` : ""}
                        </div>
                        <div class="workout-player-progress"><span>${progressState.completedExercises} de ${exercises.length} exercícios</span><i aria-hidden="true"><b style="width:${exerciseProgress}%"></b></i></div>
                    </div>
                    <div class="workout-player-rest"${workoutView.rest ? "" : " hidden"}><span><i class="fas fa-hourglass-half" aria-hidden="true"></i> Descanso</span><strong data-workout-rest-compact>${workoutView.rest ? formatRestRemaining((workoutView.rest.endsAt - Date.now()) / 1000) : ""}</strong></div>
                    ${!exerciseDone && !exerciseSkipped ? renderWorkoutQuickSetEntry(currentOriginal, exercise, setCount) : ""}
                    <section class="workout-session-sheet${sheetExpanded ? " is-expanded" : " is-collapsed"}" data-workout-sheet aria-label="Controles da sessão">
                        <button type="button" class="workout-sheet-handle" data-workout-action="toggle-session-sheet" aria-expanded="${workoutView.setEntryMode !== 'closed'}" aria-controls="workoutSessionSheetContent"><span aria-hidden="true"></span><b>${sheetExpanded ? "Recolher revisão" : "Arraste para registrar série"}</b><i class="fas fa-chevron-${sheetExpanded ? "down" : "up"}" aria-hidden="true"></i></button>
                        <div id="workoutSessionSheetContent" class="workout-session-sheet__scroll"${sheetExpanded ? "" : " inert"}>
                            ${stateContent}
                            ${renderWorkoutRest(nextStep)}
                            ${details ? `<div class="current-exercise-meta">${details}</div>` : ""}
                            ${exercise.effort_guidance ? `<p class="current-exercise-note"><i class="fas fa-gauge-high" aria-hidden="true"></i><span><strong>Esforço</strong>${esc(exercise.effort_guidance)}</span></p>` : ""}
                            ${exercise.notes ? `<p class="current-exercise-instruction"><i class="fas fa-circle-info" aria-hidden="true"></i>${esc(exercise.notes)}</p>` : ""}
                            ${!exerciseDone && !exerciseSkipped ? `<details class="current-exercise-secondary"><summary>Mais ações</summary><div><button type="button" class="skip-current-exercise-button" data-workout-action="skip-exercise" data-exercise-id="${esc(currentOriginal.id)}"><i class="fas fa-forward" aria-hidden="true"></i> Pular exercício</button>${override ? `<button type="button" class="restore-exercise-button" data-workout-action="restore-exercise" data-exercise-id="${esc(currentOriginal.id)}"${workoutView.pendingAction === `restore-${currentOriginal.id}` ? " disabled" : ""}><i class="fas fa-rotate-left" aria-hidden="true"></i> Restaurar original</button>` : ""}</div></details>` : ""}
                            <details class="active-workout-queue"><summary><span>Sequência do treino</span><strong>${progressState.completedExercises} concluídos${progressState.skippedExercises ? ` · ${progressState.skippedExercises} pulado(s)` : ""}</strong></summary><ol>${queue}</ol></details>
                            <div class="workout-sheet-session-actions"><button type="button" class="finish-workout-link" data-workout-action="open-finish-card"><i class="fas fa-stop-circle" aria-hidden="true"></i> Revisar e finalizar treino</button></div>
                            <div class="workout-sheet-danger"><span>Encerrar sem salvar o treino</span><button type="button" class="cancel-workout-button" data-workout-action="cancel-session"><i class="fas fa-trash-can" aria-hidden="true"></i> Cancelar e apagar sessão</button></div>
                        </div>
                        ${!exerciseDone && !exerciseSkipped ? `<div class="workout-sheet-save-action"${sheetExpanded ? "" : " inert"}><button type="button" class="complete-exercise-button workout-exercise-primary" data-workout-action="complete-exercise" data-exercise-id="${esc(currentOriginal.id)}"${workoutView.pendingAction ? " disabled" : ""}>${completeExerciseLabel}</button></div>` : ""}
                    </section>
                    ${workoutPlayerFeedbackMarkup()}
                </article>
                ${renderReplacementPanel(currentOriginal, panel)}
            </section>`;
    }

    function renderCompletedWorkoutSummary() {
        const summary = workoutView.completedSummary;
        if (!summary) return "";
        const volume = summary.volume_total_kg == null
            ? ""
            : `<article><i class="fas fa-weight-hanging" aria-hidden="true"></i><strong>${esc(Number(summary.volume_total_kg).toLocaleString("pt-BR", { maximumFractionDigits: 2 }))} kg</strong><span>volume total</span></article>`;
        const exerciseList = asArray(summary.exercises).map((exercise) => {
            const bestSetText = formatWorkoutBestSet(exercise.best_set);
            const hasRecord = asArray(exercise.personal_records).length > 0;
            return `<li class="${hasRecord ? "has-personal-record" : ""}"><div><strong>${esc(exercise.name)}${hasRecord ? ' <em><i class="fas fa-trophy" aria-hidden="true"></i> Novo PR</em>' : ""}</strong><span>${esc(exercise.sets_performed)} ${exercise.sets_performed === 1 ? "série realizada" : "séries realizadas"}</span><span class="completed-workout-exercise-links">${exercise.catalog_key ? `<button type="button" data-workout-action="view-exercise-progress" data-exercise-key="${esc(exercise.catalog_key)}">Ver progresso</button><button type="button" data-workout-action="set-exercise-goal" data-exercise-key="${esc(exercise.catalog_key)}" data-exercise-name="${esc(exercise.name)}">Definir meta</button>` : ""}</span>${hasRecord ? (window.renderProgressRecord?.(exercise.personal_records[0]) || "") : ""}</div><b>${esc(bestSetText)}</b></li>`;
        }).join("");
        const skippedList = asArray(summary.skipped_exercises).length
            ? `<section class="completed-workout-skipped"><h4>Exercícios pulados</h4><ul>${asArray(summary.skipped_exercises).map((exercise) => `<li><i class="fas fa-forward" aria-hidden="true"></i><span>${esc(exercise.name)}</span></li>`).join("")}</ul></section>`
            : "";
        const personalRecords = asArray(summary.personal_records);
        const recordsBlock = personalRecords.length ? `<section class="workout-result-highlight"><div><i class="fas fa-trophy" aria-hidden="true"></i><span><small>Novo progresso</small><strong>${esc(personalRecords.length)} ${personalRecords.length === 1 ? "novo recorde" : "novos recordes"}</strong></span></div>${personalRecords.map((record) => `<p><b>${esc(record.exercise_name)}</b><span>${esc(formatWorkoutBestSet(record))}</span></p>`).join("")}</section>` : "";
        const weekly = summary.weekly_progress?.current;
        const weeklyBlock = weekly?.target ? `<section class="workout-weekly-result"><div><span>Meta semanal</span><strong>${esc(weekly.completed)} / ${esc(weekly.target)} treinos</strong></div><div class="workout-weekly-result__bar" aria-label="${esc(weekly.completed)} de ${esc(weekly.target)} treinos"><i style="width:${Math.min(100, (weekly.completed / weekly.target) * 100)}%"></i></div><p><i class="fas fa-fire" aria-hidden="true"></i> ${esc(weekly.streak)} ${weekly.streak === 1 ? "semana consecutiva" : "semanas consecutivas"}</p></section>` : "";
        const achievements = asArray(summary.achievements_unlocked);
        const achievementsBlock = achievements.length ? `<section class="workout-achievements-result"><span>Achievement desbloqueado</span>${achievements.slice(0, 2).map((item) => `<div><i class="fas fa-award" aria-hidden="true"></i><p><strong>${esc(item.title)}</strong><small>${esc(item.description)}</small></p></div>`).join("")}</section>` : "";

        if (workoutView.shareOpen) {
            return renderWorkoutShareEditor(summary);
        }

        return `<section class="completed-workout-summary">
            <header><span><i class="fas ${summary.completion_state === "partial" ? "fa-flag" : "fa-check"}" aria-hidden="true"></i></span><div><small>${summary.completion_state === "partial" ? "Treino finalizado parcialmente" : "Treino concluído"}</small><h3>${esc(summary.workout_name)}</h3><p>${summary.exercises_performed === summary.total_exercises ? "Sessão completa" : `${esc(summary.exercises_performed)} de ${esc(summary.total_exercises)} exercícios concluídos${summary.skipped_count ? ` · ${esc(summary.skipped_count)} pulado(s)` : ""}`}</p></div></header>
            ${summary.sync_pending ? '<p class="completed-workout-sync" role="status"><i class="fas fa-cloud-arrow-up" aria-hidden="true"></i> Finalização salva neste dispositivo. O histórico será sincronizado quando a conexão voltar.</p>' : ""}
            <div class="completed-workout-metrics">
                <article><i class="fas fa-stopwatch" aria-hidden="true"></i><strong>${esc(formatWorkoutElapsed(summary.duration_seconds))}</strong><span>duração</span></article>
                <article><i class="fas fa-dumbbell" aria-hidden="true"></i><strong>${esc(summary.exercises_performed)}</strong><span>exercícios</span></article>
                <article><i class="fas fa-layer-group" aria-hidden="true"></i><strong>${esc(summary.sets_performed)}</strong><span>séries</span></article>
                ${volume}
            </div>
            ${recordsBlock}${weeklyBlock}${achievementsBlock}
            <button type="button" class="workout-share-button" data-workout-action="open-workout-share"><i class="fas fa-share-nodes" aria-hidden="true"></i><span><strong>${workoutView.summaryOrigin === "activities" ? "Compartilhar atividade" : "Compartilhar treino"}</strong><small>Criar card com foto e exercícios</small></span><i class="fas fa-arrow-right" aria-hidden="true"></i></button>
            ${exerciseList ? `<section class="completed-workout-exercises"><h4>Exercícios realizados</h4><ul>${exerciseList}</ul></section>` : '<p class="completed-workout-empty">Nenhum exercício foi marcado como concluído.</p>'}
            ${skippedList}
            ${workoutView.summaryOrigin === "activities" ? '<button type="button" class="workout-delete-button" data-workout-action="delete-activity"><i class="fas fa-trash" aria-hidden="true"></i> Excluir atividade</button>' : ""}
            <button type="button" class="completed-workout-close" data-workout-action="close-summary">${workoutView.summaryOrigin === "activities" ? "Voltar às atividades" : "Voltar ao plano"}</button>
        </section>`;
    }

    function formatWorkoutBestSet(bestSet) {
        if (!bestSet) return "Sem série registrada";
        const load = bestSet.load_kg == null
            ? "Peso corporal"
            : `${Number(bestSet.load_kg).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} kg`;
        return `${load} × ${bestSet.repetitions}`;
    }

    function formatWorkoutShareDuration(seconds) {
        const totalMinutes = Math.max(1, Math.round(Number(seconds || 0) / 60));
        const hours = Math.floor(totalMinutes / 60);
        const minutes = totalMinutes % 60;
        if (!hours) return `${totalMinutes} min`;
        return minutes ? `${hours}h ${minutes}min` : `${hours}h`;
    }

    function createWorkoutShareDraft(summary) {
        return {
            sessionId: summary.session_id,
            photoDataUrl: null,
            selectedExerciseIds: new Set(asArray(summary.exercises).map((exercise) => String(exercise.exercise_id))),
            mode: "photo",
            photoScale: 1.0,
            photoOffsetX: 0,
            photoOffsetY: 0,
            infoPreset: "full",
        };
    }

    function workoutShareDraft(summary) {
        if (!workoutView.shareDraft || String(workoutView.shareDraft.sessionId) !== String(summary.session_id)) {
            workoutView.shareDraft = createWorkoutShareDraft(summary);
        }
        return workoutView.shareDraft;
    }

    function workoutShareInfoModel(summary, selectedExercises, draft) {
        const preset = ["full", "compact", "minimal"].includes(draft.infoPreset) ? draft.infoPreset : "full";
        const durationText = summary.duration_seconds ? formatWorkoutShareDuration(summary.duration_seconds) : "";
        const exerciseCount = selectedExercises.length || summary.exercises_performed || 0;
        const subtitleParts = [durationText, exerciseCount ? `${exerciseCount} exercício${exerciseCount > 1 ? "s" : ""}` : ""].filter(Boolean);
        const visibleExercises = preset === "compact" ? selectedExercises.slice(0, 2) : selectedExercises.slice(0, 3);
        const extraCount = preset === "full" ? Math.max(0, selectedExercises.length - 3) : 0;
        return {
            preset,
            title: summary.workout_name || "Treino",
            subtitle: subtitleParts.join(" · "),
            durationText,
            exerciseCount,
            visibleExercises,
            extraCount,
        };
    }

    function renderWorkoutShareEditor(summary) {
        const draft = workoutShareDraft(summary);
        const exercises = asArray(summary.exercises);
        const selectedExercises = exercises.filter((exercise) => draft.selectedExerciseIds.has(String(exercise.exercise_id)));
        const isDark = draft.mode === "dark";
        const infoModel = workoutShareInfoModel(summary, selectedExercises, draft);
        const exerciseControls = exercises.map((exercise) => {
            const selected = draft.selectedExerciseIds.has(String(exercise.exercise_id));
            return `<li class="${selected ? "is-selected" : ""}"><div><strong>${esc(exercise.name)}</strong><span>${esc(formatWorkoutBestSet(exercise.best_set))}</span></div><button type="button" data-workout-action="toggle-share-exercise" data-exercise-id="${esc(exercise.exercise_id)}" aria-pressed="${selected}"><i class="fas ${selected ? "fa-eye-slash" : "fa-eye"}" aria-hidden="true"></i>${selected ? "Não mostrar" : "Mostrar"}</button></li>`;
        }).join("");
        const photoSlider = !isDark ? `
                        <section class="workout-share-option" aria-labelledby="workoutSharePhotoAdjustTitle">
                            <div class="workout-share-option__heading"><span><i class="fas fa-crop-simple" aria-hidden="true"></i></span><div><h4 id="workoutSharePhotoAdjustTitle">Ajustar foto</h4><p>Escala e posição da imagem de fundo.</p></div></div>
                            <div class="workout-share-slider">
                                <label>Escala</label>
                                <input type="range" min="50" max="200" value="${Math.round((draft.photoScale || 1) * 100)}" data-workout-action="set-share-photo-scale">
                                <small>${(draft.photoScale || 1).toFixed(1)}x</small>
                            </div>
                            <div class="workout-share-slider">
                                <label>Horizontal</label>
                                <input type="range" min="-300" max="300" value="${draft.photoOffsetX || 0}" data-workout-action="set-share-photo-offset-x">
                                <small>${draft.photoOffsetX || 0}px</small>
                            </div>
                            <div class="workout-share-slider">
                                <label>Vertical</label>
                                <input type="range" min="-300" max="300" value="${draft.photoOffsetY || 0}" data-workout-action="set-share-photo-offset-y">
                                <small>${draft.photoOffsetY || 0}px</small>
                            </div>
                        </section>` : "";

        const infoPresetToggle = `
            <section class="workout-share-option" aria-labelledby="workoutShareInfoPresetTitle">
                <div class="workout-share-option__heading"><span><i class="fas fa-layer-group" aria-hidden="true"></i></span><div><h4 id="workoutShareInfoPresetTitle">Informações</h4><p>Escolha o estilo do bloco de texto no card.</p></div></div>
                <div class="workout-share-mode-toggle workout-share-mode-toggle--compact">
                    <button type="button" class="${infoModel.preset === "full" ? "is-active" : ""}" data-workout-action="set-share-info-preset" data-info-preset="full">Completo</button>
                    <button type="button" class="${infoModel.preset === "compact" ? "is-active" : ""}" data-workout-action="set-share-info-preset" data-info-preset="compact">Compacto</button>
                    <button type="button" class="${infoModel.preset === "minimal" ? "is-active" : ""}" data-workout-action="set-share-info-preset" data-info-preset="minimal">Minimalista</button>
                </div>
            </section>`;

        return `<section class="workout-share-shell">
            <header class="workout-share-header"><button type="button" data-workout-action="back-to-summary"><i class="fas fa-arrow-left" aria-hidden="true"></i> Voltar</button><span>Workout Share</span><h3 tabindex="-1">Monte seu compartilhamento</h3><p>Escolha o modo, ajuste a foto e as informações do card.</p></header>
            <div class="workout-share-editor">
                <div class="workout-share-options">
                    <section class="workout-share-option" aria-labelledby="workoutShareModeTitle">
                        <div class="workout-share-option__heading"><span><i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i></span><div><h4 id="workoutShareModeTitle">Modo</h4><p>Foto com filtro ou fundo escuro com dados.</p></div></div>
                        <div class="workout-share-mode-toggle">
                            <button type="button" class="${!isDark ? "is-active" : ""}" data-workout-action="set-share-mode" data-share-mode="photo"><i class="fas fa-camera" aria-hidden="true"></i> Foto</button>
                            <button type="button" class="${isDark ? "is-active" : ""}" data-workout-action="set-share-mode" data-share-mode="dark"><i class="fas fa-moon" aria-hidden="true"></i> Fundo preto</button>
                        </div>
                    </section>
                    ${!isDark ? `<section class="workout-share-option" aria-labelledby="workoutSharePhotoTitle">
                        <div class="workout-share-option__heading"><span><i class="fas fa-image" aria-hidden="true"></i></span><div><h4 id="workoutSharePhotoTitle">Foto</h4><p>Use uma imagem como fundo ou continue sem foto.</p></div></div>
                        <div class="workout-share-photo-actions">
                            <button type="button" class="workout-share-photo-select" data-workout-action="choose-share-photo"><i class="fas fa-camera" aria-hidden="true"></i>${draft.photoDataUrl ? "Trocar foto" : "Selecionar foto"}</button>
                            <input id="workoutSharePhotoInput" type="file" accept="image/*" class="hidden">
                            ${draft.photoDataUrl ? '<button type="button" data-workout-action="remove-share-photo"><i class="fas fa-trash" aria-hidden="true"></i> Remover</button>' : ""}
                        </div>
                    </section>` : ""}
                    ${photoSlider}
                    ${infoPresetToggle}
                    <section class="workout-share-option" aria-labelledby="workoutShareExercisesTitle">
                        <div class="workout-share-option__heading"><span><i class="fas fa-list-check" aria-hidden="true"></i></span><div><h4 id="workoutShareExercisesTitle">Exercícios</h4><p>Somente os ${esc(exercises.length)} exercícios realizados nesta sessão.</p></div></div>
                        ${exerciseControls ? `<ul class="workout-share-exercise-controls">${exerciseControls}</ul>` : '<p class="workout-share-empty">Nenhum exercício realizado para exibir.</p>'}
                    </section>
                </div>
                <section id="workoutSharePreview" class="workout-share-preview" aria-labelledby="workoutSharePreviewTitle">
                    <div class="workout-share-preview__heading"><div><span>Prévia</span><h4 id="workoutSharePreviewTitle">Seu card</h4></div><small>${esc(selectedExercises.length)} de ${esc(exercises.length)} exercícios</small></div>
                    <canvas data-workout-share-canvas width="1080" height="1920" role="img" aria-label="Prévia do card do treino"></canvas>
                    <p id="workoutShareStatus" class="workout-share-status" role="status">Preparando card…</p>
                </section>
            </div>
            <footer class="workout-share-shell__actions">
                <button type="button" class="completed-workout-close" data-workout-action="back-to-summary"><i class="fas fa-arrow-left" aria-hidden="true"></i> Voltar</button>
                <button type="button" class="btn-secondary" data-workout-action="share-workout-card" ${selectedExercises.length ? "" : "disabled"}><i class="fas fa-share-nodes" aria-hidden="true"></i> Compartilhar card</button>
            </footer>
        </section>`;
    }

    function syncWorkoutSharePreview() {
        const canvas = byId("viewWorkoutPlanDetails")?.querySelector("[data-workout-share-canvas]");
        if (!canvas || !workoutView.completedSummary || !workoutView.shareDraft) return;
        window.WorkoutShare?.updatePreview(canvas, workoutView.completedSummary, workoutView.shareDraft, ({state, message}) => {
            if (!canvas.isConnected) return;
            const button = byId("viewWorkoutPlanDetails").querySelector('[data-workout-action="share-workout-card"]');
            const status = byId("workoutShareStatus");
            if (button) { button.disabled = state !== "ready" || !workoutView.shareDraft.selectedExerciseIds.size; button.setAttribute("aria-busy", String(["preparing","sharing"].includes(state))); }
            if (status) { status.textContent = message; status.setAttribute("role", state === "error" ? "alert" : "status"); }
        });
    }

    async function shareWorkoutCard(summary) {
        try {
            const result = await window.WorkoutShare.sharePrepared(summary, workoutView.shareDraft);
            if (result.status === "download-started") showToast("Download solicitado. Confira os downloads do navegador.", "info");
        } catch (error) {
            if (byId("workoutShareStatus")) byId("workoutShareStatus").textContent = error.message;
        }
    }

    function contextualWorkoutDay(plan) {
        if (!plan?.is_current || String(workoutTodayState?.current_plan_id || "") !== String(plan.id || "")) return null;
        return ["active", "scheduled"].includes(workoutTodayState?.state)
            ? workoutTodayState.current_day
            : workoutTodayState?.next_day;
    }

    function setWorkoutPlanEditMode(editing) {
        if (workoutView.session || workoutView.sessionLoading || workoutView.pendingAction) return;
        workoutView.editMode = Boolean(editing);
        workoutView.addExerciseOpen = false;
        workoutView.replacementPanels.clear();
        renderWorkoutDetail({
            focusSelector: editing
                ? "#workoutPlanEditTitle"
                : '[data-workout-action="enter-plan-edit"]'
        });
    }

    function workoutNodeKey(node) {
        if (node.nodeType !== 1) return node.nodeType;
        return `${node.tagName}:${node.id || node.dataset.workoutSetIndex || node.dataset.workoutAction || node.classList[0] || ""}`;
    }

    // Reconcile only the active player so status, timers and polling keep input nodes alive.
    function patchWorkoutNode(current, next) {
        if (!current || !next) return;
        if (current.nodeType !== next.nodeType || workoutNodeKey(current) !== workoutNodeKey(next)) {
            current.replaceWith(next);
            return;
        }
        if (current.nodeType !== 1) {
            if (current.nodeValue !== next.nodeValue) current.nodeValue = next.nodeValue;
            return;
        }
        for (const attribute of Array.from(current.attributes)) {
            if (attribute.name === "open" || (current.tagName === "INPUT" && ["value", "checked"].includes(attribute.name))) continue;
            if (!next.hasAttribute(attribute.name)) current.removeAttribute(attribute.name);
        }
        for (const attribute of Array.from(next.attributes)) {
            if (attribute.name === "open" || (current.tagName === "INPUT" && ["value", "checked"].includes(attribute.name))) continue;
            if (current.getAttribute(attribute.name) !== attribute.value) current.setAttribute(attribute.name, attribute.value);
        }
        const wanted = Array.from(next.childNodes);
        wanted.forEach((child, index) => {
            let existing = current.childNodes[index];
            if (existing && workoutNodeKey(existing) !== workoutNodeKey(child)) {
                const match = Array.from(current.childNodes).slice(index + 1).find((item) => workoutNodeKey(item) === workoutNodeKey(child));
                if (match) { current.insertBefore(match, existing); existing = match; }
                else { current.insertBefore(child, existing); return; }
            }
            if (!existing) current.appendChild(child);
            else patchWorkoutNode(existing, child);
        });
        while (current.childNodes.length > wanted.length) current.lastChild.remove();
    }

    let workoutViewportFrame = null;
    let workoutViewportFullHeight = 0;
    let workoutViewportWidth = 0;
    function updateWorkoutVisualViewport() {
        if (workoutViewportFrame) return;
        workoutViewportFrame = requestAnimationFrame(() => {
            workoutViewportFrame = null;
            const modal = byId("viewWorkoutPlanModal");
            const viewport = window.visualViewport;
            if (!modal || !viewport) return;
            const active = modal.classList.contains("show") && Boolean(workoutView.session);
            if (!active || Math.abs(viewport.scale - 1) > 0.02) {
                modal.classList.remove("has-workout-keyboard");
                modal.style.removeProperty("--workout-viewport-height");
                modal.style.removeProperty("--workout-viewport-top");
                modal.style.removeProperty("--workout-entry-height");
                return;
            }
            if (Math.abs(window.innerWidth - workoutViewportWidth) > 100) workoutViewportFullHeight = 0;
            workoutViewportWidth = window.innerWidth;
            workoutViewportFullHeight = Math.max(workoutViewportFullHeight, window.innerHeight, viewport.height);
            modal.style.setProperty("--workout-viewport-height", `${Math.round(viewport.height)}px`);
            modal.style.setProperty("--workout-viewport-top", `${Math.round(viewport.offsetTop)}px`);
            const focused = document.activeElement;
            const isInput = focused?.matches?.("input, textarea") && modal.contains(focused);
            const keyboard = Boolean(isInput && workoutViewportFullHeight - viewport.height > 100);
            modal.classList.toggle("has-workout-keyboard", keyboard);
            modal.style.setProperty("--workout-entry-height", `${Math.round(Math.min(viewport.height, workoutViewportFullHeight / 2))}px`);
            if (keyboard) {
                const scroll = focused.closest(".workout-session-sheet__scroll, .workout-quick-set-layer");
                if (!scroll) return;
                const field = focused.getBoundingClientRect();
                const bounds = scroll.getBoundingClientRect();
                if (field.bottom > bounds.bottom - 12) scroll.scrollTop += field.bottom - bounds.bottom + 12;
                else if (field.top < bounds.top + 12) scroll.scrollTop -= bounds.top + 12 - field.top;
            }
        });
    }

    function renderWorkoutDetail(options = {}) {
        const details = byId("viewWorkoutPlanDetails");
        if (!details) return;
        byId("viewWorkoutPlanModal")?.classList.toggle("workout-execution-mode", Boolean(workoutView.session && !workoutView.completedSummary));
        const previousScroll = options.preserveScroll ? details.scrollTop : 0;
        const previousSheetScroll = details.querySelector(".workout-session-sheet__scroll")?.scrollTop || 0;
        const previousPlayerCard = details.querySelector("[data-workout-player-card]");
        const focused = details.contains(document.activeElement) ? document.activeElement : null;
        if (workoutView.completedSummary) {
            const title = byId("viewWorkoutPlanTitle");
            if (title) title.textContent = workoutView.shareOpen ? "Workout Share" : "Resumo do treino";
            details.innerHTML = renderCompletedWorkoutSummary();
            if (workoutView.shareOpen) syncWorkoutSharePreview();
            details.scrollTop = previousScroll;
            if (options.focusSelector) requestAnimationFrame(() => details.querySelector(options.focusSelector)?.focus());
            return;
        }
        const plan = workoutView.plan;
        if (!plan) return;
        if (workoutView.selectedDay >= workoutView.days.length) workoutView.selectedDay = 0;
        const day = selectedWorkoutDay();
        const editing = workoutView.editMode && !workoutView.session;
        const contextualDay = contextualWorkoutDay(plan);
        const summaryMeta = [
            plan.split_type && `<span><i class="fas fa-layer-group" aria-hidden="true"></i><small>Divisão</small><strong>${esc(labelFor(SPLIT_TYPES, plan.split_type, plan.split_type))}</strong></span>`,
            (plan.days_count || plan.days_per_week || workoutView.days.length) && `<span><i class="fas fa-calendar-week" aria-hidden="true"></i><small>Frequência</small><strong>${esc(plan.days_count || plan.days_per_week || workoutView.days.length)} dias/semana</strong></span>`,
            plan.session_duration && `<span><i class="fas fa-clock" aria-hidden="true"></i><small>Duração</small><strong>${esc(plan.session_duration)} min</strong></span>`
        ].filter(Boolean);
        const currentAction = plan.is_current
            ? '<span class="plan-current-pill"><i class="fas fa-star" aria-hidden="true"></i> Plano atual</span>'
            : '<button type="button" class="btn-primary plan-use-current" data-workout-action="use-current-plan"><i class="fas fa-check" aria-hidden="true"></i> Usar este plano</button>';
        const professionalReview = plan.professional_review
            ? `<span class="professional-review-badge"><i class="fas fa-shield-check" aria-hidden="true"></i> Revisado por ${esc(plan.professional_review.professional?.username || "profissional")}</span>`
            : "";
        const editContext = editing ? `
            <section class="workout-plan-edit-context" aria-labelledby="workoutPlanEditTitle">
                <div><span>Modo de edição</span><h3 id="workoutPlanEditTitle" tabindex="-1">Editar estrutura do plano</h3><p>Adicione, remova ou substitua exercícios. As mudanças valem para as próximas sessões.</p></div>
                <div class="workout-plan-edit-context__actions">
                    <button type="button" class="btn-secondary" data-workout-action="request-plan-review"><i class="fas fa-user-check" aria-hidden="true"></i> Solicitar revisão</button>
                    <button type="button" class="workout-plan-edit-back" data-workout-action="exit-plan-edit"><i class="fas fa-arrow-left" aria-hidden="true"></i> Voltar ao plano</button>
                </div>
            </section>` : "";
        const nextWorkout = !editing && contextualDay ? `
            <section class="workout-plan-next" aria-label="Próximo treino">
                <span><i class="fas fa-forward" aria-hidden="true"></i>${workoutTodayState?.state === "active" ? "Em andamento" : workoutTodayState?.state === "scheduled" ? "Treino de hoje" : "Próximo treino"}</span>
                <strong>${esc(contextualDay.title || contextualDay.code || "Treino programado")}</strong>
                ${contextualDay.focus ? `<small>${esc(contextualDay.focus)}</small>` : ""}
            </section>` : "";
        const summary = `
            <section class="workout-plan-overview${editing ? " is-editing" : ""}">
                <div class="workout-plan-overview__icon"><i class="fas fa-dumbbell" aria-hidden="true"></i></div>
                <div class="workout-plan-overview__copy"><span>${plan.is_current ? "Plano atual" : "Plano de treino"}</span><h3>${esc(plan.title || "Plano de treino")}</h3><p>${esc(plan.description || "Uma rotina criada para sua evolução.")}</p>${summaryMeta.length ? `<div class="workout-summary__meta">${summaryMeta.join("")}</div>` : ""}${professionalReview}</div>
                <div class="workout-plan-overview__actions">${currentAction}${editing ? "" : `<button type="button" class="workout-plan-edit-entry" data-workout-action="enter-plan-edit"${workoutView.sessionLoading ? " disabled" : ""}><i class="fas fa-pen" aria-hidden="true"></i> Editar plano</button>`}</div>
            </section>${editContext}${nextWorkout}`;
        if (!day) {
            details.innerHTML = `${summary}<div class="plan-details-empty">Nenhum exercício detalhado para este plano.</div>`;
            return;
        }

        const session = workoutView.session;
        const tabs = session ? "" : `
            <div class="plan-day-tabs plan-day-tabs--workout" role="tablist" aria-label="Dias do plano de treino">
                ${workoutView.days.map((workoutDay, index) => `<button type="button" role="tab" id="workout-day-tab-${index}" aria-controls="workout-day-panel" aria-selected="${index === workoutView.selectedDay}" tabindex="${index === workoutView.selectedDay ? "0" : "-1"}" class="plan-day-tab${index === workoutView.selectedDay ? " active" : ""}" data-workout-action="select-day" data-day-index="${index}"><span>${esc(workoutDay.code || `Dia ${index + 1}`)}</span><strong>${esc(workoutDay.title || `Treino ${index + 1}`)}</strong></button>`).join("")}
            </div>`;
        const sessionControls = editing
            ? '<span class="workout-edit-day-status"><i class="fas fa-pen-ruler" aria-hidden="true"></i> Editando este treino</span>'
            : workoutView.sessionLoading
            ? '<div class="session-loading" role="status"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Verificando sessão...</div>'
            : session
                ? `<div class="active-session-bar"><div><span><i class="fas fa-circle" aria-hidden="true"></i> Treino em andamento</span><small>Iniciado em ${esc(formatDateTime(session.started_at))}</small></div><i class="fas fa-stopwatch" aria-hidden="true"></i></div>`
                : day.id
                    ? `<button type="button" class="start-workout-button" data-workout-action="start-session"${workoutView.pendingAction === "start" ? " disabled" : ""}>${workoutView.pendingAction === "start" ? '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Iniciando...' : '<i class="fas fa-play" aria-hidden="true"></i> Iniciar treino'}</button>`
                    : '<span class="legacy-plan-badge"><i class="fas fa-box-archive" aria-hidden="true"></i> Plano anterior</span>';
        const sessionFooter = session
            ? `<button type="button" class="finish-workout-button finish-workout-button--full" data-workout-action="finish-session"${workoutView.pendingAction === "finish" ? " disabled" : ""}>${workoutView.pendingAction === "finish" ? '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>' : '<i class="fas fa-circle-check" aria-hidden="true"></i>'} Finalizar treino</button>`
            : "";
        const panel = session ? renderActiveWorkout(day) : `
            <section id="workout-day-panel" role="tabpanel" aria-labelledby="workout-day-tab-${workoutView.selectedDay}" class="workout-day-panel${editing ? " is-editing" : ""}">
                <div class="workout-day-header"><div><span>${editing ? "Estrutura do treino" : contextualDay && String(contextualDay.id) === String(day.id) ? workoutTodayState?.state === "scheduled" ? "Treino de hoje" : "Próximo treino" : "Treino selecionado"}</span><h4>${esc(day.title)}</h4>${day.focus ? `<p>${esc(day.focus)}</p>` : ""}</div>${sessionControls}</div>
                ${workoutView.sessionError ? `<p class="session-inline-error" role="alert"><i class="fas fa-circle-exclamation" aria-hidden="true"></i> ${esc(workoutView.sessionError)}</p>` : ""}
                <div class="plan-section-title workout-plan-edit-heading"><span><i class="fas fa-bolt" aria-hidden="true"></i> Sequência do dia</span><div><small>${asArray(day.exercises).length} exercícios</small>${editing ? '<button type="button" data-workout-action="toggle-add-exercise"><i class="fas fa-plus" aria-hidden="true"></i> Adicionar</button>' : ""}</div></div>
                ${renderAddExercisePanel(day)}
                <div class="exercise-list">${asArray(day.exercises).length ? asArray(day.exercises).map(renderExerciseCard).join("") : '<div class="plan-details-empty">Nenhum exercício neste dia.</div>'}</div>
                ${sessionFooter}
            </section>`;
        const title = byId("viewWorkoutPlanTitle");
        if (title) title.textContent = session ? "Treino em andamento" : editing ? "Editar plano" : plan.title || "Plano de Treino";
        const template = document.createElement("template");
        if (session) template.innerHTML = panel.trim();
        const nextPlayerCard = template.content.querySelector?.("[data-workout-player-card]");
        const samePlayerCard = Boolean(session && previousPlayerCard && nextPlayerCard
            && previousPlayerCard.dataset.workoutCardKind === nextPlayerCard.dataset.workoutCardKind
            && String(previousPlayerCard.dataset.exerciseId || "") === String(nextPlayerCard.dataset.exerciseId || ""));
        if (samePlayerCard) {
            patchWorkoutNode(details.querySelector(".active-workout-shell"), template.content.firstElementChild);
        } else {
            details.innerHTML = `${session ? "" : summary}${tabs}${panel}`;
        }
        byId("viewWorkoutPlanModal")?.classList.toggle("workout-execution-mode", Boolean(session));
        details.scrollTop = previousScroll;
        if (samePlayerCard || options.preserveScroll) {
            const scroll = details.querySelector(".workout-session-sheet__scroll");
            if (scroll) scroll.scrollTop = previousSheetScroll;
        }
        if (focused?.isConnected && document.activeElement !== focused) focused.focus({ preventScroll: true });
        updateWorkoutTimer();
        updateWorkoutVisualViewport();
        if (options.focusSelector) requestAnimationFrame(() => details.querySelector(options.focusSelector)?.focus({ preventScroll: true }));
        if (session && !samePlayerCard && workoutView.playerScreen === "exercise") {
            const exercises = asArray(day.exercises);
            const next = exercises[exercises.findIndex((exercise) => String(exercise.id) === String(workoutView.activeExerciseId)) + 1];
            if (next) { const image = new Image(); image.src = exerciseImage(displayedExercise(next).exercise); }
        }
    }

    async function loadActiveWorkoutSession() {
        const day = selectedWorkoutDay();
        workoutView.requestToken += 1;
        const token = workoutView.requestToken;
        workoutView.sessionError = "";
        workoutView.replacementPanels.clear();
        if (!day?.id || !workoutView.plan?.id) {
            workoutView.sessionLoading = false;
            renderWorkoutDetail({ preserveScroll: true });
            return;
        }
        workoutView.sessionLoading = true;
        renderWorkoutDetail({ preserveScroll: true });
        try {
            const result = await apiRequest(`/workout_plans/${apiSegment(workoutView.plan.id)}/days/${apiSegment(day.id)}/sessions/active`);
            if (token !== workoutView.requestToken) return;
            workoutView.session = result.session || null;
            if (workoutView.session) {
                workoutView.editMode = false;
                hydrateWorkoutDrafts(workoutView.session);
                preloadWorkoutAssets(day).catch(() => {});
                activeWorkoutSummary = {
                    session: workoutView.session,
                    plan: { id: workoutView.plan.id, title: workoutView.plan.title },
                    day: { id: day.id, title: day.title }
                };
                renderActiveWorkoutDock();
            } else if (
                String(activeWorkoutSummary?.plan?.id || "") === String(workoutView.plan.id)
                && String(activeWorkoutSummary?.day?.id || "") === String(day.id)
            ) {
                clearActiveWorkoutDock();
            }
        } catch (error) {
            if (token !== workoutView.requestToken) return;
            workoutView.sessionError = error.message;
        } finally {
            if (token === workoutView.requestToken) {
                workoutView.sessionLoading = false;
                renderWorkoutDetail({ preserveScroll: true });
            }
        }
    }

    async function viewWorkoutPlan(id, preferredDayId = null) {
        if (workoutView.pendingAction) return null;
        invalidateWorkoutView();
        const version = workoutView.viewVersion;
        const account = workoutAccount();
        const details = byId("viewWorkoutPlanDetails");
        const cachedPlan = String(workoutView.plan?.id) === String(id) ? workoutView.plan : null;
        const knownSession = String(activeWorkoutSummary?.plan?.id) === String(id) ? activeWorkoutSummary.session : null;
        workoutView.completedSummary = null;
        workoutView.shareOpen = false;
        workoutView.shareDraft = null;
        window.WorkoutShare?.reset();
        resetWorkoutExecutionState();
        workoutView.session = knownSession;
        workoutView.sessionError = "";
        workoutView.plan = cachedPlan;
        if (cachedPlan) {
            workoutView.days = normalizedWorkoutDays(cachedPlan);
            const target = preferredDayId || knownSession?.workout_day_id;
            workoutView.selectedDay = Math.max(0, workoutView.days.findIndex(day => String(day.id) === String(target)));
            if (knownSession) hydrateWorkoutDrafts(knownSession);
            renderWorkoutDetail();
        } else details.innerHTML = '<div class="workout-player-loading" role="status"><div class="home-skeleton" aria-hidden="true"></div>Preparando seu treino…</div>';
        openAppModal(byId("viewWorkoutPlanModal"));
        const activeRead = apiRequest("/workout_sessions/active");
        try {
            const key = `workout:plan:${account}:${id}`;
            const planRead = window.AppReadCache
                ? window.AppReadCache.read(key, ({signal}) => apiRequest(`/workout_plans/${apiSegment(id)}`, {signal}), {ttl: 60000})
                : apiRequest(`/workout_plans/${apiSegment(id)}`);
            const [plan, active] = await Promise.all([planRead, activeRead]);
            if (!workoutContextCurrent(account, version)) return null;
            workoutView.plan = plan;
            workoutView.days = normalizedWorkoutDays(plan);
            const session = String(active.session?.workout_plan_id) === String(id) ? active.session : null;
            const target = session?.workout_day_id || preferredDayId || contextualWorkoutDay(plan)?.id;
            workoutView.selectedDay = Math.max(0, workoutView.days.findIndex(day => String(day.id) === String(target)));
            workoutView.session = session;
            workoutView.sessionLoading = false;
            preloadWorkoutAssets(workoutView.days[workoutView.selectedDay]).catch(() => {});
            if (session) {
                hydrateWorkoutDrafts(session);
            }
            activeWorkoutSummary = active;
            renderActiveWorkoutDock();
            byId("viewWorkoutPlanTitle").textContent = plan.title || "Plano de treino";
            if (session) preloadReplacementOptions(workoutView.days[workoutView.selectedDay], session).catch(() => {});
            renderWorkoutDetail({preserveScroll: true});
            apiRequest(`/workout_plans/${apiSegment(id)}/professional-review`).then(result => {
                if (!workoutContextCurrent(account, version)) return;
                plan.professional_review = result.professional_review;
                if (!workoutView.session) renderWorkoutDetail({preserveScroll: true});
            }).catch(() => {});
            return plan;
        } catch (error) {
            if (workoutContextCurrent(account, version) && error.name !== "AbortError") {
                if (cachedPlan) { workoutView.sessionError = error.message; renderWorkoutDetail({preserveScroll: true}); }
                else details.innerHTML = `<div class="workout-player-loading" role="alert"><p>${esc(error.message)}</p><button type="button" data-workout-action="retry-open-plan" data-plan-id="${esc(id)}">Tentar novamente</button></div>`;
            }
            return null;
        }
    }

    function findSelectedExercise(id) {
        return asArray(selectedWorkoutDay()?.exercises).find((exercise) => String(exercise.id) === String(id));
    }

    function replacementPayload() {
        return { unavailable_equipment: [], available_equipment: [] };
    }

    async function reconciledMutationResult(action, sessionId, options) {
        const active = await apiRequest("/workout_sessions/active");
        const session = active.session;
        const exerciseId = action.split("-").slice(1).join("-");
        if (String(session?.id) === String(sessionId)) {
            if (action.startsWith("complete-") && asArray(session.completed_exercise_ids).map(String).includes(exerciseId)) return {session};
            const override = asArray(session.overrides).find(item => String(item.workout_exercise_id) === exerciseId);
            if (action.startsWith("replace-") && override?.catalog_key === options.body.catalog_key) return {override};
            if (action.startsWith("restore-") && !override) return {};
        } else if (action === "cancel") return {};
        if (action === "finish" && String(session?.id) !== String(sessionId)) {
            const result = await apiRequest(`/activities/${apiSegment(sessionId)}`);
            if (result.activity?.completed_at) return {summary: result.activity};
        }
        return null;
    }

    async function performSessionMutation(action, path, options, apply, retry = false) {
        const sessionId = workoutView.session?.id;
        if (!sessionId) return false;
        const account = workoutAccount(), version = workoutView.viewVersion;
        const lock = beginSessionMutation(action, sessionId);
        if (!lock) return false;
        workoutView.sessionError = "";
        workoutView.mutationErrorStatus = null;
        workoutView.uncertainMutation = null;
        cancelWorkoutDraftTimers();
        renderWorkoutDetail({preserveScroll: true});
        let succeeded = false;
        try {
            const result = await queueSessionWrite(sessionId, async () => {
                if (!workoutContextCurrent(account, version, sessionId)) throw new DOMException("Contexto alterado", "AbortError");
                if (retry) {
                    const confirmed = await reconciledMutationResult(action, sessionId, options);
                    if (confirmed) return confirmed;
                }
                try { return await apiRequest(path, options); }
                catch (error) {
                    if (!["timeout", "offline"].includes(error.code)) throw error;
                    try {
                        const confirmed = await reconciledMutationResult(action, sessionId, options);
                        if (confirmed) return confirmed;
                    } catch (_) { /* Keep the original payload until an explicit retry. */ }
                    error.uncertain = true;
                    throw error;
                }
            });
            if (!workoutContextCurrent(account, version, sessionId)) return false;
            apply(result);
            succeeded = true;
        } catch (error) {
            if (workoutContextCurrent(account, version, sessionId) && error.name !== "AbortError") {
                workoutView.sessionError = error.uncertain
                    ? "A confirmação não chegou. Seus registros foram preservados. Verifique antes de continuar."
                    : error.message;
                workoutView.mutationErrorStatus = error.status;
                if (error.uncertain) workoutView.uncertainMutation = () => performSessionMutation(action, path, options, apply, true);
            }
        } finally {
            endSessionMutation(lock, action, account, version);
            if (workoutContextCurrent(account, version)) {
                renderWorkoutDetail({preserveScroll: !succeeded});
                if (succeeded && action.startsWith("complete-")) requestAnimationFrame(() => (byId("currentExerciseTitle") || byId("workoutFinishCardTitle"))?.focus({preventScroll: true}));
            }
        }
        return succeeded;
    }

    async function startWorkoutSession() {
        const day = selectedWorkoutDay();
        if (!day?.id || !workoutView.plan?.id || workoutView.pendingAction) return;
        const planId = workoutView.plan.id;
        const dayId = day.id;
        const viewVersion = workoutView.viewVersion;
        const account = workoutAccount();
        workoutView.mutationRevision += 1;
        activeDockRequestToken += 1;
        workoutView.pendingAction = "start";
        workoutView.sessionError = "";
        renderWorkoutDetail({ preserveScroll: true });
        try {
            const result = await apiRequest(`/workout_plans/${apiSegment(workoutView.plan.id)}/days/${apiSegment(day.id)}/sessions`, { method: "POST" });
            if (!workoutContextCurrent(account, viewVersion) || String(workoutView.plan?.id) !== String(planId) || String(selectedWorkoutDay()?.id) !== String(dayId)) return;
            workoutView.session = result.session;
            workoutView.editMode = false;
            hydrateWorkoutDrafts(result.session);
            activeWorkoutSummary = {
                session: result.session,
                plan: { id: workoutView.plan.id, title: workoutView.plan.title },
                day: { id: day.id, title: day.title }
            };
            renderActiveWorkoutDock();
            showToast("Treino iniciado. Boa sessão!", "success");
        } catch (error) {
            if (viewVersion === workoutView.viewVersion) workoutView.sessionError = error.message;
        } finally {
            invalidateWorkoutReads();
            if (viewVersion === workoutView.viewVersion && workoutView.pendingAction === "start") {
                workoutView.pendingAction = "";
                renderWorkoutDetail({ preserveScroll: true });
            }
        }
    }

    async function openReplacementOptions(exerciseId) {
        const exercise = findSelectedExercise(exerciseId), session = workoutView.session;
        if (!exercise || !session || workoutView.pendingAction || workoutView.uncertainMutation) return;
        const key = String(exercise.id), account = workoutAccount(), version = workoutView.viewVersion;
        if (workoutView.replacementPanels.has(key)) {
            if (!workoutView.replacementPanels.get(key).error) return;
            closeReplacementPanel(key);
        }
        captureWorkoutSetDraft(exercise.id);
        const payload = replacementPayload(exercise);
        const panel = {mode: "session", loading: true, options: [], payload, returnFocus: workoutView.lastField, controller: new AbortController()};
        workoutView.replacementPanels.set(key, panel);
        renderWorkoutDetail({preserveScroll: true, focusSelector: `#replacement-panel-${key}`});
        try {
            const cacheKey = `workout:options:${account}:${session.id}:${key}:${JSON.stringify(session.overrides)}`;
            const cached = window.AppReadCache?.peek(cacheKey);
            const optionsPath = `/workout_sessions/${apiSegment(session.id)}/exercises/${key}/replacement_options`;
            let result;
            if (cached && Date.now() - cached.at < 60000) result = cached.data;
            else if (navigator.onLine === false) {
                const snapshot = await window.AppOffline?.readSnapshot(`${API_BASE}${optionsPath}`);
                if (!snapshot?.data) throw new Error("Conecte-se para carregar alternativas deste exercício.");
                result = snapshot.data;
            } else {
                result = await apiRequest(optionsPath, {method: "POST", body: payload, timeout: 30000, signal: panel.controller.signal});
            }
            if (!workoutContextCurrent(account, version, session.id) || workoutView.replacementPanels.get(key) !== panel) return;
            if (window.AppReadCache) await window.AppReadCache.read(cacheKey, () => result, {ttl: 60000, force: true});
            Object.assign(panel, {loading: false, options: asArray(result.options), message: result.message || "", error: ""});
        } catch (error) {
            if (panel.controller.signal.aborted || !workoutContextCurrent(account, version, session.id) || workoutView.replacementPanels.get(key) !== panel) return;
            Object.assign(panel, {loading: false, error: error.message});
        }
        if (workoutView.replacementPanels.get(key) === panel) renderWorkoutDetail({preserveScroll: true, focusSelector: `#replacement-panel-${key}`});
    }

    async function applyReplacement(exerciseId, catalogKey) {
        const session = workoutView.session, key = String(exerciseId), panel = workoutView.replacementPanels.get(key);
        if (!session || !panel || !asArray(panel.options).some(item => item.catalog_key === catalogKey) || workoutView.pendingAction || workoutView.uncertainMutation) return;
        panel.applying = catalogKey;
        const returnFocus = panel.returnFocus;
        const success = await performSessionMutation(`replace-${key}`, `/workout_sessions/${apiSegment(session.id)}/exercises/${key}/replace`, {method: "POST", body: {...panel.payload, catalog_key: catalogKey}}, result => {
            workoutView.session.overrides = [...asArray(workoutView.session.overrides).filter(item => String(item.workout_exercise_id) !== key), result.override];
            closeReplacementPanel(key);
            persistWorkoutDraftLocally(session.id);
            if (activeWorkoutSummary?.session?.id === session.id) activeWorkoutSummary.session = workoutView.session;
        });
        if (workoutView.replacementPanels.get(key) === panel) {
            panel.applying = "";
            panel.error = workoutView.sessionError;
            renderWorkoutDetail({preserveScroll: true});
        }
        if (success) {
            const field = returnFocus?.exerciseId === key && document.querySelector(`[data-workout-set-index="${returnFocus.index}"] [data-workout-set-${returnFocus.field}]`);
            (field?.offsetParent ? field : byId("currentExerciseTitle"))?.focus({preventScroll: true});
        } else if (workoutView.mutationErrorStatus === 409 && !panel.refreshed) {
            panel.refreshed = true;
            await openReplacementOptions(key);
        }
    }

    async function restoreExercise(exerciseId) {
        const session = workoutView.session;
        if (!session || workoutView.uncertainMutation) return;
        const key = String(exerciseId);
        await performSessionMutation(`restore-${key}`, `/workout_sessions/${apiSegment(session.id)}/exercises/${key}/replace`, {method: "DELETE"}, () => {
            workoutView.session.overrides = asArray(workoutView.session.overrides).filter(item => String(item.workout_exercise_id) !== key);
            closeReplacementPanel(key);
            persistWorkoutDraftLocally(session.id);
        });
    }

    function applyWorkoutPlanUpdate(result, preferredDayId) {
        invalidateWorkoutReads();
        if (!result?.plan) return;
        workoutView.plan = result.plan;
        workoutView.days = normalizedWorkoutDays(result.plan);
        const selectedIndex = workoutView.days.findIndex((day) => String(day.id) === String(preferredDayId));
        workoutView.selectedDay = selectedIndex >= 0 ? selectedIndex : 0;
        workoutView.replacementPanels.clear();
        workoutView.addExerciseOpen = false;
        renderWorkoutDetail({ preserveScroll: true });
    }

    async function openPermanentReplacementOptions(exerciseId) {
        const exercise = findSelectedExercise(exerciseId);
        if (!exercise || workoutView.session || !workoutView.editMode || !workoutView.plan?.id) return;
        const key = String(exercise.id);
        workoutView.replacementPanels.set(key, { mode: "permanent", loading: true, options: [], message: "", error: "" });
        renderWorkoutDetail({ preserveScroll: true, focusSelector: `#replacement-panel-${exercise.id}` });
        try {
            const result = await apiRequest(`/workout_plans/${apiSegment(workoutView.plan.id)}/exercises/${apiSegment(exercise.id)}/replacement_options`);
            workoutView.replacementPanels.set(key, { mode: "permanent", loading: false, options: asArray(result.options), message: "", error: "" });
        } catch (error) {
            workoutView.replacementPanels.set(key, { mode: "permanent", loading: false, options: [], message: "", error: error.message });
        }
        renderWorkoutDetail({ preserveScroll: true, focusSelector: `#replacement-panel-${exercise.id}` });
    }

    async function applyPermanentReplacement(exerciseId, catalogKey) {
        const exercise = findSelectedExercise(exerciseId);
        const panel = workoutView.replacementPanels.get(String(exerciseId));
        const dayId = selectedWorkoutDay()?.id;
        if (!exercise || !workoutView.editMode || panel?.mode !== "permanent" || panel.applying) return;
        panel.applying = catalogKey;
        renderWorkoutDetail({ preserveScroll: true });
        try {
            const result = await apiRequest(`/workout_plans/${apiSegment(workoutView.plan.id)}/exercises/${apiSegment(exercise.id)}`, {
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
        await performSessionMutation("finish", `/workout_sessions/${apiSegment(session.id)}/finish`, {method: "POST"}, result => {
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
            workoutView.summaryOrigin = "workout";
            workoutView.shareOpen = false;
            workoutView.shareDraft = null;
            workoutView.sharePhotoToken += 1;
            resetWorkoutExecutionState();
            clearLocalWorkoutDraft(session.id);
            clearActiveWorkoutDock();
            workoutView.replacementPanels.clear();
            window.invalidateProgressOverview?.();
            showToast(result.queued ? "Finalização salva. O histórico será sincronizado quando a conexão voltar." : "Treino finalizado. Excelente trabalho!", "success");
        });
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
                if (action === 'start-today') {
                    if (startingTodayWorkout) return;
                    startingTodayWorkout = true;
                    workoutTodayAction.disabled = true;
                    try {
                        const state = await loadWorkoutTodayCard(true);
                        if (state?.state === 'scheduled' && state.current_day?.id) {
                            const plan = await viewWorkoutPlan(state.current_plan_id, state.current_day.id);
                            if (plan && byId("viewWorkoutPlanModal")?.classList.contains("show") && !workoutView.session && String(selectedWorkoutDay()?.id) === String(state.current_day.id)) await startWorkoutSession();
                        } else if (state?.state === 'active') await openWorkoutTodayPlan();
                    } finally {
                        startingTodayWorkout = false;
                        workoutTodayAction.disabled = false;
                        await loadWorkoutTodayCard(true);
                    }
                }
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
            if (action === "retry-open-plan") { await viewWorkoutPlan(control.dataset.planId); return; }
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
            } else if (action === "request-plan-review") {
                openPlanReviewRequest("workout", workoutView.plan.id);
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
                renderWorkoutDetail({ focusSelector: '[data-workout-action="open-workout-share"]' });
            } else if (action === "set-share-mode") {
                const draft = workoutShareDraft(workoutView.completedSummary);
                const newMode = control.dataset.shareMode;
                if (newMode === "photo" || newMode === "dark") {
                    draft.mode = newMode;
                    renderWorkoutDetail({ preserveScroll: true, focusSelector: `[data-workout-action="set-share-mode"][data-share-mode="${newMode}"]` });
                }
            } else if (action === "set-share-photo-scale") {
                const draft = workoutShareDraft(workoutView.completedSummary);
                draft.photoScale = Math.max(0.5, Math.min(2, Number(control.value) / 100));
                renderWorkoutDetail({ preserveScroll: true, focusSelector: `[data-workout-action="set-share-photo-scale"]` });
            } else if (action === "set-share-photo-offset-x") {
                const draft = workoutShareDraft(workoutView.completedSummary);
                draft.photoOffsetX = Math.max(-300, Math.min(300, Number(control.value)));
                renderWorkoutDetail({ preserveScroll: true, focusSelector: `[data-workout-action="set-share-photo-offset-x"]` });
            } else if (action === "set-share-photo-offset-y") {
                const draft = workoutShareDraft(workoutView.completedSummary);
                draft.photoOffsetY = Math.max(-300, Math.min(300, Number(control.value)));
                renderWorkoutDetail({ preserveScroll: true, focusSelector: `[data-workout-action="set-share-photo-offset-y"]` });
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
    window.openProfessionalPlanWizard = openProfessionalPlanWizard;
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
