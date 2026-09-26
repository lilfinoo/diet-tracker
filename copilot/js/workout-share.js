(function () {
    "use strict";

    const WIDTH = 1080;
    const HEIGHT = 1920;
    const FONT = "Inter, Arial, sans-serif";
    let revision = 0;
    let current = null;
    let prepared = null;
    let preparing = null;
    let busy = false;
    let notify = () => {};
    let photoCache = null;
    let nativeShare = null;

    function snapshot(summary, draft) {
        const selected = draft.selectedExerciseIds || new Set();
        return {
            sessionId: String(summary.session_id),
            title: String(summary.workout_name || "Meu treino"),
            duration: Number(summary.duration_seconds) || 0,
            mode: draft.mode === "dark" ? "dark" : "photo",
            transparent: draft.mode !== "dark" && draft.transparent === true,
            preset: ["full", "compact", "minimal"].includes(draft.infoPreset) ? draft.infoPreset : "full",
            photo: draft.photoDataUrl || "",
            scale: Math.max(0.5, Math.min(2, Number(draft.photoScale) || 1)),
            offsetX: Math.max(-300, Math.min(300, Number(draft.photoOffsetX) || 0)),
            offsetY: Math.max(-300, Math.min(300, Number(draft.photoOffsetY) || 0)),
            exercises: (summary.exercises || []).filter((item) => selected.has(String(item.exercise_id))).map((item) => ({
                id: String(item.exercise_id), name: String(item.name || "Exercício"),
                bestSet: item.best_set ? { load_kg: item.best_set.load_kg, repetitions: item.best_set.repetitions } : null,
                hasPR: Boolean(item.personal_records?.length),
            })),
        };
    }

    function sameSnapshot(first, second) {
        if (!first || !second || first.photo !== second.photo) return false;
        return JSON.stringify({ ...first, photo: "" }) === JSON.stringify({ ...second, photo: "" });
    }

    function shareError(message, code) {
        return Object.assign(new Error(message), { code });
    }

    function durationLabel(seconds) {
        if (!seconds) return "Duração não registrada";
        const minutes = Math.max(1, Math.round(seconds / 60));
        return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)}h${minutes % 60 ? ` ${minutes % 60}min` : ""}`;
    }

    function metricLabel(set) {
        if (!set) return "Séries não registradas";
        const load = set.load_kg == null ? "Carga não informada" : `${Number(set.load_kg).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} kg`;
        return `${load} · ${set.repetitions} repetições`;
    }

    function textLines(ctx, value, width, limit = 2) {
        const words = String(value).trim().split(/\s+/);
        const lines = [];
        let line = "";
        for (const word of words) {
            const candidate = line ? `${line} ${word}` : word;
            if (line && ctx.measureText(candidate).width > width) {
                lines.push(line);
                line = word;
            } else line = candidate;
        }
        if (line) lines.push(line);
        const result = lines.slice(0, limit);
        return result.map((item, index) => {
            const truncated = ctx.measureText(item).width > width || (index === limit - 1 && lines.length > limit);
            if (!truncated) return item;
            let end = item;
            while (end && ctx.measureText(`${end}…`).width > width) end = end.slice(0, -1);
            return `${end}…`;
        });
    }

    function photoAsset(source) {
        if (!source) return Promise.resolve(null);
        if (photoCache?.source === source) return photoCache.promise;
        const promise = new Promise((resolve, reject) => {
            const image = new Image();
            const timer = setTimeout(() => reject(shareError("A foto demorou para carregar. Tente novamente.", "asset-timeout")), 10000);
            image.onload = async () => {
                try {
                    if (image.decode) await image.decode();
                    if (!image.naturalWidth || !image.naturalHeight) throw new Error("Imagem vazia");
                    clearTimeout(timer);
                    resolve(image);
                } catch (_) {
                    clearTimeout(timer);
                    reject(shareError("Não foi possível preparar a foto. Escolha outra imagem.", "asset-error"));
                }
            };
            image.onerror = () => {
                clearTimeout(timer);
                reject(shareError("Não foi possível carregar a foto. Escolha outra imagem.", "asset-error"));
            };
            image.src = source;
        });
        photoCache = { source, promise };
        promise.catch(() => { if (photoCache?.promise === promise) photoCache = null; });
        return promise;
    }

    function drawCard(model, photo) {
        const canvas = document.createElement("canvas");
        canvas.width = WIDTH;
        canvas.height = HEIGHT;
        const ctx = canvas.getContext("2d");
        if (!ctx) throw shareError("Não foi possível preparar o card.", "canvas-unavailable");
        ctx.fillStyle = "#0b1220";
        ctx.fillRect(0, 0, WIDTH, HEIGHT);
        if (photo && model.mode === "photo") {
            const ratio = Math.max(WIDTH / photo.naturalWidth, HEIGHT / photo.naturalHeight) * model.scale;
            const width = photo.naturalWidth * ratio;
            const height = photo.naturalHeight * ratio;
            ctx.drawImage(photo, (WIDTH - width) / 2 + model.offsetX, (HEIGHT - height) / 2 + model.offsetY, width, height);
        }
        const x = 104;
        const width = WIDTH - x * 2;
        ctx.font = `700 72px ${FONT}`;
        const titles = textLines(ctx, model.title, width);
        const rows = model.preset === "full" ? model.exercises.slice(0, 3).map((exercise) => {
            ctx.font = `700 48px ${FONT}`;
            const lines = textLines(ctx, exercise.name, width - (exercise.hasPR ? 120 : 0));
            return { ...exercise, lines, height: lines.length * 56 + 92 };
        }) : [];
        const extraCount = model.preset === "full" ? Math.max(0, model.exercises.length - rows.length) : 0;
        const listHeight = rows.reduce((height, row) => height + row.height, 0);
        const blockHeight = 66 + 30 + titles.length * 80 + 80 + listHeight + (extraCount ? 64 : 0) + (model.preset === "compact" ? 170 : 0) + 96;
        const top = HEIGHT - 144 - blockHeight;
        if (model.transparent) {
            ctx.shadowColor = "rgba(0, 0, 0, .85)";
            ctx.shadowBlur = 12;
            ctx.shadowOffsetY = 3;
        } else {
            // An opaque panel makes text contrast independent of the chosen photograph.
            ctx.fillStyle = "#0b1220";
            ctx.beginPath();
            const panelY = top - 48, panelBottom = panelY + blockHeight + 96;
            ctx.moveTo(84, panelY);
            ctx.arcTo(WIDTH - 48, panelY, WIDTH - 48, panelBottom, 36);
            ctx.arcTo(WIDTH - 48, panelBottom, 48, panelBottom, 36);
            ctx.arcTo(48, panelBottom, 48, panelY, 36);
            ctx.arcTo(48, panelY, WIDTH - 48, panelY, 36);
            ctx.closePath();
            ctx.fill();
        }
        ctx.textBaseline = "top";
        ctx.fillStyle = "#60a5fa";
        ctx.font = `700 42px ${FONT}`;
        ctx.fillText("TREINO CONCLUÍDO", x, top);
        let y = top + 88;
        ctx.fillStyle = "#ffffff";
        ctx.font = `700 72px ${FONT}`;
        titles.forEach((line) => { ctx.fillText(line, x, y); y += 80; });
        y += 16;
        ctx.fillStyle = "#d1d9e6";
        ctx.font = `400 42px ${FONT}`;
        const count = `${model.exercises.length} exercício${model.exercises.length === 1 ? "" : "s"}`;
        textLines(ctx, `${durationLabel(model.duration)} · ${count}`, width, 1).forEach((line) => ctx.fillText(line, x, y));
        y += 74;
        if (model.preset === "compact") {
            ctx.fillStyle = "#172337";
            if (!model.transparent) ctx.fillRect(x, y, width, 132);
            ctx.fillStyle = "#ffffff";
            ctx.font = `700 48px ${FONT}`;
            ctx.fillText(count, x + 28, y + 20);
            ctx.fillStyle = "#d1d9e6";
            ctx.font = `400 42px ${FONT}`;
            ctx.fillText("Cada sessão conta.", x + 28, y + 78);
            y += 170;
        }
        rows.forEach((row) => {
            ctx.fillStyle = "#ffffff";
            ctx.font = `700 48px ${FONT}`;
            row.lines.forEach((line, index) => ctx.fillText(line, x, y + index * 56));
            if (row.hasPR) {
                ctx.fillStyle = "#fde68a";
                ctx.fillRect(WIDTH - x - 104, y, 104, 58);
                ctx.fillStyle = "#0b1220";
                ctx.font = `700 42px ${FONT}`;
                ctx.fillText("PR", WIDTH - x - 82, y + 6);
            }
            ctx.font = `400 42px ${FONT}`;
            ctx.fillStyle = "#d1d9e6";
            ctx.fillText(textLines(ctx, metricLabel(row.bestSet), width, 1)[0], x, y + row.lines.length * 56 + 10);
            y += row.height;
        });
        if (extraCount) {
            ctx.font = `400 42px ${FONT}`;
            ctx.fillStyle = "#d1d9e6";
            ctx.fillText(`+ ${extraCount} exercício${extraCount === 1 ? "" : "s"}`, x, y);
            y += 64;
        }
        ctx.fillStyle = "#6ee7b7";
        ctx.fillRect(x, y + 8, 56, 5);
        ctx.font = `700 42px ${FONT}`;
        ctx.fillText("Fit-Tracker.AI", x, y + 34);
        return canvas;
    }

    function pngBlob(canvas) {
        return new Promise((resolve, reject) => canvas.toBlob((blob) => blob
            ? resolve(blob)
            : reject(shareError("Não foi possível gerar o PNG. Tente novamente.", "png-error")), "image/png"));
    }

    function pngData(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(",")[1]);
            reader.onerror = () => reject(shareError("Não foi possível preparar o arquivo.", "png-error"));
            reader.readAsDataURL(blob);
        });
    }

    function isNativeIOS() {
        return window.Capacitor?.isNativePlatform?.() && window.Capacitor.getPlatform?.() === "ios";
    }

    async function preparePNG(summary, draft) {
        const model = snapshot(summary, draft);
        if (prepared && sameSnapshot(prepared.model, model)) return prepared;
        if (preparing && sameSnapshot(current, model)) return preparing;
        const token = ++revision;
        current = model;
        prepared = null;
        notify({ state: "preparing", message: "Preparando card…" });
        const work = (async () => {
            // Arial remains available when the app's Inter font has not loaded.
            const photo = model.mode === "photo" ? await photoAsset(model.photo) : null;
            if (token !== revision) return null;
            const canvas = drawCard(model, photo);
            const blob = await pngBlob(canvas);
            const file = new File([blob], "treino-card.png", { type: "image/png" });
            const base64 = isNativeIOS() ? await pngData(blob) : null;
            if (token !== revision) return null;
            prepared = { model, canvas, blob, file, base64, revision: token };
            return prepared;
        })();
        preparing = work;
        try {
            return await work;
        } catch (error) {
            if (token === revision) notify({ state: "error", message: error.message });
            throw error;
        } finally {
            if (token === revision) preparing = null;
        }
    }

    async function updatePreview(canvas, summary, draft, onState = () => {}) {
        notify = onState;
        const model = snapshot(summary, draft);
        try {
            const result = await preparePNG(summary, draft);
            if (!result || !sameSnapshot(current, model) || canvas.isConnected === false) return;
            canvas.width = WIDTH;
            canvas.height = HEIGHT;
            canvas.getContext("2d").drawImage(result.canvas, 0, 0);
            canvas.setAttribute("aria-label", `Card do treino ${model.title}: ${model.exercises.length} exercícios selecionados.`);
            notify({ state: busy ? "sharing" : "ready", message: busy ? "Compartilhamento aberto…" : "Card pronto para compartilhar." });
        } catch (_) {
            // preparePNG already exposes the error beside the sharing action.
        }
    }

    async function sharePrepared(summary, draft) {
        if (busy) return { status: "busy" };
        const artifact = prepared;
        if (!artifact || !sameSnapshot(artifact.model, snapshot(summary, draft))) {
            throw shareError("Aguarde a preparação do card antes de compartilhar.", "not-ready");
        }
        busy = true;
        notify({ state: "sharing", message: "Abrindo compartilhamento…" });
        try {
            if (isNativeIOS()) {
                nativeShare ||= window.Capacitor.Plugins?.FitTrackerShare || window.Capacitor.registerPlugin?.("FitTrackerShare");
                if (!nativeShare) throw shareError("Compartilhamento indisponível neste build do app.", "native-unavailable");
                return await nativeShare.sharePNG({ base64: artifact.base64 });
            }
            if (navigator.canShare?.({ files: [artifact.file] }) && navigator.share) {
                // No asset loading or blob conversion may precede this call: preserve user activation.
                await navigator.share({ files: [artifact.file], title: "Meu treino" });
                return { status: "shared" };
            }
            const url = URL.createObjectURL(artifact.blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = "treino-card.png";
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 30000);
            return { status: "download-started" };
        } catch (error) {
            if (error.name === "AbortError" || error.code === "cancelled") return { status: "cancelled" };
            throw error;
        } finally {
            busy = false;
            if (artifact.revision === revision) notify({ state: "ready", message: "Card pronto para compartilhar." });
        }
    }

    function reset() {
        revision += 1;
        current = null;
        prepared = null;
        preparing = null;
        photoCache = null;
        notify = () => {};
    }

    window.WorkoutShare = { updatePreview, preparePNG, sharePrepared, reset };
})();
