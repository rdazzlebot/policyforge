"""A per-organization crosswalk file over a catalog's published mapping.

The property everything else rests on: an overlay seeded from the published
mapping changes nothing, and each departure from it — a rejection, an
addition, a pair still under review — reaches the crosswalk as exactly that.
"""

from __future__ import annotations

import re

import pytest

from policyforge.crosswalk.overlay import (
    ACCEPTED,
    REJECTED,
    MappingRow,
    OverlayError,
    apply_overlays,
    check_overlay,
    dump_overlay,
    load_overlay,
    load_overlays,
    parse_overlay,
    seed_overlay,
)
from policyforge.ingest.schema import Control, ControlEnhancement
from policyforge.mapping.crosswalk import build_crosswalk

HIPAA = "HIPAA Security Rule"


def _catalogs():
    nist = [
        Control(
            control_id=cid,
            title=cid,
            framework="NIST 800-53",
            framework_version="r5",
            control_statement="x",
        )
        for cid in ("SI-3", "IR-6", "AT-2", "RA-3")
    ]
    hipaa = [
        Control(
            control_id="164.308(a)(5)(i)",
            title="Security awareness and training",
            framework=HIPAA,
            framework_version="45 CFR 164",
            control_statement="Implement a security awareness and training program.",
            source_crosswalk={"nist": "AT-2"},
            enhancements=[
                ControlEnhancement(
                    enhancement_id="164.308(a)(5)(ii)(B)",
                    title="Protection from malicious software",
                    baseline="Required",
                    description="Procedures for guarding against and reporting malicious software.",
                    source_crosswalk={"nist": "SI-3, RA-3"},
                )
            ],
        ),
        Control(
            control_id="164.308(a)(1)(i)",
            title="Security management process",
            framework=HIPAA,
            framework_version="45 CFR 164",
            control_statement="Implement policies and procedures to prevent security violations.",
            source_crosswalk={"nist": "RA-3"},
        ),
    ]
    return nist + hipaa


def _mapped(controls):
    return {
        nist: sorted(entry.get("hipaa", [])) for nist, entry in build_crosswalk(controls).items()
    }


def test_a_seeded_overlay_changes_nothing():
    before = _mapped(_catalogs())
    controls = _catalogs()
    overlay = seed_overlay(controls, HIPAA)

    apply_overlays(controls, [overlay])

    assert _mapped(controls) == before


def test_a_seeded_overlay_survives_a_round_trip_through_yaml(tmp_path):
    controls = _catalogs()
    path = tmp_path / "hipaa.yaml"
    path.write_text(dump_overlay(seed_overlay(controls, HIPAA)), encoding="utf-8")

    apply_overlays(controls, [load_overlay(path)])

    assert _mapped(controls) == _mapped(_catalogs())


def test_a_rejected_pair_is_gone_and_an_added_one_is_present():
    controls = _catalogs()
    overlay = seed_overlay(controls, HIPAA)
    rows = overlay.requirements["164.308(a)(5)(ii)(B)"]
    next(r for r in rows if r.control == "RA-3").status = REJECTED
    rows.append(MappingRow(control="IR-6", relationship="superset", status=ACCEPTED))

    apply_overlays(controls, [overlay])
    mapped = _mapped(controls)

    assert "164.308(a)(5)(ii)(B)" in mapped["IR-6"]
    assert "164.308(a)(5)(ii)(B)" not in mapped["RA-3"]
    # The other requirement mapping to RA-3 is untouched by that rejection.
    assert "164.308(a)(1)(i)" in mapped["RA-3"]


def test_a_proposed_pair_does_not_reach_the_crosswalk():
    controls = _catalogs()
    overlay = seed_overlay(controls, HIPAA)
    overlay.requirements["164.308(a)(1)(i)"].append(MappingRow(control="IR-6"))

    apply_overlays(controls, [overlay])

    assert "164.308(a)(1)(i)" not in _mapped(controls).get("IR-6", [])


def test_a_requirement_the_overlay_does_not_list_keeps_the_published_mapping():
    """Reviewing some requirements must not unmap the rest."""
    controls = _catalogs()
    overlay = parse_overlay(
        {
            "framework": HIPAA,
            "requirements": {"164.308(a)(1)(i)": [{"control": "IR-6", "status": "accepted"}]},
        }
    )

    apply_overlays(controls, [overlay])
    mapped = _mapped(controls)

    assert "164.308(a)(5)(ii)(B)" in mapped["SI-3"]
    assert "164.308(a)(1)(i)" in mapped["IR-6"]
    assert "164.308(a)(1)(i)" not in mapped["RA-3"]


def test_a_requirement_with_every_pair_rejected_maps_to_nothing():
    controls = _catalogs()
    overlay = parse_overlay(
        {
            "framework": HIPAA,
            "requirements": {"164.308(a)(1)(i)": [{"control": "RA-3", "status": "rejected"}]},
        }
    )

    apply_overlays(controls, [overlay])

    assert "164.308(a)(1)(i)" not in _mapped(controls).get("RA-3", [])


def test_an_overlay_for_another_framework_touches_nothing_here():
    controls = _catalogs()
    overlay = parse_overlay(
        {
            "framework": "GovRAMP",
            "requirements": {"164.308(a)(1)(i)": [{"control": "IR-6", "status": "accepted"}]},
        }
    )

    assert apply_overlays(controls, [overlay]) == 0
    assert _mapped(controls) == _mapped(_catalogs())


@pytest.mark.parametrize(
    ("row", "complaint"),
    [
        ({"control": "SI-3", "status": "acepted"}, "status 'acepted'"),
        ({"control": "SI-3", "relationship": "same"}, "relationship 'same'"),
        ({"status": "accepted"}, "needs a `control:`"),
    ],
)
def test_a_typo_that_would_change_what_is_mapped_is_refused(row, complaint):
    """A misspelled status would otherwise read as not-accepted and silently unmap."""
    with pytest.raises(OverlayError, match=re.escape(complaint)):
        parse_overlay({"framework": HIPAA, "requirements": {"164.308(a)(1)(i)": [row]}})


def test_an_overlay_names_its_framework():
    with pytest.raises(OverlayError, match="framework"):
        parse_overlay({"requirements": {}})


def test_invalid_yaml_names_the_file(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("framework: [unclosed\n", encoding="utf-8")
    with pytest.raises(OverlayError, match=r"broken\.yaml"):
        load_overlay(path)


def test_a_missing_directory_is_no_overlays(tmp_path):
    assert load_overlays(tmp_path / "nowhere") == []


def test_stale_and_unreviewed_entries_are_reported_not_dropped():
    controls = _catalogs()
    overlay = parse_overlay(
        {
            "framework": HIPAA,
            "requirements": {
                "164.999(z)": [{"control": "SI-3", "status": "accepted"}],
                "164.308(a)(5)(ii)(B)": [
                    {"control": "SI-3", "status": "accepted"},
                    {"control": "ZZ-9", "status": "proposed"},
                ],
            },
        }
    )

    check = check_overlay(overlay, controls)

    assert check.unknown_requirements == ["164.999(z)"]
    assert check.unknown_controls == [("164.308(a)(5)(ii)(B)", "ZZ-9")]
    # RA-3 is published for that requirement, and the overlay neither
    # accepts nor rejects it: a catalog update nobody has looked at.
    assert check.unreviewed_published == [("164.308(a)(5)(ii)(B)", "RA-3")]
    assert check.proposed == 1
    assert not check.is_clean


# ---- applied wherever catalogs are loaded -------------------------------


def _write_catalogs(tmp_path):
    import dataclasses
    import json

    controls = _catalogs()
    nist = [dataclasses.asdict(c) for c in controls if c.framework.startswith("NIST")]
    hipaa = [dataclasses.asdict(c) for c in controls if c.framework == HIPAA]
    nist_path, hipaa_path = tmp_path / "nist.json", tmp_path / "hipaa.json"
    nist_path.write_text(json.dumps(nist), encoding="utf-8")
    hipaa_path.write_text(json.dumps(hipaa), encoding="utf-8")
    return nist_path, hipaa_path


def _map(tmp_path, monkeypatch):
    import json

    from click.testing import CliRunner

    from policyforge.cli import cli

    nist_path, hipaa_path = _write_catalogs(tmp_path)
    out = tmp_path / "crosswalk.json"
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli,
        ["map", "--controls", str(nist_path), "--controls", str(hipaa_path), "--out", str(out)],
    )
    crosswalk = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return result, crosswalk


def test_the_map_command_uses_the_organizations_overlay(tmp_path, monkeypatch):
    (tmp_path / "config" / "crosswalks").mkdir(parents=True)
    (tmp_path / "config" / "crosswalks" / "hipaa.yaml").write_text(
        "framework: HIPAA Security Rule\n"
        "requirements:\n"
        "  164.308(a)(5)(ii)(B):\n"
        "    - {control: SI-3, status: accepted}\n"
        "    - {control: RA-3, status: rejected}\n",
        encoding="utf-8",
    )

    result, crosswalk = _map(tmp_path, monkeypatch)

    assert result.exit_code == 0, result.output
    assert crosswalk["SI-3"] == {"hipaa": ["164.308(a)(5)(ii)(B)"]}
    assert crosswalk["RA-3"] == {"hipaa": ["164.308(a)(1)(i)"]}


def test_without_an_overlay_the_map_command_is_unchanged(tmp_path, monkeypatch):
    result, crosswalk = _map(tmp_path, monkeypatch)

    assert result.exit_code == 0, result.output
    assert sorted(crosswalk["RA-3"]["hipaa"]) == ["164.308(a)(1)(i)", "164.308(a)(5)(ii)(B)"]


def test_an_unreadable_overlay_stops_the_command_rather_than_being_skipped(tmp_path, monkeypatch):
    (tmp_path / "config" / "crosswalks").mkdir(parents=True)
    (tmp_path / "config" / "crosswalks" / "hipaa.yaml").write_text(
        "framework: HIPAA Security Rule\n"
        "requirements:\n"
        "  164.308(a)(5)(ii)(B):\n"
        "    - {control: RA-3, status: rejectd}\n",
        encoding="utf-8",
    )

    result, crosswalk = _map(tmp_path, monkeypatch)

    assert result.exit_code != 0
    assert "rejectd" in result.output
    assert crosswalk is None


def test_zardoz_sees_the_same_overlay(tmp_path, monkeypatch):
    from policyforge.zardoz.shell import ShellState
    from policyforge.zardoz.skills import _controls

    nist_path, hipaa_path = _write_catalogs(tmp_path)
    (tmp_path / "config" / "crosswalks").mkdir(parents=True)
    (tmp_path / "config" / "crosswalks" / "hipaa.yaml").write_text(
        "framework: HIPAA Security Rule\n"
        "requirements:\n"
        "  164.308(a)(5)(ii)(B):\n"
        "    - {control: RA-3, status: rejected}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    state = ShellState(controls_paths=[nist_path, hipaa_path])

    crosswalk = build_crosswalk(_controls(state))

    assert crosswalk["RA-3"] == {"hipaa": ["164.308(a)(1)(i)"]}


def test_the_built_crosswalk_is_byte_identical_across_processes(tmp_path):
    """String hashing is randomised per process; the output must not depend on it.

    `build_crosswalk` iterated a set of NIST ids, so `map` wrote the same
    crosswalk with its keys in a different order on every run. Found while
    checking that a seeded overlay changes nothing: the two files differed,
    and so did two runs with no overlay at all.
    """
    import json
    import os
    import subprocess
    import sys

    nist_path, hipaa_path = _write_catalogs(tmp_path)
    script = (
        "import json, sys\n"
        "from policyforge.ingest.schema import load_controls\n"
        "from policyforge.mapping.crosswalk import build_crosswalk\n"
        "controls = load_controls(sys.argv[1]) + load_controls(sys.argv[2])\n"
        "print(json.dumps(build_crosswalk(controls)))\n"
    )
    outputs = set()
    for seed in ("1", "2", "3", "4"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(
            [sys.executable, "-c", script, str(nist_path), str(hipaa_path)],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        outputs.add(result.stdout)
    assert len(outputs) == 1, outputs
    assert json.loads(outputs.pop())


# ---- `policyforge crosswalk seed` and `check` ----------------------------


def _cli(tmp_path, monkeypatch, *args):
    from click.testing import CliRunner

    from policyforge.cli import cli

    nist_path, hipaa_path = _write_catalogs(tmp_path)
    monkeypatch.chdir(tmp_path)
    controls = ["--controls", str(nist_path), "--controls", str(hipaa_path)]
    return CliRunner().invoke(cli, ["crosswalk", *args, *controls])


def test_seed_writes_the_published_mapping_and_check_finds_it_clean(tmp_path, monkeypatch):
    seeded = _cli(tmp_path, monkeypatch, "seed")
    assert seeded.exit_code == 0, seeded.output
    path = tmp_path / "config" / "crosswalks" / "hipaa-security-rule.yaml"
    overlay = load_overlay(path)
    assert [r.control for r in overlay.requirements["164.308(a)(5)(ii)(B)"]] == ["SI-3", "RA-3"]
    assert "4 published pairs" in seeded.output

    checked = _cli(tmp_path, monkeypatch, "check", "--strict")
    assert checked.exit_code == 0, checked.output
    assert "matches the catalogs" in checked.output


def test_seed_refuses_to_overwrite_decisions(tmp_path, monkeypatch):
    assert _cli(tmp_path, monkeypatch, "seed").exit_code == 0
    path = tmp_path / "config" / "crosswalks" / "hipaa-security-rule.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("accepted", "rejected", 1), "utf-8")

    again = _cli(tmp_path, monkeypatch, "seed")

    assert again.exit_code != 0
    assert "--force" in again.output
    assert "rejected" in path.read_text(encoding="utf-8")


def test_seed_reads_the_published_mapping_not_an_existing_overlay(tmp_path, monkeypatch):
    """Seeding through the overlay would copy its rejections in as the published state."""
    assert _cli(tmp_path, monkeypatch, "seed").exit_code == 0
    path = tmp_path / "config" / "crosswalks" / "hipaa-security-rule.yaml"
    other = tmp_path / "config" / "crosswalks" / "zz-edited.yaml"
    other.write_text(
        "framework: HIPAA Security Rule\n"
        "requirements:\n"
        "  164.308(a)(5)(ii)(B):\n"
        "    - {control: RA-3, status: rejected}\n",
        encoding="utf-8",
    )

    result = _cli(tmp_path, monkeypatch, "seed", "--force")

    assert result.exit_code == 0, result.output
    rows = load_overlay(path).requirements["164.308(a)(5)(ii)(B)"]
    assert [r.control for r in rows] == ["SI-3", "RA-3"]


def test_check_strict_fails_on_stale_entries(tmp_path, monkeypatch):
    (tmp_path / "config" / "crosswalks").mkdir(parents=True)
    (tmp_path / "config" / "crosswalks" / "hipaa.yaml").write_text(
        "framework: HIPAA Security Rule\n"
        "requirements:\n"
        "  164.308(a)(5)(ii)(B):\n"
        "    - {control: SI-3, status: accepted}\n"
        "    - {control: ZZ-9, status: proposed}\n",
        encoding="utf-8",
    )

    result = _cli(tmp_path, monkeypatch, "check", "--strict")

    assert result.exit_code == 1
    assert "unknown control: 164.308(a)(5)(ii)(B) -> ZZ-9" in result.output
    assert "unreviewed: 164.308(a)(5)(ii)(B) -> RA-3" in result.output
    assert "1 pair(s) needing review" in result.output


def test_check_with_no_overlays_says_how_to_start(tmp_path, monkeypatch):
    result = _cli(tmp_path, monkeypatch, "check")
    assert result.exit_code == 0
    assert "crosswalk seed" in result.output
