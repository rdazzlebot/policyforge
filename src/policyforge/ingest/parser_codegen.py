"""LLM-assisted codegen for BYOC (licensed) framework loaders.

HITRUST/GovRAMP exports don't have a stable, publicly documented column
layout this project can hand-write a parser against ahead of time — every
org's MyCSF/GovRAMP export can differ. Instead of leaving `byoc_loader.py`'s
stubs unimplemented indefinitely, `generate_byoc_parser` sends a sample
export to your configured LLM provider and asks it to write a
*deterministic* Python parser targeting this project's Control/
ControlEnhancement schema (see `schema.py`).

This is a one-time, human-in-the-loop codegen step, not a runtime
dependency: `cli.py`'s `generate-parser` command writes the result to disk
once, then you review, test, and commit it like any other source file.
Nothing under `ingest/*_loader.py` calls an LLM at parse time — only this
module does, and only when you explicitly run that command.

WARNING: this sends the *entire content* of the sample export you point it
at to your configured LLM provider's API. If that sample is licensed/
contractual content (a real MyCSF or GovRAMP export), confirm your license
terms actually permit sending it to a third-party API processor before
running this — see this project's README "A note on using this at work"
section for the same concern in reverse (employer content vs. this repo).
"""

from __future__ import annotations

import re

from policyforge.llm.base import LLMProvider

# Kept in sync with schema.py by hand (not imported) so the prompt shows the
# model plain source rather than a runtime-introspected dump.
_SCHEMA_SOURCE = """\
@dataclass
class ControlEnhancement:
    enhancement_id: str
    title: str
    baseline: str
    description: str


@dataclass
class Control:
    control_id: str
    title: str
    framework: str          # e.g. "HITRUST CSF", "GovRAMP"
    framework_version: str  # e.g. "v11.8"
    family: str | None = None
    family_abbr: str | None = None
    baseline: str | None = None
    control_statement: str = ""
    discussion: str = ""
    enhancements: list[ControlEnhancement] = field(default_factory=list)
    related_controls: list[str] = field(default_factory=list)
    source_crosswalk: dict[str, str] = field(default_factory=dict)
    source_path: str | None = None
"""

_SYSTEM_PROMPT = """You are a Python codegen engine that writes ONE ETL \
loader function for a compliance-framework export, targeting an existing \
dataclass schema in a larger project.

Rules:
- Output ONLY a single, complete, well-formed Python module — no markdown
  code fences, no prose before or after the code.
- The module must define exactly one function,
  `load_<framework_slug>_export(export_path: Path) -> list[Control]`
  (substitute the literal framework slug given below), that parses the
  export format shown in the sample and returns a list of `Control`
  objects matching the schema given below exactly (field names, types,
  defaults) — do not invent new fields.
- Parsing must be fully deterministic: use only the standard library plus
  packages already common for this kind of ETL (csv, json, openpyxl,
  pandas, re) — never call an LLM, network, or any nondeterministic API
  from inside the generated function.
- Start with `from __future__ import annotations`, then only the imports
  the function actually uses, then `from .schema import Control,
  ControlEnhancement` (relative import — this module lives inside the same
  `ingest/` package as schema.py).
- Set `control.framework` and `control.framework_version` to sensible
  literal values for this framework (given below) rather than reading them
  from the export, unless the export itself contains that information.
- Always set `control.source_path = str(export_path)` on every Control you
  return.
- If a field isn't present in the sample, leave it at its dataclass
  default rather than inventing a value.
- Write one short module docstring (2-3 sentences) describing the export
  format this loader was derived from, so a future maintainer knows why
  the parsing logic looks the way it does. No other comments unless a
  parsing decision is genuinely non-obvious.
"""


def _strip_code_fence(text: str) -> str:
    """Defensively strip a ```python ... ``` fence if the model wrapped its
    output in one despite being told not to."""
    match = re.match(r"^```(?:python)?\s*\n(.*?)\n```\s*$", text, re.DOTALL)
    return match.group(1) if match else text


def generate_byoc_parser(
    *, framework: str, framework_slug: str, sample_text: str, provider: LLMProvider
) -> str:
    """Ask `provider` to write a deterministic parser for `sample_text`
    (the full content of a BYOC sample export) targeting this project's
    Control schema. Returns raw Python source — the caller is responsible
    for validating it (e.g. `ast.parse`) and writing it to disk."""
    if not sample_text.strip():
        raise ValueError("sample_text is empty — nothing to derive a parser from.")

    prompt = (
        f"Framework: {framework}\n"
        f"Framework slug (for the function name): {framework_slug}\n\n"
        f"Target Control/ControlEnhancement schema (from ingest/schema.py):\n\n"
        f"{_SCHEMA_SOURCE}\n\n"
        f"Sample export content (full file):\n\n{sample_text}\n\n"
        "Write the loader module per the rules above."
    )
    response = provider.generate(
        system=_SYSTEM_PROMPT, prompt=prompt, temperature=0, max_tokens=8192
    )
    return _strip_code_fence(response.text.strip()) + "\n"
