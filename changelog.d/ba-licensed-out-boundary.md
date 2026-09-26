**`etl-hitrust` and `etl-govramp` now refuse to write a licensed catalog
where the model boundary would not treat it as licensed, and exit non-zero,
even with `--force`.** Before, `--out output/hitrust/controls.json` was
accepted because git ignores `output/`, and the catalog was then read as
your organisation's own material, which a hosted model may receive, so your
boundary settings for licensed content were not applied to it. Write licensed
catalogs under `local_content/`, for example `--out local_content/hitrust/controls.json`,
or in a directory of your own `frameworks/` with no `framework.yaml`
declaring it public domain. **If you script either command with another
`--out`, it will now fail**; the refusal names where to write instead. Run
the command from your project's root, because the boundary reads its search
paths from there.

**A licensed catalog these commands write is now held to your boundary
settings.** Previously, one saved outside `local_content/` was treated as your
own content and could reach a hosted model even if your boundary kept
licensed content local. If you wrote a HITRUST or GovRAMP catalog outside
`local_content/` with an earlier version, re-run the ETL into
`local_content/` so your settings apply to it.
