**New bundled catalog: the ONC certification criteria (45 CFR 170.315)**,
fetched from eCFR by `policyforge etl-onc`. Public domain, so it ships with
the package. 69 criteria across 9 categories.

**One criterion is one control**, cited the way developers and ONC's own
programme documents cite them — `170.315(g)(10)`. The lettered category is
the family; the sub-paragraphs stay in the statement, because they are the
conditions of one capability rather than separate duties.

**A criterion is not a control, and the catalog's README says so before it
says anything else.** A criterion states what a Health IT Module must be
able to do to be certified. Citing `170.315(g)(10)` asserts a capability
exists in a product; it does not assert that your organization has
implemented, configured or operates it. Those are different claims in a
report — one about software you bought, one about a control you run — and
the catalog ships without a crosswalk for that reason.

**47 reserved criteria are excluded and reported by id on every run.**
`170.315(i)` is reserved in its entirety, and `(j)(1)`–`(j)(19)` are a
reserved range written as a single paragraph. 69 emitted plus 47 reserved
is the 116 the section contains.

Declared as `ONC Certification Criteria`, taken from the section's own
heading, and pinned in `FRAMEWORK_ALIASES`. A name beginning with a digit
is not a legal source tag, so `45 CFR 170` could not have been cited by any
document; and Part 170's Subparts D and E are also "ONC … Certification",
so a future catalog drawn from either would otherwise key alongside this
one and pool its requirement ids.
