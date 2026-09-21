**Four loaders now refuse a parse that quietly found less than its source
contains.** `info_blocking`, `hipaa_loader`, `oscal_loader` and `arc_ampe`
each assert *external extent* — how many entries there should be — in
addition to the internal consistency they already checked.

**Nothing about a correct catalog changes.** All four parse their current
sources exactly as before; the new checks raise only where a parse would
previously have returned a short catalog and said nothing.

**Why this is a class of defect rather than four bugs.** A loader that
asserts hard about the *shape* of what it found and nothing about
*whether it found everything* fails in one direction only: it returns
fewer entries, and every remaining entry is well-formed. No exception,
no empty result, no malformed id — a catalog that is internally
consistent, renders correctly, crosswalks correctly, and is missing a
requirement. Every count a README states about it stays true of the
catalog as parsed.

**Each check asks the source document, never a constant.** eCFR emits a
node per section; OSCAL declares its controls in arrays; the ARC-AMPE
workbook has rows. Both sides of every comparison come from the artefact
being parsed, so a publisher may extend a framework without anyone
editing a number here, and there is no expected total to go stale.

The NIST AI RMF remains the deliberate exception: its source is a flat
HTML table that declares no extent of its own, so there is nothing to
reconcile against and a pinned shape is the only option left. That is
documented where the pin lives rather than left as the pattern to copy.
