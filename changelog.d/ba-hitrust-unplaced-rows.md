**`etl-hitrust` now reports two more ways a rendered report loses text.**
Both used to be silent, and in the first the record count dropped with no
explanation:

- a row with three or more cells whose label is not second-to-last, such as
  a label, its text and then an extra cell, was misread, skipped, and took
  the whole level record it would have opened with it;
- a row whose caption ends in a colon but is not a label PolicyForge
  recognises was skipped with its text.

Both are now `warn` lines in the import summary, showing the row. **What is
read has not changed**: PolicyForge has never seen a real export in either
shape, so the warning is the evidence a later fix would need. A third cell in
front of the label, a heading row such as "Level 1 | Implementation
Requirements", and a label PolicyForge knows and deliberately does not keep,
such as "Topics:", are not reported, because nothing is lost.
