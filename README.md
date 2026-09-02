# PolicyForge

**Security compliance documentation for healthcare organizations running
HITRUST and a NIST-based program at the same time.**

PolicyForge turns overlapping control catalogs — HITRUST CSF, the HIPAA
Security Rule, NIST 800-53, FedRAMP, ARC-AMPE — into policies, standards and
procedures an engineer can actually execute, organized so that **every topic
has one clearly accountable owner** rather than being split across teams. It
uses an LLM you bring the API key for, grounded strictly in the control text
you supply rather than the model's own recollection of what a framework
says.

This project separates two things that are easy to accidentally tangle
together: **the engine** (this code — the crosswalk logic, the merge/dedupe
methodology, the generation pipeline) and **the content** (the frameworks
themselves, some of which are freely redistributable and some of which are
not). See [Licensing model](#licensing-model-per-framework) below before you
add any framework content to this repo.

## The problem this solves

A healthcare organization rarely gets to pick one framework. It carries the
HIPAA Security Rule because it's law, HITRUST CSF because a payer or partner
contract demands certification, and often a NIST-based program on top —
800-53 directly, or through FedRAMP, ARC-AMPE, or a customer's security
addendum. These catalogs cover largely the same ground in different words,
at different granularity, with different prescribed values.

The obvious fix is a crosswalk, and both NIST and HITRUST publish one. In
practice the published mappings are necessary but nowhere near sufficient,
for reasons that are structural rather than fixable by a better spreadsheet:

- **They are bare ID pairs, often with no stated relationship.** This repo
  ingests NIST's own HIPAA-to-800-53 crosswalk from CPRT. Its OLIR format
  has fields for a relationship type (*equal to*, *subset of*, *intersects
  with*) and a rationale — and in the published data those fields are
  **empty**, for that crosswalk and for the other OLIR crosswalks alongside
  it. What you get is "these two identifiers are related somehow."
- **The fan-out is unusable at the row level.** That same crosswalk is 278
  pairs across 68 HIPAA citations and 108 NIST controls. One citation —
  § 164.316(b)(2)(iii), on updating documentation — maps to 21 separate NIST
  controls. An engineer handed that row has a matrix, not a task.
- **Granularity doesn't line up.** NIST AC-2 is twelve lettered parts,
  a. through l., several with sub-items of their own. A mapping to a HITRUST
  requirement points at *AC-2*, not at which of those parts it actually
  corresponds to.
- **The prescribed values are missing on one side and specified on the
  other.** SP 800-53 Rev 5 carries 1,600 organization-defined parameters —
  1,467 assignments (`[Assignment: organization-defined frequency]` and
  friends) plus 133 selections. HITRUST frequently states a concrete value
  instead, and varies it by implementation level. A crosswalk row reconciles
  none of this: someone still has to decide the number, once, and defend it
  to both assessors.
- **The scoping axes are different.** HITRUST implementation levels are
  driven by organizational risk factors (record volumes, regulatory
  exposure). NIST baselines are driven by FIPS 199 impact categorization.
  Level 2 is not Moderate.
- **Control text is declarative; procedures are imperative.** "Review
  accounts for compliance with account management requirements
  [Assignment: frequency]" and "every quarter, the IAM team exports the
  Okta user list, reconciles it against Workday active employees, and opens
  a ticket per exception" are different genres of writing. Nothing in a
  crosswalk performs that translation.
- **No framework tells you who does the work.** AC-2 alone touches identity
  engineering, HR onboarding/offboarding, and individual application owners.
  The catalog is silent on ownership, which is precisely the thing an
  operational document needs to establish.

Reconciling all of that is a language problem before it is a data problem —
which is why the merge step here is LLM-driven rather than a lookup table.
It is doing work a join cannot do: collapsing requirements that say the same
thing in different vocabulary, keeping genuinely conflicting ones apart,
carrying the stricter prescribed value forward with its source attached, and
rewriting declarative control language as ordered steps — while every
statement stays tagged back to the controls it came from, so the traceability
an assessor needs survives the rewrite.

## One topic, one team

Compliance catalogs are organized for the person auditing the work: by
control family, in the order the framework's authors chose. Engineering
organizations are organized around the people doing the work: by system, by
service, by on-call rotation. Those two shapes almost never coincide, and
most compliance documentation fails because it keeps the auditor's shape and
hands it to engineers.

The synthesis step in this pipeline is a transpose. Instead of generating one
document per control — 300-plus artifacts, none of which anyone owns —
it generates one document per **topic**, and every topic has a single
accountable team.

The test is **ownership, not step count**. A topic can — and usually does —
involve several teams' work. User lifecycle touches HR for the joiner and
leaver signal, IAM for provisioning, IT support for hardware, and individual
app owners for entitlements. That's still *one* topic, because one team can
comfortably own the process end to end. What breaks a topic is not
cross-team steps; it's cross-team *accountability*, where two owners each
assume the other has it.

So a topic is well-formed when:

- **One team can comfortably own the whole process.** There's a clear owner
  who can describe it end to end, chase the handoffs, and answer for the
  outcome — not a process split down the middle between two teams who each
  own half.
- **Its handoffs live inside it, and the owner is accountable for them
  working.** This is deliberate. Most compliance failures aren't inside a
  team's remit, they're at the boundary — HR processes a termination and the
  deprovisioning signal never reaches IAM. Putting the seam inside a topic
  with a named owner is what makes someone responsible for the seam.
- **It has a coherent operational rhythm.** Continuous, on-change, quarterly.
  A topic that mixes a real-time detection duty with an annual attestation
  is two rhythms wearing one hat.
- **Its evidence collects together.** The same export, dashboard or ticket
  query should satisfy most of the requirements underneath it. This is where
  the multi-framework overlap finally pays off: one quarterly access-review
  artifact can answer HITRUST, HIPAA and 800-53 at once, but only if the
  requirements were gathered into one topic first.
- **It reads like a runbook, not a restatement.** If the output could be
  mistaken for a paraphrase of the control catalog, the topic hasn't earned
  its place.

**Around 25 topics is the practical ceiling.** Fewer than that and a topic
grows too broad for one team to own comfortably; many more and the topics
start slicing the same process apart, which reintroduces the split
accountability the model exists to avoid — and the cross-framework overlap
stops consolidating, because the shared requirements scatter across
neighbouring topics instead of gathering in one.

Twenty-odd procedures with named owners is a program someone can run. Three
hundred control write-ups is a document set that goes stale the week after
the audit.

The ownership axis is also what makes the multi-framework problem tractable
rather than multiplicative. HITRUST, HIPAA and 800-53 each have something to
say about access review; they say it three times, in three vocabularies, at
three levels of specificity. Gathered into one topic, that becomes a single
procedure the IAM team executes, with three sets of citations attached — and
the next framework added to the mix costs one more citation per requirement,
not a fourth parallel document set.

### The topic registry

Topics are declared in `config/topics.yaml` — gitignored, because it names
your internal teams. Copy `config/topics.example.yaml`, which ships a
20-topic starter set that fully covers the Low, Moderate and High baselines,
and change the owners to your teams.

```yaml
topics:
  - name: Identity Lifecycle & Access Review
    owner: IAM Engineering
    cadence: quarterly
    nist_controls: [AC-1, AC-2, AC-3, AC-5, AC-6, AC-14, IA-4, IA-12, PS-4, PS-5]
    evidence:
      - Identity provider user export
      - HR active-employee roster
      - Access review tickets with sign-off
```

`nist_controls` are **anchors, not an exhaustive list**: anchoring AC-2 also
claims AC-2(1) through AC-2(13), so a topic doesn't have to enumerate
enhancements. Anchor an enhancement directly only when it genuinely belongs
to another team — a direct claim beats an inherited one, which is how
AC-2(1) can sit with Platform Engineering while AC-2 stays with IAM without
either becoming contested.

### Checking ownership: `policyforge coverage`

```
policyforge coverage \
  --controls data/frameworks/nist-800-53-r5/controls.json \
  --controls data/frameworks/hipaa-security-rule/controls.json \
  --baseline moderate
```

```
Coverage — scope: Moderate baseline
============================================================
  In scope        287
  Owned           287 (100%)
  Orphaned        0
  Contested       0
...
HIPAA reachable via the crosswalk
------------------------------------------------------------
  65 of 75 requirements map to an owned NIST control
```

It reports four things, and needs no LLM — it's set arithmetic over the
registry:

- **Orphaned** — in-scope controls no topic claims. Nobody is doing the work,
  and nobody knows nobody is doing it.
- **Contested** — controls two or more topics claim. The worse of the two: on
  paper it looks covered, while each owner assumes the other has it.
- **Unknown anchors** — control IDs that don't exist in the catalog, i.e.
  typos. Distinguished from *anchored but out of scope*, which is normal —
  the PM and PT families sit in no baseline at all, so a topic legitimately
  anchors controls a Moderate analysis doesn't include.
- **Cross-framework reachability** — because topics anchor NIST controls and
  the crosswalk maps other frameworks onto them, an owned NIST control also
  accounts for the HIPAA requirements mapped to it. Same orphan question,
  asked from the assessor's side.

`--baseline` matters: "orphaned" only means something relative to a defined
scope. `--strict` exits non-zero when anything is orphaned, contested or
mis-anchored, which makes it usable as a CI gate; `--json` emits the report
for further processing.

### From registry to document

`synthesize --topic-name` takes a topic straight from the registry, so its
anchor controls and its owning team come from one declared place instead of
being retyped on the command line:

```
policyforge synthesize --topic-name "Media Handling & Disposal" \
  --controls data/frameworks/nist-800-53-r5/controls.json \
  --controls data/frameworks/hipaa-security-rule/controls.json
```

The owner then has to survive the gap between two commands — `synthesize`
knows it, `generate` needs it — so it travels *in* the synthesis file, as
YAML frontmatter:

```yaml
---
topic: Media Handling & Disposal
owner: IT Asset Management
cadence: continuous
evidence:
  - Certificates of destruction
  - Media transport log
nist_controls: [MP-1, MP-2, MP-3, MP-4, MP-5, MP-6]
---
```

`generate` reads that back and names the real team wherever the document has
to say who performs a step, who reviews, or who answers for the outcome —
instead of falling back to `[Responsible Team]`. The cadence and evidence
artifacts flow through the same way, so a generated Standard cites the
actual review frequency and the actual artifacts the topic is expected to
produce.

The frontmatter is optional and additive. `synthesize --topic <name> --nist-controls <ids>` still works for a one-off topic that isn't in the
registry; it writes no frontmatter, and says so, and the resulting document
uses placeholders exactly as before. Synthesis files written before any of
this existed still generate unchanged.

## Company context

Frameworks describe what must be true. They can't describe *your* org — and
that difference is most of the distance between a document template and a
procedure someone can follow on a Tuesday. That org-specific half lives in
one gitignored file, `config/config.yaml` (copy `config/config.example.yaml`
to start), and it feeds every generation stage.

```yaml
org:
  name: "Northwind Health"
  industry: "Healthcare provider"
  vendors: [Okta, AWS, CrowdStrike, Workday]

system:              # NIST SP 800-18 plan elements, used by `policyforge ssp`
  name: "Patient Portal"
  overall_categorization: "Moderate"
  owner: "Platform Engineering"
```

It matters more than its size suggests, for three reasons.

**It decides whether output is specific or generic.** Every generator here
is under strict instructions never to invent a vendor, a frequency, an owner
or a tool. What it doesn't know, it writes as a `[Square-Bracket Placeholder]` — deliberately, because a plausible-sounding invention in a
compliance document is worse than an obvious blank. The context file is how
you convert those blanks into specifics. With `vendors: [Okta]`, an access
control procedure names Okta; without it, you get `[Identity Provider]` and
a job for a human. Placeholders are the correct default, not a failure —
but the more context you supply, the fewer of them you're left editing.

**It's a boundary, not just a convenience.** `config.yaml` is gitignored
because it holds your org's name, vendor stack, system inventory and the env
var naming your API key. That keeps the engine publishable while the
org-specific content stays local — the same split that lets licensed HITRUST
content be processed here without ever being committed.

**It makes regeneration cheap.** Swapping an EDR vendor or re-categorizing a
system is a config edit and a re-run, not a pass through every document
looking for the old product name. The same property makes the documents
reproducible: same context plus same control data yields the same output.

### A known rough edge

`vendors` is a flat list, so the model has to *infer* what each product is
for. In a real run against AC-7 with `vendors: [Okta, AWS]`, the draft came
back as:

> …enforces unsuccessful logon attempt limits through **\[Identity Provider
> — Okta\]**, the identity provider for the system.

It hedged a vendor it had actually been given, wrapping a known name in
placeholder brackets, because nothing told it Okta was the IdP rather than,
say, the HR system. Role-keyed context — `identity_provider: Okta`,
`edr: CrowdStrike`, `hr_system: Workday` — would make that substitution
deterministic instead of inferred. See the roadmap.

## Status

The full pipeline is functional end-to-end: `etl-oscal` -> `map` ->
`synthesize` -> `generate` -> `export-confluence` (optional), plus `ssp` as a
separate output path. All three LLM providers (Anthropic, Bedrock, Vertex),
the control loaders, crosswalk builder, LLM-driven synthesis/generation
stages, Confluence export/import, and local version history are all wired up
and tested. HITRUST/GovRAMP BYOC loaders remain stubs pending a sample export
to parse against — see `ingest/byoc_loader.py` and
`policyforge generate-parser`.

Bundled and populated from public-domain sources, each re-fetchable:

| Data                                                                            | Command               | Source                          |
| ------------------------------------------------------------------------------- | --------------------- | ------------------------------- |
| NIST 800-53 Rev 5 (300 controls, 714 enhancements, Low/Moderate/High baselines) | `etl-oscal`           | NIST's OSCAL content repository |
| HIPAA Security Rule (34 standards, 41 implementation specifications)            | `etl-hipaa`           | eCFR's public API               |
| HIPAA-to-800-53 crosswalk (278 mappings over 108 NIST controls)                 | `etl-hipaa-crosswalk` | NIST's CPRT catalog             |

Because the crosswalk is wired into `mapping/crosswalk.py`, `synthesize`
pulls HIPAA requirements into a NIST-anchored topic alongside NIST/FedRAMP,
and `ssp` shows each 800-53 control's HIPAA equivalents as a column.

### Why HITRUST is bring-your-own-content

The table above is the public-domain half of the overlap. The HITRUST half
isn't there, and won't be: **HITRUST CSF is licensed content.** Its
requirement text and its mappings can't be redistributed, so no open-source
project can ship them — not this one, not any other. That is a licensing
fact, not an oversight, and it's the reason a healthcare organization can't
just download a solved HITRUST-to-NIST reconciliation from anywhere.

This project's answer is to split the problem along the licence line:

- **The engine is open.** Crosswalk logic, topic synthesis, the
  Policy/Standard/Procedure generators, the SSP builder — all here, all
  public.
- **The public-domain content is bundled.** NIST 800-53, HIPAA, and NIST's
  own HIPAA-to-800-53 crosswalk, each re-fetchable from source.
- **You bring your own HITRUST.** Your MyCSF export, under your own licence,
  parsed from `local_content/` (gitignored). It is never written into
  `data/frameworks/`, never committed, never uploaded by this tool.
- **The LLM closes the gap between them.** This is the part that makes the
  arrangement work rather than merely legal. Even with both halves in hand,
  the published mappings are the bare ID pairs described above. Reconciling
  your licensed HITRUST requirements against the public NIST controls —
  collapsing the duplicates, keeping the real conflicts, carrying the
  stricter prescribed value — is the language work the LLM does locally,
  against content you already hold a licence to.

`policyforge generate-parser --framework hitrust --sample <path>` drafts the
loader from a real export. `ingest/byoc_loader.py`'s `load_hitrust_export` is
currently a stub, so today the pipeline reconciles HIPAA against 800-53 but
not yet HITRUST against either — that's the next thing worth building. Read
[Generating a BYOC parser](#generating-a-byoc-parser-from-a-sample-export)
first: that command sends your export's contents to your LLM provider, and
whether your licence permits that is a question to answer before running it,
not after.

## Input adapters

Ingestion is pluggable: every loader in `ingest/` parses one source format
into the same `Control` schema, and nothing downstream (mapping, synthesis,
generation, export) knows or cares which one produced the data.

| Loader                      | Command               | Reads                                                                                                                            |
| --------------------------- | --------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `oscal_loader.py`           | `etl-oscal`           | NIST's OSCAL release of SP 800-53 — the default way to populate 800-53 data                                                      |
| `hipaa_loader.py`           | `etl-hipaa`           | eCFR's XML for 45 CFR 164 Subpart C                                                                                              |
| `hipaa_crosswalk_loader.py` | `etl-hipaa-crosswalk` | NIST CPRT's HIPAA-to-800-53 OLIR catalog                                                                                         |
| `nist_vault_loader.py`      | `etl-vault`           | Markdown notes in one specific shape (YAML frontmatter + `## headings` + `[[wikilinks]]`) — the format this project started from |
| `byoc_loader.py`            | —                     | Your own licensed HITRUST/GovRAMP exports (stubbed; see `generate-parser`)                                                       |

`nist_vault_loader.py` is the only one that touches Obsidian-flavoured
markdown, and it's an *option*, not a dependency — `etl-oscal` needs nothing
but network access. It's kept because it reads one thing the OSCAL catalog
doesn't carry: a "Cross-Framework Mappings" table, which is currently the
only route to FedRAMP crosswalk data. Nothing about it is Obsidian-specific
at runtime; point it at any directory of markdown in that shape and it works
identically.

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

## Confluence import and local version history

`export/confluence_importer.py` is the reverse of the exporter: it pulls a
page's current content back out of Confluence and converts it to markdown.
Two things this is for:

- **Bootstrapping** a policy that already lives in Confluence (written by
  hand before this tool existed) into the pipeline, so it can be tracked
  going forward.
- **Drift detection**: `policyforge import-confluence --tier <tier> --name <name> ...` records the imported content into the *same local version
  stream* `policyforge generate` uses for that tier/name, so you can diff
  what this tool last generated against what's actually live — e.g. after
  someone hand-edits the published page directly.

Round-trip fidelity (markdown -> Confluence -> markdown) is only guaranteed
for documents this tool itself published — a hand-authored page using
Confluence-native macros (panels, expand blocks, page properties) will
import with those macros passed through as raw HTML rather than clean
markdown.

**Local version history** (`history/version_store.py`) is a lightweight,
offline changelog every `generate` and `import-confluence` run writes into
`output/.history/<tier>/<name>/` — one full snapshot, one unified diff
against the previous version, and one index line per version. Regenerating
identical content is a no-op (it doesn't pad the history). This is **not**
a replacement for your org's actual system of record — Confluence's own
page version history, git history if you commit `output/` somewhere
private, a GRC platform like Drata. It exists because those systems only
see what got *published*; this also captures drafts you regenerated but
never pushed. Since `output/` is gitignored, this history is local to your
machine, not shared or backed up by this repo.

```
policyforge generate --tier standard --synthesis output/synthesis/auth-mgmt.md
# -> Recorded 'standard/auth-mgmt' v1 in output/.history (+42/-0 lines).

policyforge history --tier standard --name auth-mgmt
# -> v1  2026-08-23T22:10:00+00:00  generate  +42/-0  a1b2c3d4e5f6

policyforge import-confluence --tier standard --name auth-mgmt \
  --space ENG --title "Authenticator Management Standard" \
  --host https://yourorg.atlassian.net/wiki
# -> Differs from the last recorded version (v1) — recorded as
#    'standard/auth-mgmt' v2. Run `policyforge history --tier standard
#    --name auth-mgmt --diff 1:2` to see what changed.

policyforge history --tier standard --name auth-mgmt --diff 1:2
# -> unified diff between what was generated and what's actually live
```

## Editing a live page

`policyforge edit-confluence` takes a plain-language instruction, fetches the
page, **plans** the edits, shows you the plan and the resulting diff, and
publishes only when you ask it to.

```
policyforge edit-confluence \
  --instruction "Tighten the access review cadence to monthly, and add a
                 section on how review outcomes are recorded." \
  --space ENG --title "Access Control Standard" \
  --host https://yourorg.atlassian.net/wiki
```

Plan and execution are deliberately two separate LLM calls. The plan is the
review surface: six steps read in a few seconds catch "you're about to delete
the exceptions section" far more reliably than diffing a regenerated page,
rejecting a bad plan costs one call instead of a careful read of the whole
document, and the plan itself records what was asked, what was intended, and
what was declined — which is the provenance a change to a live policy page
needs.

The planner is allowed to refuse, and does. Asked to shorten a review cadence,
add a section, *and* delete a requirement, it planned the first two and put
the third under **Needs your judgement**:

> Deleting the least privilege requirement [NIST AC-6] would remove a stated
> access control requirement tied to a NIST citation; this narrows the
> standard's scope and should be confirmed by a human before removal.

It also listed what it wouldn't guess at under **Not attempted** — where the
new section should live, and what system records the outcomes — and filled
the gaps it did write with `[Access Review Record Repository]` placeholders
rather than inventing a tool.

### Editing a topic's whole document set

A real change rarely lands in one document. "Access reviews move from
quarterly to monthly" belongs in the Standard (which states the requirement)
and the Procedure (which carries the steps), and usually shouldn't touch the
Policy at all. `policyforge edit-topic` applies one instruction across the
set, resolving the pages from the topic registry:

```yaml
# config/topics.yaml
- name: Identity Lifecycle & Access Review
  owner: IAM Engineering
  nist_controls: [AC-1, AC-2, AC-3, ...]
  confluence:
    space: SEC
    pages:
      policy: Access Control Policy
      standard: Access Control Standard
      procedure: Access Review Procedure
```

```
policyforge edit-topic   --instruction "Access reviews move from quarterly to monthly."   --topic-name "Identity Lifecycle & Access Review"   --host https://yourorg.atlassian.net/wiki
```

This is not three single-page runs in a loop. Two things make it different:

- **Each page is planned at its own altitude.** The planner is told which
  tier it's reading and that the siblings exist and are being edited in the
  same run, so it doesn't paste a threshold change into the Policy or restate
  the Standard's requirement in the Procedure. A page whose plan comes back
  empty is left completely untouched — no rewrite call, no diff, no publish —
  rather than having an edit forced into it to justify the run.
- **Nothing publishes until everything is ready.** Every page is fetched,
  macro-checked, planned and rewritten before any of them is written back,
  and you confirm the set once. Confluence has no cross-page transaction, so
  this narrows the window rather than closing it: a failure *during* the
  publish loop is reported page by page, naming exactly what landed and what
  didn't, so a half-updated set is visible instead of silent.

`--tiers standard,procedure` narrows the run when you already know where the
change belongs. Everything in **The gates** below applies to `edit-topic`
identically.

### The gates

This is the only part of PolicyForge that changes something outside the repo,
so the defaults are conservative:

- **Dry run by default.** Without `--apply` it plans, rewrites, writes the
  result to `output/edits/` and shows the diff — and touches nothing in
  Confluence. `--apply` publishes; without `--yes` it still asks first.

- **Version-guarded writes.** The page version read at fetch time is checked
  at publish time, so an edit made while you were planning fails loudly
  instead of being silently overwritten. This is why editing uses
  `update_page_body` rather than `export_to_confluence` — the latter re-reads
  the version and always wins, which is right for publishing a generated
  document and wrong for editing what's already there.

- **Macro refusal.** The edit path is storage format → markdown → edit →
  storage format, which is lossless only for the `code` macro this project's
  own exporter emits. A page containing a panel, expand block or page-property
  macro is **refused**, not warned about, because editing it would flatten
  parts nobody asked to change. `--allow-macros` overrides once you've read
  what will be lost.

- **Citation and section checks.** After the rewrite, every inline source tag
  (`[NIST AC-2 | HIPAA 164.308(a)(3)(i)]`) present before is checked for
  afterwards, as is every heading the plan didn't ask to remove. Losses are
  reported before the publish prompt. A rewrite that reads fine but has
  quietly dropped an assessor's traceability is the most damaging failure
  this tool could have.

- **Local history either way.** The page's "before" state is recorded to
  `output/.history/confluence/<slug>/` as soon as it's fetched — before any
  LLM call — so there's something to diff and restore from even if the run is
  abandoned. Confluence keeps its own page versions too; this is the local
  copy.

- **The plan is kept, not just printed.** Terminal output scrolls away, and
  Confluence's own page history records *what* changed but not why. So the
  plan — the instruction, each step, what was flagged under **Needs your
  judgement**, and what the model declined under **Not attempted** — is
  written to `output/edits/<slug>.plan.json` (dry runs included) and stored in
  the published version's history metadata alongside the model name and the
  page version the edit created. Read it back with:

  ```
  policyforge history --tier confluence --name access-control-standard
  ```

  which prints each revision with the plan that produced it:

  ```
  v1  2026-08-30T00:58:04+00:00  confluence-edit-before  +3/-0  cc2c08068aef
  v2  2026-08-30T01:14:22+00:00  confluence-edit-after   +1/-1  a9b5c9d61bc8
          asked: Access reviews move from quarterly to monthly.
          - [modify] Requirements: change the review cadence to monthly
          ! flagged: A monthly cadence increases reviewer workload.
          ~ not done: Left the Policy alone; cadence is a Standard-tier detail.
  ```

  The refusals matter as much as the edits: "the model was asked to delete
  the least-privilege requirement and declined" is exactly the kind of thing
  an assessor asks about a year later, and it exists nowhere else.

## Zardoz: asking questions instead of running commands

Everything above is one-shot — a command runs a pipeline stage and exits.
`policyforge zardoz` is the read side, and it is a conversation because the
questions people actually have about a policy set are follow-ups: *what's our
access review cadence?*, then *who owns that?*, then *does it satisfy the
HIPAA citation?* Each is cheap to answer and expensive to re-ask from a cold
command line.

```
policyforge zardoz sync --content-dir docs   # read a markdown tree (no credentials)
policyforge zardoz sync                      # or/and pull the published pages
policyforge zardoz                           # open the shell
```

Zardoz **reads; it does not write.** It can draft a `policyforge edit-topic`
command for you to run, but the publish path is not in its import graph at
all — a test walks the parsed AST of every module in the package to prove it,
which catches a lazy import inside a function body as readily as one at the
top of a file. That makes it a structural property rather than a rule
somebody has to remember during review.

### Two sources: files and pages

`zardoz sync` builds a local snapshot in `output/.zardoz/` rather than
reading live on every question. A Confluence round trip is 300–800ms,
answering one question well wants several, the API is rate-limited per token,
and a conversation is a burst rather than a trickle. The snapshot also means
retrieval can be developed and tested against fixtures — you cannot iterate
on ranking quality against a resource that answers slowly and differently
each time.

Documents come from either or both of:

- **a markdown content tree** (`--content-dir`, or `zardoz.content_dir`).
  Needs no network and no credentials at all, which means a repo-backed
  document set is answerable offline and trying Zardoz doesn't require an
  Atlassian account. Tier comes from the directory (`standards/` → standard,
  the layout `generate` already writes), owner from the topic registry or
  from the file's own frontmatter.
- **Confluence** (`--host`, or `zardoz.host`), a round trip per page.

Where both are configured **the tree wins**: in a repo-backed setup the file
is the source of truth and the page is a copy of it, so holding both would
cite one requirement twice and invite an answer quoting the stale half. A
file says which page it publishes to in its frontmatter, since a repo path
and a page title are different strings:

```yaml
---
title: Access Review Standard
tier: standard
topic: Access Review
owner: IAM Engineering
confluence:
  space: SEC
  title: Acme Access Review Standard
---
```

None of that is required — a file with no frontmatter still resolves from its
path and its first heading, which is what makes an existing tree loadable
without anyone editing forty files first.

### Trusted and supporting

Orthogonally to where a document came from, each carries a confidence level,
and the distinction is load-bearing:

- **trusted** — the document knows who is accountable for it, because the
  topic registry declares it or its frontmatter says so. An answer drawn from
  it can say who owns this and whether a threshold belongs there at all.
- **supporting** — real content nobody has claimed: a page from
  `zardoz.supporting_space`, or a file in the tree with no topic and no
  owner. Often more current than the governance set. Answers may draw on it
  and will say when they did.

```yaml
# config/config.yaml
zardoz:
  content_dir: docs                          # optional
  host: https://yourorg.atlassian.net/wiki   # optional
  supporting_space: RUNBOOKS                 # optional
```

Sync is forgiving of individual failures and unforgiving of silent ones. A
registry page whose title no longer matches is reported as a skip and the run
continues — one renamed page should not cost you the other nineteen topics.
A page two topics both declare is reported rather than synced twice, because
two teams claiming one document is the contested-ownership problem
`coverage` exists to surface, not a duplicate to quietly drop. A page that
vanishes from the registry has its cached file deleted, so a corpus can't
keep answering from documents that were deliberately removed.

But a sync that resolves **nothing** will not overwrite a corpus that has
documents in it. A typo'd space key used to empty the snapshot silently; the
way you found out was by getting worse answers, which is the worst way to
find out anything. Pass `--allow-empty` to clear it on purpose.

### Asking a question, and being told no

Anything you type that doesn't start with `/` is a question. Zardoz chunks
each document at its headings, ranks the chunks, and shows the passages that
bear on what you asked, each with a citation you can go and check:

```
zardoz> how long do we retain media protection documentation?

1. Media Handling & Disposal Standard § 4. Policy > 4.2 Documentation
   Retention and Maintenance  (standards/media-handling-disposal.md)
   All media-protection policies, procedures, and related action and
   assessment records must be maintained in written form ... retain such
   documentation for 6 years from the date of its creation ...
   [matched documentation, media, protection, retain]
```

**No embeddings, deliberately.** The highest-signal terms in a compliance
question are exact tokens — `AC-2`, `164.312(a)(1)`, `MP-6(1)` — where a
near-miss is not a near-answer but a *different control*, and semantic
similarity works against you: AC-2 and AC-3 embed almost identically and
mean different things to an assessor. So identifiers are matched exactly
(and an identifier anchors its enhancements, the same rule `coverage` uses),
and everything else is BM25 over terms of art that appear verbatim in both
the question and the document, because the people asking learned the words
from the documents. Every result can say which terms hit, which is what
makes ranking something you can iterate on.

**Refusing is a feature.** Ask about something the documents don't cover and
you get told so, rather than handed the least-bad section in the corpus:

```
zardoz> what is our vacation policy?
Nothing in the synced documents appears to bear on that.
```

That matters more than it sounds. A retriever that always returns
*something* is how a grounded-answers-only tool starts inventing things —
the model is handed irrelevant context, asked a question, and obliges. A
passage has to match a control identifier, a term distinctive enough to be
about something, or essentially the whole question. Ask about a control the
corpus never cites and you get nothing, which is itself the answer a
coverage check is looking for.

When the question's own words find nothing, and only then, the model is
asked to name the vocabulary a document would use instead — *how often do we
check who has admin?* becomes a search that also looks for *privileged
access*, *entitlements*, *recertification*:

```
zardoz> how often do we check who has admin?
(nothing matched those words; searched also for: privileged access,
 entitlements, recertification)
...
   [via privileged, entitlements (guessed)]
```

Exact first, expansion only on a miss. While retrieval is finding passages on
the user's own words there is nothing to gain by mixing in guessed vocabulary
and precision to lose. Guessed terms score at a discount, never count toward
whether the question was covered, and are reported separately — "matched
cadence" and "matched cadence, which we guessed you meant" are different
claims about the evidence. A question the corpus genuinely doesn't cover is
still refused: expansion can only find words that are actually in a document.

**Not embeddings, deliberately.** A vector index would work, and it would need
an embedding model: a local one is a multi-gigabyte dependency for a tool that
installs in seconds, and a hosted one is an API this project's default
provider doesn't offer, since Anthropic ships no embeddings endpoint. For a
corpus of tens to hundreds of documents, asking the already-configured model
to name the vocabulary gets the same recall on this failure mode, adds no
dependency, and has the property embeddings don't — you can read the expansion
and see exactly why a passage surfaced. What it doesn't cover is scale; the
seam for that is `RetrievalIndex.search(..., expansion=...)`.

### Answers you can check, or none

With an LLM configured, those passages become prose — with a citation on
every claim, and the sources listed under it:

```
zardoz> how long do we retain media protection documentation?

IT Asset Management must retain media-protection documentation for six years
from creation or last effective date, whichever is later. [1]

Sources:
  [1] Media Handling & Disposal Standard § 4. Policy > 4.2 Documentation
      Retention and Maintenance  (standards/media-handling-disposal.md)
```

The model is *asked* to cite every claim. It is not trusted to have done it.
Three things are checked after the reply comes back, because a prompt is a
request and a check is a guarantee:

- **a citation pointing at a passage that was never supplied** — a fabricated
  source, caught here rather than by the reader;
- **an answer with no citations at all** — prose with nothing behind it;
- **a quotation that isn't verbatim in the passage it cites** — the most
  damaging thing this tool could emit, because a quotation is what somebody
  pastes into a ticket or shows an assessor.

Anything found is printed *above* the answer, not below it, since a warning
is only useful if you see it before you believe the sentence it's about:

```
!! This answer did not pass its own checks:
!!   - it quotes text that appears in no passage: "records shall be destroyed
!!     after three years"
!! Read the passages below rather than trusting the prose.
```

And when retrieval finds nothing, **the model is never called at all**. There
is nothing to ground an answer in, and a model handed a question with no
context will answer it from what access control standards usually say — which
is exactly the failure this package exists to prevent, arriving in the most
plausible-sounding form available.

`/sources` shows the full text behind the last answer. Running with no model
configured is supported, not degraded: retrieval is entirely offline, so you
get the passages and draw the conclusion yourself.

### Asking about the programme, not the documents

Half the questions people have aren't answerable from any document, because
they're questions *about* the programme rather than about its prose. Which
controls does nobody own. What did the catalog change. How many values are
still undecided. No Standard states any of that — it falls out of the
registry, the catalogs and the ledger.

Those computations already existed as CLI commands. Zardoz can now reach
them, either by name or by asking:

```
zardoz> are we missing any controls in the audit family?

(ran /coverage)

Coverage — scope: all controls
============================================================
  In scope        1089
  Owned           36 (3%)
  Orphaned        1053
```

Seven analyses, each also a command: `/coverage`, `/parameters`, `/drift`,
`/history`, `/check`, `/frameworks`, `/roles`.

**The model routes; the report speaks.** Choosing which analysis a question
wants is a judgement about intent, which is what a model is for. Reporting
the result is not — a paraphrase of "14 orphaned controls" can become
"mostly in the audit family" with nothing to check it against, and a
compliance answer nobody can check is worth less than no answer. So the
model picks, and then the analysis's own output is printed **verbatim**.
Routing can be wrong in a way you can see, because the chosen skill is
always named. Reporting can't be wrong at all, because no model touches it.

Analyses answer with **nothing synced** — coverage comes out of the registry
and the catalogs, not the corpus — and without a model at all, via a
deliberately narrow keyword router. Narrow because a keyword router that
guessed broadly would be worse than none: it would hijack ordinary document
questions and send them somewhere that can't answer them.

Note the cost: routing adds one small model call per question (a dozen
output tokens), on top of answering.

### Follow-up questions

The questions people have about a policy set arrive in chains, and only the
first one stands on its own:

```
zardoz> how often are accounts recertified?
  Quarterly, by the system owner. [1]

zardoz> who owns that?
  (reading that as: who owns the quarterly account recertification?)
  IAM Engineering. [1]
```

"who owns that?" has one content word. Retrieved literally it finds nothing
and earns an honest refusal that helps nobody, because the question was
perfectly clear to anyone reading the exchange.

Resolution happens **before** retrieval, not inside answering. Retrieval is
keyword scoring; it has no mechanism for "that" and never will. The
alternative — hand the answering model the whole conversation and hope it
works out which passages *would* have been relevant — fails silently, because
the model answers from whatever it was given and nobody can tell the right
section was never fetched.

**The rewritten question is always shown.** Resolving "who owns that?" is a
guess about intent, and a good guess is indistinguishable from a bad one once
the answer is written; printing it means a wrong guess is visible rather than
convincing. `/forget` drops the context when you change subject, and a
question that already stands alone is never rewritten at all.

## The repo as the source of truth

The pipeline above ends at Confluence. It also runs the other way round, with
markdown in a git repository as the source of truth and Confluence as a
publishing target fed from it:

```
policyforge check                    # the pull-request gate, offline
policyforge publish --apply          # tree -> Confluence, on merge
policyforge pull --apply             # Confluence -> tree, when someone hand-edits
```

That inversion buys what a wiki cannot. A pull request is a review gate with
named approvers and a diff. `git log` is a history nobody can quietly rewrite.
A branch is a draft that doesn't confuse anyone reading production. And a
document set in a repo can be checked *before* it is published rather than
after somebody notices.

Each document names its own destination, so the file-to-page mapping lives in
the repository under review rather than in a workflow argument somebody has to
keep in step:

```yaml
---
title: Access Review Standard
tier: standard
owner: IAM Engineering
confluence:
  space: SEC
  title: Acme Access Review Standard
---
```

A file with no `confluence:` block is never published, which is how a draft
stays a draft.

**`check` is the piece that earns its keep.** It runs with no credentials, so
it works on a pull request from a fork, and it catches what survives review:

| Finding                               | Why it isn't visible in a diff                                                    |
| ------------------------------------- | --------------------------------------------------------------------------------- |
| Two files claiming one page           | Both publish; the second wins; the repo still holds two apparent sources of truth |
| A link to a renamed document          | The prose still reads correctly                                                   |
| A `confluence:` block with no space   | Nothing says where it goes until publish time                                     |
| Citations dropped since the synthesis | The traceability an assessor needs, gone from a paragraph that reads fine         |

Missing owners and tiers are warnings rather than errors — a repo mid-migration
is full of them, and a gate that cannot be satisfied gets switched off. `--strict`
promotes them once you've finished migrating.

### Wiring it to GitHub

`.github/workflows/content.yml` runs the two halves with deliberately
different privileges:

|           | When                    | Credentials                               | Can block a merge |
| --------- | ----------------------- | ----------------------------------------- | ----------------- |
| `check`   | every pull request      | none                                      | yes               |
| `publish` | after a merge to `main` | Confluence token, behind an `environment` | no                |

`check` needing nothing is what lets it run on a pull request from a fork —
exactly where a gate is worth having. `publish` is fenced the other way: only
on `push`, only from this repository, and behind a GitHub environment, because
a workflow that could write to a live wiki from an untrusted pull request is a
supply-chain problem rather than a convenience. It plans into the job log
before applying, so when a publish does something surprising there's a record
of what it believed it was doing.

Set `CONFLUENCE_HOST` as a repository variable, `CONFLUENCE_USERNAME` and
`CONFLUENCE_API_TOKEN` as secrets on the `confluence` environment. The
workflow does not pass `--allow-macros`, on purpose.

### Starting from a space nobody catalogued

`policyforge zardoz discover --space ENG` proposes a registry rather than
requiring you to write one:

```
Proposed 14 topic(s) from 61 page(s):

  Access Control    [UNASSIGNED]  [policy, standard]  AC-2, AC-6
                    (3 page(s) sharing the title stem 'Access Control')
  Backup and Restore [UNASSIGNED] [standard]          CP-9
```

Most of the grouping is already written down, just not as data: a governance
space names its pages by convention and cites the same controls across a
related set. Those signals are exact and free, and they place the majority of
a real space with no model involved — which matters for trust as much as cost,
since "these pages share a title stem and cite AC-2" is a reason you can check
and "a model thought so" is not. The LLM sees only the residue, and a page it
can't place is listed rather than forced into a topic.

**Every owner comes back `[UNASSIGNED]`.** Nothing in a page reliably says
which team is accountable — authorship isn't ownership, and the last editor is
usually neither. A wrong owner in a compliance artifact gets believed; a blank
one gets filled in. The file is written to `topics.proposed.yaml`, not
`topics.yaml`, for the same reason.

**Both directions refuse rather than degrade.** A page using `info`, `expand`,
`status` or page-properties macros converts to readable markdown and would be
flattened on the way back. `publish` skips such a page instead of overwriting
work nobody agreed to lose; `pull` refuses it instead of writing a file that
looks correct and destroys the macros the first time it is published. Both name
the page and the macros. `--allow-macros` exists on each and should not be
reached for to get past a skip you haven't read.

### Reading pages this tool didn't write

Bringing an existing Confluence space in asks more of the conversion than
round-tripping our own documents does, and it turned up a real defect.
Confluence stores cross-page links, user mentions and images as `<ac:link>`
and `<ac:image>` elements whose payload lives entirely in *attributes*.
markdownify knows only HTML, so it rendered all three as nothing at all:

| On the page                       | Was read as      | Now reads as                            |
| --------------------------------- | ---------------- | --------------------------------------- |
| `Owner: @Jane`                    | `Owner:` (blank) | the display name, or `@unresolved-user` |
| "see the Access Review Procedure" | "see ."          | the linked page's title                 |
| an architecture diagram           | *nothing*        | `[image: access-flow.png]`              |

The first row is why this mattered enough to fix before anything else. A
blank owner field doesn't read as a gap — it reads as *an answer*, and
"nobody owns this" is exactly the kind of confident wrong that a compliance
tool cannot afford. Where a mention can't be resolved to a name, it renders
as a conspicuous `@unresolved-user` and `sync` reports the count, rather than
leaving an empty cell.

This never mattered before because PolicyForge's own exporter emits only the
`code` macro, so round-tripping its own documents was always clean. It only
surfaces when reading somebody else's page.

**Readable is a lower bar than editable.** There is no required format —
almost any page converts, and headings and tables both survive intact, which
is what chunking, citation and requirements-in-a-table depend on. But a
hand-written page full of `info`, `expand`, `status` and page-properties
macros will be *readable* while `edit-topic` still refuses to touch it,
because writing it back would flatten those macros. `sync` flags those pages
so Zardoz can say "I can answer from this but not safely change it" instead
of drafting an edit that gets refused later.

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

Not all frameworks this project targets are safe to bundle and redistribute
in an open repo. Treat them differently:

| Framework               | Status                                                                                                                            | How this project handles it                                                                                                                                                                                              |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **NIST 800-53 Rev 5**   | US federal government work — public domain                                                                                        | Bundled directly in `data/frameworks/nist-800-53-r5/`, sourced from NIST's own OSCAL content repository via `policyforge etl-oscal`                                                                                      |
| **FedRAMP**             | US federal government work — public domain                                                                                        | Bundled directly in `data/frameworks/fedramp/`                                                                                                                                                                           |
| **ARC-AMPE**            | Published by CMS (federal agency) — public domain                                                                                 | Bundled directly in `data/frameworks/arc-ampe/`                                                                                                                                                                          |
| **HIPAA Security Rule** | US federal regulation (45 CFR 164 Subpart C) — public domain                                                                      | Bundled directly in `data/frameworks/hipaa-security-rule/`, sourced from eCFR's public API via `policyforge etl-hipaa`, with NIST's official 800-53 crosswalk attached via `policyforge etl-hipaa-crosswalk`             |
| **GovRAMP**             | GovRAMP's Terms & Conditions claim ownership of "documents, downloadable files" on their site, with no redistribution grant found | **Not bundled.** Treated as bring-your-own-content (BYOC) via `local_content/` until GovRAMP grants explicit permission (worth emailing info@govramp.org — ask before assuming).                                         |
| **HITRUST CSF**         | Contractually licensed content                                                                                                    | **Never bundled.** BYOC only — you supply your own MyCSF/CSF export under your own license, and it's parsed locally. It is never committed, never uploaded anywhere by this tool, and stays out of git via `.gitignore`. |

### Two repositories, two sets of rights

The table above is about **this** repository. Your own is a different
question, and the answer is usually different too.

A HITRUST CSF export must never be committed here — this repo is public and
Apache-licensed, and may hold only content anyone may redistribute. But your
organization's repository, the private one holding your `docs/` tree, your
`topics.yaml` and your config, very often **may** hold that same export,
because your MyCSF licence permits internal use. Telling you to keep your own
licensed catalog outside your own private repo, when your licence allows it,
is a restriction this project has no standing to impose — and it makes CI
harder for nothing.

So the rule isn't "licensed content never goes in a repository". It's
**"licensed content never goes in a repository that hasn't declared the right
to hold it"** — a permission only you can grant, granted once:

```yaml
# your repo's config/config.yaml
frameworks:
  search_paths:
    - data/frameworks     # bundled: 800-53, HIPAA
    - frameworks          # yours, committed alongside docs/
  allow_licensed_in_repo: true    # our MyCSF licence permits this
```

Each catalog directory carries a `framework.yaml` declaring its terms:

```yaml
id: hitrust-csf
name: HITRUST CSF v11.3
licence: licensed        # or: public-domain
source: MyCSF export, 2026-01
```

`policyforge frameworks` lists what's on disk and where each one stands.
`policyforge check` fails on licensed content committed to a repo that hasn't
declared the right — so **this** repo's CI breaks the moment a HITRUST export
lands in it, while the identical command passes in yours. A directory with no
manifest is treated as licensed: assuming content is freely redistributable
because nobody said otherwise is the mistake with consequences.

**What this does not decide.** Whether a *generated document* citing
`[HITRUST 01.c]` may be redistributed is a question about identifiers,
paraphrase and fair use that depends on your licence and your jurisdiction,
and this tool has no business answering it. What it can do is tell you which
documents drew on licensed catalogs, so the question gets asked about the
right files by someone qualified to answer it.

**Rule of thumb:** if you're not certain a document is a public-domain
government work, it goes in `local_content/` (gitignored), not `data/`.

### Generating a BYOC parser from a sample export

`ingest/byoc_loader.py`'s `load_hitrust_export` / `load_govramp_export` are
stubs — every org's MyCSF/GovRAMP export can differ, so there's no one
column layout to hand-write a parser against ahead of time. Once you have a
real sample export in hand:

```
policyforge generate-parser --framework hitrust --sample path/to/sample-export.csv
```

This sends the sample's **full content** to your configured LLM provider and
asks it to draft a deterministic parser (stdlib/csv/pandas — no LLM calls at
parse time) targeting the `Control`/`ControlEnhancement` schema, then writes
it to `src/policyforge/ingest/hitrust_loader.py` for you to read, test, and
commit like any other source file.

**Before running this against a real export**, confirm your HITRUST/GovRAMP
license actually permits sending its content to a third-party API
processor — the same IP-boundary concern as the "note on using this at
work" section below, just in the other direction. This command exists for
public-repo maintainers building the parsing logic itself (which contains
no licensed content once written); it is not a way around that license
question.

## Handling a framework update

NIST republishes the 800-53 catalog without telling you. The failure is
silent: your documents keep citing AC-2 while AC-2 quietly says something
else, and nobody finds out until somebody reads both.

Slurping up an update is two commands, because `etl-oscal` overwrites the
catalog in place and **git is still holding the version you had** — no
snapshot to remember, no `--old` to pass:

```
policyforge etl-oscal
policyforge drift --controls data/frameworks/nist-800-53-r5/controls.json
```

```
Rev 5 (5.1.1) -> Rev 5 (5.2.0): 1 added, 1 removed, 3 changed.
4 change(s) alter what the organization must do; 1 are editorial.

Worth reading:
  ADDED   AC-99  (added)
          reaches nothing you have written yet
  REMOVED AC-4  (removed)
  CHANGED AC-2  (control_statement, parameters)
          topics: Access Review | docs: standards/access-review.md | parameters: AC-2/frequency
  CHANGED AU-6  (baseline)
          topics: Audit Logging

Editorial only (1): CP-9

Blast radius:
  2 topic(s): Access Review, Audit Logging
  1 document(s): standards/access-review.md
  1 recorded parameter decision(s): AC-2/frequency
```

The question a bump raises isn't *what is different* — a diff answers that
and is unreadable — but **what do I have to go and look at?** So this walks
all the way through to documents rather than stopping at control
identifiers, and separates changes by what they touch:

| Change                              | Treated as  | Why                                              |
| ----------------------------------- | ----------- | ------------------------------------------------ |
| Control statement                   | substantive | It is the requirement                            |
| Baseline moved                      | substantive | Changes what the SSP answers for                 |
| Enhancement added or dropped        | substantive | A new obligation, or one retired                 |
| An ODP appeared or vanished         | substantive | A decision you now owe, or no longer get to make |
| Discussion, title, related controls | editorial   | Noted, kept out of the way                       |

That last row is what keeps the report readable. Reporting a reworded
discussion paragraph as work is how a drift report becomes something people
skim past — so a CP-9 discussion edit does **not** drag the backup Standard
into review.

The parameter line is the one worth pausing on: if AC-2's frequency stopped
being organization-defined, a value you recorded and defended was decided
against wording that no longer exists. That is exactly the thing nobody
notices.

**Both wrong answers are expensive.** Regenerate everything and you discard
every hand edit and every review the documents ever had. Change nothing and
they quietly stop matching the catalog they cite. A blast radius you can
trust is what makes the third option available.

`.github/workflows/framework-drift.yml` runs this monthly with
`--fail-on-change`, so a red build is the notification and the job log is the
triage list. It writes nothing — applying an update is a pull request
somebody opens after reading the report, because deciding what a changed
requirement *means* is the part that needs a person.

## Organization-defined parameters

SP 800-53 doesn't tell you how often to review accounts. It says
`[Assignment: organization-defined frequency]` and leaves the number to you —
**1,210 times** across the bundled catalog, counting statements and
enhancements.

Those decisions get made whether or not anyone decides them. Without a
ledger, a model picks each one inside the prose it's drafting, with no memory
of what it chose for the neighbouring control. The result is documents that
are individually plausible and collectively indefensible: the Access Control
Standard says quarterly, the Audit Standard says "periodically", the SSP says
annually, and an assessor asking *why quarterly?* gets no answer, because
there isn't one.

```
policyforge parameters --controls data/frameworks/nist-800-53-r5/controls.json   --baseline moderate --group
```

```
742 organization-defined parameter(s) in scope: 0 decided, 742 undecided

By the kind of value being decided:
  selection             0/93 decided
  frequency             0/71 decided
  personnel or roles    0/54 decided
  time period           0/29 decided
```

**Scoping is what makes this tractable.** The whole catalog is a thousand
distinct parameters, which is not a to-do list. `--baseline moderate` is 742;
`--topics config/topics.yaml` narrows it to what your own topics anchor. And
they aren't a thousand different questions — "frequency" is asked 71 times —
so `--group` sorts by leverage and lets you decide one kind of value at a
sitting.

`--init` scaffolds `config/parameters.yaml` with every in-scope parameter,
preserving anything already decided:

```yaml
parameters:
  # AC-2: frequency
  #   a. Review accounts [Assignment: organization-defined frequency];
  AC-2/frequency:
    value: 'quarterly'
    rationale: 'HITRUST 01.c specifies quarterly; 800-53 leaves it ODP, so the stricter framework governs.'
    source: 'HITRUST CSF 01.c'
```

`synthesize` substitutes decided values into the control text **before** the
merge, which is the ordering that matters: a requirement that already says
"quarterly" is one the model restates, while one that still says
`[Assignment: organization-defined frequency]` is one it quietly decides,
differently in every document.

Three things the design insists on:

- **An undecided parameter stays undecided.** No value means the marker
  survives into the output, which reads as the gap it is. That is better than
  a number nobody chose.
- **A value without reasoning is reported.** "Why quarterly" is the question
  asked a year later; the ledger flags decisions carrying no `rationale` or
  `source`.
- **A decision is never silently lost.** If a control is reworded and a key
  no longer matches, it's reported as stale and *kept in the file* — a change
  upstream should cost you a question, not a decision you made and defended.

## System Security Plan (SSP)

`policyforge ssp` builds a NIST 800-53 System Security Plan as a spreadsheet
workbook — a different output path from the Policy/Standard/Procedure
documents, aimed at the control-by-control table an assessor reads.

```
policyforge ssp \
  --controls data/frameworks/nist-800-53-r5/controls.json \
  --controls data/frameworks/hipaa-security-rule/controls.json \
  --baseline moderate \
  --system-name "Acme Health Platform"
```

**Format: `.xlsx`, and no Excel licence is needed.** Despite the name, xlsx
is not a Microsoft-proprietary format — it's the open ISO/IEC 29500
(ECMA-376) standard, written here by `openpyxl` in pure Python. LibreOffice
Calc opens and edits it natively. It's used in preference to `.ods` only
because the same file also opens unmodified in Excel and Google Sheets, and
in preference to `.csv` because a csv can't carry dropdowns, frozen headers
or multiple sheets.

Five sheets:

| Sheet                  | What's in it                                                                                                                                                              |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| System Information     | The plan elements NIST SP 800-18 expects — system identification, FIPS 199 categorization, owner, authorizing official, operational status, environment, interconnections |
| Control Implementation | One row per control: NIST's verbatim control text, its enhancements, plus implementation status, control origination, responsible role and implementation narrative       |
| Control Enhancements   | One row per enhancement, since baselines select and assessors evaluate them separately                                                                                    |
| CIS Summary            | The checkbox matrix from FedRAMP's SSP Appendix J "CIS Worksheet", derived by formula from the Control Implementation sheet so the two can't drift apart                  |
| Reference              | The controlled vocabularies backing the dropdowns, their definitions, and the provenance of the control data                                                              |

The Implementation Status and Control Origination vocabularies are
FedRAMP's, read from its published
[SSP Appendix J CIS/CRM Workbook](https://www.fedramp.gov/assets/resources/templates/SSP-Appendix-J-CSO-CIS-and-CRM-Workbook.xlsx),
and enforced by dropdown. `--baseline low|moderate|high` narrows the plan to
one NIST baseline, selecting controls and enhancements independently the way
NIST's own profiles do (AC-2 is in Low; AC-2(1) is not).

Because this is built inside PolicyForge, each control also carries a
`Maps to: HIPAA` column drawn from the crosswalk — so a single workbook shows
which HIPAA requirements each 800-53 control satisfies.

### What the LLM does, and what it deliberately doesn't

Only the **implementation description** is generated. The control
description is copied verbatim from the NIST catalog and is never
paraphrased — it's authoritative wording, and a drifting paraphrase is an
audit finding waiting to happen.

The narrative itself is a *scaffold*, not an assertion. Nothing in this tool
can know what a system actually does, so the prompt requires a
`[Square-Bracket Placeholder]` wherever a detail is unknown rather than a
plausible guess, forbids naming vendors outside your configured vendor list,
and follows the control's own a./b./c. lettering so it can be checked
part-by-part. Every generated cell is prefixed `[DRAFT — REVIEW REQUIRED]`
and the row is flagged "Not reviewed". An SSP that confidently describes
controls a system doesn't have is worse than an empty one: it's a false
attestation.

`--no-narratives` builds the workbook with those cells empty and makes no
LLM calls; otherwise the command tells you how many requests it's about to
make and asks before making them.

## Architecture

```
config/                  Your local config (model, API key env var name, chosen frameworks)
data/frameworks/         Bundled, redistributable framework data (NIST, FedRAMP, ARC-AMPE)
local_content/           Gitignored. Drop your own HITRUST/GovRAMP exports here.
src/policyforge/
  llm/                    Provider abstraction. Ships Anthropic, Amazon Bedrock
                          (`pip install "policyforge[bedrock]"`), and Google Cloud
                          Vertex AI Model Garden (`pip install "policyforge[vertex]"`) —
                          adding another provider means one new class, no changes to
                          calling code.
  ingest/                 Parses framework sources (bundled markdown, BYOC exports) into
                          a common Control/Element schema.
  mapping/                Cross-framework control crosswalk logic.
  synthesis/              Topic-themed merge/dedupe engine (the "30 synthesis docs" pattern).
  generate/               Turns synthesized requirements + org context into draft
                          policies/standards/procedures.
  edit/                   LLM-driven editing of live Confluence pages
                          (`policyforge edit-confluence`, `edit-topic`): plan.py
                          turns an instruction into a reviewable plan, apply.py
                          carries it out and checks nothing else was damaged, and
                          session.py runs the fetch/plan/rewrite sequence over a
                          whole topic's document set. See "Editing a live page".
  content/                The markdown content tree: documents as files, resolved
                          into tier/owner/published-page whether or not they carry
                          frontmatter, plus check.py's offline pull-request gate.
                          Shared, not Zardoz-specific — it's the reading half of a
                          repo-backed document set, and talks to no network.
  zardoz/                 The conversational read side (`policyforge zardoz`):
                          art.py is the floating head and every persona string,
                          shell.py the REPL, corpus.py the local document
                          snapshot over markdown and/or Confluence, retrieve.py
                          the chunking and ranking that finds the passage a
                          question is about, answer.py the grounded answering
                          and the checks that verify its citations, and
                          conversation.py the follow-up resolution that makes it
                          a conversation, paraphrase.py the vocabulary expansion
                          that runs only after a miss, and discover.py the topic
                          proposal for an uncatalogued space. Never imports the
                          publish path.
  ssp/                    Builds a NIST 800-53 System Security Plan as an .xlsx
                          workbook (`policyforge ssp`), with LLM-drafted
                          implementation narratives. See "System Security Plan" below.
  export/                 Markdown / Confluence exporters, the Confluence importer
                          (pulls a page's content back out, converts it to markdown,
                          restoring the links/mentions/images markdownify drops),
                          and confluence_search.py for finding pages by CQL.
  history/                Local, offline version history of generated/imported
                          documents (output/.history/) — see "Confluence import and
                          local version history" above.
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
1. `policyforge llm-check` — confirms your API key and model work.

## Repo hygiene / scanning

Before every commit and on every push, this repo is designed to run:

- **ruff** — lint and format, replacing the flake8/isort/black stack with one tool.
  It's the consistency gate: rule selection, line length (100) and per-file ignores
  live in `[tool.ruff]` in `pyproject.toml`, so the pre-commit hook, CI and
  `scripts/check.py` all enforce byte-identical formatting instead of three
  near-identical configs drifting apart. Beyond style it selects rule families that
  catch real defects — `B` (bugbear), `BLE` (blind excepts must be deliberate),
  `F` (unused imports, undefined names) and `SIM`.
- **gitleaks** — scans staged changes for API keys, tokens, and secrets so you never
  accidentally commit your Anthropic key or an employer-specific config.
- **pip-audit** — checks dependencies for known CVEs.
- **bandit** — static analysis for common Python security issues in this codebase.
- **semgrep** — broader open-source SAST (`p/python`, `p/security-audit`,
  `p/owasp-top-ten` community rulesets), catching patterns bandit's Python-specific
  ruleset doesn't — e.g. it's what caught this repo's GitHub Actions using mutable
  version tags (`@v4`) instead of pinned commit SHAs, a real supply-chain hardening
  gap bandit has no rules for.
- **mdformat** — checks that any markdown this project generates (or that lives in the
  repo itself) is well-formed CommonMark. This is the enforcement mechanism behind
  the "Markdown is the primary deliverable" requirement above, not just a style nit.

Two more run continuously rather than per-commit/per-push:

- **CodeQL** (`.github/workflows/codeql.yml`) — a second SAST engine alongside semgrep,
  using data-flow/taint-tracking analysis rather than pattern matching, so it catches a
  genuinely different class of bug (e.g. untrusted input reaching a dangerous sink
  across multiple function calls). Runs the `security-extended` query suite rather than
  the default — the default is tuned to keep false positives low on very large
  codebases, and this repo is small enough to absorb the extra noise in exchange for
  wider coverage. Runs on push/PR to `main` and weekly on a schedule; results land in
  the repo's Security tab.
- **Dependabot** (`.github/dependabot.yml`) — unlike pip-audit's point-in-time CI check,
  this watches continuously and opens a PR the moment a new CVE is published against a
  Python dependency or a GitHub Action this repo uses, with a 7-day cooldown before
  proposing any newly published version (so a malicious or broken release has time to
  get caught upstream first). It also keeps this repo's SHA-pinned GitHub Actions (see
  ci.yml) current — Dependabot resolves and updates the pinned SHA, not just tag-based
  references. **Enabling Dependabot alerts/security updates is a separate step** — go to
  the repo's Settings → Code security and analysis and turn them on; committing
  `dependabot.yml` alone doesn't enable it.

See `.pre-commit-config.yaml` and `.github/workflows/ci.yml`.

### Running the quality checks yourself

`python scripts/check.py` runs every check in one command — ruff (lint),
ruff (format), pytest, bandit, semgrep, pip-audit, mdformat, plus gitleaks
if you have the binary installed (see the script's docstring for why
gitleaks is optional locally but always runs in CI). Lint and format run
first, since they're the fastest and the most likely to fail on a fresh
edit. Exits non-zero if anything fails, so it's safe to use as a pre-push
gate.

To fix rather than just report, run `ruff check --fix src tests scripts`
and `ruff format src tests scripts` — or install the pre-commit hooks
(`pre-commit install`), which do both automatically on commit.

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
- [x] Confluence importer (`export/confluence_importer.py`) + local version history
  (`history/version_store.py`) — see "Confluence import and local version history" above
- [x] Amazon Bedrock LLM provider (`llm/bedrock_provider.py`) — install with `pip install "policyforge[bedrock]"`
- [x] `ingest/parser_codegen.py` + `policyforge generate-parser` — LLM-assisted codegen
  for a BYOC loader from a real sample export (see "Generating a BYOC parser from a
  sample export" above)
- [ ] `ingest/byoc_loader.py` — HITRUST/GovRAMP export parsing itself still stubbed;
  run `generate-parser` (or hand-write) against a real sample export once you have one
- [ ] GovRAMP: follow up on redistribution permission; if granted, move from BYOC to bundled
- [x] Google Cloud Vertex AI Model Garden LLM provider (`llm/vertex_provider.py`) —
  install with `pip install "policyforge[vertex]"`
- [x] `ingest/hipaa_loader.py` + `policyforge etl-hipaa` — HIPAA Security Rule (45 CFR
  164 Subpart C), bundled and populated, sourced from eCFR's public API
- [x] HIPAA-to-NIST-800-53 crosswalk (`ingest/hipaa_crosswalk_loader.py` +
  `policyforge etl-hipaa-crosswalk`) — sourced from NIST's CPRT catalog, *not* SP
  800-66 Rev. 2's PDF: that document's Appendix D states the mapping table was moved
  out of the PDF and into CPRT. `synthesize` now pulls HIPAA requirements into a topic
  alongside NIST/FedRAMP
- [x] `ingest/oscal_loader.py` + `policyforge etl-oscal` — NIST 800-53 Rev 5 from NIST's
  own OSCAL catalog, so 800-53 data can be populated with no pre-existing Obsidian vault
- [x] `ssp/` + `policyforge ssp` — NIST 800-53 System Security Plan as a LibreOffice-
  compatible .xlsx workbook, with FedRAMP's CIS vocabularies and LLM-drafted
  implementation narratives (see "System Security Plan" above)
- [ ] SSP round-trip: read an edited workbook back in, so implementation status and
  narratives survive a catalog refresh instead of being re-drafted from scratch
- [ ] OSCAL SSP export — NIST's machine-readable SSP model is what FedRAMP is moving
  to; the same data assembled by `ssp/` could emit it
- [ ] Other healthcare-relevant frameworks worth considering: HITRUST CSF (already
  stubbed as BYOC, and now that `generate-parser` exists, buildable against a real
  MyCSF export), MARS-E (CMS, NIST-800-53-based, same public-domain lineage as ARC-AMPE)

### Making "one topic, one team" first-class

The ownership model above is currently a convention you hold in your head:
`synthesize` takes `--topic "Access Review" --nist-controls AC-2,AC-6` and
nothing records which team owns it or what it's for. Turning that into
declared, checkable data is where most of the remaining value is.

- [x] **Topic registry** (`config/topics.yaml` + `topics/registry.py`) — topic name,
  owner, cadence, NIST anchors, evidence artifacts, with a 20-topic starter set in
  `config/topics.example.yaml` that fully covers all three baselines
- [x] **Coverage and ownership analysis** (`policyforge coverage`) — orphaned and
  contested controls, unknown vs out-of-scope anchors, per-team rollup, and
  cross-framework reachability via the crosswalk. `--strict` for CI, `--json` for
  downstream tooling
- [x] **Registry wired into `synthesize`/`generate`** — `synthesize --topic-name` pulls
  anchors and the owning team from the registry and records them as frontmatter on the
  synthesis file; `generate` reads them back, so documents name the real team instead
  of `[Responsible Team]`, and carry the topic cadence and evidence artifacts
- [x] **Confluence editing harness** (`edit/` + `policyforge edit-confluence`) —
  instruction -> plan -> review -> execute against a live page, with dry-run by
  default, version-guarded writes, macro round-trip refusal, and a post-edit check
  for dropped citations or sections (see "Editing a live page")
- [x] **Edit a whole topic's document set** (`policyforge edit-topic`) — resolves a
  topic's pages from the registry's `confluence:` block and applies one instruction
  across them, planning each page at its own tier and leaving untouched any page
  whose plan comes back empty; nothing publishes until the whole set is ready
- [x] **The plan is part of the record** — written to `output/edits/<slug>.plan.json`
  and into version-history metadata, and read back with
  `policyforge history --tier confluence`, so what was flagged and what was declined
  survive the terminal scrolling away
- [x] **Zardoz, the conversational read side** (`zardoz/` + `policyforge zardoz`) —
  a REPL over the policy set, with a local corpus that tags each document
  trusted (owner known) or supporting (unowned). Reads only; the publish path is
  kept out of its import graph and a test asserts it
- [x] **Markdown as a first-class source** (`content/`) — sync a tree of files with
  no network and no credentials, so a repo-backed document set is answerable
  offline. Frontmatter binds a file to the page it publishes to; a file without any
  still resolves from its path and first heading
- [x] **Confluence read fidelity for foreign pages** — cross-page links, user
  mentions and images are attribute-only elements markdownify dropped entirely, so
  an Owner field read as blank. Restored before conversion; unresolvable mentions
  render as a conspicuous `@unresolved-user` and are counted by `sync`
- [x] **Zardoz retrieval** (`zardoz/retrieve.py`) — chunks at headings so a citation
  can name a section, scores with BM25 over terms plus exact matching on control
  identifiers, and refuses rather than returning its least-bad chunk. No embeddings:
  `AC-2` and `AC-3` embed almost identically and mean different things to an
  assessor, so a near-miss is a wrong answer, not a close one
- [x] **Zardoz answering** (`zardoz/answer.py`) — grounded prose with a citation
  on every claim, verified after the fact rather than merely requested: a marker
  pointing at a passage that was never supplied, an answer with no citations at
  all, or a quotation that isn't verbatim in the source are each caught and shown
  above the answer. With no model configured the passages are returned instead,
  which is a supported way to run — retrieval is entirely offline
- [x] **Paraphrase recovery** (`zardoz/paraphrase.py`) — when the question's own
  words find nothing, the model names the vocabulary a document would use and the
  search is retried with it, scored at a discount and reported separately. Chosen
  over embeddings: no dependency, no endpoint the default provider lacks, and an
  expansion you can read
- [x] **`policyforge publish`** — walks the content tree and pushes each document
  to the page its own frontmatter declares, so the file-to-page mapping lives in
  the repo under review rather than in a workflow argument. Plans by default;
  refuses to publish over a page whose macros it cannot round-trip
- [x] **`policyforge pull`** — the way back. Fetches live pages into the tree as
  markdown with the binding written into frontmatter, so a page somebody
  hand-edited becomes a reviewable diff instead of a surprise. Refuses pages that
  would not survive a later publish rather than writing a file that looks correct
  and destroys them
- [x] **`policyforge check`** — the pull-request gate, entirely offline so it runs
  on a fork with no credentials: frontmatter resolves, no two files claim one
  page, no dangling cross-references, no citations dropped since the synthesis
- [x] **Zardoz analyses** (`zardoz/skills.py`) — coverage, drift, parameters,
  history, check, frameworks and roles reachable from the shell, by name or by
  asking. The model routes and the deterministic report is printed verbatim, so a
  number in a Zardoz answer is worth the same as a number from the CLI
- [x] **Zardoz follow-up questions** (`zardoz/conversation.py`) — "what's our
  access review cadence?" then "who owns that?". The question is resolved against
  the exchange *before* retrieval, since keyword scoring has no mechanism for
  "that", and the rewritten question is always shown: a good guess about intent
  is indistinguishable from a bad one once the answer is written
- [x] **`zardoz discover`** — crawls a space and proposes a draft `topics.yaml`
  from title conventions and inline control citations, using the LLM only for the
  pages those conventions did not reach. Ownership stays `[UNASSIGNED]`: nothing
  in a page reliably says which team is accountable, and a wrong owner in a
  compliance artifact gets believed while a blank one gets filled in
- [x] **Role-keyed tools and teams** (`org/`) — `identity_provider: Okta` says what
  Okta is *for*, which is the only fact a substitution needs. 33 tool roles and 14
  team roles (`policyforge roles`), and the fill happens in code after generation
  rather than in the prompt, so the same document and config give the same output
  every time. A flat `vendors:` list still works
- [x] **Licensed catalogs in your own repository** (`frameworks/`) — a HITRUST or
  GovRAMP export may not be committed here, but your own private repo very often
  may hold it under your own licence. Each catalog declares its terms in a
  `framework.yaml`, and `check` fails on licensed content committed to a repository
  that has not declared the right to hold it
- [x] **Parameter ledger** (`parameters/`, `config/parameters.yaml`) — one decided
  value per organization-defined parameter, with the reasoning and source beside it.
  Substituted into control text *before* synthesis, so every document drawn from a
  control agrees and so does the SSP. An undecided parameter stays visibly
  `[Assignment: ...]` rather than becoming a number nobody chose
- [ ] **Conflict log** — where frameworks genuinely disagree, `synthesis/merge.py`
  already keeps both statements rather than silently picking. The next step is to
  surface those as an explicit decision queue rather than leaving them for a reader to
  notice. Password rotation is the standing example: some frameworks still expect
  periodic expiry, NIST SP 800-63B advises against it.
- [ ] **Per-team bundles** — generate one packet per owning team (its procedures, the
  requirements underneath them, the evidence it owes, its review cadence) instead of
  one document per topic. This is the artifact a team lead can actually be handed.
- [ ] **Evidence-artifact modelling** — let a procedure step declare what it produces
  (an export, a dashboard link, a ticket query). Collect once, satisfy many: the
  bridge between a procedure and a HITRUST assessment's evidence demands.
- [ ] **Reverse view for assessors** — given a generated procedure, list every
  framework requirement it satisfies. Inverse of the crosswalk, and the view an
  assessor actually asks for.
- [x] **Framework-version drift** (`frameworks/drift.py` + `policyforge drift`) —
  when a catalog bumps version, reports which controls actually changed and which
  of your topics, documents and recorded parameter decisions each one reaches, so
  review is scoped to what moved rather than restarting the document set. Compares
  against the committed catalog by default, so running the ETL is the whole setup.
