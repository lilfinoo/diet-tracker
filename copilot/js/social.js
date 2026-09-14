(function () {
    "use strict";

    const byId = (id) => document.getElementById(id);
    const esc = (value) => escapeHtml(value == null ? "" : String(value));
    const asArray = (value) => Array.isArray(value) ? value : [];

    function renderRequestCount() {
        const count = byId("networkRequestCount");
        if (!count) return;
        const total = Number(count.dataset.connections || 0) + Number(count.dataset.reviews || 0);
        count.textContent = String(total);
        count.classList.toggle("hidden", !total);
    }

    function setNetworkReviewCount(value) {
        const count = byId("networkRequestCount");
        if (count) count.dataset.reviews = String(Number(value) || 0);
        renderRequestCount();
    }

    async function api(path, options = {}) {
        const response = await fetch(`${API_BASE}${path}`, {
            method: options.method || "GET",
            credentials: "include",
            headers: options.body === undefined ? {} : { "Content-Type": "application/json" },
            body: options.body === undefined ? undefined : JSON.stringify(options.body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Não foi possível atualizar sua rede.");
        return data;
    }

    function showAvatar(url) {
        const initial = String(currentUser?.username || "U").charAt(0).toUpperCase();
        [["headerUserAvatar", "headerUserInitial"], ["homeUserAvatar", "homeUserInitial"], ["profileUserAvatar", "profileUserInitial"]].forEach(([imageId, fallbackId]) => {
            const image = byId(imageId);
            const fallback = byId(fallbackId);
            if (image) {
                image.src = url || "";
                image.classList.toggle("hidden", !url);
            }
            fallback?.classList.toggle("hidden", Boolean(url));
        });
        const preview = byId("networkAvatarPreview");
        if (preview) {
            preview.src = url || "";
            preview.classList.toggle("hidden", !url);
        }
        const previewFallback = byId("networkAvatarFallback");
        if (previewFallback) {
            previewFallback.textContent = initial;
            previewFallback.classList.toggle("hidden", Boolean(url));
        }
    }

    function connectionActions(profile) {
        const actions = [];
        if (profile.is_professional) actions.push(`<button type="button" class="btn-primary" data-network-connect="request_professional" data-network-username="${esc(profile.username)}">Solicitar acompanhamento</button>`);
        if (currentUser?.professional_entitled) actions.push(`<button type="button" class="btn-secondary" data-network-connect="invite_student" data-network-username="${esc(profile.username)}">Convidar como aluno</button>`);
        return actions.join("");
    }

    function profileCard(profile) {
        const initial = esc(String(profile.username || "U").charAt(0).toUpperCase());
        return `<article class="network-card"><div class="network-card__avatar">${profile.avatar_url ? `<img src="${esc(profile.avatar_url)}" alt="">` : `<span>${initial}</span>`}</div><div><strong>${esc(profile.username)}</strong><small>${profile.is_professional ? `Profissional · ${esc(profile.professional_scope || "")}` : "Aluno"}</small></div><div class="network-card__actions">${connectionActions(profile)}</div></article>`;
    }

    async function search() {
        const container = byId("networkSearchResults");
        const query = byId("networkSearchInput")?.value.trim();
        if (!container || !query) return;
        container.innerHTML = '<div class="plans-loading"><i class="fas fa-spinner fa-spin"></i><span>Buscando...</span></div>';
        try {
            const result = await api(`/profiles/search?q=${encodeURIComponent(query)}&limit=20`);
            const profiles = asArray(result.items).filter((item) => String(item.id) !== String(currentUser?.id));
            container.innerHTML = profiles.length ? profiles.map(profileCard).join("") : '<p class="empty-state">Nenhum perfil público encontrado.</p>';
        } catch (error) {
            container.innerHTML = `<p class="session-inline-error">${esc(error.message)}</p>`;
        }
    }

    async function connect(username, direction) {
        const studentIsRequester = direction === "request_professional";
        if (studentIsRequester && !window.confirm("Ao continuar, você autoriza este profissional a acompanhar seus dados de treino, dieta e medidas enquanto o vínculo estiver ativo.")) return;
        try {
            await api("/connections", {
                method: "POST",
                body: {
                    username,
                    direction,
                    data_sharing_consent: studentIsRequester,
                    sharing_consent_version: studentIsRequester ? legalVersions?.professional_sharing?.version : null,
                },
            });
            showToast("Solicitação enviada.", "success");
            loadInbox();
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    function relationshipCard(item) {
        const currentId = String(currentUser?.id);
        const incoming = String(item.initiated_by_user_id || "") !== currentId;
        const counterpart = String(item.professional?.id) === currentId ? item.student : item.professional;
        const actions = item.status === "pending" && incoming
            ? `<button type="button" class="btn-primary" data-connection-accept="${esc(item.id)}">Aceitar</button><button type="button" class="btn-secondary" data-connection-decline="${esc(item.id)}">Recusar</button>`
            : item.status === "pending" ? `<button type="button" class="btn-link" data-connection-cancel="${esc(item.id)}">Cancelar</button>` : "";
        return `<article class="network-card"><div class="network-card__avatar"><span>${esc(String(counterpart?.username || "U").charAt(0).toUpperCase())}</span></div><div><strong>${esc(counterpart?.username || "Usuário")}</strong><small>${item.status === "pending" ? (incoming ? "Solicitação recebida" : "Aguardando resposta") : `Vínculo ${esc(item.status)}`}</small></div><div class="network-card__actions">${actions}</div></article>`;
    }

    async function loadInbox() {
        if (!currentUser) return;
        const container = byId("networkInbox");
        try {
            const result = await api("/connections");
            const items = asArray(result.items);
            const incoming = items.filter((item) => item.status === "pending" && String(item.initiated_by_user_id || "") !== String(currentUser.id));
            const count = byId("networkRequestCount");
            if (count) {
                count.dataset.connections = String(incoming.length);
                renderRequestCount();
            }
            byId("networkHeaderButton")?.classList.remove("hidden");
            if (container) container.innerHTML = items.length ? items.map(relationshipCard).join("") : '<p class="empty-state">Nenhuma solicitação no momento.</p>';
        } catch (error) {
            if (container) container.innerHTML = `<p class="session-inline-error">${esc(error.message)}</p>`;
        }
    }

    async function updateSettings() {
        try {
            const result = await api("/profile/public", {
                method: "PUT",
                body: {
                    is_public: Boolean(byId("publicProfileToggle")?.checked),
                    accepts_external_workout_reviews: Boolean(byId("externalReviewsToggle")?.checked),
                    accepts_external_diet_reviews: Boolean(byId("externalDietReviewsToggle")?.checked),
                },
            });
            currentUser.is_public = result.profile.is_public;
            showToast("Preferências públicas atualizadas.", "success");
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    async function uploadPhoto(file) {
        const input = byId("networkAvatarInput");
        if (input?.dataset.uploading) return;
        if (!file || !file.type.startsWith("image/")) { showToast("Selecione um arquivo de imagem.", "error"); return; }
        if (file.size > 12 * 1024 * 1024) { showToast("A foto deve ter no máximo 12 MB.", "error"); return; }
        input?.setAttribute("aria-busy", "true");
        if (input) input.dataset.uploading = "true";
        if (input) input.disabled = true;
        const form = new FormData();
        try {
            const image = await downscaleImageFile(file, 1200);
            const blob = await fetch(image.dataUrl).then(response => response.blob());
            form.append("photo", blob, "avatar.jpg");
        } catch (error) {
            showToast("Não foi possível preparar a foto. Escolha JPG/PNG ou tente outra imagem.", "error");
            delete input?.dataset.uploading;
            if (input) input.disabled = false;
            input?.removeAttribute("aria-busy");
            return;
        }
        try {
            const response = await window.fetchWithTimeout(`${API_BASE}/profile/avatar`, { method: "POST", credentials: "include", body: form }, 60_000);
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || "Não foi possível atualizar a foto.");
            currentUser.avatar_url = data.avatar_url;
            showAvatar(data.avatar_url);
            showToast(data.message, "success");
        } catch (error) {
            showToast(error.message, "error");
        } finally {
            delete input?.dataset.uploading;
            if (input) input.disabled = false;
            input?.removeAttribute("aria-busy");
        }
    }

    async function removePhoto() {
        const input = byId("networkAvatarInput");
        if (input?.dataset.uploading) return;
        if (input) input.dataset.uploading = "true";
        try {
            const result = await api("/profile/avatar", { method: "DELETE", body: {} });
            currentUser.avatar_url = null;
            showAvatar(null);
            showToast(result.message, "success");
        } catch (error) {
            showToast(error.message, "error");
        } finally {
            delete input?.dataset.uploading;
        }
    }

    async function openNetworkCenter(highlightReviewId) {
        if (!requireAuth("Entre para acessar sua rede.", { resume: openNetworkCenter })) return;
        openAppModal(byId("networkModal"));
        showAvatar(currentUser.avatar_url);
        byId("externalReviewsSetting")?.classList.toggle("hidden", !["workout", "both"].includes(currentUser.professional_scope));
        byId("externalDietReviewsSetting")?.classList.toggle("hidden", !["diet", "both"].includes(currentUser.professional_scope));
        try {
            const result = await api("/profile");
            const profile = result.profile || {};
            byId("publicProfileToggle").checked = Boolean(profile.is_public);
            byId("externalReviewsToggle").checked = Boolean(profile.accepts_external_workout_reviews);
            byId("externalDietReviewsToggle").checked = Boolean(profile.accepts_external_diet_reviews);
        } catch (error) {
            showToast(error.message, "error");
        }
        loadInbox();
        await window.loadReviewInbox?.(highlightReviewId);
    }

    document.addEventListener("change", (event) => {
        if (event.target.matches("#publicProfileToggle, #externalReviewsToggle, #externalDietReviewsToggle")) updateSettings();
        if (event.target.matches("#networkAvatarInput") && event.target.files?.[0]) uploadPhoto(event.target.files[0]);
    });

    document.addEventListener("click", async (event) => {
        if (event.target.closest("#networkSearchButton")) search();
        if (event.target.closest("#networkAvatarRemove")) removePhoto();
        const connectButton = event.target.closest("[data-network-connect]");
        if (connectButton) connect(connectButton.dataset.networkUsername, connectButton.dataset.networkConnect);
        const action = event.target.closest("[data-connection-accept], [data-connection-decline], [data-connection-cancel]");
        if (!action) return;
        try {
            if (action.dataset.connectionAccept) await api(`/connections/${action.dataset.connectionAccept}/accept`, { method: "POST", body: { data_sharing_consent: true, sharing_consent_version: legalVersions?.professional_sharing?.version } });
            if (action.dataset.connectionDecline) await api(`/connections/${action.dataset.connectionDecline}/decline`, { method: "POST", body: {} });
            if (action.dataset.connectionCancel) await api(`/connections/${action.dataset.connectionCancel}`, { method: "DELETE", body: {} });
            showToast("Solicitação atualizada.", "success");
            loadInbox();
        } catch (error) {
            showToast(error.message, "error");
        }
    });

    window.openNetworkCenter = openNetworkCenter;
    window.loadNetworkInbox = loadInbox;
    window.applyCurrentUserAvatar = showAvatar;
    window.setNetworkReviewCount = setNetworkReviewCount;
})();
