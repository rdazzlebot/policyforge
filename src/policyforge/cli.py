from __future__ import annotations

from pathlib import Path

import click

from policyforge.config import load_config
from policyforge.llm.base import get_provider

# Local, offline version history of generated/imported documents — see
# history/version_store.py's module docstring for what this is (and isn't)
# a substitute for. Shared default across `generate`, `import-confluence`,
# and `history` so a given tier+name lands in the same stream by default.
_DEFAULT_HISTORY_DIR = Path("output/.history")


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
@click.option(
    "--history-dir",
    default=_DEFAULT_HISTORY_DIR,
    type=click.Path(path_type=Path),
    help="Where local version history is recorded (default: output/.history). "
    "See `policyforge history`.",
)
def generate_cmd(
    tier: str,
    synthesis_path: Path,
    standard_path: Path | None,
    out: Path | None,
    history_dir: Path,
):
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

    from policyforge.history.version_store import record_version

    slug = f"{tier}/{out_path.stem}"
    record = record_version(
        history_dir,
        slug,
        document + "\n",
        source="generate",
        metadata={"org": org.name, "model": config.get("llm", {}).get("model"), "synthesis_source": str(synthesis_path)},
    )
    if record is None:
        click.echo(f"No content change since the last recorded version of {slug!r} — history unchanged.")
    else:
        click.echo(
            f"Recorded {slug!r} v{record.version} in {history_dir} "
            f"(+{record.lines_added}/-{record.lines_removed} lines)."
        )


@cli.command("generate-parser")
@click.option(
    "--framework",
    required=True,
    type=click.Choice(["hitrust", "govramp"]),
    help="Which BYOC framework this sample export is for.",
)
@click.option(
    "--sample",
    "sample_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a real sample export from your own license (e.g. a MyCSF CSV/Excel "
    "export). Its full content is sent to your configured LLM provider — confirm "
    "your license terms permit that before running this.",
)
@click.option(
    "--out",
    default=None,
    type=click.Path(path_type=Path),
    help="Where to write the generated parser "
    "(default: src/policyforge/ingest/<framework>_loader.py).",
)
@click.option("--force", is_flag=True, help="Overwrite --out if it already exists.")
@click.option(
    "--yes",
    is_flag=True,
    help="Skip the confirmation prompt before sending --sample's content to the LLM provider.",
)
def generate_parser_cmd(framework: str, sample_path: Path, out: Path | None, force: bool, yes: bool):
    """Generate a deterministic ETL parser for a BYOC framework export via your
    configured LLM, from a real sample export file.

    This is a one-time codegen step: it writes a plain Python module to disk,
    which you should read, test, and commit like any other source file.
    Nothing under ingest/*_loader.py calls the LLM at parse time — only this
    command does, and only when you run it.
    """
    import ast

    from policyforge.ingest.parser_codegen import generate_byoc_parser

    out_path = out or Path(f"src/policyforge/ingest/{framework}_loader.py")
    if out_path.exists() and not force:
        raise click.UsageError(f"{out_path} already exists. Pass --force to overwrite.")

    click.echo(
        f"This sends the full contents of {sample_path} to your configured LLM "
        "provider's API. Confirm your license for this export actually permits "
        "sending it to a third-party API processor before continuing."
    )
    if not yes:
        click.confirm("Continue?", abort=True)

    sample_text = sample_path.read_text(encoding="utf-8", errors="replace")
    config = load_config()
    provider = get_provider(config)

    source = generate_byoc_parser(
        framework=framework,
        framework_slug=framework,
        sample_text=sample_text,
        provider=provider,
    )

    try:
        ast.parse(source)
    except SyntaxError as exc:
        click.echo(f"Generated code failed to parse as valid Python: {exc}")
        raise SystemExit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(source, encoding="utf-8")
    click.echo(
        f"Wrote generated parser -> {out_path}\n"
        "Review it, run it against your sample, add it to your test suite, and "
        "commit like any other source file before relying on it."
    )


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


@cli.command("import-confluence")
@click.option(
    "--tier",
    type=click.Choice(["standard", "policy", "procedure"]),
    required=True,
    help="Which document tier this Confluence page corresponds to — determines which "
    "local version-history stream the import is recorded into.",
)
@click.option(
    "--name",
    required=True,
    help="Document slug/filename stem, matching what `policyforge generate` used, "
    "e.g. 'authenticator-mgmt'. Determines the version-history stream and the "
    "default --out path.",
)
@click.option("--space", required=True, help="Confluence space key to read from.")
@click.option("--title", required=True, help="Page title to look up.")
@click.option(
    "--host",
    required=True,
    help="Confluence base URL, e.g. https://yourorg.atlassian.net/wiki.",
)
@click.option(
    "--out",
    default=None,
    type=click.Path(path_type=Path),
    help="Where to write the imported markdown "
    "(default: output/<tier>s/<name>.imported.md — deliberately not the same "
    "filename `generate` writes, so an import never silently overwrites a fresh draft).",
)
@click.option(
    "--history-dir",
    default=_DEFAULT_HISTORY_DIR,
    type=click.Path(path_type=Path),
    help="Where local version history is recorded (default: output/.history).",
)
def import_confluence_cmd(
    tier: str, name: str, space: str, title: str, host: str, out: Path | None, history_dir: Path
):
    """Pull a page's current content back out of Confluence, converting it to
    markdown, and record it into the same local version-history stream
    `generate` uses for --tier/--name — so you can diff what this tool last
    generated against what's actually live (e.g. after a manual edit)."""
    from policyforge.export.confluence_importer import import_from_confluence
    from policyforge.history.version_store import load_history, record_version

    markdown_text = import_from_confluence(space=space, title=title, host=host)

    out_path = out or Path(f"output/{tier}s") / f"{name}.imported.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown_text, encoding="utf-8")
    click.echo(f"Imported {title!r} from Confluence -> {out_path}")

    slug = f"{tier}/{name}"
    previous = load_history(history_dir, slug)
    record = record_version(
        history_dir, slug, markdown_text, source="confluence-import", metadata={"space": space, "title": title}
    )

    if record is None:
        latest = previous[-1].version if previous else None
        click.echo(
            f"Matches the last recorded version of {slug!r} (v{latest}) — no drift detected."
        )
    elif previous:
        click.echo(
            f"Differs from the last recorded version (v{previous[-1].version}) — recorded as "
            f"{slug!r} v{record.version}. Run `policyforge history --tier {tier} --name {name} "
            f"--diff {previous[-1].version}:{record.version}` to see what changed."
        )
    else:
        click.echo(f"Recorded as {slug!r} v{record.version} (first version in this stream).")


@cli.command("history")
@click.option(
    "--tier",
    type=click.Choice(["standard", "policy", "procedure"]),
    required=True,
)
@click.option(
    "--name",
    required=True,
    help="Document slug/filename stem — the stem of the file `policyforge generate` "
    "wrote via --out (e.g. 'authenticator-mgmt' for authenticator-mgmt.md), or the "
    "--name given to `import-confluence`.",
)
@click.option(
    "--history-dir",
    default=_DEFAULT_HISTORY_DIR,
    type=click.Path(path_type=Path),
    help="Where local version history is recorded (default: output/.history).",
)
@click.option(
    "--diff",
    "diff_range",
    default=None,
    help="Show a unified diff between two versions instead of listing them: 'N:M' for "
    "specific version numbers (e.g. '2:3'), or 'latest' for the two most recent versions.",
)
def history_cmd(tier: str, name: str, history_dir: Path, diff_range: str | None):
    """List (or diff) the locally recorded version history for one document."""
    from policyforge.history.version_store import diff_versions, load_history

    slug = f"{tier}/{name}"
    records = load_history(history_dir, slug)
    if not records:
        click.echo(f"No recorded history for {slug!r} in {history_dir}.")
        return

    if diff_range is not None:
        if diff_range == "latest":
            if len(records) < 2:
                raise click.UsageError(f"{slug!r} only has one recorded version — nothing to diff.")
            v1, v2 = records[-2].version, records[-1].version
        else:
            try:
                v1_str, v2_str = diff_range.split(":", 1)
                v1, v2 = int(v1_str), int(v2_str)
            except ValueError as exc:
                raise click.UsageError(f"--diff must be 'N:M' or 'latest', got {diff_range!r}.") from exc
        click.echo(diff_versions(history_dir, slug, v1, v2))
        return

    for record in records:
        click.echo(
            f"v{record.version}  {record.timestamp}  {record.source:<17} "
            f"+{record.lines_added}/-{record.lines_removed}  {record.content_hash}"
        )


if __name__ == "__main__":
    cli()
