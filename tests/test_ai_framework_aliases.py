"""Keys for the two AI catalogs, pinned before either catalog exists.

**The cheap moment is now.** `NIST AI RMF` would take the bare `nist`
key — the orphan the NIST-family split existed to remove — and
`HITRUST AI Security Certification` collides outright with `HITRUST CSF`.
That second one is not hypothetical: HITRUST's AI certification is an
add-on to a CSF assessment and cannot be held standalone, so a user who
brings one almost certainly has both, and their requirement ids would
share a bucket.

Both names are already citable — capital-initial, so neither repeats the
digit-initial trap that made two CFR catalogs impossible to cite. What
was missing was the key.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from policyforge.content.tags import source_tags
from policyforge.mapping.crosswalk import normalize_framework

CATALOGS = Path(__file__).resolve().parent.parent / "data" / "frameworks"


@pytest.mark.parametrize(
    "written",
    ["NIST AI RMF", "NIST AI Risk Management Framework", "AI RMF"],
)
def test_every_spelling_of_ai_rmf_keys_to_one_catalog(written: str):
    """NIST writes the name both ways and neither spelling contains the
    other, so one needle cannot cover both."""
    assert normalize_framework(written) == "nist-ai-rmf"


@pytest.mark.parametrize("written", ["HITRUST AI Security Certification", "HITRUST AI"])
def test_hitrust_ai_does_not_share_a_key_with_the_csf(written: str):
    """The collision that is real rather than anticipated."""
    assert normalize_framework(written) == "hitrust-ai"
    assert normalize_framework(written) != normalize_framework("HITRUST CSF")


def test_both_names_are_citable_so_the_cfr_trap_is_not_repeated():
    """A framework name beginning with a digit is not a source tag, which
    is what made `45 CFR 171` and `42 CFR Part 2` impossible to cite.
    Neither AI name has that shape, and this says so before anyone writes
    a catalog that assumes it."""
    for tag in ("[NIST AI RMF GOVERN-1.1]", "[HITRUST AI 01.a]"):
        assert source_tags(tag) == [tag], f"{tag} is not a legal source tag"


@pytest.mark.parametrize(
    "identifier",
    ["hitrust-csf", "hitrust-ai", "nist-ai-rmf", "nist-800-53", "cfr-171-information-blocking"],
)
def test_a_needle_does_not_swallow_a_catalog_identifier(identifier: str):
    """A `hitrust` needle was removed once for exactly this: it matched
    inside the id `hitrust-csf` and returned `hitrust`. These needles
    carry a space, so they cannot match a hyphenated id."""
    assert normalize_framework(identifier) == identifier


#: Catalogs that ship README-only, for a user to bring their own controls.
#: They carry no `controls.json` and no `framework.yaml`, so there is no
#: declared name in this tree to key — the guard below cannot reach them,
#: and says so rather than counting them as covered.
BYOC_ONLY = {"govramp", "hitrust-csf"}


def test_no_bundled_catalog_changed_key():
    """The regression guard, derived from the tree rather than listed, so
    a catalog added later is covered without anyone remembering this.

    **Covered: catalogs with a `controls.json`.** Not covered: the
    README-only ones in `BYOC_ONLY`, which have no declared name in this
    tree to check. 80 found that gap — `hitrust-ai` will land as BYOC,
    so the collision this module exists to prevent is outside this
    test's reach at exactly the moment it matters.

    The second assertion is the answer to that: **the skipped set is
    pinned, so a new README-only catalog turns this red** and somebody
    decides whether it needs covering, rather than being skipped in
    silence. A guard that states its own reach can be wrong out loud.
    """
    expected = {
        "arc-ampe": "arc-ampe",
        "cfr-170-315-onc-certification": "cfr-170-315-onc-certification",
        "cfr-171-information-blocking": "cfr-171-information-blocking",
        "cfr-42-part-2-sud-records": "cfr-42-part-2-sud-records",
        "fedramp": "fedramp",
        "hipaa-security-rule": "hipaa",
        "nist-800-171-r3": "nist-800-171",
        "nist-800-53-r5": "nist-800-53",
    }
    seen = {}
    skipped = set()
    for directory in sorted(CATALOGS.iterdir()):
        controls = directory / "controls.json"
        if not controls.exists():
            skipped.add(directory.name)
            continue
        declared = json.loads(controls.read_text(encoding="utf-8"))[0]["framework"]
        seen[directory.name] = normalize_framework(declared)

    assert skipped == BYOC_ONLY, (
        f"the catalogs this guard cannot see have changed: {sorted(skipped)}. "
        f"A README-only catalog has no declared name here to key, so it is "
        f"skipped — which is fine for `govramp` and `hitrust-csf` and is NOT "
        f"fine silently. If `hitrust-ai` is in that list, the HITRUST collision "
        f"this module exists to prevent is untested; add it to BYOC_ONLY only "
        f"after deciding how its key is covered instead."
    )

    assert seen == expected, (
        "a bundled catalog's key moved. The AI needles carry a space and should "
        "not reach any of these; if one did, a citation could cross between "
        "catalogs silently."
    )
    assert len(set(seen.values())) == len(seen), "two bundled catalogs now share a key"
