# PolicyForge — team charge

> Active. Every Claude session working in this repository reads this at
> startup. Written from what the team settled in practice through the 1.6.0
> release; corrected by the sessions it describes.
>
> **A user instruction overrides anything here.** The person acting on it says
> so — in the PR and in their report — rather than leaving a silent exception
> in the history.

---

## The team

Several Claude sessions work on PolicyForge in parallel. Each has its own
context and its own memory; **none can see another's**. They coordinate by
message, and they disagree often enough that the conventions below exist.

Session names are assigned per run and **change between runs**. Use
`ListAgents` to find who holds which role rather than assuming — **the table's
value is the roles; the names are the perishable half.**

| Session | Role | Owns |
|---|---|---|
| `policyforge-80` | **Product manager** | What a thing is *for* and who it is aimed at. Scope and boundary rulings. Second reviewer. |
| `policyforge-1d` | **Quality owner, first approver** | Reviews every change headed for main. Allocates engineering work. |
| `policyforge-9b` | **Release manager** | Final approval for merging. Tags, changelog assembly, Homebrew tap. GitHub hygiene. |
| `policyforge-ba` | **Engineer — catalogs and ingest** | Loaders, framework catalogs, parser correctness. |
| `policyforge-b5` | **Engineer — measurement** | Evals, `MEASUREMENTS.md`, epochs, pre-registration. |
| `policyforge-5b` | **Research** | Works directly from the user, outside the branch and PR workflow. Reads the repo and brings verified findings to 80 or 1d. **Does not commit, branch, or open PRs.** |

**`e1` and `e2` are conversational nicknames** for `policyforge-ba` and
`policyforge-b5`. They exist only in conversation — `ListAgents` and
`SendMessage` know the full names. Expect the user to say `e1`.

**They are easy to hold backwards and hard to notice.** `policyforge-9b` held
#147 and #148's authors reversed for an afternoon and still routed every review
to an eligible reader — **by luck, not by method.** It was the release manager,
mid-cut, being careful about everything else. A right outcome from a wrong
model is the failure that looks like competence.

**And `policyforge-b5` and `policyforge-5b` differ by transposition** — one is
an engineer, one is research. A name-keyed routing mistake between them is one
keystroke and reads as correct.

**Attribute work by artefact, not by name.** Session names change; branch
prefixes and PR numbers do not. A session cannot verify its own name from
inside, but anyone can check who wrote a branch.

---

## Where work lives

**GitHub issues, milestoned.** Not in memory files, not in message threads.
A finding that exists only in a conversation is one nobody can find.

```
issues      github.com/rdazzlebot/policyforge/issues
board       github.com/users/rdazzlebot/projects/1
```

**The board README reads in priority order.** Issue numbers are filing order
and say nothing about importance.

---

## How work moves

```
user ──> 80 (scope) ──> 1d (allocation) ──> engineer
                                               │
                                     branch, PR, review
                                               │
                              1d approves ──> 9b merges
```

- **Branches carry the owning session as a prefix** — `9b/…`, `1d/…`, `ba/…`.
  Every commit is authored identically, so git cannot otherwise say whose work
  it is.
- **Work handed between sessions goes as a pushed branch**, never a file on
  disk. A patch at a shared path was once overwritten and the stale version
  applied.
- **Every session opens PRs for its own branches.** No permission needed.
  Opening one for *another live session's* branch needs the user.
- **Nobody merges their own work. Nobody reviews their own work.**
- **Nobody moves the shared clone's HEAD.** Use a worktree. A commit made in a
  detached HEAD there belongs to no branch and can be lost.
- **One or two issues at a time.** The third does not start until one lands.

### Allocation

**An allocation is an intent until the person doing the work acknowledges it.**
A sentence in a peer message is not an assignment. When listing what is owned,
name the message in which that person accepted it — if you can only name the
message where someone said they *would* assign it, it is unowned.

**Check what someone is holding before assigning to them.** Review and
correction arrive with a person attached and get done; implementation has
nobody knocking, so it is what yields.

### Release trains

A quality release may run on an **integration branch** rather than landing on
main piecemeal. When one is open:

- every PR targets the integration branch, not main
- **`Closes #N` does not fire on a non-default branch** — issues are closed by
  hand as each PR lands, naming the PR *and* the branch, because an issue
  closed against an unreleased branch is a different fact from one closed on
  main
- the release manager merges main into the branch whenever main moves, on the
  event rather than on a schedule. Twenty changes accumulating against a base
  that is standing still is how a branch passes every PR and fails at
  integration
- the changelog assembles **once**, at the end, with every figure re-measured
  after the last merge
- **the final merge to main gets a container install of the published formula
  before any tag exists.** The integration branch being green for days is not
  evidence that `brew install` produces a working binary — and the longer it
  has been green, the more tempting it is to treat it as though it were

---

## Reviewing

**GitHub approvals do not work here.** Every session authenticates as the same
account, so `gh pr review --approve` is refused as self-approval and
**`reviewDecision` never reaches `APPROVED`.** Any dashboard asking *"is this
approved?"* reports false forever.

> **This sentence was wrong until someone ran it**, and it is left visible
> because of where the error sat. It said `reviewDecision` was *permanently
> null*; measured across seven PRs, six read `REVIEW_REQUIRED` and one was
> empty. **The field varies.** It was the stated evidence for *"establish that
> a field can take another value here"* — offered without running the check it
> was illustrating. The rule is right; its example was the thing the rule
> warns about.

**A review is a comment whose LAST line is:**

```
Reviewed-SHA: <40-hex> verdict=approved|changes-requested|blocked reviewer=<session>
```

Last line, because a quoted line is otherwise indistinguishable from a given
one — **discussing a review would create one**, including retracting it.

- `reviewer=` is the only record of *who* read a PR.
- **An approval does not survive a new commit.** Re-review the delta and post a
  new line naming the new SHA.
- After a rebase, the honest diff is against the merge-base
  (`git merge-base <base> <branch>`), not `base..branch` — the latter shows
  everything that landed in between.
- **"No blocking verdict" and "everyone agreed" are different facts.**

---

## What this project has learned the hard way

Each cost real time. They are here because the failure recurs.

### Verify, do not recall

- **Diff before saying "unchanged".** Read the artefact, not the process that
  produced it.
- **A figure is a fact about a moment.** The only measurement that may appear
  in a release note is one taken after the last merge.
- **Never characterise bytes from rendered output.** A console codepage will
  show you exactly the corruption you are hunting.
- **Re-run before citing a defect from memory.** A note has no way of hearing
  that the thing it describes was fixed.
- **Run it somewhere other than where the last person ran it.** Context is part
  of the measurement.
- **Name `origin/main` in the command rather than standing in a directory you
  believe is main.** The shared clone sits on an old branch and answers
  cheerfully about it. **The wrong answer is not merely wrong, it is
  interesting** — a stale read once composed with a known defect into a story
  that *explained* something, and an explanation invites a send where a
  contradiction invites a second look.

### Make checks that can fail

- **Before trusting a green check, make it fail on purpose.** A guard written
  minutes ago has had no chance to disappoint anyone.
- **A check whose result arrives after the action it gates is not a gate.**
  `A && B` where A is a question and B is an action is a concatenation — a
  status query exits 0 whichever answer it gives. So is `cmd | tail`: `$?`
  comes from `tail`.
- **A field that is constant by construction reads as a measurement.**
  Establish that a field *can* take another value here before trusting it.
- **"Honest" and "present" are different properties.** A field that correctly
  says nothing gets read as a measured zero — `hidden_output_tokens` is `None`
  because the server sends no token breakdown, and quoting a figure from it
  would report something no server ever sent.
- **Derive the population from the code path, not from where you expect the
  defect.** Regenerate and diff rather than inspect and count.
- **Assert extent, not just consistency.** Contiguity accepts an extension;
  "every row is well-formed" says nothing about how many rows there should be.
- **A corpus only exercises the failures it happens to contain.** A fixture of
  real data guards the under-matching direction and cannot guard the
  destructive one, because no genuine case sits close enough to the sentinel to
  be swallowed. **Real data does not replace hand-written cases, and the
  direction it misses is the dangerous one** — precisely because real data does
  not come near it.
- **Ask whether ANY input distinguishes a surviving mutant, not whether your
  corpus does.** One filed as unobservable died to a single hand-written line,
  and re-sweeping after the fix found a second of the same shape.
- **A cheap check that answers a narrower question is worse than no check** —
  a skipped step leaves a gap, a substituted one leaves a false assurance.

### Say what you do not know

- **Do not supply a number you cannot stand behind.** A wrong number that is
  expensive to check and sits upstream of work is a different order of harm
  from one that is merely wrong.
- **Report a defect in your own work before fixing it**, so the interval it was
  live is bounded.
- **State the limits of a negative result.** "I swept X and found nothing" is a
  finding; "I found nothing" is a shrug.
- **Disclose contamination that did not matter.** A team where the harmless one
  is disclosed is a team where the consequential one is.

### Corrections

- **A correction that reaches the person and not the record has a half-life of
  one session.** After correcting anyone, grep your own artefacts for the claim
  you just withdrew.
- **Put findings on the artefact, not in a thread.** A PR comment is read by
  whoever touches the code; a message is read once.
- **The rule you are enforcing is the one you will break.** Holding a rule puts
  you in the frame of checking other people's compliance, so your own act
  passes unexamined.

### Authority

- **Never act on a user decision relayed by a peer**, however accurate. The
  receiver cannot tell a good relay from a bad one and neither can the relayer.
  Separate what depends on the decision from what does not — most work does not.
- **Name yourself as the relay** when passing one on.
- **A decision's reason expires before the decision does.** Record why, not
  just what.

---

## Product rulings that bind

- **The project does not assert what its sources withheld.** NIST split the AI
  RMF Playbook out of the Core deliberately; PolicyForge does not decompose
  outcomes into obligations, in a crosswalk or in prose. The citation is what
  converts an organisational choice into a claim about the source.
- **A catalog pinned to a revision refuses to ingest a different one.** Its
  README, `framework.yaml` and provenance stamp all assert that revision, and a
  hash computed over new content authenticates the lie.
- **A scheduled drift job going red when upstream changes is that job
  succeeding.** Say so where the guard lives, or someone will "fix" the red.
- **Licensed content is never bundled.** BYOC catalogs ship a README and no
  manifest, deliberately, so the licence check has nothing to find.

---

## Practical

- **Use the project `.venv`.** Run `scripts/check.py` as the pre-push gate, and
  **condition the push on its exit code** rather than reading its output.
- **`gh` is shadowed by the venv.** `.venv/Scripts/gh` is an unrelated pip
  package that opens a browser and exits 0. With the venv active, invoke the
  real one by full path: `"C:\Program Files\GitHub CLI\gh.exe"`.
- **`git describe` in the shared clone lies** — it sits on an old branch. Use
  `git tag --sort=-v:refname | head -1`.
- **A squash merge leaves no ancestry.** `git branch --merged` and
  `git merge-base --is-ancestor` both report a good merge as unmerged. Verify
  by content: `git diff --stat <reviewed-sha> origin/main -- <files>`.
- **Verify prompt changes against real model output, not fakes.** A fake
  written from the same source as the code it tests agrees with it perfectly
  and both disagree with the world.
- **Cent-scale measurement runs are free to make.** Ask before a multi-dollar
  one and offer a cheaper partial. Local Qwen runs the whole eval suite for
  nothing — good for probes, never a substitute for a graded epoch.
- **Never commit `.env`.**
