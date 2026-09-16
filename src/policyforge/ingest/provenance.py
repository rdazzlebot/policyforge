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


def verify_content(framework_dir: Path, *, controls_name: str = "controls.json") -> str | None:
    """Check the committed catalog still hashes to what was recorded.

    Returns None when it matches or when there is nothing to check, and a
    description of the mismatch otherwise. This is the question provenance
    exists to answer — "is the file I am holding the one that was fetched" —
    and it is answerable offline, which the drift job is not.
    """
    recorded = read_provenance(framework_dir / "framework.yaml")
    expected = recorded.get("content_sha256")
    if not expected:
        return None

    controls = framework_dir / controls_name
    if not controls.exists():
        return f"{framework_dir.name}: {controls_name} is recorded but missing"

    actual = content_digest(controls.read_bytes())
    if actual != expected:
        return (
            f"{framework_dir.name}: {controls_name} does not match the recorded hash — "
            f"expected {expected[:16]}…, found {actual[:16]}…. Either it was edited by "
            f"hand, or it was re-fetched without updating the provenance stamp."
        )
    return None
