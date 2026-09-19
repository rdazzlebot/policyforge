"""After cutting a tag: does what a user installs match what you released?

Every check in this repository looks *inside* the repository. On 2026-09-19
three sessions declared 1.4.0 done — the tag was right, the version triple
agreed, the changelog was correct, the gate was green, the release notes
were published — and for roughly three hours `brew install
rdazzlebot/tap/policyforge`, the first command in this project's own README,
installed **1.3.0**. Every individual check passed. None of them looked at
the artefact a user receives.

That release was the one adding the `etl-hipaa` guard, so anyone installing
in that window got the build where running `etl-hipaa` on its own silently
rewrote their catalog from 65 crosswalk mappings to 0 and reported nothing
wrong. The tag is not the deliverable. For anyone following the README, the
tap is.

Three assertions, in the order they fail:

1. The published formula's `url` names the tag just cut.
2. The formula's pinned resource versions match the lock at that tag.
3. `changelog.d/` is empty — no fragment survived the release.

**Every one compares values and prints them, and none reads an exit
status.** That is not stylistic. On the same night a Homebrew build failed
while its harness reported success, because the shell returns the status of
the *last* command in a sequence and that was `tail`; `set -o pipefail`
protects a pipe and has no opinion about `cmd; echo; tail`. A release step
that shells out and trusts `$?` inherits exactly that. So does one that
exits quietly on success — a step nobody can tell ran is the gate defect
this project already fixed once, wearing different clothes.

Run it after pushing the tap, not before: it fetches the *published*
formula, because the question is what a user gets rather than what is in
your working copy.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

FORMULA_URL = (
    "https://raw.githubusercontent.com/rdazzlebot/homebrew-tap/main/Formula/policyforge.rb"
)

#: The lock the formula's resources must agree with. `runtime.txt` rather
#: than `ci.txt`: Homebrew installs what a user runs, not the dev extras.
LOCK = "requirements/runtime.txt"

_FORMULA_URL_RE = re.compile(r'^\s*url "([^"]+)"', re.MULTILINE)
_RESOURCE_RE = re.compile(
    r'^  resource "([^"]+)" do\n\s*url "([^"]+)"',
    re.MULTILINE,
)
#: `name==1.2.3` at the start of a line, before any `\` continuation.
_PIN_RE = re.compile(r"^([A-Za-z0-9._-]+)==([^\s\\;]+)", re.MULTILINE)


def fetch_formula(url: str = FORMULA_URL) -> str:
    """The formula as published, not as it sits in a local clone."""
    # The default is a fixed https URL to this project's own tap.
    # `--formula-url` is a maintainer-supplied override, used only to point
    # the check at a perturbed copy while proving it can fail — it is not
    # reachable from any user-facing command, and this script is a release
    # step run by hand rather than anything `policyforge` invokes.
    #
    # Both suppressions sit on the offending line: semgrep honours
    # `nosemgrep` only on that line or the one directly above, so a comment
    # a few lines up reads as documentation and suppresses nothing.
    with urllib.request.urlopen(url, timeout=30) as response:  # nosec B310  # nosemgrep
        return response.read().decode("utf-8")


def tag_in_formula(formula: str) -> str | None:
    """The tag the formula's source `url` names, e.g. `v1.4.0`."""
    match = _FORMULA_URL_RE.search(formula)
    if not match:
        return None
    tag = re.search(r"/tags/([^/]+)\.tar\.gz", match.group(1))
    return tag.group(1) if tag else None


def formula_resources(formula: str) -> dict[str, str]:
    """`{name: version}` for every `resource` block, from its sdist URL.

    Read from the URL rather than a version field because a `resource` has
    no version field — the version is only in the filename it fetches.
    """
    found: dict[str, str] = {}
    for name, url in _RESOURCE_RE.findall(formula):
        filename = url.rsplit("/", 1)[-1]
        stem = re.sub(r"\.(tar\.gz|zip|tar\.bz2)$", "", filename)
        if "-" in stem:
            found[name.lower().replace("_", "-")] = stem.rsplit("-", 1)[-1]
    return found


def lock_pins(text: str) -> dict[str, str]:
    """`{name: version}` from a hashed requirements lock."""
    return {name.lower().replace("_", "-"): version for name, version in _PIN_RE.findall(text)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True, help="the version just cut, e.g. 1.4.0")
    parser.add_argument(
        "--formula-url", default=FORMULA_URL, help="override the published formula location"
    )
    args = parser.parse_args(argv or [])

    expected_tag = args.version if args.version.startswith("v") else f"v{args.version}"
    failures: list[str] = []

    # ---------------------------------------------------------------- 1
    print("=" * 62)
    print(f"1. The published formula installs {expected_tag}")
    print("=" * 62)
    # Recorded rather than returned. An unreachable formula is a transient;
    # a leftover fragment is deterministic and needs no network. Returning
    # here let the transient mask it, so an operator fixed the network, re-ran,
    # and only then learned a fragment had missed the release — two round
    # trips, the second reporting the failure this script prints first
    # precisely because nothing else will catch it. A transient must not be
    # able to hide a result that was already known. (1d, demonstrated.)
    formula: str | None = None
    try:
        formula = fetch_formula(args.formula_url)
    except Exception as exc:  # noqa: BLE001 - any fetch failure is a real answer
        print(f"  could not fetch the formula: {type(exc).__name__}: {exc}")
        print("  -> CANNOT ANSWER")
        failures.append(
            f"could not fetch the formula ({type(exc).__name__}) — cannot tell what a "
            "user installs, so this is a failure rather than a pass; retry"
        )

    if formula is not None:
        found_tag = tag_in_formula(formula)
        print(f"  formula url names : {found_tag}")
        print(f"  tag just cut      : {expected_tag}")
        if found_tag != expected_tag:
            failures.append(f"the tap installs {found_tag}, not {expected_tag} — push the formula")
            print("  -> MISMATCH")
        else:
            print("  -> match")

    # ---------------------------------------------------------------- 2
    print()
    print("=" * 62)
    print("2. The formula's resources match the lock")
    print("=" * 62)
    if formula is None:
        # Skipped with a stated reason rather than silently absent. A check
        # that did not run and does not say so is the gate defect #112 fixed.
        # Flow continues: assertion 3 is local and must still be answered.
        print("  SKIPPED — the formula could not be fetched (see 1 above)")
        print("  -> not answered")
    else:
        resources = formula_resources(formula)
        pins = lock_pins((REPO_ROOT / LOCK).read_text(encoding="utf-8"))
        overlap = sorted(set(resources) & set(pins))
        mismatched = [(n, resources[n], pins[n]) for n in overlap if resources[n] != pins[n]]
        unlocked = sorted(set(resources) - set(pins))

        print(f"  formula resources : {len(resources)}")
        print(f"  lock pins         : {len(pins)}")
        print(f"  overlapping       : {len(overlap)}")
        print(f"  version mismatches: {len(mismatched)}")
        print(f"  in formula, not in lock: {len(unlocked)}")
        for name, got, want in mismatched:
            print(f"    {name}: formula {got}, lock {want}")
        for name in unlocked:
            print(f"    {name}: pinned by the formula and in no lock")
        if mismatched or unlocked:
            failures.append(
                f"{len(mismatched)} resource(s) disagree with {LOCK} and "
                f"{len(unlocked)} are unlocked — the lock decides"
            )
            print("  -> MISMATCH")
        else:
            print("  -> match")

    # ---------------------------------------------------------------- 3
    print()
    print("=" * 62)
    print("3. No changelog fragment survived the release")
    print("=" * 62)
    fragment_dir = REPO_ROOT / "changelog.d"
    leftover = (
        sorted(p.name for p in fragment_dir.glob("*.md") if p.name != "README.md")
        if fragment_dir.is_dir()
        else []
    )
    print(f"  changelog.d/ entries: {len(leftover)}")
    for name in leftover:
        print(f"    {name}")
    if leftover:
        failures.append(
            f"{len(leftover)} fragment(s) still in changelog.d/ — their entries "
            f"missed {args.version} and nothing else will say so"
        )
        print("  -> LEFTOVER")
    else:
        print("  -> empty")

    # ----------------------------------------------------------------
    print()
    print("=" * 62)
    if failures:
        # Leftover fragments first: the other two are visible the moment
        # someone installs, while a fragment that missed its version is
        # invisible until a reader goes looking for an entry that is not
        # there — and by then the release is published.
        for line in sorted(failures, key=lambda f: "fragment" not in f):
            print(f"  FAILED: {line}")
        print("=" * 62)
        return 1
    print(f"  All three hold for {expected_tag}.")
    print("=" * 62)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
