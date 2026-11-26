/* Tests of the on-device 112 Voice Agent triage engine (citizen_app/voice_engine.js). */
import assert from 'node:assert/strict';
import test from 'node:test';

import {ADVICE, PHRASES, createLocalSession} from '../../citizen_app/voice_engine.js';

test('starts with the official automated 112 greeting in en, tr, and el', async () => {
    for (const lang of ['en', 'tr', 'el']) {
        const s = createLocalSession({lang});
        const first = await s.start();
        assert.equal(first.action, 'continue');
        assert.equal(first.reply_text, PHRASES.greeting[lang]);
    }
});

test('hands off immediately when caller reports someone is not breathing or asks for a human', async () => {
    const s1 = createLocalSession({lang: 'en'});
    await s1.start();
    const r1 = await s1.turn('My father is not breathing!');
    assert.equal(r1.action, 'handoff');
    assert.equal(r1.handoff_reason, 'life_threat_not_breathing');
    assert.equal(r1.report.urgency, 'critical');

    const s2 = createLocalSession({lang: 'tr'});
    await s2.start();
    const r2 = await s2.turn('Operatör ile görüşmek istiyorum');
    assert.equal(r2.action, 'handoff');
    assert.equal(r2.handoff_reason, 'caller_requested_human');
});

test('gives official verbatim trapped advice and completes report on confirmation', async () => {
    const s = createLocalSession({lang: 'en', aml: {lat: 36.201, lon: 36.152}});
    await s.start();
    const r1 = await s.turn('I am trapped under rubble');
    assert.equal(r1.action, 'continue');
    assert.ok(r1.reply_text.includes(ADVICE.trapped.en));
    assert.equal(r1.report.hazard, 'trapped');
    assert.equal(r1.report.urgency, 'critical');

    const r2 = await s.turn('Two people, one injured leg');
    assert.equal(r2.action, 'continue');
    assert.ok(r2.reply_text.includes(PHRASES.confirm.en));

    const r3 = await s.turn('Yes');
    assert.equal(r3.action, 'end');
    assert.equal(r3.reply_text, PHRASES.passedOn.en);
    assert.equal(r3.report.status, 'completed');
});
