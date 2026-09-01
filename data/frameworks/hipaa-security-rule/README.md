# HIPAA Security Rule

Public domain (US federal regulation — 45 CFR Part 164, Subpart C:
"Security Standards for the Protection of Electronic Protected Health
Information"). Same basis as NIST 800-53/FedRAMP/ARC-AMPE, so unlike
HITRUST/GovRAMP this is safe to bundle directly rather than treat as BYOC.

Populated: 34 top-level Standards carrying 41 Required/Addressable
implementation specifications between them (75 requirements in total),
drawn from §§ 164.306, 164.308, 164.310, 164.312, 164.314, 164.316,
164.318 — the definitions section, § 164.304, is intentionally excluded
since defined terms aren't requirements.

Source: eCFR's public versioner API,
<https://www.ecfr.gov/api/versioner/v1/full/%7Bdate%7D/title-45.xml?part=164>
— not a hand-copied transcription, so this can always be regenerated and
diffed against the actual current regulation text:

```
policyforge etl-hipaa
```

Only the Security Rule (Subpart C) is parsed — HIPAA's Privacy Rule
(Subpart E) and Breach Notification Rule (Subpart D) are out of scope for
this security-focused pipeline. See `ingest/hipaa_loader.py` for parsing
details, including how it resolves citation-hierarchy ambiguity and why
Required/Addressable tagging can't be assumed to sit at a fixed nesting
depth.

## NIST 800-53 crosswalk

**Wired into `mapping/crosswalk.py`.** Each Standard and implementation
specification carries NIST's official mapping to SP 800-53 Rev 5 in its
`source_crosswalk["nist"]`, so `build_crosswalk()` resolves a NIST control
ID to its HIPAA equivalents and `synthesize` pulls HIPAA requirements into
a NIST-anchored topic.

Coverage: **65 of the 75** requirements are mapped (25 Standards, 40
implementation specifications) across **278 distinct citation-to-control
pairs**, reaching **108 distinct SP 800-53 controls**. The 10 unmapped are
ones NIST's crosswalk doesn't cover, and are reported by name each time the
ETL runs rather than left invisible: § 164.306(a)-(e) (general rules),
§ 164.318(a)-(c) (compliance dates), and the two bare "Implementation
specifications" container paragraphs, § 164.308(a)(5)(ii) and
§ 164.314(a)(2), whose child specifications *are* individually mapped.

### Source

NIST's **Cybersecurity and Privacy Reference Tool (CPRT)** catalog
`HIPAA-Security-Rule-to-SP-800-53-Rev-5.1.1`:

|                              |                                                                                                        |
| ---------------------------- | ------------------------------------------------------------------------------------------------------ |
| Framework version identifier | `HIPAA-Sec-Rule-800-53-5.1.1`                                                                          |
| Version                      | 1.0.0                                                                                                  |
| NIST OLIR hash               | `80EE1B51D5B48F394E35311A9A93006D2F9E530E35266C6F1F00EB212B776B95`                                     |
| Retrieved                    | 2026-08-28                                                                                             |
| Landing page                 | <https://csrc.nist.gov/projects/cprt/catalog#/cprt/framework/version/HIPAA-Sec-Rule-800-53-5.1.1/home> |

Fetched from CPRT's public API — one request per OLIR element type
(`olir_entry`, `fde`, `rde`) — not hand-transcribed, so it can be
regenerated and diffed against what NIST currently publishes:

```
policyforge etl-hipaa-crosswalk
```

```
https://csrc.nist.gov/extensions/nudp/services/json/nudp/framework/version/HIPAA-Sec-Rule-800-53-5.1.1/type/{element_type}/elements
```

**Not from the SP 800-66r2 PDF.** SP 800-66 Rev. 2 is the natural-looking
source, but its Appendix D states that "the mapping table has been removed
from the document and placed online in the NIST Cybersecurity and Privacy
Reference Tool (CPRT)" — the published PDF contains no SP 800-53 control
identifiers anywhere in its 122 pages. CPRT is the authoritative source.

### Reproducibility and auditing

The exact CPRT responses this data was built from are committed verbatim at
`tests/fixtures/cprt_hipaa_to_800-53r5.json`, so the mapping is auditable
without network access and a NIST-side revision shows up as a fixture diff:

```
policyforge etl-hipaa-crosswalk --fixture tests/fixtures/cprt_hipaa_to_800-53r5.json
```

Both forms produce byte-identical output as of the retrieval date above.

Two source-shape mismatches are reconciled by the `CITATION_ALIASES` table
in `ingest/hipaa_crosswalk_loader.py` — CPRT cites some Standards one
paragraph level higher than the CFR codifies them, and a few citations
reflect a pre-Omnibus paragraph numbering. Every alias is asserted
text-equivalent against the eCFR data in
`tests/test_hipaa_crosswalk_loader.py`, so a CFR renumbering or CPRT
revision fails the test suite instead of silently mis-mapping a
requirement. Nothing is mapped by inference: `tests` also assert that every
stored control ID traces back to an actual published CPRT row.
