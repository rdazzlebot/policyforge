**The NIST SP 800-171 rev 3 catalog now carries NIST's own mapping to
800-53.** NIST's OSCAL file, the one this catalog is built from, links every
one of its 97 requirements to the 800-53 controls it was derived from: 157
links, 114 to controls and 43 to control enhancements. Until now the catalog
kept none of them, so `/coverage` reported 800-171 as reaching nothing. With
the example topic registry it now reports 97 of 97 requirements mapping to an
owned 800-53 control, and `policyforge map` gains 157 800-171 entries across
155 800-53 controls. The 800-53 coverage figures (1,105 in scope, 905 owned)
and topic anchoring are unchanged: 800-171 is still reached through 800-53,
not anchored beside it. `policyforge etl-800-171` now refuses to write the
catalog unless every link resolves to an 800-53 control or enhancement. The
catalog's `content_sha256` changes because the catalog it is computed over
changed; the NIST source it was built from did not.
