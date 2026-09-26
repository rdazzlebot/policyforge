**`etl-hitrust` and `etl-govramp` now refuse to write a licensed catalog
where the model boundary would not treat it as licensed, and exit non-zero,
even with `--force`.** Before, `--out output/hitrust/controls.json` was
accepted because git ignores `output/`, and the catalog was then read as
your organisation's own material, which a hosted model may receive. So
generating from it with a hosted provider sent the HITRUST or GovRAMP text
to that provider, and no refusal fired. Write licensed catalogs under
`local_content/`, for example `--out local_content/hitrust/controls.json`,
or in a directory of your own `frameworks/` with no `framework.yaml`
declaring it public domain. **If you script either command with another
`--out`, it will now fail**; the refusal names where to write instead. Run
the command from your project's root, because the boundary reads its search
paths from there.

**If you wrote a HITRUST or GovRAMP catalog anywhere other than
`local_content/` with an earlier version**, move it there, or re-run the ETL
with an `--out` there. Treat any generation from it with a hosted provider as
having sent that content to the provider.
