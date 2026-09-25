**A catalog can now declare its framework key in `framework.yaml`.** Add
`crosswalk_as: acme-baseline` beside `name:`, and every place PolicyForge keys that
catalog's name will use your key, including crosswalks, coverage and
citations. Before, a name the built-in table did not know was keyed by its
first word, so "NIST Privacy Framework" and every other unlisted NIST name
shared the key `nist`. Every bundled catalog now declares its key, and none
of those keys changed. If a declared key differs from the one the name would
have produced, PolicyForge says so by name.
