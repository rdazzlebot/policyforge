**A HIPAA crosswalk gap is now reported or refused, never silently
dropped.** `apply_crosswalk` skips two things by design: a CPRT citation
the eCFR-derived HIPAA data does not carry, and an SP 800-53 identifier
that did not parse. Both are meant to be reported, and the reporting had
no test — against the published crosswalk neither happens, so the
existing assertions that both lists are empty held just as well with the
lines that fill them removed.

**Whether this changes anything for you: no, not today.** The bundled
crosswalk maps every one of its 68 citations, so nothing in the data you
have changes, and `policyforge etl-hipaa-crosswalk` produces byte-identical
output.

**It changes what happens on the next CPRT revision.** NIST publishes the
crosswalk on its own schedule and the eCFR moves on another. When the two
drift — a citation renumbered, an identifier written as free text — the
run now either names the gap in its report or stops. Previously a drop
that escaped the report would have written a mapping that looks complete
and covers less than it claims, which in compliance data reads as
coverage.
