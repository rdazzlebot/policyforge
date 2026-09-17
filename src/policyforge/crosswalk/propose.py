"""A model's reading of each requirement against 800-53, for a person to review.

This does not decide anything. It reads one requirement and a short list of
candidate controls (`candidates.py`) and says which of them address it, how,
and with which words of each text. Those become notes on the organization's
overlay: a published pair the model could quote a basis for gains the quote;
one it could not is flagged; a pair nobody published is added as proposed.
Only a person moves a row's status.

**Why it cannot decide.** Measured on the 75 HIPAA requirements before this
was built (see MEASUREMENTS.md): two models confirmed 31% and 41% of NIST's
published pairs while being shown every one of them, and agreed with each
other on 58% of what they asserted. Reading the disagreements, the models
were not simply wrong. NIST's mapping links a requirement to controls that
*support* it — IR-5 and IR-6 for reviewing system activity, AC-4 for access
authorization — where the models map controls that *carry the obligation*.
Those are different questions, and which one an organization wants answered
is its decision. The value of this step is that it puts the difference, with
the words that justify each side, in front of the person making it.

**The model is not told which pairs were published.** Its candidates are
sorted by id with the published ones among them. Told which ones NIST chose,
agreeing with NIST is the easy answer, and a confirmation would say nothing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

from policyforge.crosswalk.candidates import CatalogEntry, WordIndex, candidates_for
from policyforge.crosswalk.grounding import grounded, minimum_for
from policyforge.crosswalk.overlay import (
    ACCEPTED,
    PROPOSED,
    REJECTED,
    MappingRow,
    Overlay,
    published_pairs,
)
from policyforge.llm.base import SchemaReplyError
from policyforge.llm.prompts import REGISTRY, Prompt, register

#: The relationships a model may assert. `unspecified` is for published pairs
#: whose relationship nobody stated, never an answer.
ASSERTABLE = ("equal", "subset", "superset", "intersects")

#: On a published pair the model was shown and gave no quotable basis for.
#: Cleared and recomputed on every run for rows nobody has reviewed.
NOT_CONFIRMED = "not-confirmed-by-model"

PROPOSE_PROMPT = register(
    Prompt(
        name="crosswalk.propose",
        version=1,
        text="""You map one requirement from a compliance framework to the \
NIST SP 800-53 Rev. 5 controls that address it.

You are given the REQUIREMENT and a list of CANDIDATE controls. Most \
candidates are not related; they were found by word overlap. Return only the \
candidates that genuinely address the requirement, each with:

- relationship, read from the requirement's side:
  - equal: the two require the same thing.
  - subset: the requirement is narrower; the control fully covers it.
  - superset: the requirement is broader; the control covers only part.
  - intersects: they overlap, and each requires something the other does not.
- requirement_quote: words copied exactly from the requirement text that the
  control addresses.
- control_quote: words copied exactly from the control text that address them.

Rules:
1. Judge the texts, not what you remember about published crosswalks. A shared
   word ("audit", "access", "review") is not a relationship; the obligation has
   to be the same kind of obligation.
2. Quotes must be copied from the text given, at least four words each where
   the text is that long. A mapping you cannot quote is a mapping you should
   not make.
3. Returning no candidates is correct when none address the requirement, and
   some requirements (definitions, compliance dates) are not controls at all.
4. A requirement listed under a parent standard is part of that standard, and
   is read in its context: a specification under a training standard is about
   what the workforce is trained on.
5. A control ending in -1 (AC-1, PS-1) is that family's policy and procedures
   control. It addresses a requirement to have policies or procedures for that
   family's subject.
6. Reply with the JSON object only, including when the list is empty.""",
    )
)


@dataclass
class Requirement:
    requirement_id: str
    title: str
    text: str
    #: The standard an implementation specification sits under, as text, or "".
    parent: str = ""


@dataclass
class ProposedMapping:
    control: str
    relationship: str
    requirement_quote: str
    control_quote: str


@dataclass
class Proposal:
    requirement_id: str
    candidates: list[str]
    mappings: list[ProposedMapping] = field(default_factory=list)
    #: Returned by the model and refused: an id not on the list, a relationship
    #: not in the vocabulary, or a quote the text does not contain.
    refused: list[dict] = field(default_factory=list)
    error: str = ""


def requirements_of(controls, framework: str) -> list[Requirement]:
    wanted = framework.casefold()
    found = []
    for control in controls:
        if control.framework.casefold() != wanted:
            continue
        found.append(
            Requirement(control.control_id, control.title, control.control_statement or "")
        )
        parent = f"{control.control_id} — {control.title}: {control.control_statement or ''}"
        for enhancement in control.enhancements:
            found.append(
                Requirement(
                    enhancement.enhancement_id,
                    enhancement.title,
                    enhancement.description or "",
                    parent=parent,
                )
            )
    return found


def _schema(candidates: list[str]) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "mappings",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "mappings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "control": {"type": "string", "enum": candidates or ["none"]},
                                "relationship": {"type": "string", "enum": list(ASSERTABLE)},
                                "requirement_quote": {"type": "string"},
                                "control_quote": {"type": "string"},
                            },
                            "required": [
                                "control",
                                "relationship",
                                "requirement_quote",
                                "control_quote",
                            ],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["mappings"],
                "additionalProperties": False,
            },
        },
    }


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def parse_reply(text: str) -> list:
    """The rows in a reply, from the schema's object or a common near miss.

    Measured on glm-5.3-flash: 13 of 75 replies held their rows in the wrong
    wrapper — 9 inside a markdown code fence, 4 as a bare list — and were
    lost as errors, since neither is the schema's object. The rows
    themselves are still validated one by one, so reading past the wrapper
    admits nothing the schema would have kept out.
    """
    fenced = _FENCE.match(text)
    data = json.loads(fenced.group(1) if fenced else text)
    if isinstance(data, dict):
        data = data.get("mappings", [])
    if not isinstance(data, list):
        raise ValueError("reply holds no list of mappings")
    return data


def _render(requirement: Requirement, framework: str, candidates, entries) -> str:
    catalog = "\n\n".join(f"{i} — {entries[i].title}\n{entries[i].text[:900]}" for i in candidates)
    context = f"UNDER THE STANDARD\n\n{requirement.parent}\n\n" if requirement.parent else ""
    return (
        f"{context}REQUIREMENT ({framework})\n\n"
        f"{requirement.requirement_id} — {requirement.title}\n{requirement.text}\n\n"
        f"CANDIDATES\n\n{catalog}"
    )


def propose_for(
    requirement: Requirement,
    *,
    framework: str,
    published: list[str],
    entries: dict[str, CatalogEntry],
    index: WordIndex,
    provider,
) -> Proposal:
    from policyforge.llm import effort

    candidates = candidates_for(
        f"{requirement.title} {requirement.text}",
        published=published,
        entries=entries,
        index=index,
    )
    proposal = Proposal(requirement.requirement_id, candidates)
    try:
        response = effort.call_json(
            provider,
            effort=effort.MAPPING,
            system=PROPOSE_PROMPT,
            prompt=_render(requirement, framework, candidates, entries),
            schema=_schema(candidates),
            temperature=0.0,
            max_tokens=6000,
        )
        rows = parse_reply(response.text)
    except SchemaReplyError as exc:
        try:
            rows = parse_reply(exc.text)
        except ValueError:
            proposal.error = str(exc)[:300]
            return proposal
    except (ValueError, RuntimeError) as exc:
        proposal.error = f"{type(exc).__name__}: {exc}"[:300]
        return proposal

    requirement_words = f"{requirement.title} {requirement.text} {requirement.parent}"
    shortest = minimum_for(requirement.text)
    seen = set()
    for row in rows:
        control = row.get("control") if isinstance(row, dict) else None
        valid = (
            control in candidates
            and control not in seen
            and row.get("relationship") in ASSERTABLE
            and grounded(
                str(row.get("requirement_quote", "")), requirement_words, min_words=shortest
            )
            and grounded(
                str(row.get("control_quote", "")),
                f"{entries[control].title} {entries[control].text}",
            )
        )
        if not valid:
            proposal.refused.append(row if isinstance(row, dict) else {"row": row})
            continue
        seen.add(control)
        proposal.mappings.append(
            ProposedMapping(
                control=control,
                relationship=row["relationship"],
                requirement_quote=str(row["requirement_quote"]).strip(),
                control_quote=str(row["control_quote"]).strip(),
            )
        )
    return proposal


@dataclass
class MergeReport:
    confirmed: int = 0
    not_confirmed: int = 0
    proposed: int = 0
    #: Rows a person has already decided, left exactly as they were.
    left_reviewed: int = 0
    #: Pairs a person rejected, which the model named again. Not re-proposed.
    rejected_again: int = 0
    errors: list[str] = field(default_factory=list)


def merge(
    overlay: Overlay,
    proposals: list[Proposal],
    controls,
    *,
    model: str,
    today: date | None = None,
) -> MergeReport:
    """Record `proposals` on `overlay`, in place. Never changes a decision.

    A requirement the overlay does not list yet is first seeded from the
    published mapping, so recording a proposal on it does not unmap the
    published pairs the model happened not to confirm.
    """
    prompt = REGISTRY["crosswalk.propose"]
    proposed_by = {
        "model": model,
        "prompt": prompt.label,
        "date": (today or date.today()).isoformat(),
    }
    published = published_pairs(controls, overlay.framework, overlay.anchor)
    report = MergeReport()

    for proposal in proposals:
        rid = proposal.requirement_id
        if proposal.error:
            report.errors.append(f"{rid}: {proposal.error}")
            continue
        rows = overlay.requirements.get(rid)
        if rows is None:
            rows = [
                MappingRow(control=c, status=ACCEPTED, sources=["published"])
                for c in published.get(rid, [])
            ]
            overlay.requirements[rid] = rows
        by_control = {row.control: row for row in rows}
        asserted = {m.control: m for m in proposal.mappings}

        for row in rows:
            if row.reviewed_by:
                report.left_reviewed += 1
                continue
            if NOT_CONFIRMED in row.flags:
                row.flags.remove(NOT_CONFIRMED)
            mapping = asserted.get(row.control)
            if mapping is None:
                # Shown to the model and not asserted. Only meaningful for a
                # row that is live or waiting; a control that was never a
                # candidate was not judged at all.
                if row.control in proposal.candidates and row.status != REJECTED:
                    row.flags.append(NOT_CONFIRMED)
                    report.not_confirmed += 1
                continue
            if row.status == REJECTED:
                continue
            _annotate(row, mapping, proposed_by)
            report.confirmed += row.status == ACCEPTED

        for control, mapping in asserted.items():
            existing = by_control.get(control)
            if existing is not None:
                report.rejected_again += existing.status == REJECTED
                report.proposed += existing.status == PROPOSED and not existing.reviewed_by
                continue
            row = MappingRow(control=control, status=PROPOSED, sources=["model"])
            _annotate(row, mapping, proposed_by)
            rows.append(row)
            report.proposed += 1
    return report


def _annotate(row: MappingRow, mapping: ProposedMapping, proposed_by: dict) -> None:
    if row.relationship == "unspecified" or "model" in row.sources:
        row.relationship = mapping.relationship
    row.evidence = {"requirement": mapping.requirement_quote, "control": mapping.control_quote}
    if "model" not in row.sources:
        row.sources.append("model")
    row.proposed_by = dict(proposed_by)
