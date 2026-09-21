**`docs/verifying-a-merge.md` gains the three rules an audit of orphaned
commits produced**, two of which invert a reading people already have.

**Half of a shortstat is the opposite of a finding.** Diffing a commit
against its PR's merge commit is directional: *insertions* mean the merge
commit is a superset and nothing was lost; only *deletions* are lines the
merge did not carry. Read the wrong way, every cleanly-merged commit looks
like a loss.

**For changelog fragments, absent-from-main is what success looks like.**
Fragments are consumed and deleted at release, so a sweep for unlanded
content flags every shipped fragment as lost work.

And the method that survives both traps is written as four steps: find the
PR whose head the commit was, take its merge commit, diff over the commit's
own files, read deletions only. Not by subject — squash rewrites it — and
not against `origin/main`, which has moved. **Both wrong methods were tried
first and both gave confident false answers**, including 165 "unlanded"
lines in a commit that had been reviewed and approved into a merged PR.
