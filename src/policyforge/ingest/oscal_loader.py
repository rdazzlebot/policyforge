"""Parse NIST's official OSCAL edition of SP 800-53 into this project's
common Control/ControlEnhancement schema.

`ingest/nist_vault_loader.py` parses one specific Obsidian vault's markdown
notes, which makes it useful only to someone who already has that vault.
This loader reads NIST's own machine-readable catalog instead, so the
800-53 data can be populated from scratch by anyone:

    policyforge etl-oscal

Source is the `usnistgov/oscal-content` repository — the authoritative
OSCAL release of SP 800-53 Rev 5 plus the Low/Moderate/High baseline
profiles. A US government work, so public domain, same basis as the eCFR
and CPRT sources used elsewhere in `ingest/`.

OSCAL shapes that need translating into this project's flatter schema:

* **Identifiers.** OSCAL ids are lowercase and dotted (`ac-2`, `ac-2.1`).
  The human-facing label is carried in a `props` entry, and each control
  has *three* of them: a zero-padded form ("AC-02"), an SP 800-53A form,
  and the plain form NIST prints in the publication ("AC-2"). Only the
  last has no `class` key, and that's the one the rest of this codebase
  uses — see `mapping/crosswalk.py`'s ID regex.
* **Statements.** Control text is a `parts` tree, not a string: a
  `statement` part containing labelled `item` parts ("a.", "b.", then
  nested "1.", "2."). These are flattened back into readable prose with
  their labels preserved, since that lettering is what an SSP's
  implementation narrative refers to.
* **Parameters.** Prose contains `{{ insert: param, ac-02_odp.01 }}`
  placeholders. Each resolves either to an assignment (a `label`) or to a
  selection (a `select` with `choice` values), and is rendered the way NIST
  prints them: "[Assignment: organization-defined ...]" /
  "[Selection (one or more): ...]". Leaving the raw placeholders in would
  put OSCAL internals into a compliance deliverable.
* **Withdrawn controls.** 182 enhancements are marked `status: withdrawn`
  and carry no statement text. They are excluded: they aren't part of Rev 5
  any more, they appear in no baseline, and listing them in an SSP would
  invite implementation narratives for controls that no longer exist. The
  count is reported by `parse_oscal_catalog` rather than silently dropped.
"""

from __future__ import annotations

import re

from .schema import Control, ControlEnhancement

CATALOG_URL = (
    "https://raw.githubusercontent.com/usnistgov/oscal-content/main"
    "/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json"
)
BASELINE_URLS = {
    "Low": (
        "https://raw.githubusercontent.com/usnistgov/oscal-content/main"
        "/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_LOW-baseline_profile.json"
    ),
    "Moderate": (
        "https://raw.githubusercontent.com/usnistgov/oscal-content/main"
        "/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_MODERATE-baseline_profile.json"
    ),
    "High": (
        "https://raw.githubusercontent.com/usnistgov/oscal-content/main"
        "/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_HIGH-baseline_profile.json"
    ),
}
# Baselines are cumulative, so ordering them least-to-most protective keeps
# the rendered value readable ("Low, Moderate, High" rather than set order).
BASELINE_ORDER = ("Low", "Moderate", "High")

_PARAM_INSERT_RE = re.compile(r"\{\{\s*insert:\s*param,\s*([^\s}]+)\s*\}\}")


def _plain_label(item: dict) -> str | None:
    """The unpadded, publication-style label ("AC-2", "AC-2(1)").

    OSCAL carries several labels per control, distinguished by `class`; the
    unclassed one is the form NIST prints and this codebase uses.
    """
    for prop in item.get("props", []):
        if prop.get("name") == "label" and "class" not in prop:
            return prop["value"]
    # Fall back to any label rather than losing the control entirely.
    for prop in item.get("props", []):
        if prop.get("name") == "label":
            return prop["value"]
    return None


def _is_withdrawn(item: dict) -> bool:
    return any(
        prop.get("name") == "status" and prop.get("value") == "withdrawn"
        for prop in item.get("props", [])
    )


def _param_text(param: dict, params: dict[str, dict], seen: frozenset[str] = frozenset()) -> str:
    """Render one parameter the way SP 800-53 prints it.

    Selections nest: several controls (AC-7 among them) have `choice` values
    that themselves contain `{{ insert: param, ... }}` references, so choices
    are resolved recursively. `seen` guards against a parameter cycle, which
    would otherwise recurse forever on malformed input.
    """
    param_id = param.get("id", "")
    if param_id in seen:
        return "[Assignment: organization-defined parameter]"
    seen = seen | {param_id}

    if "select" in param:
        select = param["select"]
        choices = "; ".join(
            _resolve_params(choice, params, seen).strip() for choice in select.get("choice", [])
        )
        qualifier = " (one or more)" if select.get("how-many") == "one-or-more" else ""
        return f"[Selection{qualifier}: {choices}]"
    label = param.get("label")
    if label:
        # Most labels are the bare noun phrase ("frequency", "personnel or
        # roles") and need the "organization-defined" lead-in that SP 800-53
        # prints. A minority (141 of 1467 in Rev 5.2.0) already include it,
        # and prepending unconditionally would render "[Assignment:
        # organization-defined organization-defined personnel or roles]".
        if label.lower().startswith("organization-defined"):
            return f"[Assignment: {label}]"
        return f"[Assignment: organization-defined {label}]"
    return "[Assignment: organization-defined parameter]"


def _resolve_params(prose: str, params: dict[str, dict], seen: frozenset[str] = frozenset()) -> str:
    def replace(match: re.Match) -> str:
        param = params.get(match.group(1))
        return _param_text(param, params, seen) if param else match.group(0)

    return _PARAM_INSERT_RE.sub(replace, prose)


def _render_parts(parts: list[dict], params: dict[str, dict], depth: int = 0) -> list[str]:
    """Flatten a `statement`/`guidance` parts tree into labelled lines."""
    lines: list[str] = []
    for part in parts:
        label = _plain_label(part)
        prose = _resolve_params(part.get("prose", ""), params).strip()
        if prose:
            indent = "  " * depth
            lines.append(f"{indent}{label} {prose}" if label else f"{indent}{prose}")
        if part.get("parts"):
            lines.extend(_render_parts(part["parts"], params, depth + 1))
    return lines


def _part_text(item: dict, name: str, params: dict[str, dict]) -> str:
    """Rendered text of the named top-level part (`statement`, `guidance`)."""
    for part in item.get("parts", []):
        if part.get("name") != name:
            continue
        if part.get("parts"):
            return "\n".join(_render_parts(part["parts"], params))
        return _resolve_params(part.get("prose", ""), params).strip()
    return ""


def _related_controls(item: dict) -> list[str]:
    """OSCAL links `rel="related"` point at fragment ids (`#ac-3`); convert
    them to the label form the rest of the pipeline uses."""
    related = []
    for link in item.get("links", []):
        if link.get("rel") == "related":
            oscal_id = link["href"].lstrip("#")
            label = oscal_id_to_label(oscal_id)
            if label not in related:
                related.append(label)
    return related


def oscal_id_to_label(oscal_id: str) -> str:
    """Convert an OSCAL id to a label: "ac-2" -> "AC-2", "ac-2.1" -> "AC-2(1)".

    Used for link targets, whose labels aren't available inline the way a
    control's own `props` are.
    """
    match = re.fullmatch(r"([a-z]{2})-(\d+)(?:\.(\d+))?", oscal_id)
    if match is None:
        return oscal_id.upper()
    family, number, enhancement = match.groups()
    label = f"{family.upper()}-{int(number)}"
    return f"{label}({int(enhancement)})" if enhancement else label


def parse_baseline_profile(profile_json: dict) -> set[str]:
    """The set of OSCAL control ids a baseline profile includes."""
    ids: set[str] = set()
    for import_ in profile_json["profile"].get("imports", []):
        for include in import_.get("include-controls", []):
            ids.update(include.get("with-ids", []))
    return ids


def _baseline_label(oscal_id: str, baselines: dict[str, set[str]]) -> str:
    names = [name for name in BASELINE_ORDER if oscal_id in baselines.get(name, ())]
    # Any baseline not covered by the standard three is appended as-is so a
    # custom profile passed in by a caller still shows up.
    names += [n for n in baselines if n not in BASELINE_ORDER and oscal_id in baselines[n]]
    return ", ".join(names)


def parse_oscal_catalog(
    catalog_json: dict, baselines: dict[str, set[str]] | None = None
) -> tuple[list[Control], int]:
    """Parse an OSCAL 800-53 catalog into Controls.

    Returns `(controls, withdrawn_count)` — the withdrawn tally is returned
    rather than logged so the caller can report it (see `cli.py`'s
    `etl-oscal`) instead of the exclusion being invisible.
    """
    catalog = catalog_json["catalog"]
    version = catalog["metadata"]["version"]
    baselines = baselines or {}

    controls: list[Control] = []
    withdrawn = 0

    for group in catalog.get("groups", []):
        family = group.get("title", "")
        family_abbr = group.get("id", "").upper()

        for raw_control in group.get("controls", []):
            if _is_withdrawn(raw_control):
                # Count the whole subtree, so the reported tally matches the
                # catalog's own withdrawn count rather than omitting the
                # enhancements that go with a withdrawn control.
                withdrawn += 1 + len(raw_control.get("controls", []))
                continue

            # Parameter scope is the control *and all of its enhancements*
            # together, not each item in isolation: SC-42(2)'s statement
            # references `sc-42.01_odp`, a parameter defined on its sibling
            # SC-42(1). Ids are namespaced by their owner, so pooling them
            # can't collide.
            params = {p["id"]: p for p in raw_control.get("params", [])}
            for raw_enhancement in raw_control.get("controls", []):
                params.update({p["id"]: p for p in raw_enhancement.get("params", [])})
            control_id = _plain_label(raw_control) or raw_control["id"].upper()

            enhancements: list[ControlEnhancement] = []
            for raw_enhancement in raw_control.get("controls", []):
                if _is_withdrawn(raw_enhancement):
                    withdrawn += 1
                    continue
                enhancements.append(
                    ControlEnhancement(
                        enhancement_id=_plain_label(raw_enhancement)
                        or raw_enhancement["id"].upper(),
                        title=raw_enhancement.get("title", ""),
                        baseline=_baseline_label(raw_enhancement["id"], baselines),
                        description=_part_text(raw_enhancement, "statement", params),
                    )
                )

            controls.append(
                Control(
                    control_id=control_id,
                    title=raw_control.get("title", ""),
                    framework="NIST 800-53",
                    framework_version=f"Rev 5 ({version})",
                    family=family,
                    family_abbr=family_abbr,
                    baseline=_baseline_label(raw_control["id"], baselines),
                    control_statement=_part_text(raw_control, "statement", params),
                    discussion=_part_text(raw_control, "guidance", params),
                    enhancements=enhancements,
                    related_controls=_related_controls(raw_control),
                    source_path=CATALOG_URL,
                )
            )

    return controls, withdrawn


def fetch_oscal_catalog(*, url: str = CATALOG_URL) -> dict:
    """Fetch NIST's OSCAL 800-53 catalog.

    Kept separate from `parse_oscal_catalog` — network access lives only in
    the `fetch_*` functions here — so the parser stays pure and testable
    offline against a fixture.
    """
    import requests

    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.json()


def fetch_oscal_baselines(*, urls: dict[str, str] | None = None) -> dict[str, set[str]]:
    """Fetch the Low/Moderate/High baseline profiles as id sets."""
    import requests

    baselines = {}
    for name, url in (urls or BASELINE_URLS).items():
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        baselines[name] = parse_baseline_profile(response.json())
    return baselines
