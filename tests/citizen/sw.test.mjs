/* Tests of the script that keeps the app on the phone (citizen_app/sw.js): which requests it answers from the phone,
   and which it never touches. What the service says about streets must never come from here: an old answer handed
   out as a new one would make the phone say "received just now" about old information.
   The script runs here as a browser runs it, beside a network and browser caches of our own.
   Run:  node --test tests/citizen/sw.test.mjs   (pytest runs it too: tests/test_citizen_app.py)
*/
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const SOURCE = readFileSync(new URL('../../citizen_app/sw.js', import.meta.url), 'utf8');
const SITE = 'https://shield.example', HERE = `${SITE}/app/sw.js`;
const PAGE = `${SITE}/app/`, CODE = `${SITE}/app/app.js`, PACK = `${SITE}/public/areas/defne/pack.json`;

/* The script with the list of files and the version filled in, as the service hands it out (drone_vision/service.py). */
const filled = (files, version) => SOURCE.replace('/*FILES*/[]', JSON.stringify(files)).replace('/*VERSION*/', version);

/* A browser around the script.
   network: path -> the text the service answers with; a path that is missing cannot be reached.
   kept:    what the browser caches hold already: cache name -> {address -> text}.
   broken:  the browser refuses to open a cache (a full phone, some private windows).
   -> {asked (what went to the network: [path, how the browser's own cache was to be used]), did (what the worker
       told the browser), names() (the caches that exist), files(name), happen(kind), ask(address, init)} */
function browser({source = filled(['./', 'app.js', 'vendor/map.js'], 'v2'), network = {}, kept = {}, broken = false} = {}) {
    const asked = [], did = [], listeners = {};
    const stores = new Map(Object.entries(kept).map(([name, entries]) => [name, new Map(Object.entries(entries))]));
    const address = input => new URL(typeof input === 'string' ? input : input.url, HERE);

    async function fetch(input) {
        const {pathname, search} = address(input);
        asked.push([pathname + search, input.cache]);
        if (!(pathname in network)) throw new TypeError('Failed to fetch');
        return new Response(network[pathname]);
    }
    const cache = name => ({
        async addAll(requests) {                                // every file, or none
            const replies = await Promise.all(requests.map(async request => [address(request).href, await (await fetch(request)).text()]));
            for (const [href, text] of replies) stores.get(name).set(href, text);
        },
        async match(request, {ignoreSearch = false} = {}) {
            const url = address(request);
            if (ignoreSearch) url.search = '';
            return stores.get(name).has(url.href) ? new Response(stores.get(name).get(url.href)) : undefined;
        },
    });
    const caches = {
        async open(name) {
            if (broken) throw new Error('The operation is insecure.');
            if (!stores.has(name)) stores.set(name, new Map());
            return cache(name);
        },
        async match(request, options) {                         // in any cache, the oldest first
            for (const name of stores.keys()) {
                const found = await cache(name).match(request, options);
                if (found) return found;
            }
        },
        keys: async () => [...stores.keys()],
        delete: async name => stores.delete(name),
    };
    class Asked extends Request {                               // in a worker a relative address starts at the worker's own
        constructor(input, init) {
            super(typeof input === 'string' ? new URL(input, HERE).href : input, init);
        }
    }
    const self = {
        addEventListener: (kind, listener) => void (listeners[kind] = listener),
        skipWaiting: async () => void did.push('skipWaiting'),
        clients: {claim: async () => void did.push('claim')},
    };
    vm.runInNewContext(source, {self, caches, fetch, location: new URL(HERE), URL, Request: Asked, Response});

    /* 'install' or 'activate' happens, and the browser waits for what the worker does about it. */
    async function happen(kind) {
        let work = null;
        listeners[kind]({waitUntil: promise => void (work = promise)});
        await work;
    }
    /* The page asks for something -> what the worker answers, as text; undefined when it leaves the request alone. */
    async function ask(where, init) {
        let answer;
        listeners.fetch({request: new Asked(new URL(where, HERE).href, init), respondWith: promise => void (answer = promise)});
        return answer && (await answer).text();
    }
    return {asked, did, names: () => [...stores.keys()], files: name => [...stores.get(name).keys()], happen, ask};
}

test('a new version fetches every file of the app, and takes over only when all of them have arrived', async () => {
    const all = {'/app/': 'the page', '/app/app.js': 'the code', '/app/vendor/map.js': 'the map'};
    const phone = browser({network: all});
    await phone.happen('install');
    assert.deepEqual(phone.files('shell-v2'), [PAGE, CODE, `${SITE}/app/vendor/map.js`]);
    assert.deepEqual(phone.asked, [['/app/', 'no-cache'], ['/app/app.js', 'no-cache'], ['/app/vendor/map.js', 'no-cache']]);      // never a copy the browser had lying around
    assert.deepEqual(phone.did, ['skipWaiting']);

    const half = browser({network: {'/app/': 'the page', '/app/app.js': 'the code'}});       // one file cannot be reached
    await assert.rejects(half.happen('install'), /Failed to fetch/);
    assert.deepEqual(half.did, []);                                                          // the version before stays in charge
});

test('taking over removes the older versions of the app and nothing else', async () => {
    const phone = browser({kept: {'shell-v1': {[PAGE]: 'old page'}, 'shell-v2': {[PAGE]: 'the page'}, answers: {[PACK]: '{}'}, other: {}}});
    await phone.happen('activate');
    assert.deepEqual(phone.names(), ['shell-v2', 'answers', 'other']);                        // the last pack stays (store.js)
    assert.deepEqual(phone.did, ['claim']);
});

test('the files of the app come from the phone, also when there is no network', async () => {
    const phone = browser({kept: {'shell-v2': {[PAGE]: 'the page', [CODE]: 'the code'}}});
    assert.equal(await phone.ask('/app/'), 'the page');
    assert.equal(await phone.ask('/app/?area=defne'), 'the page');                           // the same page, whatever area it is to open
    assert.equal(await phone.ask('/app/app.js'), 'the code');
    assert.deepEqual(phone.asked, []);
    await assert.rejects(phone.ask('/app/icon.png'), /Failed to fetch/);                     // not kept, and no network: as without the worker
});

test('a file of the app that the phone does not have is fetched', async () => {
    const phone = browser({network: {'/app/icon.png': 'a picture'}, kept: {'shell-v1': {[`${SITE}/app/icon.png`]: 'an old picture'}}});
    assert.equal(await phone.ask('/app/icon.png'), 'a picture');                             // never from another version
    assert.deepEqual(phone.asked.map(([path]) => path), ['/app/icon.png']);
});

test('a phone that cannot read what it kept asks the network', async () => {
    const phone = browser({network: {'/app/app.js': 'the code'}, kept: {'shell-v2': {[CODE]: 'the code it kept'}}, broken: true});
    assert.equal(await phone.ask('/app/app.js'), 'the code');
});

test('what the service says, the operators\' side and other sites are left alone', async () => {
    const everywhere = {[PACK]: 'an old pack', [`${SITE}/public/areas.json`]: '[]', [`${SITE}/maps`]: 'maps', [`${SITE}/`]: 'operators',
                        [`${SITE}/application/x`]: 'x', 'https://other.example/app/app.js': 'theirs', [CODE]: 'the code'};
    const phone = browser({kept: {'shell-v2': everywhere, answers: everywhere}});
    for (const where of ['/public/areas/defne/pack.json', '/public/areas/defne/revision.json', '/public/areas.json', '/maps', '/',
                         '/application/x', 'https://other.example/app/app.js']) {
        assert.equal(await phone.ask(where), undefined, where);
    }
    assert.equal(await phone.ask('/app/app.js', {method: 'POST'}), undefined);                // the app never sends; if it did, not from here
    assert.equal(await phone.ask('/app/app.js'), 'the code');
    assert.deepEqual(phone.asked, []);
});

test('read as it is in the repo, without the list of files, the script keeps nothing', async () => {
    const phone = browser({source: SOURCE, network: {'/app/app.js': 'the code'}});
    await phone.happen('install');
    assert.deepEqual([phone.asked, phone.names().flatMap(phone.files)], [[], []]);
    assert.equal(await phone.ask('/app/app.js'), 'the code');                                 // straight from the network
});
