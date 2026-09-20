**Fixed a parser guard that could never fire.** The AI RMF row pattern
enumerated the four function names inside the identifier capture, so the
`unrecognised AI RMF function` check could not be reached: a fifth NIST
function did not raise, the row simply **failed to match and vanished**,
and the reader got a confusing complaint about category numbering instead.

The pattern now captures any capitalised word and lets the guard do its job.
A page carrying `Sustain 1` reports *"unrecognised AI RMF function(s):
['Sustain']"* rather than silently dropping it.

Found by `policyforge-ba`, constructively: deleting each of the five guards
in turn and recording which test noticed. Two noticed nothing and one of
those could not have. All five are now caught by the test named for them,
and two tests were renamed because their names described a guard other than
the one they exercised.

Also removes `docs/probes/airmf-extraction/`, whose own note said to delete
it once the loader landed.
