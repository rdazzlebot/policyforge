"""A sentence citing the NIST AI RMF Playbook may say NIST suggests; never shall (#300).

The Playbook is voluntary (NIST: "Playbook suggestions are voluntary"). A
generated sentence that turns a suggestion into "must", and cites the
Playbook for it, asserts something NIST did not say. 80's ruling (A): a
Playbook-cited sentence never binds, whatever its subject; an obligation the
organization adopts goes in its own sentence, without the Playbook tag.

Measured before writing this ($0, local `qwen3:14b-pf`): on the prompts
before this change, 10 of 10 Playbook-cited sentences read "The organization
must ...". With the prompt rule, 9 of 9 read "NIST suggests ...".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from policyforge.content.check import ERROR, check_tree
from policyforge.content.deontic import analyze, playbook_obligations, weakened_citations
from policyforge.content.grounding import unanchored

TAG = "[NIST AI RMF Playbook Govern 1.1 Action 1]"


# --------------------------------------------------------------------------
# The check
# --------------------------------------------------------------------------


def test_nist_suggests_passes():
    """The passing case, and the form the prompt now asks for."""
    text = f"NIST suggests maintaining awareness of applicable legal requirements. {TAG}\n"

    assert playbook_obligations(text) == []


def test_an_obligation_citing_the_playbook_is_refused():
    text = f"The organization **must** maintain awareness of legal requirements. {TAG}\n"

    (found,) = playbook_obligations(text)
    assert "maintain awareness" in found.text


def test_the_organization_as_subject_is_still_refused():
    """Ruling (A): "whatever its subject". This presents NIST's suggestion
    as the organization's requirement just as "NIST requires" would."""
    text = f"Acme Health shall maintain an inventory of AI systems. {TAG}\n"

    assert len(playbook_obligations(text)) == 1


def test_a_citation_on_the_next_line_is_credited_to_the_sentence():
    """Generated Standards put the tag under the sentence; `deontic` credits
    it backwards, and the check must see it there."""
    text = f"The organization must maintain an AI inventory.\n{TAG}\n"

    assert len(playbook_obligations(text)) == 1


@pytest.mark.parametrize("phrase", ["needs to", "has to", "is expected to"])
def test_a_paraphrased_obligation_is_refused(phrase):
    """Obligations `classify` does not count as binding, added for this check
    only (#267: a phrase list alone misses paraphrase)."""
    text = f"The AI team {phrase} maintain an inventory of AI systems. {TAG}\n"

    assert len(playbook_obligations(text)) == 1


def test_a_paraphrase_outside_the_set_is_not_caught():
    """**The stated boundary**, per 80's ruling. "It is mandatory to" is an
    obligation this check does not recognise. Pinned so the gap is visible
    in the suite, not discovered."""
    text = f"It is mandatory to maintain an inventory of AI systems. {TAG}\n"

    assert playbook_obligations(text) == []


def test_other_frameworks_are_not_this_checks_business():
    text = "The organization must enforce approved authorizations. [NIST 800-53 AC-3]\n"

    assert playbook_obligations(text) == []


def test_citations_are_recorded_per_sentence():
    """The field the check reads, which `deontic` did not record before."""
    (statement,) = analyze(f"NIST suggests an inventory. {TAG}\n")

    assert statement.citations == (TAG,)
    assert statement.cites_the_playbook


# --------------------------------------------------------------------------
# The requirement-strength exemption, and its limit
# --------------------------------------------------------------------------


def test_the_correct_form_is_not_reported_as_a_weakened_citation():
    """Before #300, "NIST suggests ... [Playbook]" was cited and did not bind,
    so it warned as weakened, while "must ... [Playbook]" passed."""
    assert weakened_citations(f"NIST suggests an AI inventory. {TAG}\n") == []


def test_a_non_binding_sentence_citing_a_binding_source_still_warns():
    """The exemption is only for sentences whose EVERY citation is a
    Playbook tag (80). A binding source stays held to binding strength."""
    text = "Teams should consider enforcing authorizations. [NIST 800-53 AC-3]\n"

    assert len(weakened_citations(text)) == 1


# --------------------------------------------------------------------------
# A merged tag: a binding source beside the Playbook (80's second ruling)
# --------------------------------------------------------------------------

MIXED = "[NIST 800-53 CM-8 | NIST AI RMF Playbook Govern 1.6 Action 1]"


def test_a_mixed_tag_that_binds_is_not_an_error():
    """The binding source carries the obligation, so binding is correct."""
    text = f"The organization must maintain an inventory of system components. {MIXED}\n"

    assert playbook_obligations(text) == []
    assert weakened_citations(text) == []


def test_a_mixed_tag_is_mixed_whichever_reference_comes_first():
    """Split on `|` before deciding: with the Playbook reference first, the
    tag as a whole begins like a Playbook tag."""
    playbook_first = "[NIST AI RMF Playbook Govern 1.6 Action 1 | NIST 800-53 CM-8]"
    text = f"The organization must maintain an inventory of components. {playbook_first}\n"

    assert playbook_obligations(text) == []


def test_a_mixed_tag_that_does_not_bind_is_held_to_the_binding_source():
    """The exemption is for sentences citing ONLY the Playbook. Beside a
    binding source, a non-binding sentence still weakens that source."""
    text = f"NIST suggests maintaining an inventory of system components. {MIXED}\n"

    assert playbook_obligations(text) == []
    assert len(weakened_citations(text)) == 1


def test_only_playbook_tags_split_across_a_merged_tag_are_still_only_playbook():
    """Two Playbook references in one merged tag are still Playbook-only."""
    both = "[NIST AI RMF Playbook Govern 1.6 Action 1 | NIST AI RMF Playbook Govern 1.6 Action 2]"

    assert len(playbook_obligations(f"The organization must keep an inventory. {both}\n")) == 1


# --------------------------------------------------------------------------
# The adopted obligation, in its own sentence
# --------------------------------------------------------------------------


ADOPTED = (
    "# AI Governance Standard\n\n"
    "## Inventory\n\n"
    f"NIST suggests maintaining an inventory of AI systems. {TAG}\n\n"
    "Every AI system must be recorded in the inventory.\n\n"
    "The inventory must record each system's owner. [NIST 800-53 CM-8]\n"
)


def test_an_adopted_obligation_is_reported_as_unanchored_not_as_this():
    """**80's ruling, measured.** The organization's own requirement goes in
    its own sentence without the Playbook tag. This check leaves it alone,
    and `_check_unanchored` reports it -- correctly, since it is the
    organization's decision for a person to confirm, not NIST's."""
    assert playbook_obligations(ADOPTED) == []

    (finding,) = unanchored(ADOPTED)
    assert "recorded in the inventory" in finding.claim.text


def test_an_adoption_phrased_as_requires_is_reported_by_neither():
    """**A stated limit, found writing the test above.** "Acme Health
    requires ..." is not binding to `deontic` (must, shall, is required to),
    so `_check_unanchored` does not see it either. An adopted obligation
    phrased that way is checked by nothing -- pinned so it is known."""
    text = ADOPTED.replace(
        "Every AI system must be recorded", "Acme Health requires every AI system to be recorded"
    )

    assert playbook_obligations(text) == []
    assert unanchored(text) == []


# --------------------------------------------------------------------------
# Through the content check
# --------------------------------------------------------------------------


def _tree(tmp_path: Path, body: str) -> Path:
    doc = tmp_path / "standards" / "ai-governance.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\ntitle: AI Governance Standard\ntier: standard\nowner: AI Team\n---\n\n" + body,
        encoding="utf-8",
    )
    return tmp_path


def test_the_content_check_reports_it_as_an_error(tmp_path):
    report = check_tree(
        _tree(tmp_path, f"## A\n\nThe organization must keep an inventory. {TAG}\n")
    )

    playbook = [f for f in report.findings if "NIST AI RMF Playbook" in f.message]
    assert len(playbook) == 1
    assert playbook[0].severity == ERROR


def test_the_content_check_passes_the_correct_form(tmp_path):
    report = check_tree(_tree(tmp_path, f"## A\n\nNIST suggests keeping an inventory. {TAG}\n"))

    assert not [f for f in report.findings if "NIST AI RMF Playbook" in f.message]
    assert not [f for f in report.findings if "does not bind" in f.message or "weaken" in f.message]
