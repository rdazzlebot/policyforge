**A crosswalk built on one platform is no longer reported stale on
another.** `map` records a digest of each file in `config/crosswalks/`
beside the crosswalk it builds, and `synthesize` compares them. Those
digests were taken over raw bytes, so the same overlay checked out on
Windows and on Linux produced two different values.

**The symptom was a hard failure with the wrong cause.** `synthesize`
refused to run — *"was not built from the crosswalk overlays now in
config/crosswalks/"* — and told you to rebuild a crosswalk that was
correct. Only teams that commit both their overlays and the provenance
file, and build across platforms, could hit it.

**You will need to run `policyforge map` once.** Every recorded digest
changes with this fix, so a crosswalk built before it reads as stale the
first time — once, and then not again.

`.gitattributes` pins only `*.md` to LF, so a `config/crosswalks/*.yaml`
still checks out however `core.autocrlf` decides. That is now harmless
rather than load-bearing.
