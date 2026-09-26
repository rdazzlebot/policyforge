**A generation run now ends by saying what it cost.** `generate`,
`synthesize`, `ssp` and `crosswalk-propose` finish with one line, printed
even when the run fails: the number of requests sent, the cost, and how many
were re-sent with a larger budget, including "0 re-send(s)". For example:
`Run: 2 request(s), $0.5000; 1 re-send(s), whose replaced attempts billed $0.2000 of that.` Re-sends were already announced as they happened; this
line is for a run nobody watched, such as one in CI.

**A cost is no longer reported as a total when part of it is unknown.**
When any call's cost is unknown, the cost is shown as two parts: `$0.2666 known + 13 request(s) of unknown cost`. Before, only the known calls were
added up, and that sum was shown as the whole bill. This applies to the run
line, to `policyforge ledger`'s totals (now `$0.2666 + 13 unpriced`), and to
the `generated_by` record in each document's frontmatter. That record keeps
`cost_usd` only when every call was priced, and now always adds
`cost_known_usd` and `calls_unpriced`. A local model's calls count as free.
Documents generated earlier keep their record as it was; there, a missing
`calls_unpriced` means it was not recorded.
