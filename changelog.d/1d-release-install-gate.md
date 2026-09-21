**`release_check.py` no longer passes without an install.** It gained a
fourth assertion: install the published formula in a clean container and run
the CLI. If the container cannot be started, the check reports **did not
run** and the script fails — unless you accept the gap explicitly with
`--allow-skip install`, the same contract `scripts/check.py` uses.

**The script was itself the substitution.** The recorded procedure was to
verify in a container *before* pushing the formula; what happened was push,
run this script, call it done. It reads the formula and compares values and
**never installed anything** — so the cheap check stood in for the expensive
one, and a substituted step leaves a false assurance where a skipped one
would only leave a gap.

The container smoke tests are pinned here rather than retyped each cut,
because the previous run's two failures were both the tests being wrong:
`policyforge --version` does not exist, and `policyforge frameworks` in an
empty directory exits 1 by design. **A smoke test that is wrong is
indistinguishable from a release that is broken until somebody checks
which.**
