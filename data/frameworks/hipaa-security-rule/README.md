# HIPAA Security Rule

Public domain (US federal regulation — 45 CFR Part 164, Subpart C:
"Security Standards for the Protection of Electronic Protected Health
Information"). Same basis as NIST 800-53/FedRAMP/ARC-AMPE, so unlike
HITRUST/GovRAMP this is safe to bundle directly rather than treat as BYOC.

Populated (34 requirements: standards + their Required/Addressable
implementation specifications, drawn from §§ 164.306, 164.308, 164.310,
164.312, 164.314, 164.316, 164.318 — the definitions section, § 164.304,
is intentionally excluded since defined terms aren't requirements).

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

**Not yet in `mapping/crosswalk.py`.** This data is loaded and available
via `policyforge etl-hipaa` / `load_controls`, but nothing yet links these
HIPAA citations to NIST 800-53 controls, so `synthesize` won't pull HIPAA
requirements into a topic until that crosswalk exists. NIST SP 800-66
Rev. 2 publishes an official HIPAA-Security-Rule-to-NIST-800-53 crosswalk
that's the natural source for this — building a loader for it is the next
step, not yet done here.
