(function () {
    "use strict";

    let dietPlans = [];
    let workoutPlans = [];

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
        2: ["full_body"],
        3: ["full_body", "abc"],
        4: ["upper_lower", "abcd"],
        5: ["abcde"],
        6: ["abc"]
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
        diet: ["Objetivo", "Preferências", "Revisão"],
        workout: ["Rotina", "Estrutura", "Revisão"]
    };
    const FIELD_STEPS = {
        diet: {
            goal: 0,
            meals_per_day: 0,
            diet_pattern: 0,
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
            split_type: 1,
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
            allergies: "",
            intolerances: "",
            disliked_foods: "",
            preferred_foods: "",
            budget: "moderate",
            prep_minutes: "30",
            available_ingredients: "",
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
        diet: { step: 0, answers: defaultDietAnswers(), error: "", fieldErrors: {}, generating: false },
        workout: { step: 0, answers: defaultWorkoutAnswers(), error: "", fieldErrors: {}, generating: false }
    };
    const dietView = { plan: null, selectedDay: 0 };
    const workoutView = {
        plan: null,
        days: [],
        selectedDay: 0,
        session: null,
        sessionLoading: false,
        sessionError: "",
        pendingAction: "",
        replacementPanels: new Map(),
        requestToken: 0,
        viewVersion: 0
    };
    let activeWorkoutSummary = null;
    let activeWizardType = null;
    let workoutTimerInterval = null;
    let workoutSyncInterval = null;
    let activeDockRequestToken = 0;

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
        const fetchOptions = {
            method: options.method || "GET",
            credentials: "include",
            headers: {}
        };
        if (options.body !== undefined) {
            fetchOptions.headers["Content-Type"] = "application/json";
            fetchOptions.body = JSON.stringify(options.body);
        }

        let response;
        try {
            response = await fetch(`${API_BASE}${path}`, fetchOptions);
        } catch (error) {
            const connectionError = new Error("Não foi possível conectar ao servidor. Tente novamente.");
            connectionError.cause = error;
            throw connectionError;
        }

        let data = {};
        try {
            data = await response.json();
        } catch (error) {
            data = {};
        }
        if (!response.ok) {
            const fieldMessages = data.fields && typeof data.fields === "object"
                ? Object.values(data.fields).filter(Boolean)
                : [];
            const fallback = response.status === 403
                ? "Este recurso está disponível para assinantes Premium."
                : "Não foi possível concluir a solicitação.";
            const requestError = new Error(data.error || data.message || fieldMessages[0] || fallback);
            requestError.status = response.status;
            requestError.fields = data.fields && typeof data.fields === "object" ? data.fields : {};
            requestError.data = data;
            throw requestError;
        }
        return data;
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

    function loadIngredientPool() {
        if (INGREDIENT_POOL.length || ingredientPoolLoading) return ingredientPoolLoading;
        ingredientPoolLoading = fetch("minha-pasta/alimentos.json")
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
        return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
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
        return matches.slice(0, 60).map((name) => `<option value="${esc(name)}"></option>`).join("");
    }

    function addIngredient(value) {
        const state = wizardMemory[activeWizardType];
        const answers = state.answers;
        const token = String(value || "").trim().replace(/^,+|,+$/g, "");
        if (!token) return;
        const tokens = parseIngredientTokens(answers.available_ingredients);
        if (tokens.indexOf(token) !== -1) return;
        tokens.push(token);
        if (tokens.length > 24) return;
        answers.available_ingredients = tokens.join(", ");
        delete state.fieldErrors.available_ingredients;
        const chips = byId("ingredient-chips");
        if (chips) chips.innerHTML = ingredientChipsMarkup(answers.available_ingredients);
    }

    function removeIngredient(value) {
        const state = wizardMemory[activeWizardType];
        if (!state) return;
        const tokens = parseIngredientTokens(state.answers.available_ingredients).filter((token) => token !== String(value));
        state.answers.available_ingredients = tokens.join(", ");
        const chips = byId("ingredient-chips");
        if (chips) chips.innerHTML = ingredientChipsMarkup(state.answers.available_ingredients);
    }

    function renderDietStep(state) {
        const answers = state.answers;
        if (state.step === 0) {
            return `
                <div class="wizard-step-heading" tabindex="-1"><span>Etapa 1 de 3</span><h4>Qual resultado você busca?</h4><p>Defina a base do plano alimentar. Você poderá revisar tudo antes de gerar.</p></div>
                <fieldset class="wizard-fieldset"><legend>Objetivo principal</legend>${radioCards("goal", DIET_GOALS, answers.goal, state)}</fieldset>
                <div class="wizard-field-row">
                    <fieldset class="wizard-fieldset"><legend>Refeições por dia</legend>${radioCards("meals_per_day", { 3: "3 refeições", 4: "4 refeições", 5: "5 refeições" }, answers.meals_per_day, state, true)}</fieldset>
                    <div class="wizard-field">
                        <label for="wizard-diet-pattern">Padrão alimentar</label>
                        <select id="wizard-diet-pattern" name="diet_pattern"${invalidAttributes("diet_pattern", state)}>${selectOptions(DIET_PATTERNS, answers.diet_pattern)}</select>
                        ${fieldError("diet_pattern", state)}
                    </div>
                </div>`;
        }
        if (state.step === 1) {
            return `
                <div class="wizard-step-heading" tabindex="-1"><span>Etapa 2 de 3</span><h4>Preferências e cuidados</h4><p>Separe vários itens com vírgulas. Deixe em branco o que não se aplicar.</p></div>
                <div class="wizard-field-grid">
                    <div class="wizard-field"><label for="wizard-allergies">Alergias</label><input id="wizard-allergies" name="allergies" value="${esc(answers.allergies)}" placeholder="Ex.: amendoim, camarão" maxlength="970"${invalidAttributes("allergies", state)}><small class="wizard-field-hint">Confira sempre rótulos e risco de contaminação cruzada.</small>${fieldError("allergies", state)}</div>
                    <div class="wizard-field"><label for="wizard-intolerances">Intolerâncias</label><input id="wizard-intolerances" name="intolerances" value="${esc(answers.intolerances)}" placeholder="Ex.: lactose, glúten" maxlength="970"${invalidAttributes("intolerances", state)}>${fieldError("intolerances", state)}</div>
                    <div class="wizard-field"><label for="wizard-disliked-foods">Alimentos que não gosta</label><input id="wizard-disliked-foods" name="disliked_foods" value="${esc(answers.disliked_foods)}" placeholder="Ex.: berinjela, coentro" maxlength="970"${invalidAttributes("disliked_foods", state)}>${fieldError("disliked_foods", state)}</div>
                    <div class="wizard-field"><label for="wizard-preferred-foods">Alimentos preferidos</label><input id="wizard-preferred-foods" name="preferred_foods" value="${esc(answers.preferred_foods)}" placeholder="Ex.: arroz, frango, banana" maxlength="970"${invalidAttributes("preferred_foods", state)}>${fieldError("preferred_foods", state)}</div>
                </div>`;
        }
        return `
            <div class="wizard-step-heading" tabindex="-1"><span>Etapa 3 de 3</span><h4>Rotina e revisão</h4><p>Ajuste o preparo e confirme as escolhas antes de criar seus três dias.</p></div>
            <div class="wizard-field-row">
                <fieldset class="wizard-fieldset"><legend>Orçamento</legend>${radioCards("budget", BUDGETS, answers.budget, state, true)}</fieldset>
                <div class="wizard-field"><label for="wizard-prep-minutes">Tempo máximo de preparo</label><select id="wizard-prep-minutes" name="prep_minutes"${invalidAttributes("prep_minutes", state)}>${selectOptions({ 15: "Até 15 min", 30: "Até 30 min", 45: "Até 45 min", 60: "Até 60 min" }, answers.prep_minutes)}</select>${fieldError("prep_minutes", state)}</div>
            </div>
            <div class="wizard-field wizard-field--ingredients">
                <label for="wizard-ingredient-input">Selecionar ingredientes <span>opcional</span></label>
                <div class="ingredient-picker">
                    <input id="wizard-ingredient-input" name="available_ingredients" list="wizard-ingredient-options" placeholder="Digite um ingrediente e pressione Enter" autocomplete="off" maxlength="970" value="${esc(answers.available_ingredients)}"${invalidAttributes("available_ingredients", state)}>
                    <datalist id="wizard-ingredient-options">${ingredientOptions(ingredientLastToken(answers.available_ingredients))}</datalist>
                    <button type="button" class="ingredient-add" data-add-ingredient aria-label="Adicionar ingrediente"><i class="fas fa-plus" aria-hidden="true"></i></button>
                </div>
                <div class="ingredient-chips" id="ingredient-chips">${ingredientChipsMarkup(answers.available_ingredients)}</div>
                <small class="wizard-field-hint">Informe o que você tem em casa. A IA monta o plano usando principalmente esses ingredientes.</small>
                ${fieldError("available_ingredients", state)}
            </div>
            <div class="wizard-field"><label for="wizard-diet-notes">Observações finais <span>opcional</span></label><textarea id="wizard-diet-notes" name="notes" rows="3" maxlength="500" placeholder="Conte algo importante sobre sua rotina."${invalidAttributes("notes", state)}>${esc(answers.notes)}</textarea><small class="wizard-character-count">${String(answers.notes || "").length}/500</small>${fieldError("notes", state)}</div>
            ${renderWizardReview("diet", answers)}`;
    }

    function compatibleSplits(days) {
        const values = SPLITS_BY_DAYS[Number(days)] || [];
        return values.reduce((result, value) => {
            result[value] = SPLIT_TYPES[value];
            return result;
        }, {});
    }

    function recommendedSplit(days, experienceLevel) {
        const numericDays = Number(days);
        if (numericDays === 2) return "full_body";
        if (numericDays === 3) return experienceLevel === "beginner" ? "full_body" : "abc";
        if (numericDays === 4) return "upper_lower";
        if (numericDays === 5) return "abcde";
        return "abc";
    }

    function renderWorkoutStep(state) {
        const answers = state.answers;
        if (state.step === 0) {
            return `
                <div class="wizard-step-heading" tabindex="-1"><span>Etapa 1 de 3</span><h4>Monte uma rotina possível</h4><p>Escolha o objetivo e uma frequência que caiba de verdade na sua semana.</p></div>
                <div class="wizard-field"><label for="wizard-workout-goal">Objetivo principal</label><select id="wizard-workout-goal" name="goal"${invalidAttributes("goal", state)}><option value="">Selecione um objetivo</option>${selectOptions(WORKOUT_GOALS, answers.goal)}</select>${fieldError("goal", state)}</div>
                <div class="wizard-field-row">
                    <fieldset class="wizard-fieldset"><legend>Experiência</legend>${radioCards("experience_level", EXPERIENCE_LEVELS, answers.experience_level, state, true)}</fieldset>
                    <fieldset class="wizard-fieldset"><legend>Dias por semana</legend>${radioCards("days_per_week", { 2: "2", 3: "3", 4: "4", 5: "5", 6: "6" }, answers.days_per_week, state, true)}</fieldset>
                </div>`;
        }
        if (state.step === 1) {
            return `
                <div class="wizard-step-heading" tabindex="-1"><span>Etapa 2 de 3</span><h4>Estrutura do treino</h4><p>A divisão já está limitada às opções compatíveis com sua frequência.</p></div>
                <div class="wizard-field-row">
                    <fieldset class="wizard-fieldset"><legend>Divisão semanal</legend><p class="wizard-field-hint">Recomendação: ${esc(labelFor(SPLIT_TYPES, recommendedSplit(answers.days_per_week, answers.experience_level)))}</p>${radioCards("split_type", compatibleSplits(answers.days_per_week), answers.split_type, state, true)}</fieldset>
                    <div class="wizard-field"><label for="wizard-session-duration">Duração por sessão</label><select id="wizard-session-duration" name="session_duration"${invalidAttributes("session_duration", state)}>${selectOptions({ 20: "20 minutos", 30: "30 minutos", 45: "45 minutos", 60: "60 minutos", 75: "75 minutos", 90: "90 minutos" }, answers.session_duration)}</select>${fieldError("session_duration", state)}</div>
                </div>
                <fieldset class="wizard-fieldset"><legend>Equipamentos disponíveis</legend><p class="wizard-field-hint">Marque tudo o que costuma estar ao seu alcance.</p>${checkboxCards("equipment", WORKOUT_EQUIPMENT, answers.equipment, state)}</fieldset>`;
        }
        return `
            <div class="wizard-step-heading" tabindex="-1"><span>Etapa 3 de 3</span><h4>Ajustes e revisão</h4><p>Esses detalhes ajudam a IA a criar um treino mais seguro e relevante.</p></div>
            <div class="wizard-field-grid">
                <div class="wizard-field"><label for="wizard-limitations">Limitações ou dores <span>opcional</span></label><textarea id="wizard-limitations" name="limitations" rows="3" maxlength="500" placeholder="Ex.: desconforto no joelho direito"${invalidAttributes("limitations", state)}>${esc(answers.limitations)}</textarea><small class="wizard-field-hint">Interrompa movimentos que causem dor. O plano não substitui avaliação profissional.</small>${fieldError("limitations", state)}</div>
                <div class="wizard-field"><label for="wizard-priorities">Regiões prioritárias <span>opcional</span></label><textarea id="wizard-priorities" name="priorities" rows="3" maxlength="300" placeholder="Ex.: costas e glúteos"${invalidAttributes("priorities", state)}>${esc(answers.priorities)}</textarea>${fieldError("priorities", state)}</div>
            </div>
            <div class="wizard-field"><label for="wizard-avoid-exercises">Exercícios que prefere evitar <span>opcional</span></label><input id="wizard-avoid-exercises" name="avoid_exercises" value="${esc(answers.avoid_exercises)}" maxlength="300" placeholder="Ex.: agachamento livre"${invalidAttributes("avoid_exercises", state)}>${fieldError("avoid_exercises", state)}</div>
            ${renderWizardReview("workout", answers)}`;
    }

    function renderWizardReview(type, answers) {
        const rows = type === "diet"
            ? [
                ["Objetivo", labelFor(DIET_GOALS, answers.goal)],
                ["Rotina", `${answers.meals_per_day} refeições, dieta ${labelFor(DIET_PATTERNS, answers.diet_pattern).toLowerCase()}`],
                ["Preparo", `${labelFor(BUDGETS, answers.budget)}, até ${answers.prep_minutes} min`]
            ]
            : [
                ["Objetivo", labelFor(WORKOUT_GOALS, answers.goal)],
                ["Rotina", `${answers.days_per_week} dias, ${answers.session_duration} min por sessão`],
                ["Estrutura", `${labelFor(SPLIT_TYPES, answers.split_type)} · ${labelFor(EXPERIENCE_LEVELS, answers.experience_level)}`]
            ];
        return `
            <aside class="wizard-review" aria-label="Resumo das respostas">
                <div class="wizard-review__title"><i class="fas fa-clipboard-check" aria-hidden="true"></i><div><strong>Pronto para gerar</strong><span>Revise o resumo. Suas respostas ficam salvas se precisar tentar novamente.</span></div></div>
                <dl>${rows.map(([term, description]) => `<div><dt>${esc(term)}</dt><dd>${esc(description)}</dd></div>`).join("")}</dl>
            </aside>`;
    }

    function renderWizard(options = {}) {
        if (!activeWizardType) return;
        const type = activeWizardType;
        const state = wizardMemory[type];
        const modal = byId("guidedPlanModal");
        const stepContainer = byId("planWizardStep");
        if (!modal || !stepContainer) return;

        const isDiet = type === "diet";
        byId("planWizardTitle").textContent = isDiet ? "Seu plano alimentar" : "Seu plano de treino";
        byId("planWizardDescription").textContent = isDiet
            ? "Três dias rotativos alinhados às suas preferências."
            : "Uma semana de treinos alinhada à sua rotina.";
        byId("planWizardKicker").textContent = isDiet ? "Planejamento alimentar" : "Rotina de movimento";
        byId("planWizardIcon").className = `plan-wizard__icon${isDiet ? "" : " plan-wizard__icon--workout"}`;
        byId("planWizardIcon").innerHTML = `<i class="fas ${isDiet ? "fa-apple-alt" : "fa-dumbbell"}" aria-hidden="true"></i>`;

        const steps = WIZARD_STEPS[type];
        byId("planWizardSteps").innerHTML = steps.map((label, index) => {
            const status = index < state.step ? "complete" : index === state.step ? "active" : "";
            const current = index === state.step ? ' aria-current="step"' : "";
            return `<li class="${status}"${current}><span>${index < state.step ? '<i class="fas fa-check" aria-hidden="true"></i>' : index + 1}</span><small>${esc(label)}</small></li>`;
        }).join("");
        byId("planWizardProgressBar").style.width = `${((state.step + 1) / steps.length) * 100}%`;
        stepContainer.innerHTML = isDiet ? renderDietStep(state) : renderWorkoutStep(state);
        stepContainer.setAttribute("aria-busy", state.generating ? "true" : "false");

        const errorElement = byId("planWizardError");
        if (state.error) {
            errorElement.textContent = state.error;
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
            nextLabel.textContent = isDiet ? "Criando sua dieta..." : "Criando seu treino...";
            nextIcon.className = "fas fa-spinner fa-spin";
        } else if (state.step === 2) {
            nextLabel.textContent = "Gerar plano";
            nextIcon.className = "fas fa-wand-magic-sparkles";
        } else if (state.step === 1) {
            nextLabel.textContent = "Revisar";
            nextIcon.className = "fas fa-arrow-right";
        } else {
            nextLabel.textContent = "Continuar";
            nextIcon.className = "fas fa-arrow-right";
        }

        modal.dataset.modalLocked = state.generating ? "true" : "false";
        const form = byId("guidedPlanForm");
        form.querySelectorAll("input, select, textarea, button").forEach((control) => {
            control.disabled = state.generating;
        });
        if (options.focusHeading) {
            requestAnimationFrame(() => stepContainer.querySelector(".wizard-step-heading")?.focus());
        }
    }

    function openPlanWizard(type) {
        if (type !== "diet" && type !== "workout") return;
        activeWizardType = type;
        const modal = byId("guidedPlanModal");
        if (!modal) return;
        renderWizard();
        modal.setAttribute("aria-hidden", "false");
        openAppModal(modal);
        requestAnimationFrame(() => byId("planWizardStep")?.querySelector(".wizard-step-heading")?.focus());
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
                const fields = {
                    allergies: "Alergias",
                    intolerances: "Intolerâncias",
                    disliked_foods: "Alimentos evitados",
                    preferred_foods: "Alimentos preferidos"
                };
                Object.entries(fields).forEach(([field, label]) => {
                    const message = validateTextList(answers[field], label);
                    if (message) errors[field] = message;
                });
            } else {
                if (!BUDGETS[answers.budget]) errors.budget = "Selecione uma faixa de orçamento.";
                if (!["15", "30", "45", "60"].includes(String(answers.prep_minutes))) errors.prep_minutes = "Selecione o tempo de preparo.";
                const ingredientMessage = validateTextList(answers.available_ingredients, "Ingredientes");
                if (ingredientMessage) errors.available_ingredients = ingredientMessage;
                if (String(answers.notes || "").length > 500) errors.notes = "Resuma as observações em até 500 caracteres.";
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
                allergies: parseTextList(answers.allergies),
                intolerances: parseTextList(answers.intolerances),
                disliked_foods: parseTextList(answers.disliked_foods),
                preferred_foods: parseTextList(answers.preferred_foods),
                budget: answers.budget,
                prep_minutes: Number(answers.prep_minutes),
                available_ingredients: parseTextList(answers.available_ingredients),
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

    async function generatePlan(type) {
        const state = wizardMemory[type];
        const errors = validateAllWizardSteps(type);
        if (Object.keys(errors).length) {
            showWizardErrors(type, errors, "Revise os campos destacados antes de gerar o plano.");
            return;
        }

        state.generating = true;
        renderWizard();
        let result;
        try {
            result = await apiRequest(`/${type === "diet" ? "diet_plans" : "workout_plans"}/generate`, {
                method: "POST",
                body: buildWizardPayload(type)
            });
        } catch (error) {
            state.generating = false;
            const serverFields = error.fields && typeof error.fields === "object" ? error.fields : {};
            showWizardErrors(type, serverFields, error.message);
            return;
        }

        state.generating = false;
        state.error = "";
        state.fieldErrors = {};
        const planId = result.plan_id || result.plan?.id;
        wizardMemory[type] = {
            step: 0,
            answers: type === "diet" ? defaultDietAnswers() : defaultWorkoutAnswers(),
            error: "",
            fieldErrors: {},
            generating: false
        };
        closePlanWizard();
        showToast(type === "diet" ? "Plano alimentar criado!" : "Plano de treino criado!", "success");
        showTab(type === "diet" ? "diet_plans" : "workout_plans");
        if (planId) {
            if (type === "diet") await viewDietPlan(planId);
            else await viewWorkoutPlan(planId);
        }
    }

    function handleWizardInput(event) {
        if (!activeWizardType) return;
        const control = event.target;
        if (!control.name) return;
        const state = wizardMemory[activeWizardType];
        if (control.type === "checkbox") {
            const current = new Set(asArray(state.answers[control.name]));
            if (control.checked) current.add(control.value);
            else current.delete(control.value);
            state.answers[control.name] = Array.from(current);
        } else {
            state.answers[control.name] = control.value;
        }
        delete state.fieldErrors[control.name];

        if (activeWizardType === "workout" && ["days_per_week", "experience_level"].includes(control.name)) {
            state.answers.split_type = recommendedSplit(state.answers.days_per_week, state.answers.experience_level);
        }
        if (control.name === "notes") {
            const count = byId("planWizardStep")?.querySelector(".wizard-character-count");
            if (count) count.textContent = `${control.value.length}/500`;
        }
    }

    function handleWizardKeydown(event) {
        const control = event.target;
        if (!activeWizardType || control.id !== "wizard-ingredient-input") return;
        if (event.key === "Enter" || event.key === "," || event.key === ";") {
            event.preventDefault();
            addIngredient(control.value);
            control.value = "";
        }
    }

    function handleIngredientClick(event) {
        const addButton = event.target.closest("[data-add-ingredient]");
        if (addButton) {
            const input = byId("wizard-ingredient-input");
            if (input) {
                addIngredient(input.value);
                input.value = "";
                input.focus();
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
            return `
                <article class="plan-card plan-card--${type}">
                    <div class="plan-card__icon"><i class="fas ${isDiet ? "fa-apple-alt" : "fa-dumbbell"}" aria-hidden="true"></i></div>
                    <div class="plan-card__body">
                        <div class="plan-card__topline"><span class="plan-type">${isDiet ? "Plano alimentar" : "Plano de treino"}</span><span class="plan-count"><i class="fas ${isDiet ? "fa-utensils" : "fa-dumbbell"}" aria-hidden="true"></i> ${esc(count || 0)} ${countLabel}</span></div>
                        <h3>${esc(plan.title || (isDiet ? "Plano alimentar" : "Plano de treino"))}</h3>
                        <p>${esc(plan.description || fallback)}</p>
                        <span class="plan-date"><i class="far fa-calendar" aria-hidden="true"></i> Criado em ${esc(formatDateTime(plan.created_at))}</span>
                    </div>
                    <div class="plan-card__actions">
                        <button type="button" data-plan-action="view" data-plan-type="${type}" data-plan-id="${esc(plan.id)}" class="btn-view"><i class="fas fa-arrow-right" aria-hidden="true"></i> ${isDiet ? "Ver plano" : "Ver treino"}</button>
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

    async function loadDietPlans() {
        const container = byId("dietPlansTableBody");
        if (container) {
            container.setAttribute("aria-busy", "true");
            if (!container.children.length) container.innerHTML = planLoadingMarkup("Carregando planos alimentares...");
        }
        try {
            const result = await apiRequest("/diet_plans");
            dietPlans = Array.isArray(result) ? result : [];
            renderPlanList("diet", dietPlans);
            return dietPlans;
        } catch (error) {
            showToast(error.message, "error");
            return [];
        } finally {
            container?.setAttribute("aria-busy", "false");
        }
    }

    async function loadWorkoutPlans() {
        const container = byId("workoutPlansTableBody");
        if (container) {
            container.setAttribute("aria-busy", "true");
            if (!container.children.length) container.innerHTML = planLoadingMarkup("Carregando planos de treino...");
        }
        try {
            const result = await apiRequest("/workout_plans");
            workoutPlans = Array.isArray(result) ? result : [];
            renderFilteredWorkoutPlans();
            return workoutPlans;
        } catch (error) {
            showToast(error.message, "error");
            return [];
        } finally {
            container?.setAttribute("aria-busy", "false");
        }
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
        const items = asArray(meal.items).filter((item) => item != null && String(item).trim());
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
                    : `<p class="meal-description">${esc(meal.description || "Descrição não informada.")}</p>`}
                <div class="meal-macro-heading"><span>Macros estimados</span><small>valores aproximados</small></div>
                ${renderMealMacros(meal)}
                ${meal.prep_instructions ? `<div class="meal-preparation"><strong><i class="fas fa-kitchen-set" aria-hidden="true"></i> Como preparar</strong><p>${esc(meal.prep_instructions)}</p></div>` : ""}
                ${renderSubstitutions(meal.substitutions)}
                ${meal.notes ? `<p class="plan-note"><i class="fas fa-lightbulb" aria-hidden="true"></i> ${esc(meal.notes)}</p>` : ""}
            </article>`;
    }

    function renderDietDetail() {
        const plan = dietView.plan;
        const details = byId("viewDietPlanDetails");
        if (!plan || !details) return;
        const groups = groupDietMeals(plan);
        if (dietView.selectedDay >= groups.length) dietView.selectedDay = 0;
        const summary = `
            <section class="plan-summary">
                <div class="plan-summary__icon"><i class="fas fa-apple-alt" aria-hidden="true"></i></div>
                <div><span>Plano alimentar</span><p>${esc(plan.description || "Uma rotina alimentar organizada para você.")}</p></div>
                <small><i class="far fa-calendar" aria-hidden="true"></i> ${esc(formatDateTime(plan.created_at))}</small>
            </section>`;
        if (!groups.length) {
            details.innerHTML = `${summary}<div class="plan-details-empty">Nenhuma refeição detalhada para este plano.</div>`;
            return;
        }
        const tabs = `
            <div class="plan-day-tabs" role="tablist" aria-label="Dias do plano alimentar">
                ${groups.map((group, index) => `<button type="button" role="tab" id="diet-day-tab-${index}" aria-controls="diet-day-panel-${index}" aria-selected="${index === dietView.selectedDay}" tabindex="${index === dietView.selectedDay ? "0" : "-1"}" class="plan-day-tab${index === dietView.selectedDay ? " active" : ""}" data-diet-day-index="${index}"><span>Dia ${index + 1}</span><strong>${esc(group.name)}</strong></button>`).join("")}
            </div>`;
        const sections = groups.map((group, index) => `
            <section id="diet-day-panel-${index}" role="tabpanel" aria-labelledby="diet-day-tab-${index}" class="plan-details-section diet-day-panel${index === dietView.selectedDay ? "" : " hidden"}">
                <div class="plan-section-title"><span><i class="far fa-calendar-check" aria-hidden="true"></i> ${esc(group.name)}</span><small>${group.meals.length} refeição(ões)</small></div>
                <div class="meal-list">${group.meals.map(renderMealCard).join("")}</div>
            </section>`).join("");
        details.innerHTML = `${summary}${tabs}${sections}`;
    }

    async function viewDietPlan(id) {
        showGlobalLoading("Carregando detalhes do plano alimentar...");
        try {
            const plan = await apiRequest(`/diet_plans/${apiSegment(id)}`);
            dietView.plan = plan;
            dietView.selectedDay = 0;
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

    async function loadActiveWorkoutDock() {
        const token = ++activeDockRequestToken;
        let result = null;
        try {
            result = await apiRequest("/workout_sessions/active");
        } catch (error) {
            result = null;
        }
        if (token !== activeDockRequestToken || byId("mainScreen")?.classList.contains("hidden")) return;
        activeWorkoutSummary = result;
        renderActiveWorkoutDock();
        const modalOpen = byId("viewWorkoutPlanModal")?.classList.contains("show");
        if (!modalOpen || !workoutView.session) return;
        if (result?.session && String(result.session.id) === String(workoutView.session.id)) {
            workoutView.session = result.session;
            renderWorkoutDetail({ preserveScroll: true });
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

    function isCurrentWorkoutSession(sessionId) {
        return String(workoutView.session?.id || "") === String(sessionId || "");
    }

    function invalidateWorkoutView() {
        workoutView.viewVersion += 1;
        workoutView.requestToken += 1;
        workoutView.pendingAction = "";
    }

    function exerciseImage(exercise) {
        return typeof exerciseImagePath === "function"
            ? exerciseImagePath(exercise?.name, exercise?.catalog_key)
            : "";
    }

    function exerciseImageMarkup(exercise) {
        const imagePath = exerciseImage(exercise);
        if (imagePath) {
            return `<img class="exercise-demonstration-image" src="${esc(imagePath)}" alt="Demonstração de ${esc(exercise?.name || "exercício")}" loading="lazy">`;
        }
        return '<span class="exercise-image-placeholder" role="img" aria-label="Imagem não disponível"><i class="fas fa-dumbbell" aria-hidden="true"></i></span>';
    }

    function equipmentLabel(value) {
        return labelFor({ ...WORKOUT_EQUIPMENT, ...CATALOG_EQUIPMENT_LABELS }, value, value || "Equipamento livre");
    }

    function renderReplacementPanel(exercise, panel) {
        if (!panel) return "";
        const panelId = `replacement-panel-${esc(exercise.id)}`;
        if (panel.loading) {
            return `<section id="${panelId}" class="replacement-panel" tabindex="-1" aria-live="polite"><div class="replacement-panel__loading"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>Buscando alternativas seguras...</span></div></section>`;
        }
        return `
            <section id="${panelId}" class="replacement-panel" tabindex="-1" aria-labelledby="replacement-title-${esc(exercise.id)}">
                <div class="replacement-panel__header">
                    <div><span>Somente nesta sessão</span><h6 id="replacement-title-${esc(exercise.id)}">Trocar ${esc(exercise.name)}</h6><p>Alternativas compatíveis com o mesmo padrão de movimento.</p></div>
                    <button type="button" class="replacement-close" data-workout-action="close-replacements" data-exercise-id="${esc(exercise.id)}" aria-label="Fechar alternativas"><i class="fas fa-xmark" aria-hidden="true"></i></button>
                </div>
                ${panel.error ? `<p class="session-inline-error" role="alert">${esc(panel.error)}</p>` : ""}
                ${panel.message ? `<p class="replacement-message">${esc(panel.message)}</p>` : ""}
                <div class="replacement-options">
                    ${asArray(panel.options).slice(0, 3).map((option) => `
                        <article class="replacement-option">
                            ${exerciseImageMarkup(option)}
                            <div class="replacement-option__body"><h6>${esc(option.name)}</h6><p>${esc(option.rationale || "Mantém o foco do exercício original.")}</p><span><i class="fas fa-dumbbell" aria-hidden="true"></i> ${esc(equipmentLabel(option.equipment))}</span></div>
                            <button type="button" class="replacement-apply" data-workout-action="apply-replacement" data-exercise-id="${esc(exercise.id)}" data-catalog-key="${esc(option.catalog_key)}"${panel.applying === option.catalog_key ? " disabled" : ""}>${panel.applying === option.catalog_key ? '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Aplicando' : "Usar hoje"}</button>
                        </article>`).join("")}
                </div>
                ${!panel.error && !asArray(panel.options).length ? '<div class="replacement-empty"><i class="fas fa-circle-info" aria-hidden="true"></i><span>Nenhuma alternativa disponível para os equipamentos do plano.</span></div>' : ""}
            </section>`;
    }

    function renderExerciseCard(originalExercise, index) {
        const { exercise, override } = displayedExercise(originalExercise);
        const active = Boolean(workoutView.session);
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
                ${active ? `<div class="exercise-session-actions"><button type="button" class="machine-busy-button" data-workout-action="replacement-options" data-exercise-id="${esc(originalExercise.id)}" aria-expanded="${Boolean(panel)}" aria-controls="replacement-panel-${esc(originalExercise.id)}"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i> Máquina ocupada</button>${override ? `<button type="button" class="restore-exercise-button" data-workout-action="restore-exercise" data-exercise-id="${esc(originalExercise.id)}"${workoutView.pendingAction === `restore-${originalExercise.id}` ? " disabled" : ""}><i class="fas fa-rotate-left" aria-hidden="true"></i> Restaurar original</button>` : ""}</div>` : ""}
                ${renderReplacementPanel(originalExercise, panel)}
            </article>`;
    }

    function renderActiveWorkout(day) {
        const exercises = asArray(day.exercises);
        const completedIds = completedWorkoutExerciseIds();
        const completedCount = exercises.filter((exercise) => completedIds.has(String(exercise.id))).length;
        const currentOriginal = exercises.find((exercise) => !completedIds.has(String(exercise.id)));
        const progress = exercises.length ? Math.round((completedCount / exercises.length) * 100) : 0;
        const timer = formatWorkoutElapsed(workoutElapsedSeconds(workoutView.session?.started_at));
        const toolbar = `
            <header class="active-workout-toolbar">
                <div class="active-workout-status"><span><i class="fas fa-circle" aria-hidden="true"></i> Treino em andamento</span><strong>${esc(day.title)}</strong></div>
                <div class="active-workout-timer" aria-label="Tempo de treino"><small><i class="fas fa-stopwatch" aria-hidden="true"></i> Tempo</small><time data-workout-elapsed data-workout-started-at="${esc(workoutView.session?.started_at || "")}">${timer}</time></div>
                <div class="active-workout-progress" aria-label="${completedCount} de ${exercises.length} exercícios concluídos"><span><b>${completedCount}</b> de ${exercises.length}</span><div aria-hidden="true"><i style="width:${progress}%"></i></div></div>
            </header>`;
        if (!currentOriginal) {
            return `
                <section class="active-workout-shell active-workout-shell--complete">
                    ${toolbar}
                    <div class="workout-complete-state">
                        <span><i class="fas fa-trophy" aria-hidden="true"></i></span>
                        <div><small>Sessão completa</small><h4 id="workoutCompleteTitle" tabindex="-1">Todos os exercícios foram concluídos</h4><p>Finalize o treino para salvar esta sessão no seu histórico.</p></div>
                        <button type="button" class="finish-workout-button active-workout-finish" data-workout-action="finish-session"${workoutView.pendingAction === "finish" ? " disabled" : ""}>${workoutView.pendingAction === "finish" ? '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>' : '<i class="fas fa-flag-checkered" aria-hidden="true"></i>'} Finalizar treino</button>
                    </div>
                </section>`;
        }

        const { exercise, override } = displayedExercise(currentOriginal);
        const panel = workoutView.replacementPanels.get(String(currentOriginal.id));
        const currentPosition = completedCount + 1;
        const details = [
            exercise.primary_muscle && `<span><i class="fas fa-bullseye" aria-hidden="true"></i>${esc(exercise.primary_muscle)}</span>`,
            exercise.equipment && `<span><i class="fas fa-dumbbell" aria-hidden="true"></i>${esc(equipmentLabel(exercise.equipment))}</span>`,
            exercise.rest_seconds && `<span><i class="fas fa-hourglass-half" aria-hidden="true"></i>${esc(exercise.rest_seconds)}s de descanso</span>`
        ].filter(Boolean).join("");
        const queue = exercises.map((item, index) => {
            const done = completedIds.has(String(item.id));
            const active = String(item.id) === String(currentOriginal.id);
            const shown = displayedExercise(item).exercise;
            return `<li class="${done ? "is-complete" : active ? "is-current" : ""}"><span>${done ? '<i class="fas fa-check" aria-hidden="true"></i>' : index + 1}</span><strong>${esc(shown.name)}</strong>${active ? "<small>Agora</small>" : ""}</li>`;
        }).join("");
        return `
            <section class="active-workout-shell">
                ${toolbar}
                ${workoutView.sessionError ? `<p class="session-inline-error" role="alert"><i class="fas fa-circle-exclamation" aria-hidden="true"></i> ${esc(workoutView.sessionError)}</p>` : ""}
                <article class="current-exercise-stage">
                    <figure class="current-exercise-media">${exerciseImageMarkup(exercise)}</figure>
                    <div class="current-exercise-content">
                        <span class="current-exercise-kicker">Exercício ${currentPosition} de ${exercises.length}</span>
                        ${override ? '<span class="session-override-badge"><i class="fas fa-shuffle" aria-hidden="true"></i> Substituição desta sessão</span>' : ""}
                        <h3 id="currentExerciseTitle" tabindex="-1">${esc(exercise.name)}</h3>
                        <div class="current-exercise-prescription"><strong>${esc(exercise.sets ?? "—")}<small>séries</small></strong><span>×</span><strong>${esc(exercise.reps ?? "—")}<small>repetições</small></strong></div>
                        ${details ? `<div class="current-exercise-meta">${details}</div>` : ""}
                        ${exercise.weight ? `<p class="current-exercise-note"><i class="fas fa-weight-hanging" aria-hidden="true"></i><span><strong>Carga</strong>${esc(exercise.weight)}</span></p>` : ""}
                        ${exercise.effort_guidance ? `<p class="current-exercise-note"><i class="fas fa-gauge-high" aria-hidden="true"></i><span><strong>Esforço</strong>${esc(exercise.effort_guidance)}</span></p>` : ""}
                        ${exercise.notes ? `<p class="current-exercise-instruction"><i class="fas fa-circle-info" aria-hidden="true"></i>${esc(exercise.notes)}</p>` : ""}
                        <div class="current-exercise-actions">
                            <button type="button" class="complete-exercise-button" data-workout-action="complete-exercise" data-exercise-id="${esc(currentOriginal.id)}"${workoutView.pendingAction === `complete-${currentOriginal.id}` ? " disabled" : ""}>${workoutView.pendingAction === `complete-${currentOriginal.id}` ? '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Salvando...' : '<i class="fas fa-check" aria-hidden="true"></i> Exercício concluído'}</button>
                            <button type="button" class="replace-current-exercise-button" data-workout-action="replacement-options" data-exercise-id="${esc(currentOriginal.id)}" aria-expanded="${Boolean(panel)}" aria-controls="replacement-panel-${esc(currentOriginal.id)}"><i class="fas fa-shuffle" aria-hidden="true"></i> Substituir</button>
                            ${override ? `<button type="button" class="restore-exercise-button" data-workout-action="restore-exercise" data-exercise-id="${esc(currentOriginal.id)}"${workoutView.pendingAction === `restore-${currentOriginal.id}` ? " disabled" : ""}><i class="fas fa-rotate-left" aria-hidden="true"></i> Restaurar original</button>` : ""}
                        </div>
                    </div>
                </article>
                ${renderReplacementPanel(currentOriginal, panel)}
                <details class="active-workout-queue"><summary><span>Sequência do treino</span><strong>${completedCount}/${exercises.length} concluídos</strong></summary><ol>${queue}</ol></details>
                <button type="button" class="finish-workout-link" data-workout-action="finish-session"><i class="fas fa-stop-circle" aria-hidden="true"></i> Encerrar treino antes de concluir tudo</button>
            </section>`;
    }

    function renderWorkoutDetail(options = {}) {
        const plan = workoutView.plan;
        const details = byId("viewWorkoutPlanDetails");
        if (!plan || !details) return;
        const previousScroll = options.preserveScroll ? details.scrollTop : 0;
        if (workoutView.selectedDay >= workoutView.days.length) workoutView.selectedDay = 0;
        const day = selectedWorkoutDay();
        const summaryMeta = [
            plan.goal && labelFor(WORKOUT_GOALS, plan.goal, plan.goal),
            plan.experience_level && labelFor(EXPERIENCE_LEVELS, plan.experience_level, plan.experience_level),
            plan.session_duration && `${plan.session_duration} min`
        ].filter(Boolean);
        const summary = `
            <section class="plan-summary workout-summary">
                <div class="plan-summary__icon"><i class="fas fa-dumbbell" aria-hidden="true"></i></div>
                <div><span>Plano de treino</span><p>${esc(plan.description || "Uma rotina criada para sua evolução.")}</p>${summaryMeta.length ? `<div class="workout-summary__meta">${summaryMeta.map((item) => `<small>${esc(item)}</small>`).join("")}</div>` : ""}</div>
                <small><i class="far fa-calendar" aria-hidden="true"></i> ${esc(formatDateTime(plan.created_at))}</small>
            </section>`;
        if (!day) {
            details.innerHTML = `${summary}<div class="plan-details-empty">Nenhum exercício detalhado para este plano.</div>`;
            return;
        }

        const session = workoutView.session;
        const tabs = session ? "" : `
            <div class="plan-day-tabs plan-day-tabs--workout" role="tablist" aria-label="Dias do plano de treino">
                ${workoutView.days.map((workoutDay, index) => `<button type="button" role="tab" id="workout-day-tab-${index}" aria-controls="workout-day-panel" aria-selected="${index === workoutView.selectedDay}" tabindex="${index === workoutView.selectedDay ? "0" : "-1"}" class="plan-day-tab${index === workoutView.selectedDay ? " active" : ""}" data-workout-action="select-day" data-day-index="${index}"><span>${esc(workoutDay.code || `Dia ${index + 1}`)}</span><strong>${esc(workoutDay.title || `Treino ${index + 1}`)}</strong></button>`).join("")}
            </div>`;
        const sessionControls = workoutView.sessionLoading
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
            <section id="workout-day-panel" role="tabpanel" aria-labelledby="workout-day-tab-${workoutView.selectedDay}" class="workout-day-panel">
                <div class="workout-day-header"><div><span>Treino selecionado</span><h4>${esc(day.title)}</h4>${day.focus ? `<p>${esc(day.focus)}</p>` : ""}</div>${sessionControls}</div>
                ${workoutView.sessionError ? `<p class="session-inline-error" role="alert"><i class="fas fa-circle-exclamation" aria-hidden="true"></i> ${esc(workoutView.sessionError)}</p>` : ""}
                <div class="plan-section-title"><span><i class="fas fa-bolt" aria-hidden="true"></i> Sequência do dia</span><small>${asArray(day.exercises).length} exercícios</small></div>
                <div class="exercise-list">${asArray(day.exercises).length ? asArray(day.exercises).map(renderExerciseCard).join("") : '<div class="plan-details-empty">Nenhum exercício neste dia.</div>'}</div>
                ${sessionFooter}
            </section>`;
        const title = byId("viewWorkoutPlanTitle");
        if (title) title.textContent = session ? "Treino em andamento" : plan.title || "Plano de Treino";
        details.innerHTML = `${session ? "" : summary}${tabs}${panel}`;
        details.scrollTop = previousScroll;
        updateWorkoutTimer();
        if (options.focusSelector) requestAnimationFrame(() => details.querySelector(options.focusSelector)?.focus());
    }

    async function loadActiveWorkoutSession() {
        const day = selectedWorkoutDay();
        workoutView.requestToken += 1;
        const token = workoutView.requestToken;
        workoutView.session = null;
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
        const viewVersion = ++workoutView.viewVersion;
        showGlobalLoading("Carregando detalhes do plano de treino...");
        try {
            const plan = await apiRequest(`/workout_plans/${apiSegment(id)}`);
            if (viewVersion !== workoutView.viewVersion) return null;
            const reopenSelectedDay = String(workoutView.plan?.id) === String(plan.id)
                ? workoutView.selectedDay
                : 0;
            workoutView.plan = plan;
            workoutView.days = normalizedWorkoutDays(plan);
            const preferredDayIndex = preferredDayId == null
                ? -1
                : workoutView.days.findIndex((day) => String(day.id) === String(preferredDayId));
            workoutView.selectedDay = preferredDayIndex >= 0
                ? preferredDayIndex
                : Math.min(reopenSelectedDay, Math.max(workoutView.days.length - 1, 0));
            workoutView.session = null;
            workoutView.sessionError = "";
            workoutView.pendingAction = "";
            workoutView.replacementPanels.clear();
            const title = byId("viewWorkoutPlanTitle");
            if (title) title.textContent = plan.title || "Plano de Treino";
            renderWorkoutDetail();
            openAppModal(byId("viewWorkoutPlanModal"));
            hideGlobalLoading();
            await loadActiveWorkoutSession();
            return plan;
        } catch (error) {
            if (viewVersion === workoutView.viewVersion) showToast(error.message, "error");
            return null;
        } finally {
            hideGlobalLoading();
        }
    }

    function findSelectedExercise(id) {
        return asArray(selectedWorkoutDay()?.exercises).find((exercise) => String(exercise.id) === String(id));
    }

    function replacementPayload(exercise) {
        return {
            unavailable_equipment: exercise.equipment ? [exercise.equipment] : [],
            available_equipment: []
        };
    }

    async function startWorkoutSession() {
        const day = selectedWorkoutDay();
        if (!day?.id || !workoutView.plan?.id || workoutView.pendingAction) return;
        const planId = workoutView.plan.id;
        const dayId = day.id;
        const viewVersion = workoutView.viewVersion;
        activeDockRequestToken += 1;
        workoutView.pendingAction = "start";
        workoutView.sessionError = "";
        renderWorkoutDetail({ preserveScroll: true });
        try {
            const result = await apiRequest(`/workout_plans/${apiSegment(workoutView.plan.id)}/days/${apiSegment(day.id)}/sessions`, { method: "POST" });
            if (viewVersion !== workoutView.viewVersion || String(workoutView.plan?.id) !== String(planId) || String(selectedWorkoutDay()?.id) !== String(dayId)) return;
            workoutView.session = result.session;
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
            if (viewVersion === workoutView.viewVersion && workoutView.pendingAction === "start") {
                workoutView.pendingAction = "";
                renderWorkoutDetail({ preserveScroll: true });
            }
        }
    }

    async function openReplacementOptions(exerciseId) {
        const exercise = findSelectedExercise(exerciseId);
        const session = workoutView.session;
        if (!exercise || !session) return;
        const viewVersion = workoutView.viewVersion;
        const key = String(exercise.id);
        const payload = replacementPayload(exercise);
        workoutView.replacementPanels.set(key, { loading: true, options: [], message: "", error: "", payload });
        renderWorkoutDetail({ preserveScroll: true, focusSelector: `#replacement-panel-${exercise.id}` });
        try {
            const result = await apiRequest(`/workout_sessions/${apiSegment(session.id)}/exercises/${apiSegment(exercise.id)}/replacement_options`, { method: "POST", body: payload });
            if (viewVersion !== workoutView.viewVersion || workoutView.session?.id !== session.id) return;
            workoutView.replacementPanels.set(key, {
                loading: false,
                options: asArray(result.options).slice(0, 3),
                message: result.message || "",
                error: "",
                payload
            });
        } catch (error) {
            if (viewVersion !== workoutView.viewVersion) return;
            workoutView.replacementPanels.set(key, { loading: false, options: [], message: "", error: error.message, payload });
        }
        if (viewVersion !== workoutView.viewVersion) return;
        renderWorkoutDetail({ preserveScroll: true, focusSelector: `#replacement-panel-${exercise.id}` });
    }

    async function applyReplacement(exerciseId, catalogKey) {
        const exercise = findSelectedExercise(exerciseId);
        const session = workoutView.session;
        const key = String(exerciseId);
        const panel = workoutView.replacementPanels.get(key);
        const option = asArray(panel?.options).find((item) => item.catalog_key === catalogKey);
        if (!exercise || !session || !panel || !option || panel.applying) return;
        const viewVersion = workoutView.viewVersion;
        activeDockRequestToken += 1;
        panel.applying = catalogKey;
        panel.error = "";
        renderWorkoutDetail({ preserveScroll: true });
        try {
            const result = await apiRequest(`/workout_sessions/${apiSegment(session.id)}/exercises/${apiSegment(exercise.id)}/replace`, {
                method: "POST",
                body: { ...panel.payload, catalog_key: catalogKey }
            });
            if (viewVersion !== workoutView.viewVersion || !isCurrentWorkoutSession(session.id)) return;
            const overrides = asArray(workoutView.session.overrides).filter((item) => String(item.workout_exercise_id) !== String(exercise.id));
            overrides.push(result.override);
            workoutView.session = { ...workoutView.session, overrides };
            if (String(activeWorkoutSummary?.session?.id || "") === String(session.id)) {
                activeWorkoutSummary = { ...activeWorkoutSummary, session: workoutView.session };
            }
            workoutView.replacementPanels.delete(key);
            showToast("Exercício trocado somente para esta sessão.", "success");
            renderWorkoutDetail({ preserveScroll: true, focusSelector: `[data-workout-action="restore-exercise"][data-exercise-id="${exercise.id}"]` });
        } catch (error) {
            if (viewVersion !== workoutView.viewVersion) return;
            panel.applying = "";
            panel.error = error.message;
            renderWorkoutDetail({ preserveScroll: true, focusSelector: `#replacement-panel-${exercise.id}` });
        }
    }

    async function restoreExercise(exerciseId) {
        const exercise = findSelectedExercise(exerciseId);
        const session = workoutView.session;
        if (!exercise || !session || workoutView.pendingAction) return;
        const actionKey = `restore-${exercise.id}`;
        const viewVersion = workoutView.viewVersion;
        activeDockRequestToken += 1;
        workoutView.pendingAction = actionKey;
        renderWorkoutDetail({ preserveScroll: true });
        try {
            await apiRequest(`/workout_sessions/${apiSegment(session.id)}/exercises/${apiSegment(exercise.id)}/replace`, { method: "DELETE" });
            if (viewVersion !== workoutView.viewVersion || !isCurrentWorkoutSession(session.id)) return;
            workoutView.session = {
                ...workoutView.session,
                overrides: asArray(workoutView.session.overrides).filter((item) => String(item.workout_exercise_id) !== String(exercise.id))
            };
            if (String(activeWorkoutSummary?.session?.id || "") === String(session.id)) {
                activeWorkoutSummary = { ...activeWorkoutSummary, session: workoutView.session };
            }
            showToast("Exercício original restaurado.", "success");
        } catch (error) {
            if (viewVersion === workoutView.viewVersion) workoutView.sessionError = error.message;
        } finally {
            if (viewVersion === workoutView.viewVersion && workoutView.pendingAction === actionKey) {
                workoutView.pendingAction = "";
                renderWorkoutDetail({ preserveScroll: true });
            }
        }
    }

    async function completeWorkoutExercise(exerciseId) {
        const exercise = findSelectedExercise(exerciseId);
        const session = workoutView.session;
        if (!exercise || !session || workoutView.pendingAction) return;
        const actionKey = `complete-${exercise.id}`;
        const viewVersion = workoutView.viewVersion;
        activeDockRequestToken += 1;
        workoutView.pendingAction = actionKey;
        workoutView.sessionError = "";
        renderWorkoutDetail({ preserveScroll: true });
        try {
            const result = await apiRequest(`/workout_sessions/${apiSegment(session.id)}/exercises/${apiSegment(exercise.id)}/complete`, { method: "POST" });
            if (String(activeWorkoutSummary?.session?.id || "") === String(session.id)) {
                activeWorkoutSummary = { ...activeWorkoutSummary, session: result.session };
            }
            if (viewVersion !== workoutView.viewVersion || !isCurrentWorkoutSession(session.id)) return;
            workoutView.session = result.session;
            workoutView.replacementPanels.delete(String(exercise.id));
            showToast("Exercício concluído. Vamos para o próximo!", "success");
        } catch (error) {
            if (viewVersion === workoutView.viewVersion) workoutView.sessionError = error.message;
        } finally {
            if (viewVersion === workoutView.viewVersion && workoutView.pendingAction === actionKey) {
                workoutView.pendingAction = "";
                renderWorkoutDetail();
                requestAnimationFrame(() => (byId("currentExerciseTitle") || byId("workoutCompleteTitle"))?.focus());
            }
        }
    }

    async function finishWorkoutSession() {
        const session = workoutView.session;
        if (!session || workoutView.pendingAction || !window.confirm("Finalizar o treino de hoje?")) return;
        const actionKey = "finish";
        const viewVersion = workoutView.viewVersion;
        activeDockRequestToken += 1;
        workoutView.pendingAction = actionKey;
        renderWorkoutDetail({ preserveScroll: true });
        try {
            await apiRequest(`/workout_sessions/${apiSegment(session.id)}/finish`, { method: "POST" });
            if (String(activeWorkoutSummary?.session?.id || "") === String(session.id)) clearActiveWorkoutDock();
            if (viewVersion !== workoutView.viewVersion || !isCurrentWorkoutSession(session.id)) return;
            workoutView.session = null;
            clearActiveWorkoutDock();
            workoutView.replacementPanels.clear();
            showToast("Treino finalizado. Excelente trabalho!", "success");
        } catch (error) {
            if (viewVersion === workoutView.viewVersion) workoutView.sessionError = error.message;
        } finally {
            if (viewVersion === workoutView.viewVersion && workoutView.pendingAction === actionKey) {
                workoutView.pendingAction = "";
                renderWorkoutDetail({ preserveScroll: true });
            }
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
        loadIngredientPool();
        if (!workoutTimerInterval) workoutTimerInterval = window.setInterval(updateWorkoutTimer, 1000);
        if (!workoutSyncInterval) {
            workoutSyncInterval = window.setInterval(() => {
                if (!byId("mainScreen")?.classList.contains("hidden")) loadActiveWorkoutDock();
            }, 30000);
        }
        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "visible" && !byId("mainScreen")?.classList.contains("hidden")) {
                loadActiveWorkoutDock();
            }
        });
        byId("activeWorkoutDock")?.addEventListener("click", openActiveWorkout);
        ["workoutGoalFilter", "workoutExperienceFilter", "workoutDaysFilter"].forEach((id) => {
            byId(id)?.addEventListener("change", renderFilteredWorkoutPlans);
        });

        document.addEventListener("click", (event) => {
            const wizardTrigger = event.target.closest("[data-plan-wizard]");
            if (wizardTrigger) {
                event.preventDefault();
                openPlanWizard(wizardTrigger.dataset.planWizard);
                return;
            }
            const planAction = event.target.closest("[data-plan-action]");
            if (!planAction) return;
            const { planAction: action, planType: type, planId: id } = planAction.dataset;
            if (action === "view") {
                if (type === "diet") viewDietPlan(id);
                else viewWorkoutPlan(id);
            }
            if (action === "delete") deletePlan(type, id);
        });

        byId("viewDietPlanDetails")?.addEventListener("click", (event) => {
            const tab = event.target.closest("[data-diet-day-index]");
            if (!tab) return;
            const index = Number(tab.dataset.dietDayIndex);
            if (!Number.isInteger(index)) return;
            dietView.selectedDay = index;
            renderDietDetail();
            requestAnimationFrame(() => byId(`diet-day-tab-${index}`)?.focus());
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
            const exerciseId = control.dataset.exerciseId;
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
            } else if (action === "replacement-options") {
                await openReplacementOptions(exerciseId);
            } else if (action === "close-replacements") {
                workoutView.replacementPanels.delete(String(exerciseId));
                renderWorkoutDetail({ preserveScroll: true, focusSelector: `[data-workout-action="replacement-options"][data-exercise-id="${exerciseId}"]` });
            } else if (action === "apply-replacement") {
                await applyReplacement(exerciseId, control.dataset.catalogKey);
            } else if (action === "restore-exercise") {
                await restoreExercise(exerciseId);
            } else if (action === "complete-exercise") {
                await completeWorkoutExercise(exerciseId);
            } else if (action === "finish-session") {
                await finishWorkoutSession();
            }
        });
        byId("viewWorkoutPlanDetails")?.addEventListener("keydown", async (event) => {
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
    }

    window.openPlanWizard = openPlanWizard;
    window.handlePlanChatAction = handlePlanChatAction;
    window.loadDietPlans = loadDietPlans;
    window.loadWorkoutPlans = loadWorkoutPlans;
    window.viewDietPlan = viewDietPlan;
    window.viewWorkoutPlan = viewWorkoutPlan;
    window.loadActiveWorkoutDock = loadActiveWorkoutDock;
    window.clearActiveWorkoutDock = clearActiveWorkoutDock;
    window.invalidateWorkoutView = invalidateWorkoutView;

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initializePlanExperience);
    else initializePlanExperience();
})();
