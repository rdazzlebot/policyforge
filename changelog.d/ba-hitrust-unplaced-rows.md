**`etl-hitrust` now accounts for every cell of text in a rendered report.**
Each cell is either read into the catalog, part of a row that deliberately
carries nothing, or reported. The rows that carry nothing are a heading such
as "Level 1 | Implementation Requirements" for a level the report uses, a
label left empty, and "Topics:", which PolicyForge knows and does not keep.
Anything else is reported by default, so text in a shape PolicyForge does
not know shows up as a warning instead of disappearing.

Five ways of losing text were silent until now, and in the first the record
count dropped with no explanation:

- a row whose label is not second-to-last, such as a label, its text and
  then an extra cell, was misread, skipped, and took the whole level record
  it would have opened with it;
- a row whose label PolicyForge does not recognise, with or without a
  trailing colon, was skipped with its text;
- a statement label with no level in it, such as "Implementation:", was
  recognised and then dropped;
- a level row that came before any "Control Reference:" had nowhere to go
  and was dropped;
- a cell in front of a label and value was ignored while the row around it
  was read.

All are now `warn` lines in the import summary, showing the text. **What is
read has not changed**: PolicyForge has never seen a real export in any of
these shapes, so the warning is the evidence a later fix would need.
