**A crosswalk built on one platform is no longer reported stale on
another.** `map` records a digest of each file in `config/crosswalks/`
beside the crosswalk it builds, and `synthesize` compares them. Those
digests were taken over raw bytes, so the same overlay checked out on
Windows and on Linux produced two different values.

**The symptom was a hard failure with the wrong cause.** `synthesize`
refused to run — *"was not built from the crosswalk overlays now in
config/crosswalks/"* — and told you to rebuild a crosswalk that was
correct.

**Whether this changes anything for you:**

**If your overlays are stored with LF — Linux, macOS, and Windows
checkouts configured for it — nothing changes and there is nothing to
do.** Your recorded digests are identical before and after; the
normalisation has nothing to normalise.

**If your overlays are checked out with CRLF**, their digests change
once. A crosswalk built before this upgrade then reads as stale the
first time, and one `policyforge map` settles it.

**The fix is for teams with both.** A Windows member recorded one digest
and a Linux member computed another from the same committed file, so
whoever ran `synthesize` second was told to rebuild. That stops.

`.gitattributes` pins only `*.md` to LF, so a `config/crosswalks/*.yaml`
still checks out however `core.autocrlf` decides. That is now harmless
rather than load-bearing.
