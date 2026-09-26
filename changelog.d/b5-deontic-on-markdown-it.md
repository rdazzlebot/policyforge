**`policyforge check` no longer counts a list number as a sentence.** A
numbered step, `1. Open the console`, was read as two sentences: `1.` and
`Open the console`. In the 45 generated Procedures we measured, 4,133 of
8,972 statements were such numbers. They changed no finding, because a
number binds nothing, but every figure divided by the number of statements
was diluted by them. A number glued to the end of the sentence above it
(`... broadcasting. 1.`) is gone too, and so is a section number opening a
paragraph (`6.2. The organization must ...`): 426 of them in the 83
generated Standards.

**A numbered list after a colon now reads like a bulleted one.** In "The
business associate will:" followed by numbered items, the lead-in and its
items are read together for their citations, as they already were for `-`
items. In the 83 generated Standards we measured, that removed two "binds
but cites nothing" warnings on lead-ins whose items carry the citation, and
six weakened-citation warnings on items that are part of the obligation
above them. It added one warning that is correct: a separate uncited
obligation in the same section.

`policyforge check` now takes a document's structure (headings, lists,
paragraphs and breaks) from a CommonMark parser, not its own patterns.
Across those 128 documents, nothing else it reports changed. Four shapes
none of them contains do change: a code block is read on its own, not
joined to the paragraph before it; a `#` line inside a code block is no
longer taken for a heading; a heading inside a list item (`- ## ...`)
is checked like any other heading; and a `## ...` line indented four
spaces is code, read as a sentence, not a heading.
