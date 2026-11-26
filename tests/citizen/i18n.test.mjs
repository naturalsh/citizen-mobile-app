/* Tests of the words the citizen reads (citizen_app/i18n.js): every language says everything English says, with the
   same blanks, and every text the code asks for exists. A missing text would show its bare key, such as
   "verdict.partly", to somebody who needs an answer.
   Run:  node --test tests/citizen/i18n.test.mjs   (pytest runs it too: tests/test_citizen_app.py)
*/
import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';
import test from 'node:test';

import {LANGUAGES, clock, keys, metres, setLanguage, t} from '../../citizen_app/i18n.js';
import {KINDS} from '../../citizen_app/map.js';

const APP = new URL('../../citizen_app/', import.meta.url);
const CODE = Object.fromEntries(readdirSync(APP).filter(name => name.endsWith('.js')).map(name => [name, readFileSync(new URL(name, APP), 'utf8')]));
const OTHERS = Object.keys(LANGUAGES).filter(language => language !== 'en');

const written = (language, key) => (setLanguage(language), t(key));           // with no values given, the blanks stay as written
const blanks = text => [...text.matchAll(/\{(\w+)\}/g)].map(found => found[1]).sort();
const named = (file, call) => [...CODE[file].matchAll(call)].map(found => found[1]);

/* A key that is put together while the app runs, t(`group.${...}`): everything that can come after the dot. */
const GROUPS = ['checked', 'unchecked', 'blocked', 'no_data'];                 // route.js: group()
const STATES = ['in_use', 'full', 'closed'];                                   // contracts.py: PlaceState (test_citizen_app.py holds them together)
const ENDINGS = {
    group: GROUPS,
    groupMore: GROUPS,
    verdict: ['checked', 'partly', 'blocked'],                                 // route.js: route(), worst
    step: ['start', 'straight', 'left', 'right'],                              // route.js: steps(), turn
    kind: KINDS,                                                               // the kinds of place the app has a sign for
    facility: ['water', 'medical', 'power', 'shelter', 'accessible'],          // contracts.py: PlaceFacility
    seen: ['drone', 'field_report'],                                           // contracts.py: seen_by
    report: STATES,                                                            // what the operators reported about a place
    reportShort: STATES,
    unnamed: ['street', 'footway', 'steps', 'track'],                          // i18n.js: streetName()
};
/* A key that reaches t() under another name, t(name): the texts given under that name. */
const HANDED = {
    'sheet.js': {name: named('sheet.js', /\btab\('(\w+)'\)/g), key: named('app.js', /\bfail\('(\w+)'\)/g)},
    'app.js': {'message.key': named('app.js', /\bsay\('(\w+)'/g)},
};

/* Every text the code asks for: [key, where]. A call written in a way this test cannot read fails here, so that a
   new way of asking is never left unchecked. */
function asked() {
    const list = [];
    for (const [file, code] of Object.entries(CODE)) {
        for (const found of code.matchAll(/(?<![\w.$])(?<!function )t\(([^,)]*)/g)) {
            const first = found[1].trim(), where = `${file}: t(${first}`;
            const plain = /^'([\w.]+)'$/.exec(first), built = /^`(\w+)\.\$\{/.exec(first), either = /\? '([\w.]+)' : '([\w.]+)'$/.exec(first);
            if (plain) list.push([plain[1], where]);
            else if (built) {
                assert.ok(ENDINGS[built[1]], `${where}: ENDINGS in this test does not say what can follow "${built[1]}."`);
                list.push(...ENDINGS[built[1]].map(ending => [`${built[1]}.${ending}`, where]));
            } else if (either) list.push([either[1], where], [either[2], where]);
            else {
                const handed = HANDED[file]?.[first];
                assert.ok(handed?.length, `${where}: this test cannot tell which text that asks for (see HANDED)`);
                list.push(...handed.map(key => [key, where]));
            }
        }
    }
    return list;
}

test('every language says everything English says, and nothing more', () => {
    assert.ok(keys('en').length > 50);
    for (const language of OTHERS) assert.deepEqual(keys(language), keys('en'), language);
});

test('no text is empty, and a translation has the same blanks as the English text', () => {
    for (const key of keys('en')) {
        const english = written('en', key);
        assert.ok(english.trim() && english !== key, key);
        for (const language of OTHERS) {
            const text = written(language, key);
            assert.ok(text.trim(), `${language}: ${key}`);
            assert.deepEqual(blanks(text), blanks(english), `${language}: ${key}`);
        }
    }
});

test('every text the code asks for exists', () => {
    const english = new Set(keys('en')), wanted = asked();
    assert.ok(wanted.length > 80, 'the code was not read');
    for (const [key, where] of wanted) assert.ok(english.has(key), `${where} asks for "${key}", which i18n.js does not have`);
});

test('a blank is filled in, and a text that is missing shows its key', () => {
    setLanguage('en');
    assert.equal(t('fromGps', {m: '10 m'}).includes('{'), false);
    assert.ok(t('fromGps', {m: '10 m'}).includes('10 m'));
    assert.equal(t('no.such.text'), 'no.such.text');
    assert.equal(setLanguage('xx'), 'en');                                     // a language the app does not speak: English
});

test('a distance is rounded the way people say it', () => {
    setLanguage('en');
    assert.deepEqual([2, 37, 644, 994, 1234, 1115600].map(metres), ['5 m', '35 m', '640 m', '990 m', '1.2 km', '1,116 km']);
    setLanguage('tr');
    assert.equal(metres(1234), '1,2 km');
    setLanguage('el');
    assert.equal(metres(1234), '1,2 km');
});

test('a time of day is written on the 24-hour clock in every language', () => {
    const two = n => String(n).padStart(2, '0'), plain = time => `${two(time.getHours())}:${two(time.getMinutes())}`;
    const night = new Date(), noon = new Date();                               // today, in this computer's own time:
    night.setHours(0, 58, 0, 0);                                               // 00:58 (where that day has such an hour)
    noon.setHours(12, 5, 0, 0);                                                // and 12:05
    for (const language of Object.keys(LANGUAGES)) {
        setLanguage(language);
        assert.equal(clock(night), plain(night), language);                    // not "12:58 AM", not "12:58 π.μ.", not "24:58"
        assert.equal(clock(noon), plain(noon), language);
        assert.equal(clock(night.toISOString()), plain(night), language);      // the pack gives a time as text
        assert.match(clock(new Date(2023, 1, 9, 14, 5)), /^\D*9\D+14:05$/, language);          // another day: the day and the month with it
    }
});
