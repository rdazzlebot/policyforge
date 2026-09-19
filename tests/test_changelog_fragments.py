"""Fragment assembly, and the guard accepting a fragment.

The coupling is the part worth testing hardest. `scripts/changelog_guard.py`
demands a changelog entry; `changelog.d/` exists so people stop editing the
one shared section. If the guard did not accept a fragment it would push
every author back into the file the fragments were built to keep them out
of — a well-meant check defeating the change it sits beside.

The assembly cases come from what actually went wrong in one sitting: a
resolution that converted 1,768 lines to CRLF, one that left an entry as a
heading so five unrelated entries nested under it, and two merges that
shipped no entry at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import changelog_fragments as frag
import changelog_guard as guard


def write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


# ------------------------------------------------- the guard accepts fragments


def test_a_fragment_satisfies_the_guard() -> None:
    """Otherwise the guard defeats the fragments."""
    ok, message = guard.decide(
        ["src/policyforge/cli/etl.py", "changelog.d/1d-my-branch.md"], body=""
    )
    assert ok
    assert "changelog.d/1d-my-branch.md" in message


def test_the_fragment_readme_does_not_count_as_an_entry() -> None:
    """Editing the instructions is not writing an entry."""
    ok, _ = guard.decide(["src/policyforge/cli/etl.py", "changelog.d/README.md"], body="")
    assert not ok


def test_editing_the_changelog_directly_still_satisfies_it() -> None:
    ok, _ = guard.decide(["src/policyforge/cli/etl.py", "CHANGELOG.md"], body="")
    assert ok


def test_the_failure_message_offers_the_fragment_first() -> None:
    _, message = guard.decide(["src/policyforge/cli/etl.py"], body="")
    assert "changelog.d/" in message
    assert message.index("changelog.d/") < message.index("CHANGELOG.md")


# ----------------------------------------------------------------- validation


def test_an_empty_fragment_is_a_problem(tmp_path: Path) -> None:
    """Someone opened the file and did not write the entry."""
    write(tmp_path, "a.md", "   \n\n")
    assert any("empty" in p for p in frag.check(frag.fragments(tmp_path)))


def test_a_fragment_with_crlf_is_a_problem(tmp_path: Path) -> None:
    """The 1,768-line conversion in miniature."""
    (tmp_path / "a.md").write_bytes(b"**A change.** It does a thing.\r\n")
    assert any("CR" in p for p in frag.check(frag.fragments(tmp_path)))


def test_a_fragment_that_starts_a_section_is_a_problem(tmp_path: Path) -> None:
    """A `## ` inside a fragment makes a second release section."""
    write(tmp_path, "a.md", "## 1.5.0\n\n**A change.**\n")
    assert any("section" in p for p in frag.check(frag.fragments(tmp_path)))


def test_a_bold_lead_fragment_is_fine(tmp_path: Path) -> None:
    write(tmp_path, "a.md", "**A change.** What a user does differently.\n")
    assert frag.check(frag.fragments(tmp_path)) == []


def test_the_readme_is_never_a_fragment(tmp_path: Path) -> None:
    write(tmp_path, "README.md", "# Changelog fragments\n\nHow to write one.\n")
    write(tmp_path, "1d-thing.md", "**A change.**\n")
    assert [p.name for p in frag.fragments(tmp_path)] == ["1d-thing.md"]


# ------------------------------------------------------------------- assembly


def test_assembly_emits_filename_order_under_one_heading(tmp_path: Path) -> None:
    write(tmp_path, "b-second.md", "**Second.** Body.\n")
    write(tmp_path, "a-first.md", "**First.** Body.\n")
    section = frag.assemble(frag.fragments(tmp_path), "1.5.0")

    assert section.startswith("## 1.5.0\n\n")
    assert section.count("## ") == 1
    assert section.index("**First.**") < section.index("**Second.**")


def test_the_section_is_inserted_above_the_newest_release() -> None:
    changelog = "# Changelog\n\n## 1.4.0\n\nold entry\n\n## 1.3.0\n\nolder\n"
    out = frag.insert(changelog, "## 1.5.0\n\nnew entry\n\n")

    assert out.index("## 1.5.0") < out.index("## 1.4.0") < out.index("## 1.3.0")
    assert "old entry" in out and "older" in out


def test_insertion_without_a_release_heading_refuses(tmp_path: Path) -> None:
    """Better to stop than to guess where a section belongs."""
    with pytest.raises(SystemExit):
        frag.insert("# Changelog\n\nnothing released yet\n", "## 1.5.0\n\nx\n\n")


def test_assembly_does_not_reorder_or_categorise(tmp_path: Path) -> None:
    """The tool has no opinion about what belongs first, deliberately.

    This changelog's voice is bold-lead paragraphs in a narrative order.
    A tool emitting `### Added` / `### Fixed` would flatten that into
    something nobody here would have written, so ordering stays a person's
    judgement — made once, in one file, with no conflict to resolve.
    """
    write(tmp_path, "a.md", "**Trivial.** A small thing.\n")
    write(tmp_path, "b.md", "**Breaking.** Your pipeline fails.\n")
    section = frag.assemble(frag.fragments(tmp_path), "1.5.0")

    assert section.index("**Trivial.**") < section.index("**Breaking.**")
    assert "### " not in section
