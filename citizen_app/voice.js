/* Mobile 112 Voice Agent UI: connects directly to the LiveKit room of the running Voice_Agents backend. */

import {t} from './i18n.js';
import {h} from './dom.js';

let activeRoom = null;
let timerId = null;

function formatElapsed(sec) {
    const m = String(Math.floor(sec / 60)).padStart(2, '0');
    const s = String(sec % 60).padStart(2, '0');
    return `${m}:${s}`;
}

export async function openVoiceAgent(container) {
    if (!container) return;
    if (activeRoom) {
        try { await activeRoom.disconnect(); } catch {}
        activeRoom = null;
    }
    clearInterval(timerId);

    let muted = false;
    let startedAt = null;
    let statusEl, timerEl, orbEl, muteBtn, logEl, audioEl;

    const close = async () => {
        clearInterval(timerId);
        if (activeRoom) {
            try { await activeRoom.disconnect(); } catch {}
            activeRoom = null;
        }
        audioEl?.remove();
        container.hidden = true;
        container.replaceChildren();
    };

    const setStatus = (text, mode = '') => {
        if (statusEl) statusEl.textContent = text;
        if (orbEl) {
            orbEl.className = `voice-orb ${mode}`.trim();
        }
    };

    const appendLine = (who, text) => {
        if (!logEl || !text) return;
        const item = h('p', {class: `voice-line ${who}`}, h('strong', {text: who === 'agent' ? '112: ' : 'You: '}), text);
        logEl.append(item);
        logEl.scrollTop = logEl.scrollHeight;
    };

    muteBtn = h('button', {
        class: 'voice-btn voice-mute',
        type: 'button',
        onclick: async () => {
            if (!activeRoom?.localParticipant) return;
            muted = !muted;
            await activeRoom.localParticipant.setMicrophoneEnabled(!muted);
            muteBtn.textContent = t(muted ? 'voiceUnmute' : 'voiceMute');
            muteBtn.classList.toggle('is-muted', muted);
        },
    }, t('voiceMute'));

    const endBtn = h('button', {
        class: 'voice-btn voice-end',
        type: 'button',
        onclick: close,
    }, t('voiceEnd'));

    statusEl = h('p', {class: 'voice-status', text: t('voiceConnecting')});
    timerEl = h('p', {class: 'voice-timer', text: '00:00'});
    orbEl = h('div', {class: 'voice-orb connecting'});
    logEl = h('div', {class: 'voice-log', 'aria-live': 'polite'});

    container.replaceChildren(
        h('div', {class: 'voice-head'},
            h('span', {class: 'voice-badge', text: '112'}),
            h('h2', {text: t('voiceTitle')}),
            h('a', {class: 'voice-dial', href: 'tel:112', text: t('voiceDial112')})),
        h('div', {class: 'voice-center'}, orbEl, statusEl, timerEl),
        logEl,
        h('div', {class: 'voice-controls'}, muteBtn, endBtn),
    );
    container.hidden = false;

    try {
        const LK = window.LivekitClient;
        if (!LK?.Room) throw new Error('LiveKit client SDK not loaded');

        const res = await fetch('/api/voice/token', {method: 'POST'});
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `HTTP ${res.status}`);
        }
        const {url, token} = await res.json();

        const room = new LK.Room({adaptiveStream: true, dynacast: true});
        activeRoom = room;

        room.on(LK.RoomEvent.TrackSubscribed, track => {
            if (track.kind === LK.Track.Kind.Audio) {
                audioEl = track.attach();
                audioEl.autoplay = true;
                container.append(audioEl);
            }
        });

        room.on(LK.RoomEvent.ActiveSpeakersChanged, speakers => {
            const agentSpeaking = speakers.some(p => !p.isLocal);
            if (agentSpeaking) setStatus(t('voiceSpeaking'), 'speaking');
            else if (activeRoom) setStatus(t('voiceListening'), 'listening');
        });

        room.on(LK.RoomEvent.TranscriptionReceived, (segments, participant) => {
            const text = segments.map(s => s.text).join(' ').trim();
            if (text && segments.some(s => s.final)) {
                appendLine(participant?.isLocal ? 'user' : 'agent', text);
            }
        });

        room.on(LK.RoomEvent.Disconnected, () => {
            clearInterval(timerId);
            setStatus(t('voiceEnded'), 'ended');
        });

        await room.connect(url, token);
        await room.localParticipant.setMicrophoneEnabled(true);

        startedAt = Date.now();
        setStatus(t('voiceListening'), 'listening');
        timerId = setInterval(() => {
            if (startedAt && timerEl) timerEl.textContent = formatElapsed(Math.floor((Date.now() - startedAt) / 1000));
        }, 1000);
    } catch (err) {
        console.warn('Voice agent connection failed:', err);
        setStatus(t('voiceError'), 'error');
    }
}
