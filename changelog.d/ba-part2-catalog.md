**New bundled catalog: 42 CFR Part 2, substance use disorder patient
records**, fetched from eCFR by `policyforge etl-part2`. Public domain, so
it ships with the package like NIST and HIPAA rather than as BYOC.

**It has two controls, and that is the whole catalog.** Part 2 has 38
sections; §2.16 (security for records and notification of breaches) and
§2.19 (disposition of records by discontinued programs) are the only two
that impose a safeguard. The rest is conduct — when a disclosure is
permitted, what a consent must contain, what a court must find — and citing
a conduct rule as a control would assert that a safeguard exists where the
regulation says only that a disclosure was lawful. The thinness is the
correct answer rather than a parse failure, and the catalog's README states
the count, the test that produced it, and the sections it rejected, so a
reader who thinks something is missing gets the reasoning instead of
re-running the parser.

Unlike `cfr-171-information-blocking`, this catalog **seeds a crosswalk
normally**: its entries are safeguards to implement, so there is something
for an 800-53 control to correspond to. It ships without a
`source_crosswalk` because no authority publishes one for Part 2, which is
a different thing from being unmappable.

The monthly `framework-drift` job now covers it.
