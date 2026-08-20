"""One input adapter: parse NIST 800-53 control notes out of a markdown
source using the specific frontmatter + heading shape this project started
from (an Obsidian vault) into the common Control schema.

This is one adapter among possible others, not a dependency — nothing about
this format is Obsidian-specific at runtime; it's just markdown with YAML
frontmatter and `[[wikilink]]`-style cross-references, which Obsidian
happens to be a convenient tool for authoring. Point this loader at any
directory of markdown files in the same shape (e.g. exported from a
different editor entirely) and it works identically. A different source
format (spreadsheet, OSCAL JSON, plain YAML) would get its own loader in
this package, implementing the same `list[Control]` output contract.

NIST 800-53 control text is a US federal government work — public domain —
so this loader is safe to point at bundled, redistributable output. It is
NOT safe to point at a vault's HITRUST or GovRAMP control notes and bundle
the result; see README's licensing table. That's why `parse_control_file`
strips non-public-domain crosswalk columns by default (see
`keep_crosswalk_columns`).
"""

from __future__ import annotations

import re
from pathlib import Path

import frontmatter

from .schema import Control, ControlEnhancement

# Columns in the "Cross-Framework Mappings" table that are safe to retain in
# bundled/public output by default. FedRAMP mappings for NIST 800-53 are
# themselves published as part of a federal program (public domain).
# HITRUST / GovRAMP / ISO / PCI-DSS columns are NOT included by default —
# even ID-level correspondence drawn from a licensed crosswalk table is a
# grey area worth avoiding until confirmed. Override with
# `keep_crosswalk_columns` if you've verified it's safe for your use case.
_DEFAULT_SAFE_CROSSWALK_COLUMNS = {"fedramp"}

_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_ENHANCEMENT_ROW_RE = re.compile(
    r"^\|\s*\*{0,2}(?P<id>[A-Z]{2}-\d+\(\d+\))\*{0,2}\s*\|\s*"
    r"(?P<title>[^|]*)\|\s*(?P<baseline>[^|]*)\|\s*(?P<desc>[^|]*)\|\s*$",
    re.MULTILINE,
)
_CROSSWALK_ROW_RE = re.compile(
    r"^\|\s*(?P<framework>[^|]+?)\s*\|\s*(?P<equiv>[^|]+?)\s*\|\s*$",
    re.MULTILINE,
)
_RELATED_ID_RE = re.compile(r"\[\[([A-Z]{2}-\d+)\]\]")


def _sections(body: str) -> dict[str, str]:
    """Split the markdown body into {heading: content} on '## ' headings."""
    matches = list(_SECTION_RE.finditer(body))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        heading = m.group(1).strip().lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        # Each section in this vault format is followed by a "---" horizontal
        # rule before the next heading; strip it so it doesn't leak into the
        # captured text.
        content = re.sub(r"\n?-{3,}\s*$", "", content).strip()
        sections[heading] = content
    return sections


def _parse_enhancements(text: str) -> list[ControlEnhancement]:
    out = []
    for m in _ENHANCEMENT_ROW_RE.finditer(text):
        eid = m.group("id").strip()
        title = m.group("title").strip()
        if not title or title.lower() == "title":
            continue  # header row
        out.append(
            ControlEnhancement(
                enhancement_id=eid,
                title=title,
                baseline=m.group("baseline").strip(),
                description=m.group("desc").strip(),
            )
        )
    return out


def _parse_crosswalk(text: str, keep_columns: set[str]) -> dict[str, str]:
    out = {}
    for m in _CROSSWALK_ROW_RE.finditer(text):
        framework = m.group("framework").strip()
        equiv = m.group("equiv").strip()
        key = framework.lower()
        if key in ("framework", "---", "") or set(framework) <= {"-"}:
            continue
        # normalize keys like "HITRUST CSF" -> "hitrust", "FedRAMP" -> "fedramp"
        norm = key.split()[0]
        if norm in keep_columns and equiv:
            out[norm] = equiv
    return out


def parse_control_file(
    path: Path,
    *,
    keep_crosswalk_columns: set[str] = _DEFAULT_SAFE_CROSSWALK_COLUMNS,
) -> Control:
    post = frontmatter.load(path)
    fm = post.metadata
    body = post.content
    sections = _sections(body)

    related = []
    if "related controls" in sections:
        related = _RELATED_ID_RE.findall(sections["related controls"])

    enhancements = []
    if "control enhancements" in sections:
        enhancements = _parse_enhancements(sections["control enhancements"])

    crosswalk = {}
    if "cross-framework mappings" in sections:
        crosswalk = _parse_crosswalk(
            sections["cross-framework mappings"], keep_crosswalk_columns
        )

    control_statement = sections.get("control statement", "").strip("> \n")
    discussion = sections.get("discussion", "")

    return Control(
        control_id=fm.get("control_id", path.stem),
        title=fm.get("title", ""),
        framework=fm.get("framework", "NIST 800-53"),
        framework_version=fm.get("version", "Rev 5"),
        family=fm.get("family"),
        family_abbr=fm.get("family_abbr"),
        baseline=fm.get("baseline"),
        control_statement=control_statement,
        discussion=discussion,
        enhancements=enhancements,
        related_controls=related,
        source_crosswalk=crosswalk,
        source_path=str(path),
    )


def load_vault_controls(
    controls_dir: Path,
    *,
    keep_crosswalk_columns: set[str] = _DEFAULT_SAFE_CROSSWALK_COLUMNS,
) -> list[Control]:
    """Parse every *.md control note in a directory (non-recursive)."""
    controls = []
    for path in sorted(controls_dir.glob("*.md")):
        try:
            controls.append(
                parse_control_file(path, keep_crosswalk_columns=keep_crosswalk_columns)
            )
        except Exception as exc:  # noqa: BLE001 — collect and report, don't abort the batch
            print(f"WARN: failed to parse {path}: {exc}")
    return controls
