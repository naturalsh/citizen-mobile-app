/* Mobile 112 Voice Agent UI: connects directly to the LiveKit room of the running Voice_Agents backend.
   Supports mic mute/unmute, speaker mute/unmute (agent audio), and switching to text writing mode. */

import {t} from './i18n.js';
import {h} from './dom.js';

let activeRoom = null;
let timerId = null;

function formatElapsed(sec) {
    const m = String(Math.floor(sec / 60)).padStart(2, '0');
    const s = String(sec % 60).padStart(2, '0');
    return `${m}:${s}`;
}

const icon = name => h('span', {class: `ico ico-${name}`, 'aria-hidden': 'true'});

export async function openVoiceAgent(container) {
    if (!container) return;
    if (activeRoom) {
        try { await activeRoom.disconnect(); } catch {}
        activeRoom = null;
    }
    clearInterval(timerId);

    let micMuted = false;
    let speakerMuted = false;
    let textMode = false;
    let startedAt = null;
    const audioEls = [];

    let statusEl, timerEl, orbEl, logEl, composerForm, textInput;

    const close = async () => {
        clearInterval(timerId);
        if (activeRoom) {
            try { await activeRoom.disconnect(); } catch {}
            activeRoom = null;
        }
        for (const el of audioEls) el.remove();
        audioEls.length = 0;
        container.classList.remove('text-mode');
        container.hidden = true;
        container.replaceChildren();
    };

    const setStatus = (text, mode = '') => {
        if (statusEl) statusEl.textContent = text;
        if (orbEl) orbEl.className = `voice-orb ${mode}`.trim();
    };

    let lastLine = '';
    const appendLine = (who, text) => {
        const cleaned = (text || '').trim();
        if (!logEl || !cleaned) return;
        const key = `${who}:${cleaned}`;
        if (key === lastLine) return;
        lastLine = key;
        const item = h('p', {class: `voice-line ${who}`}, h('strong', {text: who === 'agent' ? '112: ' : 'You: '}), cleaned);
        logEl.append(item);
        logEl.scrollTop = logEl.scrollHeight;
    };

    /* Bottom dock buttons: Mic, Speaker (mute agent voice), Text mode, End call */
    const micIco = icon('mic');
    const micLbl = h('span', {class: 'voice-action-lbl', text: t('voiceMute')});
    const micBtn = h('button', {
        class: 'voice-action',
        type: 'button',
        'aria-pressed': 'false',
        onclick: async () => {
            micMuted = !micMuted;
            if (activeRoom?.localParticipant) {
                try { await activeRoom.localParticipant.setMicrophoneEnabled(!micMuted); } catch {}
            }
            micIco.className = `ico ico-${micMuted ? 'mic-off' : 'mic'}`;
            micLbl.textContent = micMuted ? t('voiceUnmute') : t('voiceMute');
            micBtn.setAttribute('aria-pressed', String(micMuted));
            micBtn.classList.toggle('is-muted', micMuted);
        },
    }, h('span', {class: 'voice-circle'}, micIco), micLbl);

    const spkIco = icon('speaker');
    const spkLbl = h('span', {class: 'voice-action-lbl', text: t('voiceSpeakerMute')});
    const spkBtn = h('button', {
        class: 'voice-action',
        type: 'button',
        'aria-pressed': 'false',
        onclick: () => {
            speakerMuted = !speakerMuted;
            for (const el of audioEls) el.muted = speakerMuted;
            spkIco.className = `ico ico-${speakerMuted ? 'speaker-off' : 'speaker'}`;
            spkLbl.textContent = speakerMuted ? t('voiceSpeakerUnmute') : t('voiceSpeakerMute');
            spkBtn.setAttribute('aria-pressed', String(speakerMuted));
            spkBtn.classList.toggle('is-muted', speakerMuted);
        },
    }, h('span', {class: 'voice-circle'}, spkIco), spkLbl);

    const txtIco = icon('keyboard');
    const txtLbl = h('span', {class: 'voice-action-lbl', text: t('voiceTextMode')});
    const txtBtn = h('button', {
        class: 'voice-action',
        type: 'button',
        'aria-pressed': 'false',
        onclick: () => {
            textMode = !textMode;
            container.classList.toggle('text-mode', textMode);
            composerForm.hidden = !textMode;
            txtLbl.textContent = textMode ? t('voiceVoiceMode') : t('voiceTextMode');
            txtBtn.setAttribute('aria-pressed', String(textMode));
            txtBtn.classList.toggle('is-active', textMode);
            if (textMode) textInput.focus();
        },
    }, h('span', {class: 'voice-circle'}, txtIco), txtLbl);

    const endBtn = h('button', {
        class: 'voice-action voice-action-end',
        type: 'button',
        onclick: close,
    }, h('span', {class: 'voice-circle'}, icon('hangup')), h('span', {class: 'voice-action-lbl', text: t('voiceEnd')}));

    textInput = h('input', {
        class: 'voice-input',
        type: 'text',
        autocomplete: 'off',
        placeholder: t('voicePlaceholder'),
        'aria-label': t('voicePlaceholder'),
    });

    const sendBtn = h('button', {
        class: 'voice-send',
        type: 'submit',
        'aria-label': t('voiceSend'),
    }, icon('send'));

    composerForm = h('form', {
        class: 'voice-composer',
        hidden: true,
        onsubmit: async event => {
            event.preventDefault();
            const msg = textInput.value.trim();
            if (!msg) return;
            textInput.value = '';
            appendLine('user', msg);
            if (activeRoom?.localParticipant) {
                try {
                    if (typeof activeRoom.localParticipant.sendText === 'function') {
                        await activeRoom.localParticipant.sendText(msg, {topic: 'lk.chat'});
                    } else {
                        const encoded = new TextEncoder().encode(msg);
                        await activeRoom.localParticipant.publishData(encoded, {reliable: true, topic: 'lk.chat'});
                    }
                } catch (err) {
                    console.warn('Failed to send text to voice agent:', err);
                }
            }
        },
    }, textInput, sendBtn);

    statusEl = h('p', {class: 'voice-status', text: t('voiceConnecting')});
    timerEl = h('p', {class: 'voice-timer', text: '00:00'});
    orbEl = h('div', {class: 'voice-orb connecting'});
    logEl = h('div', {class: 'voice-log', 'aria-live': 'polite'});

    container.classList.remove('text-mode');
    container.replaceChildren(
        h('div', {class: 'voice-head'},
            h('span', {class: 'voice-badge', text: '112'}),
            h('h2', {text: t('voiceTitle')}),
            h('a', {class: 'voice-dial', href: 'tel:112', text: t('voiceDial112')})),
        h('div', {class: 'voice-center'}, orbEl, statusEl, timerEl),
        logEl,
        composerForm,
        h('div', {class: 'voice-controls'}, micBtn, spkBtn, txtBtn, endBtn),
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
                const audioEl = track.attach();
                audioEl.autoplay = true;
                audioEl.muted = speakerMuted;
                audioEls.push(audioEl);
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

        if (typeof room.registerTextStreamHandler === 'function') {
            room.registerTextStreamHandler('lk.chat', async (reader, participantInfo) => {
                try {
                    const text = (await reader.readAll()).trim();
                    if (text && participantInfo?.identity !== room.localParticipant?.identity) {
                        appendLine('agent', text);
                    }
                } catch {}
            });
        }

        room.on(LK.RoomEvent.DataReceived, (payload, participant, _kind, topic) => {
            if (topic === 'lk.chat' && !participant?.isLocal) {
                const text = new TextDecoder().decode(payload).trim();
                if (text) appendLine('agent', text);
            }
        });

        room.on(LK.RoomEvent.Disconnected, () => {
            clearInterval(timerId);
            setStatus(t('voiceEnded'), 'ended');
        });

        await room.connect(url, token);
        await room.localParticipant.setMicrophoneEnabled(!micMuted);

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
