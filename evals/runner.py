"""Grading Zardoz's prompts against a real model, repeatably.

Everything else in this repository is tested against fixtures, which is
right: fixtures are fast, free, and answer the same way every time. But four
things here are prompts, and a prompt cannot be tested that way. Whether the
answerer refuses when the passages do not support a claim, whether the
router picks the right analysis, whether the rewriter invents a detail — all
of that is a property of a model's behaviour, and the only way to know it is
to ask the model.

**One run is not evidence.** That is the lesson this harness is built
around. A truncation bug in the routing budget was measured at one failure
in eight, and the first two probes came back clean; had it been graded once
per case it would have shipped. So every case runs `--repeat` times and the
report is a *rate*, not a verdict. A case that passes seven times out of
eight is not a passing case, and a harness that cannot tell the difference
is worse than none.

**Grading is deterministic.** No model judges another model's output. Every
check is a substring, a citation marker, a refusal sentinel, or the
project's own `check_answer` — the same integrity checks that run in
production. A grader that itself needed a model would have the failure mode
it exists to detect.

Kept out of the test suite deliberately: these cost money and need network,
and a suite people cannot run offline is a suite people stop running.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CASES = Path(__file__).parent / "cases.yaml"

_CITATION_RE = re.compile(r"\[\d+\]")


@dataclass
class Outcome:
    """What one graded run produced."""

    passed: bool
    detail: str = ""
    output: str = ""


@dataclass
class CaseResult:
    """One case, run several times."""

    suite: str
    name: str
    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def runs(self) -> int:
        return len(self.outcomes)

    @property
    def passes(self) -> int:
        return sum(1 for o in self.outcomes if o.passed)

    @property
    def rate(self) -> float:
        return self.passes / self.runs if self.runs else 0.0

    @property
    def flaky(self) -> bool:
        """Sometimes right. The outcome a single run cannot distinguish from
        either of the other two, and the one worth knowing about."""
        return 0 < self.passes < self.runs

    @property
    def failures(self) -> list[Outcome]:
        return [o for o in self.outcomes if not o.passed]


def _missing(text: str, required) -> list[str]:
    lowered = text.lower()
    return [term for term in required or [] if term.lower() not in lowered]


def _present(text: str, forbidden) -> list[str]:
    lowered = text.lower()
    return [term for term in forbidden or [] if term.lower() in lowered]


def grade_text(text: str, case: dict) -> Outcome:
    """The shared substring checks every suite uses."""
    missing = _missing(text, case.get("must_contain"))
    if missing:
        return Outcome(False, f"missing {missing}", text)

    forbidden = _present(text, case.get("must_not_contain"))
    if forbidden:
        return Outcome(False, f"should not contain {forbidden}", text)

    any_of = case.get("must_contain_any")
    if any_of and not any(term.lower() in text.lower() for term in any_of):
        return Outcome(False, f"none of {any_of} present", text)

    return Outcome(True, output=text)


# --------------------------------------------------------------------------
# Suites
# --------------------------------------------------------------------------


def run_routing(case: dict, provider) -> Outcome:
    """Does the question reach the analysis that can answer it?

    The negative cases matter as much as the positive ones: a router that
    hijacks "what is our access review cadence?" into an analysis has made
    the shell worse, not better.
    """
    from policyforge.zardoz.skills import route

    chosen = route(case["question"], provider)
    expected = case["expect"]
    if chosen != expected:
        return Outcome(False, f"routed to {chosen!r}, expected {expected!r}", chosen)
    return Outcome(True, output=chosen)


def run_resolution(case: dict, provider) -> Outcome:
    """Does a follow-up become the question it obviously means?"""
    from policyforge.zardoz.conversation import Conversation, Turn, resolve_question

    conversation = Conversation(
        turns=[
            Turn(question=t["q"], resolved=t["q"], answer=t.get("a", ""))
            for t in case.get("history", [])
        ]
    )
    resolved, rewritten = resolve_question(case["question"], conversation, provider)

    if "rewritten" in case and bool(rewritten) != bool(case["rewritten"]):
        state = "rewritten" if rewritten else "left alone"
        return Outcome(False, f"{state}, expected the opposite", resolved)
    return grade_text(resolved, case)


def run_expansion(case: dict, provider) -> Outcome:
    """Does expansion name the document's vocabulary, and nothing else?

    The forbidden list is the important half. An expansion that supplies a
    frequency or a control identifier has invented a fact, and retrieval
    would then go looking for it.
    """
    from policyforge.zardoz.paraphrase import expand_query

    return grade_text(expand_query(case["question"], provider), case)


def _passages(case: dict):
    """Build retrieval passages from the case's own documents."""
    from policyforge.zardoz.corpus import TRUSTED, Corpus
    from policyforge.zardoz.corpus import CorpusDocument as Doc
    from policyforge.zardoz.retrieve import build_index

    corpus = Corpus(
        documents=[
            Doc(
                doc_id=str(n),
                title=doc["title"],
                space="",
                confidence=doc.get("confidence", TRUSTED),
                source="markdown",
                path=doc.get("path", f"standards/{n}.md"),
                owner=doc.get("owner", "IAM Engineering"),
                body=doc["body"],
            )
            for n, doc in enumerate(case["documents"])
        ]
    )
    # Retrieval is deterministic, so the passages a case is graded on are the
    # same every run and only the answering varies. Grading two stochastic
    # stages at once would make a failure impossible to attribute.
    return build_index(corpus).search(case.get("retrieve", case["question"]), limit=4)


def run_answering(case: dict, provider) -> Outcome:
    """Does the answer stay inside its passages, and refuse when it must?"""
    from policyforge.zardoz.answer import answer_question, check_answer

    passages = _passages(case)
    if case.get("expect_passages") is not None and len(passages) != case["expect_passages"]:
        return Outcome(
            False,
            f"retrieval found {len(passages)} passage(s), case expects "
            f"{case['expect_passages']} — the case, not the model, is wrong",
        )

    answer = answer_question(case["question"], passages, provider)

    if case.get("expect_refusal") and not answer.refused:
        return Outcome(False, "answered, expected a refusal", answer.text)
    if case.get("expect_refusal") is False and answer.refused:
        return Outcome(False, "refused, expected an answer", answer.text)
    if answer.refused:
        return Outcome(True, "refused", answer.text)

    if case.get("must_cite", True) and not _CITATION_RE.search(answer.text):
        return Outcome(False, "no citation marker", answer.text)

    # The project's own integrity checks, run as a grader. A fabricated
    # citation or a quotation that is not in the source is a failure here
    # for exactly the reason it is a warning in production.
    if case.get("integrity_clean", True):
        _, warnings = check_answer(answer.text, passages)
        if warnings:
            return Outcome(False, f"integrity: {'; '.join(warnings)}", answer.text)

    return grade_text(answer.text, case)


SUITES = {
    "routing": run_routing,
    "resolution": run_resolution,
    "expansion": run_expansion,
    "answering": run_answering,
}


def load_cases(path: Path = DEFAULT_CASES) -> dict[str, list[dict]]:
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {suite: list(cases or []) for suite, cases in data.items() if suite in SUITES}


def run_case(suite: str, case: dict, provider, *, repeat: int = 1) -> CaseResult:
    result = CaseResult(suite=suite, name=case.get("name") or case.get("question", "?"))
    for _ in range(repeat):
        try:
            result.outcomes.append(SUITES[suite](case, provider))
        except Exception as exc:  # noqa: BLE001 - one bad case must not end the run
            result.outcomes.append(Outcome(False, f"{type(exc).__name__}: {exc}"))
    return result


def format_report(results: list[CaseResult], *, repeat: int) -> str:
    lines = []
    for suite in SUITES:
        rows = [r for r in results if r.suite == suite]
        if not rows:
            continue
        passes = sum(r.passes for r in rows)
        runs = sum(r.runs for r in rows)
        clean = sum(1 for r in rows if r.rate == 1.0)
        lines.append(
            f"{suite}: {clean}/{len(rows)} cases always pass "
            f"({passes}/{runs} runs, {passes / runs:.0%})"
        )
        for row in rows:
            if row.rate == 1.0:
                continue
            mark = "FLAKY" if row.flaky else "FAIL "
            lines.append(f"  {mark} {row.passes}/{row.runs}  {row.name}")
            for outcome in row.failures[:1]:
                lines.append(f"        {outcome.detail}")
                if outcome.output:
                    lines.append(f"        got: {' '.join(outcome.output.split())[:150]}")

    flaky = [r for r in results if r.flaky]
    failed = [r for r in results if r.passes == 0]
    lines += ["", f"{len(results)} case(s) x {repeat} run(s)"]
    if failed:
        lines.append(f"  {len(failed)} never passed")
    if flaky:
        lines.append(
            f"  {len(flaky)} flaky — right sometimes, which one run per case "
            "cannot tell from right always"
        )
    if not failed and not flaky:
        lines.append("  every case passed every run")
    return "\n".join(lines)
