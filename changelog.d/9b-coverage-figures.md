**What `/coverage` reports across this release, in one place.** Three things
moved it and they moved it for three different reasons, so the percentage
alone cannot tell you which happened.

```
                              in scope   owned          orphaned
v1.5.0                            1657    814 (49%)          397   <- see below
1.6, no AI topics adopted         1014    814 (80%)          200
1.6, AI topics adopted            1105    905 (82%)          200
```

**The v1.5.0 row does not add up, and that is the defect this release
fixes rather than a typo here.** 1657 − 814 is 843, not 397. The owned
count was measured over the NIST 800-53 set and the denominator over
every catalog on disk, so `814/1657` was **a ratio of two different
populations**. Measured over one population at that same commit, v1.5.0's
programme was 1014 in scope, 814 owned, 200 orphaned — which reconciles,
and is the same 814 and the same 200 you see below.

**So 49% was never a true statement about a programme, and 49% → 80% is
not a 31-point gain anybody earned.** The programme did not change. The
measurement became correct.

**The scope moved twice.** It stopped counting requirements no topic could
ever claim — a HIPAA or CFR identifier was an orphan by construction — and
it started counting the NIST AI RMF for registries that anchor it.

**The numerator moved once**, because topics now claim the AI RMF. That is
the only one of the three that means more of your programme is covered.

**Which figure you see depends on adoption, not on upgrading.** A programme
that adopts none of the AI topics is at 80% and its orphan count is
unchanged at 200. Adopting them takes it to 82%. The report's scope line
names the catalogs it counted:

```
Coverage — scope: all controls (NIST 800-53, NIST AI RMF)
Coverage — scope: all controls (NIST 800-53)
```

so a moved denominator is visible on the line rather than inferred from a
number changing.

**Figures measured on the release commit**, with the example registry. Your
own numbers depend on your registry; the shape of the change does not.
