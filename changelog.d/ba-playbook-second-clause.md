**`policyforge check` now catches an organisation committing inside a Playbook
sentence.** A sentence citing only the NIST AI RMF Playbook must speak as
NIST, and "NIST suggests reviewing the inventory, and Acme will adopt it"
passed, because only the start of the sentence was read. A clause after
", and", ", but", ", so", a semicolon or a dash is now refused when its
subject is the organisation: "the organization", "we", "our", "staff", "the
team" and similar, or the organisation's own name, team names and vendor
names, read from `org:` in your config. An actor that is none of these is not
caught, and the check says so in its documentation.
