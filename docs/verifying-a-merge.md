# Verifying a merge

Shell and git idioms used for verification here that **answer correctly and
are read as answering something else.** Every one below caused a real error.

**Every figure here is a fact about a moment**, measured at `origin/main` =
`599bb8b`. Some are facts about a *clone* rather than about the repository,
which is said where it applies. **Re-derive before quoting.**

## `A && B` is not a gate when A is a question

```
gh pr view 151 --json mergeStateStatus … && gh pr merge 151 --squash …
```

printed `state=UNSTABLE … 2x IN_PROGRESS` — **as output of the invocation
that had already merged.**

`&&` stops B on A's **exit code**, and a status query exits 0 whichever
answer it gives. The construct reads as sequencing and is a concatenation.

`--match-head-commit` looks like the guard and is not: it binds the SHA, so
it protects against the head moving and says nothing about whether checks
finished.

The same shape reaches beyond git. `cmd | tail` takes `$?` from `tail`.
A gate script and the push that follows it are two statements, and nothing
consumes the exit code unless you write `gate && push`.

> **Read the answer in its own call.** If a question and an action are on one
> line, the action is not gated.

## "Merged" and "in main" are different facts

Squash merges rewrite the commit, so **a merged branch's tip is never an
ancestor of main.** Measured here:

```
origin/1d/coverage-scope            ancestor-of-main = NO   (#149, merged)
origin/1d/citable-framework-names   ancestor-of-main = NO   (#146, merged)
```

**And the count from `git branch -r --merged` is not a property of the
repository at all — it is a property of your clone.** Three readings of one
question, hours apart, against the same remote:

```
4 of 26      an earlier draft of this document
2 of 25      another session, its own clone
3 of 25      this clone, immediately after `git fetch --prune`
```

Remote-tracking refs linger until someone prunes, and every clone prunes on
its own schedule. **An instrument whose answer depends on when you last
fetched is reporting your housekeeping, not the branches.** That is the
sharpest form of this document's subject, and three people measuring and
disagreeing is what found it.

**The durable statement, which does not drift:** every squash-merged branch
reports unmerged, so **the flag's count is a lower bound and never the
answer.** Sampled across ten merged PRs: nine are genuinely ancestors of
main; the flag names three branches. Prefer that sentence to any count.

`git merge-base --is-ancestor <reviewed-sha> origin/main` agrees with the
flag and is wrong for the same reason. **Both fail toward alarm**, so a
cleanup driven by them keeps merged branches forever — the opposite of the
mistake people expect.

### The content check is not a fix either

The obvious remedy — diff the branch's own files against main and call an
empty diff *landed* — **does not survive main moving.** Measured on the two
branches above, both long since merged:

```
git diff --shortstat origin/1d/coverage-scope origin/main -- <its own files>
  -> 3 files changed, 459 insertions(+), 47 deletions(-)   reads as NOT LANDED
```

Measured at `origin/main` = `599bb8b`. **The figure moves as main moves; the
sign does not.** Re-derive rather than quoting this one.

Later work touched the same files. The check is sound only when nothing else
has, which in an active repository is rarely true and never checkable from
the diff itself.

### A branch head is not what was merged either

The next remedy after the content check is to diff the branch against its
own merge commit. **That fails too, and for a reason worth knowing.**

```
#149  merge commit  16eee00d   committed 10:58
      branch head   bc622fec   committed 11:01     three minutes LATER

commits on the branch and not in the merge:
  bc622fe  Guard the population the zero-row test loops over
  3af68b9  Cover the zero-row else-branch, and stop splitting on full stops
  b27c921  Scope /coverage to the set the registry anchors to
```

**The branch kept moving after it was merged** — `bc622fe` went on to become
#151. So a branch head is whatever was last pushed, which may be more, less
or different from what landed. **It is not a stable identifier for anything.**

Found by policyforge-80 while testing its own recommendation rather than
defending it.

### Content IS checkable — from the reviewed SHA, not the branch head

Both failures above share one cause, which this document named and did not
act on: **the branch head is not a stable identifier.** Start from one that
is — the SHA that was actually reviewed — and content-checking works.

```
git diff --stat <REVIEWED-SHA> <merge-commit> -- <the reviewed files>
```

Measured on #149, the same PR as both failures:

```
branch-head  vs main            459 insertions, 47 deletions
branch-head  vs merge-commit      3 insertions, 12 deletions
3af68b97     vs merge-commit    EMPTY
```

`3af68b97` is the commit the squash was built from. **Empty means exactly
what was reviewed is exactly what landed** — which is a different and
stronger statement than *something landed*.

**Ancestry says something landed. Content says what landed.** Use both: the
merge commit's ancestry proves it reached main, and this diff proves it is
the thing you read.

**And this is where the review convention earns its keep.** The reviewed
SHA is not recoverable from the branch — the branch has moved — nor from
the merge commit, which is a new object. It is recoverable from the
`Reviewed-SHA:` line, which exists precisely because nothing else records
it. **A review line that names a fabricated or abbreviated SHA destroys the
only proof that what was approved is what shipped.**

Found by policyforge-80, which read this document and noticed that it
proves content-checking impossible while its own two failures shared a
cause it had already identified.

### What actually works

Ask GitHub for the merge commit, then test *that* for ancestry:

```
gh pr view <N> --json mergeCommit -q .mergeCommit.oid
git merge-base --is-ancestor <that-sha> origin/main
```

```
#149   MERGED   16eee00   ancestor-of-main = YES
#146   MERGED   17fd4c6   ancestor-of-main = YES
#168   MERGED   6b7a295   ancestor-of-main = NO    <-- stranded
```

**#168 is why this matters.** It was merged into its own stacked base after
that base had landed, so `gh pr merge` reported success and the content
reached nothing. `state=MERGED` was true the whole time. It had to be
recovered by cherry-picking onto a fresh branch as #169.

> **`MERGED` is a fact about a pull request. Being an ancestor of main is a
> fact about the release.** Check both.

Locally, without the API, the squash subject carries the number:

```
git log origin/main --oneline --grep="(#149)"
  16eee00 Scope /coverage to the set the registry anchors to (#149)
```

## `gh pr merge` merges into the PR's own base

A stacked PR merged after its base has landed goes somewhere irrelevant
**and reports success.** `--match-head-commit` binds the head and says
nothing about the destination.

> **Check `baseRefName` before merging**, not only the head.

## A `git fetch` into an existing ref can be a no-op

```
git fetch origin pull/N/head:refN
```

git declines the non-fast-forward, and everything downstream is then
correct about the wrong object. **A diff against a stale ref looks equally
clean.**

> Always `--force`, and verify against `gh pr view --json headRefOid` rather
> than against the ref you just asked for.

## A staleness check that reads a cache

`release_check.py` fetches the tap formula from `raw.githubusercontent.com`.
During the v1.6.0 cut that served `v1.5.0` twelve polls after `v1.6.0` was
pushed, while a `git clone` said `v1.6.0`:

```
git ls-remote tap refs/heads/main          605e00a
git clone --depth 1  -> Formula/*.rb       v1.6.0
raw.githubusercontent.com/.../*.rb         v1.5.0   <- what the check read
```

**`brew tap` clones the repository; it does not read the CDN.** So the check
read something no user reads, through a cache with its own propagation
delay. It reported a correct release broken — and with different timing it
would report a broken one fine.

> **Read the artefact the user receives, by the route they receive it.**

## The shape they share

Each is an instrument giving a correct answer to a question nobody asked,
and each is read as having answered the question that mattered. That is the
same substitution as a cheap check standing in for an expensive one: **a
skipped check leaves a gap, a substituted one leaves a false assurance.**

When an instrument disagrees with your expectation, the first question is
not *which is wrong* but **what exactly did this measure.**
