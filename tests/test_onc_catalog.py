"""The shipped ONC certification catalog, and the README that describes it.

Written with the catalog rather than after a PR is blocked for it — the
third time that lesson has been applied today and the second time before
being asked.

**The failure this file guards against is not a crash.** § 170.315 is one
section of 540 flat paragraphs whose hierarchy is in the text, so a parse
that reads labels naively produces a plausible catalog with invented ids:
`170.315(v)`, `170.315(x)`, and dozens of controls whose numbers name
sub-clauses. Nothing raises. So the assertions here pin identifier
*shape* and the specific phantoms, not counts alone.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

CATALOG = Path(__file__).resolve().parent.parent / "data" / "frameworks"
CATALOG = CATALOG / "cfr-170-315-onc-certification"

#: `170.315(g)(10)` — the section, a category letter, a criterion number.
CRITERION_RE = re.compile(r"^170\.315\([a-z]\)\(\d+\)$")
#: `(g)` — the category a criterion belongs to.
FAMILY_RE = re.compile(r"^\([a-z]\)$")


@pytest.fixture(scope="module")
def controls() -> list[dict]:
    return json.loads((CATALOG / "controls.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def readme() -> str:
    """Whitespace collapsed, so a `mdformat` reflow that changes nothing
    does not break an assertion about what the README says."""
    return " ".join((CATALOG / "README.md").read_text(encoding="utf-8").split())


# --------------------------------------------------------------------------
# Identifiers, which is where a naive parse looks right and is wrong
# --------------------------------------------------------------------------


def test_every_id_is_a_criterion_citation(controls):
    """A control id must be citable as `170.315(g)(10)`. A parse that read
    sub-paragraph labels as criteria yields ids naming sub-clauses, and
    every count check still passes."""
    wrong = [c["control_id"] for c in controls if not CRITERION_RE.match(c["control_id"])]

    assert wrong == [], f"ids that are not criterion citations: {wrong}"


def test_every_family_is_a_category_letter(controls):
    wrong = [c["family_abbr"] for c in controls if not FAMILY_RE.match(c["family_abbr"] or "")]

    assert wrong == [], f"families that are not category letters: {wrong}"


def test_a_criterion_belongs_to_the_category_its_own_id_names(controls):
    """Holds the two against each other, so a parse that got one right and
    the other wrong is caught rather than looking self-consistent."""
    for control in controls:
        letter = control["family_abbr"].strip("()")
        assert control["control_id"].startswith(f"170.315({letter})(")


@pytest.mark.parametrize("phantom", ["170.315(v)", "170.315(x)"])
def test_the_roman_numeral_phantoms_are_absent(controls, phantom):
    """`(i)`, `(v)` and `(x)` are roman numerals in 47 sub-paragraphs and
    letters in one. Reading them all as criteria invents categories the
    regulation does not have."""
    ids = {c["control_id"] for c in controls}

    assert not any(i.startswith(phantom) for i in ids)


@pytest.mark.parametrize(
    "citation",
    ["170.315(a)(1)", "170.315(b)(1)", "170.315(d)(1)", "170.315(g)(10)", "170.315(j)(20)"],
)
def test_criteria_people_actually_cite_are_present(controls, citation):
    """`170.315(g)(10)` is the standardized API criterion and the most
    cited of these anywhere. `(j)(20)` is in the category whose first
    nineteen criteria are a reserved range, so it also pins that the range
    advanced the counter rather than stopping the parse."""
    assert citation in {c["control_id"] for c in controls}


# --------------------------------------------------------------------------
# Reserved criteria: found, not emitted, and said so
# --------------------------------------------------------------------------


def test_no_reserved_criterion_is_emitted(controls):
    """`is_reserved`'s docstring names this as the assertion that was owed
    and could not be written: *the emitted catalog must be asserted not to
    contain 170.315(i), and there is no emitter to assert it against*.

    There is one now. Together with the source-side test that the letter
    run is unbroken from (a) to (j), this proves the parser saw ten
    categories and emitted nine deliberately — alone, the source-side test
    proves only that it saw ten.
    """
    ids = {c["control_id"] for c in controls}

    assert not any(i.startswith("170.315(i)") for i in ids)
    for reserved in ("170.315(a)(6)", "170.315(g)(11)", "170.315(j)(1)"):
        assert reserved not in ids


def test_nothing_emitted_is_empty(controls):
    """No exception for reserved paragraphs, deliberately: an exception
    has to be kept in step with the source and can drift, where a rule
    with no exception cannot."""
    for control in controls:
        assert control["title"].strip(), control["control_id"]
        assert control["control_statement"].strip(), control["control_id"]


def test_criteria_in_one_category_have_distinct_titles(controls):
    """`(a)(1)`, `(a)(2)` and `(a)(3)` are all "Computerized provider order
    entry" and differ only after the em dash. A title cut at the dash gives
    three criteria one name, which reads as a duplicate rather than a
    parse fault."""
    by_family: dict[str, list[str]] = {}
    for control in controls:
        by_family.setdefault(control["family_abbr"], []).append(control["title"])

    for family, titles in by_family.items():
        assert len(set(titles)) == len(titles), f"duplicate titles within {family}: {titles}"


# --------------------------------------------------------------------------
# The README, held to the catalog
# --------------------------------------------------------------------------


def test_the_readme_counts_match_the_catalog(controls, readme):
    families = {c["family_abbr"] for c in controls}
    stated = re.search(r"(\d+) criteria across (\d+) categories", readme)

    assert stated, "the README no longer states its counts"
    assert int(stated.group(1)) == len(controls)
    assert int(stated.group(2)) == len(families)


def test_the_readme_arithmetic_closes(controls, readme):
    """`69 + 47 = 116` is stated as a sum so a reader can check it rather
    than take three numbers on trust."""
    stated = re.search(r"(\d+) \+ (\d+) = (\d+)", readme)

    assert stated, "the README no longer states the reserved arithmetic"
    emitted, reserved, total = (int(g) for g in stated.groups())
    assert emitted == len(controls)
    assert emitted + reserved == total


def test_the_readme_says_a_criterion_is_not_a_control(readme):
    """The product distinction a buyer needs: a criterion says a product
    can do something, a control says an organization does it. Citing one
    as the other is the category error this project keeps finding."""
    assert "not the same as a control catalog" in readme
    assert "capability exists" in readme


def test_the_readme_explains_the_missing_category(controls, readme):
    """There is no `(i)` row in the README's table and no `(i)` control in
    the catalog. A reader who counts the letters will notice; the README
    has to say why before they go looking for a parse bug."""
    assert not any(c["family_abbr"] == "(i)" for c in controls)
    assert "170.315(i)` is reserved in its entirety" in readme
