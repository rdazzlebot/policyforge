"""Turns a synthesized topic (see synthesis/merge.py) plus org context
(industry, vendor stack, existing docs) into a drafted document at one of
three tiers, matching this project's document hierarchy:

    Policy > Standard > Procedure

- **Standard** (`generate_standard`) is the detailed, technical tier:
  every synthesized requirement, source-tagged back to the frameworks it
  came from, vendor-specific where the org context allows it. Audience:
  security/IT staff who implement and audit against it.
- **Policy** (`generate_policy`) is the brief, principle-level tier read by
  the whole organization, not just practitioners. It compresses the same
  synthesized requirements into a small number of plain-language
  commitments, drops framework/control citations entirely (that
  traceability lives in the Standard), and points to the Standard by name
  for anyone who needs the specifics.
- **Procedure** (`generate_procedure`) is one level *more* granular than the
  Standard tier: it turns each requirement into the literal ordered steps a
  practitioner performs to satisfy it, still source-tagged for traceability.
  Audience: the same security/IT staff as the Standard, but read while
  actually doing the task rather than while auditing against it.

Output contract: every generator here must return portable, well-formed
CommonMark markdown — no Obsidian wikilinks, no vault-relative-only paths.
This is the *canonical* output; export/confluence_exporter.py converts this
same markdown to Confluence storage format rather than generating
Confluence content independently. See README's "Output format priority"
section — getting this contract right is what keeps both output formats
correct.

Documents get `[Square-Bracket Placeholder]` placeholders wherever a detail
isn't available from the organization context below (a vendor, an owning
team, an exceptions contact) rather than inventing a specific name.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from policyforge.llm.base import LLMProvider


@dataclass
class OrgContext:
    name: str
    industry: str
    vendors: list[str] = field(default_factory=list)


_STANDARD_SYSTEM_PROMPT = """You are a compliance policy drafting engine. \
Turn a set of already-synthesized, source-tagged requirement statements \
into a formal information security STANDARD document for one \
organization.

Rules:
- Output portable, well-formed CommonMark markdown only: a single '#'
  document title, '##' sections, no Obsidian-style [[wikilinks]], no
  vault-relative-only paths, properly closed code fences, well-formed
  tables. This markdown must render correctly unmodified on GitHub, in a
  plain text editor, or pasted into Confluence.
- Every requirement in the input must be reflected in the output — do not
  drop or water down a requirement, and do not add requirements that
  weren't in the input.
- Preserve each requirement's inline source tag (e.g. `[NIST IA-5 |
  GovRAMP IA-5]`) so the document stays traceable back to the frameworks it
  was drawn from.
- Where a requirement is vendor/tool-specific: if the organization's vendor
  list below names a plausible match, use that vendor's actual name. If not,
  write a placeholder in the square-bracket form `[Square-Bracket Vendor]`
  (e.g. `[Endpoint Protection Vendor]`) rather than naming a real product.
- Write in formal policy language ("must", "shall"), addressed to the
  security/IT staff who implement and audit against this document, not to
  a generic reader.
"""

_POLICY_SYSTEM_PROMPT = """You are a compliance policy drafting engine. \
Turn a set of already-synthesized, source-tagged requirement statements \
into a short, plain-language information security POLICY document for one \
organization. Unlike the Standard document these requirements also feed,
a Policy is read by the entire organization — most readers have no
compliance background and will never see a framework control ID.

Rules:
- Output portable, well-formed CommonMark markdown only: a single '#'
  document title, followed by these '##' sections in this exact order:
  Purpose, Scope, Policy Statements, Roles & Responsibilities, Exceptions,
  Related Standards, Enforcement. No Obsidian-style [[wikilinks]], no
  vault-relative-only paths.
- Purpose: 1-2 sentences, plain language, on why this policy exists.
- Scope: 1-2 sentences naming who/what it applies to.
- Policy Statements: this is the section you must compress the hardest.
  Merge the source requirements into a SHORT list of high-level,
  plain-language commitments — far fewer bullets than the number of source
  requirements you were given. Each bullet is one organizational
  commitment a non-technical employee could read once and remember, not a
  restatement of one technical control. Never cite a framework or control
  ID here. Do not shorten each source requirement 1:1 into its own bullet
  — genuinely merge related requirements together. If you find yourself
  writing more than a handful of bullets, you haven't compressed enough;
  go back and merge further.
- Roles & Responsibilities: 1-2 sentences on who owns and enforces this
  policy.
- Exceptions: 1-2 sentences on how someone requests an exception.
- Related Standards: name the Standard document given below by its title —
  this is where a reader goes for the technical specifics, and it's the
  only place framework/control traceability needs to live from here on.
- Enforcement: one sentence on the consequence of a violation.
- Never invent a specific fact (a named team, a named contact, a specific
  consequence) that isn't given to you below or in the source requirements.
  Where a detail is missing, use a square-bracket placeholder in the same
  style as vendor placeholders, e.g. `[Security Team]` or
  `[Policy Owner Title]`, rather than making one up.
"""


_PROCEDURE_SYSTEM_PROMPT = """You are a compliance policy drafting engine. \
Turn a set of already-synthesized, source-tagged requirement statements \
into a formal information security PROCEDURE document for one \
organization — the step-by-step operational instructions for executing an \
existing Standard's requirements. This is one level MORE granular than the \
Standard, not a summary of it.

Rules:
- Output portable, well-formed CommonMark markdown only: a single '#'
  document title, followed by these '##' sections in this exact order:
  Purpose, Scope, Prerequisites, Procedure Steps, Roles & Responsibilities,
  Related Standard. No Obsidian-style [[wikilinks]], no vault-relative-only
  paths, properly closed code fences, well-formed tables.
- Purpose: 1-2 sentences on what executing this procedure accomplishes.
- Scope: 1-2 sentences naming who performs it and on what systems.
- Prerequisites: access, tools, or approvals needed before starting, as a
  bullet list. Use a square-bracket placeholder (e.g. `[Access Request
  System]`) for anything not given below rather than inventing one.
- Procedure Steps: one '###' subsection per input requirement (or tightly
  related group of requirements), each containing a numbered list of
  concrete, ordered actions — who does what, in what order, using which
  tool/system — that satisfy that requirement. Every requirement in the
  input must be reflected here; do not drop, water down, or merge unrelated
  requirements together the way the Policy tier does. Preserve each
  requirement's inline source tag (e.g. `[NIST IA-5 | GovRAMP IA-5]`) at the
  end of its subsection heading or its first step, so the document stays
  traceable back to the frameworks it was drawn from.
- Where a step is vendor/tool-specific: if the organization's vendor list
  below names a plausible match, use that vendor's actual name and its real
  UI/CLI actions where you can reasonably infer them. If not, write a
  placeholder in the square-bracket form `[Square-Bracket Vendor]` rather
  than naming a real product or inventing specific UI steps for it.
- Roles & Responsibilities: 1-2 sentences on who is authorized to perform
  these steps and who reviews/approves exceptions.
- Related Standard: name the Standard document given below by its title —
  that document is where the *why* and the full requirement text live.
- Write in direct, imperative operational language ("Open the console and
  verify...", "Set the value to..."), addressed to the practitioner
  executing the procedure, not to an auditor.
"""


def _render_org(org: OrgContext) -> str:
    lines = [f"Organization: {org.name}", f"Industry: {org.industry}"]
    if org.vendors:
        lines.append(f"Known vendors/tools: {', '.join(org.vendors)}")
    else:
        lines.append(
            "Known vendors/tools: none supplied — use [Square-Bracket Vendor] "
            "placeholders throughout."
        )
    return "\n".join(lines)


def extract_title(markdown_text: str) -> str:
    """Pull the document title out of a generated document's leading '# '
    heading — used to have a Policy reference its Standard by name without
    requiring the caller to retype it."""
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    raise ValueError("No '# ' title heading found in markdown_text.")


def generate_standard(topic_synthesis: str, org: OrgContext, provider: LLMProvider) -> str:
    if not topic_synthesis.strip():
        raise ValueError("topic_synthesis is empty — nothing to draft a document from.")

    prompt = (
        f"{_render_org(org)}\n\n"
        f"Synthesized requirements:\n\n{topic_synthesis}\n\n"
        "Draft the Standard document per the rules above."
    )
    response = provider.generate(
        system=_STANDARD_SYSTEM_PROMPT, prompt=prompt, temperature=0.2, max_tokens=8192
    )
    return response.text.strip()


def generate_policy(
    topic_synthesis: str, org: OrgContext, provider: LLMProvider, *, standard_title: str
) -> str:
    if not topic_synthesis.strip():
        raise ValueError("topic_synthesis is empty — nothing to draft a document from.")
    if not standard_title.strip():
        raise ValueError(
            "standard_title is required so the Policy's Related Standards "
            "section can name what it points to."
        )

    prompt = (
        f"{_render_org(org)}\n\n"
        f"This policy's implementing Standard document is titled: "
        f"{standard_title!r}\n\n"
        "Synthesized requirements (the Standard above is built from these "
        "in full detail; you must compress them, not enumerate them):\n\n"
        f"{topic_synthesis}\n\n"
        "Draft the Policy document per the rules above."
    )
    response = provider.generate(
        system=_POLICY_SYSTEM_PROMPT, prompt=prompt, temperature=0.2, max_tokens=4096
    )
    return response.text.strip()


def generate_procedure(
    topic_synthesis: str, org: OrgContext, provider: LLMProvider, *, standard_title: str
) -> str:
    if not topic_synthesis.strip():
        raise ValueError("topic_synthesis is empty — nothing to draft a document from.")
    if not standard_title.strip():
        raise ValueError(
            "standard_title is required so the Procedure's Related Standard "
            "section can name what it operationalizes."
        )

    prompt = (
        f"{_render_org(org)}\n\n"
        f"This procedure operationalizes the Standard document titled: "
        f"{standard_title!r}\n\n"
        "Synthesized requirements (turn each into ordered, concrete steps "
        "per the rules above):\n\n"
        f"{topic_synthesis}\n\n"
        "Draft the Procedure document per the rules above."
    )
    response = provider.generate(
        system=_PROCEDURE_SYSTEM_PROMPT, prompt=prompt, temperature=0.2, max_tokens=8192
    )
    return response.text.strip()
