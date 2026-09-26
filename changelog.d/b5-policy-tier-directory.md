**`generate` now writes Policies to `output/policies/`, where `check`
reads them.** It wrote them to `output/policys/`, which `check` does not
recognise, so every generated Policy was reported as having "no tier".
`import-confluence` wrote imported Policies there too; it now uses
`output/policies/` as well.

**`check` no longer reports a Policy as "missing" its synthesis's
citations.** A Policy leaves framework citations out by design, since that
traceability lives in the Standard. The warning had been appearing
alongside the "no tier" one, and it would have stayed after the directory
fix, because the citation check did not look at the tier. Standards and
Procedures are checked as before.

**If you have an `output/policys/` directory, move its files to
`output/policies/`.** `check` now names each file there and says where it
belongs. Until you move them, `import-confluence` still reads a Policy
from the old directory, so its content class carries over to the import.
