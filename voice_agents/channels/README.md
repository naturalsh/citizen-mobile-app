# Channels

Ways in to the brain other than the phone call. Each one is a thin wrapper around `start_call` / `turn` / `end_call`.

`messaging.py` is one small server with two Twilio webhooks, plus the failed-112-call trigger (below):

| Endpoint | Channel | Twilio setting |
|---|---|---|
| `POST /whatsapp` | WhatsApp | Sandbox settings → *When a message comes in* |
| `POST /sms` | SMS | Phone number → Messaging → *A message comes in* |
| `GET /call` | Browser test call | none: a signed link from `python -m voice.link` opens a new LiveKit room per click (voice/README.md) |
| every other path | The shared dashboard | none: `https://<tunnel-address>/?key=<key>` (`dashboard_proxy.py`, below) |

How it behaves:

- **Language** comes from the phone's country code first, then from the message itself (Greek letters → Greek, ğ/ş/ı → Turkish, French accents → French). See `brain/langs.py`.
- **One conversation per sender and channel.** It ends when the brain finishes or hands off, or after 30 minutes of silence (saved as `dropped`). The next message starts a new report.
- **One reply message per incoming message.** The "this is an automated assistant" greeting is joined to the first reply, which saves a message and stays under the sandbox's limit of 1 message every 3 seconds.
- **One list, not one question per message.** Each reply ends with a numbered list of every detail still missing (what happened, where, people, injuries, floor, name), so the person answers all of it at once; one reminder lists what is still missing, then the read-back asks for YES or a correction. A report takes two or three messages from the agent; a test before this took a dozen. See "By text" in `brain/README.md`.
- **SMS is kept short.** Greek or Turkish SMS holds only 70 characters per part and every part is billed, so SMS uses short versions of the greeting, handoff and advice (`greeting_sms`, `handoff_sms`, `"sms"` in `brain/advice/*.json`), and the list is one line ("1) Τι συνέβη. 2) Πού: …"). The first list is 3–4 SMS parts in Greek; a full report is about 6–8 parts, against 10–12 with one question per message (estimated from the text lengths, not measured on Twilio).
- **Voice notes and photos** can't be read yet; the brain asks the person to type instead.
- **Reports** go to `output/reports/` like voice calls, with `"source": "whatsapp_agent"` or `"sms_agent"`.

## Run it locally

```bash
.venv/bin/uvicorn channels.messaging:app --port 8000
```

Testing with simulated messages costs nothing on Twilio. Keep real WhatsApp/SMS for end-to-end checks and the demo: the free trial has only **100 WhatsApp + 100 SMS messages in total**.

## Connect it to real WhatsApp (Twilio sandbox)

1. **Twilio account.** Sign up at https://www.twilio.com/try-twilio (free trial, 30 days, no card).
2. **Join the sandbox.** In the Twilio Console go to *Messaging → Try it out → Send a WhatsApp message*. It shows a sandbox number and a code like `join something-word`. Send that code from your own WhatsApp to the sandbox number. Every phone that should talk to the bot has to do this, and again every 3 days.
3. **Make your laptop reachable from the internet with ngrok.** Twilio can't call `localhost`. The free ngrok plan (https://ngrok.com/pricing: 20,000 requests, 1 GB a month) gives every account one fixed address, so Twilio's settings are made once:
   - Sign up at https://dashboard.ngrok.com/signup, download ngrok for macOS from https://ngrok.com/download and move the `ngrok` file to `/usr/local/bin`.
   - Run `ngrok config add-authtoken <token>` once, with the token from *Your Authtoken* in the ngrok dashboard. It is stored in ngrok's own config, not in this repo.
   - Start the tunnel while the server runs. A free account gets one address, chosen by ngrok and ending in `.ngrok-free.dev`, and uses it on its own (naming another one fails with ERR_NGROK_313):
   ```bash
   ngrok http 8000
   ```
   The address is shown in the ngrok window and under *Domains* in the ngrok dashboard. It stays the same between restarts.
   Only the messaging server (port 8000) is reachable, and step 5 makes it refuse anything not signed by Twilio. The free plan shows browsers a warning page first; Twilio's requests are not browsers.
4. **Point the sandbox at the server.** On the sandbox page, open *Sandbox settings* and set **When a message comes in** to `https://<tunnel-address>/whatsapp`, method **POST**. Save.
5. **Turn on signature checking.** In `.env`, set `TWILIO_AUTH_TOKEN` (Auth Token from the Twilio Console home page) and `PUBLIC_BASE_URL=https://<tunnel-address>`. The server then rejects any request that doesn't really come from Twilio. Restart the server after changing `.env`.
6. **Message the sandbox number** from WhatsApp, e.g. "Σεισμός στη Σάμο, έπεσε το σπίτι".

## Connect it to real SMS

Same server, tunnel and `.env`. You also need a Twilio phone number that can send SMS to your phone:

1. In the Twilio Console, get a number with SMS capability (*Phone Numbers → Buy a number*; the trial covers one).
2. On that number's page, under *Messaging*, set **A message comes in** to `https://<tunnel-address>/sms`, method **POST**.
3. Text that number from a verified phone.

Trial limits for SMS: only up to 5 verified numbers, only within the country you signed up in, and every message starts with "Sent from your Twilio trial account". Greek and Turkish numbers usually need regulatory documents first, so a trial number may not be able to text Greek or Turkish phones; check before relying on it for the demo.

## Failed-112-call trigger (`trigger.py`)

When someone's call to 112 doesn't get through, we message them first instead of waiting for them to try again:

```
112 switch / phone network ──POST /112/call-failed──► brain starts a conversation ──► first SMS/WhatsApp sent via Twilio
person replies ──► /sms or /whatsapp ──► same conversation continues as usual
```

Only the phone network or the 112 call centre can know a call failed (busy, no answer, dropped), so in a real deployment *they* call this endpoint. For the demo, we call it ourselves:

```bash
curl -X POST http://localhost:8000/112/call-failed \
  -H "Content-Type: application/json" \
  -H "X-Trigger-Token: $TRIGGER_TOKEN" \
  -d '{"phone": "+306900000000", "reason": "busy", "channel": "sms"}'
```

| Field | Values |
|---|---|
| `phone` | `+<country><number>`, required |
| `reason` | `busy` (default), `no_answer`, `dropped`, `network` |
| `channel` | `sms` (default, works without mobile data) or `whatsapp` |
| `attempted_at`, `aml` | optional; `aml` (`{"lat", "lon", "accuracy_m"}`) goes straight into the report |
| `lang` | optional: `el`, `tr`, `en` or `fr`, when the person's language is known (a tourist with a Greek SIM). Without it the country code decides, so a +30 number gets Greek |

How it behaves:

- **Closed by default.** The endpoint refuses everything unless `TRIGGER_TOKEN` is set in `.env` and sent as `X-Trigger-Token`. Otherwise anyone could make us text strangers.
- **No spam.** It skips the number if a conversation with it is already open on any channel, or if we messaged it in the last 15 minutes, however many times 112 fails.
- **The first message** says the 112 call didn't get through, that this is the automated assistant, and asks where they are and what happened. Language comes from `lang` if given, else from the country code.
- **"I called by mistake" / "we're fine"** is recorded with urgency `information` and ends politely.
- **Reports** carry `"trigger": {"type": "failed_112_call", "reason": ..., "attempted_at": ...}`.
- **Dry run.** Without `TWILIO_ACCOUNT_SID` and a sender number (`TWILIO_SMS_FROM` or `TWILIO_WHATSAPP_FROM`), nothing is sent: the response shows the message that *would* have gone out. Good for testing without spending trial messages.

For WhatsApp in the sandbox, we can only send free text to a phone that messaged the sandbox in the last 24 hours (sending the `join` code counts). So for the demo, join with the demo phone shortly before.

## The shared dashboard at the same address (`dashboard_proxy.py`)

The free Cloudflare links to the shared dashboard changed every few hours, so this server's fixed ngrok address shows it too: every path that isn't one of the endpoints above is forwarded to the shared copy of the dashboard (`python -m dashboard --share`, port 8003). Send `https://<tunnel-address>/?key=<key>` with the key that `--share` prints (kept in `output/dashboard_share_key`).

- **The key is checked here too**, before anything is forwarded, so a dashboard without a key (the operator's own, on 8002) is never reachable from the internet. No key set anywhere: every request is refused.
- **Texting comes first.** The dashboard isn't running: the page says so (502) and texting goes on. `MESSAGING_DASHBOARD=off` turns the forwarding off; it points at `http://127.0.0.1:8003` by default.
- **ngrok's free allowance is shared** (20,000 requests and 1 GB a month, https://ngrok.com/pricing) with WhatsApp, SMS and call links. The page there asks for updates every 10 s instead of 2 s, compressed, and not while its tab is hidden: about 360 requests and 2 MB per hour of an open page, so roughly 55 hours a month. ngrok shows its own warning page once per browser before the dashboard; click *Visit Site*.

## Limits to mention in the pitch

- The WhatsApp sandbox only talks to phones that joined it. A real deployment needs a registered WhatsApp Business sender.
- WhatsApp needs mobile data, which often fails in a disaster, and new WhatsApp senders can only start a few hundred conversations a day. SMS works without data, so it is the better channel for the failed-112-call alert. A real rollout would send it through the mobile operators or 112's own SMS system.
- Twilio waits about 15 seconds for a reply. The brain usually answers in 1–3 s; the end-of-conversation summary runs after the reply is sent.
