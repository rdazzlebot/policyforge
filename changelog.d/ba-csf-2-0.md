**NIST CSF 2.0 ships as a bundled catalog, with NIST's own mapping to
800-53.** Pass `data/frameworks/nist-csf-2-0/controls.json` to `/coverage`,
`satisfies` or `crosswalk seed`, and cite it as
`[NIST CSF 2.0 GV.OC-01]`. It carries the 22 categories and 106
subcategories of the Core and NIST's 742 links to 800-53 (OLIR 186).
`policyforge etl-csf` rebuilds it, and refuses any file other than the two
it is pinned to.

**A CSF subcategory is never reported as fully covered on NIST's link
alone.** NIST publishes the mapping with no relationship types and marks it
not comprehensive. So `/coverage` counts every CSF link as partial, and
`satisfies` reports a CSF id reached through the crosswalk as *in part*.
`/coverage` also says which CSF ids NIST did not map at all. That is "not
mapped by NIST", not "no 800-53 equivalent". An organisation that reviews a
link records its own relationship in its crosswalk overlay, and that
overrides the default.

**CSF 2.0 states outcomes, not obligations**, as the AI RMF Core does, so
citing it commits nobody to anything on its own. Read the catalog's README
before citing it.

Nothing moves for any other catalog: every shipped mapping reads exactly as
it did.

**If you script on `coverage --json`:** each entry in `framework_coverage`
now carries two more keys. `source_name` is who published the crosswalk, and
`unmapped_by_source` lists the ids that source left unmapped. For every
catalog other than CSF 2.0 they are `""` and `null`, and no existing key
changed.
