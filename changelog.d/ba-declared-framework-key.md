**A catalog can now declare its framework key in `framework.yaml`.** Add
`framework_id: acme-baseline` beside `name:`, and every place PolicyForge keys that
catalog's name will use your key, including crosswalks, coverage and
citations. Before, a name the built-in table did not know was keyed by its
first word, so "NIST Privacy Framework" and every other unlisted NIST name
shared the key `nist`. Every bundled catalog now declares its key, and none
of those keys changed. `etl-hitrust` and `etl-govramp` now write the
declaration beside the catalog they import, with the key the name already
had; a `framework.yaml` you wrote yourself is kept, and a different key in it
is named rather than replaced. PolicyForge warns only when the name alone
would have produced another framework's key, since citations written before
the declaration were then filed under that framework. Name lookup now
ignores extra spacing, so an irregularly spaced name may key differently
than it did.
