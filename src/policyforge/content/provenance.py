"""Which model wrote this document, recorded in the document.

`generate` already builds the right stamp — the models that answered, how
many calls, the prompt hashes, the provider and its class, the cost, the
content class — and writes it to `output/.history`, which is gitignored.
That is the wrong place for it in a repo-backed setup, for two reasons.

The first is that the local store duplicates git. A tree under version
control already records what changed and when; what it does not record is
*who wrote it*, and that is the one thing the stamp knows.

The second is the question the stamp exists to answer. When a model is
found to systematically weaken cited requirements — turning "shall" into
"should consider", which `content/deontic.py` exists to catch — the next
question is which documents it touched. In a gitignored directory on one
person's laptop that question is answerable by that person, for as long as
they keep the directory. In frontmatter it is answerable by anyone with a
checkout, with `git log`, and about a document that was published two years
ago.

So the stamp travels in the document, as a `generated_by:` block.

**It does not survive a round trip through Confluence.** A document that was
generated, published, and later pulled back comes home as storage format
converted to markdown, and the frontmatter this wrote is not in the page
body. That is a real limit and it is why absence is never treated as
suspicious: an unstamped document may be hand-written, may predate this, or
may have been pulled. What a stamp asserts is positive only — this model
wrote this text — and nothing is inferred from its absence.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The frontmatter key. One block rather than scattered keys so a reader can
#: see at a glance which part of the frontmatter a person chose and which
#: part a tool wrote.
GENERATED_BY = "generated_by"


def stamp_document(text: str, stamp: dict) -> str:
    """Return `text` with `stamp` recorded under `generated_by`.

    Any frontmatter already present is preserved — this merges a key rather
    than replacing a block, because the synthesis-derived keys a generated
    document may carry (topic, owner, tier) are not this function's to
    discard.

    Written through the same `frontmatter` library `content/tree.py` parses
    with, so what is written is by construction what will be read back.
    """
    import frontmatter
    import mdformat

    parsed = frontmatter.loads(text)
    parsed.metadata[GENERATED_BY] = dict(stamp)
    # `dumps` emits frontmatter followed by the body, and appends no trailing
    # newline; the caller's text kept its own.
    stamped = frontmatter.dumps(parsed) + "\n"

    # Normalised through mdformat so a stamped document passes the same
    # markdown gate everything else here is held to. Two different YAML
    # dumpers are involved — python-frontmatter's and mdformat's — and they
    # disagree about list indentation, so without this every generated
    # document would be reported as badly formatted over two spaces of YAML.
    # The extension set matters: mdformat without `frontmatter` rewrites a
    # leading `---` into a thematic break and destroys the block underneath.
    return mdformat.text(stamped, extensions={"gfm", "frontmatter"})


def read_generated_by(metadata: dict) -> dict:
    """The `generated_by` block, or {} where the document carries none."""
    block = metadata.get(GENERATED_BY)
    return dict(block) if isinstance(block, dict) else {}


@dataclass(frozen=True)
class Attribution:
    """One document and what is known about who wrote it."""

    path: str
    models: tuple[str, ...] = ()
    provider_class: str = ""
    cost_usd: float | None = None

    @property
    def stamped(self) -> bool:
        return bool(self.models)


def attribution(document) -> Attribution:
    """What `document`'s frontmatter says about the model that wrote it."""
    block = read_generated_by(getattr(document, "metadata", {}) or {})
    models = block.get("models") or []
    if isinstance(models, str):
        models = [models]
    cost = block.get("cost_usd")
    return Attribution(
        path=getattr(document, "relative_path", ""),
        models=tuple(str(m) for m in models),
        provider_class=str(block.get("provider_class") or ""),
        cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
    )


def documents_by_model(documents) -> dict[str, list[str]]:
    """Every stamped document, grouped by the model that wrote it.

    This is the question the whole mechanism is for. A model found to be
    weakening requirements produces a list of documents to re-check, and the
    list comes from the repository rather than from anyone's memory.
    """
    grouped: dict[str, list[str]] = {}
    for document in documents:
        found = attribution(document)
        for model in found.models:
            grouped.setdefault(model, []).append(found.path)
    return {model: sorted(paths) for model, paths in sorted(grouped.items())}


def attribution_summary(documents) -> str:
    """A human-readable account of who wrote what in a content tree."""
    found = [attribution(d) for d in documents]
    stamped = [a for a in found if a.stamped]
    if not stamped:
        return (
            f"No document in this tree records the model that wrote it "
            f"({len(found)} document(s) checked). A document is stamped when "
            f"`generate` writes it; one that was hand-written, or pulled back "
            f"from Confluence, carries no stamp and that is not a fault."
        )

    lines = [f"{len(stamped)} of {len(found)} document(s) record how they were written:", ""]
    for model, paths in documents_by_model(documents).items():
        lines.append(f"  {model} — {len(paths)} document(s)")
        lines += [f"      {path}" for path in paths]

    unstamped = len(found) - len(stamped)
    if unstamped:
        lines += [
            "",
            f"  {unstamped} document(s) carry no stamp. That is not a finding: a "
            f"document written by hand, predating this, or pulled back from "
            f"Confluence has none, and nothing is inferred from absence.",
        ]
    return "\n".join(lines)
