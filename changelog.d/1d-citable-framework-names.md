**Two bundled catalogs could not be cited at all, and now can.** A source
tag's framework name must begin with a capital letter, so
`[45 CFR 171 171.203(a)]` and `[42 CFR Part 2 2.16(a)]` were never tags —
they were prose. A policy written entirely against the information-blocking
rule reported **no citations**, `satisfies --strict` exited **0**, and
`policyforge check` said *"No errors — safe to publish."* The report said so
plainly in words; neither gate failed.

The two catalogs now declare themselves as **`Information Blocking`** and
**`Substance Use Disorder Records`**:

```
[Information Blocking 171.203(a)]
[Substance Use Disorder Records 2.16(a)]
```

The regulation is still named in each catalog's `framework.yaml`, in
`framework_version` and in its README. What a citation carries and what a
catalog is called are different jobs, and conflating them is what made these
two unusable.

**If you have documents citing the old spellings, they were resolving to
nothing already** — rewrite them to the forms above, and **rewrite every tag
in a document at once.**

A document written entirely against the old spellings says so plainly:
*"Cites no framework requirement. Nothing here is traceable."* **That signal
disappears the moment you fix the first tag.** A half-migrated document
reports the tags you rewrote, counts `0 resolving to nothing`, and exits 0 —
saying nothing at all about the ones still written the old way, because
those are not citations to the tool, they are prose. A partly-rewritten
document looks finished.

**Find them with grep, not with `satisfies`.** The tool cannot list them —
that is the whole defect: an old-form tag is prose to it, so it is not in
the report to be counted. This is the search:

```
grep -rnE '\[[0-9]' --include=*.md .
```

Broad on purpose. Searching for `[45 CFR 171` and `[42 CFR Part 2` misses
`[45 CFR Part 171 ...]` — **the spelling `framework.yaml` itself uses**, so
it is what a careful person copied — along with `[42 CFR 2.16(a)]` and a
bare `[2.16(a)]`. All are equally invisible to the tag reader, and the
pattern above catches any bracket opening with a digit.

It also catches footnote markers and citations that were never tags; those
identify themselves. One worth naming so nobody chases it: the Part 2
README carries `[89 FR 12622, Feb. 16, 2024]`, eCFR's own source note,
correct as it stands.

**`crosswalk seed`'s refusal for the information-blocking catalog now names
an action you can take.** It told you to cite `171.203(a)` instead of
mapping it, which was impossible for the same reason. Renaming the catalog
also re-opened that refusal — it is keyed on the declared name, and the new
name shares no word with the old — so both spellings are keyed and a test
covers it.

A test now asserts that **every** bundled catalog's declared name is a legal
tag, splits back to itself, and keys to its own catalog rather than to its
first word. The population is read from `data/frameworks/` rather than
listed, so the next catalog is covered without anyone remembering this.
`FRAMEWORK_ALIASES` could not have fixed any of it: the alias table runs
*after* the tag pattern, so it never sees a name the pattern rejected.
