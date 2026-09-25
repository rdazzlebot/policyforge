**New bundled catalog: the NIST AI RMF Playbook**, NIST's suggested actions for
each of the 72 subcategories of the AI RMF 1.0 Core. That makes 459 actions,
cited as `[NIST AI RMF Playbook Govern 1.1 Action 3]`. The AI RMF Core states
outcomes, not actions, and NIST published its actions separately in the
Playbook. This catalog lets a document name an action and attribute it to NIST
without PolicyForge inventing one.

**The Playbook is voluntary.** A document may say NIST suggests an action,
never that NIST requires it. The catalog's README says so first, in NIST's own
words. This release enforces it: `policyforge check` reports a Playbook
action written as a requirement as an error, and a Standard whose Playbook
sentences fail that check is regenerated or refused.

Fetch it again with `policyforge etl-ai-rmf-playbook`. NIST publishes no
revision number for the Playbook, so the catalog is pinned to the exact export
it was built from, and the command refuses any other. The catalog carries no
outcome wording, because the Playbook's restatement of the outcomes differs
from the AI RMF 1.0 Core in 30 of the 72 subcategories. Each outcome is read
from the AI RMF catalog under the same id.
