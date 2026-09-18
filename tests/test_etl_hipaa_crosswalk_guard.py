"""`etl-hipaa` must not silently destroy the crosswalk it does not produce.

The pipeline is two commands. `etl-hipaa` parses 45 CFR 164 Subpart C, which
carries no mapping to NIST; `etl-hipaa-crosswalk` attaches those afterwards
from the CPRT fixture. So running the first alone — the obvious thing to do
when you want a fresh provenance stamp — rewrote the catalog without them:
**65 mappings to 0**, on a file that still loaded, still held 34 controls
with correct ids, and reported nothing wrong.

It refuses rather than warning, on policyforge-1d's ruling: a warning printed
by one command in a two-command pipeline is a line nobody reads, and the loss
it describes is invisible in the result.

The tests here hold three things, and the third is the one a presence check
would miss:

* the refusal fires, exits non-zero, and leaves the file untouched
* the normal path — a catalog with no mappings yet, or a write that keeps
  them — is unaffected
* a **partial** loss is refused too. 65 to 60 is five mappings destroyed and
  passes any "are there mappings?" test.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from policyforge.cli import cli

#: A catalog shaped like the bundled one: mappings on controls *and* on
#: enhancements. Most of the real ones are on enhancements — 40 of the 65 —
#: so a fixture with only top-level mappings would pass a guard that counted
#: only the top level, which is the mistake this counts against.
WITH_MAPPINGS = [
    {
        "control_id": "164.308(a)(1)(i)",
        "title": "Security management process",
        "source_crosswalk": {"nist-800-53": "RA-1"},
        "enhancements": [
            {"enhancement_id": "164.308(a)(1)(ii)(A)", "source_crosswalk": {"nist-800-53": "RA-3"}},
            {"enhancement_id": "164.308(a)(1)(ii)(B)", "source_crosswalk": {"nist-800-53": "RA-7"}},
        ],
    },
    {
        "control_id": "164.312(a)(1)",
        "title": "Access control",
        "source_crosswalk": {"nist-800-53": "AC-3"},
        "enhancements": [],
    },
]

WITHOUT_MAPPINGS = [
    {
        "control_id": "164.308(a)(1)(i)",
        "title": "Security management process",
        "source_crosswalk": {},
        "enhancements": [
            {"enhancement_id": "164.308(a)(1)(ii)(A)", "source_crosswalk": {}},
            {"enhancement_id": "164.308(a)(1)(ii)(B)", "source_crosswalk": {}},
        ],
    },
    {
        "control_id": "164.312(a)(1)",
        "title": "Access control",
        "source_crosswalk": {},
        "enhancements": [],
    },
]


def _counted(catalog):
    from policyforge.cli.etl import _crosswalk_mappings

    return _crosswalk_mappings(catalog)


def test_the_count_includes_enhancements_not_only_controls():
    """40 of the bundled catalog's 65 mappings hang off enhancements. A guard
    that counted only the top level would call losing all 40 no change."""
    assert _counted(WITH_MAPPINGS) == 4
    assert _counted(WITHOUT_MAPPINGS) == 0


def test_the_count_does_not_depend_on_which_framework_is_mapped():
    """`nist` became `nist-800-53` in `fix/nist-family-catalog-key`. A guard
    keyed to the name would have stopped counting and said nothing."""
    renamed = json.loads(json.dumps(WITH_MAPPINGS).replace("nist-800-53", "something-else"))

    assert _counted(renamed) == 4


def _run(tmp_path: Path, existing, monkeypatch, parsed=None):
    """Run `etl-hipaa` against a catalog on disk, with the network faked."""
    out = tmp_path / "controls.json"
    out.write_text(json.dumps(existing), encoding="utf-8")

    from policyforge.ingest import hipaa_loader

    monkeypatch.setattr(hipaa_loader, "current_ecfr_date", lambda: "2026-01-01")
    monkeypatch.setattr(hipaa_loader, "fetch_ecfr_subpart_c_xml", lambda **_: "<xml/>")

    import dataclasses

    # The command calls `dataclasses.asdict` on whatever the parser returned.
    # These fixtures are already dicts, so asdict is the identity here — the
    # command's own write path is what is under test, not the parser's.
    rows = parsed if parsed is not None else WITHOUT_MAPPINGS
    monkeypatch.setattr(hipaa_loader, "parse_hipaa_security_rule", lambda _xml: rows)
    monkeypatch.setattr(dataclasses, "asdict", lambda row: row)

    result = CliRunner().invoke(cli, ["etl-hipaa", "--out", str(out)])
    return result, out


def test_it_refuses_and_writes_nothing_when_mappings_would_be_lost(tmp_path, monkeypatch):
    """The defect, as a test: the single command would have replaced a
    catalog carrying mappings with one carrying none."""
    before = json.dumps(WITH_MAPPINGS)
    result, out = _run(tmp_path, WITH_MAPPINGS, monkeypatch)

    assert result.exit_code != 0
    assert out.read_text(encoding="utf-8") == before, "the catalog must be untouched"
    assert "etl-hipaa-crosswalk" in result.output, "it must name what to run instead"
    assert "4" in result.output and "0" in result.output, "it must say what would be lost"


def test_a_partial_loss_is_refused_too(tmp_path, monkeypatch):
    """65 to 60 passes any presence check and has destroyed five mappings."""
    fewer = json.loads(json.dumps(WITH_MAPPINGS))
    fewer[0]["enhancements"][0]["source_crosswalk"] = {}

    result, out = _run(tmp_path, WITH_MAPPINGS, monkeypatch, parsed=fewer)

    assert result.exit_code != 0
    assert json.loads(out.read_text(encoding="utf-8")) == WITH_MAPPINGS


def test_it_writes_normally_when_nothing_would_be_lost(tmp_path, monkeypatch):
    """A catalog with no mappings yet — the first run of the pipeline — is
    written without complaint, which is the path that must stay open."""
    result, out = _run(tmp_path, WITHOUT_MAPPINGS, monkeypatch)

    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text(encoding="utf-8")) == WITHOUT_MAPPINGS


def test_it_writes_when_the_catalog_does_not_exist_yet(tmp_path, monkeypatch):
    """Nothing to lose, so nothing to refuse."""
    from policyforge.ingest import hipaa_loader

    monkeypatch.setattr(hipaa_loader, "current_ecfr_date", lambda: "2026-01-01")
    monkeypatch.setattr(hipaa_loader, "fetch_ecfr_subpart_c_xml", lambda **_: "<xml/>")
    monkeypatch.setattr(hipaa_loader, "parse_hipaa_security_rule", lambda _xml: WITHOUT_MAPPINGS)

    import dataclasses

    monkeypatch.setattr(dataclasses, "asdict", lambda row: row)
    out = tmp_path / "new" / "controls.json"

    result = CliRunner().invoke(cli, ["etl-hipaa", "--out", str(out)])

    assert result.exit_code == 0, result.output
    assert out.exists()
