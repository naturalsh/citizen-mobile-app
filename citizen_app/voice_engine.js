/* Client for the real naturalsh/Voice_Agents backend (brain/contract.py).
   No local/mock answering model lives here: every call goes directly to
   Voice_Agents (start_call / turn / end_call) and optionally LiveKit rooms.

   Server URL resolution:
   1. ?voice_api=https://... query parameter (useful when opening from GitHub Pages)
   2. localStorage 'voiceApiBase' if saved previously
   3. Same-origin ../voice-api/ (proxied automatically by server.mjs to voice_bridge.py) */

export function resolveVoiceApiBase() {
    if (typeof location === 'undefined') return 'http://127.0.0.1:8010/voice-api/';
    const param = new URLSearchParams(location.search).get('voice_api');
    if (param) {
        const clean = param.replace(/\/+$/, '');
        const base = clean.endsWith('/voice-api') ? `${clean}/` : `${clean}/voice-api/`;
        try {
            localStorage.setItem('voiceApiBase', base);
        } catch {
            // private window
        }
        return base;
    }
    try {
        const saved = localStorage.getItem('voiceApiBase');
        if (saved) return saved;
    } catch {
        // private window
    }
    return new URL('../voice-api/', location.href).href;
}

/* Extracts human-readable fields from the exact naturalsh/Voice_Agents brain/report.py schema. */
export function summarizeReport(report) {
    if (!report || typeof report !== 'object') return null;
    const loc = report.location || {};
    const locParts = [loc.spoken_address, loc.street, loc.cross_street, loc.area, loc.landmark].filter(Boolean);
    const locationText = locParts.length
        ? locParts.join(', ')
        : loc.aml && loc.aml.lat != null && loc.aml.lon != null
            ? `${Number(loc.aml.lat).toFixed(5)}, ${Number(loc.aml.lon).toFixed(5)}`
            : null;
    const hazard = [report.hazard_type, report.hazard_subtype].filter(Boolean).join(' / ') || null;
    const urgencyObj = report.urgency && typeof report.urgency === 'object' ? report.urgency : null;
    const urgency = urgencyObj?.suggested || null;
    const reasons = Array.isArray(urgencyObj?.reasons) ? urgencyObj.reasons : [];
    const adviceTopics = Array.isArray(report.advice_given) ? report.advice_given : [];
    const summary = report.summary_for_operator || report.summary_en || report.situation || null;
    if (!hazard && !locationText && !urgency && !summary && !adviceTopics.length) return null;
    return {hazard, location: locationText, urgency, reasons, adviceTopics, summary};
}

/* Connects to the real Voice_Agents bridge (scripts/voice_bridge.py -> brain/contract.py).
   Throws if the server is unreachable or returns an error. */
export async function createVoiceSession({lang = 'en', aml = null, baseUrl = resolveVoiceApiBase(), fetchImpl = globalThis.fetch} = {}) {
    const endpoint = path => new URL(path, baseUrl).href;

    const healthRes = await fetchImpl(endpoint('health'), {method: 'GET', headers: {Accept: 'application/json'}});
    if (!healthRes.ok) throw new Error(`Voice agent server error (${healthRes.status})`);
    const health = await healthRes.json();

    const startRes = await fetchImpl(endpoint('start'), {
        method: 'POST',
        headers: {'Content-Type': 'application/json', Accept: 'application/json'},
        body: JSON.stringify({lang, aml, channel: 'voice'}),
    });
    if (!startRes.ok) {
        const detail = await startRes.text().catch(() => '');
        throw new Error(`Voice agent start failed (${startRes.status}): ${detail}`);
    }
    const first = await startRes.json();
    const callId = first.call_id;

    return {
        mode: 'live',
        callId,
        health,
        async start() {
            return first;
        },
        async turn(text) {
            const res = await fetchImpl(endpoint('turn'), {
                method: 'POST',
                headers: {'Content-Type': 'application/json', Accept: 'application/json'},
                body: JSON.stringify({call_id: callId, text, lang}),
            });
            if (!res.ok) {
                const detail = await res.text().catch(() => '');
                throw new Error(`Voice agent turn failed (${res.status}): ${detail}`);
            }
            return await res.json();
        },
        async end(reason = 'hung_up') {
            const res = await fetchImpl(endpoint('end'), {
                method: 'POST',
                headers: {'Content-Type': 'application/json', Accept: 'application/json'},
                body: JSON.stringify({call_id: callId, reason}),
            });
            if (!res.ok) return {call_id: callId, status: reason};
            return await res.json();
        },
        async livekitLink() {
            const res = await fetchImpl(endpoint('livekit'), {
                method: 'POST',
                headers: {'Content-Type': 'application/json', Accept: 'application/json'},
                body: JSON.stringify({lang}),
            });
            if (!res.ok) return null;
            return await res.json();
        },
    };
}
