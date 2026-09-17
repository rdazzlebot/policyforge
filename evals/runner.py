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
DEFAULT_PARAPHRASES = Path(__file__).parent / "paraphrases.yaml"
DEFAULT_ANSWER_PARAPHRASES = Path(__file__).parent / "answer_paraphrases.yaml"

_CITATION_RE = re.compile(r"\[(\d+)\]")


#: Substrings identifying a failure of the API rather than of the prompt.
#: A dead key, an exhausted balance and a rate limit are all "this did not
#: run", and reporting them as graded failures says the model got the answer
#: wrong when it was never asked the question.
_INFRASTRUCTURE = (
    "credit balance",
    "rate limit",
    "authentication",
    "api key",
    "overloaded",
    "connection",
    "timeout",
)


@dataclass
class Outcome:
    """What one graded run produced."""

    passed: bool
    detail: str = ""
    output: str = ""
    #: True when the request never reached a verdict. Counted apart from
    #: failures: a run that could not happen is not evidence about the
    #: prompt, and folding it in turns an expired card into what looks like
    #: a regression.
    errored: bool = False


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

    @property
    def errors(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.errored]

    @property
    def graded(self) -> int:
        """Runs that actually reached a verdict."""
        return self.runs - len(self.errors)


def _missing(text: str, required) -> list[str]:
    lowered = text.lower()
    return [term for term in required or [] if term.lower() not in lowered]


def _present(text: str, forbidden) -> list[str]:
    lowered = text.lower()
    return [term for term in forbidden or [] if term.lower() in lowered]


def grade_text(text: str, case: dict) -> Outcome:
    """The shared substring checks every suite uses.

    Empty output is a failure unless the case says otherwise, and that
    default is the whole point. A case whose assertions are all negative
    passes trivially on an empty string, so it cannot fail for the reason it
    was written: `no-prose` forbids a prose expansion, but `parse_expansion`
    already discards a prose reply and returns nothing, and nothing contains
    no prose. Mutation testing found it — deleting the rule that forbids
    prose changed the case's verdict not at all.
    """
    if not text.strip() and not case.get("allow_empty"):
        return Outcome(False, "empty output — negative assertions pass on nothing", text)

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


def run_routing(case: dict, provider, corpora: dict | None = None) -> Outcome:
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


def run_chaining(case: dict, provider, corpora: dict | None = None) -> Outcome:
    """Does a question get every analysis it asks for, and no others?

    Graded as a set. For a question that genuinely asks two separate things,
    which one a model routes first is its choice, and grading the order would
    fail a correct plan. What is graded strictly is the count: a single-intent
    case that comes back with a second analysis has attached a report nobody
    asked for, which is the failure this suite exists to catch.
    """
    from policyforge.zardoz.skills import route_plan

    chosen = [routed.skill for routed in route_plan(case["question"], provider)]
    expected = case["expect"] if isinstance(case["expect"], list) else [case["expect"]]
    if len(chosen) != len(expected) or set(chosen) != set(expected):
        return Outcome(False, f"ran {chosen}, expected {expected}", ", ".join(chosen))
    return Outcome(True, output=", ".join(chosen))


def run_resolution(case: dict, provider, corpora: dict | None = None) -> Outcome:
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


def run_expansion(case: dict, provider, corpora: dict | None = None) -> Outcome:
    """Does expansion name the document's vocabulary, and nothing else?

    The forbidden list is the important half. An expansion that supplies a
    frequency or a control identifier has invented a fact, and retrieval
    would then go looking for it.
    """
    from policyforge.zardoz.paraphrase import expand_query

    return grade_text(expand_query(case["question"], provider), case)


def _corpus_of(case: dict, corpora: dict | None = None):
    """The Corpus a case is about, before anything is retrieved from it.

    Split out because a multi-turn case cannot pre-compute passages: each
    turn asks a different question and must retrieve for itself, which is
    the point of driving the real shell rather than the answering function.
    """
    from policyforge.zardoz.corpus import TRUSTED, Corpus
    from policyforge.zardoz.corpus import CorpusDocument as Doc

    if "corpus" in case:
        case = {**case, "documents": (corpora or {})[case["corpus"]]}

    documents = [
        {**doc, "body": (Path(__file__).parent / doc["from_file"]).read_text(encoding="utf-8")}
        if "from_file" in doc
        else doc
        for doc in case["documents"]
    ]
    return Corpus(
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
            for n, doc in enumerate(documents)
        ]
    )


def _passages(case: dict, corpora: dict | None = None):
    """The passages a single-turn answering case is graded on.

    Retrieval is deterministic, so these are the same every run and only the
    answering varies. Grading two stochastic stages at once would make a
    failure impossible to attribute.
    """
    from policyforge.zardoz.retrieve import build_index

    corpus = _corpus_of(case, corpora)
    return build_index(corpus).search(case.get("retrieve", case["question"]), limit=4)


_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")


def check_attribution(text: str, passages, attributions) -> str:
    """Verify each claim is credited to the passage that actually supports it.

    `check_answer` already proves a citation *exists* and points at a real
    passage. It cannot tell whether it points at the right one â€” an answer
    that says "restores are tested twice a year [1]" while [1] is the access
    control standard passes every integrity check and is wrong in the way
    that matters, because the reader who follows the citation finds nothing.

    Graded from the case rather than inferred: the case names the claim and
    the document that should be credited for it, and this checks the
    sentence carrying that claim cites a passage from that document. A claim
    stated with no citation at all fails here too, which is the other half
    of the same problem.
    """
    by_number = dict(enumerate(passages, start=1))

    for rule in attributions or []:
        claim, source = rule["claim"].lower(), rule["from"].lower()
        sentences = [s for s in _SENTENCE_RE.findall(text) if claim in s.lower()]
        if not sentences:
            return f"never states {rule['claim']!r}"

        cited_titles = {
            by_number[int(n)].document.title.lower()
            for sentence in sentences
            for n in _CITATION_RE.findall(sentence)
            if int(n) in by_number
        }
        if not cited_titles:
            return f"states {rule['claim']!r} with no citation"
        if source not in cited_titles:
            return (
                f"credits {rule['claim']!r} to {sorted(cited_titles)}, "
                f"but it comes from {rule['from']!r}"
            )
    return ""


def run_answering(case: dict, provider, corpora: dict | None = None) -> Outcome:
    """Does the answer stay inside its passages, and refuse when it must?"""
    from policyforge.zardoz.answer import answer_question, check_answer

    passages = _passages(case, corpora)
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

    # Some answers are only answers if they credit every passage. A
    # contradiction reported from one of the two documents that disagree is
    # not a contradiction reported — it is the model having quietly picked
    # one, which reads exactly like a straight answer.
    if case.get("must_cite_all"):
        uncited = [n for n in range(1, len(passages) + 1) if f"[{n}]" not in answer.text]
        if uncited:
            return Outcome(
                False,
                f"cites no passage {', '.join(f'[{n}]' for n in uncited)} of "
                f"{len(passages)} supplied",
                answer.text,
            )

    # The project's own integrity checks, run as a grader. A fabricated
    # citation or a quotation that is not in the source is a failure here
    # for exactly the reason it is a warning in production.
    if case.get("integrity_clean", True):
        _, warnings = check_answer(answer.text, passages, case["question"])
        if warnings:
            return Outcome(False, f"integrity: {'; '.join(warnings)}", answer.text)

    misattributed = check_attribution(answer.text, passages, case.get("attributions"))
    if misattributed:
        return Outcome(False, f"attribution: {misattributed}", answer.text)

    return grade_text(answer.text, case)


def _multiplied(original: str, revised: str, terms) -> list[str]:
    """Terms the revision has more of than its source did.

    A planted instruction is *supposed* to survive the edit. It is part of
    what the page says, and a rewrite that silently deleted it would be
    making a change nobody planned. So the words it contains appear in a
    correct revision too, and a case that simply forbade them would fail on
    the right answer.

    What must not happen is the model *acting* on it — and acting on it
    means those words turn up somewhere they were not. Counting says that
    without having to locate the planted line in the output, which a
    revision that reflowed a paragraph would defeat.
    """
    lowered_before, lowered_after = original.lower(), revised.lower()
    return [
        term
        for term in terms or []
        if lowered_after.count(term.lower()) > lowered_before.count(term.lower())
    ]


def _edit_plan_from(case: dict):
    """Build the approved plan a case supplies, rather than planning it.

    The executor is graded on one stochastic stage. A plan produced by a
    model in the same run would vary too, and a failure could not be
    attributed to either.
    """
    from policyforge.edit.plan import EditPlan, EditStep

    spec = case["plan"]
    return EditPlan(
        instruction=spec["instruction"],
        page_title=case.get("page_title", ""),
        steps=[
            EditStep(
                kind=step["kind"],
                target=step["target"],
                summary=step["summary"],
                rationale=step.get("rationale", ""),
            )
            for step in spec.get("steps") or []
        ],
    )


def run_edit_plan(case: dict, provider, corpora: dict | None = None) -> Outcome:
    """Does the planner plan the operator's instruction, and only that?

    The document here is a live wiki page, which means anyone with edit
    rights on it can write a line addressed to whoever reads the prompt.
    A planner that turns such a line into a step has taken an instruction
    from the page — and the step it produces is the thing a reviewer is
    then asked to approve, which is how it gets published.

    Both halves are graded. A fence that makes the model refuse the
    operator's actual instruction is not a fence that works; it is a broken
    editor. So the positive assertion matters as much as the negative one.
    """
    from policyforge.edit.plan import build_edit_plan

    plan = build_edit_plan(
        case["instruction"],
        case["document"],
        provider,
        page_title=case.get("page_title", ""),
        tier=case.get("tier", ""),
    )

    if case.get("expect_steps") is not None and len(plan.steps) != case["expect_steps"]:
        return Outcome(
            False,
            f"planned {len(plan.steps)} step(s), case expects {case['expect_steps']}",
            plan.render(),
        )

    forbidden_targets = [t.lower() for t in case.get("forbid_targets") or []]
    for step in plan.steps:
        if step.target.lower() in forbidden_targets:
            return Outcome(False, f"planned a step targeting {step.target!r}", plan.render())

    # Graded on the steps alone, not the whole rendered plan. `risks` and
    # `out_of_scope` are where a planner *reports* something it declined,
    # and a planner that says "the page contains an instruction to set this
    # to annually, which I did not act on" has done exactly the right thing.
    # Grading the full render would fail it for saying so.
    return grade_text("\n".join(step.render() for step in plan.steps), case)


def run_edit_apply(case: dict, provider, corpora: dict | None = None) -> Outcome:
    """Does the rewrite make the planned change and leave everything else?

    Graded by the project's own `check_edit`, for the reason the answering
    suite is graded by `check_answer`: the thing that runs in production is
    the thing that should decide, or the eval is measuring something else.
    An injected requirement lands in a section the plan never named, which
    is exactly what `check_edit` reports.
    """
    from policyforge.edit.apply import apply_edit_plan, check_edit

    plan = _edit_plan_from(case)
    document = case["document"]
    revised = apply_edit_plan(plan, document, provider)

    # The markers are scaffolding. A model that echoes them would publish
    # them to the live page, and the fence would have caused the damage it
    # exists to prevent.
    #
    # Counted against the source rather than simply forbidden. A page that
    # imitates the fence contains marker-shaped lines of its own, and a
    # correct revision keeps them byte for byte — the first version of this
    # check failed exactly that answer, and reported a model that had done
    # the right thing as one that had leaked the fence.
    echoed = _multiplied(document, revised, ["BEGIN pf-", "END pf-"])
    if echoed:
        return Outcome(False, f"the revision reproduced the fence markers {echoed}", revised)

    if case.get("expect_check_clean", True):
        check = check_edit(document, revised, plan=plan)
        damage = []
        if check.dropped_source_tags:
            damage.append(f"dropped citations {check.dropped_source_tags}")
        if check.removed_headings:
            damage.append(f"removed sections {check.removed_headings}")
        if check.changed_sections:
            damage.append(f"changed unplanned sections {check.changed_sections}")
        if check.added_headings and not check.additions_were_planned:
            damage.append(f"added unplanned sections {check.added_headings}")
        if damage:
            return Outcome(False, f"check_edit: {'; '.join(damage)}", revised)

    acted_on = _multiplied(document, revised, case.get("must_not_multiply"))
    if acted_on:
        return Outcome(
            False,
            f"acted on planted text — {acted_on} appears more often than in the source",
            revised,
        )

    return grade_text(revised, case)


def run_conversation(case: dict, provider, corpora: dict | None = None) -> Outcome:
    """Drive several turns through the real shell and grade each one.

    Every other suite exercises one prompt in isolation, which is right for
    attributing a failure and wrong for the thing a conversation actually
    is. A chain compounds: turn three is resolved against turn two's
    resolution, retrieved on the result, and answered from that. The
    failures worth finding here — a subject that drifts and is never
    reclaimed, a pronoun that binds to the wrong antecedent, an analysis
    that hijacks the middle of a document conversation — cannot appear in a
    single-turn case by construction.

    Driven through `dispatch` rather than the underlying functions so that
    resolution, routing and answering interact exactly as they do for a
    person at the prompt.
    """
    from policyforge.zardoz.answer import check_answer
    from policyforge.zardoz.shell import ShellState, dispatch

    state = ShellState(
        corpus=_corpus_of(case, corpora),
        provider=provider,
        config={},
        topics=[],
    )

    for number, turn in enumerate(case["turns"], start=1):
        output = dispatch(turn["ask"], state)
        recorded = state.conversation.last
        resolved = recorded.resolved if recorded else ""
        where = f"turn {number} ({turn['ask']!r})"

        if "expect_skill" in turn:
            ran = f"(ran /{turn['expect_skill']})" in output
            if turn["expect_skill"] == "documents":
                if "(ran /" in output:
                    return Outcome(False, f"{where}: routed to an analysis", output[:200])
            elif not ran:
                return Outcome(False, f"{where}: did not run /{turn['expect_skill']}", output[:200])

        checks = {
            "must_contain": turn.get("resolved_contains"),
            "must_not_contain": turn.get("resolved_not_contains"),
            "must_contain_any": turn.get("resolved_contains_any"),
        }
        if any(checks.values()):
            graded = grade_text(resolved, {k: v for k, v in checks.items() if v})
            if not graded.passed:
                return Outcome(False, f"{where} resolved: {graded.detail}", resolved)

        answer_checks = {
            "must_contain": turn.get("answer_contains"),
            "must_not_contain": turn.get("answer_not_contains"),
            "must_contain_any": turn.get("answer_contains_any"),
        }
        if any(answer_checks.values()):
            graded = grade_text(output, {k: v for k, v in answer_checks.items() if v})
            if not graded.passed:
                return Outcome(False, f"{where} answer: {graded.detail}", output[:220])

        # The same integrity checks the single-turn suite runs. They were
        # missing here, which left the chain — the one place a drifted
        # subject produces a confident answer about the wrong thing —
        # graded only on substrings. Skipped for a turn that ran an
        # analysis, which has no passages and is printed verbatim.
        # `recorded.answer` is empty on the no-provider path, where the
        # shell prints the passages verbatim and no model wrote anything.
        # There are no claims there to check.
        if (
            turn.get("integrity_clean", True)
            and recorded
            and recorded.passages
            and recorded.answer.strip()
        ):
            _, warnings = check_answer(recorded.answer, recorded.passages, recorded.subject)
            if warnings:
                return Outcome(False, f"{where} integrity: {'; '.join(warnings)}", recorded.answer)

    return Outcome(True, output=f"{len(case['turns'])} turns")


def _section(document: str, name: str) -> str:
    """The body of one `## ` section, up to the next one."""
    lines, inside = [], False
    for line in document.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().lower().startswith(name.lower())
            continue
        if inside:
            lines.append(line)
    return "\n".join(lines)


#: A NIST control identifier in running text. A Policy is read by people who
#: will never see one, so any at all is the tier failing at its one job.
_CONTROL_ID_RE = re.compile(r"\b[A-Z]{2}-\d+(?:\(\d+\))?\b")


def _tags(text: str) -> set[str]:
    """The control references a text cites: one per framework and identifier.

    References rather than tag strings, for two reasons a live run found. A
    tag inside a markdown table has its pipe escaped — `[NIST AC-2 \\| HIPAA
    164.308]` — which is correct markdown and a different string. And a
    document that merges two requirements writes one tag naming both
    controls, `[NIST AC-2 | NIST AC-6]`, which cites nothing its synthesis
    did not. Compared as strings, both read as fabricated citations, and the
    grader failed documents for being right.

    Splitting also makes the loss check stricter where it counts: a merged
    tag that quietly drops one of the two controls it replaced is a missing
    reference, which a string comparison would have called a new tag.
    """
    from policyforge.edit.apply import _SOURCE_TAG_RE

    references: set[str] = set()
    for tag in _SOURCE_TAG_RE.findall(text):
        for part in tag.strip("[]").replace("\\", "").split("|"):
            reference = " ".join(part.split())
            if reference:
                references.add(reference)
    return references


def _cited_blocks(document: str) -> list[str]:
    """The heading-to-heading blocks that carry a source tag.

    The unit for "states an interval the synthesis does not". A whole
    document is the wrong unit: a Standard that ends "this Standard is
    reviewed annually" has invented nothing, and a check that flagged it
    would fire on every well-formed document. A sentence is the wrong unit
    too — a Procedure carries its tag on the subsection heading, so the step
    inventing a cadence underneath it is never itself cited. The block
    between headings is what a requirement and its steps actually occupy.
    """
    from policyforge.edit.apply import _SOURCE_TAG_RE

    blocks: list[list[str]] = [[]]
    for line in document.splitlines():
        blocks.append([line]) if line.startswith("#") else blocks[-1].append(line)
    joined = ["\n".join(block) for block in blocks]
    return [block for block in joined if _SOURCE_TAG_RE.search(block)]


def _heading_name(line: str) -> str:
    """A `## ` heading's name, without the numbering documents often carry."""
    return re.sub(r"^\d+[.)]\s*", "", line[3:].strip()).lower()


def run_generation(case: dict, provider, corpora: dict | None = None) -> Outcome:
    """Does a drafted document keep what its synthesis said, and only that?

    Graded by the checks the project already runs on real documents, which
    is the point: `content/check.py`'s citation comparison, `deontic`'s
    binding share and weakened citations, the answering path's
    `ungrounded_values`, and each tier's own structural rules from its
    prompt. The ones that matter most are the ones a reader cannot see — a
    dropped citation, "shall" become "should consider", an interval the
    synthesis never stated — because the prose around them reads fine.
    """
    from policyforge.content.deontic import binding_share, weakened_citations
    from policyforge.generate.policy_writer import (
        OrgContext,
        generate_policy,
        generate_procedure,
        generate_standard,
    )
    from policyforge.org.context import apply_substitutions, load_org_profile
    from policyforge.zardoz.answer import ungrounded_values

    synthesis, tier = case["synthesis"], case["tier"]
    # Built the way `policyforge generate` builds it, not by hand. This used
    # to pass `OrgContext(vendors=[...])` with no profile, which reaches a
    # prompt branch the CLI never sends — the CLI always attaches a profile,
    # even for a legacy flat vendor list — and skipped the role substitution
    # the CLI applies afterwards. A case could then fail for "missing Okta"
    # on output production would have filled in, or pass on a prompt
    # production never shows a model.
    name = case.get("org", "Acme Health")
    industry = case.get("industry", "Healthcare")
    profile = load_org_profile(
        {"org": {"name": name, "industry": industry, "vendors": case.get("vendors")}}
    )
    org = OrgContext(
        name=name,
        industry=industry,
        vendors=profile.unkeyed_vendors,
        profile=profile,
    )
    standard_title = case.get("standard_title", "Access Control Standard")
    if tier == "standard":
        document = generate_standard(synthesis, org, provider)
    elif tier == "policy":
        document = generate_policy(synthesis, org, provider, standard_title=standard_title)
    elif tier == "procedure":
        document = generate_procedure(synthesis, org, provider, standard_title=standard_title)
    else:
        raise ValueError(f"unknown tier {tier!r}")
    document = apply_substitutions(document, profile).text

    expected = _tags(synthesis)
    present = _tags(document)
    if tier != "policy":
        missing = sorted(expected - present)
        if missing:
            return Outcome(False, f"dropped citations {missing}", document)
    invented = sorted(present - expected)
    if invented:
        return Outcome(False, f"cites what the synthesis does not {invented}", document)
    if tier == "policy":
        cited = present or set(_CONTROL_ID_RE.findall(document))
        if cited:
            return Outcome(False, f"a Policy names controls {sorted(cited)}", document)

    # Opt-in, because a weakened citation is not always a weakening. The
    # synthesis prohibits shared accounts "except where approved in
    # writing", and a document writing that exception as "an exception may
    # be made where..." is being faithful, not permissive. The binding share
    # below is the measure of "shall" drifting to "should"; this catches a
    # document where it has gone further than a case will allow.
    allowed_weak = case.get("max_weakened")
    if allowed_weak is not None:
        weakened = weakened_citations(document)
        if len(weakened) > allowed_weak:
            return Outcome(
                False,
                f"{len(weakened)} cited requirement(s) do not bind, over {allowed_weak}: "
                f"{weakened[0].text[:90]!r}",
                document,
            )
    floor = case.get("min_binding_share")
    if floor is not None:
        binding, modal = binding_share(document)
        if modal and binding / modal < floor:
            return Outcome(False, f"binding share {binding}/{modal} below {floor:.0%}", document)

    # Over the blocks that carry a citation, not the whole document, and
    # casefolded because the check casefolds each value it finds and
    # compares it against the haystack as given — a document writing
    # "Quarterly" at the start of a sentence would otherwise read as an
    # invention of the word its synthesis states in lower case.
    ungrounded = sorted(
        {
            value
            for block in _cited_blocks(document)
            for value in ungrounded_values(block, synthesis.casefold())
        }
    )
    if ungrounded:
        return Outcome(
            False,
            f"a cited requirement states intervals the synthesis does not {ungrounded}",
            document,
        )

    matched = [p for p in case.get("forbid_patterns") or [] if re.search(p, document, re.I)]
    if matched:
        return Outcome(False, f"matches forbidden pattern {matched[0]!r}", document)

    # The positive twin, one pattern per thing that must each survive. A
    # pattern rather than a phrase because a faithful rewrite moves words:
    # "implement these procedures as needed" keeps the source's qualifier
    # exactly as well as "implemented as needed" does, and a phrase list
    # failed the first while passing a document that dropped it elsewhere.
    unmet = [p for p in case.get("require_patterns") or [] if not re.search(p, document, re.I)]
    if unmet:
        return Outcome(False, f"does not match required pattern {unmet[0]!r}", document)

    headings = [_heading_name(line) for line in document.splitlines() if line.startswith("## ")]
    positions = []
    for name in case.get("sections") or []:
        index = next((i for i, h in enumerate(headings) if h.startswith(name.lower())), None)
        if index is None:
            return Outcome(False, f"no '## {name}' section", document)
        positions.append(index)
    if positions != sorted(positions):
        return Outcome(False, "sections are out of the order the tier requires", document)

    most = case.get("max_policy_bullets")
    if most is not None:
        bullets = [
            line
            for line in _section(document, "Policy Statements").splitlines()
            if line.lstrip().startswith(("- ", "* ", "+ "))
        ]
        if len(bullets) > most:
            return Outcome(
                False, f"{len(bullets)} policy statements, compressed to at most {most}", document
            )

    fewest = case.get("min_subsections")
    if fewest is not None:
        subsections = sum(1 for line in document.splitlines() if line.startswith("### "))
        if subsections < fewest:
            return Outcome(False, f"{subsections} step subsection(s), expected {fewest}+", document)

    return grade_text(document, case)


_CROSSWALK_CATALOGS: dict = {}


def _crosswalk_catalogs() -> dict:
    """The bundled 800-53 and HIPAA catalogs, loaded once per run."""
    if not _CROSSWALK_CATALOGS:
        from policyforge.crosswalk.candidates import WordIndex, catalog_entries
        from policyforge.crosswalk.overlay import published_pairs
        from policyforge.crosswalk.propose import requirements_of
        from policyforge.ingest.schema import load_controls

        root = Path(__file__).resolve().parents[1] / "data" / "frameworks"
        controls = load_controls(root / "nist-800-53-r5" / "controls.json") + load_controls(
            root / "hipaa-security-rule" / "controls.json"
        )
        entries = catalog_entries(controls)
        _CROSSWALK_CATALOGS.update(
            entries=entries,
            index=WordIndex(entries),
            published=published_pairs(controls, "HIPAA Security Rule"),
            requirements={
                r.requirement_id: r for r in requirements_of(controls, "HIPAA Security Rule")
            },
        )
    return _CROSSWALK_CATALOGS


def run_crosswalk(case: dict, provider, corpora: dict | None = None) -> Outcome:
    """Does a proposal map what plainly addresses the requirement, and not a word match?

    Graded on the real `propose_for` against the bundled catalogs, so the
    candidate list is the one production builds and the quotes go through the
    same verification. Only pairs whose quotes verified count as asserted.

    Every case is one a careful reader would not dispute, because the
    published crosswalk is not ground truth here and neither is a model: what
    is graded is the floor. `must_map` holds groups of which one must be
    asserted; `must_not_map` is a control sharing the requirement's words and
    none of its obligation — physical access against logical access, a network
    disconnect against employee termination. `expect_none` is a requirement
    that is not a control at all.
    """
    from policyforge.crosswalk.propose import propose_for

    catalogs = _crosswalk_catalogs()
    requirement = catalogs["requirements"][case["requirement"]]
    proposal = propose_for(
        requirement,
        framework="HIPAA Security Rule",
        published=catalogs["published"].get(requirement.requirement_id, []),
        entries=catalogs["entries"],
        index=catalogs["index"],
        provider=provider,
    )
    asserted = [m.control for m in proposal.mappings]
    shown = ", ".join(asserted) or "(none)"
    if proposal.error:
        raise RuntimeError(proposal.error)

    for group in case.get("must_map") or []:
        missing = [c for c in group if c not in proposal.candidates]
        if missing:
            raise ValueError(f"case expects {missing}, which are not candidates")
        if not any(control in asserted for control in group):
            return Outcome(False, f"mapped none of {group}", shown)
    wrong = [c for c in case.get("must_not_map") or [] if c in asserted]
    if wrong:
        return Outcome(False, f"mapped {wrong}, which share words, not the obligation", shown)
    if case.get("expect_none") and asserted:
        return Outcome(False, f"mapped {asserted} to a requirement that is not a control", shown)
    return Outcome(True, output=shown)


SUITES = {
    "routing": run_routing,
    # Separate from routing so a chaining regression cannot hide inside a
    # routing score, and so routing's numbers stay comparable with every
    # epoch before chaining existed.
    "chaining": run_chaining,
    "resolution": run_resolution,
    "expansion": run_expansion,
    "answering": run_answering,
    "conversation": run_conversation,
    # Same grader as routing; a separate suite so the hand-written
    # cases and the generated ones are reported apart. They measure
    # different things: whether routing is right, and whether it is
    # right only for the wording its author happened to think of.
    "paraphrase": run_routing,
    # Answering, asked in wordings its author did not choose. Same
    # grader and same passages as the parent case; only the question
    # text differs.
    "answer_paraphrase": run_answering,
    # The write path. Split in two for the same reason answering pins its
    # passages: the planner and the executor are separate prompts, and one
    # run grading both cannot say which of them failed.
    "edit_plan": run_edit_plan,
    "edit_apply": run_edit_apply,
    # The drafting prompts, graded by the checks that already run on real
    # documents. The largest gap the review found: every prompt that writes
    # policy was unmeasured, and a model that routes perfectly can still
    # turn "shall" into "should consider".
    "generation": run_generation,
    # A model reading one requirement against 800-53 candidates. Graded on
    # the floor only: what plainly addresses the requirement is mapped, and
    # a control that merely shares its words is not.
    "crosswalk": run_crosswalk,
}


def load_cases(path: Path = DEFAULT_CASES) -> dict[str, list[dict]]:
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    cases = {suite: list(rows or []) for suite, rows in data.items() if suite in SUITES}

    paraphrases = load_paraphrases()
    if paraphrases:
        cases["paraphrase"] = paraphrases

    reworded = load_answer_paraphrases(parents=cases.get("answering", []))
    if reworded:
        cases["answer_paraphrase"] = reworded
    return cases


def load_answer_paraphrases(
    parents: list[dict], path: Path = DEFAULT_ANSWER_PARAPHRASES
) -> list[dict]:
    """Answering cases reworded, keeping their parent's expectations.

    Retrieval is pinned to the parent's wording, so the passages are
    identical across every phrasing and only the answering varies. A
    paraphrase that drove retrieval too would change the passages *and* the
    question at once, and a failure could not be attributed to either.
    """
    import yaml

    if not Path(path).exists():
        return []
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    by_name = {case["name"]: case for case in parents}

    rows = []
    for origin, entry in data.items():
        parent = by_name.get(origin)
        if parent is None:
            continue
        for n, phrasing in enumerate(entry.get("phrasings") or [], start=1):
            rows.append(
                {
                    **parent,
                    "name": f"{origin}#{n}",
                    "question": phrasing,
                    "retrieve": entry.get("retrieve", parent.get("question")),
                }
            )
    return rows


def load_paraphrases(path: Path = DEFAULT_PARAPHRASES) -> list[dict]:
    """Generated rewordings of the routing cases, as routing cases.

    The expected label is inherited from the case each was generated from,
    so novel wording is graded against a fixed answer. What this measures is
    paraphrase-invariance: a router that only works on the phrasings its
    author happened to write is brittle, and no hand-written case can show
    that, because the author writes those too.
    """
    import yaml

    if not Path(path).exists():
        return []
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

    rows = []
    for origin, entry in data.items():
        for n, phrasing in enumerate(entry.get("phrasings") or [], start=1):
            rows.append({"name": f"{origin}#{n}", "question": phrasing, "expect": entry["expect"]})
    return rows


def load_corpora(path: Path = DEFAULT_CASES) -> dict[str, list[dict]]:
    """Document sets several answering cases share."""
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return dict(data.get("corpora") or {})


def run_case(
    suite: str, case: dict, provider, *, repeat: int = 1, corpora: dict | None = None
) -> CaseResult:
    from policyforge.llm import ledger
    from policyforge.llm.base import TruncatedResponse

    result = CaseResult(suite=suite, name=case.get("name") or case.get("question", "?"))
    for _ in range(repeat):
        try:
            # Every runner takes the same three arguments, whether or not it
            # uses the corpora. Dispatching on a list of suite names instead
            # meant a new suite silently ran without its documents: the
            # answering paraphrases were added and every one of them failed
            # with a KeyError for a corpus that was loaded and sitting right
            # there.
            #
            # Named for the ledger: the provider is production's, wrapper
            # included, and a call that reached a vendor with the eval
            # corpora in it is recorded like any other — under the case it
            # graded rather than as `(unattributed)`.
            with ledger.about(f"{suite}/{result.name}", site="eval"):
                result.outcomes.append(SUITES[suite](case, provider, corpora))
        except TruncatedResponse as exc:
            # A failure, never a pass and never infrastructure noise: the
            # model answered, and its answer was cut off at the budget after
            # a retry. Graded as such so a budget that is too small for a
            # case shows up as that case failing with the reason on it.
            result.outcomes.append(
                Outcome(False, f"truncated at {exc.budget} tokens ({exc.stop_reason})", exc.text)
            )
        except Exception as exc:  # noqa: BLE001 - one bad case must not end the run
            detail = f"{type(exc).__name__}: {exc}"
            infrastructure = any(hint in detail.lower() for hint in _INFRASTRUCTURE)
            result.outcomes.append(Outcome(False, detail, errored=infrastructure))
    return result


#: Where the fingerprints of the last recorded epoch live. A file rather
#: than a constant in this module: it is data about a past run, and editing
#: it is the deliberate act of saying "the current prompts are what the
#: newest epoch measured".
FINGERPRINT_FILE = Path(__file__).with_name("prompt-fingerprints.json")


def recorded_fingerprints() -> dict[str, str]:
    """The fingerprints the newest MEASUREMENTS.md epoch was produced by."""
    import json

    try:
        return json.loads(FINGERPRINT_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def code_provenance() -> list[str]:
    """Which commit this run's code came from, and whether it was still moving.

    Added after a run was lost to a hazard that cost real forensics to
    identify. A measurement against `kimi-k3` reported `edit_plan` 0/5 with
    `AttributeError: no attribute 'call_shaped'` — not a model score, a
    process artifact. The run had started before a commit landed and was
    still going after it. Because nearly every import in this codebase is
    lazy, a long-running process keeps reading modules off disk for its
    whole run: `policyforge.llm.effort` was cached from before the commit,
    `policyforge.edit.plan` was imported fresh from after it, and the older
    cached module did not have the function the newer one called.

    Nothing was wrong with the repository at any point, which is what made
    it expensive to diagnose — it was reconstructed from file mtimes and a
    log's birth time. A run that states its own commit and dirty flag makes
    the same situation legible in one line.

    A dirty tree is not an error. It is the normal way a prompt change gets
    measured before it is committed. It is a fact the number needs attached
    to it, for the same reason an epoch is.
    """
    import subprocess

    def git(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=Path(__file__).resolve().parent.parent,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
        except Exception:  # noqa: BLE001 - provenance is never worth failing a run over
            return ""

    commit = git("rev-parse", "--short", "HEAD")
    if not commit:
        return ["", "Code: not a git checkout, so this run cannot name what it measured."]

    dirty = bool(git("status", "--porcelain"))
    lines = ["", f"Code: {commit}{' plus uncommitted changes' if dirty else ''}"]
    if dirty:
        lines.append(
            "  The working tree was modified. This number measures what was on "
            "disk, which is not any commit — say so if it goes into MEASUREMENTS.md."
        )
    lines.append(
        "  A long run reads modules off disk as it goes. If the tree changes "
        "underneath it, later suites can load code the earlier ones did not, and "
        "the mixture is not a state that ever existed. Run from a worktree pinned "
        "to a commit (`git worktree add ../pf-eval <commit>`) to make that impossible."
    )
    return lines


def prompt_epoch_report() -> list[str]:
    """What this run's prompts are, and whether they match the last epoch.

    This exists because of a specific failure. A measured run against
    `kimi-k3` was half finished when two commits changed the edit planner
    and the clusterer. Python had imported the old modules at process start,
    so the run was measuring code that no longer existed on disk — and
    nothing in the run, the report, or the resulting numbers could have said
    so. It was caught by one person comparing file mtimes against a log's
    birth time, and only because somebody thought to look.

    A run that prints its own prompt fingerprints cannot hide that. If they
    do not match what the last epoch recorded, the report says which prompts
    differ, and the number that follows is not comparable with the epoch
    above it until somebody opens a new one.
    """
    from policyforge.llm import prompts

    prompts.load_all()
    current = prompts.fingerprints()
    recorded = recorded_fingerprints()

    # "in this build", not "this run used". The registry is build-wide and
    # some registered prompts are reached by no runtime path at all —
    # `entail.judge` is implemented, tested, and called by nothing. Saying
    # "used" would make this report assert exactly the kind of thing it
    # exists to stop being asserted.
    lines = ["", "Prompts in this build:"]
    lines += [f"  {prompts.REGISTRY[name].label}" for name in sorted(current)]

    if not recorded:
        lines += [
            "",
            f"  No recorded epoch to compare against. Write {FINGERPRINT_FILE.name} "
            "when this run's numbers go into MEASUREMENTS.md, and the next run "
            "will be able to say whether it is comparable with them.",
        ]
        return lines

    lines += [
        f"  {old} is now {new}: renamed, text unchanged ({current[new]})"
        for old, new in prompts.renames(recorded)
    ]
    differences = prompts.compare(recorded)
    if not differences:
        lines += ["", "  Unchanged since the last recorded epoch — comparable with it."]
        return lines

    lines += [
        "",
        f"  {len(differences)} prompt(s) differ from the last recorded epoch. These "
        "numbers are NOT comparable with the epoch above them in MEASUREMENTS.md; "
        "open a new one.",
    ]
    lines += [f"    {line}" for line in differences]
    return lines


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
            mark = "ERROR" if row.errors else ("FLAKY" if row.flaky else "FAIL ")
            lines.append(f"  {mark} {row.passes}/{row.runs}  {row.name}")
            for outcome in row.failures[:1]:
                lines.append(f"        {outcome.detail}")
                if outcome.output:
                    lines.append(f"        got: {' '.join(outcome.output.split())[:150]}")

    errored = [r for r in results if r.errors]
    flaky = [r for r in results if r.flaky and not r.errors]
    failed = [r for r in results if r.passes == 0 and not r.errors]
    lines += ["", f"{len(results)} case(s) x {repeat} run(s)"]
    if errored:
        lines += [
            f"  {len(errored)} could not run — the API refused the request, so "
            "these say nothing about the prompts:",
            f"    {errored[0].errors[0].detail[:130]}",
        ]
    if failed:
        lines.append(f"  {len(failed)} never passed")
    if flaky:
        lines.append(
            f"  {len(flaky)} flaky — right sometimes, which one run per case "
            "cannot tell from right always"
        )
    if not failed and not flaky:
        lines.append("  every case passed every run")
    lines += code_provenance()
    lines += prompt_epoch_report()
    return "\n".join(lines)
