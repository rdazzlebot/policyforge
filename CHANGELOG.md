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

**The model-side half is unmeasured.** The fence and the contract sentence
change the answering prompt, and this project's own evidence is that a prompt
change helping one model can cost others five and six points. The eval cases
exist so that sweep is a command rather than a project; it has not been run.

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
