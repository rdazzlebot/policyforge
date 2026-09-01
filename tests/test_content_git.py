"""check / publish / pull — the repo-backed loop.

markdown in a repo -> pull request -> merge -> published to Confluence, and
back again when somebody edits the wiki directly.

The tests that matter are the refusals. Publishing over a page full of
macros this tool cannot round-trip destroys work nobody agreed to lose, and
pulling such a page produces a file that looks correct and does the damage
on its first publish. Both are refused by name rather than warned about
afterwards, and neither should ever become a warning somebody learns to
scroll past.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from click.testing import CliRunner

from policyforge.content.check import check_tree
from policyforge.export.publish import CREATED, SKIPPED, UPDATED, publish_tree
from policyforge.export.pull import REFUSED, UNCHANGED, WRITTEN, pull_pages, target_path

MACRO_PAGE = (
    '<ac:structured-macro ac:name="info"><ac:rich-text-body><p>Careful.</p>'
    "</ac:rich-text-body></ac:structured-macro><h1>Access</h1><p>Quarterly.</p>"
)
PLAIN_PAGE = "<h1>Access Control Standard</h1><p>Reviews happen quarterly.</p>"


@dataclass
class FakePage:
    id: str
    title: str
    storage_body: str
    version: int = 3
    webui_url: str = "https://x/wiki/page"
    labels: list = field(default_factory=list)
    ancestors: list = field(default_factory=list)


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _bound(title, space="SEC", page_title=None, body="Reviews happen quarterly."):
    page_title = page_title or title
    return (
        f"---\ntitle: {title}\nowner: IAM Engineering\n"
        f"confluence:\n  space: {space}\n  title: {page_title}\n---\n\n"
        f"# {title}\n\n{body}\n"
    )


def _patch_confluence(monkeypatch, *, pages=None, exported=None):
    """Fake the three network functions publish/pull reach for."""
    store = pages or {}

    def _fetch(*, space, title, host, **kwargs):
        if title not in store:
            raise LookupError(f"No Confluence page titled {title!r} in space {space!r}.")
        return FakePage(id=f"id-{title}", title=title, storage_body=store[title])

    def _export(markdown_text, *, space, title, host, **kwargs):
        if exported is not None:
            exported.append((space, title, markdown_text))
        return f"https://x/wiki/{title}"

    monkeypatch.setattr("policyforge.export.confluence_importer.fetch_confluence_page", _fetch)
    monkeypatch.setattr("policyforge.export.confluence_exporter.export_to_confluence", _export)
    monkeypatch.setattr(
        "policyforge.export.confluence_search.fetch_user_names", lambda ids, **kw: {}
    )


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------


def test_a_clean_tree_reports_nothing(tmp_path):
    _write(tmp_path, "standards/access-control.md", _bound("Access Control Standard"))

    report = check_tree(tmp_path)

    assert report.ok
    assert report.errors == []


def test_two_files_claiming_one_page_is_an_error(tmp_path):
    """Both would publish, the second would overwrite the first, and the repo
    would still contain two files each looking like the source of truth."""
    _write(tmp_path, "standards/a.md", _bound("A", page_title="Access Control Standard"))
    _write(tmp_path, "standards/b.md", _bound("B", page_title="Access Control Standard"))

    report = check_tree(tmp_path)

    assert not report.ok
    assert any("already claims" in f.message for f in report.errors)


def test_the_same_title_in_different_spaces_is_fine(tmp_path):
    _write(tmp_path, "standards/a.md", _bound("Access Control Standard", space="SEC"))
    _write(tmp_path, "standards/b.md", _bound("Access Control Standard", space="ENG"))

    assert check_tree(tmp_path).ok


def test_a_link_to_a_document_that_does_not_exist_is_an_error(tmp_path):
    _write(
        tmp_path,
        "standards/access-control.md",
        _bound("Access", body="See [the procedure](../procedures/review.md)."),
    )

    report = check_tree(tmp_path)

    assert not report.ok
    assert any("does not exist" in f.message for f in report.errors)


def test_a_link_that_resolves_is_not_an_error(tmp_path):
    _write(tmp_path, "procedures/review.md", _bound("Review Procedure"))
    _write(
        tmp_path,
        "standards/access-control.md",
        _bound("Access", body="See [the procedure](../procedures/review.md)."),
    )

    assert check_tree(tmp_path).ok


def test_a_confluence_block_with_no_space_cannot_publish_anywhere(tmp_path):
    _write(
        tmp_path,
        "standards/a.md",
        "---\ntitle: A\nowner: Sec\nconfluence:\n  title: Somewhere\n---\n\n# A\n",
    )

    report = check_tree(tmp_path)

    assert not report.ok
    assert any("no `space:`" in f.message for f in report.errors)


def test_a_missing_owner_warns_without_blocking(tmp_path):
    """A repo mid-migration is full of these, and a gate that cannot be
    satisfied gets switched off."""
    _write(tmp_path, "standards/a.md", "# A Standard\n\nText.\n")

    report = check_tree(tmp_path)

    assert report.ok
    assert any("no owner" in f.message for f in report.warnings)


def test_broken_frontmatter_is_an_error(tmp_path):
    _write(tmp_path, "standards/a.md", "---\ntitle: [unclosed\n---\n\n# A\n")

    assert not check_tree(tmp_path).ok


def test_citations_dropped_since_the_synthesis_are_reported(tmp_path):
    """Invisible in a diff of the prose, and it is the traceability an
    assessor needs."""
    synthesis = tmp_path / "synthesis"
    synthesis.mkdir()
    (synthesis / "access-control.md").write_text(
        "- Accounts are reviewed. [NIST AC-2 | HIPAA 164.308(a)(4)]\n"
        "- Credentials rotate. [NIST IA-5]\n",
        encoding="utf-8",
    )
    root = tmp_path / "docs"
    _write(root, "standards/access-control.md", _bound("Access", body="Reviews. [NIST AC-2]"))

    report = check_tree(root, synthesis_dir=synthesis)

    assert any("missing" in f.message and "IA-5" in f.message for f in report.warnings)


def test_the_check_command_exits_nonzero_on_an_error(tmp_path):
    import policyforge.cli as cli_mod

    _write(tmp_path, "standards/a.md", _bound("A", page_title="Shared"))
    _write(tmp_path, "standards/b.md", _bound("B", page_title="Shared"))

    result = CliRunner().invoke(cli_mod.cli, ["check", "--content-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "already claims" in result.output


def test_strict_makes_warnings_fail_too(tmp_path):
    import policyforge.cli as cli_mod

    _write(tmp_path, "standards/a.md", "# A Standard\n\nText.\n")
    args = ["check", "--content-dir", str(tmp_path)]

    assert CliRunner().invoke(cli_mod.cli, args).exit_code == 0
    assert CliRunner().invoke(cli_mod.cli, [*args, "--strict"]).exit_code == 1


# --------------------------------------------------------------------------
# publish
# --------------------------------------------------------------------------


def test_a_dry_run_plans_without_writing(tmp_path, monkeypatch):
    exported = []
    _patch_confluence(monkeypatch, exported=exported)
    _write(tmp_path, "standards/a.md", _bound("Access Control Standard"))

    report = publish_tree(tmp_path, host="https://x")

    assert exported == [], "nothing was published"
    assert [r.action for r in report.results] == [CREATED]
    assert "Would publish" in report.format_report()
    assert "--apply" in report.format_report()


def test_applying_publishes_the_document_body(tmp_path, monkeypatch):
    exported = []
    _patch_confluence(monkeypatch, exported=exported)
    _write(tmp_path, "standards/a.md", _bound("Access Control Standard"))

    publish_tree(tmp_path, host="https://x", dry_run=False)

    assert len(exported) == 1
    space, title, body = exported[0]
    assert (space, title) == ("SEC", "Access Control Standard")
    assert "Reviews happen quarterly" in body
    assert "confluence:" not in body, "frontmatter is not published"


def test_an_existing_page_is_an_update_not_a_create(tmp_path, monkeypatch):
    _patch_confluence(monkeypatch, pages={"Access Control Standard": PLAIN_PAGE})
    _write(tmp_path, "standards/a.md", _bound("Access Control Standard"))

    report = publish_tree(tmp_path, host="https://x")

    assert [r.action for r in report.results] == [UPDATED]


def test_a_page_full_of_macros_is_skipped_not_flattened(tmp_path, monkeypatch):
    """Publishing over it would destroy work nobody agreed to lose."""
    exported = []
    _patch_confluence(monkeypatch, pages={"Access Control Standard": MACRO_PAGE}, exported=exported)
    _write(tmp_path, "standards/a.md", _bound("Access Control Standard"))

    report = publish_tree(tmp_path, host="https://x", dry_run=False)

    assert exported == []
    assert [r.action for r in report.results] == [SKIPPED]
    assert "info" in report.skipped[0].reason


def test_allow_macros_publishes_anyway(tmp_path, monkeypatch):
    exported = []
    _patch_confluence(monkeypatch, pages={"Access Control Standard": MACRO_PAGE}, exported=exported)
    _write(tmp_path, "standards/a.md", _bound("Access Control Standard"))

    publish_tree(tmp_path, host="https://x", dry_run=False, allow_macros=True)

    assert len(exported) == 1


def test_a_document_with_no_destination_is_left_alone(tmp_path, monkeypatch):
    """A file with no `confluence:` block is how a draft stays a draft."""
    _patch_confluence(monkeypatch)
    _write(tmp_path, "standards/draft.md", "# A Draft\n\nNot ready.\n")

    report = publish_tree(tmp_path, host="https://x")

    assert report.results == []
    assert report.undeclared == 1


def test_only_narrows_the_run_to_what_a_merge_touched(tmp_path, monkeypatch):
    _patch_confluence(monkeypatch)
    _write(tmp_path, "standards/a.md", _bound("A"))
    _write(tmp_path, "policies/b.md", _bound("B"))

    report = publish_tree(tmp_path, host="https://x", only="policies/")

    assert [r.title for r in report.results] == ["B"]


# --------------------------------------------------------------------------
# pull
# --------------------------------------------------------------------------


def test_a_pulled_page_lands_at_its_tier_and_records_where_it_came_from(tmp_path, monkeypatch):
    """A repo path and a page title are different strings; a pull that did
    not record the correspondence would publish back to the wrong place."""
    _patch_confluence(monkeypatch, pages={"Access Control Standard": PLAIN_PAGE})

    report = pull_pages(
        [("SEC", "Access Control Standard", "standard")],
        root=tmp_path,
        host="https://x",
        dry_run=False,
    )

    written = tmp_path / "standards" / "access-control-standard.md"
    assert written.exists()
    text = written.read_text(encoding="utf-8")
    assert "space: SEC" in text
    assert "title: Access Control Standard" in text
    assert "quarterly" in text
    assert [r.action for r in report.results] == [WRITTEN]


def test_a_dry_run_pull_writes_no_files(tmp_path, monkeypatch):
    _patch_confluence(monkeypatch, pages={"Access Control Standard": PLAIN_PAGE})

    report = pull_pages(
        [("SEC", "Access Control Standard", "standard")], root=tmp_path, host="https://x"
    )

    assert list(tmp_path.rglob("*.md")) == []
    assert "--apply" in report.format_report()


def test_pulling_the_same_page_twice_reports_it_unchanged(tmp_path, monkeypatch):
    _patch_confluence(monkeypatch, pages={"Access Control Standard": PLAIN_PAGE})
    targets = [("SEC", "Access Control Standard", "standard")]

    pull_pages(targets, root=tmp_path, host="https://x", dry_run=False)
    report = pull_pages(targets, root=tmp_path, host="https://x", dry_run=False)

    assert [r.action for r in report.results] == [UNCHANGED]


def test_a_page_that_would_not_survive_a_publish_is_refused(tmp_path, monkeypatch):
    """The file would look correct and destroy the macros on first publish."""
    _patch_confluence(monkeypatch, pages={"Runbook": MACRO_PAGE})

    report = pull_pages(
        [("SEC", "Runbook", "procedure")], root=tmp_path, host="https://x", dry_run=False
    )

    assert list(tmp_path.rglob("*.md")) == []
    assert [r.action for r in report.results] == [REFUSED]
    assert "info" in report.refused[0].reason


def test_a_missing_page_is_refused_by_name(tmp_path, monkeypatch):
    _patch_confluence(monkeypatch)

    report = pull_pages(
        [("SEC", "Gone", "standard")], root=tmp_path, host="https://x", dry_run=False
    )

    assert [r.action for r in report.results] == [REFUSED]
    assert "Gone" in report.refused[0].reason


def test_the_tier_decides_where_a_pulled_page_lands(tmp_path):
    assert target_path(tmp_path, tier="policy", slug="ac") == tmp_path / "policies" / "ac.md"
    assert target_path(tmp_path, tier="procedure", slug="ac") == tmp_path / "procedures" / "ac.md"
    assert target_path(tmp_path, tier="", slug="ac") == tmp_path / "ac.md"


def test_a_pulled_page_can_be_published_straight_back(tmp_path, monkeypatch):
    """The round trip has to close, or the repo model does not work."""
    exported = []
    _patch_confluence(monkeypatch, pages={"Access Control Standard": PLAIN_PAGE}, exported=exported)

    pull_pages(
        [("SEC", "Access Control Standard", "standard")],
        root=tmp_path,
        host="https://x",
        dry_run=False,
    )
    report = publish_tree(tmp_path, host="https://x", dry_run=False)

    assert [r.action for r in report.results] == [UPDATED]
    assert exported and exported[0][1] == "Access Control Standard"
