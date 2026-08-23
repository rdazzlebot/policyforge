---
name: policyforge
description: Operate the PolicyForge CLI in this repo to draft, publish, and version cross-mapped information-security policies/standards/procedures from NIST 800-53/FedRAMP/ARC-AMPE/HITRUST/GovRAMP. Use whenever the user asks to generate, draft, or update a policy/standard/procedure/SOP; synthesize or map compliance controls/frameworks; publish to or pull from Confluence; check what changed in a policy over time (version history/drift); or set up/troubleshoot the policyforge CLI (config.yaml, API key, llm-check, "temperature deprecated" errors). Covers the etl-vault -> map -> synthesize -> generate -> export/import-confluence -> history pipeline.
---

# PolicyForge operator skill

You are operating the `policyforge` CLI in this repo, not writing new
features for it. For deep architecture/licensing detail this skill doesn't
cover, read `README.md` — it's the source of truth; this skill is the
"how do I actually run this" companion to it.

## Before anything: environment check

1. Activate the venv: `.venv/Scripts/activate` (Windows) or
   `source .venv/bin/activate` (Unix). If `.venv` doesn't exist, run
   `pip install -e ".[dev]"` first (see README "Setup").
1. Confirm `config/config.yaml` exists (copied from `config/config.example.yaml`,
   gitignored, never commit it). If missing, ask the user for their `llm.provider`,
   model, and org details before proceeding — don't invent org name/industry/vendors.
1. Run `policyforge llm-check`. If it fails:
   - `Environment variable X is not set` — the user needs to export their API key
     in their *own* shell session (PowerShell: `$env:VAR = "..."`; cmd:
     `set VAR=...`; bash: `export VAR=...`). You likely can't set it for them if
     your shell tool is a different process than their interactive terminal —
     say so plainly and ask them to run it themselves, then re-check.
   - Any other error — read it; don't guess. AnthropicProvider/VertexProvider
     already retry once without `temperature` if a model rejects it as
     deprecated, so that specific failure mode is already handled.

## The pipeline, in order

Only steps 3-4 are needed per new topic once steps 1-2 have been run once for
the org's framework data.

1. **`policyforge etl-vault --controls-dir <path> [--out <path>]`** — one-time
   (or refresh-on-demand): parse NIST 800-53 control notes from a vault into
   `data/frameworks/nist-800-53-r5/controls.json`. Skip if that file already
   exists and is current.
1. **`policyforge map --controls <path> [--out <path>]`** — build/refresh the
   cross-framework crosswalk (`data/frameworks/crosswalk.json`). Re-run after
   any change to controls.json.
1. **`policyforge synthesize --topic "<name>" --nist-controls <IDs> --controls <path>... [--crosswalk <path>] [--out-dir <path>]`**
   — merge/dedupe controls for one topic (e.g. "Password & Credential
   Management", `IA-5,IA-5(1)`) into synthesized requirement prose. This is
   the only stage where you need to know NIST control IDs — ask the user or
   infer from context if they only named a topic in plain language.
1. **`policyforge generate --tier standard --synthesis <synthesis.md>`**
   first, then, once the Standard exists:
   **`policyforge generate --tier policy --synthesis <synthesis.md> --standard <standard.md>`**
   and/or
   **`policyforge generate --tier procedure --synthesis <synthesis.md> --standard <standard.md>`**.
   Policy and Procedure both require `--standard` — they reference it by
   title (auto-extracted). Never generate Policy/Procedure before Standard
   exists for that topic. Each successful `generate` auto-records into local
   version history (see below) — no extra flag needed.

Optional, after generating:

- **`policyforge export-confluence --doc <path> --space <KEY> --title "<title>" --host <url> [--parent-id <id>] [--dry-run]`**
  — publish. Requires `CONFLUENCE_API_TOKEN` (and usually `CONFLUENCE_USERNAME`)
  set in the user's shell. Always offer `--dry-run` first to show the
  converted storage format before actually publishing, unless the user
  clearly just wants it published.
- **`policyforge import-confluence --tier <tier> --name <name> --space <KEY> --title "<title>" --host <url>`**
  — pull the page's *current live* content back and diff it against the last
  locally-recorded version for that tier/name (drift detection — did someone
  hand-edit the published page?). `--name` must match the filename stem
  `generate` used (e.g. `auth-mgmt` for `auth-mgmt.md`).
- **`policyforge history --tier <tier> --name <name> [--diff latest | --diff N:M]`**
  — list or diff the local version history for one document. Use this
  whenever the user asks "what changed" or "show me the history" for a
  policy/standard/procedure.

## Guardrails — do not skip these

- **Never commit `output/` or `config/config.yaml`.** Both are gitignored on
  purpose — generated policies are org-specific content, not engine code. If
  you're asked to commit changes, `git status` first and make sure nothing
  under those paths is staged.
- **`generate-parser` sends real file content to the LLM API.** Before
  running `policyforge generate-parser --framework hitrust|govramp --sample <path>`
  against a *real* HITRUST/GovRAMP export, confirm with the user that their
  license actually permits sending that content to a third-party API
  processor — don't just proceed because they asked. A synthetic/dummy
  sample needs no such confirmation.
- **BYOC frameworks (HITRUST, GovRAMP) never go in `data/frameworks/` or
  get bundled/committed.** They live in `local_content/` (gitignored) only.
  See README's licensing table before touching either framework's data.
- **Org context (`config.yaml`'s `org:` block) drives placeholders.** If
  `vendors` is empty, generated docs use `[Square-Bracket Vendor]`
  placeholders rather than inventing product names — that's correct
  behavior, not a bug to fix.
- **Local version history (`output/.history/`) is a convenience, not the
  system of record.** Don't present it as an authoritative changelog if the
  user's actual system of record is Confluence/Git/Drata — it's a
  supplementary local trail, per `history/version_store.py`'s docstring.

## Typical end-to-end request

User: "Draft a password policy and standard for us, then publish the
standard to Confluence."

1. Check env (above).
1. `synthesize --topic "Password & Credential Management" --nist-controls IA-5,IA-5(1) --controls data/frameworks/*/controls.json`
1. `generate --tier standard --synthesis output/synthesis/password-credential-management.md`
1. `generate --tier policy --synthesis output/synthesis/password-credential-management.md --standard output/standards/password-credential-management.md`
1. Show the user both drafts before publishing anything.
1. On confirmation: `export-confluence --doc output/standards/password-credential-management.md --space <ask if unknown> --title "<from doc title>" --host <ask if unknown>`

Don't skip step 5 — these are compliance documents; publish only after the
user has actually looked at the draft.
