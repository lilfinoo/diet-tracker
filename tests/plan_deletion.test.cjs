const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('copilot/js/plans.js', 'utf8');
const deletion = source.slice(source.indexOf('    async function deletePlan('), source.indexOf('    function groupDietMeals('));
function setup(confirm = true, failure = false) {
    const calls = [], messages = [], rendered = [];
    const context = vm.createContext({
        window: {confirm: () => confirm},
        dietPlans: [{id:1},{id:2}], workoutPlans: [{id:1},{id:2}],
        apiSegment: String,
        apiRequest: async (path, options) => {
            calls.push({path, method: options.method});
            if (failure) throw new Error('Finalize o treino em andamento antes de excluir este plano.');
            return {message:'Plano removido. O histórico foi preservado.'};
        },
        showToast: (message, type) => messages.push({message,type}),
        renderPlanList: (_type, plans) => rendered.push(plans.map(plan=>plan.id)),
        renderFilteredWorkoutPlans: () => rendered.push(context.workoutPlans.map(plan=>plan.id)),
        loadDietPlans: async () => {}, loadWorkoutPlans: async () => {},
    });
    vm.runInContext(deletion, context);
    return {context,calls,messages,rendered};
}
test('canceling plan deletion never sends a request or changes the list', async () => {
    const {context,calls} = setup(false);
    await context.deletePlan('workout', 1);
    assert.equal(calls.length, 0);
    assert.equal(context.workoutPlans.length, 2);
});
for (const type of ['diet','workout']) test(`${type} deletion removes only the selected card before refreshing`, async () => {
    const {context,calls,messages,rendered} = setup();
    await context.deletePlan(type, '1');
    assert.deepEqual(calls, [{path:`/${type === 'diet' ? 'diet_plans' : 'workout_plans'}/1`, method:'DELETE'}]);
    assert.deepEqual(Array.from(rendered[0]), [2]);
    assert.equal(messages[0].message, 'Plano removido. O histórico foi preservado.');
});
test('active workout protection leaves the plan visible and explains the failure', async () => {
    const {context,messages,rendered} = setup(true, true);
    await context.deletePlan('workout', 1);
    assert.equal(context.workoutPlans.length, 2);
    assert.equal(rendered.length, 0);
    assert.equal(messages[0].type, 'error');
    assert.match(messages[0].message, /Finalize o treino/);
});
