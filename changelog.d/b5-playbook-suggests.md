**Generated Standards and Procedures now write a NIST AI RMF Playbook action as
NIST suggesting it, never as a requirement, and `policyforge check` reports
one that does not as an error.** The Playbook is voluntary, but the
generation prompts told the model to write in "must" and "shall", so a
Playbook-cited action came out as an obligation. In a local test before this
change, every one of ten did. With the new prompt rule, nine of nine read
"NIST suggests". If your organization adopts a suggested action as its own
requirement, the document states it in a separate sentence without the
Playbook tag, and `policyforge check` reports that sentence for a person to
confirm.

**`policyforge check` can now exit non-zero** on a document with a sentence
that cites only the Playbook and is not framed as NIST's: its subject must be
NIST or the Playbook, and it must not say NIST requires or mandates anything.
Any other wording fails, so an obligation in words nobody anticipated is still
caught. A sentence whose tag also cites a binding source, such as
`[NIST 800-53 CM-8 | NIST AI RMF Playbook ...]`, is held to that source's
rules instead. A correctly worded Playbook sentence is no longer reported as a
weakened requirement.
