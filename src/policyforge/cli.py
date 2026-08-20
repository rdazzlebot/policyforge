from __future__ import annotations

from pathlib import Path

import click

from policyforge.config import load_config
from policyforge.llm.base import get_provider


@click.group()
def cli():
    """PolicyForge — cross-mapped compliance policy/procedure generation."""


@cli.command("llm-check")
def llm_check():
    """Confirm your configured API key + model actually work."""
    config = load_config()
    provider = get_provider(config)
    ok = provider.check()
    if ok:
        click.echo(f"OK — {config['llm']['provider']} / {config['llm']['model']} responded.")
    else:
        click.echo("Provider responded, but the sanity check didn't match expected output.")
        raise SystemExit(1)


@cli.command("etl-vault")
@click.option(
    "--controls-dir",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to an Obsidian vault's Frameworks/NIST-800-53/Controls/ directory.",
)
@click.option(
    "--out",
    default=Path("data/frameworks/nist-800-53-r5/controls.json"),
    type=click.Path(path_type=Path),
    help="Where to write the parsed, public-domain-only control data.",
)
def etl_vault(controls_dir: Path, out: Path):
    """Parse NIST 800-53 control notes from an existing vault into this
    project's data schema. Public-domain content only — see
    ingest/nist_vault_loader.py for what crosswalk columns are stripped
    by default and why.
    """
    import dataclasses
    import json

    from policyforge.ingest.nist_vault_loader import load_vault_controls

    controls = load_vault_controls(controls_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps([dataclasses.asdict(c) for c in controls], indent=2),
        encoding="utf-8",
    )
    click.echo(f"Parsed {len(controls)} controls -> {out}")


@cli.command("map")
def map_cmd():
    """Build the cross-framework crosswalk. (Not yet implemented.)"""
    click.echo("mapping/crosswalk.py is a stub — see its module docstring for the plan.")
    raise SystemExit(1)


@cli.command("synthesize")
def synthesize_cmd():
    """Run the topic merge/dedupe engine. (Not yet implemented.)"""
    click.echo("synthesis/merge.py is a stub — see its module docstring for the plan.")
    raise SystemExit(1)


@cli.command("generate")
def generate_cmd():
    """Draft a policy/standard/procedure from synthesized topics. (Not yet implemented.)"""
    click.echo("generate/policy_writer.py is a stub — see its module docstring for the plan.")
    raise SystemExit(1)


if __name__ == "__main__":
    cli()
