/* Guided meal entry. Drafts and images live only for the current open flow. */
(() => {
    const el = id => document.getElementById(id);
    const fields = ['dietCalories', 'dietProtein', 'dietCarbs', 'dietFat'];
    let step = 1, method = 'text', photo = null, dirty = false, busy = false;
    let version = 0, estimateDescription = '', stale = false, editing = false;
    let photoVersion = 0, loadingPhoto = false, identified = false;
    const account = () => currentUser?.id;
    function message(text = '') { el('dietMessage').textContent = text; }
    function clearNutrients() {
        fields.forEach(id => { el(id).value = ''; });
        estimateDescription = '';
        stale = false;
    }
    function dataUrlBlob(dataUrl) {
        const match = String(dataUrl).match(/^data:([^;,]+)(?:;[^,]+)*,([^]*)$/);
        if (!match) return null;
        const binary = atob(match[2]);
        const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
        return new Blob([bytes], { type: match[1] });
    }
    function summary() {
        const values = fields.map(id => el(id).value);
        const empty = values.every(value => value === '');
        el('dietSummaryCalories').textContent = empty ? 'Sem estimativa' : `${values[0] === '' ? '—' : values[0]} kcal`;
        ['Protein', 'Carbs', 'Fat'].forEach((key, i) => {
            el('dietSummary' + key).textContent = empty ? '' : `${values[i + 1] === '' ? '—' : values[i + 1]} g ${['proteínas', 'carboidratos', 'gorduras'][i]}`;
        });
        el('dietReviewLabel').textContent = identified ? 'O que identificamos' : 'Descrição da refeição';
        el('dietEstimateHint').textContent = stale
            ? 'Você alterou a descrição. Recalcule ou continue sem estimativa.'
            : empty ? 'Você pode salvar sem informar nutrientes.' : 'Valores estimados. Confira alimentos e quantidades.';
    }
    function render(focus = false) {
        document.querySelectorAll('[data-diet-step]').forEach(node => {
            node.hidden = Number(node.dataset.dietStep) !== step;
            node.inert = node.hidden;
        });
        el('dietModalTitle').textContent = ['Como você quer registrar?', 'O que você comeu?', 'Confira sua refeição', 'Quando foi essa refeição?'][step - 1];
        el('dietFlowProgress').textContent = `Etapa ${step} de 4`;
        el('dietFlowBack').hidden = step === 1 || (editing && step === 3);
        el('dietFlowActions').hidden = step === 1;
        el('dietFlowNext').hidden = step === 4;
        el('dietSaveBtn').hidden = step !== 4;
        el('dietFlowNext').disabled = busy || loadingPhoto;
        el('dietFlowNext').textContent = loadingPhoto ? 'Preparando foto…' : busy ? 'Analisando sua refeição…' : step === 2 ? 'Analisar refeição' : stale ? 'Recalcular' : 'Continuar';
        el('dietFlowManual').hidden = step !== 2 && !(step === 3 && stale);
        el('dietPhotoArea').hidden = method !== 'photo';
        el('dietReviewPhoto').hidden = !photo;
        if (photo) el('dietReviewPhoto').src = el('dietPhotoPreviewImg').src;
        el('dietSourceLabel').textContent = method === 'photo' ? 'Quer complementar a foto?' : 'Descreva sua refeição';
        el('dietSourceText').placeholder = method === 'photo' ? 'Ex.: O café está sem açúcar' : 'Ex.: 2 colheres de arroz, feijão e um filé de frango';
        el('dietFinalDescription').textContent = el('dietDescription').value;
        summary();
        if (focus) {
            el('dietModalTitle').focus();
            el('dietModal').querySelector('.modal-content').scrollTop = 0;
        }
    }
    function invalidate() { version++; busy = false; }
    function begin(isEdit = false) {
        invalidate();
        el('dietDiscardPanel').hidden = true;
        el('dietForm').hidden = false;
        el('dietSaveLoading').classList.add('hidden');
        lockSaving(false);
        photoVersion++; loadingPhoto = false;
        editing = isEdit;
        dirty = false;
        method = 'text'; photo = null; stale = false; identified = false;
        el('dietSourceText').value = isEdit ? el('dietDescription').value : '';
        el('dietPhotoInput').value = '';
        ['dietPhotoPreview', 'dietReviewPhoto'].forEach(id => { el(id).hidden = true; });
        ['dietPhotoPreviewImg', 'dietReviewPhoto'].forEach(id => el(id).removeAttribute('src'));
        el('dietNutritionDetails').open = false;
        estimateDescription = isEdit ? el('dietDescription').value.trim() : '';
        step = isEdit ? 3 : 1;
        message(); render();
    }
    async function analyze() {
        if (busy || loadingPhoto) return;
        const review = step === 3;
        const description = (review ? el('dietDescription') : el('dietSourceText')).value.trim();
        if (!description && !photo) { message('Escreva o que comeu ou escolha uma foto para continuar.'); return; }
        const requestVersion = ++version, owner = account();
        busy = true; message(); render();
        try {
            const body = { description };
            if (photo) body.image = photo;
            const response = await fetch(`${API_BASE}/diet/ai_macros`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                credentials: 'include', body: JSON.stringify(body),
            });
            let data = await response.json();
            if (response.status === 202 && data.job_id) data = await window.waitForAIJob(data);
            if (requestVersion !== version || owner !== account()) return;
            if (!response.ok) throw new Error(data.error || 'A análise não está disponível. Tente novamente ou continue manualmente.');
            const identifiedText = typeof data.description === 'string' ? data.description.trim() : '';
            if (!identifiedText || identifiedText.length > 2000) throw new Error('Não foi possível identificar os alimentos. Descreva a refeição ou tente outra foto.');
            const keys = ['calories', 'protein', 'carbs', 'fat'];
            if (keys.some((key, i) => data[key] != null && (typeof data[key] !== 'number' || !Number.isFinite(data[key]) || data[key] < 0 || data[key] > (i ? 5000 : 20000)))) {
                throw new Error('A análise retornou valores inválidos. Tente novamente ou continue sem estimativa.');
            }
            el('dietDescription').value = review ? description : identifiedText;
            fields.forEach((id, index) => { el(id).value = data[keys[index]] ?? ''; });
            estimateDescription = el('dietDescription').value.trim();
            stale = false; dirty = true; identified = true; step = 3;
            render(true);
        } catch (error) {
            if (requestVersion === version && owner === account()) message(error.message || 'Erro de conexão. Tente novamente ou continue manualmente.');
        } finally {
            if (requestVersion === version && owner === account()) { busy = false; render(); }
        }
    }
    function manual() {
        invalidate();
        identified = false;
        clearNutrients();
        if (step === 2) el('dietDescription').value = el('dietSourceText').value.trim();
        step = 3; dirty = true;
        message(el('dietDescription').value.trim() ? '' : 'Descreva os alimentos para salvar sem análise.');
        render(true);
    }
    function validateReview() {
        if (!el('dietDescription').value.trim()) { message('Descreva os alimentos antes de continuar.'); el('dietDescription').focus(); return false; }
        for (const id of fields) {
            const input = el(id);
            if (!input.checkValidity()) { el('dietNutritionDetails').open = true; input.reportValidity(); return false; }
        }
        return true;
    }
    function canSave() {
        if (step !== 4 || busy) return false;
        if (stale) { step = 3; render(true); return false; }
        for (const id of ['dietDate', 'dietMeal']) {
            if (!el(id).checkValidity()) { el(id).reportValidity(); return false; }
        }
        return !!el('dietDescription').value.trim();
    }
    function canClose() {
        if (el('dietSaveBtn').disabled) return false;
        if (dirty) {
            invalidate();
            el('dietDiscardPanel').hidden = false;
            el('dietForm').hidden = true;
            el('dietFlowBack').disabled = true;
            el('dietKeepDraft').focus();
            return false;
        }
        reset();
        return true;
    }
    function reset() {
        dirty = false; invalidate(); photo = null;
        el('dietSaveBtn').disabled = false;
        el('dietForm').reset();
        begin();
    }
    function lockSaving(value) {
        el('dietForm').inert = value;
        el('dietFlowBack').disabled = value;
    }
    document.addEventListener('DOMContentLoaded', () => {
        el('dietKeepDraft').addEventListener('click', () => {
            el('dietDiscardPanel').hidden = true;
            el('dietForm').hidden = false;
            el('dietFlowBack').disabled = false;
            render(true);
        });
        el('dietDiscardDraft').addEventListener('click', () => {
            dirty = false;
            closeDietModal();
        });
        document.querySelectorAll('[data-diet-method]').forEach(button => button.addEventListener('click', () => {
            if (method !== button.dataset.dietMethod) { invalidate(); photoVersion++; loadingPhoto = false; photo = null; el('dietPhotoInput').value = ''; el('dietPhotoPreview').hidden = true; clearNutrients(); }
            method = button.dataset.dietMethod; step = 2; message(); render(true);
        }));
        el('dietFlowBack').addEventListener('click', () => { invalidate(); step--; message(); render(true); });
        el('dietReviewAgain').addEventListener('click', () => { step = 3; message(); render(true); });
        el('dietFlowNext').addEventListener('click', () => {
            if (step === 2 || stale) analyze();
            else if (validateReview()) { step = 4; message(); render(true); }
        });
        el('dietFlowManual').addEventListener('click', manual);
        el('dietForm').addEventListener('input', event => {
            dirty = true;
            if (event.target.id === 'dietSourceText') { invalidate(); clearNutrients(); }
            if (event.target.id === 'dietDescription') {
                invalidate();
                stale = !!estimateDescription && fields.some(id => el(id).value !== '') && el('dietDescription').value.trim() !== estimateDescription;
            }
            if (fields.includes(event.target.id) && !stale) estimateDescription = el('dietDescription').value.trim();
            render();
        });
        const handlePhotoFile = async file => {
            if (!file) return;
            invalidate(); const token = ++photoVersion, owner = account();
            photo = null; dirty = true; clearNutrients(); el('dietPhotoPreview').hidden = true;
            loadingPhoto = true; message('Preparando a foto…'); render();
            try {
                const result = await downscaleImageFile(file, 1024);
                if (token !== photoVersion || owner !== account()) return;
                const mime = result.dataUrl.match(/^data:([^;]+);/)?.[1];
                photo = { data: result.base64, mime_type: mime || 'image/jpeg' };
                const imageBlob = dataUrlBlob(result.dataUrl);
                await window.AppOffline?.saveMedia('diet-photo-pending', imageBlob, { type: 'diet-photo', date: new Date().toISOString() });
                el('dietPhotoPreviewImg').src = result.dataUrl; el('dietPhotoPreview').hidden = false; message();
            } catch (error) {
                if (token === photoVersion && owner === account()) message(error.message === 'Arquivo de imagem inválido'
                    ? 'Escolha uma foto válida.'
                    : 'Não foi possível abrir a foto. Escolha JPG/PNG ou escreva a refeição.');
            } finally {
                el('dietPhotoInput').value = '';
                if (token === photoVersion && owner === account()) { loadingPhoto = false; render(); }
            }
        };
        el('dietPhotoBtn').addEventListener('click', () => {
            const pickerRequest = window.FitTrackerImagePicker?.open({ inputId: 'dietPhotoInput', onFile: handlePhotoFile });
            pickerRequest?.catch(() => message('Não foi possível abrir a câmera ou fototeca.'));
        });
        el('dietPhotoRemove').addEventListener('click', () => {
            invalidate(); photoVersion++; loadingPhoto = false; photo = null; dirty = true; clearNutrients();
            el('dietPhotoInput').value = ''; el('dietPhotoPreview').hidden = true; el('dietReviewPhoto').hidden = true;
            el('dietPhotoPreviewImg').removeAttribute('src'); render();
        });
        el('dietPhotoInput').addEventListener('change', event => handlePhotoFile(event.target.files?.[0]));
    });
    window.DietEntryFlow = { begin, canClose, canSave, reset, analyze, lockSaving, revision: () => version,
        saved() { dirty = false; el('dietSaveBtn').disabled = false; }, invalidate };
})();
