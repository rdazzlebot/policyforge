**A command the product prints is now checked against the CLI that has to
run it.** Every backtick-quoted `policyforge …` carrying a flag is extracted
and each flag verified against `--help` on the live CLI, so a printed
command cannot name an option the product does not accept.

**Three sites interpolated a value inside hand-written quotes.** A document
title is user-authored prose, so `--title "Vendor "Bring Your Own" Policy"`
parses as `--title "Vendor Bring"` — a valid command naming the wrong
document, with nothing to indicate it went wrong. Those now use
`shlex.quote`, which handles the quote characters the value may itself
contain.

Illustrative strings — `satisfies --controls ...`, `--content-dir <your markdown tree>` — are recognised as examples rather than invocations. A
class check that cannot say *this one is an example* fails on strings doing
their job, which is the fastest way to get it deleted.
