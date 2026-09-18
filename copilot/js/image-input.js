/* One image source adapter for native camera/library and browser file inputs. */
(() => {
    "use strict";
    let registeredCamera = null;

    function cameraPlugin() {
        if (window.Capacitor?.Plugins?.Camera) return window.Capacitor.Plugins.Camera;
        if (!registeredCamera && window.Capacitor?.registerPlugin) {
            registeredCamera = window.Capacitor.registerPlugin("Camera");
        }
        return registeredCamera || window.CapacitorCamera;
    }

    function wasCancelled(error) {
        const message = String(error?.message || error || "").toLowerCase();
        const code = String(error?.code || "");
        return message.includes("cancel") || message.includes("canceled") || message.includes("cancelled")
            || ["OS-PLUG-CAMR-0006", "OS-PLUG-CAMR-0013", "OS-PLUG-CAMR-0020"].includes(code);
    }

    async function nativeFile() {
        const camera = cameraPlugin();
        if (!camera?.getPhoto) return null;
        try {
            const photo = await camera.getPhoto({
                quality: 82,
                resultType: "uri",
                source: "PROMPT",
                allowEditing: false,
            });
            const source = photo?.webPath || photo?.path;
            if (!source) return null;
            const response = await fetch(source);
            if (!response.ok) throw new Error("Não foi possível ler a foto selecionada.");
            const blob = await response.blob();
            return new File([blob], "fit-tracker-photo.jpg", { type: blob.type || "image/jpeg" });
        } catch (error) {
            if (wasCancelled(error)) return null;
            throw error;
        }
    }

    async function open({ inputId, onFile }) {
        const input = document.getElementById(inputId);
        if (input) input.value = "";
        let file = null;
        if (document.documentElement.dataset.nativePlatform === "ios") file = await nativeFile();
        if (file) {
            await onFile?.(file);
            return file;
        }
        input?.click();
        return null;
    }

    window.FitTrackerImagePicker = { open };
})();
