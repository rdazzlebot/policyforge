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

Four assertions, in the order they fail:

1. The published formula's `url` names the tag just cut.
1b. ...and its `sha256` matches the archive that URL actually serves. A
    formula can name the right tag beside a stale hash, and then every
    install fails at verification while assertion 1 reports it correct.
2. The formula's pinned resource versions match the lock at that tag.
3. `changelog.d/` is empty — no fragment survived the release.
4. A user can actually install it — `brew install --build-from-source` in
   a clean container, then the CLI runs.

**Assertion 4 exists because this script was the substitution.** The
recorded procedure was: verify in a container BEFORE pushing the formula.
What happened at 1.6.0 was push → run this script → call it done, and the
formula was live and unverified for the whole gap. The container run
afterwards passed, which is not the point: it ran because the user asked
*"don't you usually run a docker test after cutting a release?"*

This script reads the formula and compares values. **It never installed
anything.** Those are different questions, and the cheap one stood in for
the one that matters — so the fix is that the cheap one can no longer
report success on its own. A skipped step leaves a gap; a substituted step
leaves a false assurance, which is worse.

Assertion 4 is SKIPPABLE and skipping it FAILS unless you say so, the same
contract `scripts/check.py` uses for gitleaks: a check nobody ran must not
look like a check that passed.

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
import hashlib
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
#: The FIRST top-level sha256 — the source archive's. `resource` blocks
#: carry their own below it; assertion 2 handles those against the lock.
_FORMULA_SHA_RE = re.compile(r'^  sha256 "([0-9a-f]{64})"', re.MULTILINE)
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


def source_url_in_formula(formula: str) -> str | None:
    """The source archive the formula fetches, as written."""
    match = _FORMULA_URL_RE.search(formula)
    return match.group(1) if match else None


def sha256_in_formula(formula: str) -> str | None:
    """The formula's top-level `sha256`, which is the source archive's.

    The first one in the file: `resource` blocks carry their own further
    down, and they are checked by assertion 2 against the lock instead.
    """
    match = _FORMULA_SHA_RE.search(formula)
    return match.group(1) if match else None


def hash_of(url: str) -> str:
    """SHA-256 of whatever that URL actually serves, fetched now.

    From the URL the formula names rather than from a copy already on
    disk. A hash taken from the archive you happen to be holding matches
    whatever you are holding, which is the question nobody asked.
    """
    # The URL is read out of the published formula, which is fetched from a
    # fixed https address; `--formula-url` is a maintainer override used only
    # to point this at a perturbed copy while proving it can fail. Suppression
    # on the offending line, not above it — see CONTRIBUTING.
    with urllib.request.urlopen(url, timeout=120) as response:  # nosec B310  # nosemgrep
        digest = hashlib.sha256()
        for chunk in iter(lambda: response.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


#: The container steps, in order, each run as its own process so its exit
#: status is read rather than inherited.
#:
#: **The smoke tests here are the corrected ones.** The 1.6.0 run used
#: `policyforge --version`, which does not exist — the flag was invented,
#: click exits 2, and that reads as a broken release to anyone skimming.
#: And it ran `policyforge frameworks` in an empty directory, which exits 1
#: by design: every command reads `data/frameworks/` relative to where it
#: runs, and the install's own caveats say so three lines above. **A smoke
#: test that is wrong is indistinguishable from a release that is broken
#: until somebody checks which**, so the correct sequence is pinned here
#: rather than retyped from memory each time.
INSTALL_STEPS: tuple[tuple[str, str], ...] = (
    ("tap", "brew tap rdazzlebot/tap"),
    ("install", "brew install --build-from-source rdazzlebot/tap/policyforge"),
    ("audit", "brew audit --strict --online rdazzlebot/tap/policyforge"),
    ("init", "cd /tmp/pf && policyforge init"),
    ("frameworks", "cd /tmp/pf && policyforge frameworks"),
)

CONTAINER_IMAGE = "homebrew/brew"


def run_install_check(image: str = CONTAINER_IMAGE) -> tuple[bool, list[str]]:
    """Install the published formula in a clean container and run the CLI.

    Returns `(ran, lines)`. **`ran` is False when the container could not
    be started at all** — no docker, no daemon, no image — which is a
    different answer from "the install failed" and must not be collapsed
    into it. The caller turns *did not run* into a failure unless the
    operator said otherwise; it does not turn it into a pass.

    Each step is a separate `docker run`, so each exit status is its own.
    Chaining them into one shell would return the status of the LAST
    command, which is the defect this file's header already records: a
    Homebrew build failed while its harness reported success because the
    final command in the sequence was `tail`.
    """
    import shutil
    import subprocess

    lines: list[str] = []
    if shutil.which("docker") is None:
        return False, ["docker is not on PATH"]

    script = " && ".join(command for _, command in INSTALL_STEPS)
    # One container, but the steps are joined with `&&` so the FIRST
    # failure stops the run and its status propagates. `;` would not --
    # that is the `cmd; echo; tail` shape the header warns about, and it
    # is also issue #182 on this milestone.
    proc = subprocess.run(
        ["docker", "run", "--rm", image, "bash", "-lc", f"mkdir -p /tmp/pf && {script}"],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-12:]
    lines.extend(tail)
    lines.append(f"docker exit status: {proc.returncode}")
    return True, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True, help="the version just cut, e.g. 1.4.0")
    parser.add_argument(
        "--formula-url", default=FORMULA_URL, help="override the published formula location"
    )
    parser.add_argument(
        "--allow-skip",
        action="append",
        default=[],
        choices=["install"],
        help="acknowledge that a check did not run. Without this, a check that "
        "did not run fails -- the same contract scripts/check.py uses.",
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

        # 1b. Naming the right tag is not the same as installing it. A
        # formula edited by hand can carry the new url beside the previous
        # release's sha256, and then *every* install fails at verification
        # while this check reports the url as correct. Asked of the archive
        # the formula actually names, fetched now — a hash taken from a copy
        # already on disk matches whatever you are holding, which is the
        # question nobody asked. (1d, who found assertion 1 could not see it.)
        print()
        print("=" * 62)
        print("1b. ...and the sha256 matches what that URL serves")
        print("=" * 62)
        stated = sha256_in_formula(formula)
        source = source_url_in_formula(formula)
        if not stated or not source:
            print(f"  could not read url/sha256 from the formula (url={source}, sha256={stated})")
            print("  -> CANNOT ANSWER")
            failures.append("the formula's url or sha256 could not be read — check its shape")
        else:
            try:
                actual = hash_of(source)
            except Exception as exc:  # noqa: BLE001 - not knowing is a failure
                print(f"  could not fetch the archive: {type(exc).__name__}: {exc}")
                print("  -> CANNOT ANSWER")
                failures.append(
                    f"could not fetch the source archive ({type(exc).__name__}) — cannot tell "
                    "whether the formula's sha256 is current; retry"
                )
            else:
                print(f"  formula sha256 : {stated}")
                print(f"  archive served : {actual}")
                if stated != actual:
                    failures.append(
                        "the formula's sha256 does not match the archive it names — every "
                        "`brew install` fails at verification; recompute it from that URL"
                    )
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

    # ---------------------------------------------------------------- 4
    print()
    print("=" * 62)
    print("4. A user can actually install it")
    print("=" * 62)
    ran, lines = run_install_check()
    for line in lines:
        print(f"    {line}")
    if not ran:
        if "install" in args.allow_skip:
            print("  -> DID NOT RUN, acknowledged with --allow-skip install")
            print("     Nothing here has installed anything. The formula is unverified.")
        else:
            failures.append(
                "the install check did not run, and nothing else in this script "
                "installs anything -- run it where docker is available, or accept "
                "the gap explicitly with --allow-skip install"
            )
            print("  -> DID NOT RUN")
    elif lines and lines[-1].endswith(" 0"):
        print("  -> installed and ran")
    else:
        failures.append(
            "the published formula did not install in a clean container -- this is "
            "what a user following the README gets"
        )
        print("  -> FAILED")

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
    print(f"  All four hold for {expected_tag}.")
    print("=" * 62)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
