**`/coverage` in the shell no longer counts every catalog as NIST scope.**
Installing a catalog used to move the headline percentage without anything
about the programme changing: the denominator grew, the owned count did
not, and the percentage fell. A falling percentage reads as *you got
worse*.

The report's scope is the NIST 800-53 set the topic registry anchors to.
Every other catalog was being handed to it as that scope, so a HIPAA or
CFR requirement was an orphan by construction: no topic anchors to its
identifiers, and none ever could. They are now reported where they belong,
through the crosswalk, which is what `/addresses` in the same shell has
always done.

```
In scope   1014      Owned  814 (80%)      Orphaned  200

HIPAA reachable via the crosswalk          65 of 74
NIST-800-171 reachable via the crosswalk    0 of 97
```

**A zero there says which kind of zero it is.** Three frameworks report
none, for two reasons that want opposite responses: nobody has published a
mapping, or mapping it would assert something the documents do not say.
The information-blocking catalog is the second kind — its entries are
conditions of an exception, not controls — and `crosswalk seed` has
refused to seed it since 1.5.0. The report now says so rather than
printing the same zero under a heading that reads as a gap.

The numbers no longer depend on what else is installed, so they are
comparable between machines and across an upgrade.
