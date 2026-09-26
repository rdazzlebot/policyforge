"""Which content may be sent to which provider, decided before the call.

PolicyForge writes security policy, so "we only send licensed catalog
content to a model we run ourselves" should be a control it can evidence
rather than a sentence in a README. Today the one live case is advisory:
`generate-parser` prints a paragraph asking a human to confirm their MyCSF
licence permits sending an export to a third-party API, and then trusts the
answer. A paragraph is not a control. This module is.

**Two classifications and a ceiling between them.**

Providers are classified by where the bytes end up:

* `local` — a model running on this machine. Ollama, llama-server, LM
  Studio: a loopback endpoint. Nothing leaves the host.
* `self-hosted` — a model the organization runs, reached over its own
  network. An RFC 1918 or link-local address, or an internal name. It
  leaves the host but not the boundary.
* `third-party` — somebody else's processor. Anthropic, Bedrock, Vertex,
  OpenRouter, any public endpoint. It leaves the boundary, and a licence
  that permits internal use has now been tested against a question it was
  probably not written to answer.

Content is classified by who may hold it:

* `public-domain` — NIST 800-53, FedRAMP, ARC-AMPE, the HIPAA Security
  Rule. Government works; anyone may redistribute them.
* `organization-internal` — the organization's own material: generated
  documents, its topic registry, its synthesis output. Sensitive, but the
  organization decides where it goes, and sending it to a model is the
  entire purpose of this tool.
* `licensed` — HITRUST CSF and GovRAMP exports, and anything under
  `local_content/`. Held under a licence that permits *the licensee's* use
  and says nothing helpful about handing a copy to a processor.

The rule is a ceiling per content class: the most exposed provider class
that class of content may reach. Licensed content's ceiling is `local`;
everything else may reach a third party, because that is what the tool does
every working day. A configuration can tighten any ceiling and cannot
loosen one, since tightening is the only direction that is safe to make
easy.

**It fails closed in three places, on purpose.** A provider nobody can
classify is third-party, because the expensive mistake is assuming a model
is local when it is not. A framework with no manifest is licensed, which is
`frameworks/registry.py`'s existing rule and this module defers to it. And
a ceiling naming a class that does not exist raises rather than falling
back to a default, because a typo that silently restores the default
permission is how a control stops being one.

**What this is not.** It does not decide whether a generated document
citing `[HITRUST 01.c]` may be redistributed — that is a fair-use question
for a lawyer, and `registry.derived_from` exists to put the right files in
front of one. It decides only whether a specific file may be sent to a
specific endpoint, which is a question with an answer.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from policyforge.frameworks import registry

# ---- provider classes, ordered by exposure --------------------------------

LOCAL = "local"
SELF_HOSTED = "self-hosted"
THIRD_PARTY = "third-party"

#: Ordered least- to most-exposed. The order is the whole comparison: a
#: ceiling permits every class at or below it, and a cascade takes the
#: maximum of its halves.
PROVIDER_CLASSES = (LOCAL, SELF_HOSTED, THIRD_PARTY)

# ---- content classes ------------------------------------------------------

PUBLIC_DOMAIN = "public-domain"
ORG_INTERNAL = "organization-internal"
LICENSED = "licensed"

CONTENT_CLASSES = (PUBLIC_DOMAIN, ORG_INTERNAL, LICENSED)

#: The most exposed provider class each kind of content may reach, absent a
#: configured ceiling. Only `licensed` is restrictive, and it is restrictive
#: because the licence under which that content arrived did not contemplate
#: a processor.
DEFAULT_CEILINGS: dict[str, str] = {
    PUBLIC_DOMAIN: THIRD_PARTY,
    ORG_INTERNAL: THIRD_PARTY,
    LICENSED: LOCAL,
}


class BoundaryViolation(Exception):
    """Raised when a call would send content past its ceiling.

    An exception rather than a warning: the whole difference between this
    module and the paragraph it replaces is that this one stops.
    """


@dataclass(frozen=True)
class ProviderClassification:
    """Where a configured provider sends its bytes, and how that was decided."""

    klass: str
    reason: str
    #: True when config said so outright rather than this module inferring
    #: it from a URL. A declaration is the operator's statement about their
    #: own network and outranks any guess made here.
    declared: bool = False

    def __str__(self) -> str:
        how = "declared" if self.declared else "inferred"
        return f"{self.klass} ({how}: {self.reason})"


@dataclass(frozen=True)
class ContentClassification:
    """What a path holds, and what said so."""

    klass: str
    reason: str
    #: The framework the path was found in, when it was found in one. Named
    #: so a refusal can say *which* catalog made the content licensed
    #: instead of leaving the operator to guess.
    framework_id: str | None = None

    def __str__(self) -> str:
        return f"{self.klass} ({self.reason})"


@dataclass(frozen=True)
class Decision:
    """The answer to "may this content go to this provider", with its reasons."""

    allowed: bool
    content: ContentClassification
    provider: ProviderClassification
    ceiling: str

    def explain(self) -> str:
        verdict = "allowed" if self.allowed else "REFUSED"
        return (
            f"{verdict}: {self.content.klass} content -> {self.provider.klass} provider "
            f"(the ceiling for {self.content.klass} is {self.ceiling})\n"
            f"  content:  {self.content}\n"
            f"  provider: {self.provider}"
        )


def exposure(klass: str) -> int:
    """Rank a provider class. Higher means the bytes travel further."""
    try:
        return PROVIDER_CLASSES.index(klass)
    except ValueError:
        raise ValueError(
            f"Unknown provider class {klass!r}. Known: {', '.join(PROVIDER_CLASSES)}."
        ) from None


# ---- classifying a provider ----------------------------------------------


def _host_class(url: str | None) -> tuple[str, str]:
    """Classify an endpoint by its host. Returns (class, reason).

    A hostname is not proof of anything — a loopback address can be
    port-forwarded, and an internal DNS name can resolve to a CDN — so this
    is inference and is labelled as such. `llm.classification` exists for
    the operator who knows better, which is every operator with a
    non-obvious network.
    """
    if not url:
        return THIRD_PARTY, "no endpoint configured, so where it goes is unknown"

    host = urlparse(url).hostname
    if not host:
        return THIRD_PARTY, f"could not read a host out of {url!r}"

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # A name, not an address. Only the names that cannot mean anything
        # else are treated as local; a name this module cannot resolve
        # safely stays at the closed end.
        lowered = host.lower()
        if lowered == "localhost" or lowered.endswith(".localhost"):
            return LOCAL, f"{host} is this machine"
        if lowered.endswith(".local") or lowered.endswith(".internal"):
            return SELF_HOSTED, f"{host} is an internal name"
        return THIRD_PARTY, f"{host} is a public name"

    if address.is_loopback:
        return LOCAL, f"{host} is a loopback address"
    if address.is_private or address.is_link_local:
        return SELF_HOSTED, f"{host} is on a private network"
    return THIRD_PARTY, f"{host} is a routable address"


def classify_provider(llm_config: dict) -> ProviderClassification:
    """Where the provider described by an `llm:` block sends its bytes.

    Takes the config block rather than a built provider, so this can be
    answered before any client is constructed, any key is read, or any
    optional dependency is imported. Refusing a run should not require the
    credentials for the call being refused.
    """
    declared = llm_config.get("classification")
    if declared is not None:
        declared = str(declared).strip().lower()
        if declared not in PROVIDER_CLASSES:
            raise ValueError(
                f"llm.classification is {declared!r}, which is not a provider class. "
                f"Use one of: {', '.join(PROVIDER_CLASSES)}."
            )
        return ProviderClassification(declared, "llm.classification in config", declared=True)

    name = str(llm_config.get("provider", "")).strip().lower()

    if name == "cascade":
        # Content reaches whichever half answers, and which half that is
        # depends on a runtime failure nobody can predict at configuration
        # time. So a cascade is as exposed as its most exposed half — the
        # only reading that cannot be wrong in the dangerous direction.
        halves = [
            classify_provider(llm_config.get(key) or {}) for key in ("primary", "escalate_to")
        ]
        worst = max(halves, key=lambda c: exposure(c.klass))
        both = " and ".join(c.klass for c in halves)
        return ProviderClassification(
            worst.klass,
            f"a cascade is as exposed as its most exposed half ({both})",
        )

    if name in ("anthropic", "bedrock", "vertex", "gemini"):
        # Named rather than left to the unrecognised-provider fallback
        # below. That fallback is also third-party, so the outcome would be
        # the same today — but a provider whose classification depends on
        # falling off the end of this function is one rename away from
        # being classified by accident, and this table is what the licensed
        # ceiling is enforced from.
        return ProviderClassification(THIRD_PARTY, f"{name} is a hosted API")

    if name in ("openai-compat", "local"):
        # The `local` alias names the provider *protocol*, not the network.
        # Someone pointing it at a hosted vLLM endpoint would otherwise read
        # the alias as a guarantee, which is exactly backwards — so the
        # alias is ignored here and the URL decides.
        klass, reason = _host_class(llm_config.get("base_url"))
        return ProviderClassification(klass, reason)

    if name == "litellm":
        api_base = llm_config.get("api_base")
        if api_base:
            klass, reason = _host_class(api_base)
            return ProviderClassification(klass, reason)
        return ProviderClassification(
            THIRD_PARTY,
            f"litellm resolves {llm_config.get('model', '?')!r} to a hosted vendor",
        )

    return ProviderClassification(
        THIRD_PARTY,
        f"provider {name or '(unset)'} is unrecognised, so it is treated as exposed",
    )


def classify_endpoint(block: dict, *, default_url: str, key: str) -> ProviderClassification:
    """Where an `embed:` or `rerank:` block sends its bytes.

    The rule `classify_provider` applies to a URL-addressed `llm:` block,
    for the two channels addressed by URL alone: a declared `classification`
    wins, otherwise the host decides. `default_url` is the one the factory
    would use, so an unset `base_url` is classified as what it actually is —
    this machine — rather than as unknown and therefore exposed.
    """
    declared = block.get("classification")
    if declared is not None:
        declared = str(declared).strip().lower()
        if declared not in PROVIDER_CLASSES:
            raise ValueError(
                f"{key}.classification is {declared!r}, which is not a provider class. "
                f"Use one of: {', '.join(PROVIDER_CLASSES)}."
            )
        return ProviderClassification(declared, f"{key}.classification in config", declared=True)
    klass, reason = _host_class(block.get("base_url") or default_url)
    return ProviderClassification(klass, reason)


# ---- classifying content --------------------------------------------------


def _under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except (ValueError, OSError):
        return False
    return True


def classify_path(
    path: Path, config: dict | None = None, *, assume_written: bool = False
) -> ContentClassification:
    """What kind of content lives at `path`.

    Three questions, in order of how much they know. Is it inside a
    discovered framework, which carries a manifest saying what it is? Is it
    under a search path this project keeps out of git, which is where it
    tells people to put licensed exports? Otherwise it is the organization's
    own material, which is the ordinary case and the one the tool exists to
    send to a model.

    `assume_written` answers for a file that does not exist yet, as the
    answer will be once it does (#459): a licensed ETL asks it about its
    `--out` before writing, and refuses a destination this would call
    anything but licensed.
    """
    config = config or {}
    resolved = path.resolve()
    pending = path if assume_written else None

    for framework in registry.discover(config, assume_written=pending):
        if _under(resolved, framework.path):
            if framework.redistributable:
                return ContentClassification(
                    PUBLIC_DOMAIN,
                    f"{framework.id} declares itself public domain",
                    framework.id,
                )
            how = "declares itself licensed" if framework.declared else "has no manifest"
            return ContentClassification(LICENSED, f"{framework.id} {how}", framework.id)

    for root in registry.search_paths(config):
        # `local_content/` is gitignored precisely so licensed exports
        # cannot be committed. A file put there was put there for that
        # reason, whether or not anyone got around to writing a manifest
        # beside it.
        if root.name == "local_content" and _under(resolved, root):
            return ContentClassification(LICENSED, f"under {root}, which is kept out of git")

    return ContentClassification(ORG_INTERNAL, "not part of any declared framework catalog")


# ---- the ceiling ----------------------------------------------------------


def ceilings(config: dict | None = None) -> dict[str, str]:
    """The ceiling per content class, configured values over defaults.

    Config tightens, never loosens::

        llm:
          boundary:
            organization-internal: self-hosted   # our drafts stay inside

    Raising a ceiling is refused. The point of a declared boundary is that
    relaxing it takes more than a line of YAML written in a hurry; someone
    who genuinely may send a HITRUST export to a hosted model can classify
    that model with `llm.classification`, which says the same thing as a
    claim about their own network, where it is visible as one.
    """
    configured = ((config or {}).get("llm") or {}).get("boundary") or {}
    if not isinstance(configured, dict):
        raise ValueError(
            "llm.boundary should be a mapping of content class to the most exposed "
            f"provider class it may reach, not {type(configured).__name__}."
        )

    resolved = dict(DEFAULT_CEILINGS)
    for content_class, ceiling in configured.items():
        key = str(content_class).strip().lower()
        if key not in CONTENT_CLASSES:
            raise ValueError(
                f"llm.boundary names {content_class!r}, which is not a content class. "
                f"Use one of: {', '.join(CONTENT_CLASSES)}."
            )
        value = str(ceiling).strip().lower()
        if value not in PROVIDER_CLASSES:
            raise ValueError(
                f"llm.boundary.{key} is {ceiling!r}, which is not a provider class. "
                f"Use one of: {', '.join(PROVIDER_CLASSES)}."
            )
        if exposure(value) > exposure(DEFAULT_CEILINGS[key]):
            raise ValueError(
                f"llm.boundary.{key} is {value!r}, which is more permissive than the "
                f"default of {DEFAULT_CEILINGS[key]!r}. This setting tightens the "
                "boundary; it cannot loosen it. If that provider really is inside your "
                "boundary, say so with `llm.classification` instead, where the claim is "
                "about your network and reads like one."
            )
        resolved[key] = value
    return resolved


def check(
    content: ContentClassification,
    provider: ProviderClassification,
    config: dict | None = None,
) -> Decision:
    """Decide one pairing. Returns the verdict; raises nothing."""
    ceiling = ceilings(config)[content.klass]
    return Decision(
        allowed=exposure(provider.klass) <= exposure(ceiling),
        content=content,
        provider=provider,
        ceiling=ceiling,
    )


def enforce(path: Path, config: dict) -> Decision:
    """Refuse to send `path` to the configured provider, or say why it is fine.

    The one call a command that reads a file and then calls a model should
    make, before it reads the file.
    """
    decision = check(
        classify_path(path, config),
        classify_provider(config.get("llm") or {}),
        config,
    )
    if not decision.allowed:
        raise BoundaryViolation(
            f"Refusing to send {path} to the configured provider.\n"
            f"{decision.explain()}\n"
            "  Point `llm:` at a local model (Ollama at http://localhost:11434/v1, say) "
            "for this run, or — if this provider really is inside your boundary — "
            "declare that with `llm.classification` in config.yaml."
        )
    return decision


def matrix(config: dict | None = None) -> str:
    """The ceilings as a table, for `policyforge boundary` and the README."""
    resolved = ceilings(config)
    width = max(len(name) for name in CONTENT_CLASSES)
    header = "  ".join(klass.ljust(11) for klass in PROVIDER_CLASSES)
    lines = [f"{'content'.ljust(width)}  {header}"]
    for content_class in CONTENT_CLASSES:
        allowed = exposure(resolved[content_class])
        cells = "  ".join(
            ("yes" if exposure(klass) <= allowed else "no").ljust(11) for klass in PROVIDER_CLASSES
        )
        lines.append(f"{content_class.ljust(width)}  {cells}")
    return "\n".join(lines)
