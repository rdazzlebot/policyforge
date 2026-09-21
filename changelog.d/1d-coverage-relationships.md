**The shell's `/coverage` now reads the crosswalk relationships the CLI
reads.** It passed none, so every lookup returned `None`, `None` is not a
partial relationship, and a mapping an organisation had reviewed and
recorded as `superset` or `intersects` counted as **full** coverage in the
shell while counting as **partial** in `policyforge coverage`.

Two views of one registry, disagreeing about what the organisation's own
recorded decision means — and the shell's view was the optimistic one.
