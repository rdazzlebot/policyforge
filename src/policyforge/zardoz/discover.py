"""Proposing a topic registry from a space nobody has catalogued.

The registry is the spine of everything downstream — coverage, synthesis,
ownership, `edit-topic`, the trusted half of the corpus — and writing one by
hand for an existing wiki means reading sixty pages and deciding which
belong together. That is a tedious afternoon, and it is the barrier between
"we have a Confluence space" and any of this being useful.

Most of the grouping is already written down, just not as data. A governance
space names its pages by convention (*Access Control Policy*, *Access
Control Standard*), nests them under a parent, labels them, and cites the
same control family throughout a related set. Those signals are exact, they
are free, and they group the great majority of a real space without a model
being involved at all.

The LLM is used only for the residue — the pages the conventions did not
reach. That ordering matters for cost and for trust: a proposal you can
check is one where most rows have a reason you can point at, and "these two
pages share a title stem and cite AC-2" is a better reason than "a model
thought so".

**Ownership is never guessed.** Every proposed topic gets `[UNASSIGNED]`.
Nothing in a document reliably says which team is accountable for it —
authorship is not ownership, and the last person to edit a page is usually
neither — and a wrong owner in a compliance artifact is worse than a blank
one, because a blank one gets filled in and a wrong one gets believed.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .retrieve import extract_control_ids

#: Written into every proposed topic. Deliberately conspicuous: it has to
#: survive a skim of the file and stop anyone publishing from it unedited.
UNASSIGNED = "[UNASSIGNED]"

#: Tier words stripped from a page title to find the subject underneath, so
#: that "Access Control Policy" and "Access Control Standard" land together.
_TIER_WORDS = {
    "policy": "policy",
    "policies": "policy",
    "standard": "standard",
    "standards": "standard",
    "procedure": "procedure",
    "procedures": "procedure",
    "sop": "procedure",
    "runbook": "procedure",
    "guideline": "standard",
    "guidelines": "standard",
}

#: Words that carry no subject and would otherwise become the topic name.
_NOISE_WORDS = """
    the a an and or of for to in on at is are our your their this that
    v1 v2 draft final wip copy new old
    """
_NOISE = frozenset(_NOISE_WORDS.split())

_CONTROL_FAMILY_RE = re.compile(r"^([A-Z]{2})-(\d+)")
_WORD_RE = re.compile(r"[A-Za-z0-9&/']+")


@dataclass
class ProposedTopic:
    """One candidate topic, with the evidence that produced it."""

    name: str
    pages: list[tuple[str, str]] = field(default_factory=list)
    nist_controls: list[str] = field(default_factory=list)
    space: str = ""
    #: Why these pages were grouped, in a form a reviewer can check.
    evidence: str = ""

    @property
    def owner(self) -> str:
        return UNASSIGNED

    def as_yaml_block(self) -> dict:
        block = {
            "name": self.name,
            "owner": UNASSIGNED,
            "nist_controls": self.nist_controls,
        }
        if self.pages:
            block["confluence"] = {
                "space": self.space,
                "pages": dict(self.pages),
            }
        return block


@dataclass
class DiscoveryReport:
    topics: list[ProposedTopic] = field(default_factory=list)
    #: Pages no signal could place. Listed rather than forced into a topic:
    #: a wrong grouping is harder to spot than an absent one.
    unplaced: list[str] = field(default_factory=list)
    pages_seen: int = 0

    def format_report(self) -> str:
        lines = [f"Proposed {len(self.topics)} topic(s) from {self.pages_seen} page(s):", ""]
        width = max((len(t.name) for t in self.topics), default=0)
        for topic in self.topics:
            tiers = ", ".join(tier for tier, _ in topic.pages) or "no tier"
            anchors = ", ".join(topic.nist_controls[:4]) or "no citations found"
            lines.append(f"  {topic.name.ljust(width)}  {UNASSIGNED}  [{tiers}]  {anchors}")
            if topic.evidence:
                lines.append(f"  {' ' * width}  ({topic.evidence})")

        if self.unplaced:
            lines += ["", f"{len(self.unplaced)} page(s) no convention placed:"]
            lines += [f"  {title}" for title in self.unplaced[:20]]
            if len(self.unplaced) > 20:
                lines.append(f"  ... and {len(self.unplaced) - 20} more")

        lines += [
            "",
            f"Every owner is {UNASSIGNED}. Nothing in a page reliably says which team "
            "is accountable for it, and a wrong owner in a compliance artifact is worse "
            "than a blank one — a blank one gets filled in.",
        ]
        return "\n".join(lines)


def split_title(title: str) -> tuple[str, str]:
    """Split a page title into `(subject, tier)`.

    "Access Control Standard" -> ("Access Control", "standard"). A title with
    no tier word yields an empty tier, which is what marks it as a page the
    naming convention did not reach.
    """
    words = _WORD_RE.findall(title)
    if not words:
        return title.strip(), ""

    tier = ""
    kept: list[str] = []
    for word in words:
        mapped = _TIER_WORDS.get(word.lower())
        if mapped and not tier:
            tier = mapped
            continue
        kept.append(word)

    subject = " ".join(w for w in kept if w.lower() not in _NOISE).strip()
    return (subject or title.strip()), tier


def _anchor_controls(bodies: list[str]) -> list[str]:
    """The control IDs a group of pages cites, reduced to base controls.

    Enhancements collapse into their parent because the registry anchors
    controls and inherits enhancements — the same rule `coverage.py` uses —
    so proposing AC-2(1) alongside AC-2 would be noise. Ordered by how often
    they appear, so the anchors a reviewer sees first are the ones the pages
    are actually about.
    """
    counts: Counter = Counter()
    for body in bodies:
        for identifier in extract_control_ids(body):
            match = _CONTROL_FAMILY_RE.match(identifier)
            if match:
                counts[f"{match.group(1)}-{match.group(2)}"] += 1
    return [control for control, _ in counts.most_common()]


def group_by_convention(pages) -> tuple[list[ProposedTopic], list]:
    """Group pages by the naming convention their titles already follow.

    Returns `(topics, leftovers)`. A subject with a tiered page is a topic; a
    page whose title carries no tier word is left for the caller to place
    another way, because "Laptop Encryption" alone is as likely to be a
    runbook somebody filed here as a governance document.
    """
    by_subject: dict[str, list] = {}
    leftovers = []
    for page in pages:
        subject, tier = split_title(page.title)
        if not tier:
            leftovers.append(page)
            continue
        by_subject.setdefault(subject, []).append((tier, page))

    topics = []
    for subject, entries in sorted(by_subject.items()):
        tiers = [(tier, page.title) for tier, page in entries]
        bodies = [page.storage_body for _, page in entries]
        topics.append(
            ProposedTopic(
                name=subject,
                pages=tiers,
                nist_controls=_anchor_controls(bodies),
                evidence=f"{len(entries)} page(s) sharing the title stem {subject!r}",
            )
        )
    return topics, leftovers


CLUSTER_SYSTEM_PROMPT = """You group Confluence page titles into candidate \
information-security topics.

A topic is a coherent operational process that one team could own end to end
— access review, backup and restore, vendor risk. It is not a control
family, and it is not one document.

Return one topic per line, in exactly this format and nothing else:

Topic Name: Page Title One | Page Title Two

Rules:
1. Use only the titles given. Never invent a page, and never split or
   reword a title.
2. Every title appears at most once, under one topic.
3. Leave a title out entirely if it does not belong with anything. A page
   that is genuinely on its own is a normal outcome and better than a topic
   invented to hold it.
4. Name the topic after the process, not the document. "Access Review", not
   "Access Review Standard".
5. Prefer fewer, broader topics. Around 25 is the ceiling for a whole
   organization, so a space of forty pages should not yield forty topics."""


def _parse_clusters(text: str, titles: set[str]) -> list[tuple[str, list[str]]]:
    """Read the model's groupings back, keeping only real page titles.

    A title the model invented or reworded is dropped rather than trusted:
    the whole file is about to be turned into page lookups, and a title that
    does not exist becomes a skip nobody can explain later.
    """
    lookup = {title.lower(): title for title in titles}
    clusters: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, _, rest = line.partition(":")
        name = name.strip().lstrip("-*0123456789. ").strip()
        members = [
            lookup[part.strip().lower()]
            for part in rest.split("|")
            if part.strip().lower() in lookup
        ]
        if name and members:
            clusters.append((name, members))
    return clusters


def cluster_leftovers(pages, provider) -> tuple[list[ProposedTopic], list]:
    """Ask a model to group the pages no convention reached."""
    if not pages or provider is None:
        return [], list(pages)

    by_title = {page.title: page for page in pages}
    response = provider.generate(
        system=CLUSTER_SYSTEM_PROMPT,
        prompt="TITLES\n\n" + "\n".join(sorted(by_title)) + "\n\nGroup these into topics.",
        temperature=0.0,
        max_tokens=1500,
    )

    topics: list[ProposedTopic] = []
    placed: set[str] = set()
    for name, members in _parse_clusters(response.text, set(by_title)):
        chosen = [by_title[title] for title in members if title not in placed]
        if not chosen:
            continue
        placed.update(page.title for page in chosen)
        topics.append(
            ProposedTopic(
                name=name,
                pages=[("standard", page.title) for page in chosen],
                nist_controls=_anchor_controls([page.storage_body for page in chosen]),
                evidence="grouped by the model; no title convention applied",
            )
        )

    return topics, [page for page in pages if page.title not in placed]


def discover_topics(pages, *, space: str, provider=None) -> DiscoveryReport:
    """Propose a registry from a space's pages."""
    topics, leftovers = group_by_convention(pages)
    clustered, unplaced = cluster_leftovers(leftovers, provider)
    topics.extend(clustered)

    for topic in topics:
        topic.space = space

    return DiscoveryReport(
        topics=sorted(topics, key=lambda t: t.name.lower()),
        unplaced=sorted(page.title for page in unplaced),
        pages_seen=len(pages),
    )


def render_registry(report: DiscoveryReport) -> str:
    """The proposal as a `topics.yaml` somebody can edit and rename."""
    import yaml

    header = (
        "# Proposed by `policyforge zardoz discover`. Not usable as-is.\n"
        "#\n"
        f"# Every owner is {UNASSIGNED}: nothing in a page reliably says which\n"
        "# team is accountable for it, and guessing one into a compliance\n"
        "# artifact is worse than leaving it blank. Set them, check the\n"
        "# groupings and the anchor controls, then rename this to topics.yaml.\n"
        "#\n"
        "# `policyforge coverage` will tell you what no topic claims and what\n"
        "# two topics claim once you have.\n\n"
    )
    body = yaml.safe_dump(
        {"topics": [topic.as_yaml_block() for topic in report.topics]},
        sort_keys=False,
        allow_unicode=True,
    )
    return header + body
