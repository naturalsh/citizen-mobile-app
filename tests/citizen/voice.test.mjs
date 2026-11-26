/* Tests of the naturalsh/Voice_Agents API client (citizen_app/voice_engine.js). */
import assert from 'node:assert/strict';
import test from 'node:test';

import {createVoiceSession, summarizeReport} from '../../citizen_app/voice_engine.js';

function fakeBridge() {
    const calls = [];
    const fetchImpl = async (url, opts) => {
        calls.push({url, method: opts.method, body: opts.body ? JSON.parse(opts.body) : null});
        if (url.endsWith('/health')) {
            return new Response(JSON.stringify({ok: true, gemini_configured: true, livekit_configured: false}), {status: 200});
        }
        if (url.endsWith('/start')) {
            return new Response(JSON.stringify({
                call_id: 'web-abc123',
                reply_text: 'You are speaking with the automated emergency assistant of 112.',
                lang: 'en',
                action: 'continue',
                handoff_reason: null,
                report: {call_id: 'web-abc123', hazard_type: null, location: {aml: {lat: 36.2, lon: 36.15}}, urgency: {suggested: null, reasons: []}},
            }), {status: 200});
        }
        if (url.endsWith('/turn')) {
            return new Response(JSON.stringify({
                call_id: 'web-abc123',
                reply_text: 'I am connecting you to a human operator now.',
                lang: 'en',
                action: 'handoff',
                handoff_reason: 'not_breathing',
                report: {
                    call_id: 'web-abc123',
                    hazard_type: 'earthquake',
                    hazard_subtype: 'collapse',
                    location: {street: 'Atatürk Cd.', area: 'Defne'},
                    urgency: {suggested: 'life_threat', reasons: ['not breathing']},
                    summary_for_operator: 'Collapse at Atatürk Cd., Defne.',
                    advice_given: ['trapped'],
                },
            }), {status: 200});
        }
        if (url.endsWith('/end')) {
            return new Response(JSON.stringify({call_id: 'web-abc123', status: 'handed_to_human'}), {status: 200});
        }
        return new Response('Not found', {status: 404});
    };
    return {calls, fetchImpl};
}

test('connects to naturalsh/Voice_Agents contract (start -> turn -> end)', async () => {
    const {calls, fetchImpl} = fakeBridge();
    const session = await createVoiceSession({lang: 'en', aml: {lat: 36.2, lon: 36.15}, baseUrl: 'http://127.0.0.1:8010/voice-api/', fetchImpl});
    assert.equal(session.mode, 'live');
    assert.equal(session.callId, 'web-abc123');

    const first = await session.start();
    assert.equal(first.action, 'continue');

    const reply = await session.turn('Collapsed building, not breathing');
    assert.equal(reply.action, 'handoff');
    assert.equal(reply.handoff_reason, 'not_breathing');

    const summary = summarizeReport(reply.report);
    assert.equal(summary.hazard, 'earthquake / collapse');
    assert.equal(summary.location, 'Atatürk Cd., Defne');
    assert.equal(summary.urgency, 'life_threat');
    assert.deepEqual(summary.reasons, ['not breathing']);

    const finalReport = await session.end('handed_off');
    assert.equal(finalReport.status, 'handed_to_human');
    assert.equal(calls.length, 4);
});

test('throws clearly when Voice_Agents server is unreachable (no local fallback model)', async () => {
    const failFetch = async () => {
        throw new Error('ECONNREFUSED');
    };
    await assert.rejects(
        () => createVoiceSession({lang: 'tr', baseUrl: 'http://127.0.0.1:8010/voice-api/', fetchImpl: failFetch}),
        /ECONNREFUSED/,
    );
});
