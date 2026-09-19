**Entailment checking asks the judge fewer times for the same findings.**
A sentence citing several passages is supported if any one of them carries
it, but every citation was judged before the first verdict was looked at —
so a supported sentence citing three passages cost three model calls on the
judging model where one would do, and the supported case is the common one.
It now stops at the first passage that carries the sentence. **Findings are
unchanged**: when nothing supports a sentence every citation is still
judged, because preferring a contradiction over a "says nothing about it"
needs all of them, and stopping early there would bury a real contradiction
behind whichever passage happened to be cited first. Only reachable with
`entail.answering: true`, which is off by default.
