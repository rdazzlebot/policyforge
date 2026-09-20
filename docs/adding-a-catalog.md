# Adding a catalog

What the loaders here have learned the hard way, written for whoever adds
the next one. Every rule below cost a real defect; none is style.

## A pinned catalog must refuse to ingest a different revision

**If a catalog's README, `framework.yaml` and provenance stamp all assert a
revision, the loader must fail when the source publishes a different one.**

Not because the parse is unsafe — usually it is fine. Because those three
artefacts go stale *simultaneously*, and a loader that quietly ingests the
new revision produces a file stamped `revision 1.0` holding revision 2.0's
content, with a `content_sha256` that verifies the lie. **A hash that
authenticates wrong content is worse than no hash**: it converts "I do not
know what this is" into a false assurance, and everything downstream that
trusts provenance inherits it.

The failure exists to make four artefacts stale **visibly and together**,
rather than one silently.

The NIST AI RMF loader pins `EXPECTED_SHAPE = (19, 72)` and says exactly
this in its error. Pin the shape, not just the version string: a version
string is what the page *claims*, and the shape is what it *contains*.

**A scheduled drift job going red the day the source revises is that job
succeeding.** Its entire purpose is to detect upstream change. The defect
would be a drift job staying green while the upstream moved — so do not
"fix" the red by loosening the pin.

## Assert external extent, not only internal consistency

**Every loader here asserts that its rows are well-formed. None asserts how
many rows there should be**, and those are different questions.

Appending an invented `Govern 7` to the AI RMF source produced **20
categories, zero orphans, contiguous numbering, every row well-formed** — a
clean parse of a wrong catalog. Contiguity accepts an *extension*. ONC is
the proof at scale: twelve fabricated criteria passed every structural check
that loader had.

So: pin the count. And when you write the guard, **say what it must ALLOW as
well as what it refuses** — a pinned shape is one typo away from rejecting
its own source, and a parser that refuses the real document is
indistinguishable from a broken one.

## The declared name must be citable

`content/tags.SOURCE_TAG_RE` builds a framework name from **capital-initial
words**. A name beginning with a digit is not a tag — it is prose.

`45 CFR 171` and `42 CFR Part 2` shipped for months in exactly that state:
every citation to them was prose, `satisfies --strict` exited 0 reporting
nothing cited, and every gate stayed green. **`FRAMEWORK_ALIASES` cannot
rescue it** — the alias table is downstream of the pattern that failed to
match.

Test the whole population, not a worked example. A sample chosen because it
is well known is selected for the property that makes it easy to get right.

## Key the catalog before it exists, and never inside the pattern

Add the framework's key to `FRAMEWORK_ALIASES` before writing the loader.
Every needle must be **as narrow as the thing it names** and should carry a
space, so it cannot match inside a hyphenated identifier — a bare `hitrust`
needle once swallowed the id `hitrust-csf` and returned `hitrust`.

And **do not enumerate a vocabulary inside the row pattern.** The AI RMF
parser's row regex listed the four function names, which made its
`unrecognised function` guard unreachable: nothing the regex could produce
would be rejected, so a fifth function did not raise — the row *vanished*.
**Enumerating a vocabulary in a pattern turns "I do not recognise this" into
"this does not exist".** Key on shape; let the guard do the validating.

## Say what a citation to this catalog proves

Most catalogs state obligations. Some state **outcomes** — the NIST AI RMF
says *"the risks are understood and managed"*, with nobody named and no act
required.

A document citing an outcome is fully traceable and may still commit nobody
to anything. **That hazard is a property of the source rather than of the
parse, so it can only be disclosed, not fixed.** Say so in the catalog's
README, next to the counts, where a reader meets it.

If the catalog cannot be crosswalked — because mapping an outcome to a
control would assert the control *achieves* the outcome — put it in
`NOT_CROSSWALK_ANCHORABLE` with the reason. Otherwise `/coverage` will tell
the reader to run `crosswalk seed`, which is the opposite of what the
catalog's own README says.

## Make each guard fire before you trust it

Delete each guard in turn and record which test notices. Two of the AI RMF
parser's five were found this way: one untested, one **unreachable**.

**Run a control first.** An audit harness that cannot run the suite reports
the same thing as a suite where nothing noticed — ours invoked `python`
rather than `sys.executable`, got an interpreter without pytest, and
reported "nothing noticed" for five guards including ones already proved
covered. **A control run on the unmutated tree must be green before any
mutation result is believed.**

And **mutate through the parser's own pattern**, not a second one written to
mean the same thing. A hand-written twin swallowed a closing tag, deleted
the row instead of emptying it, and a different guard fired — the test would
have passed while measuring the wrong thing. A test that re-expresses the
thing under test tests the re-expression.

## Register in every surface, derived rather than listed

A catalog is not added until it appears in `scaffold.py`, `pyproject.toml`
package data, the ETL command, the drift workflow, the licence table in
`README.md`, the CLI surface snapshot, and a changelog fragment.

Where a test needs to know which catalogs exist, **derive the population
from the tree or from the relevant constant** — never a hand-written list. A
fixture narrower than the thing it tests does not fail quietly: it turns
"out of scope" into "does not exist" and blames correct data.
