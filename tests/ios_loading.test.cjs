const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../copilot/js/utils.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
function harness(fetch = async () => new Response('{}')) {
    const window = {setTimeout, clearTimeout};
    const c = {window, fetch, AbortController, DOMException, Response, setTimeout, clearTimeout, console};
    vm.createContext(c); vm.runInContext(source, c);
    return window;
}
test('ten simultaneous reads share one request; valid cache needs no request', async () => {
    const {AppReadCache: cache} = harness(); let calls = 0, resolve;
    const loader = () => { calls++; return new Promise(r => resolve = r); };
    const reads = Array.from({length:10}, () => cache.read('diet:alice:2026-09-14', loader, {ttl:60000}));
    await tick(); assert.equal(calls,1); resolve({total:10});
    await Promise.all(reads);
    assert.equal((await cache.read('diet:alice:2026-09-14',loader,{ttl:60000})).total,10);
    assert.equal(calls,1);
});
test('mutation invalidates pending reads even when transport ignores abort', async () => {
    const {AppReadCache: cache} = harness(); let resolve;
    const old = cache.read('workout:today:alice', () => new Promise(r => resolve = r));
    const rejected = assert.rejects(old, {name:'AbortError'});
    await tick(); cache.invalidate('workout:');
    await cache.read('workout:today:alice', () => ({state:'completed'}));
    resolve({state:'active'}); await rejected;
    assert.equal(cache.peek('workout:today:alice').data.state,'completed');
});
test('account reset discards cached and in-flight private data', async () => {
    const {AppReadCache: cache} = harness(); let resolve;
    await cache.read('diet:alice:2026-09-14',() => 1);
    const old = cache.read('workout:alice', () => new Promise(r => resolve = r));
    const rejected = assert.rejects(old, {name:'AbortError'});
    await tick(); cache.reset(); resolve(2); await rejected;
    assert.equal(cache.accountVersion,1); assert.equal(cache.peek('diet:alice:2026-09-14'),null);
    assert.equal(cache.peek('workout:alice'),null);
});
test('cache separates day and account and retains stale data during refresh', async () => {
    const {AppReadCache: cache} = harness();
    for(const key of ['alice:14','alice:15','bob:14']) await cache.read(key,()=>key);
    let resolve; const work = cache.read('alice:14',()=>new Promise(r=>resolve=r),{force:true});
    await tick(); assert.equal(cache.peek('alice:14').data,'alice:14');
    assert.equal(cache.peek('bob:14').data,'bob:14'); resolve('updated'); await work;
    assert.equal(cache.peek('alice:14').data,'updated');
});
test('timeout includes delayed body, even after headers arrived', async () => {
    const {fetchWithTimeout} = harness(async()=>({status:200,json:()=>new Promise(()=>{})}));
    const response = await fetchWithTimeout('/api/test', {}, 20);
    await assert.rejects(response.json(), {name:'TimeoutError'});
});
test('external cancellation aborts the body and is not presented as timeout', async () => {
    let signal; const {fetchWithTimeout} = harness(async(_,options)=>{signal=options.signal;return {status:200,json:()=>new Promise(()=>{})};});
    const controller = new AbortController();
    const response = await fetchWithTimeout('/api/test',{signal:controller.signal},100);
    const body = response.json(); const rejected = assert.rejects(body,{name:'AbortError'});
    controller.abort(); await rejected; assert.equal(signal.aborted,true);
});
test('completed reads preserve response metadata and credentials', async () => {
    let options; const {fetchWithTimeout} = harness(async(_,opts)=>{options=opts;return new Response('{"ok":true}',{headers:{'x-test':'same'}});});
    const response=await fetchWithTimeout('/api/test',{credentials:'include'},100);
    assert.equal(response.headers.get('x-test'),'same'); assert.equal((await response.json()).ok,true);
    assert.equal(options.credentials,'include');
});
test('GET retries once on transient failure, but never retries 401/403', async () => {
    let calls=0;
    const api = harness(async()=>{calls++;return new Response('{}',{status:calls===1?503:200});});
    api.setTimeout=(fn,ms)=>setTimeout(fn,ms===1000?0:ms);
    await api.readApiJson('/api/test'); assert.equal(calls,2);
    for(const status of [401,403,409,429]) {
        calls=0; const noRetry=harness(async()=>{calls++;return new Response('{}',{status});});
        await assert.rejects(noRetry.readApiJson('/api/test'),error=>error.status===status);
        assert.equal(calls,1);
    }
});
