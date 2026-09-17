"""config/config.example.yaml works as written, for every provider.

The example is the first file a new user edits, and it had drifted: it said
"supported: anthropic, bedrock, vertex" while the factory also built
openai-compat, litellm and cascade, and it called `api_key_env` anthropic-only
when two other providers read it. Nothing failed, because nothing read the
example. A comment is the wrong form for a claim about what the code accepts,
so these tests read it.

The active `llm:` block and every commented `# llm:` block under "Other
providers" are parsed and built through `get_provider`, the path
`policyforge` takes, with no network. A provider whose optional extra is not
installed is skipped by name rather than silently passing. Two boundary claims
the comments make are checked too, because a wrong classification in an
example is how someone sends content somewhere they believed was local.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

EXAMPLE = Path(__file__).resolve().parent.parent / "config" / "config.example.yaml"

#: The package each provider's constructor needs beyond the base install.
#: Only these may skip; any other failure to build is a real one.
EXTRA_MODULE = {
    "bedrock": "boto3",
    "vertex": "google.auth",
    "litellm": "litellm",
}


def _commented_blocks(text: str) -> list[dict]:
    """Every `# llm:` block, uncommented and parsed.

    A block is a `# llm:` line followed by the indented `#   ...` lines under
    it. It ends at the first line that is not one of those, normally a blank
    line.
    """
    lines = text.splitlines()
    blocks: list[dict] = []
    index = 0
    while index < len(lines):
        if lines[index].rstrip() != "# llm:":
            index += 1
            continue
        body = ["llm:"]
        index += 1
        while index < len(lines) and lines[index].startswith("#   "):
            body.append(lines[index][2:])
            index += 1
        blocks.append(yaml.safe_load("\n".join(body)))
    return blocks


def _examples() -> list[tuple[str, dict]]:
    text = EXAMPLE.read_text(encoding="utf-8")
    active = {"llm": yaml.safe_load(text)["llm"]}
    found = [active, *_commented_blocks(text)]
    return [(config["llm"]["provider"], config) for config in found]


def _key_envs(block: dict) -> list[str]:
    """Every `api_key_env` a block names, including inside a cascade's halves."""
    names = [block["api_key_env"]] if block.get("api_key_env") else []
    for half in ("primary", "escalate_to"):
        if isinstance(block.get(half), dict):
            names += _key_envs(block[half])
    return names


def _providers_needing_extras(block: dict) -> list[str]:
    needed = [block["provider"]] if block["provider"] in EXTRA_MODULE else []
    for half in ("primary", "escalate_to"):
        if isinstance(block.get(half), dict):
            needed += _providers_needing_extras(block[half])
    return needed


def _supported_by_the_factory() -> set[str]:
    """The provider names `_build_provider` accepts, read from the factory itself.

    Its unknown-provider error lists them. Reading that rather than a list
    kept here means a provider added to the factory without an example fails
    this test, instead of the example drifting again.
    """
    from policyforge.llm.base import get_provider

    with pytest.raises(ValueError) as raised:
        get_provider({"llm": {"provider": "not-a-provider", "model": "x"}})
    supported = str(raised.value).split("Supported:", 1)[1]
    names = set(re.findall(r"[a-z][a-z-]*", supported)) - {"alias"}
    return names


def test_the_example_covers_every_provider_the_factory_builds():
    covered = {name for name, _ in _examples()}
    # `local` is the factory's alias for openai-compat, so an example of either
    # covers both.
    if "local" in covered:
        covered.add("openai-compat")
    if "openai-compat" in covered:
        covered.add("local")

    assert covered == _supported_by_the_factory()


@pytest.mark.parametrize("provider,config", _examples(), ids=[name for name, _ in _examples()])
def test_every_example_block_builds_as_written(provider, config, monkeypatch):
    from policyforge.llm.base import get_provider

    for module in (EXTRA_MODULE[name] for name in _providers_needing_extras(config["llm"])):
        pytest.importorskip(module, reason=f"{provider} example needs the extra providing {module}")

    for name in _key_envs(config["llm"]):
        monkeypatch.setenv(name, "test-key-not-real")

    provider_object = get_provider(config)

    assert provider_object is not None


def test_the_local_example_is_classified_local_and_the_cascade_third_party():
    """The comments say both. A wrong classification here is the dangerous
    direction: content sent somewhere its owner believed was on the machine."""
    from policyforge.llm.boundary import LOCAL, THIRD_PARTY, classify_provider

    by_provider = dict(_examples())

    assert classify_provider(by_provider["local"]["llm"]).klass == LOCAL
    assert classify_provider(by_provider["cascade"]["llm"]).klass == THIRD_PARTY
