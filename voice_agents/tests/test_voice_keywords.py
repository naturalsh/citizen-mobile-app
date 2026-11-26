"""The keyword list sent to Soniox, no API calls."""
from voice import keywords


def test_list_fits_sonioxs_context_limit():
    assert keywords.size_chars(keywords.load()) < keywords.MAX_CHARS


def test_every_language_and_the_demo_places_are_covered():
    data = keywords.load()
    assert set(data["terms"]) == {"el", "tr", "en", "fr"}
    for place in ("Βαθύ", "Vathy", "Bayraklı", "İzmir"):
        assert place in data["places"]


def test_terms_are_clean_and_not_repeated():
    terms = keywords.all_terms(keywords.load())
    assert all(t and t == t.strip() for t in terms)
    assert len(terms) == len(set(terms))


def test_context_carries_terms_and_setting():
    ctx = keywords.context()
    assert "σεισμός" in ctx.terms and "enkaz altında" in ctx.terms
    assert any(g.key == "domain" for g in ctx.general)


def test_every_place_of_the_demo_regions_is_hinted_within_the_limit():
    # Test call 2026-10-26: Παιανία heard as "Πυρανία"; it was not in the hand-made list.
    data = keywords.load()
    terms = keywords.hinted_terms(data)
    assert "Παιανία" in terms and "Bornova" in terms and "Καρλόβασι" in terms
    assert keywords.size_chars(data, terms) < keywords.MAX_CHARS - keywords.MARGIN
    assert len(terms) == len(set(terms))


def test_the_area_streets_come_before_the_region_places_and_are_capped():
    data = keywords.load()
    streets = ["Βασιλίσσης Φρειδερίκης"] + [f"Οδός Δοκιμής {i}" for i in range(600)]
    terms = keywords.hinted_terms(data, streets)
    assert "Βασιλίσσης Φρειδερίκης" in terms and "Αθήνα" in terms  # the biggest places stay
    assert keywords.size_chars(data, terms) < keywords.MAX_CHARS - keywords.MARGIN
    assert sum(len(t) + 4 for t in terms if t.startswith("Οδός Δοκιμής")) <= keywords.STREETS_MAX_CHARS


def test_new_street_hints_reconnect_the_open_streams_once():
    from livekit.plugins import soniox

    class Stream:
        reasons = []

        def _request_reconnect(self, reason):
            self.reasons.append(reason)

    stt = keywords.StreetHintSTT(params=soniox.STTOptions(context=keywords.context()), api_key="test")
    stream = Stream()
    stt._live.add(stream)
    assert stt.use_streets(["Βασιλίσσης Φρειδερίκης"]) is True
    assert "Βασιλίσσης Φρειδερίκης" in stt._params.context.terms and len(Stream.reasons) == 1
    assert stt.use_streets(["Βασιλίσσης Φρειδερίκης"]) is False and len(Stream.reasons) == 1  # nothing new
