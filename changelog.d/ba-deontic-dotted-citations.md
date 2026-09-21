**`check` can now see a citation whose identifier contains a dot.** It
could not before, and the failure was silent: a Standard whose
requirements were all correctly cited and all written as *"should
consider"* reported nothing.

`weakened_citations` — the check that catches a cited requirement
rendered as advice instead of an obligation — **had never fired for
HIPAA**. The sentence splitter broke at every full stop, including the
ones inside `164.308(a)(3)(i)`, so the citation became three fragments,
none of which is a citation.

Counted from the shipped catalogs rather than estimated: **324 of 1,844
identifiers contain a dot, and four catalogs are entirely dotted** —
`hipaa-security-rule`, `cfr-171-information-blocking`,
`cfr-42-part-2-sud-records` and `nist-800-171-r3`. The check worked for
800-53, FedRAMP and ARC-AMPE.

**`nist-ai-rmf` was neither, and it is the case worth understanding**:
72 of its 91 identifiers contain a dot. Its nineteen categories —
`Govern 1` through `Manage 4` — the check could always read; all
seventy-two subcategories beneath them, `Govern 1.1` through
`Manage 4.3`, it could not. **A catalog where the check fires
for some citations and not others is the hardest kind to notice**,
because the check was visibly working the whole time.

**What you will see change.** On a document whose requirements bind
correctly, nothing — measured on the two generated Standards in
`docs/probes/`, findings stayed at zero, while the statements the checker
could see as cited went from 0 to 7 and 0 to 10. On a document that
hedges a cited requirement, you will now get the finding you should
always have got.

No command, option or exit code changes.
