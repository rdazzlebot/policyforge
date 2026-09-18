# Changelog

## Unreleased

### The ledger can see what was removed from a reply, not only what was billed

- **`stripped_reasoning_chars` records how much inline reasoning was cut
  before a reply was stored.** The pair to `hidden_output_tokens` from the
  other side: that field is what the vendor says it billed and did not
  return, this is what arrived and was not kept. Until both existed
  neither was recoverable after the fact — a reply came back, its
  `<think>` preamble was removed, and the ledger stored the remainder with
  nothing to say a cut had happened, so "did this model spend most of its
  reply thinking?" needed a fresh run to answer and a fresh run is a
  different run. Populated by the two providers that strip, `local` and
  `litellm`. Characters rather than tokens, because characters are exact
  here and a tokenizer is not carried for every model; the field answers
  how much was removed, not what it cost.
- **Unknown and zero stay apart, as on the token counts.** None means the
  provider does not strip at all, zero means it stripped and found
  nothing. A zero asserted on behalf of a provider that never looked is a
  measurement nobody made.

### Gemini, with a key from AI Studio

- **`provider: gemini` calls Google's own models with an API key**, at
  `generativelanguage.googleapis.com`, with no cloud project and nothing
  to install. It is deliberately not the `vertex` provider with a
  different endpoint: that one serves *Claude* models in Google Cloud
  through Anthropic's client and has nothing to do with Gemini, which is a
  confusion the docs now name explicitly in both places.
- **Capability flags describe what this provider sends, not what Google
  offers.** Structured output is implemented and the request carries the
  schema, so `supports_schema` is true; effort, caching, grounding and
  batch are not implemented and say so in the code with the reason, each
  one a deliberate false rather than an inherited one.
- **`max_tokens` means tokens of answer, which took a live call to get
  right.** Gemini counts a model's own thinking against `maxOutputTokens`
  and returns none of it, so a 64-token budget spent 60 on reasoning and
  came back with no content at all — the truncation guard firing correctly
  on a call that could never have produced anything, which reads as a
  guard defect and would be "fixed" by removing the guard. The provider
  now sends a zero thinking budget on every call, so the caller's number
  means what the caller meant. Translating a vendor quirk into the
  interface's contract is the adapter's job: the alternative is every
  caller and every budget learning that one vendor thinks.
- **Thinking tokens reach the ledger**, through the
  `hidden_output_tokens` field, so a call that bills for reasoning is not
  recorded at a fraction of its cost. Where the count is absent — which is
  what the API returns once thinking is off — it stays unknown rather than
  becoming zero, and the same holds for `candidatesTokenCount`, which is
  absent rather than zero on a reply cut off before its first content
  token. That distinction is
  the lesson from `bedrock`, which declares nothing at all and therefore
  silently dropped every hint a capable model could have used.
- **Held to the same boundary as every other hosted provider.** `gemini`
  is named in the content-class ceiling rather than left to the
  fail-closed default, so licensed content cannot reach it; the endpoint
  is in the declared allowlist with its reason; the key is read only
  through the declared credential reader; and the transport contract test
  drives Gemini's own wire shape — `finishReason: "MAX_TOKENS"` inside the
  first candidate — through the real parsing path, because a fake that
  sets the field proves nothing.
- **A blocked reply is an empty reply, not a crash.** Gemini answers a
  safety block with HTTP 200 and no candidates at all, a shape no other
  provider here produces, so it is read as empty text and refused by the
  usual empty-reply guard.
- **The free tier is named as a question, not answered.**
  `docs/subprocessors.md` gains a row whose confirm column says which tier
  a key is on matters, because Google's terms have historically treated
  free and paid keys differently on whether prompts may improve their
  products, and those terms are theirs to change. The page does not
  characterise what Google does, which is its standing rule.

### The ledger can see output tokens you paid for and cannot read

- **`LLMResponse.hidden_output_tokens` and a matching ledger column record
  tokens billed as output that never appear in the reply.** A reasoning
  model charges for its own thinking; measured on a live Gemini call, 842
  such tokens sat beside 813 returned ones, and on a schema-constrained
  call 292 beside 12. Until now the ledger recorded only the returned
  half, so a cost figure produced through such a provider was a floor
  presented as a total — silently, and by a ratio that varied per call.
  The ledger is a compliance artefact and the published cost measurements
  are built from it, which is why this is a defect rather than a rounding
  question.
- **None and zero stay different answers.** The field defaults to None,
  meaning the provider does not report such tokens, which is every
  provider here today. Zero means it reports them and there were none.
  Defaulting to zero would have asserted "nothing was hidden" on behalf of
  providers that cannot tell. The run summary prints a hidden-token column
  only where some call in the group actually reported one, for the same
  reason.
- **Not a Gemini property.** Gemini is the first provider here to surface
  the count, not the first whose model thinks: the same tokens are billed
  behind LiteLLM or an OpenAI-compatible endpoint and reported by neither,
  so their ledger entries stay honestly unknown rather than falsely zero.

### The subprocessors page no longer characterises a third party

- **`docs/subprocessors.md` said content routed through LiteLLM goes to
  "commonly OpenRouter".** Two paragraphs above, the same page states that
  it cannot attest to any third party's terms and that the "you must
  confirm" column is its actual deliverable — so the row broke the page's
  own rule by describing how another company commonly routes. That is
  worse than an undated claim: this page's whole value is that a careful
  reader can trust it, and a reader who spots the contradiction has been
  handed a reason to doubt the rest. The row now reads "Whatever LiteLLM
  routes to, which may itself route to further providers", which loses
  nothing it needed to say.

### Positioning names a category, not companies

- **The competitive comparison no longer names vendors.** `positioning.md`
  described five named platforms with links and quoted marketing copy;
  it now describes the category in the terms those products use about
  themselves, and says plainly why the names are absent — the distinction
  is about what a kind of tool is for, it does not get sharper by naming
  anyone, and a named comparison dates the moment one of them rewrites a
  page. The three passing mentions elsewhere, in the README, the skill
  file and a `history/version_store.py` docstring, now say "a GRC
  platform". Note that git history is unchanged: the names remain in
  earlier commits, and rewriting published history is not something this
  project does.

### A claim is judged whole, or the judge is answering about debris

- **The entailment check split claims on every full stop, including the
  ones inside `Section 4.2`, `164.308(a)(3)`, `45 C.F.R.`, `Rev. 5`, `e.g.`
  and `99.9%`.** Each break cost two things and only one was visible: the
  judge was handed a fragment such as `2 of the Standard`, reported it
  unsupported, and that appeared in the finding list as a false positive —
  while the claim the fragment was carved out of was never judged at all,
  and that appeared as nothing. A claim never examined is indistinguishable
  from one that passed. Measured on a real run over the Zardoz eval suite,
  26 of the 42 findings carrying claim text were fragments, so most of the
  finding list was the splitter reporting on itself. The rule now breaks
  only at a terminator that ends a sentence — at the end of the text, or
  followed by whitespace and something that starts one — which leaves
  decimals, abbreviations, legal references and quoted spans intact. It
  deliberately splits on fewer things than before: under-splitting merges
  two claims into a coarser unit and both are still judged, while
  over-splitting drops claims silently, so the failure direction is chosen
  rather than inherited. A legal reference is the case it is designed
  against, not a decimal: `45 C.F.R. 164.312` is how every HIPAA citation
  is written, and a rule special-casing digit-dot-digit would have left the
  framework this tool exists to handle broken while looking fixed. The
  tests are built from the fragments the real run recorded, and each one
  asserts the whole claim comes back rather than only that no fragment
  does. One exception to the pattern, for an initial followed by a
  capital: `The U.S. Department of Health and Human Services enforces it`
  reads as two sentences by every other rule here, and that phrase is in
  essentially every HIPAA document. A sentence ending in an acronym
  (`Contact the CISO. The lead reviews it`) still ends, because the
  exception is for a one-letter token.
  Found by policyforge-b5 while measuring the entailment check;
  widened by policyforge-ba and policyforge-1d.

### Publish to a wiki from CI

- **A `publish-wiki` job in `content.yml`**, behind its own `github-wiki`
  environment and fenced the way the Confluence job is: only on a push to
  the default branch, only from this repository, only when
  `vars.WIKI_REPOSITORY` is set, and `needs: check`. The push condition is
  stated in the job rather than left to the trigger list, so a trigger added
  later cannot hand a fork a write path. It plans before it applies, and the
  plan's first line records what the job believed about who can read those
  pages.
- **The token is a secret on that environment, never the workflow's built-in
  `GITHUB_TOKEN`** — that one is minted for every run of every workflow, and
  write access to a policy set should be a credential granted for the
  purpose. The job passes no `--allow-public`, `--force` or `--allow-macros`.
- **`--token-env` on `publish`, `wiki-drift` and `pull`** names the variable
  holding that token, for a runner with no config file to read
  `publish.github_wiki.token_env` from. The name travels on the command
  line; the value stays in the environment.

### Publish to a GitHub wiki, through the same guards as Confluence

- **`policyforge publish --target github-wiki` writes your content tree to a
  GitHub wiki**, which is a git repository of markdown pages. The three
  guards are the ones Confluence already has, answered from git: a page is
  overwritten only when this tool wrote its last commit, or when `pull`
  recorded that sha in the document, or when the file already says what the
  repository says. Anything else is reported as moved, with the author and
  date from `git log`, and fails the run. `wiki-drift` and `pull` take
  `--target` too, so the reconcile loop closes the same way.
- **Two rules stand between a wiki and your documents.** The plan's first
  line says whether the wiki is public, every run; publishing to a public
  wiki — or to one whose visibility could not be determined, which counts as
  public — needs `--allow-public`. And a document carrying
  `content_class: licensed`, in its frontmatter or in the provenance stamp
  `generate` writes, is never published to a public wiki whether or not that
  flag is passed. An unrecognised class is treated as not licensed, which is
  deliberate and documented in `export/github_wiki.py`: the ceiling holds
  where the class is said, and the visibility rule stands between an
  unstamped document and the world.
- **A byte difference on the wiki is a change**, unlike Confluence, which
  reflows storage format when it saves. Trailing newlines are the one
  exception, because every GitHub editor adds one.
- **Cross-references are rewritten both ways**, tree paths to
  `[[Page Title]]` on publish and back on pull. A link to a document with no
  wiki page is left as written and reported once.
- **A page in a format this tool cannot round-trip is refused by name** —
  AsciiDoc, RST and the six others GitHub wikis accept — the way Confluence
  macros are.
- Configure it with `publish.target` and `publish.github_wiki.repository`;
  each document then declares `targets.github_wiki`, which may be empty to
  mean "this wiki, under this document's title". A file with no such block
  is not published.
- The token reaches `git` through `GIT_CONFIG_*` environment variables, so
  it never appears on a command line, in the clone's `.git/config`, or in an
  error quoting the remote. Without `token_env`, git uses your credential
  helper. The working clone lives in `output/.wiki/`, gitignored.

### Checks

- **`check` reports a Standard or Procedure that cites no framework
  requirement at all.** The tag is the whole traceability story — how a
  document says which control it answers for, and how `satisfies`, the
  drift report and the edit path find it — so a Standard carrying none is
  not weakly traced, it is untraced, and the two ways that happens are
  both worth seeing: a generation cut off part-way, or citations written
  and then lost in an edit. Tier-scoped, and the scoping is the check: all
  nineteen Policies in the bundled 20-topic starter set cite nothing by
  design, so an unscoped rule would report nineteen correct documents
  beside the two wrong ones and be switched off inside a week. Measured on
  that set: two flagged, both real — a Standard truncated mid-sentence at
  1,066 bytes and a full-length Procedure whose tags are simply absent —
  and nineteen Policies silent. Both were found by hand during the
  citation-measurement reconciliation; this is that finding made
  mechanical. A warning, never an error: a hand-written Standard not yet
  mapped to a framework is a normal thing to have mid-migration. It reads
  tags through `content/tags.py`, so a citation the old framework-name
  list could not see now counts as one.

### Fixes

- **The `etl-*` commands write catalogs with LF on every platform.** The
  eight `controls.json` writers, the two `framework.yaml` provenance
  stamps and the generated BYOC parser sources went through `write_text`,
  which on Windows emits CRLF into files that are committed under
  `data/frameworks/` — a whole-file diff on the next `git status`, and the
  reason the provenance hash had to normalise line endings before
  comparing. They go through `write_text_lf` now, like every markdown
  writer since 1.2.1, and the two modules join the LF writer list the test
  suite sweeps. The hash keeps normalising: a checkout with
  `core.autocrlf=true` still hands it CRLF bytes.

### Evals

- **The eval report says, per run, why each reply stopped and how long it
  was.** The truncation re-measure had one `length` stop in 200 calls and
  no way to tell whether it was the run that failed: the harness recorded
  pass or fail, the ledger recorded stop reasons, and nothing joined them.
  The meter now keeps every reply's stop reason, output tokens and model;
  `run_case` attaches each run's slice to its outcome; a failed case's
  first failure prints `replies: stop=length out=1019, ...`; and the
  summary counts the runs that had a reply cut off at its budget — said
  even when every case passed, because a reply that stopped at its budget
  and was retried into a pass is a budget one paraphrase from a failure.

### Budgets

- **The answering budget is 2048 output tokens, from 1024, and named.**
  `zardoz/budgets.py` gains `ANSWERING_TOKENS`, overridable with
  `POLICYFORGE_ANSWERING_TOKENS` like the other short-call budgets. Sized
  from the truncation re-measure (200 calls at 553d430): deepseek-v4-flash
  used 1019 and 967 of 1024 on two answering cases and glm-5.3-flash at
  most 515 — nothing cut off, but two cases within five tokens of the cap.
  A cut-off answer has been refused rather than shown since 1.2.1, so the
  headroom costs nothing until a model uses it. The request shape is
  otherwise unchanged; the answering suite's next epoch is the one to
  compare against.

### Tests

- **A new document producer cannot write an empty body unnoticed.**
  `tests/test_document_text_guard.py` walks the modules that write model
  replies as documents — synthesis, the three document tiers, the edit
  rewrite — and requires every function that makes a model call to pass
  the reply through `effort.document_text`, the check that refuses an
  empty reply (1.2.1). Every other module under `src/` that reads a
  reply's text must be listed with the reason its empty reply is handled
  another way, so a module that starts writing a document is caught the
  day it is written; the sweep found one reader the first list missed.

### A provider's rejection reaches you as a sentence, not a traceback

- **A 4xx from the model's API now says which call, which budget and
  what the vendor said.** With document budgets at 16384 since 1.2.1, a
  model whose output cap is lower rejects every draft, and until now that
  arrived as an SDK traceback ending in "HTTP 400". Each provider raises
  `ProviderRejected` with the vendor's own message — Anthropic's and
  Vertex's `BadRequestError`, LiteLLM's, a 4xx from an OpenAI-compatible
  server, a Bedrock `ValidationException` — `llm/effort.py` adds the
  ledger subject, the site and the budget the request carried, and the
  CLI prints that and exits non-zero with nothing written, the way it does
  for a truncated or empty reply. The budget is never clamped silently:
  the message tells you to lower it for that call site or choose a model
  that accepts it. A 5xx, a throttle or a credentials failure is not a
  rejection and is raised as before.

### A cascade advertises what both of its halves can do

- **`provider: cascade` forwards every capability flag, by one stated
  rule: a flag is true only when both halves honour it.** Which half
  answers is decided by a runtime failure after the request is built, so a
  caller promised a capability has to get it from whichever half answers.
  Until now the cascade forwarded `supports_schema` and let effort,
  caching, grounding and batch fall to False, so a flash-to-pro cascade of
  two capable models sent no effort level, marked no cache prefix and
  asked for no citations — the same silent loss the ledger wrapper had in
  1.2.0, one layer up. Effort and cache hints now reach whichever half
  answers, and a grounded call escalates the way a plain one does.
  `supports_batch` stays False on a cascade by design: a batch is one
  submission with nothing to escalate on, and `ssp --batch` says to
  configure the batching provider directly. A local-plus-hosted cascade
  therefore advertises the local half's capabilities, and `llm-check`
  prints that table so the trade is visible; a test builds such a cascade
  through `get_provider` and holds every discovered flag to the rule.

### One interface between the tree and a live page store

- **`publish`, `wiki-drift` and `pull` run through `export/publisher.py`,
  a `Publisher` interface with Confluence as its first adapter.** The
  three guards — a page the round trip would flatten is skipped by name, a
  page somebody edited since the last publish is reported as moved, a dry
  run reads and never writes — are stated once over a `LivePage` rather
  than in Confluence's terms, so a second kind of store (a GitHub wiki is
  next) gets the same rules rather than a copy of them. No behaviour
  changes for Confluence: `tests/test_publisher_equivalence.py` runs every
  scenario the content/git tests exercise through the loops as they stood
  before and through the new ones, and holds the reports and the exporter
  calls identical, argument for argument. A document may now declare its
  destinations under `targets:` keyed by kind, and a topic in the registry
  likewise; `confluence:` at the top level stays as the alias of
  `targets.confluence`, and `check` reports a file carrying both with
  different contents. A pulled page is still written with `confluence:`
  at the top level, so a tree pulled by this version reads the same under
  the previous one.

### A citation tag is recognised by its shape, not by a list of names

- **Every reader of `[NIST AC-2 | HIPAA 164.308(a)(3)(i)]` tags now takes
  one pattern from `content/tags.py`.** The edit path (refuses a revision
  that dropped a tag), `check` (reports a tag the synthesis carries and the
  document lost), `frameworks/drift` (finds the documents a changed control
  reaches) and the deontic analysis (which sentences claim to implement a
  control) each carried a hand-written list of framework names, and the
  bundled starter set writes `[ARC PE-1 ...]` where the lists said
  `ARC-AMPE`: twenty-two tags, thirty-one citations, invisible to all four
  at once and counted by `satisfies` only as a stated floor. A tag is now a
  capitalised framework name followed by a requirement identifier carrying
  a digit, never a link. Measured over every document and catalog in the
  repository: the shape matches every tag the lists matched, adds none, and
  stops treating six prose brackets such as `[NIST AI RMF alignment]` as
  citations, which they never were. A test holds the four readers to the
  one object so a private copy cannot grow back. The same rule corrects a
  false positive nobody had noticed: a placeholder that opens with a
  framework name, `[HIPAA Documentation Review Frequency]`, sitting
  mid-sentence beside `[Ticketing System]`, matched the old list because
  `HIPAA` was on it and was published as the starter set's least followable
  citation; with the identifier rule it is the placeholder it always was,
  and the residual count is 33 of 4,090.

### Repository hardening

- **The gate refuses to run against a `policyforge` that is not the tree
  it was started from.** The editable install writes the absolute path of
  the checkout it was made in, so `scripts/check.py` or a bare `pytest` run
  inside a git worktree imported the main checkout's source and reported
  all-pass on a branch whose code was never loaded. Four review sessions
  accepted such a pass on the same day. `scripts/tree_guard.py` resolves
  the package before anything runs and, when it lies outside the invoking
  tree's `src/`, stops with exit 2 naming both paths and the
  `PYTHONPATH=<tree>/src` invocation that fixes it; `tests/conftest.py`
  does the same for pytest before collection. A main-checkout run, CI and
  the Docker gate are unaffected: each installs the package from the tree
  it tests.
- **The Confluence publish job skips unless a wiki is configured.** This
  repository has no `CONFLUENCE_HOST` and no credentials, so every push
  touching `docs/` failed at the Plan step and left a red workflow on `main`
  that means nothing. It now runs only when the variable is set, with a
  comment saying publishing is off until then, so a skipped job is not read
  as a successful publish. The `check` job still runs on every pull request.

## 1.2.1

A correctness release. Nothing new to learn, one thing to check.

**If you generated documents with 1.1.0 or 1.2.0, check them for
truncation.** Those versions saved a model reply that stopped at its output
limit as if it were finished: a synthesis or document cut off mid-sentence,
written with exit 0 and no warning, so anything built from it silently lacks
the requirements that were cut. 1.2.1 retries once with a larger budget and
otherwise refuses, naming the document, without writing anything.

Every model call is in the call ledger, on by default at
`output/.model-log/calls.jsonl` (or wherever `llm.ledger.path` points).
`policyforge model-log` shows totals but not why a call stopped, so search the
file for cut-off calls:

```bash
grep -E '"stop_reason": *"(length|max_tokens)"' output/.model-log/calls.jsonl
```

PowerShell:
`Select-String -Path output\.model-log\calls.jsonl -Pattern '"stop_reason": *"(length|max_tokens)"'`

`length` is how LiteLLM and OpenRouter report it; `max_tokens` is
Anthropic's, Vertex's and Bedrock's. For each matching line:

- `"site": "synthesize"`, `"subject": "synthesis/<topic>"`: that topic's
  synthesis is incomplete. Regenerate it, then every Standard, Policy and
  Procedure generated from it.
- `"site": "generate"`, `"subject": "<tier>/<name>"` (for example
  `standard/access-control`): that document is incomplete. Regenerate it.
- `"site": "ssp"`: the SSP narrative for the control named in `subject`
  (`ssp/<system>` for a batch run). Regenerate the workbook.
- `"site": null` and `"subject": null`: an edit (`edit-topic`,
  `edit-confluence`), which 1.2.0 didn't attribute. Match its `timestamp` to
  the edit you ran, and review that revision before it's published.

**An empty reply was also saved without warning**, and it leaves no signal in
the ledger (its stop reason is a normal `stop`). Look for a synthesis or
document file that has frontmatter and nothing after it, and regenerate it.
1.2.1 refuses an empty document reply by name.

Not covered by the search, all of it about what 1.1.0 and 1.2.0 recorded
rather than what 1.2.1 detects: runs on the `openai-compat` provider (a local
server such as Ollama, vLLM or LM Studio), which those versions did not
record a stop reason for at all; runs with `llm.ledger.enabled: false`; and
anything generated with 1.0.0, which had no ledger. For those, regenerate
large topics, or read the end of each file for a sentence that stops mid-way.

**1.2.1 detects a cut-off reply on every provider**, including
OpenAI-compatible and local servers, which is the setup the documentation
recommends for licensed content. A contract test holds each provider to its
own vendor's signal — `stop_reason`, `stopReason` or `finish_reason` — by
driving it with a fake at its SDK or transport boundary, so a provider that
stops reporting truncation fails the suite rather than writing a short
document.

**What changes in use:** synthesis, Standards and Procedures now request up
to 16384 output tokens, retried once at 32768. That was verified on
glm-5.3-flash and deepseek-v4-flash through OpenRouter. A provider or model
with a lower output cap may reject the request.

Also in this release: config files read as UTF-8, ASCII help text, `pull` no
longer reporting unchanged pages as changed, the test suite and provenance
stamps on Python 3.10, and the test suite now running on Windows and macOS in
CI.

### A reply cut off at its budget is refused, not written

- **1.1.0 and 1.2.0 wrote cut-off replies as finished documents.** The
  first 20-topic cost run found that a reply the model stopped at its
  output budget was written to disk with exit 0 and no warning: 11 of 20
  syntheses stopped at the 4096-token default (one ended "...(PII) and
  support"), 4 of 60 drafts stopped at 8192 (a risk Standard ended "shall
  make risk"), and every Policy and Procedure drafted from a truncated
  synthesis silently lacks the requirements it never saw. It applied to
  every provider. How to find affected documents is at the top of this
  release's notes.
- **Now, centrally:** `LLMResponse.truncated` normalises every vendor's
  spelling, and `llm/effort.py` — the one path every model call takes —
  retries a cut-off reply once at twice its budget (capped at 32768) and
  raises `TruncatedResponse` if it is still cut off. The CLI group turns
  that into a non-zero exit naming the document and the budget, so every
  command is covered, including ones written later. No writer writes
  before its model calls return, so nothing partial is left on disk; both
  billed calls are in the ledger.
- **Detection covers the OpenAI-compatible provider as of this change.**
  `provider: openai-compat` / `local` — Ollama, vLLM, LM Studio, the setup
  recommended for licensed content — never carried `finish_reason` into
  `stop_reason`, so the first version of this fix could not see a cut-off
  reply there and still wrote it. It does now, and a contract test builds
  every provider the factory knows with a fake at its SDK or transport
  boundary returning that vendor's own cut-off shape, so a provider that
  drops the field fails in CI rather than in a user's `output/`.
- **Budgets sized from the run.** A synthesis that completed used up to
  13,569 output tokens on the recommended model (a reasoning model spends
  part of the budget thinking, and the ledger counts both), so synthesis
  gets an explicit 16384 instead of the 4096 default. Standards and
  Procedures ran a p90 of about 8,000 against an 8192 budget with two of
  twenty cut off each, so both move to 16384. Policies stay at 4096: the
  largest was 1,104. Each figure sits beside the constant it justifies.
- **An empty document reply is refused too.** Found by the live check of
  the new budgets: glm-5.3-flash answered the Incident Response synthesis
  with 4,869 output tokens, a normal stop and no content at all — the
  tokens went into its reasoning channel — and the synthesis was written
  as frontmatter with no body, exit 0, so the next `generate` failed on an
  empty file. Synthesis, the three document tiers and the edit rewrite now
  refuse an empty reply by name (`EmptyReply`), with the same clean exit
  and nothing written. Routing and expansion calls are not held to this:
  an empty reply there is a decision the caller reads.
- **No silent fallback.** The four Zardoz routing calls that went to the
  provider directly now go through the helper, and their catch-all
  handlers re-raise a truncation instead of routing to the documents;
  query expansion does the same. In the eval harness a truncated reply
  grades as a failure with the reason `truncated at N tokens`, never as a
  pass and never as infrastructure noise. Batch SSP narratives are
  checked by control id, since a batch cannot be retried one item at a
  time.

### Fixes

- **`config.yaml` is read as UTF-8 on every platform.** It was opened with
  the system default, so on Windows an organization, vendor or team name
  outside the console code page was mis-decoded into generated documents or
  failed to load.
- **`pull` no longer reports an unchanged page as changed.** A page whose
  Confluence body carried a carriage return compared as different on every
  pull, was rewritten identically and reported as written.
- **Help text is plain ASCII.** The banner and 38 other help strings carried
  an em-dash that some Windows consoles showed as a replacement character.
  A test now refuses non-ASCII characters in command and option help.
- **The test suite and `etl-*` provenance stamps work on the declared
  Python 3.10 floor.** Provenance used `datetime.UTC` (3.11+), and the tests
  imported `tomllib` (3.11+). CI still tests Python 3.12 only.

### Documentation

- **`config/config.example.yaml` shows all six providers**: anthropic,
  bedrock, vertex, openai-compat, litellm and cascade, with which of them read
  `api_key_env`. A test builds every example block, so a new provider without
  an example fails.
- **CONTRIBUTING says the request capture covers LiteLLM-backed runs only**,
  and asks a pull request to say how a change to the other providers was
  checked.

### Repository hardening

- **The test suite runs on Windows and macOS in CI**, as a
  `pytest-platforms` job beside the Linux job, on Python 3.12 from the same
  hashed lock. Two Windows-only defects had reached `main` with the Linux job
  green. The scanners stay on Linux only.

## 1.2.0

**Upgrading from 1.1.0 changes what your model is asked for, and can change
what it costs.** 1.1.0 shipped with a bug in the call ledger that silently
switched off provider capabilities for every provider built from config: no
effort level on Anthropic, Vertex or LiteLLM (including OpenRouter), no
native citations and no prompt caching on Anthropic and Vertex, and
`ssp --batch` refused on Anthropic. This release sends them. On the same
config, drafts, answers and per-call cost can differ from 1.1.0. Run
`policyforge llm-check` to see the capability line for the provider you have
configured. Bedrock and OpenAI-compatible endpoints advertise none of these
and are unaffected. "The call ledger hid four provider capabilities" below
has the per-provider detail.

**Eval measurements from that window don't describe production.** The eval
harness built its provider around the wrapper, so MEASUREMENTS epochs 15
through 18 sent effort while the CLI did not. Those epochs were recorded
before this fix and aren't yet annotated in `MEASUREMENTS.md`. The harness
now builds its provider through the same path as every command, with a test
holding the two to parity.

Also in this release:

- **A container image, a dev container and CI's checks in Docker.**
  `docker build -t policyforge:local .` gives the CLI and the MCP server,
  from a hashed runtime lock, as a non-root user. See "Running in a
  container" in the README.
- **`policyforge frameworks` exits 1 when it finds no catalog**, and tells
  you to run `policyforge init`. Inside a project nothing changes.
- **Generated Markdown is written with LF line endings on Windows**, so
  files `generate`, `pull` and `edit-topic` write pass the repository's own
  Markdown check.
- **The eval generation cases are graded the way the CLI generates**, with
  role substitution applied.
- **`scripts/capture_eval_requests.py`** records every request an eval run
  sends and compares two captures, so a change to the harness or `llm/` can
  be shown not to change what a model is asked.

### Request captures for the eval harness

- **`scripts/capture_eval_requests.py`** records every request the eval
  harness would send, with `litellm.completion` replaced by a recorder, and
  `--compare` diffs two captures. It is how the harness change below ("The
  eval harness builds its provider the way production does") was shown to
  leave the harness's requests byte-identical, and CONTRIBUTING now asks
  for a capture before and after any change to what the harness sends —
  a pass rate cannot show that two runs asked for different things.

### The call ledger hid four provider capabilities

- **`RecordingProvider` now forwards every `supports_*` flag to the provider
  inside it**, and `generate_grounded` passes through and is recorded the
  way `generate_json` already was. The wrapper relied on `__getattr__` to
  reach anything it did not define, and `__getattr__` is consulted only
  when normal lookup fails — but every `supports_*` flag exists on
  `LLMProvider` as `return False`, so the four the wrapper did not override
  (`supports_effort`, `supports_caching`, `supports_batch`,
  `supports_grounding`) answered False for every provider, whatever the one
  inside would have said. `get_provider` wraps every provider and the ledger
  is on by default.
- **What that meant in practice, from 7241d90 (2026-09-14) until this
  fix:** every provider built from config lost those four flags, because
  every one of them comes back from `get_provider` wrapped. Every provider
  that advertises effort — Anthropic, Vertex and LiteLLM, the last being
  the recommended default and the OpenRouter path — sent no effort level on
  any call. Anthropic and Vertex, which advertise grounding and caching,
  never requested native citations (the answering path took the
  inline-passages route, the reply carried no citation spans, and the
  citation cross-check received an empty list and could report nothing)
  and never marked a cacheable prefix. Anthropic, the one provider that
  advertises batching, had `policyforge ssp --batch` refused with a message
  telling the user to configure the provider they had configured; Vertex
  does not advertise it, so its refusal is by design. Bedrock and the
  OpenAI-compatible endpoint advertise none of the four and lost nothing.
- **The eval harness was not affected, which is the uncomfortable half.**
  Until the harness change below, `scripts/eval_zardoz.py --model` built a
  `LiteLLMProvider` directly inside its own meter rather than through
  `get_provider`, so its flags
  were read from the real provider and every recorded epoch sent effort.
  The CLI, running the same prompts through the wrapper, did not. The
  measurements in that window describe a request production never made.
  Epochs 15–18 in `MEASUREMENTS.md` were recorded before this fix and aren't
  yet annotated; on the LiteLLM path they reflect a request that sends
  effort, which config-built runs do only from this release.
- **Why the tests passed:** the effort and native-citation tests exercised
  fake providers unwrapped, and no ledger test asked a wrapped provider
  about any flag but `supports_schema`. `tests/test_llm_ledger.py` now
  discovers every `supports_*` on `LLMProvider` and requires the wrapper to
  return the inner provider's answer for each, so a flag added later cannot
  be forgotten — and asks the same of the real composition, building each
  provider the factory can construct offline through `get_provider` and
  comparing every flag against the provider inside. `generate` accepts the
  `effort` and `cache` arguments the flags unlock, which a fixed signature
  would have refused.
- **`policyforge llm-check` prints the capability table** — schema, effort,
  caching, batch, grounding — asked of the provider as configured, wrapper
  included. A downgrade that used to be invisible is now the fourth line of
  the one command everyone runs first.

### The eval harness builds its provider the way production does

- **One construction path.** `scripts/eval_zardoz.py --model` used to
  construct a `LiteLLMProvider` by name and meter it, while every command
  built its provider through `get_provider` and the ledger wrapper. That is
  how the entry above went unmeasured: the harness read its flags from the
  real provider and kept sending effort, and the CLI, through the wrapper,
  did not. Epochs 15 through 18 in `MEASUREMENTS.md` describe a request
  production never made. Now `evals/provider.py` turns `--model` and
  `--min-interval` into overrides on the same config dict production reads
  and hands it to `get_provider`; the meter wraps the result. The mutation
  sweep in `scripts/mutate_zardoz.py` builds its provider the same way.
- **Eval calls have their own ledger, and a label.** They are recorded in
  `evals.jsonl` beside the production ledger — wherever config put it — and
  each call carries `<suite>/<case>` as its subject and `eval` as its site,
  rather than landing in `calls.jsonl` as `(unattributed)`. A ledger the
  config turned off stays off under the harness, since that was a decision.
- **`tests/test_eval_provider_parity.py`** builds every provider the
  factory can construct offline both ways and requires the same provider
  class under the wrappers, the same answer to every discovered
  `supports_*` flag, and the same effort, caching, grounding and schema
  decisions in `llm/effort.py`. A recorded run of the routing suite with
  `litellm.completion` replaced by a recorder sent byte-identical request
  parameters before and after this change, on top of the ledger fix above.

### Repository hardening

- **Containers: a runtime image, a dev container, and CI's checks in
  Docker.** The `Dockerfile` builds the CLI and MCP server from
  `requirements/runtime.txt`, a new hashed lock of the project's dependencies
  and the `mcp` extra at exactly the versions CI tests, with no dev tools. It
  runs as a non-root user from a digest-pinned base, and is documented under
  "Running in a container". Its build context is an allowlist, so licensed
  exports, `.env`, the organization's config and `output/` cannot reach an
  image. `.devcontainer/` opens the repository in CI's environment.
  `scripts/ci_in_docker.py` runs CI's steps on Linux and Python 3.12 from a
  clean clone. It adds lock reproduction, a runtime-lock check and a live MCP
  handshake, then builds the image with private files planted and checks that
  none got in. `scripts/mcp_smoke.py` is that handshake on its own, for any
  server command. `tests/test_container.py` keeps the base images on one
  digest, keeps the allowlist closed, and keeps the runtime lock matched to
  CI's. Dependabot tracks the base image digest.

### `frameworks` outside a project says what to do, and fails

- **Behaviour change: `policyforge frameworks` exits 1 when it finds no
  catalog.** It printed "No frameworks found" and exited 0, which from an
  installed package is the first thing a new user sees before `init`, and a
  script checking for catalogs passed on nothing. The message now names
  `policyforge init` first, goes to stderr, and the exit code says the
  listing failed. Inside a project, including one `init` laid out, nothing
  changes.
- **The sdist no longer ships `tests/`.** setuptools added `tests/*.py` by
  default but not `tests/fixtures/`, so a suite run from the sdist failed.
  `MANIFEST.in` prunes the directory; the sdist is a build input, and tests
  run from a clone.

### Markdown is written with LF on every platform

- **Every markdown and diff writer goes through one function,
  `policyforge/textfile.py`'s `write_text_lf`.** `Path.write_text` opens in
  text mode with universal newlines, and on Windows that turns every `\n`
  into `\r\n` on the way out. Each writer passed `encoding="utf-8"` and none
  passed `newline`, so a Standard drafted on Windows, a page `pull` brought
  down, a revision `edit-topic --apply` wrote into `docs/`, and every copy
  in `output/.history/` arrived with CRLF. `mdformat` rejects a CR, and the
  repository gate runs it over every markdown file: the tool wrote files its
  own check then failed on, on the one platform CI does not run. A CRLF copy
  in the version history also diffed on every line against the LF document
  it was a copy of, and `publish` could compare an unchanged page as changed.
- **`.gitattributes` was not the fix.** `*.md text eol=lf` governs what git
  checks out; it says nothing about what a program writes, and `output/` is
  not tracked. Writers: `export/markdown_exporter.py`, `export/pull.py`,
  `edit/tree.py`, `history/version_store.py`, the `synthesize`,
  `edit-confluence`, `edit-topic` and `import-confluence` commands, and the
  corpus snapshot `zardoz sync` writes — that last one found by the new
  test's sweep over `src/` rather than by the report that prompted it. The
  function also folds CRLF it is handed, since a model reply or a wiki page
  can carry one already; the guarantee is that the file has no CR, not that
  none was added. The plan files written beside a revision go the same way.
- **`tests/test_lf_output.py`** writes through the real writers and reads
  the bytes back — on Windows those tests fail without the fix — and walks
  the writers' source to refuse a direct `write_text` call, with a sweep
  over `src/` for any other `.md` or `.diff` write not on the list.
- **`ingest/provenance.py` keeps normalising line endings before hashing.**
  It answers a different case: a catalog already checked out with CRLF by
  `core.autocrlf=true` on Windows, which no writer here touched. The
  `etl-*` commands still write catalog JSON with `write_text`; that is the
  provenance hash's reason to exist and is not changed here.

## 1.1.0

Installable without a clone. Until this release PolicyForge ran from a
checkout of this repository and nowhere else: every command reads `config/`
and `data/frameworks/` relative to where it runs, and an installed package
had neither. It now installs with `brew install rdazzlebot/tap/policyforge`,
and everything else below had accumulated on `main` since 1.0.0.

### Installing without a clone

- **`policyforge init [DIRECTORY]`** lays out a project: the four
  public-domain catalogs (NIST 800-53, FedRAMP, ARC-AMPE, the HIPAA Security
  Rule), both example configs, a README for each bring-your-own catalog, an
  empty `local_content/`, and a `.gitignore` with the same entries this
  repository ignores. It never overwrites, so it is safe to run twice or
  inside a clone. Offline, and reads no environment variable.
- **The catalogs ship in the package**, as `policyforge._bundled`, mapped
  from `data/frameworks/` and `config/` in `pyproject.toml` so there is still
  one copy. They are named one by one rather than globbed, because a glob
  would package a licensed HITRUST export somebody had placed in their own
  checkout. `tests/test_scaffold.py` holds the list to the catalogs whose
  manifests say `public-domain`, and the hand-kept package list to every
  package under `src/`.
- **`license = "Apache-2.0"`** as an SPDX expression. The file pointer it
  replaces named no licence, and neither GitHub nor Homebrew could read one.
- **A Homebrew formula** in
  [rdazzlebot/homebrew-tap](https://github.com/rdazzlebot/homebrew-tap).
  `CONTRIBUTING.md` has the release steps that keep it current.

### Security documentation, and eight commitments with tests behind them

`docs/` now holds the account of this tool that an adopter — or their
assessor — needs in order to run it against real compliance work: a
[system card](docs/system-card.md), a
[security architecture](docs/security-architecture.md) with an explicit
untrusted-input inventory and a residual-risk section, a mapping to the
[OWASP Top 10 for LLM Applications](docs/owasp-llm-top-10.md), a
[NIST AI RMF alignment](docs/nist-ai-rmf.md), a
[subprocessor and data-flow](docs/subprocessors.md) enumeration, and the
[responsible-use](docs/responsible-ai-use.md) argument with its limits.

The part that is not prose is [docs/commitments.md](docs/commitments.md):
eight statements about this tool's behaviour, each naming the test that fails
when it stops being true. The project's own argument is that a control an
organization cannot evidence is not a control, and a security promise in a
README is the same mistake one level up — so the promises point at tests
rather than at intentions.

**Changing one of these is a breaking change**, requiring a major version
bump and an entry under a `Security` heading here. That rule starts with
this entry.

Two commitments had no enforcing test and now do:

- `tests/test_no_undeclared_endpoints.py` — every host-shaped literal in
  `src/` must appear in an allowlist with a stated reason, the allowlist may
  contain no telemetry-shaped name, and it may contain no dead entries. The
  audit found nothing wrong, which is the point: "no telemetry" was true and
  unenforced, and adding an endpoint is now a deliberate act that edits a
  test.
- `tests/test_credential_containment.py` — every module reading the
  environment must be declared with what it reads and why; **no module that
  defines prompt text may read the environment at all**; and no prompt text
  may name a credential variable.

The second of those found a gap in itself while being written. Detecting
prompt-defining modules by matching `NAME = "..."` found 14 constants across
11 modules and silently missed `edit/plan.py`, `zardoz/answer.py` and
`entail/llm_entailer.py` — the three most security-relevant prompts in the
project — because the prompt registry had changed them to
`NAME = register(...)`, an `ast.Call` rather than an `ast.Constant`. Gathering
every string constant beneath the assigned value finds 22 across 15 modules.
A check that silently stops covering the thing it was written for is worse
than no check, so the module docstring names that failure rather than the
node type.

Documentation accuracy fixes found while writing the above, each of which had
overclaimed:

- Native citations are documented as engaging only on providers holding a
  real Anthropic client, and as unmeasured against a real endpoint. An
  OpenRouter deployment takes the prose-and-fence route, which is what every
  published measurement covers.
- Entailment checking is documented as a **capability, not an operating
  control**: it is implemented and tested, and no runtime path calls it. A
  statement can therefore cite a real passage that does not support it.
- Catalog provenance is documented per catalog rather than in general:
  `nist-800-53-r5` verifies against upstream `v1.5.0`;
  `hipaa-security-rule` is unstamped and reports as unverifiable.

### Security

- **C-05's write guard was bypassable, and is fixed.** Refusing to write a
  licensed catalog into `data/frameworks/`, even with `--force`, was a
  substring test on the path's spelling. `Data/Frameworks/…` and
  `DATA/frameworks/…` got past it on case-insensitive filesystems, and
  `frameworks/…` run from inside `data/` got past it on every platform. Each
  wrote licensed content into the redistributable directory with exit 0. The
  guard now compares filesystem identity with `os.path.samefile`, and — after
  review found the first fix still let `--out <other-repo>/Data/Frameworks/…`
  through when run from outside that checkout — compares the path's
  components case-folded, so the spelling fallback no longer depends on
  case. This
  restores a stated commitment rather than changing one, so it is not a
  breaking change; it is recorded here because a published commitment was
  false and adopters on an affected layout should check `data/frameworks/`
  for licensed content they did not intend to commit.

### Repository hardening

- **semgrep runs from its own lock, not the dev extra.** It pins its
  dependencies exactly (`click~=8.4.2`, `mcp==1.29.0`, `pywin32==311`,
  opentelemetry to `~=1.37.0`, and more), and as a dev extra those pins were
  resolved into `requirements/ci.txt` as if they were this project's. Nearly
  every Dependabot pull request bumped one of them and could never install —
  and the two that passed, `pywin32`, passed only because CI runs Linux, and
  would have broken a Windows install. semgrep now has
  `requirements/semgrep/`, a hashed lock of its own, installed into a
  separate environment in CI and found on `PATH` or in `.tools/semgrep` by
  `scripts/check.py`. The project lock lost 26 packages and changed no
  versions; `pip-audit` audits both locks; Dependabot proposes only semgrep
  itself from the new one. The `mcp` extra is now in the CI lock explicitly,
  where it used to arrive only through semgrep.
- **The dependency bumps that lock unblocked.** `requirements/ci.txt` moves
  to click 8.5.0, jsonschema 4.26.0 and pywin32 312 (Windows only),
  regenerated from its header command rather than merged from Dependabot's
  paired pull requests, which each edited the same lock. **mcp is held below
  2** (at 1.30.0), in the extra and in Dependabot's ignores: mcp 2.0 removed the
  `Server.list_tools` decorator `serve()` is built on, so `policyforge mcp`
  died on startup — with CI green, because no test ever started the server.
  `test_the_server_answers_a_client_over_stdio` now spawns it and speaks
  JSON-RPC to it, and fails on mcp 2 in three seconds; the port is its own
  change. Trying mcp 2 also showed the suite importing `python-dotenv`
  without declaring it, so `tests/conftest.py` disarms dotenv's loader only
  when something has installed it, and the test proving that runs either
  way rather than skipping. Click 8.5
  stores an unset boolean flag's default as a sentinel rather than `False`,
  so `tests/test_cli_surface.py` records what the command receives, and the
  snapshot pins the interface rather than the installed Click. semgrep moves
  to 1.176.1, in its lock and in `.pre-commit-config.yaml` together, and the
  Scorecard workflow's `actions/upload-artifact` to v7.0.1, off the
  deprecated Node 20 runtime.
- **OpenSSF Scorecard** (`.github/workflows/scorecard.yml`) publishes a
  third-party grade of the repository practices the commitments rest on,
  rather than asking a reader to accept a self-assessment.
  `dependency-review-action` was considered for pull requests and
  deliberately not added: it needs the repository's dependency graph
  enabled, and a check that cannot run yet is a red job people learn to
  scroll past — the failure mode this project's own documents warn about
  twice. `pip-audit` already runs on every pull request, and a hash-pinned
  lock means no dependency arrives without a deliberate regeneration. It is
  a one-line addition if the dependency graph is ever turned on, and worth
  more as a gate that means something on the day it lands.
- **CI markdown checking no longer drifts from the local gate.**
  `scripts/check.py` globs every `*.md`, while CI used a hand-maintained
  list that had fallen behind — `CHANGELOG.md`, `MEASUREMENTS.md` and
  `evals/documents/*.md` were gated locally and not in CI, so the pre-push
  gate was strictly stricter than the build. CI now runs
  `git ls-files -z '*.md' | xargs -0 mdformat --check`.
- **`CONTRIBUTING.md`** and a pull-request template name the paths where a
  change is most likely to break a commitment, so the question is asked in
  review rather than discovered in CI.
- **`SECURITY.md`** gains a coordinated-disclosure timeline, and states that
  a report which cannot be fixed is written into residual risk under its own
  heading rather than closed.
- **Scorecard findings that a file change can close.** The workflows no
  longer run an unpinned `pip install --upgrade pip setuptools` before the
  hashed install (the lock pins pip, so that install is the upgrade),
  `codeql.yml` declares read-only token permissions at the top level, and
  `SECURITY.md` links the private reporting form. The rest — branch
  protection, code review, fuzzing, the OpenSSF badge and the repository's
  age — are settings or time, not files.

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
still fails the job.

**CI installs from a hashed lock.** Every workflow resolved the newest release
of every dependency at run time, so Dependabot's seven-day cooldown
constrained nothing — including the publish job, which holds the Confluence
token. `requirements/ci.txt` is now a universal lock with hashes, resolved
by `uv pip compile --universal --python-version 3.12 --generate-hashes` so it
is correct for CI's Linux and Python 3.12 whatever machine regenerates it;
the command is in its header. All three workflows install it with
`--require-hashes` and then the checkout with `--no-deps`, and Dependabot
watches `requirements/` so the lock does not freeze. What is not hashed:
the `pip install --upgrade pip setuptools` that precedes it, and the
setuptools a build-isolated editable install fetches.

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

**Pages published before this change carry no stamp**, so they are adopted
by content rather than by history: a page whose body is exactly what the
repository would publish — compared after collapsing the whitespace between
tags, since Confluence may reflow its markup on save — is published and
stamped, because overwriting it destroys nothing. Any other difference counts
as an edit and the page is reported as moved until it is pulled once or
published with `--force`.

### The prompts that write policy are graded

The largest gap the review found: `evals/` covered Zardoz's four prompts and
nothing that writes a document. A model that routes perfectly can still turn
"shall" into "should consider", and nothing would have said so.

A `generation` suite drafts a Standard, a Policy and a Procedure from one
fixed synthesis and grades them with the checks that already run on real
documents — the source tags a synthesis carried, `deontic`'s binding share,
`ungrounded_values` for an interval nobody stated, and each tier's own rules
from its prompt: a Policy that names a control has failed at its one job, a
Procedure needs a subsection per requirement, and a document may not name a
vendor the configuration never supplied. Citations are compared as
*references* rather than as tag strings, so a merged `[NIST AC-2 | NIST AC-6(5)]` is the two controls it names and a table's escaped pipe is not a
new citation.

**Measured on two models, which fail differently.** `deepseek-v4-flash`
invents intervals inside cited requirements — `annually` in Standards,
`2 hours` and `15 business days` in a Procedure — none of which its
synthesis states, each under a heading carrying a framework tag. It passed
2 of 6 cases. `glm-5.3-flash` invents no intervals and drops citations
instead, once losing all seven references by rendering the Standard as a
table; it passed 4 of 6. `MEASUREMENTS.md` epoch 9 has the numbers and the
rates behind them.

**The graders were wrong five times first**, each failing a correct
document: an escaped pipe in a table, a numbered heading, a Standard's own
"reviewed annually" furniture, a faithful "may" exception, and a merged tag
citing two controls. Every one is now a unit test, because a grader that
fails correct behaviour produces a number that looks like a model getting
worse — the same failure the harness refuses to accept from a model-judged
eval.

### Wiki drift is a question you can ask

`publish` knows which pages hold an edit the repository has not seen — it
refuses to overwrite them and reports them as moved. But that answer arrives
as the wreckage of a publish somebody was trying to do, which is the wrong
moment to learn it and the wrong person to tell. "What changed on the wiki
since we last published?" is what a policy owner asks before a review cycle,
and answering it meant pulling everything and reading the diff.

`policyforge wiki-drift` answers it directly, on the same two rules: this
tool's stamp on the latest version, or the version `pull` recorded in
frontmatter. A page that already says what the repository says is in sync
whoever touched it last, and a page that was never published is reported
apart, because nobody edited it. It writes nothing and prints the `pull`
command that would reconcile each page rather than running it — bringing an
edit into the repository is a diff somebody reviews, not a step a report
takes on their behalf. `--fail-on-change` is opt-in, as in `drift`, so a
scheduled run can be the notification without a routine report exiting
non-zero and being muted within a month.

### The response carries what it knew, and each call asks for what it needs

Three things the providers already had and discarded. `stop_reason` was read
to decide whether to retry a truncation and then thrown away, so a reply cut
off *after* some text reached the caller looking finished. Cache hits were
never read. The request id — the first thing a vendor asks for — was gone by
the time the call returned. `LLMResponse` now carries `stop_reason`,
`cached_input_tokens` and `request_id`, the SDK-backed providers populate
them, LiteLLM maps its own spellings, and the ledger records all three. Zero
and None stay different answers for the cache: zero is a call that could
have hit it and did not, which is what a silently too-short prefix looks
like from the outside.

**Effort is set per call site, not by sizing token budgets around
deliberation.** `zardoz/budgets.py` is generous because a reasoning model
spends its ceiling thinking before a one-word answer, and
`_anthropic_compat` retries at eight times the budget for the same reason.
Both work around the wrong lever. `llm/effort.py` names what each of the
eleven call sites actually wants — `low` for routing, resolution and
expansion, `high` for synthesis, drafting and editing — and passes it only
to providers that advertise `supports_effort()`. One that would drop the
parameter is called exactly as before, rather than letting the call site
believe it asked for less deliberation and pay for the same. The budgets
themselves are untouched: lowering them is a measured change, and epoch 2
records what happened the last time they were set by argument.

**Prompt caching on the two paths that repeat.** A cache is a prefix match,
so the breakpoint sits at the end of what repeats: the system prompt for
`synthesize`, and the system prompt plus the organization block for `ssp`,
whose narrative prompt is now split into its stable and varying halves. The
text sent is their concatenation either way — what changes is the price, not
the question — and a provider that cannot mark a prefix is still sent it,
because the prefix is part of the request rather than a hint about it.

**`ssp --batch`.** Nobody watches a System Security Plan build, and it is
the highest-volume path here: one call per control, several hundred in a
run. `--batch` submits them together for half the price. Results come back
in any order, so each is matched by the control id that went out — matching
by position would fill every cell in the workbook with another control's
narrative and look entirely plausible. The ledger's wrapper implements
`generate_batch` itself rather than inheriting it, which would have sent
several hundred narratives with nothing on file to say so, and each one is
recorded against its own control id.

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
