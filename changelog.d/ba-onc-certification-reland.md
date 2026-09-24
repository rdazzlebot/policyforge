**The ONC certification criteria catalog is back**: 45 CFR 170.315, 59 live
criteria across 9 categories, cited as `170.315(g)(10)`. Refresh it with
`policyforge etl-onc`.

The first version was withdrawn before release because it contained
criteria that do not exist. The regulation's structure lives only in its
text, where a numbered item three levels inside one criterion looks like the
next criterion. This version reads the formatting eCFR uses to tell those
apart. **It also refuses to produce a catalog unless its criteria exactly
match a list that two independent sources agree on**: ONC's own test-method
index, and the Federal Register's amendment history applied to CHPL's list of
every criterion ever used.

Reserved and expired criteria are left out and named on every run.
`170.315(b)(3)` stays in: it is a live criterion that only opens with a
reserved sub-paragraph. `170.315(a)(9)` is left out because its own text says
it expired on 1 January 2025.

A certification criterion describes what a product must be able to do, not
what your organization runs. The catalog's README explains the difference.
