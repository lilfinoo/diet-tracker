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

    function isNativePlatform() {
        if (window.Capacitor?.isNativePlatform) return window.Capacitor.isNativePlatform();
        const platform = window.Capacitor?.getPlatform?.() || document.documentElement.dataset.nativePlatform;
        return platform === "ios" || platform === "android";
    }

    function pickerError(code, message, cause) {
        const error = new Error(message);
        error.code = code;
        if (cause) error.cause = cause;
        return error;
    }

    function wasCancelled(error) {
        const message = String(error?.message || error || "").toLowerCase();
        const code = String(error?.code || "");
        return message.includes("cancel") || message.includes("canceled") || message.includes("cancelled")
            || ["OS-PLUG-CAMR-0006", "OS-PLUG-CAMR-0013", "OS-PLUG-CAMR-0020"].includes(code);
    }

    function isUnavailable(error) {
        const message = String(error?.message || error || "").toLowerCase();
        const code = String(error?.code || "").toLowerCase();
        return code === "os-plug-camr-0007" || code.includes("unimplemented") || code.includes("unavailable")
            || message.includes("not implemented") || message.includes("plugin is not implemented");
    }

    function isPermissionDenied(error) {
        return ["OS-PLUG-CAMR-0003", "OS-PLUG-CAMR-0005"].includes(String(error?.code || "").toUpperCase());
    }

    function permissionError(source) {
        const label = source === "CAMERA" ? "câmera" : "fototeca";
        return pickerError("permission_denied", `Permita o acesso à ${label} nos ajustes do dispositivo para adicionar uma foto.`);
    }

    async function ensurePermission(camera, source, notify) {
        const permission = source === "CAMERA" ? "camera" : "photos";
        notify("checking_permission");
        let permissions = camera.checkPermissions ? await camera.checkPermissions() : null;
        let state = permissions?.[permission];
        if ((!state || state === "prompt" || state === "prompt-with-rationale") && camera.requestPermissions) {
            notify("requesting_permission");
            permissions = await camera.requestPermissions({ permissions: [permission] });
            state = permissions?.[permission];
        }
        const granted = state === "granted" || (source === "PHOTOS" && state === "limited");
        if (state && !granted) throw permissionError(source);
    }

    async function fileFromPhoto(photo) {
        const uri = photo?.webPath || photo?.path || photo?.uri;
        if (!uri) throw pickerError("image_read_failed", "Não foi possível ler a foto selecionada.");
        try {
            const response = await fetch(uri);
            if (!response.ok) throw new Error("invalid response");
            const blob = await response.blob();
            return new File([blob], "fit-tracker-photo.jpg", { type: blob.type || "image/jpeg" });
        } catch (error) {
            if (error?.code === "image_read_failed") throw error;
            throw pickerError("image_read_failed", "Não foi possível ler a foto selecionada.", error);
        }
    }

    async function nativeFile(source = "CAMERA", notify = () => {}) {
        const camera = cameraPlugin();
        if (!camera) throw pickerError("source_unavailable", "O recurso de imagem não está disponível neste dispositivo.");
        try {
            await ensurePermission(camera, source, notify);
            let photo;
            if (source === "CAMERA" && camera.takePhoto) {
                notify("opening_camera");
                photo = await camera.takePhoto({ quality: 82, correctOrientation: true, saveToGallery: false });
            } else if (source === "PHOTOS" && camera.chooseFromGallery) {
                notify("opening_photos");
                photo = (await camera.chooseFromGallery({ quality: 82 }))?.results?.[0];
            } else if (camera.getPhoto) {
                notify(source === "CAMERA" ? "opening_camera" : "opening_photos");
                photo = await camera.getPhoto({ quality: 82, resultType: "uri", source, allowEditing: false });
            } else {
                throw pickerError("source_unavailable", "O recurso de imagem não está disponível neste dispositivo.");
            }
            return photo ? await fileFromPhoto(photo) : null;
        } catch (error) {
            if (wasCancelled(error)) { notify("cancelled"); return null; }
            if (isPermissionDenied(error)) throw permissionError(source);
            if (isUnavailable(error)) {
                throw pickerError(source === "CAMERA" ? "camera_unavailable" : "source_unavailable",
                    source === "CAMERA" ? "Nenhuma câmera está disponível neste dispositivo." : "A fototeca não está disponível neste dispositivo.", error);
            }
            throw error;
        }
    }

    async function open({ inputId, onFile, onState, source = "CAMERA" }) {
        const input = document.getElementById(inputId);
        if (input) input.value = "";
        const notify = status => onState?.({ status, source });
        if (isNativePlatform()) {
            const file = await nativeFile(source, notify);
            if (!file) return null;
            notify("processing");
            const accepted = await onFile?.(file);
            if (accepted !== false) notify("ready");
            return file;
        }
        notify(source === "CAMERA" ? "opening_camera" : "opening_photos");
        input?.click();
        return null;
    }

    window.FitTrackerImagePicker = { open };
})();
