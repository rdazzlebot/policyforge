"""Two meanings of "anchor", kept apart on purpose.

    NIST_ANCHOR     the CROSSWALK anchor - what every other framework's
                    requirements are mapped ONTO. Singular.
    TOPIC_ANCHORS   which catalogs a TOPIC may claim identifiers from.
                    A set.

They were one constant until 2026-09-20. **The reason to split them is
that the obvious way to let topics anchor a second catalog — grep
`NIST_ANCHOR`, widen it — also widens the crosswalk-anchor sites**, and a
catalog that becomes a crosswalk target becomes one `crosswalk seed` will
generate a mapping for.

For the NIST AI RMF that mapping is refused on product grounds: it would
assert an 800-53 control *achieves* an AI RMF outcome, the claim NIST
declined to make when it split the Playbook out. So the natural refactor
publishes the thing the project decided not to publish, while looking
exactly like the change that was asked for.

These tests make that impossible rather than discouraged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from policyforge.mapping.crosswalk import (
    NIST_ANCHOR,
    TOPIC_ANCHORS,
    anchors_a_topic,
    build_crosswalk,
    normalize_framework,
)

ROOT = Path(__file__).resolve().parent.parent

#: **The assignment, enumerated so a reviewer diffs rather than re-derives.**
#: Every module that referenced the single constant was consciously placed
#: on one side. A file in the B list must not mention `NIST_ANCHOR` at all;
#: that is what `test_no_b_site_still_reads_the_crosswalk_anchor` holds.
B_SITE_FILES = (
    "cli/documents.py",
    "cli/programme.py",
    "zardoz/skills.py",
)

A_SITE_FILES = (
    "crosswalk/candidates.py",
    "crosswalk/overlay.py",
    "ingest/hipaa_crosswalk_loader.py",
    "mapping/crosswalk.py",
    "synthesis/merge.py",
    "topics/satisfies.py",
)

#: `mapping/crosswalk.py` is excluded from the "must not mention the topic
#: anchor" guard for one stated reason: **it is where both constants are
#: defined.** It necessarily names them.
#:
#: Written as a visible exclusion rather than by quietly dropping it from
#: the tuple, because a guard that states its own reach can be wrong out
#: loud. The residual it leaves: a genuine A-side *misuse* inside the
#: definition module would not be caught here. `_is_nist` there is the one
#: consumer, and `test_the_crosswalk_offers_only_the_anchor_as_a_target`
#: covers it behaviourally.
DEFINITION_SITE = "mapping/crosswalk.py"
A_SITE_CONSUMERS = tuple(f for f in A_SITE_FILES if f != DEFINITION_SITE)


def test_exactly_which_catalogs_a_topic_may_anchor():
    """Pinned by exact equality, not by membership.

    **Adding a catalog here grows `/coverage`'s denominator** — its
    requirements become things a topic *could* own and therefore things a
    topic can fail to own. Admitting the AI RMF moved the programme
    headline from 80.3% to 73.7% with the numerator unchanged at 814.
    That is a real report, but it is indistinguishable from lost work if
    it happens without anyone deciding it. So the set is a decision, and
    this is where the decision is recorded.

    Exact equality rather than `in`, because a subset check would let a
    catalog be added silently — which is the case that matters.

    The previous version of this test asserted the set equalled
    `{NIST_ANCHOR}`, which was correct for the commit that split the two
    constants apart and changed no behaviour. It went red when the AI RMF
    was admitted, which is the guard working: a deliberate change to a
    decision should have to be written down twice.
    """
    assert frozenset({NIST_ANCHOR, "nist-ai-rmf"}) == TOPIC_ANCHORS
    assert anchors_a_topic("NIST 800-53") is True
    assert anchors_a_topic("NIST AI RMF") is True
    # Reachable only through the crosswalk, and must stay that way.
    assert anchors_a_topic("HIPAA Security Rule") is False
    assert anchors_a_topic("Information Blocking") is False
    assert anchors_a_topic("NIST 800-171") is False


def test_a_category_claims_its_subcategories():
    """`Govern 1` must claim `Govern 1.1`..`Govern 1.7`.

    "Anchoring a control also claims its enhancements" is the registry's
    documented rule, implemented by `_parent_of`. Before the AI RMF
    grammar was added, `_parent_of('Govern 1.1')` returned `None`, so a
    topic anchoring the category claimed **nothing** and seven
    subcategories reported orphaned — no error, a plausible number, and a
    topic author would have "fixed" it by anchoring all seven by hand.
    **The workaround looks like diligence**, which is what makes the
    silence expensive.
    """
    from policyforge.topics.coverage import _parent_of

    assert _parent_of("Govern 1.1") == "Govern 1"
    assert _parent_of("Manage 4.3") == "Manage 4"
    assert _parent_of("AC-2(1)") == "AC-2"
    # A top-level identifier has no parent, in either grammar.
    assert _parent_of("Govern 1") is None
    assert _parent_of("AC-2") is None
    # Catalogs no topic can anchor keep returning None: a grammar listed
    # for a framework nothing anchors would be untestable.
    assert _parent_of("03.01.01") is None
    assert _parent_of("164.308(a)(1)") is None


def test_the_two_concepts_are_different_kinds_of_thing():
    """A scalar and a set, so they cannot be silently interchanged.

    If someone later writes `NIST_ANCHOR` where `TOPIC_ANCHORS` belongs,
    `in` against a string is a substring test and would quietly answer
    True for any framework key containing "nist-800-53". The type
    difference is load-bearing, not cosmetic.
    """
    assert isinstance(NIST_ANCHOR, str)
    assert isinstance(TOPIC_ANCHORS, frozenset)


@pytest.mark.parametrize("relative", B_SITE_FILES)
def test_no_b_site_still_reads_the_crosswalk_anchor(relative: str):
    """A topic-anchor site naming `NIST_ANCHOR` is the bug coming back.

    This is the guard that survives the people who were here. Someone
    adding a framework filter to `programme.py` reaches for the constant
    they can see; this makes them reach for the right one.
    """
    source = (ROOT / "src" / "policyforge" / relative).read_text(encoding="utf-8")
    assert "NIST_ANCHOR" not in source, (
        f"{relative} decides which catalogs a TOPIC may anchor, so it must use "
        f"`anchors_a_topic`/`TOPIC_ANCHORS`. `NIST_ANCHOR` is the crosswalk "
        f"anchor — what requirements are mapped ONTO — and widening this site "
        f"with it would make a catalog a crosswalk target."
    )


@pytest.mark.parametrize("relative", A_SITE_FILES)
def test_every_a_site_still_exists_and_still_uses_the_scalar(relative: str):
    """The other half of the enumeration.

    Without this, the B-site guard above is satisfied by deleting the
    concept entirely. Naming both lists means the assignment is the
    artefact, not one side of it.
    """
    source = (ROOT / "src" / "policyforge" / relative).read_text(encoding="utf-8")
    assert "NIST_ANCHOR" in source, (
        f"{relative} was assigned to the crosswalk-anchor side and no longer "
        f"mentions it. If that is deliberate, move it to B_SITE_FILES and say "
        f"why; if it is not, the crosswalk anchor has been widened."
    )


def _catalogs():
    from policyforge.ingest.schema import load_controls

    controls = []
    for path in sorted((ROOT / "data" / "frameworks").glob("*/controls.json")):
        controls.extend(load_controls(path))
    return controls


@pytest.mark.parametrize("relative", A_SITE_CONSUMERS)
def test_no_a_site_reads_the_topic_anchor(relative: str):
    """**The test this module exists for, and the only form of it that
    actually fails.**

    The converse of the B-site guard: a crosswalk-anchor site must never
    consult `TOPIC_ANCHORS` or `anchors_a_topic`. That is precisely the
    edit which turns "let topics anchor the AI RMF" into "publish an AI
    RMF crosswalk", and it is a one-line change someone makes while
    believing they are doing the first.

    **This replaced a version that could not fail.** The first attempt
    widened `TOPIC_ANCHORS` with `monkeypatch.setattr` and asserted the
    crosswalk was unmoved. It passed -- and it passed just as happily
    with `candidates.py` deliberately rewritten to follow
    `TOPIC_ANCHORS`, which is the exact defect it existed to catch. The
    reason: `candidates.py` does `from ... import TOPIC_ANCHORS`, binding
    its own module-level name at import time, so patching the attribute
    on `mapping.crosswalk` never reaches it. **A guard against a
    dangerous refactor that was itself a check that cannot fail** --
    found only by performing the mutation instead of trusting the green.

    Reading the source is cruder and it works, because the thing being
    prevented is textual: a name appearing in a file where it does not
    belong.
    """
    source = (ROOT / "src" / "policyforge" / relative).read_text(encoding="utf-8")
    for forbidden in ("TOPIC_ANCHORS", "anchors_a_topic"):
        assert forbidden not in source, (
            f"{relative} decides what requirements are mapped ONTO, and it now "
            f"consults `{forbidden}` -- the set of catalogs a TOPIC may anchor. "
            f"Widening that set would make those catalogs crosswalk targets. "
            f"For the AI RMF that publishes a claim NIST declined to make: that "
            f"an 800-53 control ACHIEVES an AI RMF outcome."
        )


def test_the_crosswalk_offers_only_the_anchor_as_a_target():
    """The behavioural half, with no patching, so nothing is bypassed.

    `catalog_entries` is what a crosswalk proposal offers a model to
    choose from. An AI RMF subcategory appearing there is this failure in
    its user-visible form.
    """
    from policyforge.crosswalk.candidates import catalog_entries

    controls = _catalogs()
    ai_rmf_ids = {
        identifier
        for control in controls
        if normalize_framework(control.framework) == "nist-ai-rmf"
        for identifier in [
            control.control_id,
            *(e.enhancement_id for e in control.enhancements),
        ]
    }
    assert ai_rmf_ids, "the AI RMF catalog is not installed, so this proves nothing"

    leaked = ai_rmf_ids & set(catalog_entries(controls))
    assert not leaked, (
        f"{sorted(leaked)[:5]} are offered as crosswalk targets, which lets a "
        f"model map requirements onto AI RMF outcomes."
    )
    assert "nist-ai-rmf" not in build_crosswalk(controls)


def test_seeding_the_ai_rmf_is_refused():
    """The user-facing path, rather than the internals."""
    from policyforge.crosswalk.overlay import NotAnchorableError, seed_overlay

    with pytest.raises(NotAnchorableError, match="outcomes, not obligations"):
        seed_overlay(_catalogs(), "NIST AI RMF")


def test_the_anchor_error_message_names_the_set_rather_than_a_catalog():
    """A message that hardcodes "NIST 800-53" becomes false the moment the
    set widens, and **a false error message is worse than a missing one** —
    confident, quoted back, and it sends the reader to fix the wrong thing.
    Same family as a remedy command that cannot run.
    """
    for relative in ("cli/programme.py", "cli/documents.py"):
        source = (ROOT / "src" / "policyforge" / relative).read_text(encoding="utf-8")
        assert "contain a catalog a topic can anchor" in source
        assert "None of the --controls files contain NIST 800-53 controls" not in source


def test_the_catalog_count_is_derived_not_remembered():
    """`_catalogs()` above underpins two assertions; if it silently read
    nothing they would both pass vacuously."""
    directories = [
        d for d in (ROOT / "data" / "frameworks").iterdir() if (d / "controls.json").exists()
    ]
    assert len(directories) >= 8
    loaded = {
        json.loads((d / "controls.json").read_text(encoding="utf-8"))[0]["framework"]
        for d in directories
    }
    assert "NIST AI RMF" in loaded
    assert len(_catalogs()) > 500


def test_a_topic_anchoring_ai_rmf_categories_covers_them_end_to_end(tmp_path):
    """**The user's path, not the helper's.**

    `test_a_category_claims_its_subcategories` exercises `_parent_of`
    directly, which proves the regex and nothing about whether a topic
    registry can actually own an AI RMF category. Running the right
    function with your own arguments is not evidence about the product.

    So: write a real topic registry anchoring the six Govern categories,
    load it the way the CLI does, and require that all twenty-five Govern
    identifiers come back owned — six categories and nineteen
    subcategories — with no unknown anchors.
    """
    import yaml

    from policyforge.cli._common import load_catalogs
    from policyforge.topics.coverage import analyze_coverage, scope_label
    from policyforge.topics.registry import load_topics

    registry = tmp_path / "topics.yaml"
    registry.write_text(
        yaml.safe_dump(
            {
                "topics": [
                    {
                        "name": "AI Governance",
                        "owner": "AI Risk / GRC",
                        "cadence": "annual",
                        "description": "Governance of AI systems.",
                        "nist_controls": [f"Govern {n}" for n in range(1, 7)],
                        "evidence": ["AI system inventory"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    paths = [str(p) for p in sorted((ROOT / "data" / "frameworks").glob("*/controls.json"))]
    controls = load_catalogs(paths)
    anchorable = [c for c in controls if anchors_a_topic(c.framework)]
    report = analyze_coverage(
        load_topics(registry),
        anchorable,
        scope=scope_label(anchorable),
        other_controls=[c for c in controls if not anchors_a_topic(c.framework)],
        crosswalk=build_crosswalk(controls),
    )

    govern = {
        identifier
        for control in controls
        if control.framework == "NIST AI RMF"
        for identifier in [
            control.control_id,
            *(e.enhancement_id for e in control.enhancements),
        ]
        if identifier.startswith("Govern")
    }
    assert len(govern) == 25, f"expected 6 categories + 19 subcategories, got {len(govern)}"

    assert not report.unknown_anchors, (
        f"the registry's AI RMF anchors did not resolve: {dict(report.unknown_anchors)}"
    )
    assert not (govern & set(report.orphaned)), (
        f"anchoring the six Govern categories left "
        f"{sorted(govern & set(report.orphaned))[:5]} unowned — a category is "
        f"not claiming its subcategories."
    )


def test_the_scope_line_names_the_catalogs_it_counted():
    """**A percentage whose denominator can change silently is not a
    measurement.**

    Admitting the AI RMF moved the programme headline 80.3% -> 73.7% with
    the numerator unchanged at 814. From the number alone that is
    indistinguishable from work having been lost — and the same arithmetic
    with the opposite meaning was a real defect once, when every installed
    catalog was counted as anchorable and installing one lowered the score.

    The reader cannot tell those apart by looking at the percentage, so
    the scope line names what was counted.
    """
    from policyforge.topics.coverage import scope_label

    controls = [c for c in _catalogs() if anchors_a_topic(c.framework)]
    label = scope_label(controls)
    assert "NIST 800-53" in label
    assert "NIST AI RMF" in label
    assert scope_label(controls, "moderate").startswith("moderate baseline (")
    assert scope_label([]) == "all controls (no anchorable catalog)"


def test_the_shipped_registry_owns_every_ai_rmf_requirement():
    """The example registry ships clean, including the AI RMF.

    **Shipping orphans would demonstrate the failure this tool exists to
    detect** — and the AI RMF is the case where it would be easiest to do
    accidentally, because its 91 requirements only entered the denominator
    when the catalog became anchorable. Before the five AI topics: 291
    orphaned. After: 200, which is exactly the count from before the AI RMF
    was anchorable at all. The 800-53 side is untouched.
    """
    from policyforge.cli._common import load_catalogs
    from policyforge.topics.coverage import analyze_coverage, scope_label
    from policyforge.topics.registry import load_topics

    paths = [str(p) for p in sorted((ROOT / "data" / "frameworks").glob("*/controls.json"))]
    controls = load_catalogs(paths)
    anchorable = [c for c in controls if anchors_a_topic(c.framework)]
    report = analyze_coverage(
        load_topics(ROOT / "config" / "topics.example.yaml"),
        anchorable,
        scope=scope_label(anchorable),
        other_controls=[c for c in controls if not anchors_a_topic(c.framework)],
        crosswalk=build_crosswalk(controls),
    )

    ai_rmf = {
        identifier
        for control in controls
        if control.framework == "NIST AI RMF"
        for identifier in [
            control.control_id,
            *(e.enhancement_id for e in control.enhancements),
        ]
    }
    assert len(ai_rmf) == 91, f"expected 19 categories + 72 subcategories, got {len(ai_rmf)}"

    assert not (ai_rmf & set(report.orphaned)), (
        f"the shipped registry leaves {sorted(ai_rmf & set(report.orphaned))[:5]} "
        f"unowned. A bundled, anchorable catalog with no topic owning it puts "
        f"every user's coverage down for requirements nobody decided to take on."
    )
    assert not report.unknown_anchors, dict(report.unknown_anchors)
    assert not (ai_rmf & set(report.contested)), (
        f"{sorted(ai_rmf & set(report.contested))} is claimed by two topics. "
        f"Third-party AI spans Govern 6, Map 4 and Manage 3 and is deliberately "
        f"ONE topic for that reason; a contested AI id usually means it got "
        f"split back along the framework's functions."
    )


def test_third_party_ai_is_one_topic_across_three_functions():
    """The registry's rule is that **split accountability breaks a topic**,
    and this is the case that tests whether it was followed.

    Cutting the AI RMF one-topic-per-function is the obvious move and it
    would split third-party AI — Govern 6 (policy), Map 4 (what the vendor
    brings), Manage 3 (managing it in production) — across three teams for
    one vendor model. Asserted because the obvious cut is the one someone
    will reach for later.
    """
    from policyforge.topics.registry import load_topics

    topics = load_topics(ROOT / "config" / "topics.example.yaml")
    owners = {
        anchor: topic.name
        for topic in topics
        for anchor in topic.nist_controls
        if anchor in ("Govern 6", "Map 4", "Manage 3")
    }
    assert len(owners) == 3, f"expected all three third-party anchors, found {owners}"
    assert len(set(owners.values())) == 1, (
        f"third-party AI is split across {sorted(set(owners.values()))}. One team "
        f"is accountable for a vendor model end to end; the framework files it "
        f"under three functions but that is not three processes."
    )


# ---- in scope is what the registry ANCHORS, not what it COULD anchor -------


def _registry_without_ai(tmp_path):
    """The shipped registry with every AI topic removed."""
    import yaml

    doc = yaml.safe_load((ROOT / "config" / "topics.example.yaml").read_text(encoding="utf-8"))
    doc["topics"] = [
        t
        for t in doc["topics"]
        if not any(
            str(c).split()[0] in ("Govern", "Map", "Measure", "Manage") for c in t["nist_controls"]
        )
    ]
    path = tmp_path / "topics.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


def _coverage_for(registry_path):
    from policyforge.cli._common import load_catalogs
    from policyforge.topics.coverage import analyze_coverage, scope_label, split_by_adoption
    from policyforge.topics.registry import load_topics

    paths = [str(p) for p in sorted((ROOT / "data" / "frameworks").glob("*/controls.json"))]
    controls = load_catalogs(paths)
    topics = load_topics(registry_path)
    in_scope, unadopted, reachable = split_by_adoption(topics, controls)
    report = analyze_coverage(
        topics,
        in_scope,
        scope=scope_label(in_scope),
        other_controls=reachable,
        crosswalk=build_crosswalk(controls),
    )
    return report, unadopted


def test_a_registry_that_anchors_no_ai_is_unaffected_by_the_bundled_catalog(tmp_path):
    """**The defect this ruling fixes, asserted as a number.**

    A customer who does no AI upgrades to a release that bundles the AI
    RMF. Before the fix their denominator grew by 91 and they lost six
    points for work they never took on — measured by 80: 1105 in scope,
    291 orphaned, against 1014 and 200.

    `anchors_a_topic` answers *could this be anchored*; the coverage scope
    needs *is this anchored*. Those read the same and only diverge once a
    bundled catalog is anchorable **but optional**, which the AI RMF is and
    no earlier catalog was.

    The property to hold: **an existing user's number does not move unless
    they change their own registry.**
    """
    report, unadopted = _coverage_for(_registry_without_ai(tmp_path))
    owned = len(report.in_scope) - len(report.orphaned)

    assert len(report.in_scope) == 1014, (
        f"a registry anchoring no AI RMF id has {len(report.in_scope)} in scope; "
        f"the bundled catalog is being counted against a user who never adopted it"
    )
    assert owned == 814
    assert len(report.orphaned) == 200, "the 800-53 side moved, which it must not"
    assert not any(c.framework == "NIST AI RMF" for c in report_frameworks(report))

    # Excluded, but named: the exclusion must not become a hiding place.
    assert any(c.framework == "NIST AI RMF" for c in unadopted)


def report_frameworks(report):
    """Controls whose ids are in the report's scope, for readability above."""
    from policyforge.cli._common import load_catalogs

    paths = [str(p) for p in sorted((ROOT / "data" / "frameworks").glob("*/controls.json"))]
    in_scope = set(report.in_scope)
    return [
        c
        for c in load_catalogs(paths)
        if c.control_id in in_scope or any(e.enhancement_id in in_scope for e in c.enhancements)
    ]


def test_anchoring_one_ai_identifier_adopts_the_whole_catalog(tmp_path):
    """Adoption is per catalog, not per identifier.

    Anything finer makes coverage unfalsifiable: a registry would only ever
    be measured against what it had already claimed, so it could never be
    told it had missed something.
    """
    import yaml

    doc = yaml.safe_load((ROOT / "config" / "topics.example.yaml").read_text(encoding="utf-8"))
    doc["topics"] = [
        t
        for t in doc["topics"]
        if not any(
            str(c).split()[0] in ("Govern", "Map", "Measure", "Manage") for c in t["nist_controls"]
        )
    ]
    doc["topics"].append(
        {
            "name": "A Toe In The Water",
            "owner": "AI Risk",
            "cadence": "annual",
            "description": "One anchor, to see what happens.",
            "nist_controls": ["Govern 1"],
            "evidence": ["nothing yet"],
        }
    )
    path = tmp_path / "topics.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    report, unadopted = _coverage_for(path)
    assert len(report.in_scope) == 1105, (
        "anchoring one AI RMF identifier did not bring the catalog into scope"
    )
    assert not unadopted, "the catalog is adopted, so nothing should be reported unadopted"
    # Govern 1 and its seven subcategories are owned; the rest are honest gaps.
    assert "Govern 1" not in report.orphaned
    assert "Map 1" in report.orphaned


def test_an_unadopted_catalog_is_named_rather_than_silently_absent(tmp_path):
    """80's condition on the ruling, and the reason it is a condition.

    **Excluding a catalog from the denominator is right; making it
    invisible is not** — the exclusion would become somewhere a framework
    could hide, and a user could not discover an unadopted framework
    without it first distorting their percentage.
    """
    from policyforge.topics.coverage import unadopted_note

    _, unadopted = _coverage_for(_registry_without_ai(tmp_path))
    note = "\n".join(unadopted_note(unadopted))
    assert "NIST AI RMF" in note
    assert "91 requirements" in note
    assert "anchored by no topic" in note
    assert unadopted_note([]) == [], "an all-adopted registry prints no section"


def test_generation_still_sees_every_anchorable_catalog():
    """**`documents.py` deliberately keeps the wider set, and that is not an
    oversight.**

    Generation needs a control to be AVAILABLE, which is a different
    question from whether it belongs in a denominator. Narrowing the
    generation path by adoption too would mean a topic anchoring `Govern 1`
    could not draw on the catalog it anchors.
    """
    source = (ROOT / "src" / "policyforge" / "cli" / "documents.py").read_text(encoding="utf-8")
    assert "anchors_a_topic(c.framework)" in source, (
        "documents.py no longer uses the wide anchorable set. If that is "
        "deliberate, check a topic anchoring an AI RMF category can still "
        "generate — it draws on controls this filter selects."
    )
    assert "split_by_adoption" not in source, (
        "documents.py now scopes generation by adoption. That is the coverage "
        "question, not the generation one."
    )


def test_adoption_only_ever_narrows(tmp_path):
    """**A guard has to state what it ALLOWS, not only what it refuses.**

    Narrowing the scope to adopted catalogs must not turn *you have a typo*
    into *you have no registry*. A registry whose every anchor is a typo
    adopts nothing, and the informative answer is still the full scope plus
    `unknown_anchors` — which is the field that exists to say so.

    Found by the suite, not by reasoning: an existing test anchoring `ZZ-9`
    against a catalog of `AC-2` went red reporting "no topic anchors any
    catalog on disk".

    The empty registry is **not** a case here, and checking that was worth
    more than the assertion I first wrote about it: `parse_topics` refuses
    `topics: []` outright. The product rejects it one layer up, which is a
    better place than a fallback in the scope rule.
    """
    import yaml

    from policyforge.cli._common import load_catalogs
    from policyforge.topics.coverage import split_by_adoption
    from policyforge.topics.registry import load_topics

    paths = [str(p) for p in sorted((ROOT / "data" / "frameworks").glob("*/controls.json"))]
    controls = load_catalogs(paths)

    for label, topic_list in [
        (
            "every anchor a typo",
            [
                {
                    "name": "Typos",
                    "owner": "O",
                    "cadence": "annual",
                    "description": "x",
                    "nist_controls": ["ZZ-9"],
                    "evidence": ["x"],
                }
            ],
        ),
        (
            "anchors that name no catalog here",
            [
                {
                    "name": "Elsewhere",
                    "owner": "O",
                    "cadence": "annual",
                    "description": "x",
                    "nist_controls": ["A.5.1", "A.5.2"],
                    "evidence": ["x"],
                }
            ],
        ),
    ]:
        path = tmp_path / f"{label.replace(' ', '-')}.yaml"
        path.write_text(yaml.safe_dump({"topics": topic_list}), encoding="utf-8")
        in_scope, unadopted, _ = split_by_adoption(load_topics(path), controls)
        assert in_scope, f"{label}: scope collapsed to nothing instead of staying wide"
        assert not unadopted, (
            f"{label}: a catalog was reported unadopted even though nothing was "
            f"adopted — narrowing fired when there was nothing to narrow to"
        )
        frameworks = {c.framework for c in in_scope}
        assert frameworks == {"NIST 800-53", "NIST AI RMF"}, frameworks

    # The empty registry never reaches the scope rule: the parser refuses it.
    from policyforge.topics.registry import TopicRegistryError, parse_topics

    with pytest.raises(TopicRegistryError, match="non-empty"):
        parse_topics({"topics": []})
