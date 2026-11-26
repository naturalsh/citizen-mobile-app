/* Tests of what the phone keeps (citizen_app/store.js): the last answer of the service comes back when there is no
   network, with the moment it arrived; and a refusal, a page that is not ours or silence never counts as an answer.
   Run:  node --test tests/citizen/store.test.mjs   (pytest runs it too: tests/test_citizen_app.py)
*/
import assert from 'node:assert/strict';
import test from 'node:test';

import {createStore} from '../../citizen_app/store.js';

const AREAS = 'areas.json', PACK = 'areas/defne/pack.json';

/* The browser's caches, as far as the app uses them: `kept` shows what is on the shelf. */
function shelves() {
    const kept = new Map();
    const shelf = {put: async (address, reply) => void kept.set(address, reply), match: async address => kept.get(address)?.clone()};
    return {kept, open: async () => shelf};
}

/* A service that answers every address with the same text, and remembers what it was asked. */
function service(text, status = 200) {
    const asked = [];
    return Object.assign(async address => (asked.push(address), new Response(text, {status})), {asked});
}

const stopped = signal => new Promise((_, refuse) => signal.addEventListener('abort', () => refuse(new Error('stopped'))));
const quiet = async work => {                                                    // the app warns on the console: not here
    const warn = console.warn;
    console.warn = () => {};
    try {
        return await work();
    } finally {
        console.warn = warn;
    }
};

test('an answer goes on the shelf only when the app says so, with the moment it arrived', async () => {
    const place = shelves(), get = service('{"revision": "a1"}');
    let time = 1000;
    const store = createStore({get, shelves: place, now: () => time});
    const answer = await store.live(PACK);
    assert.deepEqual([answer.value, answer.received], [{revision: 'a1'}, 1000]);
    assert.deepEqual(get.asked, [PACK]);
    assert.equal(await store.kept(PACK), null);                                  // nothing yet: the app has not said "keep"
    time = 4000;                                                                 // the app reads the answer first: that takes a while
    assert.equal(await answer.keep(), true);                                     // it is there now
    assert.deepEqual(await store.kept(PACK), {value: {revision: 'a1'}, received: 1000});
    assert.equal(await store.kept(AREAS), null);                                 // one answer per address
    assert.deepEqual([...place.kept.keys()], [PACK]);
});

test('without a network the kept answer comes back, with the time it arrived and not the time of asking', async () => {
    const place = shelves();
    let time = 1000;
    const first = createStore({get: service('{"revision": "a1"}'), shelves: place, now: () => time});
    await (await first.live(PACK)).keep();

    time = 9000;                                                                 // later: the page is opened again, the network is gone
    const later = createStore({get: async () => { throw new TypeError('Failed to fetch'); }, shelves: place, now: () => time});
    await assert.rejects(later.live(PACK), TypeError);
    assert.deepEqual(await later.kept(PACK), {value: {revision: 'a1'}, received: 1000});
    assert.deepEqual(await later.kept(PACK), {value: {revision: 'a1'}, received: 1000});       // and it can be read again

    const newer = createStore({get: service('{"revision": "b2"}'), shelves: place, now: () => time});
    await (await newer.live(PACK)).keep();                                       // a newer answer takes the place of the old one
    assert.deepEqual(await newer.kept(PACK), {value: {revision: 'b2'}, received: 9000});
});

test('a refusal and a page that is not ours are no answer', async () => {
    const place = shelves();
    await assert.rejects(createStore({get: service('{"detail": "no such area"}', 404), shelves: place}).live(PACK), /404/);
    await assert.rejects(createStore({get: service('{"revision": "a1"}', 500), shelves: place}).live(PACK), /500/);
    await assert.rejects(createStore({get: service('<html>Log in to the hotel network</html>'), shelves: place}).live(PACK), SyntaxError);
    assert.equal(place.kept.size, 0);
});

test('silence is no answer: the request is stopped after the time allowed', {timeout: 5000}, async () => {
    let told = null;
    const silent = createStore({get: (address, signal) => (told = signal, stopped(signal)), shelves: shelves()});
    await assert.rejects(silent.live(PACK, 20), /stopped/);
    assert.equal(told.aborted, true);

    /* the first lines arrive and then nothing more: the time allowed is for the whole answer */
    const half = createStore({get: async (address, signal) => ({ok: true, status: 200, text: () => stopped(signal)}), shelves: shelves()});
    await assert.rejects(half.live(PACK, 20), /stopped/);

    /* an answer in time is not stopped afterwards */
    const quick = createStore({get: async (address, signal) => (told = signal, new Response('{"revision": "a1"}')), shelves: shelves()});
    assert.deepEqual((await quick.live(PACK, 20)).value, {revision: 'a1'});
    await new Promise(done => setTimeout(done, 60));
    assert.equal(told.aborted, false);
});

test('where nothing can be kept, the app still gets its answer', async () => {
    const refusing = {open: async () => { throw new Error('SecurityError'); }};                // some private windows
    const full = {open: async () => ({put: async () => { throw new Error('QuotaExceededError'); }, match: async () => undefined})};
    const broken = {open: async () => ({put: async () => {}, match: async () => new Response('not JSON')})};
    for (const [place, took] of [[undefined, false], [refusing, false], [full, false], [broken, true]]) {
        const store = createStore({get: service('{"revision": "a1"}'), shelves: place});
        const answer = await store.live(PACK);
        assert.deepEqual(answer.value, {revision: 'a1'});
        assert.equal(await quiet(() => answer.keep()), took);                    // does not throw, and says whether the phone took it
        assert.equal(await store.kept(PACK), null);
    }
});
