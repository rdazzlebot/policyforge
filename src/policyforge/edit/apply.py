"""Apply an approved `EditPlan` to a document, and check it was applied
faithfully.

Second half of the editing harness. The planner decided *what* changes; this
rewrites the document to make exactly those changes and nothing else.

The constraint that matters here is restraint. A model handed a governance
document and asked to change one section will cheerfully also reflow prose,
renumber headings, harmonise terminology and drop a citation it judged
redundant — none of which anyone reviewed, all of which land on a live
policy page. So the prompt is written around leaving things alone, and
`check_edit` verifies the parts that must not change afterwards rather than
trusting that instruction held.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from policyforge.edit.plan import EditPlan
from policyforge.llm.base import LLMProvider

#: Inline framework source tags, e.g. `[NIST AC-2 | HIPAA 164.308(a)(3)(i)]`.
#: These are the document's traceability back to the frameworks it was drawn
#: from; losing one silently is a compliance defect, not a formatting nit.
_SOURCE_TAG_RE = re.compile(r"\[(?:NIST|HIPAA|FedRAMP|HITRUST|GovRAMP|ARC-AMPE)\s[^\]]*\]")

#: Confluence macros this project's own exporter emits. Anything else in a
#: fetched page came from elsewhere and will not survive the
#: storage -> markdown -> storage round trip.
_SUPPORTED_MACROS = {"code"}
_MACRO_RE = re.compile(r'<ac:structured-macro\s+ac:name="([^"]+)"')


@dataclass
class EditCheck:
    """What changed, and what should not have."""

    dropped_source_tags: list[str] = field(default_factory=list)
    removed_headings: list[str] = field(default_factory=list)
    unchanged: bool = False
    lines_added: int = 0
    lines_removed: int = 0

    @property
    def is_clean(self) -> bool:
        return not (self.dropped_source_tags or self.removed_headings)


def detect_unsupported_macros(storage_html: str) -> list[str]:
    """Confluence macros in a page that this tool cannot round-trip.

    The edit path is storage format -> markdown -> edit -> storage format.
    That is lossless only for what `confluence_exporter.py` itself emits; a
    panel, expand block, status lozenge or page-properties macro would be
    flattened to approximate HTML or lost outright on the way back. Editing
    such a page would quietly damage parts of it nobody asked to change, so
    callers are expected to check this first and refuse rather than warn
    after the fact.
    """
    return sorted(set(_MACRO_RE.findall(storage_html)) - _SUPPORTED_MACROS)


def _headings(document: str) -> list[str]:
    return [
        line.lstrip("#").strip() for line in document.splitlines() if line.lstrip().startswith("#")
    ]


def check_edit(original: str, revised: str, *, plan: EditPlan) -> EditCheck:
    """Compare a revision against its source for damage the plan didn't call for.

    Only losses are flagged. Additions are what the plan asked for; it's the
    things that quietly went missing that need a human to see them.
    """
    check = EditCheck(unchanged=original.strip() == revised.strip())

    original_tags = _SOURCE_TAG_RE.findall(original)
    revised_tags = set(_SOURCE_TAG_RE.findall(revised))
    check.dropped_source_tags = sorted({t for t in original_tags if t not in revised_tags})

    # A heading the plan explicitly removes is expected to disappear; any
    # other missing heading is collateral.
    intentionally_removed = {step.target for step in plan.steps if step.kind == "remove"}
    revised_headings = set(_headings(revised))
    check.removed_headings = sorted(
        h
        for h in _headings(original)
        if h not in revised_headings and h not in intentionally_removed
    )

    original_lines = original.splitlines()
    revised_lines = revised.splitlines()
    import difflib

    for line in difflib.ndiff(original_lines, revised_lines):
        if line.startswith("+ "):
            check.lines_added += 1
        elif line.startswith("- "):
            check.lines_removed += 1
    return check


_SYSTEM_PROMPT = """You are applying an approved, specific set of edits to a \
published information security governance document.

Return ONLY the complete revised document as CommonMark markdown. No
preamble, no explanation, no code fence around the whole thing.

Rules, in priority order:
1. Make exactly the edits listed in the plan. Make no other change of any
   kind. Do not reflow paragraphs you were not asked to touch, do not
   renumber or re-title sections, do not harmonise wording, do not reorder
   content, do not "improve" anything. Text outside the planned edits must
   come back byte-for-byte identical.
2. Preserve every inline source tag (e.g. `[NIST AC-2 | HIPAA
   164.308(a)(3)(i)]`) exactly as written. These trace requirements back to
   the frameworks they came from. If an edit would strand a citation, keep
   the citation and adjust the surrounding sentence instead.
3. Keep the document's existing heading structure and heading text unless a
   planned step explicitly changes it.
4. Match the surrounding document's voice and formality. These are formal
   documents: "must"/"shall" for requirements, not "should try to".
5. Where an edit needs a detail you have not been given — a vendor, a team, a
   frequency, a threshold — write a `[Square-Bracket Placeholder]` naming
   what is needed. Never invent a specific value.
6. Output valid CommonMark: properly closed fences, well-formed tables,
   consistent list markers.
"""


def apply_edit_plan(
    plan: EditPlan,
    document: str,
    provider: LLMProvider,
) -> str:
    """Rewrite `document` with the plan's edits applied."""
    if plan.is_empty:
        raise ValueError(
            "The plan contains no steps — nothing to apply. Check the plan's "
            "`out_of_scope` for why the instruction produced no edits."
        )
    if not document.strip():
        raise ValueError("document is empty — nothing to edit.")

    steps = "\n".join(
        f"{index}. [{step.kind}] target: {step.target}\n   change: {step.summary}"
        for index, step in enumerate(plan.steps, start=1)
    )
    prompt = (
        f"Original instruction (for context only — the plan below is what you apply):\n"
        f"{plan.instruction}\n\n"
        f"Approved plan:\n{steps}\n\n"
        f"Current document:\n\n{document}\n\n"
        "Return the complete revised document now."
    )
    response = provider.generate(
        system=_SYSTEM_PROMPT, prompt=prompt, temperature=0.0, max_tokens=8192
    )
    return response.text.strip() + "\n"
