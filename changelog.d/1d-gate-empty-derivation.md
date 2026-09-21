**The pre-push gate could report PASS having examined nothing.**
`scripts/check.py` derived its markdown targets with `rglob` and passed
them to `mdformat --check`, which exits 0 on an empty argument list —
*"No files have been passed in. Doing nothing."* — so `run()` saw
`returncode == 0` and printed **PASS**. Measured in-process before the
fix: an empty population and a clean tree returned the identical value,
and the exit code the charge tells everyone to condition their push on
was 0.

**Three populations had that property, not one.** #224 reported the
markdown targets; the tracked-file list behind the CRLF check and the
corpus behind the conflict-marker scan were the same shape, found by
asking what else in the file derives a set and then believes a clean
result over it.

All three now pass through one `derived()` guard, which refuses an empty
population and names what was not found. **An empty derivation exits 2,
deliberately distinct from 1**: `1` means a check ran and failed and
sends a reader looking for it; `2` means nothing was checked. It is not
silenceable with `--allow-skip`, which acknowledges a tool that is
*absent* — a tool that ran and examined nothing is a different fact and
must not share the same acknowledgement.

A test derives the population list from the source by parsing, so a
fourth one added later is covered by the check that exists rather than by
somebody remembering, and names that are genuinely not populations are
enumerated by hand with a reason. Its own exemption list is asserted
against the source, so an entry for something that no longer exists
fails rather than silently pre-exempting the next thing to take that
name.

Closes #224.
