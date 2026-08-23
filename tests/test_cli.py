"""CLI-level tests: exercise each `policyforge` command end-to-end through
Click's test runner, faking the LLM provider and config so nothing here
makes a network call."""

from __future__ import annotations

import json

from click.testing import CliRunner


class FakeProvider:
    def __init__(self, text="- merged requirement [NIST IA-5]"):
        self.text = text
        self.calls = []

    def generate(self, *, system, prompt, max_tokens=4096, temperature=0.2):
        from policyforge.llm.base import LLMResponse

        self.calls.append({"system": system, "prompt": prompt})
        return LLMResponse(text=self.text, model="fake")

    def check(self):
        return True


def _write_controls_json(path, entries):
    path.write_text(json.dumps(entries), encoding="utf-8")


def _control(**overrides):
    base = {
        "control_id": "IA-5",
        "title": "Authenticator Management",
        "framework": "NIST 800-53",
        "framework_version": "Rev 5",
        "family": None,
        "family_abbr": None,
        "baseline": None,
        "control_statement": "Manage system authenticators.",
        "discussion": "",
        "enhancements": [],
        "related_controls": [],
        "source_crosswalk": {},
        "source_path": None,
    }
    base.update(overrides)
    return base


def test_llm_check_reports_ok(monkeypatch):
    import policyforge.cli as cli_mod

    monkeypatch.setattr(cli_mod, "load_config", lambda: {"llm": {"provider": "anthropic", "model": "m"}})
    monkeypatch.setattr(cli_mod, "get_provider", lambda config: FakeProvider())

    result = CliRunner().invoke(cli_mod.cli, ["llm-check"])

    assert result.exit_code == 0
    assert "OK" in result.output


def test_etl_vault_parses_fixture_directory(tmp_path):
    from policyforge.cli import cli

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / "AC-2.md").write_text(
        """---
control_id: AC-2
title: Account Management
framework: NIST 800-53
version: Rev 5
---

# AC-2: Account Management

## Control Statement

> Manage information system accounts.
""",
        encoding="utf-8",
    )
    out_path = tmp_path / "controls.json"

    result = CliRunner().invoke(
        cli, ["etl-vault", "--controls-dir", str(vault_dir), "--out", str(out_path)]
    )

    assert result.exit_code == 0
    controls = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(controls) == 1
    assert controls[0]["control_id"] == "AC-2"


def test_map_builds_crosswalk_from_controls_json(tmp_path):
    from policyforge.cli import cli

    controls_path = tmp_path / "controls.json"
    _write_controls_json(
        controls_path,
        [_control(source_crosswalk={"fedramp": "IA-5 (same ID)"})],
    )
    out_path = tmp_path / "crosswalk.json"

    result = CliRunner().invoke(
        cli, ["map", "--controls", str(controls_path), "--out", str(out_path)]
    )

    assert result.exit_code == 0
    assert json.loads(out_path.read_text(encoding="utf-8")) == {"IA-5": {"fedramp": ["IA-5"]}}


def test_synthesize_writes_merged_requirements(tmp_path, monkeypatch):
    import policyforge.cli as cli_mod

    controls_path = tmp_path / "controls.json"
    _write_controls_json(controls_path, [_control()])
    crosswalk_path = tmp_path / "crosswalk.json"
    crosswalk_path.write_text(json.dumps({}), encoding="utf-8")
    out_dir = tmp_path / "synthesis"

    monkeypatch.setattr(cli_mod, "load_config", lambda: {})
    monkeypatch.setattr(cli_mod, "get_provider", lambda config: FakeProvider())

    result = CliRunner().invoke(
        cli_mod.cli,
        [
            "synthesize",
            "--topic",
            "Authenticator Mgmt",
            "--nist-controls",
            "IA-5",
            "--controls",
            str(controls_path),
            "--crosswalk",
            str(crosswalk_path),
            "--out-dir",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0
    written = (out_dir / "authenticator-mgmt.md").read_text(encoding="utf-8")
    assert "merged requirement [NIST IA-5]" in written


def test_synthesize_fails_when_no_controls_match(tmp_path, monkeypatch):
    import policyforge.cli as cli_mod

    controls_path = tmp_path / "controls.json"
    _write_controls_json(controls_path, [_control()])
    crosswalk_path = tmp_path / "crosswalk.json"
    crosswalk_path.write_text(json.dumps({}), encoding="utf-8")

    monkeypatch.setattr(cli_mod, "load_config", lambda: {})
    monkeypatch.setattr(cli_mod, "get_provider", lambda config: FakeProvider())

    result = CliRunner().invoke(
        cli_mod.cli,
        [
            "synthesize",
            "--topic",
            "Nonexistent",
            "--nist-controls",
            "ZZ-99",
            "--controls",
            str(controls_path),
            "--crosswalk",
            str(crosswalk_path),
            "--out-dir",
            str(tmp_path / "synthesis"),
        ],
    )

    assert result.exit_code != 0


def test_generate_standard_drafts_document_from_synthesis(tmp_path, monkeypatch):
    import policyforge.cli as cli_mod

    synthesis_path = tmp_path / "authenticator-mgmt.md"
    synthesis_path.write_text("- Authenticators must be managed. [NIST IA-5]\n", encoding="utf-8")
    out_path = tmp_path / "standards" / "authenticator-mgmt.md"

    fake = FakeProvider(
        text="# Authenticator Management Standard\n\nStaff must manage authenticators. [NIST IA-5]\n"
    )
    monkeypatch.setattr(
        cli_mod,
        "load_config",
        lambda: {"org": {"name": "Acme Corp", "industry": "Fintech", "vendors": ["Okta"]}},
    )
    monkeypatch.setattr(cli_mod, "get_provider", lambda config: fake)

    result = CliRunner().invoke(
        cli_mod.cli,
        ["generate", "--tier", "standard", "--synthesis", str(synthesis_path), "--out", str(out_path)],
    )

    assert result.exit_code == 0
    assert "Acme Corp" in fake.calls[0]["prompt"]
    assert out_path.read_text(encoding="utf-8").startswith("# Authenticator Management Standard")


def test_generate_policy_requires_standard_and_references_its_title(tmp_path, monkeypatch):
    import policyforge.cli as cli_mod

    synthesis_path = tmp_path / "authenticator-mgmt.md"
    synthesis_path.write_text("- Authenticators must be managed. [NIST IA-5]\n", encoding="utf-8")
    standard_path = tmp_path / "standards" / "authenticator-mgmt.md"
    standard_path.parent.mkdir()
    standard_path.write_text(
        "# Authenticator Management Standard\n\nStaff must manage authenticators. [NIST IA-5]\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "policies" / "authenticator-mgmt.md"

    fake = FakeProvider(text="# Authenticator Management Policy\n\nStaff must use strong authentication.\n")
    monkeypatch.setattr(
        cli_mod,
        "load_config",
        lambda: {"org": {"name": "Acme Corp", "industry": "Fintech", "vendors": ["Okta"]}},
    )
    monkeypatch.setattr(cli_mod, "get_provider", lambda config: fake)

    # --tier policy without --standard should fail fast with a clear error.
    missing_standard = CliRunner().invoke(
        cli_mod.cli,
        ["generate", "--tier", "policy", "--synthesis", str(synthesis_path)],
    )
    assert missing_standard.exit_code != 0

    result = CliRunner().invoke(
        cli_mod.cli,
        [
            "generate",
            "--tier",
            "policy",
            "--synthesis",
            str(synthesis_path),
            "--standard",
            str(standard_path),
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 0
    assert "Authenticator Management Standard" in fake.calls[0]["prompt"]
    assert out_path.read_text(encoding="utf-8").startswith("# Authenticator Management Policy")


def test_export_confluence_dry_run_prints_storage_format(tmp_path):
    from policyforge.cli import cli

    doc_path = tmp_path / "policy.md"
    doc_path.write_text("# Title\n\nBody text.\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "export-confluence",
            "--doc",
            str(doc_path),
            "--space",
            "ENG",
            "--title",
            "Test Page",
            "--host",
            "https://example.atlassian.net/wiki",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "<h1>Title</h1>" in result.output
