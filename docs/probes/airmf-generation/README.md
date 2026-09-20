# Probe: what generation does to an outcome-based framework

**Run 2026-09-20, before the NIST AI RMF catalog existed.** Kept because it
changed a release decision, and a near-miss that lives only in a conversation
is one nobody can find later.

## The question

Every catalog PolicyForge has shipped states **obligations** — *the
organization must do X*. NIST AI RMF states **outcomes** — *X is understood,
managed, and documented*. Nobody here had generated a document against an
outcome-based framework, and the three AI governance documents in the 1.6 scope
would be the first.

## What was run

A seven-item stub built from the real `GOVERN 1.x` subcategory text on
[AIRC](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/), through
`synthesize_topic` → `generate_standard`, on two models:

| File | Model | Cost |
|---|---|---|
| `synthesis.md` | `qwen3:14b-pf` (local) | $0 |
| `standard-local-qwen3-14b-pf.md` | `qwen3:14b-pf` (local) | $0 |
| `standard-production-kimi-k3.md` | `openrouter/moonshotai/kimi-k3` | cents |

`stub-controls.json` is **not a catalog**. Its `source_path` is
`PROBE-STUB-NOT-FOR-SHIPPING`, it holds seven of seventy-two subcategories, and
it is deliberately named `stub-controls.json` rather than `controls.json` and
placed outside every entry in `DEFAULT_SEARCH_PATHS`
(`data/frameworks`, `frameworks`, `local_content`) so `discover()` cannot load
it. Verified: 7 catalogs discovered with this directory present.

## What it showed

**The generated requirement is the outcome with an obligation verb prefixed,
on both models.**

    SOURCE  GOVERN-1.1  "Legal and regulatory requirements involving AI are
                         understood, managed, and documented."

    local   "The organization must ensure that all legal and regulatory
             requirements involving AI are understood, managed, and
             documented in accordance with organizational policies."

    prod    "Acme Health shall ensure that legal and regulatory requirements
             involving AI are understood, managed, and documented."

Circular: *you must ensure that X is understood*, where the subcategory says
*X is understood*. A reader cannot act on it.

**And nothing mechanical catches it.** In the local document: 7/7 citations
resolve, binding share is ~100%, no invented identifiers, and `[Review
Frequency]` was correctly left undecided rather than fabricated. `satisfies`,
`check`, `deontic` and `ungrounded_values` all pass. **The failure is
invisible by construction** — which is why the artefact is worth more than a
description of it.

**The difference the stronger model makes is supplementation, and it is
inconsistent.** `kimi-k3` adds Purpose and Scope sections, and *sometimes*
splits an outcome into something actionable — GOVERN-1.6 becomes *"shall
establish and maintain mechanisms to inventory AI systems"* plus *"The
inventory mechanism shall be resourced according to organizational risk
priorities"*. Several sections get no supplementation at all.

## What was decided from it

1. **The hollowness is prompt-shaped, not model-shaped** — both models produce
   the same restatement on the same sections. An outcome-framework branch in
   the generation prompt is in scope for 1.6.
2. **The branch's job is to make supplementation the rule rather than a
   tendency.** That is the spec, and it came from reading both documents.
3. **This document goes into the reading brief** for whoever reviews the real
   AI governance documents. *Here is what hollow-but-traceable looks like*
   beats any description of it.

## One note on method

An automated comparison was written first — per-section overlap ratio,
restatement-only count. **It returned 0.05–0.08 overlap for text plainly
readable as near-verbatim, and scored 0/7 restatement-only on both
documents**, because the sentence splitter fragmented on the markdown. It was
discarded and seven items were read instead.

The conclusion above rests on reading, not on a metric. For small N, read
them; build a metric only when N is too large to read, and then test it
against items already read.
