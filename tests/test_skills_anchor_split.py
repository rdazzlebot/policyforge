"""`/bundle` and `/addresses` see an AI RMF anchor as anchorable (#312).

Both skills split the loaded catalogs into the half a topic can anchor and
the half reachable only through the crosswalk. ba found the split unguarded:
dropping the AI RMF from it (`... and "rmf" not in framework`) changed the
helper's answer and left the whole suite green, while the CLI's `/coverage`
split was guarded. These run the skills themselves, against the shipped
registry and catalogs, so the split is held where a user meets it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from policyforge.topics.registry import load_topics
from policyforge.zardoz import skills

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def state(monkeypatch):
    monkeypatch.chdir(ROOT)
    return SimpleNamespace(
        topics=load_topics(ROOT / "config" / "topics.example.yaml"),
        controls_paths=[],
        config={},
        content_dir=None,
    )


def _owner_of(state, prefix: str) -> str:
    return next(t.owner for t in state.topics if t.name.startswith(prefix))


def test_bundle_counts_an_ai_rmf_anchor_as_the_teams(state):
    """The AI team owns its AI RMF anchors. With the AI RMF dropped from the
    anchorable half, the team would answer for nothing."""
    owner = _owner_of(state, "AI Governance")

    out = skills._bundle(state, owner.split())

    assert f"{owner} owns 1 topic(s) and answers for 5 requirement(s)." in out


def test_bundle_still_counts_an_800_53_teams_anchors(state):
    """The twin: an 800-53 team's bundle is unchanged by the AI half."""
    owner = _owner_of(state, "Security Program Governance")

    out = skills._bundle(state, owner.split())

    assert f"{owner} owns" in out
    assert "answers for 0 requirement(s)" not in out


def test_addresses_finds_the_topic_anchoring_an_ai_rmf_category(state):
    out = skills._addresses(state, ["Govern", "1"])

    assert "AI Governance & Accountability" in out
    assert "Nothing in the registry answers" not in out


def test_addresses_still_finds_an_800_53_anchor(state):
    out = skills._addresses(state, ["AC-2"])

    assert "Nothing in the registry answers" not in out
    assert "not in any loaded catalog" not in out
