"""Closing the gap between how a question is asked and how a document is written.

Retrieval matches the words people use, and that holds for most of a
compliance corpus because the vocabulary is terms of art the askers learned
from the documents. It fails on the paraphrase: *how often do we check who
has admin?* against a Standard that only ever says **privileged access
review cadence**. Not one content word overlaps, and the honest refusal that
earns is wrong — the document answers the question completely.

**Exact first, expansion only on a miss.** Nothing here runs while retrieval
is finding passages on the user's own words, which keeps the common case
free and, more importantly, keeps it precise: an expansion is a guess at
vocabulary, and a guess mixed into a search that was already working can
only make it worse. Expansion is what happens instead of a refusal, not
alongside a success.

**Why not embeddings.** The README's earlier note said this gap wanted a
vector index alongside the exact matching, and that would work. It would
also need an embedding model — a local one means a multi-gigabyte dependency
for a tool that currently installs in seconds, and a hosted one means an API
this project's own default provider does not offer, since Anthropic ships no
embeddings endpoint. Neither is a good trade for a corpus of tens to
hundreds of documents. Asking the model that is already configured to name
the vocabulary a document would use gets the same recall on this failure
mode, adds no dependency, and has the property embeddings do not: you can
read the expansion and see exactly why a passage surfaced.

What that leaves uncovered is scale. Expansion is one guess per question;
embeddings would rank the whole corpus by meaning. If a document set ever
grows past the point where a handful of extra terms can bridge it, the seam
is `RetrievalIndex.search(..., expansion=...)` — a scorer that already
weighs guessed vocabulary below the user's own words and keeps them
separable in the result.
"""

from __future__ import annotations

#: Ceiling on how much vocabulary one expansion may add. Enough to name a
#: phrase and its close variants, short enough that it cannot become a
#: second query in its own right and drag the search somewhere new.
MAX_EXPANSION_TERMS = 12

EXPANSION_SYSTEM_PROMPT = """You name the vocabulary an organization's \
security policy documents would use for an idea, so a keyword search can \
find them.

You are given a question. Return only the terms and short phrases a formal
policy, standard or procedure would use for the same idea — the words the
document has, not the words the question has.

Rules:

1. Terms only, separated by commas. No sentences, no explanation, no
   numbering, no restating the question.
2. Formal register. A question says "who has admin"; a Standard says
   "privileged access", "administrative accounts", "elevated entitlements".
   Give the Standard's words.
3. Do not repeat words already in the question. They have been searched for
   already; repeating them adds nothing and crowds out what would help.
4. Never invent specifics. No control identifiers, no numbers, no
   frequencies, no team or vendor names. You are naming vocabulary, not
   answering — and a frequency you supplied would be searched for and might
   well be found, which would attach this tool's guess to a real citation.
5. At most twelve terms. If the question is already in the documents' own
   register, return fewer, or nothing at all."""


def expand_query(question: str, provider, *, max_terms: int = MAX_EXPANSION_TERMS) -> str:
    """Vocabulary a document might use for what `question` asks about.

    Returns a space-joined string for `RetrievalIndex.search(expansion=...)`,
    or an empty string when there is nothing useful to add. Never raises:
    expansion is a recovery path taken after a refusal, and a failure here
    should leave the user with the refusal they had, not an error.
    """
    if provider is None or not question.strip():
        return ""

    try:
        response = provider.generate(
            system=EXPANSION_SYSTEM_PROMPT,
            prompt=f"QUESTION\n\n{question.strip()}\n\nName the documents' vocabulary.",
            temperature=0.0,
            max_tokens=150,
        )
    except Exception:  # noqa: BLE001 - any provider failure just means no expansion
        return ""

    return " ".join(parse_expansion(response.text, max_terms=max_terms))


def parse_expansion(text: str, *, max_terms: int = MAX_EXPANSION_TERMS) -> list[str]:
    """Read a comma-separated expansion back, defensively.

    Models occasionally answer the question instead of naming vocabulary. A
    sentence-shaped segment means the format was not followed, and then the
    whole reply is discarded rather than mined for the fragments that happen
    to fit — "Certainly, here are the terms a standard would use" yields the
    term "Certainly", which is not vocabulary, and salvaging it puts the
    model's preamble into the search. No expansion is better than noise.
    """
    segments = [
        segment.strip().strip("-*•").strip().strip('"').strip()
        for segment in text.replace("\n", ",").split(",")
    ]
    kept = [segment for segment in segments if segment]
    if any(len(segment.split()) > 4 for segment in kept):
        return []

    terms: list[str] = []
    for segment in kept:
        if segment.lower() not in (term.lower() for term in terms):
            terms.append(segment)
        if len(terms) >= max_terms:
            break
    return terms
