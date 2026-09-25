"""No silent escalation (#361, 80's ruling half 1).

A reasoning model can spend its whole budget thinking and return an empty,
billed reply. Measured on #301: sonnet's Evaluation Standard came back empty
at 16,384 tokens, and the provider's re-send at 131,072 had a worst case of
$1.41, with nothing telling the user. Every bigger-budget re-send is now
announced before it is sent (the topic, the model, the new max_tokens and
the worst case at the model's list price), and the billed attempt before it
is kept in that call's ledger row.
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

from policyforge.llm import escalation, ledger
from policyforge.llm.litellm_provider import LiteLLMProvider


def _reply(text, finish, *, cost, prompt=1000, completion=16384, rid="gen-1"):
    choice = SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish)
    usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
    return SimpleNamespace(
        choices=[choice], usage=usage, id=rid, model="m", _hidden_params={"response_cost": cost}
    )


class _Completion:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, **payload):
        self.calls.append(payload)
        return self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]


def _wrapped(model, completion, path):
    inner = LiteLLMProvider(model=model)
    inner._completion = completion
    return ledger.RecordingProvider(
        inner, provider_name="litellm", provider_class="cloud", path=path
    )


def test_a_re_send_is_announced_and_both_attempts_are_in_the_ledger(tmp_path, capsys):
    """The #301 shape: empty and cut off at 16,384, then re-sent at 8x."""
    completion = _Completion(
        _reply("", "length", cost=0.1985, rid="gen-first"),
        _reply("# Standard\n\nText.", "stop", cost=0.30, completion=26338, rid="gen-second"),
    )
    provider = _wrapped("anthropic/claude-sonnet-5", completion, tmp_path / "calls.jsonl")

    with ledger.about("standard/ai-evaluation-measurement", site="generate"):
        provider.generate(system="s", prompt="p", max_tokens=16384)

    said = capsys.readouterr().err
    assert "standard/ai-evaluation-measurement" in said, "the topic"
    assert "max_tokens 131,072" in said and "16,384" in said, "the new budget and the old"
    assert "worst case $" in said and "claude-sonnet-5" in said, "priced at the model's list price"
    assert "$0.1985, billed" in said, "the empty first attempt was billed"
    assert [c["max_tokens"] for c in completion.calls] == [16384, 131072]

    (row,) = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert row["request_id"] == "gen-second"
    (first,) = row["escalations"]
    assert first["first_request_id"] == "gen-first", "the billed first attempt is on the record"
    assert first["first_cost_usd"] == 0.1985
    assert first["max_tokens"] == 131072 and first["first_max_tokens"] == 16384
    assert first["subject"] == "standard/ai-evaluation-measurement"


def test_the_worst_case_is_the_new_budget_at_the_list_price():
    """The arithmetic, shown: input at the input price plus the NEW max_tokens
    at the output price, from LiteLLM's own table entry, which is named."""
    price = escalation._price("openrouter/anthropic/claude-sonnet-5")
    assert price is not None, "the premise: the model is in LiteLLM's table under some name"
    out = io.StringIO()
    e = escalation.announce(
        model="openrouter/anthropic/claude-sonnet-5",
        first_max_tokens=16384,
        max_tokens=131072,
        input_tokens=17448,
        out=out,
    )
    assert e.worst_case_usd == pytest.approx(17448 * price[0] + 131072 * price[1], rel=1e-6)
    assert e.price_source == price[2]
    escalation.take()


def test_an_unknown_model_is_unpriced_not_guessed():
    out = io.StringIO()
    e = escalation.announce(
        model="local/some-model", first_max_tokens=64, max_tokens=512, input_tokens=10, out=out
    )
    assert e.worst_case_usd is None
    assert "worst case unpriced: up to 512 output tokens" in out.getvalue()
    escalation.take()


def test_a_call_with_no_re_send_announces_nothing(tmp_path, capsys):
    completion = _Completion(_reply("fine", "stop", cost=0.01, completion=10))
    provider = _wrapped("anthropic/claude-sonnet-5", completion, tmp_path / "calls.jsonl")
    with ledger.about("standard/x", site="generate"):
        provider.generate(system="s", prompt="p", max_tokens=100)
    assert capsys.readouterr().err == ""
    (row,) = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert row["escalations"] == []


def test_an_escalation_that_then_fails_is_still_recorded(tmp_path, capsys):
    """Empty again after the re-send: the call raises, and its row still
    carries the escalation and the billed first attempt."""
    completion = _Completion(
        _reply("", "length", cost=0.2, rid="gen-a"), _reply("", "length", cost=1.3, rid="gen-b")
    )
    provider = _wrapped("anthropic/claude-sonnet-5", completion, tmp_path / "calls.jsonl")
    from policyforge.llm._inline_thinking import ReasoningBudgetExhausted

    with ledger.about("standard/x", site="generate"), pytest.raises(ReasoningBudgetExhausted):
        provider.generate(system="s", prompt="p", max_tokens=100)
    (row,) = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert row["error"] and row["escalations"][0]["first_request_id"] == "gen-a"


def test_effort_announces_its_own_2x_retry(capsys):
    """`effort` retries a cut-off reply at 2x the budget: a budget
    escalation too, announced the same way."""
    from policyforge.llm import effort
    from policyforge.llm.base import LLMResponse

    replies = [
        LLMResponse(text="partial", model="m", stop_reason="length", output_tokens=100),
        LLMResponse(text="whole", model="m", stop_reason="stop"),
    ]

    class Fake:
        def generate(self, **kwargs):
            return replies.pop(0)

    with ledger.about("standard/y", site="generate"):
        effort.call(Fake(), system="s", prompt="p", max_tokens=1000)
    said = capsys.readouterr().err
    assert "standard/y" in said and "max_tokens 2,000" in said and "cut off" in said
    escalation.take()


def test_the_anthropic_shim_announces_its_re_send(capsys):
    """`_anthropic_compat`, shared by the Anthropic and Vertex providers:
    a thinking block and no text at max_tokens is re-sent at 8x."""
    from policyforge.llm._anthropic_compat import call_messages_api

    def message(blocks, stop, rid, usage):
        return SimpleNamespace(
            content=blocks,
            stop_reason=stop,
            _request_id=rid,
            model="claude-sonnet-5",
            usage=SimpleNamespace(
                input_tokens=usage[0],
                output_tokens=usage[1],
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )

    thinking = SimpleNamespace(type="thinking", thinking="...")
    text = SimpleNamespace(type="text", text="ok")
    replies = [
        message([thinking], "max_tokens", "req_1", (900, 64)),
        message([text], "end_turn", "req_2", (900, 20)),
    ]
    calls = []

    def create(**payload):
        calls.append(payload["max_tokens"])
        return replies.pop(0)

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    with ledger.about("standard/w", site="generate"):
        call_messages_api(
            client, model="claude-sonnet-5", system="s", prompt="p", max_tokens=64, temperature=0.2
        )
    said = capsys.readouterr().err
    assert calls == [64, 512]
    assert "standard/w" in said and "max_tokens 512" in said and "worst case $" in said
    (e,) = escalation.take()
    assert e["first_request_id"] == "req_1" and e["input_tokens"] == 900


def test_the_openai_compatible_provider_announces_its_re_send(capsys, monkeypatch):
    from policyforge.llm.openai_compat_provider import OpenAICompatProvider

    provider = OpenAICompatProvider(model="local/q", base_url="http://localhost:1/v1")
    posts = [
        {
            "id": "r1",
            "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 64},
        },
        {
            "id": "r2",
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {},
        },
    ]
    monkeypatch.setattr(provider, "_post", lambda payload: posts.pop(0))
    with ledger.about("synthesis/z", site="synthesize"):
        provider.generate(system="s", prompt="p", max_tokens=64)
    said = capsys.readouterr().err
    assert "synthesis/z" in said and "max_tokens 512" in said and "unpriced" in said
    escalation.take()
