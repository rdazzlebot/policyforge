"""The Zardoz read-eval-print loop.

The loop itself is deliberately thin. Everything that decides *what to say*
lives in `dispatch()`, which is a pure function: line in, text out, with the
only side effect being flags it sets on the `ShellState` it is handed. That
split is what makes a conversational program testable — a test can drive a
hundred turns through `dispatch()` without a terminal, a subprocess, or a
fake stdin, and `run_shell()` stays small enough to read in one screen and
verify by eye.

The same split is what keeps retrieval and answering honest. Each is a
separate module returning a value this one only formats, so "did it find the
right section?" and "did it answer well from that section?" stay separately
testable rather than collapsing into one prompt nobody can debug.

Answering needs a model; retrieval does not. Running without one is
therefore supported rather than degraded: questions return the passages
themselves, which is the same evidence an answer would be built from, and an
API key is not the price of searching your own documents.

This module never imports the Confluence publish path. Zardoz is allowed to
*draft* an edit — it resolves the topic, works out what it would ask for and
hands back a `policyforge edit-topic` command to run — but the write itself
goes through that command's own gates: dry run by default, macro refusal,
citation checks, explicit confirmation. Keeping `update_page_body` out of
this module's import graph makes that a structural property rather than a
rule someone has to remember.
"""

from __future__ import annotations

import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from policyforge.topics.registry import Topic

from .art import voice
from .corpus import DEFAULT_CORPUS_DIR, Corpus, load_corpus

PROMPT = "zardoz> "

#: How many documents of one kind `/corpus` lists before summarising the
#: rest. A twenty-topic registry publishes sixty pages, and a command whose
#: job is to orient you should not be the thing that scrolls the terminal.
_LIST_LIMIT = 15


@dataclass
class ShellState:
    """Everything one session knows.

    Held in one object rather than in closures so that a test can construct
    a session, drive turns through `dispatch()`, and then assert on what
    changed.
    """

    topics: list[Topic] = field(default_factory=list)
    plain: bool = False
    running: bool = True
    #: The synced document snapshot, or None when `zardoz sync` has not been
    #: run. Absent is a first-class state rather than an empty corpus: the
    #: two need different answers, since "nothing is synced" and "the
    #: documents do not mention that" are different facts about the world.
    corpus: Corpus | None = None
    #: Where the snapshot lives, so `/reload` can pick up a re-sync without
    #: the session having to end.
    corpus_dir: Path = DEFAULT_CORPUS_DIR
    #: Built on the first question rather than at launch, so opening the
    #: shell to run `/topics` doesn't pay for indexing a corpus nobody is
    #: about to search. Cleared whenever the corpus is replaced.
    _index: object | None = field(default=None, repr=False)
    #: The LLM that writes answers, or None when none is configured. Absent
    #: is a supported way to run: retrieval is offline, so the shell still
    #: finds and shows the passages, and the reader draws the conclusion.
    #: An API key should not be the price of searching your own documents.
    provider: object | None = field(default=None, repr=False)
    #: Why there is no provider, if there isn't one — shown once, when it
    #: first matters, rather than as a launch-time complaint.
    provider_note: str = ""
    #: The last answer, so `/sources` can show what it was drawn from in
    #: full rather than in the excerpts that fit beside the prose.
    last_answer: object | None = field(default=None, repr=False)

    @property
    def voice(self) -> dict[str, str]:
        return voice(plain=self.plain)

    @property
    def corpus_loaded(self) -> bool:
        return self.corpus is not None and len(self.corpus) > 0

    @property
    def index(self):
        """The retrieval index over the current corpus."""
        from .retrieve import build_index

        if self._index is None and self.corpus is not None:
            self._index = build_index(self.corpus)
        return self._index

    def set_corpus(self, corpus: Corpus | None) -> None:
        """Swap in a corpus and drop the index built over the old one.

        One method rather than two assignments at each call site: an index
        that outlived its corpus would answer from documents that are no
        longer there, which is the one failure a re-sync is supposed to fix.
        """
        self.corpus = corpus
        self._index = None


@dataclass
class Command:
    summary: str
    handler: Callable[[list[str], ShellState], str]
    aliases: tuple[str, ...] = ()


def _cmd_help(args: list[str], state: ShellState) -> str:
    """Rendered from the command table rather than written out, so it cannot
    drift out of date as commands are added."""
    width = max(len(name) for name in COMMANDS)
    lines = [state.voice["help_header"], ""]
    for name, command in COMMANDS.items():
        aliases = ", ".join("/" + alias for alias in command.aliases)
        alias_note = f"  (also {aliases})" if aliases else ""
        lines.append(f"  /{name.ljust(width)}  {command.summary}{alias_note}")
    lines += ["", "  Anything that does not start with / is treated as a question."]
    return "\n".join(lines)


def _cmd_quit(args: list[str], state: ShellState) -> str:
    state.running = False
    return state.voice["goodbye"]


def _cmd_topics(args: list[str], state: ShellState) -> str:
    """List the registry, flagging which topics have documents to sync.

    A topic with no `confluence:` block is invisible to everything Zardoz
    does, so it is worth showing that gap here rather than letting it look
    like a retrieval failure later.
    """
    if not state.topics:
        return (
            "No topic registry loaded. Copy config/topics.example.yaml to "
            "config/topics.yaml and set the owners to your own teams."
        )

    name_width = max(len(topic.name) for topic in state.topics)
    owner_width = max(len(topic.owner) for topic in state.topics)
    lines = [f"{len(state.topics)} topics:", ""]
    unpublished = 0
    for topic in state.topics:
        pages = topic.confluence_pages()
        if pages:
            where = ", ".join(tier for tier, _ in pages)
        else:
            where = "no pages declared"
            unpublished += 1
        lines.append(
            f"  {topic.name.ljust(name_width)}  {topic.owner.ljust(owner_width)}  [{where}]"
        )
    if unpublished:
        lines += [
            "",
            f"  {unpublished} topic(s) declare no Confluence pages, so there is "
            "nothing to read for them.",
        ]
    return "\n".join(lines)


def _cmd_corpus(args: list[str], state: ShellState) -> str:
    """Show what is synced, split by confidence.

    Worth its own command because the commonest cause of a disappointing
    answer is not the model but the corpus: a page that never synced cannot
    be quoted, and the difference is invisible from the answer alone.
    """
    if state.corpus is None:
        return (
            "No corpus synced. Run `policyforge zardoz sync` to read your markdown "
            "content tree, your published Confluence pages, or both."
        )

    corpus = state.corpus
    lines = [
        f"{len(corpus)} document(s), synced {corpus.synced_at or 'at an unknown time'}",
        f"  {len(corpus.trusted)} trusted    — owner known, from the registry or frontmatter",
        f"  {len(corpus.supporting)} supporting — real content nobody has claimed",
        f"  {len(corpus.from_markdown)} from markdown, {len(corpus.from_confluence)} from "
        "Confluence",
    ]
    if corpus.is_stale:
        age = corpus.age_days or 0
        lines += [
            "",
            f"  This snapshot is {age:.0f} days old. Anything published or edited since "
            "then is invisible here — re-sync, then /reload.",
        ]

    lines.append("")
    for doc in corpus.trusted[:_LIST_LIMIT]:
        where = doc.location or doc.space
        lines.append(f"  [{doc.tier or '?'}] {doc.title}  ({doc.topic} / {doc.owner})  {where}")
    if len(corpus.trusted) > _LIST_LIMIT:
        lines.append(f"  ... and {len(corpus.trusted) - _LIST_LIMIT} more")

    if corpus.supporting:
        lines.append("")
        for doc in corpus.supporting[:_LIST_LIMIT]:
            lines.append(f"  [supporting] {doc.title}  {doc.location or doc.space}")
        if len(corpus.supporting) > _LIST_LIMIT:
            lines.append(f"  ... and {len(corpus.supporting) - _LIST_LIMIT} more")

    brittle = [doc for doc in corpus.documents if not doc.is_editable]
    if brittle:
        lines += [
            "",
            f"  {len(brittle)} page(s) can be read but not safely edited (Confluence "
            "macros that would not survive a round trip).",
        ]
    return "\n".join(lines)


def _cmd_reload(args: list[str], state: ShellState) -> str:
    """Re-read the snapshot from disk without ending the session.

    The loop this exists for is the one a repo-backed setup makes normal:
    ask a question, notice the document is wrong, edit the markdown, ask
    again. Before this, "ask again" meant quitting the shell, and a tool you
    have to restart to see your own change is one people stop using.
    """
    try:
        state.set_corpus(load_corpus(state.corpus_dir))
    except FileNotFoundError:
        return (
            f"Still nothing synced at {state.corpus_dir}. Run `policyforge zardoz sync` "
            "in another terminal, then /reload."
        )
    except ValueError as exc:
        return str(exc)

    corpus = state.corpus
    local = len(corpus.from_markdown)
    return (
        f"Reloaded {len(corpus)} document(s) — {local} from markdown, "
        f"{len(corpus) - local} from Confluence, synced "
        f"{corpus.synced_at or 'at an unknown time'}."
    )


def _cmd_sources(args: list[str], state: ShellState) -> str:
    """Show, in full, what the last answer was drawn from.

    The answer lists its sources by title and section; this is the text
    itself. Checking a compliance answer means reading the requirement it
    came from, and making that a separate command keeps the answer short
    without putting the evidence out of reach.
    """
    answer = state.last_answer
    if answer is None or not getattr(answer, "passages", None):
        return "No sources yet — ask a question first."

    lines = []
    for number, passage in enumerate(answer.passages, start=1):
        marker = "  " if not answer.cited or number in answer.cited else " (uncited)"
        lines.append(f"[{number}]{marker} {passage.citation}")
        lines.append(_indent(" ".join(passage.chunk.text.split())))
        lines.append("")
    return "\n".join(lines).rstrip()


#: How many passages one question returns. Enough to cover a requirement
#: that is split across a Standard and its Procedure, few enough to read.
_PASSAGE_LIMIT = 4

#: Characters of a passage shown inline. The whole chunk is available to
#: whatever asks the index directly; this is what fits in a terminal without
#: burying the next result.
_EXCERPT_CHARS = 400


COMMANDS: dict[str, Command] = {
    "help": Command("Show the available commands.", _cmd_help, aliases=("?",)),
    "topics": Command("List the topic registry and who owns each topic.", _cmd_topics),
    "corpus": Command("Show which documents are synced and available.", _cmd_corpus),
    "sources": Command("Show the last answer's passages in full.", _cmd_sources),
    "reload": Command("Re-read the snapshot from disk after a re-sync.", _cmd_reload),
    "quit": Command("Leave the shell.", _cmd_quit, aliases=("exit",)),
}

#: Flattened alias -> canonical name, built once from the table above.
_ALIASES = {alias: name for name, cmd in COMMANDS.items() for alias in cmd.aliases}


def dispatch(line: str, state: ShellState) -> str:
    """Turn one line of input into one block of output.

    Pure apart from the flags it sets on `state`, so the whole conversational
    surface can be tested without a terminal.
    """
    line = line.strip()
    if not line:
        return ""

    if not line.startswith("/"):
        return _answer(line, state)

    word, _, rest = line[1:].partition(" ")
    name = _ALIASES.get(word.lower(), word.lower())
    command = COMMANDS.get(name)
    if command is None:
        return state.voice["unknown_command"].format(command=f"/{word}")
    return command.handler(rest.split() if rest else [], state)


def _answer(question: str, state: ShellState) -> str:
    """Answer a question from the synced corpus.

    Without a synced corpus there is nothing to answer *from*, and saying so
    is the only honest response — a chatbot that improvises an answer about
    what your access control standard requires is worse than one that admits
    it has not read it.

    With no LLM configured the passages themselves are shown instead. That
    is a supported way to run rather than a degraded one: retrieval is
    entirely offline, and an API key should not be the price of searching
    your own documents. The reader draws the conclusion, from the same
    evidence an answer would have been built out of.
    """
    from .answer import answer_question

    if state.corpus is None:
        return (
            "No document corpus is synced yet, so I have nothing to answer from.\n"
            "Run `policyforge zardoz sync --content-dir <your markdown tree>` — that "
            "needs no Confluence credentials — then /reload."
        )
    if not state.corpus_loaded:
        return (
            "The corpus is empty — sync ran but found no documents. `/corpus` shows "
            "what it found, and `/topics` shows which topics declare pages at all."
        )

    passages = state.index.search(question, limit=_PASSAGE_LIMIT)

    if state.provider is None:
        if not passages:
            return (
                "Nothing in the synced documents appears to bear on that.\n"
                "That may be the answer — the documents genuinely may not say — or the "
                "page you want may not be synced; `/corpus` shows what is."
            )
        note = state.provider_note or "No LLM configured"
        return "\n".join(
            [f"{note}, so here are the passages themselves:", "", _render_passages(passages)]
        )

    try:
        answer = answer_question(question, passages, state.provider)
    except Exception as exc:  # noqa: BLE001 - any provider/SDK failure, session survives
        lines = [f"The model could not be reached ({type(exc).__name__}: {exc})."]
        if passages:
            lines += ["", "The passages that bear on it:", "", _render_passages(passages)]
        return "\n".join(lines)

    state.last_answer = answer
    return _render_answer(answer)


def _render_answer(answer) -> str:
    """Lay out an answer so the evidence is never further away than the claim."""
    lines: list[str] = []

    # Warnings go first. An integrity problem discovered after the fact is
    # only useful if the reader sees it before they believe the sentence it
    # is about.
    if answer.warnings:
        lines.append("!! This answer did not pass its own checks:")
        lines += [f"!!   - it {warning}" for warning in answer.warnings]
        lines.append("!! Read the passages below rather than trusting the prose.")
        lines.append("")

    lines.append(answer.text)

    if answer.refused and answer.passages:
        lines += ["", "Closest passages:", "", _render_passages(answer.passages)]
        return "\n".join(lines)
    if answer.refused:
        return "\n".join(lines)

    sources = answer.sources() or list(enumerate(answer.passages, start=1))
    lines += ["", "Sources:"]
    for number, passage in sources:
        lines.append(f"  [{number}] {passage.citation}")
        if not passage.is_trusted:
            lines.append("        (supporting — nobody has claimed this document)")
    lines.append("")
    lines.append("  /sources shows these in full.")
    return "\n".join(lines)


def _render_passages(passages) -> str:
    lines: list[str] = []
    for rank, passage in enumerate(passages, start=1):
        lines.append(f"{rank}. {passage.citation}")
        if not passage.is_trusted:
            lines.append("   (supporting — real content, but nobody has claimed it)")
        lines.append(_indent(_excerpt(passage.chunk.text)))
        why = []
        if passage.matched_controls:
            why.append("cites " + ", ".join(passage.matched_controls))
        if passage.matched_terms:
            why.append("matched " + ", ".join(passage.matched_terms[:6]))
        if why:
            lines.append(f"   [{'; '.join(why)}]")
        lines.append("")
    return "\n".join(lines).rstrip()


def _excerpt(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= _EXCERPT_CHARS:
        return collapsed
    return collapsed[:_EXCERPT_CHARS].rsplit(" ", 1)[0] + " ..."


def _indent(text: str) -> str:
    return "\n".join(f"   {line}" for line in textwrap.wrap(text, width=76)) or "   (empty)"


def run_shell(
    state: ShellState,
    *,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> None:
    """Drive the loop until the user leaves.

    The two ways out of a terminal program are handled differently on
    purpose. Ctrl-D (EOF, and also what a piped stdin does when it runs out)
    means "I am done" and exits. Ctrl-C means "abandon the line I am typing"
    and must *not* exit — killing a session because someone interrupted a
    half-typed question is the kind of small hostility that makes a REPL
    unpleasant to live in.
    """
    while state.running:
        try:
            line = read(PROMPT)
        except EOFError:
            write(state.voice["goodbye"])
            return
        except KeyboardInterrupt:
            write("")
            write(state.voice["interrupt"])
            continue

        output = dispatch(line, state)
        if output:
            write(output)
