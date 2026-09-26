**The eval runner now says which measured epoch a run is compared with.**
`evals/prompt-fingerprints.json` names the epoch its fingerprints come from,
with the pull request and commits it ran at and each prompt's version. A
run's report now reads "differ from epoch 24", where it used to say "the
last recorded epoch". The file still held epoch 18's fingerprints
(2026-09-16) while epochs 19 to 24 were recorded, so that phrase pointed at
an older epoch than anyone reading it assumed. A new ledger,
`evals/prompt-versions.json`, records every version each prompt has
declared, and a prompt whose text no longer matches its recorded version
now fails the test suite. The ledger is meant only to grow; an edit to one
of its entries is caught by review, not by the tests. Maintainer tooling;
nothing a user runs changes.
