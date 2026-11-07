(function () {
    "use strict";
    const byId = id => document.getElementById(id);
    const esc = value => escapeHtml(String(value ?? ""));
    const segment = value => encodeURIComponent(String(value));
    let version = 0;
    let consentVersion = null;
    const pending = new Set();
    async function api(path, options = {}) {
        const current = version;
        const response = await fetch(`${API_BASE}${path}`, { method: options.method || "GET", credentials: "include", headers: options.body ? { "Content-Type": "application/json" } : {}, body: options.body ? JSON.stringify(options.body) : undefined });
        const data = await response.json();
        if (current !== version) throw new Error("A sessão mudou. Abra o acompanhamento novamente.");
        if (!response.ok) throw new Error(data.error || "Não foi possível concluir. Tente novamente.");
        return data;
    }
    async function openProfessionalCompanion() {
        const current = version;
        if (!window.currentUser) { window.requireAuth?.("Entre para gerenciar seu acompanhamento.", { resume: openProfessionalCompanion }); return; }
        openAppModal(byId("professionalCompanionModal"));
        byId("professionalCompanionMessage").textContent = "Carregando acompanhamento…";
        try {
            const [links, inbox] = await Promise.all([api("/professional-relationships"), api("/professional-plans/inbox")]);
            consentVersion = links.data_sharing_consent_version;
            byId("professionalCompanionLinks").innerHTML = (links.relationships || []).map(link => `<article><strong>${esc(link.professional?.username || link.professional_name || "Profissional")}</strong><span>${link.status === "pending" ? "Solicitação aguardando confirmação" : "Acompanhamento ativo"}</span><button type="button" class="btn-secondary" onclick="changeProfessionalRelationship('${esc(link.id)}')">Encerrar vínculo</button></article>`).join("") || "<p>Você ainda não tem profissionais vinculados. Encontre um pelo usuário ou código.</p>";
            const plans = [...(inbox.workout_plans || []).map(plan => ({ ...plan, kind: "workout" })), ...(inbox.diet_plans || []).map(plan => ({ ...plan, kind: "diet" }))];
            byId("professionalCompanionInbox").innerHTML = plans.map(plan => `<article><small>${plan.kind === "diet" ? "Dieta" : "Treino"} · ${esc(plan.professional?.username || plan.created_by_professional?.username || "Seu profissional")}</small><strong>${esc(plan.title)}</strong><p>${esc(plan.description || "Confira o conteúdo antes de aceitar.")}</p><button type="button" class="btn-primary" onclick="reviewProfessionalReceivedPlan('${plan.kind}', '${esc(plan.id)}')">Revisar e decidir</button><button type="button" class="btn-secondary" onclick="declineProfessionalPlan('${plan.kind}', '${esc(plan.id)}')">Recusar plano</button></article>`).join("") || "<p>Nenhum plano aguardando aceite.</p>";
            byId("professionalCompanionMessage").textContent = "Você pode ter até dois profissionais. Um plano só entra na Home quando você escolhe usá-lo.";
        } catch (error) { if (current === version) byId("professionalCompanionMessage").textContent = error.message; }
    }
    async function searchProfessionalProfiles(event) {
        const current = version;
        event.preventDefault();
        const query = byId("professionalCompanionQuery").value.trim();
        if (!query) return;
        const results = byId("professionalCompanionResults");
        results.textContent = "Buscando…";
        try {
            const data = await api(`/professionals/search?q=${segment(query)}`);
            results.innerHTML = (data.items || data.professionals || []).map(profile => `<article><strong>${esc(profile.username)}</strong><span>${esc(profile.professional_code || profile.code || "")}</span><button type="button" class="btn-primary" onclick="requestProfessionalProfile('${esc(profile.id)}')">Solicitar acompanhamento</button></article>`).join("") || "<p>Nenhum profissional encontrado. Confira o usuário ou código.</p>";
        } catch (error) { if (current === version) results.textContent = error.message; }
    }
    async function requestProfessionalProfile(id) {
        const current = version;
        if (pending.has(id)) return;
        if (!window.confirm("Solicitar acompanhamento? Ao aceitar, o profissional poderá consultar os dados de acompanhamento autorizados e preparar treinos e dietas para você. Cada plano continuará dependendo do seu aceite.")) return;
        pending.add(id);
        try {
            await api(`/professionals/${segment(id)}/requests`, { method: "POST", body: { data_sharing_consent: true, data_sharing_consent_version: consentVersion } });
            showToast("Solicitação enviada. Aguarde a confirmação do profissional.", "success");
            await openProfessionalCompanion();
        } catch (error) { if (current === version) byId("professionalCompanionMessage").textContent = error.message; }
        finally { if (current === version) pending.delete(id); }
    }
    async function changeProfessionalRelationship(id) {
        const current = version;
        if (pending.has(id) || !window.confirm("Encerrar este vínculo? O profissional deixará de acompanhar sua conta. Os planos já aceitos ficam preservados.")) return;
        pending.add(id);
        try { await api(`/professional-relationships/${segment(id)}`, { method: "DELETE" }); await openProfessionalCompanion(); }
        catch (error) { if (current === version) byId("professionalCompanionMessage").textContent = error.message; }
        finally { if (current === version) pending.delete(id); }
    }
    async function reviewProfessionalReceivedPlan(type, id) {
        closeAppModal(byId("professionalCompanionModal"));
        if (type === "diet") await window.viewDietPlan(id);
        else await window.viewWorkoutPlan(id);
    }
    async function declineProfessionalPlan(type, id) {
        const current = version;
        if (pending.has(id) || !window.confirm("Recusar este plano? Sua Home continuará como está.")) return;
        pending.add(id);
        try { await api(`/professional-plans/${type}/${segment(id)}/decline`, { method: "POST", body: {} }); await openProfessionalCompanion(); }
        catch (error) { if (current === version) byId("professionalCompanionMessage").textContent = error.message; }
        finally { if (current === version) pending.delete(id); }
    }
    async function loadProfessionalRequests() {
        const current = version;
        if (!window.ProfessionalWorkspace?.hasAccess()) return;
        try {
            const data = await api("/professional/requests");
            byId("professionalIncomingRequests").innerHTML = (data.items || data.requests || []).map(request => `<article><strong>${esc(request.student?.username || request.username || "Aluno")}</strong><p>Quer receber seu acompanhamento.</p><button type="button" class="btn-primary" onclick="acceptProfessionalRequest('${esc(request.id)}')">Aceitar aluno</button></article>`).join("");
        } catch (error) { if (current === version) byId("professionalIncomingRequests").textContent = error.message; }
    }
    async function acceptProfessionalRequest(id) {
        const current = version;
        if (pending.has(id)) return;
        pending.add(id);
        try { await api(`/professional/requests/${segment(id)}/accept`, { method: "POST", body: {} }); await loadProfessionalRequests(); if (current === version) await window.loadProfessionalDashboard(); }
        catch (error) { if (current === version) showToast(error.message, "error"); }
        finally { if (current === version) pending.delete(id); }
    }
    Object.assign(window, { openProfessionalCompanion, searchProfessionalProfiles, requestProfessionalProfile, changeProfessionalRelationship, reviewProfessionalReceivedPlan, declineProfessionalPlan, loadProfessionalRequests, acceptProfessionalRequest });
    window.addEventListener("diettracker:auth-ready", () => {
        version += 1; consentVersion = null; pending.clear();
        ["professionalCompanionLinks", "professionalCompanionInbox", "professionalCompanionResults", "professionalIncomingRequests"].forEach(id => { if (byId(id)) byId(id).innerHTML = ""; });
        if (byId("professionalCompanionModal")) closeAppModal(byId("professionalCompanionModal"));
    });
}());
