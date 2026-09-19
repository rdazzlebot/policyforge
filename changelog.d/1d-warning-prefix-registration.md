**A warning the answering path writes can no longer be silently dropped from
eval reports.** `evals/runner.py` picks entailment findings out of an
answer's warnings by the words they open with, and a new prefix that was not
added to its filter would have been discarded with nothing reporting it —
the finding made, written into the answer, and absent from every report,
with the output looking exactly as it does today. The prefixes are now
enumerated from `zardoz/answer.py` and each is asserted to survive the
filter, so adding one and forgetting the other edit fails a test instead.
