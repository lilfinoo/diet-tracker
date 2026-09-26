/* The photo and generated card exist only while the meal entry is open. */
(() => {
    "use strict";

    const WIDTH = 1080, HEIGHT = 1920;
    let source = null, sourceUrl = null, imagePromise = null;
    let revision = 0, prepared = null, busy = false;

    function isNativeIOS() {
        return window.Capacitor?.isNativePlatform?.() && window.Capacitor.getPlatform?.() === "ios";
    }

    function snapshot(values, framing) {
        return {
            values: values.map(value => value === '' || value == null ? null : Number(value)),
            scale: Math.max(1, Math.min(2.5, Number(framing.scale) || 1)),
            x: Math.max(-100, Math.min(100, Number(framing.x) || 0)),
            y: Math.max(-100, Math.min(100, Number(framing.y) || 0)),
        };
    }

    function loadPhoto(file) {
        if (source !== file) {
            if (sourceUrl) URL.revokeObjectURL(sourceUrl);
            source = file;
            sourceUrl = URL.createObjectURL(file);
            imagePromise = null;
            prepared = null;
        }
        if (!imagePromise) imagePromise = new Promise((resolve, reject) => {
            const image = new Image();
            image.onload = () => image.naturalWidth && image.naturalHeight ? resolve(image) : reject(new Error('Foto inválida.'));
            image.onerror = () => reject(new Error('Não foi possível carregar a foto.'));
            image.src = sourceUrl;
        });
        return imagePromise;
    }

    function label(value, unit) {
        return value == null || !Number.isFinite(value) ? '—' : `${value.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}${unit}`;
    }

    function draw(photo, model) {
        const canvas = document.createElement('canvas');
        canvas.width = WIDTH; canvas.height = HEIGHT;
        const ctx = canvas.getContext('2d');
        if (!ctx) throw new Error('Não foi possível preparar o card.');
        ctx.fillStyle = '#0b1220'; ctx.fillRect(0, 0, WIDTH, HEIGHT);
        const ratio = Math.max(WIDTH / photo.naturalWidth, HEIGHT / photo.naturalHeight) * model.scale;
        const width = photo.naturalWidth * ratio, height = photo.naturalHeight * ratio;
        const overflowX = (width - WIDTH) / 2, overflowY = (height - HEIGHT) / 2;
        ctx.drawImage(photo, -overflowX + overflowX * model.x / 100, -overflowY + overflowY * model.y / 100, width, height);
        const shade = ctx.createLinearGradient(0, 0, 0, HEIGHT);
        shade.addColorStop(0, 'rgba(4, 13, 24, .42)');
        shade.addColorStop(.36, 'rgba(4, 13, 24, .10)');
        shade.addColorStop(.62, 'rgba(4, 13, 24, .68)');
        shade.addColorStop(1, 'rgba(4, 13, 24, .98)');
        ctx.fillStyle = shade; ctx.fillRect(0, 0, WIDTH, HEIGHT);

        ctx.fillStyle = '#0b1220';
        ctx.beginPath(); ctx.roundRect(48, 1120, WIDTH - 96, 752, 36); ctx.fill();
        ctx.textBaseline = 'top';
        ctx.fillStyle = '#60a5fa'; ctx.font = '700 42px Inter, Arial, sans-serif';
        ctx.fillText('ESTIMATIVAS POR FOTO', 104, 1176);
        ctx.fillStyle = '#ffffff'; ctx.font = '800 144px Inter, Arial, sans-serif';
        ctx.fillText(label(model.values[0], ''), 104, 1256, WIDTH - 208);
        ctx.fillStyle = '#cbd5e1'; ctx.font = '600 44px Inter, Arial, sans-serif';
        ctx.fillText('kcal estimadas', 104, 1420);

        const labels = ['PROTEÍNAS', 'CARBOIDRATOS', 'GORDURAS'];
        const groupWidth = (WIDTH - 208) / 3;
        model.values.slice(1).forEach((value, index) => {
            const x = 104 + index * groupWidth;
            ctx.fillStyle = index === 1 ? '#60a5fa' : '#6ee7b7';
            ctx.fillRect(x, 1556, 56, 5);
            ctx.fillStyle = '#ffffff'; ctx.font = '700 56px Inter, Arial, sans-serif';
            ctx.fillText(label(value, ' g'), x, 1586, groupWidth - 16);
            ctx.fillStyle = '#cbd5e1'; ctx.font = '600 25px Inter, Arial, sans-serif';
            ctx.fillText(labels[index], x, 1666, groupWidth - 16);
        });
        ctx.fillStyle = '#6ee7b7'; ctx.fillRect(104, 1750, 56, 5);
        ctx.font = '700 42px Inter, Arial, sans-serif';
        ctx.fillText('Fit-Tracker.AI', 104, 1776);
        return canvas;
    }

    function pngBlob(canvas) {
        return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Não foi possível gerar o PNG.')), 'image/png'));
    }

    function base64Data(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(',')[1]);
            reader.onerror = () => reject(new Error('Não foi possível preparar o PNG.'));
            reader.readAsDataURL(blob);
        });
    }

    async function updatePreview(canvas, file, values, framing, onState) {
        if (!file) return;
        const model = snapshot(values, framing);
        const token = ++revision;
        prepared = null;
        onState('preparing', 'Preparando card…');
        try {
            const photo = await loadPhoto(file);
            if (token !== revision) return;
            const rendered = draw(photo, model);
            const blob = await pngBlob(rendered);
            const base64 = isNativeIOS() ? await base64Data(blob) : null;
            if (token !== revision || !canvas.isConnected) return;
            canvas.width = WIDTH; canvas.height = HEIGHT;
            canvas.getContext('2d').drawImage(rendered, 0, 0);
            prepared = { file, model, blob, base64, revision: token };
            onState('ready', 'Card pronto para compartilhar.');
        } catch (error) {
            if (token === revision) onState('error', error.message || 'Não foi possível preparar o card.');
        }
    }

    async function sharePrepared(file, values, framing) {
        if (busy) return { status: 'busy' };
        const artifact = prepared;
        if (!artifact || artifact.file !== file || JSON.stringify(artifact.model) !== JSON.stringify(snapshot(values, framing))) {
            throw new Error('Aguarde a preparação do card.');
        }
        busy = true;
        try {
            if (isNativeIOS()) {
                const plugin = window.Capacitor.Plugins?.FitTrackerShare || window.Capacitor.registerPlugin?.('FitTrackerShare');
                if (!plugin) throw new Error('Compartilhamento indisponível neste app.');
                return await plugin.sharePNG({ base64: artifact.base64, filename: 'macros-card.png' });
            }
            const png = new File([artifact.blob], 'macros-card.png', { type: 'image/png' });
            if (navigator.share && navigator.canShare?.({ files: [png] })) {
                await navigator.share({ files: [png], title: 'Estimativas por foto' });
                return { status: 'shared' };
            }
            const url = URL.createObjectURL(artifact.blob);
            const link = document.createElement('a');
            link.href = url; link.download = 'macros-card.png'; link.click();
            setTimeout(() => URL.revokeObjectURL(url), 30000);
            return { status: 'download-started' };
        } catch (error) {
            if (error.name === 'AbortError' || error.code === 'cancelled') return { status: 'cancelled' };
            throw error;
        } finally {
            busy = false;
        }
    }

    function reset() {
        revision++;
        prepared = null;
        imagePromise = null;
        source = null;
        if (sourceUrl) URL.revokeObjectURL(sourceUrl);
        sourceUrl = null;
    }

    window.DietShare = { updatePreview, sharePrepared, reset };
})();
