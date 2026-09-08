"""Keep the test suite hermetic.

Every test in this project is meant to run offline, for free, and to give
the same answer every time. That held until the shell started building a
provider at launch: with `ANTHROPIC_API_KEY` set in a developer's
environment, CLI tests quietly began making real API calls — slow, billed,
and non-deterministic. One of them passed and failed on consecutive runs
depending on how a model routed a question.

So credentials are stripped for the whole suite. Tests that need a model
pass a fake one explicitly, which is what every one of them already does.

The side effect is the more valuable half: with no key present, the CLI
takes its own no-model path, so the suite now exercises the way most people
will actually run this. That path was crashing — `AnthropicProvider` raises
`RuntimeError` for a missing key and the shell only caught `ValueError` —
and nobody noticed, because everybody working on it had a key.
"""

from __future__ import annotations

import pytest

#: Every environment variable that could let a provider reach the network.
_CREDENTIALS = (
    "ANTHROPIC_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "CONFLUENCE_API_TOKEN",
    "CONFLUENCE_USERNAME",
)


@pytest.fixture(autouse=True)
def no_live_credentials(monkeypatch):
    """Strip provider credentials so no test can reach a real service.

    Autouse and unconditional. A test that wants a model injects a fake;
    there is no legitimate reason for the suite to hold a live key, and
    "only this one test calls out" is how a suite becomes slow and flaky.
    """
    for name in _CREDENTIALS:
        monkeypatch.delenv(name, raising=False)
