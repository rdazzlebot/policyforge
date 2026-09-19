**Nothing user-facing.** `CONTRIBUTING.md` now says how to suppress a
`bandit` or `semgrep` finding: put the marker on the offending line,
state the bound rather than asserting a false positive, name the premise
a future change could break, and test rather than silence when two
scanners flag the same line.
