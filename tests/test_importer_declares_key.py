"""The importers declare the catalog they write (#295, PR 2).

80's ruling: `etl-hitrust` and `etl-govramp` write `framework_id:` into the
catalog's `framework.yaml`, **equal to the key the name already had**, so no
citation or overlay written before the import moves. A manifest already
there is the user's: it gains the line if it lacks one, and a different
value is kept and named.
"""

from __future__ import annotations

import warnings

import pytest
import yaml
from click.testing import CliRunner

from policyforge.frameworks.registry import FrameworkKeyWarning, declared_keys
from policyforge.mapping import crosswalk
from policyforge.mapping.crosswalk import prose_framework_key
from tests.test_cli import _hitrust


@pytest.fixture(autouse=True)
def _permitted(monkeypatch):
    import policyforge.cli as cli_mod

    monkeypatch.setattr(cli_mod, "load_config", lambda: {})
    crosswalk.reset_declared_keys()
    yield
    crosswalk.reset_declared_keys()


def _govramp(tmp_path, out):
    import policyforge.cli as cli_mod
    from tests.test_govramp import build_workbook

    matrix = build_workbook(tmp_path / "GovRAMP-Controls-Matrix_Mod_Rev5_V1.06.xlsx")
    return CliRunner().invoke(
        cli_mod.cli, ["etl-govramp", "--export", str(matrix), "--out", str(out), "--force"]
    )


def _declared(root):
    with warnings.catch_warnings():
        warnings.simplefilter("error", FrameworkKeyWarning)
        return declared_keys(roots=[root])


def test_etl_govramp_declares_the_key_the_name_already_had(tmp_path):
    from policyforge.ingest.govramp import FRAMEWORK

    out = tmp_path / "catalogs" / "govramp" / "controls.json"
    result = _govramp(tmp_path, out)

    assert result.exit_code == 0, result.output
    manifest = yaml.safe_load((out.parent / "framework.yaml").read_text(encoding="utf-8"))
    assert manifest["framework_id"] == prose_framework_key(FRAMEWORK) == "govramp"
    assert manifest["name"] == FRAMEWORK and manifest["licence"] == "licensed"
    # Read back through the same path keying uses, silently: nothing moved.
    assert _declared(tmp_path / "catalogs")[" ".join(FRAMEWORK.lower().split())] == "govramp"
    assert "framework_id govramp" in result.output


def test_etl_hitrust_declares_the_key_the_name_already_had(tmp_path, monkeypatch):
    from policyforge.ingest.hitrust import FRAMEWORK

    out = tmp_path / "catalogs" / "hitrust" / "controls.json"
    result = _hitrust(monkeypatch, tmp_path, "--out", str(out), "--force")

    assert result.exit_code == 0, result.output
    manifest = yaml.safe_load((out.parent / "framework.yaml").read_text(encoding="utf-8"))
    assert manifest["framework_id"] == prose_framework_key(FRAMEWORK) == "hitrust-csf"


def test_a_manifest_without_a_key_gains_one_line_and_keeps_the_rest(tmp_path):
    out = tmp_path / "catalogs" / "govramp" / "controls.json"
    out.parent.mkdir(parents=True)
    written = "# my notes\nname: GovRAMP\nlicence: licensed\n"
    (out.parent / "framework.yaml").write_text(written, encoding="utf-8")

    result = _govramp(tmp_path, out)

    assert result.exit_code == 0, result.output
    text = (out.parent / "framework.yaml").read_text(encoding="utf-8")
    assert text == written + "framework_id: govramp\n"


def test_a_manifest_that_declares_a_different_key_is_kept_and_named(tmp_path):
    out = tmp_path / "catalogs" / "govramp" / "controls.json"
    out.parent.mkdir(parents=True)
    written = "name: GovRAMP\nframework_id: govramp-moderate\n"
    (out.parent / "framework.yaml").write_text(written, encoding="utf-8")

    result = _govramp(tmp_path, out)

    assert result.exit_code == 0, result.output
    assert (out.parent / "framework.yaml").read_text(encoding="utf-8") == written
    assert "already declares framework_id govramp-moderate" in result.output
    assert "Keeping yours" in result.output
    # Where the declaration is made, its prose collision is stated (80 on
    # #347): `govramp`, the key the name had, is an alias target.
    assert "would key to 'govramp', a key the built-in alias table assigns" in result.output


def test_a_declaration_equal_to_todays_key_states_no_collision(tmp_path):
    out = tmp_path / "catalogs" / "govramp" / "controls.json"
    result = _govramp(tmp_path, out)
    assert result.exit_code == 0, result.output
    assert "Note:" not in result.output


def test_nothing_is_declared_when_nothing_is_written(tmp_path):
    """Parse-only is the safe default for licensed content; it writes no
    manifest either."""
    import policyforge.cli as cli_mod
    from tests.test_govramp import build_workbook

    matrix = build_workbook(tmp_path / "GovRAMP-Controls-Matrix_Mod_Rev5_V1.06.xlsx")
    result = CliRunner().invoke(cli_mod.cli, ["etl-govramp", "--export", str(matrix)])

    assert result.exit_code == 0, result.output
    assert not list(tmp_path.rglob("framework.yaml"))
