Split `NIST_ANCHOR` into two constants, because one name was serving two
different ideas.

`NIST_ANCHOR` is the **crosswalk** anchor — what every other framework's
requirements are mapped *onto*. It stays singular, because an overlay row
asserts "this requirement and that control are the same obligation", which
needs one side fixed. `TOPIC_ANCHORS` is the set of catalogs a **topic
registry** may claim identifiers from, and a programme can be organised
around more than one without either becoming what the other maps onto.

No behaviour changes: the set equals `{NIST_ANCHOR}` today, and a test says
so rather than the release note asserting it.

**Why it is worth a fragment at all.** The obvious way to let topics anchor
a second catalog is to widen `NIST_ANCHOR`, which also widens the crosswalk
sites — and a catalog that becomes a crosswalk *target* becomes one
`crosswalk seed` will generate a mapping for. For the NIST AI RMF that
mapping is refused on product grounds. So the natural refactor would have
published the thing the project decided not to publish, while looking
exactly like the change that was asked for.

Also reworded two error messages that named NIST 800-53 directly. They now
name the anchor set, so they stay true when it widens; a false error message
is worse than a missing one, because it is confident and sends the reader to
fix the wrong thing.
