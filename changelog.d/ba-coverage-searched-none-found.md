**`/coverage` no longer claims a search nobody made, or tells you to rebuild
a mapping a catalog already carries.** When a framework read zero and nothing
explained why, its row said *"no published crosswalk yet"* and suggested
`crosswalk seed`. That printed for every such catalog: 42 CFR Part 2, every
catalog you bring yourself, and, whenever your topics owned none of the
controls they map to, HIPAA and FedRAMP too. Both of those ship their
publisher's mapping.

The row now names the actual cause:

- **A catalog that maps to 800-53** (HIPAA, FedRAMP, ARC-AMPE) now accounts
  for every requirement, with a count for each reason it reads zero:

  - how many your topics reach only in part, because your organisation's
    crosswalk overlay records the mapping as `superset` or `intersects`.
    Whether that is enough is a decision for a person;
  - how many map to 800-53 controls none of your topics owns. That gap is in
    your topics, so do not seed them by hand: a hand-made mapping would
    compete with the publisher's;
  - how many carry no mapping in the catalog's crosswalk at all. HIPAA has
    9 of these, including the general rules in 164.306.

  A reason with nothing to count is left out, and nothing on these rows
  suggests a command.

- **42 CFR Part 2** says *"no published crosswalk found"*, because a search
  was made. It covered NIST, HHS/OCR, SAMHSA rulemaking and HITRUST's source
  list, but not NIST's OLIR catalog, where a formal mapping would be
  registered. The search and its limits are recorded beside the claim in the
  code.

- **A catalog with no mapping at all** says *"this catalog carries no
  crosswalk"*.

The last two still suggest `crosswalk seed` to start one. The note above the
rows no longer counts the kinds of zero; each row names its own.
