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

    monkeypatch.setattr(
        cli_mod, "load_config", lambda: {"llm": {"provider": "anthropic", "model": "m"}}
    )
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


def test_etl_hipaa_fetches_and_parses(tmp_path, monkeypatch):
    from pathlib import Path

    from policyforge.cli import cli

    fixture = (Path(__file__).parent / "fixtures" / "ecfr_45cfr164_subpart_c.xml").read_text(
        encoding="utf-8"
    )
    monkeypatch.setattr(
        "policyforge.ingest.hipaa_loader.fetch_ecfr_subpart_c_xml", lambda **kwargs: fixture
    )
    out_path = tmp_path / "hipaa-controls.json"

    result = CliRunner().invoke(cli, ["etl-hipaa", "--out", str(out_path)])

    assert result.exit_code == 0
    controls = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(controls) == 34
    assert any(c["control_id"] == "164.308(a)(1)(i)" for c in controls)


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
        text="# Authenticator Management Standard\n\n"
        "Staff must manage authenticators. [NIST IA-5]\n"
    )
    monkeypatch.setattr(
        cli_mod,
        "load_config",
        lambda: {"org": {"name": "Acme Corp", "industry": "Fintech", "vendors": ["Okta"]}},
    )
    monkeypatch.setattr(cli_mod, "get_provider", lambda config: fake)

    history_dir = tmp_path / "history"

    result = CliRunner().invoke(
        cli_mod.cli,
        [
            "generate",
            "--tier",
            "standard",
            "--synthesis",
            str(synthesis_path),
            "--out",
            str(out_path),
            "--history-dir",
            str(history_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Acme Corp" in fake.calls[0]["prompt"]
    assert out_path.read_text(encoding="utf-8").startswith("# Authenticator Management Standard")

    from policyforge.history.version_store import load_history

    history = load_history(history_dir, "standard/authenticator-mgmt")
    assert len(history) == 1
    assert history[0].version == 1
    assert history[0].source == "generate"


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

    fake = FakeProvider(
        text="# Authenticator Management Policy\n\nStaff must use strong authentication.\n"
    )
    monkeypatch.setattr(
        cli_mod,
        "load_config",
        lambda: {"org": {"name": "Acme Corp", "industry": "Fintech", "vendors": ["Okta"]}},
    )
    monkeypatch.setattr(cli_mod, "get_provider", lambda config: fake)

    # --tier policy without --standard should fail fast with a clear error.
    missing_standard = CliRunner().invoke(
        cli_mod.cli,
        [
            "generate",
            "--tier",
            "policy",
            "--synthesis",
            str(synthesis_path),
            "--history-dir",
            str(tmp_path / "history"),
        ],
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
            "--history-dir",
            str(tmp_path / "history"),
        ],
    )

    assert result.exit_code == 0
    assert "Authenticator Management Standard" in fake.calls[0]["prompt"]
    assert out_path.read_text(encoding="utf-8").startswith("# Authenticator Management Policy")


def test_generate_parser_writes_generated_module(tmp_path, monkeypatch):
    import policyforge.cli as cli_mod

    sample_path = tmp_path / "sample.csv"
    sample_path.write_text("control_id,title\nAC-1,Access Control Policy\n", encoding="utf-8")
    out_path = tmp_path / "hitrust_loader.py"

    fake = FakeProvider(
        text="from __future__ import annotations\n\n"
        "def load_hitrust_export(export_path):\n    return []\n"
    )
    monkeypatch.setattr(cli_mod, "load_config", lambda: {})
    monkeypatch.setattr(cli_mod, "get_provider", lambda config: fake)

    result = CliRunner().invoke(
        cli_mod.cli,
        [
            "generate-parser",
            "--framework",
            "hitrust",
            "--sample",
            str(sample_path),
            "--out",
            str(out_path),
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert "control_id,title" in fake.calls[0]["prompt"]
    written = out_path.read_text(encoding="utf-8")
    assert "def load_hitrust_export(export_path):" in written

    # Re-running without --force should refuse to clobber the file just written.
    refused = CliRunner().invoke(
        cli_mod.cli,
        [
            "generate-parser",
            "--framework",
            "hitrust",
            "--sample",
            str(sample_path),
            "--out",
            str(out_path),
            "--yes",
        ],
    )
    assert refused.exit_code != 0


def test_generate_parser_rejects_syntactically_invalid_output(tmp_path, monkeypatch):
    import policyforge.cli as cli_mod

    sample_path = tmp_path / "sample.csv"
    sample_path.write_text("control_id,title\nAC-1,Access Control Policy\n", encoding="utf-8")
    out_path = tmp_path / "hitrust_loader.py"

    fake = FakeProvider(text="def broken(:\n    this is not python")
    monkeypatch.setattr(cli_mod, "load_config", lambda: {})
    monkeypatch.setattr(cli_mod, "get_provider", lambda config: fake)

    result = CliRunner().invoke(
        cli_mod.cli,
        [
            "generate-parser",
            "--framework",
            "hitrust",
            "--sample",
            str(sample_path),
            "--out",
            str(out_path),
            "--yes",
        ],
    )

    assert result.exit_code != 0
    assert not out_path.exists()


def test_import_confluence_writes_markdown_and_records_history(tmp_path, monkeypatch):
    from policyforge.cli import cli

    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "tok")

    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    monkeypatch.setattr(
        "requests.get",
        lambda *a, **k: FakeResponse(
            {
                "results": [
                    {
                        "id": "1",
                        "title": "Authenticator Management Standard",
                        "version": {"number": 1},
                        "body": {
                            "storage": {
                                "value": "<h1>Authenticator Management Standard</h1><p>Body</p>"
                            }
                        },
                        "_links": {"webui": "/x"},
                    }
                ]
            }
        ),
    )

    out_path = tmp_path / "imported.md"
    history_dir = tmp_path / "history"

    result = CliRunner().invoke(
        cli,
        [
            "import-confluence",
            "--tier",
            "standard",
            "--name",
            "authenticator-mgmt",
            "--space",
            "ENG",
            "--title",
            "Authenticator Management Standard",
            "--host",
            "https://example.atlassian.net/wiki",
            "--out",
            str(out_path),
            "--history-dir",
            str(history_dir),
        ],
    )

    assert result.exit_code == 0
    assert out_path.read_text(encoding="utf-8").startswith("# Authenticator Management Standard")

    from policyforge.history.version_store import load_history

    history = load_history(history_dir, "standard/authenticator-mgmt")
    assert len(history) == 1
    assert history[0].source == "confluence-import"


def test_history_command_lists_and_diffs_versions(tmp_path):
    from policyforge.cli import cli
    from policyforge.history.version_store import record_version

    history_dir = tmp_path / "history"
    record_version(history_dir, "standard/auth-mgmt", "line one\n", source="generate")
    record_version(history_dir, "standard/auth-mgmt", "line one\nline two\n", source="generate")

    listing = CliRunner().invoke(
        cli,
        ["history", "--tier", "standard", "--name", "auth-mgmt", "--history-dir", str(history_dir)],
    )
    assert listing.exit_code == 0
    assert "v1" in listing.output
    assert "v2" in listing.output

    diff = CliRunner().invoke(
        cli,
        [
            "history",
            "--tier",
            "standard",
            "--name",
            "auth-mgmt",
            "--history-dir",
            str(history_dir),
            "--diff",
            "latest",
        ],
    )
    assert diff.exit_code == 0
    assert "+line two" in diff.output


def test_history_command_reports_no_history(tmp_path):
    from policyforge.cli import cli

    result = CliRunner().invoke(
        cli,
        [
            "history",
            "--tier",
            "standard",
            "--name",
            "never-generated",
            "--history-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "No recorded history" in result.output


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
