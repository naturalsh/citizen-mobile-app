/* Finds the walking route ON THE PHONE, from the area pack alone (drone_vision/public_pack.py).
   Nothing here touches the page or the network: the same file runs in the browser and in the tests
   (tests/citizen/route.test.mjs), and the service never learns where anybody stands.

   The rule for people on foot: a street costs its length times a factor, and the route is the cheapest way.

       checked by a person (open, narrow)   x 1
       not checked yet                      x 1.3
       no information                       x 1.8
       reported blocked                     x 8     (x 40 once a person confirmed the blockage)

   A blocked street is never forbidden. Somebody whose only way out goes over it must still get an answer, with a
   warning, not "no route". It is only very expensive, so every reasonable detour wins. */

export const FACTOR = Object.freeze({checked: 1, unchecked: 1.3, no_data: 1.8, blocked: 8, blocked_confirmed: 40});
export const WALK_M_PER_S = 1;      // slow on purpose: debris, children, older people
export const NEAR_M = 250;          // farther than this from every street we do not guess where somebody stands
const LOOK_M = 15;                  // a turn is judged over this stretch before and after a corner

/* What a street counts as. The service already applies the rule ("open" only after a person confirmed it), and the
   phone checks it again: an "open" that nobody confirmed counts as unchecked, a word we do not know as blocked. */
export function group(street) {
    if (street.status === 'open' || street.status === 'narrow') return street.confirmed === true ? 'checked' : 'unchecked';
    return ['unchecked', 'no_data'].includes(street.status) ? street.status : 'blocked';
}

export function factor(street) {
    const kind = group(street);
    return kind === 'blocked' && street.confirmed === true ? FACTOR.blocked_confirmed : FACTOR[kind];
}

/* The streets of a pack as a network: pieces of street that meet at their ends.
   Everything is measured on a flat sheet in metres around the middle of the area (a few km: the error is far below
   what a phone's GPS knows). */
export function buildNetwork(pack) {
    const [south, west, north, east] = pack.area.bbox;
    const lon0 = (west + east) / 2, lat0 = (south + north) / 2;
    const phi = lat0 * Math.PI / 180;                                     // metres per degree at this latitude (WGS84)
    const mx = 111412.84 * Math.cos(phi) - 93.5 * Math.cos(3 * phi) + 0.118 * Math.cos(5 * phi);
    const my = 111132.92 - 559.82 * Math.cos(2 * phi) + 1.175 * Math.cos(4 * phi);
    const flat = ([lon, lat]) => [(lon - lon0) * mx, (lat - lat0) * my];

    const numbers = new Map();                                            // OpenStreetMap node -> 0, 1, 2 ...
    const number = node => {
        if (!numbers.has(node)) numbers.set(node, numbers.size);
        return numbers.get(node);
    };
    const pieces = pack.streets.map((street, index) => {
        const xy = street.line.map(flat), at = [0];                       // at[i]: metres from the first end to point i
        for (let i = 1; i < xy.length; i++) at.push(at[i - 1] + Math.hypot(xy[i][0] - xy[i - 1][0], xy[i][1] - xy[i - 1][1]));
        return {index, street, xy, at, metres: at[at.length - 1], ends: street.ends.map(number),
                group: group(street), factor: factor(street), main: false};
    });
    const meets = Array.from({length: numbers.size}, () => []);           // node -> the pieces that end there
    for (const piece of pieces) {
        meets[piece.ends[0]].push(piece);
        if (piece.ends[1] !== piece.ends[0]) meets[piece.ends[1]].push(piece);
    }

    // A map cut out of a town has a few stubs that lead nowhere (a yard, a street cut at the edge). Somebody put on
    // one would get "no route" to everything, so people and places are only ever put on the biggest connected part.
    const part = new Int32Array(numbers.size).fill(-1), length = [];
    for (let first = 0; first < numbers.size; first++) {
        if (part[first] !== -1) continue;
        const todo = [first];
        part[first] = length.length;
        length.push(0);
        while (todo.length) {
            const node = todo.pop();
            for (const piece of meets[node]) {
                for (const other of piece.ends) {
                    if (part[other] === -1) {
                        part[other] = part[first];
                        todo.push(other);
                    }
                }
            }
        }
    }
    for (const piece of pieces) length[part[piece.ends[0]]] += piece.metres;
    const biggest = length.indexOf(Math.max(...length));
    for (const piece of pieces) piece.main = part[piece.ends[0]] === biggest;

    return {pieces, meets, nodes: numbers.size, flat};
}

/* The point of a piece that lies `m` metres from its first end, as [lon, lat]. */
function pointAt(piece, m) {
    const {at} = piece, line = piece.street.line;
    let i = 1;
    while (i < at.length - 1 && at[i] < m) i++;
    const span = at[i] - at[i - 1], t = span ? Math.min(1, Math.max(0, (m - at[i - 1]) / span)) : 0;
    return [line[i - 1][0] + t * (line[i][0] - line[i - 1][0]), line[i - 1][1] + t * (line[i][1] - line[i - 1][1])];
}

/* The line of a piece between two marks (metres from its first end), in the order it is walked. */
function stretch(piece, from, to) {
    const low = Math.min(from, to), high = Math.max(from, to);
    const points = [pointAt(piece, low)];
    piece.at.forEach((m, i) => {
        if (m > low && m < high) points.push(piece.street.line[i]);
    });
    points.push(pointAt(piece, high));
    return from <= to ? points : points.reverse();
}

/* Where somebody at [lon, lat] is on the network: the nearest point of the nearest street.
   -> {piece, along (metres from the piece's first end), off (metres between the person and the street), point}
   or null when no street is within `limit` metres. */
export function nearest(network, lonLat, limit = NEAR_M) {
    const [px, py] = network.flat(lonLat);
    let best = null;
    for (const piece of network.pieces) {
        if (!piece.main) continue;
        const {xy, at} = piece;
        for (let i = 1; i < xy.length; i++) {
            const ax = xy[i - 1][0], ay = xy[i - 1][1], dx = xy[i][0] - ax, dy = xy[i][1] - ay, len2 = dx * dx + dy * dy;
            const t = len2 ? Math.min(1, Math.max(0, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
            const off = Math.hypot(px - ax - t * dx, py - ay - t * dy);
            if (!best || off < best.off) best = {piece, off, along: at[i - 1] + t * Math.sqrt(len2)};
        }
    }
    return best && best.off <= limit ? {...best, point: pointAt(best.piece, best.along)} : null;
}

/* A small heap: always hands back the cheapest node that is waiting. */
class Heap {
    constructor() {
        this.items = [];
    }

    get size() {
        return this.items.length;
    }

    push(cost, node) {
        const items = this.items;
        let i = items.push([cost, node]) - 1;
        while (i > 0) {
            const up = (i - 1) >> 1;
            if (items[up][0] <= items[i][0]) break;
            [items[up], items[i]] = [items[i], items[up]];
            i = up;
        }
    }

    pop() {
        const items = this.items, top = items[0], last = items.pop();
        if (items.length) {
            items[0] = last;
            for (let i = 0; ;) {
                const left = 2 * i + 1, right = left + 1;
                let least = i;
                if (left < items.length && items[left][0] < items[least][0]) least = left;
                if (right < items.length && items[right][0] < items[least][0]) least = right;
                if (least === i) break;
                [items[least], items[i]] = [items[i], items[least]];
                i = least;
            }
        }
        return top;
    }
}

/* The cheapest way from `start` (a nearest() answer) to EVERY corner of the network, in one sweep (Dijkstra).
   After it, the route to any place is read off without searching again. */
export function reach(network, start) {
    const cost = new Float64Array(network.nodes).fill(Infinity);
    const came = new Array(network.nodes).fill(null);       // how we got to a node: {piece, from (node, or -1 = the start), exit}
    const waiting = new Heap();
    const offer = (node, value, piece, from, exit) => {
        if (value < cost[node]) {
            cost[node] = value;
            came[node] = {piece, from, exit};
            waiting.push(value, node);
        }
    };
    const {piece, along} = start;                           // the person stands somewhere along a piece: both ends are offered
    offer(piece.ends[0], along * piece.factor, piece, -1, 0);
    offer(piece.ends[1], (piece.metres - along) * piece.factor, piece, -1, piece.metres);
    while (waiting.size) {
        const [value, node] = waiting.pop();
        if (value > cost[node]) continue;                   // an older, dearer offer of the same node
        for (const next of network.meets[node]) {
            const other = next.ends[0] === node ? next.ends[1] : next.ends[0];
            offer(other, value + next.metres * next.factor, next, node, null);
        }
    }
    return {start, cost, came};
}

/* The route from the start of `reached` to `target` (a nearest() answer for a place), or null when there is none.

   -> {metres    everything to walk: to the street, along the streets, from the street to the place
       seconds   at WALK_M_PER_S
       cost      what the route was chosen by (metres times factors): places are ranked by it
       by        metres of street per group: {checked, unchecked, no_data, blocked}
       worst     'checked' (every street checked by a person) | 'partly' | 'blocked' (crosses a blocked street)
       off       {start, end}: metres off the streets at both ends
       parts     the pieces in walking order: {street, index, group, metres, line, bend}
                 bend: degrees turned when entering the piece, left is positive} */
export function route(network, reached, target) {
    const {start, cost, came} = reached, {piece, along} = target;
    const ways = [{cost: cost[piece.ends[0]] + along * piece.factor, node: piece.ends[0], enter: 0},
                  {cost: cost[piece.ends[1]] + (piece.metres - along) * piece.factor, node: piece.ends[1], enter: piece.metres}];
    if (piece === start.piece) ways.push({cost: Math.abs(along - start.along) * piece.factor, node: -1});   // along the same piece
    const best = ways.reduce((a, b) => (b.cost < a.cost ? b : a));
    if (!Number.isFinite(best.cost)) return null;

    let legs = [];                                          // {piece, from, to}: marks along the piece, in walking order
    if (best.node === -1) legs.push({piece, from: start.along, to: along});
    else {
        legs.push({piece, from: best.enter, to: along});
        for (let node = best.node; node !== -1;) {          // walk the "came" notes back to the start
            const step = came[node], forward = step.piece.ends[0] === step.from;
            if (step.from === -1) legs.push({piece: step.piece, from: start.along, to: step.exit});
            else legs.push({piece: step.piece, from: forward ? 0 : step.piece.metres, to: forward ? step.piece.metres : 0});
            node = step.from;
        }
        legs.reverse();
    }
    legs = legs.filter(leg => leg.from !== leg.to);

    const by = {checked: 0, unchecked: 0, no_data: 0, blocked: 0};
    const heading = (leg, entering) => {                    // the direction walked just after entering / before leaving a leg
        const way = Math.sign(leg.to - leg.from), far = Math.min(LOOK_M, Math.abs(leg.to - leg.from));
        const [a, b] = entering ? [leg.from, leg.from + way * far] : [leg.to - way * far, leg.to];
        const [ax, ay] = network.flat(pointAt(leg.piece, a)), [bx, by_] = network.flat(pointAt(leg.piece, b));
        return [bx - ax, by_ - ay];
    };
    const parts = legs.map((leg, i) => {
        const metres = Math.abs(leg.to - leg.from);
        by[leg.piece.group] += metres;
        let bend = 0;
        if (i > 0) {
            const [ax, ay] = heading(legs[i - 1], false), [bx, by_] = heading(leg, true);
            bend = Math.atan2(ax * by_ - ay * bx, ax * bx + ay * by_) * 180 / Math.PI;
        }
        return {street: leg.piece.street, index: leg.piece.index, group: leg.piece.group, metres, bend,
                line: stretch(leg.piece, leg.from, leg.to)};
    });
    const metres = start.off + parts.reduce((sum, part) => sum + part.metres, 0) + target.off;
    const worst = by.blocked >= 1 ? 'blocked' : by.unchecked + by.no_data >= 1 ? 'partly' : 'checked';
    return {metres, seconds: metres / WALK_M_PER_S, cost: best.cost + (start.off + target.off) * FACTOR.no_data,
            by, worst, off: {start: start.off, end: target.off}, parts};
}

/* The route as a few steps to read: consecutive pieces of the same street are one step.
   -> [{name (null: the street has no name), kind, metres, turn: 'start' | 'straight' | 'left' | 'right', worst}] */
export function steps(found) {
    const order = ['checked', 'unchecked', 'no_data', 'blocked'];
    const list = [];
    for (const part of found.parts) {
        const name = part.street.name || null, kind = part.street.kind, last = list[list.length - 1];
        if (last && last.name === name && (name !== null || last.kind === kind)) {
            last.metres += part.metres;
            if (order.indexOf(part.group) > order.indexOf(last.worst)) last.worst = part.group;
        } else {
            const turn = !last ? 'start' : Math.abs(part.bend) < 30 ? 'straight' : part.bend > 0 ? 'left' : 'right';
            list.push({name, kind, metres: part.metres, turn, worst: part.group});
        }
    }
    return list;
}

/* The streets whose answer differs between two packs of the same area (the operator checked or closed something).
   -> [{street (as it is now), before, after}] with the groups 'checked' | 'unchecked' | 'no_data' | 'blocked'. */
export function changes(before, after) {
    const key = street => `${street.way}:${street.ends[0]}-${street.ends[1]}`;
    const was = new Map(before.streets.map(street => [key(street), street]));
    const list = [];
    for (const street of after.streets) {
        const old = was.get(key(street));
        if (old && group(old) !== group(street)) list.push({street, before: group(old), after: group(street)});
    }
    return list;
}

/* What became of the authority's notice between two packs: 'new' (the first one, or another one), 'gone' (it was
   taken back), or null (the same as before, or none both times). */
export function noticed(before, after) {
    if (JSON.stringify(before.notice ?? null) === JSON.stringify(after.notice ?? null)) return null;
    return after.notice ? 'new' : 'gone';
}

/* Does the place take people in, as far as anybody told us? Only a place the operators reported full or closed does
   not. Without a report nothing is known about it: that is not a reason to send nobody there. */
export const takesPeople = place => !['full', 'closed'].includes(place.report?.state);

/* The places in the order a person should think of them: first the ones that take people in (with `emergencyFirst`
   an emergency department before the rest), the cheapest way first (`cost`: place -> the cost of the way to it,
   Infinity when there is none); then the ones reported full; last the ones reported closed. None is left out: the
   person sees why a place near them is not the one suggested. "In use" does not go ahead of "nothing reported". */
export function rank(places, cost, emergencyFirst = false) {
    const last = place => ['full', 'closed'].indexOf(place.report?.state) + 1;          // 0: it takes people in
    return [...places].sort((a, b) => last(a) - last(b) || (emergencyFirst ? (b.emergency === true) - (a.emergency === true) : 0) ||
                                      cost(a) - cost(b) || a.name.localeCompare(b.name));
}

/* The places whose report differs between two packs of the same area: reported for the first time, reported as
   something else, or the report was taken back. The same report with a newer time is not news.
   -> [{place (as it is now), before, after}] with 'in_use' | 'full' | 'closed' | null (nothing reported). */
export function reported(before, after) {
    const was = new Map(before.places.map(place => [place.id, place.report?.state ?? null]));
    const list = [];
    for (const place of after.places) {
        const old = was.get(place.id) ?? null, now = place.report?.state ?? null;
        if (old !== now) list.push({place, before: old, after: now});
    }
    return list;
}
