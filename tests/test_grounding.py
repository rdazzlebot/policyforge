"""Whether a generated document's obligations trace back to its synthesis.

The two findings here are different kinds of claim and the tests are written
to keep them apart: an uncited obligation is a **fact** about the document
and may gate an exit code; a cited obligation its premise does not carry is a
model's **opinion** and may not. Nothing in this file consults a model.
"""

from __future__ import annotations

import pytest

from policyforge.content.grounding import (
    Claim,
    claims,
    judgeable,
    parse_synthesis,
    premises_for,
    unanchored,
)

SYNTHESIS = """\
- Accounts shall be reviewed quarterly. [NIST 800-53 AC-2]
- Privileged access shall be separately approved. [NIST 800-53 AC-6]
"""


def _document(*sections: str) -> str:
    return "\n\n".join(sections) + "\n"


# --------------------------------------------------------------------------
# Reading the two sides
# --------------------------------------------------------------------------


def test_a_synthesis_is_read_one_requirement_per_bullet():
    found = parse_synthesis(SYNTHESIS)

    assert [r.tags for r in found] == [("[NIST 800-53 AC-2]",), ("[NIST 800-53 AC-6]",)]


def test_a_requirement_containing_a_full_stop_stays_whole():
    """Parsed by bullet, not by sentence. A requirement may legitimately
    contain a full stop, and a fragment of one grounds nothing."""
    found = parse_synthesis("- Review accounts. Then approve them. [NIST 800-53 AC-2]\n")

    assert len(found) == 1
    assert "Then approve them" in found[0].text


def test_only_binding_sentences_become_claims():
    body = _document(
        "## 1. Access",
        "Accounts shall be reviewed quarterly. [NIST 800-53 AC-2]",
        "This section describes account review. [NIST 800-53 AC-2]",
    )

    found = claims(body)

    assert len(found) == 1, "a statement of fact is not a claim to ground"
    assert "shall be reviewed" in found[0].text


# --------------------------------------------------------------------------
# The join — the tag as an index, not as the assertion
# --------------------------------------------------------------------------


def test_a_claim_is_joined_to_every_requirement_sharing_a_tag():
    """A document sentence may merge two requirements and cite both. An
    exact tag-set match would miss that and report a grounded sentence as
    ungrounded, which is the direction that gets a check ignored."""
    requirements = parse_synthesis(SYNTHESIS)
    claim = Claim(text="…", line=1, tags=("[NIST 800-53 AC-2]", "[NIST 800-53 AC-6]"))

    assert len(premises_for(claim, requirements)) == 2


def test_a_claim_citing_something_the_synthesis_lacks_has_no_premise():
    requirements = parse_synthesis(SYNTHESIS)
    claim = Claim(text="…", line=1, tags=("[NIST 800-53 AU-6]",))

    assert premises_for(claim, requirements) == []


# --------------------------------------------------------------------------
# Unanchored: the fact, and the half that may gate
# --------------------------------------------------------------------------


def test_an_uncited_obligation_beside_cited_ones_is_reported():
    body = _document(
        "## 1. Access",
        "Accounts shall be reviewed quarterly. [NIST 800-53 AC-2]",
        "Reviewers shall retain evidence of each review for seven years.",
    )

    found = unanchored(body)

    assert len(found) == 1
    assert "seven years" in found[0].claim.text


def test_boilerplate_in_a_section_that_cites_nothing_is_not_reported():
    """**The half that gets skipped, and the one that decides whether this
    check survives contact with a real tree.** A Standard's own enforcement
    clause binds, carries no framework tag, and is entirely correct. A rule
    that reported it would be wrong on every document in the corpus."""
    body = _document(
        "## 1. Access",
        "Accounts shall be reviewed quarterly. [NIST 800-53 AC-2]",
        "## 2. Compliance and Enforcement",
        "Conformance with this Standard is mandatory.",
        "Exceptions must be approved in writing.",
    )

    assert unanchored(body) == []


def test_a_document_that_cites_nothing_anywhere_reports_nothing_here():
    """`check.py:_check_uncited` owns that case and states it as a fact about
    the whole document. Two checks reporting one defect teaches people to
    read neither."""
    body = _document(
        "## 1. Access",
        "Accounts shall be reviewed quarterly.",
        "Reviewers shall retain evidence.",
    )

    assert unanchored(body) == []


# --------------------------------------------------------------------------
# Cost, knowable before anything is spent
# --------------------------------------------------------------------------


def test_the_number_of_model_calls_is_countable_without_making_one():
    body = _document(
        "## 1. Access",
        "Accounts shall be reviewed quarterly. [NIST 800-53 AC-2]",
        "Privileged access shall be separately approved. [NIST 800-53 AC-6]",
        "Reviewers shall retain evidence of each review.",
    )

    pairs = judgeable(body, SYNTHESIS)

    assert len(pairs) == 2, "one per cited claim with a premise; the uncited one is free"


def test_a_cited_claim_with_no_premise_costs_nothing_and_is_not_judged():
    """Nothing to judge it against, so asking a model would be asking about
    the empty set. `_check_citations` already reports a tag mismatch."""
    body = _document(
        "## 1. Logging",
        "Logs shall be retained for one year. [NIST 800-53 AU-11]",
    )

    assert judgeable(body, SYNTHESIS) == []


# --------------------------------------------------------------------------
# Blocked on #205
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="#205: content.deontic splits sentences on [.!?], cutting through a "
    "dotted identifier like 164.308(a)(3)(i). The fragments land on the SAME "
    "line as the cited sentence, so an uncited obligation beside it inherits "
    "that line's tag and reads as anchored. The gate then reports nothing — "
    "it fails toward silence on exactly the frameworks that need it. Measured "
    "on the #164 probe: 0 unanchored today, 2 with the splitter fixed. "
    "Expected to XPASS when ba/deontic-dotted-citations lands.",
    strict=False,
)
def test_a_dotted_citation_does_not_lend_its_tag_to_the_sentence_after_it():
    body = _document(
        "## 1. Workforce",
        "Access shall be reviewed quarterly. [HIPAA Security Rule 164.308(a)(3)(i)]",
        "Reviewers shall retain evidence of each review for seven years.",
    )

    found = unanchored(body)

    assert len(found) == 1, "the second obligation cites nothing and must be reported"
    assert "seven years" in found[0].claim.text
