**HITRUST AI Security Certification is named as a bring-your-own
catalog.** `data/frameworks/hitrust-ai/` holds a README and nothing else,
on the same terms as `hitrust-csf` and `govramp`: the requirement text is
licensed and no open-source project can redistribute it, and a
`framework.yaml` here would make the licence check report a licensed
catalog committed to a public repository.

**It is an add-on to a CSF assessment and cannot be held on its own**, so
an organization carrying it carries the CSF too. The two catalogs meet in
the normal case rather than the unusual one, which is why their keys had
to be separated: `HITRUST AI Security Certification` and `HITRUST AI` both
key to `hitrust-ai`, distinct from `HITRUST CSF`'s `hitrust`. Without that
pin the first-word fallback would pool their requirement ids and a
citation to one could resolve against the other.

**There is no `etl-hitrust-ai` command, and `etl-hitrust` must not be used
instead.** It stamps `HITRUST-CSF` on whatever it parses, so an AI export
run through it arrives labelled as CSF content — and a CSF export and an
AI export come out under one framework name with their ids pooled. The
README says how to declare the name yourself in the meantime, and a test
holds that warning to the command it warns about.
