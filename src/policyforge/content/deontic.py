"""How strongly a document states its requirements, and whether that
strength survived the trip from the control that justifies it.

An assessor does not read `must` and `should` as variations in tone. One is
a commitment the organization can be held to and the other is an intention,
and a Standard full of the second is not auditable. The source controls are
written in obligation language — 800-53 says an organization *shall* — so a
generated Standard that renders a cited requirement as "teams should
consider recertifying" has quietly downgraded a control while still
displaying its citation. The document looks correct, cites correctly, and
promises less than the framework it claims to satisfy.

That is the finding this module exists for, and it is narrower than
counting modal verbs. A `should` on its own is often right: a Policy states
principles, a Standard's commentary can advise, and flagging every one of
them would bury the case that matters under noise nobody reads — the same
trap `zardoz/answer.py` keeps warning about with its integrity checks.
What is reported is a sentence that carries a framework citation and does
not bind.

Deterministic on purpose. Every grader in this project is a substring, a
pattern or a rule, for the reason `evals/runner.py` gives: a checker that
needed a model would have the failure mode it exists to detect.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .tags import SOURCE_TAG_RE

#: A sentence binds the organization to something.
OBLIGATION = "obligation"
#: A sentence binds the organization *not* to something. Also binding.
PROHIBITION = "prohibition"
#: Advice. Real content, no commitment.
RECOMMENDATION = "recommendation"
#: Explicit latitude — the reader may choose.
PERMISSION = "permission"
#: A statement of fact, a heading, a definition.
NONE = "none"

#: Binding modalities. An assessor can ask for evidence against these and
#: nothing else.
BINDING = frozenset({OBLIGATION, PROHIBITION})

#: Framework citations, the same shape `edit/apply.py` protects when it
#: rewrites a page. A sentence carrying one is claiming to implement a
#: control, which is what makes its modality checkable at all. Decided in
#: `content/tags.py`, once, for every reader.
_CITATION_RE = SOURCE_TAG_RE

#: Ordered strongest first, because the longer forms contain the shorter
#: ones: "must not" must be tested before "must", or every prohibition in
#: the corpus reads as an obligation to do the thing it forbids.
_MODALITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        PROHIBITION,
        re.compile(
            r"\b(?:must not|shall not|may not|must never|shall never|"
            r"is prohibited|are prohibited|is forbidden|are forbidden)\b",
            re.IGNORECASE,
        ),
    ),
    (
        OBLIGATION,
        re.compile(
            r"\b(?:must|shall|is required to|are required to|is obligated to|"
            r"are obligated to|will be required to)\b",
            re.IGNORECASE,
        ),
    ),
    (
        RECOMMENDATION,
        re.compile(
            r"\b(?:should|ought to|is recommended|are recommended|"
            r"is encouraged|are encouraged|is advised|are advised)\b",
            re.IGNORECASE,
        ),
    ),
    (
        PERMISSION,
        re.compile(
            r"\b(?:may|can elect to|is permitted|are permitted|is allowed|"
            r"are allowed|at the discretion of|optional)\b",
            re.IGNORECASE,
        ),
    ),
)

#: Markdown emphasis, stripped before matching for the reason
#: `zardoz/answer.py` strips it: a generated Standard writes "**must**",
#: and a checker that cannot see through the asterisks reports the one
#: sentence that got it right.
_MARKUP_RE = re.compile(r"\*\*|__|\*|`")


def _sentences(text: str) -> list[tuple[int, str]]:
    """`(offset, piece)` for each sentence, using the project's boundary rule.

    **This split every citation containing a dot until 2026-09-21.** The
    rule was `[^.!?]+(?:[.!?]+|$)`, which breaks at every full stop —
    including the ones *inside* an identifier. `[HIPAA Security Rule
    164.308(a)(3)(i)]` became three fragments, none of which is a
    citation, so `cited` was False on every statement and
    `weakened_citations` reported nothing.

    **The direction of that failure is silence.** A document whose
    requirements were all correctly cited and all written as "should
    consider" read as clean. Counted over the shipped catalogs, 324 of
    1,844 identifiers contain a dot and four catalogs are **entirely**
    dotted — `cfr-171-information-blocking`, `hipaa-security-rule`,
    `cfr-42-part-2-sud-records` and `nist-800-171-r3`. The check worked
    for 800-53, FedRAMP and ARC-AMPE, and not for the framework this
    product exists to serve.

    `entail/base.py` replaced the same pattern for the same reason and
    its docstring carries the argument, including why a rule that
    special-cased digit-dot-digit would leave `45 C.F.R. 164.312`
    broken. Imported rather than restated: two copies of one rule, one of
    them fixed, is how this defect existed at all. Found by
    policyforge-b5, who wrote that fix and then found its sibling still
    carrying the bug.

    Returns offsets because a `Statement` carries the line it came from
    and `entail`'s `_segments` does not need them.
    """
    from policyforge.entail.base import _BOUNDARY_RE, _ends_an_initial, _starts_with_a_capital

    pieces: list[tuple[int, str]] = []
    start = 0
    for match in _BOUNDARY_RE.finditer(text):
        if _ends_an_initial(text, match.start()) and _starts_with_a_capital(text, match.end()):
            continue
        pieces.append((start, text[start : match.end()]))
        start = match.end()
    pieces.append((start, text[start:]))
    return [(offset, piece) for offset, piece in pieces if piece.strip()]


@dataclass(frozen=True)
class Statement:
    """One sentence, and what it commits the organization to."""

    line: int
    text: str
    modality: str
    cited: bool
    #: The citation tags this sentence carries, including one trailing it on
    #: the next line. Recorded so a check can ask WHICH framework a sentence
    #: cites, not only whether it cites one (#300).
    citations: tuple[str, ...] = ()

    @property
    def binds(self) -> bool:
        return self.modality in BINDING

    @property
    def cites_the_playbook(self) -> bool:
        """Any of its citations names the NIST AI RMF Playbook."""
        return any(_is_playbook(part) for tag in self.citations for part in _parts(tag))

    @property
    def cites_only_the_playbook(self) -> bool:
        """It cites the Playbook, and nothing that states an obligation.

        The unit both Playbook rules use (80, on #300). A sentence that also
        cites a binding source carries that source's obligation, so the
        binding source's strength rule governs it, and binding is correct.

        **The AI RMF Core does not count as binding** (#341, 80's ruling). It
        states outcomes, so a Playbook sentence that also cites the Core is
        still NIST's suggestion and still read by the gate. The non-binding
        set is `crosswalk.overlay.NON_BINDING_FRAMEWORKS`, not a list here.
        The name is kept because every caller asks the same question it
        always did: is this sentence governed by the Playbook rules?
        """
        from policyforge.crosswalk.overlay import NON_BINDING_FRAMEWORKS
        from policyforge.mapping.crosswalk import normalize_framework

        parts = [part for tag in self.citations for part in _attributed_parts(tag)]
        if not parts:
            return False
        frameworks = [normalize_framework(part.framework or "") for part in parts]
        return "nist-ai-rmf-playbook" in frameworks and all(
            f in NON_BINDING_FRAMEWORKS for f in frameworks
        )

    @property
    def weakens_a_citation(self) -> bool:
        """Claims a control and promises less than one.

        A sentence with no citation is not making a claim this can judge,
        and a binding sentence has nothing wrong with it. The overlap is
        the finding.

        **Except a sentence citing only the Playbook**, which is meant not to
        bind: NIST's suggestions are voluntary, so "NIST suggests ..." is the
        correct rendering and must not be reported as a weakened requirement
        (#300). Without this, the correct form warned and the wrong form,
        "must ...", passed.
        """
        if self.cites_only_the_playbook:
            return False
        return self.cited and not self.binds


#: How a Playbook citation begins, as the catalog's framework name is written
#: into tags: `[NIST AI RMF Playbook Govern 1.1 Action 1]`.
_PLAYBOOK = "NIST AI RMF Playbook "


#: The Playbook's framework name as written into tags, without the space.
_PLAYBOOK_NAME = _PLAYBOOK.strip()


def _parts(tag: str) -> list[str]:
    """One tag's references, a Playbook shorthand part written out in full (#333).

    Split by `content/tags.tag_parts`, the one function `satisfies` also
    uses, against the one list of framework names both read
    (`tags.known_framework_names`, every catalog on disk). A part naming
    another framework -- `NIST 800-53 AC-2`, or an abbreviation that resolves
    to exactly one known catalog, `HIPAA 164.308(a)(1)` -- is that framework's
    and not inherited. A part naming none inherits the part before it (#333).

    **An inherited Playbook part is the Playbook's whether or not its id
    resolves** (80's ruling on #340). #337 counted it only if it resolved, so
    an invented `Govern 9.9 Action 1` left the sentence mixed, and the gate
    never read it: adding one bogus id turned an ERROR into a strength
    warning (1d). Now the sentence stays Playbook-only, and `check` reports
    the unresolvable part as its own ERROR (`unresolved_playbook_parts`).
    """
    out: list[str] = []
    for part in _attributed_parts(tag):
        out.append(_PLAYBOOK + part.rest if part.framework == _PLAYBOOK_NAME else part.citation)
    return out


def _attributed_parts(tag: str):
    """`tag_parts` against every known framework name plus the Playbook's,
    with an abbreviation that names exactly one known catalog kept as its
    own framework, as `satisfies` does."""
    from policyforge.mapping.crosswalk import normalize_framework
    from policyforge.topics.satisfies import resolve_framework

    from .tags import known_framework_names, tag_parts

    names = {_PLAYBOOK_NAME, *known_framework_names()}
    keys = {normalize_framework(n): () for n in names}
    return tag_parts(tag, names, lambda word: bool(resolve_framework(word, keys)))


def unresolved_playbook_parts(text: str) -> list[tuple[int, str]]:
    """(line, citation) for each shorthand part that inherits the Playbook
    and names no Playbook subcategory or action (#340, 80's ruling (a)).

    An invented citation in a compliance document is an error on its own
    terms, whatever else the sentence says: `[NIST AI RMF Playbook Govern 1.1
    Action 1 | Govern 9.9 Action 1]` names an action NIST never published.
    **Inherited parts only**, as ruled: a part that writes the Playbook's
    name in full and still fails to resolve is reported by `satisfies` as an
    unknown citation, not here.
    """
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for tag in _CITATION_RE.findall(line):
            for part in _attributed_parts(tag):
                if (
                    part.framework == _PLAYBOOK_NAME
                    and part.inherited
                    and part.rest.lower() not in _playbook_ids()
                ):
                    found.append((number, part.citation))
    return found


def _is_playbook(reference: str) -> bool:
    return reference.startswith(_PLAYBOOK)


#: A sentence framed as NIST's: its subject is NIST or the Playbook. Matched
#: at the start of the sentence, after list markers and emphasis.
_NIST_SUBJECT = re.compile(
    r"^(?:NIST(?:'s)?(?:\s+AI\s+RMF)?(?:\s+Playbook)?"
    r"|The\s+(?:NIST\s+)?(?:AI\s+RMF\s+)?Playbook)\s+(?:also\s+|further\s+)?(\w+)",
    re.IGNORECASE,
)

#: With NIST as subject, the verbs that say NIST obliges. Closed on purpose:
#: it names the one claim the ruling forbids, "NIST requires ...".
_NIST_OBLIGES = frozenset({"requires", "mandates", "obliges", "obligates", "directs"})

_LEADING_MARKER = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+)+")

#: The only openers a Playbook sentence may put before its NIST/Playbook
#: subject (#319, 80's corrected ruling). **A closed list of SHAPES, not a
#: free-text phrase checked for commitments**: the first ruling allowed any
#: prepositional phrase without a binding verb, and "For Govern 1.4 the
#: organization will adopt these, NIST suggests ..." passed, because
#: `classify` does not count will, commits or is responsible as binding. That
#: was the default-allow shape #309 rejected, one clause over.
#:
#: **The bound, stated:** at most ONE opener, exactly one of the four shapes
#: below, ending at its comma. `<SUB>` must be a Core subcategory id in the
#: shipped `nist-ai-rmf` catalog (checked in `_opener_end`, so the id slot
#: cannot carry text), and `<N>` is digits. Case and whitespace are free.
#: Anything else before the subject fails: two stacked openers, a comma
#: inside one, a missing comma, and harmless openers not listed here, such as
#: "In practice, NIST suggests ...". Those are false alarms on purpose, loud,
#: and fixed by a reword, which is the safe direction.
_SUB = r"(?P<sub>[A-Za-z]+\s+\d+\.\d+)"
_OPENERS = tuple(
    re.compile(shape, re.IGNORECASE)
    for shape in (
        rf"For\s+{_SUB}\s*,\s*",
        rf"Among\s+the\s+\d+\s+actions\s+(?:NIST\s+suggests|the\s+Playbook\s+lists)\s+for\s+{_SUB}\s*,\s*",
        r"Across\s+(?:these|the\s+\d+)\s+actions\s*,\s*",
        rf"Of\s+the\s+\d+\s+actions\s+for\s+{_SUB}\s*,\s*",
    )
)


def _core_subcategories() -> frozenset[str]:
    """The shipped AI RMF Core's subcategory ids, lower-cased (#319).

    Read once from the bundled catalog, the same one `etl-ai-rmf` pins. An
    installation with no bundled catalogs raises here rather than answering
    "none": an empty set would pass the id-free opener and refuse the rest,
    which is a gate that half works.
    """
    global _SUBCATEGORIES
    if _SUBCATEGORIES is None:
        import json

        from policyforge.scaffold import bundled_root

        rows = json.loads(
            bundled_root()
            .joinpath("frameworks", "nist-ai-rmf", "controls.json")
            .read_text(encoding="utf-8")
        )
        _SUBCATEGORIES = frozenset(
            " ".join(e["enhancement_id"].split()).lower()
            for row in rows
            for e in row.get("enhancements") or []
        )
    return _SUBCATEGORIES


_SUBCATEGORIES: frozenset[str] | None = None


def _opener_end(plain: str) -> int:
    """Where the subject may start: after one allowed opener, else 0."""
    for shape in _OPENERS:
        match = shape.match(plain)
        if not match:
            continue
        sub = match.groupdict().get("sub")
        if sub is not None and " ".join(sub.split()).lower() not in _core_subcategories():
            return 0
        return match.end()
    return 0


#: The shortest run quoted from a cited action that can carry a binding word
#: past the check (#320, 80's ruling). **The bound, stated:** at least this
#: many consecutive words, compared case-insensitively on whitespace-split
#: tokens (so punctuation is part of a word, and "preserved," is not
#: "preserved"), occurring verbatim in the text of a Playbook action the
#: SAME sentence cites, looked up in the shipped catalog. A binding word
#: outside every such run still binds. A paraphrase does not qualify, so a
#: model gets no licence to write its own "must".
#:
#: **The second bound, stated (80's ruling (b) on #325):** a run's FIRST word
#: is never exempted, so a binding word is excused only when at least one
#: word of the same verbatim run comes before it. The first word still counts
#: toward the six. A run starting AT "must" let the writer supply the
#: subject outright: "NIST suggests that the organization must be preserved
#: for fulsome understanding ..." quotes Action 4's words and was passing
#: (1d's finding).
#:
#: **The limit, stated (1d and 9b measured it on #325; 80 ruled it stays a
#: limit, not a second count):** a preceding word keeps the modal inside
#: NIST's clause but does NOT guarantee NIST's subject. When that word is a
#: relative pronoun, the writer can still supply its antecedent, and these
#: pass: "NIST suggests keeping the organization's own records that must be
#: preserved for fulsome understanding or execution", and "... the
#: organization that must be preserved ...". A second word count would only
#: move the smuggle one word right. The exposure is instead pinned by
#: `test_playbook_quoted_must`: the shipped Playbook actions that carry a
#: binding word at all -- today Govern 1.7 Action 4 (must), Measure 2.9
#: Action 6 and Measure 3.2 Action 1 (may not) -- and a catalog that adds one
#: fails that test, so the limit is revisited then.
QUOTE_MIN_WORDS = 6

_PLAYBOOK_ACTIONS: dict[str, list[str]] | None = None
_PLAYBOOK_IDS: frozenset[str] | None = None


def _playbook_ids() -> frozenset[str]:
    """Every id the shipped Playbook catalog holds, lower-cased: its
    subcategories (`govern 1.1`) and their actions (`govern 1.1 action 2`).
    What an inherited shorthand part must resolve to (#333)."""
    global _PLAYBOOK_IDS
    if _PLAYBOOK_IDS is None:
        import json

        from policyforge.scaffold import bundled_root

        rows = json.loads(
            bundled_root()
            .joinpath("frameworks", "nist-ai-rmf-playbook", "controls.json")
            .read_text(encoding="utf-8")
        )
        _PLAYBOOK_IDS = frozenset(
            " ".join(i.split()).lower()
            for row in rows
            for i in [
                row["control_id"],
                *(e["enhancement_id"] for e in row.get("enhancements") or []),
            ]
        )
    return _PLAYBOOK_IDS


def _playbook_actions() -> dict[str, list[str]]:
    """Each shipped Playbook action's text as lower-cased tokens, by id."""
    global _PLAYBOOK_ACTIONS
    if _PLAYBOOK_ACTIONS is None:
        import json

        from policyforge.scaffold import bundled_root

        rows = json.loads(
            bundled_root()
            .joinpath("frameworks", "nist-ai-rmf-playbook", "controls.json")
            .read_text(encoding="utf-8")
        )
        _PLAYBOOK_ACTIONS = {
            " ".join(e["enhancement_id"].split()).lower(): (e.get("description") or "")
            .lower()
            .split()
            for row in rows
            for e in row.get("enhancements") or []
        }
    return _PLAYBOOK_ACTIONS


def _cited_actions(citations) -> list[list[str]]:
    """The token lists of the Playbook actions these citation tags name."""
    actions = _playbook_actions()
    cited = []
    for tag in citations:
        for part in _parts(tag):
            if _is_playbook(part):
                key = " ".join(part[len(_PLAYBOOK) :].split()).lower()
                if key in actions:
                    cited.append(actions[key])
    return cited


def _unquoted(plain: str, quoted_from: list[list[str]]) -> str:
    """`plain` with every run of QUOTE_MIN_WORDS+ words found verbatim in
    one of `quoted_from` blanked, so `classify` sees only the rest."""
    tokens = plain.split()
    lowered = [t.lower() for t in tokens]
    covered = [False] * len(tokens)
    for action in quoted_from:
        for i in range(len(lowered)):
            for j in range(len(action)):
                length = 0
                while (
                    i + length < len(lowered)
                    and j + length < len(action)
                    and lowered[i + length] == action[j + length]
                ):
                    length += 1
                if length >= QUOTE_MIN_WORDS:
                    # From i + 1: the run's first word is never excused.
                    for k in range(i + 1, i + length):
                        covered[k] = True
    return " ".join("_" if c else t for t, c in zip(tokens, covered, strict=True))


#: Where a Playbook sentence can open a second clause (#323, 80's ruling (B)):
#: `, and` / `, but` / `, so`, a semicolon (optionally followed by one of those
#: words) or an em dash. Closed.
_JOINER = r"(?:,\s+(?:and|but|so)\s+|;\s+(?:(?:and|but|so)\s+)?|\s*\u2014\s*(?:(?:and|but|so)\s+)?)"

#: Subjects that commit the organization when they open a clause after a
#: joiner. Closed and case-insensitive. **"management" is deliberately NOT
#: here**: in b5's 66 real glm sentences, "..., and management resources" is
#: a list item, and it was the only false alarm this list produced.
GENERIC_ACTORS = (
    "the organization",
    "the organisation",
    "we",
    "our",
    "us",
    "staff",
    "employees",
    "personnel",
    "the team",
    "the company",
)


def _alternatives(actors) -> str:
    words = [a for a in {" ".join(str(a).split()) for a in actors} if a]
    return "|".join(
        r"\s+".join(re.escape(w) for w in a.split()) for a in sorted(words, key=len, reverse=True)
    )


def _actor_pattern(org_actors=()) -> re.Pattern[str]:
    """Joiner, then an actor, then no further word character.

    **Generic actors match in any case; the organization's own do NOT**
    (1d on #329). Config names are proper nouns, and one-word team or vendor
    names are also ordinary words: with teams "Security", "Compliance", "IT"
    and vendors "Legal", "Privacy", case-insensitive matching fired on 4 of
    the 459 shipped Playbook actions and 3 of b5's 66 sentences, every one an
    Oxford-comma list item ("..., and legal review"). Stated limit: a
    declared name written in another case ("ACME" for "Acme") is not caught.

    A negative lookahead for a word character, rather than a word boundary,
    follows the actor, so a name that ends in punctuation, "Foo (EU)", can
    still match (1d on #329).
    """
    generic = _alternatives(GENERIC_ACTORS)
    declared = _alternatives(org_actors)
    actor = f"(?i:{generic})" + (f"|{declared}" if declared else "")
    return re.compile(rf"(?i:{_JOINER})(?:{actor})(?!\w)")


def _second_clause_actor(plain: str, org_actors=()) -> str | None:
    """The actor opening a clause after a joiner, if it is the organization's.

    **Why not "anything after a joiner must be NIST"** (80's first ruling on
    #323, withdrawn): glm writes LISTS -- "...; establishing ...", "...; and
    determining ...", "..., and stakeholder engagement plans" -- and that rule
    refused 65 of b5's 66 real sentences. What must not appear is the
    organization committing, and the organization's actors are knowable: the
    generic ones above, plus its own name, teams and vendors from config
    (`org_actors`, derived by `org.context.org_actors`, never typed here).

    **The bound, stated:** only the joiners in `_JOINER`, and only an actor
    that is generic or declared. An actor that is neither -- an unlisted
    subsidiary, a person's name -- is NOT caught, and nor is a clause joined
    some other way (a bare comma, "which", "while").
    """
    match = _actor_pattern(org_actors).search(_CITATION_RE.sub("", plain))
    return match.group(0) if match else None


def framed_as_nists(sentence: str, citations=(), org_actors=()) -> bool:
    """Whether a sentence speaks as NIST describing or suggesting (#300).

    **An allow-list on the subject, not a deny-list of obligation verbs**
    (80's ruling, refined after 1d's review). Every round of a verb list
    found another spelling -- "will", "is responsible for", the imperative,
    "ensures", "NIST requires" -- because a deny-list chases paraphrase. So
    the sentence must have NIST or the Playbook as its subject ("NIST
    suggests ...", "The Playbook groups ..."), and anything else fails by
    default: an organization as subject in any wording, an imperative, any
    other subject. Within NIST-as-subject, the verbs that say NIST obliges
    are refused, and so is a sentence that binds anyway ("NIST suggests that
    the organization must ..."), since a Playbook sentence never binds.

    The subject may follow one opener from `_OPENERS` (#319), such as "Among
    the 7 actions NIST suggests for Govern 1.4, NIST suggests ...". The
    binding check below still reads the WHOLE sentence, opener included.

    **Except NIST's own words (#320).** With `citations` given, a binding
    word inside a run of `QUOTE_MIN_WORDS`+ words quoted verbatim from a
    Playbook action those citations name is NIST's text, not the
    organization's obligation, and is not counted. Without citations
    nothing is exempt.

    **And one main clause, NIST's (#323).** A clause after a joiner whose
    subject is the organization -- generic, or declared in config as
    `org_actors` -- fails, whatever its verb: "NIST suggests reviewing the
    inventory, and Acme will adopt it". See `_second_clause_actor`.
    """
    plain = _LEADING_MARKER.sub("", _MARKUP_RE.sub("", sentence).strip())
    match = _NIST_SUBJECT.match(plain[_opener_end(plain) :])
    if not match or match.group(1).lower() in _NIST_OBLIGES:
        return False
    if _second_clause_actor(plain, org_actors):
        return False
    if classify(plain) not in BINDING:
        return True
    return classify(_unquoted(plain, _cited_actions(citations))) not in BINDING


def playbook_tagged_headings(text: str) -> list[tuple[int, str]]:
    """Headings that carry a Playbook citation, as (line, heading) (#309).

    **A heading may not cite the Playbook at all**, even merged with a
    binding source (80's ruling on #309). A heading tag scopes every step
    beneath it, so it turns a suggestion into an instruction by position,
    whatever the heading says. `analyze` blanks headings on purpose, so the
    sentence check never saw these: measured on a generated Procedure, all
    9 of its 9 Playbook tags sat on headings, and the gate reported none.
    """
    found = []
    lines = text.split("\n")
    kinds = _line_kinds(lines)
    for number, line in enumerate(lines, start=1):
        # Headings as `analyze` classifies them (9b on #350): a setext
        # heading's text line, blanked out of sentence analysis, is still
        # a heading here, so an obligation underlined with `---` is caught
        # by this rule rather than by neither.
        if kinds[number - 1] not in _HEADING_TEXT:
            continue
        tags = _CITATION_RE.findall(line)
        if any(_is_playbook(part) for tag in tags for part in _parts(tag)):
            found.append((number, line.strip()))
    return found


def playbook_obligations(text: str, org_actors=()) -> list[Statement]:
    """Sentences citing only the NIST AI RMF Playbook, not framed as NIST's.

    The Playbook is voluntary: NIST's suggested actions, which it
    deliberately kept out of the AI RMF Core. A sentence citing it may say
    NIST suggests or describes; it may never present an action as anyone's
    obligation -- "Acme Health will ... [Playbook ...]" does so as surely as
    "NIST requires ..." (80's rulings on #300 and #309). An obligation the
    organization adopts goes in its own sentence, without the Playbook tag.

    **Only sentences whose every citation is a Playbook tag.** A merged tag
    that also names a binding source -- `[NIST 800-53 AC-2 | NIST AI RMF
    Playbook ...]` -- carries that source's obligation, and the requirement
    strength rule governs it instead.

    **A colon list is judged item by item** (80's ruling (a) on #354). The
    lead-in and its items are one statement for citation crediting (#351),
    but that joining never let one item's citation vouch for a sibling: in
    `Acme Health must:` / `- maintain a register [Playbook]` / `- review
    access [AC-2]` the joined statement cites both, reads as mixed, and the
    Playbook item escaped. So each SENTENCE of each item is judged against its
    own citations (plus any the lead-in or the list itself carries) and
    reported at its line: the item's first sentence as "lead-in + sentence",
    unless it is NIST's speech on its own, and any later sentence alone, as
    in a plain item (1d on #356: one item's 800-53 sentence vouched for its
    Playbook sentence). Under an organization's lead-in this is the verdict
    the same item gets as a plain item, and the tests take that verdict as
    their oracle. A lead-in with NIST as its subject (`NIST suggests:`)
    frames each item's first sentence as NIST's.
    """
    statements = analyze(text)
    units, covered = _colon_units(text, statements, org_actors)
    judged = [s for s in statements if id(s) not in covered] + units
    return sorted(
        (
            s
            for s in judged
            if s.cites_only_the_playbook and not framed_as_nists(s.text, s.citations, org_actors)
        ),
        key=lambda s: s.line,
    )


def _colon_units(
    text: str, statements: list[Statement], org_actors=()
) -> tuple[list[Statement], set[int]]:
    """Each colon list's items as "lead-in + item" statements, and the ids of
    the statements those lists cover (#354)."""
    lines = text.split("\n")
    heading = [kind is not None for kind in _line_kinds(lines)]
    units: list[Statement] = []
    covered: set[int] = set()
    for colon in _walk_lists(lines, heading)[1]:
        if colon.lead < 0 or not colon.items:
            continue
        lead_line, end_line = colon.lead + 1, colon.end + 1
        before = [s for s in statements if s.line <= lead_line]
        if not before:
            continue
        owner = before[-1]
        owned = [owner] + [s for s in statements if lead_line < s.line <= end_line]
        covered.update(id(s) for s in owned)

        def joined(first: int, last: int) -> str:
            return " ".join(" ".join(lines[first : last + 1]).split())

        first_item = joined(colon.items[0][0], colon.items[0][0])
        at = owner.text.find(first_item)
        lead = owner.text[:at].strip() if at > 0 else joined(colon.lead, colon.lead)
        shared = tuple(_CITATION_RE.findall(lead)) + tuple(
            tag for index in colon.trailing for tag in _CITATION_RE.findall(lines[index])
        )
        for first, last in colon.items:
            # Each SENTENCE of the item, split by `analyze` itself so that its
            # boundaries and trailing-citation credit are a plain item's: one
            # item's 800-53 sentence must not vouch for its Playbook sentence
            # any more than a sibling item may (1d on #356). The lead-in runs
            # on into the item's FIRST sentence only ("Acme Health must: keep
            # a register"); a later sentence stands alone, as it does in a
            # plain item, so `NIST suggests ...` there is still NIST's. So does
            # a first sentence that is NIST's speech on its own: it has its own
            # subject, and the lead-in does not run into it.
            body = "\n".join([_LEADING_MARKER.sub("", lines[first]), *lines[first + 1 : last + 1]])
            for position, sentence in enumerate(analyze(body)):
                own = shared + sentence.citations
                alone = position > 0 or framed_as_nists(sentence.text, own, org_actors)
                unit = sentence.text if alone else f"{lead} {sentence.text}"
                units.append(
                    Statement(
                        line=first + sentence.line,
                        text=unit,
                        modality=classify(unit),
                        cited=bool(shared + sentence.citations),
                        citations=shared + sentence.citations,
                    )
                )
    return units, covered


def classify(sentence: str) -> str:
    """The strongest modality the sentence carries.

    Strongest rather than first, because real requirement prose nests
    latitude inside obligation: "records must be retained in written form
    (which may be electronic)" is an obligation with a permitted detail,
    not a permission. Reading it as the latter would report the firmest
    sentence in the document as its weakest.
    """
    visible = _MARKUP_RE.sub("", sentence)
    for modality, pattern in _MODALITY_PATTERNS:
        if pattern.search(visible):
            return modality
    return NONE


#: Markdown headings are structure, not statements: "### 4.1 Media Protection"
#: commits the organization to nothing, and a heading ending in a numbered
#: section makes the sentence splitter cut in the middle of one. Which lines
#: are headings is decided once, by `_line_kinds` below.


def analyze(text: str) -> list[Statement]:
    """Every sentence in `text`, classified, with the line it starts on.

    Headings are blanked rather than deleted so line numbers still point at
    the document a reader has open.

    A citation trailing its sentence on the following line is attached
    backwards. Generated Standards put it there — the requirement ends with
    a full stop and `[NIST MP-1 ...]` sits underneath — so a naive split
    makes the citation the opening of the *next* sentence, which is usually
    a heading and binds nothing. Left alone that reported every correctly
    cited requirement in the corpus as a weakened one, which is precisely
    the kind of false positive that teaches people to ignore the check.

    **A heading ends a sentence, and nothing is credited across one (#349).**
    Headings used to be blanked and then read straight through, so a
    sentence ending `... [Playbook Map 1.6 Action 8].` ran across `## 3.` and
    `### 3.1` into `- **CAT-01:** ... shall ensure ... [NIST AI RMF Map 2]`,
    and the gate read CAT-01's obligation and citation as NIST's suggestion
    (18 of 2,501 statements across 33 generated Standards). Sentences are
    now split within each run of lines between headings, ATX or setext.
    """
    text, blocks = _heading_blocks(text)

    statements: list[Statement] = []
    for block_offset, block in blocks:
        _analyze_block(text, block_offset, block, statements)
    return statements


#: An ATX heading, CommonMark's shapes: up to three spaces, 1-6 `#`, then a
#: space or the end of the line (so a bare `##` is an empty heading), inside
#: any number of blockquote markers (`> ## heading`).
_ATX_RE = re.compile(r"^[ \t]{0,3}(?:>[ \t]?)*[ \t]{0,3}#{1,6}(?:[ \t]|$)")
#: A thematic break, CommonMark's shape: up to three spaces, then three or
#: more of ONE of `-`, `*`, `_`, spaces allowed between (1d on #350: `***`,
#: `___`, `- - -` and `* * *` did not end a block).
_THEMATIC_BREAK_RE = re.compile(r"^[ \t]{0,3}(?:(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})$")
#: A setext underline: any run of `=`, or two or more `-`, and nothing else.
#: It is an underline only under a paragraph line (see `_line_kinds`).
#: **A lone `-` is excluded by choice, not by CommonMark** (1d on #350:
#: markdown-it reads `text\n-` as a setext h2). Excluding it keeps the line
#: above in sentence analysis, where every gate reads it; including it would
#: blank that line on a single stray character, the destructive direction.
_SETEXT_UNDERLINE_RE = re.compile(r"^[ \t]{0,3}(?:=+|-{2,})[ \t]*$")
#: A line that cannot be setext heading text: a list item or a table row.
_LIST_OR_TABLE_RE = re.compile(r"^[ \t]*(?:[-*+][ \t]|\d+[.)][ \t]|\|)")


#: Line kinds `_line_kinds` returns; the first two are heading TEXT.
_ATX, _SETEXT, _UNDERLINE, _BREAK = "atx", "setext", "underline", "break"
_HEADING_TEXT = (_ATX, _SETEXT)


def _line_kinds(lines: list[str]) -> list[str | None]:
    """Each line's block role, or None for ordinary text.

    **The one classification of headings**, read by `analyze` (a boundary)
    and by `playbook_tagged_headings` (a tagged heading). Two readings of
    one document disagreeing is how an obligation underlined with `---` left
    sentence analysis without becoming a heading anywhere (9b on #350).
    """
    kinds: list[str | None] = [_ATX if _ATX_RE.match(line) else None for line in lines]
    for index, line in enumerate(lines):
        if kinds[index] is not None:
            continue
        above = index - 1
        paragraph_above = (
            above >= 0
            and lines[above].strip()
            and kinds[above] is None
            and not _LIST_OR_TABLE_RE.match(lines[above])
            and not _THEMATIC_BREAK_RE.match(lines[above])
        )
        if paragraph_above and _SETEXT_UNDERLINE_RE.match(line):
            kinds[index] = _UNDERLINE
            # The whole paragraph above is the heading, as in CommonMark,
            # not only its last line (1d on #350): a tag on its first line
            # must reach the heading check too.
            while (
                above >= 0
                and lines[above].strip()
                and kinds[above] is None
                and not _LIST_OR_TABLE_RE.match(lines[above])
                and not _THEMATIC_BREAK_RE.match(lines[above])
            ):
                kinds[above] = _SETEXT
                above -= 1
        elif _THEMATIC_BREAK_RE.match(line):
            kinds[index] = _BREAK
    return kinds


def _heading_blocks(text: str) -> tuple[str, list[tuple[int, str]]]:
    """`text` with every heading line blanked in place (so line numbers hold),
    and the runs of lines between headings as `(offset, block)`.

    Block boundaries, in CommonMark's precedence:
    - an ATX heading (`## x`, a bare `##`, or `> ## x`);
    - a setext underline under a paragraph line: the underline and the
      line above are both heading. `---` there is setext, not a break;
    - a thematic break anywhere else: it ends the block, and the line
      above it stays text.

    **Named, not handled:** a setext heading inside a blockquote, and
    indented code blocks, whose contents are still read as prose.
    """
    lines = text.split("\n")
    heading = [kind is not None for kind in _line_kinds(lines)]
    blanked = [" " * len(line) if heading[i] else line for i, line in enumerate(lines)]
    text = "\n".join(blanked)

    list_start = _list_starts(lines, heading)

    blocks: list[tuple[int, str]] = []
    offset, start = 0, None
    for index, line in enumerate(blanked):
        if heading[index]:
            if start is not None:
                blocks.append((start, text[start : offset - 1]))
                start = None
        elif start is None:
            start = offset
        elif list_start[index]:
            blocks.append((start, text[start : offset - 1]))
            start = offset
        offset += len(line) + 1
    if start is not None:
        blocks.append((start, text[start:]))
    return text, blocks


#: A list item's opening line: `-`, `*` or `+`, or `1.` / `1)`, then a space.
_LIST_ITEM_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\S")
#: An ordered item's number, which decides whether it may interrupt a paragraph.
_ORDERED_RE = re.compile(r"^[ \t]*(\d+)[.)][ \t]")


def _ends_with_colon(line: str) -> bool:
    """Whether `line`, less its trailing citations and emphasis, ends in `:`."""
    return _CITATION_RE.sub("", line).rstrip(" \t*_`").endswith(":")


def _list_starts(lines: list[str], heading: list[bool]) -> list[bool]:
    """True for each line where a list gives a new block (#351).

    **A list item starts a block, as in CommonMark** (80's ruling): the
    sentence splitter ends a sentence only before a capital, a quote, `[` or
    `(`, so without this `The owner must review logs.` ran on into `- item
    ... [AU-6]` and borrowed its citation, blank line or not, and so did one
    item into the next. As in CommonMark, too, an ordered marker other than
    `1` directly under paragraph text does NOT start a list: `no fewer than`
    / `90) days` is one sentence wrapped across lines. The tests take their
    expected answer for each shape from markdown-it, not from this rule.

    **Except a colon lead-in's list.** `The owner must identify:` is carried
    by its items, so the lead-in and every item of its list stay one block.
    The lead-in is the last line before the list's first item that is not
    blank and not only citations.

    A list ends at a heading, or at an unindented line of prose after a
    blank line; that line starts a block of its own, so a paragraph after a
    colon's list is not read as one of its items. An indented line, or one
    straight after an item with no blank line (CommonMark's lazy
    continuation), stays with the item. **A line of only citations never
    ends a list or starts a block**, blank line or not: it is the trailing
    citation `analyze` credits backwards, and the generated Standards put a
    colon lead-in's citation there, under its list (a draft of this rule
    orphaned one, measured over the 33 Standards).
    """
    return _walk_lists(lines, heading)[0]


@dataclass
class _ColonList:
    """A colon lead-in and its list, as line indexes (0-based) (#354)."""

    lead: int
    #: [first, last] line of each item, continuation lines included.
    items: list[list[int]] = field(default_factory=list)
    #: Citation-only lines under the list after a blank line: the list's own.
    trailing: list[int] = field(default_factory=list)

    @property
    def end(self) -> int:
        return max([self.lead, *(last for _, last in self.items), *self.trailing])


def _walk_lists(lines: list[str], heading: list[bool]) -> tuple[list[bool], list[_ColonList]]:
    """The ONE reading of lists: where a list gives a new block (`_list_starts`,
    #351) and each colon lead-in's list with its items (`playbook_obligations`,
    #354). Two walkers would disagree about where a list ends, and the gate
    would judge items the block splitter never kept together."""
    starts = [False] * len(lines)
    colon_lists: list[_ColonList] = []
    in_list = colon_list = blank_since = False
    lead = ""
    lead_index = -1
    for index, line in enumerate(lines):
        if heading[index]:
            in_list = colon_list = blank_since = False
            lead, lead_index = "", -1
            continue
        if not line.strip():
            blank_since = True
            continue
        prose = bool(_CITATION_RE.sub("", line).strip())
        ordered = _ORDERED_RE.match(line)
        interrupts = not (
            # CommonMark: only an ordered list starting at 1 may interrupt a
            # paragraph, so `...no fewer than` / `90) days` is one paragraph
            # (1d on #353, confirmed against markdown-it).
            ordered
            and not in_list
            and int(ordered.group(1)) != 1
            and index > 0
            and lines[index - 1].strip()
            and not heading[index - 1]
        )
        if _LIST_ITEM_RE.match(line) and interrupts:
            if not in_list:
                in_list, colon_list = True, _ends_with_colon(lead)
                if colon_list:
                    colon_lists.append(_ColonList(lead=lead_index))
            starts[index] = not colon_list
            if colon_list:
                colon_lists[-1].items.append([index, index])
        elif in_list and blank_since and prose and not line[:1].isspace():
            in_list = colon_list = False
            starts[index] = True
        elif colon_list and colon_lists[-1].items:
            if not prose and blank_since:
                colon_lists[-1].trailing.append(index)
            else:
                colon_lists[-1].items[-1][1] = index  # the item's continuation
        if prose:
            lead, lead_index = line, index
            blank_since = False
    return starts, colon_lists


def _analyze_block(text: str, block_offset: int, block: str, statements: list[Statement]) -> None:
    """The sentences of one run of lines between headings, appended to
    `statements`. A leading citation is credited backwards only to a
    sentence in this same block."""
    first_in_block = len(statements)
    for piece_start, raw in _sentences(block):
        offset = block_offset + piece_start + (len(raw) - len(raw.lstrip()))
        sentence = raw.strip()
        if not sentence:
            continue

        # Peel citations off the front and credit them to the sentence
        # above. The full stop lands *before* the citation, so a split puts
        # it at the head of whatever follows — which is either a heading
        # (binding nothing) or the next requirement (binding for its own
        # reasons, and wrongly absorbing this citation). Both readings lose
        # the link between a control and the sentence that implements it.
        trailing_citation = False
        peeled: list[str] = []
        while True:
            leading = _CITATION_RE.match(sentence)
            if not leading:
                break
            trailing_citation = True
            peeled.append(leading.group(0))
            offset += leading.end()
            sentence = sentence[leading.end() :]
            stripped = sentence.lstrip(" \t\r\n.;:|")
            offset += len(sentence) - len(stripped)
            sentence = stripped

        carried: tuple[str, ...] = ()
        if trailing_citation and len(statements) > first_in_block:
            previous = statements[-1]
            statements[-1] = Statement(
                line=previous.line,
                text=previous.text,
                modality=previous.modality,
                cited=True,
                citations=previous.citations + tuple(peeled),
            )
        elif trailing_citation:
            # Nothing above it in this block: a citation opening a block
            # belongs to the sentence it opens, never to one across a heading.
            carried = tuple(peeled)

        if not sentence:
            continue

        inline = carried + tuple(_CITATION_RE.findall(sentence))
        statements.append(
            Statement(
                line=text.count("\n", 0, offset) + 1,
                text=" ".join(sentence.split()),
                modality=classify(sentence),
                cited=bool(inline),
                citations=inline,
            )
        )


def weakened_citations(text: str) -> list[Statement]:
    """Sentences that cite a control and do not bind."""
    return [s for s in analyze(text) if s.weakens_a_citation]


def binding_share(text: str) -> tuple[int, int]:
    """(binding sentences, sentences carrying any modality at all).

    The denominator excludes plain declaratives on purpose. A Standard is
    mostly prose — purpose, scope, definitions — and counting that as
    "unbound" would make every document look permissive.
    """
    modal = [s for s in analyze(text) if s.modality != NONE]
    return sum(1 for s in modal if s.binds), len(modal)
