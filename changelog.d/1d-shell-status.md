**A green CI markdown check could have examined nothing.** `ci.yml` ran
`git ls-files -z '*.md' | xargs -0 mdformat --check`. GitHub's default shell
is `bash -e`, which does **not** set `pipefail`, so the step's exit status
came from `xargs` alone: measured, the same pipeline exits 0 under `bash -e`
and 1 with pipefail. If `git ls-files` failed, the step passed having
checked no files, and the green light read as "markdown is fine".

**Adding `set -o pipefail` closes half of it.** `mdformat --check` with no
paths prints *"No files have been passed in"* and exits 0, so a pathspec
that stops matching still reads as all-clean — and pipefail never fires,
because nothing failed. The step now asserts the file list is non-empty
before believing a clean result, and says how many files it checked.

**`scripts/shell_status.py` is the new check that finds both**, in the
pre-push gate and in CI. It derives what a shell will execute from
`git ls-files` rather than from a list, so a script added tomorrow is
covered by the check that exists rather than by someone remembering, and it
refuses to pass on an empty derivation — a check whose population can
silently become empty reports the absence of input as the absence of
problems, which is the defect it exists to find in other people's
pipelines.

It states what it **allows** as carefully as what it refuses:
capture-then-branch (`cmd > log 2>&1; rc=$?`), plain sequencing with no pipe,
and a pipeline whose right-hand side is the real work. Documentation
snippets are not required to set `pipefail` — a snippet is run by hand and
watched, a script runs unattended and is believed — but a snippet still
cannot pipe a status into a `&&`, because a reader who pastes it gets the
wrong outcome wherever it came from.

One known false positive is written down rather than papered over: the bad
shape inside a quoted string is reported, because `bash -c 'x | tail && y'`
cannot be told from `echo 'x | tail && y'` without a shell parser, and the
first one really does execute it.

Closes #215 and #216.
