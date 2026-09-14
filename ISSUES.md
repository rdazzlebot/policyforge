# Proposed issues

Work identified while adding multi-model support and measuring nine models
against the eval suite. Each entry is written to be filed as-is.

Everything here is a design intention rather than a report of a live
defect. Where a security item describes a risk, it describes one the
current design already narrows — the point is to make the narrowing
mechanical rather than advisory.

## Filing these

After `gh auth login`, split on the markers and file them:

````bash
python - <<'PY'
import re, subprocess, pathlib

MARK = "<!" + "-- issue: "          # split, not spelled, so this snippet
CLOSE = "--" + ">"                  # is not parsed as an issue itself

text = pathlib.Path("ISSUES.md").read_text(encoding="utf-8")
text = re.sub(r"```.*?```", "", text, flags=re.S)   # drop fenced blocks

for part in text.split(MARK)[1:]:
    marker, body = part.split(CLOSE, 1)
    title, labels = (piece.strip() for piece in marker.split("|", 1))
    subprocess.run(
        ["gh", "issue", "create", "--title", title, "--label", labels,
         "--body", body.split(MARK)[0].strip()],
        check=True,
    )
PY
````

Labels used: `security`, `cost`, `prompts`, `retrieval`, `analysis`,
`measurement`. Create them first, or drop `--label`.

______________________________________________________________________

<!-- issue: Treat retrieved passages as data, not as instructions | security -->

Zardoz answers from passages retrieved out of a document corpus, and
`zardoz.supporting_space` deliberately admits content that nobody has
declared ownership of. Text arriving that way is currently placed into the
prompt alongside the instructions that govern how it should be used.

For a tool whose output an assessor may rely on, the consequence of a
passage being read as instruction rather than as evidence is that somebody
is told something false about their own control posture.

Several existing properties already narrow this, and are worth keeping in
view when designing the fix: every claim must carry a citation that is
verified against the passages actually supplied, quotations are checked
verbatim, and unowned sources have to be disclosed in the answer.

Worth considering:

- A clear structural boundary between instruction and evidence in
  `build_prompt`, rather than headings alone.
- A restatement of the grounding rules *after* the passages, so the last
  thing read is the contract rather than the content.
- A check that reports passages containing imperative text addressed at the
  reader, as a warning on the corpus rather than on the answer.
- Extending `zardoz sync`'s report, which already surfaces ownership
  problems, to cover this.

<!-- issue: Make the licensed-content boundary a control, not a confirmation | security -->

HITRUST and GovRAMP exports are licensed, and the project is careful about
them: they live under `local_content/`, `policyforge check` fails when
licensed content is committed to a repository that has not declared the
right to hold it, and `frameworks.allow_licensed_in_repo` is a statement
only the licence holder can make.

One step is still advisory rather than enforced. Sending that content to a
third-party API processor is a licence question, and today it is answered
by a human confirming it before `generate-parser` runs.

That could be a control instead: content from a framework whose manifest
says `licence: licensed`, or that lives under `local_content/`, may only be
sent to a provider classified as local. The classification already has a
natural home now that providers are pluggable — a local Ollama and a hosted
vendor are different things and the config already distinguishes them.

Fails closed, needs no model, and turns a policy into something that can be
evidenced.

<!-- issue: Classify providers and content, and enforce the pairing | security -->

Follows from the licensed-content issue and generalises it.

Two classifications:

- **Providers**: local (Ollama, llama-server), self-hosted, third-party API.
- **Content**: public domain (NIST, HIPAA), organization-internal
  (generated documents, topic registry), licensed (BYOC exports).

Then a matrix saying which may meet which, checked before a call rather
than documented in a README.

This is how a security programme reasons about data handling, applied to
the tool that writes security programmes. It also makes the answer to "can
this run offline" a property of the configuration rather than a matter of
recollection.

<!-- issue: Record which model saw which document | security -->

There is no record of which model was sent which document, when, or at what
cost. `LLMResponse` now carries model and cost, and `_Metered` in
`scripts/eval_zardoz.py` shows the shape of the accounting, but nothing
persists it.

For this product that record is itself an auditable control: it is what
lets someone evidence that licensed content never left the boundary, or
identify every document a particular model touched.

Should note the provider, the model string, the document or control, token
counts and cost. `history/version_store.py` is the closest existing home,
though this is a different kind of record and may want its own.

<!-- issue: Stamp generated documents with their model provenance | security -->

`policyforge generate` records each document into local version history,
but not which model wrote it.

The day a model is found to have a flaw — a systematic weakening of cited
requirements, say, of the kind `content/deontic.py` now detects — the
question is which documents it touched. Right now that cannot be answered.

Recording model, model version and a hash of the prompt alongside the
document would close the loop, and costs nothing at generation time.

<!-- issue: Scan generated documents for secrets | security -->

`gitleaks` runs over the repository. Nothing scans what the generator
writes.

A passage can contain a credential, and an answer or a generated Standard
can reproduce it — `check_answer` verifies that a quotation is *faithful*,
which is precisely the wrong property here. Publishing then puts it in
Confluence.

A scan over generated output before `export-confluence` and `publish`, and
as a warning in `policyforge check`.

<!-- issue: Batch the SSP narrative calls | cost -->

`policyforge ssp` makes one model call per in-scope control. A moderate
baseline is several hundred controls, which makes it the largest volume
path in the project, and nobody is waiting on the result.

The Batch API is a flat 50% reduction for exactly this shape. The only cost
is latency that is not needed.

`--no-narratives` already exists as the zero-call option; this is the
middle ground.

<!-- issue: Cache the SSP system prompt | cost -->

Every SSP narrative call sends the same system prompt and the same
organization context, with only the control changing. That is the textbook
prompt-caching shape.

Worth measuring before building: caching has a minimum cacheable prefix
that varies by model, and a short system prompt will silently fail to
cache. Verify `usage.cache_read_input_tokens` is non-zero across repeated
calls rather than assuming.

<!-- issue: Set effort per call site | cost -->

No call in the project passes `output_config.effort`, so every request runs
at the provider default — including a routing call that wants a single
word.

The call sites are already tiered by budget after the work in
`zardoz/budgets.py`: routing, expansion and resolution are short and
decisive, while `synthesize` and `generate` are long-form judgement. Effort
should follow that split.

<!-- issue: Cache eval responses so --repeat is affordable | cost -->

`evals/runner.py` argues at length that one run is not evidence — a
truncation bug measured at one failure in eight came back clean on its
first two probes. The harness reports a rate for that reason.

In practice runs are done at `--repeat 3` because higher costs more. A
response cache keyed on (model, system, prompt, budget, temperature) would
make `--repeat 20` nearly free for the unchanged cases, which is what the
harness's own thesis asks for.

Needs care: the cache must be invalidated by any prompt change, or it will
cheerfully report yesterday's behaviour.

<!-- issue: Refuse a run that would cost more than a ceiling | cost -->

`policyforge ssp` already prompts before spending, because it makes one
call per control. Nothing else estimates cost, and `eval_zardoz.py` can
issue several hundred calls from one command.

Now that `LLMResponse` carries cost and the eval runner totals it, a
projected-cost ceiling is tractable: estimate from the planned call count
and the model's rates, and refuse to start above a configured limit.

The mis-scoped `ssp` run against the wrong baseline is the expensive
mistake available today.

<!-- issue: Measure prompt changes across a panel, not one model | prompts -->

The prompts in this project were authored and iterated against Anthropic
models, which is visible in `config.example.yaml` and the
`_anthropic_compat` lineage. A prompt change that helps the model you are
testing with, and harms others, is currently invisible.

Measured during the multi-model work: moving one rule earlier in the
answering prompt improved one model by three points and cost two others
five and six. Only a three-model before-and-after revealed it, and the
change was reverted.

Worth writing down as a practice, and worth a script that runs a suite
across a configured panel and reports the deltas side by side. Models are
now cheap enough that a full sweep is a couple of cents.

<!-- issue: The placeholder rule is missed by six of nine models | prompts -->

`an-undecided-parameter-is-reported-as-undecided` failed or flaked on six
of the nine models measured — both Gemini models, both DeepSeek models,
gpt-oss-120b and a local Qwen. Only sonnet-5 and glm-5.3-flash handle it
reliably.

That case tests rule 10 of the answering prompt: never present an unfilled
placeholder as an answer, never guess what belongs there, never illustrate
it with example values. It is the most compliance-relevant rule in the
prompt, since a frequency is a commitment defended to an assessor.

When two thirds of models across five vendors miss the same rule, the
prompt is the likelier explanation. Note that simply moving it earlier was
tried and reverted — it helped one model and cost two. Restating it at both
ends, or making it a procedure rather than a prohibition, are the
untried options.

<!-- issue: Detect vague requirements | analysis -->

"as appropriate", "where feasible", "commercially reasonable efforts",
"periodically". These make a requirement unauditable while looking like
one, and they are a known anti-pattern in compliance documents. The
generated Standard in `evals/documents/` contains one.

Same shape as `content/deontic.py` — a lexicon, deterministic, reported as
a warning through `policyforge check`. Should share its care about false
positives: hedging in a Purpose section is not the same as hedging in a
requirement.

<!-- issue: Detect obligations with no actor | analysis -->

"Accounts must be recertified quarterly." By whom? An assessor's next
question after *must* is *who*, and passive voice hides it.

The natural sibling of the deontic work, in the same module and the same
deterministic style. `org.teams` already knows what the legitimate actors
are, so a candidate actor can be validated rather than guessed.

A Standard where a large share of obligations name no actor is a real
finding.

<!-- issue: Normalise intervals rather than matching them as strings | analysis -->

`quarterly`, `within 24 hours`, `6 years`, `annually` are currently matched
as text — `zardoz/answer.py`'s `ungrounded_values` recognises them by
pattern.

Parsing them into structured durations would enable three things: detecting
where two documents assert different frequencies for the same action (the
**conflict log** already on the roadmap), checking documents against the
parameter ledger, and comparing values rather than their spelling.

The last of those is not hypothetical. A narrow no-break space inside "6
years" once caused a correctly grounded figure to be reported as invented.

<!-- issue: Diff requirements by modality across versions | analysis -->

`policyforge history` diffs document text. `policyforge drift` compares
catalogs. Neither can say *a requirement changed meaning*.

Now that `content/deontic.py` classifies modality, a revision that turned a
`must` into a `should` is detectable — and that is a compliance regression
that nothing currently reports, arriving in a diff that looks like an
ordinary wording change.

<!-- issue: Chunk tables so quotations survive them | retrieval -->

Measured: `an-answer-can-come-from-a-table` produced a fabricated quotation
from **both** claude-sonnet-5 and deepseek-v4-flash, in different runs.
Both put non-verbatim text in quotation marks while citing correctly.

`check_answer`'s quote rule caught both, and was right to — the passages do
not contain those words. The cause looks structural: retrieval chunks at
headings, tables get flattened, and models reflow cells into prose.

Worth investigating whether table content should be chunked, or quoted,
differently.

<!-- issue: Flag terminology drift across the corpus | analysis -->

A corpus that says "privileged account" in one document and "administrative
account" in another is confusing to an assessor, and it is also the
condition `zardoz/paraphrase.py` exists to work around at query time.

Fixing it at the source would make that subsystem less necessary. Needs a
glossary or a controlled vocabulary to check against; `policyforge roles`
is a precedent for fixed, checkable keys.

<!-- issue: Calibrate the dense-retrieval floor before defaulting it | retrieval -->

`src/policyforge/embed/` adds dense retrieval and RRF fusion, off by
default. The evidence for it is strong: BM25 returned zero passages for two
questions a real generated Standard plainly answers, and dense retrieval
found both.

What blocks it becoming default is `MIN_SIMILARITY`. It is measured, not
guessed — questions the document answers in other words scored 0.646, 0.557
and 0.521, and questions it does not answer scored 0.458 and 0.410 — but
the margin between noise and signal is thin and comes from **one**
document.

That floor is what keeps "nothing in the synced documents appears to bear
on that" a possible answer. Too high and the recall failure returns; too
low and the honest refusal goes. Needs calibration across several real
corpora, with the refusal cases confirmed still empty.

<!-- issue: Revisit reranking once recall is wider | retrieval -->

`src/policyforge/rerank/` adds a cross-encoder stage, off by default and
called by nothing.

It is parked on evidence rather than doubt. Retrieval gates hard on
specificity so that an honest refusal stays possible, which means it does
not produce the wide candidate set reranking depends on — in testing it
returned a single candidate twice. A reranker improves ordering and cannot
improve recall, so it cannot rescue a passage the gate filtered out.

Revisit after dense retrieval widens the candidate set. Loosening the
specificity gate to feed a reranker would trade a measured strength for a
speculative gain.

<!-- issue: Record the model comparison as evidence | measurement -->

Nine models were measured across five suites during the multi-model work,
with per-call costs. That data currently lives only in a session
transcript.

It is worth a file in the repository: it is what justifies the default
model choice, it is the baseline any future prompt change is measured
against, and it shows which eval cases discriminate between models and
which every model passes.

Should note the date and the harness revision, since both the models and
the prompts move.
