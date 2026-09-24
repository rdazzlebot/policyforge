**`etl-hitrust` now says when a rendered report loses text.** Reading an
HTML or MHTML export can discard requirement text in two ways, and until now
it did so silently. The record count did not change and nothing was printed:

- a row of text with no label, such as a long cell continued onto the next
  page without its label reprinted, was skipped;
- a requirement statement that arrived as two different copies, such as one
  split across a page break with its label reprinted, kept the longer copy
  and dropped the other.

Both are now reported as `warn` lines in the import summary, with the count
and the first few pieces of text lost, so an export that hits either shape
says so on its first run. **What is read has not changed**: which copy of a
statement is kept is the same as before. PolicyForge has never seen a real
export in either shape, and changing the parse on a guess about a licensed
format would alter a customer's catalog with nothing to check it against. A
field left empty, a spacer row, and a statement printed twice identically
are not reported, because nothing is lost. A page title, page number or
print date that sits in a cell of its own **is** counted, because it cannot be
told apart from a continuation for certain. The warning splits the count into
rows that look like page furniture and rows that do not, and shows the second
kind first, so real lost text is not hidden behind page footers.

The CSV and Excel exports are unaffected. They remain the better choice where
you have one.
