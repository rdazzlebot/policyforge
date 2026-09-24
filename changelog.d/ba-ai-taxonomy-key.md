**NIST AI 100-2 and the AI RMF's document number now key to their own
catalogs.** A catalog named "NIST AI 100-2", the Adversarial Machine Learning
Taxonomy, was filed under a bare `nist` key. So was "NIST AI 100-1", the AI
RMF's own document number, even though "NIST AI RMF" and "NIST AI Risk
Management Framework" already keyed correctly. They now key to
`nist-ai-100-2` and `nist-ai-rmf`.

Some names are deliberately left as they are, and tested so the choice is
visible. "AI Taxonomy" and "adversarial machine learning" are not treated as
NIST names, because OECD, Microsoft, MITRE and others publish catalogs under
the same words. A catalog named only "AI Taxonomy" or "NIST AI Taxonomy"
keeps its current key. The names of ONC programmes still share the key `onc`,
since their exact names are not yet known. A fix that keys every catalog by a
name it declares is planned for a later release.
