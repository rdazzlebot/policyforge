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
from policyforge.mapping.crosswalk import normalize_framework


@dataclass
class SynthesisTopic:
    name: str
    controls: list[Control]


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
- Where frameworks genuinely disagree (e.g. different minimums), keep them
  as separate statements rather than silently picking one.
- Output a markdown bullet list, one requirement per bullet, and nothing
  else — no preamble, no closing remarks.
- End every bullet with an inline source tag listing every framework/control
  it was drawn from, e.g. `[NIST IA-5 | GovRAMP IA-5]`. Include the baseline
  in the tag when the source control specifies one, e.g.
  `[GovRAMP IA-5 Moderate]`.
"""


def _render_control(control: Control) -> str:
    lines = [f"### {control.framework} {control.control_id} — {control.title}"]
    if control.baseline:
        lines.append(f"Baseline: {control.baseline}")
    if control.control_statement:
        lines.append(f"Control statement: {control.control_statement}")
    if control.discussion:
        lines.append(f"Discussion: {control.discussion}")
    for enh in control.enhancements:
        lines.append(
            f"Enhancement {enh.enhancement_id} ({enh.baseline}) — "
            f"{enh.title}: {enh.description}"
        )
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
    response = provider.generate(system=_SYSTEM_PROMPT, prompt=prompt, temperature=0.1)
    return response.text.strip()


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
    frameworks."""
    by_framework_id = {(normalize_framework(c.framework), c.control_id): c for c in controls}

    topic_controls: list[Control] = []
    seen: set[int] = set()

    def _add(control: Control | None) -> None:
        if control is not None and id(control) not in seen:
            seen.add(id(control))
            topic_controls.append(control)

    for nist_id in nist_control_ids:
        _add(by_framework_id.get(("nist", nist_id)))
        for framework, equivalent_ids in crosswalk.get(nist_id, {}).items():
            for equivalent_id in equivalent_ids:
                _add(by_framework_id.get((framework, equivalent_id)))

    return SynthesisTopic(name=name, controls=topic_controls)
