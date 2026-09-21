"""Reading a Homebrew formula: the parts that decide what a user installs.

`scripts/release_check.py` had no tests at all — not the new assertion, the
whole file. So its behaviour was proven by two people probing it by hand on
the night it was written, and by nothing afterwards. That is this project's
own finding pointed at itself: **a written rule fires only if recalled; an
assertion fires whether or not anyone remembers it exists.**

Only the pure functions are covered here. Everything else in that script
fetches over the network, and a unit test that mocks the fetch would be
asserting the mock. The network half is verified by running the script
against the published formula after a tag, which is what it is for.

The fragile part is `sha256_in_formula`. A formula carries **one** source
hash at two spaces and one per `resource` at four, so the indentation
anchor is the whole mechanism: matching a resource hash instead would
compare a wheel's digest against the source archive and mismatch forever.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import release_check

#: The shape a real formula has: source url and hash at two spaces, then
#: resources with their own at four. Trimmed, not invented — the ordering
#: and indentation are what the tap actually ships.
FORMULA = """class Policyforge < Formula
  desc "Generate cross-mapped security policies"
  url "https://github.com/rdazzlebot/policyforge/archive/refs/tags/v1.5.0.tar.gz"
  sha256 "28136768f54dff1dd2d351869dfdbab82f701c83518e3545f663355381a84b94"
  license "Apache-2.0"

  resource "anyio" do
    url "https://files.pythonhosted.org/packages/a9/d2/anyio-4.15.1.tar.gz"
    sha256 "1111111111111111111111111111111111111111111111111111111111111111"
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/bb/aa/click-8.3.0.tar.gz"
    sha256 "2222222222222222222222222222222222222222222222222222222222222222"
  end
end
"""


def test_the_source_hash_is_read_and_not_a_resource_hash():
    """The two-space anchor is the mechanism, not a formatting preference.

    A resource's hash compared against the source archive would mismatch
    on every run forever — loud rather than silent, which is the right
    direction to fail, but it would make the check useless.
    """
    assert (
        release_check.sha256_in_formula(FORMULA)
        == "28136768f54dff1dd2d351869dfdbab82f701c83518e3545f663355381a84b94"
    )


def test_a_formula_with_no_source_hash_returns_none():
    """`None` rather than falling through to the first resource's hash.

    Absent and wrong are different answers, and the caller reports the
    first as "cannot answer" instead of a mismatch nobody can act on.
    """
    stripped = FORMULA.replace(
        '  sha256 "28136768f54dff1dd2d351869dfdbab82f701c83518e3545f663355381a84b94"\n', ""
    )

    assert release_check.sha256_in_formula(stripped) is None


def test_the_source_url_is_read_and_not_a_resource_url():
    assert release_check.source_url_in_formula(FORMULA) == (
        "https://github.com/rdazzlebot/policyforge/archive/refs/tags/v1.5.0.tar.gz"
    )


@pytest.mark.parametrize(
    "url, expected",
    [
        ('  url "https://x/archive/refs/tags/v1.5.0.tar.gz"', "v1.5.0"),
        ('  url "https://x/archive/refs/tags/v1.10.2.tar.gz"', "v1.10.2"),
        ('  url "https://x/some/other/path.tar.gz"', None),
    ],
)
def test_the_tag_comes_from_the_url_or_not_at_all(url, expected):
    """A url that names no tag returns `None`, so the caller says so rather
    than comparing a guess against the version it was given."""
    assert release_check.tag_in_formula(url + "\n") == expected


def test_resources_are_read_from_their_filenames():
    """A `resource` block has no version field — only the sdist filename."""
    assert release_check.formula_resources(FORMULA) == {"anyio": "4.15.1", "click": "8.3.0"}


def test_lock_pins_ignore_hash_continuations():
    """A hashed lock wraps with `\\` and `--hash=` lines that are not pins."""
    lock = (
        "anyio==4.15.1 \\\n"
        "    --hash=sha256:abc \\\n"
        "    --hash=sha256:def\n"
        "click==8.3.0 \\\n"
        "    --hash=sha256:aaa\n"
        "# a comment\n"
    )

    assert release_check.lock_pins(lock) == {"anyio": "4.15.1", "click": "8.3.0"}


def test_names_are_compared_case_and_separator_insensitively():
    """PyPI writes `Jinja2` and `python-frontmatter`; a lock may not agree
    on case or on `_` versus `-`, and a false mismatch there would block a
    release for a naming convention."""
    assert release_check.lock_pins("Typing_Extensions==4.16.0\n") == {"typing-extensions": "4.16.0"}


# ---- assertion 4: the cheap check may no longer stand in for the real one ----


def test_the_install_steps_are_the_corrected_ones():
    """**A smoke test that is wrong is indistinguishable from a release
    that is broken, until somebody checks which.**

    The 1.6.0 container run used `policyforge --version` — a flag that
    does not exist, so click exits 2 — and ran `policyforge frameworks`
    in an empty directory, which exits 1 by design because every command
    reads `data/frameworks/` relative to where it runs. Both read as
    release defects. Neither was one.

    Pinned here so the sequence is not retyped from memory at each cut.
    """
    from release_check import INSTALL_STEPS

    names = [name for name, _ in INSTALL_STEPS]
    commands = " ; ".join(command for _, command in INSTALL_STEPS)

    assert "--version" not in commands, (
        "`policyforge --version` does not exist; click exits 2 and it reads as a broken release"
    )
    assert names.index("init") < names.index("frameworks"), (
        "`frameworks` must run after `init`: in an empty directory it exits 1 "
        "by design, which is the product working as documented"
    )
    assert "--build-from-source" in commands, (
        "installing a bottle does not exercise the formula being released"
    )


def test_a_check_that_did_not_run_does_not_pass(monkeypatch, capsys):
    """**The whole point of the issue.** A skipped step leaves a gap; a
    substituted step leaves a false assurance, and this script *was* the
    substitution — it compares values and never installs anything.

    So "docker is unavailable" must not read as "the install is fine".
    Same contract `scripts/check.py` uses for gitleaks: a check nobody ran
    fails until somebody says otherwise, out loud.
    """
    import shutil

    import release_check

    # Patched on `shutil` itself, because `run_install_check` imports it
    # inside the function -- so there is no module attribute to replace.
    # Worth stating: the first version patched `release_check.shutil` and
    # failed with AttributeError rather than silently passing, which is
    # the good kind of wrong.
    monkeypatch.setattr(shutil, "which", lambda _: None)
    ran, lines = release_check.run_install_check()

    assert ran is False, "no docker must report DID NOT RUN, not a result"
    assert any("docker" in line for line in lines)


def test_did_not_run_is_a_different_answer_from_failed():
    """Two states that must not collapse into one.

    `run_install_check` returns `(ran, lines)` rather than a bool,
    precisely so the caller can tell *nothing happened* from *the install
    is broken*. A single boolean would force one of them to masquerade as
    the other, and the one that would masquerade is the dangerous one.
    """
    import inspect

    from release_check import run_install_check

    signature = inspect.signature(run_install_check)
    assert signature.return_annotation != "bool"
    source = inspect.getsource(run_install_check)
    assert "return False" in source and "return True" in source


def test_each_step_failure_stops_the_run():
    """The defect this file's own header records: a Homebrew build failed
    while its harness reported success, because a shell returns the status
    of the LAST command and that was `tail`.

    `&&` propagates the first failure; `;` does not. This is also #182 on
    the same milestone, which is why it is asserted rather than assumed.
    """
    import inspect

    from release_check import run_install_check

    source = inspect.getsource(run_install_check)
    assert '" && ".join' in source, (
        "steps joined with `;` would report the status of the last one, so a "
        "failed install followed by a successful command reads as success"
    )
