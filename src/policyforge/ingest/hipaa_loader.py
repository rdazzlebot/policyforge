"""Parse the HIPAA Security Rule (45 CFR Part 164, Subpart C) into this
project's common Control/Element schema.

Unlike HITRUST/GovRAMP, the HIPAA Security Rule is a US federal regulation
— public domain, same basis as NIST 800-53/FedRAMP/ARC-AMPE — so it's safe
to bundle directly rather than treat as BYOC. Source of truth is the
Electronic Code of Federal Regulations (eCFR)'s versioner API
(https://www.ecfr.gov/developers/documentation/api/v1), not a hand-copied
transcription, so `data/frameworks/hipaa-security-rule/controls.json` can
always be regenerated and diffed against the actual current regulation
text via `policyforge etl-hipaa`.

Parsing approach: within each `<DIV8 TYPE="SECTION">` (one CFR section,
e.g. § 164.308), every `<P>` starts with zero or more leading citation
tokens like `(a)`, `(1)`, `(i)`, `(A)` establishing its position in the
paragraph hierarchy — but a lone token's *meaning* (new top-level letter
vs. next roman numeral vs. next capital letter) is ambiguous from the
token alone (e.g. is `(i)` a roman numeral continuing an existing numbered
standard, or — hypothetically — a fifth top-level letter?). This is
resolved with a small state machine (`_CitationTracker`) using two facts
that hold throughout this specific Subpart: digits and uppercase letters
are unambiguous types, and a lowercase token is only ever a roman numeral
once a digit has already been seen at the current nesting point — otherwise
it's a new top-level letter. Verified against every section in Subpart C
(164.302-164.318); see tests/test_hipaa_loader.py.

Rather than assume Required/Addressable implementation specifications
always sit at a fixed citation depth (they don't — § 164.308 tags them at
the `(A)`/capital-letter level, § 164.310 tags them at the `(i)`/roman
level), each named `<I>...</I>` paragraph is classified by content: one
containing "(Required)" or "(Addressable)" becomes a `ControlEnhancement`
on the most recently opened `Control`; any other named paragraph (a
"Standard: ..." heading, or an unlabeled-but-titled requirement like
"Business associate contracts and other arrangements") opens a new
`Control`. Paragraphs with no italicized lead-in (pure connective prose,
or a bare "Implementation specifications:" label) update the citation
path but produce neither.
"""

from __future__ import annotations

import re

from .schema import Control, ControlEnhancement

_SECTION_RE = re.compile(
    r'<DIV8 N="(?P<id>164\.\d+)" TYPE="SECTION"[^>]*>'
    r"\s*<HEAD>(?P<head>.*?)</HEAD>(?P<body>.*?)</DIV8>",
    re.DOTALL,
)
_PARA_RE = re.compile(r"<P>(?P<content>.*?)</P>", re.DOTALL)
# Some paragraphs introduce a second, nested citation mid-text after an
# em-dash rather than at the start of a new <P> (e.g. "(2) <I>Implementation
# specifications (Required)</I>&#x2014;(i) <I>Business associate
# contracts.</I> ..."). Splitting on this decomposes one such paragraph into
# multiple virtual paragraphs so the rest of the logic below doesn't need to
# know about the distinction.
_COMPOUND_SPLIT_RE = re.compile(r"&#x2014;(?=\([a-zA-Z0-9]+\))")
_LEADING_TOKENS_RE = re.compile(r"^((?:\([a-zA-Z0-9]+\))+)\s*")
_TOKEN_RE = re.compile(r"\(([a-zA-Z0-9]+)\)")
_ITALIC_RE = re.compile(r"<I>(?P<italic>.*?)</I>\s*(?P<rest>.*)", re.DOTALL)
_REQUIRED_ADDRESSABLE_RE = re.compile(r"\((Required|Addressable)\)")
# Ambiguous single-letter tokens (e.g. "c", "d") could be roman numerals
# (C=100, D=500) or the next top-level paragraph letter. Restricting the
# "treat as roman" branch to plausible small list positions — rather than
# any string built from roman-numeral characters — resolves the ambiguity
# correctly in practice: a real roman-numeral list here only ever counts
# 1-10, while top-level letters routinely reach 'c'/'d'/'l'/'m'.
_PLAUSIBLE_ROMAN_RE = re.compile(r"^(i|ii|iii|iv|v|vi|vii|viii|ix|x)$")


def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&#xA7;", "§").replace("&#x2014;", "—")
    text = text.replace("&#x201C;", "“").replace("&#x201D;", "”")
    text = text.replace("&amp;", "&").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()


class _CitationTracker:
    """Tracks the current full citation path (e.g. ['a', '1', 'ii']) across
    a section's paragraphs. See module docstring for the disambiguation
    rule this depends on."""

    def __init__(self, section_id: str):
        self.section_id = section_id
        self._path: list[str] = []

    def _token_depth(self, token: str) -> int:
        """Where a single leading token belongs in the path, given the
        path built up so far *within this same leading-token group*."""
        if token.isdigit():
            return 2
        if token.isupper():
            return 4
        # Ambiguous lowercase: a roman numeral continuing an existing
        # numbered standard, or a new top-level letter.
        if self._path and len(self._path) >= 2 and _PLAUSIBLE_ROMAN_RE.match(token):
            return 3
        return 1

    def advance(self, leading_tokens: str) -> str:
        """Update the path from a paragraph's leading `(x)(y)...` group
        (may be empty) and return the resulting full citation string."""
        for token in _TOKEN_RE.findall(leading_tokens):
            depth = self._token_depth(token)
            self._path = self._path[: depth - 1] + [token]
        return self.section_id + "".join(f"({t})" for t in self._path)


def _parse_section(section_id: str, head: str, body: str) -> list[Control]:
    # Head is "§ 164.NNN Title." — three whitespace-separated tokens
    # (section mark, number, title), so split at most twice.
    title = _strip_tags(head).split(None, 2)[-1].rstrip(".")
    if title.lower() == "definitions":
        return []  # defined terms aren't requirements

    tracker = _CitationTracker(section_id)
    controls: list[Control] = []
    current: Control | None = None
    # The most recently opened item — either `current` itself or its most
    # recent enhancement, whichever is more specific. Un-italicized
    # continuation paragraphs (e.g. a bare "(A) Comply with ...;" list item
    # under an already-open requirement) get appended to whichever this is,
    # rather than silently dropped, since real requirement text lives there
    # too — CFR sections don't italicize every list item, only the first
    # one that introduces the list.
    current_enh: ControlEnhancement | None = None

    for match in _PARA_RE.finditer(body):
        for raw in _COMPOUND_SPLIT_RE.split(match.group("content")):
            leading_match = _LEADING_TOKENS_RE.match(raw)
            leading = leading_match.group(1) if leading_match else ""
            remainder = raw[leading_match.end() :] if leading_match else raw
            citation = tracker.advance(leading)

            italic_match = _ITALIC_RE.match(remainder.strip())
            if not italic_match:
                text = _strip_tags(remainder)
                target = current_enh or current
                if text and target is not None:
                    field = (
                        "description"
                        if isinstance(target, ControlEnhancement)
                        else "control_statement"
                    )
                    setattr(target, field, f"{getattr(target, field)} {text}".strip())
                continue  # otherwise: framing prose before any item has opened
            italic_text = _strip_tags(italic_match.group("italic"))
            rest_text = _strip_tags(italic_match.group("rest"))

            if italic_text.rstrip(":") in (
                "Implementation specifications",
                "Implementation specification",
            ):
                continue  # bare section-header label, not itself a requirement

            req_match = _REQUIRED_ADDRESSABLE_RE.search(italic_text)
            if req_match:
                spec_title = italic_text[: req_match.start()].strip(" :.")
                if current is None:
                    continue  # malformed input — spec with no preceding standard
                current_enh = ControlEnhancement(
                    enhancement_id=citation,
                    title=spec_title,
                    baseline=req_match.group(1),
                    description=rest_text,
                )
                current.enhancements.append(current_enh)
                continue

            # New named item: a "Standard: ..." heading, or an unlabeled-but-
            # titled requirement (e.g. "Business associate contracts...").
            item_title = italic_text.strip(" :.")
            if item_title.lower().startswith("standard:"):
                item_title = item_title[len("standard:") :].strip()
            current = Control(
                control_id=citation,
                title=item_title,
                framework="HIPAA Security Rule",
                framework_version="45 CFR 164 Subpart C",
                control_statement=rest_text,
                source_path=f"https://www.ecfr.gov/current/title-45/section-{section_id}",
            )
            current_enh = None
            controls.append(current)

    return controls


def fetch_ecfr_subpart_c_xml(*, date: str | None = None) -> str:
    """Fetch the current (or a specific effective date's) full XML text of
    45 CFR Part 164 from eCFR's public versioner API. Kept separate from
    `parse_hipaa_security_rule` — the only network-touching function in
    this module — so the parser itself stays pure and testable offline
    against a fixed fixture (see tests/test_hipaa_loader.py).
    """
    import requests

    if date is None:
        titles_response = requests.get(
            "https://www.ecfr.gov/api/versioner/v1/titles.json", timeout=30
        )
        titles_response.raise_for_status()
        title_45 = next(t for t in titles_response.json()["titles"] if t["number"] == 45)
        date = title_45["up_to_date_as_of"]

    response = requests.get(
        f"https://www.ecfr.gov/api/versioner/v1/full/{date}/title-45.xml",
        params={"part": "164"},
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def parse_hipaa_security_rule(xml_text: str) -> list[Control]:
    """Parse eCFR's XML for 45 CFR Part 164 (or just its Subpart C excerpt)
    into a flat list of Controls, one per "Standard" (or per unlabeled-but-
    titled requirement), each carrying its Required/Addressable
    implementation specifications as ControlEnhancements.

    Only Subpart C (Security Standards) sections are parsed; anything from
    Subpart A/B/D/E present in a full-Part-164 fetch is ignored — this
    project targets the Security Rule specifically, not HIPAA Privacy or
    Breach Notification.
    """
    subpart_start = xml_text.find('<DIV6 N="C" TYPE="SUBPART"')
    if subpart_start == -1:
        raise ValueError("Subpart C not found in the given XML — check the eCFR fetch.")
    subpart_end = xml_text.find("<DIV6", subpart_start + 10)
    subpart_text = xml_text[subpart_start : subpart_end if subpart_end != -1 else None]

    controls: list[Control] = []
    for match in _SECTION_RE.finditer(subpart_text):
        controls.extend(_parse_section(match.group("id"), match.group("head"), match.group("body")))
    return controls
