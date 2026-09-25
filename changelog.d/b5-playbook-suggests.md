**Generated Standards and Procedures now write a NIST AI RMF Playbook action as
NIST suggesting it, never as a requirement, and `policyforge check` reports
one that does not as an error.** The Playbook is voluntary, and the
generation prompts now say so. **The prompt rule reduces this but does not
stop it**, which is why `policyforge check` reports any Playbook-cited action
still written as a requirement. A Standard for an AI topic is also
regenerated or refused when its Playbook sentences would fail the check. A
Procedure is not, so for a Procedure the prompt rule and
`policyforge check` are the whole safeguard. If your organization adopts a
suggested action as its own requirement, the document states it in a
separate sentence without the Playbook tag, and `policyforge check` reports
that sentence for a person to confirm.

**`policyforge check` can now exit non-zero** on a document with a sentence
that cites only the Playbook and is not framed as NIST's: its subject must be
NIST or the Playbook, and it must not say NIST requires or mandates anything.
Any other wording fails, so an obligation in words nobody anticipated is still
caught. A sentence whose tag also cites a binding source, such as
`[NIST 800-53 CM-8 | NIST AI RMF Playbook ...]`, is held to that source's
rules instead. A correctly worded Playbook sentence is no longer reported as a
weakened requirement.
