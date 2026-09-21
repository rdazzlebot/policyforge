**`policyforge etl-vault` no longer reports a file count as a control
count, and no longer exits 0 on a vault it could not read.** It now
prints `Parsed N of M control note(s)` and fails when any note could not
be parsed, naming each one.

**The defect it fixes was silent in both directions.** Every field in the
note parser had a default, so an empty `.md` file became a control whose
ID was taken from its *filename*, with no title and no statement. Five
real notes plus two empty files reported `Parsed 7 controls` and exited
0, and the resulting `controls.json` loaded back without complaint. A
vault where every note failed was indistinguishable from a vault with no
notes.

**Whether this changes anything for you.** If `etl-vault` has been
exiting 0 for you, it still will and the output file is unchanged. If it
has been quietly skipping notes, the next run says which ones and fails
— **you may find a catalog you already have is short**, which is the
point: that was already true and nothing said so.

**An empty `Controls/` directory is now an error rather than a success.**
`--controls-dir` pointing one level too high, or at a vault that stores
notes under another extension, produced `Parsed 0 controls` and exit 0.
