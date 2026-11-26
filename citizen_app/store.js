/* What the service said last, kept on the phone: with it the app opens and finds a way when there is no network,
   which is when it is needed most.

   Only answers that everybody may read are kept (the list of areas, the area pack), each with the moment it arrived.
   Nothing about the person is kept here: no position, no chosen place. The browser keeps the answers until the person
   clears the data of this site. Where the browser offers no place to keep things (an old browser, a page that is not
   served over a safe connection, some private windows) nothing is kept, and the app works only with a network. */

const SHELF = 'answers';                                        // the browser cache the answers are kept in
const ARRIVED = 'x-arrived';                                    // on a kept answer: when it arrived, in ms since 1970

/* The only request this app makes: read an address of its own site, asking each time whether there is something newer. */
const ask = (address, signal) => fetch(address, {cache: 'no-cache', signal});

/* -> {live, kept}. `get`, `shelves` and `now` are replaced in the tests (tests/citizen/store.test.mjs). */
export function createStore({get = ask, shelves = globalThis.caches, now = Date.now} = {}) {
    async function shelf() {
        try {
            return shelves ? await shelves.open(SHELF) : null;
        } catch {
            return null;                                        // the browser refuses to keep anything: the app goes on without
        }
    }

    /* What the service says at `address` now -> {value, received (ms), keep()}. keep() puts the answer on the shelf
       and says whether it is there now: the app calls it once it knows that it can read the answer.
       Throws when no whole answer came within `limit` ms, when the service refused, and when what came is not JSON
       (the login page of a hotel network is not an answer). */
    async function live(address, limit = 10000) {
        const stop = new AbortController(), timer = setTimeout(() => stop.abort(), limit);
        try {
            const reply = await get(address, stop.signal);
            if (!reply.ok) throw new Error(`${address}: ${reply.status}`);
            const text = await reply.text(), value = JSON.parse(text), received = now();
            const keep = async () => {
                try {
                    const place = await shelf();
                    if (!place) return false;
                    await place.put(address, new Response(text, {headers: {'content-type': 'application/json', [ARRIVED]: String(received)}}));
                    return true;
                } catch (trouble) {
                    console.warn('The answer could not be kept on this phone:', trouble);       // a full phone: the app goes on
                    return false;
                }
            };
            return {value, received, keep};
        } finally {
            clearTimeout(timer);
        }
    }

    /* What the service said at `address` when an answer was last kept -> {value, received (ms)}, or null. */
    async function kept(address) {
        try {
            const place = await shelf(), old = place ? await place.match(address) : null;
            return old ? {value: await old.json(), received: Number(old.headers.get(ARRIVED))} : null;
        } catch {
            return null;                                        // a kept answer that cannot be read is no answer
        }
    }

    return {live, kept};
}
