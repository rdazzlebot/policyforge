Added the **NIST AI Risk Management Framework 1.0** Core as a bundled catalog —
19 categories carrying 72 subcategories, fetched from NIST's AIRC by the new
`policyforge etl-ai-rmf` command. A US government work, so it ships with the
package like the other public-domain catalogs.

**This catalog states outcomes rather than obligations, and that changes what
citing it proves.** Every other catalog here says what an organization must do;
the AI RMF Core says what should end up true — NIST puts the actions in the
separately versioned, explicitly voluntary Playbook. So a document citing a
subcategory can be fully traceable and still commit nobody to anything, and no
check in this project currently tells those apart. The catalog's README says so
in full; read it before citing the catalog.

**There is deliberately no crosswalk.** `satisfies` resolves an AI RMF citation
and then stops. Mapping an outcome to a control would assert that the control
*achieves* the outcome, which is precisely the claim NIST declined to make when
it split the Playbook out.
