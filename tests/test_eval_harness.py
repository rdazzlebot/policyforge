"""The eval harness's own grading, tested without an API key.

A harness whose scoring is wrong is worse than no harness: it produces
numbers that look like evidence. So the grading logic is graded here, with
scripted providers, and only the *running* of it needs a model.

The property that matters most is that flaky is not passing. A case right
seven times in eight is indistinguishable from a case right always if you
only look once, and looking only once is the mistake that shipped a routing
bug.
"""

from __future__ import annotations

from dataclasses import dataclass

from evals.runner import (
    CaseResult,
    Outcome,
    format_report,
    grade_text,
    load_cases,
    run_case,
)


@dataclass
class R:
    text: str
    model: str = "fake"


class Scripted:
    """Returns replies in order, cycling once exhausted."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies) or [""]
        self.n = 0

    def generate(self, **kwargs):
        reply = self.replies[min(self.n, len(self.replies) - 1)]
        self.n += 1
        return R(reply)


# --------------------------------------------------------------------------
# The shared checks
# --------------------------------------------------------------------------


def test_a_required_term_that_is_missing_fails():
    result = grade_text("nothing relevant", {"must_contain": ["quarterly"]})

    assert not result.passed
    assert "quarterly" in result.detail


def test_a_forbidden_term_that_is_present_fails():
    """The negative checks are the ones that catch invention."""
    result = grade_text("review every 90 days", {"must_not_contain": ["90"]})

    assert not result.passed


def test_any_of_needs_only_one():
    case = {"must_contain_any": ["privileged", "entitlement"]}

    assert grade_text("privileged access review", case).passed
    assert not grade_text("something else entirely", case).passed


def test_checks_are_case_insensitive():
    assert grade_text("QUARTERLY", {"must_contain": ["quarterly"]}).passed


# --------------------------------------------------------------------------
# Counting runs
# --------------------------------------------------------------------------


def test_a_case_right_every_time_is_not_flaky():
    result = CaseResult("routing", "x", [Outcome(True), Outcome(True)])

    assert result.rate == 1.0
    assert not result.flaky


def test_a_case_right_sometimes_is_flaky_not_passing():
    """The whole reason this harness exists. Seven of eight looks like a
    pass if you only ever run once."""
    result = CaseResult("routing", "x", [Outcome(True)] * 7 + [Outcome(False, "empty")])

    assert result.flaky
    assert result.rate < 1.0
    assert result.passes == 7


def test_a_case_never_right_is_not_flaky_either():
    result = CaseResult("routing", "x", [Outcome(False), Outcome(False)])

    assert not result.flaky
    assert result.rate == 0.0


def test_every_run_happens_even_when_one_raises():
    class Exploding:
        def generate(self, **kwargs):
            raise RuntimeError("boom")

    result = run_case("routing", {"question": "q", "expect": "coverage"}, Exploding(), repeat=3)

    assert result.runs == 3, "one bad run must not abandon the rest"
    assert result.passes == 0


# --------------------------------------------------------------------------
# The suites
# --------------------------------------------------------------------------


def test_routing_grades_the_chosen_skill():
    passing = run_case("routing", {"question": "q", "expect": "coverage"}, Scripted("coverage"))
    failing = run_case("routing", {"question": "q", "expect": "coverage"}, Scripted("drift"))

    assert passing.rate == 1.0
    assert failing.rate == 0.0
    assert "expected 'coverage'" in failing.failures[0].detail


def test_resolution_grades_whether_a_rewrite_happened():
    case = {
        "history": [{"q": "what is our access review cadence?", "a": "Quarterly."}],
        "question": "who owns that?",
        "rewritten": True,
        "must_contain": ["access review"],
    }

    good = run_case("resolution", case, Scripted("who owns the access review cadence?"))
    assert good.rate == 1.0

    # Returned unchanged, so no rewrite happened.
    bad = run_case("resolution", case, Scripted(""))
    assert bad.rate == 0.0
    assert "expected the opposite" in bad.failures[0].detail


def test_expansion_fails_when_the_model_invents_a_frequency():
    case = {
        "question": "how often do we check who has admin?",
        "must_contain_any": ["privileged"],
        "must_not_contain": ["quarterly"],
    }

    assert run_case("expansion", case, Scripted("privileged access, entitlements")).rate == 1.0
    assert run_case("expansion", case, Scripted("privileged access, quarterly")).rate == 0.0


def test_answering_fails_an_answer_that_cites_nothing():
    case = {
        "documents": [
            {
                "title": "Access Control Standard",
                "body": (
                    "# A\n\n## 4.1 Account Review\n\n"
                    "Account entitlements are recertified quarterly. [NIST AC-2]\n\n"
                    "## 4.2 Privileged Access\n\nAdmin credentials need tokens.\n"
                ),
            }
        ],
        "question": "how often are accounts recertified?",
        "expect_refusal": False,
    }

    assert run_case("answering", case, Scripted("Quarterly. [1]")).rate == 1.0

    uncited = run_case("answering", case, Scripted("Quarterly."))
    assert uncited.rate == 0.0
    assert "no citation" in uncited.failures[0].detail


def test_answering_runs_the_projects_own_integrity_checks():
    """A fabricated citation is a failure here for exactly the reason it is
    a warning in production."""
    case = {
        "documents": [
            {
                "title": "Access Control Standard",
                "body": (
                    "# A\n\n## 4.1 Account Review\n\n"
                    "Account entitlements are recertified quarterly. [NIST AC-2]\n\n"
                    "## 4.2 Privileged Access\n\nAdmin credentials need tokens.\n"
                ),
            }
        ],
        "question": "how often are accounts recertified?",
        "expect_refusal": False,
    }

    result = run_case("answering", case, Scripted("Quarterly. [9]"))

    assert result.rate == 0.0
    assert "integrity" in result.failures[0].detail


def test_a_case_whose_retrieval_does_not_match_blames_the_case():
    """If the passages are not what the case assumed, the case is wrong and
    should say so rather than reporting the model failed."""
    case = {
        "documents": [{"title": "T", "body": "# T\n\n## S\n\nText about backups.\n"}],
        "question": "anything",
        "expect_passages": 5,
    }

    result = run_case("answering", case, Scripted("x"))

    assert "the case, not the model, is wrong" in result.failures[0].detail


# --------------------------------------------------------------------------
# The shipped cases
# --------------------------------------------------------------------------


def test_the_shipped_cases_load_and_are_well_formed():
    cases = load_cases()

    assert set(cases) == {"routing", "resolution", "expansion", "answering"}
    for suite, rows in cases.items():
        assert rows, f"{suite} has no cases"
        for case in rows:
            assert case.get("name"), f"unnamed case in {suite}"
            assert case.get("question"), f"{case.get('name')} asks nothing"


def test_routing_cases_include_questions_that_must_not_route():
    """A router that hijacks ordinary document questions has made the shell
    worse, so the negative cases have to exist."""
    negatives = [c for c in load_cases()["routing"] if c["expect"] == "documents"]

    assert len(negatives) >= 3


def test_the_report_calls_out_flaky_cases_separately_from_failures():
    results = [
        CaseResult("routing", "always", [Outcome(True), Outcome(True)]),
        CaseResult("routing", "sometimes", [Outcome(True), Outcome(False, "empty")]),
        CaseResult("routing", "never", [Outcome(False, "bad"), Outcome(False, "bad")]),
    ]

    report = format_report(results, repeat=2)

    assert "FLAKY" in report
    assert "1 never passed" in report
    assert "1 flaky" in report


# --------------------------------------------------------------------------
# Attribution: the failure the integrity checks structurally cannot see
# --------------------------------------------------------------------------


def _two_passages():
    from evals.runner import _passages

    return _passages(
        {
            "documents": [
                {
                    "title": "Access Control Standard",
                    "body": (
                        "# A\n\n## 4.1 Account Review\n\n"
                        "Account entitlements are recertified quarterly. [NIST AC-2]\n"
                    ),
                },
                {
                    "title": "Backup and Restore Standard",
                    "body": (
                        "# B\n\n## 4.1 Restore Testing\n\n"
                        "Restore drills happen twice a year. [NIST CP-9]\n"
                    ),
                },
            ],
            "question": "x",
            "retrieve": "account recertification and restore drill testing",
        }
    )


def _rules(passages):
    """Claims keyed to whichever passage number actually holds them."""
    return [
        {"claim": "quarterly", "from": "Access Control Standard"},
        {"claim": "twice a year", "from": "Backup and Restore Standard"},
    ]


def _number_of(passages, title):
    return next(n for n, p in enumerate(passages, start=1) if p.document.title == title)


def test_a_correctly_attributed_answer_passes():
    from evals.runner import check_attribution

    passages = _two_passages()
    access = _number_of(passages, "Access Control Standard")
    backup = _number_of(passages, "Backup and Restore Standard")
    text = f"Recertified quarterly [{access}]. Restores are tested twice a year [{backup}]."

    assert check_attribution(text, passages, _rules(passages)) == ""


def test_a_swapped_citation_is_caught():
    """An answer that credits a real passage for the wrong claim passes every
    integrity check and is wrong in the way that matters: the reader who
    follows the citation finds nothing there."""
    from evals.runner import check_attribution

    passages = _two_passages()
    access = _number_of(passages, "Access Control Standard")
    backup = _number_of(passages, "Backup and Restore Standard")
    text = f"Recertified quarterly [{backup}]. Restores are tested twice a year [{access}]."

    detail = check_attribution(text, passages, _rules(passages))

    assert "quarterly" in detail
    assert "comes from" in detail


def test_the_existing_integrity_checks_do_not_catch_a_swap():
    """The reason this grader exists at all."""
    from policyforge.zardoz.answer import check_answer

    passages = _two_passages()
    access = _number_of(passages, "Access Control Standard")
    backup = _number_of(passages, "Backup and Restore Standard")
    text = f"Recertified quarterly [{backup}]. Restores are tested twice a year [{access}]."

    _, warnings = check_answer(text, passages)

    assert warnings == [], "check_answer sees a valid citation and stops there"


def test_a_claim_stated_with_no_citation_is_caught():
    from evals.runner import check_attribution

    passages = _two_passages()
    backup = _number_of(passages, "Backup and Restore Standard")
    text = f"Recertified quarterly. Restores are tested twice a year [{backup}]."

    assert "no citation" in check_attribution(text, passages, _rules(passages))


def test_a_claim_never_stated_is_caught():
    from evals.runner import check_attribution

    passages = _two_passages()

    detail = check_attribution("Nothing relevant [1].", passages, _rules(passages))

    assert "never states" in detail


def test_no_attribution_rules_means_no_attribution_check():
    from evals.runner import check_attribution

    assert check_attribution("anything at all", _two_passages(), None) == ""
