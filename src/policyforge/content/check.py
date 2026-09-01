"""The gate a pull request has to pass before anything reaches the wiki.

Everything here is local and offline. That is the point: these are the
mistakes worth catching *before* a publish, and a check that needed
credentials could not run on a fork's pull request, which is exactly where
you want it running.

The failures it looks for are the ones that are invisible in review. A
reviewer reading a diff sees the prose change and not that two files now
claim the same Confluence page, that a link points at a file somebody
renamed, or that a rewrite dropped the `[NIST AC-2 | HIPAA 164.308(a)(3)(i)]`
tag that was the document's only traceability back to the control it
implements. Each of those survives review comfortably and then fails at
publish time, or worse, does not fail at all.

Errors and warnings are separated because they need different answers. Two
documents pointing at one page will publish one over the other and lose
work, so it stops the build. A document with no declared owner is a gap
worth seeing on every run and not worth blocking a merge over — a repo
mid-migration is full of them, and a gate that cannot be satisfied gets
switched off.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .tree import ContentDocument, load_content_tree

ERROR = "error"
WARNING = "warning"


@dataclass
class Finding:
    """One problem, and where to go and look at it."""

    path: str
    message: str
    severity: str = ERROR

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


@dataclass
class CheckReport:
    documents: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def format_report(self) -> str:
        lines = [f"Checked {self.documents} document(s)."]
        if self.errors:
            lines += ["", f"{len(self.errors)} error(s):"]
            lines += [f"  {finding}" for finding in self.errors]
        if self.warnings:
            lines += ["", f"{len(self.warnings)} warning(s):"]
            lines += [f"  {finding}" for finding in self.warnings]
        if self.ok and not self.warnings:
            lines.append("Nothing to report.")
        elif self.ok:
            lines += ["", "No errors — safe to publish."]
        return "\n".join(lines)


def _check_page_claims(documents: list[ContentDocument]) -> list[Finding]:
    """No two files may publish to the same page.

    Left alone this is silent data loss: both documents publish, the second
    overwrites the first, and the repo still contains two files that each
    look like the source of truth for that page. Whichever one happened to
    run second wins, which is not a rule anybody chose.
    """
    claims: dict[tuple[str, str], str] = {}
    findings: list[Finding] = []
    for doc in documents:
        if not doc.space:
            continue
        key = (doc.space.lower(), doc.page_title.lower())
        first = claims.get(key)
        if first is not None:
            findings.append(
                Finding(
                    doc.relative_path,
                    f"publishes to {doc.space}/{doc.page_title!r}, which {first} already "
                    "claims — one of them would silently overwrite the other",
                )
            )
            continue
        claims[key] = doc.relative_path
    return findings


def _check_references(documents: list[ContentDocument], root: Path) -> list[Finding]:
    """Every local link must point at a file that exists.

    A renamed document leaves working prose behind a broken link, and in a
    governance set the links are load-bearing: a Standard pointing at its
    Procedure is how a reader gets from the requirement to the steps.
    """
    findings: list[Finding] = []
    for doc in documents:
        for reference in doc.references:
            # Wikilinks name a title rather than a path; resolve those
            # against the set of document titles instead of the filesystem.
            if reference.endswith(".md"):
                target = (doc.path.parent / reference).resolve()
                if not target.exists():
                    findings.append(
                        Finding(doc.relative_path, f"links to {reference!r}, which does not exist")
                    )
            elif not any(
                other.title.lower() == reference.lower() or other.slug.lower() == reference.lower()
                for other in documents
            ):
                findings.append(
                    Finding(
                        doc.relative_path,
                        f"links to [[{reference}]], which matches no document",
                        WARNING,
                    )
                )
    return findings


def _check_publishable(documents: list[ContentDocument]) -> list[Finding]:
    findings: list[Finding] = []
    for doc in documents:
        block = doc.confluence
        if block and not doc.space:
            findings.append(
                Finding(
                    doc.relative_path,
                    "declares a `confluence:` block with no `space:`, so it cannot be "
                    "published anywhere",
                )
            )
        if not doc.tier:
            findings.append(
                Finding(
                    doc.relative_path,
                    "has no tier — put it under policies/, standards/ or procedures/, "
                    "or set `tier:` in its frontmatter",
                    WARNING,
                )
            )
        if not doc.owner:
            findings.append(
                Finding(
                    doc.relative_path,
                    "has no owner, so an answer drawn from it cannot say who is accountable",
                    WARNING,
                )
            )
    return findings


def _check_citations(documents: list[ContentDocument], synthesis_dir: Path) -> list[Finding]:
    """Framework tags in the synthesis must survive into the document.

    The generated document is prose written from a synthesis; the synthesis
    is the requirement list with its provenance attached. A tag that exists
    in one and not the other means the traceability an assessor needs was
    dropped somewhere between them, which is a compliance defect rather than
    a formatting one — and it is invisible in a diff of the prose.
    """
    from policyforge.edit.apply import _SOURCE_TAG_RE

    if not synthesis_dir.exists():
        return []

    findings: list[Finding] = []
    for doc in documents:
        source = synthesis_dir / f"{doc.slug}.md"
        if not source.exists():
            continue
        expected = set(_SOURCE_TAG_RE.findall(source.read_text(encoding="utf-8")))
        present = set(_SOURCE_TAG_RE.findall(doc.body))
        missing = sorted(expected - present)
        if missing:
            shown = ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else "")
            findings.append(
                Finding(
                    doc.relative_path,
                    f"is missing {len(missing)} citation(s) its synthesis carries: {shown}",
                    WARNING,
                )
            )
    return findings


def check_tree(root: Path, *, synthesis_dir: Path | None = None) -> CheckReport:
    """Run every local check over a content tree."""
    documents, problems = load_content_tree(root)
    report = CheckReport(documents=len(documents))

    report.findings.extend(Finding(path, reason) for path, reason in problems)
    report.findings.extend(_check_page_claims(documents))
    report.findings.extend(_check_references(documents, root))
    report.findings.extend(_check_publishable(documents))
    if synthesis_dir is not None:
        report.findings.extend(_check_citations(documents, synthesis_dir))

    return report
