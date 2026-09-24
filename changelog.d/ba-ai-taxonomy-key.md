**NIST's AI Taxonomy and the AI RMF's document number now key to their own
catalogs.** A catalog named "NIST AI 100-2" or "NIST AI Taxonomy" was filed
under a bare `nist` key, and "AI Taxonomy" under a bare `ai`. The same
happened to "NIST AI 100-1", which is the AI RMF's own document number, even
though "NIST AI RMF" and "NIST AI Risk Management Framework" already keyed
correctly. They now key to `nist-ai-100-2` and `nist-ai-rmf`.

Two things are deliberately left as they are, and tested so the choice is
visible. The Taxonomy's title words, "adversarial machine learning", are not
treated as a NIST name, because other publishers use them. The names of ONC
programmes still share the key `onc`, since their exact names are not yet
known. A fix that keys every catalog by a name it declares is planned for a
later release.
