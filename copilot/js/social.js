(function () {
    "use strict";

    const byId = (id) => document.getElementById(id);

    async function api(path) {
        const response = await fetch(`${API_BASE}${path}`, { credentials: "include" });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Não foi possível carregar seu perfil.");
        return data;
    }

    function showAvatar() {
        const initial = String(currentUser?.username || "U").charAt(0).toUpperCase();
        ["headerUserInitial", "homeUserInitial", "profileUserInitial"].forEach(id => {
            const fallback = byId(id);
            if (fallback) fallback.textContent = initial;
        });
    }

    window.applyCurrentUserAvatar = showAvatar;
    window.addEventListener("fittracker:offline-synced", async (event) => {
        if (!String(event.detail?.url || "").includes("/profile/avatar")) return;
        try {
            const result = await api("/profile");
            const avatarUrl = result.profile?.avatar_url || null;
            currentUser.avatar_url = avatarUrl;
            window.currentUser = currentUser;
            showAvatar();
            await window.AppOffline?.removeMedia("avatar-pending");
            showToast("Foto sincronizada.", "success");
        } catch (_error) { /* Reconcile again on the next foreground sync. */ }
    });
})();
