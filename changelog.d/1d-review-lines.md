**`scripts/review_lines.py` reads a pull request's `Reviewed-SHA:` verdict
lines and says what each one is a claim about.** The review record here is
a convention rather than a mechanism — every session authenticates as the
same account, so GitHub's own approvals are refused as self-approval — and
a convention has no validator, so every failure it has had has been silent.

**A well-formed SHA that names nothing splits three ways, and they differ
in whether the review survives.** Three sessions produced one of these in a
single day — forty hex characters, syntactically perfect, naming no object,
because the visible prefix of an abbreviated display was extended with
invented characters. If the longest resolving prefix *is* the reviewed head,
the prefix is evidence the reviewer read the right commit: a correct review
with a broken anchor, and recoverable. If it names a different commit, what
was read is unknown. If nothing resolves, nobody read anything identifiable.
The message names the object the prefix resolves to, because **the remedy is
in the display, not in the discipline** — the rule *never lengthen an
abbreviated SHA* has now failed three times, and it asks a person to resist
something the tooling hands them.

**Five states, because "not at head" was hiding four different facts.**
`AT HEAD` is the only one that counts. `STALE` is a real ancestor. `ELSEWHERE`
is a real commit that is *not* an ancestor — a review against a pre-rebase
history, which reads as valid to a naive tool. `FABRICATED` is a well-formed
SHA naming no object, which has happened here. `MALFORMED` is a SHA that is
not 40 hex, reported separately from whether it resolves.

**Shape and location are asked independently**, because chaining them meant
a malformed line never had its ancestry asked and the tool credited a review
the pull request had never carried.

**A stale approval and a stale block are opposite facts.** An expiring
approval is safe — the work changed, read it again. An expiring
`changes-requested` is not: a push about something unrelated turns an
unanswered objection into "no blocking verdicts". Stale blocks are warned
about separately, and the warning is suppressed when that same reviewer
later approved at head.

**It refuses rather than reports when its own population is short**, by
comparing the comment list it assembled against the count GitHub maintains —
two derivations independent in dimension. And it prints its timestamp and
population in the first three lines, because a report that was true when
taken and false when read has already caused one misroute.

**It does not compute consent**, deliberately. Counting verdicts into a merge
decision would turn a written convention into an authorisation mechanism, and
no such mechanism exists. A reader reports; a person decides.
