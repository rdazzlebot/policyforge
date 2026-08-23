# PolicyForge

Generate cross-mapped information security policies, standards, and
procedures from public compliance frameworks (NIST 800-53, FedRAMP,
ARC-AMPE) plus your own optionally-licensed content (HITRUST CSF, GovRAMP),
using an LLM you bring the API key for.

This project separates two things that are easy to accidentally tangle
together: **the engine** (this code — the crosswalk logic, the merge/dedupe
methodology, the generation pipeline) and **the content** (the frameworks
themselves, some of which are freely redistributable and some of which are
not). See [Licensing model](#licensing-model-per-framework) below before you
add any framework content to this repo.

## Status

The full pipeline is functional end-to-end: `etl-vault` -> `map` -> `synthesize`
-> `generate` -> `export-confluence` (optional). The Anthropic provider, NIST
vault ETL loader, crosswalk builder, LLM-driven synthesis/generation stages,
and Confluence export are all wired up and tested. HITRUST/GovRAMP BYOC
loaders remain stubs pending a sample export to parse against — see
`ingest/byoc_loader.py`.

## Zero Obsidian dependency

Nothing in this codebase requires Obsidian. The only place Obsidian shows up
is `ingest/nist_vault_loader.py`, which parses one *specific* markdown shape
(YAML frontmatter + `## headings` + `[[wikilinks]]`) as one possible input
adapter — because that happens to be the format of the vault this project
started from. Everything downstream of ingestion (schema, mapping,
synthesis, generation, export) works from plain, portable data and has no
idea Obsidian exists. Swap in a different loader for a different source
format and the rest of the pipeline doesn't change. You can keep authoring
your personal knowledge base in Obsidian (or anything else) — that's a
choice about where *you* maintain content, not a requirement of this tool.

## Output format priority

**Markdown is the primary deliverable.** Everything this project generates
must be correct, well-formed, portable CommonMark first:

- No Obsidian-specific syntax in generated output — standard `[text](path)`
  links, not `[[wikilinks]]`; no vault-relative-only paths.
- Consistent heading hierarchy, properly closed code fences, well-formed
  tables — markdown that renders correctly unmodified on GitHub, in a plain
  text editor, or pasted into any wiki.
- Enforced, not just intended: `mdformat --check` runs in pre-commit and CI
  against anything generated into `output/` during development, the same
  way gitleaks/bandit/pip-audit enforce the security scanning requirements.

**Confluence export is a secondary, additional feature — not a second
generation path.** `export/confluence_exporter.py` converts the *same*
canonical markdown produced above into Confluence storage format, rather
than the generation step producing Confluence content independently. That's
deliberate: it's the only way to guarantee both outputs are actually
correct, since there's only one thing to get right upstream. If Confluence
needs something markdown can't express well (e.g. Confluence-native macros),
that's a transform-time enrichment on top of the canonical markdown, not a
fork of the generation logic.

## Document hierarchy: Policy > Standard > Procedure

Every topic's synthesis output (see `synthesis/merge.py`) can be drafted
into more than one document tier, each with a different audience and level
of detail — `policyforge generate --tier <tier>`:

- **Standard** (`--tier standard`, the default) — the detailed, technical
  document: every synthesized requirement, source-tagged back to the
  frameworks it came from (`[NIST IA-5 | FedRAMP IA-5]`), vendor-specific
  where `org.vendors` allows it. Audience: security/IT staff who implement
  and audit against it.
- **Policy** (`--tier policy`, requires `--standard <path>`) — a short,
  principle-level document read by the whole organization, not just
  practitioners. It compresses the same synthesized requirements into a
  small number of plain-language commitments and drops framework/control
  citations entirely — that traceability lives in the Standard, which the
  Policy references by name in its "Related Standards" section (extracted
  automatically from the Standard document's title, via
  `generate/policy_writer.py`'s `extract_title`).
- **Procedure** (`--tier procedure`, requires `--standard <path>`) — one
  level *more* granular than the Standard: each requirement becomes the
  literal ordered steps a practitioner performs to satisfy it, still
  source-tagged for traceability and referencing the Standard by name the
  same way the Policy does.

Generate a topic's Standard first, then its Policy and/or Procedure from
that Standard:

```
policyforge generate --tier standard --synthesis output/synthesis/auth-mgmt.md
policyforge generate --tier policy --synthesis output/synthesis/auth-mgmt.md \
  --standard output/standards/auth-mgmt.md
policyforge generate --tier procedure --synthesis output/synthesis/auth-mgmt.md \
  --standard output/standards/auth-mgmt.md
```

## Licensing model (per framework)

Not all four frameworks this project targets are safe to bundle and
redistribute in an open repo. Treat them differently:

| Framework             | Status                                                                                                                            | How this project handles it                                                                                                                                                                                              |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **NIST 800-53 Rev 5** | US federal government work — public domain                                                                                        | Bundled directly in `data/frameworks/nist-800-53-r5/`                                                                                                                                                                    |
| **FedRAMP**           | US federal government work — public domain                                                                                        | Bundled directly in `data/frameworks/fedramp/`                                                                                                                                                                           |
| **ARC-AMPE**          | Published by CMS (federal agency) — public domain                                                                                 | Bundled directly in `data/frameworks/arc-ampe/`                                                                                                                                                                          |
| **GovRAMP**           | GovRAMP's Terms & Conditions claim ownership of "documents, downloadable files" on their site, with no redistribution grant found | **Not bundled.** Treated as bring-your-own-content (BYOC) via `local_content/` until GovRAMP grants explicit permission (worth emailing info@govramp.org — ask before assuming).                                         |
| **HITRUST CSF**       | Contractually licensed content                                                                                                    | **Never bundled.** BYOC only — you supply your own MyCSF/CSF export under your own license, and it's parsed locally. It is never committed, never uploaded anywhere by this tool, and stays out of git via `.gitignore`. |

**Rule of thumb:** if you're not certain a document is a public-domain
government work, it goes in `local_content/` (gitignored), not `data/`.

## Architecture

```
config/                  Your local config (model, API key env var name, chosen frameworks)
data/frameworks/         Bundled, redistributable framework data (NIST, FedRAMP, ARC-AMPE)
local_content/           Gitignored. Drop your own HITRUST/GovRAMP exports here.
src/policyforge/
  llm/                    Provider abstraction. Ships Anthropic and Amazon Bedrock
                          (`pip install "policyforge[bedrock]"`); interface is designed
                          so a Vertex AI provider can be added later without touching
                          calling code.
  ingest/                 Parses framework sources (bundled markdown, BYOC exports) into
                          a common Control/Element schema.
  mapping/                Cross-framework control crosswalk logic.
  synthesis/              Topic-themed merge/dedupe engine (the "30 synthesis docs" pattern).
  generate/               Turns synthesized requirements + org context into draft
                          policies/standards/procedures.
  export/                 Markdown / Confluence exporters.
scripts/
  vault_to_data_etl.py    One-time helper: converts an existing Obsidian vault's NIST
                          control notes (public-domain content only) into this project's
                          data schema.
```

## Setup

1. `python -m venv .venv && source .venv/bin/activate`
1. `pip install --upgrade pip setuptools` — a fresh venv's own pip/setuptools are
   often a version behind, which otherwise shows up as a confusing false-alarm-feeling
   failure the first time you run `pip-audit` (see "Running the quality checks" below).
1. `pip install -e ".[dev]"`
1. `cp config/config.example.yaml config/config.yaml` and fill in your model choice
   and the *name* of the environment variable holding your API key (not the key itself).
1. `export ANTHROPIC_API_KEY=sk-...` (or whatever env var name you configured)
1. `pre-commit install` — sets up the secrets/dependency scanner to run before every commit.
1. `curl -o LICENSE https://polyformproject.org/licenses/shield/1.0.0.txt` — replace the
   placeholder LICENSE with the real text before your first public push.
1. `policyforge llm-check` — confirms your API key and model work.

## Repo hygiene / scanning

Before every commit and on every push, this repo is designed to run:

- **gitleaks** — scans staged changes for API keys, tokens, and secrets so you never
  accidentally commit your Anthropic key or an employer-specific config.
- **pip-audit** — checks dependencies for known CVEs.
- **bandit** — static analysis for common Python security issues in this codebase.
- **mdformat** — checks that any markdown this project generates (or that lives in the
  repo itself) is well-formed CommonMark. This is the enforcement mechanism behind
  the "Markdown is the primary deliverable" requirement above, not just a style nit.

See `.pre-commit-config.yaml` and `.github/workflows/ci.yml`.

### Running the quality checks yourself

`python scripts/check.py` runs all four checks in one command (pytest,
bandit, pip-audit, mdformat, plus gitleaks if you have the binary
installed — see the script's docstring for why gitleaks is optional
locally but always runs in CI). This is the same verification pass used
while building this scaffold, just packaged as a script instead of typed
commands. Exits non-zero if anything fails, so it's safe to use as a
pre-push gate.

## A note on using this at work

If you plan to install and run this against your employer's compliance work, check
your employment agreement's IP-assignment / moonlighting clause first — many
agreements assign the employer rights to side projects that overlap your job duties,
even when built on personal time, especially in security roles. Keeping the *engine*
(this repo) and your *employer-specific content* (control status, vendor names,
internal workflow docs) in entirely separate places — this repo vs. a private,
non-public vault — is what keeps that boundary clean. Never commit employer-specific
content, org context, or exported policies to this public repo.

## Roadmap

- [x] `mapping/crosswalk.py` — cross-framework control correspondence
- [x] `synthesis/merge.py` — the dedupe/merge-to-prose engine
- [x] `generate/policy_writer.py` — Standard tier (`generate_standard`), Policy tier
  (`generate_policy`), and Procedure tier (`generate_procedure`), org-context-aware,
  producing canonical portable markdown (see "Document hierarchy" and "Output format
  priority" above)
- [x] Confluence exporter — converts canonical markdown to Confluence storage format
  via `markdown-it-py`
- [x] Amazon Bedrock LLM provider (`llm/bedrock_provider.py`) — install with `pip install "policyforge[bedrock]"`
- [ ] `ingest/byoc_loader.py` — implement HITRUST/GovRAMP export parsing once a sample export is in hand
- [ ] GovRAMP: follow up on redistribution permission; if granted, move from BYOC to bundled
- [ ] Optional: Vertex AI Model Garden provider
