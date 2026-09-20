**`/coverage` is now scoped to the catalogs your registry actually anchors,
not the catalogs it could anchor.** A bundled, anchorable catalog that no
topic anchors is excluded from the numbers and named under the report
instead.

Without this, bundling the NIST AI RMF would have cost every user who does
no AI six points on upgrade: 91 requirements would have entered their
denominator with nothing owning them. As shipped, a registry that anchors
no AI topics sees exactly what it saw before.

**This is not a new principle; it is the existing one stated correctly.**
Coverage was already meant to scope to "the set the registry anchors to",
and the implementation asked "could this be anchored". Those read the same
and only diverge once a bundled catalog is anchorable *but optional*, which
the AI RMF is and no earlier catalog was — every other one was either
always-anchored (800-53) or never-anchorable (HIPAA, the CFR pair).

Adoption is per catalog: anchoring any one identifier brings the whole
catalog into scope. Adoption only ever narrows, so a registry whose anchors
are all typos still reports its orphans and its unknown anchors rather than
claiming you have no registry.

Generation is unchanged and deliberately so — `documents.py` still sees
every anchorable catalog, because a control being *available* to generate
from is a different question from whether it belongs in a denominator.
