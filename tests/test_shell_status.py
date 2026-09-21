"""The committed-shell status checker, made to fail in both directions.

**A guard that refuses everything passes a refusal test and is useless.**
This repository has already produced one near-miss of exactly that shape, so
every rule below is stated twice: the string it must refuse, and the string
it must let through. The second half is the one that keeps the guard alive,
because a check that fires on correct code gets switched off within a day.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import shell_status

REPO_ROOT = Path(__file__).resolve().parent.parent


def _scan(kind: str, *lines: str) -> list[shell_status.Finding]:
    source = shell_status.Source(path="seeded.yml", kind=kind, lines=list(enumerate(lines, 1)))
    return shell_status.findings([source])


def _rules(findings: list[shell_status.Finding]) -> set[str]:
    return {finding.rule for finding in findings}


# --- what it must REFUSE -------------------------------------------------


def test_the_shape_that_cost_seven_instances_in_one_day():
    """`cmd | tail && action` -- the `&&` runs on `tail`'s status."""
    findings = _scan("workflow", "python scripts/check.py | tail -4 && git push")
    assert "swallowed-status" in _rules(findings)


@pytest.mark.parametrize(
    "line",
    [
        "make build | grep -v warning && deploy",
        "pytest -q | head -20 && echo ok",
        "cat log | awk '{print $2}' && rm log",
        "git ls-files | wc -l && touch stamp",
    ],
)
def test_every_stream_consumer_is_covered_not_just_tail(line: str):
    """**The instance-versus-class failure this repo has now found five times.**

    The rule was written after a `| tail`, and a guard written while fixing
    one case covers only that case. `head`, `grep` and `awk` discard a
    status exactly as `tail` does.
    """
    assert "swallowed-status" in _rules(_scan("workflow", line))


def test_a_pipeline_in_a_workflow_without_pipefail_is_a_finding():
    """GitHub's default shell is `bash -e`, which does not set pipefail.

    Measured rather than assumed, in the module docstring: the same
    pipeline exits 0 under `bash -e` and 1 with pipefail.
    """
    assert "no-pipefail" in _rules(_scan("workflow", "git ls-files -z '*.md' | xargs -0 mdformat"))


def test_the_empty_input_path_is_reported_separately_from_pipefail():
    """**policyforge-9b's finding, and the reason there are two rules.**

    `mdformat --check` with no paths exits 0. So a pathspec that stops
    matching makes the step pass having examined nothing -- and **pipefail
    does not fire, because nothing failed.** A single rule would have
    reported this as fixed once `set -o pipefail` was added.
    """
    findings = _scan("workflow", "git ls-files -z '*.md' | xargs -0 mdformat --check")
    assert {"no-pipefail", "empty-input-passes"} <= _rules(findings)

    with_pipefail = _scan(
        "workflow", "set -o pipefail", "git ls-files -z '*.md' | xargs -0 mdformat --check"
    )
    assert "no-pipefail" not in _rules(with_pipefail), "pipefail should satisfy that rule"
    assert "empty-input-passes" in _rules(with_pipefail), (
        "pipefail must NOT silence the empty-input rule -- that is the whole finding"
    )


def test_a_tool_nobody_enumerated_is_still_caught():
    """**policyforge-ba's question, and it found a real gap.**

    The first version keyed this rule on a list of four tool names. The
    property belongs to tools, the set of tools with it is larger than any
    list, and it grows whenever someone adds a linter to CI. Measured in
    the project venv:

        mdformat 0   ruff 0   semgrep 0   pip-audit 0   pytest 0   bandit 2

    **Three of those were missing from the list on the day it was
    written** — the class-versus-instance failure, inside the file whose
    job is to catch that shape.

    So the rule is keyed on the construct: `xargs` without `-r` runs its
    command once on empty input, whatever the command is. This test uses a
    tool that is deliberately **not** in `EMPTY_INPUT_TOOLS`, so it fails
    if anyone puts the list back in charge.
    """
    line = "git ls-files -z '*.tf' | xargs -0 some-future-linter --check"
    assert not any(
        re.search(rf"\b{re.escape(tool)}\b", line) for tool in shell_status.EMPTY_INPUT_TOOLS
    ), "pick a tool that is not enumerated, or this test proves nothing"
    assert "empty-input-passes" in _rules(_scan("workflow", line))


def test_xargs_dash_r_is_the_other_legitimate_fix():
    """What the rule must ALLOW, stated beside what it refuses.

    `xargs -r` declines to run the command at all on empty input, so the
    tool cannot report "nothing to do" as success. That is a real fix and
    a shorter one than asserting a count, and a rule that refused it would
    be demanding a specific spelling rather than the property.
    """
    line = "set -o pipefail; git ls-files -z '*.md' | xargs -0 -r mdformat --check"
    assert "empty-input-passes" not in _rules(_scan("workflow", "set -o pipefail", line))


def test_a_pipeline_that_is_not_xargs_is_not_an_empty_input_finding():
    """The rule is about `xargs`, not about the word `mdformat`.

    Piping into a tool directly does not run it on an empty list — the
    tool simply reads an empty stream. Flagging this would fire on correct
    code, which is how a check gets muted.
    """
    assert "empty-input-passes" not in _rules(
        _scan("workflow", "set -o pipefail", "cat files.txt | mdformat --check -")
    )


# --- what it must ALLOW --------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        # capture-then-branch: the house idiom the rule exists to promote
        "python scripts/check.py > gate.log 2>&1; rc=$?",
        # sequencing with no pipe at all -- three of these are in the README
        "policyforge init my-policies && cd my-policies",
        "python -m venv .venv && source .venv/bin/activate",
        # a real pipeline: the right-hand side is the work, not a pager
        "cat manifest.json | python -m json.tool > pretty.json",
    ],
)
def test_the_legitimate_forms_are_not_findings(line: str):
    """**Stated as a requirement, not as an absence.**

    A guard with no passing case has already produced one near-miss here.
    These four are what correct code in this repository looks like, and a
    rule that reddens on them would be removed rather than obeyed.
    """
    assert _scan("workflow", line) == []


def test_a_documentation_snippet_is_not_required_to_set_pipefail():
    """A snippet is run by hand and watched; a script runs unattended and is
    believed. Requiring `set -o pipefail` in every README block would be
    noise, and noise is how a check gets muted."""
    line = "git ls-files -z '*.md' | xargs -0 mdformat --check"
    assert "no-pipefail" not in _rules(_scan("doc", line))
    assert "swallowed-status" not in _rules(_scan("doc", line))


def test_a_doc_snippet_still_cannot_swallow_a_status_into_a_decision():
    """The one rule that does apply to documentation: a reader who pastes
    `cmd | tail && action` gets the wrong outcome wherever it came from."""
    assert "swallowed-status" in _rules(_scan("doc", "check.py | tail -4 && git push"))


def test_prose_about_the_rule_is_not_a_violation_of_it():
    """**Two tests in this repository have failed on their own explanation**,
    asserting the absence of strings their docstrings had to name. A checker
    that flags the comment describing it has the identical defect, and
    `ci.yml`, this file and `verifying-a-merge.md` all now carry the bad
    shape inside a comment."""
    assert _scan("workflow", "# never write: cmd | tail -4 && git push") == []
    assert _scan("workflow", "run: make  # unlike cmd | grep x && y") == []


def test_the_shape_inside_a_quoted_string_is_still_reported():
    """**A known and deliberate false positive, written down rather than fixed.**

    `echo 'cmd | tail && x'` does not execute the pipeline and is reported
    anyway, because `bash -c 'cmd | tail && x'` is indistinguishable from it
    without a shell parser -- and that one *does* execute it. Stripping
    quoted spans would make the checker silent on the `bash -c` form, which
    is a real path and the more dangerous error.

    So the limit is: **quoted content is treated as code.** A comment is
    not, which is the case that actually recurs. If this ever fires on
    something genuinely inert, `PIPEFAIL_EXEMPT` takes it with a reason
    rather than the rule being loosened for everyone.
    """
    assert "swallowed-status" in _rules(_scan("workflow", "bash -c 'x | tail && y'"))
    assert "swallowed-status" in _rules(_scan("workflow", "echo 'x | tail && y'"))


# --- the population, and the assertion that keeps the rest meaningful ----


def test_the_population_is_not_empty_and_covers_every_kind():
    """**The defect this check exists to find, applied to itself.**

    A derivation that stops matching enumerates zero, every rule over it
    becomes vacuous, and the check goes green. `population()` is derived
    from `git ls-files`, so a renamed directory or a changed pathspec would
    do exactly that.
    """
    sources = shell_status.population()
    assert sources, "derived zero shell sources -- the derivation is broken"
    kinds = {source.kind for source in sources}
    assert {"workflow", "doc"} <= kinds, f"a whole kind stopped being derived: {kinds}"
    assert sum(1 for s in sources if s.kind == "workflow") >= 5


def test_an_empty_population_fails_rather_than_passes(monkeypatch):
    """Run through `main`, not through `population`.

    A monkeypatched constant does not reach a `from x import y` binding in
    another module -- a guard written that way in this repository passed
    with the defect deliberately introduced. Patching the function that
    `main` actually calls is what makes this test able to fail.
    """
    monkeypatch.setattr(shell_status, "population", lambda: [])
    assert shell_status.main([]) == 2


def test_the_repository_itself_is_clean():
    """The check run the way the gate runs it, as a subprocess.

    Not `main([])` in-process: the gate invokes a script, and an import-time
    difference between the two is exactly the gap that lets a gate pass
    while CI fails.
    """
    result = subprocess.run(
        [sys.executable, "scripts/shell_status.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_ci_still_gates_markdown_on_a_non_empty_list():
    """The fix, asserted on the artefact rather than on the intention.

    `shell_status` would pass if the step were deleted outright, since a
    step that does not exist has no pipeline to complain about. **A guard
    against a bad line does not notice a missing line**, so the presence of
    the check is pinned here.
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "mdformat --check" in workflow, "CI no longer checks markdown at all"
    assert "set -o pipefail" in workflow
    assert '"${#files[@]}" -eq 0' in workflow, "the empty-list assertion is gone"
