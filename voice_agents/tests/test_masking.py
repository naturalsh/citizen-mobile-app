import pytest

from brain.masking import Masker


@pytest.mark.parametrize(
    "text, hidden, visible",
    [
        # Greek
        ("Είμαι στους Αμπελοκήπους, Μιχαήλ Μελά 13", ["Μελά 13"], ["Αμπελοκήπους"]),
        ("I'm in Belokipos, Michail Mela 13.", ["Mela 13"], ["Belokipos"]),
        ("Είμαι στο Βαθύ, οδός Θεμιστοκλέους 5, δίπλα στο φαρμακείο", ["Θεμιστοκλέους 5"], ["Βαθύ", "φαρμακείο"]),
        ("στην οδό Λογοθέτη 40 έπεσε ένας τοίχος", ["Λογοθέτη 40"], ["έπεσε"]),
        ("Θεμιστοκλέους 5, η μητέρα μου είναι στα συντρίμμια", ["Θεμιστοκλέους 5"], ["μητέρα"]),
        ("Με λένε Μαρία Παπαδοπούλου", ["Μαρία Παπαδοπούλου"], []),
        ("Είμαστε 3 άτομα", [], ["Είμαστε 3"]),
        # Turkish
        ("İzmir Bayraklı Manas Bulvarı 12, bina çöktü", ["Manas Bulvarı 12"], ["Bayraklı", "İzmir"]),
        ("Atatürk Caddesi No: 5 önündeyim", ["Atatürk Caddesi No: 5"], []),
        ("Adım Mehmet Yılmaz", ["Mehmet Yılmaz"], []),
        ("TC kimlik 12345678901", ["12345678901"], ["kimlik"]),
        # English / French / tourists
        ("I'm at 12 Main Street with my kids", ["12 Main Street"], ["kids"]),
        ("The block at Themistokleous 5 collapsed", ["Themistokleous 5"], ["collapsed"]),
        ("My name is John Smith", ["John Smith"], []),
        ("Je m'appelle Claire Dubois, 5 rue des Lilas", ["Claire Dubois", "rue des Lilas"], []),
        # Numbers and e-mail
        ("call me on +30 690 123 4567 or 6901234567", ["+30 690 123 4567", "6901234567"], []),
        ("write to maria.p@example.com", ["maria.p@example.com"], []),
    ],
)
def test_mask_hides_details_and_keeps_context(text, hidden, visible):
    m = Masker()
    masked = m.mask(text)
    for h in hidden:
        assert h not in masked, masked
    for v in visible:
        assert v in masked, masked
    assert m.unmask(masked) == text


def test_answer_to_name_question():
    assert Masker().mask("Ayşe Demir", expecting="name") == "<PERSON_1>"
    assert Masker().mask("Μαρία Παπαδοπούλου.", expecting="name") == "<PERSON_1>."
    # Not after a name question: left alone
    assert Masker().mask("Ayşe Demir") == "Ayşe Demir"


@pytest.mark.parametrize("answer, name", [
    ("Εε, Δοκιμάκης...", "Δοκιμάκης"), ("εε Μαρία Δοκιμάκη", "Μαρία Δοκιμάκη"), ("Iı, Ayşe Deneme", "Ayşe Deneme"),
    ("Ehm, John Testman.", "John Testman"),
])
def test_hesitation_before_a_name_is_not_part_of_it(answer, name):
    # From a live test call: "Εε, Πολιτόπουλος" became the caller's name.
    m = Masker()
    masked = m.mask(answer, expecting="name")
    assert "<PERSON_1>" in masked and m.unmask("<PERSON_1>") == name


@pytest.mark.parametrize("answer", ["Ναι", "Ναι, σωστά.", "Είμαστε δύο.", "Evet", "Oui, c'est correct.", "No", "maria papadopoulou"])
def test_answers_that_are_not_names(answer):
    # The caller answered something else after "what is your name?"; don't turn it into a name.
    # (A lower-case name is not caught either; see masking.py.)
    assert Masker().mask(answer, expecting="name") == answer


def test_turkish_dotted_i_is_masked_again_later():
    m = Masker()
    m.mask("İnönü Caddesi No 33")
    assert m.mask_known("Adres: İnönü Caddesi No 33") == "Adres: <ADDRESS_1>"


def test_same_value_same_placeholder_and_reused_later():
    m = Masker()
    first = m.mask("Με λένε Μαρία Παπαδοπούλου")
    later = m.mask("Ναι, η Μαρία Παπαδοπούλου είμαι")
    assert "<PERSON_1>" in first and "<PERSON_1>" in later
    assert "Μαρία" not in later


def test_unmask_model_output_and_report():
    m = Masker()
    m.mask("Θεμιστοκλέους 5")
    m.mask("Μαρία Παπαδοπούλου", expecting="name")
    reply = "Βρίσκεστε στη <ADDRESS_1>, Βαθύ, και λέγεστε < PERSON 1 >. Σωστά;"
    assert m.unmask(reply) == "Βρίσκεστε στη Θεμιστοκλέους 5, Βαθύ, και λέγεστε Μαρία Παπαδοπούλου. Σωστά;"
    report = {"caller_name": "<PERSON_1>", "people": [{"note": "<PERSON_1>'s mother"}], "count": 3}
    assert m.unmask_obj(report) == {"caller_name": "Μαρία Παπαδοπούλου", "people": [{"note": "Μαρία Παπαδοπούλου's mother"}], "count": 3}


def test_a_placeholder_the_model_invented_is_never_read_out():
    # From an eval run: the read-back said "με όνομα <PERSON_1>" for a name we never masked.
    m = Masker()
    assert m.unmask("Με όνομα <PERSON_1>, σωστά;") == "Με όνομα, σωστά;"
    assert m.unmask("<PERSON_1>") == ""
    assert m.unmask("Οδός <ADDRESS_1> ") == "Οδός "  # streamed piece: trailing space kept


def test_a_corrected_name_at_the_read_back_is_masked_too():
    # Eval: "Αιγέας Δοκιμάκης" corrected a misheard "Αγίας Δοκιμάκης" while the agent was reading back,
    # and went to the model unmasked because nobody had just asked for the name.
    m = Masker()
    m.mask("Με λένε Αγίας Δοκιμάκης.", expecting="name")
    masked = m.mask("Αιγέας Δοκιμάκης.", expecting="other")
    assert "Αιγέας" not in masked and "<PERSON_" in masked
    assert m.mask("Νέα Σμύρνη.", expecting="other") == "Νέα Σμύρνη."  # a place is not a name


def test_a_street_with_a_street_word_or_a_number_after_a_location_question_is_masked():
    # Eval 2026-10-25: "στην οδό Ορλώφ" and "Ορλώφ 12" (an indeclinable name) reached the model.
    m = Masker()
    assert "Ορλώφ" not in m.mask("Είμαι στην Αθήνα, στην οδό Ορλώφ.", "location")
    assert "Ορλώφ" not in m.mask("Είμαι στην Αθήνα, Ορλώφ 12.", "location")
    assert m.mask("Στο 12.", "location") == "Στο 12."  # a number alone, after "what number?"
    assert m.mask("Είμαστε 3.", "location") == "Είμαστε 3."
    assert m.mask("Είμαστε 3 άτομα στην Αθήνα.", "other") == "Είμαστε 3 άτομα στην Αθήνα."  # only after a location question


def test_a_street_said_alone_after_which_street_is_masked_but_the_area_stays():
    # Eval 2026-10-26: "Στην Ορλώφ." after "which street?" reached the model.
    m = Masker()
    assert m.mask("Στην Ορλώφ. Έπιασε φωτιά ένα κτίριο.", "street", "Koukaki, Athens Κουκάκι, Αθήνα") == \
        "Στην <ADDRESS_1>. Έπιασε φωτιά ένα κτίριο."
    assert m.mask("Στην Αθήνα, στο Κουκάκι.", "street", "Κουκάκι, Αθήνα") == "Στην Αθήνα, στο Κουκάκι."


def test_in_an_answer_to_which_street_every_name_is_the_street_except_places_given():
    m = Masker()
    known = "Koukaki, Athens Κουκάκι Αθήνα Ακρόπολη"
    assert m.mask("Ορλώφ, στο Κουκάκι.", "street", known) == "<ADDRESS_1>, στο Κουκάκι."
    assert m.mask("Έπιασε φωτιά στην Ορλώφ.", "street", known) == "Έπιασε φωτιά στην <ADDRESS_1>."  # not the verb
    assert m.mask("Δεν ξέρω, κοντά στην Ακρόπολη.", "street", known) == "Δεν ξέρω, κοντά στην Ακρόπολη."


def test_a_real_street_of_the_area_is_masked_wherever_it_is_said():
    # With the area's street list (OpenStreetMap), however the caller phrases it.
    m = Masker()
    streets = frozenset({"orlof", "athanasiou diakou", "diakou"})
    assert m.mask("Είμαι στην Αθήνα, στην Ορλώφ, κοντά στην Ακρόπολη.", "location", "Athens", streets) == \
        "Είμαι στην Αθήνα, στην <ADDRESS_1>, κοντά στην Ακρόπολη."
    assert "Διάκου" not in m.mask("Μένω πάνω από τον φούρνο της Διάκου.", "other", "", streets)
    assert m.mask("Είμαστε τρεις.", "other", "", streets) == "Είμαστε τρεις."


def test_a_street_in_the_opening_sentence_is_masked_but_places_stay():
    # Eval 2026-10-26: "… στην Αθήνα, στην Ορλώφ, κοντά στην Ακρόπολη." sent Ορλώφ to the model.
    m = Masker()
    said = m.mask("Βγαίνει καπνός από μια πολυκατοικία στην Αθήνα, στην Ορλώφ, κοντά στην Ακρόπολη.", "opening")
    assert "Ορλώφ" not in said and "Αθήνα" in said and "Ακρόπολη" in said
    assert m.mask("Σεισμός στο Βαθύ Σάμου, στον Πειραιά.", "opening") == "Σεισμός στο Βαθύ Σάμου, στον Πειραιά."
    assert m.mask("Έπεσε ένας τοίχος στον δρόμο.", "opening") == "Έπεσε ένας τοίχος στον δρόμο."


def test_a_texted_list_answer_masks_the_name_and_streets_line_by_line():
    m = Masker()
    said = m.mask("1. Φωτιά στην κουζίνα\n2. Ορλώφ 12, Κουκάκι\n3. Δύο άτομα\n4. Νίκος Δοκιμάκης", "form")
    assert said == "1. Φωτιά στην κουζίνα\n2. <ADDRESS_1> 12, Κουκάκι\n3. Δύο άτομα\n4. <PERSON_1>"
    assert m.form_name == "Νίκος Δοκιμάκης"
    said = Masker().mask("Yangın var. Atatürk Caddesi 5, Bayraklı, İzmir. Adım Ayşe Deneme", "form")
    assert "Ayşe" not in said and "Atatürk" not in said and "Bayraklı" in said


def test_a_street_word_with_a_two_word_name_and_number_is_one_address():
    # Test set 2026-11-15: "οδός Αγίου Νικολάου 12" was masked as "οδός Αγίου" and "Νικολάου 12", the
    # report's street became "Νικολάου 12", and the caller's surname Νικολάου was then masked as a street.
    m = Masker()
    assert m.mask("Στο Καρλόβασι της Σάμου, οδός Αγίου Νικολάου 12.", "location") == "Στο Καρλόβασι της Σάμου, <ADDRESS_1>."
    assert m.unmask("<ADDRESS_1>") == "οδός Αγίου Νικολάου 12"
    assert m.mask("Γιώργος Νικολάου.", "name") == "<PERSON_1>."


def test_english_i_is_not_a_street():
    # Test set 2026-11-15: after "What street are you on?", "I'm" was masked as the street, recorded
    # as it, and the caller heard "I'm, Ampelokipoi, Athens. Is that right?" five times.
    m = Masker()
    said = m.mask("Oh no, not Kifisia actually, I'm in Belokipos, Michail Mela 13.", "street", places="Kifisia")
    assert "I'm in" in said and "Mela" not in said and "Belokipos" not in said
    assert "I'm" not in m.values("ADDRESS")


@pytest.mark.parametrize("answer", ["Bilmiyorum.", "Hatırlamıyorum", "Δεν ξέρω.", "I don't know.", "Je ne sais pas."])
def test_i_dont_know_is_not_a_street(answer):
    # Test set 2026-11-15: "Bilmiyorum." to the street question was masked as a street and read back
    # as "Şirinyer, Bilmiyorum, Gazi Caddesi No 18".
    for asked in ("street", "form"):
        m = Masker()
        assert m.mask(answer, asked) == answer and m.values("ADDRESS") == []
    assert Masker().mask("Atatürk.", "street") == "<ADDRESS_1>."  # a one-word street is still masked


def test_i_dont_know_is_not_a_name_and_two_towns_stay_visible():
    # Test set 2026-11-16: "Bilmiyorum." after the name question became the caller's name, and "Buca"
    # in "İzmir Buca, Şirinyer, Gazi Caddesi No 18" was masked and recorded as the street.
    m = Masker()
    assert m.mask("Bilmiyorum.", "name") == "Bilmiyorum." and m.values("PERSON") == []
    m = Masker()
    said = m.mask("İzmir Buca, Şirinyer, Gazi Caddesi No 18. Ben ve komşum, iki kişiyiz.", "form")
    assert said.startswith("İzmir Buca, Şirinyer, <ADDRESS_1>.") and m.values("ADDRESS") == ["Gazi Caddesi No 18"]
