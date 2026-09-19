"""Whether a cited passage actually supports the claim made from it.

This is the one place in the project where a model judges a model, and the
tests are written to keep that contained: the verdicts are opinions, they
never touch `check_answer`, and nothing here is an eval grader. What is
tested exactly is everything around the judgement — which sentence gets
judged, against which passage, and what happens when the judge is wrong or
unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from policyforge.entail import (
    CONTRADICTED,
    ENTAILED,
    NEUTRAL,
    Unsupported,
    Verdict,
    get_entailer,
    unsupported_claims,
)
from policyforge.entail.base import cited_sentences


@dataclass
class FakeChunk:
    text: str


@dataclass
class FakePassage:
    chunk: FakeChunk


def _passages(*texts):
    return [FakePassage(FakeChunk(t)) for t in texts]


class FakeEntailer:
    """Returns a scripted verdict per (premise, hypothesis) pair."""

    def __init__(self, verdicts=None, default=ENTAILED):
        self.verdicts = verdicts or {}
        self.default = default
        self.calls: list[tuple[str, str]] = []

    def entails(self, premise, hypothesis):
        self.calls.append((premise, hypothesis))
        label = self.verdicts.get(premise, self.default)
        return Verdict(label=label, reason=f"scripted {label}")

    def check(self):
        return True


# --------------------------------------------------------------------------
# Which sentence is judged against which passage
# --------------------------------------------------------------------------


def test_a_trailing_citation_belongs_to_the_sentence_before_it():
    """The bug that made the first live run meaningless. The full stop lands
    before the marker, so a naive split hands the judge "[1]" and no claim —
    and it replies, reasonably, that no claim was supplied."""
    assert cited_sentences("The Officer approves certificates. [1]", 2) == [
        ("The Officer approves certificates.", [1])
    ]


def test_each_sentence_keeps_its_own_citations():
    assert cited_sentences("A is so. [1] B is so. [2][3]", 3) == [
        ("A is so.", [1]),
        ("B is so.", [2, 3]),
    ]


def test_an_uncited_sentence_is_not_judged():
    """`check_answer` already reports "makes claims without citing any
    passage" — a fact. Duplicating it with an opinion helps nobody."""
    assert cited_sentences("No citation here.", 2) == []


def test_markers_are_stripped_from_the_claim():
    """A judge shown "[2]" has been handed a token meaning nothing outside
    this tool, which can only distract from the sentence it must weigh."""
    assert cited_sentences("Inline [2] citation here.", 2) == [("Inline citation here.", [2])]


def test_a_citation_to_a_passage_that_does_not_exist_is_not_judged():
    """That is `check_answer`'s finding, and it is a fact."""
    assert cited_sentences("Out of range. [9]", 2) == []


# --------------------------------------------------------------------------
# The finding
# --------------------------------------------------------------------------


def test_a_supported_claim_produces_nothing():
    entailer = FakeEntailer(default=ENTAILED)

    assert (
        unsupported_claims("Records are retained. [1]", _passages("shall retain"), entailer) == []
    )


def test_an_unsupported_claim_is_reported_with_its_reason():
    """The measured case: the passage names IT Asset Management generating a
    certificate, the answer names the Security Officer approving one, and
    every deterministic check passes it."""
    entailer = FakeEntailer(default=NEUTRAL)

    found = unsupported_claims(
        "The Security Officer approves certificates. [1]",
        _passages("IT Asset Management shall generate certificates"),
        entailer,
    )

    assert len(found) == 1
    assert found[0].cited == [1]
    assert "scripted neutral" in str(found[0])


def test_one_supporting_passage_is_enough():
    """An answer may draw a claim from two documents and cite both, which is
    the behaviour the answering prompt asks for."""
    entailer = FakeEntailer({"first": NEUTRAL, "second": ENTAILED})

    found = unsupported_claims("A claim. [1][2]", _passages("first", "second"), entailer)

    assert found == []


def test_a_contradiction_outranks_a_neutral_in_the_report():
    """ "says otherwise" is a stronger finding than "says nothing about it",
    and burying it behind another passage's shrug would hide it."""
    entailer = FakeEntailer({"first": NEUTRAL, "second": CONTRADICTED})

    found = unsupported_claims("A claim. [1][2]", _passages("first", "second"), entailer)

    assert found[0].verdict.label == CONTRADICTED


def test_every_cited_passage_is_actually_consulted():
    entailer = FakeEntailer(default=NEUTRAL)

    unsupported_claims("A claim. [1][2]", _passages("first", "second"), entailer)

    assert [premise for premise, _ in entailer.calls] == ["first", "second"]


def test_an_empty_answer_is_not_a_finding():
    assert unsupported_claims("", _passages("a"), FakeEntailer()) == []


def test_the_finding_reads_as_a_sentence():
    finding = Unsupported("A claim.", [1, 2], Verdict(NEUTRAL, "the passage says otherwise"))

    assert "[1][2]" in str(finding)
    assert "the passage says otherwise" in str(finding)


# --------------------------------------------------------------------------
# The LLM judge
# --------------------------------------------------------------------------


class FakeProvider:
    def __init__(self, text='{"label": "entailed", "reason": "because"}', can_schema=True):
        self.text = text
        self.can_schema = can_schema
        self.calls: list[dict] = []

    def supports_schema(self):
        return self.can_schema

    def generate_json(self, **kwargs):
        from policyforge.llm.base import LLMResponse

        self.calls.append(kwargs)
        return LLMResponse(text=self.text, model="fake")


def _entailer(provider, **kw):
    from policyforge.entail.llm_entailer import LLMEntailer

    return LLMEntailer(provider=provider, **kw)


def test_the_verdict_is_constrained_to_three_labels():
    """A schema is what makes this tolerable rather than merely plausible:
    "Entailed.", "I'd say entailed" and a paragraph of hedging all become
    impossible."""
    provider = FakeProvider()

    _entailer(provider).entails("premise", "hypothesis")

    enum = provider.calls[0]["schema"]["json_schema"]["schema"]["properties"]["label"]["enum"]
    assert set(enum) == {ENTAILED, NEUTRAL, CONTRADICTED}


def test_the_passage_and_the_claim_both_reach_the_judge():
    provider = FakeProvider()

    _entailer(provider).entails("the passage text", "the claim text")

    assert "the passage text" in provider.calls[0]["prompt"]
    assert "the claim text" in provider.calls[0]["prompt"]


def test_the_reason_survives_onto_the_verdict():
    """A bare label is not actionable; naming what the passage says is."""
    provider = FakeProvider('{"label": "neutral", "reason": "names a different team"}')

    verdict = _entailer(provider).entails("p", "h")

    assert verdict.label == NEUTRAL
    assert verdict.reason == "names a different team"
    assert not verdict.supports


def test_a_model_that_cannot_be_held_to_a_schema_is_refused():
    """An unconstrained verdict is not worth having."""
    provider = FakeProvider(can_schema=False)

    with pytest.raises(RuntimeError, match="schema"):
        _entailer(provider).entails("p", "h")


def test_naming_no_model_is_refused():
    """Configuring this at all is a decision to use a *different* model than
    the one writing the answers."""
    from policyforge.entail.llm_entailer import LLMEntailer

    with pytest.raises(ValueError, match="other"):
        LLMEntailer(model=None)


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def test_entailment_is_off_unless_asked_for():
    assert get_entailer({"llm": {"provider": "anthropic"}}) is None
    assert get_entailer({"entail": {}}) is None


def test_an_unknown_provider_names_what_is_supported():
    with pytest.raises(ValueError, match="llm"):
        get_entailer({"entail": {"provider": "nonsense"}})


# --------------------------------------------------------------------------
# How many times the judge is asked
# --------------------------------------------------------------------------


def test_a_supported_sentence_stops_at_the_first_passage_that_carries_it():
    """Each call here is a model call on a second model, and the supported
    case is the common one. Judging all three citations before looking at
    the first verdict made the common case pay for the rare one."""
    judge = FakeEntailer(default=ENTAILED)

    findings = unsupported_claims(
        "Accounts are recertified quarterly [1][2][3].",
        _passages("first says so", "second says so", "third says so"),
        judge,
    )

    assert findings == []
    assert len(judge.calls) == 1
    assert judge.calls[0][0] == "first says so"


def test_it_keeps_asking_until_something_supports_the_sentence():
    """A passage that does not carry the claim does not end the search —
    the sentence is supported if *any* cited passage carries it."""
    judge = FakeEntailer({"silent": NEUTRAL}, default=ENTAILED)

    findings = unsupported_claims(
        "Accounts are recertified quarterly [1][2].", _passages("silent", "says so"), judge
    )

    assert findings == []
    assert len(judge.calls) == 2


def test_an_unsupported_sentence_is_still_judged_against_every_passage():
    """**The saving is only on the supported path, and that is required.**
    `worst` prefers a contradiction over a neutral, and it can only do that
    if every verdict was collected — stopping early here would bury a real
    contradiction behind whichever passage happened to be cited first."""
    judge = FakeEntailer({"silent": NEUTRAL, "disagrees": CONTRADICTED}, default=NEUTRAL)

    findings = unsupported_claims(
        "Accounts are recertified monthly [1][2].", _passages("silent", "disagrees"), judge
    )

    assert len(judge.calls) == 2, "every citation must be judged when none supports"
    assert len(findings) == 1
    assert findings[0].verdict.label == CONTRADICTED


def test_the_contradiction_is_reported_wherever_it_is_cited():
    """The same finding whichever order the passages are cited in, which is
    what "collect them all before choosing" buys."""
    judge = FakeEntailer({"silent": NEUTRAL, "disagrees": CONTRADICTED}, default=NEUTRAL)

    first = unsupported_claims(
        "Recertified monthly [1][2].", _passages("disagrees", "silent"), judge
    )
    second = unsupported_claims(
        "Recertified monthly [1][2].", _passages("silent", "disagrees"), judge
    )

    assert first[0].verdict.label == CONTRADICTED
    assert second[0].verdict.label == CONTRADICTED


def test_a_single_citation_costs_one_call_either_way():
    """The case that cannot be improved, pinned so a later refactor does
    not quietly make it worse."""
    for label in (ENTAILED, NEUTRAL, CONTRADICTED):
        judge = FakeEntailer(default=label)

        unsupported_claims("Quarterly [1].", _passages("only passage"), judge)

        assert len(judge.calls) == 1
