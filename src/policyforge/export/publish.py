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

The guard that matters is macros. A page somebody hand-wrote in Confluence
may use `info`, `expand`, `status` or page-properties macros, and this
project's markdown conversion cannot round-trip them — publishing over such
a page flattens work nobody agreed to lose. Those pages are skipped and
named, rather than published with a warning printed after the damage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

CREATED = "created"
UPDATED = "updated"
SKIPPED = "skipped"


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


def publish_tree(
    root: Path,
    *,
    host: str,
    dry_run: bool = True,
    allow_macros: bool = False,
    only: str = "",
) -> PublishReport:
    """Publish every document in the tree that declares a destination.

    `only` restricts the run to paths containing that substring, which is
    what makes it usable from a CI job that knows which files a merge
    touched rather than republishing the whole set every time.
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
