**One shipped figure was wrong and is corrected.** ARC-AMPE's README said
*95 of the 402 guidance cells say there is no guidance*. The catalog has
**96**, and so does CMS's published workbook. The same figure was wrong
in the loader's own module docstring.

**Three catalog READMEs now have their numbers held to their catalogs** —
`arc-ampe`, `fedramp` and `nist-800-53-r5`. The other five already did.
These files ship inside the wheel, so a stale number reaches a reader who
has no way to check it against anything.

Nothing else changes: `fedramp` and `nist-800-53-r5` were accurate, and
are now checked rather than merely correct.

**FedRAMP's figures are the ones worth knowing are subtle.** `19` counts
parameter *values*, not the entries carrying them — there are 15 of
those. `the 79 controls FedRAMP tailors` is a union: 85 items exist, and
79 carry at least one of the two things a profile adds. Reading either
number the obvious way gives the wrong answer, and both are now pinned
with the reasoning beside them.
