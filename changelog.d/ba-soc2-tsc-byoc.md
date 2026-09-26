**SOC 2's Trust Services Criteria can now be brought in from your own
copy.** `policyforge etl-soc2-tsc --criteria <text export> --out local_content/soc2-tsc/controls.json`
reads a plain-text export you make from your own copy of the AICPA's
criteria, and writes a licensed catalog in `local_content/`. Nothing of
the AICPA's ships with PolicyForge, and nothing is fetched from the AICPA.
The catalog README quotes the AICPA's terms. Whether they permit this use
is your decision. Cite the criteria as `[AICPA Trust Services Criteria CC1.1]`.

**This ETL was built and tested only against synthetic input**, because the
project holds no copy of the criteria, so your run is the first real one.
It refuses the whole file, writing nothing, if its shape differs from what
it expects (a line that starts like an id but isn't one, a repeated id, an
empty criterion, or a gap in a group's numbering), and names the line.

**If you also have the AICPA's mapping to NIST SP 800-53** (`--mapping`), its
links are read as partial, because the mapping states no relationship and
predates 800-53 Rev 5. Each 800-53 id NIST marks as changed substantively
since Rev 4 is flagged, from NIST's own comparison workbook. An id withdrawn
in Rev 5, or not a Rev 5 id, is refused by name, never remapped.
