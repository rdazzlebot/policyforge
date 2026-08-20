"""Turns a synthesized topic (see synthesis/merge.py) plus org context
(industry, vendor stack, existing docs) into a drafted policy, standard, or
procedure document.

Output contract: this function must return portable, well-formed CommonMark
markdown — no Obsidian wikilinks, no vault-relative-only paths. This is the
*canonical* output; export/confluence_exporter.py converts this same
markdown to Confluence storage format rather than generating Confluence
content independently. See README's "Output format priority" section —
getting this contract right is what keeps both output formats correct.

TODO (next build phase): mirror the source vault's Procedures workflow —
generate documents with `[Square-Bracket Vendor]` placeholders where the
requirement is vendor/tool-specific, filled in from org.vendors in
config.yaml where a match exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from policyforge.llm.base import LLMProvider


@dataclass
class OrgContext:
    name: str
    industry: str
    vendors: list[str]


def generate_procedure(topic_synthesis: str, org: OrgContext, provider: LLMProvider) -> str:
    raise NotImplementedError("Next build phase — see module docstring.")
