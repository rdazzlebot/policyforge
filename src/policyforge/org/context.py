"""Reading an organization's tools and teams, and filling them in exactly.

Two halves, and the second is the point.

**Reading** accepts both shapes. `vendors` has always been a flat list, and
config files people already maintain must keep working, so a list is still
valid and still means "these products exist, work out where they go". A
mapping is the richer form: `identity_provider: Okta` says what Okta is
*for*, which is the only fact a substitution needs.

**Filling in** happens after the model has written the document, not inside
the prompt. That ordering is the whole reason this module exists. Asking a
model to use a name consistently gets it right most of the time, and "most
of the time" across forty documents is a set where the same system is called
three things. A post-pass over the finished text is exact, repeatable, and
testable without an API key: the generator writes `[Identity Provider]`
wherever the role belongs, and every one of those becomes `Okta` or none of
them does.

Placeholders that stay unfilled are the useful output of the same pass. A
document saying `[Ticketing System]` is telling you a fact about your
configuration, not failing — and knowing which ones are outstanding is worth
more than a document that quietly invented a product name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .roles import TEAM_ROLES, VENDOR_ROLES, Role, resolve_role

#: Matches `[Identity Provider]` and the hedged `[Identity Provider - Okta]`
#: form a model writes when it has been given a name but is unsure the role
#: is right. Both resolve to the configured value when there is one.
#:
#: The dash separating a hedge must have whitespace on both sides. Without
#: that, `[On-Call Paging]` parses as the role "On" hedged with "Call
#: Paging" - a label with a hyphen in it is ordinary English, and several of
#: the role labels have one.
#:
#: Em dash, en dash, hyphen, built by code point rather than written out:
#: three dashes side by side in a source file are indistinguishable to a
#: reader and to a linter, and only one of them is the ASCII one.
_HEDGE_DASHES = "".join(chr(code) for code in (0x2014, 0x2013, 0x2D))
_PLACEHOLDER_RE = re.compile(rf"\[([A-Z][A-Za-z0-9/ .&-]*?)(?:\s+[{_HEDGE_DASHES}]\s+[^\]]+)?\]")


@dataclass
class Assignment:
    """One role, and what fills it."""

    role: Role
    value: str


@dataclass
class OrgProfile:
    """Who the organization is, and what it runs."""

    name: str = ""
    industry: str = ""
    #: Products named with no role attached. Still passed to the generator,
    #: which infers what it can — the old behaviour, kept because config
    #: files in the wild use it.
    unkeyed_vendors: list[str] = field(default_factory=list)
    vendors: dict[str, Assignment] = field(default_factory=dict)
    teams: dict[str, Assignment] = field(default_factory=dict)
    #: Keys that matched no known role. Reported rather than dropped: a
    #: typo'd `identity-provdier` should be visible, not silently ignored.
    unknown: list[str] = field(default_factory=list)

    @property
    def assignments(self) -> list[Assignment]:
        return list(self.vendors.values()) + list(self.teams.values())

    def substitutions(self) -> dict[str, str]:
        """Placeholder label -> the value that replaces it, lowercased keys."""
        return {a.role.label.lower(): a.value for a in self.assignments}


def _parse(raw, roles: dict[str, Role]) -> tuple[dict[str, Assignment], list[str], list[str]]:
    """Read a role mapping, tolerating the legacy list form."""
    if not raw:
        return {}, [], []
    if isinstance(raw, list):
        return {}, [str(item) for item in raw if str(item).strip()], []

    if not isinstance(raw, dict):
        return {}, [], []

    assignments: dict[str, Assignment] = {}
    unknown: list[str] = []
    for key, value in raw.items():
        text = str(value).strip() if value is not None else ""
        if not text:
            continue
        role = resolve_role(str(key), roles)
        if role is None:
            unknown.append(str(key))
            continue
        assignments[role.key] = Assignment(role=role, value=text)
    return assignments, [], sorted(unknown)


def load_org_profile(config: dict) -> OrgProfile:
    """Build a profile from the `org:` block of a loaded config."""
    org = (config or {}).get("org") or {}
    vendors, unkeyed, unknown_vendors = _parse(org.get("vendors"), VENDOR_ROLES)
    teams, unkeyed_teams, unknown_teams = _parse(org.get("teams"), TEAM_ROLES)

    return OrgProfile(
        name=str(org.get("name") or ""),
        industry=str(org.get("industry") or ""),
        # A team list with no roles is meaningless — a team name only helps
        # when you know what it owns — so those fall through to `unknown`
        # rather than being carried as free-floating strings.
        unkeyed_vendors=unkeyed,
        vendors=vendors,
        teams=teams,
        unknown=sorted(unknown_vendors + unknown_teams + unkeyed_teams),
    )


@dataclass
class SubstitutionResult:
    text: str
    #: (placeholder label, value) actually replaced, in document order.
    filled: list[tuple[str, str]] = field(default_factory=list)
    #: Labels left as placeholders, deduplicated. Not a failure: a document
    #: that says [Ticketing System] is reporting a gap in the configuration
    #: rather than inventing a product.
    outstanding: list[str] = field(default_factory=list)


def apply_substitutions(text: str, profile: OrgProfile) -> SubstitutionResult:
    """Replace every placeholder whose role the organization has filled.

    Deterministic by construction: the same document and the same config
    produce the same output, and no model is consulted. Placeholders for
    roles nobody has assigned are left exactly as written.
    """
    table = profile.substitutions()
    filled: list[tuple[str, str]] = []
    outstanding: list[str] = []

    def _replace(match: re.Match) -> str:
        label = match.group(1).strip()
        value = table.get(label.lower())
        if value is None:
            if label not in outstanding:
                outstanding.append(label)
            return match.group(0)
        filled.append((label, value))
        return value

    return SubstitutionResult(
        text=_PLACEHOLDER_RE.sub(_replace, text),
        filled=filled,
        outstanding=outstanding,
    )


def render_for_prompt(profile: OrgProfile) -> str:
    """The organization block a generator prompt is given.

    Roles with a value are stated as facts. Roles without one are *not*
    listed: naming thirty unfilled roles would invite the model to mention
    systems the organization never said it had, and the placeholder it
    should write is already specified by the drafting rules.
    """
    lines = [f"Organization: {profile.name}", f"Industry: {profile.industry}"]

    if profile.vendors:
        lines.append("")
        lines.append("Tools, by the role each one fills:")
        lines += [
            f"  {a.role.label}: {a.value}"
            for a in sorted(profile.vendors.values(), key=lambda a: a.role.label)
        ]
        lines.append(
            "  Use these names for these roles. Where the document needs a system "
            "whose role is not listed above, write the role in square brackets "
            "(for example [Ticketing System]) rather than naming a product the "
            "organization has not said it uses."
        )
    if profile.unkeyed_vendors:
        lines.append("")
        lines.append(
            "Other tools in use, roles not stated: "
            + ", ".join(profile.unkeyed_vendors)
            + ". Use them only where you are confident what they are for."
        )
    if profile.teams:
        lines.append("")
        lines.append("Teams, by the function each one performs:")
        lines += [
            f"  {a.role.label}: {a.value}"
            for a in sorted(profile.teams.values(), key=lambda a: a.role.label)
        ]

    if not profile.vendors and not profile.unkeyed_vendors:
        lines.append("")
        lines.append(
            "No tools supplied. Write the role in square brackets wherever the "
            "document needs to name a system — [Identity Provider], [Ticketing "
            "System] — rather than naming a product."
        )
    return "\n".join(lines)
