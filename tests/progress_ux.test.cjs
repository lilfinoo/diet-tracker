const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function harness() {
    const source = fs.readFileSync(path.join(__dirname,'../copilot/js/progress.js'),'utf8').replace('    window.loadWorkoutActivities =', '    window.testProgress = {recordLabel, renderWeekly, renderWeeklyEditor, renderFoodRhythm, compactPerformanceSets, renderBodyPreview, renderRecentPerformance, saveGoal, renderConsistencyCalendar, renderConsistencyHistory, performanceSets, performanceDate, renderProgressOverview};\n    window.loadWorkoutActivities =');
    const calls=[];
    const c={window:{}, currentUser:{id:'test'}, API_BASE:'/api', Intl, URLSearchParams,
        bodyMetrics:{weight:['Peso','kg'],body_fat:['Gordura','%']}, escapeHtml:v=>String(v??''), showToast(){}, document:{getElementById:()=>null,addEventListener(){}},
        fetch:async(url,opts)=>{calls.push({url,opts});return {ok:true,json:async()=>({})};},
    };
    c.window.fetchWithTimeout = (...args) => c.fetch(...args);
    vm.createContext(c); vm.runInContext(source,c);
    return {api:c.window.testProgress,calls,context:c};
}
test('each PR type shows meaningful units and previous/new values',()=>{
    const {api}=harness();
    for(const [metric,label] of [['max_load','Carga'],['reps_at_load','Repetições'],['estimated_1rm','Força estimada']]) {
        const html=api.recordLabel({metric_type:metric,previous_value:40,new_value:42.5,load_kg:40,repetitions:12});
        assert.ok(html.includes(label));assert.ok(html.includes('40 → 42,5'));
    }
});
test('weekly schedule shows effective date alongside current goal',()=>{
    const {api}=harness();
    const weekly={current:{completed:2,target:3,streak:1},scheduled_goal:{target_sessions:5,effective_week_start:'2026-09-14'}};
    const html=api.renderWeekly(weekly)+api.renderWeeklyEditor(weekly);
    assert.ok(html.includes('2 de 3 treinos')); assert.ok(html.includes('5 treinos por semana')); assert.ok(html.includes('14/09/2026'));
    assert.ok(html.includes('aria-controls="weeklyGoalEditor"'));
});
test('decimal comma is normalized and invalid input never reaches API',async()=>{
    const {api,calls}=harness(); const error={textContent:''};
    const form={dataset:{goalKind:'exercise',exerciseKey:'supino'},elements:{target:{value:'47,5',focus(){}}},querySelectorAll:()=>[],querySelector:s=>s==='[data-goal-error]'?error:{focus(){}},innerHTML:''};
    await api.saveGoal(form);
    assert.equal(JSON.parse(calls[0].opts.body).target_load_kg,47.5);
    assert.equal(calls[0].url,'/api/progress/exercise-goals');
    form.elements.target.value='27,5,0'; await api.saveGoal(form);
    assert.equal(calls.length,1); assert.ok(error.textContent.includes('carga válida'));
});

test('constancy counts days and exposes food states without evaluating missing weeks',()=>{
 const {api}=harness();
 const days=[{date:'2026-09-07',workout:true,diet_tracked:true,diet_states:['consumed_planned','skipped']},{date:'2026-09-08',workout:false,diet_tracked:false,diet_states:['pending']},{date:'2026-09-09',workout:false,diet_tracked:false,diet_states:['no_information']}];
 const html=api.renderConsistencyCalendar({start_date:'2026-09-07',end_date:'2026-09-09',days});
 assert.match(html,/1 dias com treino · 1 dias com acompanhamento alimentar/);
 for(const label of ['Consumido conforme planejado','Pulado','Pendente','Sem informação']) assert.ok(html.includes(label));
 assert.equal((html.match(/data-constancy-date=/g)||[]).length,3);
 const weeks=api.renderConsistencyHistory({history:['fulfilled','unfulfilled','in_progress','no_goal'].map(status=>({week_start:'2026-09-07',completed:0,target:status==='no_goal'?null:3,status}))});
 for(const label of ['Cumprida','Encerrada sem cumprir','Em andamento','Sem meta']) assert.ok(weeks.includes(label));
 assert.ok(!weeks.includes('de 8 semanas'));
});

test('performance preserves missing loads and distinguishes warmups; PRs explain rep gains',()=>{
 const {api}=harness();
 const html=api.performanceSets({sets:[{load_kg:null,repetitions:10},{load_kg:0,repetitions:12},{load_kg:40,repetitions:8,is_warmup:true}]});
 assert.match(html,/Carga não informada/); assert.match(html,/0 kg/); assert.match(html,/aquecimento/);
 assert.match(api.performanceSets({sets:[]}),/Séries não informadas/);
 assert.match(api.recordLabel({metric_type:'reps_at_load',previous_value:8,new_value:10,load_kg:40,repetitions:10}),/\+2 reps com 40 kg/);
});

test('performance dates preserve local snapshots and treat legacy timestamps as UTC',()=>{
 const {api}=harness();
 assert.equal(api.performanceDate({local_date:'2026-08-10',completed_at:'2026-08-11T01:00:00'}),'10/08/2026');
 assert.equal(api.performanceDate({completed_at:'2026-08-11T01:00:00'}), new Date('2026-08-11T01:00:00Z').toLocaleDateString('pt-BR'));
});

test('mobile summary distinguishes food states without counting pending or future days',()=>{
 const {api}=harness();
 const html=api.renderFoodRhythm({end_date:'2026-09-10',days:[{date:'2026-09-07',diet_tracked:true},{date:'2026-09-08',diet_tracked:false,diet_states:['pending']} ]},{week_start:'2026-09-07'});
 assert.equal((html.match(/class="food-day food-day--/g)||[]).length,7);
 for(const status of ['tracked','pending','unknown','future'])assert.ok(html.includes('food-day--'+status));
 assert.match(html,/1<small> dia/);
});
test('compact sets group identical results but retain missing load, zero and warmup distinctions',()=>{
 const {api}=harness();
 const set={load_kg:40,repetitions:10};
 const html=api.compactPerformanceSets([set,set,{...set,is_warmup:true},{load_kg:null,repetitions:10},{load_kg:0,repetitions:10}]);
 assert.match(html,/2 × 10 reps/); assert.match(html,/aquecimento/); assert.match(html,/Mais séries no detalhe/);
 assert.equal((html.match(/<strong>/g)||[]).length,2);
 assert.match(api.compactPerformanceSets([{load_kg:null,repetitions:10}]),/carga não informada/);
 assert.match(api.compactPerformanceSets([{load_kg:0,repetitions:10}]),/0 kg/);
});
test('compact cards handle empty, stable, sparse and stale measurements and no PR',()=>{
 const {api}=harness();
 assert.match(api.renderBodyPreview(null),/primeira medição/);
 const metric={latest:{value:70,date:'2025-01-02'},previous:{value:70,date:'2025-01-01'},change:0};
 const html=api.renderBodyPreview({metrics:{weight:metric}});
 assert.match(html,/Sem alteração/);assert.match(html,/mais de 30 dias/);assert.doesNotMatch(html,/is-complete|success/);
 assert.match(api.renderBodyPreview({metrics:{body_fat:{...metric,change:-1}}}),/−1 p.p./);
 assert.match(api.renderBodyPreview({metrics:{weight:{latest:metric.latest}}}),/ponto inicial/);
 assert.match(api.renderRecentPerformance(null),/próximo treino/);
 assert.match(api.renderRecentPerformance({name:'Exercício',max_load_kg:null,sessions:{items:[{completed_at:'2026-09-08T12:00:00',sets:[]}]}}),/não registrado/);
 assert.match(api.renderWeekly({current:{completed:4,target:3,fulfilled:true}}),/--fill:100%/);
 assert.match(api.renderWeekly({current:{completed:0,target:null}}),/Sem meta definida/);
});

test('overview still makes one request and rejects responses from a cleared account',async()=>{
 const {context:c,calls}=harness();
 const overview={innerHTML:'',replaceChildren(){this.innerHTML=''}};
 c.document.getElementById=id=>id==='workoutProgressOverview'?overview:null;
 let resolve;
 c.fetch=async(url)=>{calls.push(url);return new Promise(r=>resolve=r)};
 const pending=c.window.loadProgressOverview();
 c.window.clearWorkoutProgress();
 resolve({ok:true,json:async()=>({weekly:{current:{}},consistency:{days:[]}})});
 await pending;
 assert.equal(overview.innerHTML,'');
 assert.equal(calls.length,1);assert.equal(calls[0],'/api/progress/overview?view=summary');
});
test('overview keeps headings, empty state actions and only one editor outside the grid',()=>{
 const {context:c,api}=harness();const overview={innerHTML:''};
 c.document.getElementById=id=>id==='workoutProgressOverview'?overview:null;
 api.renderProgressOverview({weekly:{current:{}},consistency:{days:[]}});
 const html=overview.innerHTML;
 assert.ok(html.indexOf('Seu ritmo')<html.indexOf('Suas mudanças'));
 assert.ok(html.indexOf('Suas mudanças')<html.indexOf('Próximo passo'));
 assert.equal((html.match(/id="weeklyGoalEditor"/g)||[]).length,1);
 assert.match(html,/progress-primary-action[^>]+data-progress-action="edit-weekly"/);
 assert.match(html,/data-progress-action="go-body"/);
});
