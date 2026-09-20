# AI RMF loader — state at the 2026-09-20 15:00 pause

**WIP, not for merge.** This directory exists so a resumed session does not
re-derive an afternoon's work. Delete it when the real loader lands.

## What is settled, and should not be re-litigated

**The source is AIRC, not CPRT.** CPRT does not carry the AI RMF core.
Canonical URL:

```
https://airc.nist.gov/airmf-resources/airmf/5-sec-core/
sha256 of the page as parsed: 123a92fe73a5e716306c949ed6496b5a04e54bfb35161f5074a3a83f7678e5ee
```

**The extraction works, and `rows.json` here is its output** — 19 categories
and 72 subcategories (Govern 6, Map 5, Measure 4, Manage 4), every entry
non-empty, every subcategory's parent present, each function contiguous
1..N. Those are not remembered numbers: `extract.py` asserts all four and
exits non-zero otherwise.

**`extract.py` does not run from a clean clone** — it needs
`source-airc.html` beside it, which is not committed. Re-fetch from the URL
above. `rows.json` is committed precisely so the *result* survives without
the source. If a re-fetch yields a different digest, the page moved and the
row count is the thing to check first.

**The pattern keys on identifier shape, not CSS class**, and the docstring
says why: a class-keyed parser fails into zero rows on a restyle, silently.

## What remains

Control objects · ETL command · fixture · tests · catalog + provenance
stamp · README (rev-1.0 pin, and the citation-only consequence) · six
registration surfaces.

**Estimate, revised, and the revision is the point.** Calibration was
"a day", from Part 2 and 800-171 at ~1250 lines each. The remaining *work*
is still roughly that — call it 4–6 focused hours. **But the figure that
has actually predicted anything today is the rate, and the rate has been
near zero**, because allocation and review interrupt and implementation
does not. So: 4–6 hours of uninterrupted work, and **that condition is
load-bearing, not a caveat.** A resumed session that budgets a day of
wall-clock and gets reviews instead will land where today landed.

## `_zero_row_reasons` — 80's defect, confirmed, mine to fix

**Measured 13:58 today on `origin/main` (ab837a0), not inferred.** The
remedy line this function prints, run verbatim:

```
$ policyforge crosswalk seed --framework 'NIST 800-171'
Error: No catalog here declares the framework 'NIST 800-171', so there
is nothing to seed. The catalogs you loaded declare: 'NIST 800-53',
'HIPAA Security Rule'.
EXIT=1
```

The shell's `discover()` sees seven catalogs with controls; the `crosswalk`
CLI's default context has two. **The report knows which catalog file
declared the framework, because `discover()` handed it over** — so the fix
is to emit the matching `--controls` flags and make the suggestion
copy-pasteable. Not started; no code written.

**Why this one stings: it is the failure I warned `ba` about for
`satisfies`, built into my own output.** A remedy that is well-formed,
confident, and not performable is the same shape as a check that cannot
fail — nothing is red, and the user is the one who finds out.

One caution for whoever picks it up: I read `_DEFAULT_CONTROLS` with a
regex and it returned *one* path while the error names *two* catalogs. **The
error message is the authoritative statement of the context; my regex
under-read it.** Derive the default from the CLI, not from that grep.

## Not started

- **AI Governance topic** — follows the loader, so it can be verified
  against a real catalog rather than against the fixture that produced it.
- **The outcome-framework prompt branch is UNOWNED.** I said I was
  allocating it to b5; b5 never received it. Recorded here so it is not
  re-recorded as assigned until whoever takes it says so.

## Unreported finding: #164 fails the gate

`FAIL mdformat (markdown quality)` on
`docs/probes/airmf-generation/README.md` and
`standard-local-qwen3-14b-pf.md`. **`origin/main` alone is 10 ran, 0
failed, 1 skipped**, so the PR introduces it. Reported clean.

The fix is running `mdformat` over those files — **but the generated-output
file may want an exclusion instead**, since reformatting a model's output
edits the artefact being preserved. That is 80's call, not mine.
