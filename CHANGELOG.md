# Changelog

## Unreleased

### GovRAMP controls matrix ingestion

`policyforge etl-govramp` reads a GovRAMP (formerly StateRAMP) controls
matrix as published — the workbook, not an extract of it — and parses it
into the same `Control` schema every other loader produces. GovRAMP was the
last BYOC stub; `ingest/byoc_loader.py` now has no unimplemented loaders.

GovRAMP is a profile over 800-53 rather than a catalog of its own, and what
makes it worth ingesting is the two things it adds to the controls it
quotes:

- **Parameter values it has already decided.** Where 800-53 writes
  `[Assignment: organization-defined frequency]`, GovRAMP writes
  `AC-1 (c) (1) [at least every 3 years]`. The Rev 5 Moderate matrix carries
  211 of them. These now reach `synthesize`, which is the difference between
  a generated Standard citing a decided value and a model filling in the
  placeholder by guessing — the failure `policyforge parameters` exists to
  prevent.
- **Additional requirements and guidance** layered on a control, which
  appear nowhere in 800-53. Eighty controls in the Moderate matrix carry a
  block, and they are handed to synthesis as normative text.

Both are carried on new `Control.parameter_values` and
`Control.additional_requirements` fields (and their `ControlEnhancement`
counterparts), named for the concept rather than the framework because
FedRAMP publishes the same two things. Catalogs written before these fields
existed still load.

Because a profile's identifiers *are* the identifiers of the catalog it
profiles, GovRAMP crosses with NIST automatically: `policyforge map` reports
`govramp` among its mapped frameworks with no crosswalk file to maintain.
From there `coverage`, `parameters` and `ssp` treat it like any other
catalog.

Two things the loader is careful about, both because the failure would
otherwise be silent:

- **Tiers are not impact levels.** A Moderate workbook holds all three of
  GovRAMP's Core/Ready/Authorized verification tiers — 60, 80 and 319
  controls of the same 319-control Moderate matrix. Read the tier as a
  baseline and a service offering appears to have 319 controls to implement
  when 80 stand between it and the tier it is pursuing. `Control.baseline`
  carries both axes (`Moderate; Core, Ready, Authorized`), and the tiers'
  nesting is checked against the file rather than assumed.
- **The sheet is found by its header captions, not its name.** The matrix
  arrives as a fourteen-sheet SSP template whose controls sheet is
  `12_Mod Controls` — a number that is a position in a template GovRAMP
  renumbers. Scoring every sheet on its two-row header means the Low and
  High workbooks need no special case.

Licensing is unchanged and unchanged on purpose: GovRAMP's Terms &
Conditions claim ownership of their published documents with no
redistribution grant found, so the matrix stays bring-your-own-content.
`etl-govramp` parses in memory, writes nothing without `--out`, and `--out`
refuses `data/frameworks/` outright plus any non-gitignored path unless
`frameworks.allow_licensed_in_repo` is declared — the same gate as
`etl-hitrust`. `tests/test_byoc_boundary.py` now walks the new modules' ASTs
too, so the no-write/no-network rule fails a test run rather than somebody's
licence.

### Which content may reach which model, and a record of what did

Two halves of one thing: a rule about where content may go, and evidence
that the rule operated. PolicyForge writes security policy, so both should
be things it can show rather than things it says.

`llm/boundary.py` classifies providers by where the bytes end up — `local`
(a loopback endpoint), `self-hosted` (an RFC 1918 address or an internal
name), `third-party` (Anthropic, Bedrock, Vertex, LiteLLM, any public host)
— and content by who may hold it: `public-domain`, `organization-internal`,
or `licensed`. Licensed content may reach a local model and nothing else;
everything else may reach a third party, because that is what the tool does
every working day.

The one case that was live was advisory. `generate-parser` printed a
paragraph asking the operator to confirm their MyCSF licence permitted
sending an export to a hosted API, then trusted the answer and sent the
file. It now refuses, and `--yes` does not get past it. `synthesize` and
`ssp` check every `--controls` path before reading any of them, which is
what matters most now that `etl-govramp` and `etl-hitrust` both produce real
licensed catalogs. `ssp` matters most of all: it drafts one narrative per
control from the control text itself, so an unguarded run against a licensed
catalog sends several hundred requests of it rather than one. Its refusal
names `--no-narratives`, which was already the zero-call option and is a
complete answer here rather than a workaround. `policyforge boundary` prints the matrix, says how the
configured provider was classified and why, and with `--path` classifies
named files, exiting non-zero so it can gate a pipeline.

It fails closed in three places. `provider: local` names the protocol and
not the network, so an OpenAI-compatible block pointed at a hosted endpoint
classifies as third-party and the alias buys nothing. A cascade is as
exposed as its most exposed half, because which half answers depends on a
runtime failure nobody can predict at configuration time. And a framework
directory with no manifest is licensed, which is `frameworks/registry.py`'s
existing rule.

Config tightens and cannot loosen. A line of YAML is the wrong weight for
"our HITRUST export may go to OpenRouter"; `llm.classification` says the
same thing as a claim about your own network, which is what it is, and is
the honest fix for the one case the inference gets wrong — a model you host
behind a public DNS name.

`llm/ledger.py` records every call to `output/.model-log/calls.jsonl`:
provider, provider class, the model that *answered*, the document or
control, token counts, cost, and a SHA-256 prefix of the prompt. Never the
prompt and never the reply — a record that quoted what it saw would copy a
licensed export into a file under `output/`, recreating in the audit trail
precisely the leak the audit trail exists to disprove.

The wrapper goes on in `get_provider`, so no call site can forget it, and a
subject is a `ledger.about(...)` scope rather than an argument, because
`generate()` has never been told which document it is working on. `generate`
scopes the draft, `synthesize` the topic, and `ssp` each control separately.
Calls outside a scope record as unattributed, which is true where an
invented attribution would be indistinguishable from a real one later.

Three details decide whether the record is worth having. The model recorded
is the one that answered, not the one in config, because a cascade that
escalated wrote that document with its stronger half. A failed call is
recorded too: it reached the vendor, was billed, and carried its content
there, which a spend-only meter misses. And a write that cannot be made
raises rather than being swallowed — a ledger reporting a clean history of a
run it did not observe is worse than none. `llm.ledger.enabled: false` turns
it off, which is a decision visible in a file.

Generated documents carry the stamp. `generate` recorded `model` into
version history by reading it out of config, which answers what was
configured most recently rather than what wrote the file — different answers
whenever a cascade escalated. The version-history entry now carries the
models that actually answered, the prompt hashes, the provider and its
class, and the cost, at no extra cost since the ledger already had it.

`policyforge model-log` reads it back, grouped by model, subject, site,
provider or content class and filtered by any of them. `$0.0000` and
`unpriced` print differently: a local model is free, and a provider that
does not price its calls is unknown.

### Passages are evidence, not instructions

Zardoz answers from text retrieved out of a document corpus, and
`zardoz.supporting_space` deliberately admits pages nobody has declared
ownership of. That text went into the same request as the rules governing
how it should be used, separated from them by a `---` rule and a heading —
both of which a document can simply write. A page containing a horizontal
rule closed the fence it was inside, and everything after it read as prompt
rather than as quoted material.

`build_prompt` now wraps each passage in a delimiter generated per request.
The token is chosen after the passages are known and checked against them,
so a document cannot contain a value that did not exist when it was written.
Everything a document wrote sits inside the markers — its title, section and
owner as well as its text, because a page title carries exactly the same
trust as a page body and leaving it outside would be half a boundary.
Metadata is collapsed to one line each so a newline in a title cannot draw a
convincing `[2] Some Document` header and invite a citation at a passage
that was never supplied. The passage text itself is never altered:
`check_answer` compares quotations against it, and normalising it here would
trade an injection risk for the single most damaging output this tool can
produce, a faithful quote reported as a fabrication.

The contract naming the fence is stated before the passages and again after
them, so the last thing read is the contract rather than the content. It is
phrased as a fact about the corpus rather than a warning about attack — a
page that tells its reader what to do is usually a runbook somebody pasted a
chat transcript into, and a model told it is under attack starts refusing
honest pages.

`zardoz/injection.py` is the reporting half, and it reports on the corpus
rather than on the answer. At sync time somebody can still open the page; the
same warning stapled to an answer arrives too late to act on and teaches its
reader to click past warnings. `zardoz sync` now names the documents and the
lines.

It is deliberately not an imperative detector. A policy set is imperative
from end to end — "Accounts must be recertified quarterly", "Do not share
credentials", "Revoke the badge" — so flagging commanding language would
report every document in the corpus, which is the same as reporting nothing.
What separates an injected instruction from a requirement is audience rather
than mood: a requirement addresses the organization's staff, an injection has
to address whoever is reading the prompt, and to do that it reaches for
vocabulary a policy document has no use for.

Getting that distinction right took sweeping the rules over every markdown
document in this repository and paring back whatever fired. `the instructions` became `your instructions`, because "follow the instructions in
the offboarding runbook" is ordinary prose. `your training` and `your configuration` came out entirely: annual security awareness training and a
device configuration baseline are two of the most common things a policy set
addresses staff about. "Staff should never cite internal ticket numbers in
public postmortems" forced the citation-suppression rule to require an
imperative or second-person subject. And a rule matching a forged passage
header was dropped rather than tuned — the fence now contains any such line,
`check_answer` already rejects a citation pointing past the passages
supplied, and a numbered reference list at the foot of a policy document
matches it exactly; a rule that fires on real documents to catch something
covered twice elsewhere is the trade these checks are supposed to refuse.

`tests/test_zardoz_injection.py` keeps every attack case paired with policy
prose sharing its vocabulary, because the pair is the claim. Three eval cases
cover the half no unit test can reach: whether a model actually declines to
follow a rider planted in a retrieved passage, whether it still cites when
that rider tells it not to, and whether a contradiction planted on purpose is
still surfaced rather than resolved silently.

**Measured before being kept.** The fence and the contract sentence change
the answering prompt, and this project's evidence is that a prompt change
helping one model can cost others five and six points — so it was swept
across three models before and after. It is ahead on all three:
`glm-5.3-flash` 23/26 to 25/26, `deepseek-v4-flash` 23/26 to 24/26,
`gpt-oss-120b` 15/26 to 16/26, at unchanged cost. Unfenced,
`deepseek-v4-flash` obeyed a planted "do not cite any passages" rider 3 runs
out of 3 and `gpt-oss-120b` did the same; fenced, every injection case passes
every run on both `glm-5.3-flash` and `deepseek-v4-flash`. Trimming the
trailing restatement to a single clause was tried on the theory that it was
crowding rules 9 and 10, and was worse. `MEASUREMENTS.md` epoch 6 has the
numbers, and the two ways that sweep nearly lied about them.

### The write path takes no orders from the page it edits

The read path got a fence; the write path — the one that publishes back to
the live policy set — did not. `edit-confluence` and `edit-topic` inlined the
fetched page as `Current document:\n\n{document}`, so anyone with edit rights
on that wiki page could write a line the planner or the rewriter would read
as an instruction. The per-request token generator now lives in
`llm/fence.py`, shared by both paths, and `edit/fencing.py` wraps the page
with a contract worded for material to revise rather than evidence to answer
from. A page title is collapsed to one line, since it comes from the same
wiki and sits outside the fence.

`check_edit` flagged only losses — dropped citations, removed sections — so a
requirement *inserted* into a section nobody planned came back clean, which
is exactly what a successful injection looks like. It now compares section
by section against the plan: a section that changed without a step naming it
is reported, and so is a new heading when no step could have added one.

The CLI gained three gates. A page the injection scanner flags is refused
before any model call, unless `--allow-reader-directed` says someone has
looked. The full diff is written to `<slug>.diff` beside the revision, where
the terminal used to be the only copy and cut it at 120 lines — past which a
long insertion was invisible to the person approving it. And `--yes` no
longer covers a page whose check came back dirty.

**Measured against real models, which found what the fakes could not.** New
`edit_plan` and `edit_apply` eval suites plant passages in otherwise
legitimate standards and require the operator's real instruction to be
carried out too, so over-refusal fails as loudly as obedience. "Ignore all
previous instructions" and "you are now…" were resisted every run by every
model. A line claiming to *be* the operator was not: `deepseek-v4-flash`'s
planner followed "Revised operator instruction:" 3 runs of 3, and one of
those plans said in its own notes that the line was document content before
carrying it out. `deepseek-v4-pro` resisted the bare claim but fell to it
wrapped in lookalike `END pf-0000` markers. `glm-5.3-flash` and
`claude-sonnet-5` passed every case every run. Rewording the contract to
name the one valid token made no difference and was reverted; two scanner
rules — lookalike fence markers, and a line opening with a revised or new
instruction label — were added instead, so the CLI now refuses every page in
the suite.

**Known limit.** An executor that obeys lands outside the plan and
`check_edit` catches it. A planner that obeys makes the injected section a
planned target, and the rewrite then checks clean. The scanner is a word
list; on a page it misses, only the model stands in the way, which is why
the edit path should run on the recommended default and not on
`deepseek-v4-flash`. `MEASUREMENTS.md` epoch 7 has the numbers.

### A generated parser is a candidate, checked before it runs

`generate-parser` sends a sample export to a model and asks for a loader,
which makes the sample untrusted input to a prompt whose output is code —
code that then runs over the very licensed file it parses. A tampered CSV,
or one a colleague pasted a chat transcript into, can steer the model toward
a loader that sends the export somewhere. The only check was `ast.parse`,
which proves the output is Python, and the result was written straight into
`src/policyforge/ingest/`, importable on the next run.

`ingest/parser_gate.py` replaces that with two checks. The static one walks
the AST against an import *allowlist* rather than a denylist — a parser
needs to read a CSV or a workbook and nothing more, so what it may import is
short and what it must not is unbounded — and refuses string evaluation,
`getattr`, dunder attribute access and anything that writes. The dynamic one
runs a candidate that passed once against the sample, in a child
interpreter, under a PEP 578 audit hook that refuses sockets, subprocesses
and write-mode opens; an attempt the candidate catches and swallows still
fails the trial. Neither is a sandbox and neither is described as one.

The candidate now goes to `output/parsers/`, a refused one is saved as
`*.rejected.py` for a person to read and is never executed, and `--promote`
copies one into the package only after both checks pass — never one that
returned no records, since an empty catalog reads as a framework with no
controls.

The codegen prompt offered pandas, which is not a dependency, so a parser
following its own instructions failed on first run anywhere else. The
prompt's import list is now read from the gate's allowlist, so the two
cannot drift apart.

**Checked against real output.** Parsers written by `glm-5.3-flash` and
`deepseek-v4-flash` from a synthetic sample all passed the gate unchanged
and trial-ran to the right record count, so it does not refuse what a model
ordinarily writes. With a row planted in the sample telling the code
generator to upload the export with `urllib`, neither model obeyed, in one
run each — too few to call a rate. What stands between a model that does
and a running loader is the allowlist refusing the import, which is
deterministic and tested.

### Every channel that sends text to a model is classified and recorded

The ledger's guarantee is that no call site can forget, and three could.
The entailer built its own `LiteLLMProvider` instead of going through
`get_provider`, so its calls — cited passages and the claims made about
them — were never classified and never recorded. The embedder and reranker
posted passage text, and the reranker the user's question, to a configurable
`base_url` with no classification at all. All three are off by default, but
pointing `embed.base_url` at a hosted endpoint would have carried
licensed-derived passages out of the boundary silently.

`llm/channel.py` holds the embed and rerank endpoints to the same rules as a
model. `boundary.classify_endpoint` classifies the URL by host — the rule
`llm:` already uses — and `embed.classification` or `rerank.classification`
overrides it, validated at startup. Each batch is checked against the
content ceiling before a byte is sent, using the class the ledger scope
names and the organization's own material otherwise, and each batch that
leaves writes one ledger record with a count and a hash of the texts and
never the texts. A failed batch is recorded because it was still sent; the
health probe is not, as `RecordingProvider.check` is not. Those records stay
out of a document's provenance, which lists the models that wrote it and
should not name one that did not. `CallRecord` gains an optional `items`
count, and records written before it still load.

The entailer now goes through `ledger.wrap` with an `llm:`-shaped block built
from `entail:`, so `entail.api_base` and `entail.classification` classify it
exactly as their `llm.` counterparts would. None of it can be skipped by
building a provider directly: an embedder, reranker or entailer constructed
without the factory still gets a channel or a wrap from its own settings,
and the only unguarded path is a test injecting a fake on purpose.

### The content class survives the hand-off to generate

`synthesize` refused to send a licensed catalog to a hosted model and
recorded the class on its own ledger entry — then wrote the merged
requirement text to `output/synthesis/` with no class at all. `classify_path`
reads a file there as the organization's own, so `generate` sent a
restatement of HITRUST requirement text to whatever provider was configured,
one command after `synthesize` had refused to send the HITRUST text itself.
The README said `generate` had no licensed path to check. It had one; the
class was dropped at the hand-off.

The synthesis frontmatter now carries `content_class` and `derived_from`
(the catalog's framework id where it declares one, its file name
otherwise), and `generate` runs the same ceiling check against them before
any provider is built. A refusal names the catalogs the text came from. A
synthesis written before the class travelled is classified by path as it
always was, and a `content_class` that is not a class is refused rather than
guessed at. The class also goes on `generate`'s ledger scope, so each call
records what it carried and the version-history provenance says what the
document was drawn from.

Found on the way: `synthesize` and `ssp` labelled a multi-catalog run with
"licensed if any input is, otherwise the first input's class", so 800-53
listed ahead of an organization-internal catalog marked the whole synthesis
public domain. Both now take the most restrictive class of their inputs.

### Four smaller findings from the same review

**A refusal is the whole reply, not a token found in it.** Zardoz treated any
reply containing `INSUFFICIENT_CONTEXT` as a refusal, so a model that
answered the supported half of a question and named the gap with the token
had the cited half thrown away, and so would a reply quoting a passage that
carried it. Now only a reply that *is* the token — give or take backticks,
quotes or a full stop — refuses; the token inside prose keeps the answer
and adds a warning. Measured before keeping it: no answering outcome moved
on either model tested, and a half-answerable question asked ten times drew
no sentinel inside prose at all, so this guards a failure that is rare
rather than one that was seen. `MEASUREMENTS.md` epoch 8 has the numbers.

**A section number is not a control.** "What does section 4.2 say?" worked
and "section 4.12" returned nothing: `4.12` has the shape of a HITRUST
objective, no document cited it, and naming a control nothing cites is an
immediate empty result — so any generated Standard with ten or more
subsections could not be asked about its later ones. `192.168`, `1.06` and
`100.00` were read the same way. A HITRUST- or CFR-shaped token now gates
retrieval only when a cue sits just before it (`HITRUST`, `CSF`, `CFR`,
`HIPAA`, `§`, a source tag) or the corpus actually cites it. NIST
identifiers keep the gate, and a cued identifier nothing cites is still an
honest empty result.

**The ledger knows which question a Zardoz call answered.** Zardoz calls were
recorded with no subject, so a challenged answer's record named the model
and nothing about what it was asked. Every call a turn makes now shares one
scope, `site: zardoz.answer`, named for the session and, once the question
is resolved, a digest of it — never its text.

**CI runs with the least privilege it needs.** `ci.yml` had no `permissions`
block, unlike the other workflows, so it ran with the repository default.
It now declares `contents: read` and `pull-requests: read`, and gitleaks'
PR comments — the only thing that needed write access — are off; a leak
still fails the job. The other half of that finding, a hashed lockfile
installed with `--require-hashes`, is not done: resolving one for CI's
Linux and Python 3.12 from here needs a cross-platform resolver this
repository does not yet use.

### A publish no longer destroys an edit made on the wiki

`export_to_confluence` read the live version and incremented it, so a
publish always won. With `publish --apply` running in CI on every merge, an
edit somebody made on the wiki last week was overwritten the next time an
unrelated document changed, and nothing reported it.

The review's suggested fix — record the page version in frontmatter at
publish time and compare — does not survive CI: the publish job runs on a
checkout it cannot commit to, so the recorded number would fall one behind
after every publish and the next would refuse forever. Every write this
tool makes is now stamped instead, with a marker in the Confluence version
message, and `pull` records the version it brought in. `publish` overwrites
a page only when its latest version carries the stamp — nothing has touched
it since this tool wrote it — or equals the version the repository pulled,
so a person has already reviewed that edit as a diff. Anything else is a new
outcome, *moved*: reported in its own section, not overwritten, and failing
the run even when other pages published, so a CI job goes red where it used
to go green over the damage. `--force` overwrites anyway. The edit path's
`update_page_body` stamps its writes too, so an approved edit is not later
mistaken for a hand one.

**Pages published before this change carry no stamp.** Until each is pulled
once or published with `--force`, a publish reports it as moved rather than
overwriting it — the safe direction, but it means the first CI run after
upgrading will fail on every existing page.

## 1.0.0

The release that makes the policy set answerable.

Until now PolicyForge was a one-shot pipeline: a command ran a stage and
exited. It could draft a Standard from cross-mapped controls and publish it,
but the moment somebody asked *what does our access review cadence actually
say*, the tool had nothing to offer and the answer lived in whatever page
they could find. This release adds the read side, and enough of a content
pipeline underneath it that the read side has something trustworthy to read.

### Zardoz, a conversational read side

`policyforge zardoz` opens a shell over the documents you publish. Questions
about a compliance programme come in runs — "what's our review cadence?",
then "who owns that?", then "does it satisfy the HIPAA citation?" — and each
one is cheap to answer and expensive to re-ask from a cold command line.

Two rules hold across the whole package:

- **Answers are grounded or absent.** Every claim cites the document and
  section it came from, citations are verified against the passages actually
  retrieved, and "the documents do not say" is an expected outcome rather
  than a failure. A confidently wrong answer about your own policy is worse
  than no answer, because somebody acts on it.
- **Zardoz never writes.** It can draft an `edit-topic` command for you to
  run, but the publish path is unreachable from this package's import graph,
  and a test walks the AST to prove it.

What it does:

- **Corpus** — a local snapshot of the document tree and/or Confluence,
  carrying two confidence levels. A *trusted* document knows who is
  accountable for it; a *supporting* one is real content nobody has claimed,
  which answers may draw on and must say they did.
- **Retrieval** — BM25 over heading-delimited chunks, with control
  identifiers (`AC-2`, `164.312(a)(1)`, `01.a`) scored by exact equality
  rather than tokenized into fragments, stemming so a question meets its own
  document, and paraphrase expansion when a result comes back thin.
- **Answering** — grounded generation with post-hoc citation and quotation
  verification, refusal when the passages do not support a claim, and a
  correction path when a question's premise contradicts the documents.
- **Follow-ups** — a question resolved against the turns before it, so "who
  owns that?" knows what *that* is.
- **Skills** — read-only analyses for the questions no document answers:
  coverage, undecided parameters, catalog drift, document history, tree
  health, framework licences, HITRUST catalog contents. The model routes and
  the report speaks: a skill's output is printed verbatim, because a
  paraphrase of "14 orphaned controls" can become "mostly in the audit
  family" with nothing to check it against.
- **Discovery** — propose a topic registry from an uncatalogued Confluence
  space.

### HITRUST CSF, as bring-your-own-content

`policyforge etl-hitrust` reads your own licensed MyCSF export — CSV, TSV,
XLSX, HTML or MHTML — and parses it in memory. Nothing is bundled, nothing
is fetched, and nothing is written without `--out`, which refuses
`data/frameworks/` outright and refuses any path git would not ignore unless
your config declares `frameworks.allow_licensed_in_repo`.

`ingest/hitrust.py` holds what the framework *is* — the Category → Objective
→ Control Reference → Requirement hierarchy, the split between a 1/2/3
maturity ladder and sixty-odd regulatory overlays selected by scoping
factors, and the per-requirement crosswalk into some ninety authoritative
sources. `ingest/hitrust_export.py` holds what a MyCSF rendering looks like,
including the column detection that survives SSRS textbox names.

`Requirement` is new in the schema, and is not `ControlEnhancement`: an
800-53 enhancement adds rigour to a control everyone shares, while a HITRUST
overlay is a parallel statement selected by a regulatory factor.

### Content pipeline

- **Content tree** — a tree of markdown documents as the model, with
  `check` reporting broken cross-document links, two files publishing to one
  page, and missing frontmatter before anything is published.
- **Confluence, both directions** — `import-confluence` reads pages this
  tool did not write; `edit-topic` edits live pages from a plain-language
  instruction; `export-confluence` publishes.
- **Publishing from CI** — `check` runs on every pull request with no
  credentials, so it works on a fork's PR. `publish` runs only after a merge
  to the default branch and lives behind an environment, because a workflow
  that could write to a live wiki from an untrusted PR is a supply-chain
  problem rather than a convenience.

### Frameworks and parameters

- **Drift** — `policyforge drift` reports what a framework update changed
  and which of your topics, documents and recorded decisions it reaches. A
  monthly workflow runs the ETL and diffs it against the committed catalog,
  because NIST republishes the OSCAL catalog without telling you.
- **Parameter ledger** — one recorded decision per organization-defined
  value, so a threshold chosen once is not re-chosen differently in the next
  document.
- **Licence registry** — a framework directory declares its terms, anything
  undeclared is treated as licensed, and `check` fails when a licensed
  catalog is committed to a repository that has not declared the right to
  hold it. The declaration is config, because only the repository owner can
  make it.
- **Roles** — tools and teams keyed by role and filled in deterministically,
  rather than by the model.

### Grading the prompts

Four things in Zardoz are prompts, and a prompt cannot be tested against a
fixture. `scripts/eval_zardoz.py` grades answering, follow-up resolution,
paraphrase expansion and skill routing against a real model, over phrasings
the author did not choose and whole conversations rather than single turns.
The suite is itself measured by deleting the rules it grades and checking
that the score moves. One run is not evidence, so cases are repeated.

### Robustness

Fuzzing over every function that parses text nobody sanitised; a typography
table spelled in code points rather than in characters indistinguishable
from each other; a config file that is empty or not a mapping refused rather
than half-read; and test coverage extended to the modules no test imported.

### Notes

- The version was `0.1.0` and is now `1.0.0`. This is the first tagged
  release; there is no upgrade path to document.
- HITRUST CSF and GovRAMP remain content you supply under your own licence.
