# NIST 800-53 Rev 5

Public domain (US federal government work). Populate this directory by
running the ETL against an existing structured source, e.g.:

```
policyforge etl-vault --controls-dir /path/to/your/vault/Frameworks/NIST-800-53/Controls --out data/frameworks/nist-800-53-r5/controls.json
```

Or source directly from NIST's own OSCAL catalog:
https://csrc.nist.gov/projects/risk-management/sp800-53-controls
