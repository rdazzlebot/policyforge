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

The loop is `publisher.pull_documents`, the same for every kind of store;
this module is its Confluence entry point and owns where a pulled page
lands in the tree.
"""

from __future__ import annotations

from pathlib import Path

from policyforge.content.tree import TIER_DIRS
from policyforge.export.publisher import (  # noqa: F401 — re-exported for callers
    REFUSED,
    UNCHANGED,
    WRITTEN,
    ConfluencePublisher,
    PullReport,
    PullResult,
    pull_documents,
)

#: Where a pulled document lands when nothing says otherwise. Tier-first,
#: matching what `generate` writes, so a pulled page and a generated one
#: sit beside each other rather than in two parallel hierarchies.
_TIER_DIR = {tier: directory for directory, tier in TIER_DIRS.items()}


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
    return pull_documents(
        ConfluencePublisher(host=host),
        pages,
        root=root,
        target_path=target_path,
        dry_run=dry_run,
        allow_unsupported=allow_macros,
    )


def pages_from_topics(topics) -> list[tuple[str, str, str]]:
    """Every page the topic registry declares, as pull targets."""
    targets: list[tuple[str, str, str]] = []
    for topic in topics:
        space = (topic.confluence or {}).get("space", "")
        if not space:
            continue
        targets.extend((space, title, tier) for tier, title in topic.confluence_pages())
    return targets
