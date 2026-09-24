# Surviving ledgers

The primary data behind every figure in `MEASUREMENTS.md` that can still be
re-derived. Preserved here by #207 on 2026-09-24. **Before this, each lived in
one session's scratch directory and nowhere else**, which is how most of the
file's history lost its source.

Each row is one model call, or one topic in the 2026-09-21 file, as the
project's ledger (`src/policyforge/llm/ledger.py`) or the partial-matrix
runner wrote it. The rows hold **metadata only**: model, site, subject, token
counts, cost, stop reason, a prompt hash and the provider's request id. No
prompt text, no generated text, no catalog content.

| file                                           | rows | what it is                                                                                     | backs                                                        |
| ---------------------------------------------- | ---- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `2026-09-17-policy-set-glm.jsonl`              | 80   | 20 topics × synthesize + three tiers, `z-ai/glm-5.3-flash` via OpenRouter, on 1.2.1's code     | epoch 21                                                     |
| `2026-09-17-policy-set-glm-before-1.2.1.jsonl` | 80   | the same run on the code before 1.2.1, with 15 truncated calls                                 | epoch 21, "What 1.2.1 did"                                   |
| `2026-09-17-policy-set-sonnet-5.jsonl`         | 25   | 5 topics, `anthropic/claude-sonnet-5` **via OpenRouter**, not the direct API                   | epoch 21                                                     |
| `2026-09-18-evals-glm-deepseek-a.jsonl`        | 505  | eval-harness calls, glm and deepseek-v4-flash, plus 2 sonnet-5 calls                           | no written epoch                                             |
| `2026-09-18-evals-glm-deepseek-b.jsonl`        | 136  | the same                                                                                       | no written epoch                                             |
| `2026-09-19-evals-glm-deepseek-c.jsonl`        | 178  | the same                                                                                       | no written epoch                                             |
| `2026-09-21-document-set-sonnet-4.5.jsonl`     | 25   | one row **per topic**, not per call: synthesize + Standard, `claude-sonnet-4.5` via OpenRouter | epoch 24                                                     |
| `2026-09-24-synthesize-glm-paired.jsonl`       | 3    | three synthesize calls paired by topic with epoch 21                                           | epoch 23's cost correction, and "How an epoch is registered" |

Beside them, the three epoch-21 runs' **step records** (`*-steps.json`): one
entry per topic and step, with its seconds, whether it succeeded and any
error, plus the run's `wall_seconds`. The wall-clock figures in epoch 21 (103
and 37 minutes) come from these, not from the call ledgers. A ledger's
first-to-last timestamp span is a different instrument and reads shorter. The
glm record's one error is why that run holds 59 documents, not 60: the model
returned an empty Policy for Security Program Governance, and the pipeline
refused it by name rather than writing an empty file.

**Three of the files belong to no written epoch.** They are eval-harness runs
from 2026-09-18 and 19, preserved from another session's scratch directory.
Which work they measured is not recorded with them, so they back no figure in
`MEASUREMENTS.md` except the per-call eval rates quoted in its opening
section. They are kept because they are primary data, not because anything
depends on them.

## Checked before committing

- **Credentials:** a scan for key and token shapes matched ten strings, and
  all ten are false positives: nine are the topic slug
  `ri`+`sk-assessment-authorization`, and one is the topic name
  "Risk Assessment & Authorization". `request_id` values are provider
  generation ids, which are not credentials. The gate's secrets scan runs
  over these files too.
- **Licensed content:** none. No row holds text from a catalog or a
  document.
- **Line endings:** the ledgers were written with CRLF on Windows. They are
  committed as LF, and every file was checked to parse to identical rows
  before and after.

## Checksums of the committed files

```
6a6f4f0e46ca00eed355ff9be8345df70595c075e3156aceefbb6f3fb01ad363  2026-09-17-policy-set-glm-before-1.2.1.jsonl
2f557667f8293b3d72821e1cb65ddef61ee8122b279c2814d9c589eb0c4f1191  2026-09-17-policy-set-glm.jsonl
d18433ca579f32f1378c242941fd654e53cecf4a9e4a06e2cd8846b321004aa0  2026-09-17-policy-set-sonnet-5.jsonl
2c183410eb72538b073a5a78b29715e105c50f3e099c85e8c98676a855bcd627  2026-09-18-evals-glm-deepseek-a.jsonl
837e7a4728998b7089bd1184f72199ab548f2cfa756549c5ae1540493c04df0d  2026-09-18-evals-glm-deepseek-b.jsonl
e0cfc1f98bf2dea2c5da6abd3ed114943b2d5fc7ea0092fe2610dff15ead5109  2026-09-19-evals-glm-deepseek-c.jsonl
90c1b8238ee5ef9aa2847a3040d3cfa085c5f9a856168dc7920ceabf32135fb6  2026-09-21-document-set-sonnet-4.5.jsonl
1ecd6f8e8a5a163400556c86682280f91f611f50e33807ad6132bcb6005c8ff3  2026-09-24-synthesize-glm-paired.jsonl
e995d84b70a033ae41982fa348e4cf9461d95b739934b77ecc1d5307687cb6a1  2026-09-17-policy-set-glm-before-1.2.1-steps.json
6c3008e1322964c1b3977b8903600f13dd943846af8d65a77af73412807f51d5  2026-09-17-policy-set-glm-steps.json
324e13062063263717cf9bfa262136cb9db20fb4a7635d84eb5b1bf78707235b  2026-09-17-policy-set-sonnet-5-steps.json
```
