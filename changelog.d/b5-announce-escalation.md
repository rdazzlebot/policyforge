**PolicyForge now tells you when it re-sends a request with a bigger token
budget, and what that could cost.** A reasoning model can spend its whole
budget thinking and return nothing, which is still billed. PolicyForge then
re-sends the request with up to eight times the budget. That used to happen
silently: measured on one AI Standard with Claude Sonnet 5, an empty reply
cost $0.20, and the re-send could have cost up to $1.41 more. You now get a
warning before the re-send goes out, naming the document, the model, the new
budget and the worst-case cost at that model's list price ("unpriced" when no
price is known). The call log (`output/.model-log/calls.jsonl`) records the
billed attempt that came back empty, with its request id and cost, under
`escalations`.
