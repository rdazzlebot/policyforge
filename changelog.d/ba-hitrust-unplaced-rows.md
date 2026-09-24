**`etl-hitrust` now accounts for every row of a rendered report.** Each row
that carries text is either read into the catalog, one of a few rows that
deliberately carry nothing (a heading such as "Level 1 | Implementation
Requirements", a label left empty, or "Topics:", which PolicyForge knows
and does not keep), or reported. Anything else is reported by default, so a
row in a shape PolicyForge does not know shows up as a warning instead of
disappearing.

Four ways of losing text were silent until now, and in the first the record
count dropped with no explanation:

- a row with three or more cells whose label is not second-to-last, such as
  a label, its text and then an extra cell, was misread, skipped, and took
  the whole level record it would have opened with it;
- a row whose label PolicyForge does not recognise, with or without a
  trailing colon, was skipped with its text;
- a statement label with no level in it, such as "Implementation:", was
  recognised and then dropped;
- a level row that came before any "Control Reference:" had nowhere to go
  and was dropped.

All are now `warn` lines in the import summary, showing the text. **What is
read has not changed**: PolicyForge has never seen a real export in any of
these shapes, so the warning is the evidence a later fix would need.
