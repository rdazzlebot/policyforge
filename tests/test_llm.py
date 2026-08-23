"""LLM provider layer tests: the Bedrock Converse API request/response
shape (via an injected fake client, so no boto3 install or live AWS
credentials are required), the Anthropic-SDK-shaped request/response
handling shared by AnthropicProvider and VertexProvider (including the
`temperature`-deprecation retry), and the provider factory's dispatch."""

from __future__ import annotations

import httpx


def _bad_request_error(message: str):
    import anthropic

    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(400, request=request)
    return anthropic.BadRequestError(message, response=response, body=None)


class FakeAnthropicSdkClient:
    """Stands in for `anthropic.Anthropic` / `anthropic.AnthropicVertex` —
    both expose the same `.messages.create(...)` shape that
    `_anthropic_compat.call_messages_api` and VertexProvider depend on."""

    class _Messages:
        def __init__(self, outer):
            self._outer = outer

        def create(self, **kwargs):
            self._outer.calls.append(kwargs)
            if self._outer.fail_on_temperature and "temperature" in kwargs:
                raise _bad_request_error("`temperature` is deprecated for this model.")

            class Block:
                type = "text"
                text = self._outer.reply_text

            class Usage:
                input_tokens = 7
                output_tokens = 3

            class Response:
                content = [Block()]
                usage = Usage()

            return Response()

    def __init__(self, reply_text="ok", fail_on_temperature=False):
        self.reply_text = reply_text
        self.fail_on_temperature = fail_on_temperature
        self.calls = []
        self.messages = self._Messages(self)


def test_call_messages_api_sends_expected_request_and_parses_response():
    from policyforge.llm._anthropic_compat import call_messages_api

    client = FakeAnthropicSdkClient(reply_text="ok")

    result = call_messages_api(
        client, model="claude-x", system="sys prompt", prompt="hello", max_tokens=16, temperature=0.1
    )

    assert result.text == "ok"
    assert result.model == "claude-x"
    assert result.input_tokens == 7
    assert result.output_tokens == 3
    call = client.calls[0]
    assert call["model"] == "claude-x"
    assert call["system"] == "sys prompt"
    assert call["messages"] == [{"role": "user", "content": "hello"}]
    assert call["temperature"] == 0.1


def test_call_messages_api_retries_without_temperature_when_deprecated():
    from policyforge.llm._anthropic_compat import call_messages_api

    client = FakeAnthropicSdkClient(reply_text="ok", fail_on_temperature=True)

    result = call_messages_api(
        client, model="claude-sonnet-5", system="sys", prompt="hi", max_tokens=8, temperature=0.2
    )

    assert result.text == "ok"
    assert len(client.calls) == 2
    assert "temperature" in client.calls[0]
    assert "temperature" not in client.calls[1]


def test_call_messages_api_reraises_unrelated_bad_request_errors():
    from policyforge.llm._anthropic_compat import call_messages_api

    class FailingClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise _bad_request_error("model not found")

    try:
        call_messages_api(
            FailingClient(), model="nope", system="s", prompt="p", max_tokens=8, temperature=0.2
        )
    except Exception as exc:
        assert "model not found" in str(exc)
    else:
        raise AssertionError("expected the unrelated BadRequestError to propagate")


def test_vertex_provider_sends_expected_request_via_injected_client():
    from policyforge.llm.vertex_provider import VertexProvider

    client = FakeAnthropicSdkClient(reply_text="hello from vertex")
    provider = VertexProvider(model="claude-x", project_id="my-project", client=client)

    result = provider.generate(system="sys", prompt="hi", max_tokens=16, temperature=0.1)

    assert result.text == "hello from vertex"
    assert result.model == "claude-x"
    assert client.calls[0]["model"] == "claude-x"


def test_vertex_provider_check_true_on_ok_reply():
    from policyforge.llm.vertex_provider import VertexProvider

    provider = VertexProvider(
        model="claude-x", project_id="my-project", client=FakeAnthropicSdkClient(reply_text="OK")
    )

    assert provider.check() is True


def test_vertex_provider_check_false_on_unexpected_reply():
    from policyforge.llm.vertex_provider import VertexProvider

    provider = VertexProvider(
        model="claude-x",
        project_id="my-project",
        client=FakeAnthropicSdkClient(reply_text="not what was asked"),
    )

    assert provider.check() is False


def test_vertex_provider_requires_anthropic_vertex_extra_without_injected_client(monkeypatch):
    import builtins

    from policyforge.llm.vertex_provider import VertexProvider

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("no anthropic.vertex extra installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    try:
        VertexProvider(model="claude-x", project_id="my-project")
    except RuntimeError as exc:
        assert "anthropic[vertex]" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when the vertex extra isn't installed")


def test_get_provider_dispatches_to_vertex(monkeypatch):
    from policyforge.llm.base import get_provider

    created = {}

    class FakeVertexProvider:
        def __init__(self, *, model, project_id, region):
            created["model"] = model
            created["project_id"] = project_id
            created["region"] = region

    monkeypatch.setattr("policyforge.llm.vertex_provider.VertexProvider", FakeVertexProvider)

    provider = get_provider(
        {"llm": {"provider": "vertex", "model": "m", "project_id": "proj", "region": "europe-west4"}}
    )

    assert isinstance(provider, FakeVertexProvider)
    assert created == {"model": "m", "project_id": "proj", "region": "europe-west4"}


def test_get_provider_vertex_requires_project_id():
    from policyforge.llm.base import get_provider

    try:
        get_provider({"llm": {"provider": "vertex", "model": "m"}})
    except ValueError as exc:
        assert "project_id" in str(exc)
    else:
        raise AssertionError("expected ValueError when llm.project_id is missing")


class FakeBedrockClient:
    def __init__(self, reply_text="ok", usage=None):
        self.reply_text = reply_text
        self.usage = usage if usage is not None else {"inputTokens": 5, "outputTokens": 2}
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "output": {"message": {"content": [{"text": self.reply_text}]}},
            "usage": self.usage,
        }


def test_bedrock_provider_sends_expected_converse_request():
    from policyforge.llm.bedrock_provider import BedrockProvider

    client = FakeBedrockClient()
    provider = BedrockProvider(model="anthropic.claude-3-5-sonnet", client=client)

    result = provider.generate(system="sys prompt", prompt="hello", max_tokens=16, temperature=0.1)

    assert result.text == "ok"
    assert result.model == "anthropic.claude-3-5-sonnet"
    assert result.input_tokens == 5
    assert result.output_tokens == 2

    call = client.calls[0]
    assert call["modelId"] == "anthropic.claude-3-5-sonnet"
    assert call["system"] == [{"text": "sys prompt"}]
    assert call["messages"] == [{"role": "user", "content": [{"text": "hello"}]}]
    assert call["inferenceConfig"] == {"maxTokens": 16, "temperature": 0.1}


def test_bedrock_provider_check_true_on_ok_reply():
    from policyforge.llm.bedrock_provider import BedrockProvider

    provider = BedrockProvider(model="m", client=FakeBedrockClient(reply_text="OK"))

    assert provider.check() is True


def test_bedrock_provider_check_false_on_unexpected_reply():
    from policyforge.llm.bedrock_provider import BedrockProvider

    provider = BedrockProvider(model="m", client=FakeBedrockClient(reply_text="not what was asked"))

    assert provider.check() is False


def test_bedrock_provider_requires_boto3_without_injected_client():
    from policyforge.llm.bedrock_provider import BedrockProvider

    try:
        import boto3  # noqa: F401
    except ImportError:
        pass
    else:
        return  # boto3 happens to be installed in this environment; nothing to assert.

    try:
        BedrockProvider(model="m")
    except RuntimeError as exc:
        assert "boto3" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when boto3 isn't installed")


def test_get_provider_dispatches_to_bedrock(monkeypatch):
    from policyforge.llm.base import get_provider

    created = {}

    class FakeBedrockProvider:
        def __init__(self, *, model, region):
            created["model"] = model
            created["region"] = region

    monkeypatch.setattr(
        "policyforge.llm.bedrock_provider.BedrockProvider", FakeBedrockProvider
    )

    provider = get_provider({"llm": {"provider": "bedrock", "model": "m", "region": "us-west-2"}})

    assert isinstance(provider, FakeBedrockProvider)
    assert created == {"model": "m", "region": "us-west-2"}


def test_get_provider_rejects_unknown_provider():
    from policyforge.llm.base import get_provider

    try:
        get_provider({"llm": {"provider": "not-a-real-provider"}})
    except ValueError as exc:
        assert "not-a-real-provider" in str(exc)
    else:
        raise AssertionError("expected ValueError for an unknown provider")
