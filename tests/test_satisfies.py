"""What a document can be shown against, from the citations in its text.

The properties this report is only worth running if it holds:

* the evidence is the citations, and a topic anchor is never counted as one;
* a mapping's provenance never flattens — reviewed, unreviewed and published
  stay distinguishable, `superset`/`intersects` render as *in part*, and a
  pair somebody rejected is not reachable at all;
* a citation is parsed by asking the catalog, not by counting words, since
  framework names, requirement ids and qualifiers all carry spaces.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from policyforge.crosswalk.overlay import (
    ACCEPTED,
    REJECTED,
    MappingRow,
    Overlay,
    accepted_rows,
    apply_overlays,
)
from policyforge.ingest.schema import Control, ControlEnhancement
from policyforge.mapping.crosswalk import build_crosswalk
from policyforge.topics.registry import Topic
from policyforge.topics.satisfies import (
    PUBLISHED,
    REVIEWED,
    UNREVIEWED,
    as_records,
    build_report,
    document_evidence,
    format_report,
    parse_citations,
    resolve_framework,
    split_citation,
)

HIPAA = "HIPAA Security Rule"
NIST = "NIST 800-53"


class FakeDocument:
    """The three attributes this analysis reads off a ContentDocument."""

    def __init__(self, body, *, path="standards/access.md", title="Access", topic="", slug=""):
        self.body = body
        self.relative_path = path
        self.title = title
        self.tier = "standard"
        self.metadata = {"topic": topic}
        self.topic = topic
        self.slug = slug or path.split("/")[-1].removesuffix(".md")


def _catalogs():
    nist = [
        Control(
            control_id="AC-2",
            title="Account Management",
            framework=NIST,
            framework_version="r5",
            control_statement="Manage accounts.",
            enhancements=[
                ControlEnhancement(
                    enhancement_id="AC-2(3)",
                    title="Disable Accounts",
                    baseline="Moderate",
                    description="Disable accounts.",
                )
            ],
        ),
        Control(
            control_id="IR-3",
            title="Incident Response Testing",
            framework=NIST,
            framework_version="r5",
            control_statement="Test the plan.",
            enhancements=[
                ControlEnhancement(
                    enhancement_id="IR-3(1)",
                    title="Automated Testing",
                    baseline="High",
                    description="Automate it.",
                )
            ],
        ),
    ]
    hipaa = [
        Control(
            control_id="164.308(a)(3)(i)",
            title="Workforce security",
            framework=HIPAA,
            framework_version="45 CFR 164",
            control_statement="Authorize access.",
            source_crosswalk={"nist": "AC-2"},
        ),
        Control(
            control_id="164.308(a)(4)(i)",
            title="Information access management",
            framework=HIPAA,
            framework_version="45 CFR 164",
            control_statement="Authorize access to ePHI.",
            source_crosswalk={"nist": "AC-2"},
        ),
        Control(
            control_id="164.308(a)(6)(ii)",
            title="Response and reporting",
            framework=HIPAA,
            framework_version="45 CFR 164",
            control_statement="Respond to incidents.",
            source_crosswalk={"nist": "IR-3"},
        ),
    ]
    return nist + hipaa


def _evidence(body, *, controls=None, overlays=(), **kwargs):
    controls = controls if controls is not None else _catalogs()
    if overlays:
        apply_overlays(controls, list(overlays))
    return document_evidence(
        FakeDocument(body, **kwargs),
        controls=controls,
        crosswalk=build_crosswalk(controls),
        provenance=accepted_rows(list(overlays)),
    )


# --- parsing: every field of a citation can contain a space ---------------


def test_framework_name_is_taken_from_the_catalog_not_the_first_word():
    """`NIST 800-53 AC-2` is one framework and one id, not `NIST` + `800-53 AC-2`.

    The generator writes the framework's full name. Splitting on the first
    space leaves `800-53 AC-2` as the requirement, which resolves to
    nothing, and the citation is then reported as unknown while sitting in
    the document perfectly well-formed.
    """
    names = [NIST, HIPAA]
    ids = {"nist": {"AC-2"}, "hipaa": {"164.308(a)(3)(i)"}}
    assert split_citation("NIST 800-53 AC-2", names, ids) == (NIST, "AC-2", "")
    assert split_citation(f"{HIPAA} 164.308(a)(3)(i)", names, ids) == (
        HIPAA,
        "164.308(a)(3)(i)",
        "",
    )


def test_qualifier_is_split_off_by_asking_the_catalog():
    """`AC-2(3) Moderate, High` is an id plus a qualifier — and so is `... AE Mandatory`.

    The vocabulary is per-framework and open-ended: NIST baselines, HIPAA's
    `Addressable`, ARC-AMPE's `AE Mandatory`. Matching a fixed word list
    would need updating per framework, so the id is the longest run of
    words the catalog actually has.
    """
    names = [NIST, HIPAA]
    ids = {"nist": {"AC-2(3)"}, "hipaa": {"164.310(a)(2)(i)"}}
    assert split_citation("NIST 800-53 AC-2(3) Moderate, High", names, ids) == (
        NIST,
        "AC-2(3)",
        "Moderate, High",
    )
    assert split_citation(f"{HIPAA} 164.310(a)(2)(i) Addressable", names, ids) == (
        HIPAA,
        "164.310(a)(2)(i)",
        "Addressable",
    )


def test_an_identifier_containing_spaces_survives():
    """HITRUST builds ids like `01.a Level 1`, so the last word is not the qualifier.

    This is why the split asks the catalog from the long end first: taking
    the trailing word would leave `01.a Level`, which is not an id in any
    framework.
    """
    ids = {"hitrust": {"01.a Level 1"}}
    assert split_citation("HITRUST CSF 01.a Level 1", ["HITRUST CSF"], ids) == (
        "HITRUST CSF",
        "01.a Level 1",
        "",
    )


def test_an_unresolvable_citation_is_returned_as_written():
    """No id matches, so nothing is split off and it is reported verbatim.

    Guessing a shorter id here would invent a citation the document does
    not contain, and the reader would go looking for the wrong defect.
    """
    assert split_citation("HIPAA Documentation Review Frequency", [HIPAA], {"hipaa": set()}) == (
        "HIPAA",
        "Documentation Review Frequency",
        "",
    )


def test_the_nearest_heading_above_a_citation_is_recorded():
    body = "# Access\n\n## Provisioning\n\nRequests are approved. [NIST 800-53 AC-2]\n"
    found = parse_citations(body, [NIST], {"nist": {"AC-2"}})
    assert found == [(NIST, "AC-2", "", "Provisioning")]


# --- the evidence is the citations ---------------------------------------


def test_a_cited_control_reaches_the_requirements_crosswalked_to_it():
    evidence = _evidence("## Accounts\n\nAccounts are managed. [NIST 800-53 AC-2]\n")
    assert [c.requirement_id for c in evidence.cited] == ["AC-2"]
    assert [(r.framework, r.requirement_id, r.via) for r in evidence.reached] == [
        ("hipaa", "164.308(a)(3)(i)", "AC-2"),
        ("hipaa", "164.308(a)(4)(i)", "AC-2"),
    ]


def test_a_requirement_cited_outright_is_not_also_reported_as_crosswalked():
    """Cited beats reached: it is the stronger evidence, and one row is one pair."""
    evidence = _evidence(
        "## Accounts\n\n[NIST 800-53 AC-2 | HIPAA Security Rule 164.308(a)(3)(i)]\n"
    )
    assert ("hipaa", "164.308(a)(3)(i)") in {c.key for c in evidence.cited}
    assert "164.308(a)(3)(i)" not in {r.requirement_id for r in evidence.reached}


def test_a_citation_no_catalog_has_is_reported_not_dropped():
    evidence = _evidence("## X\n\n[HIPAA Security Rule 164.308(a)(7)(ii)]\n")
    assert evidence.cited == []
    assert evidence.unknown == [f"{HIPAA} 164.308(a)(7)(ii)"]


def test_a_real_id_cited_under_the_wrong_framework_is_unknown():
    """`HIPAA AC-2` names a real NIST control, and resolves to nothing in HIPAA.

    Checked per framework rather than against every id in every catalog,
    because an assessor follows the citation as written.
    """
    evidence = _evidence("## X\n\n[HIPAA Security Rule AC-2]\n")
    assert evidence.cited == []
    assert evidence.unknown == [f"{HIPAA} AC-2"]


# --- anchors are intentions, not evidence --------------------------------


def test_an_anchor_no_document_cites_is_reported_apart_from_the_citations():
    topics = [Topic(name="Access", owner="IAM", nist_controls=["AC-2", "IR-3"])]
    controls = _catalogs()
    documents = [FakeDocument("[NIST 800-53 AC-2]", path="standards/access.md", slug="access")]
    (evidence,) = build_report(
        documents, controls=controls, crosswalk=build_crosswalk(controls), topics=topics
    )
    assert [c.requirement_id for c in evidence.cited] == ["AC-2"]
    # IR-3 is claimed by the registry and named nowhere in the text.
    assert evidence.anchored_not_cited == ["IR-3"]


def test_citing_an_enhancement_counts_as_mentioning_its_control():
    """A topic citing IR-3(1) has not ignored IR-3; the enhancement is part of it.

    `coverage` reads the relation the other way round — anchoring IR-3
    claims IR-3(1) — and reporting IR-3 as "cited nowhere" here would put a
    false gap in the section an assessor reads first.
    """
    topics = [Topic(name="Access", owner="IAM", nist_controls=["IR-3"])]
    controls = _catalogs()
    documents = [FakeDocument("[NIST 800-53 IR-3(1) High]", path="s/access.md", slug="access")]
    (evidence,) = build_report(
        documents, controls=controls, crosswalk=build_crosswalk(controls), topics=topics
    )
    assert evidence.anchored_not_cited == []


def test_a_topics_documents_answer_for_its_anchors_together():
    """The Procedure citing IR-3 covers the Policy that does not.

    Asked one file at a time, a Policy would be reported as missing every
    anchor its own Procedure cites, which is noise.
    """
    topics = [Topic(name="Access", owner="IAM", nist_controls=["AC-2", "IR-3"])]
    controls = _catalogs()
    documents = [
        FakeDocument("No tags here.", path="policies/access.md", slug="access"),
        FakeDocument("[NIST 800-53 AC-2] [NIST 800-53 IR-3]", path="p/access.md", slug="access"),
    ]
    policy, _ = build_report(
        documents, controls=controls, crosswalk=build_crosswalk(controls), topics=topics
    )
    assert policy.cited == []
    assert policy.anchored_not_cited == []


# --- provenance never flattens -------------------------------------------


def _overlay(rows):
    return Overlay(framework=HIPAA, anchor="nist", requirements=rows)


def test_a_reviewed_partial_mapping_is_reported_in_part_never_as_satisfied():
    """`superset` means the requirement asks for more than the control gives.

    The same reading `coverage` uses for its "reached in part" column. A
    report that called this satisfied would be claiming coverage nobody
    recorded.
    """
    overlay = _overlay(
        {
            "164.308(a)(3)(i)": [
                MappingRow(
                    control="AC-2",
                    relationship="superset",
                    status=ACCEPTED,
                    reviewed_by={"who": "ryan"},
                )
            ]
        }
    )
    evidence = _evidence("[NIST 800-53 AC-2]", overlays=[overlay])
    (reached,) = [r for r in evidence.reached if r.requirement_id == "164.308(a)(3)(i)"]
    assert reached.in_part is True
    assert reached.provenance == REVIEWED
    assert reached.reviewed_by == "ryan"
    assert "in part" in format_report([evidence])
    assert "164.308(a)(3)(i)     satisfied" not in format_report([evidence])


def test_a_rejected_pair_is_not_reachable_at_all():
    """Rejected means a person looked at it and said no. It is not evidence.

    Asserted through the real pipeline — `apply_overlays` then
    `build_crosswalk` — rather than against a hand-built crosswalk, so this
    keeps holding if the way a rejection is applied changes.
    """
    overlay = _overlay(
        {
            "164.308(a)(3)(i)": [
                MappingRow(control="AC-2", status=REJECTED, reviewed_by={"who": "ryan"})
            ],
            "164.308(a)(4)(i)": [
                MappingRow(control="AC-2", status=ACCEPTED, reviewed_by={"who": "ryan"})
            ],
        }
    )
    evidence = _evidence("[NIST 800-53 AC-2]", overlays=[overlay])
    reached = {r.requirement_id for r in evidence.reached}
    assert "164.308(a)(3)(i)" not in reached
    assert "164.308(a)(4)(i)" in reached
    assert "164.308(a)(3)(i)" not in format_report([evidence])


def test_an_unreviewed_mapping_is_shown_and_marked_rather_than_hidden():
    """A model proposal accepted by hand is the weakest evidence in the file.

    It is still reported: dropping it would make the report look stronger
    than what stands behind it. The text has to say so in terms a reader
    cannot miss.
    """
    overlay = _overlay(
        {
            "164.308(a)(3)(i)": [
                MappingRow(
                    control="AC-2",
                    status=ACCEPTED,
                    sources=["model"],
                    proposed_by={"model": "glm"},
                )
            ]
        }
    )
    evidence = _evidence("[NIST 800-53 AC-2]", overlays=[overlay])
    (reached,) = [r for r in evidence.reached if r.requirement_id == "164.308(a)(3)(i)"]
    assert reached.provenance == UNREVIEWED
    assert evidence.unreviewed == [reached]
    report = format_report([evidence])
    assert "NOT REVIEWED" in report
    assert "accepted by hand" in report


def test_a_seeded_published_pair_is_not_called_unreviewed():
    """`seed_overlay` accepts the catalog's own pairs with no reviewer.

    Nobody reviewed them because they came with the catalog. Calling those
    unreviewed would flag every row of a freshly seeded file and teach a
    reader to ignore the warning.
    """
    overlay = _overlay(
        {"164.308(a)(3)(i)": [MappingRow(control="AC-2", status=ACCEPTED, sources=["published"])]}
    )
    evidence = _evidence("[NIST 800-53 AC-2]", overlays=[overlay])
    (reached,) = [r for r in evidence.reached if r.requirement_id == "164.308(a)(3)(i)"]
    assert reached.provenance == PUBLISHED
    assert evidence.unreviewed == []


def test_a_pair_with_no_overlay_row_is_published_provenance():
    evidence = _evidence("[NIST 800-53 AC-2]")
    assert {r.provenance for r in evidence.reached} == {PUBLISHED}


# --- the JSON shape is a contract ----------------------------------------


def test_json_records_carry_provenance_and_route_for_every_mapping():
    overlay = _overlay(
        {
            "164.308(a)(3)(i)": [
                MappingRow(
                    control="AC-2",
                    relationship="intersects",
                    status=ACCEPTED,
                    reviewed_by={"who": "ryan"},
                    flags=["not-confirmed-by-model"],
                )
            ]
        }
    )
    evidence = _evidence("[NIST 800-53 AC-2]", overlays=[overlay])
    (record,) = as_records([evidence])
    assert record["document"] == "standards/access.md"
    assert {c["route"] for c in record["cited"]} == {"cited"}
    reached = next(r for r in record["reached"] if r["requirement_id"] == "164.308(a)(3)(i)")
    assert reached == {
        "framework": "hipaa",
        "requirement_id": "164.308(a)(3)(i)",
        "route": "crosswalked",
        "via": "AC-2",
        "provenance": REVIEWED,
        "relationship": "intersects",
        "in_part": True,
        "reviewed_by": "ryan",
        "flags": ["not-confirmed-by-model"],
        "sections": [],
    }


# --- the command ----------------------------------------------------------


@pytest.fixture
def programme(tmp_path, monkeypatch):
    """A content tree, a registry and catalogs, laid out as the CLI expects."""
    from policyforge.cli import cli  # noqa: F401  (registers the commands)

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "docs" / "standards").mkdir(parents=True)
    (tmp_path / "docs" / "standards" / "access.md").write_text(
        "# Access\n\n## Provisioning\n\nAccounts are managed. [NIST 800-53 AC-2]\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "topics.yaml").write_text(
        "topics:\n  - name: Access\n    owner: IAM\n    nist_controls: [AC-2, IR-3]\n",
        encoding="utf-8",
    )
    import dataclasses

    controls = tmp_path / "controls.json"
    controls.write_text(json.dumps([dataclasses.asdict(c) for c in _catalogs()]), encoding="utf-8")
    return tmp_path, controls


def _run(controls, *args):
    from policyforge.cli import cli

    return CliRunner().invoke(cli, ["satisfies", "--controls", str(controls), *args])


def test_command_reports_a_topics_documents(programme):
    _, controls = programme
    result = _run(controls, "--topic", "Access")
    assert result.exit_code == 0, result.output
    assert "AC-2" in result.output
    assert "164.308(a)(3)(i)" in result.output
    # IR-3 is anchored by the registry and cited by nothing.
    assert "Anchored by the topic, cited nowhere" in result.output
    assert "IR-3" in result.output


def test_command_refuses_more_than_one_selector(programme):
    _, controls = programme
    result = _run(controls, "--all", "--topic", "Access")
    assert result.exit_code != 0
    assert "exactly one of --document, --topic or --all" in result.output


def test_strict_fails_only_on_a_citation_that_resolves_to_nothing(programme):
    root, controls = programme
    assert _run(controls, "--all", "--strict").exit_code == 0
    (root / "docs" / "standards" / "access.md").write_text(
        "# Access\n\n[HIPAA Security Rule 164.999]\n", encoding="utf-8"
    )
    result = _run(controls, "--all", "--strict")
    assert result.exit_code == 1
    assert "resolve to nothing" in result.output


def test_require_reviewed_is_a_separate_gate_from_strict(programme):
    """An unreviewed mapping is a state of the programme, not a broken document.

    `--strict` passes with one present; only `--require-reviewed` fails, so
    a CI job can demand well-formed citations without also demanding that
    every overlay row has been through review.
    """
    root, controls = programme
    (root / "config" / "crosswalks").mkdir()
    (root / "config" / "crosswalks" / "hipaa.yaml").write_text(
        "framework: HIPAA Security Rule\n"
        "anchor: nist\n"
        "requirements:\n"
        "  164.308(a)(3)(i):\n"
        "    - control: AC-2\n"
        "      status: accepted\n"
        "      sources: [model]\n",
        encoding="utf-8",
    )
    strict = _run(controls, "--all", "--strict")
    assert strict.exit_code == 0, strict.output
    assert "NOT REVIEWED" in strict.output

    gated = _run(controls, "--all", "--require-reviewed")
    assert gated.exit_code == 1
    assert "unreviewed overlay entry" in gated.output


def test_json_output_is_parseable_and_lists_every_document(programme):
    _, controls = programme
    result = _run(controls, "--all", "--json")
    assert result.exit_code == 0, result.output
    records = json.loads(result.output)
    assert [r["document"] for r in records] == ["standards/access.md"]
    assert records[0]["cited"][0]["requirement_id"] == "AC-2"


def test_the_report_says_how_much_it_searched_before_calling_an_anchor_uncited():
    """The same list means two different things depending on the scope.

    A gap found across a topic's three documents is a real gap; the same
    list under `--document` only means this one file does not cite it.
    Leaving the reader to infer which would send somebody to rewrite a
    Policy that was never the problem.
    """
    topics = [Topic(name="Access", owner="IAM", nist_controls=["AC-2", "IR-3"])]
    controls = _catalogs()
    both = [
        FakeDocument("[NIST 800-53 AC-2]", path="policies/access.md", slug="access"),
        FakeDocument("No tags.", path="procedures/access.md", slug="access"),
    ]
    policy, _ = build_report(
        both, controls=controls, crosswalk=build_crosswalk(controls), topics=topics
    )
    assert policy.anchored_scope == "across this topic's 2 documents"
    assert "searched across this topic's 2 documents" in format_report([policy])

    (alone,) = build_report(
        both[:1], controls=controls, crosswalk=build_crosswalk(controls), topics=topics
    )
    assert alone.anchored_scope == "in this document alone"
    assert "searched in this document alone" in format_report([alone])


def test_the_unreviewed_warning_names_the_state_it_describes():
    """ "Not reviewed" has to mean something a reader can act on.

    The state is: somebody wrote `accepted` into the overlay by hand
    instead of going through `crosswalk review`, so no one has recorded
    checking it. A vaguer warning gets ignored.
    """
    overlay = _overlay(
        {"164.308(a)(3)(i)": [MappingRow(control="AC-2", status=ACCEPTED, sources=["model"])]}
    )
    report = format_report([_evidence("[NIST 800-53 AC-2]", overlays=[overlay])])
    assert "accepted by hand" in report
    assert "NOT accepted through `policyforge crosswalk review`" in report


def test_an_abbreviation_resolves_when_it_names_exactly_one_loaded_catalog():
    """`ARC` reaches ARC-AMPE for the same reason `NIST` reaches NIST 800-53.

    Tags abbreviate — the synthesis prompt teaches it by example and never
    says what a given name's short form is. Accepting `NIST` while
    rejecting `ARC` was an accident of first-word normalization, not a
    rule, and it reported well-formed citations as defects.
    """
    ids = {"nist": {"PE-1"}, "arc-ampe": {"PE-1"}, "hipaa": {"164.308(a)(3)(i)"}}
    assert resolve_framework("ARC", ids) == "arc-ampe"
    assert resolve_framework("ARC-AMPE", ids) == "arc-ampe"
    assert resolve_framework("NIST", ids) == "nist"
    assert resolve_framework("NIST 800-53", ids) == "nist"
    assert resolve_framework("HIPAA Security Rule", ids) == "hipaa"


def test_an_abbreviation_naming_two_catalogs_resolves_to_neither():
    """With 800-53 and 800-171 both loaded, `NIST` names no one catalog.

    Picking one would attribute a citation to a framework the document
    never named. Reported as unknown instead, which is what it is.
    """
    ids = {"nist-800-53": {"AC-2"}, "nist-800-171": {"3.1.1"}}
    assert resolve_framework("NIST", ids) == ""
    assert resolve_framework("NIST-800-53", ids) == "nist-800-53"


def test_a_partial_token_is_not_an_abbreviation():
    assert resolve_framework("NIS", {"nist": {"AC-2"}}) == ""


def test_an_abbreviated_framework_is_followed_through_to_the_crosswalk():
    """End to end: the citation resolves, so it counts as evidence.

    Guards the real regression — `[ARC PE-1]` was reported as an unknown
    citation while naming a requirement the loaded catalog has.
    """
    controls = _catalogs() + [
        Control(
            control_id="PE-1",
            title="Physical protection policy",
            framework="ARC-AMPE",
            framework_version="1.0",
            control_statement="Protect the facility.",
            source_crosswalk={"nist": "AC-2"},
        )
    ]
    # The tag as the generator actually wrote it. `edit/apply._SOURCE_TAG_RE`
    # only matches a tag whose *first* citation names a listed framework, so
    # a bare `[ARC PE-1]` is invisible to every stage of the pipeline — this
    # report and `content/check` alike. That is a shared-regex question, not
    # this command's to answer, so the case here is the one that occurs.
    evidence = _evidence("[NIST 800-53 AC-2 | ARC PE-1 AE Mandatory]", controls=controls)
    assert evidence.unknown == []
    assert [(c.framework, c.requirement_id, c.qualifier) for c in evidence.cited] == [
        ("arc-ampe", "PE-1", "AE Mandatory"),
        ("nist", "AC-2", ""),
    ]
