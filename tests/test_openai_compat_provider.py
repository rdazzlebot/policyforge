"""The OpenAI-compatible endpoint provider, driven through an injected fake
session so none of this needs a server running.

The cases worth having are the two that bite in practice and neither of
which is about HTTP: a reasoning model putting its chain of thought in the
same field as its answer, and a small `max_tokens` being spent entirely on
that preamble. The second is the local restatement of a bug this project
already measured on the Anthropic path at roughly one call in eight.
"""

from __future__ import annotations

import pytest


class FakeSession:
    """Stands in for `requests.Session` — the provider only ever calls
    `.post(url, json=..., headers=..., timeout=...)` on it."""

    class _Response:
        def __init__(self, payload, status_code=200, text=""):
            self._payload = payload
            self.status_code = status_code
            self.text = text

        def json(self):
            return self._payload

    def __init__(self, replies=None, status_code=200, raise_exc=None):
        #: One payload per call, so a retry can be given a different reply.
        self.replies = list(replies or [])
        self.status_code = status_code
        self.raise_exc = raise_exc
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if self.raise_exc is not None:
            raise self.raise_exc
        payload = self.replies.pop(0) if self.replies else {}
        return self._Response(payload, self.status_code, text="server said no")


def _reply(content, finish_reason="stop", model="qwen3:14b"):
    return {
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 5},
    }


def _provider(session, **kwargs):
    from policyforge.llm.openai_compat_provider import OpenAICompatProvider

    return OpenAICompatProvider(
        model=kwargs.pop("model", "qwen3:14b"),
        base_url=kwargs.pop("base_url", "http://localhost:11434/v1"),
        session=session,
        **kwargs,
    )


def test_it_sends_the_expected_request_and_parses_the_response():
    session = FakeSession([_reply("hello from ollama")])

    result = _provider(session).generate(system="sys", prompt="hi", max_tokens=64)

    sent = session.calls[0]
    assert sent["url"] == "http://localhost:11434/v1/chat/completions"
    assert sent["json"]["model"] == "qwen3:14b"
    assert sent["json"]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    assert sent["json"]["max_tokens"] == 64
    assert result.text == "hello from ollama"
    assert (result.input_tokens, result.output_tokens) == (11, 5)


def test_a_trailing_slash_in_base_url_does_not_double_up():
    session = FakeSession([_reply("ok")])

    _provider(session, base_url="http://localhost:11434/v1/").generate(system="s", prompt="p")

    assert session.calls[0]["url"] == "http://localhost:11434/v1/chat/completions"


def test_a_reasoning_preamble_is_not_part_of_the_answer():
    """A <think> block is not an answer, for the same reason a thinking
    block isn't one on the Anthropic path."""
    session = FakeSession([_reply("<think>The user wants a word.</think>ok")])

    assert _provider(session).generate(system="s", prompt="p").text == "ok"


def test_a_budget_spent_entirely_on_thinking_is_retried_with_room_to_speak():
    """The failure this exists to prevent: every token went into an
    unterminated <think>, so the reply is pure reasoning. Returning "" for
    that is indistinguishable from the model deciding to say nothing, and
    callers read that as a decision — Zardoz's router reads an empty reply
    as "not an analysis" and silently routes to the documents instead.
    """
    session = FakeSession(
        [
            _reply("<think>Let me consider whether this is a covera", finish_reason="length"),
            _reply("coverage"),
        ]
    )

    result = _provider(session).generate(system="s", prompt="p", max_tokens=12)

    assert result.text == "coverage"
    assert len(session.calls) == 2
    # Retried with a real budget rather than the same doomed one.
    assert session.calls[1]["json"]["max_tokens"] >= 256


def test_a_deliberate_empty_answer_is_not_retried():
    """Only a stop-on-length reply is treated as truncation. A model that
    stopped normally with nothing to say has made a decision, and retrying
    it would spend eight times the budget to hear the same silence."""
    session = FakeSession([_reply("", finish_reason="stop")])

    result = _provider(session).generate(system="s", prompt="p", max_tokens=12)

    assert result.text == ""
    assert len(session.calls) == 1


def test_no_auth_header_when_the_endpoint_needs_no_key():
    session = FakeSession([_reply("ok")])

    _provider(session).generate(system="s", prompt="p")

    assert "Authorization" not in session.calls[0]["headers"]


def test_an_api_key_is_sent_when_config_names_one(monkeypatch):
    monkeypatch.setenv("SOME_ENDPOINT_KEY", "sk-local-123")
    session = FakeSession([_reply("ok")])

    _provider(session, api_key_env="SOME_ENDPOINT_KEY").generate(system="s", prompt="p")

    assert session.calls[0]["headers"]["Authorization"] == "Bearer sk-local-123"


def test_a_named_but_unset_api_key_env_is_an_error(monkeypatch):
    monkeypatch.delenv("SOME_ENDPOINT_KEY", raising=False)

    with pytest.raises(RuntimeError) as caught:
        _provider(FakeSession(), api_key_env="SOME_ENDPOINT_KEY")

    assert "SOME_ENDPOINT_KEY" in str(caught.value)


def test_an_unreachable_server_reports_a_connection_failure():
    """evals/runner.py grades a message containing "connection" as
    infrastructure rather than as a failed case, so a server that simply is
    not running must not be reported as the prompt answering wrongly."""
    import requests

    session = FakeSession(raise_exc=requests.exceptions.ConnectionError("refused"))

    with pytest.raises(RuntimeError) as caught:
        _provider(session).generate(system="s", prompt="p")

    assert "connection" in str(caught.value).lower()


def test_a_non_200_reports_the_server_response():
    session = FakeSession([{}], status_code=500)

    with pytest.raises(RuntimeError) as caught:
        _provider(session).generate(system="s", prompt="p")

    assert "500" in str(caught.value)
    assert "server said no" in str(caught.value)


def test_check_is_true_on_an_ok_reply():
    assert _provider(FakeSession([_reply("ok")])).check() is True


def test_check_is_false_on_an_unexpected_reply():
    assert _provider(FakeSession([_reply("certainly!")])).check() is False


def test_get_provider_dispatches_to_openai_compat(monkeypatch):
    from policyforge.llm.base import get_provider

    captured = {}

    class FakeOpenAICompatProvider:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "policyforge.llm.openai_compat_provider.OpenAICompatProvider",
        FakeOpenAICompatProvider,
    )

    for name in ("openai-compat", "local"):
        provider = get_provider(
            {
                "llm": {
                    "provider": name,
                    "model": "qwen3:14b",
                    "base_url": "http://localhost:11434/v1",
                }
            }
        )
        # `get_provider` wraps what it builds in the model-call ledger, so
        # the dispatch is asserted on the factory's result underneath.
        assert isinstance(provider.inner, FakeOpenAICompatProvider)

    assert captured["model"] == "qwen3:14b"
    assert captured["base_url"] == "http://localhost:11434/v1"
    # Absent from config, and that is not an error for a local endpoint.
    assert captured["api_key_env"] is None


def test_get_provider_openai_compat_requires_base_url():
    from policyforge.llm.base import get_provider

    with pytest.raises(ValueError) as caught:
        get_provider({"llm": {"provider": "local", "model": "qwen3:14b"}})

    assert "base_url" in str(caught.value)


def test_a_second_truncation_is_raised_not_returned_as_silence():
    from policyforge.llm._inline_thinking import ReasoningBudgetExhausted

    session = FakeSession(
        [
            _reply("<think>still going", finish_reason="length"),
            _reply("<think>still going and going", finish_reason="length"),
        ]
    )

    with pytest.raises(ReasoningBudgetExhausted):
        _provider(session).generate(system="s", prompt="p", max_tokens=150)

    assert len(session.calls) == 2
