"""`policyforge init`, and the package data it depends on.

The packaging half matters as much as the command. pyproject.toml lists the
packages and the bundled files by hand, because the catalogs are mapped in
from outside src/, and a hand-kept list is exactly what drifts: a new
subpackage left off ships an install that fails on import, and a catalog
glob would ship somebody's licensed export. These tests hold both lists to
what is actually in the repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from policyforge.scaffold import (
    BUNDLED_CATALOGS,
    BYOC_CATALOGS,
    CATALOG_FILES,
    CONFIG_EXAMPLES,
    GITIGNORE,
    init_project,
)

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORKS = ROOT / "data" / "frameworks"


def _pyproject() -> dict:
    tomllib = pytest.importorskip("tomllib")
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


# ---- what ships ---------------------------------------------------------


def test_only_public_domain_catalogs_are_bundled():
    """Decided by each catalog's own manifest, not by what is on disk."""
    public = sorted(
        d.name
        for d in FRAMEWORKS.iterdir()
        if (d / "framework.yaml").is_file()
        and yaml.safe_load((d / "framework.yaml").read_text(encoding="utf-8")).get("licence")
        == "public-domain"
    )
    assert sorted(BUNDLED_CATALOGS) == public


def test_every_other_catalog_directory_is_bring_your_own():
    others = sorted(
        d.name for d in FRAMEWORKS.iterdir() if d.is_dir() and d.name not in BUNDLED_CATALOGS
    )
    assert sorted(BYOC_CATALOGS) == others
    for name in BYOC_CATALOGS:
        assert not (FRAMEWORKS / name / "controls.json").exists()


def test_package_data_names_exactly_the_files_init_copies():
    package_data = _pyproject()["tool"]["setuptools"]["package-data"]
    expected = {f"{c}/{f}" for c in BUNDLED_CATALOGS for f in CATALOG_FILES}
    expected |= {f"{c}/README.md" for c in BYOC_CATALOGS}
    assert set(package_data["policyforge._bundled.frameworks"]) == expected
    assert not any("*" in entry for entry in package_data["policyforge._bundled.frameworks"])
    assert set(package_data["policyforge._bundled.config"]) == set(CONFIG_EXAMPLES)


def test_every_package_under_src_is_listed():
    """Listed by hand, so a new subpackage must be added by hand too."""
    listed = set(_pyproject()["tool"]["setuptools"]["packages"])
    discovered = {
        ".".join(p.parent.relative_to(ROOT / "src").parts)
        for p in (ROOT / "src").rglob("__init__.py")
    }
    mapped = set(_pyproject()["tool"]["setuptools"]["package-dir"]) - {""}
    assert listed == discovered | mapped


def test_the_mapped_directories_exist():
    for package, directory in _pyproject()["tool"]["setuptools"]["package-dir"].items():
        assert (ROOT / directory).is_dir(), f"{package} maps to missing {directory}"


def test_the_license_is_declared_as_spdx():
    """Homebrew and PyPI both read it; a file pointer alone names no licence."""
    assert _pyproject()["project"]["license"] == "Apache-2.0"


# ---- the command --------------------------------------------------------


def test_init_lays_out_a_project_that_matches_the_repository(tmp_path):
    report = init_project(tmp_path / "proj")
    project = tmp_path / "proj"

    for catalog in BUNDLED_CATALOGS:
        for name in CATALOG_FILES:
            copied = project / "data" / "frameworks" / catalog / name
            # Bytes: a catalog is checked against its recorded hash.
            assert copied.read_bytes() == (FRAMEWORKS / catalog / name).read_bytes()
    for catalog in BYOC_CATALOGS:
        assert (project / "data" / "frameworks" / catalog / "README.md").is_file()
        assert not (project / "data" / "frameworks" / catalog / "controls.json").exists()
    for name in CONFIG_EXAMPLES:
        assert (project / "config" / name).read_bytes() == (ROOT / "config" / name).read_bytes()
    assert (project / "local_content" / ".gitkeep").is_file()
    assert (project / ".gitignore").read_text(encoding="utf-8") == GITIGNORE
    assert report.kept == []


def test_init_never_overwrites(tmp_path):
    init_project(tmp_path)
    edited = tmp_path / "config" / "config.example.yaml"
    edited.write_text("mine", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("my own\n", encoding="utf-8")

    report = init_project(tmp_path)

    assert report.written == []
    assert edited.read_text(encoding="utf-8") == "mine"
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "my own\n"


def test_the_written_gitignore_keeps_what_the_repository_keeps_out():
    """The same reasons apply to a project as to this repository."""
    ours = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for line in GITIGNORE.splitlines():
        if line and not line.startswith("#"):
            assert line in ours, f"{line!r} is not ignored by this repository"
    for required in ("config/config.yaml", "config/topics.yaml", "output/", ".env"):
        assert required in GITIGNORE.splitlines()


def test_init_command_reports_and_leaves_a_usable_catalog_set(tmp_path):
    from policyforge.cli import cli
    from policyforge.frameworks.registry import check_licences

    result = CliRunner().invoke(cli, ["init", str(tmp_path / "proj")])
    assert result.exit_code == 0, result.output
    assert "wrote  data/frameworks/nist-800-53-r5/controls.json" in result.output

    report = check_licences(roots=[tmp_path / "proj" / "data" / "frameworks"])
    assert report.ok
    assert sorted(f.id for f in report.frameworks) == sorted(BUNDLED_CATALOGS)

    again = CliRunner().invoke(cli, ["init", str(tmp_path / "proj")])
    assert again.exit_code == 0
    assert "wrote" not in again.output


def test_the_package_version_matches_pyproject():
    """A release tags one version; the command must report the same one."""
    import policyforge

    assert policyforge.__version__ == _pyproject()["project"]["version"]
