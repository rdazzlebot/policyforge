"""A "may" that states a possibility is neither permission nor prohibition (#364).

*May* binds with an agent and an action verb ("You may not share your
password"). With a verb of judgement ("may not be considered external",
"may also be known as") or an adjective ("may not always be possible", "may
be necessary") it says what might be true (80's rulings on #364: the ruled
verbs, plus an explicit adjective list, never a suffix rule; no -ed form is
ever cleared).

**Measured:** f8's 43 sentences from #360 change on L6, L11 and L12 only;
the shipped catalogs on 57 discussion sentences, each a possibility; the 33
Standards on 5, with `check` 158 -> 158 (one warning reworded: see #363).
"""

from __future__ import annotations

import pytest

from policyforge.content.deontic import NONE, PERMISSION, PROHIBITION, classify


@pytest.mark.parametrize(
    ("sentence", "modality"),
    [
        # 5b's rows on #360, verbatim: must change.
        ("Systems within these organizations may not be considered external.", NONE),
        (
            "Emergency and temporary accounts are not to be confused with infrequently used "
            "accounts, including local logon accounts used for special tasks or when network "
            "resources are unavailable (may also be known as accounts of last resort).",
            NONE,
        ),
        (
            "Wireless link protection applies to internal and external wireless communication "
            "links that may be visible to individuals who are not authorized system users.",
            NONE,
        ),
        # From the shipped catalogs (800-53 PS-4, CM-7; 800-171; the Playbook).
        ("Exit interviews may not always be possible for some individuals.", NONE),
        ("Some of the functions and services may not be necessary to support operations.", NONE),
        ("Establish processes for tracking emergent risks that may not be measurable.", NONE),
        ("Organizations may be subject to laws, executive orders, and directives.", NONE),
        ("Such energy bursts may be natural or man-made.", NONE),
        # 5b's rows that must stay, verbatim.
        ("You may not share your personal UW NetID password.", PROHIBITION),
        (
            "Users may not share University Confidential Data with friends or family members.",
            PROHIBITION,
        ),
        ("However, exceptions may be required based on operational mission or need.", PERMISSION),
        # Action participles and verbs are never cleared.
        (
            "Any subsequent sharing that is not compatible may not be done until approved.",
            PROHIBITION,
        ),
        ("Access to PII may not be granted to entities that are unknown.", PROHIBITION),
        ("An actor may not charge a royalty for intellectual property.", PROHIBITION),
        ("Workstations may not be left unattended.", PROHIBITION),
        ("Records may be withheld under this section.", PERMISSION),
        # "known" only as a name: split knowledge is a requirement.
        ("The key may not be known to any single administrator.", PROHIBITION),
        # An unlisted adjective stays as it was, loudly (80: never a suffix rule).
        ("Staff may not be accountable for vendor errors.", PROHIBITION),
    ],
)
def test_classify(sentence, modality):
    assert classify(sentence) == modality


@pytest.mark.xfail(strict=True, reason="named miss (80, option (c) out): a thing's capability")
@pytest.mark.parametrize(
    "sentence",
    [
        "Dynamic account creation is an automated process that may not support independent "
        "verification of a need to know.",
        "Such key combinations, however, are platform-specific and may not provide a trusted "
        "path implementation in every case.",
        "Since explanations may not accurately summarize complex systems, test explanations.",
    ],
)
def test_a_things_capability_is_a_known_miss(sentence):
    """The three catalog sentences 80 ruled out of scope. Strict, so a fix
    that clears them is noticed and the named miss retired."""
    assert classify(sentence) == NONE
