"""C-02 — credentials are read in known places, and never where prompts are built.

`docs/commitments.md` states that no credential ever reaches a model: not in
a system prompt, not in a user prompt, not in the ledger, not in version
history. The ledger half is enforced in `test_llm_ledger.py`, which asserts
it records a hash and never content. This is the prompt half.

The failure being prevented is mundane rather than exotic. Nobody sets out
to put an API key in a prompt. What happens is that a module which already
builds prompt text acquires a reason to read an environment variable — a
feature flag, a default host, an account id — and six months later somebody
interpolates the wrong one into an f-string that is three lines from a
prompt constant. The two capabilities being in the same file is what makes
that possible, so the invariant enforced here is that they are never in the
same file.

Two checks, in the order a reviewer would want them:

* **Every module that reads the environment is declared**, with what it
  reads and why. A new env read anywhere in `src/` fails until somebody
  writes it down, which is the review conversation that should happen.
* **No module that defines prompt text reads the environment at all**, and
  no prompt constant mentions a credential variable by name. This half is
  detected rather than declared: a new prompt module is covered the day it
  is written, without anybody remembering to add it here.

What this does not prove: that a credential cannot reach a model by some
path with more indirection than one module — a value read in a provider,
passed through three calls, and appended to a prompt by a caller that never
touched the environment. Nothing short of taint tracking proves that, and
CodeQL's `security-extended` suite is the thing in this repo that looks for
it. What this makes impossible is the version that actually happens.
"""

from __future__ import annotations

import ast
from pathlib import Path

import policyforge

SRC = Path(policyforge.__file__).resolve().parent

#: Every module in `src/` permitted to read the environment, and what for.
#: Only the first four read anything secret; the other two are here because
#: the check is "who reads the environment at all", which is the question
#: with a stable answer. A narrower check on credential-shaped names only
#: would pass a module that read `ANTHROPIC_KEY` under a different spelling.
DECLARED_ENV_READERS: dict[str, str] = {
    "llm/anthropic_provider.py": "the Anthropic API key, by the variable name config gives",
    "llm/litellm_provider.py": "same, for OpenRouter and other LiteLLM-routed providers",
    "llm/openai_compat_provider.py": "same, for an OpenAI-compatible endpoint",
    "export/_confluence_auth.py": "CONFLUENCE_API_TOKEN and CONFLUENCE_USERNAME",
    "export/_wiki_auth.py": (
        "the GitHub token, by the variable name config gives — passed to git through "
        "GIT_CONFIG_* so it never reaches argv or .git/config"
    ),
    "config.py": "POLICYFORGE_CONFIG, a path — lets a second config be run without editing one",
    "zardoz/budgets.py": "budget overrides, integers",
}

#: Credential variables this project reads. Named here so the prompt check
#: can assert no prompt text mentions one.
CREDENTIAL_ENV_NAMES = (
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "CONFLUENCE_API_TOKEN",
    "CONFLUENCE_USERNAME",
    "GITHUB_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
)


def _python_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _rel(path: Path) -> str:
    return path.relative_to(SRC).as_posix()


def _reads_environment(tree: ast.AST) -> bool:
    """True if this module reads an environment variable.

    Matches `os.environ`, `os.getenv` and `environ[...]` however they were
    imported, since `from os import environ` is the spelling that walks past
    a check written only for the attribute form.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
            return True
        if isinstance(node, ast.Name) and node.id in {"environ", "getenv"}:
            return True
    return False


def _prompt_constants(tree: ast.AST) -> list[tuple[str, str]]:
    """Module-level bindings that hold prompt text, as (name, text).

    Detected by name rather than declared, so a prompt added tomorrow is
    covered tomorrow. `_PROMPT`, `_RULES`, `_CONTRACT`, `_INSTRUCTION` and
    `_SYSTEM` are the markers this project actually uses for text that
    reaches a model.

    The text is gathered from every string constant *underneath* the
    assigned value rather than from a bare `ast.Constant`, because a prompt
    is not always assigned directly. `llm/prompts.py` introduced
    `SYSTEM_PROMPT = register("...")`, which is an `ast.Call`; implicit
    concatenation across lines and f-strings are the other two shapes in
    this tree. A check written for the bare form silently stopped covering
    the answering, planning and entailment prompts the day the registry
    landed — which is the failure this docstring exists to stop repeating.
    """
    markers = ("PROMPT", "RULES", "CONTRACT", "INSTRUCTION", "SYSTEM")
    found: list[tuple[str, str]] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if node.value is None:
            continue
        text = "\n".join(
            sub.value
            for sub in ast.walk(node.value)
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
        )
        if not text:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and any(m in target.id.upper() for m in markers):
                found.append((target.id, text))
    return found


def test_every_environment_reader_is_declared():
    """No module reads the environment without being written down."""
    undeclared = [
        _rel(path)
        for path in _python_files()
        if _reads_environment(ast.parse(path.read_text(encoding="utf-8")))
        and _rel(path) not in DECLARED_ENV_READERS
    ]
    assert not undeclared, (
        "Module(s) read the environment without being declared in "
        "DECLARED_ENV_READERS. Credentials are read in known places on "
        "purpose (docs/commitments.md, C-02) — add the module with what it "
        "reads and why, or read the value somewhere that already may:\n  "
        + "\n  ".join(sorted(undeclared))
    )


def test_declared_env_readers_all_exist():
    """The declaration does not outlive the code it describes."""
    missing = [name for name in DECLARED_ENV_READERS if not (SRC / name).exists()]
    assert not missing, f"DECLARED_ENV_READERS names module(s) that no longer exist: {missing}"


def test_no_prompt_building_module_reads_the_environment():
    """A module that defines prompt text never also reads a credential.

    This is the invariant that makes the commitment hold: the two
    capabilities are never in the same file, so the accident that puts a key
    in an f-string has nowhere to happen.
    """
    offenders: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prompts = _prompt_constants(tree)
        if prompts and _reads_environment(tree):
            names = ", ".join(name for name, _ in prompts)
            offenders.append(f"{_rel(path)} (defines {names})")

    assert not offenders, (
        "Module(s) both define prompt text and read the environment. Keep "
        "them apart: read the value in a provider and pass it as an "
        "argument, never alongside a prompt constant "
        "(docs/commitments.md, C-02):\n  " + "\n  ".join(sorted(offenders))
    )


def test_no_prompt_text_mentions_a_credential_variable():
    """No prompt constant names a credential environment variable.

    A prompt that says "set ANTHROPIC_API_KEY" is harmless; a prompt that
    interpolates one is not, and the two are one character apart. Refusing
    the name outright in prompt text costs nothing — error messages and
    docstrings, which are where that advice belongs, are not prompts.
    """
    offenders: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, text in _prompt_constants(tree):
            for credential in CREDENTIAL_ENV_NAMES:
                if credential in text:
                    offenders.append(f"{_rel(path)}:{name} mentions {credential}")

    assert not offenders, (
        "Prompt text names a credential variable (docs/commitments.md, "
        "C-02):\n  " + "\n  ".join(sorted(offenders))
    )
