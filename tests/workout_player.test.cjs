const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../copilot/js/plans.js'),'utf8');
const tick = () => new Promise(resolve=>setImmediate(resolve));
function harness() {
    const storage = new Map(), nodes = new Map(), calls = [], renders=[];
    const window = {currentUser:{id:'alice'}, setTimeout, clearTimeout, confirm:()=>true};
    const c={window, console, setTimeout, clearTimeout, AbortController, DOMException, Intl,
        API_BASE:'/api', escapeHtml:v=>String(v??''), showToast(){}, closeAppModal(){},
        requestAnimationFrame:fn=>fn(), navigator:{onLine:true},
        localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
        document:{readyState:'loading',addEventListener(){},getElementById:id=>nodes.get(id)||null,querySelector:()=>null,querySelectorAll:()=>[],visibilityState:'visible'},
        getComputedStyle:()=>({getPropertyValue:()=>76}),
    };
    vm.createContext(c);
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../copilot/js/utils.js'),'utf8'),c);
    const expose = `window.testPlayer = {state:workoutView, openReplacementOptions, closeReplacementPanel, applyReplacement, restoreExercise, completeWorkoutExercise, finishWorkoutSession, resetWorkoutAccount, hydrateWorkoutDrafts, persistWorkoutDraftLocally, saveWorkoutDraftToServer, scheduleWorkoutDraftSave, queueSessionWrite, setWorkoutSheetExpanded, setWorkoutEntryMode, confirmWorkoutQuickSet, openWorkoutFinishCard, returnFromWorkoutFinishCard, navigateSessionExercise, startWorkoutPlayerGesture, moveWorkoutPlayerGesture, endWorkoutPlayerGesture, cancelWorkoutPlayerGesture, loadWorkoutTodayCard, renderWorkoutTodayCard, displayedExercise, setAPI(fn){apiRequest=fn}, setRenderer(fn){renderWorkoutDetail=fn}, dock(){return activeWorkoutSummary}, gesture(){return workoutGesture}};\n    window.loadWorkoutTodayCard =`;
    vm.runInContext(source.replace('window.loadWorkoutTodayCard =',expose),c);
    const api=window.testPlayer, s=api.state;
    s.plan={id:1,title:'Treino A'}; s.days=[{id:10,title:'Peito',exercises:[{id:100,name:'Supino',sets:3,reps:'8-12',rest_seconds:60,equipment:['barbell'],catalog_key:'original'},{id:101,name:'Flexão',sets:3,rest_seconds:45}]}];
    s.session={id:77,workout_plan_id:1,workout_day_id:10,completed_exercise_ids:[],overrides:[],draft_sets:{}}; s.activeExerciseId='100';
    api.setRenderer(options=>renders.push(options));
    c.respond=async()=>({});
    api.setAPI((url,options={})=>{calls.push({url,options});return c.respond(url,options);});
    return {api,s,c,window,storage,nodes,calls,renders};
}
function stage(ready=false) {
    return {dataset:{exerciseId:'100'},hasAttribute:()=>ready,querySelector:()=>null,
        setPointerCapture(){},hasPointerCapture:()=>false,style:{setProperty(){},removeProperty(){}},classList:{add(){},remove(){}}};
}
function event(surface,x,y,extra={}) {
    return {target:{closest:selector=>selector.startsWith('.current-exercise-stage')?surface:null},isPrimary:true,button:0,pointerId:1,clientX:x,clientY:y,preventDefault(){},...extra};
}
function swipe(api,surface,dx,dy) {
    api.startWorkoutPlayerGesture(event(surface,200,300));
    api.moveWorkoutPlayerGesture(event(surface,200+dx,300+dy));
    api.endWorkoutPlayerGesture(event(surface,200+dx,300+dy));
}
test('replacement reads deduplicate and closing rejects a late response', async()=>{
    const {api,s,c,calls}=harness(); let resolve;
    c.respond=()=>new Promise(r=>resolve=r);
    const first=api.openReplacementOptions(100); await api.openReplacementOptions(100);
    assert.equal(calls.length,1); assert.equal(calls[0].options.body.unavailable_equipment.length,0);
    api.closeReplacementPanel(100); assert.equal(calls[0].options.signal.aborted,true);
    resolve({options:[{catalog_key:'alternative'}]}); await first;
    assert.equal(s.replacementPanels.size,0);
});
test('replacement confirmation runs once and preserves original ID, sets and rest', async()=>{
    const {api,s,c,calls}=harness();
    s.setDrafts.set('100',[{load_kg:'42,5',repetitions:'8',is_warmup:false}]);
    const rest={endsAt:Date.now()+60000}; s.rest=rest;
    c.respond=async()=>({options:[{catalog_key:'alt'}]}); await api.openReplacementOptions(100);
    let resolve; c.respond=()=>new Promise(r=>resolve=r);
    const applying=api.applyReplacement(100,'alt'); await tick(); await api.applyReplacement(100,'alt');
    assert.equal(calls.filter(c=>c.url.endsWith('/replace')).length,1);
    assert.equal(s.pendingAction,'replace-100');
    resolve({override:{workout_exercise_id:100,catalog_key:'alt',name:'Novo',weight:'Carga leve'}}); await applying;
    const shown=api.displayedExercise(s.days[0].exercises[0]).exercise;
    assert.equal(shown.id,100); assert.equal(shown.weight,'Carga leve');
    assert.equal(s.setDrafts.get('100')[0].load_kg,'42,5'); assert.equal(s.rest,rest);
    assert.equal(s.activeExerciseId,'100'); assert.equal(s.replacementPanels.size,0);
});
test('replacement cannot compete with completion; restore uses the same mutation lock', async()=>{
    const {api,s,c,calls}=harness(); s.pendingAction='complete-100';
    await api.openReplacementOptions(100); await api.restoreExercise(100); assert.equal(calls.length,0);
    s.pendingAction=''; let resolve; c.respond=()=>new Promise(r=>resolve=r);
    const restore=api.restoreExercise(100); await tick(); await api.completeWorkoutExercise(100);
    assert.equal(calls.length,1); resolve({}); await restore;
});
test('up opens the quick set entry without saving or starting rest',()=>{
    const {api,s,calls}=harness(); swipe(api,stage(),0,-80);
    assert.equal(s.setEntryMode,'quick'); assert.equal(s.sessionSheetExpanded,false); assert.equal(s.rest,null); assert.equal(calls.length,0);
});
test('confirming an empty quick set advances and starts the prescribed rest',()=>{
    const {api,s}=harness(); api.setWorkoutEntryMode('quick');
    assert.equal(api.confirmWorkoutQuickSet(100),true);
    assert.equal(s.setDrafts.get('100')[0].completed,true);
    assert.equal(s.activeSetIndex,1);
    assert.ok(s.rest.endsAt>Date.now());
});
test('cancel, lost capture, second finger, ambiguity and pending state never save',async()=>{
    const {api,s,calls}=harness(); const surface=stage();
    for(const cancel of ['cancel','lostcapture','second']) {
        api.startWorkoutPlayerGesture(event(surface,200,300)); api.moveWorkoutPlayerGesture(event(surface,50,300));
        if(cancel==='second') api.startWorkoutPlayerGesture(event(surface,70,300,{isPrimary:false,pointerId:2}));
        else api.cancelWorkoutPlayerGesture(event(surface,50,300));
        api.endWorkoutPlayerGesture(event(surface,50,300));
    }
    swipe(api,surface,-90,-90);
    s.pendingAction='complete-100'; swipe(api,surface,-90,0);
    await tick(); assert.equal(calls.length,0); assert.equal(api.gesture(),null);
});
test('a left horizontal gesture completes the current exercise and advances before a slow server responds', async()=>{
    const {api,s,c,calls}=harness(); let resolveServer;
    s.setDrafts.set('100',[{load_kg:'42,5',repetitions:'8',completed:true}]);
    c.respond=()=>new Promise(resolve=>{resolveServer=resolve;});
    swipe(api,stage(),-90,0);
    await tick(); await tick();
    assert.equal(calls.length,1); assert.ok(calls[0].url.endsWith('/complete'));
    assert.equal(s.activeExerciseId,'101'); assert.ok(s.session.completed_exercise_ids.includes('100'));
    assert.equal(calls[0].options.body.sets.length,1);
    assert.equal(calls[0].options.body.sets[0].load_kg,42.5);
    assert.equal(calls[0].options.body.sets[0].repetitions,8);
    assert.equal(calls[0].options.body.sets[0].is_warmup,false);
    resolveServer({session:{...s.session,completed_exercise_ids:[100]}});
    await tick(); await tick();
});
test('a right horizontal gesture navigates back without completing the current exercise',()=>{
    const {api,s,calls}=harness(); s.activeExerciseId='101';
    swipe(api,stage(),90,0);
    assert.equal(s.activeExerciseId,'100');
    assert.deepEqual(s.session.completed_exercise_ids,[]);
    assert.equal(calls.length,0);
});
test('a left horizontal gesture after the last exercise completes it and opens the finish card', async()=>{
    const {api,s,c,calls}=harness(); s.days[0].exercises=s.days[0].exercises.slice(0,1);
    c.respond=async()=>({session:{...s.session,completed_exercise_ids:[100]}});
    swipe(api,stage(),-90,0);
    await tick(); await tick();
    assert.equal(calls.length,1); assert.ok(calls[0].url.endsWith('/complete'));
    assert.equal(s.playerScreen,'finish'); assert.equal(s.activeExerciseId,'100'); assert.ok(s.session);
    swipe(api,stage(),90,0);
    assert.equal(s.playerScreen,'exercise'); assert.equal(s.activeExerciseId,'100');
});
test('returning from the finish card keeps the last exercise visible after all exercises are resolved',()=>{
    const {api,s}=harness();
    s.session.completed_exercise_ids=['100','101']; s.activeExerciseId='101';
    api.openWorkoutFinishCard(); assert.equal(s.playerScreen,'finish');
    api.returnFromWorkoutFinishCard(); assert.equal(s.playerScreen,'exercise');
});
test('network failure preserves exact drafts; reconciliation prevents duplicate confirmed completion',async()=>{
    const {api,s,c,calls}=harness(); s.setDrafts.set('100',[{load_kg:'42,5',repetitions:'8'}]);
    c.respond=async url=>{if(url.endsWith('/complete')) throw Object.assign(new Error('timeout'),{code:'timeout'}); throw new Error('offline');};
    await api.completeWorkoutExercise(100);
    assert.equal(s.setDrafts.get('100')[0].load_kg,'42,5'); assert.equal(s.uncertainMutation, undefined); assert.equal(s.activeExerciseId,'101');
    assert.ok(s.session.completed_exercise_ids.includes('100'));
    assert.equal(calls.filter(c=>c.url.endsWith('/complete')).length,1);
});
test('dirty local drafts survive hydration but confirmed completions remove them',()=>{
    const {api,s}=harness(); s.setDrafts.set('100',[{load_kg:'-',repetitions:'12'}]); api.persistWorkoutDraftLocally(77);
    api.hydrateWorkoutDrafts({...s.session,draft_sets:{100:[{load_kg:'10',repetitions:'8'}]}});
    assert.equal(s.setDrafts.get('100')[0].load_kg,'-');
    api.hydrateWorkoutDrafts({...s.session,completed_exercise_ids:[100]}); assert.equal(s.setDrafts.has('100'),false);
});
test('queued autosave cannot follow a confirmed complete and stale draft errors cannot replace mutation feedback',async()=>{
    const {api,s,c,calls}=harness(); let resolve;
    s.draftRevisions.set('100',1); c.respond=()=>new Promise(r=>resolve=r);
    const draft=api.saveWorkoutDraftToServer(77,100,[{repetitions:8}]); await tick();
    const complete=api.completeWorkoutExercise(100); assert.equal(s.pendingAction,'');
    c.respond=async()=>({session:{...s.session,completed_exercise_ids:[100]}});
    resolve({}); await Promise.all([draft,complete]);
    assert.ok(calls[0].url.endsWith('/draft')); assert.ok(calls[1].url.endsWith('/complete'));
    await api.saveWorkoutDraftToServer(77,100,[]); assert.equal(calls.length,2);
});
test('account switch invalidates replacement responses and retains old account draft privately',async()=>{
    const {api,s,c,window,storage}=harness(); s.setDrafts.set('100',[{load_kg:'42'}]); let resolve;
    c.respond=()=>new Promise(r=>resolve=r); const request=api.openReplacementOptions(100);
    api.resetWorkoutAccount(); window.AppReadCache.reset(); window.currentUser={id:'bob'};
    resolve({options:[{catalog_key:'alt'}]}); await request;
    assert.equal(s.session,null); assert.equal(s.replacementPanels.size,0);
    assert.match(storage.get('fittracker.workout-draft.v1.alice.77'),/42/);
    assert.equal(storage.has('fittracker.workout-draft.v1.bob.77'),false);
});
test('Home derives active dock from existing daily contract and loads one request for ten taps',async()=>{
    const {api,c,nodes,calls}=harness(); nodes.set('workoutTodayCard',{innerHTML:''});
    let resolve; c.respond=()=>new Promise(r=>resolve=r);
    const reads=Array.from({length:10},()=>api.loadWorkoutTodayCard()); await tick();
    resolve({state:'active',current_plan:{id:1},current_day:{id:10,exercises:[]},session:{id:77}}); await Promise.all(reads);
    assert.equal(calls.length,1); assert.equal(api.dock().plan.id,1);
    await api.loadWorkoutTodayCard(); assert.equal(calls.length,1);
});
