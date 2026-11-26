"""Every place of Greece and Türkiye from GeoNames (brain/gazetteer.py), and the map check's
guess of a misheard place (places.closest_known). The kept file only, no network."""
from brain import gazetteer, places


def test_names_compare_by_sound_in_either_alphabet():
    assert gazetteer.sound("Παιανία") == gazetteer.sound("Peania") == "peania"
    assert gazetteer.sound("Αμπελόκηποι") == gazetteer.sound("Abelokipi")


def test_a_misheard_town_finds_the_real_one():
    # Test call 2026-10-26: speech-to-text heard Παιανία as "Πυρανία".
    assert gazetteer.closest("Πυρανία")["name"] == "Παιανία"
    assert gazetteer.closest("Πυρανία", near=(37.98, 23.73))["name"] == "Παιανία"  # within 60 km of Athens
    assert gazetteer.closest("Παιανία") is None  # heard right: nothing to suggest
    assert gazetteer.closest("Σεφεριχισάρ", country="TR")["name"] == "Seferihisar"


def test_far_places_are_left_out_near_a_known_city():
    near_thessaloniki = gazetteer.closest("Πυρανία", near=(40.64, 22.94), within_km=20)
    assert near_thessaloniki and near_thessaloniki["name"] != "Παιανία"  # Παιανία is 300 km away


def test_region_names_fit_the_budget_biggest_first():
    names = gazetteer.names_in((37.6, 38.4, 23.3, 24.2), 300)
    assert names[0] == "Αθήνα" and sum(len(n) + 4 for n in names) <= 300 and len(names) == len(set(names))


def test_the_map_check_guess_uses_every_place_not_only_the_demo_list():
    assert places.closest_known("Πυρανία") == "Παιανία"
    assert places.closest_known("Bayrakly, Izmir") == "Bayraklı"  # the demo list still comes first


def test_a_street_named_after_a_town_is_not_a_place():
    # _norm drops street words, so "Gazi Caddesi" looked like the town Gazi.
    assert gazetteer.is_place("Gazi") and not gazetteer.is_place("Gazi Caddesi")
    assert gazetteer.is_place("Πειραιά", inflected=True) and not gazetteer.is_place("Οδός Πειραιώς", inflected=True)


def test_a_short_name_in_the_accusative_is_a_place():
    # Test set 2026-11-15: "στη Σάμο" was not known as Σάμος, so the area was asked three times.
    assert gazetteer.is_place("Σάμο", inflected=True) and gazetteer.is_place("Βόλο", inflected=True)
    assert not gazetteer.is_place("Σάμο") and not gazetteer.is_place("δρόμο", inflected=True)
