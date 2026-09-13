(function () {
    "use strict";

    const byId = (id) => document.getElementById(id);
    const esc = (value) => escapeHtml(value == null ? "" : String(value));
    const asArray = (value) => Array.isArray(value) ? value : [];
    const focusLabels = {
        structure: "Estrutura", volume: "Volume", exercises: "Exercícios", progression: "Progressão",
        goal_fit: "Adequação ao objetivo", limitations: "Limitações e dificuldades", portions: "Porções",
        foods: "Seleção de alimentos", routine: "Adequação à rotina",
    };
    let linkedProfessional = null;
    let activeReview = null;

    async function api(path, options = {}) {
        const response = await fetch(`${API_BASE}${path}`, {
            method: options.method || "GET",
            credentials: "include",
            headers: options.body === undefined ? {} : { "Content-Type": "application/json" },
            body: options.body === undefined ? undefined : JSON.stringify(options.body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Não foi possível concluir a revisão.");
        return data;
    }

    function reviewStatus(status) {
        return { pending: "Pendente", accepted: "Aceita", in_review: "Em revisão", completed: "Concluída", declined: "Recusada", cancelled: "Cancelada", expired: "Expirada" }[status] || status;
    }

    async function openPlanReviewRequest(planType, planId) {
        if (!requireAuth("Entre para solicitar uma revisão.", { resume: () => openPlanReviewRequest(planType, planId) })) return;
        byId("reviewPlanType").value = planType;
        byId("reviewPlanId").value = planId;
        byId("reviewStudentNote").value = "";
        byId("reviewDataConsent").checked = false;
        byId("planReviewRequestMessage").textContent = "";
        const keys = planType === "workout"
            ? ["structure", "volume", "exercises", "progression", "goal_fit", "limitations"]
            : ["structure", "portions", "foods", "routine", "goal_fit", "limitations"];
        byId("reviewFocusOptions").innerHTML = keys.map((key) => `<label><input type="checkbox" name="reviewFocus" value="${key}"><span>${esc(focusLabels[key])}</span></label>`).join("");
        try {
            const result = await api("/professional-relationship");
            linkedProfessional = result.relationship?.professional || null;
        } catch (error) {
            linkedProfessional = null;
        }
        const linkedRadio = document.querySelector('input[name="reviewTargetMode"][value="linked"]');
        linkedRadio.disabled = !linkedProfessional;
        byId("linkedProfessionalLabel").textContent = linkedProfessional ? linkedProfessional.username : "Nenhum profissional vinculado";
        const initialMode = linkedProfessional ? "linked" : "specific";
        document.querySelector(`input[name="reviewTargetMode"][value="${initialMode}"]`).checked = true;
        byId("reviewSpecificGroup").classList.toggle("hidden", initialMode !== "specific");
        openAppModal(byId("planReviewRequestModal"));
    }

    async function resolveSpecificProfessional(username, planType) {
        const result = await api(`/profiles/search?q=${encodeURIComponent(username)}&limit=20`);
        return asArray(result.items).find((item) => item.username.toLowerCase() === username.toLowerCase()
            && item.is_professional
            && (planType === "workout" ? item.accepts_external_workout_reviews : item.accepts_external_diet_reviews));
    }

    async function submitReviewRequest(event) {
        event.preventDefault();
        const message = byId("planReviewRequestMessage");
        const planType = byId("reviewPlanType").value;
        const targetMode = document.querySelector('input[name="reviewTargetMode"]:checked')?.value;
        const body = {
            plan_type: planType,
            plan_id: Number(byId("reviewPlanId").value),
            target_mode: targetMode,
            review_focus: Array.from(document.querySelectorAll('input[name="reviewFocus"]:checked')).map((item) => item.value),
            student_note: byId("reviewStudentNote").value,
            data_sharing_consent: byId("reviewDataConsent").checked,
            sharing_consent_version: legalVersions?.professional_sharing?.version,
        };
        try {
            if (targetMode === "specific") {
                const username = byId("reviewSpecificUsername").value.trim();
                const professional = await resolveSpecificProfessional(username, planType);
                if (!professional) throw new Error("Profissional público e disponível não encontrado.");
                body.professional_id = professional.id;
            }
            const result = await api("/plan-reviews", { method: "POST", body });
            closeAppModal(byId("planReviewRequestModal"));
            showToast("Revisão solicitada.", "success");
            if (window.openNetworkCenter) await window.openNetworkCenter(result.review?.id);
            else loadReviewInbox(result.review?.id);
        } catch (error) {
            message.textContent = error.message;
        }
    }

    function reviewCard(review, professionalView = false) {
        const person = professionalView ? review.student : review.professional;
        return `<article class="network-card review-card" data-review-id="${esc(review.id)}"><div class="network-card__avatar"><i class="fas ${review.plan_type === "workout" ? "fa-dumbbell" : "fa-utensils"}"></i></div><div><strong>${review.plan_type === "workout" ? "Revisão de treino" : "Revisão de dieta"}</strong><small>${esc(reviewStatus(review.status))}${person?.username ? ` · ${esc(person.username)}` : " · Solicitação aberta"}</small></div><div class="network-card__actions"><button type="button" class="btn-secondary" data-review-open="${esc(review.id)}">Abrir</button></div></article>`;
    }

    async function loadReviewInbox(highlightReviewId) {
        if (!currentUser) return;
        const container = byId("reviewInbox");
        if (!container) return;
        try {
            const own = await api("/plan-reviews?limit=30");
            let professionalItems = [];
            let openItems = [];
            if (currentUser.professional_entitled) {
                const [assigned, open] = await Promise.all([
                    api("/professional/plan-reviews?limit=30"),
                    api("/professional/plan-reviews/open"),
                ]);
                professionalItems = asArray(assigned.items);
                openItems = asArray(open.items);
            }
            const incomingCount = professionalItems.filter((item) => item.status === "pending").length + openItems.length;
            window.setNetworkReviewCount?.(incomingCount);
            const cards = [
                ...asArray(own.items).map((item) => reviewCard(item)),
                ...professionalItems.map((item) => reviewCard(item, true)),
                ...openItems.map((item) => `<article class="network-card review-card"><div class="network-card__avatar"><i class="fas ${item.plan_type === "workout" ? "fa-dumbbell" : "fa-utensils"}"></i></div><div><strong>Revisão aberta de ${item.plan_type === "workout" ? "treino" : "dieta"}</strong><small>${asArray(item.review_focus).map((key) => focusLabels[key]).join(" · ")}</small></div><button type="button" class="btn-primary" data-review-accept="${esc(item.id)}">Aceitar</button></article>`),
            ];
            container.innerHTML = cards.length ? cards.join("") : '<p class="empty-state">Nenhuma revisão no momento.</p>';
            if (highlightReviewId) {
                const card = Array.from(container.querySelectorAll("[data-review-id]")).find(
                    (item) => item.dataset.reviewId === String(highlightReviewId)
                );
                if (card) {
                    card.classList.add("review-card--new");
                    card.scrollIntoView({
                        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
                        block: "center",
                    });
                    card.querySelector("[data-review-open]")?.focus({ preventScroll: true });
                    window.setTimeout(() => card.classList.remove("review-card--new"), 3000);
                }
            }
        } catch (error) {
            container.innerHTML = `<p class="session-inline-error">${esc(error.message)}</p>`;
        }
    }

    function renderPlanSnapshot(plan, label) {
        if (!plan) return `<section class="review-plan"><h4>${esc(label)}</h4><p>Sem proposta estrutural.</p></section>`;
        const workoutDays = asArray(plan.days);
        const dietMeals = asArray(plan.meals);
        const content = workoutDays.length
            ? workoutDays.map((day) => `<div><strong>${esc(day.title)}</strong>${asArray(day.exercises).map((exercise) => `<p>${esc(exercise.name)} · ${esc(exercise.sets)} × ${esc(exercise.reps)} · ${esc(exercise.rest_seconds)}s</p>`).join("")}</div>`).join("")
            : ["Dia 1", "Dia 2", "Dia 3"].map((day) => `<div><strong>${day}</strong>${dietMeals.filter((meal) => meal.day_of_week === day).map((meal) => `<p>${esc(meal.meal_type)} · ${esc(window.formatDietPlanItemsText?.(meal) || asArray(meal.items).map((item) => typeof item === "object" ? item.name : item).join(", ") || meal.description)}</p>`).join("")}</div>`).join("");
        return `<section class="review-plan"><h4>${esc(label)}</h4><h5>${esc(plan.title)}</h5>${content}</section>`;
    }

    function professionalActions(review) {
        if (!currentUser?.professional_entitled || String(review.student?.id) === String(currentUser.id)) return "";
        if (review.status === "pending") return `<div class="modal-actions"><button class="btn-secondary" data-review-decline="${esc(review.id)}">Recusar</button><button class="btn-primary" data-review-accept="${esc(review.id)}">Aceitar</button></div>`;
        if (review.status === "accepted") return `<div class="modal-actions"><button class="btn-primary" data-review-start="${esc(review.id)}">Iniciar revisão</button></div>`;
        if (review.status !== "in_review") return "";
        return `<section class="review-completion"><button type="button" class="btn-secondary" data-review-edit="${esc(review.id)}"><i class="fas fa-pen"></i> Propor alterações</button><label>Avaliação<textarea id="reviewEvaluation" rows="5" maxlength="5000"></textarea></label><label>Sugestões, uma por linha<textarea id="reviewSuggestions" rows="4"></textarea></label><div class="review-outcomes"><label><input type="radio" name="reviewOutcome" value="approved_as_is" checked> Aprovar como está</label><label><input type="radio" name="reviewOutcome" value="changes_proposed"> Enviar alterações propostas</label></div><button type="button" class="btn-primary" data-review-complete="${esc(review.id)}">Concluir revisão</button></section>`;
    }

    function studentActions(review) {
        if (String(review.student?.id) !== String(currentUser?.id)) return "";
        if (["pending", "accepted", "in_review"].includes(review.status)) return `<div class="modal-actions"><button type="button" class="btn-secondary" data-review-cancel="${esc(review.id)}">Cancelar solicitação</button></div>`;
        if (review.status !== "completed" || review.student_decision !== "pending") return "";
        const schedule = review.plan_type === "workout" && review.outcome === "changes_proposed" ? '<label>Dias da semana da nova agenda (0=segunda, 6=domingo)<input id="reviewWeekdays" placeholder="0, 2, 4"></label>' : "";
        return `<section class="review-decision">${schedule}<div class="modal-actions"><button type="button" class="btn-secondary" data-review-reject="${esc(review.id)}">Manter plano atual</button><button type="button" class="btn-primary" data-review-apply="${esc(review.id)}">${review.outcome === "changes_proposed" ? "Aplicar proposta" : "Confirmar revisão"}</button></div></section>`;
    }

    async function openPlanReviewDetails(reviewId) {
        openAppModal(byId("planReviewDetailsModal"));
        const container = byId("planReviewDetails");
        container.innerHTML = '<div class="plans-loading"><i class="fas fa-spinner fa-spin"></i><span>Carregando revisão...</span></div>';
        try {
            const result = await api(`/plan-reviews/${encodeURIComponent(reviewId)}`);
            activeReview = result.review;
            const review = activeReview;
            const planLabel = review.plan_type === "workout" ? "Treino" : "Dieta";
            container.innerHTML = `<div class="review-status"><span>${esc(reviewStatus(review.status))}</span><small>${review.professional?.username ? `Profissional: ${esc(review.professional.username)}` : "Aguardando profissional"}</small></div>${review.student_note ? `<blockquote>${esc(review.student_note)}</blockquote>` : ""}${review.evaluation ? `<section class="review-evaluation"><h4>Avaliação profissional</h4><p>${esc(review.evaluation)}</p>${asArray(review.suggestions).length ? `<ul>${review.suggestions.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>` : ""}</section>` : ""}<div class="review-comparison">${renderPlanSnapshot(review.original, `${planLabel} original`)}${renderPlanSnapshot(review.proposal, "Proposta profissional")}</div>${professionalActions(review)}${studentActions(review)}`;
        } catch (error) {
            container.innerHTML = `<p class="session-inline-error">${esc(error.message)}</p>`;
        }
    }

    async function action(path, body = {}) {
        try {
            const result = await api(path, { method: "POST", body });
            showToast(result.message, "success");
            if (result.review) openPlanReviewDetails(result.review.id);
            loadReviewInbox();
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    document.querySelectorAll('input[name="reviewTargetMode"]').forEach((input) => input.addEventListener("change", () => byId("reviewSpecificGroup").classList.toggle("hidden", input.value !== "specific" || !input.checked)));
    byId("planReviewRequestForm")?.addEventListener("submit", submitReviewRequest);
    document.addEventListener("click", (event) => {
        const open = event.target.closest("[data-review-open]");
        if (open) openPlanReviewDetails(open.dataset.reviewOpen);
        const accept = event.target.closest("[data-review-accept]");
        if (accept) action(`/professional/plan-reviews/${accept.dataset.reviewAccept}/accept`);
        const decline = event.target.closest("[data-review-decline]");
        if (decline) action(`/professional/plan-reviews/${decline.dataset.reviewDecline}/decline`);
        const cancel = event.target.closest("[data-review-cancel]");
        if (cancel && window.confirm("Cancelar esta solicitação de revisão?")) action(`/plan-reviews/${cancel.dataset.reviewCancel}/cancel`);
        const start = event.target.closest("[data-review-start]");
        if (start) action(`/professional/plan-reviews/${start.dataset.reviewStart}/start`);
        const edit = event.target.closest("[data-review-edit]");
        if (edit && activeReview) window.openProfessionalReviewEditor?.(activeReview);
        const complete = event.target.closest("[data-review-complete]");
        if (complete) action(`/professional/plan-reviews/${complete.dataset.reviewComplete}/complete`, {
            evaluation: byId("reviewEvaluation")?.value,
            suggestions: String(byId("reviewSuggestions")?.value || "").split("\n").map((item) => item.trim()).filter(Boolean),
            outcome: document.querySelector('input[name="reviewOutcome"]:checked')?.value,
        });
        const reject = event.target.closest("[data-review-reject]");
        if (reject) action(`/plan-reviews/${reject.dataset.reviewReject}/decision`, { decision: "reject" });
        const apply = event.target.closest("[data-review-apply]");
        if (apply) action(`/plan-reviews/${apply.dataset.reviewApply}/decision`, {
            decision: "apply",
            weekdays: String(byId("reviewWeekdays")?.value || "").split(",").map((item) => item.trim()).filter(Boolean).map(Number),
        });
    });

    window.openPlanReviewRequest = openPlanReviewRequest;
    window.openPlanReviewDetails = openPlanReviewDetails;
    window.loadReviewInbox = loadReviewInbox;
})();
