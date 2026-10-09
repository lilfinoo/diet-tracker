const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../copilot/script.js'), 'utf8');
function harness(user) {
 const c = {currentUser:user,currentTab:'home',alerts:[],paywalls:0,showToast(message){c.alerts.push(message)},openPlansModal(){c.paywalls++},openAuthModal(){c.auth=true}};
 vm.createContext(c);
 vm.runInContext(source.slice(source.indexOf('function requireAuth('),source.indexOf('async function initializeGoogleAuth(')),c);
 return c;
}
test('default chat/text/edit permission requires Premium regardless of free balances',()=>{
 const c=harness({free_plan_uses:0,free_photo_uses:0});
 assert.equal(c.hasAiAccess(),false);
 assert.equal(c.requireAuth('chat',{premium:true}),false);
 assert.equal(c.paywalls,1);
});
test('plans remain available after all photos, and photos after plan usage',()=>{
 const c=harness({free_plan_uses:0,free_photo_uses:3,ai_trial_uses:3});
 assert.equal(c.hasAiAccess('plans'),true);
 assert.equal(c.hasAiAccess('photos'),false);
 assert.equal(c.requireAuth('plan',{premium:true,aiKind:'plans'}),true);
 c.currentUser={free_plan_uses:1,free_photo_uses:0};
 assert.equal(c.hasAiAccess('plans'),false);
 assert.equal(c.hasAiAccess('photos'),true);
 assert.equal(c.requireAuth('photo',{premium:true,aiKind:'photos'}),true);
});
test('anonymous denied, Premium allowed, manual logging unrestricted',()=>{
 const c=harness(null);
 for(const kind of ['plans','photos','premium']) assert.equal(c.hasAiAccess(kind),false);
 assert.equal(c.requireAuth('plan',{premium:true,aiKind:'plans'}),false);
 assert.equal(c.auth,true);
 c.currentUser={is_premium:true,free_plan_uses:1,free_photo_uses:3};
 for(const kind of ['plans','photos','premium']) assert.equal(c.hasAiAccess(kind),true);
 c.currentUser={free_plan_uses:1,free_photo_uses:3};
 assert.equal(c.requireAuth('manual'),true);
});
test('daily nutrition generation selects the shared plan allowance',()=>{
 const body=source.slice(source.indexOf('function editDailyNutritionTargets()'),source.indexOf('function renderPersonalizedHomeIntro('));
 assert.match(body,/aiKind: 'plans'/);
});

test('every plan wizard auth gate requests the plan allowance',()=>{
 const planSource=fs.readFileSync(require('node:path').join(__dirname,'../copilot/js/plans.js'),'utf8');
 const calls=planSource.match(/\{\s*premium: true[\s\S]*?\}/g)||[];
 assert.equal(calls.length,4);
 for(const call of calls) assert.match(call,/aiKind: "plans"/);
});
