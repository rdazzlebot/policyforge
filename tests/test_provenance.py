"""Provenance stamps on bundled framework catalogs.

The catalogs are fetched from moving upstreams and committed. Nothing
recorded which revision produced them, so an upstream revision and an
upstream compromise looked identical in a diff — both are just changed
requirement text.
"""

from __future__ import annotations

import yaml

from policyforge.ingest.oscal_loader import BASELINE_URLS, CATALOG_URL, OSCAL_REF
from policyforge.ingest.provenance import (
    content_digest,
    read_provenance,
    record_source_provenance,
    verify_content,
)

EXISTING = """\
id: nist-800-53-r5
name: NIST SP 800-53 Rev 5
licence: public-domain
source: NIST OSCAL content repository, via policyforge etl-oscal
notes: >-
  A US government work, so freely redistributable.
"""


def test_the_oscal_fetch_is_pinned_to_a_named_revision():
    """`main` cannot be traced to anything a reviewer can look up."""
    assert OSCAL_REF != "main"
    assert OSCAL_REF.startswith("v")
    assert f"/{OSCAL_REF}/" in CATALOG_URL
    for url in BASELINE_URLS.values():
        assert f"/{OSCAL_REF}/" in url
        assert "/main/" not in url


def test_stamping_preserves_what_a_person_wrote(tmp_path):
    """The licence and the redistribution note are not the ETL's to restate."""
    path = tmp_path / "framework.yaml"
    path.write_text(EXISTING, encoding="utf-8")

    record_source_provenance(
        path, source_ref="v1.5.0", source_url=CATALOG_URL, content=b"catalog bytes"
    )

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["licence"] == "public-domain"
    assert data["name"] == "NIST SP 800-53 Rev 5"
    assert data["notes"].startswith("A US government work")
    assert data["source_ref"] == "v1.5.0"
    assert data["content_sha256"] == content_digest(b"catalog bytes")


def test_stamping_is_idempotent_apart_from_the_date(tmp_path):
    path = tmp_path / "framework.yaml"
    path.write_text(EXISTING, encoding="utf-8")

    first = record_source_provenance(
        path, source_ref="v1.5.0", source_url=CATALOG_URL, content=b"same"
    )
    second = record_source_provenance(
        path, source_ref="v1.5.0", source_url=CATALOG_URL, content=b"same"
    )
    assert first == second


def test_a_missing_framework_file_is_not_invented(tmp_path):
    """An ETL run pointed at a scratch directory should leave no orphan."""
    path = tmp_path / "nothing-here" / "framework.yaml"
    assert (
        record_source_provenance(path, source_ref="v1.5.0", source_url=CATALOG_URL, content=b"x")
        is None
    )
    assert not path.exists()


def test_reading_an_unstamped_framework_is_not_an_error(tmp_path):
    """Catalogs bundled before this existed have no stamp, and that is data."""
    path = tmp_path / "framework.yaml"
    path.write_text(EXISTING, encoding="utf-8")
    assert read_provenance(path) == {}


def test_verify_catches_a_catalog_that_no_longer_matches(tmp_path):
    (tmp_path / "framework.yaml").write_text(EXISTING, encoding="utf-8")
    (tmp_path / "controls.json").write_text('[{"id": "AC-2"}]', encoding="utf-8")
    record_source_provenance(
        tmp_path / "framework.yaml",
        source_ref="v1.5.0",
        source_url=CATALOG_URL,
        content=(tmp_path / "controls.json").read_bytes(),
    )
    assert verify_content(tmp_path) is None

    (tmp_path / "controls.json").write_text(
        '[{"id": "AC-2"}, {"id": "SNUCK-IN"}]', encoding="utf-8"
    )
    problem = verify_content(tmp_path)
    assert problem is not None
    assert "does not match the recorded hash" in problem


def test_verify_is_silent_on_an_unstamped_framework(tmp_path):
    """Nothing recorded means nothing to contradict, not a failure."""
    (tmp_path / "framework.yaml").write_text(EXISTING, encoding="utf-8")
    (tmp_path / "controls.json").write_text("[]", encoding="utf-8")
    assert verify_content(tmp_path) is None


def test_verify_reports_a_recorded_catalog_that_went_missing(tmp_path):
    (tmp_path / "framework.yaml").write_text(EXISTING, encoding="utf-8")
    (tmp_path / "controls.json").write_text("[]", encoding="utf-8")
    record_source_provenance(
        tmp_path / "framework.yaml",
        source_ref="v1.5.0",
        source_url=CATALOG_URL,
        content=b"[]",
    )
    (tmp_path / "controls.json").unlink()
    assert "missing" in (verify_content(tmp_path) or "")
