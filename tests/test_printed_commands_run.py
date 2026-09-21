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
                found.append((f"{path.relative_to(SRC.parent)}:{line_no}", match.group(1)))
    return found


def test_the_population_is_not_empty():
    """Guard the population, or every loop below passes vacuously."""
    assert _printed_commands(), (
        "no printed command with a flag was found anywhere in src/. Either the "
        "pattern stopped matching or they all went away; check which."
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


@pytest.mark.parametrize("title", _INTERPOLATED)
def test_a_reconcile_command_survives_a_hostile_title(title: str):
    """**The defect: a document title is user-authored prose.**

    `--title "Vendor "Bring Your Own" Policy"` parses as
    `--title "Vendor Bring"` — a valid command naming the wrong document,
    with nothing to indicate it went wrong. Titles containing quotes are
    not exotic; a policy set has them.
    """
    from policyforge.export.publisher import ConfluencePublisher

    class _Doc:
        space = "SEC"
        page_title = title
        tier = "standard"

    # **`ConfluencePublisher`, not `Publisher`.** The first version called
    # the abstract base, whose `reconcile_command` is a stub returning
    # `None` -- so the test exercised nothing and failed on `shlex.split`
    # with "s argument must not be None" rather than on the quoting it
    # was written to check. It would have passed just as readily against
    # a broken implementation. Called unbound because the method touches
    # only `doc`.
    printed = ConfluencePublisher.reconcile_command(None, _Doc())
    parsed = shlex.split(printed)
    assert parsed[parsed.index("--title") + 1] == title, (
        f"the printed command does not round-trip {title!r}: {printed}"
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
