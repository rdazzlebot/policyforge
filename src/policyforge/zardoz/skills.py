"""The analyses Zardoz can run, as distinct from the documents it can read.

Until now Zardoz's whole world was the synced corpus: ask it something, it
finds passages and answers from them. But half the questions people have
about a compliance programme are not answerable from any document, because
they are questions *about* the programme rather than about its prose. Which
controls does nobody own. What did the catalog change last month. How many
organization-defined values are still undecided. Nothing in a Standard says
any of that; it falls out of set arithmetic over the registry, the catalogs
and the ledger.

Those computations already exist as CLI commands. What was missing was a way
to reach them from the place people are actually asking the question.

**The model routes; the report speaks.** A skill is chosen by the model —
that is a judgement about intent, which is what models are for — and then
its output is printed *verbatim*. The model never reads a result and tells
you about it. That division is the whole safety property here: a paraphrase
of "14 orphaned controls" can become "mostly in the audit family" with
nothing to check it against, and a compliance answer nobody can check is
worth less than no answer. Routing can be wrong in a way you can see, since
the chosen skill is always named. Reporting cannot be wrong at all, because
no model touches it.

Every skill is read-only. That is not a convention here — the package-wide
import guard makes the Confluence publish path unreachable from any module
in this directory, and a test walks the AST to prove it. A skill that wanted
to publish could not be written in this file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

#: What a router returns when the question is about the documents rather
#: than about the programme. The common case, and the default.
NO_SKILL = "documents"


@dataclass
class Skill:
    """One analysis, and the questions it is the right answer to."""

    name: str
    summary: str
    #: Plain-language description of what this answers, shown to the router.
    #: Written as the questions a person would ask, because that is what the
    #: router is matching against.
    answers: str
    run: Callable[..., str]
    #: Named when the skill cannot run, so the shell can say what is missing
    #: rather than printing an empty report.
    needs: str = ""


def _controls(state):
    """The control catalogs on disk, discovered rather than configured.

    A question about coverage should not require somebody to have passed
    `--controls` when they opened the shell. The framework registry already
    knows what is on disk, and using it means the shell answers with whatever
    the repository actually holds.
    """
    from policyforge.frameworks.registry import discover
    from policyforge.ingest.schema import load_controls

    if state.controls_paths:
        paths = list(state.controls_paths)
    else:
        paths = [f.controls_path for f in discover(state.config) if f.has_controls]

    controls = []
    for path in paths:
        try:
            controls.extend(load_controls(Path(path)))
        except (OSError, ValueError):
            continue
    return controls


def _coverage(state, args: list[str]) -> str:
    from policyforge.topics.coverage import analyze_coverage, format_report

    controls = _controls(state)
    if not controls:
        return "No control catalogs on disk. Run `policyforge etl-oscal` first."
    if not state.topics:
        return (
            "No topic registry loaded, so there is nothing to measure coverage "
            "against. Copy config/topics.example.yaml to config/topics.yaml."
        )

    # analyze_coverage takes controls already narrowed: "orphaned" is only
    # meaningful relative to a stated scope, so the filtering is the
    # caller's job and the scope has to be named in the report.
    baseline = next((a for a in args if a.lower() in ("low", "moderate", "high")), None)
    scope = "all controls"
    if baseline:
        controls = [c for c in controls if c.baseline and baseline in c.baseline.lower()]
        scope = f"{baseline} baseline"
        if not controls:
            return f"No controls tagged for the {baseline} baseline in the loaded catalogs."

    return format_report(analyze_coverage(state.topics, controls, scope=scope))


def _parameters(state, args: list[str]) -> str:
    from policyforge.parameters.ledger import build_report, load_ledger

    controls = _controls(state)
    if not controls:
        return "No control catalogs on disk. Run `policyforge etl-oscal` first."

    baseline = next((a for a in args if a.lower() in ("low", "moderate", "high")), None)
    if baseline:
        controls = [c for c in controls if c.baseline and baseline in c.baseline.lower()]

    decisions = load_ledger(state.parameters_path)
    report = build_report(controls, decisions)
    # Grouped by default: a thousand parameters listed one per line is not an
    # answer to anything somebody asked out loud.
    return report.format_report(group="all" not in args)


def _drift(state, args: list[str]) -> str:
    from policyforge.frameworks.drift import analyze_drift, load_previous
    from policyforge.ingest.schema import load_controls
    from policyforge.parameters.ledger import load_ledger

    from .corpus import DEFAULT_CONTENT_DIR

    paths = list(state.controls_paths)
    if not paths:
        from policyforge.frameworks.registry import discover

        paths = [f.controls_path for f in discover(state.config) if f.has_controls]
    if not paths:
        return "No control catalogs on disk, so there is nothing to compare."

    blocks = []
    for path in paths:
        previous = load_previous(Path(path))
        if previous is None:
            blocks.append(f"{Path(path).parent.name}: no committed version to compare against.")
            continue
        report = analyze_drift(
            previous,
            load_controls(Path(path)),
            topics=state.topics,
            content_root=state.content_dir or DEFAULT_CONTENT_DIR,
            decisions=load_ledger(state.parameters_path),
        )
        blocks.append(f"{Path(path).parent.name}:\n{report.format_report()}")
    return "\n\n".join(blocks)


def _history(state, args: list[str]) -> str:
    from policyforge.history.version_store import load_history

    if not args:
        return (
            "Which document? Try `/history standard access-control` — the tier "
            "and the filename stem `generate` used."
        )
    tier, name = (args[0], args[1]) if len(args) > 1 else ("standard", args[0])
    try:
        versions = load_history(state.history_dir, f"{tier}/{name}")
    except (OSError, ValueError) as exc:
        return f"Could not read history for {tier}/{name}: {exc}"
    if not versions:
        return (
            f"No recorded history for {tier}/{name} in {state.history_dir}. "
            "History is written by `generate` and by the edit commands."
        )

    lines = [f"{len(versions)} recorded version(s) of {tier}/{name}:"]
    for record in versions:
        lines.append(
            f"  v{record.version}  {record.timestamp}  {record.source}  "
            f"(+{record.lines_added}/-{record.lines_removed})"
        )
    return "\n".join(lines)


def _check(state, args: list[str]) -> str:
    from policyforge.content.check import check_tree

    from .corpus import DEFAULT_CONTENT_DIR

    root = Path(state.content_dir or DEFAULT_CONTENT_DIR)
    if not root.exists():
        return f"No content tree at {root}, so there is nothing to check."
    return check_tree(root).format_report()


def _frameworks(state, args: list[str]) -> str:
    from policyforge.frameworks.registry import check_licences

    report = check_licences(state.config)
    if not report.frameworks:
        return "No framework catalogs on disk."
    return report.format_report()


def _roles(state, args: list[str]) -> str:
    from policyforge.org.roles import TEAM_ROLES, VENDOR_ROLES

    lines = []
    for title, roles in (("Tool", VENDOR_ROLES), ("Team", TEAM_ROLES)):
        lines.append(f"{title} roles ({len(roles)}):")
        width = min(max(len(k) for k in roles), 28)
        lines += [f"  {k.ljust(width)}  {r.placeholder}" for k, r in roles.items()]
        lines.append("")
    lines.append("Assign them under `org.vendors` / `org.teams` in config.yaml.")
    return "\n".join(lines)


SKILLS: dict[str, Skill] = {
    "coverage": Skill(
        name="coverage",
        summary="Which in-scope controls no topic owns, and which two claim.",
        answers=(
            "which controls nobody owns or is responsible for; orphaned controls; "
            "controls claimed by two teams; gaps in the programme; whether a "
            "baseline is fully covered"
        ),
        run=_coverage,
    ),
    "parameters": Skill(
        name="parameters",
        summary="Organization-defined values decided and still outstanding.",
        answers=(
            "how many organization-defined parameters are still undecided; which "
            "frequencies or thresholds nobody has chosen; ODP status"
        ),
        run=_parameters,
    ),
    "drift": Skill(
        name="drift",
        summary="What a framework update changed, and what it reaches.",
        answers=(
            "what changed in the control catalog; whether a framework update "
            "affects us; which documents a catalog revision touches"
        ),
        run=_drift,
    ),
    "history": Skill(
        name="history",
        summary="Recorded versions of one document.",
        answers=(
            "what changed in a specific document over time; a document's version "
            "history; when a policy was last revised"
        ),
        run=_history,
    ),
    "check": Skill(
        name="check",
        summary="Problems in the content tree before anything is published.",
        answers=(
            "whether the document tree is healthy; broken links between documents; "
            "two files publishing to one page; documents with no owner"
        ),
        run=_check,
    ),
    "frameworks": Skill(
        name="frameworks",
        summary="Catalogs on disk and their licence position.",
        answers=(
            "which frameworks are loaded; what version of a catalog is in use; "
            "whether licensed content is committed"
        ),
        run=_frameworks,
    ),
    "roles": Skill(
        name="roles",
        summary="Tool and team roles config can assign.",
        answers="what tool or team roles can be configured; what placeholders exist",
        run=_roles,
    ),
}


ROUTER_SYSTEM_PROMPT = """You decide whether a question about an \
organization's security programme should be answered from its documents or \
by running an analysis.

You are given the question and a list of analyses. Reply with exactly one
word: the name of the analysis, or `documents`.

Rules:

1. Prefer `documents`. Most questions are about what a policy says, and the
   documents are the right source for those. An analysis is for questions
   about the *programme* — what is missing, what changed, what nobody has
   decided — which no document states.
2. Never explain, never add punctuation, never answer the question. One
   word.
3. If two could apply, choose the more specific one.
4. If you are unsure, say `documents`. A wrong analysis wastes a turn; a
   question sent to the documents that finds nothing gets an honest refusal,
   which is recoverable."""


#: Fallback routing, used when no model is configured. Deliberately narrow:
#: it fires on the words these analyses are actually about, and anything
#: else goes to the documents. A keyword router that guessed broadly would
#: hijack ordinary questions, which is worse than not routing at all.
_ROUTING_HINTS: dict[str, tuple[str, ...]] = {
    # Stems, not whole phrases. "nobody owns" misses "does nobody own?",
    # which is how the question is actually asked out loud.
    "coverage": (
        "orphan",
        "nobody own",
        "no one own",
        "no-one own",
        "unowned",
        "contested",
        "uncovered",
        "not covered",
        "who owns nothing",
    ),
    "parameters": ("undecided", "organization-defined", "odp", "parameter"),
    "drift": (
        "changed in the catalog",
        "catalog change",
        "catalog changed",
        "framework update",
        "framework changed",
        "new version",
        "version bump",
    ),
    "check": ("broken link", "content tree", "dangling"),
    "frameworks": ("which frameworks", "catalog version", "licence", "license"),
    "roles": ("what roles", "role keys", "which placeholders"),
}


def route_offline(question: str) -> str:
    lowered = question.lower()
    for name, hints in _ROUTING_HINTS.items():
        if any(hint in lowered for hint in hints):
            return name
    return NO_SKILL


def route(question: str, provider=None) -> str:
    """Which skill answers this, or `documents`.

    Never raises: a router failure should send the question to the documents,
    which is the honest default and the path that refuses gracefully.
    """
    if provider is None:
        return route_offline(question)

    catalog = "\n".join(f"{name}: {skill.answers}" for name, skill in SKILLS.items())
    try:
        response = provider.generate(
            system=ROUTER_SYSTEM_PROMPT,
            prompt=f"ANALYSES\n\n{catalog}\n\nQUESTION\n\n{question.strip()}\n\nOne word.",
            temperature=0.0,
            # Room for a reasoning preamble plus one word. The shim retries a
            # truncation, but paying for that on every call would be silly.
            max_tokens=64,
        )
    except Exception:  # noqa: BLE001 - a routing failure is not a session failure
        return route_offline(question)

    choice = response.text.strip().strip(".`").split()[0].lower() if response.text.strip() else ""
    return choice if choice in SKILLS else NO_SKILL


def run_skill(name: str, state, args: list[str] | None = None) -> str:
    """Run one skill and return its output, unmodified.

    The return value is printed verbatim. Nothing between here and the
    terminal is allowed to summarise it, which is what makes the numbers in
    a Zardoz answer worth the same as the numbers from the CLI.
    """
    skill = SKILLS.get(name)
    if skill is None:
        return f"No such analysis: {name}"
    try:
        return skill.run(state, args or [])
    except Exception as exc:  # noqa: BLE001 - one broken analysis, not a dead shell
        return f"{skill.name} could not run ({type(exc).__name__}: {exc})."


def skill_fields() -> list[tuple[str, str]]:
    """(name, summary) for the help table."""
    return [(name, skill.summary) for name, skill in SKILLS.items()]
