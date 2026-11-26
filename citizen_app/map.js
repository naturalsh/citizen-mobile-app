/* The map: the streets by what is known about them, the places to go, the person and the route.

   MapLibre GL JS draws everything from the pack itself. No map tiles are downloaded: the map works without a
   connection, and no map company learns what anybody looks at. Words that follow the citizen's language are page
   elements, not map labels: the map only carries the letter shapes of Latin script (vendor/fonts). */

import {t, day, number, streetName, language} from './i18n.js';
import {group, takesPeople} from './route.js';

export const KINDS = ['assembly_point', 'shelter', 'hospital', 'clinic'];
const COLOUR = {checked: '#15803d', unchecked: '#b45309', no_data: '#6b7280', blocked: '#b91c1c', route: '#0066cc'};
const SIGN = {assembly_point: '#15803d', shelter: '#0f766e', hospital: '#1d4ed8', clinic: '#0e7490'};
const FONT = ['noto-sans-regular'];
const BIG = ['trunk', 'trunk_link', 'primary', 'primary_link'];
const MIDDLE = ['secondary', 'secondary_link', 'tertiary', 'tertiary_link'];
const PATHS = ['footway', 'path', 'steps', 'pedestrian', 'cycleway', 'track'];
const ON_TOP = ['blocked', 'unchecked', 'checked', 'no_data'];           // where streets meet, the worse news is painted over the better
const NOTHING = {type: 'FeatureCollection', features: []};
const AROUND = 0.004;                // degrees shown around the drone flight at first: about 400 m
const BEYOND = 0.02;                 // how far past the area the map may be moved: about 2 km

/* The sign of a kind of place as a small drawing. No image files, and never a red cross (a protected emblem).
   off: the place was reported full or closed. Its sign is grey and struck through, so it reads without colour too. */
export function sign(kind, px = 32, off = false) {
    const canvas = document.createElement('canvas'), s = px * 2;               // drawn double: sharp on phone screens
    canvas.width = canvas.height = s;
    canvas.className = 'sign';
    const pen = canvas.getContext('2d');
    const square = (x, size, corner) => {
        pen.beginPath();
        pen.moveTo(x + corner, x);
        pen.arcTo(x + size, x, x + size, x + size, corner);
        pen.arcTo(x + size, x + size, x, x + size, corner);
        pen.arcTo(x, x + size, x, x, corner);
        pen.arcTo(x, x, x + size, x, corner);
        pen.fill();
    };
    const line = (...points) => {
        pen.beginPath();
        points.forEach(([x, y], i) => (i ? pen.lineTo(x * s, y * s) : pen.moveTo(x * s, y * s)));
        pen.stroke();
    };
    pen.fillStyle = '#ffffff';
    square(0, s, s * 0.22);
    pen.fillStyle = off ? '#6b7280' : SIGN[kind] || '#374151';
    square(s * 0.06, s * 0.88, s * 0.17);
    pen.strokeStyle = pen.fillStyle = '#ffffff';
    pen.lineWidth = s * 0.09;
    pen.lineCap = pen.lineJoin = 'round';
    if (kind === 'assembly_point') {                                           // four arrows towards the middle
        for (const [dx, dy] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
            const tip = [0.5 + dx * 0.13, 0.5 + dy * 0.13];
            line([0.5 + dx * 0.31, 0.5 + dy * 0.31], tip);
            line([tip[0] + dx * 0.15, tip[1]], tip, [tip[0], tip[1] + dy * 0.15]);
        }
    } else if (kind === 'shelter') {                                           // a roof over walls
        line([0.2, 0.5], [0.5, 0.24], [0.8, 0.5]);
        line([0.3, 0.52], [0.3, 0.76], [0.7, 0.76], [0.7, 0.52]);
    } else if (kind === 'hospital') {                                          // H
        pen.lineWidth = s * 0.11;
        line([0.33, 0.26], [0.33, 0.74]);
        line([0.67, 0.26], [0.67, 0.74]);
        line([0.33, 0.5], [0.67, 0.5]);
    } else {                                                                   // a health centre: +
        pen.lineWidth = s * 0.13;
        line([0.27, 0.5], [0.73, 0.5]);
        line([0.5, 0.27], [0.5, 0.73]);
    }
    if (off) {                                                                 // a dark bar with a white edge, corner to corner
        pen.lineWidth = s * 0.2;
        line([0.16, 0.84], [0.84, 0.16]);
        pen.strokeStyle = '#111827';
        pen.lineWidth = s * 0.1;
        line([0.16, 0.84], [0.84, 0.16]);
    }
    return canvas;
}

/* A name the map can write: only letters whose shapes we carry (Latin, with Turkish). */
const writable = name => (name && [...name].every(letter => letter.codePointAt(0) < 512) ? name : '');

const byKind = (big, middle, small, path) => ['match', ['get', 'kind'], BIG, big, MIDDLE, middle, PATHS, path, small];
const wide = (more = 0) => ['interpolate', ['exponential', 1.6], ['zoom'],
    11, ['+', more, byKind(1.5, 1, 0.5, 0.3)],
    15, ['+', more, byKind(6, 4.5, 3, 1.5)],
    18, ['+', more, byKind(22, 17, 13, 5)]];
const mark = ['interpolate', ['linear'], ['zoom'], 12, 2.5, 15, 4, 18, 7];
const is = name => ['==', ['get', 'group'], name];
const round = {'line-cap': 'round', 'line-join': 'round'};

function style() {
    const source = () => ({type: 'geojson', data: NOTHING});
    return {
        version: 8,
        glyphs: `${new URL('vendor/fonts/', location.href).href}{fontstack}/{range}.pbf`,
        sources: {streets: source(), drone: source(), route: source(), places: source()},
        layers: [
            {id: 'ground', type: 'background', paint: {'background-color': '#e8ebf0'}},
            {id: 'drone', type: 'fill', source: 'drone', paint: {'fill-color': '#f8fafc'}},
            {id: 'street-edge', type: 'line', source: 'streets', layout: round, paint: {'line-color': '#c0c7d2', 'line-width': wide(2)}},
            {id: 'street', type: 'line', source: 'streets', layout: round, paint: {'line-color': '#ffffff', 'line-width': wide()}},
            {id: 'drone-edge', type: 'line', source: 'drone',
             paint: {'line-color': '#475569', 'line-width': 1.5, 'line-dasharray': [3, 3]}},

            // what is known about a street: never by colour alone (solid, dashed, crossed)
            {id: 'checked', type: 'line', source: 'streets', filter: is('checked'), layout: round,
             paint: {'line-color': COLOUR.checked, 'line-width': mark}},
            {id: 'unchecked', type: 'line', source: 'streets', filter: is('unchecked'),
             paint: {'line-color': COLOUR.unchecked, 'line-width': mark, 'line-dasharray': [2, 1.5]}},
            {id: 'blocked', type: 'line', source: 'streets', filter: is('blocked'), layout: round,
             paint: {'line-color': COLOUR.blocked, 'line-width': mark}},
            {id: 'blocked-crosses', type: 'symbol', source: 'streets', filter: is('blocked'), minzoom: 14,
             layout: {'symbol-placement': 'line', 'symbol-spacing': 34, 'text-field': '×', 'text-font': FONT, 'text-size': 15,
                      'text-allow-overlap': true, 'text-ignore-placement': true, 'text-keep-upright': false},
             paint: {'text-color': '#ffffff', 'text-halo-color': COLOUR.blocked, 'text-halo-width': 2.5}},

            // the route: a blue band, and inside it what is known about each stretch
            {id: 'route-band', type: 'line', source: 'route', filter: ['has', 'group'], layout: round,
             paint: {'line-color': COLOUR.route, 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 9, 16, 14]}},
            {id: 'route-white', type: 'line', source: 'route', filter: ['has', 'group'], layout: round,
             paint: {'line-color': '#ffffff', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 5, 16, 9]}},
            {id: 'route-known', type: 'line', source: 'route', filter: ['has', 'group'], layout: round,
             paint: {'line-color': ['match', ['get', 'group'], 'checked', COLOUR.checked, 'unchecked', COLOUR.unchecked,
                                    'blocked', COLOUR.blocked, COLOUR.no_data],
                     'line-width': ['interpolate', ['linear'], ['zoom'], 12, 3, 16, 5]}},
            {id: 'route-off-street', type: 'line', source: 'route', filter: ['!', ['has', 'group']],
             paint: {'line-color': COLOUR.route, 'line-width': 3, 'line-dasharray': [1, 1.5]}},

            {id: 'names', type: 'symbol', source: 'streets', minzoom: 15, filter: ['!=', ['get', 'name'], ''],
             layout: {'symbol-placement': 'line', 'symbol-spacing': 320, 'text-field': ['get', 'name'], 'text-font': FONT,
                      'text-size': ['interpolate', ['linear'], ['zoom'], 15, 11, 18, 14]},
             paint: {'text-color': '#374151', 'text-halo-color': '#ffffff', 'text-halo-width': 1.6}},
        ],
    };
}

/* The places are added once their signs exist. The map places what is on top first, so the names, in a layer of
   their own under the signs, give way to every sign: a name never runs over the sign of another place. The chosen
   place is drawn bigger, with its name always shown. */
const OTHERS = ['places', 'place-names'];
function placeLayers() {
    const icon = {'icon-image': ['get', 'sign'], 'icon-allow-overlap': true, 'icon-padding': 0};
    const text = {'text-field': ['get', 'name'], 'text-font': FONT, 'text-anchor': 'top', 'text-max-width': 9};
    const paint = {'text-color': '#111827', 'text-halo-color': '#ffffff', 'text-halo-width': 1.8};
    const other = ['!=', ['get', 'id'], ''];
    return [
        {id: 'place-names', type: 'symbol', source: 'places', minzoom: 14, filter: other, paint,
         layout: {...text, 'text-size': 12, 'text-offset': [0, 1.35]}},
        {id: 'places', type: 'symbol', source: 'places', filter: other, layout: {...icon, 'icon-size': 0.8}},
        {id: 'place-chosen', type: 'symbol', source: 'places', filter: ['==', ['get', 'id'], ''], paint,
         layout: {...icon, ...text, 'icon-size': 1.2, 'text-size': 14, 'text-offset': [0, 1.5], 'text-allow-overlap': true}},
    ];
}

/* How far, in screen pixels, a tap at (x, y) is from the line drawn through `points`. */
function away(x, y, points) {
    let least = Infinity;
    for (let i = 1; i < points.length; i++) {
        const a = points[i - 1], dx = points[i].x - a.x, dy = points[i].y - a.y;
        const along = Math.max(0, Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / (dx * dx + dy * dy || 1)));
        least = Math.min(least, Math.hypot(a.x + along * dx - x, a.y + along * dy - y));
    }
    return least;
}

const sentence = words => words.charAt(0).toLocaleUpperCase(language()) + words.slice(1);

/* What the app says about one street, for the little window that opens when it is tapped. */
function aboutStreet(street) {
    const known = group(street), lines = [];
    if (street.observed_at && street.seen_by) lines.push(t(`seen.${street.seen_by}`, {date: day(street.observed_at)}));
    if (street.confirmed && street.checked_at) lines.push(t('confirmedOn', {date: day(street.checked_at)}));
    else if (known === 'blocked') lines.push(t('notConfirmed'));
    if (known !== 'blocked' && known !== 'no_data' && street.free_width_m != null) lines.push(t('width', {m: number(street.free_width_m)}));
    if (street.status === 'narrow' && street.confirmed) lines.push(t('narrow'));
    if (street.simulated) lines.push(t('simulatedEvent'));
    const element = (tag, name, text) => {
        const made = document.createElement(tag);
        made.className = name;
        made.textContent = text;
        return made;
    };
    const box = element('div', 'street-card', '');
    box.append(element('strong', 'street-name', streetName(street.name, street.kind)),
               element('p', `known ${known}`, t(`group.${known}`)),
               element('p', '', sentence(`${t(`groupMore.${known}`)}.`)),
               ...lines.map(line => element('p', '', line)));
    return box;
}

/* The map in `container`, or null when this phone cannot draw one (the list and the steps work without it).
   `on`: what the app wants to hear: place(id) a place was tapped, pick([lon, lat]) the map was tapped while the
   person chooses where they are, moved([lon, lat]) the person dragged their own mark. */
export function createMap(container, on) {
    if (!window.maplibregl) return null;
    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    let map;
    try {
        map = new maplibregl.Map({container, style: style(), center: [0, 0], zoom: 11, minZoom: 11, maxZoom: 19,
                                  attributionControl: false, dragRotate: false, pitchWithRotate: false, touchPitch: false,
                                  renderWorldCopies: false});
    } catch (problem) {
        console.warn('No map on this device:', problem);
        return null;
    }
    map.touchZoomRotate.disableRotation();
    map.keyboard.disableRotation();
    map.addControl(new maplibregl.NavigationControl({showCompass: false}), 'top-right');
    map.addControl(new maplibregl.AttributionControl({compact: true, customAttribution: '© OpenStreetMap contributors'}), 'bottom-right');

    const ready = new Promise(done => map.once('load', done)).then(() => {
        for (const kind of KINDS) {
            for (const off of [false, true]) {                                 // every sign twice: as it is, and struck through
                const drawn = sign(kind, 32, off);
                map.addImage(off ? `${kind}-off` : kind, drawn.getContext('2d').getImageData(0, 0, drawn.width, drawn.height), {pixelRatio: 2});
            }
        }
        placeLayers().forEach(layer => map.addLayer(layer));
    });

    let pack = null, picking = false, bubble = null, first = true, credit = true;
    const dot = document.createElement('div');
    dot.className = 'you';
    dot.setAttribute('aria-label', t('you'));
    const you = new maplibregl.Marker({element: dot, draggable: true});
    you.on('dragend', () => on.moved(you.getLngLat().toArray()));
    const label = document.createElement('div');
    label.className = 'drone-label';
    const flight = new maplibregl.Marker({element: label, anchor: 'bottom-left'});
    const relabel = () => {
        dot.setAttribute('aria-label', t('you'));
        dot.title = t('you');
        label.textContent = pack?.drone ? t('droneLabel', {date: day(pack.drone.acquired)}) : '';
        label.hidden = !pack?.drone || map.getZoom() < 13.5;
        bubble?.remove();
    };
    map.on('zoom', () => {
        label.hidden = !pack?.drone || map.getZoom() < 13.5;
    });

    map.on('click', event => {
        const {x, y} = event.point;
        if (picking) return on.pick(event.lngLat.toArray());
        bubble?.remove();
        if (!pack) return;
        const near = pack.places.map(place => {                                // a place: within a fingertip of its sign
            const at = map.project([place.lon, place.lat]);
            return {place, far: Math.hypot(at.x - x, at.y - y)};
        }).sort((a, b) => a.far - b.far)[0];
        if (near && near.far < 24) return on.place(near.place.id);
        const hits = map.queryRenderedFeatures([[x - 10, y - 10], [x + 10, y + 10]], {layers: ['street']}).map(feature => {
            const street = pack.streets[feature.properties.i];                 // the whole street: the map only holds pieces of it
            return {street, rank: ON_TOP.indexOf(group(street)), far: away(x, y, street.line.map(point => map.project(point)))};
        });
        if (!hits.length) return;
        // the street under the finger. A finger is not exact: of the streets about as near as the nearest, the one painted on top
        const least = Math.min(...hits.map(one => one.far));
        const hit = hits.filter(one => one.far <= least + 4).sort((a, b) => a.rank - b.rank || a.far - b.far)[0];
        bubble = new maplibregl.Popup({maxWidth: '280px'}).setLngLat(event.lngLat).setDOMContent(aboutStreet(hit.street)).addTo(map);
    });

    const set = (name, features) => map.getSource(name).setData({type: 'FeatureCollection', features});
    const box = ([south, west, north, east], more) => [[west - more, south - more], [east + more, north + more]];

    return {
        /* A new pack: its streets, the drone flight, its places. The first one also decides what the map looks at. */
        usePack(next) {
            pack = next;
            ready.then(() => {
                set('streets', pack.streets.map((street, i) => ({
                    type: 'Feature', geometry: {type: 'LineString', coordinates: street.line},
                    properties: {i, group: group(street), kind: street.kind, name: writable(street.name)}})));
                set('places', pack.places.map(place => ({
                    type: 'Feature', geometry: {type: 'Point', coordinates: [place.lon, place.lat]},
                    properties: {id: place.id, kind: place.kind, sign: takesPeople(place) ? place.kind : `${place.kind}-off`,
                                 name: writable(place.name)}})));
                if (pack.drone) {
                    const [south, west, north, east] = pack.drone.bbox;
                    set('drone', [{type: 'Feature', properties: {}, geometry: {type: 'Polygon', coordinates: [[
                        [west, south], [east, south], [east, north], [west, north], [west, south]]]}}]);
                    flight.setLngLat([west, north]).addTo(map);
                } else {
                    set('drone', []);
                    flight.remove();
                }
                relabel();
                if (first) {
                    first = false;
                    map.resize();
                    map.setMaxBounds(box(pack.area.bbox, BEYOND));
                    map.fitBounds(pack.drone ? box(pack.drone.bbox, AROUND) : box(pack.area.bbox, 0), {duration: 0});
                }
            });
        },

        /* The person, the chosen place and the route between them. `fit`: move the map so that all of it shows. */
        draw({position, place, found, fit}) {
            ready.then(() => {
                if (position) you.setLngLat(position.lonLat).addTo(map);
                else you.remove();
                if (position && credit) {                                      // the map is in use now: its credit folds to an "i",
                    credit = false;                                            // as it does by itself when the map is first moved
                    container.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show');
                }
                const id = place ? place.id : '';
                for (const layer of OTHERS) map.setFilter(layer, ['!=', ['get', 'id'], id]);
                map.setFilter('place-chosen', ['==', ['get', 'id'], id]);
                const lines = [];
                if (found && found.parts.length) {
                    const start = found.parts[0].line[0], end = found.parts[found.parts.length - 1].line.at(-1);
                    lines.push({type: 'Feature', properties: {}, geometry: {type: 'LineString', coordinates: [position.lonLat, start]}},
                               {type: 'Feature', properties: {}, geometry: {type: 'LineString', coordinates: [end, [place.lon, place.lat]]}});
                    for (const part of found.parts) {
                        lines.push({type: 'Feature', properties: {group: part.group}, geometry: {type: 'LineString', coordinates: part.line}});
                    }
                }
                set('route', lines);
                if (!fit) return;
                const points = [...(position ? [position.lonLat] : []), ...(found ? found.parts.flatMap(part => part.line) : []),
                                ...(place ? [[place.lon, place.lat]] : [])];
                if (!points.length) return;
                bubble?.remove();                                              // the map moves on: what was said about a street stays behind
                map.resize();                                                  // the panel may just have changed size
                const duration = still ? 0 : 600;
                if (points.length === 1) return map.easeTo({center: points[0], zoom: Math.max(map.getZoom(), 16), duration});
                const around = points.reduce((all, point) => all.extend(point), new maplibregl.LngLatBounds(points[0], points[0]));
                // room for the zoom buttons, for the name under the place and for the credit in the corner: less above and
                // below on a low map (a small phone with the answer open), where it would leave the way a strip, and more
                // where a notch or the bar at the bottom pushes the corner in (app.css)
                const low = Math.min(1, container.clientHeight / 240);
                const corner = getComputedStyle(container.querySelector('.maplibregl-ctrl-bottom-right'));
                map.fitBounds(around, {padding: {top: Math.round(52 * low), bottom: Math.round(68 * low) + (parseFloat(corner.bottom) || 0),
                                                 left: 44, right: 66 + (parseFloat(corner.right) || 0)}, maxZoom: 17.5, duration});
            });
        },

        /* While the person chooses where they are, a tap means "here" and nothing else. */
        picking(now) {
            picking = now;
            map.getCanvas().style.cursor = now ? 'crosshair' : '';
            if (now) bubble?.remove();
        },

        relabel,
        resize() {
            ready.then(() => map.resize());
        },
    };
}
