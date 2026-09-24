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


def _coverage_counts(state) -> dict[str, int]:
    """Requirements per owner, as /coverage attributes them -- a second
    instrument, built through `split_by_adoption` rather than the skills'
    split, so the two can disagree."""
    from policyforge.mapping.crosswalk import build_crosswalk
    from policyforge.topics.coverage import analyze_coverage, scope_label, split_by_adoption

    controls = skills._controls(state)
    nist, _unadopted, other = split_by_adoption(state.topics, controls)
    report = analyze_coverage(
        state.topics,
        nist,
        scope=scope_label(nist, None),
        other_controls=other,
        crosswalk=build_crosswalk(controls),
    )
    owner_of = {t.name: t.owner for t in state.topics}
    counts: dict[str, int] = {}
    for topic in report.covered.values():
        counts[owner_of[topic]] = counts.get(owner_of[topic], 0) + 1
    return counts


def test_every_800_53_teams_bundle_agrees_with_coverage(state):
    """**The twin, derived rather than pinned** (1d on #317). Pinning only
    "not zero" let the opposite mutation through: with every catalog treated
    as anchorable, Security Program / GRC went from 50 to 87, counting
    800-171 and FedRAMP ids as its own. Every owner whose topics anchor only
    800-53 must answer for exactly what /coverage attributes to it.

    AI owners are left out on purpose: /coverage credits their subcategories
    to the anchored category and /bundle does not yet -- that disagreement
    is #318, whose agreement test covers every owner.
    """
    import re

    ai = re.compile(r"^(Govern|Map|Measure|Manage)\s+\d")
    counts = _coverage_counts(state)
    owners = sorted(
        {t.owner for t in state.topics}
        - {t.owner for t in state.topics if any(ai.match(a) for a in t.nist_controls)}
    )
    assert len(owners) >= 15, "the population: every 800-53 owner in the shipped registry"

    for owner in owners:
        header = skills._bundle(state, owner.split()).splitlines()[0]
        assert f"answers for {counts[owner]} requirement(s)." in header, (owner, header)


def test_addresses_finds_the_topic_anchoring_an_ai_rmf_category(state):
    out = skills._addresses(state, ["Govern", "1"])

    assert "AI Governance & Accountability" in out
    assert "Nothing in the registry answers" not in out


def test_addresses_still_finds_an_800_53_anchor(state):
    out = skills._addresses(state, ["AC-2"])

    assert "Nothing in the registry answers" not in out
    assert "not in any loaded catalog" not in out
