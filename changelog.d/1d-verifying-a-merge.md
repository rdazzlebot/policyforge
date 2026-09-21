**Wrote down the verification idioms that answer the wrong question**, in
`docs/verifying-a-merge.md`, where someone checking a merge will meet them
rather than in four people's memories.

`git branch --merged` and `merge-base --is-ancestor <branch>` are blind to
squash merges, and two long-since-merged branches report `NO`. **And the flag answers a question you did not ask** — with no argument it
means *merged into this clone's current HEAD*, not into main. On one clone
at one instant that is 6 against 3, unchanged by pruning; and the 3 are
`origin/HEAD`, `origin/main` and an unrelated branch, so the real count of
merged feature branches is **zero**.

**The content check that was proposed as the remedy does not work either**,
which is measured here rather than assumed: diffing a merged branch's own
files against main reports 459 insertions, because later work touched the
same files. What works is asking GitHub for the merge commit and testing
*that* for ancestry — which correctly reports #168 as merged and **not** in
main, the stranding that had to be recovered as #169.

**And content-checking works too — from the reviewed SHA rather than the
branch head.** `git diff <reviewed-sha> <merge-commit>` over the reviewed
files comes back empty when what was approved is what landed. **Ancestry
says *something* landed; the content diff says *what* landed**, so use
both. The reviewed SHA survives nowhere except the review that recorded it.

**And "not an ancestor of main" is two different facts**, so the document
answers in three states rather than a boolean: *landed*, *pending* (the
base has not merged yet — says nothing), and *stranded* (the base merged
and did not carry it). During a release train seven of the ten most
recently merged PRs are not ancestors of main and every one is healthy.
