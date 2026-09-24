**HITRUST coverage is no longer always zero.** `policyforge coverage` and
`/coverage` reported every imported HITRUST requirement as unreached, whatever
your topics owned, and `/coverage` then suggested building a crosswalk by hand
for a catalog whose export already carries HITRUST's own mappings. HITRUST
publishes its mappings per level ("01.a Level 1"), and coverage was counting
per control reference ("01.a"), so the two never matched.

HITRUST is now counted per level requirement, across every level the catalog
carries, and the report says so on the HITRUST line. Levels are not rolled up
into their control reference, because that would claim a mapping for levels
HITRUST never mapped. Choosing which levels apply to your organisation is not
part of this release.

Two more places a mapping can live are now read, both by coverage and by the
zero-row explanation added in this release:

- a mapping written on an 800-53 control and naming another framework's
  requirement, which was stored under the framework's name as written and so
  was never matched;
- HITRUST's level-scoped mappings, which the zero row counted as "carry no
  mapping".

No shipped catalog uses the first, so shipped figures are unchanged. The
change applies to catalogs you bring yourself.
