**The rest of HIPAA ships: the Privacy Rule and the Breach Notification
Rule, as two bundled catalogs.** Pass
`data/frameworks/hipaa-privacy-rule/controls.json` or
`data/frameworks/hipaa-breach-notification-rule/controls.json`, and cite
them as `[HIPAA Privacy Rule 164.502(a)(5)(i)(A)(1)]` or
`[HIPAA Breach Notification Rule 164.404(a)(1)]`. Every paragraph is under
the citation eCFR itself gives it. `policyforge etl-hipaa-privacy` rebuilds
both, and refuses to write if eCFR's text changes shape. A citation written
`[HIPAA 164.502(a)]` still resolves to the Security Rule's catalog, where
it names nothing, so write the rule's full name.

**eCFR still prints text a court vacated, and the Privacy Rule catalog
says which.** *Purl v. HHS* (N.D. Tex., 2025) vacated most of the 2024
reproductive-health amendments, and eCFR has not removed them. The catalog
carries eCFR's text as printed, and marks the affected paragraphs in its
`framework.yaml`:

- Paragraphs the 2024 rule added are never used for generation, and
  `policyforge check` warns on a citation to one, naming the judgment.
- Paragraphs the rule only revised are generated from their pre-rule
  wording, which binds again. It is quoted from eCFR's own earlier text.

This is the project's reading of the judgment, not legal advice; the
catalog README cites it.

Neither catalog has a published mapping to 800-53, so neither is anchored
or counted in `/coverage`'s 800-53 figures. Both read there as "no
published crosswalk found", as 42 CFR Part 2 does.
