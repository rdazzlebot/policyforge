"""The defects policyforge-1d's review of the crosswalk branch reproduced.

Each test is named for the property that was missing and fails on the code
reviewed at `c514059`. B1 and R1-R9 refer to that review.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from policyforge.crosswalk.overlay import (
    OverlayError,
    apply_overlays,
    load_overlay,
    load_overlays,
    parse_overlay,
    seed_overlay,
)
from policyforge.crosswalk.propose import RELATIONSHIP_PROPOSED
from policyforge.ingest.schema import Control, load_controls
from policyforge.llm.base import LLMResponse
from policyforge.mapping.crosswalk import build_crosswalk
from tests.test_crosswalk_cli import HIPAA, OVERLAY, RID, Mapper, _catalogs, _setup

ROOT = Path(__file__).resolve().parents[1]
LOCAL_LLM = {"provider": "local", "base_url": "http://localhost:11434/v1", "model": "qwen3"}
HOSTED = {"provider": "anthropic", "model": "claude-sonnet-5"}


# ---- B1: licensed text never lands in a tracked file ----------------------


class ScopeRecordingMapper(Mapper):
    """Maps like `Mapper`, and records the ledger scope each call ran in."""

    def __init__(self):
        super().__init__()
        self.content_classes = []

    def generate_json(self, *, prompt, **kwargs):
        from policyforge.llm import ledger

        scope = ledger.current_scope()
        self.content_classes.append(scope.content_class if scope else None)
        return super().generate_json(prompt=prompt, **kwargs)


def _licensed_setup(tmp_path, monkeypatch, llm, provider):
    import policyforge.cli as cli_mod

    controls = _catalogs()
    export_dir = tmp_path / "local_content"
    export_dir.mkdir()
    nist = tmp_path / "nist.json"
    hipaa = export_dir / "hipaa-licensed.json"
    nist.write_text(
        json.dumps([dataclasses.asdict(c) for c in controls if c.framework != HIPAA]), "utf-8"
    )
    hipaa.write_text(
        json.dumps([dataclasses.asdict(c) for c in controls if c.framework == HIPAA]), "utf-8"
    )
    config = {"llm": dict(llm), "frameworks": {"search_paths": [str(export_dir)]}}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_mod, "load_config", lambda: config)
    monkeypatch.setattr(cli_mod, "get_provider", lambda c: provider)
    return CliRunner().invoke(
        cli_mod.cli,
        ["crosswalk", "propose", "--controls", str(nist), "--controls", str(hipaa)],
    )


def test_propose_over_a_licensed_catalog_writes_no_requirement_text(tmp_path, monkeypatch):
    provider = ScopeRecordingMapper()

    result = _licensed_setup(tmp_path, monkeypatch, LOCAL_LLM, provider)

    assert result.exit_code == 0, result.output
    written = (tmp_path / OVERLAY).read_text(encoding="utf-8")
    assert "guarding against" not in written
    assert "malicious code protection" not in written
    row = next(r for r in load_overlay(tmp_path / OVERLAY).requirements[RID] if r.control == "SI-3")
    assert row.evidence["requirement"].startswith("sha256:")
    assert row.evidence["control"].startswith("sha256:")
    # R9: the ledger says what the calls carried.
    assert provider.content_classes and set(provider.content_classes) == {"licensed"}


def test_propose_refuses_a_licensed_catalog_for_a_hosted_provider(tmp_path, monkeypatch):
    """R9: nothing is sent, and nothing is written."""
    provider = ScopeRecordingMapper()

    result = _licensed_setup(tmp_path, monkeypatch, HOSTED, provider)

    assert result.exit_code != 0
    assert "REFUSED" in result.output
    assert provider.calls == 0
    assert not (tmp_path / OVERLAY).exists()


def test_public_catalog_quotes_are_still_kept(tmp_path, monkeypatch):
    run, _ = _setup(tmp_path, monkeypatch, Mapper())
    assert run("crosswalk", "propose").exit_code == 0
    row = next(r for r in load_overlay(tmp_path / OVERLAY).requirements[RID] if r.control == "SI-3")
    assert "malicious" in row.evidence["requirement"]


@pytest.mark.parametrize("command", ["seed", "propose", "review"])
def test_an_overlay_is_never_written_into_the_bundled_catalogs(tmp_path, monkeypatch, command):
    (tmp_path / "data" / "frameworks").mkdir(parents=True)
    run, _ = _setup(tmp_path, monkeypatch, Mapper())
    flag = "--out" if command == "seed" else "--overlay"
    target = tmp_path / "data" / "frameworks" / "hipaa-overlay.yaml"

    result = run("crosswalk", command, flag, str(target))

    assert result.exit_code != 0
    assert "data/frameworks" in result.output
    assert not target.exists()


def test_overlays_are_gitignored_here_and_by_init():
    from policyforge.scaffold import GITIGNORE

    assert "config/crosswalks/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "config/crosswalks/" in GITIGNORE.splitlines()


# ---- R1: a model reply never changes a report before review ---------------


def test_propose_leaves_coverage_exactly_as_it_was(tmp_path, monkeypatch):
    class Superset(Mapper):
        def generate_json(self, *, prompt, **kwargs):
            if "Protection from malicious software" not in prompt:
                return super().generate_json(prompt=prompt, **kwargs)
            rows = [
                {
                    "control": "AT-2",
                    "relationship": "superset",
                    "requirement_quote": "guarding against, detecting, and reporting malicious",
                    "control_quote": "Provide security literacy training",
                }
            ]
            return LLMResponse(text=json.dumps({"mappings": rows}), model="fake")

    run, _ = _setup(tmp_path, monkeypatch, Superset())
    topics = tmp_path / "topics.yaml"
    topics.write_text(
        "topics:\n  - name: Training\n    owner: People\n    nist_controls: [AT-2]\n", "utf-8"
    )
    assert run("crosswalk", "seed").exit_code == 0
    before = run("coverage", "--topics", str(topics)).output

    assert run("crosswalk", "propose").exit_code == 0

    assert run("coverage", "--topics", str(topics)).output == before
    row = next(r for r in load_overlay(tmp_path / OVERLAY).requirements[RID] if r.control == "AT-2")
    assert row.relationship == "unspecified"
    assert row.proposed_relationship == "superset"
    assert RELATIONSHIP_PROPOSED in row.flags


def test_a_relationship_a_person_set_survives_every_propose_run():
    from datetime import date

    from policyforge.crosswalk.propose import Proposal, ProposedMapping, merge

    overlay = parse_overlay(
        {
            "framework": HIPAA,
            "requirements": {
                RID: [{"control": "AT-2", "relationship": "equal", "status": "accepted"}]
            },
        }
    )
    mapping = ProposedMapping("AT-2", "superset", "reporting malicious software", "training")
    for _ in range(2):
        merge(
            overlay,
            [Proposal(RID, ["AT-2"], mappings=[mapping])],
            _catalogs(),
            model="m",
            today=date(2026, 9, 17),
        )

    (row,) = overlay.requirements[RID]
    assert row.relationship == "equal"
    assert row.proposed_relationship == "superset"
    assert row.flags == [RELATIONSHIP_PROPOSED]


def test_review_promotes_the_suggested_relationship_and_can_override_it(tmp_path, monkeypatch):
    run, _ = _setup(tmp_path, monkeypatch, Mapper())
    (tmp_path / "config" / "crosswalks").mkdir(parents=True)
    (tmp_path / OVERLAY).write_text(
        "framework: HIPAA Security Rule\n"
        "requirements:\n"
        f"  {RID}:\n"
        "    - control: AT-2\n"
        "      status: accepted\n"
        "      proposed_relationship: superset\n"
        f"      flags: [{RELATIONSHIP_PROPOSED}]\n"
        "    - control: SI-3\n"
        "      status: proposed\n"
        "      proposed_relationship: intersects\n",
        encoding="utf-8",
    )

    result = run("crosswalk", "review", "--who", "ryan", input="a\n\n\na\nequal\n\n")

    assert result.exit_code == 0, result.output
    rows = {r.control: r for r in load_overlay(tmp_path / OVERLAY).requirements[RID]}
    assert rows["AT-2"].relationship == "superset"
    assert rows["SI-3"].relationship == "equal"
    assert rows["AT-2"].proposed_relationship == rows["SI-3"].proposed_relationship == ""


# ---- R2: every catalog's way of naming 800-53 -----------------------------


@pytest.mark.parametrize("catalog", ["fedramp", "arc-ampe"])
def test_catalogs_keyed_nist_800_53_seed_and_reject(catalog):
    controls = load_controls(ROOT / "data" / "frameworks" / catalog / "controls.json")
    framework = controls[0].framework
    overlay = seed_overlay(controls, framework)
    rid, rows = next((rid, rows) for rid, rows in overlay.requirements.items() if rows)
    assert rows, f"{catalog} seeded no pairs"

    before = build_crosswalk(controls)
    assert any(rid in ids for entry in before.values() for ids in entry.values())
    for row in rows:
        row.status = "rejected"
    apply_overlays(controls, [overlay])

    after = build_crosswalk(controls)
    assert not any(rid in ids for entry in after.values() for ids in entry.values())


def test_a_govramp_style_catalog_keyed_nist_800_53_is_overlaid():
    control = Control(
        control_id="AC-2",
        title="Account Management",
        framework="GovRAMP",
        framework_version="r5",
        source_crosswalk={"NIST 800-53": "AC-2"},
    )
    overlay = seed_overlay([control], "GovRAMP")
    assert [r.control for r in overlay.requirements["AC-2"]] == ["AC-2"]
    overlay.requirements["AC-2"][0].status = "rejected"
    apply_overlays([control], [overlay])
    assert control.source_crosswalk == {}


# ---- R3 and R4: a file that cannot mean one thing is refused ---------------


def test_the_same_pair_cannot_be_both_accepted_and_rejected():
    with pytest.raises(OverlayError, match="already row 1"):
        parse_overlay(
            {
                "framework": HIPAA,
                "requirements": {
                    RID: [
                        {"control": "SI-3", "status": "accepted"},
                        {"control": "si-3", "status": "rejected"},
                    ]
                },
            }
        )


def test_control_ids_are_upper_cased():
    overlay = parse_overlay(
        {"framework": HIPAA, "requirements": {RID: [{"control": "si-3(1)", "status": "accepted"}]}}
    )
    assert overlay.requirements[RID][0].control == "SI-3(1)"


def test_two_overlays_for_one_framework_are_refused(tmp_path):
    for name in ("a.yaml", "b.yaml"):
        (tmp_path / name).write_text(
            "framework: HIPAA Security Rule\nrequirements: {}\n", encoding="utf-8"
        )
    with pytest.raises(OverlayError, match="both map"):
        load_overlays(tmp_path)


# ---- R5: synthesize does not read a crosswalk older than the overlay -------


def test_synthesize_refuses_a_crosswalk_older_than_an_overlay(tmp_path, monkeypatch):
    import os

    import policyforge.cli as cli_mod

    run, _ = _setup(tmp_path, monkeypatch, Mapper())
    crosswalk = tmp_path / "crosswalk.json"
    assert run("map", "--out", str(crosswalk)).exit_code == 0
    assert run("crosswalk", "seed").exit_code == 0
    stamp = crosswalk.stat().st_mtime
    os.utime(tmp_path / OVERLAY, (stamp + 10, stamp + 10))

    result = CliRunner().invoke(
        cli_mod.cli,
        [
            "synthesize",
            "--topic",
            "Endpoint",
            "--nist-controls",
            "SI-3",
            "--controls",
            str(tmp_path / "nist.json"),
            "--controls",
            str(tmp_path / "hipaa.json"),
            "--crosswalk",
            str(crosswalk),
            "--out-dir",
            str(tmp_path / "synthesis"),
        ],
    )

    assert result.exit_code != 0
    assert "policyforge map" in result.output


# ---- R6: overlays are written with LF --------------------------------------


def test_seed_writes_lf_only(tmp_path, monkeypatch):
    run, _ = _setup(tmp_path, monkeypatch, Mapper())
    assert run("crosswalk", "seed").exit_code == 0
    assert b"\r" not in (tmp_path / OVERLAY).read_bytes()


# ---- R7: nothing a model quoted can drive the reviewer's terminal ----------


ESCAPE = "\x1b[2J\x1b]0;owned\x07"


def test_control_characters_are_removed_from_a_hand_edited_overlay():
    overlay = parse_overlay(
        {
            "framework": HIPAA,
            "requirements": {
                RID: [
                    {
                        "control": "SI-3",
                        "status": "accepted",
                        "rationale": f"fine{ESCAPE}",
                        "evidence": {"requirement": f"quote{ESCAPE}"},
                    }
                ]
            },
        }
    )
    row = overlay.requirements[RID][0]
    assert "\x1b" not in row.rationale and "\x07" not in row.rationale
    assert "\x1b" not in row.evidence["requirement"]


def test_an_escape_sequence_in_a_quote_never_reaches_review(tmp_path, monkeypatch):
    class Escaping(Mapper):
        def generate_json(self, *, prompt, **kwargs):
            if "Protection from malicious software" not in prompt:
                return super().generate_json(prompt=prompt, **kwargs)
            rows = [
                {
                    "control": "SI-3",
                    "relationship": "intersects",
                    # The escape's letters are one stray word at the end, inside
                    # the matcher's tolerance for a quote this long: the review's
                    # reproduction, which old and new matchers both accept.
                    "requirement_quote": "guarding against, detecting, and reporting "
                    "malicious software [2J",
                    "control_quote": "malicious code protection mechanisms at system entry",
                }
            ]
            return LLMResponse(text=json.dumps({"mappings": rows}), model="fake")

    run, _ = _setup(tmp_path, monkeypatch, Escaping())
    assert run("crosswalk", "propose").exit_code == 0
    overlay = load_overlay(tmp_path / OVERLAY)
    stored = next(r for r in overlay.requirements[RID] if r.control == "SI-3")
    assert "\x1b" not in stored.evidence["requirement"]

    # Skip through every row, so the one carrying the quote is printed.
    result = run("crosswalk", "review", "--who", "ryan", input="s\ns\n")

    assert "-> SI-3" in result.output
    assert "\x1b" not in result.output and "\x07" not in result.output
