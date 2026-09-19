"""Topic-themed merge/dedupe engine.

Reproduces the pattern already proven out manually in the source Obsidian
vault's Synthesis/ folder — for a given real-world topic (e.g. "Password &
Credential Management"), pull every control/element that maps to it across
the enabled frameworks, dedupe overlapping requirements, and produce a
single prose statement per requirement with inline source tags, e.g.:

    "Passwords must be a minimum of 14 characters for privileged accounts.
    [NIST IA-5 | GovRAMP Moderate]"

This is the highest-value, most novel piece of the pipeline — it's what
turns a pile of controls into something a policy can actually be written
from. Uses an LLMProvider (see llm/base.py) for the actual merge/rewrite
step, with the source elements passed in as grounding context (not relying
on the model's own knowledge of framework text).
"""

from __future__ import annotations

from dataclasses import dataclass

from policyforge.ingest.schema import Control
from policyforge.llm.base import LLMProvider
from policyforge.mapping.crosswalk import NIST_ANCHOR, normalize_framework


@dataclass
class SynthesisTopic:
    name: str
    controls: list[Control]


#: Frontmatter keys `synthesize` writes and `generate` reads back. The
#: synthesis file is the hand-off between two separate commands, so the topic's
#: ownership has to travel *in* the file rather than being re-supplied on the
#: second command line — otherwise the owning team is known when the topic is
#: assembled and forgotten by the time the document is drafted.
#:
#: `content_class` and `derived_from` travel for the same reason and matter
#: more. A synthesis drawn from a HITRUST export is a restatement of HITRUST
#: requirement text, but once written it is an ordinary file under `output/`,
#: and `classify_path` reads an ordinary file as the organization's own. The
#: class `synthesize` worked out was dropped at the hand-off, and `generate`
#: sent licensed-derived text to whatever provider was configured.
SYNTHESIS_FRONTMATTER_KEYS = (
    "topic",
    "owner",
    "cadence",
    "evidence",
    "nist_controls",
    "content_class",
    "derived_from",
)


def write_synthesis(
    body: str,
    *,
    topic: str,
    owner: str = "",
    cadence: str = "",
    evidence: list[str] | None = None,
    nist_controls: list[str] | None = None,
    content_class: str | None = None,
    derived_from: list[str] | None = None,
) -> str:
    """Render a synthesis file: YAML frontmatter, then the requirement list.

    Only keys with a value are emitted, so a call with none of them writes
    the requirement list alone. `synthesize` always passes a content class,
    so every synthesis it writes says what it was drawn from.
    """
    import yaml

    metadata = {
        "topic": topic,
        "owner": owner,
        "cadence": cadence,
        "evidence": evidence or [],
        "nist_controls": nist_controls or [],
        "content_class": content_class or "",
        "derived_from": derived_from or [],
    }
    metadata = {k: v for k, v in metadata.items() if v}
    if not metadata:
        return body.rstrip() + "\n"
    front = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{front}\n---\n\n{body.rstrip()}\n"


def read_synthesis(text: str) -> tuple[dict, str]:
    """Split a synthesis file into `(metadata, body)`.

    A file with no frontmatter yields `({}, text)` — synthesis files written
    before this existed still load.
    """
    import frontmatter

    parsed = frontmatter.loads(text)
    return dict(parsed.metadata), parsed.content


_SYSTEM_PROMPT = """You are a compliance content synthesis engine. Merge \
overlapping control requirements from multiple frameworks, for one topic, \
into a deduplicated set of plain-English requirement statements.

Rules:
- Base every statement ONLY on the control text provided below — never rely
  on your own knowledge of what a framework "usually" requires. If the
  provided text doesn't specify a detail (e.g. a minimum length or a
  frequency), do not invent one.
- Merge requirements that say the same thing across frameworks into one
  statement rather than repeating it once per framework.
- Where a "Framework-defined parameter value" is given, use it in place of
  the matching `[Assignment: ...]` or `[Selection: ...]` placeholder in the
  control text. That value is the framework's own decision, not a guess —
  it is the one case where filling in a placeholder is correct. Leave any
  placeholder with no such value as it stands.
- Treat "Additional framework requirements" as normative: they are
  requirements that framework adds on top of the base control, so they earn
  their own statement or extend an existing one.
- Where frameworks genuinely disagree (e.g. different minimums), keep them
  as separate statements rather than silently picking one.
- Output a markdown bullet list, one requirement per bullet, and nothing
  else — no preamble, no closing remarks.
- End every bullet with an inline source tag listing every framework/control
  it was drawn from, e.g. `[NIST IA-5 | GovRAMP IA-5]`. Include the baseline
  in the tag when the source control specifies one, e.g.
  `[GovRAMP IA-5 Moderate]`.
"""


def _render_profile_additions(item, prefix: str = "") -> list[str]:
    """The two things a profile (GovRAMP, FedRAMP) adds to a base control.

    Worth handing to the model rather than dropping, because both change
    what the merged requirement should say. A profile that has already
    decided "at least every 3 years" turns `[Assignment:
    organization-defined frequency]` from a placeholder the model would
    otherwise fill in by guessing into a value with a citation behind it —
    which is the same reason `parameters/ledger.py` exists. The added
    requirements are normative sentences that appear in no base catalog, so
    a synthesis drawn only from 800-53 would silently omit them.
    """
    lines = []
    if item.parameter_values:
        values = "; ".join(
            f"{citation} = {value}" for citation, value in item.parameter_values.items()
        )
        lines.append(f"{prefix}Framework-defined parameter values: {values}")
    if item.additional_requirements:
        flattened = " ".join(item.additional_requirements.split())
        lines.append(f"{prefix}Additional framework requirements: {flattened}")
    return lines


def _render_control(control: Control) -> str:
    lines = [f"### {control.framework} {control.control_id} — {control.title}"]
    if control.baseline:
        lines.append(f"Baseline: {control.baseline}")
    if control.control_statement:
        lines.append(f"Control statement: {control.control_statement}")
    if control.discussion:
        lines.append(f"Discussion: {control.discussion}")
    lines.extend(_render_profile_additions(control))
    for enh in control.enhancements:
        lines.append(
            f"Enhancement {enh.enhancement_id} ({enh.baseline}) — {enh.title}: {enh.description}"
        )
        lines.extend(_render_profile_additions(enh, prefix="  "))
    return "\n".join(lines)


def synthesize_topic(topic: SynthesisTopic, provider: LLMProvider) -> str:
    if not topic.controls:
        raise ValueError(f"SynthesisTopic {topic.name!r} has no controls to synthesize.")

    source_text = "\n\n".join(_render_control(c) for c in topic.controls)
    prompt = (
        f"Topic: {topic.name}\n\n"
        f"Source controls:\n\n{source_text}\n\n"
        "Produce the merged requirement list per the rules above."
    )
    from policyforge.llm import effort

    # Only the system prompt repeats here — every topic brings different
    # controls — so the breakpoint sits at the end of it. Worth marking
    # because a run synthesizes a topic set, not one topic.
    response = effort.call(
        provider,
        effort=effort.SYNTHESIS,
        cache=True,
        system=_SYSTEM_PROMPT,
        prompt=prompt,
        temperature=0.1,
        max_tokens=SYNTHESIS_TOKENS,
    )
    return effort.document_text(response, what="synthesis")


#: The output budget for one topic's merged requirement list.
#:
#: Sized from the first 20-topic cost run (glm-5.3-flash via OpenRouter,
#: 2026-09-17, the 20 starter topics over NIST, FedRAMP, ARC-AMPE and
#: HIPAA). With no budget named, the 4096 default applied and 11 of 20
#: syntheses stopped at it and were written as finished. The nine that
#: completed used a median of 4096 and up to 13,569 output tokens, p90
#: 12,170 — a reasoning model spends part of the budget thinking before
#: it writes, and the ledger counts both. So a topic that finishes needs
#: room for about 14k, and `llm/effort.py` retries a cut-off reply once at
#: twice this before refusing. Measured, and to be re-measured when the
#: cost table is re-run on this budget.
SYNTHESIS_TOKENS = 16384


def build_synthesis_topic(
    name: str,
    nist_control_ids: list[str],
    controls: list[Control],
    crosswalk: dict[str, dict[str, list[str]]],
) -> SynthesisTopic:
    """Assemble a SynthesisTopic by pulling the given NIST controls plus,
    via `crosswalk` (see mapping/crosswalk.py's `build_crosswalk`), every
    other framework's control that maps to them. `controls` is the pool to
    pull from — typically every loaded control across all enabled
    frameworks.

    A crosswalk entry may name either a control or one of its enhancements,
    since some frameworks are mapped at the sub-requirement level (NIST's
    HIPAA-to-800-53 crosswalk maps most of its rows to individual
    Required/Addressable implementation specifications rather than to the
    parent Standard). An enhancement ID resolves to the control that carries
    it, so those mappings pull their surrounding requirement into the topic
    instead of silently matching nothing.
    """
    by_framework_id = {(normalize_framework(c.framework), c.control_id): c for c in controls}
    for control in controls:
        framework = normalize_framework(control.framework)
        for enhancement in control.enhancements:
            by_framework_id.setdefault((framework, enhancement.enhancement_id), control)

    topic_controls: list[Control] = []
    seen: set[int] = set()

    def _add(control: Control | None) -> None:
        if control is not None and id(control) not in seen:
            seen.add(id(control))
            topic_controls.append(control)

    for nist_id in nist_control_ids:
        _add(by_framework_id.get((NIST_ANCHOR, nist_id)))
        for framework, equivalent_ids in crosswalk.get(nist_id, {}).items():
            for equivalent_id in equivalent_ids:
                _add(by_framework_id.get((framework, equivalent_id)))

    return SynthesisTopic(name=name, controls=topic_controls)
