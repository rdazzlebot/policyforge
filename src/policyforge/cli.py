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
@click.option(
    "--controls",
    "controls_path",
    default=Path("data/frameworks/nist-800-53-r5/controls.json"),
    type=click.Path(exists=True, path_type=Path),
    help="Path to a controls.json produced by `etl-vault` (or another loader).",
)
@click.option(
    "--out",
    default=Path("data/frameworks/crosswalk.json"),
    type=click.Path(path_type=Path),
    help="Where to write the built crosswalk.",
)
def map_cmd(controls_path: Path, out: Path):
    """Build the NIST-anchored cross-framework crosswalk."""
    import json

    from policyforge.ingest.schema import load_controls
    from policyforge.mapping.crosswalk import build_crosswalk

    controls = load_controls(controls_path)
    crosswalk = build_crosswalk(controls)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(crosswalk, indent=2), encoding="utf-8")
    click.echo(f"Built crosswalk for {len(crosswalk)} NIST controls -> {out}")


@cli.command("synthesize")
@click.option("--topic", required=True, help="Topic name, e.g. 'Password & Credential Management'.")
@click.option(
    "--nist-controls",
    required=True,
    help="Comma-separated NIST control IDs anchoring this topic, e.g. IA-5,IA-5(1).",
)
@click.option(
    "--controls",
    "controls_paths",
    required=True,
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a controls.json (one per loaded framework). Repeatable.",
)
@click.option(
    "--crosswalk",
    "crosswalk_path",
    default=Path("data/frameworks/crosswalk.json"),
    type=click.Path(exists=True, path_type=Path),
    help="Path to the crosswalk.json produced by `policyforge map`.",
)
@click.option(
    "--out-dir",
    default=Path("output/synthesis"),
    type=click.Path(path_type=Path),
    help="Directory to write the synthesized topic markdown into.",
)
def synthesize_cmd(topic: str, nist_controls: str, controls_paths, crosswalk_path: Path, out_dir: Path):
    """Merge/dedupe controls for one topic into synthesized requirement prose."""
    import json
    import re

    from policyforge.ingest.schema import load_controls
    from policyforge.synthesis.merge import build_synthesis_topic, synthesize_topic

    controls = []
    for path in controls_paths:
        controls.extend(load_controls(path))

    crosswalk = json.loads(crosswalk_path.read_text(encoding="utf-8"))
    nist_ids = [c.strip() for c in nist_controls.split(",") if c.strip()]

    synthesis_topic = build_synthesis_topic(topic, nist_ids, controls, crosswalk)
    if not synthesis_topic.controls:
        click.echo(f"No controls found for topic {topic!r} — check --nist-controls and --controls.")
        raise SystemExit(1)

    config = load_config()
    provider = get_provider(config)
    result = synthesize_topic(synthesis_topic, provider)

    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.md"
    out_path.write_text(result + "\n", encoding="utf-8")
    click.echo(
        f"Synthesized {len(synthesis_topic.controls)} controls for {topic!r} -> {out_path}"
    )


@cli.command("generate")
@click.option(
    "--tier",
    type=click.Choice(["standard", "policy", "procedure"]),
    default="standard",
    help="Document tier to draft. 'policy' and 'procedure' require --standard, so they "
    "can reference the Standard document by name.",
)
@click.option(
    "--synthesis",
    "synthesis_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a synthesized topic markdown file produced by `policyforge synthesize`.",
)
@click.option(
    "--standard",
    "standard_path",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Path to the already-generated Standard document this Policy or Procedure "
    "implements. Required when --tier policy or --tier procedure.",
)
@click.option(
    "--out",
    default=None,
    type=click.Path(path_type=Path),
    help="Where to write the drafted document "
    "(default: output/<tier>s/<synthesis-filename>).",
)
def generate_cmd(tier: str, synthesis_path: Path, standard_path: Path | None, out: Path | None):
    """Draft a Standard, Policy, or Procedure document from a synthesized topic."""
    from policyforge.export.markdown_exporter import check_markdown_quality, write_markdown
    from policyforge.generate.policy_writer import (
        OrgContext,
        extract_title,
        generate_policy,
        generate_procedure,
        generate_standard,
    )

    config = load_config()
    org_cfg = config.get("org", {})
    org = OrgContext(
        name=org_cfg.get("name", ""),
        industry=org_cfg.get("industry", ""),
        vendors=org_cfg.get("vendors", []),
    )

    topic_synthesis = synthesis_path.read_text(encoding="utf-8")
    provider = get_provider(config)

    if tier in ("policy", "procedure"):
        if standard_path is None:
            raise click.UsageError(
                f"--standard is required when --tier {tier}, so the {tier.capitalize()} "
                "can reference its Standard document by name."
            )
        standard_title = extract_title(standard_path.read_text(encoding="utf-8"))
        if tier == "policy":
            document = generate_policy(
                topic_synthesis, org, provider, standard_title=standard_title
            )
        else:
            document = generate_procedure(
                topic_synthesis, org, provider, standard_title=standard_title
            )
    else:
        document = generate_standard(topic_synthesis, org, provider)

    out_path = out or Path(f"output/{tier}s") / synthesis_path.name
    written = write_markdown(document + "\n", output_dir=out_path.parent, filename=out_path.name)
    if not check_markdown_quality(written):
        click.echo(f"WARNING: {written} did not pass the mdformat quality check — review before shipping.")
    click.echo(f"Drafted {tier} -> {written}")


@cli.command("export-confluence")
@click.option(
    "--doc",
    "doc_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a generated markdown document (from `policyforge generate`).",
)
@click.option("--space", required=True, help="Confluence space key to publish into.")
@click.option("--title", required=True, help="Page title.")
@click.option(
    "--host",
    required=True,
    help="Confluence base URL, e.g. https://yourorg.atlassian.net/wiki.",
)
@click.option("--parent-id", default=None, help="Parent page ID, if nesting under an existing page.")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the converted Confluence storage format instead of publishing.",
)
def export_confluence_cmd(
    doc_path: Path, space: str, title: str, host: str, parent_id: str | None, dry_run: bool
):
    """Convert a generated markdown document to Confluence storage format and publish it."""
    from policyforge.export.confluence_exporter import export_to_confluence, markdown_to_confluence

    markdown_text = doc_path.read_text(encoding="utf-8")

    if dry_run:
        click.echo(markdown_to_confluence(markdown_text))
        return

    url = export_to_confluence(
        markdown_text, space=space, title=title, host=host, parent_id=parent_id
    )
    click.echo(f"Published to Confluence -> {url}")


if __name__ == "__main__":
    cli()
