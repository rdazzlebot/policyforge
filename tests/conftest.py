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

**Stripping the environment is not sufficient on its own, and that was
measured rather than assumed.** LiteLLM calls `load_dotenv()` at import, so
it reads this repository's `.env` off disk and writes the keys into
`os.environ` — which happens *after* the fixture below has run, and happens
even when the variable was never in the environment to begin with. Observed
directly: with `OPENROUTER_API_KEY` absent from the environment, `import
litellm` created it, populated from `.env`. Any test importing litellm after
that point would hold a live, billable key.

So the load is disabled before anything can import litellm, and the fixture
strips what is already there. Two mechanisms, because they fail differently:
one covers a key in the developer's shell, the other covers a key on disk.
"""

from __future__ import annotations

import importlib.util
import ipaddress
import socket
from pathlib import Path

import pytest

try:
    import dotenv
except ImportError:  # nothing installed can load .env, so nothing to disarm
    dotenv = None

#: Disarm dotenv before any test, fixture or module import can pull a
#: credential off disk.
#:
#: Done at conftest import — the earliest point pytest gives us, and before
#: litellm can be imported by anything — because `load_dotenv()` runs at
#: *its* import and a fixture would be far too late. Patching a third-party
#: module is heavy-handed, and it is the only thing that actually works here:
#: the alternative is a suite whose hermeticity depends on which test
#: imported litellm first.
#:
#: Scoped to the test session by being in conftest. Nothing in `src/` is
#: affected, and a real run loads `.env` exactly as before.
#:
#: dotenv is not a dependency of this project. It arrives with litellm (and,
#: before mcp 2.0, with mcp), so without it there is no loader to disarm.
if dotenv is not None:
    dotenv.load_dotenv = lambda *args, **kwargs: False
    if hasattr(dotenv, "main"):
        dotenv.main.load_dotenv = lambda *args, **kwargs: False

#: Every environment variable that could let a provider reach the network.
#:
#: The second group is the one the suite was missing. LiteLLM reaches most
#: vendors behind one model string and resolves each one's key from that
#: vendor's own environment convention, so the project's rule — that a key
#: is only ever reached through a variable config names — does not constrain
#: it. `openrouter/…` is the model string this project's own measurements
#: are run with, and `OPENROUTER_API_KEY` was not on this list.
_CREDENTIALS = (
    "ANTHROPIC_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "CONFLUENCE_API_TOKEN",
    "CONFLUENCE_USERNAME",
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
    "GROQ_API_KEY",
    "DEEPSEEK_API_KEY",
    "TOGETHERAI_API_KEY",
    "HUGGINGFACE_API_KEY",
    "XAI_API_KEY",
)


def pytest_configure(config):
    """Stop before collection when `policyforge` is not this tree's.

    The editable install pins the checkout it was made from, so a bare
    `pytest` in a git worktree imports the main checkout's source and
    reports all-pass on a branch it never loaded. `scripts/check.py` refuses
    the same way; pytest gets its own hook because it is what people run
    between full gates. Same code, one place: scripts/tree_guard.py.
    """
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("tree_guard", root / "scripts" / "tree_guard.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    refusal = guard.foreign_source(guard.resolved_origin(), root, invocation="pytest")
    if refusal:
        pytest.exit(refusal, returncode=2)


@pytest.fixture(autouse=True)
def no_live_credentials(monkeypatch):
    """Strip provider credentials so no test can reach a real MODEL provider.

    Not every service needs a credential: eCFR does not, and a test that
    stubbed only half its fetch reached it live (#432). `no_network` below
    is what stops that; this stops a keyed provider.

    Autouse and unconditional. A test that wants a model injects a fake;
    there is no legitimate reason for the suite to hold a live key, and
    "only this one test calls out" is how a suite becomes slow and flaky.
    """
    for name in _CREDENTIALS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def ledger_writes_nowhere_real(monkeypatch, tmp_path):
    """Point the model-call ledger at a throwaway file.

    Same reasoning as the credentials above, in the other direction. The
    ledger defaults to `output/.model-log/calls.jsonl` relative to the
    working directory, and `get_provider` wraps every provider in it — so
    without this, running the suite would append several hundred fake
    entries to whatever real audit record the developer happens to have.
    A record somebody may one day rely on is the last file a test run
    should be writing to by accident.

    Tests that care what was recorded pass their own path explicitly.
    """
    from policyforge.llm import ledger

    monkeypatch.setattr(ledger, "DEFAULT_LEDGER_PATH", tmp_path / "calls.jsonl")


#: Hosts a test may connect to: the machine itself. Tests name
#: `localhost:11434` for a local model with the transport stubbed; loopback
#: is allowed so a stub that misses fails on its own terms, not on this.
_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain", ""})


def _is_loopback(host) -> bool:
    if not isinstance(host, str):
        return True  # a unix socket or an already-resolved local form
    name = host.strip("[]").lower()
    if name in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(name.split("%")[0]).is_loopback
    except ValueError:
        return False


class NetworkUsedInTest(RuntimeError):
    """A test reached past this machine. Not an `OSError`, so no HTTP client
    reads it as a connection failure to retry or to report as the server's."""


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Refuse every DNS lookup and connection beyond loopback (#432).

    `test_etl_hipaa_fetches_and_parses` stubbed the XML fetch and not the
    date lookup before it, so it called eCFR live; one CI run at a commit
    failed on eCFR's 403 while another at the same commit passed. A red
    that is about a third party's rate limiter teaches a reader to re-run,
    and re-running is what hides a real red. Refused at the socket, before
    any client library, so a new unstubbed call is found by the test that
    makes it, with the host named, whatever library it goes through.
    """
    real_getaddrinfo = socket.getaddrinfo
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def refuse(host):
        raise NetworkUsedInTest(
            f"this test reached the network ({host!r}); stub the call instead (#432)"
        )

    def getaddrinfo(host, *args, **kwargs):
        if not _is_loopback(host):
            refuse(host)
        return real_getaddrinfo(host, *args, **kwargs)

    def connect(self, address):
        if isinstance(address, tuple) and not _is_loopback(address[0]):
            refuse(address[0])
        return real_connect(self, address)

    def connect_ex(self, address):
        if isinstance(address, tuple) and not _is_loopback(address[0]):
            refuse(address[0])
        return real_connect_ex(self, address)

    # boto3 with no credentials asks the cloud instance-metadata service at
    # 169.254.169.254 for some. On a CI runner, a cloud VM, that address
    # answers: three Bedrock construction tests were talking to the runner's
    # metadata service (found by this guard, #432). botocore's own switch.
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
