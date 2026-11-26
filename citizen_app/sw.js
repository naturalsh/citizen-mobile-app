/* The citizen app without a network. The browser runs this file beside the page and lets it answer when the page asks
   for one of the app's own files: after the first visit the app opens although the service cannot be reached, and
   shows the last information the phone received (store.js).

   The service fills in the two lines below when it hands this file out (drone_vision/service.py): the files the app
   is made of, and a version that changes whenever one of them changes. A phone then fetches all of them again and
   uses the new ones only once every one has arrived. Read as it is here, the list is empty and nothing is kept.

   What the service says about streets and places (../public/) never passes through here: the page asks for it itself,
   so an old answer can never look like a new one. */

const FILES = /*FILES*/[];
const VERSION = '/*VERSION*/';
const SHELL = `shell-${VERSION}`;                               // the browser cache this version of the app is kept in
const HOME = new URL('./', location.href).pathname;             // "/app/": the folder of the app, and the page itself

/* A new version: fetch every file of the app. One that does not arrive stops all of it, and the old version stays. */
async function fetchAll() {
    const shelf = await caches.open(SHELL);
    await shelf.addAll(FILES.map(file => new Request(file, {cache: 'no-cache'})));
    await self.skipWaiting();                                   // do not wait until every open page of the old version is closed
}

/* The new version is complete: the older ones go, and the pages that are open get their files from this one too.
   The answers of the service that the page keeps (store.js) are in a cache of their own and stay. */
async function takeOver() {
    for (const name of await caches.keys()) {
        if (name.startsWith('shell-') && name !== SHELL) await caches.delete(name);
    }
    await self.clients.claim();
}

/* A file of the app: the kept one, whatever else the address says ("?area=defne" is the same page); else the network. */
async function hand(request) {
    let kept = null;
    try {
        const shelf = await caches.open(SHELL);
        kept = await shelf.match(request, {ignoreSearch: true, ignoreVary: true});
    } catch {
        // the browser cannot read what it kept: the network is asked
    }
    return kept || fetch(request);
}

self.addEventListener('install', event => event.waitUntil(fetchAll()));
self.addEventListener('activate', event => event.waitUntil(takeOver()));
self.addEventListener('fetch', event => {
    const {request} = event, {origin, pathname} = new URL(request.url);
    if (request.method !== 'GET' || origin !== location.origin || !pathname.startsWith(HOME)) return;         // not a file of the app
    event.respondWith(hand(request));
});
