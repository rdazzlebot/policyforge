"""A per-organization crosswalk file, applied over a catalog's published mapping.

The published HIPAA-to-800-53 crosswalk is a list of pairs. It has no
relationship type and no rationale, several requirements map to twenty
controls or more, and it is stored inside the catalog's `controls.json` —
so re-running `etl-hipaa` wipes it, and an organization that disagrees with
a pair has nowhere to say so that survives the next ETL.

An overlay is that somewhere. One YAML file per framework, in the
organization's repository next to its parameter ledger:

    framework: HIPAA Security Rule
    anchor: nist
    requirements:
      164.308(a)(5)(ii)(B):
        - control: SI-3
          relationship: subset
          status: accepted
          sources: [cprt, model]
          evidence:
            requirement: guarding against, detecting, and reporting malicious software
            control: implement malicious code protection mechanisms
          rationale: SI-3 is the detection half; reporting is IR-6.
          proposed_by: {model: glm-5.3-flash, prompt: crosswalk.propose v1 1a2b3c4d5e6f}
          reviewed_by: {who: ryan, date: 2026-09-17}

**Only accepted rows reach the pipeline.** A requirement the overlay lists
has its mapping *replaced* by that requirement's accepted rows — a rejected
pair is gone, an added one is present, a proposed one waits. A requirement
the overlay does not list keeps the catalog's mapping, so a partial overlay
is a safe one: reviewing ten requirements does not unmap the other sixty.

**Stale is reported, not dropped.** A requirement id or a control id the
catalog no longer has is listed by `check_overlay`, the same way the
parameter ledger treats a key that matches nothing: a catalog revision
surfaces as a question rather than a lost decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_OVERLAY_DIR = Path("config/crosswalks")

#: NIST's OLIR relationship vocabulary (IR 8278A), read from the mapped
#: framework's side: `subset` means the requirement is narrower and the
#: control covers all of it. `unspecified` is what a published pair with no
#: stated relationship becomes when seeded — honest about what is not known.
RELATIONSHIPS = ("equal", "subset", "superset", "intersects", "unspecified")

PROPOSED = "proposed"
ACCEPTED = "accepted"
REJECTED = "rejected"
STATUSES = (PROPOSED, ACCEPTED, REJECTED)


class OverlayError(ValueError):
    """An overlay file that cannot be read as one."""


@dataclass
class MappingRow:
    control: str
    relationship: str = "unspecified"
    status: str = PROPOSED
    sources: list[str] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)
    rationale: str = ""
    proposed_by: dict[str, str] = field(default_factory=dict)
    reviewed_by: dict[str, str] = field(default_factory=dict)

    def as_record(self) -> dict:
        record: dict = {
            "control": self.control,
            "relationship": self.relationship,
            "status": self.status,
        }
        for name in ("sources", "evidence", "rationale", "proposed_by", "reviewed_by"):
            value = getattr(self, name)
            if value:
                record[name] = value
        return record


@dataclass
class Overlay:
    framework: str
    anchor: str = "nist"
    requirements: dict[str, list[MappingRow]] = field(default_factory=dict)
    path: Path | None = None

    def accepted(self, requirement_id: str) -> list[MappingRow]:
        return [r for r in self.requirements.get(requirement_id, []) if r.status == ACCEPTED]

    def as_record(self) -> dict:
        return {
            "framework": self.framework,
            "anchor": self.anchor,
            "requirements": {
                rid: [row.as_record() for row in rows] for rid, rows in self.requirements.items()
            },
        }


def _string_map(value, where: str) -> dict[str, str]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise OverlayError(f"{where} must be a mapping, not {type(value).__name__}.")
    return {str(k): str(v) for k, v in value.items()}


def parse_overlay(data, *, path: Path | None = None) -> Overlay:
    """An `Overlay` from parsed YAML, refusing anything it cannot mean.

    Strict where a typo would change what reaches a document: a misspelled
    status (`acepted`) would otherwise read as not-accepted and silently
    unmap a control, which is exactly the quiet failure this file exists to
    stop. Everything else about a row is optional.
    """
    label = str(path) if path else "overlay"
    if not isinstance(data, dict) or not data.get("framework"):
        raise OverlayError(f"{label}: needs a top-level `framework:` naming the catalog it maps.")
    raw = data.get("requirements") or {}
    if not isinstance(raw, dict):
        raise OverlayError(f"{label}: `requirements:` must map requirement ids to lists of rows.")

    overlay = Overlay(
        framework=str(data["framework"]),
        anchor=str(data.get("anchor") or "nist"),
        path=path,
    )
    for requirement_id, rows in raw.items():
        rid = str(requirement_id)
        if rows is None:
            overlay.requirements[rid] = []
            continue
        if not isinstance(rows, list):
            raise OverlayError(f"{label}: {rid} must be a list of rows.")
        parsed = []
        for index, row in enumerate(rows, start=1):
            where = f"{label}: {rid} row {index}"
            if not isinstance(row, dict) or not row.get("control"):
                raise OverlayError(f"{where} needs a `control:`.")
            relationship = str(row.get("relationship") or "unspecified")
            status = str(row.get("status") or PROPOSED)
            if relationship not in RELATIONSHIPS:
                allowed = ", ".join(RELATIONSHIPS)
                raise OverlayError(
                    f"{where}: relationship {relationship!r} is not one of {allowed}."
                )
            if status not in STATUSES:
                raise OverlayError(
                    f"{where}: status {status!r} is not one of {', '.join(STATUSES)}."
                )
            sources = row.get("sources") or []
            if isinstance(sources, str):
                sources = [sources]
            parsed.append(
                MappingRow(
                    control=str(row["control"]).strip(),
                    relationship=relationship,
                    status=status,
                    sources=[str(s) for s in sources],
                    evidence=_string_map(row.get("evidence"), f"{where} evidence"),
                    rationale=str(row.get("rationale") or "").strip(),
                    proposed_by=_string_map(row.get("proposed_by"), f"{where} proposed_by"),
                    reviewed_by=_string_map(row.get("reviewed_by"), f"{where} reviewed_by"),
                )
            )
        overlay.requirements[rid] = parsed
    return overlay


def load_overlay(path: Path) -> Overlay:
    import yaml

    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise OverlayError(f"{path}: not valid YAML ({exc}).") from exc
    return parse_overlay(data, path=Path(path))


def load_overlays(directory: Path = DEFAULT_OVERLAY_DIR) -> list[Overlay]:
    """Every overlay in `directory`. A missing directory is no overlays."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return [load_overlay(p) for p in sorted(directory.glob("*.yaml"))]


def dump_overlay(overlay: Overlay) -> str:
    import yaml

    return yaml.safe_dump(overlay.as_record(), sort_keys=False, allow_unicode=True, width=100)


def _requirement_targets(controls, framework: str) -> dict:
    wanted = framework.casefold()
    targets = {}
    for control in controls:
        if control.framework.casefold() != wanted:
            continue
        targets[control.control_id] = control
        for enhancement in control.enhancements:
            targets[enhancement.enhancement_id] = enhancement
    return targets


def apply_overlays(controls, overlays: list[Overlay]) -> int:
    """Replace each listed requirement's mapping with its accepted rows, in place.

    Returns how many requirements were rewritten. The value is written in the
    free-text form `mapping/crosswalk.py` already reads ("SI-3, IR-6"), so
    nothing downstream needs to know an overlay exists.
    """
    rewritten = 0
    for overlay in overlays:
        targets = _requirement_targets(controls, overlay.framework)
        for requirement_id in overlay.requirements:
            target = targets.get(requirement_id)
            if target is None:
                continue
            ids = [row.control for row in overlay.accepted(requirement_id)]
            if ids:
                target.source_crosswalk[overlay.anchor] = ", ".join(ids)
            else:
                target.source_crosswalk.pop(overlay.anchor, None)
            rewritten += 1
    return rewritten


def published_pairs(controls, framework: str, anchor: str = "nist") -> dict[str, list[str]]:
    """The catalog's own mapping for `framework`, before any overlay."""
    from policyforge.mapping.crosswalk import _extract_ids

    return {
        rid: _extract_ids(target.source_crosswalk.get(anchor, ""))
        for rid, target in _requirement_targets(controls, framework).items()
    }


def seed_overlay(controls, framework: str, anchor: str = "nist") -> Overlay:
    """An overlay holding exactly the published mapping, every pair accepted.

    Applying a seeded overlay changes nothing, which is the point: it is the
    starting file an organization edits, and until somebody does, the
    pipeline behaves as it did before overlays existed.
    """
    overlay = Overlay(framework=framework, anchor=anchor)
    for rid, ids in published_pairs(controls, framework, anchor).items():
        overlay.requirements[rid] = [
            MappingRow(control=i, status=ACCEPTED, sources=["published"]) for i in ids
        ]
    if not overlay.requirements:
        raise OverlayError(f"No requirements found for framework {framework!r} in these catalogs.")
    return overlay


@dataclass
class OverlayCheck:
    unknown_requirements: list[str] = field(default_factory=list)
    unknown_controls: list[tuple[str, str]] = field(default_factory=list)
    #: Published pairs for a listed requirement that the overlay neither
    #: accepts nor rejects — usually a catalog update the organization has not
    #: looked at yet, since a listed requirement's mapping is the overlay's.
    unreviewed_published: list[tuple[str, str]] = field(default_factory=list)
    proposed: int = 0

    @property
    def is_clean(self) -> bool:
        return not (self.unknown_requirements or self.unknown_controls or self.unreviewed_published)


def check_overlay(overlay: Overlay, controls) -> OverlayCheck:
    """What in `overlay` no longer matches the catalogs, before it is applied."""
    targets = _requirement_targets(controls, overlay.framework)
    published = published_pairs(controls, overlay.framework, overlay.anchor)
    anchor_ids = set()
    for control in controls:
        if control.framework.casefold().split()[0] == overlay.anchor:
            anchor_ids.add(control.control_id)
            anchor_ids.update(e.enhancement_id for e in control.enhancements)

    check = OverlayCheck()
    for rid, rows in overlay.requirements.items():
        if rid not in targets:
            check.unknown_requirements.append(rid)
            continue
        named = {row.control for row in rows}
        check.unreviewed_published.extend(
            (rid, c) for c in published.get(rid, []) if c not in named
        )
        for row in rows:
            if row.status == PROPOSED:
                check.proposed += 1
            if anchor_ids and row.control not in anchor_ids:
                check.unknown_controls.append((rid, row.control))
    return check
