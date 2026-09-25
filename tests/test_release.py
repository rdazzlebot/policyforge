"""`scripts/release.py`: the cut as gated steps (#255).

The engine is tested with synthetic steps and spies, so every claim in the
script's contract is shown to hold and to FAIL when it should: a dry run
never acts, a failed gate stops before acting, an outward step needs its
key typed, the wait for the user's merge stops and resumes. The real step
list is tested for its order and for what it must never do.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import release
from release import ACT, CHECK, WAIT, Check, Context, Step, run_steps


def _ctx(**kw) -> Context:
    ctx = Context(version="9.9.9", run=lambda argv: subprocess.CompletedProcess(argv, 0, "", ""))
    for key, value in kw.items():
        setattr(ctx, key, value)
    return ctx


def _step(key, kind=ACT, *, gate=True, post=False, outward=False, acted=None, post_after=True):
    """A synthetic step; `acted` collects the keys of steps whose action ran."""
    state = {"acted": False}

    def act(ctx):
        state["acted"] = True
        if acted is not None:
            acted.append(key)

    def post_fn(ctx):
        return Check(post_after if state["acted"] else post, [f"{key} post"])

    return Step(
        key,
        key,
        kind,
        lambda c: Check(gate, [f"{key} gate"]),
        post_fn,
        act if kind == ACT else None,
        outward=outward,
        would=f"do {key}",
    )


def _lines():
    out: list[str] = []
    return out, out.append


# --- the engine -----------------------------------------------------------------


def test_a_dry_run_never_acts_and_says_how_far_it_reached():
    acted: list[str] = []
    steps = [_step("a", CHECK), _step("b", acted=acted), _step("c", acted=acted)]
    out, emit = _lines()
    assert run_steps(steps, _ctx(), execute=False, out=emit) == 0
    assert acted == []
    text = "\n".join(out)
    assert "reached 2 of 3" in text and "not reached: c" in text


def test_a_failed_gate_stops_before_acting_with_the_steps_code():
    acted: list[str] = []
    steps = [_step("a", acted=acted), _step("b", gate=False, acted=acted), _step("c", acted=acted)]
    assert run_steps(steps, _ctx(), execute=True, out=lambda s: None) == 12
    assert acted == ["a"], "b's gate failed, so neither b nor c may act"


def test_an_outward_step_needs_its_key_typed():
    acted: list[str] = []
    steps = [_step("tag", outward=True, acted=acted)]
    wrong = _ctx(confirm=lambda prompt: "yes")
    assert run_steps(steps, wrong, execute=True, out=lambda s: None) == 6
    assert acted == []
    right = _ctx(confirm=lambda prompt: "tag")
    assert (
        run_steps(
            [_step("tag", outward=True, acted=acted)], right, execute=True, out=lambda s: None
        )
        == 0
    )
    assert acted == ["tag"]


def test_the_wait_stops_and_a_rerun_after_it_resumes():
    """The user's merge: exit 5 until it has happened; afterwards the
    already-done steps are skipped and the rest run."""
    acted: list[str] = []
    before = [_step("a", acted=acted), _step("main", WAIT, post=False), _step("c", acted=acted)]
    assert run_steps(before, _ctx(), execute=True, out=lambda s: None) == 5
    assert acted == ["a"]
    acted.clear()
    after = [
        _step("a", post=True, acted=acted),
        _step("main", WAIT, post=True),
        _step("c", acted=acted),
    ]
    assert run_steps(after, _ctx(), execute=True, out=lambda s: None) == 0
    assert acted == ["c"], "a and main were already done, so only c acts"


def test_a_failed_postcondition_is_its_own_code():
    steps = [_step("a"), _step("b", post_after=False)]
    assert run_steps(steps, _ctx(), execute=True, out=lambda s: None) == 42


# --- the real step list -----------------------------------------------------------


def _keys():
    return [s.key for s in release.steps()]


def test_the_order_is_the_procedure():
    """Two install tests (the user's ruling on #255): the branch archive
    before the tag, the candidate formula before publishing, the published
    one last."""
    keys = _keys()
    order = [
        "train-final",
        "changelog",
        "version",
        "release-pr",
        "main",
        "branch-install",
        "tag",
        "candidate-install",
        "publish",
        "release-check",
    ]
    assert [k for k in keys if k in order] == order


def test_outward_steps_are_exactly_the_ones_that_leave_this_clone():
    outward = {s.key for s in release.steps() if s.outward}
    assert outward == {"release-pr", "tag", "publish"}


def test_the_user_merges_main_and_the_script_never_does():
    main = next(s for s in release.steps() if s.key == "main")
    assert main.kind == WAIT and main.act is None
    source = (Path(release.__file__)).read_text(encoding="utf-8")
    assert '"merge"' not in source and "'merge'" not in source, "no `gh pr merge` anywhere"


def _fake_run(responses):
    """argv -> CompletedProcess, by the first matching substring of the joined argv."""

    def run(argv):
        joined = " ".join(argv)
        for needle, (code, out) in responses.items():
            if needle in joined:
                return subprocess.CompletedProcess(argv, code, out, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    return run


def test_the_tag_step_refuses_until_a_branch_install_has_passed():
    tag = next(s for s in release.steps() if s.key == "tag")
    ctx = _ctx(run=_fake_run({}))
    assert not tag.gate(ctx).ok
    ctx.notes["branch install"] = "passed"
    assert tag.gate(ctx).ok


def test_after_tagging_the_branch_install_counts_as_done():
    """Resume fix: branch-install's own gate needs NO tag, so without this a
    re-run after the tag step would stop at branch-install."""
    step = next(s for s in release.steps() if s.key == "branch-install")
    tagged = _ctx(run=_fake_run({"ls-remote --tags origin v9.9.9": (0, "abc\trefs/tags/v9.9.9")}))
    assert step.post(tagged).ok
    untagged = _ctx(run=_fake_run({}))
    assert not step.post(untagged).ok


def test_the_milestone_must_be_zero_by_both_instruments():
    def ctx(rest, search):
        return _ctx(
            run=_fake_run(
                {
                    "milestones": (0, '[{"title": "9.9.9", "number": 7}]'),
                    "issues?milestone=7": (0, rest),
                    "search/issues": (0, search),
                }
            )
        )

    assert release._milestone_open(ctx("0", "0")).ok
    assert not release._milestone_open(ctx("0", "3")).ok, "REST alone at 0 is the false zero"
    assert not release._milestone_open(ctx("", "0")).ok, "an unanswered instrument is not 0"


def test_resources_must_equal_the_lock(tmp_path, monkeypatch):
    lock = tmp_path / release.release_check.LOCK
    lock.parent.mkdir(parents=True)
    lock.write_text("click==8.1.7 \\\n    --hash=sha256:x\n", encoding="utf-8")
    # The real formula's shape: two-space indent, as `release_check._RESOURCE_RE` requires.
    formula = '  resource "click" do\n    url "https://files/click-8.1.7.tar.gz"\n'
    ctx = _ctx(root=tmp_path)
    ctx.notes["candidate_formula"] = formula
    assert release._resources_match_lock(ctx).ok
    ctx.notes["candidate_formula"] = formula.replace("8.1.7", "8.2.0")
    assert not release._resources_match_lock(ctx).ok
    ctx.notes["candidate_formula"] = "no resources here"
    assert not release._resources_match_lock(ctx).ok, "an empty set is not a match"


@pytest.mark.parametrize("bad", ["1.6", "v1.6.1", "1.6.1-rc1"])
def test_a_version_that_is_not_x_y_z_is_refused(bad):
    assert release.main([bad]) == 2


def test_after_the_cut_commit_the_tree_check_accepts_the_release_head():
    """Resume fix: once the cut is committed, HEAD is the release PR's head,
    not the train's remote tip, and a re-run must not stop at clean-tree."""

    def ctx(pr_head):
        return _ctx(
            run=_fake_run(
                {
                    "rev-parse --abbrev-ref HEAD": (0, "release/9.9.9"),
                    "rev-parse origin/release/9.9.9": (0, "a" * 40),
                    "rev-parse HEAD": (0, "b" * 40),
                    "status --porcelain": (0, ""),
                    "pr list": (
                        0,
                        '[{"title": "Release 9.9.9", "state": "OPEN", '
                        f'"headRefOid": "{pr_head}"}}]',
                    ),
                }
            )
        )

    assert release._train_tree(ctx("b" * 40)).ok
    assert not release._train_tree(ctx("c" * 40)).ok, "HEAD is neither the train tip nor the cut"


def test_the_status_probe_refuses_anything_but_https(tmp_path):
    """urllib opens `file://`; the probe answers 0 without opening it. The
    file EXISTS, because a missing one raises OSError and reads 0 anyway,
    which would pass this test with the guard deleted."""
    target = tmp_path / "secret.txt"
    target.write_text("x", encoding="utf-8")
    assert release._real_status(target.as_uri()) == 0
    assert release._real_status("http://github.com/x") == 0


# --- #348 review: step 6 against the cut, the homepage, the two artefact gates ----


def _merged_ctx(pr_head: str, cut: str, merge_tree: str, cut_tree: str):
    return _ctx(
        run=_fake_run(
            {
                "pr list": (
                    0,
                    '[{"title": "Release 9.9.9", "state": "MERGED", '
                    f'"headRefOid": "{pr_head}", "mergeCommit": {{"oid": "{"m" * 40}"}}}}]',
                ),
                "merge-base --is-ancestor": (0, ""),
                "rev-parse HEAD": (0, cut),
                f"rev-parse {'m' * 40}^{{tree}}": (0, merge_tree),
                f"rev-parse {cut}^{{tree}}": (0, cut_tree),
            }
        )
    )


def test_step_six_accepts_the_merge_of_the_cut_commit():
    assert release._main_merged(_merged_ctx("c" * 40, "c" * 40, "t1", "t1")).ok


def test_step_six_refuses_a_head_pushed_after_the_cut():
    """policyforge-9b on #348: something pushed to the release branch after
    step 5 was merged, and the old check compared the merge with that PR head
    AS FETCHED NOW, which passes by construction. Against the cut commit this
    script made, it is refused, even if the trees happen to agree."""
    moved = _merged_ctx("d" * 40, "c" * 40, "t1", "t1")
    check = release._main_merged(moved)
    assert not check.ok
    assert any("is the cut commit" in line and "False" in line for line in check.measured)


def test_step_six_refuses_a_merge_whose_tree_is_not_the_cut():
    assert not release._main_merged(_merged_ctx("c" * 40, "c" * 40, "t1", "t2")).ok


def test_the_candidate_formula_names_the_owner_in_homepage_and_url(monkeypatch):
    published = (
        '  homepage "https://github.com/rdazzlebot/policyforge"\n'
        '  url "https://github.com/rdazzlebot/policyforge/archive/refs/tags/v1.6.0.tar.gz"\n'
        f'  sha256 "{"0" * 64}"\n'
    )
    monkeypatch.setattr(release.release_check, "fetch_formula", lambda url=None: published)
    formula = release._formula(_ctx(), release._tag_archive(_ctx()), "1" * 64)
    assert release.release_check.names_canonical_homepage(
        release.release_check.homepage_in_formula(formula)
    )
    assert release.release_check.names_canonical_owner(
        release.release_check.source_url_in_formula(formula)
    )


def _records_ctx(comments, closed=("2026-09-25T01:00:00Z",), tip="a" * 40):
    import json as _json

    lines = "\n".join(_json.dumps([created, body]) for created, body in comments)
    return _ctx(
        tracking=99,
        run=_fake_run(
            {
                "milestones": (0, '[{"title": "9.9.9", "number": 7}]'),
                "state=closed": (0, "\n".join(closed)),
                "issues/99/comments": (0, lines),
                "rev-parse origin/release/9.9.9": (0, tip),
            }
        ),
    )


def _review(handle, at="2026-09-25T02:00:00Z", version="9.9.9"):
    return (at, f"Reviewed.\n\nPost-zero-review: {version} reviewer=policyforge-{handle}")


def test_the_post_zero_review_needs_all_three_after_the_zero():
    assert release._post_zero_reviewed(
        _records_ctx([_review("80"), _review("5b"), _review("1d")])
    ).ok
    assert not release._post_zero_reviewed(_records_ctx([_review("80"), _review("5b")])).ok
    early = [_review("80"), _review("5b"), _review("1d", at="2026-09-25T00:30:00Z")]
    assert not release._post_zero_reviewed(_records_ctx(early)).ok, (
        "a review BEFORE the zero is not one"
    )
    other = [_review("80"), _review("5b"), _review("1d", version="9.9.8")]
    assert not release._post_zero_reviewed(_records_ctx(other)).ok, "another release's review"


def test_a_quoted_review_line_is_not_a_review():
    """The last-line rule: discussing a review must not create one.

    Pinned to exactly which reviewer is missing: a bare `not ok` also held
    under a "first line counts" mutant, because that one dropped 80's and
    5b's real reviews instead -- right answer, wrong reason."""
    quoted = (
        "2026-09-25T02:00:00Z",
        "Post-zero-review: 9.9.9 reviewer=policyforge-1d\n\nquoted above.",
    )
    check = release._post_zero_reviewed(_records_ctx([_review("80"), _review("5b"), quoted]))
    assert not check.ok
    assert check.measured[-1].endswith("['1d']"), check.measured


def test_the_notes_measurement_must_name_the_train_tip():
    def measured(sha, at="2026-09-25T02:00:00Z"):
        return (
            at,
            f"Re-measured.\n\nNotes-measured-SHA: {sha} release=9.9.9 reviewer=policyforge-9b",
        )

    assert release._notes_measured(_records_ctx([measured("a" * 40)])).ok
    assert not release._notes_measured(_records_ctx([measured("b" * 40)])).ok, (
        "before the last merge"
    )
    stale_last = [
        measured("a" * 40, at="2026-09-25T02:00:00Z"),
        measured("b" * 40, at="2026-09-25T03:00:00Z"),
    ]
    assert not release._notes_measured(_records_ctx(stale_last)).ok, "the LATEST record decides"


def test_the_artefact_gates_need_a_tracking_issue():
    assert not release._post_zero_reviewed(_ctx()).ok
    assert not release._notes_measured(_ctx()).ok


def test_the_artefact_gates_come_before_the_changelog():
    keys = _keys()
    assert keys.index("post-zero-review") < keys.index("changelog")
    assert keys.index("notes-measured") < keys.index("changelog")
    kinds = {s.key: s.kind for s in release.steps()}
    assert kinds["post-zero-review"] == CHECK and kinds["notes-measured"] == CHECK, (
        "a CHECK has no action, so --execute cannot satisfy it"
    )
