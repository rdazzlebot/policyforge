**The HIPAA catalog no longer ships an implementation specification with
no text.** `164.314(a)(2)`, *"Implementation specifications"*, had a title
and an empty description — the only such entry in any bundled catalog, 1
of 1,044. A user citing it cited a title, and an assessor following that
citation found nothing, while the obligation they wanted sat at
`164.314(a)(2)(i)`. Its source paragraph is a run-in heading that
delegates everything to its children, and all three children already ship
as controls in their own right, so **no requirement is lost** — the
citation that resolves to text is now the only one offered. The
identically titled `164.314(b)(2)`, where the text really does follow the
label, is unchanged.

**`policyforge etl-hipaa` can be re-run again.** It carries existing
crosswalk mappings forward by citation, so re-parsing the regulation no
longer destroys the NIST mappings that `etl-hipaa-crosswalk` attaches.
Before this, the guard added in 1.3.0 correctly refused every re-parse and
its error message told you to run the command that had just refused —
there was no way through. The guard keeps its teeth: an entry the parser
no longer produces still takes its mapping with it and is still refused.
`etl-hipaa-crosswalk` remains the only thing that *decides* mappings.
