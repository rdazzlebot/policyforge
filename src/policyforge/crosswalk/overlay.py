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


def printable(text) -> str:
    """`text` with control characters replaced by spaces, tabs kept.

    Quotes come from a model and rationales from a hand-edited file, and
    `review` prints both to a terminal. A quote carrying an escape sequence
    passes word-based grounding untouched — the checker compares words, not
    bytes — so the characters are removed where text enters the overlay rather
    than trusted to have been caught upstream.
    """
    return "".join(
        ch if ch == "\t" or (ch.isprintable() and ch not in "\x7f") else " " for ch in str(text)
    ).strip()


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
    #: Machine-set notes for a reviewer, such as `not-confirmed-by-model`.
    #: Never change what reaches the pipeline; only `status` does.
    flags: list[str] = field(default_factory=list)
    #: A relationship a model suggested. Held apart from `relationship`,
    #: which coverage reads: only `review` promotes it, so a model reply can
    #: never change a report before a person has seen it.
    proposed_relationship: str = ""

    @property
    def needs_review(self) -> bool:
        return not self.reviewed_by and (self.status == PROPOSED or bool(self.flags))

    def as_record(self) -> dict:
        record: dict = {
            "control": self.control,
            "relationship": self.relationship,
            "status": self.status,
        }
        for name in (
            "proposed_relationship",
            "sources",
            "flags",
            "evidence",
            "rationale",
            "proposed_by",
            "reviewed_by",
        ):
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
    return {printable(k): printable(v) for k, v in value.items()}


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
        framework=printable(data["framework"]),
        anchor=printable(data.get("anchor") or "nist"),
        path=path,
    )
    for requirement_id, rows in raw.items():
        rid = printable(requirement_id)
        if rows is None:
            overlay.requirements[rid] = []
            continue
        if not isinstance(rows, list):
            raise OverlayError(f"{label}: {rid} must be a list of rows.")
        parsed = []
        seen: dict[str, int] = {}
        for index, row in enumerate(rows, start=1):
            where = f"{label}: {rid} row {index}"
            if not isinstance(row, dict) or not row.get("control"):
                raise OverlayError(f"{where} needs a `control:`.")
            # Upper-cased so `si-3` is SI-3 rather than a control nobody has.
            control = printable(row["control"]).upper()
            if control in seen:
                raise OverlayError(
                    f"{where}: {control} is already row {seen[control]} for {rid}. One "
                    "requirement names a control once; two rows could accept and reject "
                    "the same pair."
                )
            seen[control] = index
            relationship = str(row.get("relationship") or "unspecified")
            proposed_relationship = str(row.get("proposed_relationship") or "")
            status = str(row.get("status") or PROPOSED)
            for name, value in (
                ("relationship", relationship),
                ("proposed_relationship", proposed_relationship or "unspecified"),
            ):
                if value not in RELATIONSHIPS:
                    allowed = ", ".join(RELATIONSHIPS)
                    raise OverlayError(f"{where}: {name} {value!r} is not one of {allowed}.")
            if status not in STATUSES:
                raise OverlayError(
                    f"{where}: status {status!r} is not one of {', '.join(STATUSES)}."
                )
            sources = row.get("sources") or []
            if isinstance(sources, str):
                sources = [sources]
            flags = row.get("flags") or []
            if isinstance(flags, str):
                flags = [flags]
            parsed.append(
                MappingRow(
                    control=control,
                    relationship=relationship,
                    status=status,
                    sources=[printable(s) for s in sources],
                    evidence=_string_map(row.get("evidence"), f"{where} evidence"),
                    rationale=printable(row.get("rationale") or ""),
                    proposed_by=_string_map(row.get("proposed_by"), f"{where} proposed_by"),
                    reviewed_by=_string_map(row.get("reviewed_by"), f"{where} reviewed_by"),
                    flags=[printable(f) for f in flags],
                    proposed_relationship=proposed_relationship,
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


def overlay_files(directory: Path = DEFAULT_OVERLAY_DIR) -> list[Path]:
    """The overlay files in `directory`, `.yaml` and `.yml` alike, in name order."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix in (".yaml", ".yml") and p.is_file())


def overlay_digests(directory: Path = DEFAULT_OVERLAY_DIR) -> dict[str, str]:
    """{file name: sha256 of its bytes} for every overlay in `directory`.

    What `map` records beside the crosswalk it builds, and what `synthesize`
    compares against, so a crosswalk built before an overlay was added,
    edited or deleted is recognised as stale. Content, not modification time:
    a timestamp can tie, and a deleted file has none.
    """
    import hashlib

    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in overlay_files(directory)}


def provenance_path(crosswalk_path: Path) -> Path:
    """Where `map` records which overlays a crosswalk was built from.

    Beside the crosswalk rather than inside it: every reader of crosswalk.json
    takes its top-level keys to be 800-53 control ids.
    """
    crosswalk_path = Path(crosswalk_path)
    return crosswalk_path.with_name(f"{crosswalk_path.stem}.overlays.json")


def load_overlays(directory: Path = DEFAULT_OVERLAY_DIR) -> list[Overlay]:
    """Every overlay in `directory`. A missing directory is no overlays.

    Two files for one framework are refused rather than applied in name
    order: the later one would silently replace the earlier one's decisions
    for every requirement both list.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []
    overlays = [load_overlay(p) for p in overlay_files(directory)]
    first: dict[str, Overlay] = {}
    for overlay in overlays:
        key = _framework_key(overlay.framework)
        if key in first:
            raise OverlayError(
                f"{first[key].path} and {overlay.path} both map {overlay.framework!r}. "
                "Keep one file per framework."
            )
        first[key] = overlay
    return overlays


def dump_overlay(overlay: Overlay) -> str:
    import yaml

    return yaml.safe_dump(overlay.as_record(), sort_keys=False, allow_unicode=True, width=100)


def _requirement_targets(controls, framework: str) -> dict:
    wanted = _framework_key(framework)
    targets = {}
    for control in controls:
        if _framework_key(control.framework) != wanted:
            continue
        targets[control.control_id] = control
        for enhancement in control.enhancements:
            targets[enhancement.enhancement_id] = enhancement
    return targets


def _anchor_keys(crosswalk: dict, anchor: str) -> list[str]:
    """The keys in a `source_crosswalk` that name the anchor framework.

    Catalogs do not agree on the key: the HIPAA and NIST loaders write
    `nist`, and FedRAMP, GovRAMP and ARC-AMPE write `NIST 800-53`. Reading
    only `nist` seeded those catalogs with no pairs at all, and a rejection
    left the `NIST 800-53` pair in place.
    """
    from policyforge.mapping.crosswalk import normalize_framework

    return [key for key in crosswalk if normalize_framework(key) == anchor]


def _framework_key(name: str) -> str:
    """A framework name compared the way a person reads it: case and spacing aside."""
    return " ".join(str(name).split()).casefold()


#: How close an overlay's framework name must be to a loaded catalog's name to
#: be read as a misspelling of it. "HIPPA Security Rule" against "HIPAA Security
#: Rule" is 0.95; "FedRAMP" against "ARC-AMPE" is 0.53, and against "GovRAMP"
#: 0.57. A shortened name — "HIPAA" for "HIPAA Security Rule", 0.42 — is caught
#: separately, by its words all appearing in the catalog's name.
TYPO_SIMILARITY = 0.8


def _check_framework_is_loaded(controls, overlay: Overlay) -> None:
    """Refuse an overlay whose framework name looks like a misspelled loaded catalog.

    A framework the loaded catalogs do not include is normal — most commands
    load 800-53 alone — so that on its own is not an error. Two signals
    together make a typo: the name is close to a loaded catalog's name, and
    the requirement ids it lists belong to that catalog. Either alone is not
    enough. FedRAMP, GovRAMP and ARC-AMPE all number their requirements with
    800-53 ids, so ids alone would read a FedRAMP overlay as a misspelled
    800-53 or ARC-AMPE one whenever FedRAMP is not loaded — the review
    reproduced exactly that — and the anchor catalog is never a candidate.
    """
    from difflib import SequenceMatcher

    from policyforge.mapping.crosswalk import normalize_framework

    if _requirement_targets(controls, overlay.framework):
        return
    wanted = _framework_key(overlay.framework)
    listed = set(overlay.requirements)
    owners: set[str] = set()
    for control in controls:
        if normalize_framework(control.framework) == overlay.anchor:
            continue
        if control.control_id in listed or any(
            e.enhancement_id in listed for e in control.enhancements
        ):
            owners.add(control.framework)

    def resembles(name: str) -> bool:
        key = _framework_key(name)
        return SequenceMatcher(None, wanted, key).ratio() >= TYPO_SIMILARITY or set(
            wanted.split()
        ) <= set(key.split())

    names = sorted(name for name in owners if resembles(name))
    if names:
        raise OverlayError(
            f"{overlay.path or 'overlay'}: framework {overlay.framework!r} matches no loaded "
            f"catalog, but reads like {', '.join(repr(n) for n in names)}, whose requirement "
            "ids it lists. Correct the `framework:` line; until then none of its decisions apply."
        )


def apply_overlays(controls, overlays: list[Overlay]) -> int:
    """Replace each listed requirement's mapping with its accepted rows, in place.

    Returns how many requirements were rewritten. The value is written in the
    free-text form `mapping/crosswalk.py` already reads ("SI-3, IR-6"), so
    nothing downstream needs to know an overlay exists.
    """
    rewritten = 0
    for overlay in overlays:
        _check_framework_is_loaded(controls, overlay)
        targets = _requirement_targets(controls, overlay.framework)
        for requirement_id in overlay.requirements:
            target = targets.get(requirement_id)
            if target is None:
                continue
            for key in _anchor_keys(target.source_crosswalk, overlay.anchor):
                target.source_crosswalk.pop(key)
            ids = [row.control for row in overlay.accepted(requirement_id)]
            if ids:
                target.source_crosswalk[overlay.anchor] = ", ".join(ids)
            rewritten += 1
    return rewritten


def published_pairs(controls, framework: str, anchor: str = "nist") -> dict[str, list[str]]:
    """The catalog's own mapping for `framework`, before any overlay."""
    from policyforge.mapping.crosswalk import _extract_ids

    pairs = {}
    for rid, target in _requirement_targets(controls, framework).items():
        ids: dict[str, None] = {}
        for key in _anchor_keys(target.source_crosswalk, anchor):
            ids.update(dict.fromkeys(_extract_ids(target.source_crosswalk[key])))
        pairs[rid] = list(ids)
    return pairs


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
    from policyforge.mapping.crosswalk import normalize_framework

    anchor_ids = set()
    for control in controls:
        if normalize_framework(control.framework) == overlay.anchor:
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
            if row.needs_review:
                check.proposed += 1
            if anchor_ids and row.control not in anchor_ids:
                check.unknown_controls.append((rid, row.control))
    return check


def accepted_rows(overlays: list[Overlay]) -> dict[tuple[str, str, str], MappingRow]:
    """(framework, requirement id, anchor id) -> the row that accepted the pair.

    Keyed by the normalized framework name `mapping/crosswalk.py` files a
    requirement under, so a report can look a pair up by the same key it
    reached the requirement with.

    Only accepted rows, because only those are what `apply_overlays` writes
    into the crosswalk: a rejected pair is not reachable downstream and must
    not be discoverable through this either.
    """
    from policyforge.mapping.crosswalk import normalize_framework

    found: dict[tuple[str, str, str], MappingRow] = {}
    for overlay in overlays:
        framework = normalize_framework(overlay.framework)
        for requirement_id, rows in overlay.requirements.items():
            for row in rows:
                if row.status == ACCEPTED:
                    found[(framework, requirement_id, row.control)] = row
    return found


def accepted_relationships(overlays: list[Overlay]) -> dict[tuple[str, str, str], str]:
    """(framework, requirement id, anchor id) -> relationship, for accepted rows.

    The relationship half of `accepted_rows`, which is all `coverage` needs.
    Both are keyed the same way, deliberately: two reports disagreeing about
    which pair a key names would be a hard bug to see.
    """
    return {key: row.relationship for key, row in accepted_rows(overlays).items()}
