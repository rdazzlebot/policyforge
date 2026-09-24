"""NIST's own "must", quoted from an action the sentence cites, is not an obligation (#320).

#309's check refuses any binding word in a sentence citing only the Playbook.
Playbook Govern 1.7 Action 4 itself says "artifacts that must be preserved",
so a sentence faithfully restating the action it cites was a false ERROR. It
was the one of b5's 17 stored glm sentences still flagged after #319.

80's ruling: a binding word is exempt only inside a run of at least
`QUOTE_MIN_WORDS` (6) consecutive words that occurs verbatim, case-insensitive
and whitespace-normalised, in the text of a Playbook action the SAME sentence
cites, looked up in the shipped catalog. A paraphrase is still flagged.

The action text used here is the catalog's own, read in the test, so a
change to the catalog moves the cases rather than silently emptying them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from policyforge.content.deontic import QUOTE_MIN_WORDS, playbook_obligations

CATALOG = Path(__file__).resolve().parent.parent / "data" / "frameworks" / "nist-ai-rmf-playbook"
CITES_1_7_4 = "[NIST AI RMF Playbook Govern 1.7 Action 4]"
CITES_1_4_1 = "[NIST AI RMF Playbook Govern 1.4 Action 1]"


def _action(action_id: str) -> str:
    rows = json.loads((CATALOG / "controls.json").read_text(encoding="utf-8"))
    return next(
        e["description"]
        for r in rows
        for e in r["enhancements"]
        if e["enhancement_id"] == action_id
    )


def _flagged(sentence: str, tag: str) -> bool:
    return len(playbook_obligations(f"{sentence} {tag}\n")) == 1


def test_the_cases_below_are_built_from_the_catalogs_own_wording():
    """The premise, measured: Action 4 carries the phrase the cases quote."""
    assert "artifacts that must be preserved for fulsome understanding" in _action(
        "Govern 1.7 Action 4"
    )
    assert QUOTE_MIN_WORDS == 6


def test_a_six_word_quote_from_the_cited_action_passes():
    # "artifacts that must be preserved for" -- six words, verbatim.
    assert not _flagged(
        "NIST suggests listing artifacts that must be preserved for audits.", CITES_1_7_4
    )


def test_a_five_word_quote_fails():
    # "that must be preserved for" -- five: "records" is not "artifacts".
    assert _flagged("NIST suggests listing records that must be preserved for audits.", CITES_1_7_4)


def test_the_same_quote_fails_when_the_action_is_not_cited():
    """Verbatim from the Playbook is not enough; from a CITED action is."""
    sentence = "NIST suggests listing artifacts that must be preserved for audits."
    assert _flagged(sentence, CITES_1_4_1)


def test_a_paraphrased_must_fails():
    assert _flagged(
        "NIST suggests policies for artifacts that must be kept to understand the system.",
        CITES_1_7_4,
    )


def test_a_six_word_run_in_no_cited_action_fails():
    """1d's case: six words of the right length, carrying "must", but not
    NIST's -- so the match is against the action text, not a word count."""
    assert _flagged("NIST suggests that all model records must be kept on file.", CITES_1_7_4)


def test_a_must_outside_the_quoted_run_still_binds():
    """The exemption covers the quoted words only, not the sentence."""
    assert _flagged(
        "NIST suggests policies for artifacts that must be preserved for fulsome "
        "understanding, and the organization must log each one.",
        CITES_1_7_4,
    )


def test_the_quote_is_case_and_whitespace_insensitive():
    assert not _flagged(
        "NIST suggests listing ARTIFACTS  that\tmust be Preserved FOR audits.", CITES_1_7_4
    )


def test_a_merged_tag_naming_the_action_counts_as_citing_it():
    tag = "[NIST AI RMF Playbook Govern 1.7 Action 1 | NIST AI RMF Playbook Govern 1.7 Action 4]"
    assert not _flagged("NIST suggests listing artifacts that must be preserved for audits.", tag)


@pytest.mark.parametrize(
    "sentence",
    [
        # The exemption is only for the binding check; the subject rule is unchanged.
        "The organization lists artifacts that must be preserved for fulsome understanding.",
        "NIST requires artifacts that must be preserved for fulsome understanding.",
    ],
)
def test_quoting_nist_does_not_excuse_the_wrong_subject(sentence):
    assert _flagged(sentence, CITES_1_7_4)
