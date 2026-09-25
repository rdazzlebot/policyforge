**`policyforge check` no longer reads a sentence across a heading.** Text on
either side of a heading could be judged as one sentence, carrying the second
part's citations and its "must" or "shall". Across 33 generated Standards, 18
of 2,501 sentences ran across a heading. You may see a few more "binds but
cites nothing" warnings: those obligations had been borrowing a citation from
the next section, and they are genuinely uncited. In the same 33 Standards
that was 8 new warnings and 1 that no longer applies.

**A NIST AI RMF Playbook sentence that also cites the AI RMF Core is now held
to the Playbook rules.** The Core states outcomes, not obligations, so citing
it beside the Playbook no longer exempts a sentence from the check that the
Playbook is presented as NIST's suggestion. A sentence that also cites a
catalog of obligations, such as SP 800-53, is still judged by that catalog's
rules instead.
