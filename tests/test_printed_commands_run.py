"""A command the product prints must be one a person can actually run.

Three ways a printed command fails, and this project has now produced all
three:

- **its context differs from the reader's** — `/coverage` printed
  `crosswalk seed --framework 'NIST 800-171'`, which worked in the shell
  that printed it and exited 1 from the CLI's own default catalogs;
- **it does not survive a shell** — the same fix then emitted Windows
  backslashes, which bash eats as escapes;
- **an interpolated value breaks the quoting** — the subject of #187.

A printed command is a promise. It is also the one kind of output nothing
here executes, so nothing here notices when it stops being true.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "policyforge"

#: A backtick-quoted `policyforge …` string carrying at least one flag.
#: Bare command names in prose — "see `policyforge generate`" — are
#: references rather than invocations and cannot fail to run.
_PRINTED = re.compile(r"`policyforge ([^`]*--[^`]*)`")

#: Markers that a string is illustrative rather than runnable.
#:
#: `zardoz/skills.py` prints ``policyforge satisfies --controls ...`` with a
#: literal ellipsis, and `zardoz/shell.py` prints `<your markdown tree>`.
#: **Both are doing their job.** A class test that cannot say "this one is
#: an example" fails on strings that are correct, which is the fastest way
#: to get a class test deleted.
_ILLUSTRATIVE = ("...", "<")


def _printed_commands() -> list[tuple[str, str]]:
    found = []
    for path in sorted(SRC.rglob("*.py")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in _PRINTED.finditer(line):
                # `as_posix`, so the site string is the same on every
                # platform. `relative_to` gives backslashes on Windows, and
                # anything comparing these — the exemption set below, a
                # failure message someone pastes into an issue — would then
                # hold on one runner and not the other.
                where = f"{path.relative_to(SRC.parent).as_posix()}:{line_no}"
                found.append((where, match.group(1)))
    return found


def test_the_population_is_not_empty():
    """Guard the population, or every loop below passes vacuously."""
    assert _printed_commands(), (
        "no printed command with a flag was found anywhere in src/. Either the "
        "pattern stopped matching or they all went away; check which."
    )


#: The printed commands that are examples rather than invocations, named
#: rather than counted. Both are doing their job — `skills.py` prints a
#: literal ellipsis and `shell.py` a `<placeholder>`.
ILLUSTRATIVE_SITES = {
    "policyforge/zardoz/shell.py:552",
    "policyforge/zardoz/skills.py:305",
}


def test_exactly_the_known_commands_are_exempt():
    """**A skip is how a site leaves this check, so the set of skips is a
    decision and not a side effect.**

    `_ILLUSTRATIVE` is a marker rule: any printed command containing
    `...` or `<` is skipped. That is right for the two sites it was
    written for, and it means a *third* one added later would be excluded
    silently — the check would keep passing while covering less.

    Pinned by site rather than by count, so the failure message names
    which string stopped being checked. Adding a genuinely illustrative
    command should turn this red once and be resolved by editing this
    set, which is a person deciding; a real command that happens to
    contain `<` should be caught here rather than skipped forever.

    Same shape as the catalog-key guard: derive the population from the
    code, enumerate the exemptions by hand.
    """
    exempt = {
        where
        for where, printed in _printed_commands()
        if any(marker in printed for marker in _ILLUSTRATIVE)
    }

    assert exempt == ILLUSTRATIVE_SITES, (
        "the set of printed commands treated as examples has changed. Anything "
        "added here stops being checked against the CLI, so it wants a decision "
        "rather than a silent skip."
    )


def _cli_help(*command: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "policyforge.cli", *command, "--help"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout + result.stderr


@pytest.mark.parametrize("where,printed", _printed_commands())
def test_every_flag_in_a_printed_command_exists(where: str, printed: str):
    """**Checked against the live CLI, not against a list written here.**

    A list would be a second copy of the interface, correct on the day it
    was typed. Asking the CLI costs a subprocess and cannot go stale.
    """
    if any(marker in printed for marker in _ILLUSTRATIVE):
        pytest.skip(f"{where} is illustrative, not an invocation")

    words = printed.split()
    stop = next((i for i, w in enumerate(words) if w.startswith("-")), len(words))
    command = list(words[:stop])
    flags = {w.split("=")[0] for w in words if w.startswith("--")}
    if not command:
        pytest.skip(f"{where} names no subcommand")

    help_text = _cli_help(*command)
    for flag in sorted(flags):
        assert flag in help_text, (
            f"{where} prints `policyforge {printed}`, but {flag!r} is not on "
            f"`policyforge {' '.join(command)} --help`. The product is telling a "
            f"user to run something it does not accept."
        )


#: Every site that interpolates a value into a printed command, with a
#: hostile value for each. Derived by hand and listed because **there is no
#: way to discover an interpolation's runtime value statically** — the
#: population of *sites* is checkable, and that is what the next test does.
_INTERPOLATED = (
    'Vendor "Bring Your Own" Policy',
    "Ryan's Access Policy",
    "Policy; rm -rf /tmp/x",
    "a title with\ttabs",
)


def _publishers():
    """Every concrete `Publisher`, derived rather than listed.

    **The population is the point.** The first version of the test below
    named `ConfluencePublisher` and covered one of the three sites this
    PR quotes; reverting `shlex.quote` in `github_wiki.py` left the suite
    green. A fourth publisher must be covered by existing, not by
    somebody remembering to add a case.
    """
    import policyforge.export.github_wiki  # noqa: F401  — registers the subclass
    from policyforge.export.publisher import Publisher

    return sorted(Publisher.__subclasses__(), key=lambda c: c.__name__)


@pytest.mark.parametrize("publisher", _publishers(), ids=lambda c: c.__name__)
@pytest.mark.parametrize("title", _INTERPOLATED)
def test_a_reconcile_command_survives_a_hostile_title(publisher, title: str):
    """**The defect: a document title is user-authored prose.**

    `--title "Vendor "Bring Your Own" Policy"` parses as
    `--title "Vendor Bring"` — a valid command naming the wrong document,
    with nothing to indicate it went wrong. Titles containing quotes are
    not exotic; a policy set has them.

    **Across every publisher, because the guard that shipped with the fix
    covered only the site being fixed.** policyforge-80 reverted each
    `shlex.quote` in turn, confirming each edit landed, and found
    `publisher.py` caught and `github_wiki.py` not — a guard written
    while fixing one case covering only that case, in the PR closing the
    issue about exactly that.
    """

    # A distinct hostile value per field, so a field that is dropped or
    # merged into its neighbour is visible rather than masked by another
    # field carrying the same string.
    fields = {
        "space": f"space {title}",
        "page_title": f"page_title {title}",
        "tier": f"tier {title}",
    }

    class _Doc:
        space = fields["space"]
        page_title = fields["page_title"]
        tier = fields["tier"]

    class _Self:
        """Enough of a publisher for `reconcile_command`.

        `ConfluencePublisher` reads only `doc`; `GitHubWikiPublisher`
        calls `self.title(doc)`. Called unbound with this stub so the
        test needs no network config and no constructor arguments.
        """

        def title(self, doc):
            return doc.page_title

    class _Benign:
        space = "space benign"
        page_title = "page_title benign"
        tier = "tier benign"

    benign = publisher.reconcile_command(_Self(), _Benign())
    printed = publisher.reconcile_command(_Self(), _Doc())
    parsed = shlex.split(printed)

    # **Every field the document supplies, not the one the author was
    # thinking about.** The first version set only `page_title` hostile
    # and asserted only `--title`. Reverting
    # `shlex.quote(doc.tier or "standard")` on both publishers then left
    # the whole suite green — 2913 passed — and `tier` is declared
    # `tier: str` with no enum and no validator, so
    # `standard --apply --force /etc` injects flags into a command
    # printed for a person to copy. policyforge-80 found it: the fix had
    # derived *which sites* to walk and still hand-fixed *which field*
    # was hostile, which is the original finding one axis over.
    #
    # Asserted as "each value survives as one argv element" rather than
    # "each flag's next word matches", because a publisher may print a
    # constant (`--target`) or a valueless flag (`--apply`), and indexing
    # past the last one raises rather than failing.
    #
    # Which fields a publisher uses is derived from a BENIGN run, not
    # from `value in printed` — `shlex.quote` escapes the value, so a
    # title containing an apostrophe never appears literally in the
    # printed string. Asking the benign run also means a field that the
    # hostile run *drops entirely* is a failure rather than silently
    # dropping out of the population.
    expected = {
        name: marker
        for name, marker in (("space", "space "), ("page_title", "page_title "), ("tier", "tier "))
        if any(word.startswith(marker) for word in shlex.split(benign))
    }
    assert expected, f"{publisher.__name__} interpolated no document field: {benign}"
    for name in expected:
        assert parsed.count(fields[name]) == 1, (
            f"{publisher.__name__} does not round-trip {name} as one argument "
            f"— a shell would see {parsed}: {printed}"
        )


@pytest.mark.parametrize("name", _INTERPOLATED)
def test_the_history_command_survives_a_hostile_document_name(name: str):
    """The third quoting site, and the one that is not a publisher.

    `cli/content.py` prints a `history` invocation naming a document.
    Reverting its `shlex.quote` also left the suite green, because the
    test above reaches publishers and this is a `click.echo` in a CLI
    function — a different shape, so the derived population cannot
    include it and it gets its own case, stated rather than assumed.
    """
    from policyforge.cli import content

    # **Both interpolated fields, not the one in the test's name.** The
    # first version set only `name` hostile, and reverting
    # `shlex.quote(tier)` left the suite green — the same axis error as
    # the publishers, committed one file over in the commit fixing it.
    values = {"--tier": f"tier {name}", "--name": f"name {name}"}
    printed = content.history_hint(
        tier=values["--tier"], name=values["--name"], previous="v1", current="v2"
    )
    parsed = shlex.split(printed)

    for flag, value in values.items():
        assert parsed[parsed.index(flag) + 1] == value, (
            f"the history hint does not round-trip {flag} {value!r} — a shell "
            f"would see {parsed}: {printed}"
        )


def test_every_interpolating_site_quotes_its_values():
    """The class, so a fourth site cannot be added unquoted.

    Source-level because the values are runtime data — the behavioural
    test above can only reach the sites it knows about, and this one
    reaches the sites that exist.
    """
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "policyforge " not in line or "{" not in line:
                continue
            if "--" not in line:
                continue
            # An interpolated value inside hand-written quotes is the defect.
            if re.search(r'"\{[^}]+\}"', line) or re.search(r"'\{[^}]+\}'", line):
                offenders.append(f"{path.relative_to(SRC.parent)}:{line_no}: {line.strip()}")
    assert not offenders, (
        "a printed command interpolates a value inside hand-written quotes. Use "
        "`shlex.quote`, which handles the quote characters the value may itself "
        "contain:\n  " + "\n  ".join(offenders)
    )
