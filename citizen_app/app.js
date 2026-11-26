/* The citizen app: fetches the area pack, keeps what is true at this moment (`state`) and shows it.

   The phone downloads the same file as everybody else and finds the route itself (route.js). Where the person stands
   never leaves this file: it is not sent, not stored, not written into the address of the page.

   While the page is on screen it asks the service every few seconds whether something changed (an operator confirmed
   or closed a street) and fetches the pack again only then. The last pack is kept on the phone (store.js) and so are
   the app's own files (sw.js): the app opens with them at once, also without a network, and says how old the pack is. */

import {LANGUAGES, firstLanguage, setLanguage, language, t, said, metres, clock, streetName} from './i18n.js';
import {buildNetwork, nearest, reach, route, changes, noticed, rank, reported, takesPeople, NEAR_M} from './route.js';
import {createMap} from './map.js';
import {drawSheet, drawFailure, exerciseWindow, aboutWindow, receivedLine, answer} from './sheet.js';
import {createStore} from './store.js';
import {h} from './dom.js';
import {openVoiceAgent} from './voice.js';

const PUBLIC = new URL('../public/', location.href);            // what the service lets every citizen read
const FORMAT = 1;                                               // the kind of pack this page understands (contracts.py: AreaPack.format)
const CHECK_MS = 15000;                                         // how often the service is asked whether something changed
const QUICK_MS = 10000, SLOW_MS = 90000;                        // how long to wait for a small answer, and for a whole pack
const KEEPS = 'caches' in globalThis && 'serviceWorker' in navigator;        // this browser can keep the app and the last pack,
                                                                // so that both open without a network
const WORSE = ['checked', 'unchecked', 'no_data', 'blocked'];   // what can be known about a street, the worst last
const TABS = {assembly: ['assembly_point', 'shelter'], medical: ['hospital', 'clinic']};
const MOVED_M = 10;                                             // a new reading of the phone closer than this changes nothing
// the answer beside the map: a wide screen, or a phone held sideways (unless desktop Mobile View frame is active)
const wide = window.matchMedia('(min-width: 900px), (orientation: landscape) and (min-width: 560px)');
const isWide = () => wide.matches && !document.documentElement.classList.contains('mobile-view');
const $ = id => document.getElementById(id);

const state = {
    pack: null, network: null,
    received: null,                 // the last moment the service said that this pack is its newest
    failed: null,                   // the text key of what went wrong while loading
    stale: null,                    // why nothing newer can be shown: 'offline' | 'tooOld' (this page cannot read the newer pack)
    position: null,                 // {lonLat, source: 'gps' | 'tap' | 'example', accuracy}
    reached: null,                  // the cheapest way from the position to every corner (route.js reach)
    routes: new Map(),              // place id -> route, or null when there is none
    spots: new Map(),               // place id -> where the place touches the streets
    tab: 'assembly',
    chosen: null,                   // the id of the place the person picked; null = the suggested one
    asking: false,                  // "Where are you?" is open although a position exists
    picking: false,                 // the next tap on the map says where the person is
    gps: null,                      // 'waiting' for the first reading | 'on' | null
    message: null,                  // {key, far}: what went wrong with the position
    sheetOpen: true, sheetFull: false, showAll: false, stepsOpen: false,
    refit: false, toTop: false,     // for the next drawing: move the map to show everything / scroll the panel up
};
const store = createStore({shelves: KEEPS ? globalThis.caches : null});      // no pack where the app itself cannot be kept:
                                                                // without a network nobody could open it
const holds = {pack: false, app: false};                        // what is on this phone now, as "About" says it
let map = null, watch = null, toastTimer = null, spoken = '', installPrompt = null;
let checking = false, answered = false, missed = 0;             // the questions to the service: one at a time; did it ever
                                                                // answer since the page opened; how many it left unanswered
let touched = false;                                            // the person pressed something since the page opened

/* Metres between two points on the globe. */
function apart([lon1, lat1], [lon2, lat2]) {
    const rad = Math.PI / 180;
    const a = Math.sin((lat2 - lat1) * rad / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin((lon2 - lon1) * rad / 2) ** 2;
    return 2 * 6371000 * Math.asin(Math.sqrt(a));
}

/* Metres between a point and the area this pack covers: 0 inside it. */
function outside([lon, lat]) {
    const [south, west, north, east] = state.pack.area.bbox;
    const inside = [Math.min(east, Math.max(west, lon)), Math.min(north, Math.max(south, lat))];
    return apart([lon, lat], inside);
}

const problem = (message = state.message) =>
    message && t(message.key, {km: metres(message.far), area: said(state.pack.area.name), m: metres(NEAR_M)});

function toast(words, ms = 6000) {
    const box = $('toast');
    box.textContent = words;
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
        box.hidden = true;
    }, ms);
}

/* ---- loading, and staying up to date ---- */

const at = path => new URL(path, PUBLIC).href;
const packOf = id => at(`areas/${encodeURIComponent(id)}/pack.json`);

/* The first pack. A pack kept on this phone is shown at once, also without a network, and check() then asks the
   service for something newer. A phone that has nothing kept waits for the service. */
async function load() {
    state.failed = null;
    $('sheet').replaceChildren(h('p', {class: 'wait', text: t('loading')}));
    const wanted = new URLSearchParams(location.search).get('area');
    try {
        const known = await store.kept(at('areas.json'));
        const last = known?.value.find(one => one.has_pack && (!wanted || one.id === wanted));
        let pack = last ? await store.kept(packOf(last.id)) : null;
        holds.pack = !!pack;
        if (pack?.value.format !== FORMAT) {                    // nothing kept that this page can read: ask the service
            const areas = await store.live(at('areas.json'), QUICK_MS);
            const area = areas.value.find(one => one.id === wanted && one.has_pack) || areas.value.find(one => one.has_pack);
            if (!area) throw new Error('no area has a pack yet');
            pack = await store.live(packOf(area.id), SLOW_MS);
            if (pack.value.format !== FORMAT) return fail('tooOld');          // a newer kind of pack than this page understands
            areas.keep();
            keepPack(pack);
            answered = true;
        }
        usePack(pack.value, pack.received);
        render();
        check();
        keepApp();
    } catch (trouble) {
        console.warn('The area could not be loaded:', trouble);
        fail('noPack');
    }
}

function fail(key) {
    state.failed = key;
    $('sheet').replaceChildren(...drawFailure(key, key === 'tooOld' ? () => location.reload() : load));
}

/* A pack arrived (the first one, or a newer one later): everything that was worked out from the old one is redone.
   The caller draws it (render). */
function usePack(pack, received) {
    Object.assign(state, {pack, received, failed: null, network: buildNetwork(pack)});
    state.spots = new Map(pack.places.map(place => [place.id, nearest(state.network, [place.lon, place.lat])]));
    if (!pack.places.some(place => place.id === state.chosen)) state.chosen = null;
    map?.usePack(pack);
    words();
    recompute();
}

/* The service is asked whether it has something newer: every CHECK_MS while the page is on screen, and at once when
   the page comes back to the screen or the phone finds a network. The question costs a few bytes; the pack is fetched
   only when it changed. One missed answer says little on a bad network, so "no connection" is said after two in a
   row; at once when the phone itself says it has no network, or when the service has not answered since the page opened. */
async function check() {
    if (checking || document.hidden || !state.pack || state.stale === 'tooOld') return;
    checking = true;
    const id = state.pack.area.id;
    let newer = null;
    try {
        const newest = await store.live(at(`areas/${encodeURIComponent(id)}/revision.json`), QUICK_MS);
        if (newest.value.revision === state.pack.revision) state.received = newest.received;
        else newer = await store.live(packOf(id), SLOW_MS);
        if (!answered) store.live(at('areas.json'), QUICK_MS).then(areas => areas.keep(), () => {});      // for the next opening
        state.stale = null;
        answered = true;
        missed = 0;
    } catch {
        missed += 1;
        if (missed >= 2 || !answered || navigator.onLine === false) state.stale = 'offline';
    }
    checking = false;
    if (newer && newer.value.format !== FORMAT) {               // a newer kind of pack: only a newer page can read it
        state.stale = 'tooOld';
        newerPage();
    } else if (newer) {
        keepPack(newer);
        renew(newer.value, newer.received);
    }
    freshness();
}

/* A newer pack arrived while the app was open: say what changed, and move the map only when the way shown changed. */
function renew(pack, received) {
    const before = wayShown(), moved = changes(state.pack, pack), notice = noticed(state.pack, pack), places = reported(state.pack, pack);
    usePack(pack, received);
    const after = wayShown(), {selected} = showing();
    const calm = !selected || takesPeople(selected);            // "your way stays the same" is not said of a way to a place that takes nobody
    if (after !== before && !state.picking) state.refit = true;
    render();
    toast([t('updated'), notice && t(notice === 'new' ? 'noticeNew' : 'noticeGone'), toldPlaces(places, selected), told(moved),
           (before || after) && (after !== before || calm) && t(after === before ? 'routeSame' : 'routeChanged')].filter(Boolean).join(' '), 10000);
}

/* The places with another report, in words: by name while they are few ("Devlet Hastanesi: Closed."), else how
   many. The place the panel shows is named in any case. */
function toldPlaces(places, shown) {
    const line = ({place, after}) => `${place.name}: ${after ? t(`reportShort.${after}`) : t('reportGone')}.`;
    if (places.length <= 2) return places.map(line).join(' ');
    const mine = places.find(({place}) => place === shown);
    return [mine && line(mine), t('updatedPlaces', {n: places.length})].filter(Boolean).join(' ');
}

/* The streets that changed, in words: by name while they are few ("Ay Sokak: Reported blocked."), else how many. */
function told(moved) {
    const streets = new Map();                                  // per street: its name, and the worst now known about a part of it
    for (const {street, after} of moved) {
        const key = street.name || street.way, old = streets.get(key);
        if (!old || WORSE.indexOf(after) > WORSE.indexOf(old.after)) streets.set(key, {name: streetName(street.name || null, street.kind), after});
    }
    if (streets.size > 2) return t('updatedStreets', {n: streets.size});
    return [...streets.values()].map(({name, after}) => `${name}: ${t(`group.${after}`)}.`).join(' ');
}

/* How old the information is: the line at the foot of the panel, and the strip that says why nothing newer can come. */
function freshness() {
    if (!state.pack) return;
    if ($('received')) $('received').textContent = receivedLine({received: state.received, revision: state.pack.revision});
    const why = state.stale === 'tooOld' ? t('tooOld') : state.stale ? t('offline', {when: clock(state.received)}) : '';
    $('stale').hidden = !why;
    if ($('stale').textContent !== why) $('stale').textContent = why;         // read out once, not every time the line is checked
}

/* ---- what is shown ---- */

/* The words outside the panel, in the language of the moment. */
function words() {
    const {pack} = state, area = pack ? said(pack.area.name) : '';
    document.documentElement.lang = language();
    document.title = area ? `${t('appName')} · ${area}` : t('appName');
    $('name').replaceChildren(t('appName'), ...(area ? [h('span', {class: 'area', text: area})] : []));
    $('language').setAttribute('aria-label', t('language'));
    $('about').setAttribute('aria-label', t('about'));
    $('call').setAttribute('aria-label', t('call'));
    const mobileOn = document.documentElement.classList.contains('mobile-view');
    $('view-toggle').setAttribute('aria-label', t(mobileOn ? 'desktopView' : 'mobileView'));
    $('view-toggle').setAttribute('aria-pressed', String(mobileOn));
    $('view-toggle').title = t(mobileOn ? 'desktopView' : 'mobileView');
    $('install-btn').setAttribute('aria-label', t('installApp'));
    $('install-btn').title = t('installApp');
    $('fab-gps').setAttribute('aria-label', t('locateMe'));
    $('fab-gps').title = t('locateMe');
    $('fab-fit').setAttribute('aria-label', t('recenterMap'));
    $('fab-fit').title = t('recenterMap');
    $('nav-map').querySelector('.nav-label').textContent = t('navMap');
    $('nav-assembly').querySelector('.nav-label').textContent = t('navAssembly');
    $('nav-medical').querySelector('.nav-label').textContent = t('navMedical');
    $('exercise').hidden = !pack?.exercise;
    $('exercise').textContent = `${t('exercise')} · ${t('exerciseShort')}`;
    $('notice').hidden = !pack?.notice;
    if (pack?.notice) {
        $('notice').replaceChildren(h('strong', {text: `${t('notice')} · ${pack.notice.issued_by} · ${clock(pack.notice.issued_at)}`}),
                                    said(pack.notice.text));
    }
    $('hint').replaceChildren(h('span', {text: t('tapHint')}), h('button', {type: 'button', onclick: () => stopPicking()}, t('cancel')));
    if (!map) $('map').textContent = t('mapMissing');
    freshness();
}

/* The places of the open tab, best first (route.js: rank): the cheapest route, hospitals with an emergency department
   ahead, and a place the operators reported full or closed after all the others. */
function ranked() {
    const cost = place => state.routes.get(place.id)?.cost ?? Infinity;
    return rank(state.pack.places.filter(place => TABS[state.tab].includes(place.kind)), cost, state.tab === 'medical');
}

/* The way to every place from where the person is. The caller draws it (render). */
function recompute() {
    const {network, position, pack} = state;
    const spot = position ? nearest(network, position.lonLat) : null;
    state.reached = spot ? reach(network, spot) : null;
    state.routes = new Map(pack.places.map(place => {
        const target = state.spots.get(place.id);
        return [place.id, state.reached && target ? route(network, state.reached, target) : null];
    }));
}

/* The place the panel shows at this moment, and the way to it: the one the person picked, else the best of the
   list. A place reported full or closed is never picked for them; one they picked themselves stays, with what was
   reported about it. */
function showing() {
    const list = ranked();
    const selected = state.pack.places.find(place => place.id === state.chosen) ||
                     (state.position && list.length && takesPeople(list[0]) ? list[0] : null);
    return {list, selected, found: selected ? state.routes.get(selected.id) : null};
}

/* The way shown at this moment as one text: the place, and every street walked with what is known about it.
   Two moments with the same text show the same way. */
function wayShown() {
    const {selected, found} = showing();
    return found ? [selected.id, ...found.parts.map(part => `${part.street.way}:${part.street.ends}:${part.group}`)].join(' ') : '';
}

/* The panel was drawn again: the button that had the focus keeps it. A button that is gone hands it on (to the one
   that took its place, else to the name of the place), so nobody using a keyboard or a screen reader is thrown back
   to the top of the page. */
const HEIR = {change: 'gps', cancel: 'change'};
function refocus(sheet, key) {
    const find = name => name && sheet.querySelector(`[data-key="${CSS.escape(name)}"]`);
    const next = find(key) || find(HEIR[key]) || (key === 'all' && sheet.querySelectorAll('.row')[3]) || sheet.querySelector('.card h2');
    next?.focus({preventScroll: true});
}

function render() {
    if (!state.pack) return;
    const {list, selected, found} = showing();
    const open = isWide() || !map || (state.sheetOpen && !state.picking);
    const view = {...state, ranked: list, selected, hasMap: !!map, message: problem(), revision: state.pack.revision,
                  open,
                  suggested: !!state.position && !!selected && selected === list[0] && takesPeople(selected),
                  noneTakes: list.length > 0 && !takesPeople(list[0])};       // the best of the list takes nobody: none of it does

    const sheet = $('sheet'), top = sheet.scrollTop;
    const key = sheet.contains(document.activeElement) ? document.activeElement.dataset.key : null;
    sheet.classList.toggle('sheet-peek', !isWide() && !!map && !open);
    sheet.classList.toggle('sheet-full', !isWide() && !!map && open && state.sheetFull);
    sheet.replaceChildren(...drawSheet(view, actions));
    if (key) refocus(sheet, key);
    sheet.scrollTop = state.toTop ? 0 : top;

    // sync floating map controls and mobile bottom navigation bar
    $('map-fabs').hidden = !map || state.picking;
    $('fab-fit').hidden = !state.position && !selected;
    $('fab-gps').classList.toggle('waiting', state.gps === 'waiting');
    $('fab-gps').classList.toggle('active', state.gps === 'on');

    const mapFocus = !open && !state.picking;
    $('nav-map').classList.toggle('active', mapFocus);
    $('nav-map').setAttribute('aria-pressed', String(mapFocus));
    $('nav-assembly').classList.toggle('active', !mapFocus && state.tab === 'assembly');
    $('nav-assembly').setAttribute('aria-pressed', String(!mapFocus && state.tab === 'assembly'));
    $('nav-medical').classList.toggle('active', !mapFocus && state.tab === 'medical');
    $('nav-medical').setAttribute('aria-pressed', String(!mapFocus && state.tab === 'medical'));

    map?.draw({position: state.position, place: selected, found, fit: state.refit});
    state.refit = state.toTop = false;

    const heard = view.message || (selected && found ? answer(selected, found) : view.noneTakes ? t('allReported') : '');     // for people who listen to the screen
    if (heard !== spoken) $('live').textContent = spoken = heard;
}

/* ---- where the person is ---- */

function stopGps() {
    if (watch !== null) navigator.geolocation.clearWatch(watch);
    watch = null;
    state.gps = null;
}

function stopPicking(show = true) {
    if (!state.picking) return;
    state.picking = false;
    map?.picking(false);
    $('hint').hidden = true;
    if (show) render();
}

/* Something is wrong with the position: said on the map while a point is being chosen there, else in the panel. */
function say(key, far = 0) {
    const message = {key, far};
    if (state.picking) return toast(problem(message));
    Object.assign(state, {message, asking: true, sheetOpen: true});
    render();
}

function setPosition(lonLat, source, accuracy = null, refit = true) {
    if (!nearest(state.network, lonLat)) {                      // too far from every street to guess where that is
        if (source === 'gps') stopGps();
        return say('noStreet');
    }
    if (source !== 'gps') stopGps();
    stopPicking(false);
    Object.assign(state, {position: {lonLat, source, accuracy}, asking: false, message: null, refit: state.refit || refit});
    recompute();
    render();
}

function useGps() {
    stopPicking(false);
    stopGps();
    if (!navigator.geolocation) return say('gpsFailed');
    Object.assign(state, {gps: 'waiting', message: null});
    render();
    watch = navigator.geolocation.watchPosition(onFix, onNoFix, {enableHighAccuracy: true, maximumAge: 10000, timeout: 20000});
}

function onFix({coords}) {
    const lonLat = [coords.longitude, coords.latitude], far = outside(lonLat), first = state.gps === 'waiting';
    if (far > 0) {
        stopGps();
        return say('gpsOutside', far);
    }
    state.gps = 'on';
    const last = state.position?.source === 'gps' ? state.position.lonLat : null;
    if (!first && last && apart(last, lonLat) < MOVED_M) return;          // standing still: nothing to work out again
    setPosition(lonLat, 'gps', coords.accuracy, first);                  // the map moves only for the first reading
}

function onNoFix(trouble) {
    const refused = trouble.code === trouble.PERMISSION_DENIED;
    if (!refused && state.gps === 'on') return;                 // a quiet moment after good readings: the last one stays
    stopGps();
    say(refused ? 'gpsDenied' : 'gpsFailed');
}

function choose(id) {
    const place = state.pack?.places.find(one => one.id === id);
    if (!place) return;
    const tab = Object.keys(TABS).find(name => TABS[name].includes(place.kind)) || state.tab;
    Object.assign(state, {chosen: id, tab, sheetOpen: true, refit: true, toTop: true});
    render();
}

/* What the buttons of the panel do (sheet.js). */
const actions = {
    fold() {
        if (state.picking) return stopPicking();
        Object.assign(state, {sheetOpen: !state.sheetOpen, sheetFull: false, refit: true});      // the map changes size: show the whole way again
        render();
    },
    gps: useGps,
    pick() {
        stopGps();
        Object.assign(state, {picking: true, message: null});
        map.picking(true);
        $('hint').hidden = false;
        render();
    },
    example() {
        const [south, west, north, east] = (state.pack.drone || state.pack.area).bbox;          // the middle of what the drone saw
        setPosition([(west + east) / 2, (south + north) / 2], 'example');
    },
    cancel() {
        if (state.gps === 'waiting') stopGps();
        Object.assign(state, {asking: false, message: null});
        render();
    },
    change() {
        Object.assign(state, {asking: true, message: null, toTop: true});
        render();
    },
    tab(name) {
        if (name === state.tab) return;
        Object.assign(state, {tab: name, chosen: null, showAll: false, refit: true, toTop: true});
        render();
    },
    choose,
    showAll() {
        state.showAll = true;
        render();
    },
    steps(open) {
        state.stepsOpen = open;
    },
};

/* ---- the window for "exercise" and "about" ---- */

const close = () => $('dialog').close();

function show(body) {
    const dialog = $('dialog');
    dialog.replaceChildren(body);
    if (dialog.open) return;
    if (dialog.showModal) dialog.showModal();
    else dialog.setAttribute('open', '');
}

$('dialog').addEventListener('click', event => {
    if (event.target === event.currentTarget) close();          // a tap beside the window
});
$('exercise').addEventListener('click', () => show(exerciseWindow(state.pack, close)));
$('about').addEventListener('click', () => show(aboutWindow(state.pack, state.received, close, holds)));
$('call').addEventListener('click', () => openVoiceAgent($('voice-screen')));

/* ---- the app on the phone ---- */

/* A pack this page can read goes on the phone, for the next opening. */
function keepPack(pack) {
    pack.keep().then(kept => (holds.pack ||= kept));
}

/* The browser keeps the app's own files (sw.js), so that the app opens without a network: asked for once the first
   pack is on the screen, which matters more. */
function keepApp() {
    if (KEEPS) navigator.serviceWorker.register('sw.js').catch(trouble => console.warn('The app could not be kept on this phone:', trouble));
}

/* This page cannot read what the service sends, so the service has a newer page: the browser is asked to fetch it now. */
function newerPage() {
    if (KEEPS) navigator.serviceWorker.getRegistration().then(kept => kept?.update()).catch(() => {});
}

/* The app's files on the phone were replaced (sw.js) while this page is open. The page is loaded again with them in
   two cases only: it cannot read what the service sends; or it is a page of the app kept at an earlier visit, so an
   older one, and the person has not pressed anything yet, so nothing is lost. Anybody in the middle of something
   keeps the page they have, and gets the newer app at the next opening. */
if (KEEPS) {
    navigator.serviceWorker.ready.then(() => (holds.app = true));           // every file of the app is on the phone (sw.js)
    const tended = !!navigator.serviceWorker.controller;        // the app kept at an earlier visit handed out this page
    for (const kind of ['pointerdown', 'keydown', 'click']) addEventListener(kind, () => (touched = true), {once: true, capture: true});
    navigator.serviceWorker.addEventListener('controllerchange', () => {
        const stuck = state.failed === 'tooOld' || state.stale === 'tooOld';
        if (stuck || (tended && state.pack && !touched)) location.reload();
    });
}

/* ---- mobile view, touch gestures, bottom nav, FABs & PWA install ---- */

function setMobileView(on, persist = true) {
    document.documentElement.classList.toggle('mobile-view', on);
    if (persist) {
        try {
            localStorage.setItem('viewMode', on ? 'mobile' : 'desktop');
        } catch {
            // private window: fine
        }
    }
    words();
    state.refit = true;
    if (state.pack) render();
    requestAnimationFrame(() => map?.resize());
}

/* Initial view mode: ?view=mobile or ?view=desktop overrides stored preference. */
{
    const param = new URLSearchParams(location.search).get('view');
    let stored = null;
    try {
        stored = localStorage.getItem('viewMode');
    } catch {
        // private window
    }
    const wantMobile = param === 'mobile' || (param !== 'desktop' && stored === 'mobile');
    if (wantMobile) document.documentElement.classList.add('mobile-view');
}

$('view-toggle').addEventListener('click', () => {
    setMobileView(!document.documentElement.classList.contains('mobile-view'));
});

$('fab-gps').addEventListener('click', useGps);
$('fab-fit').addEventListener('click', () => {
    if (!state.pack) return;
    state.refit = true;
    render();
});

$('nav-map').addEventListener('click', () => {
    if (!state.pack) return;
    if (state.picking) stopPicking(false);
    Object.assign(state, {sheetOpen: false, sheetFull: false, refit: true});
    render();
});

for (const tabName of ['assembly', 'medical']) {
    $(`nav-${tabName}`).addEventListener('click', () => {
        if (!state.pack) return;
        if (state.picking) stopPicking(false);
        const changed = state.tab !== tabName;
        Object.assign(state, {
            tab: tabName,
            ...(changed ? {chosen: null, showAll: false} : {}),
            sheetOpen: true,
            sheetFull: false,
            refit: true,
            toTop: changed,
        });
        render();
    });
}

/* Touch swipe on the bottom sheet handle: swipe up expands (peek -> half -> full), swipe down collapses. */
{
    let startY = null;
    $('sheet').addEventListener('touchstart', event => {
        if (isWide() || !event.target.closest('.handle') || event.touches.length !== 1) return;
        startY = event.touches[0].clientY;
    }, {passive: true});
    $('sheet').addEventListener('touchend', event => {
        if (startY === null || !event.changedTouches.length) return;
        const dy = event.changedTouches[0].clientY - startY;
        startY = null;
        if (Math.abs(dy) < 32) return;
        if (dy < 0) {
            // swiped up
            if (!state.sheetOpen) Object.assign(state, {sheetOpen: true, sheetFull: false, refit: true});
            else if (!state.sheetFull) Object.assign(state, {sheetFull: true, refit: true});
        } else {
            // swiped down
            if (state.sheetFull) Object.assign(state, {sheetFull: false, refit: true});
            else if (state.sheetOpen) Object.assign(state, {sheetOpen: false, refit: true});
        }
        render();
    }, {passive: true});
}

/* PWA install prompt (Chrome / Android / Edge). */
window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    installPrompt = event;
    $('install-btn').hidden = false;
});
$('install-btn').addEventListener('click', async () => {
    if (!installPrompt) return;
    installPrompt.prompt();
    try {
        await installPrompt.userChoice;
    } finally {
        installPrompt = null;
        $('install-btn').hidden = true;
    }
});
window.addEventListener('appinstalled', () => {
    installPrompt = null;
    $('install-btn').hidden = true;
});

/* ---- start ---- */

setLanguage(firstLanguage());
$('language').replaceChildren(...Object.entries(LANGUAGES).map(([code, name]) => h('option', {value: code, lang: code, text: name})));
$('language').value = language();
$('language').addEventListener('change', event => {
    setLanguage(event.currentTarget.value);
    if ($('dialog').open) close();
    words();
    map?.relabel();
    if (state.pack) render();
    else if (state.failed) fail(state.failed);
});

map = createMap($('map'), {place: choose, pick: lonLat => setPosition(lonLat, 'tap'), moved: lonLat => setPosition(lonLat, 'tap', null, false)});
if (!map) {                                                      // the list and the steps work without a map
    document.querySelector('.app').classList.add('no-map');
    $('map').className = 'map-missing';
}
wide.addEventListener('change', () => {                          // the phone was turned: the map has another shape,
    state.refit = true;                                          // show the whole way again
    render();
});
setInterval(freshness, 30000);                                   // "received 3 min ago" keeps counting
setInterval(check, CHECK_MS);
document.addEventListener('visibilitychange', check);            // back on the screen: ask at once (check() does nothing while hidden)
window.addEventListener('online', () => {                        // the phone found a network
    if (state.pack) check();
    else if (state.failed === 'noPack') load();
});
words();
load();
