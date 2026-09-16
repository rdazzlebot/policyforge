"""Where a bundled framework catalog came from, recorded beside it.

The catalogs in `data/frameworks/` are fetched from upstreams that move. The
OSCAL catalog was read from `main`; eCFR and CPRT are read live. Nothing
recorded which revision produced the committed `controls.json`, so a
reviewer looking at that file could not tell an upstream revision from an
upstream compromise — and the two are indistinguishable in a diff, because
both are just changed requirement text.

The monthly drift job is a genuine compensating control: any upstream change
turns the build red. What it cannot do is say *what* the file is supposed to
be. A red build tells you something moved; provenance tells you whether what
you are holding now is what NIST published.

Three fields, written into the framework's own `framework.yaml`:

* `source_ref` — the upstream revision, a release tag where one exists.
  A tag rather than a bare commit because the tag is what the publisher
  announces and what a reviewer can look up.
* `source_url` — the exact URL fetched, so the claim is checkable without
  reading this code.
* `content_sha256` — the hash of the parsed output as committed. This is the
  field that makes the other two mean anything: a ref with no hash says
  where you meant to look, not what you got.

Deliberately additive. The file is read and rewritten with these keys set
and everything else preserved, because `framework.yaml` carries a licence
and a redistribution note that a person wrote and an ETL run must not
quietly restate.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

#: Keys this module owns. Anything else in the file belongs to whoever wrote
#: it and is preserved untouched.
PROVENANCE_KEYS = ("source_ref", "source_url", "content_sha256", "fetched_at")


def content_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def record_source_provenance(
    framework_yaml: Path,
    *,
    source_ref: str,
    source_url: str,
    content: bytes,
) -> str | None:
    """Stamp provenance into `framework_yaml`. Returns the digest recorded.

    Returns None and writes nothing when there is no `framework.yaml` to
    stamp — an ETL run pointed at a scratch directory is a normal thing to
    do, and inventing a metadata file there would leave an orphan nobody
    asked for.
    """
    if not framework_yaml.exists():
        return None

    import yaml

    data = yaml.safe_load(framework_yaml.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return None

    digest = content_digest(content)
    data["source_ref"] = source_ref
    data["source_url"] = source_url
    data["content_sha256"] = digest
    data["fetched_at"] = datetime.now(UTC).strftime("%Y-%m-%d")

    framework_yaml.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=88),
        encoding="utf-8",
    )
    return digest


def read_provenance(framework_yaml: Path) -> dict:
    """The recorded provenance, or {} where none has been stamped yet.

    Absence is a normal answer, not an error: the catalogs bundled before
    this existed have none, and a reader should be able to say "this one is
    unstamped" rather than crash.
    """
    if not framework_yaml.exists():
        return {}

    import yaml

    data = yaml.safe_load(framework_yaml.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return {key: data[key] for key in PROVENANCE_KEYS if key in data}


#: The four things a catalog can be, kept apart on purpose.
#:
#: An earlier version of this returned None for both VERIFIED and UNSTAMPED,
#: which is the same conflation `zardoz/shadow.py` exists to avoid and the
#: same one `LLMResponse.cached_input_tokens` distinguishes zero from None
#: for: a check that did not run reads exactly like a check that passed.
#: It matters here more than most places, because today *every* bundled
#: catalog is UNSTAMPED — the stamps are written by the etl-* commands, and
#: the committed catalogs predate them — so a caller treating "nothing to
#: check" as "checked" would report the whole bundled set as verified while
#: verifying nothing at all.
VERIFIED = "verified"
UNSTAMPED = "unstamped"
MISMATCH = "mismatch"
MISSING = "missing"


@dataclass(frozen=True)
class ProvenanceStatus:
    """What is known about one catalog's integrity, and how sure."""

    state: str
    framework: str
    message: str = ""

    @property
    def ok(self) -> bool:
        """True only when a hash was recorded and the file matches it.

        Deliberately False for UNSTAMPED. "We have no way to tell" is not a
        pass, and a caller writing `if status.ok` should not quietly inherit
        an unverifiable catalog.
        """
        return self.state == VERIFIED

    @property
    def checkable(self) -> bool:
        """Whether there was anything to check at all."""
        return self.state != UNSTAMPED

    def __str__(self) -> str:
        return self.message or f"{self.framework}: {self.state}"


def verify_content(
    framework_dir: Path, *, controls_name: str = "controls.json"
) -> ProvenanceStatus:
    """Whether the committed catalog is the one that was fetched.

    This is the question provenance exists to answer, and it is answerable
    offline — which the monthly drift job is not, since that compares
    against a live upstream and tells you something moved rather than
    whether what you hold is what was published.

    UNSTAMPED is the honest answer for every catalog bundled before the
    stamps existed. It is not an error and must not be treated as one: an
    unstamped catalog should stay usable. It is also not a pass.
    """
    name = framework_dir.name
    recorded = read_provenance(framework_dir / "framework.yaml")
    expected = recorded.get("content_sha256")
    if not expected:
        return ProvenanceStatus(
            state=UNSTAMPED,
            framework=name,
            message=(
                f"{name}: no provenance recorded, so integrity cannot be checked. "
                f"Re-run the framework's etl-* command to stamp it."
            ),
        )

    controls = framework_dir / controls_name
    if not controls.exists():
        return ProvenanceStatus(
            state=MISSING,
            framework=name,
            message=f"{name}: {controls_name} is recorded but missing",
        )

    actual = content_digest(controls.read_bytes())
    if actual != expected:
        return ProvenanceStatus(
            state=MISMATCH,
            framework=name,
            message=(
                f"{name}: {controls_name} does not match the recorded hash — "
                f"expected {expected[:16]}…, found {actual[:16]}…. Either it was edited "
                f"by hand, or it was re-fetched without updating the provenance stamp."
            ),
        )
    ref = recorded.get("source_ref", "?")
    return ProvenanceStatus(
        state=VERIFIED,
        framework=name,
        message=f"{name}: matches the recorded hash ({expected[:16]}…, {ref})",
    )


def verify_all(frameworks_dir: Path) -> list[ProvenanceStatus]:
    """Every framework directory's status, so a caller can see the shape.

    Returns one row per framework rather than a single verdict, because the
    interesting fact today is the proportion: a set where most catalogs are
    UNSTAMPED is a different security posture from one where they are all
    VERIFIED, and a boolean would hide that entirely.
    """
    if not frameworks_dir.exists():
        return []
    return [
        verify_content(child)
        for child in sorted(frameworks_dir.iterdir())
        if child.is_dir() and (child / "framework.yaml").exists()
    ]
