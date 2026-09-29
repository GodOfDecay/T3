"""`must_not_change` is the user's own wording (`modernization_common/verbatim.py`). Pure."""
from agents_orchestrator.modernization_common.verbatim import normalise, not_in_user_words

SAID = [
    "Hi. ClaimTrack is our claims system.",
    'Two things cannot change: the /api/v1 claims API brokers call, and the bank payment file (BACS Standard 18).',
    "Also the CR-4 quarterly return to the regulator must stay exactly as it is.",
]


def test_the_users_words_are_found_ignoring_case_spacing_and_quotes():
    assert not_in_user_words(['"The /api/v1 claims API brokers call"', "the bank payment file  (BACS Standard 18)",
                              "CR-4 quarterly return to the regulator."], SAID) == []


def test_a_paraphrase_is_not_the_users_words():
    assert not_in_user_words(["the claims API", "BACS payment files", "the CR-4 report"], SAID) == [
        "the claims API", "BACS payment files", "the CR-4 report"]


def test_a_paraphrase_that_happens_to_be_a_fragment_is_accepted_only_if_said():
    # A fragment of what was said IS the user's words; a rewording is not.
    assert not_in_user_words(["claims API brokers call"], SAID) == []
    assert not_in_user_words(["claims api used by brokers"], SAID) == ["claims api used by brokers"]


def test_nothing_said_means_nothing_matches():
    assert not_in_user_words(["the API"], []) == ["the API"]


def test_normalise():
    assert normalise('  “The  API.”  ') == "the api"


def test_whole_words_only():
    """Review finding 1: a plain substring let "api" match "rapid" and "port" match "report"."""
    said = ["We need rapid delivery of the quarterly report files."]
    assert not_in_user_words(["api delivery", "port files"], said) == ["api delivery", "port files"]
    assert not_in_user_words(["quarterly report files"], said) == []


def test_a_single_word_names_nothing_precisely_enough():
    assert not_in_user_words(["call", "API"], SAID) == ["call", "API"]
