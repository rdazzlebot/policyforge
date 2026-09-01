"""Finding the passages that bear on a question.

Retrieval is a separate milestone from answering on purpose. "Did it find
the right section?" and "did it answer well from that section?" are
different failures with different fixes, and a system that collapses them
into one prompt gives you no way to tell which one you are looking at. Every
function here is pure and offline, so ranking quality can be iterated on
against fixtures rather than against a model whose output moves underneath
you.

**Why keyword scoring rather than embeddings.** The obvious move for a
question-answering tool in 2026 is to embed everything, and for prose about
open-ended subjects it is the right move. Compliance documents are not that.
The highest-signal query terms are exact tokens — `AC-2`, `164.312(a)(1)`,
`MP-6(1)` — where a near-miss is not a near-answer but a different control,
and semantic similarity actively works against you: AC-2 and AC-3 embed
almost identically and mean different things to an assessor. The rest of the
vocabulary is terms of art that appear verbatim in both the question and the
document, because the people asking learned the words from the documents.
BM25 with an exact-identifier boost is not a placeholder for embeddings
here; it is the better tool, and it stays debuggable — every score in this
module can be explained by naming which terms hit.

Where embeddings would earn their place is the paraphrase case: "how often
do we check who has admin?" against a document that only ever says
"privileged access review cadence". That is a real gap, and the honest fix
is a hybrid — this scorer for identifiers and terms of art, embeddings for
the residue — rather than replacing something precise with something fuzzy.

**Chunking at headings** follows from what a citation has to look like. An
answer that says "Access Control Standard § 4.1" can be checked by a human
in ten seconds; one that says "somewhere in the Access Control Standard"
cannot, and a compliance answer nobody can check is not worth much.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from .corpus import Corpus, CorpusDocument

#: Sections longer than this are split on paragraph boundaries. Short
#: sections are never merged with their siblings: merging would widen the
#: citation, and a precise pointer into a small section is the whole reason
#: to chunk at headings in the first place.
MAX_CHUNK_CHARS = 1500

#: How many times a chunk's heading and its document's title are repeated
#: into the bag of terms BM25 scores. Field weighting by repetition rather
#: than a multi-field scorer: one code path to reason about, and the ranking
#: effect is the same. A term in the heading is a strong claim about what
#: the section is *about*; a term in the body may be an aside.
HEADING_WEIGHT = 3
TITLE_WEIGHT = 2

#: Added per control identifier shared by the query and the chunk. Large
#: enough to dominate term scoring, because it is a different kind of
#: evidence: "AC-2" in the question and "AC-2" in the section is not a
#: similarity judgement, it is a match.
CONTROL_ID_BONUS = 8.0

#: Added when the document knows who owns it. Only ever a tiebreak — it
#: cannot lift an irrelevant passage above a relevant one — but where two
#: passages say the same thing, the one somebody is accountable for is the
#: one to quote.
TRUSTED_BONUS = 0.5

#: An optional absolute floor, off by default. Refusing on raw magnitude is
#: tempting and wrong: BM25 scores are not comparable between corpora, so
#: any fixed number means something different at three chunks than at three
#: hundred. A floor tuned on a full document set silently refuses everything
#: in a small one, and the user sees "the documents do not say" about a
#: document that plainly does. Distinctiveness does the filtering instead —
#: see MAX_TERM_SHARE and FULL_COVERAGE — and it is scale-free. Callers who
#: want a magnitude cut can still pass one.
MIN_SCORE = 0.0

#: A passage must match at least one query term that appears in no more than
#: this fraction of the corpus, or match a control identifier outright.
#: Score alone is not enough: asked "what is our vacation policy?", a corpus
#: with no vacation policy still scores every chunk saying "policy" above any
#: plain floor, and answers confidently about the wrong thing.
#:
#: A share of the corpus rather than an IDF number, because IDF's ceiling
#: moves with corpus size — a term in one chunk of two scores 0.69, one of
#: nine scores 1.90, one of five hundred scores 5.81 — so any absolute
#: threshold means something different at each scale, and a 0.7 cut made the
#: gate literally unreachable below three chunks. Normalising against that
#: ceiling fixes the scale problem but not the ordering: it let a term in 3
#: of 5 chunks through while refusing one in 5 of 9, which is backwards.
#:
#: "Appears in more than half the documents" needs no calibration and says
#: what it means: such a term cannot tell you *which* document you want. It
#: agrees with every case measured against a real generated Standard.
MAX_TERM_SHARE = 0.5

#: The other way to clear the specificity bar: a passage that matches this
#: fraction of everything the question asked about is on topic even when
#: every one of those terms is common. Needed because IDF is meaningless in
#: a corpus of three chunks, where a word in all of them looks worthless and
#: is in fact the subject.
FULL_COVERAGE = 0.75

_K1 = 1.5
_B = 0.75

# NIST-style control identifiers (AC-2, MP-6(1)) and CFR-style regulatory
# citations (164.312(a)(1)). Both appear in the inline source tags this
# project's documents carry — `[NIST MP-1 | HIPAA 164.310(d)(1)]` — and in
# the questions people ask about them.
# No trailing word-boundary anchor: these identifiers can end in `)`, and `)` before a
# `]` is not a word boundary, so requiring one silently truncated
# `AC-6(5)` to `AC-6` and `164.308(a)(4)` to `164.308` — turning every
# enhancement into its parent control.
_NIST_ID_RE = re.compile(r"\b([A-Za-z]{2}-\d+(?:\(\d+\))?)")
_CFR_ID_RE = re.compile(r"\b(\d{3}\.\d+(?:\([A-Za-z0-9]+\))*)")

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.+?)\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

#: Function words only. The domain noise in these documents — "shall",
#: "organization", "policy" — is deliberately *not* listed here: those words
#: appear in nearly every chunk, so IDF drives their weight to nothing on
#: its own, and hard-coding them would silently break the one query where
#: they matter ("which documents are policies?").
_STOPWORD_TEXT = """
    a an and are as at be been by do does for from had has have how i if in into is it
    its of on or our that the their them there these they this to was we were what when
    where which who why will with you your
    """
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())


def normalize(token: str) -> str:
    """Fold the plural forms that make a query miss its own document.

    "reviews" in the question and "review" in the standard should meet.
    Only the trailing `s` is stripped, and only where it is unlikely to be
    part of the word — `access`, `status` and `analysis` all end in `s` and
    none of them is a plural, so stripping blindly would turn the most
    common term in the corpus into a token that matches nothing.

    A real stemmer would do better. It would also be a dependency and a
    source of surprises ("policies" -> "polici"), and this covers the case
    that actually shows up.
    """
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _strip_control_ids(text: str) -> str:
    """Blank out identifiers so they cannot be tokenized into fragments.

    Without this, `MP-6` in a question becomes the term `mp`, which matches
    a section citing `MP-1` — and the result claims a match on a control the
    document does not mention. Identifiers are scored by exact equality or
    not at all, which is the only reading of them that is ever correct.
    """
    return _CFR_ID_RE.sub(" ", _NIST_ID_RE.sub(" ", text))


#: Acronyms expanded to their spelled-out terms, and kept alongside them.
#: This is the one place a fixed vocabulary earns its keep: a question asks
#: "do admins need MFA?" while the Standard says "multi-factor
#: authentication", and no amount of exact matching bridges that. These
#: expansions are safe to hard-code because they are standardized — MFA
#: means one thing across every framework this tool reads — which is not
#: true of synonyms in general, so the list stops at acronyms rather than
#: growing into a thesaurus nobody can reason about.
#:
#: It does not close the vocabulary gap, only the part of it with a fixed
#: answer. "admins" against "administrative" is ordinary morphology and
#: still misses; that case wants a real stemmer or embeddings.
ACRONYMS = {
    "mfa": ("multi", "factor", "authentication"),
    "2fa": ("two", "factor", "authentication"),
    "sso": ("single", "sign", "on"),
    "rbac": ("role", "based", "access", "control"),
    "iam": ("identity", "access", "management"),
    "pii": ("personally", "identifiable", "information"),
    "phi": ("protected", "health", "information"),
    "ephi": ("electronic", "protected", "health", "information"),
    "vpn": ("virtual", "private", "network"),
    "edr": ("endpoint", "detection", "response"),
    "dlp": ("data", "loss", "prevention"),
    "siem": ("security", "information", "event", "management"),
    "rto": ("recovery", "time", "objective"),
    "rpo": ("recovery", "point", "objective"),
    "sla": ("service", "level", "agreement"),
    "bcdr": ("business", "continuity", "disaster", "recovery"),
}


def term_groups(text: str) -> list[tuple[str, ...]]:
    """One group per word asked about, holding every way of writing it.

    An acronym and its expansion are *alternatives*, not separate things to
    look for, and the distinction decides whether a question gets answered.
    Counted as three flat terms, `SSO` can never be more than two-thirds
    matched by a document that spells out "single sign-on" — so the
    expansion ends up penalising exactly the documents it exists to reach.
    Grouped, matching any member satisfies the group.

    The acronym is kept alongside its expansion because documents use both,
    often in one sentence ("multi-factor authentication (MFA)"). Expansions
    go through the same stopword filter as everything else: `sso` spells out
    to "single sign on", and an unfiltered "on" is a term no document can
    match, since the document side drops it.
    """
    groups: list[tuple[str, ...]] = []
    for raw in _TOKEN_RE.findall(_strip_control_ids(text).lower()):
        if raw in _STOPWORDS or len(raw) < 2:
            continue
        expansion = tuple(word for word in ACRONYMS.get(raw, ()) if word not in _STOPWORDS)
        groups.append((normalize(raw), *expansion))
    return groups


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric terms, minus function words and identifiers.

    Applied to documents and questions alike, so expansion works in both
    directions: a page that only says "MFA" is found by a question about
    multi-factor authentication, and the reverse.
    """
    return [term for group in term_groups(text) for term in group]


def _matching_controls(query_ids: set[str], chunk_ids: set[str]) -> list[str]:
    """The chunk's identifiers that answer one of the query's.

    An identifier anchors its own enhancements: asking about `AC-2` is
    asking about `AC-2(1)` too, and asking about `164.312` covers
    `164.312(a)(1)`. This is the same rule `coverage.py` uses to decide what
    a topic claims, and it has to hold here for the same reason — nobody
    enumerates AC-2(1) through AC-2(13) to ask a question about AC-2.

    Not symmetric: asking about the enhancement is a narrower question than
    asking about the control, so `AC-2(1)` does not match a section that
    only cites `AC-2`.
    """
    matched = {
        chunk_id
        for chunk_id in chunk_ids
        for query_id in query_ids
        if chunk_id == query_id or chunk_id.startswith(f"{query_id}(")
    }
    return sorted(matched)


def extract_control_ids(text: str) -> list[str]:
    """Every control or regulatory identifier in the text, uppercased.

    Deliberately run over the whole text rather than only over source tags:
    a hand-written page cites `AC-2` in a sentence, and a question names it
    with no tag at all.
    """
    found: list[str] = []
    for match in _NIST_ID_RE.finditer(text):
        identifier = match.group(1).upper()
        if identifier not in found:
            found.append(identifier)
    for match in _CFR_ID_RE.finditer(text):
        identifier = match.group(1)
        if identifier not in found:
            found.append(identifier)
    return found


@dataclass
class Chunk:
    """One citable section of one document."""

    doc_id: str
    #: Heading ancestry, outermost first: ["4. Policy", "4.1 Media Protection"].
    #: Carried whole because "4.1" alone does not tell a reader where they
    #: are, and the parent heading is often what makes the section legible.
    heading_path: list[str]
    text: str
    index: int
    control_ids: list[str] = field(default_factory=list)

    @property
    def heading(self) -> str:
        return self.heading_path[-1] if self.heading_path else ""

    @property
    def section(self) -> str:
        return " > ".join(self.heading_path)


@dataclass
class Passage:
    """A chunk, the document it came from, and why it scored."""

    chunk: Chunk
    document: CorpusDocument
    score: float
    matched_terms: list[str] = field(default_factory=list)
    matched_controls: list[str] = field(default_factory=list)

    @property
    def citation(self) -> str:
        """What an answer puts next to a claim drawn from this passage.

        Includes the location, so the reader can go and look: a repo path
        they can open and change, or a wiki URL they can only read.
        """
        where = f"{self.document.title}"
        if self.chunk.section:
            where += f" § {self.chunk.section}"
        location = self.document.location
        return f"{where} ({location})" if location else where

    @property
    def is_trusted(self) -> bool:
        return self.document.is_trusted


def chunk_document(document: CorpusDocument) -> list[Chunk]:
    """Split one document into citable sections.

    Each chunk is a heading plus the text directly beneath it, not including
    its subsections — those become their own chunks and carry the parent in
    their heading path. Text before the first heading becomes a chunk with
    an empty path rather than being dropped, because a document's opening
    paragraph is frequently its scope statement.

    Fenced code blocks are passed through verbatim: a `#` inside a fence is
    a shell comment, not a heading, and treating it as one would split a
    command in half.
    """
    chunks: list[Chunk] = []
    #: (level, text) rather than text alone. A list indexed by position
    #: cannot express ancestry: `## A` then `#### A1` then `## B` puts B at
    #: position 1, so trimming by position leaves A as B's parent when they
    #: are siblings. Carrying the level makes "trim to my ancestors" exact.
    stack: list[tuple[int, str]] = []
    buffer: list[str] = []
    buffered_path: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(buffer).strip()
        buffer.clear()
        if not text:
            return
        # A document whose opening H1 restates its own title would otherwise
        # put that title at the root of every heading path, and the citation
        # would read "Access Control Standard § Access Control Standard >
        # 4.1". The title is already named beside the section, so the
        # repetition is pure noise. An H1 that says something *else* is kept.
        path = list(buffered_path)
        if path and path[0].strip().casefold() == document.title.strip().casefold():
            path = path[1:]
        for piece in _split_long(text):
            chunks.append(
                Chunk(
                    doc_id=document.doc_id,
                    heading_path=path,
                    text=piece,
                    index=len(chunks),
                    control_ids=extract_control_ids(piece),
                )
            )

    for line in document.body.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            continue

        heading = None if in_fence else _HEADING_RE.match(line)
        if heading is None:
            buffer.append(line)
            continue

        flush()
        level = len(heading.group("hashes"))
        # Keep only genuine ancestors: headings shallower than this one.
        stack = [entry for entry in stack if entry[0] < level]
        stack.append((level, heading.group("text")))
        buffered_path = [text for _, text in stack]

    flush()
    return chunks


def _split_long(text: str) -> list[str]:
    """Break an over-long section on paragraph boundaries.

    A single section can be thousands of characters — a requirements table,
    or a Policy section that runs for pages — and handing all of it to an
    answering model buries the sentence that matters. Splitting on blank
    lines keeps sentences and table rows intact.
    """
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in text.split("\n\n"):
        if current and size + len(paragraph) > MAX_CHUNK_CHARS:
            pieces.append("\n\n".join(current))
            current, size = [], 0
        current.append(paragraph)
        size += len(paragraph) + 2
    if current:
        pieces.append("\n\n".join(current))
    return pieces


@dataclass
class _Indexed:
    chunk: Chunk
    document: CorpusDocument
    terms: Counter
    length: int
    control_ids: set[str]


class RetrievalIndex:
    """A searchable index over a synced corpus.

    Built once and queried many times: a conversation is a burst of related
    questions, and rebuilding per question would make follow-ups pay for the
    whole corpus again.
    """

    def __init__(self, corpus: Corpus) -> None:
        self._entries: list[_Indexed] = []
        self._document_frequency: Counter = Counter()

        for document in corpus.documents:
            title_terms = tokenize(document.title) * TITLE_WEIGHT
            for chunk in chunk_document(document):
                terms = Counter(
                    tokenize(chunk.text) + tokenize(chunk.section) * HEADING_WEIGHT + title_terms
                )
                self._entries.append(
                    _Indexed(
                        chunk=chunk,
                        document=document,
                        terms=terms,
                        length=sum(terms.values()),
                        # Only what this passage's own text cites. Folding in
                        # identifiers from the document title made every
                        # section of an "AC-2 Account Management Standard"
                        # report `[cites AC-2]`, including sections that say
                        # nothing about it — a fabricated citation, which is
                        # the one output this package must never produce.
                        # The title's *words* still weigh on ranking through
                        # `title_terms`, which is the part that was earning
                        # its keep anyway.
                        control_ids=set(chunk.control_ids),
                    )
                )
                self._document_frequency.update(terms.keys())

        lengths = [entry.length for entry in self._entries]
        self._average_length = (sum(lengths) / len(lengths)) if lengths else 0.0

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def chunks(self) -> list[Chunk]:
        return [entry.chunk for entry in self._entries]

    def _idf(self, term: str) -> float:
        total = len(self._entries)
        frequency = self._document_frequency.get(term, 0)
        return math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))

    def _share(self, term: str) -> float:
        """The fraction of chunks this term appears in.

        Scale-free by construction, and the thing the gate actually wants to
        know: a term in most of the corpus cannot tell you which part of it
        the question was about.
        """
        total = len(self._entries)
        return self._document_frequency.get(term, 0) / total if total else 1.0

    def search(self, query: str, *, limit: int = 5, min_score: float = MIN_SCORE) -> list[Passage]:
        """The passages that bear on `query`, best first.

        Returns an empty list when nothing clears `min_score`. That is a
        real answer — "the documents do not appear to say" — and the caller
        is expected to pass it on rather than lowering the bar until
        something comes back.
        """
        groups = term_groups(query)
        query_terms = {term for group in groups for term in group}
        query_controls = {c.upper() for c in extract_control_ids(query)}
        if not query_terms and not query_controls:
            return []

        # Naming a control is the strongest statement of intent a question
        # can make, so if nothing in the corpus cites it, term matches must
        # not paper over that. "Nothing here cites AC-3" is a useful answer
        # to somebody checking coverage; a section that merely contains the
        # word "require" is a misleading one.
        if query_controls and not any(
            _matching_controls(query_controls, entry.control_ids) for entry in self._entries
        ):
            return []

        passages: list[Passage] = []
        for entry in self._entries:
            score = 0.0
            matched: list[str] = []
            for term in query_terms:
                frequency = entry.terms.get(term, 0)
                if not frequency:
                    continue
                matched.append(term)
                normalization = (
                    1
                    - _B
                    + _B * (entry.length / self._average_length if self._average_length else 1)
                )
                score += self._idf(term) * (
                    frequency * (_K1 + 1) / (frequency + _K1 * normalization)
                )

            controls = _matching_controls(query_controls, entry.control_ids)
            score += CONTROL_ID_BONUS * len(controls)
            if score and entry.document.is_trusted:
                score += TRUSTED_BONUS

            # Distinctiveness, not just magnitude. A pile of ubiquitous
            # terms can out-score a real match without saying anything the
            # question asked about. Three ways to clear the bar, because no
            # one of them survives every corpus size:
            #
            #   * an identifier matched — exact evidence, never in doubt;
            #   * a matched term is specific enough to be about something;
            #   * or the passage covers essentially the whole question,
            #     which is what saves a small corpus where IDF has too few
            #     documents to tell a common word from a rare one.
            # Over groups, not raw terms: matching "single sign-on" fully
            # answers a question about SSO, and should count as such.
            hit = set(matched)
            covered = sum(1 for group in groups if hit.intersection(group))
            coverage = covered / len(groups) if groups else 0.0
            specific = (
                bool(controls)
                or any(self._share(term) <= MAX_TERM_SHARE for term in matched)
                or coverage >= FULL_COVERAGE
            )
            if score > 0 and score >= min_score and specific:
                passages.append(
                    Passage(
                        chunk=entry.chunk,
                        document=entry.document,
                        score=score,
                        matched_terms=sorted(matched),
                        matched_controls=controls,
                    )
                )

        # Position is the final tiebreak so that equal scores rank in corpus
        # order rather than arbitrarily — a ranking that reshuffles between
        # runs cannot be regression-tested.
        passages.sort(key=lambda p: (-p.score, p.document.doc_id, p.chunk.index))
        return passages[:limit]


def build_index(corpus: Corpus) -> RetrievalIndex:
    return RetrievalIndex(corpus)
