**The model-call ledger keeps every known cost when a call's total is
unknown.** When a request is re-sent with a larger budget and one attempt's
cost is unknown, the row's `cost_usd` is left empty rather than showing
only the known part as the total. Until now, the known cost of the re-send
after an unknown first attempt was recorded nowhere. It is now kept in a
new field, `last_cost_usd`, which is filled only on a row whose total is
empty, so it is never added to a known total. A cascade whose first model
reports no cost now also leaves the total empty: before, the stronger
model's cost alone was recorded as the whole bill, although the first
model's attempts were billed too. We found no such row in the 1,210 ledger
rows we checked, but only 16 of them were written by a version that
records re-sends, and none of those 16 had one. LiteLLM prices both
attempts of one model the same way, so this mainly affects a local or
OpenAI-compatible first model escalating to a priced one.

**A reply that should have been JSON and was not is now recorded with its
request id, cost and tokens.** It was billed, but its ledger row had no
cost and no request id: 22 rows in the ledgers we checked, from glm and
deepseek runs. And a local or OpenAI-compatible server's request id is now
kept on every call: each of the 5 local rows we checked had none.
