**A change to a HIPAA implementation specification now reaches the
documents citing its standard.** `drift` reads the HIPAA Security Rule,
42 CFR Part 2, Information Blocking and the ONC certification criteria by
the unit each regulation names as a requirement, declared in the catalog's
`framework.yaml`: a HIPAA standard with its implementation specifications,
a Part 2 or Information Blocking section, an ONC criterion. A change to
`164.308(a)(1)(ii)(A)` reaches a document citing `164.308(a)(1)` or any of
that standard's specifications; a change to `171.202(b)` reaches one citing
any condition of the privacy exception. Before, only an exact citation of
the changed id was reached.

**A HIPAA standard cited by its paragraph resolves.**
`[HIPAA Security Rule 164.308(a)(1)]` is how a standard is cited, but the
catalog's id is `164.308(a)(1)(i)`; `/satisfies` listed it as a citation
nobody can follow, and `drift` could not tell which requirement it meant.
Both now read it as that standard. A section cited whole, such as
`164.308(a)`, stands for every standard in it.

Citations written as a range (`164.308(a)(5)(ii)(A)-(D)`) or as a
comma-separated list in one tag are still reported as unresolved.
