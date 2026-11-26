"""The eval caller answers the step the brain asked (eval/run.py next_line). No API calls."""
from eval.run import next_line


def case(**answers):
    return {"lang": "el", "answers": answers}


def test_it_answers_the_step_that_was_asked_once():
    c, used = case(house_number="Στο 12.", name="Νίκος Δοκιμάκης."), set()
    assert next_line(c, [], "name", used) == "Νίκος Δοκιμάκης."
    assert next_line(c, [], "house_number", used) == "Στο 12."
    assert next_line(c, [], "house_number", used) == "Στο 12."  # asked again: says it again
    assert next_line(c, [], "floor", used) == "Δεν ξέρω."  # nothing to say about that


def test_read_backs_get_a_yes_before_any_scripted_line():
    script = ["Όχι, δεν είπα φωτιά."]
    assert next_line(case(), script, "location_readback", set()) == "Ναι, σωστά." and script


def test_scripted_lines_fill_questions_without_an_answer():
    script = ["Πέντε ενήλικες έχουν πεθάνει."]
    assert next_line(case(people="5 κολόβριες."), script, "danger", set()) == "Πέντε ενήλικες έχουν πεθάνει."


def test_a_fixed_script_without_answers_works_as_before():
    script = ["Ναι, σωστά."]
    assert next_line({"lang": "el"}, script, "name", set()) == "Ναι, σωστά."
    assert next_line({"lang": "el"}, script, "name", set()) is None  # ran out: the caller hangs up
