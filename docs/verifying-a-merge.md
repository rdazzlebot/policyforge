# Verifying a merge

Shell and git idioms used for verification here that **answer correctly and
are read as answering something else.** Every one below caused a real error,
and the figures are measured on this repository rather than quoted.

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
branches reported merged by `git branch -r --merged origin/main`     4
remote branches                                                     26

origin/1d/coverage-scope            ancestor-of-main = NO   (#149, merged)
origin/1d/citable-framework-names   ancestor-of-main = NO   (#146, merged)
```

`git merge-base --is-ancestor <reviewed-sha> origin/main` agrees with the
flag and is wrong for the same reason. **Both fail toward alarm**, so a
cleanup driven by them keeps merged branches forever — the opposite of the
mistake people expect.

### The content check is not a fix either

The obvious remedy — diff the branch's own files against main and call an
empty diff *landed* — **does not survive main moving.** Measured on the two
branches above, both long since merged:

```
git diff --stat origin/1d/coverage-scope origin/main -- <its files>
  -> 459 insertions, 47 deletions     reads as NOT LANDED
```

Later work touched the same files. The check is sound only when nothing else
has, which in an active repository is rarely true and never checkable from
the diff itself.

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
