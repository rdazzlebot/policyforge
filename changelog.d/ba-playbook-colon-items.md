**The Playbook check now judges each item of a colon list.** In `policyforge
check`, a list introduced by a colon, such as "Acme Health must:", was read
as one statement, so when one item cited only the NIST AI RMF Playbook and
another cited NIST SP 800-53, the Playbook item's obligation passed
unreported. Each item is now checked as the lead-in plus that item, against
its own citations, and reported at the item's line. A lead-in with NIST as
its subject, such as "NIST suggests:", still frames every item as NIST's
suggestion. A list whose items all cite only the Playbook was already an
error and still is, but is now reported once per item instead of once for
the list.
