"""Calls a model behind an OpenAI-compatible `/v1/chat/completions`
endpoint — a local runtime (Ollama, LM Studio, llama.cpp's server, vLLM)
or a hosted one (Vertex AI's Model-as-a-Service open models, and most
third-party inference vendors). They all speak the same request/response
shape, so one provider covers the lot; only `base_url` changes.

Deliberately built on `requests`, which this project already depends on,
rather than the `openai` SDK. The surface used here is one POST and three
fields of the reply, and an extra dependency (plus an extra install extra
to document) buys nothing for that.

Auth is optional, unlike every other provider here: a local server on
localhost normally has none, so `api_key_env` is only consulted if
config.yaml names it. That is the one place this differs from
AnthropicProvider, where a missing key is always an error.

Running locally is not only about token cost. This project keeps licensed
BYOC exports (HITRUST, GovRAMP) out of git precisely because redistributing
them is a licence question, and sending one to a third-party API processor
is the same question wearing a different hat — see the README's licensing
section and `generate-parser`'s warning. A model on localhost removes that
question rather than answering it.
"""

from __future__ import annotations

import os

from ._inline_thinking import answer_of, exhausted, needs_more_room, retry_budget
from .base import LLMProvider, LLMResponse, ProviderRejected


class OpenAICompatProvider(LLMProvider):
    """Calls any OpenAI-compatible chat-completions endpoint.

    `base_url` is the server root (e.g. http://localhost:11434/v1); the
    provider appends /chat/completions. `api_key_env` is optional and only
    needed by endpoints that authenticate.
    """

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key_env: str | None = None,
        timeout: int = 600,
        session=None,
    ):
        self.model = model
        # Tolerate a trailing slash in config rather than producing a URL
        # with a doubled one, which some servers 404 on.
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        # Generous by default: a 14B on a consumer GPU can take minutes over
        # a long synthesis prompt, and the failure mode of a short timeout
        # is a run that dies most of the way through a document.
        self.timeout = timeout

        self._headers = {"Content-Type": "application/json"}
        if api_key_env:
            api_key = os.environ.get(api_key_env)
            if not api_key:
                raise RuntimeError(
                    f"Environment variable {api_key_env} is not set. "
                    f"Either export it, or drop llm.api_key_env from your config "
                    f"if this endpoint needs no key (a local server usually does not)."
                )
            self._headers["Authorization"] = f"Bearer {api_key}"

        if session is not None:
            # Dependency injection point for tests, matching BedrockProvider
            # and VertexProvider, so the request/response handling below is
            # exercisable without a server running.
            self._session = session
            return
        import requests

        self._session = requests.Session()

    def _post(self, payload: dict) -> dict:
        import requests

        url = f"{self.base_url}/chat/completions"
        try:
            response = self._session.post(
                url, json=payload, headers=self._headers, timeout=self.timeout
            )
        except requests.exceptions.RequestException as exc:
            # The word "connection" is load-bearing: evals/runner.py grades a
            # matching message as infrastructure rather than as a failed
            # case, so a server that is simply not running does not get
            # reported as the prompt getting the answer wrong.
            raise RuntimeError(
                f"Connection to {url} failed: {exc}. Is the server running? "
                f"For Ollama, `ollama serve`; check with `ollama ps`."
            ) from exc

        if 400 <= response.status_code < 500:
            # The server understood the request and refused it — a budget
            # above the model's cap, an unknown model. That is a rejection
            # the user has to act on, and `llm/effort.py` names the call
            # and the budget on it. A 5xx below is the server failing.
            raise ProviderRejected(
                response.text[:400] or f"{url} returned HTTP {response.status_code}",
                status=response.status_code,
                model=self.model,
            )
        if response.status_code != 200:
            raise RuntimeError(f"{url} returned HTTP {response.status_code}: {response.text[:400]}")
        return response.json()

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        data = self._post(payload)
        choice = (data.get("choices") or [{}])[0]
        text = answer_of((choice.get("message") or {}).get("content", ""))

        # A reasoning model spends `max_tokens` thinking before it writes
        # anything, so a tight budget can return a stop-on-length reply whose
        # every token was preamble. Returning "" for that is the dangerous
        # outcome, because it is indistinguishable from the model choosing to
        # say nothing — and callers read that as a decision. The identical
        # bug on the Anthropic path was measured at roughly one call in
        # eight on a 12-token budget; see `_anthropic_compat` for the full
        # account. Retry with room to speak.
        if needs_more_room(text, choice.get("finish_reason")):
            second = retry_budget(max_tokens)
            data = self._post({**payload, "max_tokens": second})
            choice = (data.get("choices") or [{}])[0]
            text = answer_of((choice.get("message") or {}).get("content", ""))
            if needs_more_room(text, choice.get("finish_reason")):
                raise exhausted(self.model, max_tokens, second)

        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            model=data.get("model") or self.model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            # `finish_reason` was read above only to retry an empty reply,
            # then dropped — so a non-empty reply Ollama or vLLM cut off at
            # `max_tokens` reached the caller with no stop reason, and
            # `LLMResponse.truncated` was False on exactly the local setup
            # the docs recommend for licensed content. It travels now, as it
            # does from every other provider.
            stop_reason=choice.get("finish_reason"),
        )

    def check(self) -> bool:
        """Cheap round-trip to confirm the endpoint + model actually work."""
        result = self.generate(
            system="Reply with exactly one word.",
            prompt="Reply with the word: ok",
            max_tokens=8,
            temperature=0,
        )
        return "ok" in result.text.lower()
