/* 112 Voice Agent session client + on-device emergency triage fallback.
   Follows Voice_Agents/brain/contract.py (start_call / turn / end_call) and
   Voice_Agents safety rules (EU AI Act Article 50 disclosure, verbatim official
   advice from Voice_Agents/brain/advice/*.json, immediate handoff on life-threat
   or human operator request).

   When a live Voice_Agents HTTP bridge is reachable at ../voice-api/, requests go
   there; otherwise (e.g. GitHub Pages or offline phone) the on-device triage engine
   runs locally with zero network dependency. */

const VOICE_API = typeof location !== 'undefined' ? new URL('../voice-api/', location.href) : null;

export const PHRASES = {
    greeting: {
        en: 'You are speaking with the automated emergency assistant of 112. All operators are busy, so I will take your details and pass them on right away. Tell me what happened, and where.',
        tr: '112\'nin otomatik acil durum asistanına bağlandınız. Tüm operatörler meşgul, bu yüzden bilgilerinizi alıp hemen iletiyorum. Ne olduğunu ve nerede olduğunu anlatın.',
        el: 'Είστε συνδεδεμένοι με τον αυτόματο βοηθό έκτακτης ανάγκης του 112. Όλοι οι χειριστές είναι απασχολημένοι, γι\' αυτό θα καταγράψω τα στοιχεία σας και θα τα διαβιβάσω αμέσως. Πείτε μου τι συνέβη και πού.',
    },
    handoff: {
        en: 'I am connecting you to a human operator now. Please stay on the line, or tap Call 112 directly if someone is in immediate danger.',
        tr: 'Sizi şimdi bir operatöre bağlıyorum. Lütfen hatta kalın; birinin hayatı hemen tehlikedeyse doğrudan 112 Ara düğmesine dokunun.',
        el: 'Σας συνδέω τώρα με έναν χειριστή. Παρακαλώ μείνετε στη γραμμή ή πατήστε απευθείας Κλήση 112 αν κάποιος κινδυνεύει άμεσα.',
    },
    askLocation: {
        en: 'Understood. Where exactly are you? Tell me the street name, building number, or nearest landmark.',
        tr: 'Anlaşıldı. Tam olarak neredesiniz? Sokak adını, bina numarasını veya yakınındaki bilinen bir yeri söyleyin.',
        el: 'Κατανοητό. Πού ακριβώς βρίσκεστε; Πείτε μου την οδό, τον αριθμό ή ένα κοντινό γνωστό σημείο.',
    },
    askDetails: {
        en: 'Are there any injuries, or is anyone trapped or in immediate danger?',
        tr: 'Yaralı var mı, ya da mahsur kalan veya acil tehlikede olan biri var mı?',
        el: 'Υπάρχουν τραυματίες ή κάποιος εγκλωβισμένος ή σε άμεσο κίνδυνο;',
    },
    confirm: {
        en: 'Before I pass this on to 112 operators: is everything correct now? Say yes to send, or tell me what to change.',
        tr: '112 operatörlerine iletmeden önce: her şey doğru mu? Göndermek için evet deyin veya düzeltmek istediğiniz bilgiyi söyleyin.',
        el: 'Πριν το διαβιβάσω στους χειριστές του 112: είναι όλα σωστά τώρα; Πείτε ναι για αποστολή ή τι να αλλάξω.',
    },
    passedOn: {
        en: 'Your report is going to the operators right away.',
        tr: 'Bildiriminiz hemen operatörlere iletiliyor.',
        el: 'Η αναφορά σας περνά αμέσως στους χειριστές.',
    },
};

/* Verbatim official safety advice from Voice_Agents/brain/advice/*.json. */
export const ADVICE = {
    trapped: {
        en: 'Do not light matches or lighters. Cover your mouth with cloth and move as little as possible. Tap on a pipe or wall so rescuers can hear you, and shout only as a last resort to save your strength.',
        tr: 'Kibrit veya çakmak yakmayın. Ağzınızı bir bezle kapatın ve olabildiğince az hareket edin. Kurtarma ekiplerinin sizi duyması için bir boruya veya duvara vurun; gücünüzü korumak için ancak son çare olarak bağırın.',
        el: 'Μην ανάβετε σπίρτα ή αναπτήρες. Καλύψτε το στόμα σας με ένα ύφασμα και κινηθείτε όσο λιγότερο γίνεται. Χτυπάτε σε έναν σωλήνα ή στον τοίχο για να σας ακούσουν οι διασώστες, και φωνάξτε μόνο αν δεν υπάρχει άλλη λύση, για να μην εξαντληθείτε.',
    },
    earthquake: {
        en: 'Stay inside during shaking. Get under a sturdy table, kneel and hold on to its leg, or cover your head and neck away from windows. Once shaking stops, move to open ground away from buildings and power lines.',
        tr: 'Sarsıntı sırasında sağlam bir masanın altına girin, diz çöküp tutunun veya pencerelerden uzak durarak başınızı koruyun. Sarsıntı bitince binalardan ve elektrik hatlarından uzak açık bir alana çıkın.',
        el: 'Κατά τη δόνηση μπείτε κάτω από ένα γερό τραπέζι ή προστατέψτε κεφάλι και λαιμό μακριά από παράθυρα. Μόλις σταματήσει, βγείτε σε ανοιχτό χώρο μακριά από κτίρια και καλώδια.',
    },
    fire: {
        en: 'Leave the building immediately using stairs, never the elevator. Stay low under smoke and close doors behind you. If you cannot leave, seal door gaps with wet cloth and signal from a window.',
        tr: 'Asansör kullanmadan merdivenlerden hemen binayı terk edin. Dumanın altında eğilerek ilerleyin ve kapıları arkanızdan kapatın. Çıkamıyorsanız kapı altını ıslak bezle kapatıp pencereden işaret verin.',
        el: 'Βγείτε αμέσως από το κτίριο από τις σκάλες, ποτέ με ασανσέρ. Μείνετε χαμηλά κάτω από τον καπνό και κλείστε τις πόρτες πίσω σας. Αν δεν μπορείτε να βγείτε, κλείστε τα κενά της πόρτας με βρεγμένο πανί.',
    },
    medical: {
        en: 'If there is heavy bleeding, press firmly on the wound with a clean cloth and do not remove it. Keep the person warm and still unless they are in immediate danger.',
        tr: 'Şiddetli kanama varsa temiz bir bezle yaranın üzerine sıkıca bastırın ve bezi kaldırmayın. Acil tehlike yoksa yaralıyı hareket ettirmeyin ve sıcak tutun.',
        el: 'Αν υπάρχει έντονη αιμορραγία, πιέστε σταθερά την πληγή με καθαρό πανί χωρίς να το αφαιρέσετε. Κρατήστε το άτομο ζεστό και ακίνητο αν δεν υπάρχει άμεσος κίνδυνος.',
    },
    flood: {
        en: 'Move immediately to higher ground or an upper floor. Do not walk or drive through moving water, and stay away from fallen power lines.',
        tr: 'Hemen yüksek bir noktaya veya üst katlara çıkın. Akan suyun içinden yürümeyin veya araçla geçmeyin; devrilmiş elektrik hatlarından uzak durun.',
        el: 'Μετακινηθείτε αμέσως σε υψηλότερο σημείο ή σε πάνω όροφο. Μην περπατάτε και μην οδηγείτε μέσα σε τρεχούμενο νερό και μείνετε μακριά από πεσμένα καλώδια.',
    },
};

const pick = (table, lang) => table[lang] || table.en;

const PATTERNS = {
    human: /\b(operator|human|person|operatör|insan|yetkili|χειριστ|άνθρωπ)\b/i,
    notBreathing: /(not breathing|stopped breathing|no pulse|unconscious|nefes almıyor|bilinci kapalı|kalbi durdu|δεν αναπνέει|αναίσθητ)/i,
    trapped: /(trapped|rubble|collapsed|under debris|enkaz|mahsur|çöktü|yıkıldı|εγκλωβισ|ερείπια|κατέρρευσ)/i,
    fire: /(fire|smoke|burning|flames|yangın|duman|yanıyor|φωτιά|πυρκαγιά|καπν)/i,
    medical: /(injur|bleed|hurt|broken|ambulance|heart|yaralı|kanama|ambulans|kırık|τραυματ|αιμορραγ|ασθενοφόρ)/i,
    flood: /(flood|water rising|sel|su bastı|πλημμύρ)/i,
    earthquake: /(earthquake|shaking|deprem|sarsıntı|σεισμ)/i,
    location: /(street|sokak|cadde|mahalle|park|hospital|hastane|near|at |οδός|πλατεία|νοσοκομείο|no\.?\s*\d|\d{2}\.\d{3})/i,
    confirmYes: /^\s*(yes|yeah|yep|ok|okay|confirm|correct|send|evet|tamam|doğru|gönder|ναι|εντάξει|σωστά)\b/i,
};

/* Deterministic on-device session matching Voice_Agents/brain/contract.py. */
export function createLocalSession({lang = 'en', aml = null} = {}) {
    const callId = `local-${Date.now().toString(36)}`;
    const report = {
        call_id: callId,
        mode: 'local',
        hazard: null,
        summary: '',
        location: aml ? `${aml.lat.toFixed(5)}, ${aml.lon.toFixed(5)}` : null,
        injuries: null,
        urgency: 'medium',
        advice_given: null,
        status: 'in_progress',
    };
    let stage = 'what';

    const snapshot = () => ({...report});

    return {
        mode: 'local',
        callId,
        async start() {
            return {
                reply_text: pick(PHRASES.greeting, lang),
                lang,
                action: 'continue',
                handoff_reason: null,
                report: snapshot(),
            };
        },
        async turn(text) {
            const clean = String(text || '').trim();
            if (!clean) {
                return {
                    reply_text: pick(PHRASES.askDetails, lang),
                    lang,
                    action: 'continue',
                    handoff_reason: null,
                    report: snapshot(),
                };
            }

            // Immediate safety handoffs (EU AI Act & Docs/Research/05)
            if (PATTERNS.notBreathing.test(clean)) {
                report.urgency = 'critical';
                report.injuries = clean;
                report.summary = report.summary ? `${report.summary}; ${clean}` : clean;
                report.status = 'handed_off';
                return {
                    reply_text: pick(PHRASES.handoff, lang),
                    lang,
                    action: 'handoff',
                    handoff_reason: 'life_threat_not_breathing',
                    report: snapshot(),
                };
            }
            if (PATTERNS.human.test(clean)) {
                report.status = 'handed_off';
                return {
                    reply_text: pick(PHRASES.handoff, lang),
                    lang,
                    action: 'handoff',
                    handoff_reason: 'caller_requested_human',
                    report: snapshot(),
                };
            }

            // Confirming final report
            if (stage === 'confirm' && PATTERNS.confirmYes.test(clean)) {
                report.status = 'completed';
                return {
                    reply_text: pick(PHRASES.passedOn, lang),
                    lang,
                    action: 'end',
                    handoff_reason: null,
                    report: snapshot(),
                };
            }

            // Detect hazard & assign official verbatim advice
            if (PATTERNS.trapped.test(clean)) {
                report.hazard = 'trapped';
                report.urgency = 'critical';
                report.advice_given = pick(ADVICE.trapped, lang);
            } else if (PATTERNS.fire.test(clean)) {
                report.hazard = report.hazard || 'fire';
                report.urgency = 'high';
                report.advice_given = report.advice_given || pick(ADVICE.fire, lang);
            } else if (PATTERNS.medical.test(clean)) {
                report.hazard = report.hazard || 'medical';
                report.urgency = 'high';
                report.injuries = clean;
                report.advice_given = report.advice_given || pick(ADVICE.medical, lang);
            } else if (PATTERNS.flood.test(clean)) {
                report.hazard = report.hazard || 'flood';
                report.urgency = 'high';
                report.advice_given = report.advice_given || pick(ADVICE.flood, lang);
            } else if (PATTERNS.earthquake.test(clean)) {
                report.hazard = report.hazard || 'earthquake';
                report.advice_given = report.advice_given || pick(ADVICE.earthquake, lang);
            }

            if (stage === 'location' || (!report.location && PATTERNS.location.test(clean))) {
                report.location = clean;
            }
            if (stage === 'details') {
                report.injuries = clean;
            }
            report.summary = report.summary ? `${report.summary} · ${clean}` : clean;

            const parts = [];
            if (report.advice_given && stage === 'what') parts.push(report.advice_given);

            if (!report.location) {
                stage = 'location';
                parts.push(pick(PHRASES.askLocation, lang));
            } else if (!report.injuries && stage !== 'details' && stage !== 'confirm') {
                stage = 'details';
                parts.push(pick(PHRASES.askDetails, lang));
            } else {
                stage = 'confirm';
                parts.push(pick(PHRASES.confirm, lang));
            }

            return {
                reply_text: parts.join(' '),
                lang,
                action: 'continue',
                handoff_reason: null,
                report: snapshot(),
            };
        },
        async end(reason = 'completed') {
            report.status = reason;
            return snapshot();
        },
    };
}

/* Creates a live Voice_Agents API session if reachable, otherwise falls back seamlessly to local triage. */
export async function createVoiceSession({lang = 'en', aml = null} = {}) {
    if (VOICE_API) {
        try {
            const stop = new AbortController();
            const timer = setTimeout(() => stop.abort(), 3500);
            const res = await fetch(new URL('start', VOICE_API), {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({lang, aml, channel: 'voice'}),
                signal: stop.signal,
            });
            clearTimeout(timer);
            if (res.ok) {
                const first = await res.json();
                const callId = first.call_id;
                return {
                    mode: 'live',
                    callId,
                    async start() {
                        return first;
                    },
                    async turn(text) {
                        const r = await fetch(new URL('turn', VOICE_API), {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({call_id: callId, text, lang}),
                        });
                        if (!r.ok) throw new Error(`voice-api turn: ${r.status}`);
                        return await r.json();
                    },
                    async end(reason = 'hung_up') {
                        const r = await fetch(new URL('end', VOICE_API), {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({call_id: callId, reason}),
                        });
                        return r.ok ? await r.json() : {call_id: callId, status: reason};
                    },
                };
            }
        } catch {
            // Live voice bridge not running (e.g. static GitHub Pages or offline phone): use local engine
        }
    }
    return createLocalSession({lang, aml});
}
