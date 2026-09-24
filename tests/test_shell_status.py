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


def test_one_kind_going_quiet_fails_even_when_the_others_are_healthy(monkeypatch):
    """**policyforge-9b's finding, and it is the whole reason this rule is
    per-kind rather than over the union.**

    `main` originally asked only `if not sources`. A derivation over three
    kinds has three ways to go vacuous and a union has one, so breaking a
    single pathspec left the other kinds intact, printed `clean`, and
    exited 0 — **with `ci.yml`, this lint's one real finding, unexamined.**
    Confirmed by running it: the tool reported clean on a tree that still
    contained the violation.

    Parametrised over every kind that has a signal today, so a fourth kind
    added later is covered by the test that exists.
    """
    real = shell_status.population()
    for quiet in ("workflow", "doc"):
        monkeypatch.setattr(
            shell_status, "population", lambda quiet=quiet: [s for s in real if s.kind != quiet]
        )
        assert shell_status.main([]) == 2, f"{quiet} went to zero and the tool passed"


def test_a_kind_with_nothing_to_find_stays_silent():
    """**What the rule must ALLOW, and it is not hypothetical.**

    `0 script` is today's *correct* state — the repository has no committed
    `*.sh`. A bare "no kind may be zero" rule would have been wrong on
    arrival, and would have been switched off rather than obeyed. The census
    is what separates *nothing to find* from *stopped looking*.
    """
    assert shell_status.census()["script"] == {}, (
        "a committed *.sh now exists; this test's premise is gone and the "
        "script kind should be asserted non-empty instead"
    )
    assert shell_status.main([]) == 0


def test_the_census_is_a_second_derivation_not_the_parser_again():
    """A census computed by the block parser would agree with it by
    construction — the `arc_ampe` defect, and the thing that makes a check
    unable to fail. Since #256 the workflow and doc censuses are a YAML load
    and a CommonMark parse, not regexes, so they are free to disagree with
    the line-walking parsers on inputs a regex would miss on both sides.
    `test_a_flow_style_step_is_seen_by_one_instrument_and_not_the_other`
    holds that.

    **Independence is a property of the METHOD, not of the units, and the
    earlier version of this test confused the two.** It asserted
    `census["workflow"] != count of workflow sources` — 3 against 34 —
    and called the difference evidence of independence. It was evidence
    of a unit mismatch: the census counted *files* and the parser counted
    *run-blocks*. The only question answerable across those two numbers
    is whether both are zero, so `main` could catch a pathspec that
    stopped matching entirely and never a pathspec that matched less. A
    56% loss of the workflow population reported `clean`. #228.

    **The anti-tautology property and the extent-blindness were the same
    fact seen from two sides**, which is why nobody caught it: the check
    that proved the guard was real is the check that proved it was
    limited.

    Both sides now name files, so they are comparable — and still
    independent, which is asserted here by the census being a *strict
    subset* of the tracked files. A census that returned everything it
    globbed would be a list, not a detection.
    """
    signalled = shell_status.census()
    sources = shell_status.population()
    produced: dict[str, dict[str, int]] = {k: {} for k in shell_status._SIGNALS}
    for source in sources:
        produced[source.kind][source.path] = produced[source.kind].get(source.path, 0) + 1

    # Every block the census sees must have been produced. Per file and in
    # blocks, which is the unit change #228 is about.
    for kind, counts in signalled.items():
        for path, blocks in counts.items():
            assert produced[kind].get(path, 0) >= blocks, (
                f"{kind}: {path} signalled {blocks} block(s), parser produced "
                f"{produced[kind].get(path, 0)}"
            )

    # **Independence is no longer "the two numbers differ" and asserting
    # that now would be WRONG.** The earlier version required
    # `census != parser` -- 3 files against 34 run-blocks -- and called the
    # difference evidence of independence. It was evidence of the unit
    # mismatch that made extent unreachable (#228). Both sides now count
    # blocks and agree exactly, 34 and 34, which is the point.
    #
    # So independence is asserted where it actually lives: the census is a
    # YAML load or a CommonMark parse (#256), the parser is a line walk, and
    # a census that returned everything it globbed would be a list rather
    # than a detection.
    tracked_workflows = set(shell_status.tracked(".github/workflows/*.yml"))
    assert set(signalled["workflow"]) < tracked_workflows, (
        "the census returned every workflow it globbed, so it is a list rather "
        "than a detection and cannot disagree with anything"
    )


def test_the_census_does_not_follow_the_parser(monkeypatch):
    """**The independence property, tested by breaking one side.**

    Two derivations are only independent if one can move while the other
    stays put. Asserting that their numbers differ does not show that --
    it shows they are measuring different things, which is what caused
    #228 in the first place.

    So: break the parser and require the census to hold its ground. If the
    census tracked the parser, this is the test that would notice, and it
    is the one the earlier "they must differ" assertion was reaching for.
    """
    before = shell_status.census()
    monkeypatch.setattr(shell_status, "_workflow_run_blocks", lambda path, text: [])
    monkeypatch.setattr(shell_status, "_doc_shell_blocks", lambda path, text: [])
    after = shell_status.census()
    assert after == before, "the census changed when only the parser was broken"
    for kind in ("workflow", "doc"):
        assert sum(after[kind].values()) > 0, (
            f"the census reports no {kind} blocks, so holding steady proves nothing"
        )


# --- #256: the census reaches the population by a different MECHANISM ----------

_FLOW_STEP = """\
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - { name: x, run: "python scripts/check.py | tail -4 && git push" }
"""

_BLOCK_STEP = """\
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: x
        run: python scripts/check.py | tail -4 && git push
"""

_CLEAN_BLOCK_STEP = """\
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: x
        run: python scripts/check.py
"""


def test_a_flow_style_step_is_seen_by_one_instrument_and_not_the_other():
    """**policyforge-b5's case on #256, and the property the census exists for.**

    Before #256 the census was `^\\s*-?\\s*run:` and the parser an
    indentation walk. Both counted this step 0, so they agreed and the floor
    could not fire. The old regex is kept here to show that its blindness
    was shared: that is the defect, and a census that agrees with the parser
    on it is the parser again.
    """
    old_census_regex = re.compile(r"^\s*-?\s*run:", re.M)
    assert len(old_census_regex.findall(_FLOW_STEP)) == 0, "premise: the old census missed it"
    assert shell_status._workflow_run_blocks("seeded.yml", _FLOW_STEP) == [], (
        "premise: the parser misses flow style; if it now reads it, this test's "
        "disagreement is gone and the end-to-end test below should expect exit 1"
    )
    assert shell_status._count_workflow_steps(_FLOW_STEP) == 1


def test_the_workflow_census_counts_steps_and_not_their_lookalikes():
    """What the census must NOT count, measured on the real `ci.yml` shape.

    `defaults: run:` is a mapping, not a script, and a step input called
    `run` under `with:` belongs to the action. Counting either would make
    the census exceed the parser on a clean tree, and that is a false alarm
    that gets a guard switched off.
    """
    text = """\
on: push
defaults:
  run:
    shell: bash
jobs:
  a:
    defaults:
      run:
        shell: bash
    steps:
      - uses: some/action@v1
        with:
          run: not-a-shell
      - run: echo one
      - name: two
        run: |
          echo two
"""
    assert shell_status._count_workflow_steps(text) == 2
    assert shell_status._count_workflow_steps("") == 0


@pytest.mark.parametrize(
    ("fence", "parsed"),
    [
        ("```bash\necho hi\n```\n", 1),
        ("~~~bash\necho hi\n~~~\n", 0),
        ("```bash title=x\necho hi\n```\n", 0),
        ("> ```bash\n> echo hi\n> ```\n", 0),
    ],
)
def test_the_doc_census_reads_fences_the_parser_does_not(fence: str, parsed: int):
    """The CommonMark census counts every shell fence a renderer would. The
    line parser reads only an exact ```` ```bash ````, so each other form is
    now a disagreement, and so a failure, where before both regexes missed
    it and agreed."""
    assert shell_status._count_doc_fences(fence) == 1
    assert len(shell_status._doc_shell_blocks("seeded.md", fence)) == parsed


def _repo(tmp_path: Path, monkeypatch, files: dict[str, str]) -> None:
    """A real git index, so `tracked()` and both derivations run unpatched."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    monkeypatch.setattr(shell_status, "REPO_ROOT", tmp_path)


def test_a_committed_flow_style_step_is_refused(tmp_path, monkeypatch, capsys):
    """**The issue's own acceptance test: commit it and confirm the lint refuses.**

    Before #256 this exited 0: the census and parser both found nothing,
    and the swallowed status went unexamined. Now the census counts the step
    and the parser does not, so it exits 2 and names the file.
    """
    _repo(tmp_path, monkeypatch, {".github/workflows/flow.yml": _FLOW_STEP})
    assert shell_status.main([]) == 2
    assert ".github/workflows/flow.yml  1 -> 0" in capsys.readouterr().err


def test_the_same_step_in_block_style_is_a_finding_and_clean_block_style_passes(
    tmp_path, monkeypatch
):
    """The two arms beside the refusal. The block-style twin is read by the
    parser and reported as the finding it is (exit 1). A clean block-style
    step passes (exit 0), so the floor does not fire on a healthy tree."""
    _repo(tmp_path, monkeypatch, {".github/workflows/block.yml": _BLOCK_STEP})
    assert shell_status.main([]) == 1

    clean = tmp_path.parent / (tmp_path.name + "-clean")
    clean.mkdir()
    _repo(clean, monkeypatch, {".github/workflows/block.yml": _CLEAN_BLOCK_STEP})
    assert shell_status.main([]) == 0


#: Shell languages a fence might name, written from the domain rather than
#: read from either instrument. The ORACLE for the doc census is the parser:
#: every language the parser reads, the census must count. Parametrising
#: over `_SHELL_FENCES` instead would put one constant on both sides of the
#: comparison, and removing a language from it would remove the case that
#: tests it (policyforge-80's `~~~sh` survivor on #326).
_SHELL_LANGUAGE_CANDIDATES = (
    "bash", "sh", "shell", "console", "zsh", "ksh", "fish",
    "powershell", "pwsh", "ps1", "bat", "cmd", "text",
)  # fmt: skip


def _parser_reads(language: str) -> bool:
    fence = f"```{language}\necho hi\n```\n"
    return len(shell_status._doc_shell_blocks("seeded.md", fence)) == 1


_PARSED_LANGUAGES = [c for c in _SHELL_LANGUAGE_CANDIDATES if _parser_reads(c)]


def test_the_parser_reads_a_real_set_of_shell_languages():
    """Guards the parametrisation below from going vacuous: if the parser
    read nothing, the per-language tests would collect zero cases and pass."""
    assert len(_PARSED_LANGUAGES) >= 4, _PARSED_LANGUAGES


@pytest.mark.parametrize("language", _PARSED_LANGUAGES)
def test_a_committed_fence_the_parser_cannot_read_is_refused(
    language, tmp_path, monkeypatch, capsys
):
    """The doc half of the acceptance test, end to end, for EVERY language
    the parser reads.

    **Written because the unit test above was not enough, measured twice.**
    Pointing `_SIGNALS["doc"]` back at the old regex left every test green,
    because the unit test calls `_count_doc_fences` directly and never asks
    whether `census()` uses it. Then, with this test covering only `bash`,
    policyforge-80 removed `sh` from `_SHELL_FENCES` and all 37 still passed.
    A `~~~<language>` fence holding a swallowed status must fail the lint,
    for each language the parser would have read as ```` ```<language> ````.
    """
    _repo(
        tmp_path,
        monkeypatch,
        {
            ".github/workflows/block.yml": _CLEAN_BLOCK_STEP,
            "README.md": f"~~~{language}\npython scripts/check.py | tail -4 && git push\n~~~\n",
        },
    )
    assert shell_status.main([]) == 2
    assert "README.md  1 -> 0" in capsys.readouterr().err


def test_an_aliased_run_agrees_on_count_and_is_not_linted(tmp_path, monkeypatch):
    """**A known limit, pinned so it is not mistaken for coverage** (9b, #326).

    Census and parser both count the aliased step, so the floor is satisfied,
    and the parser lints the literal `*cmd`. The anchored step IS reported,
    and the aliased copy of the same command is not. If the parser is ever
    handed resolved strings, this test fails, and it should then assert 2
    findings instead of 1.
    """
    text = """\
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: &cmd "python scripts/check.py | tail -4 && git push"
      - run: *cmd
"""
    assert shell_status._count_workflow_steps(text) == 2
    assert len(shell_status._workflow_run_blocks("seeded.yml", text)) == 2
    _repo(tmp_path, monkeypatch, {".github/workflows/alias.yml": text})
    swallowed = [
        f for f in shell_status.findings(shell_status.population()) if f.rule == "swallowed-status"
    ]
    assert [f.line for f in swallowed] == [6], swallowed


def test_a_workflow_the_census_cannot_parse_fails(tmp_path, monkeypatch, capsys):
    """A census that cannot read a file cannot vouch for it."""
    _repo(tmp_path, monkeypatch, {".github/workflows/bad.yml": "jobs: [unclosed\n"})
    assert shell_status.main([]) == 2
    assert "could not count" in capsys.readouterr().err


def test_a_shrunk_population_fails_rather_than_passes(monkeypatch):
    """**Non-empty accepts a shrink, and that is the whole of #228.**

    `main` refused an *empty* population and nothing else, so a pathspec
    that matched less rather than nothing reported `clean` and exited 0.
    Measured on the train before this changed:

        control                        clean across 60 source(s)   exit 0
        keep one workflow of three     clean across 41 source(s)   exit 0

    A 56% loss, reported as success. This holds the other direction: the
    population still returns plenty, and the run must still refuse.
    """
    whole = shell_status.population()
    kept = [s for s in whole if s.path != ".github/workflows/ci.yml"]
    assert kept and len(kept) < len(whole), "the mutation must actually shrink something"

    monkeypatch.setattr(shell_status, "population", lambda: kept)
    assert shell_status.main([]) == 2, (
        "a population missing an entire workflow file still reported success"
    )


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
        encoding="utf-8",
        errors="replace",
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
