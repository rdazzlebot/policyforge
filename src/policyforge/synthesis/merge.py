"""Topic-themed merge/dedupe engine.

TODO (next build phase): reproduce the pattern already proven out manually
in the source Obsidian vault's Synthesis/ folder — for a given real-world
topic (e.g. "Password & Credential Management"), pull every control/element
that maps to it across the enabled frameworks, dedupe overlapping
requirements, and produce a single prose statement per requirement with
inline source tags, e.g.:

    "Passwords must be a minimum of 14 characters for privileged accounts.
    [NIST IA-5 | GovRAMP Moderate]"

This is the highest-value, most novel piece of the pipeline — it's what
turns a pile of controls into something a policy can actually be written
from. Uses an LLMProvider (see llm/base.py) for the actual merge/rewrite
step, with the source elements passed in as grounding context (not relying
on the model's own knowledge of framework text).
"""

from __future__ import annotations

from dataclasses import dataclass

from policyforge.ingest.schema import Control
from policyforge.llm.base import LLMProvider


@dataclass
class SynthesisTopic:
    name: str
    controls: list[Control]


def synthesize_topic(topic: SynthesisTopic, provider: LLMProvider) -> str:
    raise NotImplementedError("Next build phase — see module docstring.")
