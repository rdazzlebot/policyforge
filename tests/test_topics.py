"""topics/ tests — registry parsing/validation and coverage analysis.

Unit tests build small synthetic control sets so each ownership rule can be
asserted in isolation. The final section runs the *shipped*
config/topics.example.yaml against the real 800-53 catalog, because a starter
registry that leaves controls unowned — or lets two topics claim the same one
— would ship the exact failure this tool exists to detect.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

EXAMPLE_REGISTRY = Path(__file__).parent.parent / "config" / "topics.example.yaml"
NIST_DATA = (
    Path(__file__).parent.parent / "data" / "frameworks" / "nist-800-53-r5" / "controls.json"
)
HIPAA_DATA = (
    Path(__file__).parent.parent / "data" / "frameworks" / "hipaa-security-rule" / "controls.json"
)


def _control(control_id, *enhancement_ids, framework="NIST 800-53", baseline="Low"):
    from policyforge.ingest.schema import Control, ControlEnhancement

    return Control(
        control_id=control_id,
        title=control_id,
        framework=framework,
        framework_version="Rev 5",
        baseline=baseline,
        enhancements=[
            ControlEnhancement(enhancement_id=e, title=e, baseline=baseline, description="")
            for e in enhancement_ids
        ],
    )


def _topic(name, owner, controls):
    from policyforge.topics.registry import Topic

    return Topic(name=name, owner=owner, nist_controls=controls)


# --------------------------------------------------------------------------
# Registry parsing and validation
# --------------------------------------------------------------------------


def test_parses_the_shipped_example_registry():
    from policyforge.topics.registry import parse_topics

    topics = parse_topics(yaml.safe_load(EXAMPLE_REGISTRY.read_text(encoding="utf-8")))
    assert topics
    # README documents ~25 as the practical ceiling.
    assert len(topics) <= 25
    assert all(t.owner for t in topics), "every topic needs an accountable owner"
    assert all(t.nist_controls for t in topics)


def test_every_topic_must_declare_an_owner():
    from policyforge.topics.registry import TopicRegistryError, parse_topics

    with pytest.raises(TopicRegistryError, match="missing `owner`"):
        parse_topics({"topics": [{"name": "Orphan process", "nist_controls": ["AC-2"]}]})


def test_duplicate_topic_names_are_rejected():
    from policyforge.topics.registry import TopicRegistryError, parse_topics

    with pytest.raises(TopicRegistryError, match="Duplicate topic name"):
        parse_topics(
            {
                "topics": [
                    {"name": "Access Review", "owner": "IAM"},
                    {"name": "access review", "owner": "SecOps"},
                ]
            }
        )


def test_unknown_keys_are_rejected_rather_than_silently_ignored():
    """A typo'd key would otherwise drop real data — `nist_control` instead of
    `nist_controls` would silently produce a topic that claims nothing."""
    from policyforge.topics.registry import TopicRegistryError, parse_topics

    with pytest.raises(TopicRegistryError, match="unknown key"):
        parse_topics({"topics": [{"name": "T", "owner": "O", "nist_control": ["AC-2"]}]})


def test_registry_must_have_a_topics_list():
    from policyforge.topics.registry import TopicRegistryError, parse_topics

    with pytest.raises(TopicRegistryError, match="top-level `topics:` list"):
        parse_topics({"not_topics": []})
    with pytest.raises(TopicRegistryError, match="non-empty list"):
        parse_topics({"topics": []})


def test_missing_registry_file_says_how_to_create_one(tmp_path):
    from policyforge.topics.registry import load_topics

    with pytest.raises(FileNotFoundError, match=r"topics\.example\.yaml"):
        load_topics(tmp_path / "nope.yaml")


# --------------------------------------------------------------------------
# Coverage: orphaned, contested, and claim resolution
# --------------------------------------------------------------------------


def test_control_claimed_by_no_topic_is_orphaned():
    from policyforge.topics.coverage import analyze_coverage

    controls = [_control("AC-2"), _control("AU-6")]
    report = analyze_coverage([_topic("Access", "IAM", ["AC-2"])], controls)

    assert report.covered == {"AC-2": "Access"}
    assert report.orphaned == ["AU-6"]
    assert not report.is_clean


def test_control_claimed_by_two_topics_is_contested():
    """The worse failure of the two: it looks covered while each owner
    assumes the other has it."""
    from policyforge.topics.coverage import analyze_coverage

    report = analyze_coverage(
        [_topic("Access", "IAM", ["AC-2"]), _topic("Joiners", "HR", ["AC-2"])],
        [_control("AC-2")],
    )

    assert report.contested == {"AC-2": ["Access", "Joiners"]}
    assert report.covered == {}
    assert not report.is_clean


def test_anchoring_a_control_also_claims_its_enhancements():
    """So a topic needn't enumerate AC-2(1)..AC-2(13) to own AC-2."""
    from policyforge.topics.coverage import analyze_coverage

    report = analyze_coverage(
        [_topic("Access", "IAM", ["AC-2"])],
        [_control("AC-2", "AC-2(1)", "AC-2(2)")],
    )

    assert report.orphaned == []
    assert report.covered == {"AC-2": "Access", "AC-2(1)": "Access", "AC-2(2)": "Access"}


def test_a_direct_enhancement_claim_beats_an_inherited_one():
    """AC-2(1) can sit with a different team than AC-2 without either being
    reported as contested — the more specific claim wins."""
    from policyforge.topics.coverage import analyze_coverage

    report = analyze_coverage(
        [
            _topic("Access", "IAM", ["AC-2"]),
            _topic("Automation", "Platform", ["AC-2(1)"]),
        ],
        [_control("AC-2", "AC-2(1)", "AC-2(2)")],
    )

    assert report.contested == {}
    assert report.covered["AC-2"] == "Access"
    assert report.covered["AC-2(1)"] == "Automation"
    assert report.covered["AC-2(2)"] == "Access"  # still inherited
    assert report.is_clean


def test_owner_rollup_counts_requirements_not_topics():
    from policyforge.topics.coverage import analyze_coverage

    report = analyze_coverage(
        [_topic("Access", "IAM", ["AC-2"]), _topic("Auth", "IAM", ["IA-5"])],
        [_control("AC-2", "AC-2(1)"), _control("IA-5")],
    )

    assert report.by_owner == {"IAM": 3}
    assert report.by_topic == {"Access": 2, "Auth": 1}


# --------------------------------------------------------------------------
# Coverage: anchors that don't resolve
# --------------------------------------------------------------------------


def test_a_typod_anchor_is_reported_as_unknown():
    from policyforge.topics.coverage import analyze_coverage

    report = analyze_coverage([_topic("Access", "IAM", ["AC-9999"])], [_control("AC-2")])

    assert report.unknown_anchors == {"Access": ["AC-9999"]}
    assert not report.is_clean


def test_an_out_of_scope_anchor_is_not_treated_as_a_typo():
    """A real control that simply isn't in the baseline being analyzed — the
    PM and PT families sit in no baseline at all. Reporting those as bad IDs
    made the report cry wolf about nine valid anchors."""
    from policyforge.topics.coverage import analyze_coverage

    catalog = [_control("AC-2"), _control("PM-1", baseline="")]
    in_scope = [_control("AC-2")]

    report = analyze_coverage(
        [_topic("Access", "IAM", ["AC-2", "PM-1"])],
        in_scope,
        catalog=catalog,
        scope="Low baseline",
    )

    assert report.unknown_anchors == {}
    assert report.out_of_scope_anchors == {"Access": ["PM-1"]}
    # Out-of-scope anchors are informational, not a failure.
    assert report.is_clean


def test_without_a_catalog_every_anchor_is_judged_against_the_scope():
    """Back-compat: `catalog` is optional, and omitting it means scope is all
    the parser has to go on."""
    from policyforge.topics.coverage import analyze_coverage

    report = analyze_coverage([_topic("Access", "IAM", ["AC-2", "PM-1"])], [_control("AC-2")])
    assert report.unknown_anchors == {"Access": ["PM-1"]}


# --------------------------------------------------------------------------
# Cross-framework reachability
# --------------------------------------------------------------------------


def test_owned_nist_controls_pull_other_frameworks_in_via_the_crosswalk():
    from policyforge.mapping.crosswalk import build_crosswalk
    from policyforge.topics.coverage import analyze_coverage

    nist = [_control("AC-2"), _control("AU-6")]
    hipaa = _control("164.308(a)(3)(i)", framework="HIPAA Security Rule", baseline="")
    hipaa.source_crosswalk = {"nist": "AC-2"}
    unmapped = _control("164.318(a)", framework="HIPAA Security Rule", baseline="")

    report = analyze_coverage(
        [_topic("Access", "IAM", ["AC-2"])],
        nist,
        other_controls=[hipaa, unmapped],
        crosswalk=build_crosswalk(nist + [hipaa, unmapped]),
    )

    (hipaa_coverage,) = report.framework_coverage
    assert hipaa_coverage.framework == "hipaa"
    assert hipaa_coverage.covered == ["164.308(a)(3)(i)"]
    assert hipaa_coverage.uncovered == ["164.318(a)"]


# --------------------------------------------------------------------------
# The shipped starter registry, against the real catalog
# --------------------------------------------------------------------------


def _real():
    from policyforge.ingest.schema import load_controls
    from policyforge.topics.registry import parse_topics

    topics = parse_topics(yaml.safe_load(EXAMPLE_REGISTRY.read_text(encoding="utf-8")))
    return topics, load_controls(NIST_DATA)


def test_example_registry_anchors_are_all_real_controls():
    topics, catalog = _real()
    known = {c.control_id for c in catalog} | {
        e.enhancement_id for c in catalog for e in c.enhancements
    }
    for topic in topics:
        unknown = [a for a in topic.nist_controls if a not in known]
        assert not unknown, f"{topic.name} anchors non-existent control(s): {unknown}"


def test_no_two_example_topics_anchor_the_same_control():
    topics, _ = _real()
    seen: dict[str, str] = {}
    for topic in topics:
        for anchor in topic.nist_controls:
            assert anchor not in seen, f"{anchor} anchored by both {seen[anchor]} and {topic.name}"
            seen[anchor] = topic.name


@pytest.mark.parametrize("baseline", ["Low", "Moderate", "High"])
def test_example_registry_fully_owns_every_baseline(baseline):
    """The starter registry should ship clean: every control in every
    baseline owned by exactly one topic. Shipping orphans would demonstrate
    the failure this tool exists to detect."""
    from policyforge.ssp.workbook import select_for_baseline
    from policyforge.topics.coverage import analyze_coverage

    topics, catalog = _real()
    report = analyze_coverage(
        topics,
        select_for_baseline(catalog, baseline),
        catalog=catalog,
        scope=f"{baseline} baseline",
    )

    assert report.orphaned == []
    assert report.contested == {}
    assert report.unknown_anchors == {}
    assert report.is_clean


def test_example_registry_reaches_every_crosswalked_hipaa_requirement():
    """65 of the 75 HIPAA requirements map to a NIST control; all 65 should be
    reachable from an owned topic."""
    from policyforge.ingest.schema import load_controls
    from policyforge.mapping.crosswalk import build_crosswalk
    from policyforge.ssp.workbook import select_for_baseline
    from policyforge.topics.coverage import analyze_coverage

    topics, catalog = _real()
    hipaa = load_controls(HIPAA_DATA)
    report = analyze_coverage(
        topics,
        select_for_baseline(catalog, "Moderate"),
        catalog=catalog,
        other_controls=hipaa,
        crosswalk=build_crosswalk(catalog + hipaa),
    )

    (hipaa_coverage,) = report.framework_coverage
    assert len(hipaa_coverage.covered) == 65
    assert hipaa_coverage.total == 75
