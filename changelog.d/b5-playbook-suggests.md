**Generated Standards and Procedures now write a NIST AI RMF Playbook action as
NIST suggesting it, never as a requirement, and `policyforge check` reports
one that does as an error.** The Playbook is voluntary, but the generation
prompts told the model to write in "must" and "shall", so a Playbook-cited
action came out as an obligation. In a local test before this change, every
one of ten did. With the new prompt rule, nine of nine read "NIST suggests".
If your organization adopts a suggested action as its own requirement, the
document states it in a separate sentence without the Playbook tag.
**`policyforge check` can now exit non-zero** on a document that cites only
the Playbook for an obligation ("must", "shall", "is required to", "needs to",
"has to", "is expected to"). A sentence whose tag also cites a binding source,
such as `[NIST 800-53 CM-8 | NIST AI RMF Playbook ...]`, is held to that
source's rules instead. A correctly worded Playbook sentence is no longer
reported as a weakened requirement.
