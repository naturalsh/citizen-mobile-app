"""Operator dashboard: incidents, queue order, decisions, OpenStreetMap lookups, API. No network."""
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from brain import control
from dashboard import data
from dashboard.app import create_app
from dashboard.geocode import Geocoder, locate
from dashboard.store import OperatorStore

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def report(call_id, level=None, event=None, minutes_ago=5, area="Vathy, Samos", status="complete", now=NOW, **extra):
    created = (now - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "call_id": call_id, "event_id": event, "created_at": created, "updated_at": created, "status": status,
        "caller_language": "el", "caller": {"name": "Test", "phone": "+30 690"},
        "location": {"aml": extra.get("aml"), "spoken_address": "Odos 1", "area": area, "confirmed_with_caller": True},
        "hazard_type": "earthquake", "situation": "s", "people": extra.get("people", []),
        "urgency": {"suggested": level, "confidence": 0.9, "reasons": ["r"], "confirmed_by_operator": None},
        "new_event_suggested": extra.get("new", False), "summary_for_operator": "x", "source": "voice_agent",
        "advice_given": ["earthquake.trapped"], "trigger": None, "handoff_reason": extra.get("handoff_reason"),
    }


def build(reports, decisions=None, claims=None, demo=False):
    return data.build_incidents(reports, decisions or {}, claims or {}, lambda i: None, NOW, demo)


# --- incidents and queue order ---

def test_calls_with_the_same_event_are_one_incident_at_the_highest_level():
    incidents = build([
        report("a", "urgent", "evt-1", people=[{"count": 2, "trapped": True, "injured": 1}]),
        report("b", "life_threat", "evt-1", people=[{"count": 3, "trapped": False, "cannot_walk": 1}]),
        report("c", "needs_help", None),
    ])
    first = incidents[0]
    assert (first["id"], first["level"], first["call_count"]) == ("evt-1", "life_threat", 2)
    assert first["people"] == {"total": 3, "trapped": 2, "injured": 1, "cannot_walk": 1, "unresponsive": 0,
                               "dead": 0, "plus": []}  # max per field
    assert incidents[1]["id"] == "call:c"


def test_queue_order_urgency_then_unclaimed_then_longest_waiting():
    incidents = build([
        report("old-urgent", "urgent", "e1", minutes_ago=30),
        report("new-life", "life_threat", "e2", minutes_ago=1),
        report("old-life", "life_threat", "e3", minutes_ago=20),
        report("claimed-life", "life_threat", "e4", minutes_ago=40),
        report("info", "information", "e5", minutes_ago=50),
        report("unknown", None, "e6", minutes_ago=60),
    ], claims={"e4": {"operator": "M", "at": "x"}})
    assert [i["id"] for i in incidents] == ["e3", "e2", "e4", "e1", "e5", "e6"]


def test_operator_decision_replaces_the_ai_level():
    decisions = {"a": {"action": "change", "level": "urgent", "operator": "M", "at": "t"}}
    [incident] = build([report("a", "life_threat", "e1")], decisions)
    assert (incident["level"], incident["confirmed"]) == ("urgent", True)
    call = incident["calls"][0]
    assert call["ai"]["level"] == "life_threat"  # the AI's suggestion stays visible


def test_incident_badge_is_solid_only_when_every_top_level_call_is_confirmed():
    reports = [report("a", "life_threat", "e1"), report("b", "life_threat", "e1")]
    one = {"a": {"action": "confirm", "level": "life_threat", "operator": "M", "at": "t"}}
    assert build(reports, one)[0]["confirmed"] is False
    both = {**one, "b": {"action": "confirm", "level": "life_threat", "operator": "M", "at": "t"}}
    assert build(reports, both)[0]["confirmed"] is True


def test_counts_and_unclaimed_life_threats():
    incidents = build([report("a", "life_threat", "e1"), report("b", "life_threat", "e2"), report("c", "urgent", "e3")],
                      claims={"e2": {"operator": "M", "at": "t"}})
    c = data.counts(incidents)
    assert c["by_level"]["life_threat"] == 2 and c["unclaimed_life_threat"] == 1 and c["calls"] == 3


def test_dropped_life_threat_needs_a_call_back():
    [incident] = build([report("a", "life_threat", "e1", status="dropped")])
    assert incident["dropped_life_threat"] is True


def test_demo_keeps_the_latest_run_of_each_case_and_replays_it_recently():
    reports = [report("eval-el-eq-x-aaaa", "urgent", "e1", minutes_ago=3000),
               report("eval-el-eq-x-bbbb", "life_threat", "e2", minutes_ago=2000),
               report("eval-tr-fire-cccc", "urgent", "e3", minutes_ago=1000)]
    incidents = build(reports, demo=True)
    assert sorted(c["call_id"] for i in incidents for c in i["calls"]) == ["eval-el-eq-x-bbbb", "eval-tr-fire-cccc"]
    for i in incidents:
        age = NOW - data.parse_time(i["first_at"])
        assert timedelta(0) < age <= timedelta(minutes=41)


# --- operator decisions ---

def test_store_keeps_who_decided_and_escalating_keeps_the_level(tmp_path):
    store = OperatorStore(tmp_path / "op.sqlite")
    store.decide("a", "change", "urgent", "Maria")
    store.decide("a", "escalate", None, "Nikos")
    latest = store.decisions()["a"]
    assert (latest["action"], latest["level"], latest["operator"]) == ("escalate", "urgent", "Nikos")
    assert [h["operator"] for h in store.history("a")] == ["Maria", "Nikos"]
    [incident] = build([report("a", "life_threat", "e1")], store.decisions())
    assert (incident["level"], incident["confirmed"], incident["escalated"]) == ("urgent", True, True)
    with pytest.raises(ValueError):
        store.decide("a", "dispatch", None, "M")


def test_claims_can_be_released(tmp_path):
    store = OperatorStore(tmp_path / "op.sqlite")
    store.claim("e1", "Maria")
    assert store.claims()["e1"]["operator"] == "Maria"
    store.release("e1")
    assert store.claims() == {}


# --- OpenStreetMap lookups ---

def wait_for(condition, seconds=2.0):
    end = time.time() + seconds
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_geocoder_looks_up_the_area_once_in_the_background(tmp_path):
    asked = []

    def search(query):
        asked.append(query)
        return {"lat": 37.75, "lon": 26.98, "label": "Vathy"} if query == "Samos" else None

    g = Geocoder(tmp_path / "g.sqlite", search=search, min_interval_s=0)
    assert g.lookup("Vathy, Samos") is None  # not known yet: queued
    assert wait_for(lambda: g.lookup("Vathy, Samos") is not None)
    assert asked == ["Vathy, Samos", "Samos"]  # tried the full area, then the larger place
    g.lookup("vathy, samos")
    assert asked == ["Vathy, Samos", "Samos"]  # cached, case-insensitive: no new request


def test_geocoder_backs_off_after_a_failed_request(tmp_path):
    calls = []

    def offline(query):
        calls.append(query)
        raise OSError("offline")

    g = Geocoder(tmp_path / "g.sqlite", search=offline, min_interval_s=0)
    g.lookup("Karlovasi")
    assert wait_for(lambda: calls and g.pending() == 0)
    time.sleep(0.05)
    for _ in range(5):
        g.lookup("Karlovasi")
    time.sleep(0.1)
    assert len(calls) == 1  # no retry loop while OpenStreetMap is unreachable


def test_locate_prefers_caller_gps_and_never_sends_the_street(tmp_path):
    asked = []
    g = Geocoder(tmp_path / "g.sqlite", search=lambda q: asked.append(q), min_interval_s=0)
    gps = build([report("a", "urgent", "e1", aml={"lat": 37.0, "lon": 26.0, "accuracy_m": 10}),
                 report("b", "urgent", "e1", aml={"lat": 37.2, "lon": 26.2, "accuracy_m": 10})])[0]
    loc = locate(gps, g)
    assert (round(loc["lat"], 2), round(loc["lon"], 2), loc["source"]) == (37.1, 26.1, "aml")
    no_gps = build([report("c", "urgent", "e2", area="Bayrakli, Izmir")])[0]
    locate(no_gps, g)
    assert wait_for(lambda: asked)
    assert all("Odos" not in q for q in asked)  # only the area, never the spoken street address


# --- API ---

@pytest.fixture
def client(tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "transcripts").mkdir()
    real_now = datetime.now(timezone.utc)  # the API stamps claims and resolutions with the real time
    for r in [report("a", "life_threat", "e1", now=real_now), report("b", None, "e2", now=real_now)]:
        (tmp_path / "reports" / f"{r['call_id']}.json").write_text(json.dumps(r))
    (tmp_path / "transcripts" / "a.json").write_text(json.dumps([{"role": "caller", "text": "help", "at": "t"}]))
    g = Geocoder(tmp_path / "g.sqlite", search=lambda q: None, enabled=False)
    return TestClient(create_app(tmp_path, geocoder=g))


def test_state_lists_incidents_counts_and_controls(client):
    state = client.get("/api/state").json()
    assert state["counts"]["by_level"]["life_threat"] == 1
    assert {i["id"] for i in state["incidents"]} == {"e1", "e2"}
    assert state["paused"] is None and "hour" in state["budget"]


def test_claim_and_decide_through_the_api(client):
    assert client.post("/api/claims", json={"incident_id": "e1", "operator": "Maria"}).status_code == 200
    r = client.post("/api/decisions", json={"call_id": "a", "action": "confirm", "operator": "Maria"})
    assert r.json()["level"] == "life_threat"
    incident = next(i for i in client.get("/api/state").json()["incidents"] if i["id"] == "e1")
    assert incident["claim"]["operator"] == "Maria" and incident["confirmed"]


def test_bad_decisions_are_refused(client):
    post = lambda body: client.post("/api/decisions", json={"operator": "M", **body}).status_code  # noqa: E731
    assert post({"call_id": "nope", "action": "confirm"}) == 404
    assert post({"call_id": "a", "action": "change"}) == 422  # change needs a level
    assert post({"call_id": "b", "action": "confirm"}) == 422  # nothing suggested to confirm
    assert post({"call_id": "a", "action": "dispatch"}) == 422
    assert client.post("/api/decisions", json={"call_id": "a", "action": "confirm", "operator": ""}).status_code == 422


def test_transcript_only_from_the_transcripts_folder(client):
    assert client.get("/api/calls/a/transcript").json()["lines"][0]["text"] == "help"
    assert client.get("/api/calls/..%2Freports%2Fa/transcript").status_code == 404


def test_pause_switch_reaches_the_brain(client):
    client.post("/api/pause", json={"paused": True, "operator": "Maria"})
    assert control.is_paused() and control.pause_info()["by"] == "Maria"
    assert client.get("/api/state").json()["paused"]["by"] == "Maria"
    client.post("/api/pause", json={"paused": False, "operator": "Maria"})
    assert not control.is_paused()


def test_undo_only_your_own_recent_decision(tmp_path, monkeypatch):
    store = OperatorStore(tmp_path / "op.sqlite")
    store.decide("a", "confirm", "life_threat", "Maria")
    store.decide("a", "change", "urgent", "Maria")
    assert store.undo("a", "Nikos") is None  # not Nikos's decision
    assert store.undo("a", "Maria")["level"] == "urgent"
    assert store.decisions()["a"]["level"] == "life_threat"  # back to the earlier decision
    assert store.undo("a", "Maria", within_s=-1) is None  # too old


def test_undo_through_the_api(client):
    client.post("/api/decisions", json={"call_id": "a", "action": "change", "level": "urgent", "operator": "Maria"})
    assert client.post("/api/decisions/undo", json={"call_id": "a", "operator": "Maria"}).json()["undone"]["level"] == "urgent"
    assert client.post("/api/decisions/undo", json={"call_id": "a", "operator": "Maria"}).status_code == 409


def test_store_survives_its_file_being_deleted(tmp_path):
    store = OperatorStore(tmp_path / "op.sqlite")
    store.claim("e1", "Maria")
    (tmp_path / "op.sqlite").unlink()  # e.g. --reset while the dashboard runs
    assert store.claims() == {} and store.decisions() == {}
    store.decide("a", "confirm", "urgent", "Maria")
    assert store.decisions()["a"]["level"] == "urgent"


# --- resolving and notes ---

def test_resolved_incidents_go_last_and_leave_the_counts():
    reports = [report("a", "life_threat", "e1", minutes_ago=10), report("b", "urgent", "e2", minutes_ago=5)]
    resolved = {"e1": {"operator": "Maria", "at": "2026-10-22T11:59:00Z"}}
    incidents = data.build_incidents(reports, {}, {}, lambda i: None, NOW, resolutions=resolved)
    assert [i["id"] for i in incidents] == ["e2", "e1"]  # the resolved life-threat sinks below the open urgent one
    assert incidents[1]["resolved"]["operator"] == "Maria"
    c = data.counts(incidents)
    assert c["by_level"]["life_threat"] == 0 and c["unclaimed_life_threat"] == 0 and c["resolved"] == 1


def test_a_new_call_after_resolving_reopens_the_incident():
    resolved = {"e1": {"operator": "Maria", "at": "2026-10-22T11:50:00Z"}}  # 10 minutes ago
    old_call = report("a", "life_threat", "e1", minutes_ago=20)
    [still] = data.build_incidents([old_call], {}, {}, lambda i: None, NOW, resolutions=resolved)
    assert still["resolved"] and not still["reopened"]
    new_call = report("b", "life_threat", "e1", minutes_ago=2)  # came in after it was resolved
    [incident] = data.build_incidents([old_call, new_call], {}, {}, lambda i: None, NOW, resolutions=resolved)
    assert incident["resolved"] is None and incident["reopened"] is True


def test_notes_are_kept_and_only_your_recent_one_can_be_undone(tmp_path):
    store = OperatorStore(tmp_path / "op.sqlite")
    first = store.add_note("e1", "Maria", "Fire crew 3 sent")
    second = store.add_note("e1", "Nikos", "Ambulance on the way")
    assert [n["text"] for n in store.notes()["e1"]] == ["Fire crew 3 sent", "Ambulance on the way"]
    assert store.delete_note(second["id"], "Maria") is False  # not hers
    assert store.delete_note(first["id"], "Maria", within_s=-1) is False  # too old
    assert store.delete_note(first["id"], "Maria") is True
    assert [n["text"] for n in store.notes()["e1"]] == ["Ambulance on the way"]


def test_resolve_reopen_and_notes_through_the_api(client):
    assert client.post("/api/resolve", json={"incident_id": "nope", "operator": "M"}).status_code == 404
    client.post("/api/resolve", json={"incident_id": "e1", "operator": "Maria"})
    state = client.get("/api/state").json()
    assert state["counts"]["resolved"] == 1 and state["incidents"][-1]["id"] == "e1"
    client.post("/api/resolve", json={"incident_id": "e1", "operator": "Maria", "resolved": False})
    assert client.get("/api/state").json()["counts"]["resolved"] == 0

    note = client.post("/api/notes", json={"incident_id": "e1", "operator": "Maria", "text": " Fire crew 3 sent "}).json()
    assert note["text"] == "Fire crew 3 sent"
    assert client.post("/api/notes", json={"incident_id": "e1", "operator": "Maria", "text": "   "}).status_code == 422
    assert client.post("/api/notes", json={"incident_id": "e1", "operator": "M", "text": "x" * 301}).status_code == 422
    incident = next(i for i in client.get("/api/state").json()["incidents"] if i["id"] == "e1")
    assert [n["text"] for n in incident["notes"]] == ["Fire crew 3 sent"]
    assert client.post("/api/notes/undo", json={"note_id": note["id"], "operator": "Maria"}).status_code == 200
    assert client.post("/api/notes/undo", json={"note_id": note["id"], "operator": "Maria"}).status_code == 409


def test_calls_on_the_line_now():
    reports = [report("talking", "urgent", "e1", minutes_ago=2, status="in_progress"),
               report("stale", "urgent", "e2", minutes_ago=30, status="in_progress"),  # likely a dropped line
               report("finished", "urgent", "e3", minutes_ago=1, status="complete")]
    incidents = build(reports)
    live = {c["call_id"]: c["live"] for i in incidents for c in i["calls"]}
    assert live == {"talking": True, "stale": False, "finished": False}
    assert data.counts(incidents)["live_calls"] == 1
    assert next(i for i in incidents if i["id"] == "e1")["live"] is True


def test_claim_and_notes_follow_a_call_into_its_event(client, tmp_path):
    # Mid-call the caller says where they are and the brain puts the call in an event:
    # its incident id changes from call:c to e1. What the operator did must not be lost.
    real_now = datetime.now(timezone.utc)
    path = tmp_path / "reports" / "c.json"
    path.write_text(json.dumps(report("c", None, None, status="in_progress", area=None, now=real_now)))
    client.post("/api/claims", json={"incident_id": "call:c", "operator": "Maria"})
    client.post("/api/notes", json={"incident_id": "call:c", "operator": "Maria", "text": "Caller panicking"})

    path.write_text(json.dumps(report("c", "life_threat", "e1", status="in_progress", now=real_now)))
    incidents = {i["id"]: i for i in client.get("/api/state").json()["incidents"]}
    assert "call:c" not in incidents
    assert incidents["e1"]["claim"]["operator"] == "Maria"
    assert [n["text"] for n in incidents["e1"]["notes"]] == ["Caller panicking"]


def test_an_existing_claim_on_the_event_wins(tmp_path):
    store = OperatorStore(tmp_path / "op.sqlite")
    store.claim("e1", "Maria")
    store.claim("call:c", "Kemal")
    store.move("call:c", "e1")
    assert store.claims() == {"e1": {"operator": "Maria", "at": store.claims()["e1"]["at"]}}


def test_life_threats_rank_unresponsive_then_people_at_risk_then_waiting():
    incidents = build([
        report("old-one-trapped", "life_threat", "e1", minutes_ago=30, people=[{"count": 1, "trapped": True}]),
        report("five-trapped", "life_threat", "e2", minutes_ago=2, people=[{"count": 5, "trapped": True}]),
        report("unconscious", "life_threat", "e3", minutes_ago=1, people=[{"count": 1, "unresponsive": 1}]),
        report("also-one", "life_threat", "e4", minutes_ago=10, people=[{"count": 1, "trapped": True}]),
    ])
    assert [i["id"] for i in incidents] == ["e3", "e2", "e1", "e4"]
    assert incidents[0]["priority_reasons"] == ["1 not breathing / unconscious"]
    assert incidents[1]["priority_reasons"] == ["5 trapped"]


def test_a_handoff_for_not_breathing_counts_as_critical():
    incidents = build([
        report("trapped", "life_threat", "e1", people=[{"count": 3, "trapped": True}]),
        report("cpr", "life_threat", "e2", handoff_reason="not_breathing"),
    ])
    assert incidents[0]["id"] == "e2"


def test_new_facts_move_an_incident_up_on_the_next_refresh():
    calm = [report("a", "life_threat", "e1", minutes_ago=20, people=[{"count": 1, "trapped": True}]),
            report("b", "life_threat", "e2", minutes_ago=5, people=[{"count": 1, "trapped": True}])]
    assert build(calm)[0]["id"] == "e1"
    worse = [calm[0], report("b", "life_threat", "e2", minutes_ago=5, people=[{"count": 4, "trapped": True}])]
    assert build(worse)[0]["id"] == "e2"


def test_surge_switch_through_the_api(client):
    assert client.get("/api/state").json()["handoff"]["mode"] in ("surge", "normal")
    r = client.post("/api/handoff-mode", json={"mode": "normal", "operator": "Maria"})
    assert r.status_code == 200 and r.json()["by"] == "Maria"
    assert client.get("/api/state").json()["handoff"]["mode"] == "normal"
    assert client.post("/api/handoff-mode", json={"mode": "chaos", "operator": "Maria"}).status_code == 422


def test_the_page_is_never_served_stale(client):
    # After an update, a cached old app.js kept the old behaviour in the browser.
    for path in ("/", "/static/app.js", "/static/style.css"):
        assert client.get(path).headers["cache-control"] == "no-cache"


def test_voices_under_rubble_count_as_at_least_one_trapped():
    # From a test call: "I hear voices under the rubble" became exactly 1 trapped, 0 injured.
    incident = build([report("v", "life_threat", "e1", people=[{"count": 1, "trapped": True, "at_least": True}])])[0]
    assert incident["people"]["plus"] == ["total", "trapped"]
    assert incident["priority_reasons"] == ["1+ trapped"]


def test_one_person_is_one_tag_not_one_per_condition():
    # From a test call: one man under a tree showed as "1 trapped", "1 injured", "1 can't leave".
    assert data.group_label({"count": 1, "trapped": True, "injured": 1, "cannot_walk": 1}) == "1 trapped, injured, can't leave"
    assert data.group_label({"count": 3, "trapped": True, "injured": 1}) == "3 trapped (1 injured)"
    assert data.group_label({"count": 1, "trapped": True, "at_least": True, "note": "voices in building"}) == "1+ trapped · voices in building"
    assert data.group_label({"count": 2, "note": "caller and son, fine"}) is None


def test_separate_groups_get_separate_tags():
    incident = build([report("t", "life_threat", "e1", people=[
        {"count": 1, "trapped": True, "note": "under a tree"},
        {"count": 1, "trapped": True, "at_least": True, "note": "voices in building"}])])[0]
    assert incident["priority_reasons"] == ["1 trapped · under a tree", "1+ trapped · voices in building"]


def test_the_dead_get_their_own_tag_and_raise_the_priority():
    # From a test call: "5 have died and 2 babies" became "7 people, 1 injured".
    assert data.group_labels({"count": 7, "dead": 5, "injured": 1}) == ["5 dead", "1 injured"]
    assert data.group_labels({"count": 5, "dead": 5}) == ["5 dead"]
    incidents = build([report("a", "life_threat", "e1", people=[{"count": 2, "trapped": True}]),
                       report("b", "life_threat", "e2", people=[{"count": 7, "dead": 5, "injured": 1}])])
    assert incidents[0]["id"] == "e2" and incidents[0]["priority_reasons"][0] == "5 dead"


def test_some_injured_in_a_group_are_not_all_of_it():
    assert data.group_label({"count": 3, "injured": 1}) == "1 injured"  # was "3 injured"


def test_a_street_position_is_used_only_near_the_area(tmp_path):
    from dashboard.geocode import Geocoder, locate
    places = {"athens": {"lat": 37.9756, "lon": 23.7348, "label": "Athens", "radius_m": 3000},
              "near:καλλιρρόης": {"lat": 38.1164, "lon": 23.8409, "label": "Καλλιρρόης, Ekali"},  # 16 km: not this one
              "near:θεμιστοκλέους": {"lat": 37.9840, "lon": 23.7330, "label": "Θεμιστοκλέους"}}  # 1 km
    g = Geocoder(tmp_path / "g.sqlite", enabled=False)
    g.lookup = lambda q, exact=False, near=None: places.get(("near:" if near else "") + q.strip().lower())
    def incident(address):
        return {"area": "Athens", "calls": [{"location": {"aml": None, "spoken_address": address,
                                                          "street": address.split()[0]}}]}
    assert locate(incident("Καλλιρρόης 33, Αθήνα"), g)["label"] == "Athens"  # someone else's street: stay at the area
    near = locate(incident("Θεμιστοκλέους 5, Αθήνα"), g)
    assert near["source"] == "street" and "5" not in near["label"]


def test_a_shared_dashboard_needs_the_key_from_its_link(tmp_path):
    (tmp_path / "reports").mkdir()
    g = Geocoder(tmp_path / "g.sqlite", search=lambda q: None, enabled=False)
    client = TestClient(create_app(tmp_path, geocoder=g, access_key="s3cret"))
    assert client.get("/").status_code == 401 and client.get("/api/state").status_code == 401
    assert client.get("/?key=wrong").status_code == 401
    assert client.get("/?key=s3cret").status_code == 200  # the link sets a cookie...
    assert client.get("/api/state").status_code == 200  # ...so the page's own requests work
    assert client.post("/api/pause", json={"paused": False, "operator": "Friend"}).status_code == 200  # full dashboard


def test_every_position_says_how_exact_it_is(tmp_path):
    from dashboard.geocode import Geocoder, _radius_m, locate
    assert 1000 < _radius_m(["37.94", "37.97", "23.68", "23.71"]) < 3000  # a neighbourhood: about 2 km
    assert _radius_m(None) is None
    places = {"kallithea, athens": {"lat": 37.955, "lon": 23.70, "label": "Kallithea", "source": "openstreetmap",
                                    "radius_m": 1800}}
    g = Geocoder(tmp_path / "g.sqlite", enabled=False)
    g.lookup = lambda q, exact=False, near=None: None if near else places.get(q.strip().lower())
    area_only = {"area": "Kallithea, Athens", "calls": [{"location": {"aml": None, "spoken_address": "Μιχαήλ Μελά 13", "street": "Μιχαήλ Μελά"}}]}
    loc = locate(area_only, g)
    assert (loc["precision"], loc["radius_m"]) == ("area", 1800)  # street not found: only the area, as a circle
    gps = {"area": None, "calls": [{"location": {"aml": {"lat": 37.9, "lon": 23.7, "accuracy_m": 30}}}]}
    assert (locate(gps, g)["precision"], locate(gps, g)["radius_m"]) == ("gps", 30)


def test_the_old_place_cache_is_not_used(tmp_path):
    # It could hold a holiday flat as an area ("Acropolis, Koukaki, Athens", demo call 2026-10-30).
    import sqlite3
    from dashboard.geocode import Geocoder
    with sqlite3.connect(tmp_path / "old.sqlite") as conn:
        conn.execute("CREATE TABLE places (area TEXT PRIMARY KEY, lat REAL, lon REAL, label TEXT, looked_up REAL NOT NULL)")
        conn.execute("INSERT INTO places VALUES ('vathy', 37.75, 26.97, 'Vathy', 1)")
    asked = []
    g = Geocoder(tmp_path / "old.sqlite", search=lambda q: asked.append(q) or {"lat": 37.75, "lon": 26.97, "label": "Vathy"},
                 min_interval_s=0)
    assert g.lookup("Vathy") is None  # looked up afresh
    assert wait_for(lambda: g.lookup("Vathy") is not None) and asked == ["Vathy"]


def test_an_area_is_a_place_not_a_shop_or_a_holiday_flat(monkeypatch):
    import io
    from dashboard import geocode
    answers = {"flat": [{"category": "tourism", "type": "apartment", "lat": "37.963", "lon": "23.724",
                         "display_name": "Spacious apt in Koukaki FIX 500 meter to Acropolis"}],
               "place": [{"category": "place", "type": "neighbourhood", "lat": "37.964", "lon": "23.724",
                          "display_name": "Κουκάκι", "boundingbox": ["37.958", "37.970", "23.716", "23.732"]}]}
    def urlopen(request, timeout):
        q = request.full_url
        found = answers["flat"] + (answers["place"] if "Koukaki%2C+Athens" in q and "Acropolis" not in q else [])
        return io.BytesIO(json.dumps(found).encode())
    monkeypatch.setattr(geocode.urllib.request, "urlopen", urlopen)
    assert geocode.nominatim("Acropolis, Koukaki, Athens") is None  # only the flat: not an area
    assert geocode.nominatim("Koukaki, Athens")["label"] == "Κουκάκι"  # the flat came first, the place is taken


def test_a_landmark_without_a_known_size_falls_back_to_the_wider_place(tmp_path):
    # "The old port" has no range on the map: the page must say it shows the whole wider place.
    from dashboard.geocode import Geocoder, locate
    asked = []
    def search(query):
        asked.append(query)
        return {"lat": 35.51, "lon": 24.02, "label": "Chania", "radius_m": 4000} if query == "Chania" else None
    g = Geocoder(tmp_path / "g.sqlite", search=search, min_interval_s=0)
    incident = {"area": "Old port, Chania", "calls": [{"location": {"aml": None, "spoken_address": "Παλιό λιμάνι"}}]}
    locate(incident, g)
    assert wait_for(lambda: locate(incident, g) is not None)
    loc = locate(incident, g)
    assert (loc["precision"], loc["matched"], loc["radius_m"]) == ("wider", "Chania", 4000)
    assert asked == ["Old port, Chania", "Chania"]


def test_a_street_is_searched_inside_the_area_with_and_without_double_letters(tmp_path):
    # A test call's "Καλλιρρόης 33, Athens": OpenStreetMap spells it Καλλιρόης, and a search across the
    # country found a different Καλλιρρόης in Ekali. Now: inside the area, both spellings, no house number.
    from dashboard.geocode import Geocoder, locate, spellings
    assert spellings("Καλλιρρόης") == ["Καλλιρρόης", "Καλιρρόης", "Καλλιρόης", "Καλιρόης"]
    assert spellings("Θεμιστοκλέους") == ["Θεμιστοκλέους"]  # no doubles: one lookup
    asked = []
    def search(query, box=None):
        asked.append((query, box is not None))
        if query == "Athens":
            return {"lat": 37.9756, "lon": 23.7348, "label": "Athens", "radius_m": 3000}
        return {"lat": 37.9613, "lon": 23.7212, "label": "Καλλιρόης, Κουκάκι"} if query == "Καλλιρόης" and box else None
    g = Geocoder(tmp_path / "g.sqlite", search=search, min_interval_s=0)
    incident = {"area": "Athens", "calls": [{"location": {"aml": None, "spoken_address": "Καλλιρρόης 33, Αθήνα", "street": "Καλλιρρόης"}}]}
    # (Athens is given a neighbourhood-sized 3 km here; a real whole-city area is too big, see below.)
    for _ in range(3):
        locate(incident, g)
        wait_for(lambda: not g.pending(), seconds=1)
    loc = locate(incident, g)
    assert loc["precision"] == "street" and "33" not in str(asked)
    assert [q for q, _ in asked if q != "Athens"] == ["Καλλιρρόης", "Καλιρρόης", "Καλλιρόης"]  # stops at the hit


def test_a_street_in_a_whole_city_is_not_placed(tmp_path):
    # Real Athens is ±15 km: Καλλιρρόης matched a street in Ekali (16 km) and one near Piraeus (9 km).
    from dashboard.geocode import Geocoder, locate
    g = Geocoder(tmp_path / "g.sqlite", enabled=False)
    asked = []
    g.lookup = lambda q, exact=False, near=None: asked.append(q) or (
        None if near else {"lat": 37.9756, "lon": 23.7348, "label": "Athens", "radius_m": 15000, "matched": "Athens"})
    loc = locate({"area": "Athens", "calls": [{"location": {"aml": None, "spoken_address": "Καλλιρρόης 33, Αθήνα", "street": "Καλλιρρόης"}}]}, g)
    assert (loc["precision"], loc["street_not_placed"]) == ("area", "Καλλιρρόης")
    assert asked == ["Athens"]  # no street lookup at all


def test_the_dashboard_uses_where_the_brain_found_the_street(tmp_path):
    from dashboard.geocode import Geocoder, locate
    g = Geocoder(tmp_path / "g.sqlite", enabled=False)
    g.lookup = lambda q, exact=False, near=None: (
        None if near else {"lat": 37.976, "lon": 23.735, "label": "Athens", "radius_m": 15000, "matched": "Athens"})
    def incident(matches):
        return {"area": "Athens", "calls": [{"location": {"aml": None, "spoken_address": "Καλλιρόης 33, Αθήνα",
                                                          "street_matches": matches}}]}
    one = locate(incident([{"name": "Koukaki", "lat": 37.961, "lon": 23.721}]), g)
    assert (one["precision"], one["lat"], one["radius_m"]) == ("street", 37.961, 250)
    several = locate(incident([{"name": "Koukaki", "lat": 37.961, "lon": 23.721},
                               {"name": "Neos Kosmos", "lat": 37.967, "lon": 23.733}]), g)
    assert several["precision"] == "area" and [m["name"] for m in several["street_choices"]] == ["Koukaki", "Neos Kosmos"]
    none = locate(incident([]), g)
    assert none["precision"] == "area" and none["street_choices"] == []


def test_an_area_outline_and_a_whole_street_are_kept_for_the_map(tmp_path):
    # Asked after a test call: highlight the neighbourhood itself, and the whole street when only
    # the street is known, instead of a circle around a centre.
    from dashboard.geocode import Geocoder, locate
    outline = {"type": "Polygon", "coordinates": [[[23.72, 37.96], [23.73, 37.96], [23.73, 37.97], [23.72, 37.96]]]}
    asked = []
    g = Geocoder(tmp_path / "g.sqlite", min_interval_s=0, search=lambda q: asked.append(q) or {
        "lat": 37.965, "lon": 23.725, "label": "Koukaki", "radius_m": 900, "shape": outline})
    g.lookup("Koukaki, Athens")
    assert wait_for(lambda: g.lookup("Koukaki, Athens") is not None)
    assert g.lookup("Koukaki, Athens")["shape"] == outline and asked == ["Koukaki, Athens"]  # cached with it
    area_only = locate({"area": "Koukaki, Athens", "calls": [{"location": {"aml": None, "spoken_address": None}}]}, g)
    assert (area_only["precision"], area_only["shape"]) == ("area", outline)
    line = [[37.9650, 23.7279], [37.9659, 23.7305]]
    street = locate({"area": "Koukaki, Athens", "calls": [{"location": {
        "aml": None, "spoken_address": "Ορλώφ 4", "street": "Ορλώφ",
        "street_matches": [{"name": "Akropoli", "lat": 37.965, "lon": 23.728, "lines": [line]}]}}]}, g)
    assert (street["precision"], street["lines"]) == ("street", [line])


def _one_street(spoken, street="Kaya Sokak", area="Keçiören, Ankara"):
    match = {"name": "Kaya Mahallesi", "lat": 39.98, "lon": 32.86, "also": [], "lines": [[[39.98, 32.86], [39.981, 32.861]]]}
    return {"area": area, "calls": [{"location": {"aml": None, "street": street, "spoken_address": spoken,
                                                  "street_matches": [match]}, "caller": {"name": "Ayşe Deneme"}}]}


def test_the_building_is_pinned_when_openstreetmap_has_the_house_number(tmp_path):
    from dashboard.geocode import Geocoder, locate
    boxes = []

    def addresses(box):
        boxes.append(box)
        return [{"street": "Kaya Sokak", "number": "17", "lat": 39.9805, "lon": 32.8603},
                {"street": "Yuvarlak Kaya Sokak", "number": "17", "lat": 39.99, "lon": 32.87}]

    g = Geocoder(tmp_path / "g.sqlite", search=lambda q, box=None: None, min_interval_s=0, addresses=addresses)
    incident = _one_street("Kaya Sokak 17, Kaya Mahallesi, Keçiören, Ankara")
    assert locate(incident, g)["precision"] == "street"  # first the street, while the buildings are fetched
    assert wait_for(lambda: locate(incident, g)["precision"] == "house")
    loc = locate(incident, g)
    assert (loc["lat"], loc["radius_m"]) == (39.9805, 30) and "the building" in loc["label"]  # not Yuvarlak Kaya
    assert len(boxes) == 1 and all(isinstance(x, float) for x in boxes[0])  # only a box is sent


def test_a_missing_number_is_estimated_from_its_mapped_neighbours():
    from dashboard.geocode import place_number
    mapped = [{"street": "Kıbrıs Şehitleri Caddesi", "number": n, "lat": lat, "lon": 27.14}
              for n, lat in (("4", 38.4300), ("12", 38.4306), ("5", 38.4301), ("16", 38.4309))]
    between = place_number("Kıbrıs Şehitleri Caddesi", "10", mapped)  # 10 is between 4 and 12 on the even side
    assert between["precision"] == "estimated" and 38.4300 < between["lat"] < 38.4306 and "4 and No. 12" in between["how"]
    near = place_number("Kıbrıs Şehitleri Caddesi", "20", mapped)  # past the last one: next to 16
    assert near["precision"] == "estimated" and near["lat"] == 38.4309 and near["radius_m"] == 30 + 8 * 4
    assert place_number("Kıbrıs Şehitleri Caddesi", "90", mapped) is None  # too far from anything mapped
    # Only the other side mapped, as on Ορλώφ (No. 9 only): across from the closest one, street width added.
    orlof = [{"street": "Ορλώφ", "number": "9", "lat": 37.9641, "lon": 23.7213}]
    across = place_number("Ορλώφ", "12", orlof)
    assert across["precision"] == "estimated" and "across from No. 9" in across["how"]
    assert across["radius_m"] == 30 + 8 * 3 + 15
    assert place_number("Ορλώφ", "20", orlof) is None  # 11 numbers away: too far to say
    assert place_number("Atatürk Caddesi", "12", mapped) is None  # another street


def test_no_number_or_nothing_mapped_keeps_the_street_pin(tmp_path):
    from dashboard.geocode import Geocoder, locate
    boxes = []
    g = Geocoder(tmp_path / "g.sqlite", search=lambda q, box=None: None, min_interval_s=0,
                 addresses=lambda box: boxes.append(box) or [])
    incident = _one_street("Kaya Sokak 17, Keçiören")
    locate(incident, g)
    assert wait_for(lambda: boxes)
    time.sleep(0.1)
    loc = locate(incident, g)
    assert loc["precision"] == "street" and "not on OpenStreetMap" in loc["label"]
    boxes.clear()
    assert locate(_one_street("Kaya Sokak, 3. kat, Keçiören"), g)["precision"] == "street"
    time.sleep(0.1)
    assert boxes == []  # no number said: nothing is fetched


def test_house_numbers_come_only_from_the_street_part():
    from dashboard.geocode import house_number
    assert house_number("Ορλώφ", "Ορλώφ 12Α, Κουκάκι, Αθήνα") == "12Α"
    assert house_number("Gazi Caddesi", "Gazi Caddesi No 18, Bayraklı") == "18"
    assert house_number("Ορλώφ", "Ορλώφ, 3ος όροφος, Κουκάκι") is None  # a floor is not a house number
    assert house_number("Görken", "100. Yıl Mahallesi, Görken Sitesi") is None


def test_updates_are_compressed(client):
    # Over ngrok's free plan every byte counts: one update was 35 KB, 6 KB compressed.
    for n in range(60):
        client.post("/api/notes", json={"incident_id": "call:invented", "operator": "Tester", "text": "x" * 40 + str(n)})
    response = client.get("/api/state", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200 and response.headers.get("content-encoding") == "gzip"


def test_a_real_report_reaches_the_building_pin(tmp_path):
    # Demo call 2026-10-30: "Ορλώφ 12" was in the report, but the dashboard's call data dropped the
    # street, so the map never looked for the number and said "no house number said". The tests
    # above built that data by hand, with the street, and missed it.
    from dashboard.geocode import Geocoder, locate
    r = report("orlof", "life_threat", "e1", area="Koukaki, Athens")
    r["location"].update(street="Ορλώφ", spoken_address="downtown Athens, Ορλώφ 12, Koukaki",
                         street_matches=[{"name": "Akropoli", "lat": 37.9645, "lon": 23.7214, "also": [],
                                          "lines": [[[37.9656, 23.7214], [37.9634, 23.7214]]]}])
    incident = build([r])[0]
    assert incident["calls"][0]["location"]["street"] == "Ορλώφ"
    g = Geocoder(tmp_path / "g.sqlite", search=lambda q, box=None: None, min_interval_s=0,
                 addresses=lambda box: [{"street": "Ορλώφ", "number": "12", "lat": 37.9642, "lon": 23.7215}])
    locate(incident, g)
    assert wait_for(lambda: locate(incident, g)["precision"] == "house")
