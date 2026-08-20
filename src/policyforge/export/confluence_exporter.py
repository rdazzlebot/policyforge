"""Confluence export — a secondary, additional feature layered on top of
the canonical markdown output, not an independent generation path.

This module takes the *already-generated, already-quality-checked* markdown
from generate/policy_writer.py and converts it to Confluence storage
format, then optionally uploads via the Confluence REST API. It does not
call the LLM and does not regenerate content — that guarantees the
markdown and Confluence versions of a document can't drift from each other
in substance, only in formatting.

TODO (next build phase):
  - Markdown -> Confluence storage format conversion. Worth evaluating the
    `md2cf` package (handles exactly this conversion + upload) before
    hand-rolling one — check it handles this project's table/heading/code
    fence usage before adopting it.
  - Adapt the source vault's Confluence-Workflow approach for space/page
    hierarchy conventions.
  - Read Confluence API credentials from environment variables only,
    matching the pattern in llm/anthropic_provider.py — never from a
    committed config file.
"""

from __future__ import annotations


def markdown_to_confluence(markdown_text: str) -> str:
    """Convert already-generated canonical markdown to Confluence storage
    format (XHTML-based). Does not touch the LLM or regenerate content."""
    raise NotImplementedError("Next build phase — see module docstring.")


def export_to_confluence(*args, **kwargs):
    raise NotImplementedError("Next build phase — see module docstring.")
