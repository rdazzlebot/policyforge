**`policyforge check` now reports an invented id in a shortened Playbook
citation, and the id no longer lets the sentence escape the Playbook check.**
In `[NIST AI RMF Playbook Govern 1.1 Action 1 | Govern 9.9 Action 1]`, the
second id names an action NIST never published. It used to make the sentence
count as citing two frameworks, so "Acme will adopt ..." drew only a warning
instead of the Playbook error. Now the sentence is still checked as a
Playbook sentence, and `check` reports `Govern 9.9 Action 1` as an error of
its own. A part that names another framework, such as `NIST 800-53 AC-2` or
`HIPAA 164.308(a)(1)`, is still read as that framework's, provided its
catalog is on disk.
