**One condition leaves the 45 CFR 171 catalog: `171.1001(b)`, whose entire
text was the word `[Reserved]`.** The information-blocking catalog now
carries 54 conditions across 21 sections rather than 55. Nothing else in
it changed — the two eCFR editions either side of this are byte-identical
for Part 171, so the only content difference is the dropped row.

**If you cite `171.1001(b)` today, it currently resolves and tells you
nothing.** A reserved paragraph is a number the regulation is holding for
future use; there is no obligation behind it. After this it does not
resolve, which is the honest answer to a citation that was never pointing
at a requirement.

`171.1001(a)` — the disincentives CMS may apply — is untouched, and is the
only condition that section ever carried in substance.

**Why it was there.** The loader has always dropped reserved *sections*:
`171.402` is `[Reserved]` and has never been emitted. That check reads the
section's `<HEAD>`, so it never saw a reserved *paragraph* sitting inside
a live section. The two are different shapes and only one was covered.

The test that should have caught it is more instructive than the bug. It
exists, it is called `test_no_condition_is_empty`, and its docstring names
the hazard exactly: *"An empty condition is the reserved-section failure
one level down."* It then asserts the description is non-empty.
`[Reserved]` is eight characters, so it passed. Emptiness was the shape
this failure took in `hipaa_loader`; assuming it would keep that shape in
a different regulation is what let this one through. The replacement
asserts the property — a condition carries an obligation — instead of the
spelling of one way to fail it.

No command, option or exit code changes.
