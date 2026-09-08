"""The topic registry: which topics exist, and who owns each one.

A *topic* is a coherent operational process — access review, backup and
restore, vendor risk — that one team can comfortably own end to end. It is
the unit this project generates documentation for, instead of generating one
document per control (300-plus artifacts nobody owns).

Why this is a declared file rather than a CLI argument: without it, a topic
exists only for the duration of one `policyforge synthesize` invocation, and
nothing records who owns it. Once topics are declared, the two questions that
actually sink a compliance program become computable — see `coverage.py`:

* which in-scope controls does **no** topic claim (nobody is doing it), and
* which are claimed by **two** (worse: it looks covered, while both owners
  assume the other has it).

The registry lives in `config/topics.yaml`, which is gitignored for the same
reason `config/config.yaml` is — it names your internal teams. Copy
`config/topics.example.yaml` to start from a reasonable default set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TOPICS_PATH = Path("config/topics.yaml")


@dataclass
class Topic:
    """One ownable process, and the controls it answers for.

    `nist_controls` are *anchors*, not an exhaustive list: anchoring a
    control also claims its enhancements (see `coverage.py`), so a topic
    doesn't have to enumerate AC-2(1) through AC-2(13) to own AC-2.
    """

    name: str
    owner: str
    nist_controls: list[str] = field(default_factory=list)
    cadence: str = ""
    description: str = ""
    evidence: list[str] = field(default_factory=list)
    #: Where this topic's documents live, so `edit-topic` can change a
    #: topic's Policy, Standard and Procedure together:
    #:     confluence:
    #:       space: ENG
    #:       pages: {standard: "...", policy: "...", procedure: "..."}
    #: Optional — a topic with no published pages simply can't be edited by
    #: title, and says so rather than guessing at one.
    confluence: dict = field(default_factory=dict)

    def confluence_pages(self) -> list[tuple[str, str]]:
        """(tier, page title) for each published document, Policy first.

        Ordered Policy -> Standard -> Procedure so a reviewer reads the set
        the way the document hierarchy is meant to be read, rather than in
        whatever order the YAML happened to list them.
        """
        pages = self.confluence.get("pages") or {}
        order = ("policy", "standard", "procedure")
        ordered = [(tier, pages[tier]) for tier in order if pages.get(tier)]
        ordered += [
            (tier, title) for tier, title in sorted(pages.items()) if tier not in order and title
        ]
        return ordered


class TopicRegistryError(ValueError):
    """Raised when a registry is malformed.

    Deliberately fatal rather than best-effort: a typo'd control ID or a
    topic missing an owner silently corrupts the coverage report, which is
    the one artifact whose whole job is to be trusted about what's covered.
    """


def parse_topics(data: dict) -> list[Topic]:
    """Parse and validate a loaded `topics.yaml` structure."""
    if not isinstance(data, dict) or "topics" not in data:
        raise TopicRegistryError(
            "Topic registry must be a mapping with a top-level `topics:` list. "
            "See config/topics.example.yaml."
        )
    raw_topics = data["topics"]
    if not isinstance(raw_topics, list) or not raw_topics:
        raise TopicRegistryError("`topics:` must be a non-empty list.")

    known_fields = {f.name for f in Topic.__dataclass_fields__.values()}
    topics: list[Topic] = []
    seen: set[str] = set()

    for index, raw in enumerate(raw_topics, start=1):
        if not isinstance(raw, dict):
            raise TopicRegistryError(f"Topic #{index} is not a mapping.")

        unknown = sorted(set(raw) - known_fields)
        if unknown:
            raise TopicRegistryError(
                f"Topic #{index} ({raw.get('name', '?')!r}) has unknown key(s): "
                f"{', '.join(unknown)}. Supported: {', '.join(sorted(known_fields))}."
            )
        for required in ("name", "owner"):
            if not raw.get(required):
                raise TopicRegistryError(
                    f"Topic #{index} is missing `{required}`. Every topic needs exactly "
                    "one accountable owner — that is the point of the registry."
                )

        name = str(raw["name"]).strip()
        if name.lower() in seen:
            raise TopicRegistryError(f"Duplicate topic name: {name!r}.")
        seen.add(name.lower())

        topics.append(
            Topic(
                name=name,
                owner=str(raw["owner"]).strip(),
                nist_controls=[str(c).strip() for c in raw.get("nist_controls") or []],
                cadence=str(raw.get("cadence") or "").strip(),
                description=str(raw.get("description") or "").strip(),
                evidence=[str(e).strip() for e in raw.get("evidence") or []],
                confluence=dict(raw.get("confluence") or {}),
            )
        )

    return topics


def load_topics(path: Path = DEFAULT_TOPICS_PATH) -> list[Topic]:
    """Load the topic registry from disk."""
    import yaml

    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Copy config/topics.example.yaml to {path} and set the "
            "owners to your own teams."
        )
    return parse_topics(yaml.safe_load(path.read_text(encoding="utf-8")))
