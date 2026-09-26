**Every command now agrees on which control an id belongs to, and reads
the framework to decide.** `/coverage`, `/bundle`, `/addresses`,
`/satisfies`, `drift`, topic discovery and `programme parameters` each had
their own rule, and several knew only 800-53's shape. The Playbook's
`Govern 1.1` and the AI RMF Core's `Govern 1.1` are now told apart
everywhere, so a topic owns nothing in the Playbook.

**Topic discovery proposes AI RMF anchors.** A wiki page citing
`[NIST AI RMF Govern 1.1]` used to propose no anchor at all; it now
proposes `Govern 1`. A page citing only Playbook actions still proposes
none.

**`drift` reaches more of what a change affects.**

- An AI RMF change now reaches the documents citing its category or any
  subcategory in it (`Govern 1.3` reaches `Govern 1` and every `Govern 1.x`). Before, no AI RMF change reached any document. A Playbook change
  reaches documents citing Playbook actions for the same subcategory.
- A change in a catalog topics do not anchor now reaches topics through
  that catalog's crosswalk to 800-53, not by the shape of its ids. HIPAA and
  800-171 changes reach topics for the first time, through the mappings
  their publishers provide. FedRAMP and ARC-AMPE reach the same topics as
  before, because their crosswalks map each id to 800-53's own.
- Documents are reached across catalogs through 800-53: a change reaches a
  document whose citation maps to the same 800-53 control, whichever
  catalog it names. So an 800-53 change now also reaches documents citing
  the HIPAA and 800-171 requirements mapped to it, and no document drift
  reached before is missed. `drift` reads the crosswalks of the catalogs
  your installation loads.

**`programme parameters` includes 800-171's organisation-defined
parameters** where a topic anchors the 800-53 controls NIST maps them to,
and each such row in the ledger says `(from NIST 800-171)`. The ledger now
names each row's source catalog: every row from a catalog other than 800-53
says where it came from, FedRAMP's included. The ledger's keys are
unchanged, so decisions already recorded carry over.
