"""Two gate checks for defects the rest of the gate only caught by accident.

CRLF: a conflict-resolution script using `Path.write_text` on Windows
converted 1,768 lines of CHANGELOG.md. mdformat caught it — but only
because mdformat rejects any CR, which is a symptom of the cause rather
than the cause, and nothing covers `.yaml`, `.json`, `.toml` or `.py`.

Conflict markers: `git add -A` mid-rebase staged a file git still reported
as unresolved, and the rebase completed clean. The gate caught that one
only because a conflict marker is a Python syntax error. In `.yaml` — every
workflow file, and `framework.yaml` — nothing in the gate parses it at all.

Both tests build throwaway repositories rather than stubbing git, because
the thing under test is what git reports, not what we believe it reports.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check


def _repo(root: Path, *, autocrlf: str, attributes: str | None = None) -> Path:
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    for key, value in (
        ("core.autocrlf", autocrlf),
        ("user.email", "t@example.invalid"),
        ("user.name", "t"),
        ("commit.gpgsign", "false"),
    ):
        subprocess.run(["git", "config", key, value], cwd=root, check=True)
    if attributes is not None:
        (root / ".gitattributes").write_bytes(attributes.encode())
    return root


def _add_all(root: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)


# --------------------------------------------------------------- line endings


def test_a_clean_tree_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path, autocrlf="false")
    (root / "conf.yaml").write_bytes(b"a: 1\nb: 2\n")
    _add_all(root)
    assert check.check_line_endings(root) is True


def test_a_crlf_yaml_fails(tmp_path: Path) -> None:
    """The unprotected case: autocrlf off, and no attribute covers .yaml."""
    root = _repo(tmp_path, autocrlf="false")
    (root / "conf.yaml").write_bytes(b"a: 1\r\nb: 2\r\n")
    _add_all(root)
    assert check.check_line_endings(root) is False


def test_a_crlf_python_file_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, autocrlf="false")
    (root / "mod.py").write_bytes(b"x = 1\r\n")
    _add_all(root)
    assert check.check_line_endings(root) is False


def test_markdown_is_already_protected_by_gitattributes(tmp_path: Path) -> None:
    """Not a gap — a record of why this check is not about .md.

    `*.md text eol=lf` normalises the blob even with autocrlf off, so CRLF
    markdown cannot reach a commit. The check exists for the file types
    that attribute does not name.
    """
    root = _repo(tmp_path, autocrlf="false", attributes="*.md text eol=lf\n")
    (root / "doc.md").write_bytes(b"line one\r\nline two\r\n")
    _add_all(root)
    assert check.check_line_endings(root) is True


def test_a_windows_checkout_is_not_flagged(tmp_path: Path) -> None:
    """autocrlf=true gives a CRLF *working tree* and an LF *index*.

    Reading bytes off disk would fail on every Windows machine. The check
    asks git about the blob, which is what ships.
    """
    root = _repo(tmp_path, autocrlf="true")
    (root / "conf.yaml").write_bytes(b"a: 1\r\nb: 2\r\n")
    _add_all(root)
    assert check.check_line_endings(root) is True


def test_git_failing_is_a_skip_not_a_pass(tmp_path: Path) -> None:
    """Not a repository at all — must decline, never report success."""
    assert check.check_line_endings(tmp_path) is None


# ------------------------------------------------------------ conflict markers

MARKED_YAML = b"""jobs:
<<<<<<< HEAD
  build: {runs-on: ubuntu-latest}
=======
  build: {runs-on: windows-latest}
>>>>>>> other
"""


def test_a_clean_tree_has_no_markers(tmp_path: Path) -> None:
    root = _repo(tmp_path, autocrlf="false")
    (root / "ci.yaml").write_bytes(b"jobs:\n  build: {}\n")
    _add_all(root)
    assert check.check_conflict_markers(root) is True


def test_a_marked_yaml_fails(tmp_path: Path) -> None:
    """The file type with no incidental catch anywhere in the gate."""
    root = _repo(tmp_path, autocrlf="false")
    (root / "ci.yaml").write_bytes(MARKED_YAML)
    _add_all(root)
    assert check.check_conflict_markers(root) is False


def test_a_marked_json_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, autocrlf="false")
    (root / "data.json").write_bytes(b'{\n<<<<<<< HEAD\n  "a": 1\n>>>>>>> other\n}\n')
    _add_all(root)
    assert check.check_conflict_markers(root) is False


@pytest.mark.parametrize(
    "body",
    [
        b"Heading\n=======\n\nprose\n",
        b"```\nCoverage\n" + b"=" * 60 + b"\n  In scope  287\n```\n",
        b"x = '======='\n",
    ],
    ids=["setext-underline", "fenced-sample-output", "string-literal"],
)
def test_equals_runs_alone_are_not_flagged(tmp_path: Path, body: bytes) -> None:
    """The false positive this check must not have.

    Seven equals signs are a legal setext underline, and a tree-wide grep
    for `=======` really did report two hits in README.md — 60-character
    rules inside a fenced sample-output block. git never writes a
    `=======` without the `<<<<<<< ` that opens the conflict, so only the
    unambiguous markers are searched.
    """
    root = _repo(tmp_path, autocrlf="false")
    (root / "doc.md").write_bytes(body)
    _add_all(root)
    assert check.check_conflict_markers(root) is True


def test_a_diff3_base_marker_fails(tmp_path: Path) -> None:
    """`merge.conflictStyle = diff3` adds a ||||||| section."""
    root = _repo(tmp_path, autocrlf="false")
    (root / "ci.yaml").write_bytes(
        b"a\n<<<<<<< HEAD\nb\n||||||| base\nc\n=======\nd\n>>>>>>> other\n"
    )
    _add_all(root)
    assert check.check_conflict_markers(root) is False


def test_conflict_marker_check_on_a_non_repository_skips(tmp_path: Path) -> None:
    assert check.check_conflict_markers(tmp_path) is None
