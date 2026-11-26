/* Mobile 112 Voice Agent interface: connects directly to the embedded Voice_Agents LiveKit run.
   Flow:
     1. POST /api/voice/token {lang} -> {url, token, room}
     2. Connect with LivekitClient.Room directly to LiveKit Cloud (same room the voice.agent worker joins)
     3. Publish microphone audio, subscribe to agent audio, show live agent state & transcripts. */

import {t, language} from './i18n.js';
import {h} from './dom.js';

const TOKEN_API = new URL('../api/voice/token', location.href).href;

export function createVoicePanel(container) {
    let room = null;
    let status = 'idle';            // 'idle' | 'connecting' | 'connected' | 'ended' | 'error'
    let agentState = 'waiting';     // 'waiting' | 'listening' | 'thinking' | 'speaking'
    let muted = false;
    let errorDetail = '';
    let startedAt = null;
    let timerId = null;
    let audioEls = [];
    const lines = new Map();        // segmentId -> {who: 'caller' | 'agent', text}

    function formatElapsed() {
        if (!startedAt) return '00:00';
        const sec = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
        const m = String(Math.floor(sec / 60)).padStart(2, '0');
        const s = String(sec % 60).padStart(2, '0');
        return `${m}:${s}`;
    }

    function clearAudio() {
        for (const el of audioEls) {
            el.pause?.();
            el.remove();
        }
        audioEls = [];
    }

    function stopTimer() {
        if (timerId) {
            clearInterval(timerId);
            timerId = null;
        }
    }

    async function disconnect(nextStatus = 'ended') {
        stopTimer();
        clearAudio();
        const active = room;
        room = null;
        if (active) {
            try {
                await active.disconnect();
            } catch {
                // already disconnected
            }
        }
        muted = false;
        status = nextStatus;
        agentState = 'waiting';
        render();
    }

    async function toggleMute() {
        if (!room || status !== 'connected') return;
        muted = !muted;
        try {
            await room.localParticipant.setMicrophoneEnabled(!muted);
        } catch {
            muted = !muted;
        }
        render();
    }

    function statusLabel() {
        if (status === 'connecting') return t('voiceConnecting');
        if (status === 'error') return t('voiceError');
        if (status === 'ended') return t('voiceEnded');
        if (status === 'connected') {
            if (muted) return t('voiceMuted');
            if (agentState === 'speaking') return t('voiceSpeaking');
            if (agentState === 'thinking') return t('voiceThinking');
            if (agentState === 'listening') return t('voiceListening');
            return t('voiceWaitingAgent');
        }
        return t('voiceReady');
    }

    async function startCall() {
        if (status === 'connecting' || status === 'connected') return;
        const LK = window.LivekitClient;
        if (!LK) {
            status = 'error';
            errorDetail = t('voiceSdkMissing');
            render();
            return;
        }
        status = 'connecting';
        agentState = 'waiting';
        errorDetail = '';
        muted = false;
        lines.clear();
        render();

        try {
            const resp = await fetch(TOKEN_API, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({lang: language()}),
            });
            const data = await resp.json();
            if (!resp.ok || !data.url || !data.token) {
                throw new Error(data.error || `HTTP ${resp.status}`);
            }

            const nextRoom = new LK.Room({
                adaptiveStream: true,
                dynacast: true,
                audioCaptureDefaults: {echoCancellation: true, noiseSuppression: true, autoGainControl: true},
            });
            room = nextRoom;

            nextRoom.on(LK.RoomEvent.TrackSubscribed, track => {
                if (track.kind === LK.Track.Kind.Audio) {
                    const el = track.attach();
                    el.autoplay = true;
                    el.playsInline = true;
                    document.body.appendChild(el);
                    audioEls.push(el);
                    el.play?.().catch(() => {});
                }
            });

            nextRoom.on(LK.RoomEvent.TrackUnsubscribed, track => {
                track.detach().forEach(el => el.remove());
            });

            nextRoom.on(LK.RoomEvent.ParticipantAttributesChanged, (changed, participant) => {
                if (participant?.isLocal) return;
                const stateAttr = changed?.['lk.agent.state'] || participant?.attributes?.['lk.agent.state'];
                if (stateAttr) {
                    agentState = stateAttr;
                    render();
                }
            });

            nextRoom.on(LK.RoomEvent.ActiveSpeakersChanged, speakers => {
                if (status !== 'connected') return;
                const agentTalking = speakers.some(p => !p.isLocal);
                if (agentTalking) {
                    agentState = 'speaking';
                    render();
                } else if (agentState === 'speaking') {
                    agentState = 'listening';
                    render();
                }
            });

            nextRoom.on(LK.RoomEvent.ParticipantConnected, participant => {
                if (!participant.isLocal && agentState === 'waiting') {
                    agentState = 'listening';
                    render();
                }
            });

            if (LK.RoomEvent.TranscriptionReceived) {
                nextRoom.on(LK.RoomEvent.TranscriptionReceived, (segments, participant) => {
                    const who = participant?.isLocal ? 'caller' : 'agent';
                    let changed = false;
                    for (const seg of segments) {
                        const text = (seg.text || '').trim();
                        if (!text) continue;
                        lines.set(seg.id || `${who}-${lines.size}`, {who, text});
                        changed = true;
                    }
                    if (changed) render();
                });
            }

            nextRoom.on(LK.RoomEvent.Disconnected, () => {
                if (room === nextRoom) disconnect('ended');
            });

            await nextRoom.connect(data.url, data.token);
            await nextRoom.localParticipant.setMicrophoneEnabled(true);
            try {
                await nextRoom.startAudio();
            } catch {
                // audio already unlocked by user click
            }

            status = 'connected';
            agentState = nextRoom.remoteParticipants.size > 0 ? 'listening' : 'waiting';
            startedAt = Date.now();
            stopTimer();
            timerId = setInterval(() => {
                const clockEl = container.querySelector('.voice-timer');
                if (clockEl) clockEl.textContent = formatElapsed();
            }, 1000);
            render();
        } catch (err) {
            console.error('112 Voice Agent connection failed:', err);
            await disconnect('error');
            errorDetail = err?.name === 'NotAllowedError'
                ? t('voiceMicDenied')
                : (err?.message || t('voiceError'));
            render();
        }
    }

    function open() {
        container.hidden = false;
        render();
        startCall();
    }

    async function close() {
        await disconnect('idle');
        container.hidden = true;
    }

    function render() {
        const orbState = status === 'connected' ? (muted ? 'muted' : agentState) : status;
        const transcriptItems = [...lines.values()].slice(-8);

        container.replaceChildren(
            h('div', {class: 'voice-shell'},
                h('header', {class: 'voice-head'},
                    h('div', {class: 'voice-title-box'},
                        h('span', {class: 'voice-badge', text: '112'}),
                        h('div', {},
                            h('h2', {text: t('voiceTitle')}),
                            h('p', {class: 'voice-sub', text: t('voiceAutomated')}))),
                    h('button', {class: 'shut voice-close', type: 'button', 'aria-label': t('close'), onclick: close},
                        h('span', {class: 'ico ico-close', 'aria-hidden': 'true'}))),

                h('div', {class: 'voice-stage'},
                    h('div', {class: `voice-orb ${orbState}`, 'aria-hidden': 'true'},
                        h('span', {class: 'voice-ring'}),
                        h('span', {class: `ico ico-${muted ? 'mic-off' : 'mic'}`})),
                    h('p', {class: 'voice-status', role: 'status', text: statusLabel()}),
                    status === 'connected' && h('p', {class: 'voice-timer', text: formatElapsed()}),
                    errorDetail && h('p', {class: 'voice-error', text: errorDetail})),

                h('div', {class: 'voice-feed', 'aria-live': 'polite'},
                    transcriptItems.length
                        ? transcriptItems.map(item =>
                            h('p', {class: `voice-msg ${item.who}`},
                                h('span', {class: 'voice-who', text: t(item.who === 'caller' ? 'voiceYou' : 'voiceAgent')}),
                                item.text))
                        : h('p', {class: 'voice-hint', text: t('voiceHint')})),

                h('footer', {class: 'voice-controls'},
                    status === 'connected' || status === 'connecting'
                        ? [
                            h('button', {
                                class: `voice-btn voice-mute ${muted ? 'is-muted' : ''}`,
                                type: 'button',
                                'aria-pressed': String(muted),
                                'aria-label': t(muted ? 'voiceUnmute' : 'voiceMute'),
                                onclick: toggleMute,
                            }, h('span', {class: `ico ico-${muted ? 'mic-off' : 'mic'}`, 'aria-hidden': 'true'})),
                            h('button', {
                                class: 'voice-btn voice-hangup',
                                type: 'button',
                                'aria-label': t('voiceEnd'),
                                onclick: () => disconnect('ended'),
                            }, h('span', {class: 'ico ico-hangup', 'aria-hidden': 'true'})),
                        ]
                        : [
                            h('button', {class: 'button button-fill button-large main voice-start', type: 'button', onclick: startCall},
                                t(status === 'ended' || status === 'error' ? 'voiceCallAgain' : 'voiceStart')),
                        ],
                    h('a', {class: 'voice-dial-fallback', href: 'tel:112', text: t('voiceDialDirect')}))),
        );
    }

    return {open, close, relabel: render};
}
