**Three printed commands no longer break when a value contains a space.**
`policyforge` prints commands for you to copy, and three of them
interpolated a value without quoting it:

- `etl-hitrust` and `etl-workbook` print
  `generate-parser --framework … --sample <your export>`. A HITRUST
  export is normally named something like `MyCSF Assessment Export.xlsx`,
  and the printed command split it into three arguments — so the command
  offered as the remedy could not run.
- `zardoz satisfies` prints `crosswalk seed --framework … --controls …`.
  A framework name or catalog path containing a space did the same.
- `history` prints a `--diff` hint naming two versions.

**What changes for you: a printed command now runs as printed.** Nothing
about the commands themselves changed, only the quoting, so anything
that worked before still works.

**The guard behind it now asks a different question.** It used to look
for an interpolated value inside hand-written quotes — the shape where a
quote character truncates a command and names the wrong document. It now
asks whether the value was quoted at all, which covers both that shape
and the one above, where an unquoted value adds arguments instead of
losing them.
