**`/coverage` no longer tells 800-171 users to build a mapping NIST already
publishes.** Its zero row for NIST 800-171 said *"no published crosswalk
yet"* and suggested `crosswalk seed` to start one. NIST's own source for this
catalog links every rev 3 requirement to its 800-53 controls, so the advice
was to rebuild by hand something the publisher provides — and a hand-made
mapping competes with the source's.

The row now says what is true: NIST publishes the mapping, this release does
not read it, and **the zero is a gap in PolicyForge, not in the source.** It
suggests nothing to run, because nothing a user can run reads those links yet.

The note above the rows changed too. It sorted every zero into two kinds and
had no place for one the source publishes that this release does not yet read;
the rows now name that kind among the others.

**Nothing else changes.** The 800-171 figures are the same, and `crosswalk seed` still accepts 800-171 if you choose to
run it; the report simply no longer recommends it.
