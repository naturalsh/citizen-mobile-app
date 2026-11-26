# The citizen app ("Safe places")

A page for the phone. It shows the nearest assembly points and hospitals of an area and a walking route to each,
and says for every street what is known about it: a person checked it, only the drone saw it, it is reported
blocked, or nothing is known. For every place it says what the operations room reported about it: in use, full,
closed, or nothing yet.

It is a **prototype** made for the Greece × Türkiye hackathon by team Nature Shield. It is not an official service,
and the one area it covers (Antakya – Defne, Hatay) is shown as an **exercise**: the streets are as a drone saw them
on 9 February 2023. The page says so in a banner that cannot be closed.

## How to open it

| Where | Command | Address |
|---|---|---|
| On the computer that runs the service | `python -m drone_vision serve` | `http://127.0.0.1:8000/app/` |
| On a phone, through the shared link | `python -m drone_vision share` | `https://<the name the command prints>.trycloudflare.com/app/` |

`share` prints two addresses: the link for the team, which carries the access key, and the citizens' page, which
needs none. The citizen addresses (`/app/` and `/public/`) open **without** the key and only read. Everything else
(the operator screen, the checks, the notice to citizens, the reports on places, the model) still needs it. To put the app on the home screen: in Safari "Share →
Add to Home Screen", in Chrome "Install app" or "Add to Home screen".

The first time an area is used, its walking streets are downloaded from OpenStreetMap once:

```
python -m drone_vision area-pack defne
```

Until then the service answers 409 for that area and names this command.

## How the parts fit together

```
drone map ──> road model + width rule ──> RoadStatus per street ──> operator confirms or corrects
                                                                          │
   drone_vision/areas/defne.json (places, exercise text, notice) ─────────┤
   a notice the operators send (/operator/notice) ────────────────────────┤
   what the operators report about a place (/operator/places) ────────────┤
   OpenStreetMap (every street one can walk) ─────────────────────────────┤
                                                                          ▼
                                             the AREA PACK: one public file per area
                                             GET /public/areas/defne/pack.json
                                                                          │   the same file for everybody
                                                                          ▼
                                             the phone: map, nearest places, walking route
                                             (worked out on the phone; nothing is sent back)
```

The service never learns where anybody stands. A phone downloads the whole area and finds the route itself.

| Piece | What it does |
|---|---|
| `drone_vision/public_pack.py` | Builds the pack and applies the two rules below before anything leaves |
| `contracts.py` (`AreaPack`, `Street`, `Place`, `PlaceReport`, `Notice`) | What a pack may hold. A field that is not listed is refused. The same as `schema/area_pack.schema.json` |
| `drone_vision/areas/<id>.json` | What we write by hand about an area: its name, its box, the places with their sources, the name its operators speak under |
| `drone_vision/service.py` | Hands out the pack, its revision and the app, with the headers listed under "Security"; takes the operators' notice and their reports on places |
| `drone_vision/notice_page.html` | The operators' page for a notice to every phone of an area |
| `drone_vision/places_page.html` | The operators' page for reporting that a place is in use, full or closed |
| `citizen_app/route.js` | The walking route, from the pack alone |
| `citizen_app/map.js` | The map, drawn from the pack. No map tiles are downloaded |
| `citizen_app/sheet.js`, `app.js`, `i18n.js` | The panel, the page as a whole, the words in English, Turkish and Greek |
| `citizen_app/app.css` | How the page looks, and how it lies on the screen of a phone held upright or sideways and on a wide screen |
| `citizen_app/vendor/framework7.min.css`, `vendor/ionicons/` | What the look is built on: Framework7's stylesheet, without its script, and thirteen of Ionicons' drawings (see "The look") |
| `citizen_app/store.js`, `sw.js` | What the phone keeps so that the app opens without a network |

The pack of Defne today: 7,166 pieces of street (91 of them inside the drone flight), 12 assembly points, 3 hospitals
and 2 health centres. It is 1.6 MB, 250 KB on the wire. The app itself is 31 files, 1.3 MB, 410 KB on the wire.

## The two rules that protect people

Both are applied in the service, in `public_pack.py`, because the pack is public.

**1. A street is called passable only after a person confirmed it.**

| What the system knows | What a citizen is told | Cost of a metre on foot |
|---|---|---|
| An operator confirmed: open, or narrow | Confirmed passable | × 1 |
| The model found it passable, nobody looked | Not confirmed yet | × 1.3 |
| Outside the drone flight, or the model could not judge | No information | × 1.8 |
| The model found it blocked | Reported blocked, at once | × 8 |
| An operator confirmed the blockage | Reported blocked, confirmed | × 40 |

A false alarm costs a detour. A blockage that is missed can cost much more. So "blocked" needs no confirmation and
"open" always does. The phone applies the rule a second time (`group()` in `route.js`): an "open" without a
confirmation counts as not confirmed, and a word it does not know counts as blocked.

A blocked street is never forbidden. Somebody whose only way out goes over it still gets a route, with a warning in
red: "Go only if you can see that you can pass. If not, stay on open ground away from buildings and call 112."
The factors and the walking speed (1 m/s, slow on purpose) are our choice, not a standard. They are in one place,
at the top of `route.js`.

**2. Nothing about people leaves.** No operator name, no operator note, no position. The contract refuses any field
it does not list, so a new field of `RoadStatus` cannot slip into the pack by accident.

Every place carries its source and the day it was compared. The 12 assembly points come from AFAD Hatay's list of
20 July 2022 as printed in Öcal & Yıldız (2023, CC BY-NC 4.0), compared with AFAD's public service on
12 November 2026. Nobody from the team has been there. The hospitals come from OpenStreetMap and are marked "Not
from an official list". A real service needs the authority's own current list, with its permission.

## What the phone does

- **Position.** Three ways: the phone's GPS (asked only when the person presses "Use my location"), a tap on the
  map, or an example position for a demonstration. Farther than 250 m from every street the app does not guess.
  Outside the area it says how far away the person is.
- **Places.** Two lists: assembly points, hospitals. Each is ordered by the walking route to the place, the least
  costly by the table above first, never by the straight line. Hospitals with an emergency department come ahead.
  A place that the operators reported full or closed goes to the end of its list and is never the one suggested
  (see "A report on a place").
- **Route.** The least costly way by the table above, with turn-by-turn steps, the metres of each kind of street,
  and one sentence that says what the person should watch for.
- **112** is one press away on every screen.
- **Languages.** English, Turkish, Greek, all in `citizen_app/i18n.js`. The Turkish text has not been read by a
  Turkish speaker yet, and the Greek text not by a Greek speaker.
- **Without a map.** A phone that cannot draw the map still shows the lists and the steps.

## The screen of a phone

- **Held upright**, the map is above and the panel below it. The panel takes at most 58% of the page's height and
  scrolls inside it, and it leaves the map at least 180 px (a third of the page's height where that is less). One
  press on the panel's first line folds the panel down to that line, and the map takes the rest.
- **Held sideways, or on a wide screen**, the panel stands beside the map and cannot be folded: on a screen held
  sideways that is at least 560 px wide, and on any screen at least 900 px wide. `app.js` and `app.css` ask the
  browser about this in the same words, and a test fails when they differ. When a turn changes the arrangement,
  the map shows the whole way again.
- **Narrower than 480 px**, the language chooser is a round button with a globe, and the language's name is not
  written beside it. The list that it opens is the same.
- **What a finger presses** is at least 44 px high and wide, the banner and the map's two zoom buttons too. Three
  things are smaller: the ✕ of a street's box on the map (34 px), the pin (26 px; it is moved by dragging, or by a
  tap on the map) and the map's credit button (24 px). The page asks the phone not to zoom on two quick taps, and
  not to select the words of a button under a finger that rests on it.
- **A notch, round corners and the bar at the bottom of the screen.** Text and buttons move in by as much as the
  phone says is covered (`env(safe-area-inset-…)`). The map and the backgrounds of the strips still reach the edge.
- **Tight cases, left as they are.** On an iPhone SE (375 × 667 px, of which Safari leaves the page 549) a long
  notice together with the strip that says the information is old leaves the panel about 90 px, while the map
  keeps its 180 px. A phone held sideways that is narrower than 560 px keeps the upright arrangement, with a map
  of about 110 px: turned upright it has room. On a small map the label of the drone flight can cover the name of
  the chosen place.

## The look

The look is built on two other projects. Both are stored in `citizen_app/vendor/` (its `README.md` has the
addresses, the checksums and the licences), so the app still loads nothing from another server.

- **Framework7 9.3.0, its stylesheet only.** It draws the buttons, the lists, the white blocks and the switch
  between the two lists the way an iPhone's own apps draw them. Its script is not used: the app stays plain
  modules without a build step, and the service's rule for a citizen's page (no style and no script written into
  the page) stays as it was. What the script would have done is written out by hand: `index.html` names the
  look, and section 1 of `app.css` gives the colours of the theme and says how a pressed button looks. One rule
  was taken out of the library's stylesheet, the font it carries inside itself, which the service refuses;
  `vendor/README.md` has the command that makes the stored file from the published one.
- **The look of an iPhone on every phone.** Framework7 has a second look, for Android. It is not used: an
  Android phone shows the same screen as an iPhone. The second look was not tried.
- **Ionicons 8.1.0 for the icons**: thirteen outline drawings. The stylesheet uses each as a stencil over the
  colour of the words beside it, so a drawing has no colour of its own. The signs of the places (assembly point,
  hospital, health centre) are still the app's own, drawn by `map.js`, the same on the map and in the lists.
- **Colours.** One blue (`#0066cc`) for what can be pressed, for the way on the map and for the mark of the
  person. Green, amber, grey and red say what is known about a street, in the panel as on the map; red is also
  the 112 button and a place reported full or closed. The banner of the exercise is violet (`#4a2a7a`), and the
  browser is told the same colour for its own bar. `tests/test_citizen_app.py` fails when the stylesheet, the
  map and the manifest name different colours.
- **Letters.** The phone's own font, in four sizes: 20 px for a title, 17 px for text, 15 px and 13 px for what
  stands beside it. Only the label of the drone flight on the map is smaller (12 px).
- **What it costs.** A phone keeps 31 files of the app where it kept 18: 140 KB more (121 KB of it the library's
  stylesheet), and 24 KB more on the wire.
- **Old browsers were not tried**, before the library or with it, so what one shows is not known. Framework7's
  stylesheet uses `:has()`, which Safari knows from 15.4, Chrome from 105 and Firefox from 121; the rules that
  use it are for parts this app does not have (navigation bars, and the pressed state that the script sets).

## Live changes

While the page is on screen, the phone asks `GET /public/areas/<area>/revision.json` every 15 seconds. The answer is
a few bytes. Only when the revision differs does the phone download the pack again. It then names the streets that
changed (or says how many, when they are more than two) and says whether the way on the screen is still the same.
An operator's confirmation reaches an open phone within about 15 seconds. A notice from the operators and a report
on a place travel the same way.

## A notice from the operators

An operator can tell every phone of an area something, for example "Drinking water is given out at the stadium."
The phone shows it in a strip at the top of the page, with who speaks and when.

| Address | What it is |
|---|---|
| `/operator/notice` | The page for it, one press away from the operator screen. It says what phones show now, takes the text in English, Turkish and Greek, and sends in two presses: the second shows exactly what will go out, and under which name |
| `GET /areas/<area>/notice` | What phones show now, and who sent it |
| `PUT /areas/<area>/notice` | Send one: `{"operator": "your name", "text": {"en": "…", "tr": "…", "el": "…"}}` |
| `DELETE /areas/<area>/notice?operator=your name` | Take it back |

These are operators' addresses: through the shared link they need the access key.

- **Who speaks is never typed.** A notice goes out under the name that the area file gives its operators
  (`notice_from` in `drone_vision/areas/<id>.json`). A request that brings a name of its own (`issued_by`) is
  refused, so nobody can write the name of an authority. An area whose file names nobody cannot send. For Defne the
  name is "Nature Shield", the team: no authority speaks through this prototype.
- **The text.** English is needed, because every phone can fall back on it. A language left empty is left out, and
  phones in that language show the English. At most 300 letters per language; line breaks and double spaces become
  single spaces. The phone and the operators' page write it as text, never as HTML.
- **Who sent it stays behind.** The operator's name, the time and the text are added to
  `<output folder>/<area>_notices.json`, oldest first, and a withdrawal is added too. That record never leaves:
  the pack holds the speaker, the time and the words only. `demo-reset` does not touch it.
- **A record nobody can read.** If somebody changes that file by hand and it no longer reads, only the notice
  stops. Phones still get the streets and the places, without the operators' notice; an open phone cannot tell
  this from a withdrawal and says the notice was withdrawn. The operators' addresses and their page answer an
  error that names the file, and nothing writes over it. When somebody repairs the file, the notice is back.
- **How fast.** The notice is part of the pack, so the pack's revision changes. A phone that has the app open
  shows the notice within about 15 seconds and says "New notice at the top of the page"; when it was taken back,
  the phone says that. A phone without a connection shows it when it is back.
- **One at a time.** A newer notice takes the place of the older one. A notice written by hand into the area file
  shows whenever the operators have none out (a change of the area file needs a restart of the service).
- **It does not end by itself.** A notice stays until somebody takes it back. When it is not from today, the phone
  shows its date beside the time.

## A report on a place

The pack lists where people can go. Whether a place takes people in right now is known only when an operator says
so: the drone looks at streets, not at a park or a hospital. An operator can report a place **in use**, **full** or
**closed**, and take the report back.

| Address | What it is |
|---|---|
| `/operator/places` | The page for it, one press away from the operator screen and from the notice page. It shows the two lists of the phone, says what is reported about each place and by whom, and reports in two presses: the first shows the sentence that phones will show, the second sends |
| `GET /areas/<area>/places` | The places, what is reported about each now, and who reported it |
| `PUT /areas/<area>/places/<place>/report` | Report one: `{"operator": "your name", "state": "closed"}`. The state is `in_use`, `full` or `closed` |
| `DELETE /areas/<area>/places/<place>/report?operator=your name` | Take the report back |

These are operators' addresses: through the shared link they need the access key.

- **What the phone does with it.** The card of the place says what was reported and when: "Closed: do not go
  there. Reported by the operations room: 14:05." A place reported full or closed goes to the end of its list, full
  before closed. It is never the one suggested and never picked for the person. Its sign turns grey and is struck
  through on the map, on its card and in the list, and the legend has a line for it. No place is hidden: the person
  sees why a place near them is not the one suggested.
- **Nothing reported is not "in use".** Without a report the card says "Nobody has reported yet whether this place
  is in use." A place reported in use does not go ahead of one that nobody reported on.
- **A place the person picked stays picked.** When it is then reported full or closed, the card says so, and the
  folded panel says the report before the name. The phone does not change a person's choice behind their back.
- **When every place of a list is full or closed** the phone says so and suggests none of them. For assembly points
  it says to go to open ground, for hospitals to call 112 in an emergency. The operators' page warns the operator
  about that list too.
- **Who reported it stays behind.** The operator's name, the time, the place and the state are added to
  `<output folder>/<area>_place_reports.json`, oldest first, and a withdrawal is added too. For every place the last
  line stands. The pack holds the state and the time only. `demo-reset` does not touch the record.
- **A record nobody can read stops the pack.** If somebody changes that file by hand and it no longer reads, the
  service answers an error that names the file: for the pack, for the list of places and for every report. That is
  stricter than with a notice, on purpose. A pack built without the reports would tell every phone that a closed
  place is open again. This way a phone keeps the pack it has, with every report in it. The operators' page says
  in red which file it is, and nothing writes over it. When somebody repairs the file, everything is back.
- **How fast.** A report is part of the pack, so the pack's revision changes. A phone that has the app open shows
  it within about 15 seconds and names the place: "Türkmenzade Ahmet Ağa Parkı: Closed." When more than two places
  changed, it names the one on the screen and says how many changed. The operators' page asks the service every
  15 seconds while it is on screen, at once when it comes back on screen, and before every first press. So an
  operator sees what another operator reported. The list never moves under an open question.
- **It does not end by itself.** A report stays until somebody reports something else or takes it back. A place
  reported full in the morning is still "full" in the evening unless an operator says otherwise.
- **The time** is written on the 24-hour clock in every language ("14:05", not "2:05 PM"): here, in a notice and
  in the line that says when the last information arrived.

## Without a network

The phone keeps two things, and "About" in the app says which of them it holds at that moment:

| What | Where | When |
|---|---|---|
| The last pack and the list of areas, each with the moment it arrived | browser cache `answers` (`store.js`) | after the page could read them |
| The app's own files | browser cache `shell-<version>` (`sw.js`) | after the first pack is on the screen; all files or none |

With both, the app opens with no network at all and finds routes. A strip then says "No connection. Showing the
last information received (time)", so nobody takes old information for new. The strip appears after two missed
checks (30 seconds), or at once when the phone itself says it is offline or the app was opened without the service.

What the service says about streets never passes through the service worker. Only the app's own files do. An old
pack can therefore never be handed out as a fresh one.

**How a newer app reaches a phone.** `GET /app/sw.js` carries the list of the app's files and a version worked out
from their contents. When any file changes, the browser fetches all of them again in the background. An open page
is replaced by itself only when nobody has pressed anything on it yet, or when it cannot read what the service
sends (a newer kind of pack). Anybody in the middle of something keeps the page they have and gets the newer app at
the next opening.

## Privacy and data protection

What the design does. It is our reading as engineers, not legal advice.

- **No personal data is collected.** No account, no cookies, no analytics, no advertising, no request to any other
  server. Every phone downloads the same file.
- **The position stays on the phone.** It is used to find the route and is forgotten when the page closes. It is
  never sent and never stored. The tests fail if a line of the app sends anything or stores a position
  (`tests/test_citizen_app.py` lists every request and every use of the phone's storage, word for word).
- **What is stored on the phone:** the language of the app, the last pack, the app's own files. None of it
  describes the person, and "About" lists what is there. Clearing the site's data in the browser removes it.
- **What the service sees:** like every web server, the address (IP) of a phone that asks for a file. When shared
  (`share`), the service writes no request down. The tunnel company (Cloudflare) carries the traffic and sees the
  address and the file name.
- **Operators.** Their names and notes stay on the operators' side and never enter a pack.

Before real use, three things are missing, and a lawyer has to look at them. The prototype runs on a laptop behind a
temporary tunnel and has none of them.

1. Somebody has to be what GDPR (Greece) and KVKK (Türkiye) call the data controller, most likely the civil
   protection authority that runs the service, with a privacy notice. An IP address alone can count as personal data.
2. A written agreement with whoever hosts the service or carries its traffic.
3. A decision on what the phone stores. EU rules allow storing on a person's device without asking only what the
   service that person asked for strictly needs. We think that the three things above are that. We have not had it
   confirmed.

## Security

- Every citizen address is answered with: `Content-Security-Policy` (only the service's own files, no inline
  script, no other server, no framing), `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`,
  `Permissions-Policy: geolocation=(self), camera=(), microphone=()`, `Cache-Control: no-cache`.
- The citizen addresses only read. Nothing a citizen can reach changes anything.
- A notice and a report on a place are sent with `PUT` and taken back with `DELETE`, on addresses that need the
  access key through the shared link. A browser asks the service for leave before it lets a page of another site
  send those two, and the service gives none. The pages `/operator/notice` and `/operator/places` are answered
  with a `Content-Security-Policy` that lets them talk to the service alone and forbids framing.
- The one library (MapLibre GL JS 4.7.1) and the map's letter shapes are stored in `citizen_app/vendor/` with their
  checksums and licences. Nothing is loaded from a CDN.
- Text from the pack is always written as text, never as HTML. The tests forbid `innerHTML`, `eval` and the like in
  the app's code.

## Limits

- **An exercise, one area, one flight.** Outside the 91 streets the drone saw, nothing is known: 7,075 streets
  are "No information".
- **Not tried on a real phone yet.** With the look of 17 November 2026 it was tried in headless Chrome (the ten
  scenes at 390 × 844 px, and the layout in sixteen combinations of screen size and language, from 280 to
  1,024 px wide, upright and sideways) and in Safari on iOS 26.5 inside Apple's simulator, on an iPhone 17:
  upright in English and Greek, sideways in Greek. With the look before it, on 15 November 2026, the simulator
  was an iPhone SE (3rd generation) and an iPhone 17, upright and sideways, in the three languages; the iPhone SE
  and Turkish were not repeated in the simulator after the change of the look. In the simulator a script pressed
  the buttons. A finger, the phone's own question about the position and the app opened from the Home Screen
  were not tried, and no Android phone at all.
- **The shared address changes** every time `share` starts again. A phone that kept the app from the old address
  can never reach the service again: it shows the last pack and "No connection". A real service needs a fixed
  address.
- **HTTPS is needed.** Over plain `http://` to another computer the browser keeps neither the pack nor the app, and
  does not give the app the phone's position: the app then works only with a network and a position chosen on the
  map. `127.0.0.1` and the shared link are fine.
- **Safari** may delete what a site kept after 7 days without use, unless the app was added to the Home Screen.
- **After an opening without a network**, the time shown is when the pack arrived, not the last time the service
  said that it was still the newest.
- **Names in Greek or Arabic letters** are not written on the map (the letter shapes are not there). The lists show
  them.
- **No operator accounts.** Whoever has the team's link can send a notice to every phone of the area or report a
  place closed, and the name in the record is the name that person typed. On the computer that runs the service no
  key is asked at all. A real service needs a login for each operator before anybody relies on a notice or on a
  report.
- **A notice and a report on a place do not end by themselves**, and neither was tried on a real phone.
- **A report is one of three words.** Nothing checks it against the place itself, and it has no free text: what
  else people should know about a place goes into a notice.
- **The assembly points** are from 2022, before the earthquakes. Whether each is usable today is not known until an
  operator reports on it, and each place says so.

## Tests

```
python -m pytest
node --test tests/citizen/*.test.mjs
```

| File | Tests | What they hold |
|---|---|---|
| `tests/test_public_pack.py` | 24 | the two rules, the contract, the revision, that the public addresses only read |
| `tests/test_notice.py` | 11 | who may send a notice, under which name it goes out, what stays behind, the operators' page, a record nobody can read |
| `tests/test_place_reports.py` | 12 | who may report on a place and what phones then get, what stays behind, the operators' page, a record nobody can read |
| `tests/test_citizen_app.py` | 15 | the headers, every request and every stored thing listed word for word, the app's file list, the manifest, that the script and the stylesheet ask the same question about the screen, that the page takes the library's look and the app's own rules come after it, that the map, the page and the home screen use the same colours, that a drawing of the app holds no code, fetches nothing and is used; the last one runs the JavaScript tests |
| `tests/citizen/route.test.mjs` | 26 | the route rule on small made-up towns with known answers; what changed between two packs; the order of the places when some are reported full or closed |
| `tests/citizen/store.test.mjs` | 5 | what is kept, and that a refusal or silence is never an answer |
| `tests/citizen/sw.test.mjs` | 7 | which requests are answered from the phone, and which never are |
| `tests/citizen/i18n.test.mjs` | 6 | every text exists in the three languages; the 24-hour clock |

`pytest` skips the JavaScript tests, and says so, where Node.js 20 or newer is missing.

The tests of the app were also run against copies of the code with one deliberate mistake at a time (236 mistakes
up to 14 November 2026, and ten more on 15 November for the two new tests, about the screen and about the
drawing): every one was noticed. The 236 were not repeated after the change of 15 November. On 17 November, for
the change of the look, 36 more were tried against the tests that change touched (the question about the screen,
the drawings, the colours, the library's look, the files of other projects): each one was noticed by the test
that is there for it.

Ten browser scenes (headless Chrome at phone size, and at desk size for the operators' pages)
cover what unit tests cannot: the map and the panel, choosing a position, a browser that cannot draw the map, the
first visit, a live change, the service going away and coming back, an opening without it, a newer app, what
"About" says, a notice that an operator sends from the page, a phone shows and the operator takes back, what a
phone shows of places that were reported (their order, their signs, their cards, a list in which every place is
full or closed), and a place that an operator reports from the page while a phone beside it changes its list. The
last two scenes were also run with one deliberate mistake at a time, 25 in the phone's code and 19 in the
operators' page: every one was noticed. After the change for the screen of a phone (15 November 2026) the ten
scenes were run again, without the mistakes, and all ten passed. After the change of the look (17 November 2026)
the ten scenes were run again, fitted to the new page where they read its parts by name, and all ten passed; the
25 mistakes in the phone's code were tried again and every one was noticed; the 19 in the operators' page were
not repeated, because that page did not change. The scenes and the mistake runs were done by hand and are not in
the repository.
