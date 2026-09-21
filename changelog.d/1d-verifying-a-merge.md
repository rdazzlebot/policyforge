**Wrote down the verification idioms that answer the wrong question**, in
`docs/verifying-a-merge.md`, where someone checking a merge will meet them
rather than in four people's memories.

`git branch --merged` and `merge-base --is-ancestor <branch>` are blind to
squash merges, and two long-since-merged branches report `NO`. **The count
itself is a property of your clone rather than of the repository** — three
sessions measured it hours apart and got 4 of 26, 2 of 25 and 3 of 25,
because remote-tracking refs linger until someone prunes.

**The content check that was proposed as the remedy does not work either**,
which is measured here rather than assumed: diffing a merged branch's own
files against main reports 459 insertions, because later work touched the
same files. What works is asking GitHub for the merge commit and testing
*that* for ancestry — which correctly reports #168 as merged and **not** in
main, the stranding that had to be recovered as #169.
