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

**Whether this changes anything for you.** If every note in your vault
parses, `etl-vault` exits 0 exactly as before and writes the same file.
Nothing else changes for you.

**If some note does not parse, the run now fails where it used to
succeed — and the catalog it was writing was already short.** This is
the uncomfortable half: you may run 1.6.1 against a vault that has been
working for months and be told it is incomplete. Nothing got worse. The
notes that fail today were failing before, silently, and the
`controls.json` you have been generating has been missing them the whole
time. The new exit code is the first time anything has said so, and the
names it prints are the notes to fix.

**An empty `Controls/` directory is now an error rather than a success.**
`--controls-dir` pointing one level too high, or at a vault that stores
notes under another extension, produced `Parsed 0 controls` and exit 0.

**Nothing is written unless every note parsed, and this is the part that
protects a file you already have.** `--out` defaults to a path inside
`data/frameworks/`, so a mistyped `--controls-dir` used to overwrite a
good catalog with `[]` before reporting the problem. A run that cannot
read the whole vault now leaves the previous file exactly as it was and
names the notes to fix. **A catalog short by ten controls loses the same
ten as an empty one and looks healthier doing it**, so a partial result
is discarded rather than committed.
