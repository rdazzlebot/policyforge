**`scripts/check.py` now runs the changelog-fragment check that CI
requires.** It did not, so a fragment CI rejects passed the pre-push gate
green — observed live: the gate reported 2,921 tests and every check
passing while CI was red.

**A gate a required check can fail behind is not a gate**, it is a subset
someone has to remember is a subset. The new check is deliberately not
skippable: the other skips exist because a tool may be absent, and this one
is a script in this repository, so *"it did not run"* has no honest cause.

A test now derives the required scripts from `ci.yml` rather than listing
them, so a script added to CI later is covered without anyone remembering
the test exists.
