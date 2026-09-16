"""The registry, and the specific failure it was built for.

A measured run against `kimi-k3` was half finished when two commits changed
the edit planner and the clusterer. The run had imported the old modules at
process start, so it measured code that no longer existed, and nothing in
the run or its report could have said so — it was caught by a person
comparing file mtimes against a log's birth time. These tests pin the
mechanism that makes noticing unnecessary.
"""

from __future__ import annotations

import pytest

from policyforge.llm import prompts
from policyforge.llm.prompts import Prompt


def test_the_fingerprint_follows_the_text():
    a = Prompt(name="x", version=1, text="Do the thing.")
    b = Prompt(name="x", version=1, text="Do the other thing.")
    assert a.fingerprint != b.fingerprint


def test_the_fingerprint_ignores_the_declared_version():
    """The hash answers "is this the same prompt", nothing else.

    Version is a human claim about a change; the hash is the change. Tying
    the hash to the version would make a forgotten bump invisible, which is
    the failure mode this exists for.
    """
    a = Prompt(name="x", version=1, text="Same words.")
    b = Prompt(name="x", version=9, text="Same words.")
    assert a.fingerprint == b.fingerprint


def test_whitespace_is_not_normalised():
    """A trailing space is a different prompt to the API, so it is here too."""
    a = Prompt(name="x", version=1, text="Do the thing.")
    b = Prompt(name="x", version=1, text="Do the thing. ")
    assert a.fingerprint != b.fingerprint


def test_register_hands_back_the_text_unchanged():
    """Call sites keep receiving the `str` they always did."""
    text = "Some instructions."
    returned = prompts.register(Prompt(name="test.roundtrip", version=1, text=text))
    assert returned == text
    assert isinstance(returned, str)
    del prompts.REGISTRY["test.roundtrip"]


def test_two_different_prompts_cannot_share_a_name():
    """A duplicate name makes both fingerprints unreadable across runs."""
    prompts.register(Prompt(name="test.dup", version=1, text="One."))
    with pytest.raises(ValueError, match="both registered"):
        prompts.register(Prompt(name="test.dup", version=1, text="Two."))
    del prompts.REGISTRY["test.dup"]


def test_registering_the_same_prompt_twice_is_fine():
    """Modules get imported more than once; that is not a conflict."""
    prompt = Prompt(name="test.same", version=1, text="One.")
    prompts.register(prompt)
    prompts.register(prompt)
    del prompts.REGISTRY["test.same"]


# ---- the comparison that would have caught the straddled run -----------


def test_an_unchanged_prompt_set_is_comparable():
    prompts.load_all()
    assert prompts.compare(prompts.fingerprints()) == []


def test_a_changed_prompt_is_named_with_both_fingerprints():
    prompts.load_all()
    recorded = dict(prompts.fingerprints())
    recorded["zardoz.answer"] = "0" * 12
    (difference,) = prompts.compare(recorded)
    assert difference.startswith("zardoz.answer: 000000000000 -> ")


def test_a_split_prompt_reads_as_one_gone_and_two_new():
    """The actual A-06 change: one cluster prompt became two.

    This is what the recorded pre-A-06 baseline compares against, so it is
    worth pinning that it reads legibly rather than as three unrelated
    lines.
    """
    prompts.load_all()
    recorded = {
        "zardoz.answer": prompts.fingerprints()["zardoz.answer"],
        "zardoz.cluster": "3f58d07e4945",
    }
    differences = prompts.compare(recorded)
    assert any(d.startswith("zardoz.cluster.json: new") for d in differences)
    assert any(d.startswith("zardoz.cluster.lines: new") for d in differences)
    assert any(d.startswith("zardoz.cluster: gone") for d in differences)


def test_load_all_registers_every_prompt_it_claims_to():
    prompts.load_all()
    names = set(prompts.fingerprints())
    assert {
        "zardoz.answer",
        "edit.plan",
        "entail.judge",
        "zardoz.cluster.lines",
        "zardoz.cluster.json",
    } <= names


# ---- the prompts themselves --------------------------------------------


def test_registration_did_not_alter_a_prompt():
    """Registering wraps a constant; it must not touch what it wraps.

    A registry that silently changed a prompt while claiming to fingerprint
    it would be worse than no registry, so the two prompts whose text is
    load-bearing are checked against a known opening and closing.
    """
    from policyforge.zardoz.answer import SYSTEM_PROMPT

    assert isinstance(SYSTEM_PROMPT, str)
    assert SYSTEM_PROMPT.startswith("You answer questions about an organization's own")
    assert SYSTEM_PROMPT.rstrip().endswith("Name no candidate values at all.")


def test_the_two_cluster_prompts_have_different_fingerprints():
    """They differ in one paragraph, which is exactly what must be visible."""
    prompts.load_all()
    current = prompts.fingerprints()
    assert current["zardoz.cluster.lines"] != current["zardoz.cluster.json"]
