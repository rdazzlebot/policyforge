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

from .deontic import NONE, weakened_citations
from .tags import source_tags
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
    #: Which model wrote which document, where the document says so. Not a
    #: finding in either direction: a stamp is not a problem, and its
    #: absence is not either — a hand-written document has none, and so does
    #: one pulled back from Confluence, which cannot carry frontmatter
    #: through storage format. Reported because "which documents did that
    #: model touch" is the question asked after a model is found to be
    #: weakening requirements, and it should be answerable from a checkout.
    attribution: str = ""

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
        if self.attribution:
            lines += ["", self.attribution]
        return "\n".join(lines)


def _check_page_claims(documents: list[ContentDocument]) -> list[Finding]:
    """No two files may publish to the same page.

    Left alone this is silent data loss: both documents publish, the second
    overwrites the first, and the repo still contains two files that each
    look like the source of truth for that page. Whichever one happened to
    run second wins, which is not a rule anybody chose.
    """
    claims: dict[tuple[str, str, str], str] = {}
    findings: list[Finding] = []
    for doc in documents:
        # Keyed by kind as well as by place and title, because a page is only
        # the same page within one store: `SEC/Access Review` in Confluence
        # and `Access Review` on a wiki are two destinations, and a tree
        # publishing to both would otherwise report a collision that is not
        # one. Within a kind the rule is unchanged.
        for kind, target in (doc.targets or {}).items():
            if not isinstance(target, dict):
                continue
            where = str(target.get("space") or target.get("repository") or "")
            title = str(target.get("title") or doc.title or "")
            if not title:
                continue
            # A wiki block may name no repository, taking it from config; two
            # such files still collide with each other, so they key on the
            # empty location together rather than being skipped.
            if kind == "confluence" and not where:
                continue
            key = (kind, where.lower(), title.lower())
            first = claims.get(key)
            if first is not None:
                place = f"{where}/{title!r}" if where else f"{title!r}"
                findings.append(
                    Finding(
                        doc.relative_path,
                        f"publishes to {place}, which {first} already claims — one of "
                        "them would silently overwrite the other",
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


def _check_target_alias(documents: list[ContentDocument]) -> list[Finding]:
    """`confluence:` at the top level and `targets.confluence` must agree.

    The top-level block is the older spelling and is read as the alias of
    the newer one. A file carrying both with different contents would
    publish to whichever the reader happened to prefer, which is a page
    nobody chose; reported rather than resolved.
    """
    findings: list[Finding] = []
    for doc in documents:
        legacy = doc.metadata.get("confluence")
        general = doc.metadata.get("targets")
        if not isinstance(legacy, dict) or not isinstance(general, dict):
            continue
        inner = general.get("confluence")
        if isinstance(inner, dict) and inner != legacy:
            findings.append(
                Finding(
                    doc.relative_path,
                    "declares `confluence:` and `targets.confluence:` with different "
                    "contents — keep one, or make them agree",
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
    from policyforge.content.tags import source_tags

    if not synthesis_dir.exists():
        return []

    findings: list[Finding] = []
    for doc in documents:
        source = synthesis_dir / f"{doc.slug}.md"
        if not source.exists():
            continue
        expected = set(source_tags(source.read_text(encoding="utf-8")))
        present = set(source_tags(doc.body))
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


#: Tiers whose sentences are supposed to bind. A Policy states principles
#: and may legitimately say "should"; a Standard is what an assessor asks
#: for evidence against, and a Procedure is a set of steps somebody
#: follows.
_BINDING_TIERS = frozenset({"standard", "procedure"})


def _check_uncited(documents: list[ContentDocument]) -> list[Finding]:
    """A Standard or Procedure that cites no framework requirement at all.

    The tag is the whole traceability story: it is how a document says
    which control it answers for, and how `satisfies`, `drift` and the
    edit path find it. A Standard with no tag anywhere is not a document
    with weak traceability, it is a document with none — and the two ways
    that happens are both worth seeing. Either the generation was cut off
    part-way, or the citations were written and then lost in an edit.

    **Tier-scoped, and the scoping is the whole check.** A Policy states
    what the organization intends and cites nothing by design: in the
    bundled 20-topic starter set all nineteen Policies carry no tag, so an
    unscoped version of this rule would report nineteen documents that are
    exactly as they should be, and a check that is wrong nineteen times out
    of twenty-one gets switched off in a week. Scoped to Standards and
    Procedures it reports two documents in that same set, and both are real:
    one Standard truncated mid-sentence at 1,066 bytes, and one full-length
    Procedure whose tags are simply absent. Found by policyforge-b5 while
    reconciling the citation measurement.

    A warning rather than an error, for the reason the tier and owner rules
    are warnings: a hand-written Standard that has not been mapped to a
    framework yet is a normal thing to have in a tree mid-migration, and a
    gate that cannot be satisfied gets turned off rather than fixed.
    """
    findings: list[Finding] = []
    for doc in documents:
        if doc.tier not in _BINDING_TIERS or source_tags(doc.body):
            continue
        findings.append(
            Finding(
                doc.relative_path,
                f"is a {doc.tier} that cites no framework requirement, so nothing "
                "traces it back to a control — check whether it was cut short or "
                "whether its citations were dropped",
                WARNING,
            )
        )
    return findings


def _check_requirement_strength(documents: list[ContentDocument]) -> list[Finding]:
    """A cited requirement that does not bind.

    Warnings rather than errors: the source controls are written in
    obligation language, so rendering one as "teams should consider" or as
    a bare statement of fact promises less than the framework the citation
    claims to satisfy — but whether that is wrong is a judgement about the
    document, not a breach of a rule, and blocking a publish over it would
    be the wrong trade. See `content/deontic.py` for why only *cited*
    sentences are reported.
    """
    findings: list[Finding] = []
    for doc in documents:
        if doc.tier not in _BINDING_TIERS:
            continue
        for statement in weakened_citations(doc.body):
            how = (
                f"as a {statement.modality}"
                if statement.modality != NONE
                else "as a statement of fact, with no obligation"
            )
            findings.append(
                Finding(
                    doc.relative_path,
                    f"line {statement.line}: states a cited requirement {how} "
                    f'— "{statement.text[:70]}"',
                    WARNING,
                )
            )
    return findings


def check_tree(root: Path, *, synthesis_dir: Path | None = None) -> CheckReport:
    """Run every local check over a content tree."""
    documents, problems = load_content_tree(root)
    report = CheckReport(documents=len(documents))

    report.findings.extend(Finding(path, reason) for path, reason in problems)
    report.findings.extend(_check_target_alias(documents))
    report.findings.extend(_check_page_claims(documents))
    report.findings.extend(_check_references(documents, root))
    report.findings.extend(_check_publishable(documents))
    report.findings.extend(_check_uncited(documents))
    report.findings.extend(_check_requirement_strength(documents))
    if synthesis_dir is not None:
        report.findings.extend(_check_citations(documents, synthesis_dir))

    from .provenance import attribution_summary

    report.attribution = attribution_summary(documents)
    return report
