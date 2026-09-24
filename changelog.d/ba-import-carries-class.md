**`import-confluence` now keeps a licensed document off a public wiki.** An
imported page used to come back with no frontmatter, so it lost the content
class that stops licensed text reaching a public GitHub wiki. That became a
live risk as soon as someone declared a wiki target on the import. The
import now carries the class forward from the local draft or its recorded
versions, and never invents one: if nothing local says, the command prints
that the class is unknown. It also records where the page came from
(`imported_from`: space, title, page version, date) and never claims a model
wrote text a person may have edited. `content check` lists imported
documents as imported.
