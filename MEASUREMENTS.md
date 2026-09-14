# Measurements

What models actually score against `evals/`, and what they cost.

Kept because it is the evidence behind the default model choice, the
baseline any prompt change is measured against, and the record of which
eval cases discriminate between models and which every model passes.

**Read the epochs before comparing two numbers.** The prompts and the
call-site budgets changed during the session that produced this file, and
a score from before a change is not comparable with one from after it.

Reproduce any row with:

```bash
python scripts/eval_zardoz.py --model <litellm model string> \
    --suite routing --suite resolution --suite expansion --repeat 3
```

______________________________________________________________________

## Method, and what to distrust

- **`--repeat 3`** unless noted. The harness reports a *rate*, not a
  verdict, because one run is not evidence — `evals/runner.py` explains
  why at length.
- **2–3 points is noise at this sample size.** The same model, same code,
  two runs, moved 96% → 95% on `answer_paraphrase`. Trust a direction that
  holds across suites; do not trust a small gap.
- **Costs are per whole suite run**, from the harness's own accounting
  (64 calls for the terse trio, 67 for `answering`, 198 for `paraphrase`).
- **Costs before 2026-09-13 are understated** for any model that tripped
  `ReasoningBudgetExhausted`: a call that raised was billed but not
  counted until that was fixed.
- **Third-party routing varies.** Models reached through OpenRouter may be
  served by different upstreams between runs, with different quantisation.

### What each suite tests

| Suite               | Asks                                                                            |
| ------------------- | ------------------------------------------------------------------------------- |
| `routing`           | does a question reach the analysis that can answer it                           |
| `resolution`        | does a follow-up become the question it obviously means                         |
| `expansion`         | does query expansion name the document's vocabulary without inventing facts     |
| `answering`         | grounded prose with citations, and refusal when the passages do not support one |
| `answer_paraphrase` | the answering cases in wordings their author did not choose                     |
| `conversation`      | multi-turn, driven through the real shell                                       |
| `paraphrase`        | 66 generated rewordings of the routing cases                                    |

______________________________________________________________________

## Current baseline — 2026-09-13

After the budget, prompt and check fixes described in the epochs below.
Only these three models have been re-measured since; every other row in
this file predates those changes.

| Model                                   | routing | resolution | answering | paraphrase | cost/suite   |
| --------------------------------------- | ------- | ---------- | --------- | ---------- | ------------ |
| `openrouter/z-ai/glm-5.3-flash`         | 100     | 100        | **100**   | **100**    | $0.017–0.024 |
| `openrouter/deepseek/deepseek-v4-flash` | 100     | 100        | 96        | 99         | $0.004–0.005 |
| `openrouter/google/gemini-3.8-flash`    | 100     | 100        | 97        | —          | $0.065–0.165 |

`anthropic/claude-sonnet-5` scored **100** on `answering` ($0.2345) and
**99** on `answer_paraphrase` ($0.2176). Those remain valid: the answering
prompt was reverted byte-for-byte after the reorder experiment, so nothing
that affects them changed.

**Recommended default: `glm-5.3-flash`.** One flaky run short of sonnet-5
across every suite measured, at roughly a fifteenth of the cost.
`deepseek-v4-flash` is the value pick at about a fiftieth.

______________________________________________________________________

## The nine-model comparison — 2026-09-12

Original configuration: budgets 64/150/200, prompts before the router and
resolution fixes. **These are the numbers the recommendation was made
from**, and they are not comparable with the baseline above.

### Terse suites

| Model                           | routing | resolution | expansion | cost    |
| ------------------------------- | ------- | ---------- | --------- | ------- |
| `anthropic/claude-sonnet-5`     | 100     | 100        | 100       | $0.0869 |
| `x-ai/grok-4.6`                 | 100     | 100        | 100       | $0.2831 |
| `google/gemini-3.1-pro-preview` | 100     | 100        | 100       | $0.3431 |
| `google/gemini-3.8-flash`       | 100     | 100        | 100       | $0.0651 |
| `z-ai/glm-5.3-flash`            | 97      | 95         | 100       | $0.0124 |
| `deepseek/deepseek-v4-flash`    | 92      | 100        | 100       | $0.0052 |
| `qwen/qwen3-32b`                | 92      | 100        | 100       | $0.0147 |
| `openai/gpt-oss-120b`           | 89      | 95         | 100       | $0.0050 |
| `ollama_chat/qwen3:14b` (local) | 92      | 71         | 100       | $0      |
| `deepseek/deepseek-r1`          | 100     | 95         | **22**    | $0.0972 |
| `qwen/qwen3.7-flash`            | 81      | 100        | **33**    | $0.0052 |
| `minimax/minimax-m1`            | 44      | 48         | 33        | $0.0757 |

### Answering

| Model                           | answering | cost    | cost/call |
| ------------------------------- | --------- | ------- | --------- |
| `anthropic/claude-sonnet-5`     | 100       | $0.2345 | $0.00350  |
| `z-ai/glm-5.3-flash`            | 99        | $0.0124 | $0.00019  |
| `deepseek/deepseek-v4-flash`    | 96        | $0.0027 | $0.00004  |
| `google/gemini-3.1-pro-preview` | 96        | $0.5387 | $0.00804  |
| `google/gemini-3.8-flash`       | 94        | $0.1640 | $0.00245  |
| `deepseek/deepseek-v4-pro`      | 93        | $0.0360 | $0.00054  |
| `cohere/command-a`              | 87        | $0.1819 | $0.00272  |
| `openai/gpt-oss-120b`           | 80        | $0.0079 | $0.00012  |
| `ollama_chat/qwen3:14b` (local) | 84        | $0      | free      |

`deepseek-v4-flash` also scored 95 on `answer_paraphrase` and 95 on
`conversation`.

### Void runs

Recorded so nobody re-derives them as model verdicts.

| Model                | Reported | Why it says nothing                                                                                                     |
| -------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------- |
| `cohere/command-a`   | 28       | `tenacity` missing — a Python dependency LiteLLM needs on its retry path but does not declare. 47 of 114 calls died.    |
| `cohere/command-a`   | 71       | OpenRouter per-model rate limit for new accounts; 6 of 23 cases never reached a verdict. Fixed with `--min-interval 6`. |
| `moonshotai/kimi-k3` | 14 / 0   | Same rate limit.                                                                                                        |
| `openai/gpt-6-astra` | 14 / 0   | Same rate limit.                                                                                                        |

______________________________________________________________________

## Configuration epochs

What changed, and therefore which numbers may be compared.

### 1. Original — up to 2026-09-12

Budgets 64/150/200. Router prompt relying on two default-to-documents
rules. `check_answer` without the placeholder and provenance checks.

### 2. Raised budgets — 2026-09-12

800/1500/2000, after measuring that a tight budget does not degrade an
answer but deletes one, and costs more doing it.

| Model                                          | Before                  | After                               |
| ---------------------------------------------- | ----------------------- | ----------------------------------- |
| `deepseek-v4-pro` routing/resolution/expansion | 97 / 95 / 89, $0.0934   | 97 / **100** / **100**, **$0.0607** |
| `deepseek-v4-flash` (control)                  | 92 / 100 / 100, $0.0052 | 92 / 100 / 100, **$0.0013**         |

The control is the important row: quality flat, cost down four-fold. It
had been paying a retry tax invisibly.

### 3. `check_answer` fixes — 2026-09-13

Two false positives were costing about five points on *every* model's
answering score, with nothing pointing at the checker.

- A narrow no-break space made "6 years" read as an invented figure the
  passage states in so many words.
- `[t]erminated`, the convention for altering a quotation's case, read as
  fabrication.

`deepseek-v4-flash` answering: 91 → **96**.

### 4. Router and resolution prompts — 2026-09-13

Each analysis given positive and negative criteria so routing does not
depend on the default.

|                                | Before | After   |
| ------------------------------ | ------ | ------- |
| `deepseek-v4-flash` routing    | 92     | **100** |
| `deepseek-v4-flash` paraphrase | 92     | **99**  |
| `glm-5.3-flash` routing        | 97     | **100** |
| `glm-5.3-flash` resolution     | 95     | **100** |

`document-history`, which failed on six of nine models and five of six
phrasings, disappeared from the failures entirely.

**Reverted in the same epoch:** moving the placeholder rule from position
10 to 3. It gained gemini 3 points and cost glm 5 and deepseek 6. Only a
three-model panel revealed it.

### 5. Structured outputs — 2026-09-13

Routing constrained by an enum schema where the model supports one, falling
back to prose otherwise. No regression: `glm-5.3-flash` 100 routing and
**198/198** paraphrase; `deepseek-v4-flash` held at its 99 baseline.

______________________________________________________________________

## Findings that outlived the numbers

**Terse scores do not predict answering scores.** `deepseek-v4-flash` went
92 on routing and 96 on answering; `gpt-oss-120b` went 89 on routing and 80
on answering. Measure the suite you care about.

**Price does not predict quality.** `deepseek-v4-pro` scored *below* its
own Flash sibling on answering at fifteen times the cost. Both Gemini
models are strictly dominated — cheaper models score higher.

**Reasoning models are not worse at terse tasks; the budgets were wrong.**
R1 scored 22 on expansion and minimax-m1 33, which read as a verdict on
reasoning models. At the raised budgets two reasoning models scored 100.
The earlier conclusion was an artifact of the test conditions.

**No model is trustworthy without the deterministic checks.** `sonnet-5`
fabricated a quotation on `answer_paraphrase`; `check_answer`'s verbatim
rule caught it. The checks are not scaffolding for cheap models.

**One case discriminates more than any other.**
`an-undecided-parameter-is-reported-as-undecided` failed or flaked on six
of nine models across five vendors. When two thirds of models miss the same
rule, the prompt is the likelier explanation.

**A cited requirement stated as a bare fact is invisible to every other
check.** Both `sonnet-5` and `deepseek-v4-flash` produced non-verbatim
quotations from table content, on the same case.

______________________________________________________________________

## Adding a run

Append to the table for the current epoch, or open a new epoch when the
prompts, budgets or checks change. Each entry wants:

- the date and the model string as passed to `--model`
- `--repeat`, if not 3
- the cost line the harness prints
- what changed since the last epoch, if anything

A number without an epoch is not comparable with anything, which makes it
worse than no number at all.
