**A changelog fragment that could never be published is now refused instead
of ignored.** `changelog.d/` entries are `.md` files; a file saved there
with any other extension was silently skipped — it committed, passed the
gate, passed CI, and its entry simply never appeared in the release. Nothing
anywhere said a file had been ignored. The check now names it.

**Two heading rules changed, in opposite directions.** A fragment beginning
with `# ` was accepted although it splits the release section exactly as
`## ` does; both are now refused, by heading level rather than by the
literal characters. And a `##` inside a fenced code block was refused
although it is an example rather than structure, so a fragment documenting
the changelog format could not be written; fenced blocks are now skipped.
`###` and deeper were legitimate before and still are.

**Nothing changes for a fragment that was already correct**, and the
existing rules — no empty file, no CR — are untouched.
