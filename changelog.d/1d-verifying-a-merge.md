**Wrote down the verification idioms that answer the wrong question**, in
`docs/verifying-a-merge.md`, where someone checking a merge will meet them
rather than in four people's memories.

`A && B` is not a gate when A is a question — a status query exits 0
whichever answer it gives. `git branch --merged` and
`merge-base --is-ancestor <branch>` are blind to squash merges: **4 of this
repository's 26 branches report merged**, and two long-since-merged branches
report `NO`. `gh pr merge` merges into the PR's own base and reports success
when that base has already landed. A `git fetch` into an existing ref can
decline silently, leaving everything downstream correct about the wrong
object. And `release_check.py` reads the tap through a CDN that served the
previous version twelve polls after a release.

**The content check that was proposed as the remedy does not work either**,
which is measured here rather than assumed: diffing a merged branch's own
files against main reports 459 insertions, because later work touched the
same files. What works is asking GitHub for the merge commit and testing
*that* for ancestry — which correctly reports #168 as merged and **not** in
main, the stranding that had to be recovered as #169.
