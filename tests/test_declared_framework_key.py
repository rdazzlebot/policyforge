"""A catalog keys by the `crosswalk_as:` its `framework.yaml` declares (#295, PR 1 of 2).

`normalize_framework` keyed a framework by the first word of its prose name
unless an alias needle matched first, and every sibling of a pinned name fell
through to the bare word (#176 recorded seven). 80's ruling: a declared key in
`framework.yaml` (`crosswalk_as:`, not `key:`, which gitleaks reads as a
secret); the declaration wins; a tree-derived test that each shipped
catalog's declared key equals today's key, so this change moves no key; and a
disagreement for a shipped catalog is a test failure.

**Read from the directories, not registered at load** (80's condition): a
name keyed before any catalog is loaded -- a citation parsed first -- must
still get the declared key.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from policyforge.frameworks.registry import FrameworkKeyWarning, declared_keys, load_framework
from policyforge.mapping import crosswalk
from policyforge.mapping.crosswalk import normalize_framework, prose_framework_key

CATALOGS = Path(__file__).resolve().parent.parent / "data" / "frameworks"


@pytest.fixture
def fresh_keys():
    """Read the declarations again before and after, so no test sees another's."""
    crosswalk.reset_declared_keys()
    yield
    crosswalk.reset_declared_keys()


def _names(directory: Path) -> set[str]:
    framework = load_framework(directory)
    rows = json.loads((directory / "controls.json").read_text(encoding="utf-8"))
    return {framework.name} | {r["framework"] for r in rows}


# -- the shipped tree: declared, and equal to today's key -------------------------------


def _shipped() -> list[Path]:
    return [d for d in sorted(CATALOGS.iterdir()) if (d / "controls.json").exists()]


def test_every_shipped_catalog_declares_a_key():
    assert len(_shipped()) >= 10
    missing = [d.name for d in _shipped() if not load_framework(d).key]
    assert not missing, f"no `crosswalk_as:` in framework.yaml: {missing}"


@pytest.mark.parametrize("directory", _shipped(), ids=lambda d: d.name)
def test_the_declared_key_equals_todays_key_for_every_name(directory):
    """**No key moves.** Today's key is the prose one -- alias, else first
    word -- and it must equal the declaration for EVERY name the catalog goes
    by, the manifest's and the one its rows carry. Citations and overlays
    written before this change key through the prose path; a disagreement
    here would re-key them silently."""
    key = load_framework(directory).key
    for name in _names(directory):
        assert prose_framework_key(name) == key, (directory.name, name)


def test_the_shipped_tree_declares_without_a_single_disagreement():
    with warnings.catch_warnings():
        warnings.simplefilter("error", FrameworkKeyWarning)
        keys = declared_keys(roots=[CATALOGS])
    assert keys["nist 800-53"] == "nist-800-53"
    assert keys["hipaa security rule"] == "hipaa"
    assert keys["nist sp 800-171 rev 3"] == "nist-800-171"


# -- the declaration wins, with nothing loaded -----------------------------------------------


def _catalog(root: Path, directory: str, *, name: str, key: str, framework: str | None = None):
    path = root / directory
    path.mkdir(parents=True)
    (path / "framework.yaml").write_text(f"name: {name}\ncrosswalk_as: {key}\n", encoding="utf-8")
    row = {
        "control_id": "X-1",
        "title": "t",
        "framework": framework or name,
        "framework_version": "1",
    }
    (path / "controls.json").write_text(json.dumps([row]), encoding="utf-8")


def test_a_byoc_declared_name_keys_by_its_declaration_with_nothing_loaded(
    tmp_path, monkeypatch, fresh_keys
):
    """80's condition, as its test: no `load_controls`, no `load_catalogs`
    -- only the directory on disk, found through the default search path."""
    _catalog(
        tmp_path / "frameworks", "acme-baseline", name="Acme Security Baseline", key="acme-baseline"
    )
    monkeypatch.chdir(tmp_path)
    assert prose_framework_key("Acme Security Baseline") == "acme"  # the premise
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FrameworkKeyWarning)
        assert normalize_framework("Acme Security Baseline") == "acme-baseline"
        # Case and spacing as a hand-written citation might carry them.
        assert normalize_framework("  acme   SECURITY baseline ") == "acme-baseline"
        # Only the declared name: a longer one is someone else's.
        assert normalize_framework("Acme Security Baseline Extended") == "acme"


def test_a_sibling_of_a_pinned_name_no_longer_falls_through(tmp_path, monkeypatch, fresh_keys):
    """The class #295 is about: `NIST Privacy Framework` has no alias, so its
    prose key is bare `nist`, colliding with every other NIST name that falls
    through. Declared, it keys to itself, and the disagreement is named."""
    _catalog(
        tmp_path / "frameworks", "nist-privacy", name="NIST Privacy Framework", key="nist-privacy"
    )
    monkeypatch.chdir(tmp_path)
    with pytest.warns(FrameworkKeyWarning, match="NIST Privacy Framework.*'nist'"):
        assert normalize_framework("NIST Privacy Framework") == "nist-privacy"


def test_two_catalogs_declaring_one_name_differently_are_named_and_the_first_wins(
    tmp_path, fresh_keys
):
    first, second = tmp_path / "a", tmp_path / "b"
    _catalog(first, "one", name="Shared Name", key="shared-one")
    _catalog(second, "two", name="Shared Name", key="shared-two")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", FrameworkKeyWarning)
        keys = declared_keys(roots=[first, second])
    messages = [str(w.message) for w in caught if issubclass(w.category, FrameworkKeyWarning)]
    assert keys["shared name"] == "shared-one"
    # Two warnings, both true: the conflict, and "Shared Name" not keying
    # to 'shared-one' by prose (which gives 'shared').
    assert any("declared as 'shared-one'" in m and "as 'shared-two'" in m for m in messages)
    assert any("would give 'shared'" in m for m in messages)
    assert len(messages) == 2, messages


def test_the_bundled_catalogs_declare_from_any_working_directory(tmp_path, monkeypatch):
    """An installed wheel has no `data/frameworks` under the working
    directory, so the shipped declarations must come from the bundled root,
    not from the search path that happens to find them in a checkout."""
    monkeypatch.chdir(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("error", FrameworkKeyWarning)
        keys = declared_keys()
    assert keys.get("nist 800-53") == "nist-800-53"
    assert keys.get("nist ai rmf playbook") == "nist-ai-rmf-playbook"


def test_a_catalog_without_a_key_declares_nothing(tmp_path):
    path = tmp_path / "plain"
    path.mkdir()
    (path / "framework.yaml").write_text("name: Plain Catalog\n", encoding="utf-8")
    assert declared_keys(roots=[tmp_path]) == {}
