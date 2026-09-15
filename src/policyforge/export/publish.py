"""Publishing a content tree to Confluence, driven by the files.

`export-confluence` publishes one document to one page named on the command
line. That is the right shape for a person doing it once and the wrong shape
for a CI job doing it on every merge: the mapping from file to page belongs
in the repository, next to the file, under review — not in a workflow
argument somebody has to keep in step with the tree.

So each document declares its own destination in frontmatter, and this
walks the tree and honours it. A file with no `confluence:` block is not
published at all, which is how a draft stays a draft.

**Dry run is the default**, here as everywhere else that writes to a live
page. The interesting output is the plan: which pages would be created,
which updated, and which skipped and why.

Two guards stand between a merge and a live page:

* **Macros.** A page somebody hand-wrote in Confluence may use `info`,
  `expand`, `status` or page-properties macros, and this project's markdown
  conversion cannot round-trip them — publishing over such a page flattens
  work nobody agreed to lose. Those pages are skipped and named, rather
  than published with a warning printed after the damage.
* **Hand edits.** A publish used to read the live version and increment it,
  so it always won: an edit somebody made on the wiki last week was
  destroyed the next time an unrelated document merged, and nothing said
  so. Now a page is overwritten only when its latest version was written by
  this tool, or is the version a person has already pulled into the
  repository. Anything else has *moved*, and a moved page is reported on its
  own and fails the run — so the pull-and-review loop is triggered rather
  than bypassed. `--force` is there for the decision to overwrite anyway.

The obvious design — store the page version in frontmatter at publish time
and compare — does not work from CI. A publish job runs on a checkout and
cannot commit the new version back, so the recorded number would fall one
behind after every publish and the next one would refuse forever. The
version message this tool stamps on its own writes needs no write-back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

CREATED = "created"
UPDATED = "updated"
SKIPPED = "skipped"
#: Changed on the wiki since this tool last wrote it, by somebody the
#: repository has not heard from. Kept apart from SKIPPED because it asks
#: for a different action: not "read the reason", but "pull and review".
MOVED = "moved"


@dataclass
class PublishResult:
    """What happened, or would happen, to one document."""

    path: str
    space: str
    title: str
    action: str
    reason: str = ""
    url: str = ""


@dataclass
class PublishReport:
    results: list[PublishResult] = field(default_factory=list)
    dry_run: bool = True
    #: Documents that declared no destination. Counted rather than listed:
    #: in a tree mid-migration this is most of them, and naming each one
    #: would bury the pages that did publish.
    undeclared: int = 0

    def _of(self, action: str) -> list[PublishResult]:
        return [r for r in self.results if r.action == action]

    @property
    def skipped(self) -> list[PublishResult]:
        return self._of(SKIPPED)

    @property
    def moved(self) -> list[PublishResult]:
        return self._of(MOVED)

    @property
    def published(self) -> list[PublishResult]:
        return self._of(CREATED) + self._of(UPDATED)

    def format_report(self) -> str:
        verb = "Would publish" if self.dry_run else "Published"
        lines = [
            f"{verb} {len(self.published)} page(s): "
            f"{len(self._of(CREATED))} new, {len(self._of(UPDATED))} updated"
        ]
        for result in self.published:
            mark = "+" if result.action == CREATED else "~"
            lines.append(f"  {mark} {result.path} -> {result.space}/{result.title}")
            if result.url:
                lines.append(f"      {result.url}")

        if self.moved:
            lines += [
                "",
                f"Changed on the wiki since this tool last published them ({len(self.moved)}) "
                "— not overwritten. Pull them, review the change, then publish:",
            ]
            lines += [f"  {r.path}: {r.reason}" for r in self.moved]

        if self.skipped:
            lines += ["", f"Skipped {len(self.skipped)}:"]
            lines += [f"  {r.path}: {r.reason}" for r in self.skipped]

        if self.undeclared:
            lines += [
                "",
                f"{self.undeclared} document(s) declare no `confluence:` block and were "
                "left alone.",
            ]

        if self.dry_run and self.published:
            lines += ["", "Nothing was written. Pass --apply to publish."]
        return "\n".join(lines)


def moved_since_last_publish(doc, live) -> str:
    """Why the live page may hold an edit the repository has not seen, or "".

    Safe to overwrite in two cases. The latest version carries this tool's
    stamp, so nothing has touched the page since it was last published from
    here. Or its version is the one `pull` recorded in the document's
    frontmatter, so a person has already brought that edit into the
    repository and reviewed it as a diff.
    """
    from policyforge.export.confluence_exporter import PUBLISH_MARKER

    if PUBLISH_MARKER in (live.version_message or ""):
        return ""
    recorded = doc.confluence.get("version")
    try:
        recorded = int(recorded) if recorded is not None else None
    except (TypeError, ValueError):
        recorded = None
    if recorded is not None and recorded == live.version:
        return ""

    known = (
        f"the repository last pulled version {recorded}"
        if recorded is not None
        else "the repository has no pulled version on record"
    )
    return (
        f"the live page is at version {live.version}, last written by someone other "
        f"than this tool, and {known}"
    )


def publish_tree(
    root: Path,
    *,
    host: str,
    dry_run: bool = True,
    allow_macros: bool = False,
    only: str = "",
    force: bool = False,
) -> PublishReport:
    """Publish every document in the tree that declares a destination.

    `only` restricts the run to paths containing that substring, which is
    what makes it usable from a CI job that knows which files a merge
    touched rather than republishing the whole set every time. `force`
    overwrites pages that have moved since this tool last wrote them.
    """
    from policyforge.content.tree import load_content_tree
    from policyforge.edit.apply import detect_unsupported_macros
    from policyforge.export.confluence_exporter import export_to_confluence
    from policyforge.export.confluence_importer import fetch_confluence_page

    documents, problems = load_content_tree(root)
    report = PublishReport(dry_run=dry_run)
    report.results.extend(
        PublishResult(path=path, space="", title="", action=SKIPPED, reason=reason)
        for path, reason in problems
    )

    for doc in documents:
        if only and only not in doc.relative_path:
            continue
        if not doc.space:
            report.undeclared += 1
            continue

        try:
            live = fetch_confluence_page(space=doc.space, title=doc.page_title, host=host)
        except LookupError:
            live = None

        if live is not None and not allow_macros:
            macros = detect_unsupported_macros(live.storage_body)
            if macros:
                report.results.append(
                    PublishResult(
                        path=doc.relative_path,
                        space=doc.space,
                        title=doc.page_title,
                        action=SKIPPED,
                        reason=(
                            f"the live page uses macros this tool cannot round-trip "
                            f"({', '.join(macros)}); publishing would flatten them"
                        ),
                    )
                )
                continue

        if live is not None and not force:
            moved = moved_since_last_publish(doc, live)
            if moved:
                report.results.append(
                    PublishResult(
                        path=doc.relative_path,
                        space=doc.space,
                        title=doc.page_title,
                        action=MOVED,
                        reason=moved,
                        url=live.webui_url,
                    )
                )
                continue

        action = UPDATED if live is not None else CREATED
        url = ""
        if not dry_run:
            url = export_to_confluence(doc.body, space=doc.space, title=doc.page_title, host=host)

        report.results.append(
            PublishResult(
                path=doc.relative_path,
                space=doc.space,
                title=doc.page_title,
                action=action,
                url=url or (live.webui_url if live else ""),
            )
        )

    return report
