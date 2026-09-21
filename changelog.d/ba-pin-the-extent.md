**Two internal checks that reported success over a population they had
quietly halved now refuse it.** Neither is a command you run, and neither
changes any output — this is the project's own tooling catching its own
blind spot.

`scripts/shell_status.py`, which refuses committed shell that reports
success for a command that failed, guarded its own population by asking
whether it was empty. Breaking a pathspec so it matched one workflow
instead of three left it reporting `clean across 41 source(s)` and
exiting 0, with two workflow files unexamined. It now compares the files
a crude scan says contain shell against the files its parser actually
read, and names any that stopped being read.

The guard on printed commands did the same: narrowing the span it
searches took its population from 14 interpolated values to 11 with the
suite still green, and a real unquoted value among the missing three went
uncaught. It now pins which values it expects to find, by module and
expression.

**Nothing about the product changes.** No command, option, output or exit
code differs. The reason it is worth a line is that both guards had
already been reviewed, mutation-tested and merged — *non-empty* looked
like asserting the population, and it is the special case where the
expected extent is "more than zero".
