const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('copilot/js/professional.js', 'utf8');

function setup() {
    const elements = new Map();
    function element(id) {
        if (!elements.has(id)) {
            const classes = new Set();
            elements.set(id, { id, value: '', textContent: '', innerHTML: '', disabled: false,
                classList: { add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x), toggle: (x, on) => on ? classes.add(x) : classes.delete(x) },
                querySelectorAll: () => [], querySelector: () => null, focus() {},
                addEventListener: (name, callback) => { element(id)[name] = callback; } });
        }
        return elements.get(id);
    }
    const calls = [], toasts = [], handlers = {};
    let responder = async () => ({ ok: true, status: 200, json: async () => ({}) });
    const context = { console, URL, URLSearchParams, API_BASE: '/api',
        document: { getElementById: element },
        escapeHtml: value => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'),
        fetch: async (url, options) => { calls.push({ url, options }); return responder(url, options); },
        showToast: (...args) => toasts.push(args), openAppModal: el => el.classList.add('show'), closeAppModal: el => el.classList.remove('show'),
        currentUser: { id: 'professional', professional_entitled: true, professional_scope: 'workout' },
        location: { search: '', origin: 'https://fit.test', href: 'https://fit.test/app/perfil' },
        addEventListener: (name, callback) => { handlers[name] = callback; }, confirm: () => true,
    };
    context.window = context;
    vm.runInNewContext(source, context);
    return { context, element, calls, toasts, handlers, respond(fn) { responder = async (url, opts) => { const value = await fn(url, opts); return { ok: true, status: 200, json: async () => value }; }; }, fail() { responder = async () => { throw new Error('Sem conexão. Tente novamente.'); }; } };
}
const event = { preventDefault() {} };
const student = { id: 'student', username: 'Ana', is_offline: false, profile: {} };
async function openStudent(harness) {
    harness.respond(url => url.endsWith('/workout-plans') ? [] : student);
    await harness.context.openProfessionalStudent('student');
}
function fillEditor(harness) {
    for (const [id, value] of Object.entries({ editorTitle: 'Treino da Ana', editorDescription: 'Fortalecimento', editorGoal: 'hypertrophy', editorExperience: 'beginner', editorDays: '2', editorDuration: '45' })) harness.element(id).value = value;
    const fields = { '.exercise-key': { value: 'squat', selectedOptions: [{ dataset: { exerciseName: 'Agachamento' } }] }, '.exercise-sets': { value: '3' }, '.exercise-reps': { value: '8-12' }, '.exercise-rest': { value: '60' }, '.exercise-weight': { value: '20 kg' }, '.exercise-notes': { value: 'Controle a descida' }, '.professional-exercise-number': {} };
    const row = { dataset: {}, querySelector: selector => fields[selector], querySelectorAll: () => [{}, {}] };
    const days = [0, 1].map(index => ({ querySelector: selector => ({ value: selector.includes('dayTitle') ? `Treino ${index}` : 'Pernas', focus() {} }), querySelectorAll: selector => selector === '.professional-exercise-row' ? [row] : [] }));
    harness.element('professionalWorkoutDays').querySelectorAll = () => days;
    harness.element('professionalWorkoutDays').querySelector = () => days[0];
    return { fields, row, days };
}

test('somente profissional aprovado com escopo treino vê entrada; iOS não recebe menu', async () => {
    const h = setup();
    assert.equal(h.context.ProfessionalWorkspace.hasAccess(), true);
    h.context.currentUser.professional_scope = 'diet';
    h.context.ProfessionalWorkspace.sessionChanged(h.context.currentUser);
    assert.equal(h.element('profileProfessionalDashboard').classList.contains('hidden'), true);
    await h.context.loadProfessionalDashboard();
    assert.equal(h.calls.length, 0);
    h.context.currentUser.professional_scope = 'workout';
    h.context.Capacitor = { isNativePlatform: () => true };
    assert.equal(h.context.ProfessionalWorkspace.hasAccess(), false);
});

test('lista vazia orienta cadastrar e falha permite tentar novamente sem mutações', async () => {
    const h = setup();
    h.fail(); await h.context.loadProfessionalDashboard();
    assert.match(h.element('professionalStudents').innerHTML, /Tentar novamente/);
    h.respond(() => ({ items: [] })); await h.context.loadProfessionalDashboard();
    assert.match(h.element('professionalStudents').innerHTML, /Cadastre seu primeiro aluno/);
    assert.equal(h.calls.every(call => call.options.credentials === 'include' && call.options.method === 'GET'), true);
});

test('editor preserva campos quando salvar falha e próximo envio usa conteúdo original', async () => {
    const h = setup(); await openStudent(h);
    h.respond(() => [{ catalog_key: 'squat', name: 'Agachamento', equipment: 'Barra' }]);
    await h.context.createManualProfessionalPlan('workout'); fillEditor(h);
    h.fail(); await h.context.saveProfessionalEditor(event);
    assert.match(h.element('professionalPlanEditorMessage').textContent, /Sem conexão/);
    assert.equal(h.element('professionalPlanEditorModal').classList.contains('show'), true);
    assert.equal(h.element('editorTitle').value, 'Treino da Ana');
    h.respond((url, opts) => opts.method === 'POST' ? { id: 1 } : url.endsWith('/workout-plans') ? [] : student);
    await h.context.saveProfessionalEditor(event);
    const write = h.calls.filter(call => call.options.method === 'POST').at(-1);
    const body = JSON.parse(write.options.body);
    assert.equal(write.url, '/api/professional/students/student/workout-plans');
    assert.equal(body.plan.title, 'Treino da Ana'); assert.equal(body.plan.days.length, 2);
    assert.equal(body.plan.days[0].exercises[0].name, 'Agachamento');
});

test('cliques repetidos em salvar e publicar não enviam POST concorrente', async () => {
    const h = setup(); await openStudent(h);
    h.respond(() => []); await h.context.createManualProfessionalPlan('workout'); fillEditor(h);
    let release;
    h.respond((url, opts) => opts.method === 'POST' ? new Promise(resolve => { release = resolve; }) : url.endsWith('/workout-plans') ? [] : student);
    const first = h.context.saveProfessionalEditor(event);
    assert.equal(h.element('professionalPlanEditorMessage').textContent, 'Salvando rascunho…');
    assert.equal(h.element('professionalPlanEditorMessage').classList.contains('is-saving'), true);
    await h.context.saveProfessionalEditor(event);
    assert.equal(h.calls.filter(call => call.options.method === 'POST').length, 1);
    release({ id: 1 }); await first;
    const publish = h.context.publishProfessionalPlan('workout', 1);
    await h.context.publishProfessionalPlan('workout', 1);
    assert.equal(h.calls.filter(call => call.url.endsWith('/publish')).length, 1);
    release({ id: 1 }); await publish;
});

test('resposta atrasada de outra conta não repõe nomes de alunos', async () => {
    const h = setup(); let release;
    h.respond(() => new Promise(resolve => { release = resolve; }));
    const pending = h.context.loadProfessionalDashboard();
    h.context.currentUser = { id: 'other' }; h.context.ProfessionalWorkspace.sessionChanged(h.context.currentUser);
    release({ items: [student] }); await pending;
    assert.equal(h.element('professionalStudents').innerHTML, '');
});

test('editar rascunho salva no mesmo plano com PUT e aluno offline não publica', async () => {
    const h = setup(); await openStudent(h);
    h.respond(url => url.endsWith('/exercises') ? [{ catalog_key: 'squat', name: 'Agachamento' }] : { id: 7, title: 'Rascunho', questionnaire: { days_per_week: 2 }, days: [] });
    await h.context.editProfessionalPlan('workout', 7); fillEditor(h);
    h.respond((url, opts) => opts.method === 'PUT' ? { id: 7 } : url.endsWith('/workout-plans') ? [] : student);
    await h.context.saveProfessionalEditor(event);
    assert.equal(h.calls.filter(call => call.options.method === 'PUT').at(-1).url, '/api/professional/students/student/workout-plans/7');
    h.respond(url => url.endsWith('/workout-plans') ? [] : { ...student, is_offline: true });
    await h.context.openProfessionalStudent('student');
    const before = h.calls.length; await h.context.publishProfessionalPlan('workout', 7);
    assert.equal(h.calls.length, before);
});

test('cadastro offline falho preserva formulário e edição usa PUT no aluno correto', async () => {
    const h = setup();
    h.context.openOfflineStudent();
    for (const [id, value] of Object.entries({ rosterName: 'Ana', rosterAge: '28', rosterWeight: '65', rosterHeight: '168', rosterGender: '', rosterGoal: 'Força', rosterActivity: 'moderado' })) h.element(id).value = value;
    h.fail(); await h.context.saveOfflineStudent(event);
    assert.equal(h.element('rosterName').value, 'Ana'); assert.match(h.element('professionalStudentMessage').textContent, /Sem conexão/);
    h.respond(url => url.endsWith('/workout-plans') ? [] : { ...student, is_offline: true });
    await h.context.openProfessionalStudent('student'); h.context.openOfflineStudent('student');
    h.respond((url, opts) => opts.method === 'PUT' ? { student } : url.endsWith('/students?limit=100') ? { items: [student] } : url.endsWith('/workout-plans') ? [] : student);
    await h.context.saveOfflineStudent(event);
    assert.equal(h.calls.filter(call => call.options.method === 'PUT').at(-1).url, '/api/professional/students/student');
});

test('prescrição inválida impede salvar e leva o personal ao treino que precisa corrigir', async () => {
    const h = setup(); await openStudent(h);
    h.respond(() => []); await h.context.createManualProfessionalPlan('workout');
    const { fields } = fillEditor(h);
    const before = h.calls.length;
    for (const sets of ['0', '11', '1.5']) {
        fields['.exercise-sets'].value = sets;
        await h.context.saveProfessionalEditor(event);
        assert.equal(h.calls.length, before);
        assert.equal(h.context.ProfessionalWorkspace.editorStep(), 1);
        assert.match(h.element('professionalPlanEditorMessage').textContent, /1 a 10 séries/);
        assert.equal(h.element('professionalPlanEditorModal').classList.contains('show'), true);
    }
    fields['.exercise-sets'].value = '4';
    h.respond((url, opts) => opts.method === 'POST' ? { plan: { id: 12 } } : url.endsWith('/workout-plans') ? [] : student);
    await h.context.saveProfessionalEditor(event);
    const body = JSON.parse(h.calls.find(call => call.options.method === 'POST').options.body);
    assert.equal(body.plan.days[0].exercises[0].sets, 4);
});

test('editar prescrição preserva metadados de exercício personalizado e preferências do rascunho', async () => {
    const h = setup(); await openStudent(h);
    const custom = { catalog_key: 'custom:remada-elastico', name: 'Remada com elástico', movement_pattern: 'custom', primary_muscle: 'Costas', equipment: 'resistance_band', difficulty: 'beginner', effort_guidance: 'RPE 7 · sobram 3 repetições' };
    const questionnaire = { goal: 'strength', experience_level: 'intermediate', days_per_week: 2, split_type: 'upper_lower', session_duration: 60, equipment: ['resistance_band'], limitations: 'Dor no ombro', priorities: 'Fortalecer costas', avoid_exercises: 'Supino' };
    h.respond(url => url.endsWith('/exercises') ? [] : { id: 7, title: 'Rascunho', questionnaire, days: [{ exercises: [custom] }, { exercises: [custom] }] });
    await h.context.editProfessionalPlan('workout', 7);
    const { fields, row } = fillEditor(h);
    row.dataset.exerciseSource = JSON.stringify(custom);
    fields['.exercise-key'] = { value: custom.catalog_key, selectedOptions: [{ dataset: { exerciseName: custom.name } }] };
    fields['.exercise-reps'].value = '10-15';
    h.respond((url, opts) => opts.method === 'PUT' ? { plan: { id: 7 } } : url.endsWith('/workout-plans') ? [] : student);
    await h.context.saveProfessionalEditor(event);
    const write = h.calls.find(call => call.options.method === 'PUT');
    const body = JSON.parse(write.options.body);
    assert.equal(write.url, '/api/professional/students/student/workout-plans/7');
    assert.deepEqual(body.plan.days[0].exercises[0], { ...custom, sets: 3, reps: '10-15', rest_seconds: 60, weight: '20 kg', notes: 'Controle a descida' });
    for (const field of ['equipment', 'limitations', 'priorities', 'avoid_exercises', 'split_type']) assert.deepEqual(body.questionnaire[field], questionnaire[field]);
});

test('falha ao enviar mantém o rascunho salvo e nova tentativa usa PUT antes de publicar', async () => {
    const h = setup(); await openStudent(h);
    h.respond(() => []); await h.context.createManualProfessionalPlan('workout'); fillEditor(h);
    h.context.setProfessionalEditorStep(2);
    assert.equal(h.context.ProfessionalWorkspace.editorStep(), 2);
    h.respond((url, opts) => {
        if (url.endsWith('/publish')) throw new Error('Falha ao enviar. Tente novamente.');
        if (url.endsWith('/workout-plans/23')) return { id: 23, status: 'draft' };
        return opts.method === 'POST' ? { plan: { id: 23 } } : url.endsWith('/workout-plans') ? [] : student;
    });
    await h.context.saveProfessionalEditor(event, true);
    assert.equal(h.element('professionalPlanEditorModal').classList.contains('show'), true);
    assert.match(h.element('professionalPlanEditorMessage').textContent, /O rascunho está salvo.*Falha ao enviar/);
    assert.equal(h.element('editorTitle').value, 'Treino da Ana');
    h.respond((url, opts) => opts.method === 'PUT' ? { plan: { id: 23 } } : url.endsWith('/workout-plans') ? [] : student);
    await h.context.saveProfessionalEditor(event, true);
    const writes = h.calls.filter(call => call.options.method !== 'GET');
    assert.deepEqual(writes.map(call => [call.options.method, call.url]), [
        ['POST', '/api/professional/students/student/workout-plans'],
        ['POST', '/api/professional/students/student/workout-plans/23/publish'],
        ['PUT', '/api/professional/students/student/workout-plans/23'],
        ['POST', '/api/professional/students/student/workout-plans/23/publish'],
    ]);
    assert.equal(h.element('professionalPlanEditorModal').classList.contains('show'), false);
});

test('resposta de envio perdida confirma publicação e conclui sem tentar editar plano publicado', async () => {
    const h = setup(); await openStudent(h);
    h.respond(() => []); await h.context.createManualProfessionalPlan('workout'); fillEditor(h);
    h.context.setProfessionalEditorStep(2);
    let published = false;
    const plan = { id: 23, title: 'Treino da Ana', status: 'published' };
    h.respond((url, opts) => {
        if (url.endsWith('/publish')) {
            published = true;
            throw new Error('A conexão caiu depois que o servidor publicou o treino.');
        }
        if (opts.method === 'PUT') throw new Error('Um plano publicado não pode ser editado.');
        if (opts.method === 'POST') return { plan: { id: 23 } };
        if (url.endsWith('/workout-plans/23')) {
            assert.equal(published, true);
            return plan;
        }
        return url.endsWith('/workout-plans') ? [plan] : student;
    });
    await h.context.saveProfessionalEditor(event, true);
    assert.equal(h.element('professionalPlanEditorModal').classList.contains('show'), false);
    assert.equal(h.toasts.some(([message, kind]) => /Treino enviado/.test(message) && kind === 'success'), true);
    const writes = h.calls.filter(call => call.options.method !== 'GET');
    assert.deepEqual(writes.map(call => [call.options.method, call.url]), [
        ['POST', '/api/professional/students/student/workout-plans'],
        ['POST', '/api/professional/students/student/workout-plans/23/publish'],
    ]);
    assert.equal(h.calls.filter(call => call.options.method === 'GET' && call.url.endsWith('/workout-plans/23')).length, 1);
});

test('cancelar a saída preserva alterações e mantém a proteção até confirmar', async () => {
    const h = setup(); await openStudent(h);
    h.respond(() => []); await h.context.createManualProfessionalPlan('workout'); fillEditor(h);
    h.element('professionalPlanEditorForm').input();
    const prompts = [];
    h.context.confirm = message => { prompts.push(message); return false; };
    assert.equal(h.context.ProfessionalWorkspace.canCloseEditor(), false);
    assert.equal(h.context.ProfessionalWorkspace.canCloseEditor(), false);
    assert.equal(prompts.length, 2);
    assert.match(prompts[0], /Sair sem salvar/);
    assert.equal(h.element('professionalPlanEditorModal').classList.contains('show'), true);
    assert.equal(h.element('editorTitle').value, 'Treino da Ana');
    h.context.confirm = () => true;
    assert.equal(h.context.ProfessionalWorkspace.canCloseEditor(), true);
    h.context.confirm = () => { throw new Error('Um editor sem alterações não deve pedir confirmação.'); };
    assert.equal(h.context.ProfessionalWorkspace.canCloseEditor(), true);
});

test('revisão offline permite salvar rascunho e bloqueia as duas formas de publicação', async () => {
    const h = setup();
    const offline = { ...student, id: 'offline-9', is_offline: true };
    h.respond(url => url.endsWith('/workout-plans') ? [] : offline);
    await h.context.openProfessionalStudent(offline.id);
    h.respond(() => []); await h.context.createManualProfessionalPlan('workout'); fillEditor(h);
    h.context.setProfessionalEditorStep(2);
    assert.equal(h.element('professionalEditorSend').hidden, true);
    assert.match(h.element('professionalWorkoutReview').innerHTML, /convite aceito/);
    const before = h.calls.length;
    await h.context.saveProfessionalEditor(event, true);
    await h.context.publishProfessionalPlan('workout', 9);
    assert.equal(h.calls.length, before);
    h.respond((url, opts) => opts.method === 'POST' ? { plan: { id: 9 } } : url.endsWith('/workout-plans') ? [] : offline);
    await h.context.saveProfessionalEditor(event);
    const writes = h.calls.filter(call => call.options.method !== 'GET');
    assert.equal(writes.length, 1);
    assert.equal(writes[0].url, '/api/professional/students/offline-9/workout-plans');
});

test('trocar de conta durante o salvamento limpa o editor e ignora a resposta anterior', async () => {
    const h = setup(); await openStudent(h);
    h.respond(() => []); await h.context.createManualProfessionalPlan('workout'); fillEditor(h);
    h.element('professionalPlanEditorForm').input();
    let release;
    h.respond(() => new Promise(resolve => { release = resolve; }));
    const pending = h.context.saveProfessionalEditor(event);
    assert.equal(h.context.ProfessionalWorkspace.canCloseEditor(), false);
    const writesBeforeSwitch = h.calls.length;
    h.context.currentUser = { id: 'another-professional', professional_entitled: true, professional_scope: 'workout' };
    h.context.ProfessionalWorkspace.sessionChanged(h.context.currentUser);
    assert.equal(h.element('professionalPlanEditorBody').innerHTML, '');
    assert.equal(h.element('professionalBuilderContext').innerHTML, '');
    assert.equal(h.element('professionalPlanEditorModal').classList.contains('show'), false);
    release({ plan: { id: 88 } }); await pending;
    assert.equal(h.calls.length, writesBeforeSwitch);
    assert.equal(h.element('professionalStudentDetail').innerHTML, '');
    assert.equal(h.toasts.some(([message]) => /Rascunho salvo/.test(message)), false);
    await h.context.saveProfessionalEditor(event);
    assert.equal(h.calls.length, writesBeforeSwitch);
    assert.equal(h.context.ProfessionalWorkspace.canCloseEditor(), true);
    h.respond(url => url.endsWith('/workout-plans') ? [] : student);
    await h.context.openProfessionalStudent('student');
    h.respond(() => []); await h.context.createManualProfessionalPlan('workout');
    assert.equal(h.element('professionalPlanEditorModal').classList.contains('show'), true);
});

test('catálogo completo permite mostrar todos os resultados e buscar pelo nome original', async () => {
    const h = setup(); await openStudent(h);
    const exercises = Array.from({ length: 127 }, (_, index) => ({
        catalog_key: `workoutx:${index}`, name: `Exercício ${index}`, aliases: [`Original movement ${index}`], equipment: 'barbell',
    }));
    h.respond(() => exercises); await h.context.createManualProfessionalPlan('workout');
    assert.match(h.element('professionalCatalogCount').textContent, /127 exercícios encontrados · 60 exibidos/);
    assert.doesNotMatch(h.element('professionalCatalogResults').innerHTML, /data-catalog-key="workoutx:126"/);
    h.context.showMoreProfessionalExercises();
    h.context.showMoreProfessionalExercises();
    assert.match(h.element('professionalCatalogResults').innerHTML, /data-catalog-key="workoutx:126"/);
    assert.doesNotMatch(h.element('professionalCatalogResults').innerHTML, /Mostrar mais exercícios/);
    h.element('professionalExerciseSearch').value = 'Original movement 126';
    h.context.filterProfessionalExercises();
    assert.match(h.element('professionalCatalogCount').textContent, /1 exercícios encontrados · 1 exibidos/);
    assert.match(h.element('professionalCatalogResults').innerHTML, /data-catalog-key="workoutx:126"/);
});
