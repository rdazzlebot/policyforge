**A citation tag can now list several ids from one framework without
repeating the framework's name.** In `[NIST AI RMF Playbook Govern 1.1
Action 1 | Govern 1.1 Action 2]`, the second id now counts as a Playbook
citation. Before, `policyforge check` could not tell that such a sentence
cited only the voluntary Playbook, so it warned about correct "NIST suggests
..." wording and let "Acme must ..." through. Traceability also dropped
the later ids. A part without a framework name takes the framework of the
part before it, and must then exist in that framework's catalog: `[NIST
800-53 AC-2 | Govern 1.1 Action 2]` reports the second part as an
unresolved citation instead of reading it as either framework.
