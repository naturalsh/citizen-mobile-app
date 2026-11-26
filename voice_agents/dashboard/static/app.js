/* Operator dashboard page. Polls /api/state every 2 s (10 s over the internet); all report text is escaped before display.
   Every button says what it does, shows "Saving…" while it works, and confirms with a message
   (with Undo where it makes sense). */
"use strict";

const LEVELS = ["life_threat", "urgent", "needs_help", "information"];
const LABEL = { life_threat: "LIFE THREAT", urgent: "URGENT", needs_help: "NEEDS HELP", information: "INFO" };
// Waiting longer than this (seconds, unclaimed) marks the timer overdue. Demo targets, not a standard.
const TARGET_S = { life_threat: 120, urgent: 300, needs_help: 900 };
const HAZARD = { earthquake: "🏚️ Earthquake", fire: "🔥 Fire", flood: "🌊 Flood", storm: "🌪️ Storm", landslide: "⛰️ Landslide", other: "⚠️ Other" };
// What kind, per category (brain/report.py HAZARD_SUBTYPES).
const SUBTYPE = {
  earthquake: { collapse: "building collapse", damage: "damage" },
  fire: { wildfire: "wildfire", building: "building", vehicle: "vehicle", other: "other" },
  flood: { building: "water in a building", street: "street / area", vehicle: "vehicle in water", river: "river / flash flood" },
  storm: { wind: "wind damage", fallen_tree: "fallen tree", power_line: "power line down", lightning: "lightning" },
  other: { gas_leak: "gas leak", explosion: "explosion", road_accident: "road accident", other: "other" },
};
const hazardName = (i) => HAZARD[i.hazard]
  ? HAZARD[i.hazard] + (SUBTYPE[i.hazard]?.[i.hazard_subtype] ? ` · ${SUBTYPE[i.hazard][i.hazard_subtype]}` : "")
  : "❔ Hazard not known yet";
const SOURCE = { voice: "📞 Call", whatsapp: "💬 WhatsApp", sms: "✉️ SMS" };
const STATUS = { in_progress: "● On the line", complete: "✓ Call finished", handed_to_human: "↪ Handed to operator", dropped: "✕ Line dropped" };
const HANDOFF = {
  not_breathing: "not breathing", caller_request: "asked for a person", unsupported_language: "language not supported",
  out_of_scope: "not a disaster call", not_understood: "couldn't understand", low_confidence: "AI unsure",
  operator_paused: "AI paused", budget_limit: "AI request limit",
};
// Over the internet (the shared link through ngrok) every update counts against the free plan's monthly
// requests, so a page there asks every 10 s and not at all while its tab is hidden. The operator's own
// page (this computer or the local network) keeps 2 s and keeps polling hidden, for the alarm sound.
const LOCAL = /^(localhost|127\.|\[::1\]|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(location.hostname);
const POLL_MS = LOCAL ? 2000 : 10000, REPEAT_ALERT_MS = 15000, OLD_AFTER_S = 30 * 60, TOAST_MS = 6000;
// Zoom when an incident is selected (OSM zoom levels): addresses for phone GPS, small roads for an area.
// +0.25 of a level = 20% closer (2^0.25 ≈ 1.19), asked for after the first test calls.
const ZOOM = { aml: 17.25, building: 17.25, street: 16.5, openstreetmap: 15.25 };
// Blink and sound only for life-threats that are new (first call under 2 minutes ago) and unclaimed.
// Blinking every unclaimed one turns the screen into an alarm flood (ISA-18.2 / EEMUA 191, see README).
const NEW_FOR_S = 120;
const isNewAlert = (i) => i.level === "life_threat" && !i.claim && !i.resolved && (Date.now() - Date.parse(i.first_at)) / 1000 < NEW_FOR_S;

const ui = {
  data: null, selected: null, operator: localStorage.getItem("operator") || "",
  sound: false, audio: null, order: [], seen: new Set(), alerted: new Set(), lastAlert: 0,
  hoverQueue: false, hoverDetail: false, lastOk: 0, markers: new Map(), circles: new Map(), placedCount: 0, userMovedMap: false,
  openTranscripts: new Set(), flash: null, showResolved: false, showCanWait: false, noteDrafts: {},
  choiceMarkers: new Map(), showUnplaced: false,
  showOriginal: new Set(), // incidents shown in the caller's language instead of English
};
const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Shapes: ▲ life threat, ◆ urgent, ● needs help, ○ info. Never colour alone.
function shape(level, size = 13) {
  const colour = level ? `var(--${level})` : "var(--muted)";
  const solid = `style="fill:${colour};stroke:var(--surface);stroke-width:1.5"`;
  const body = {
    life_threat: `<polygon points="12,2 23,21 1,21" ${solid}/>`,
    urgent: `<polygon points="12,1 23,12 12,23 1,12" ${solid}/>`,
    needs_help: `<circle cx="12" cy="12" r="10" ${solid}/>`,
    information: `<circle cx="12" cy="12" r="8.5" style="fill:none;stroke:${colour};stroke-width:3"/>`,
  }[level] || `<rect x="4" y="4" width="16" height="16" rx="3" ${solid}/>`;
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true">${body}</svg>`;
}

function badge(level, confirmed) {
  const cls = level ? `lvl-${level}` : "lvl-none";
  const text = level ? LABEL[level] : "NOT ASSESSED";
  const how = confirmed ? "confirmed by an operator" : "suggested by the AI, not checked by an operator yet";
  return `<span class="badge ${cls} ${confirmed ? "solid" : "outline"}" title="${how}">${shape(level)}${text}</span>`;
}

function age(iso) {
  if (!iso) return "";
  const s = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}:${String(sec).padStart(2, "0")}`;
}
const clock = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "");
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const who = (name) => (name === ui.operator ? "you" : esc(name));
const Who = (name) => (name === ui.operator ? "You" : esc(name));
const flashing = (id) => ui.flash && Date.now() < ui.flash.until && ui.flash.ids.includes(id);

function peopleLine(p) {
  if (!p || !p.total) return "People: not known yet";
  const plus = (key) => ((p.plus || []).includes(key) ? "+" : ""); // "1+": at least, maybe more
  const parts = [`${p.total}${plus("total")} ${p.total === 1 && !plus("total") ? "person" : "people"}`];
  if (p.trapped) parts.push(`${p.trapped}${plus("trapped")} trapped`);
  if (p.injured) parts.push(`${p.injured} injured`);
  if (p.cannot_walk) parts.push(`${p.cannot_walk} can't walk`);
  if (p.unresponsive) parts.push(`${p.unresponsive} not breathing / unconscious`);
  if (p.dead) parts.push(`${p.dead} dead`);
  return parts.join(" · ");
}

// "In progress" but silent for a while usually means the line dropped without a proper ending.
function statusText(c) {
  if (c.status === "in_progress" && !c.live) return `⚠ No update for ${age(c.updated_at || c.created_at)} (line may have dropped)`;
  if (c.status === "handed_to_human" && HANDOFF[c.handoff_reason]) return `${STATUS.handed_to_human}: ${HANDOFF[c.handoff_reason]}`;
  return STATUS[c.status] || c.status;
}
const liveCalls = (incidents) => incidents.flatMap((i) => i.calls.filter((c) => c.live).map((c) => [i, c]));

const findIncident = (id) => (ui.data?.incidents || []).find((x) => x.id === id);
const findCall = (callId) => {
  for (const i of ui.data?.incidents || []) for (const c of i.calls) if (c.call_id === callId) return [i, c];
  return [null, null];
};
// A call counts as checked once an operator agreed or set its urgency (escalating alone doesn't).
const checked = (c) => c.confirmed;

/* ---------- server ---------- */

async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  if (res.status === 401) {
    // A shared copy whose key changed: say so, instead of empty transcripts and stale data.
    if (Date.now() - (ui.keyWarnedAt || 0) > 30000) { // the page polls every few seconds: once in a while is enough
      ui.keyWarnedAt = Date.now();
      toast("This shared dashboard's link has changed: open the new link (with its key) to see live data.");
    }
    throw new Error("the access key is no longer valid");
  }
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

async function poll() {
  if (!LOCAL && document.hidden) return;
  try {
    ui.data = await api("/api/state");
    ui.lastOk = Date.now();
    followSelectedCall();
    render();
    flyWhenLocated();
  } catch (err) {
    console.warn("dashboard update failed", err);
  }
  updateFreshness();
}

// A call becomes part of an event mid-call (e.g. once the caller says where they are), which
// changes its incident's id: keep the operator on it instead of dropping the selection.
function followSelectedCall() {
  if (!ui.selected?.startsWith("call:") || findIncident(ui.selected)) return;
  const callId = ui.selected.slice(5);
  const now = ui.data.incidents.find((i) => i.calls.some((c) => c.call_id === callId));
  if (!now) return;
  if (ui.noteDrafts[ui.selected]) ui.noteDrafts[now.id] = ui.noteDrafts[ui.selected];
  ui.selected = now.id;
  toast(now.area ? `📍 The caller said where they are: ${esc(now.area)}.` : "This call is now part of a bigger incident.");
}

// The selected incident gets a map position once the caller says where they are: go there.
function flyWhenLocated() {
  const i = findIncident(ui.selected), had = ui.selectedLocated;
  ui.selectedLocated = Boolean(i?.location);
  const m = i && ui.markers.get(i.id);
  if (had === false && m) map.flyTo(m.getLatLng(), ZOOM[i.location.source] || 15.25, { duration: 0.6 });
}

// Resolved incidents stay off the queue and the map unless asked for: a resolved one still on the
// map was confusing in a test (2026-10-24).
function visibleIncidents() {
  const hazard = $("hazard-filter").value, status = $("status-filter").value;
  const [kind, subtype] = hazard.split(".");
  const fits = (i) => !hazard || (hazard === "animals" ? i.animals
    : i.hazard === kind && (!subtype || i.hazard_subtype === subtype));
  return (ui.data?.incidents || []).filter((i) => fits(i)
    && (status === "all" || (status === "resolved") === Boolean(i.resolved)));
}

function showStatus(status) {
  if ($("status-filter").value !== status) { $("status-filter").value = status; render(); }
}

/* ---------- messages ---------- */

function toast(message, { kind = "ok", undo = null } = {}) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.setAttribute("role", kind === "error" ? "alert" : "status");
  el.innerHTML = `<span>${message}</span>`;
  if (undo) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = "Undo";
    b.addEventListener("click", async () => { b.disabled = true; el.remove(); await undo(); });
    el.appendChild(b);
  }
  $("toasts").appendChild(el);
  setTimeout(() => el.remove(), kind === "error" ? TOAST_MS * 2 : TOAST_MS);
}

// Run an action from a button: "Saving…" while it works, then a message, a flash on what changed, fresh data.
async function act(button, work, { done, undo, flash = [] } = {}) {
  if (!ui.operator) return showStart();
  const label = button?.innerHTML;
  if (button) { button.disabled = true; button.textContent = "Saving…"; }
  try {
    const result = await work();
    ui.flash = { ids: flash, until: Date.now() + 1600 };
    await poll();
    renderDetail(); // show the result even while the mouse is over the detail
    if (done) toast(typeof done === "function" ? done(result) : done, { undo: undo && (() => undo(result)) });
  } catch (err) {
    toast(`Not saved: ${esc(err.message)}`, { kind: "error" });
    if (button) { button.disabled = false; button.innerHTML = label; }
  }
}

// "Are you sure?" drawn inside the page. Native confirm() pop-ups can be blocked by the browser,
// and a blocked one silently counts as Cancel (found when the surge switch "did nothing").
function askConfirm(title, text, okLabel) {
  return new Promise((resolve) => {
    const box = document.createElement("div");
    box.className = "overlay";
    box.setAttribute("role", "alertdialog");
    box.setAttribute("aria-modal", "true");
    box.innerHTML = `<div class="overlay-box confirm-box"><h2>${esc(title)}</h2><p>${esc(text)}</p>
      <div class="row"><button type="button" class="primary" data-ok>${esc(okLabel)}</button><button type="button" data-cancel>Cancel</button></div></div>`;
    const done = (yes) => { box.remove(); document.removeEventListener("keydown", onKey, true); resolve(yes); };
    const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); done(false); } };
    box.addEventListener("click", (e) => {
      if (e.target.closest("[data-ok]")) done(true);
      else if (e.target.closest("[data-cancel]") || e.target === box) done(false);
    });
    document.addEventListener("keydown", onKey, true);
    document.body.appendChild(box);
    box.querySelector("[data-cancel]").focus(); // Enter alone never confirms a big change
  });
}

/* ---------- rendering ---------- */

function render() {
  const d = ui.data;
  $("demo-tag").classList.toggle("hidden", !d.demo);
  renderCounts(d.counts);
  renderBanner(d);
  renderQueue();
  renderMap();
  // Hold the detail still while the operator works in it (e.g. choosing a level in a dropdown).
  if (!ui.hoverDetail && !$("detail").contains(document.activeElement)) renderDetail();
  else liveCalls(ui.data.incidents).forEach(([, c]) => ui.openTranscripts.has(c.call_id) && loadTranscript(c.call_id));
  soundAlerts();
}

function renderCounts(c) {
  const live = `<button type="button" class="count live-count" data-jump="live" title="Calls and messages the AI is handling right now" ${c.live_calls ? "" : "disabled"}><span class="live-dot" aria-hidden="true"></span><b>${c.live_calls}</b><span>on the line</span></button>`;
  const parts = LEVELS.map((l) => `<button type="button" class="count lvl-${l}" data-jump="${l}" title="Go to the ${LABEL[l]} incidents in the queue">${shape(l, 16)}<b>${c.by_level[l]}</b><span>${LABEL[l]}</span></button>`);
  const n = c.unclaimed_life_threat;
  const anyNew = (ui.data.incidents || []).some(isNewAlert);
  parts.splice(1, 0, `<button type="button" class="count unclaimed ${anyNew ? "alert" : ""}" data-jump="unclaimed" title="Open the oldest life-threat nobody has taken yet" ${n ? "" : "disabled"}>${shape("life_threat", 16)}<b>${n}</b><span>not taken</span></button>`);
  parts.unshift(live);
  parts.push(`<button type="button" class="count resolved-count" data-jump="resolved" title="Show the incidents operators marked as resolved" ${c.resolved ? "" : "disabled"}><span aria-hidden="true">✓</span><b>${c.resolved}</b><span>resolved</span></button>`);
  $("counts").innerHTML = parts.join("");
  const u = ui.data.budget;
  $("ai-usage").textContent = `AI requests ${u.hour}/${u.max_per_hour} this hour`;
}

function renderBanner(d) {
  const b = $("banner");
  const pause = $("pause-btn");
  // act() greys a button out while it saves; these two are redrawn here, so switch them back on.
  pause.disabled = false;
  $("surge-btn").disabled = false;
  pause.setAttribute("aria-pressed", d.paused ? "true" : "false");
  pause.innerHTML = d.paused ? "▶ Resume AI" : "⏸ Pause AI";
  pause.title = d.paused ? "Let the AI answer overflow calls and messages again" : "Stop the AI: every new call and message goes straight to a human operator";
  const surge = d.handoff?.mode === "surge";
  const sb = $("surge-btn");
  sb.setAttribute("aria-pressed", surge ? "true" : "false");
  sb.innerHTML = surge ? "Surge mode: on" : "Surge mode: off";
  sb.title = surge
    ? `Only life-threats, crimes in progress and callers who insist get a person; the AI records the rest and ends the call.${d.handoff.by ? ` Set by ${d.handoff.by} at ${clock(d.handoff.at)}.` : " (Default.)"} Click to switch off.`
    : "Off: the AI hands anything outside a disaster call to a person. Click to switch on during a surge.";
  if (d.paused) {
    b.className = "banner paused";
    b.textContent = `AI PAUSED by ${d.paused.by || "an operator"}${d.paused.at ? " at " + clock(d.paused.at) : ""}: every new call and message goes straight to a human operator. Press "Resume AI" to switch it back on.`;
  } else if (d.budget.limit_on) {
    b.className = "banner limit";
    b.textContent = `AI REQUEST LIMIT REACHED (${d.budget.hour}/${d.budget.max_per_hour} this hour): callers are being handed to human operators.`;
  } else {
    b.className = "banner hidden";
  }
}

function displayOrder(incidents) {
  const ids = incidents.map((i) => i.id);
  if (!ui.hoverQueue || !ui.order.length) return (ui.order = ids);
  // Mouse over the list: keep the order still; new incidents go on top so they are still seen.
  const kept = ui.order.filter((id) => ids.includes(id));
  const added = ids.filter((id) => !kept.includes(id));
  return (ui.order = [...added, ...kept]);
}

function renderQueue() {
  const incidents = visibleIncidents();
  const byId = new Map(incidents.map((i) => [i.id, i]));
  $("queue-count").textContent = plural(incidents.length, "incident");
  if (!incidents.length) {
    $("queue").innerHTML = `<p class="muted empty">No incidents${ui.data.demo ? "" : " yet. They appear here as calls and messages come in"}.</p>`;
    return;
  }
  // One section per urgency level, so the top-bar counts can jump to it.
  const order = displayOrder(incidents);
  const open = order.filter((id) => !byId.get(id).resolved && byId.get(id).level !== "information");
  const canWait = order.filter((id) => !byId.get(id).resolved && byId.get(id).level === "information");
  const resolved = order.filter((id) => byId.get(id).resolved);
  const live = liveCalls(incidents);
  const livePanel = live.length ? `<h3 class="section live-section ${flashing("sec-live") ? "flash" : ""}" id="sec-live"><span class="live-dot" aria-hidden="true"></span> ON THE LINE NOW <span class="muted">· ${plural(live.length, "call")}</span></h3>
    <div class="live-list">${live.map(([i, c]) => `<button type="button" class="live-row" data-live-incident="${esc(i.id)}" data-live-call="${esc(c.call_id)}" title="Open it and follow the conversation">
      <span>${SOURCE[c.source] || ""} · ${esc((c.lang || "").toUpperCase())} · <span class="timer" data-since="${esc(c.created_at)}">⏱ ${age(c.created_at)}</span></span>
      <b>${esc(i.area || c.location.area || "Location not said yet")}</b>
      <span class="small muted">${esc((c.situation || "Listening… nothing reported yet").slice(0, 110))}</span>
      ${badge(c.level, c.confirmed)}</button>`).join("")}</div>` : "";
  const html = livePanel + [...LEVELS.slice(0, 3), null].map((level) => {
    const ids = open.filter((id) => (byId.get(id).level || null) === level);
    if (!ids.length) return "";
    const title = level ? `${shape(level, 14)} ${LABEL[level]}` : `${shape(null, 14)} NOT ASSESSED YET`;
    return `<h3 class="section lvl-${level || "none"} ${flashing(`sec-${level || "none"}`) ? "flash" : ""}" id="sec-${level || "none"}">${title} <span class="muted">· ${plural(ids.length, "incident")}</span></h3>${ids.map((id) => card(byId.get(id))).join("")}`;
  }).join("") + (canWait.length ? `
    <details class="collapsed-list" id="sec-information" ${ui.showCanWait ? "open" : ""}>
      <summary class="section lvl-information ${flashing("sec-information") ? "flash" : ""}">${shape("information", 14)} CAN WAIT <span class="muted">· ${plural(canWait.length, "incident")} · information only · click to ${ui.showCanWait ? "hide" : "show"}</span></summary>
      ${canWait.map((id) => card(byId.get(id))).join("")}
    </details>` : "") + (resolved.length ? `
    <details class="collapsed-list resolved-list" id="sec-resolved" ${ui.showResolved || $("status-filter").value === "resolved" ? "open" : ""}>
      <summary class="section ${flashing("sec-resolved") ? "flash" : ""}">✓ RESOLVED <span class="muted">· ${plural(resolved.length, "incident")} · click to ${ui.showResolved ? "hide" : "show"}</span></summary>
      ${resolved.map((id) => card(byId.get(id))).join("")}
    </details>` : "");
  $("queue").innerHTML = html;
  incidents.forEach((i) => ui.seen.add(i.id));
}

function card(i) {
  const fresh = ui.seen.size && !ui.seen.has(i.id);
  const flash = flashing(i.id);
  const done = i.calls.filter(checked).length;
  const tags = [
    ...i.priority_reasons.slice(0, 2).map((r) => `<span class="chip strong">${esc(r)}</span>`),
    ...[...new Set(i.calls.flatMap((c) => c.animal_tags))].slice(0, 2).map((t) => `<span class="chip" title="Animals at risk: never counted as people">${esc(t)}</span>`),
    i.live ? `<span class="tag live" title="The AI is talking or texting with this person now"><span class="live-dot" aria-hidden="true"></span> ON THE LINE</span>` : "",
    i.dropped_life_threat ? `<span class="tag callback">CALL BACK</span>` : "",
    i.calls.some((c) => c.location.on_map === false) ? `<span class="tag callback" title="The place the caller gave wasn't found on the map: maybe misheard">⚠ place not found</span>`
      : i.calls.some(streetNotFound) ? `<span class="tag callback" title="The street the caller gave doesn't exist in that area on OpenStreetMap: probably misheard. The pin is only the area.">⚠ street not found</span>`
      : !i.location && i.calls.some((c) => c.location.area || c.location.spoken_address || c.location.landmark)
        ? `<span class="tag callback" title="Not on the map: nothing the caller said was found. Check the place with the caller.">⚠ location unknown</span>`
      : ["area", "wider"].includes(i.location?.precision) ? `<span class="tag approx" title="Only an area is known: the pin is its centre, the outline or dashed circle shows where the caller may be">≈ approx. location</span>` : "",
    i.reopened ? `<span class="tag callback" title="A new call came in after it was marked resolved">NEW CALL</span>` : "",
    i.escalated ? `<span class="tag esc" title="An operator asked a supervisor to look at it">⚑ SUPERVISOR</span>` : "",
  ].join("");
  const take = i.resolved
    ? `<span>✓ Resolved by <b>${who(i.resolved.operator)}</b> ${clock(i.resolved.at)}</span>`
    : i.claim
    ? `<span>Taken by <b>${who(i.claim.operator)}</b>${i.call_count > 1 || done ? ` · ${done}/${i.call_count} checked` : ""}</span>`
    : `<span class="muted">Not taken</span><button type="button" class="take" data-take="${esc(i.id)}" title="Mark it as yours so other operators know you're handling it">Take</button>`;
  const people = i.priority_reasons.length ? "" : `<div class="card-people">${peopleLine(i.people)}</div>`;
  return `<article class="card lvl-${i.level || "none"} ${i.id === ui.selected ? "selected" : ""} ${i.claim ? "claimed" : ""} ${i.resolved ? "resolved" : ""} ${isNewAlert(i) ? "alert" : ""} ${fresh ? "fresh" : ""} ${flash ? "flash" : ""}"
      data-id="${esc(i.id)}" tabindex="0" aria-label="${esc((i.level ? LABEL[i.level] : "Not assessed") + ", " + (i.area || "unknown place") + ". Press Enter to open.")}">
    <div class="card-top">${badge(i.level, i.confirmed)}${tags}
      <span class="timer" data-since="${esc(i.first_at)}" data-level="${esc(i.level || "")}" data-open="${i.claim ? 0 : 1}" title="Waiting since the first call">⏱ ${age(i.first_at)}</span></div>
    <div class="card-title">${hazardName(i)} · ${esc(i.area || "location not said yet")}
      <span class="calls">${plural(i.call_count, "call")}${i.notes.length ? ` · 📝 ${i.notes.length}` : ""}</span></div>
    ${people}
    <div class="card-foot">${take}</div>
  </article>`;
}

/* ---------- jumping from the top-bar counts ---------- */

function jump(target) {
  if (target === "unclaimed") {
    const first = ui.order.map(findIncident).find((i) => i && i.level === "life_threat" && !i.claim && !i.resolved);
    if (!first) return toast("Every life-threat has been taken.");
    $("hazard-filter").value = "";
    showStatus("open");
    select(first.id);
    document.querySelector(`.card[data-id="${CSS.escape(first.id)}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  if (target === "resolved") { ui.showResolved = true; showStatus("resolved"); renderQueue(); }
  else if ($("status-filter").value === "resolved") showStatus("open");
  if (target === "live" && !$("sec-live") && $("hazard-filter").value) { $("hazard-filter").value = ""; render(); }
  if (target === "information") { ui.showCanWait = true; renderQueue(); }
  const section = $(`sec-${target}`);
  if (!section) {
    const filtered = $("hazard-filter").value;
    return toast(filtered ? `No ${LABEL[target]} incidents with the hazard filter "${esc(filtered)}". Set it to "All" to see every hazard.` : `No ${LABEL[target]} incidents right now.`);
  }
  ui.flash = { ids: [`sec-${target}`], until: Date.now() + 1600 }; // kept across the 2-second redraws
  section.classList.add("flash");
  section.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- map ---------- */

let map;
function initMap() {
  map = L.map("map", { zoomControl: true, zoomSnap: 0.25 }).setView([38.6, 25.8], 6); // Aegean: Greece and western Türkiye
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  // Once the operator zooms or drags, stop re-fitting the map to new incidents.
  map.on("dragstart", () => (ui.userMovedMap = true));
  map.getContainer().addEventListener("wheel", () => (ui.userMovedMap = true), { passive: true });
  map.getContainer().addEventListener("click", (e) => { if (e.target.closest(".leaflet-control-zoom")) ui.userMovedMap = true; });
  const Overview = L.Control.extend({
    onAdd() {
      const b = L.DomUtil.create("button", "map-overview");
      b.type = "button"; b.textContent = "⤢ Show all"; b.title = "Zoom out to every incident on the map";
      L.DomEvent.on(b, "click", (e) => { L.DomEvent.stop(e); fitAll(); });
      return b;
    },
  });
  new Overview({ position: "topright" }).addTo(map);
  // Incidents that couldn't be placed: listed in a corner so they never vanish from the map's view.
  const Unplaced = L.Control.extend({
    onAdd() {
      const box = L.DomUtil.create("div", "unplaced hidden");
      box.id = "unplaced";
      L.DomEvent.disableClickPropagation(box); // clicks here don't move the map, so handle them here
      L.DomEvent.on(box, "click", (e) => {
        const b = e.target.closest("button");
        if (b?.dataset.toggleUnplaced) { ui.showUnplaced = !ui.showUnplaced; renderMap(); }
        else if (b?.dataset.unplaced) select(b.dataset.unplaced);
      });
      return box;
    },
  });
  new Unplaced({ position: "bottomleft" }).addTo(map);
}

function fitAll() {
  const points = [...ui.markers.values()].map((m) => m.getLatLng());
  if (points.length) map.flyToBounds(L.latLngBounds(points).pad(0.2), { maxZoom: 11, duration: 0.6 });
}

function markerIcon(i) {
  const selected = i.id === ui.selected;
  const size = Math.round((22 + 4 * Math.min(i.call_count - 1, 5)) * (selected ? 1.45 : 1));
  const old = (Date.now() - Date.parse(i.last_at || i.first_at)) / 1000 > OLD_AFTER_S;
  const count = i.call_count > 1 ? `<text x="12" y="${i.level === "life_threat" ? 18 : 15.5}" text-anchor="middle" font-size="9" font-weight="700" fill="${i.level === "urgent" || i.level === "information" ? "#0b0b0b" : "#fff"}">${i.call_count}</text>` : "";
  const svg = shape(i.level, size).replace("</svg>", `${count}</svg>`);
  return L.divIcon({
    className: `marker ${old && !selected ? "old" : ""} ${selected ? "selected" : ""} ${i.resolved && !selected ? "resolved" : ""}`,
    html: `<span class="${isNewAlert(i) ? "pulse" : ""}">${svg}</span>${["area", "wider"].includes(i.location?.precision) ? '<b class="approx-mark" aria-hidden="true">≈</b>' : ""}`,
    iconSize: [size, size], iconAnchor: [size / 2, size / 2],
  });
}

function spread(placed) {
  // Incidents looked up to the same area share one point; fan them out a little so each is clickable.
  const groups = new Map();
  placed.forEach((i) => {
    const key = `${i.location.lat.toFixed(4)},${i.location.lon.toFixed(4)}`;
    groups.set(key, [...(groups.get(key) || []), i]);
  });
  const pos = new Map();
  groups.forEach((group) => group.forEach((i, n) => {
    if (group.length === 1) return pos.set(i.id, [i.location.lat, i.location.lon]);
    const angle = (2 * Math.PI * n) / group.length, r = 0.006; // about 600 m
    pos.set(i.id, [i.location.lat + r * Math.sin(angle), i.location.lon + r * Math.cos(angle) / Math.cos(i.location.lat * Math.PI / 180)]);
  }));
  return pos;
}

// How far "±" a position is: "±250 m", "±1.2 km".
const plusMinus = (m) => (m < 1000 ? `±${Math.round(m / 10) * 10} m` : `±${(m / 1000).toFixed(1)} km`);
const levelColour = (level) => getComputedStyle(document.documentElement).getPropertyValue(`--${level || "muted"}`).trim() || "#888";

// Where the caller may be, drawn as big as what is known so an area centre never looks like an
// exact address: the whole street when only the street is known (no house number), the
// neighbourhood's own outline from OpenStreetMap for an area, else a dashed circle (GPS accuracy,
// or an area without an outline).
function uncertaintyShape(loc) {
  if (loc.precision === "street" && loc.lines?.length) return { kind: "street", sig: `street:${JSON.stringify(loc.lines).length}:${loc.lat}` };
  if (["area", "wider"].includes(loc.precision) && loc.shape) return { kind: "outline", sig: `outline:${JSON.stringify(loc.shape).length}:${loc.lat}` };
  return { kind: "circle", sig: "circle" };
}

function drawUncertainty(i) {
  const loc = i.location, selected = i.id === ui.selected;
  const { kind, sig } = uncertaintyShape(loc);
  let c = ui.circles.get(i.id);
  if (c && c._sig !== sig) { c.remove(); c = null; }
  if (!c) {
    c = kind === "street" ? L.polyline(loc.lines, { interactive: false })
      : kind === "outline" ? L.geoJSON(loc.shape, { interactive: false })
      : L.circle([loc.lat, loc.lon], { interactive: false });
    c._sig = sig;
    c.addTo(map);
    ui.circles.set(i.id, c);
  }
  const colour = levelColour(i.level);
  if (kind === "circle") c.setLatLng([loc.lat, loc.lon]).setRadius(loc.radius_m || 1500);
  if (kind === "street") {
    // A thick line along the whole street: the caller is somewhere on it.
    c.setStyle({ color: colour, weight: selected ? 9 : 6, opacity: i.resolved ? 0.25 : selected ? 0.75 : 0.5, lineCap: "round" });
  } else {
    c.setStyle({
      color: colour, weight: selected ? 2 : 1.2, dashArray: "6 6", opacity: i.resolved ? 0.25 : selected ? 0.9 : 0.55,
      fillColor: colour, fillOpacity: i.resolved ? 0.02 : selected ? 0.12 : 0.05,
    });
  }
}

function renderUnplaced(unplaced) {
  const box = $("unplaced");
  if (!box) return;
  box.classList.toggle("hidden", !unplaced.length);
  box.innerHTML = unplaced.length ? `<button type="button" class="link unplaced-head" data-toggle-unplaced="1"
      aria-expanded="${ui.showUnplaced}">⚠ Not on the map · ${unplaced.length} ${ui.showUnplaced ? "▾" : "▸"}</button>${ui.showUnplaced ? unplaced.map((i) =>
    `<button type="button" class="link" data-unplaced="${esc(i.id)}">${shape(i.level, 11)} ${esc(i.area || i.calls[0]?.location.spoken_address || "location not said yet")}</button>`).join("") : ""}` : "";
}

// The brain searched the street inside the area and found nothing (misheard, or not on OpenStreetMap).
const streetNotFound = (c) => Array.isArray(c.location.street_matches) && c.location.street_matches.length === 0;

// One stretch of a street can cross neighbourhoods: "Neos Kosmos / Petralona".
const choiceName = (m) => [m.name, ...(m.also || [])].join(" / ");

function drawChoices(placed) {
  const keep = new Set();
  placed.filter((i) => (i.location.street_choices || []).length > 1).forEach((i) => {
    keep.add(i.id);
    let layer = ui.choiceMarkers.get(i.id);
    if (!layer) { layer = L.layerGroup().addTo(map); ui.choiceMarkers.set(i.id, layer); }
    layer.clearLayers();
    i.location.street_choices.forEach((m) => {
      if (m.lines?.length) L.polyline(m.lines, { interactive: false, color: levelColour(i.level), weight: 4, opacity: 0.45, dashArray: "4 6" }).addTo(layer);
      const icon = L.divIcon({ className: `choice-mark ${i.id === ui.selected ? "selected" : ""}`, html: "?", iconSize: [18, 18], iconAnchor: [9, 9] });
      L.marker([m.lat, m.lon], { icon, keyboard: false }).on("click", () => select(i.id))
        .bindTooltip(`Possible: ${esc(i.location.street || "street")}, ${esc(choiceName(m))} · ${esc(i.area || "")}`, { direction: "top" })
        .addTo(layer);
    });
  });
  for (const [id, layer] of ui.choiceMarkers) if (!keep.has(id)) { layer.remove(); ui.choiceMarkers.delete(id); }
}

function renderMap() {
  const incidents = visibleIncidents();
  const placed = incidents.filter((i) => i.location);
  const pos = spread(placed);
  const live = new Set(placed.map((i) => i.id));
  for (const [id, m] of ui.markers) if (!live.has(id)) { m.remove(); ui.markers.delete(id); }
  for (const [id, c] of ui.circles) if (!live.has(id)) { c.remove(); ui.circles.delete(id); }
  placed.forEach(drawUncertainty);
  drawChoices(placed);
  // Draw lower urgency first so life-threats sit on top; the selected one above everything.
  [...placed].reverse().forEach((i, z) => {
    const how = { gps: "phone GPS", house: "building", estimated: "estimated from house numbers nearby", street: "street", area: "approximate: area centre", wider: "approximate: wider place" }[i.location.precision] || "";
    const tip = `${i.resolved ? "RESOLVED · " : ""}${i.level ? LABEL[i.level] : "Not assessed"} · ${esc(i.area || "")} · ${plural(i.call_count, "call")} · ${how} ${plusMinus(i.location.radius_m || 1500)} · click to open`;
    let m = ui.markers.get(i.id);
    if (!m) {
      m = L.marker(pos.get(i.id), { keyboard: true, title: i.area || "" }).addTo(map);
      m.on("click", () => select(i.id));
      ui.markers.set(i.id, m);
    }
    m.setLatLng(pos.get(i.id)).setIcon(markerIcon(i)).setZIndexOffset(i.id === ui.selected ? 10000 : i.resolved ? -1000 : z * 10);
    m.unbindTooltip().bindTooltip(tip, { direction: "top", offset: [0, -10] });
  });
  if (!ui.userMovedMap && placed.length !== ui.placedCount && placed.length) {
    map.fitBounds(L.latLngBounds([...pos.values()]).pad(0.2), { maxZoom: 11 });
  }
  ui.placedCount = placed.length;
  renderUnplaced(incidents.filter((i) => !i.location && !i.resolved));
  const missing = incidents.length - placed.length;
  const geo = ui.data.geocoding;
  const notes = [];
  if (missing) notes.push(`${plural(missing, "incident")} not on the map yet`);
  if (geo.enabled && geo.pending) notes.push(`looking up ${plural(geo.pending, "place")} on OpenStreetMap…`);
  if (!geo.enabled) notes.push("OpenStreetMap lookups are off (DASHBOARD_GEOCODE)");
  notes.push(incidents.some((i) => i.location?.source === "aml")
    ? "positions: phone GPS where 112 passed it on, else the place the caller named (approximate)"
    : "positions: the street (no house number) or area the caller named, from OpenStreetMap; the highlighted street, the neighbourhood outline or the dashed circle shows where the caller may be");
  $("map-note").textContent = notes.join(" · ");
}

/* ---------- selecting ---------- */

function select(id) {
  ui.selected = id;
  ui.selectedLocated = Boolean(findIncident(id)?.location);
  findIncident(id)?.calls.forEach((c) => c.live && ui.openTranscripts.add(c.call_id)); // follow live calls
  renderQueue(); renderMap(); renderDetail();
  const i = findIncident(id), m = ui.markers.get(id);
  if (m && i?.location) {
    ui.userMovedMap = true; // keep the zoom; "Show all" goes back to the overview
    const circle = ui.circles.get(id);
    if ((["area", "wider"].includes(i.location.precision) || i.location.lines?.length) && circle) {
      map.flyToBounds(circle.getBounds().pad(0.1), { maxZoom: ZOOM[i.location.source] || 15.25, duration: 0.6 }); // the whole area or street it may be
    } else {
      map.flyTo(m.getLatLng(), ZOOM[i.location.source] || 15.25, { duration: 0.6 });
    }
  } else if (i) {
    toast(i.area ? `${esc(i.area)} isn't on the map yet.` : "Not on the map: the caller hasn't said where they are yet.");
  }
}

/* ---------- detail ---------- */

function renderDetail() {
  const i = findIncident(ui.selected);
  if (!i) {
    $("detail").innerHTML = `<div class="empty"><p><b>Select an incident</b> in the queue or on the map.</p>
      <ol class="howto small muted"><li><b>Take</b> it so others know you're on it.</li>
      <li><b>Check the urgency</b> of each call: agree with the AI or change it.</li>
      <li><b>Resolve</b> it when help is on the way or nothing more is needed.</li></ol></div>`;
    return;
  }
  const top = i.calls.find((c) => c.level === i.level) || i.calls[0];
  const loc = top.location;
  const where = (loc.spoken_address ? `📍 ${esc(loc.spoken_address)}${loc.confirmed_with_caller ? ' <span class="muted">✓ read back</span>' : ""}` : '<span class="muted">📍 Street not said yet</span>')
    + (i.calls.some((c) => c.location.on_map === false) ? ' <span class="tag callback" title="The place the caller gave was not found on OpenStreetMap: it may have been misheard. Check it with the caller.">⚠ not found on the map</span>' : "")
    + (i.calls.some(streetNotFound) ? ' <span class="tag callback" title="The street the caller gave doesn\'t exist in that area on OpenStreetMap: probably misheard. Check it with the caller.">⚠ street not found</span>' : "")
    + (i.calls.some((c) => !c.live && c.status !== "in_progress" && c.location.spoken_address && !c.location.confirmed_with_caller)
      ? ' <span class="tag callback" title="The caller never confirmed the location read back to them. Call back to check it.">⚠ location not confirmed</span>' : "")
    + (top.location.landmark ? `<div class="small muted">Caller said: «${esc(top.location.landmark)}»${top.location.map_suggestion ? ` · map: ${esc(top.location.map_suggestion)}` : ""}</div>` : "");
  const why = [
    ...i.priority_reasons.map((r) => `<span class="chip strong">${esc(r)}</span>`),
    ...(top.ai.reasons || []).slice(0, 2).map((r) => `<span class="chip">${esc(r)}</span>`),
  ].join("");
  const checkedBy = i.confirmed ? `<span class="muted small">✓ checked by an operator</span>`
    : top.ai.confidence != null ? `<span class="muted small">AI suggestion · ${Math.round(top.ai.confidence * 100)}% sure</span>` : "";
  $("detail").innerHTML = `
    <div class="detail-head lvl-${i.level || "none"} ${flashing(i.id) ? "flash" : ""}">
      <div class="row">${badge(i.level, i.confirmed)}${checkedBy}
        <span class="timer push" data-since="${esc(i.first_at)}" data-level="${esc(i.level || "")}" data-open="${i.claim ? 0 : 1}" title="Waiting since the first call">⏱ ${age(i.first_at)}</span></div>
      <h2>${hazardName(i)} · ${esc(i.area || "location not said yet")}</h2>
      <div class="where">${where} <span class="muted">· ${plural(i.call_count, "call")}${i.live ? ' · <span class="live-dot"></span> on the line' : ""}</span></div>
      <div class="map-line small ${["area", "wider"].includes(i.location?.precision) || !i.location ? "approx" : ""}">${mapLine(i)}</div>
      ${why ? `<div class="why">${why}</div>` : ""}
      ${nextStep(i)}
    </div>
    ${summaryBlock(i, top)}
    <h3 class="block-h">${plural(i.call_count, "call")}</h3>
    ${i.calls.map(callBox).join("")}
    ${notesBox(i)}
    ${closeZone(i)}`;
  ui.openTranscripts.forEach((id) => loadTranscript(id));
}

// English by default (summary and transcripts); one link shows the caller's own language.
const LANG_NAME = { el: "Ελληνικά", tr: "Türkçe", fr: "Français", en: "English" };
const originalLangs = (i) => [...new Set(i.calls.map((c) => c.lang).filter((l) => l && l !== "en"))];

function summaryBlock(i, top) {
  const langs = originalLangs(i);
  const original = ui.showOriginal.has(i.id);
  const text = original ? top.summary : top.summary_en || (top.lang === "en" ? top.summary : null);
  const missing = !original && !text && top.summary;
  const toggle = langs.length
    ? `<button type="button" class="link" data-original="${esc(i.id)}">${original ? "Show English" : `Show original (${langs.map((l) => LANG_NAME[l] || l).join(", ")})`}</button>` : "";
  const shown = missing ? `${esc(top.summary)} <span class="tag" title="Made before English copies existed">not translated</span>` : esc(text || "");
  if (!shown && !toggle) return "";
  return `<div class="lang-line small muted">${original ? "Original language" : "English"}${toggle ? " · " + toggle : ""}</div>
    ${shown ? `<p class="summary">${shown}</p>` : ""}`;
}

// What the pin on the map means, in one line.
function mapLine(i) {
  const loc = i.location;
  if (!loc) {
    if (!i.area) return "Map: not placed yet: no location said.";
    return `Map: not placed yet. "${esc(i.area)}" wasn't found on OpenStreetMap (maybe misheard); check the place with the caller.`;
  }
  const r = plusMinus(loc.radius_m || 1500);
  if (loc.precision === "gps") return `Map: phone GPS (${r}).`;
  if (loc.precision === "house") return `Map: the building, found by its house number on OpenStreetMap (${r}).`;
  if (loc.precision === "estimated") return `≈ Map: the house number isn't mapped; ${esc((loc.label || "").split("(").pop().replace(")", ""))} (${r}), inside the circle.`;
  if (loc.precision === "street") {
    return loc.lines?.length ? "Map: the whole street is highlighted: the house number isn't on OpenStreetMap, so the caller is somewhere along it."
      : `Map: the street (${r}; the house number isn't on OpenStreetMap).`;
  }
  const where = loc.shape ? "inside the outlined area" : "in the dashed circle";
  if (loc.precision === "wider") {
    return `≈ Map: "${esc(i.area || "")}" wasn't found, so this is the whole of ${esc(loc.matched || "the wider place")} (${r}). The caller is somewhere ${where}: ask for a street or a landmark.`;
  }
  if (loc.street_choices && loc.street_choices.length > 1) {
    const n = loc.street_choices.length;
    const named = loc.street_choices.slice(0, 3).map((m) => esc(choiceName(m)) + (m.km != null ? ` (${m.km} km out)` : "")).join("; ");
    return `≈ Map: "${esc(loc.street || "the street")}" exists in ${n} places in ${esc(i.area || "the area")}, closest first: ${named}${n > 3 ? `; ${n - 3} more farther out` : ""} (marked ? on the map). The agent asks which neighbourhood; until then only the centre of ${esc(i.area || "the area")} (${r}).`;
  }
  if (loc.street_choices && !loc.street_choices.length) {
    return `≈ Map: "${esc(loc.street || "the street")}" wasn't found in ${esc(i.area || "the area")} (maybe misheard), so only its centre (${r}).`;
  }
  if (loc.street_not_placed) {
    return `≈ Map: only the centre of ${esc(i.area || "the area")} (${r}). "${esc(loc.street_not_placed)}" isn't placed: ${esc(i.area || "the area")} is large and street names repeat, so the neighbourhood would pin it down.`;
  }
  return `≈ Map: only the centre of ${esc(i.area || "the area")} (${r}). The exact street or landmark wasn't found: the caller is somewhere ${where}.`;
}

// The one thing to do next, as the only filled button on screen (NHS / GOV.UK: one primary action).
function nextStep(i) {
  const unchecked = i.calls.filter((c) => !checked(c));
  const mine = i.claim && i.claim.operator === ui.operator;
  const giveBack = mine && !i.resolved ? `<button type="button" class="link" data-giveback="${esc(i.id)}" title="Put it back in the queue for someone else">Give back</button>` : "";
  let step, action = "";
  if (i.resolved) {
    step = `✓ Resolved by ${who(i.resolved.operator)} at ${clock(i.resolved.at)}`;
    action = `<button type="button" data-reopen="${esc(i.id)}" title="Put it back in the open queue">Reopen</button>`;
  } else if (!i.claim) {
    step = "Step 1 of 3 · Take it, so others know you're on it";
    action = `<button type="button" class="primary" data-take="${esc(i.id)}">Take incident</button>`;
  } else if (unchecked.length) {
    const c = unchecked[0];
    step = `Step 2 of 3 · Check urgency${i.call_count > 1 ? ` (${i.call_count - unchecked.length} of ${i.call_count} done)` : ""}${mine ? "" : ` · taken by ${who(i.claim.operator)}`}`;
    action = c.ai.level
      ? `<button type="button" class="primary" data-agree="${esc(c.call_id)}" title="Keep the AI's level for the ${clock(c.created_at)} call">✓ Agree: ${LABEL[c.ai.level]}</button><span class="muted small">or change it below</span>`
      : `<span class="muted small">No AI suggestion yet: set the level below.</span>`;
  } else {
    step = `Step 3 of 3 · Resolve when help is on the way${mine ? "" : ` · taken by ${who(i.claim.operator)}`}`;
    action = `<button type="button" class="primary" data-resolve="${esc(i.id)}" title="Move it to the Resolved list. A new call about it reopens it automatically.">✓ Mark resolved</button>`;
  }
  return `<div class="next"><div class="step small">${step}${i.reopened ? ' · <b>new call after it was resolved</b>' : ""}</div>
    <div class="row">${action}${giveBack}</div></div>`;
}

// Resolve set apart from routine buttons, at the bottom, when it isn't the next step yet.
function closeZone(i) {
  if (i.resolved || !i.claim || i.calls.every(checked)) return "";
  return `<div class="close-zone small muted">Done before every call is checked?
    <button type="button" data-resolve="${esc(i.id)}">✓ Mark resolved</button></div>`;
}

function notesBox(i) {
  const list = i.notes.length
    ? `<ul class="notes">${i.notes.map((n) => `<li><span class="muted small">${clock(n.at)} · ${who(n.operator)}</span> ${esc(n.text)}</li>`).join("")}</ul>`
    : "";
  return `<div class="notes-box"><h3 class="block-h">Notes${i.notes.length ? ` · ${i.notes.length}` : ""}</h3>${list}
    <div class="note-add"><textarea id="note-text" data-draft-for="${esc(i.id)}" rows="2" maxlength="300" placeholder="What was done, e.g. Fire crew 3 sent, 14:10" aria-label="New note">${esc(ui.noteDrafts[i.id] || "")}</textarea>
    <button type="button" data-note="${esc(i.id)}">Add note</button></div></div>`;
}

function callBackButton(c) {
  if (!c.caller.phone) return "";
  return `<a class="button" href="tel:${esc(c.caller.phone.replace(/\s/g, ""))}" data-callback="${esc(c.call_id)}" title="Call ${esc(c.caller.phone)} with this computer's phone app">📞 Call back</a>`;
}

function decisionLine(c) {
  const d = c.decision;
  if (!d) return `<span class="muted">Not checked yet</span>`;
  const lines = [];
  if (c.confirmed) {
    const agreed = c.level === c.ai.level;
    lines.push(agreed ? `✓ ${Who(d.operator)} agreed <span class="muted">${clock(d.at)}</span>`
      : `✎ Changed by ${who(d.operator)} <span class="muted">${clock(d.at)} · AI said ${c.ai.level ? LABEL[c.ai.level] : "nothing"}</span>`);
  }
  if (c.escalated) lines.push(`⚑ Supervisor asked <span class="muted">${clock(d.at)}</span>`);
  return lines.join(" · ");
}

// The quickest way to judge a call is to read it: one clear button in the call's top row (and T).
function transcriptButton(c, open) {
  return `<button type="button" class="transcript-btn" data-transcript="${esc(c.call_id)}" aria-expanded="${open}"
    title="${open ? "Hide" : "Read"} what was said (shortcut: T)">📄 ${open ? "Hide transcript" : c.live ? "Live transcript" : "Transcript"}</button>`;
}

function callBox(c) {
  const loc = c.location;
  const open = ui.openTranscripts.has(c.call_id);
  // Phone GPS (AML) only exists if 112 passes it on; normally we know only what the caller says.
  const gps = loc.aml && loc.aml.lat != null ? `<dt>Phone GPS</dt><dd>${loc.aml.lat.toFixed(4)}, ${loc.aml.lon.toFixed(4)} (±${loc.aml.accuracy_m ?? "?"} m)</dd>` : "";
  const options = LEVELS.map((l) => `<option value="${l}" ${l === c.level ? "selected" : ""}>${LABEL[l]}</option>`).join("");
  const dropped = c.status === "dropped" && c.level === "life_threat" ? `<span class="tag callback">Line dropped: call back</span>` : "";
  const advice = c.advice.length ? c.advice.map((a) => esc(a.title)).join("; ") : "none";
  const agree = !c.confirmed && c.ai.level
    ? `<button type="button" data-agree="${esc(c.call_id)}" title="Keep the AI's level and mark the call as checked">✓ Agree</button>` : "";
  const supervisor = c.escalated ? "" : `<button type="button" class="link" data-supervisor="${esc(c.call_id)}" title="Flag this call for a supervisor to look at">⚑ Ask supervisor</button>`;
  return `<div class="call lvl-${c.level || "none"} ${flashing(c.call_id) ? "flash" : ""}" id="call-${esc(c.call_id)}">
    <div class="row">${badge(c.level, c.confirmed)}<span class="small">${SOURCE[c.source] || esc(c.source)} · ${esc((c.lang || "").toUpperCase())} · ${clock(c.created_at)}</span>
      <span class="tag ${c.live ? "live" : ""}">${c.live ? '<span class="live-dot" aria-hidden="true"></span> On the line now' : esc(statusText(c))}</span>${c.trigger === "failed_112_call" ? '<span class="tag">after failed 112 call</span>' : ""}${dropped}
      <span class="push">${transcriptButton(c, open)} ${callBackButton(c)}</span></div>
    ${c.situation ? `<p class="situation">${esc(c.situation)}</p>` : '<p class="situation muted">Nothing reported yet.</p>'}
    <div class="decide"><span class="small">${decisionLine(c)}</span>
      ${agree}
      <select aria-label="Set the urgency of the ${clock(c.created_at)} call" data-level-for="${esc(c.call_id)}">${options}</select>
      <button type="button" data-apply="${esc(c.call_id)}" title="Save the level picked in the list">Set level</button>
      ${supervisor}</div>
    <button type="button" class="link" data-transcript="${esc(c.call_id)}" aria-expanded="${open}">${open ? "▾ Hide" : "▸ Show"} details and ${c.live ? "live conversation" : "what was said"}</button>
    <div class="${open ? "" : "hidden"}">
      <dl class="kv small">
        <dt>Caller</dt><dd>${esc(c.caller.name || "name not given")}${c.caller.phone ? ` · ${esc(c.caller.phone)}` : ""}</dd>
        <dt>Address</dt><dd>${esc(loc.spoken_address || "not said yet")}${loc.confirmed_with_caller ? " ✓ read back" : ""}</dd>
        <dt>Area</dt><dd>${esc(loc.area || "not said yet")}</dd>
        ${loc.landmark ? `<dt>Landmark</dt><dd>«${esc(loc.landmark)}» (as heard)${loc.map_suggestion ? `<br>Map: ${esc(loc.map_suggestion)}` : ""}</dd>` : ""}
        ${gps}
        <dt>People</dt><dd>${c.people_tags.length ? c.people_tags.map(esc).join("<br>") : peopleLine(c.people)}</dd>
        ${c.animal_tags.length ? `<dt>Animals</dt><dd>${c.animal_tags.map(esc).join("<br>")}</dd>` : ""}
        <dt>Advice given</dt><dd>${advice}</dd>
        <dt>AI reasons</dt><dd>${(c.ai.reasons || []).map(esc).join("; ") || "none yet"}</dd>
      </dl>
      <div class="transcript ${c.live ? "live" : ""}" id="t-${esc(c.call_id)}"></div>
    </div>
  </div>`;
}

async function loadTranscript(callId) {
  const el = document.getElementById(`t-${callId}`);
  if (!el) return;
  try {
    const t = await api(`/api/calls/${encodeURIComponent(callId)}/transcript`);
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
    const [incident] = findCall(callId);
    const original = incident && ui.showOriginal.has(incident.id);
    el.innerHTML = t.lines.map((l) => {
      const english = !original && l.text_en;
      const note = !original && !l.text_en && l.lang !== "en" ? ' <span class="tag" title="No English copy for this line">not translated</span>' : "";
      return `<p><span class="who">${l.role === "caller" ? "Caller" : "Agent"} ${clock(l.at)}</span>${esc(english || l.text)}${note}</p>`;
    }).join("");
    if (el.classList.contains("live") && atBottom) el.scrollTop = el.scrollHeight; // follow the conversation
  } catch {
    el.innerHTML = '<p class="muted">No transcript saved for this call.</p>';
  }
}

/* ---------- actions ---------- */

const callTime = (callId) => clock(findCall(callId)[1]?.created_at);

async function resolveIncident(button, id) {
  const i = findIncident(id);
  const unchecked = i.calls.filter((c) => !checked(c)).length;
  if (unchecked && !await askConfirm("Mark it resolved anyway?",
    `${plural(unchecked, "call")} in this incident ${unchecked === 1 ? "has" : "have"} no checked urgency yet.`, "✓ Mark resolved")) return;
  act(button, () => api("/api/resolve", { incident_id: id, operator: ui.operator }), {
    done: `✓ Resolved: ${esc(i.area || "the incident")} is off the queue and the map (Show → Resolved to see it).`, flash: [id],
    undo: () => act(null, () => api("/api/resolve", { incident_id: id, operator: ui.operator, resolved: false }), { done: "Reopened.", flash: [id] }),
  });
}

function addNote(button, id) {
  const text = $("note-text").value.trim();
  if (!text) { $("note-text").focus(); return toast("Write the note first.", { kind: "error" }); }
  act(button, () => api("/api/notes", { incident_id: id, operator: ui.operator, text }).then((note) => { delete ui.noteDrafts[id]; return note; }), {
    done: "📝 Note saved.", flash: [id],
    undo: (note) => act(null, () => api("/api/notes/undo", { note_id: note.id, operator: ui.operator }), { done: "Note removed.", flash: [id] }),
  });
}

function take(button, id) {
  const i = findIncident(id);
  act(button, () => api("/api/claims", { incident_id: id, operator: ui.operator }), {
    done: `✓ You took the incident in ${esc(i?.area || "this place")}.`, flash: [id],
    undo: () => act(null, () => api("/api/claims", { incident_id: id, operator: ui.operator, claim: false }), { done: "Given back to the queue." }),
  });
}

function decide(button, callId, action, level) {
  const [incident] = findCall(callId);
  const ids = [callId, incident?.id].filter(Boolean);
  const what = { confirm: () => `✓ You agreed: ${LABEL[level]}`, change: () => `✎ You changed it to ${LABEL[level]}`, escalate: () => "⚑ Supervisor asked" }[action]();
  act(button, () => api("/api/decisions", { call_id: callId, action, level: action === "change" ? level : null, operator: ui.operator }), {
    done: `${what} for the ${callTime(callId)} call.`, flash: ids,
    undo: () => act(null, () => api("/api/decisions/undo", { call_id: callId, operator: ui.operator }), { done: "Undone: back to the previous level.", flash: ids }),
  });
}

document.addEventListener("click", (e) => {
  const t = e.target.closest("button, article.card");
  if (!t || t.disabled) return;
  const d = t.dataset;
  if (d.jump) return jump(d.jump);
  if (d.take) { e.stopPropagation(); return take(t, d.take); }
  if (d.liveCall) {
    ui.openTranscripts.add(d.liveCall);
    select(d.liveIncident);
    return document.getElementById(`call-${CSS.escape(d.liveCall)}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  if (d.giveback) {
    return act(t, () => api("/api/claims", { incident_id: d.giveback, operator: ui.operator, claim: false }), { done: "Given back to the queue.", flash: [d.giveback] });
  }
  if (d.agree) return decide(t, d.agree, "confirm", findCall(d.agree)[1]?.ai.level);
  if (d.apply) return decide(t, d.apply, "change", document.querySelector(`[data-level-for="${CSS.escape(d.apply)}"]`).value);
  if (d.supervisor) return decide(t, d.supervisor, "escalate", null);
  if (d.resolve) return resolveIncident(t, d.resolve);
  if (d.reopen) {
    return act(t, () => api("/api/resolve", { incident_id: d.reopen, operator: ui.operator, resolved: false }), { done: "Reopened: back in the open queue.", flash: [d.reopen] });
  }
  if (d.note) return addNote(t, d.note);
  if (d.original) {
    ui.showOriginal.has(d.original) ? ui.showOriginal.delete(d.original) : ui.showOriginal.add(d.original);
    return renderDetail();
  }
  if (d.transcript) {
    ui.openTranscripts.has(d.transcript) ? ui.openTranscripts.delete(d.transcript) : ui.openTranscripts.add(d.transcript);
    return renderDetail();
  }
  if (t.matches("article.card")) select(d.id);
});
document.addEventListener("click", (e) => {
  const link = e.target.closest("a[data-callback]");
  if (link) toast(`📞 Calling ${esc(findCall(link.dataset.callback)[1]?.caller.phone || "")}. Add a note with what you learned.`);
  const summary = e.target.closest(".collapsed-list > summary");
  if (summary) {
    e.preventDefault();
    if (summary.parentElement.id === "sec-resolved") ui.showResolved = !ui.showResolved;
    else ui.showCanWait = !ui.showCanWait;
    renderQueue();
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.matches("article.card")) select(e.target.dataset.id);
  // T: open or close every transcript of the selected incident (not while typing a note or a name).
  if (e.key.toLowerCase() === "t" && !e.metaKey && !e.ctrlKey && !e.altKey && !e.target.matches("input, textarea, select")) {
    const calls = findIncident(ui.selected)?.calls || [];
    if (!calls.length) return;
    const open = calls.some((c) => ui.openTranscripts.has(c.call_id));
    calls.forEach((c) => (open ? ui.openTranscripts.delete(c.call_id) : ui.openTranscripts.add(c.call_id)));
    renderDetail();
    if (!open) document.getElementById(`t-${calls[0].call_id}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
});

$("pause-btn").addEventListener("click", async (e) => {
  const button = e.currentTarget;
  const pausing = !ui.data?.paused;
  const ok = pausing
    ? await askConfirm("Pause the AI?", "Every new call and message goes straight to a human operator until you press Resume.", "⏸ Pause AI")
    : await askConfirm("Resume the AI?", "It will answer overflow calls and messages again.", "▶ Resume AI");
  if (!ok) return;
  act(button, () => api("/api/pause", { paused: pausing, operator: ui.operator }), {
    done: pausing ? "⏸ AI paused: new calls go straight to human operators." : "▶ AI resumed.",
  });
});
$("surge-btn").addEventListener("click", async (e) => {
  const button = e.currentTarget;
  const on = ui.data?.handoff?.mode !== "surge";
  const ok = on
    ? await askConfirm("Switch surge mode on?", "Only people in danger, crimes in progress and callers who insist are handed to a person. The AI records everything else (e.g. a cat in a tree) as low priority and ends the call.", "Switch on")
    : await askConfirm("Switch surge mode off?", "The AI will hand anything that isn't a disaster call, and anyone who asks once, to a person.", "Switch off");
  if (!ok) return;
  act(button, () => api("/api/handoff-mode", { mode: on ? "surge" : "normal", operator: ui.operator }), {
    done: on ? "Surge mode on: only urgent calls go to a person." : "Surge mode off: the AI hands off more readily.",
  });
});
$("queue").addEventListener("mouseenter", () => (ui.hoverQueue = true));
$("queue").addEventListener("mouseleave", () => { ui.hoverQueue = false; if (ui.data) renderQueue(); });
$("detail").addEventListener("mouseenter", () => (ui.hoverDetail = true));
// Leaving with the mouse while typing in the panel must not redraw it under the operator.
$("detail").addEventListener("mouseleave", () => { ui.hoverDetail = false; if (ui.data && !$("detail").contains(document.activeElement)) renderDetail(); });
document.addEventListener("input", (e) => { if (e.target.id === "note-text") ui.noteDrafts[e.target.dataset.draftFor] = e.target.value; });
$("hazard-filter").addEventListener("change", () => ui.data && render());
$("status-filter").addEventListener("change", () => ui.data && render());

/* ---------- shift, sound, theme ---------- */

function showStart() {
  $("operator-name").value = ui.operator;
  $("start").classList.remove("hidden");
  $("operator-name").focus();
}
$("start-form").addEventListener("submit", (e) => {
  e.preventDefault();
  ui.operator = $("operator-name").value.trim().slice(0, 40);
  localStorage.setItem("operator", ui.operator);
  setSound($("start-sound").checked); // this click lets the browser play sound
  $("start").classList.add("hidden");
  $("operator-btn").textContent = `👤 ${ui.operator}`;
  toast(`Shift started as ${esc(ui.operator)}.`);
});
$("operator-btn").addEventListener("click", showStart);

function setSound(on) {
  ui.sound = on;
  if (on && !ui.audio) ui.audio = new (window.AudioContext || window.webkitAudioContext)();
  $("sound-btn").textContent = on ? "🔔 Alerts on" : "🔕 Alerts off";
  $("sound-btn").title = on ? "A sound plays for new life-threats nobody has taken. Click to mute." : "Click to hear a sound for new life-threats nobody has taken.";
  $("sound-btn").setAttribute("aria-pressed", on ? "true" : "false");
}
$("sound-btn").addEventListener("click", () => { setSound(!ui.sound); toast(ui.sound ? "🔔 Alert sound on." : "🔕 Alert sound off."); });

function beep() {
  // Two falling tones: distinct from phone ringtones, short enough not to mask speech.
  const a = ui.audio; if (!a) return;
  [[880, 0], [660, 0.18]].forEach(([freq, at]) => {
    const o = a.createOscillator(), g = a.createGain();
    o.frequency.value = freq; o.connect(g); g.connect(a.destination);
    g.gain.setValueAtTime(0.0001, a.currentTime + at);
    g.gain.exponentialRampToValueAtTime(0.25, a.currentTime + at + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, a.currentTime + at + 0.16);
    o.start(a.currentTime + at); o.stop(a.currentTime + at + 0.17);
  });
}

function soundAlerts() {
  // Only new life-threats nobody has taken: sound at once, then every 15 s while one is still new and untaken.
  const fresh = (ui.data.incidents || []).filter(isNewAlert).map((i) => i.id);
  const isNew = fresh.some((id) => !ui.alerted.has(id));
  fresh.forEach((id) => ui.alerted.add(id));
  if (!ui.sound || !fresh.length) return;
  if (isNew || Date.now() - ui.lastAlert > REPEAT_ALERT_MS) { beep(); ui.lastAlert = Date.now(); }
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("theme", theme);
  $("theme-btn").textContent = theme === "dark" ? "☀ Light" : "☾ Dark";
  $("theme-btn").title = `Switch to the ${theme === "dark" ? "light" : "dark"} theme`;
}
$("theme-btn").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));

/* ---------- timers ---------- */

function updateFreshness() {
  const s = ui.lastOk ? Math.round((Date.now() - ui.lastOk) / 1000) : null;
  const live = s != null && s <= POLL_MS / 1000 + 2; // one missed update is not yet "stale"
  const f = $("freshness");
  f.textContent = s == null ? "connecting…" : live ? "Live" : `No update for ${s}s`;
  f.className = `freshness small ${live ? "live" : "stale"}`;
}

function tick() {
  document.querySelectorAll(".timer[data-since]").forEach((el) => {
    el.textContent = `⏱ ${age(el.dataset.since)}`;
    const target = TARGET_S[el.dataset.level];
    const waited = (Date.now() - Date.parse(el.dataset.since)) / 1000;
    el.classList.toggle("overdue", el.dataset.open === "1" && target && waited > target);
  });
  updateFreshness();
}

/* ---------- start ---------- */

setTheme(localStorage.getItem("theme") || "dark");
initMap();
if (ui.operator) { $("start").classList.add("hidden"); $("operator-btn").textContent = `👤 ${ui.operator}`; }
else showStart();
poll();
setInterval(poll, POLL_MS);
document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); }); // fresh at once when shown
setInterval(tick, 1000);
