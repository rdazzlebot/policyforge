"""What changed on the wiki since this tool last published it.

`publish` already knows: it refuses to overwrite a page whose latest version
this tool did not write, and reports it as moved. But that answer arrives as
the wreckage of a publish somebody was trying to do, which is the wrong time
to learn it and the wrong person to tell. "What has changed on the wiki
since we last published?" is the question a policy owner asks *before* a
review cycle, and answering it used to mean pulling everything and reading
the diff.

So it is a query. Same two rules `publish` uses — a page this tool last
wrote carries its stamp, and a page whose version `pull` recorded has been
seen — and the same content comparison, so a page that says exactly what the
repository says is in sync whoever touched it last.

Writes nothing, and needs no `--apply` to be safe: it reads pages and prints
the `pull` command that would reconcile each one. The reconcile command is
printed rather than run because bringing an edit into the repository is a
diff somebody reviews, not a step a report takes on their behalf.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: The live page holds an edit the repository has not seen.
MOVED = "moved"
#: The live page says what the repository says, or this tool wrote it last.
IN_SYNC = "in-sync"
#: The document declares a page that does not exist yet.
ABSENT = "absent"


@dataclass(frozen=True)
class DriftResult:
    """One document, and where its page stands."""

    path: str
    space: str
    title: str
    tier: str
    state: str
    reason: str = ""
    url: str = ""

    @property
    def reconcile(self) -> str:
        """The command that brings this page's edit into the repository."""
        return (
            f'policyforge pull --space {self.space} --title "{self.title}" '
            f"--tier {self.tier or 'standard'} --apply"
        )


@dataclass
class DriftReport:
    results: list[DriftResult] = field(default_factory=list)
    #: Documents declaring no destination — most of a tree mid-migration.
    undeclared: int = 0

    def _of(self, state: str) -> list[DriftResult]:
        return [r for r in self.results if r.state == state]

    @property
    def moved(self) -> list[DriftResult]:
        return self._of(MOVED)

    @property
    def in_sync(self) -> list[DriftResult]:
        return self._of(IN_SYNC)

    @property
    def absent(self) -> list[DriftResult]:
        return self._of(ABSENT)

    def format_report(self) -> str:
        lines = [
            f"{len(self.moved)} page(s) changed on the wiki since this tool last "
            f"published them; {len(self.in_sync)} in sync."
        ]
        for result in self.moved:
            lines += [
                "",
                f"  ~ {result.space}/{result.title}",
                f"      {result.reason}",
                f"      repo: {result.path}",
                f"      reconcile: {result.reconcile}",
            ]
            if result.url:
                lines.append(f"      {result.url}")

        if self.absent:
            lines += ["", f"Declared but not published yet ({len(self.absent)}):"]
            lines += [f"  {r.path} -> {r.space}/{r.title}" for r in self.absent]

        if self.undeclared:
            lines += [
                "",
                f"{self.undeclared} document(s) declare no `confluence:` block and were "
                "not looked up.",
            ]

        if not self.moved:
            lines += ["", "Nothing to reconcile."]
        return "\n".join(lines)


def wiki_drift(root: Path, *, host: str, only: str = "") -> DriftReport:
    """Where every published page stands against the tree that owns it.

    `only` narrows the run to paths containing that substring, for the same
    reason `publish` has it: a scheduled job that knows which documents a
    team owns should not read the whole space.
    """
    from policyforge.content.tree import load_content_tree
    from policyforge.export.confluence_importer import fetch_confluence_page
    from policyforge.export.publish import moved_since_last_publish, unchanged_on_the_wiki

    documents, _ = load_content_tree(root)
    report = DriftReport()

    for doc in documents:
        if only and only not in doc.relative_path:
            continue
        if not doc.space:
            report.undeclared += 1
            continue

        try:
            live = fetch_confluence_page(space=doc.space, title=doc.page_title, host=host)
        except LookupError:
            report.results.append(
                DriftResult(
                    path=doc.relative_path,
                    space=doc.space,
                    title=doc.page_title,
                    tier=doc.tier,
                    state=ABSENT,
                )
            )
            continue

        reason = moved_since_last_publish(doc, live)
        if reason and unchanged_on_the_wiki(doc, live):
            # The page says what the repository says. Whoever wrote its last
            # version, there is nothing here to bring back.
            reason = ""
        report.results.append(
            DriftResult(
                path=doc.relative_path,
                space=doc.space,
                title=doc.page_title,
                tier=doc.tier,
                state=MOVED if reason else IN_SYNC,
                reason=reason,
                url=live.webui_url,
            )
        )

    return report
