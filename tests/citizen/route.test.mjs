/* Tests of the route the PHONE finds (citizen_app/route.js), on a tiny town where every answer can be worked out
   by hand. Run:  node --test tests/citizen/route.test.mjs   (pytest runs it too: tests/test_citizen_app.py)

        A ---------- B ---------- C          each side is 100 m; A is 100 m north of D
        |            |            |
        D ---------- E ---------- F
*/
import assert from 'node:assert/strict';
import test from 'node:test';

import {FACTOR, buildNetwork, changes, factor, group, nearest, noticed, rank, reach, reported, route, steps,
        takesPeople} from '../../citizen_app/route.js';

const LAT0 = 36.2, LON0 = 36.15, MX = 89935.5, MY = 110962.7;         // metres per degree at 36.2 N, measured on the WGS84 ellipsoid with pyproj
const at = (x, y) => [LON0 + x / MX, LAT0 + y / MY];                  // x metres east, y metres north of the middle
const CORNER = {A: [0, 100], B: [100, 100], C: [200, 100], D: [0, 0], E: [100, 0], F: [200, 0], X: [1000, 0], Y: [1100, 0]};
const SEEN = '2023-02-09T16:00:00Z', CHECKED = {confirmed: true, checked_at: '2026-11-12T10:00:00Z', observed_at: SEEN};
const OPEN = {status: 'open', ...CHECKED}, UNCHECKED = {status: 'unchecked', observed_at: SEEN};
const BLOCKED = {status: 'blocked', observed_at: SEEN}, CLOSED = {status: 'blocked', ...CHECKED};

let ways = 0;
function street(ends, told = {}, {name = null, via = [], kind = 'residential'} = {}) {
    const [from, to] = ends;
    return {way: ++ways, ends: [from.charCodeAt(0), to.charCodeAt(0)], kind, name, status: 'no_data', confirmed: false, simulated: false,
            line: [CORNER[from], ...via, CORNER[to]].map(point => at(...point)), ...told};
}
const pack = streets => ({format: 1, area: {id: 'town', name: {en: 'Town'}, hazard: 'earthquake', bbox: [LAT0 - 0.02, LON0 - 0.02, LAT0 + 0.02, LON0 + 0.02]},
                          streets, places: []});
const grid = (told = {}) => ['AB', 'BC', 'DE', 'EF', 'AD', 'BE', 'CF'].map(ends => street(ends, told[ends] || {}));

function walk(streets, from, to) {
    const network = buildNetwork(pack(streets));
    const start = nearest(network, at(...from)), end = nearest(network, at(...to));
    return route(network, reach(network, start), end);
}
const about = (value, expected, slack = 0.05) => assert.ok(Math.abs(value - expected) <= slack, `${value} is not about ${expected}`);

test('with nothing known, the shortest way', () => {
    const found = walk(grid(), CORNER.A, CORNER.C);
    about(found.metres, 200);
    about(found.seconds, 200);                              // 1 metre a second
    about(found.by.no_data, 200);
    about(found.cost, 200 * FACTOR.no_data);
    assert.equal(found.worst, 'partly');                    // nobody checked these streets: never "all clear"
    assert.deepEqual(found.parts.map(part => part.street.ends), [[65, 66], [66, 67]]);
});

test('a blocked street is walked around', () => {
    const found = walk(grid({BC: BLOCKED}), CORNER.A, CORNER.C);
    about(found.metres, 400);                               // round the block: 4 sides instead of 2
    about(found.by.blocked, 0);
    assert.equal(found.worst, 'partly');
});

test('... but it is never forbidden: the only way out still gets an answer, with a warning', () => {
    const found = walk([street('AB'), street('BC', BLOCKED)], CORNER.A, CORNER.C);
    about(found.metres, 200);
    about(found.by.blocked, 100);
    assert.equal(found.worst, 'blocked');
});

test('how far round is worth it: 8 times the blocked metres, 40 once a person confirmed the blockage', () => {
    const long = {via: [[100, 300], [200, 300]]};           // B to C the long way: 200 + 100 + 200 = 500 m
    const unconfirmed = walk([street('AB'), street('BC', BLOCKED), street('BC', {}, long)], CORNER.A, CORNER.C);
    about(unconfirmed.metres, 200);                         // 100 m blocked costs 800, the 500 m round cost 900: straight on
    assert.equal(unconfirmed.worst, 'blocked');
    const confirmed = walk([street('AB'), street('BC', CLOSED), street('BC', {}, long)], CORNER.A, CORNER.C);
    about(confirmed.metres, 600);                           // now the blocked way costs 4000: go round
    about(confirmed.by.blocked, 0);
});

test('streets a person checked are preferred, within reason', () => {
    const checkedWay = length => street('AC', OPEN, {via: [[0, 100 - length], [200, 100 - length]]});   // 200 m + 2 x length
    const near = walk([street('AB'), street('BC'), checkedWay(30)], CORNER.A, CORNER.C);
    about(near.metres, 260);                                // 260 m checked (cost 260) beat 200 m unknown (cost 360)
    about(near.by.checked, 260);
    assert.equal(near.worst, 'checked');
    const far = walk([street('AB'), street('BC'), checkedWay(100)], CORNER.A, CORNER.C);
    about(far.metres, 200);                                 // 400 m checked (cost 400) do not
});

test('seen clear by the drone but not checked: between a checked street and one we know nothing about', () => {
    const round = (told, length) => street('AC', told, {via: [[0, 100 - length], [200, 100 - length]]});   // 200 m + 2 x length
    const straight = told => [street('AB', told), street('BC', told)];                                     // 200 m
    const metres = streets => walk(streets, CORNER.A, CORNER.C).metres;
    about(metres([...straight(UNCHECKED), round(OPEN, 20)]), 240);        // 240 m checked (cost 240) beat 200 m unchecked (260)
    about(metres([...straight(UNCHECKED), round(OPEN, 40)]), 200);        // 280 m checked (280) do not
    about(metres([...straight({}), round(UNCHECKED, 20)]), 240);          // 240 m unchecked (312) beat 200 m unknown (360)
    about(metres([...straight({}), round(UNCHECKED, 50)]), 200);          // 300 m unchecked (390) do not
});

test('the walking rule in numbers', () => {
    // what a metre of each kind of street costs. A change here is a decision about where people are sent, not a fix.
    assert.deepEqual({...FACTOR}, {checked: 1, unchecked: 1.3, no_data: 1.8, blocked: 8, blocked_confirmed: 40});
    assert.throws(() => { FACTOR.blocked = 1; }, TypeError);              // and nothing changes it while the app runs
});

test('the phone checks the safety rule again', () => {
    assert.equal(group({status: 'open', confirmed: true}), 'checked');
    assert.equal(group({status: 'narrow', confirmed: true}), 'checked');
    assert.equal(group({status: 'open', confirmed: false}), 'unchecked');      // "open" that nobody confirmed
    assert.equal(group({status: 'open'}), 'unchecked');
    assert.equal(group({status: 'flooded', confirmed: true}), 'blocked');      // a word this app does not know
    assert.equal(factor({status: 'blocked', confirmed: false}), FACTOR.blocked);
    assert.equal(factor({status: 'blocked', confirmed: true}), FACTOR.blocked_confirmed);
    assert.equal(factor(UNCHECKED), FACTOR.unchecked);
});

test('people and places beside a street are put on it', () => {
    const network = buildNetwork(pack(grid()));
    const start = nearest(network, at(40, 110)), end = nearest(network, at(205, 80));
    about(start.off, 10);
    about(start.along, 40);
    assert.deepEqual(start.piece.street.ends, [65, 66]);
    const found = route(network, reach(network, start), end);
    about(found.metres, 10 + 60 + 100 + 20 + 5);            // to the street, to B, to C, 20 m down towards F, to the place
    assert.deepEqual(found.off, {start: start.off, end: end.off});
    const [lon, lat] = found.parts[0].line[0];              // the line starts where the person meets the street
    about(lon, at(40, 100)[0], 1e-7);
    about(lat, at(40, 100)[1], 1e-7);
    assert.equal(found.parts.length, 3);
});

test('start and place on the same street', () => {
    const found = walk(grid(), [20, 100], [70, 100]);
    about(found.metres, 50);
    assert.equal(found.parts.length, 1);
    const back = walk(grid(), [70, 100], [20, 100]);
    about(back.metres, 50);
    about(back.parts[0].line[0][0], at(70, 100)[0], 1e-7);  // walked from 70 back to 20
});

test('on the same street, round the block when that is cheaper', () => {
    const found = walk(grid({AB: CLOSED}), [10, 100], [90, 100]);
    about(found.metres, 10 + 300 + 10);                     // 80 m confirmed blocked cost 3200; round costs 400 + 540 + 400
    about(found.by.blocked, 20);
    assert.equal(found.worst, 'blocked');                   // the person stands ON a blocked street: said, not hidden
});

test('a stub that leads nowhere is never used', () => {
    const network = buildNetwork(pack([...grid(), street('XY')]));
    assert.deepEqual(network.pieces.map(piece => piece.main), [true, true, true, true, true, true, true, false]);
    const beside = nearest(network, at(300, 0));            // nearer to the stub's end? no: F is 100 m away, the stub 700
    assert.deepEqual(beside.piece.street.ends, [69, 70]);
    about(beside.off, 100);
    assert.equal(nearest(network, at(1050, 5)), null);      // on the stub: 850 m from the town, we do not guess
});

test('left and right', () => {
    const named = [street('AB', {}, {name: 'Top'}), street('BC', {}, {name: 'Top'}), street('DE', {}, {name: 'Low'}),
                   street('EF', {}, {name: 'Low'}), street('BE', {}, {name: 'Middle'}), street('AD'), street('CF', {}, {kind: 'steps'})];
    const list = found => steps(found).map(step => [step.turn, step.name, Math.round(step.metres)]);
    assert.deepEqual(list(walk(named, CORNER.A, [100, 20])), [['start', 'Top', 100], ['right', 'Middle', 80]]);      // east, then south
    assert.deepEqual(list(walk(named, CORNER.D, [100, 80])), [['start', 'Low', 100], ['left', 'Middle', 80]]);       // east, then north
    assert.deepEqual(list(walk(named, CORNER.A, CORNER.C)), [['start', 'Top', 200]]);                                // one street, one step
    assert.deepEqual(list(walk(named, [0, 50], [200, 50])).length, 3);
});

test('a slight bend is "straight on", a corner is a turn', () => {
    const turn = degrees => {                               // east along Top to B, then 80 m along a street that leaves B at this angle
        const angle = degrees * Math.PI / 180, end = [100 + 80 * Math.cos(angle), 100 + 80 * Math.sin(angle)];
        return steps(walk([street('AB', {}, {name: 'Top'}), street('BC', {}, {name: 'Side', via: [end]})], CORNER.A, end))[1].turn;
    };
    assert.deepEqual([20, -20, 45, -45, 120].map(turn), ['straight', 'straight', 'left', 'right', 'left']);
});

test('ways without a name are one step only while they are the same kind of way', () => {
    const list = streets => steps(walk(streets, CORNER.A, CORNER.C)).map(step => [step.kind, Math.round(step.metres)]);
    assert.deepEqual(list([street('AB', {}, {kind: 'footway'}), street('BC', {}, {kind: 'footway'})]), [['footway', 200]]);
    assert.deepEqual(list([street('AB', {}, {kind: 'footway'}), street('BC', {}, {kind: 'steps'})]), [['footway', 100], ['steps', 100]]);
});

test('standing exactly on a corner adds no empty step', () => {
    const streets = [street('AB', {}, {name: 'Top'}), street('AD', {}, {name: 'West'}), street('DE', {}, {name: 'Low'})];
    const found = walk(streets, CORNER.A, CORNER.D);        // A is an end of Top and of West, D an end of West and of Low
    assert.deepEqual(found.parts.map(part => [part.street.name, Math.round(part.metres)]), [['West', 100]]);
    assert.deepEqual(steps(found).map(step => [step.turn, step.name]), [['start', 'West']]);
});

test('a step says the worst of its street', () => {
    const streets = [street('AB', OPEN, {name: 'Top'}), street('BC', UNCHECKED, {name: 'Top'})];
    const [step] = steps(walk(streets, CORNER.A, CORNER.C));
    assert.deepEqual([step.name, Math.round(step.metres), step.worst], ['Top', 200, 'unchecked']);
});

test('loops and twin streets do no harm', () => {
    const loop = {...street('AB', {}, {via: [[-50, 150]]}), ends: [65, 65]};                          // leaves A and comes back to A
    const found = walk([...grid(), loop, street('BC', {}, {via: [[150, 180]]})], CORNER.A, CORNER.C);
    about(found.metres, 200);
    const onLoop = walk([...grid(), loop], [-50, 150], CORNER.B);                                     // standing on the loop
    assert.ok(onLoop.metres > 100 && onLoop.metres < 300);
});

test('places are ranked by what the way costs, not by how far they are', () => {
    const network = buildNetwork(pack([street('AB', BLOCKED), street('BC', OPEN)]));
    const reached = reach(network, nearest(network, at(...CORNER.B)));
    const near = route(network, reached, nearest(network, at(40, 100)));     // 60 m away, over a blocked street: costs 480
    const far = route(network, reached, nearest(network, at(...CORNER.C)));  // 100 m away on a checked street: costs 100
    about(near.metres, 60);
    about(far.metres, 100);
    about(near.cost, 60 * FACTOR.blocked);
    about(far.cost, 100 * FACTOR.checked);
    assert.deepEqual([near, far].sort((a, b) => a.cost - b.cost), [far, near]);
});

test('metres off the streets cost as much as a street we know nothing about', () => {
    const network = buildNetwork(pack([street('AB', OPEN), street('BC', OPEN)]));
    const reached = reach(network, nearest(network, at(...CORNER.A)));
    const beside = route(network, reached, nearest(network, at(60, 200)));   // 60 m along the street, then 100 m over open ground
    const along = route(network, reached, nearest(network, at(...CORNER.C)));   // 200 m, all of it on the checked street
    about(beside.metres, 160);
    about(beside.cost, 60 * FACTOR.checked + 100 * FACTOR.no_data);          // 240: fewer metres, and still ranked second
    about(along.cost, 200);
    assert.deepEqual([beside, along].sort((a, b) => a.cost - b.cost), [along, beside]);
});

test('what changed between two packs', () => {
    const before = pack(grid({AB: UNCHECKED, BC: UNCHECKED, DE: OPEN})), after = structuredClone(before);
    Object.assign(after.streets[0], OPEN);
    Object.assign(after.streets[1], BLOCKED);
    after.streets[2].status = 'narrow';                     // DE: still passable, still confirmed. Nothing a citizen acts on
    after.streets.push(street('XY', BLOCKED));              // a street the old pack did not have is not a change of a street
    assert.deepEqual(changes(before, after).map(change => [change.street.ends, change.before, change.after]),
                     [[[65, 66], 'unchecked', 'checked'], [[66, 67], 'unchecked', 'blocked']]);
    assert.deepEqual(changes(before, before), []);
});

test('a notice that came, changed or was taken back is told, and the same notice is not', () => {
    const notice = {issued_by: 'Town hall', issued_at: '2026-11-13T10:00:00Z', text: {en: 'Water at the stadium.'}};
    const none = pack([]), one = {...none, notice};
    assert.equal(noticed(none, none), null);
    assert.equal(noticed(none, one), 'new');
    assert.equal(noticed(one, {...none, notice: structuredClone(notice)}), null);                  // the same words again
    assert.equal(noticed(one, {...none, notice: {...notice, issued_at: '2026-11-13T11:00:00Z'}}), 'new');
    assert.equal(noticed(one, {...none, notice: {...notice, text: {en: 'The stadium is full.'}}}), 'new');
    assert.equal(noticed(one, none), 'gone');
});

/* A place as the pack gives it: `state` is what the operators reported about it, null when they reported nothing. */
const place = (id, state = null, more = {}) => ({id, name: id, ...(state ? {report: {state, reported_at: SEEN}} : {}), ...more});
const ids = list => list.map(one => one.id);

test('only a place reported full or closed takes nobody in', () => {
    assert.equal(takesPeople(place('park')), true);                          // nothing reported: nothing against it
    assert.equal(takesPeople(place('park', 'in_use')), true);
    assert.equal(takesPeople(place('park', 'full')), false);
    assert.equal(takesPeople(place('park', 'closed')), false);
});

test('a place reported full or closed goes to the end of the list, and none is left out', () => {
    const metres = {park: 100, school: 200, field: 250, hall: 300, yard: Infinity};        // yard: no way to it is known
    const places = [place('park', 'closed'), place('school', 'full'), place('hall', 'in_use'), place('yard'), place('field')];
    const listed = rank(places, one => metres[one.id]);
    assert.deepEqual(ids(listed), ['field', 'hall', 'yard', 'school', 'park']);            // the nearest two come last
    assert.deepEqual(ids(places), ['park', 'school', 'hall', 'yard', 'field']);            // the pack's own list is left alone
    assert.deepEqual(ids(rank(places.slice(2), one => metres[one.id])), ['field', 'hall', 'yard']);      // without a report against any: by the way alone,
    assert.deepEqual(ids(rank([place('b'), place('a', 'in_use'), place('c')], () => Infinity)), ['a', 'b', 'c']);   // and without a position by name
    assert.deepEqual(ids(rank([place('b', 'closed'), place('a', 'closed'), place('c', 'full')], () => 5)), ['c', 'a', 'b']);
});

test('an emergency department comes first only while it takes people in', () => {
    const metres = {far: 900, shut: 500, clinic: 100, crowded: 50};
    const places = [place('shut', 'closed', {emergency: true}), place('far', null, {emergency: true}),
                    place('crowded', 'full', {emergency: false}), place('clinic', 'in_use', {emergency: false})];
    assert.deepEqual(ids(rank(places, one => metres[one.id], true)), ['far', 'clinic', 'crowded', 'shut']);
    assert.deepEqual(ids(rank(places, one => metres[one.id])), ['clinic', 'far', 'crowded', 'shut']);     // assembly points: nearest first
});

test('what was reported about the places between two packs', () => {
    const before = {...pack([]), places: [place('p1'), place('p2', 'full'), place('p3', 'closed'), place('p4', 'in_use'), place('p6', 'full')]};
    const again = {state: 'full', reported_at: '2026-11-14T09:00:00Z'};      // the same state, reported once more
    const after = {...pack([]), places: [place('p1', 'closed'), {...place('p2'), report: again}, place('p3'), place('p4', 'full'),
                                         place('p5', 'in_use'), place('p7')]};              // p5 and p7 are new, p6 is gone
    assert.deepEqual(reported(before, after).map(change => [change.place.id, change.before, change.after]),
                     [['p1', null, 'closed'], ['p3', 'closed', null], ['p4', 'in_use', 'full'], ['p5', null, 'in_use']]);
    assert.equal(reported(before, after)[0].place, after.places[0]);         // the place as it is now
    assert.deepEqual(reported(before, before), []);
    assert.deepEqual(reported(after, after), []);
});
