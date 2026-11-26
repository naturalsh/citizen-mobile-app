/* Mobile 112 Voice Agent chat + spoken readout client.
   Talks to the embedded Voice_Agents brain (/api/voice/start, /turn, /end)
   and reads every agent reply out loud using the browser's Web Speech API. */

import {firstLanguage, setLanguage, language, t, clock} from './i18n.js';
import {h} from './dom.js';

const $ = id => document.getElementById(id);
const LOCALE = {en: 'en-US', tr: 'tr-TR', el: 'el-GR', fr: 'fr-FR'};

/* Optional external voice backend override (?voice_api=https://...), else same-origin /api/voice */
const apiBase = (() => {
    const param = new URLSearchParams(location.search).get('voice_api');
    if (param) return param.replace(/\/+$/, '');
    return new URL('../api/voice', location.href).href;
})();

const state = {
    callId: null,
    lang: firstLanguage(),
    soundOn: true,
    busy: false,
    ended: false,
    speakingEl: null,
    recognition: null,
    listening: false,
};

/* ---- Web Speech API: Voice readout (TTS) ---- */

const canSpeak = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;

function pickVoice(langCode) {
    if (!canSpeak) return null;
    const target = (LOCALE[langCode] || langCode || 'en-US').toLowerCase();
    const prefix = target.slice(0, 2);
    const voices = speechSynthesis.getVoices();
    return voices.find(v => v.lang.toLowerCase() === target) ||
           voices.find(v => v.lang.toLowerCase().startsWith(prefix)) ||
           null;
}

function stopSpeaking() {
    if (canSpeak) speechSynthesis.cancel();
    if (state.speakingEl) {
        state.speakingEl.classList.remove('speaking');
        state.speakingEl = null;
    }
}

function speak(text, langCode, msgEl = null) {
    if (!canSpeak || !text) return;
    stopSpeaking();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = LOCALE[langCode] || 'en-US';
    const voice = pickVoice(langCode);
    if (voice) utter.voice = voice;
    utter.rate = 1.0;

    if (msgEl) {
        state.speakingEl = msgEl;
        msgEl.classList.add('speaking');
    }
    const clear = () => {
        if (msgEl) msgEl.classList.remove('speaking');
        if (state.speakingEl === msgEl) state.speakingEl = null;
    };
    utter.onend = clear;
    utter.onerror = clear;
    try {
        speechSynthesis.speak(utter);
    } catch {
        clear();
    }
}

/* ---- Optional Speech-to-Text (dictation) ---- */

const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;

function stopListening() {
    if (state.recognition) {
        try {
            state.recognition.stop();
        } catch {
            // already stopped
        }
    }
    state.listening = false;
    $('voice-mic').classList.remove('listening');
    $('voice-mic').setAttribute('aria-pressed', 'false');
}

function toggleListening() {
    if (!SpeechRec || state.ended || state.busy) return;
    if (state.listening) return stopListening();
    stopSpeaking();

    const rec = new SpeechRec();
    rec.lang = LOCALE[state.lang] || 'en-US';
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    state.recognition = rec;
    state.listening = true;
    $('voice-mic').classList.add('listening');
    $('voice-mic').setAttribute('aria-pressed', 'true');
    $('chat-input').placeholder = t('voiceListening');

    rec.onresult = event => {
        const transcript = event.results?.[0]?.[0]?.transcript?.trim();
        if (transcript) {
            $('chat-input').value = transcript;
            syncSendState();
            sendMessage(transcript);
        }
    };
    rec.onerror = () => stopListening();
    rec.onend = () => {
        stopListening();
        $('chat-input').placeholder = t('voicePlaceholder');
    };
    try {
        rec.start();
    } catch {
        stopListening();
    }
}

/* ---- UI helpers ---- */

function scrollBottom() {
    const box = $('chat-scroll');
    box.scrollTop = box.scrollHeight;
}

function syncSendState() {
    const hasText = $('chat-input').value.trim().length > 0;
    $('chat-send').disabled = state.busy || state.ended || !hasText;
    $('chat-input').disabled = state.ended;
    $('voice-mic').disabled = state.busy || state.ended;
}

function syncWords() {
    document.documentElement.lang = language();
    document.title = `${t('voiceTitle')} · Nature Shield`;
    $('voice-title').textContent = t('voiceTitle');
    $('voice-sub').textContent = state.soundOn ? t('voiceSubtitle') : t('voiceSoundOff');
    $('voice-back').setAttribute('aria-label', t('voiceBack'));
    $('voice-dial').setAttribute('aria-label', t('voiceDial'));
    $('voice-sound').setAttribute('aria-label', t(state.soundOn ? 'voiceSoundOn' : 'voiceSoundOff'));
    $('voice-sound').setAttribute('aria-pressed', String(state.soundOn));
    $('voice-sound').classList.toggle('active', state.soundOn);
    $('voice-sound').classList.toggle('muted', !state.soundOn);
    $('voice-sound').replaceChildren(h('span', {class: `ico ico-${state.soundOn ? 'volume' : 'mute'}`, 'aria-hidden': 'true'}));
    $('chat-input').placeholder = state.listening ? t('voiceListening') : t('voicePlaceholder');
    $('chat-send').setAttribute('aria-label', t('voiceSend'));
    $('voice-mic').setAttribute('aria-label', t('voiceMic'));

    const mobileOn = document.documentElement.classList.contains('mobile-view');
    $('view-toggle').setAttribute('aria-label', t(mobileOn ? 'desktopView' : 'mobileView'));
    $('view-toggle').setAttribute('aria-pressed', String(mobileOn));
    $('view-toggle').title = t(mobileOn ? 'desktopView' : 'mobileView');
}

function updateMeta(summary) {
    const bar = $('voice-meta');
    if (!summary) {
        bar.hidden = true;
        return;
    }
    const chips = [];
    if (summary.hazard && summary.hazard !== 'unknown') {
        chips.push(h('span', {class: 'meta-chip', text: summary.hazard.replace(/_/g, ' ')}));
    }
    if (summary.urgency && summary.urgency !== 'unknown') {
        const cls = summary.urgency === 'critical' ? 'meta-chip urgent' : summary.urgency === 'high' ? 'meta-chip high' : 'meta-chip';
        chips.push(h('span', {class: cls, text: summary.urgency}));
    }
    if (summary.area || summary.address) {
        chips.push(h('span', {class: 'meta-chip', text: [summary.address, summary.area].filter(Boolean).join(', ')}));
    }
    bar.hidden = chips.length === 0;
    bar.replaceChildren(...chips);
}

function appendMessage(role, text, msgLang = state.lang, autoSpeak = false) {
    const now = clock(Date.now());
    const foot = [h('span', {text: now})];
    const msgEl = h('div', {class: `msg ${role}`}, h('div', {class: 'bubble', text}));

    if (role === 'agent' && canSpeak) {
        const replay = h('button', {
            class: 'replay-btn',
            type: 'button',
            onclick: () => {
                if (state.speakingEl === msgEl) stopSpeaking();
                else speak(text, msgLang, msgEl);
            },
        }, h('span', {class: 'ico ico-volume', 'aria-hidden': 'true'}), h('span', {text: t('voiceReplay')}));
        foot.push(replay);
    }

    msgEl.append(h('div', {class: 'msg-foot'}, ...foot));
    $('chat-log').append(msgEl);
    scrollBottom();

    if (role === 'agent' && autoSpeak && state.soundOn) {
        speak(text, msgLang, msgEl);
    }
    return msgEl;
}

let thinkingEl = null;
function setThinking(on) {
    if (on && !thinkingEl) {
        thinkingEl = h('div', {class: 'msg agent', 'aria-label': t('voiceThinking')},
            h('div', {class: 'bubble thinking'},
                h('span', {class: 'thinking-dot'}),
                h('span', {class: 'thinking-dot'}),
                h('span', {class: 'thinking-dot'})));
        $('chat-log').append(thinkingEl);
        scrollBottom();
    } else if (!on && thinkingEl) {
        thinkingEl.remove();
        thinkingEl = null;
    }
}

function appendSystemCard({kind = '', title, body, showDial = false, showRestart = true}) {
    const actions = [];
    if (showDial) {
        actions.push(h('a', {class: 'button button-fill call-now', href: 'tel:112', text: t('call')}));
    }
    if (showRestart) {
        actions.push(h('button', {class: 'button button-outline', type: 'button', onclick: () => startSession(), text: t('voiceNewChat')}));
    }
    actions.push(h('a', {class: 'button button-outline', href: './', text: t('voiceBackToMap')}));

    const card = h('section', {class: `sys-card ${kind}`.trim()},
        h('h2', {text: title}),
        body && h('p', {text: body}),
        h('div', {class: 'sys-actions'}, ...actions));
    $('chat-log').append(card);
    scrollBottom();
}

/* ---- API calls to embedded Voice_Agents brain ---- */

async function postJson(path, payload) {
    const res = await fetch(`${apiBase}${path}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

function endCallBeacon(reason = 'hung_up') {
    if (!state.callId) return;
    const callId = state.callId;
    state.callId = null;
    try {
        fetch(`${apiBase}/end`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({call_id: callId, reason}),
            keepalive: true,
        }).catch(() => {});
    } catch {
        // ignore on unload
    }
}

async function startSession() {
    stopSpeaking();
    stopListening();
    if (state.callId) endCallBeacon('hung_up');

    state.ended = false;
    state.busy = true;
    $('chat-log').replaceChildren();
    updateMeta(null);
    syncSendState();
    setThinking(true);

    try {
        const data = await postJson('/start', {lang: state.lang});
        setThinking(false);
        state.callId = data.call_id;
        state.lang = data.lang || state.lang;
        if (['en', 'tr', 'el'].includes(state.lang)) {
            setLanguage(state.lang);
            syncWords();
        }
        updateMeta(data.summary);
        appendMessage('agent', data.reply_text, state.lang, true);

        if (data.action === 'handoff') {
            state.ended = true;
            state.callId = null;
            appendSystemCard({kind: 'handoff', title: t('voiceHandoffTitle'), body: t('voiceHandoffBody'), showDial: true});
        }
    } catch {
        setThinking(false);
        state.ended = true;
        appendSystemCard({kind: 'handoff', title: t('voiceOfflineTitle'), body: t('voiceOfflineBody'), showDial: true});
    } finally {
        state.busy = false;
        syncSendState();
    }
}

async function sendMessage(rawText) {
    const text = rawText.trim();
    if (!text || state.busy || state.ended || !state.callId) return;

    stopSpeaking();
    $('chat-input').value = '';
    $('chat-input').style.height = '';
    state.busy = true;
    syncSendState();

    appendMessage('user', text, state.lang, false);
    setThinking(true);

    try {
        const data = await postJson('/turn', {call_id: state.callId, text, lang: state.lang});
        setThinking(false);
        if (data.lang && data.lang !== state.lang) {
            state.lang = data.lang;
            if (['en', 'tr', 'el'].includes(state.lang)) {
                setLanguage(state.lang);
                syncWords();
            }
        }
        updateMeta(data.summary);
        appendMessage('agent', data.reply_text, state.lang, true);

        if (data.action === 'handoff') {
            state.ended = true;
            state.callId = null;
            appendSystemCard({kind: 'handoff', title: t('voiceHandoffTitle'), body: t('voiceHandoffBody'), showDial: true});
        } else if (data.action === 'end') {
            state.ended = true;
            state.callId = null;
            appendSystemCard({title: t('voiceEndedTitle'), body: '', showDial: false});
        }
    } catch {
        setThinking(false);
        appendMessage('agent', t('voiceError'), state.lang, false);
    } finally {
        state.busy = false;
        syncSendState();
        if (!state.ended) $('chat-input').focus();
    }
}

/* ---- View mode & events ---- */

{
    const param = new URLSearchParams(location.search).get('view');
    let stored = null;
    try {
        stored = localStorage.getItem('viewMode');
    } catch {
        // private window
    }
    if (param === 'mobile' || (param !== 'desktop' && stored === 'mobile')) {
        document.documentElement.classList.add('mobile-view');
    }
}

$('view-toggle').addEventListener('click', () => {
    const on = !document.documentElement.classList.contains('mobile-view');
    document.documentElement.classList.toggle('mobile-view', on);
    try {
        localStorage.setItem('viewMode', on ? 'mobile' : 'desktop');
    } catch {
        // ignore
    }
    syncWords();
});

$('voice-sound').addEventListener('click', () => {
    state.soundOn = !state.soundOn;
    if (!state.soundOn) stopSpeaking();
    syncWords();
});

if (SpeechRec) {
    $('voice-mic').hidden = false;
    $('voice-mic').addEventListener('click', toggleListening);
}

$('chat-input').addEventListener('input', () => syncSendState());
$('chat-input').addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage($('chat-input').value);
    }
});

$('composer').addEventListener('submit', event => {
    event.preventDefault();
    sendMessage($('chat-input').value);
});

$('voice-back').addEventListener('click', () => {
    stopSpeaking();
    endCallBeacon('hung_up');
});

window.addEventListener('pagehide', () => {
    stopSpeaking();
    endCallBeacon('hung_up');
});

if (canSpeak) {
    speechSynthesis.getVoices();
    speechSynthesis.addEventListener?.('voiceschanged', () => speechSynthesis.getVoices());
}

setLanguage(state.lang);
syncWords();
startSession();
