**Reasoning a local server returns in its own field is no longer recorded as
zero.** Ollama and vLLM put a reasoning model's chain of thought in
`message.reasoning`, leaving `content` as the answer alone — so nothing was
stripped and the ledger wrote `stripped_reasoning_chars: 0`, which is
indistinguishable from a model that did not think. The stripper was working;
it was pointed at a field that never had reasoning in it. `llm/base.py` is
explicit that this is the one thing that field must not do: *a zero asserted
by a provider that never looked is a measurement nobody made.* Measured on a
live call, `qwen3:14b` returned **1,081 characters of reasoning against an
85-character answer**, with 263 output tokens billed for it — roughly nine
tokens in ten spent thinking, none of it visible to the ledger before.
`reasoning_content` is read too, since a local endpoint is whichever of the
two you happen to run, and `completion_tokens_details.reasoning_tokens` now
populates `hidden_output_tokens` where a server reports it, staying `None`
where it does not.

**`generate_json` works against a local endpoint**, so a schema-constrained
call no longer requires a vendor. **This is the only route on which a
licensed catalog's text never leaves the machine**, which is the argument for
running locally at all. `supports_schema` is True because a live call proved
it rather than because a capability table says so, and the reply is still
parsed and checked — an endpoint that ignores `response_format` answers with
prose and a 200, and that now raises rather than returning unconstrained text
from a method whose contract is that the text is constrained.

**A cascade with a local primary now advertises `schema`.** A cascade reports
the conjunction of its halves; the local half gained a capability, so the
conjunction gained one. Nothing about the rule changed.
