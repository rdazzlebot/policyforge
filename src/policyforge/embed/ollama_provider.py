"""Embeds text with a model served by Ollama's `/api/embed`.

Chosen because it needs nothing new. A machine already running Ollama for
generation can serve `bge-m3` alongside it — no second process, unlike the
reranker, and no PyTorch. `ollama pull bge-m3` is the whole installation.

The endpoint returns 501 rather than 404 when the named model cannot
embed, which is easy to misread as "Ollama does not do embeddings". It
does; `llama3.2` just is not an embedding model. `check()` below turns that
into a sentence that says so.
"""

from __future__ import annotations

from .base import Embedder


class OllamaEmbedder(Embedder):
    """Calls `POST {base_url}/api/embed` on a local Ollama."""

    def __init__(
        self,
        *,
        model: str = "bge-m3",
        base_url: str = "http://localhost:11434",
        timeout: int = 300,
        session=None,
    ):
        self.model = model
        # Tolerate a trailing slash rather than producing a doubled one.
        self.base_url = base_url.rstrip("/")
        # Generous: embedding a whole corpus is one call per batch and the
        # first one pays for loading the model into VRAM.
        self.timeout = timeout

        if session is not None:
            # Dependency injection point for tests, matching the LLM and
            # rerank providers, so this is exercisable with nothing running.
            self._session = session
            return
        import requests

        self._session = requests.Session()

    def embed(self, texts: list[str]) -> list[list[float]]:
        import requests

        if not texts:
            return []

        url = f"{self.base_url}/api/embed"
        try:
            response = self._session.post(
                url, json={"model": self.model, "input": texts}, timeout=self.timeout
            )
        except requests.exceptions.RequestException as exc:
            # "connection" is load-bearing, as in the other providers:
            # evals/runner.py grades a message containing it as
            # infrastructure rather than as a bad result.
            raise RuntimeError(
                f"Connection to {url} failed: {exc}. Is Ollama running? Check with `ollama ps`."
            ) from exc

        if response.status_code == 501:
            raise RuntimeError(
                f"{url} says '{self.model}' cannot produce embeddings. Ollama does "
                f"serve them, but only from an embedding model — try "
                f"`ollama pull bge-m3` and set embed.model to it."
            )
        if response.status_code != 200:
            raise RuntimeError(f"{url} returned HTTP {response.status_code}: {response.text[:300]}")

        vectors = (response.json() or {}).get("embeddings") or []
        # Counted rather than trusted. A short reply would otherwise pair
        # each vector with the wrong chunk from that point on, and every
        # similarity after it would be confidently wrong about which
        # passage it described.
        if len(vectors) != len(texts):
            raise RuntimeError(f"{url} returned {len(vectors)} vector(s) for {len(texts)} input(s)")
        return vectors

    def check(self) -> bool:
        """Whether this model can embed right now."""
        vectors = self.embed(["access review cadence"])
        return len(vectors) == 1 and len(vectors[0]) > 0
