/* Mobile 112 Voice Agent UI overlay.
   Opens when the citizen taps the 112 button. Supports:
   - Browser Web Speech API speech-to-text (tap mic to speak) in en / tr / el
   - SpeechSynthesis text-to-speech replies (with mute toggle)
   - Text input and quick emergency chips for silent or unsupported devices
   - Direct "tel:112" escape button at all times
   Zero inline styles or scripts (CSP-compliant via dom.js h()). */

import {t, language} from './i18n.js';
import {h} from './dom.js';
import {createVoiceSession} from './voice_engine.js';

const SPEECH_LANG = {en: 'en-US', tr: 'tr-TR', el: 'el-GR'};
const SpeechRec = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition || null;

const glyph = name => h('span', {class: `ico ico-${name}`, 'aria-hidden': 'true'});

function formatTimer(sec) {
    const m = String(Math.floor(sec / 60)).padStart(2, '0');
    const s = String(sec % 60).padStart(2, '0');
    return `${m}:${s}`;
}

export function createVoiceUI(container, {getPosition, onClose}) {
    let session = null;
    let open = false;
    let muted = false;
    let listening = false;
    let speaking = false;
    let busy = false;
    let ended = false;
    let handoff = false;
    let seconds = 0;
    let timer = null;
    let rec = null;
    let messages = [];
    let report = null;
    let draft = '';

    function stopSpeech() {
        try {
            globalThis.speechSynthesis?.cancel();
        } catch {
            // ignore
        }
        speaking = false;
    }

    function stopMic() {
        if (rec) {
            try {
                rec.abort();
            } catch {
                // ignore
            }
            rec = null;
        }
        listening = false;
    }

    function speak(text) {
        if (muted || !globalThis.speechSynthesis || !text) return;
        stopSpeech();
        try {
            const utter = new SpeechSynthesisUtterance(text);
            utter.lang = SPEECH_LANG[language()] || 'en-US';
            utter.rate = 0.98;
            speaking = true;
            render();
            utter.onend = utter.onerror = () => {
                speaking = false;
                render();
            };
            globalThis.speechSynthesis.speak(utter);
        } catch {
            speaking = false;
        }
    }

    function statusText() {
        if (handoff) return t('voice.statusHandoff');
        if (ended) return t('voice.statusEnded');
        if (busy) return t('voice.statusThinking');
        if (listening) return t('voice.statusListening');
        if (speaking) return t('voice.statusSpeaking');
        return SpeechRec ? t('voice.statusReady') : t('voice.statusType');
    }

    async function sendUtterance(text) {
        const clean = String(text || '').trim();
        if (!clean || !session || busy || ended) return;
        stopMic();
        stopSpeech();
        draft = '';
        messages.push({who: 'caller', text: clean});
        busy = true;
        render();
        try {
            const result = await session.turn(clean);
            messages.push({who: 'agent', text: result.reply_text, action: result.action});
            report = result.report || report;
            if (result.action === 'handoff') handoff = true;
            if (result.action === 'end') ended = true;
            busy = false;
            render();
            speak(result.reply_text);
        } catch {
            busy = false;
            messages.push({who: 'agent', text: t('voice.error')});
            render();
        }
    }

    function toggleMic() {
        if (ended || busy) return;
        if (listening) {
            stopMic();
            render();
            return;
        }
        if (!SpeechRec) return;
        stopSpeech();
        try {
            rec = new SpeechRec();
            rec.lang = SPEECH_LANG[language()] || 'en-US';
            rec.interimResults = false;
            rec.maxAlternatives = 1;
            listening = true;
            render();
            rec.onresult = event => {
                const spoken = event.results?.[0]?.[0]?.transcript || '';
                listening = false;
                rec = null;
                if (spoken) sendUtterance(spoken);
                else render();
            };
            rec.onerror = () => {
                listening = false;
                rec = null;
                render();
            };
            rec.onend = () => {
                if (listening) {
                    listening = false;
                    rec = null;
                    render();
                }
            };
            rec.start();
        } catch {
            listening = false;
            rec = null;
            render();
        }
    }

    async function endCall() {
        stopMic();
        stopSpeech();
        if (timer) clearInterval(timer);
        timer = null;
        if (session && !ended) {
            try {
                report = await session.end(handoff ? 'handed_off' : 'hung_up');
            } catch {
                // ignore
            }
        }
        ended = true;
        render();
    }

    function close() {
        stopMic();
        stopSpeech();
        if (timer) clearInterval(timer);
        timer = null;
        open = false;
        container.hidden = true;
        onClose?.();
    }

    async function start() {
        stopMic();
        stopSpeech();
        if (timer) clearInterval(timer);
        open = true;
        ended = false;
        handoff = false;
        busy = true;
        seconds = 0;
        messages = [];
        report = null;
        draft = '';
        container.hidden = false;
        render();

        const pos = getPosition?.();
        const aml = pos ? {lat: pos.lonLat[1], lon: pos.lonLat[0], accuracy_m: pos.accuracy || null} : null;
        session = await createVoiceSession({lang: language(), aml});
        const first = await session.start();
        messages.push({who: 'agent', text: first.reply_text, action: first.action});
        report = first.report || null;
        busy = false;
        timer = setInterval(() => {
            if (!ended && open) {
                seconds += 1;
                const el = container.querySelector('.voice-timer');
                if (el) el.textContent = formatTimer(seconds);
            }
        }, 1000);
        render();
        speak(first.reply_text);
    }

    function renderReport() {
        if (!report || (!report.hazard && !report.location && !report.injuries && !report.advice_given)) return null;
        const rows = [];
        if (report.hazard) rows.push(h('li', {}, h('strong', {text: `${t('voice.fieldHazard')}: `}), report.hazard));
        if (report.location) rows.push(h('li', {}, h('strong', {text: `${t('voice.fieldLocation')}: `}), report.location));
        if (report.urgency) rows.push(h('li', {}, h('strong', {text: `${t('voice.fieldUrgency')}: `}), report.urgency));
        return h('div', {class: 'voice-report'},
            h('div', {class: 'voice-report-title', text: t('voice.reportTitle')}),
            rows.length > 0 && h('ul', {class: 'voice-report-list'}, rows),
            report.advice_given && h('p', {class: 'voice-advice', text: report.advice_given}));
    }

    function render() {
        if (!open) return;
        const callerTurns = messages.filter(m => m.who === 'caller').length;
        const modeLabel = session?.mode === 'live' ? t('voice.modeLive') : t('voice.modeLocal');

        const inputEl = h('input', {
            class: 'voice-input',
            type: 'text',
            placeholder: t('voice.inputPlaceholder'),
            value: draft,
            disabled: busy || ended,
            oninput: e => (draft = e.currentTarget.value),
            onkeydown: e => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    sendUtterance(draft);
                }
            },
        });

        const quickChips = !ended && callerTurns === 0 ? h('div', {class: 'voice-chips'},
            [t('voice.quick.trapped'), t('voice.quick.injured'), t('voice.quick.fire'), t('voice.quick.human')].map(label =>
                h('button', {
                    class: 'voice-chip',
                    type: 'button',
                    onclick: () => sendUtterance(label),
                }, label))) : null;

        const transcript = h('div', {class: 'voice-chat'},
            messages.map(msg =>
                h('div', {class: `voice-msg ${msg.who}${msg.action === 'handoff' ? ' handoff' : ''}`},
                    h('p', {text: msg.text}))),
            renderReport(),
            quickChips);

        const body = h('div', {class: 'voice-shell'},
            h('header', {class: 'voice-top'},
                h('button', {class: 'round voice-close', type: 'button', 'aria-label': t('close'), onclick: close}, glyph('close')),
                h('div', {class: 'voice-title-box'},
                    h('h2', {text: t('voice.title')}),
                    h('span', {class: 'voice-sub'},
                        h('span', {class: `voice-dot${ended ? ' off' : ''}`, 'aria-hidden': 'true'}),
                        h('span', {class: 'voice-timer', text: formatTimer(seconds)}),
                        ' · ',
                        modeLabel)),
                h('a', {class: 'button button-fill voice-dial', href: 'tel:112'}, glyph('call'), t('voice.dialDirect'))),

            h('p', {class: 'voice-disclosure', text: t('voice.disclosure')}),

            transcript,

            h('footer', {class: 'voice-dock'},
                h('p', {class: `voice-status${listening ? ' live' : ''}`, text: statusText()}),
                !ended && h('div', {class: 'voice-controls'},
                    h('button', {
                        class: `voice-side${muted ? ' muted' : ''}`,
                        type: 'button',
                        'aria-label': t(muted ? 'voice.unmute' : 'voice.mute'),
                        'aria-pressed': String(muted),
                        onclick: () => {
                            muted = !muted;
                            if (muted) stopSpeech();
                            render();
                        },
                    }, glyph(muted ? 'volume-off' : 'volume')),
                    h('button', {
                        class: `voice-mic${listening ? ' listening' : ''}`,
                        type: 'button',
                        disabled: !SpeechRec || busy,
                        'aria-label': t(listening ? 'voice.stopMic' : 'voice.startMic'),
                        onclick: toggleMic,
                    }, glyph('mic')),
                    h('button', {
                        class: 'voice-side voice-end',
                        type: 'button',
                        'aria-label': t('voice.endCall'),
                        onclick: endCall,
                    }, glyph('close'))),
                !ended ? h('div', {class: 'voice-form'},
                    inputEl,
                    h('button', {
                        class: 'voice-send',
                        type: 'button',
                        disabled: busy,
                        'aria-label': t('voice.send'),
                        onclick: () => sendUtterance(draft),
                    }, glyph('send')))
                : h('div', {class: 'voice-ended-actions'},
                    h('button', {class: 'button button-fill button-large main', type: 'button', onclick: start}, t('voice.newCall')),
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
