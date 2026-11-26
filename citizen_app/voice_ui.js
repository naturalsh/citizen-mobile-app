/* Mobile 112 Voice Agent UI overlay connected directly to naturalsh/Voice_Agents via LiveKit WebRTC.
   Tapping 112 joins a fresh LiveKit Cloud room where voice_agent/voice/agent.py answers with:
   Silero VAD + Soniox STT -> brain.turn_stream() (Gemini) -> ElevenLabs/Cartesia TTS.
   Live transcriptions stream into the chat view; mic mute, speaker mute, and end call work natively.
   Zero inline styles or scripts (CSP-compliant via dom.js h()). */

import {t, language} from './i18n.js';
import {h} from './dom.js';
import {fetchLiveKitToken} from './voice_engine.js';

const glyph = name => h('span', {class: `ico ico-${name}`, 'aria-hidden': 'true'});

function formatTimer(sec) {
    const m = String(Math.floor(sec / 60)).padStart(2, '0');
    const s = String(sec % 60).padStart(2, '0');
    return `${m}:${s}`;
}

export function createVoiceUI(container, {onClose}) {
    let room = null;
    let open = false;
    let connecting = false;
    let connected = false;
    let agentJoined = false;
    let agentSpeaking = false;
    let micMuted = false;
    let speakerMuted = false;
    let ended = false;
    let connectError = null;
    let seconds = 0;
    let timer = null;
    let messages = [];
    let audioEls = [];

    function cleanupRoom() {
        for (const el of audioEls) {
            try {
                el.pause();
                el.remove();
            } catch {
                // ignore
            }
        }
        audioEls = [];
        if (room) {
            try {
                room.disconnect();
            } catch {
                // ignore
            }
            room = null;
        }
        connected = false;
        connecting = false;
        agentJoined = false;
        agentSpeaking = false;
    }

    function statusText() {
        if (connectError) return t('voice.statusOffline');
        if (ended) return t('voice.statusEnded');
        if (connecting) return t('voice.statusThinking');
        if (agentSpeaking) return t('voice.statusSpeaking');
        if (micMuted) return t('voice.mute');
        if (connected && !agentJoined) return t('voice.statusThinking');
        return t('voice.statusListening');
    }

    function upsertTranscript(id, who, text) {
        const clean = String(text || '').trim();
        if (!clean) return;
        const existing = messages.find(m => m.id === id);
        if (existing) existing.text = clean;
        else messages.push({id, who, text: clean});
        render();
    }

    async function toggleMic() {
        if (!room || !connected || ended) return;
        micMuted = !micMuted;
        try {
            await room.localParticipant.setMicrophoneEnabled(!micMuted);
        } catch {
            micMuted = !micMuted;
        }
        render();
    }

    function toggleSpeaker() {
        speakerMuted = !speakerMuted;
        for (const el of audioEls) el.muted = speakerMuted;
        render();
    }

    function endCall() {
        if (timer) clearInterval(timer);
        timer = null;
        cleanupRoom();
        ended = true;
        render();
    }

    function close() {
        if (timer) clearInterval(timer);
        timer = null;
        cleanupRoom();
        open = false;
        container.hidden = true;
        onClose?.();
    }

    async function start() {
        if (timer) clearInterval(timer);
        cleanupRoom();
        open = true;
        connecting = true;
        ended = false;
        micMuted = false;
        speakerMuted = false;
        connectError = null;
        seconds = 0;
        messages = [];
        container.hidden = false;
        render();

        const LK = globalThis.LivekitClient;
        if (!LK) {
            connecting = false;
            ended = true;
            connectError = 'LiveKit client not loaded';
            render();
            return;
        }

        try {
            const {livekit_url, token} = await fetchLiveKitToken({lang: language()});
            room = new LK.Room({adaptiveStream: true, dynacast: true});

            room.on(LK.RoomEvent.ParticipantConnected, () => {
                agentJoined = true;
                render();
            });

            room.on(LK.RoomEvent.TrackSubscribed, track => {
                if (track.kind === LK.Track.Kind.Audio) {
                    const audio = track.attach();
                    audio.autoplay = true;
                    audio.muted = speakerMuted;
                    audio.className = 'unseen';
                    document.body.appendChild(audio);
                    audioEls.push(audio);
                    agentJoined = true;
                    render();
                }
            });

            room.on(LK.RoomEvent.TrackUnsubscribed, track => {
                track.detach().forEach(el => el.remove());
            });

            room.on(LK.RoomEvent.ActiveSpeakersChanged, speakers => {
                agentSpeaking = speakers.some(p => p.identity !== room?.localParticipant?.identity);
                render();
            });

            room.on(LK.RoomEvent.TranscriptionReceived, (segments, participant) => {
                const who = participant?.identity === room?.localParticipant?.identity ? 'caller' : 'agent';
                for (const seg of segments) {
                    upsertTranscript(seg.id, who, seg.text);
                }
            });

            room.on(LK.RoomEvent.Disconnected, () => {
                if (open && !ended) {
                    if (timer) clearInterval(timer);
                    timer = null;
                    cleanupRoom();
                    ended = true;
                    render();
                }
            });

            await room.connect(livekit_url, token);
            await room.localParticipant.setMicrophoneEnabled(true);

            connecting = false;
            connected = true;
            timer = setInterval(() => {
                if (!ended && open) {
                    seconds += 1;
                    const el = container.querySelector('.voice-timer');
                    if (el) el.textContent = formatTimer(seconds);
                }
            }, 1000);
            render();
        } catch (err) {
            cleanupRoom();
            ended = true;
            connectError = String(err?.message || err);
            render();
        }
    }

    function render() {
        if (!open) return;
        const modeLabel = connectError ? t('voice.statusOffline') : t('voice.modeLive');

        const transcript = h('div', {class: 'voice-chat'},
            connectError && h('div', {class: 'voice-msg agent handoff'},
                h('p', {text: t('voice.offlineExplain')})),
            !connectError && !messages.length && h('div', {class: 'voice-msg agent'},
                h('p', {text: statusText()})),
            messages.map(msg =>
                h('div', {class: `voice-msg ${msg.who}`},
                    h('p', {text: msg.text}))));

        const body = h('div', {class: 'voice-shell'},
            h('header', {class: 'voice-top'},
                h('button', {class: 'round voice-close', type: 'button', 'aria-label': t('close'), onclick: close}, glyph('close')),
                h('div', {class: 'voice-title-box'},
                    h('h2', {text: t('voice.title')}),
                    h('span', {class: 'voice-sub'},
                        h('span', {class: `voice-dot${ended || connectError ? ' off' : ''}`, 'aria-hidden': 'true'}),
                        h('span', {class: 'voice-timer', text: formatTimer(seconds)}),
                        ' · ',
                        modeLabel)),
                h('a', {class: 'button button-fill voice-dial', href: 'tel:112'}, glyph('call'), t('voice.dialDirect'))),

            h('p', {class: 'voice-disclosure', text: t('voice.disclosure')}),

            transcript,

            h('footer', {class: 'voice-dock'},
                h('p', {class: `voice-status${connected && !micMuted && !ended ? ' live' : ''}`, text: statusText()}),
                !ended ? h('div', {class: 'voice-controls'},
                    h('button', {
                        class: `voice-side${speakerMuted ? ' muted' : ''}`,
                        type: 'button',
                        'aria-label': t(speakerMuted ? 'voice.unmute' : 'voice.mute'),
                        'aria-pressed': String(speakerMuted),
                        onclick: toggleSpeaker,
                    }, glyph(speakerMuted ? 'volume-off' : 'volume')),
                    h('button', {
                        class: `voice-mic${connected && !micMuted ? ' listening' : ''}`,
                        type: 'button',
                        disabled: connecting,
                        'aria-label': t(micMuted ? 'voice.startMic' : 'voice.stopMic'),
                        'aria-pressed': String(!micMuted),
                        onclick: toggleMic,
                    }, glyph('mic')),
                    h('button', {
                        class: 'voice-side voice-end',
                        type: 'button',
                        'aria-label': t('voice.endCall'),
                        onclick: endCall,
                    }, glyph('close')))
                : h('div', {class: 'voice-ended-actions'},
                    h('button', {class: 'button button-fill button-large main', type: 'button', onclick: start}, t(connectError ? 'retry' : 'voice.newCall')),
                    h('button', {class: 'plain', type: 'button', onclick: close}, t('close')))));

        container.replaceChildren(body);
        transcript.scrollTop = transcript.scrollHeight;
    }

    return {
        open: start,
        close,
        relabel: () => open && render(),
    };
}
