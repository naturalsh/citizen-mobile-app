/* The answer panel: where the person is, the place to go, how to walk there and what is known about the way.
   Everything here only turns a description of the moment (`view`) into page elements; app.js decides what is true.
   Lists, rows and filled buttons carry the class names of Framework7's stylesheet, which draws them
   (vendor/README.md); app.css holds our own rules. */

import {t, said, metres, minutes, day, clock, ago, streetName} from './i18n.js';
import {steps, takesPeople} from './route.js';
import {sign, KINDS} from './map.js';
import {h} from './dom.js';

const GROUPS = ['checked', 'unchecked', 'no_data', 'blocked'];
const FACILITIES = ['water', 'medical', 'power', 'shelter', 'accessible'];
const GLYPH = {checked: 'ok', partly: 'alert', blocked: 'no',
               water: 'water', medical: 'medical', power: 'power', shelter: 'shelter', accessible: 'accessible'};
const LEGEND = {checked: 'checked', partly: 'unchecked', blocked: 'blocked'};        // a route's verdict in the words of the legend
const FILLED = 'button button-fill button-large main';                               // the one button a screen asks to be pressed

const walk = found => t('walk', {m: metres(found.metres), min: minutes(found.seconds)});
const verdict = found => t(`verdict.${found.worst}`, {m: metres(found.worst === 'blocked' ? found.by.blocked : found.by.unchecked + found.by.no_data)});
const emergency = place => typeof place.emergency === 'boolean' && t(place.emergency ? 'emergencyYes' : 'emergencyNo');
const kindOf = place => [t(`kind.${place.kind}`), emergency(place)].filter(Boolean).join(' · ');
const button = (name, key, go, ...words) => h('button', {class: name, type: 'button', 'data-key': key, onclick: go}, ...words);

/* A drawing from vendor/ionicons, in the colour of the words beside it (app.css: .ico). */
const glyph = name => h('span', {class: `ico ico-${name}`, 'aria-hidden': 'true'});

function icon(kind, off = false, px = 28) {
    const drawn = sign(kind, px, off);
    drawn.setAttribute('aria-hidden', 'true');
    return drawn;
}

/* A list as the library draws it: white, with round corners and a hairline between its lines. */
const list = (name, ...entries) => h('div', {class: `${name} list list-strong inset list-dividers`}, h('ul', {}, ...entries));

/* One line of such a list that can be pressed: a drawing, the words, and an arrow at its end. */
const entry = (name, key, go, drawing, ...words) => h('li', {},
    button(`${name} item-link item-content`, key, go,
        h('span', {class: 'item-media'}, drawing),
        h('span', {class: 'item-inner'}, h('span', {class: 'item-title'}, ...words))));

const problem = words => h('p', {class: 'problem'}, glyph('alert'), h('span', {text: words}));

/* The answer in one breath, for people who listen to the screen: the place, what was reported about it, the way. */
export const answer = (place, found) =>
    [`${place.name}.`, place.report && t(`report.${place.report.state}`), `${walk(found)}.`, verdict(found)].filter(Boolean).join(' ');

export const receivedLine = view => `${t('received', {when: ago(view.received)})} · ${view.revision.slice(0, 8)}`;

/* The line that is always there. Folded, it says the answer in a few words and leaves the screen to the map. */
function handle(view, on) {
    const place = view.selected, found = place && view.routes.get(place.id);
    /* Of a place that takes nobody, what was reported comes first: a long name is cut at its end. */
    const name = !place ? (view.noneTakes ? t('allReportedShort') : t(view.position ? 'places' : 'whereTitle'))
        : takesPeople(place) ? place.name : `${t(`reportShort.${place.report.state}`)} · ${place.name}`;
    const more = place && takesPeople(place) && found ? walk(found) : '';
    return h('button', {class: 'handle', type: 'button', 'data-key': 'handle', 'aria-expanded': String(view.open), onclick: on.fold},
        h('span', {class: 'grabber', 'aria-hidden': 'true'}),
        h('span', {class: 'handle-row'},
            h('span', {class: 'summary'}, h('span', {class: 'summary-name', text: name}), more && ' ', more && h('span', {class: 'summary-more', text: more})),
            h('span', {class: 'handle-word'},
                view.open ? h('span', {class: 'unseen', text: t('showMap')}) : t('showDetails'),
                glyph(view.open ? 'down' : 'up'))));
}

function where(view, on) {
    const echo = !view.selected && !view.position;              // the line above the panel says the same words
    return h('section', {class: 'where'},
        h('h2', {class: echo ? 'echo' : null, text: t('whereTitle')}),
        button(FILLED, 'gps', on.gps, t('useGps')),
        list('options',
            view.hasMap && entry('option', 'pick', on.pick, glyph('map'), t('chooseOnMap')),
            entry('option', 'example', on.example, glyph('pin'), t('example'))),
        view.gps === 'waiting' && h('p', {class: 'waiting', text: t('gpsWaiting')}),
        view.message && problem(view.message),
        h('p', {class: 'private', text: t('wherePrivate')}),
        view.position && button('plain', 'cancel', on.cancel, t('cancel')));
}

function position(view, on) {
    const {source, accuracy} = view.position;
    const how = source === 'gps' ? t('fromGps', {m: metres(accuracy || 0)}) : t(source === 'tap' ? 'fromTap' : 'fromExample');
    return h('div', {class: 'position'}, h('span', {class: 'dot'}),
        h('p', {}, h('span', {class: 'label', text: t('position')}), ' ', h('span', {class: 'how', text: how})),
        button('plain', 'change', on.change, t('change')));
}

function tabs(view, on) {
    const tab = name => h('button', {class: view.tab === name ? 'tab button button-active' : 'tab button', type: 'button', 'data-key': `tab-${name}`,
                                     'aria-pressed': String(view.tab === name), onclick: () => on.tab(name)}, t(name));
    return h('div', {class: 'tabs segmented segmented-strong', role: 'group', 'aria-label': t('places')}, tab('assembly'), tab('medical'),
        h('span', {class: 'segmented-highlight'}));
}

/* The route in words: how far, what to do about what is known, how much of it is known, and the turns. */
function way(found, place, view, on) {
    const groups = GROUPS.filter(name => found.by[name] >= 1);
    const key = groups.map(name => `${t(`group.${name}`)} · ${metres(found.by[name])}`);
    const parts = groups.map(name => {
        const part = h('span', {class: `part ${name}`});
        part.style.flexGrow = found.by[name];                   // as wide as its share of the walk
        return part;
    });

    const turns = [];
    if (found.off.start >= 10) turns.push(h('li', {}, h('span', {text: t('step.toStreet', {m: metres(found.off.start)})})));
    for (const step of steps(found)) {
        turns.push(h('li', {}, h('span', {text: t(`step.${step.turn}`, {name: streetName(step.name, step.kind)})}),
            h('span', {class: 'far', text: metres(step.metres)}),
            step.worst === 'blocked' && h('span', {class: 'told blocked', text: t('group.blocked')})));
    }
    const last = found.off.end >= 10 ? ` (${t('step.fromStreet', {m: metres(found.off.end)})})` : '';
    turns.push(h('li', {}, h('span', {text: t('step.arrive', {name: place.name}) + last})));

    const arriveAt = clock(new Date(Date.now() + found.seconds * 1000));
    return [
        h('div', {class: 'walk-box'},
            glyph('walk'),
            h('div', {class: 'walk-info'},
                h('p', {class: 'walk', text: walk(found)}),
                h('p', {class: 'eta', text: t('eta', {when: arriveAt})}))),
        h('p', {class: `verdict ${found.worst}`}, glyph(GLYPH[found.worst]), h('span', {text: verdict(found)})),
        groups.length > 0 && h('div', {class: 'bar', role: 'img', 'aria-label': key.join(', ')}, parts),
        groups.length > 0 && h('ul', {class: 'key', 'aria-hidden': 'true'},
            groups.map((name, i) => h('li', {}, h('span', {class: `swatch ${name}`}), key[i]))),
        h('p', {class: 'trust', text: t('trust')}),
        h('details', {class: 'steps', open: view.stepsOpen, ontoggle: event => on.steps(event.currentTarget.open)},
            h('summary', {}, h('span', {text: t('steps')}), glyph('forward')), h('ol', {}, turns)),
    ];
}

/* What the operators reported about the place, and when. Without a report the line says that nothing is known. */
function report(place) {
    const told = place.report;
    if (!told) return h('p', {class: 'report none', text: t('report.none')});
    return h('p', {class: `report ${told.state}`}, !takesPeople(place) && glyph('no'),
        h('span', {}, t(`report.${told.state}`), ' ', h('span', {class: 'when', text: t('reportedAt', {when: clock(told.reported_at)})})));
}

/* Available amenities/facilities at a place, shown as scannable icon + label chips. */
function facilities(place, compact = false) {
    const items = (place.facilities || []).filter(name => FACILITIES.includes(name));
    if (!items.length) return null;
    return h('ul', {class: compact ? 'facilities compact' : 'facilities', 'aria-label': t('facilitiesLabel')},
        items.map(name => h('li', {class: `facility fac-${name}`}, glyph(GLYPH[name]), h('span', {text: t(`facility.${name}`)}))));
}

/* The chosen place: its name, what was reported about it, the way to it; under the card, where we know it from. */
function card(view, on) {
    const place = view.selected, found = view.routes.get(place.id);
    const digits = (place.phone || '').replace(/[^\d+]/g, '');
    const kind = [t(`kind.${place.kind}`), t(place.official ? 'official' : 'unofficial'), emergency(place)].filter(Boolean).join(' · ');
    return [
        view.suggested && h('div', {class: 'block-title suggested', text: t('suggested')}),
        h('article', {class: 'card block block-strong inset'},
            h('div', {class: 'place-head'}, icon(place.kind, !takesPeople(place), 40), h('div', {},
                h('h2', {tabindex: '-1', text: place.name}),
                h('p', {class: 'kind', text: kind}))),
            facilities(place),
            report(place),
            found ? way(found, place, view, on) : h('p', {class: 'verdict'}, h('span', {text: t(view.position ? 'noRoute' : 'chooseFirst')})),
            digits && h('p', {class: 'contact'}, `${t('phone')}: `, h('a', {href: `tel:${digits}`, text: place.phone}))),
        h('div', {class: 'sources'},
            h('p', {class: 'source', text: t('source', {source: place.source, date: day(place.checked_on)})}),
            said(place.note) && h('p', {class: 'note', text: said(place.note)}),
            /^https:\/\//.test(place.source_url || '') &&
                h('a', {class: 'source-link', href: place.source_url, target: '_blank', rel: 'noopener noreferrer', text: t('openSource')})),
    ];
}

/* mixed: the places of the list are not all of one kind, so a line without a way says which kind it is. */
function row(place, view, on, mixed) {
    const found = view.routes.get(place.id), told = place.report, takes = takesPeople(place);
    const more = found ? walk(found) : view.position ? t('noRoute') : mixed ? kindOf(place) : '';
    return entry(takes ? 'row' : 'row off', `place-${place.id}`, () => on.choose(place.id), icon(place.kind, !takes),
        h('span', {class: 'row-name', text: place.name}),
        more && h('span', {class: 'row-more', text: more}),
        told && h('span', {class: `told ${told.state}`, text: t(`reportShort.${told.state}`)}),
        found && takes && h('span', {class: 'row-way'}, h('span', {class: `swatch ${LEGEND[found.worst]}`}),       // the way to a place that takes nobody is not the news
            t(`group.${LEGEND[found.worst]}`)),
        takes && facilities(place, true));
}

function others(view, on) {
    const rest = view.ranked.filter(place => place !== view.selected), shown = view.showAll ? rest : rest.slice(0, 3);
    if (!rest.length) return [];
    const mixed = new Set(view.ranked.map(kindOf)).size > 1;
    return [
        view.selected && h('h3', {class: 'block-title others-title', text: t('others')}),
        list('rows', shown.map(place => row(place, view, on, mixed)),
            rest.length > shown.length && h('li', {}, button('list-button', 'all', on.showAll, t('showAll', {n: rest.length})))),
    ];
}

/* The whole panel for this moment.
   view: {open, hasMap, position, asking, gps, message, tab, ranked (the places of the tab, best first), routes (place id ->
          route or null), selected, suggested, noneTakes (every place of the tab was reported full or closed), showAll,
          stepsOpen, received, revision}
   on:   what the buttons do: fold, gps, pick, example, cancel, change, tab(name), choose(id), showAll, steps(open) */
export function drawSheet(view, on) {
    return [handle(view, on), h('div', {class: 'body', hidden: !view.open},
        !view.position || view.asking ? where(view, on) : position(view, on),
        tabs(view, on),
        view.noneTakes && problem(t('allReported')),
        view.noneTakes && h('p', {class: 'advice', text: t(view.tab === 'assembly' ? 'openGround' : 'urgent')}),
        view.selected && card(view, on),
        !view.ranked.length && h('p', {class: 'waiting', text: t(view.tab === 'assembly' ? 'noAssembly' : 'noMedical')}),
        others(view, on),
        h('p', {class: 'foot', id: 'received', text: receivedLine(view)}))];
}

/* Nothing could be loaded: say so, say what to do anyway, and offer to try again. */
export function drawFailure(key, retry) {
    return [h('div', {class: 'body'}, problem(t(key)), h('p', {class: 'advice', text: t('openGround')}),
        button(FILLED, 'retry', retry, t('retry')))];
}

/* The top of a window: its title, and a way out that is there before any scrolling. */
const head = (title, close) => h('div', {class: 'dialog-head'}, h('h2', {text: title}),
    h('button', {class: 'shut', type: 'button', 'aria-label': t('close'), onclick: close}, glyph('close')));

export function exerciseWindow(pack, close) {
    return h('div', {class: 'dialog-body'},
        head(t('exerciseTitle'), close),
        h('p', {text: said(pack.exercise)}),
        pack.simulated && h('p', {text: t('simulated')}),
        button(FILLED, 'close', close, t('close')));
}

/* "About and legend": what the colours mean, what the app does with a position, what it keeps on the phone, where
   the information comes from. Without a pack (nothing could be loaded) it still says what the app is and what it
   does with a position.
   holds: what is on this phone now beside the language (app.js): {pack, app}. Only that is said to be kept. */
export function aboutWindow(pack, received, close, holds) {
    const sample = (name, words, mark = '') => h('li', {}, h('span', {class: `sample ${name}`, 'aria-hidden': 'true', text: mark}), h('span', {text: words}));
    const off = pack?.places.find(place => !takesPeople(place));
    return h('div', {class: 'dialog-body'},
        head(t('about'), close),
        h('p', {text: t('aboutWhat')}),
        h('h3', {text: t('legend')}),
        h('ul', {class: 'legend'},
            ['checked', 'unchecked', 'blocked', 'no_data'].map(name =>
                sample(name, `${t(`group.${name}`)}: ${t(`groupMore.${name}`)}.`, name === 'blocked' ? '× × ×' : '')),
            sample('route', t('legendRoute')),
            pack?.drone && sample('drone', `${t('legendDrone')} (${day(pack.drone.acquired)})`),
            KINDS.filter(kind => pack?.places.some(place => place.kind === kind)).map(kind => h('li', {}, icon(kind), h('span', {text: t(`kind.${kind}`)}))),
            off && h('li', {}, icon(off.kind, true), h('span', {text: t('legendOff')}))),
        h('p', {text: t('aboutPrivacy')}),
        h('p', {text: [t('keptLanguage'), holds.pack && t('keptPack'), holds.app && t('keptApp')].filter(Boolean).join(' ')}),
        h('p', {text: t('installTip')}),
        h('p', {text: t('aboutLimits')}),
        h('p', {text: t('aboutPrototype')}),
        pack && h('h3', {text: t('data')}),
        pack && h('ul', {class: 'credits'}, pack.credits.map(credit => h('li', {text: credit}))),
        pack && h('p', {class: 'foot', text: `${t('received', {when: clock(received)})} · ${pack.revision}`}),
        button(FILLED, 'close', close, t('close')));
}
