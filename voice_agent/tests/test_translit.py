"""Greek names in Latin letters for callers who don't speak Greek (brain/translit.py), no API calls."""
from brain.translit import for_caller, to_latin


def test_street_names_in_latin_letters():
    for greek, latin in [("Ορλώφ", "Orlof"), ("Κουκάκι", "Koukaki"), ("Ερμού", "Ermou"), ("Αθηνάς", "Athinas"),
                         ("Φραγκιάδων", "Fragkiadon"), ("Καλλιρρόης", "Kallirrois"), ("Ευαγγελίστριας", "Evangelistrias"),
                         ("Αυλώνος", "Avlonos"), ("Μπουμπουλίνας", "Boumpoulinas"), ("Χαϊδάρι", "Chaidari"),
                         ("ΟΡΛΩΦ", "ORLOF")]:
        assert to_latin(greek) == latin


def test_the_english_demo_call_hears_no_greek():
    # Demo call 2026-10-30: "Εντάξει, Orlov 12, Κουκάκι." and "Did you mean Ορλώφ?" to an English caller.
    assert for_caller("Εντάξει, Orlov 12, Κουκάκι. What is your name?", "en") == "Okay, Orlov 12, Koukaki. What is your name?"
    assert for_caller("Did you mean Ορλώφ?", "en") == "Did you mean Orlof?"
    assert for_caller("Εντάξει, John. Let me confirm the location: Ορλώφ 12, Koukaki. Is that right?", "en") == \
        "Okay, John. Let me confirm the location: Orlof 12, Koukaki. Is that right?"


def test_turkish_and_french_callers_too():
    assert for_caller("Κατάλαβα. Ορλώφ 12 doğru mu?", "tr") == "Anladım. Orlof 12 doğru mu?"
    assert for_caller("Ναι, la rue Ορλώφ;", "fr") == "Oui, la rue Orlof;"


def test_greek_calls_and_whole_greek_sentences_are_left_alone():
    assert for_caller("Εντάξει, Ορλώφ 12, Κουκάκι. Πώς σας λένε;", "el") == "Εντάξει, Ορλώφ 12, Κουκάκι. Πώς σας λένε;"
    # The model answering wholly in Greek: Latin letters would be gibberish to the caller.
    assert for_caller("Πού βρίσκεστε;", "en") == "Πού βρίσκεστε;"
    assert for_caller("Where are you?", "en") == "Where are you?"
