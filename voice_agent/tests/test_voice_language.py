"""Spoken language switching rules, no API calls."""
from voice.language import LanguageTracker


def turn(tracker, *sentences):
    for text, lang in sentences:
        tracker.heard(text, lang)
    return tracker.decide()


def test_no_label_keeps_the_current_language():
    assert turn(LanguageTracker("el")) == "el"
    assert turn(LanguageTracker("el"), ("...", None)) == "el"


def test_long_sentence_switches_language():
    t = LanguageTracker("el")
    assert turn(t, ("Merhaba, Bayraklı'da bina çöktü", "tr")) == "tr"
    assert t.current == "tr"


def test_short_answer_never_switches():
    t = LanguageTracker("el")
    assert turn(t, ("OK", "en")) == "el"
    assert turn(t, ("Evet", "tr")) == "el"


def test_letters_add_up_within_one_turn():
    t = LanguageTracker("el")
    assert turn(t, ("Yangın var", "tr"), ("evimin yanında", "tr")) == "tr"


def test_majority_language_of_the_turn_wins():
    t = LanguageTracker("tr")
    assert turn(t, ("Είμαι στο Βαθύ της Σάμου", "el"), ("OK", "en")) == "el"


def test_region_codes_are_normalised():
    assert turn(LanguageTracker("el"), ("Bonjour, il y a un incendie", "fr-FR")) == "fr"


def test_unsupported_language_needs_two_long_turns():
    t = LanguageTracker("el")
    assert turn(t, ("Hallo, es gibt ein Feuer hier", "de")) == "el"
    assert turn(t, ("Bitte helfen Sie uns schnell", "de")) == "de"  # the brain hands off


def test_supported_turn_resets_the_unsupported_count():
    t = LanguageTracker("el")
    turn(t, ("Hallo, es gibt ein Feuer hier", "de"))
    turn(t, ("Είμαστε τρεις άνθρωποι εδώ", "el"))
    assert turn(t, ("Bitte helfen Sie uns schnell", "de")) == "el"


def test_the_callers_first_words_decide_with_fewer_letters():
    # Test call 2026-10-26: a Turkish caller's "Merhaba." (7 letters) kept the call in Greek.
    t = LanguageTracker("el")
    assert turn(t, ("Merhaba.", "tr")) == "tr"
    t = LanguageTracker("el")
    assert turn(t, ("Ναι", "el")) == "el" and turn(t, ("Merhaba.", "tr")) == "el"  # later: needs more


def test_short_sentences_in_the_same_language_add_up_over_turns():
    t = LanguageTracker("el")
    turn(t, ("Ναι", "el"))
    assert turn(t, ("Merhaba.", "tr")) == "el"
    assert turn(t, ("Nasılsın?", "tr")) == "tr"  # 7 + 8 letters


def test_the_letters_beat_a_wrong_label():
    # Test call 2026-10-26: speech-to-text labelled "İzmir'deyim" and "Evim yıkıldı" as English.
    t = LanguageTracker("en")
    assert turn(t, ("İzmir'deyim, evim yıkıldı.", "en")) == "tr"


def test_mixed_first_words_dont_switch():
    # "No, I— I connect. Merhaba" switched a Turkish link's call to English.
    t = LanguageTracker("tr")
    assert turn(t, ("No, I I connect.", "en"), ("Merhaba", "tr")) == "tr"
