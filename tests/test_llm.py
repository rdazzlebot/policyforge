"""LLM provider layer tests: the Bedrock Converse API request/response
shape (via an injected fake client, so no boto3 install or live AWS
credentials are required), and the provider factory's dispatch."""

from __future__ import annotations


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
