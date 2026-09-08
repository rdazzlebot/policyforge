"""Bringing live pages down into the content tree as markdown.

The inverse of publishing, and the piece that makes the repo model
survivable rather than aspirational. Somebody will always edit the wiki
directly — that is what a wiki is for — and without a way back, every such
edit is either lost on the next publish or quietly makes the repo wrong.
Pulling turns it into a diff on a branch: reviewable, attributable, and
merged like anything else.

Each pulled file is written with the frontmatter binding it back to the page
it came from, so the round trip closes. A repo path and a page title are
different strings, and a pull that did not record the correspondence would
publish to the wrong place, or nowhere.

**Pages this tool cannot round-trip are refused, not degraded.** A page
using `info`, `expand`, `status` or page-properties macros converts to
readable markdown and would be flattened on the way back — so pulling it
would produce a file that looks correct and destroys those macros the first
time it is published. Refusing names the page and the macros and leaves it
alone, which is the only outcome that does not eventually lose somebody's
work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from policyforge.content.tree import TIER_DIRS, render_document

WRITTEN = "written"
UNCHANGED = "unchanged"
REFUSED = "refused"

#: Where a pulled document lands when nothing says otherwise. Tier-first,
#: matching what `generate` writes, so a pulled page and a generated one
#: sit beside each other rather than in two parallel hierarchies.
_TIER_DIR = {tier: directory for directory, tier in TIER_DIRS.items()}


@dataclass
class PullResult:
    title: str
    path: str
    action: str
    reason: str = ""


@dataclass
class PullReport:
    results: list[PullResult] = field(default_factory=list)
    dry_run: bool = True

    def _of(self, action: str) -> list[PullResult]:
        return [r for r in self.results if r.action == action]

    @property
    def refused(self) -> list[PullResult]:
        return self._of(REFUSED)

    def format_report(self) -> str:
        written = self._of(WRITTEN)
        unchanged = self._of(UNCHANGED)
        verb = "Would write" if self.dry_run else "Wrote"
        lines = [f"{verb} {len(written)} file(s); {len(unchanged)} already matched the tree."]
        lines += [f"  {r.title} -> {r.path}" for r in written]

        if self.refused:
            lines += ["", f"Refused {len(self.refused)}:"]
            lines += [f"  {r.title}: {r.reason}" for r in self.refused]
            lines += [
                "",
                "These pages read fine but would be damaged by a publish, so they are "
                "not brought into the tree. Rewrite them in Confluence without those "
                "macros, or keep them wiki-only.",
            ]

        if self.dry_run and written:
            lines += ["", "Nothing was written. Pass --apply to write these files."]
        return "\n".join(lines)


def target_path(root: Path, *, tier: str, slug: str) -> Path:
    """Where a pulled page belongs in the tree."""
    directory = _TIER_DIR.get(tier)
    return (root / directory / f"{slug}.md") if directory else (root / f"{slug}.md")


def pull_pages(
    pages: list[tuple[str, str, str]],
    *,
    root: Path,
    host: str,
    dry_run: bool = True,
    allow_macros: bool = False,
) -> PullReport:
    """Fetch `(space, title, tier)` triples into the tree.

    Takes an explicit list rather than discovering pages itself, so the
    caller decides what is in scope — a topic's declared set, a whole space,
    or one page somebody hand-edited.
    """
    from policyforge.edit.apply import detect_unsupported_macros
    from policyforge.export.confluence_importer import (
        confluence_to_markdown,
        extract_user_ids,
        fetch_confluence_page,
    )
    from policyforge.export.confluence_search import fetch_user_names
    from policyforge.zardoz.corpus import slugify

    report = PullReport(dry_run=dry_run)

    for space, title, tier in pages:
        try:
            page = fetch_confluence_page(space=space, title=title, host=host)
        except LookupError as exc:
            report.results.append(PullResult(title=title, path="", action=REFUSED, reason=str(exc)))
            continue

        macros = detect_unsupported_macros(page.storage_body)
        if macros and not allow_macros:
            report.results.append(
                PullResult(
                    title=title,
                    path="",
                    action=REFUSED,
                    reason=f"uses macros that would not survive a publish ({', '.join(macros)})",
                )
            )
            continue

        names = fetch_user_names(extract_user_ids(page.storage_body), host=host)
        body = confluence_to_markdown(page.storage_body, user_names=names)
        slug = slugify(title) or slugify(page.id)
        destination = target_path(root, tier=tier, slug=slug)

        rendered = render_document(
            {
                "title": title,
                "tier": tier,
                "confluence": {"space": space, "title": title, "page_id": page.id},
            },
            body,
        )
        relative = destination.relative_to(root).as_posix()

        if destination.exists() and destination.read_text(encoding="utf-8") == rendered:
            report.results.append(PullResult(title=title, path=relative, action=UNCHANGED))
            continue

        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(rendered, encoding="utf-8")
        report.results.append(PullResult(title=title, path=relative, action=WRITTEN))

    return report


def pages_from_topics(topics) -> list[tuple[str, str, str]]:
    """Every page the topic registry declares, as pull targets."""
    targets: list[tuple[str, str, str]] = []
    for topic in topics:
        space = (topic.confluence or {}).get("space", "")
        if not space:
            continue
        targets.extend((space, title, tier) for tier, title in topic.confluence_pages())
    return targets
