# ONC Certification Criteria (45 CFR 170.315)

Public domain (US federal regulation — 45 CFR 170.315, the certification
criteria for health IT). Same basis as NIST 800-53/FedRAMP/ARC-AMPE/HIPAA,
so unlike HITRUST/GovRAMP this is safe to bundle directly rather than
treat as BYOC.

## What an entry is

**One criterion is one control**, cited the way developers and ONC's own
programme documents cite them:

```
170.315(g)(10)   Standardized API for patient and population services
170.315(d)(1)    Authentication, access control, authorization
170.315(b)(1)    Transitions of care
```

The lettered category above a criterion is its family — `(g) Design and performance` — and the sub-paragraphs below it stay in the control
statement. Those describe the conditions of one capability rather than
separate duties, which is the same split `cfr-171-information-blocking`
makes for the conditions of an exception.

**This is a certification catalog, and that is not the same as a control
catalog.** A criterion says what a Health IT Module must be *able to do*
to be certified. Citing `170.315(g)(10)` asserts that a capability exists
in a product; it does not assert that your organization has implemented,
configured or operates it. The two readings diverge in a report: one is a
statement about software you bought, the other about a control you run.

## What was parsed

69 criteria across 9 categories, from the 2026-09-17 revision.

| Category |                                       | Criteria |
| -------- | ------------------------------------- | -------- |
| `(a)`    | Clinical                              | 9        |
| `(b)`    | Care coordination                     | 13       |
| `(c)`    | Clinical quality measures             | 4        |
| `(d)`    | Privacy and security                  | 13       |
| `(e)`    | Patient engagement                    | 7        |
| `(f)`    | Public health                         | 7        |
| `(g)`    | Design and performance                | 12       |
| `(h)`    | Transport methods and other protocols | 2        |
| `(j)`    | Modular API capabilities              | 2        |

**47 reserved criteria are excluded, and reported by id on every run.**
`170.315(i)` is reserved in its entirety — which is why there is no `(i)`
row above — and `(j)(1)` through `(j)(19)` are a reserved range written in
a single paragraph. A reserved criterion has a number and nothing else;
emitting one produces an entry that counts, renders and crosswalks and
means nothing.

69 + 47 = 116, which is what the section contains.

## The identifier trap, twice

**The structure is not in the XML.** § 170.315 is a single section with
540 flat `<P>` children whose hierarchy lives in the text, so the parse
reconstructs the tree from labels.

`^\([a-z]\)` cannot tell the criterion `(i)` from a sub-paragraph `(i)`.
**Forty-seven paragraphs open with `(i)` and exactly one is a criterion.**
Reading them all as criteria invents `170.315(v)` and `170.315(x)`, which
do not exist — and nothing crashes. What separates them is ordinal
position: a criterion's letter is the successor of the last one seen.

**The same trap repeats one level down, and is larger.** 182 paragraphs
open with `(N)`, and most are sub-lists — `(1) To a specific set of identified users.` sits three levels inside `(a)(4)`. So a criterion
number must be the successor of the last one *in its own category*.

Two spellings also differ between categories, and matching only the first
loses a whole category: `(a) Clinical—` introduces its first criterion
after an em dash, while `(j) Modular API capabilities.` uses a period.

## Why it is not called "45 CFR 170"

A framework name beginning with a digit is **not a legal source tag** —
`content/tags.SOURCE_TAG_RE` builds a name out of capital-initial words —
so a catalog declaring `45 CFR 170` could not be cited by any document.
Two other CFR catalogs shipped that way and were renamed to fix it.

The declared name is taken from the section's own heading, *"ONC
certification criteria for Health IT"*, so the name a person types is the
name the regulation uses. It is pinned in `mapping/crosswalk`'s
`FRAMEWORK_ALIASES` because Part 170's Subpart D and Subpart E are *also*
"ONC … Certification" — a future catalog drawn from either would key to
`onc` alongside this one, and their requirement ids would pool.

## Regenerating it

```
policyforge etl-onc
```

`framework.yaml` records the effective date fetched, the exact URL, and
the SHA-256 of the catalog produced. eCFR has no release tags; the
effective date is the only thing that names a revision. The monthly
`framework-drift` job re-runs this and fails the build if the regulation
has moved.

## Crosswalk

This catalog ships without a `source_crosswalk`. No authority publishes a
mapping from certification criteria to 800-53, and the reason is the
distinction above: a criterion is a statement about product capability,
and a control is a statement about organizational practice. A crosswalk
invented here would be this project's opinion wearing the regulation's
authority.
