# Information Blocking (45 CFR Part 171)

Public domain (US federal regulation — 45 CFR Part 171, the information
blocking rule made under section 3022 of the Public Health Service Act).
Same basis as NIST 800-53/FedRAMP/ARC-AMPE/HIPAA, so unlike
HITRUST/GovRAMP this is safe to bundle directly rather than treat as BYOC.

## Read this before you map it to anything

**This is not a control catalog, and it does not become one by sitting in
this directory.** Every other framework here answers "what must we
implement?". Part 171 answers a different question. It defines a practice —
information blocking — and then sets out the *exceptions*: the conditions
under which a practice that would otherwise be blocking is not.

So an entry here is a condition of an exception. Citing `171.203(a)` says
a practice **qualifies for the security exception**; it does not say a
safeguard exists, and it is not evidence that one does. The two readings
point opposite ways in a report: one is a defence for withholding
information, the other a claim to have protected it.

Two consequences worth stating plainly:

- **Coverage here is not assurance.** A high count of satisfied Part 171
  conditions means an organization has justified its restrictions well. It
  says nothing about whether its security controls work.
- **Do not crosswalk it to 800-53 by resemblance.** `171.203` and the
  800-53 SC family both talk about protecting information, and mapping
  them because the words match would produce a crosswalk that reads as
  control coverage. Nothing in this project generates such a mapping, and
  this catalog ships without one deliberately — see "No crosswalk" below.

## What was parsed

21 sections carrying 55 conditions between them, 39 of which the
regulation gives its own italic heading ("Reasonable belief", "Practice
breadth"), preserved in each condition's `title`.

| Subpart                                          | Sections                  |
| ------------------------------------------------ | ------------------------- |
| A — General                                      | 171.100, 171.101, 171.103 |
| B — Exceptions involving not fulfilling requests | 171.200–171.206           |
| C — Exceptions involving procedure               | 171.300–171.303           |
| D — Exception involving TEFCA                    | 171.400, 171.403          |
| J — Disincentives                                | 171.1000–171.1002         |
| K — Transparency                                 | 171.1100, 171.1101        |

A section is a control; its top-level lettered paragraphs are conditions,
carried as enhancements. Deeper nesting — `(d)(1)`–`(d)(4)` under the
security exception — stays inside the condition it qualifies, because
those paragraphs say what a written security policy must contain rather
than imposing four free-standing duties. This is the same split
`hipaa-security-rule` makes between a Standard and its implementation
specifications.

**Three sections are deliberately excluded**, and the count above reflects
that:

- `171.102` and `171.401` are definitions. A defined term is not a
  requirement — the same reason `hipaa-security-rule` drops § 164.304.
- `171.402` is `[Reserved]`, as are Subparts E through I in their
  entirety. A reserved section has a number and a title and no
  obligations; emitting one produces an entry that counts, renders and
  crosswalks, and means nothing.

## Regenerating it

Source: eCFR's public versioner API,
<https://www.ecfr.gov/api/versioner/v1/full/%7Bdate%7D/title-45.xml?part=171>
— not a hand-copied transcription, so this can always be regenerated and
diffed against the actual current regulation text:

```
policyforge etl-info-blocking
```

`framework.yaml` records the effective date fetched, the exact URL, and the
SHA-256 of the catalog produced. eCFR has no release tags; the effective
date is the only thing that names a revision. The monthly `framework-drift`
job re-runs this and fails the build if the regulation has moved.

See `ingest/info_blocking.py` for parsing details — in particular how a
lettered condition is told apart from a roman numeral, since eCFR's XML
puts `(a)`, `(1)` and `(i)` in flat sibling elements and `(i)` is both the
ninth letter and roman one.

## No crosswalk

Unlike `hipaa-security-rule`, this catalog carries no
`source_crosswalk` and is not wired into `mapping/crosswalk.py`.

That is a decision, not an omission. HIPAA's mapping exists because NIST
publishes an official HIPAA-to-800-53 crosswalk that this project ingests
(`etl-hipaa-crosswalk`); there is no equivalent authority mapping Part 171
to a control framework, and for the reason above there may be no coherent
one to publish. A crosswalk invented here would be this project's opinion
wearing the source's authority.
