**`policyforge check` now reports an obligation that binds while citing
nothing, where the obligations around it do carry citations.** A generated
Standard can assert "Reviewers shall retain evidence for seven years" beside
properly cited requirements, and until now nothing said so — the existing
check only fires on a document citing *nothing at all*, so seven good tags
masked three untagged obligations. **Expect new warnings on generated
documents**: on the 33 generated Standards we measured, it reports 22. They
are warnings rather than errors, so only `--strict` turns them into a
failing exit.

**And `policyforge check --entail` asks a model whether each cited obligation
is actually carried by the synthesis requirements it cites.** Off by default,
one model call per cited obligation, and **the count is printed before
anything runs** so the cost is known rather than discovered. These findings
are reported and **never change the exit code**: a malformed document is a
fact anyone can verify twice with the same answer, and a model's verdict is
not.
