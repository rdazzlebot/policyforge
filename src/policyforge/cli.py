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


@cli.command("etl-oscal")
@click.option(
    "--out",
    default=Path("data/frameworks/nist-800-53-r5/controls.json"),
    type=click.Path(path_type=Path),
    help="Where to write the parsed control data.",
)
@click.option(
    "--no-baselines",
    is_flag=True,
    help="Skip fetching the Low/Moderate/High profiles (controls load without "
    "baseline tagging, which `ssp --baseline` needs).",
)
def etl_oscal(out: Path, no_baselines: bool):
    """Fetch NIST's official OSCAL edition of SP 800-53 Rev 5 (plus the
    Low/Moderate/High baseline profiles) and parse it into this project's
    data schema.

    Public domain — a US government work, same basis as the eCFR and CPRT
    sources. Unlike `etl-vault`, this needs no pre-existing vault, so it's
    the way to populate 800-53 data from scratch. See ingest/oscal_loader.py.
    """
    import dataclasses
    import json

    from policyforge.ingest.oscal_loader import (
        fetch_oscal_baselines,
        fetch_oscal_catalog,
        parse_oscal_catalog,
    )

    catalog = fetch_oscal_catalog()
    baselines = {} if no_baselines else fetch_oscal_baselines()
    controls, withdrawn = parse_oscal_catalog(catalog, baselines)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps([dataclasses.asdict(c) for c in controls], indent=2),
        encoding="utf-8",
    )
    enhancements = sum(len(c.enhancements) for c in controls)
    click.echo(
        f"Parsed {len(controls)} controls and {enhancements} enhancements "
        f"({catalog['catalog']['metadata']['version']}) -> {out}"
    )
    click.echo(f"Excluded {withdrawn} withdrawn controls/enhancements.")
    if baselines:
        for name, ids in baselines.items():
            click.echo(f"  {name} baseline: {len(ids)} controls")


@cli.command("etl-hipaa")
@click.option(
    "--date",
    default=None,
    help="Specific eCFR effective date (YYYY-MM-DD) to fetch, for reproducibility. "
    "Default: eCFR's current published date for Title 45.",
)
@click.option(
    "--out",
    default=Path("data/frameworks/hipaa-security-rule/controls.json"),
    type=click.Path(path_type=Path),
    help="Where to write the parsed control data.",
)
def etl_hipaa(date: str | None, out: Path):
    """Fetch the HIPAA Security Rule (45 CFR 164 Subpart C) from eCFR's public
    API and parse it into this project's data schema. Public domain — a US
    federal regulation, same basis as NIST/FedRAMP/ARC-AMPE — so unlike
    HITRUST/GovRAMP this is safe to bundle directly. See
    ingest/hipaa_loader.py for parsing details.
    """
    import dataclasses
    import json

    from policyforge.ingest.hipaa_loader import fetch_ecfr_subpart_c_xml, parse_hipaa_security_rule

    xml_text = fetch_ecfr_subpart_c_xml(date=date)
    controls = parse_hipaa_security_rule(xml_text)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps([dataclasses.asdict(c) for c in controls], indent=2),
        encoding="utf-8",
    )
    click.echo(f"Parsed {len(controls)} HIPAA Security Rule requirements -> {out}")


@cli.command("etl-hipaa-crosswalk")
@click.option(
    "--controls",
    "controls_path",
    default=Path("data/frameworks/hipaa-security-rule/controls.json"),
    type=click.Path(exists=True, path_type=Path),
    help="HIPAA controls.json produced by `etl-hipaa`, to enrich in place.",
)
@click.option(
    "--fixture",
    "fixture_path",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Parse this saved CPRT payload instead of fetching "
    "(e.g. tests/fixtures/cprt_hipaa_to_800-53r5.json). Offline/reproducible.",
)
@click.option(
    "--out",
    default=None,
    type=click.Path(path_type=Path),
    help="Where to write the enriched data (default: overwrite --controls).",
)
def etl_hipaa_crosswalk(controls_path: Path, fixture_path: Path | None, out: Path | None):
    """Attach NIST's official HIPAA-Security-Rule-to-SP-800-53-Rev-5 crosswalk
    to the HIPAA control data, so `map`/`synthesize` can pull HIPAA
    requirements into a NIST-anchored topic.

    Source is NIST's Cybersecurity and Privacy Reference Tool (CPRT), not SP
    800-66r2's PDF — Appendix D of that document states the mapping table was
    removed from the PDF and published in CPRT instead. See
    ingest/hipaa_crosswalk_loader.py.
    """
    import dataclasses
    import json

    from policyforge.ingest.hipaa_crosswalk_loader import (
        CPRT_FRAMEWORK_NAME,
        CPRT_FRAMEWORK_VERSION,
        apply_crosswalk,
        fetch_cprt_crosswalk,
        parse_cprt_crosswalk,
    )
    from policyforge.ingest.schema import load_controls

    if fixture_path is not None:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        click.echo(f"Source: {fixture_path} (saved CPRT export)")
    else:
        payload = fetch_cprt_crosswalk()
        click.echo(f"Source: CPRT {CPRT_FRAMEWORK_NAME} [{CPRT_FRAMEWORK_VERSION}]")

    mapping = parse_cprt_crosswalk(payload)
    controls = load_controls(controls_path)
    report = apply_crosswalk(controls, mapping)

    out_path = out or controls_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps([dataclasses.asdict(c) for c in controls], indent=2),
        encoding="utf-8",
    )

    click.echo(
        f"Mapped {report.mapped_controls} standards and "
        f"{report.mapped_enhancements} implementation specifications "
        f"from {len(mapping)} CPRT citations -> {out_path}"
    )
    # Anything NIST's crosswalk doesn't cover is reported rather than left
    # invisible — this is compliance data, so a gap should be an observation,
    # not a surprise.
    if report.unmapped_requirements:
        click.echo(
            f"Not covered by NIST's crosswalk ({len(report.unmapped_requirements)}): "
            + ", ".join(report.unmapped_requirements)
        )
    if report.unmatched_citations:
        click.echo(
            f"WARNING: {len(report.unmatched_citations)} CPRT citation(s) matched no HIPAA "
            "requirement and were skipped: " + ", ".join(report.unmatched_citations)
        )
    if report.unparsed_nist_ids:
        click.echo(
            f"WARNING: {len(report.unparsed_nist_ids)} CPRT control ID(s) were unparseable "
            "and were skipped: " + ", ".join(report.unparsed_nist_ids)
        )


@cli.command("map")
@click.option(
    "--controls",
    "controls_paths",
    multiple=True,
    default=(Path("data/frameworks/nist-800-53-r5/controls.json"),),
    type=click.Path(exists=True, path_type=Path),
    help="Path to a controls.json. Repeatable, and normally repeated: a "
    "cross-framework crosswalk needs every framework loaded together, so passing "
    "only the NIST file produces a crosswalk with nothing to cross-reference.",
)
@click.option(
    "--out",
    default=Path("data/frameworks/crosswalk.json"),
    type=click.Path(path_type=Path),
    help="Where to write the built crosswalk.",
)
def map_cmd(controls_paths, out: Path):
    """Build the NIST-anchored cross-framework crosswalk."""
    import json

    from policyforge.ingest.schema import load_controls
    from policyforge.mapping.crosswalk import build_crosswalk

    controls = []
    for path in controls_paths:
        controls.extend(load_controls(path))

    crosswalk = build_crosswalk(controls)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(crosswalk, indent=2), encoding="utf-8")

    frameworks = sorted({f for entry in crosswalk.values() for f in entry})
    click.echo(f"Built crosswalk for {len(crosswalk)} NIST controls -> {out}")
    if frameworks:
        click.echo(f"  Frameworks mapped: {', '.join(frameworks)}")
    else:
        click.echo(
            "  No cross-framework mappings found — pass every framework's "
            "controls.json with repeated --controls so they can be crossed."
        )


@cli.command("coverage")
@click.option(
    "--topics",
    "topics_path",
    default=Path("config/topics.yaml"),
    type=click.Path(exists=True, path_type=Path),
    help="Topic registry (default: config/topics.yaml). Copy config/topics.example.yaml to start.",
)
@click.option(
    "--controls",
    "controls_paths",
    required=True,
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a controls.json. Repeatable — pass the NIST 800-53 file plus any "
    "other framework you want reachability reported for.",
)
@click.option(
    "--baseline",
    type=click.Choice(["low", "moderate", "high"], case_sensitive=False),
    default=None,
    help="Limit the scope to one NIST baseline. 'Orphaned' only means anything "
    "relative to a defined scope, so this is usually what you want.",
)
@click.option(
    "--show-all", is_flag=True, help="List every orphaned control, not just the first 40."
)
@click.option(
    "--strict",
    is_flag=True,
    help="Exit non-zero if anything is orphaned, contested, or anchored to an unknown "
    "control — for use as a CI gate.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit the report as JSON instead of a text summary.",
)
def coverage_cmd(
    topics_path: Path,
    controls_paths,
    baseline: str | None,
    show_all: bool,
    strict: bool,
    as_json: bool,
):
    """Report which in-scope controls no topic owns, and which two topics claim.

    Orphaned controls mean nobody is doing the work. Contested controls are
    worse: it looks covered while each owner assumes the other has it. Both
    are pure set arithmetic over the topic registry — no LLM involved. See
    README's "One topic, one team".
    """
    import dataclasses
    import json as json_mod

    from policyforge.ingest.schema import load_controls
    from policyforge.mapping.crosswalk import build_crosswalk, normalize_framework
    from policyforge.ssp.workbook import select_for_baseline
    from policyforge.topics.coverage import analyze_coverage, format_report
    from policyforge.topics.registry import load_topics

    topics = load_topics(topics_path)

    all_controls = []
    for path in controls_paths:
        all_controls.extend(load_controls(path))

    nist_controls = [c for c in all_controls if normalize_framework(c.framework) == "nist"]
    if not nist_controls:
        raise click.UsageError(
            "None of the --controls files contain NIST 800-53 controls. Topics anchor "
            "NIST control IDs, so at least one is required. Run `policyforge etl-oscal`."
        )
    other_controls = [c for c in all_controls if normalize_framework(c.framework) != "nist"]

    scoped = nist_controls
    scope = "all controls"
    if baseline:
        scoped = select_for_baseline(nist_controls, baseline)
        scope = f"{baseline.capitalize()} baseline"
        if not scoped:
            raise click.UsageError(
                f"No controls matched the {baseline!r} baseline. Was the catalog loaded "
                "with baseline profiles (see `policyforge etl-oscal`)?"
            )

    report = analyze_coverage(
        topics,
        scoped,
        catalog=nist_controls,
        scope=scope,
        other_controls=other_controls,
        crosswalk=build_crosswalk(all_controls) if other_controls else None,
    )

    if as_json:
        click.echo(json_mod.dumps(dataclasses.asdict(report), indent=2))
    else:
        click.echo(format_report(report, show_all=show_all))

    if strict and not report.is_clean:
        raise SystemExit(1)


@cli.command("synthesize")
@click.option(
    "--topic-name",
    default=None,
    help="Name of a topic in the registry (config/topics.yaml). Takes its anchor "
    "controls and owning team from there, and records the owner in the output so "
    "`generate` names the real team instead of [Responsible Team].",
)
@click.option(
    "--topics",
    "topics_path",
    default=Path("config/topics.yaml"),
    type=click.Path(path_type=Path),
    help="Topic registry to resolve --topic-name against.",
)
@click.option(
    "--topic",
    default=None,
    help="Ad-hoc topic name, when not using the registry. Requires --nist-controls.",
)
@click.option(
    "--nist-controls",
    default=None,
    help="Comma-separated NIST control IDs anchoring an ad-hoc topic, e.g. IA-5,IA-5(1). "
    "Ignored when --topic-name is given.",
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
def synthesize_cmd(
    topic_name: str | None,
    topics_path: Path,
    topic: str | None,
    nist_controls: str | None,
    controls_paths,
    crosswalk_path: Path,
    out_dir: Path,
):
    """Merge/dedupe controls for one topic into synthesized requirement prose.

    Either `--topic-name <registry topic>`, which takes the anchor controls and
    the owning team from config/topics.yaml, or `--topic` plus
    `--nist-controls` for a one-off topic that isn't in the registry.
    """
    import json
    import re

    from policyforge.ingest.schema import load_controls
    from policyforge.synthesis.merge import build_synthesis_topic, synthesize_topic, write_synthesis
    from policyforge.topics.registry import load_topics

    if topic_name and (topic or nist_controls):
        raise click.UsageError(
            "--topic-name takes its name and anchors from the registry; don't also "
            "pass --topic/--nist-controls."
        )

    owner = cadence = ""
    evidence: list[str] = []
    if topic_name:
        registry = load_topics(topics_path)
        match = next((t for t in registry if t.name.lower() == topic_name.lower()), None)
        if match is None:
            raise click.UsageError(
                f"No topic named {topic_name!r} in {topics_path}. Available: "
                + ", ".join(sorted(t.name for t in registry))
            )
        topic = match.name
        nist_ids = list(match.nist_controls)
        owner, cadence, evidence = match.owner, match.cadence, list(match.evidence)
    elif topic and nist_controls:
        nist_ids = [c.strip() for c in nist_controls.split(",") if c.strip()]
    else:
        raise click.UsageError(
            "Give either --topic-name (a topic from config/topics.yaml) or both "
            "--topic and --nist-controls."
        )

    controls = []
    for path in controls_paths:
        controls.extend(load_controls(path))

    crosswalk = json.loads(crosswalk_path.read_text(encoding="utf-8"))
    synthesis_topic = build_synthesis_topic(topic, nist_ids, controls, crosswalk)
    if not synthesis_topic.controls:
        click.echo(f"No controls found for topic {topic!r} — check its anchors and --controls.")
        raise SystemExit(1)

    config = load_config()
    provider = get_provider(config)
    result = synthesize_topic(synthesis_topic, provider)

    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.md"
    out_path.write_text(
        write_synthesis(
            result,
            topic=topic,
            owner=owner,
            cadence=cadence,
            evidence=evidence,
            nist_controls=nist_ids,
        ),
        encoding="utf-8",
    )
    click.echo(f"Synthesized {len(synthesis_topic.controls)} controls for {topic!r} -> {out_path}")
    if owner:
        click.echo(f"  Owner: {owner}" + (f" | cadence: {cadence}" if cadence else ""))
    else:
        click.echo(
            "  No owning team recorded — generated documents will use "
            "[Responsible Team]. Use --topic-name to pull the owner from the registry."
        )


@cli.command("ssp")
@click.option(
    "--controls",
    "controls_paths",
    required=True,
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a controls.json. Repeatable — pass the NIST 800-53 file plus any "
    "other framework whose mappings you want shown as crosswalk columns.",
)
@click.option(
    "--baseline",
    type=click.Choice(["low", "moderate", "high"], case_sensitive=False),
    default=None,
    help="Limit the plan to one NIST baseline. Controls and enhancements are "
    "selected independently, matching NIST's own profiles. Default: every control.",
)
@click.option(
    "--system-name", default=None, help="System name (overrides config.yaml's system.name)."
)
@click.option(
    "--narratives/--no-narratives",
    default=True,
    help="Draft implementation descriptions with the configured LLM (one request per "
    "control). --no-narratives builds the workbook with those cells left empty.",
)
@click.option(
    "--yes", is_flag=True, help="Skip the confirmation prompt before making LLM requests."
)
@click.option(
    "--out",
    default=None,
    type=click.Path(path_type=Path),
    help="Where to write the workbook (default: output/ssp/<system-slug>-ssp.xlsx).",
)
def ssp_cmd(
    controls_paths,
    baseline: str | None,
    system_name: str | None,
    narratives: bool,
    yes: bool,
    out: Path | None,
):
    """Build a NIST 800-53 System Security Plan as a spreadsheet workbook.

    Writes .xlsx — an open ISO standard that LibreOffice Calc opens and edits
    natively, so no Excel licence is needed. Control text is copied verbatim
    from the catalog; only the implementation narratives are LLM-drafted, and
    those are marked as drafts requiring review. See ssp/workbook.py.
    """
    import datetime
    import re
    from dataclasses import fields as dataclasses_fields

    from policyforge.generate.policy_writer import OrgContext
    from policyforge.ingest.schema import load_controls
    from policyforge.mapping.crosswalk import build_crosswalk, normalize_framework
    from policyforge.ssp.narrative import SystemProfile, draft_implementation_narrative
    from policyforge.ssp.workbook import build_ssp_workbook, select_for_baseline

    config = load_config()
    org_cfg = config.get("org", {})
    org = OrgContext(
        name=org_cfg.get("name", ""),
        industry=org_cfg.get("industry", ""),
        vendors=org_cfg.get("vendors", []),
    )
    system_cfg = dict(config.get("system", {}) or {})
    if system_name:
        system_cfg["name"] = system_name
    known = {f.name for f in dataclasses_fields(SystemProfile)}
    unknown = sorted(set(system_cfg) - known)
    if unknown:
        raise click.UsageError(
            f"Unknown key(s) under `system:` in config.yaml: {', '.join(unknown)}. "
            f"Supported: {', '.join(sorted(known))}."
        )
    system = SystemProfile(**system_cfg)

    all_controls = []
    for path in controls_paths:
        all_controls.extend(load_controls(path))
    crosswalk = build_crosswalk(all_controls)

    nist_controls = [c for c in all_controls if normalize_framework(c.framework) == "nist"]
    if not nist_controls:
        raise click.UsageError(
            "None of the --controls files contain NIST 800-53 controls. Populate them "
            "first with `policyforge etl-oscal`."
        )

    scoped = select_for_baseline(nist_controls, baseline) if baseline else nist_controls
    if not scoped:
        raise click.UsageError(
            f"No controls matched the {baseline!r} baseline. Was the catalog loaded with "
            "baseline profiles (see `policyforge etl-oscal`)?"
        )

    drafted = {}
    if narratives:
        click.echo(
            f"Drafting implementation narratives for {len(scoped)} controls — "
            f"that is {len(scoped)} requests to your configured LLM provider."
        )
        if not yes:
            click.confirm("Continue?", abort=True)
        provider = get_provider(config)
        with click.progressbar(
            scoped, label="Drafting narratives", item_show_func=lambda c: c.control_id if c else ""
        ) as bar:
            for control in bar:
                drafted[control.control_id] = draft_implementation_narrative(
                    control, org, system, provider
                )

    slug = re.sub(r"[^a-z0-9]+", "-", (system.name or "system").lower()).strip("-")
    out_path = out or Path("output/ssp") / f"{slug}-ssp.xlsx"
    catalog_version = nist_controls[0].framework_version or "Rev 5"

    result = build_ssp_workbook(
        scoped,
        system=system,
        org=org,
        out_path=out_path,
        crosswalk=crosswalk,
        narratives=drafted,
        catalog_version=catalog_version,
        generated=datetime.date.today().isoformat(),
    )

    click.echo(
        f"Wrote SSP workbook -> {result.path}\n"
        f"  {result.control_count} controls, {result.enhancement_count} enhancements"
        + (f", {result.narrative_count} drafted narratives" if narratives else "")
    )
    if result.narrative_count:
        click.echo(
            "  Narratives are machine-drafted scaffolds marked "
            "'[DRAFT — REVIEW REQUIRED]' — review them before relying on this plan."
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
    help="Where to write the drafted document (default: output/<tier>s/<synthesis-filename>).",
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
        TopicContext,
        extract_title,
        generate_policy,
        generate_procedure,
        generate_standard,
    )
    from policyforge.synthesis.merge import read_synthesis

    config = load_config()
    org_cfg = config.get("org", {})
    org = OrgContext(
        name=org_cfg.get("name", ""),
        industry=org_cfg.get("industry", ""),
        vendors=org_cfg.get("vendors", []),
    )

    # Topic ownership travels in the synthesis file's frontmatter, written by
    # `synthesize --topic-name`. Files without it still work — they just draft
    # with [Responsible Team] placeholders, as before.
    metadata, topic_synthesis = read_synthesis(synthesis_path.read_text(encoding="utf-8"))
    topic_context = TopicContext(
        name=str(metadata.get("topic") or ""),
        owner=str(metadata.get("owner") or ""),
        cadence=str(metadata.get("cadence") or ""),
        evidence=list(metadata.get("evidence") or []),
    )
    if topic_context.owner:
        click.echo(f"Topic owner from synthesis frontmatter: {topic_context.owner}")
    else:
        click.echo(
            "No owner in the synthesis frontmatter — the draft will use "
            "[Responsible Team]. Re-run `synthesize --topic-name` to record one."
        )

    provider = get_provider(config)

    if tier in ("policy", "procedure"):
        if standard_path is None:
            raise click.UsageError(
                f"--standard is required when --tier {tier}, so the {tier.capitalize()} "
                "can reference its Standard document by name."
            )
        standard_title = extract_title(standard_path.read_text(encoding="utf-8"))
        generator = generate_policy if tier == "policy" else generate_procedure
        document = generator(
            topic_synthesis,
            org,
            provider,
            standard_title=standard_title,
            topic=topic_context,
        )
    else:
        document = generate_standard(topic_synthesis, org, provider, topic=topic_context)

    out_path = out or Path(f"output/{tier}s") / synthesis_path.name
    written = write_markdown(document + "\n", output_dir=out_path.parent, filename=out_path.name)
    if not check_markdown_quality(written):
        click.echo(
            f"WARNING: {written} did not pass the mdformat quality check — review before shipping."
        )
    click.echo(f"Drafted {tier} -> {written}")

    from policyforge.history.version_store import record_version

    slug = f"{tier}/{out_path.stem}"
    record = record_version(
        history_dir,
        slug,
        document + "\n",
        source="generate",
        metadata={
            "org": org.name,
            "model": config.get("llm", {}).get("model"),
            "synthesis_source": str(synthesis_path),
        },
    )
    if record is None:
        click.echo(
            f"No content change since the last recorded version of {slug!r} — history unchanged."
        )
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
def generate_parser_cmd(
    framework: str, sample_path: Path, out: Path | None, force: bool, yes: bool
):
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
        raise SystemExit(1) from exc

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
@click.option(
    "--parent-id", default=None, help="Parent page ID, if nesting under an existing page."
)
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


def _edit_run(
    *,
    targets,
    instruction: str,
    host: str,
    do_apply: bool,
    yes: bool,
    allow_macros: bool,
    out_dir: Path,
    history_dir: Path,
    config: dict,
):
    """Shared body of `edit-confluence` and `edit-topic`.

    Fetch everything, refuse anything unsafe, plan, rewrite, show, then
    publish only on explicit approval. Nothing is written back until every
    page has been planned and rewritten, so a failure part-way through leaves
    the whole set untouched.
    """
    import difflib
    import json
    import re

    from policyforge.edit.session import apply_targets, fetch_targets, plan_targets
    from policyforge.export.confluence_exporter import ConcurrentEditError, update_page_body
    from policyforge.history.version_store import record_version

    provider = get_provider(config)
    model = (config.get("llm") or {}).get("model", "")

    fetch_targets(targets, host=host)
    for target in targets:
        click.echo(f"Fetched {target.label!r} (version {target.version}) — {target.webui_url}")

    # storage -> markdown -> storage is lossless only for what this project's
    # own exporter emits. Check every page before spending anything on the
    # LLM, so an unsafe page in a set fails the run up front rather than after
    # the other pages have already been rewritten.
    unsafe = [t for t in targets if t.unsupported_macros]
    if unsafe and not allow_macros:
        detail = "\n".join(f"  {t.label}: {', '.join(t.unsupported_macros)}" for t in unsafe)
        raise click.UsageError(
            "These pages use Confluence macros this tool cannot round-trip:\n"
            f"{detail}\nEditing them would flatten or drop those macros. Edit in "
            "Confluence directly, or re-run with --allow-macros if you have checked "
            "that losing them is acceptable."
        )
    for target in unsafe:
        click.echo(
            f"WARNING: {target.label} has unsupported macros: "
            f"{', '.join(target.unsupported_macros)}"
        )

    slugs = {id(t): re.sub(r"[^a-z0-9]+", "-", t.title.lower()).strip("-") for t in targets}

    # Record the pre-edit state before the first LLM call, so there is a local
    # copy to restore from even if the run is abandoned partway.
    for target in targets:
        record_version(
            history_dir,
            f"confluence/{slugs[id(target)]}",
            target.original,
            source="confluence-edit-before",
            metadata={
                "space": target.space,
                "title": target.title,
                "tier": target.tier,
                "page_version": target.version,
            },
        )

    outcomes = plan_targets(targets, instruction, provider)
    for outcome in outcomes:
        click.echo("")
        click.echo("=" * 60)
        click.echo(outcome.plan.render())

    if all(o.plan.is_empty for o in outcomes):
        click.echo("\nNo edits proposed for any page. Nothing to apply.")
        return

    apply_targets(outcomes, provider)
    out_dir.mkdir(parents=True, exist_ok=True)

    publishable = []
    for outcome in outcomes:
        if outcome.plan.is_empty:
            click.echo(f"\n{outcome.target.label}: no edits planned — leaving unchanged.")
            continue
        check = outcome.check
        click.echo("")
        click.echo("=" * 60)
        click.echo(f"{outcome.target.label} (+{check.lines_added}/-{check.lines_removed})")
        diff = list(
            difflib.unified_diff(
                outcome.target.original.splitlines(),
                outcome.revised.splitlines(),
                "before",
                "after",
                lineterm="",
                n=2,
            )
        )
        for line in diff[:120]:
            click.echo("  " + line)
        if len(diff) > 120:
            click.echo(f"  ... {len(diff) - 120} more diff lines")

        if check.unchanged:
            click.echo("  (rewrite is identical to the live page — nothing to publish)")
            continue
        if not check.is_clean:
            if check.dropped_source_tags:
                click.echo(
                    "  WARNING: framework citations present before are missing after: "
                    + ", ".join(check.dropped_source_tags)
                )
            if check.removed_headings:
                click.echo(
                    "  WARNING: sections removed that the plan did not ask to remove: "
                    + ", ".join(check.removed_headings)
                )
            click.echo("  These are traceability losses — review before publishing.")

        slug = slugs[id(outcome.target)]
        (out_dir / f"{slug}.md").write_text(outcome.revised, encoding="utf-8")
        # The plan is written next to the revision, so a dry run leaves a
        # reviewable artifact rather than only terminal output that scrolls away.
        (out_dir / f"{slug}.plan.json").write_text(
            json.dumps(outcome.plan.as_record(), indent=2), encoding="utf-8"
        )
        click.echo(f"  -> {out_dir / f'{slug}.md'} (plan: {slug}.plan.json)")
        publishable.append(outcome)

    if not publishable:
        click.echo("\nNothing to publish.")
        return

    if not do_apply:
        click.echo(
            f"\nDry run — Confluence unchanged. Re-run with --apply to publish "
            f"{len(publishable)} page(s)."
        )
        return

    if not yes:
        names = ", ".join(o.target.label for o in publishable)
        click.confirm(f"Publish edits to {names}?", abort=True)

    published, failed = [], []
    for outcome in publishable:
        target = outcome.target
        try:
            url = update_page_body(
                outcome.revised,
                page_id=target.page_id,
                title=target.title,
                space=target.space,
                host=host,
                expected_version=target.version,
            )
        except ConcurrentEditError as exc:
            failed.append((target, str(exc)))
            continue

        record_version(
            history_dir,
            f"confluence/{slugs[id(target)]}",
            outcome.revised,
            source="confluence-edit-after",
            metadata={
                "space": target.space,
                "title": target.title,
                "tier": target.tier,
                "page_version": target.version + 1,
                "model": model,
                "plan": outcome.plan.as_record(),
            },
        )
        published.append((target, url))
        click.echo(f"Published {target.label} version {target.version + 1} -> {url}")

    if failed:
        click.echo("")
        for target, message in failed:
            click.echo(f"FAILED {target.label}: {message}")
        if published:
            click.echo(
                f"\n{len(published)} page(s) were published before this failed. The set is "
                "now partly updated — re-run for the remaining pages once the conflict "
                "is resolved."
            )
        raise SystemExit(1)


@cli.command("edit-confluence")
@click.option("--instruction", required=True, help="What to change, in plain language.")
@click.option("--space", required=True, help="Confluence space key.")
@click.option("--title", required=True, help="Exact page title to edit.")
@click.option(
    "--host", required=True, help="Confluence base URL, e.g. https://x.atlassian.net/wiki."
)
@click.option(
    "--tier",
    type=click.Choice(["policy", "standard", "procedure"]),
    default=None,
    help="Which document tier this page is. Tells the planner what altitude to "
    "edit at — a threshold change belongs in a Standard, not a Policy.",
)
@click.option(
    "--apply",
    "do_apply",
    is_flag=True,
    help="Actually publish the edit. Without this the command plans, rewrites and "
    "shows you the diff, but changes nothing in Confluence.",
)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt before publishing.")
@click.option(
    "--allow-macros",
    is_flag=True,
    help="Proceed even though the page uses Confluence macros this tool cannot "
    "round-trip. They will be degraded or lost. Read the warning first.",
)
@click.option(
    "--out-dir",
    default=Path("output/edits"),
    type=click.Path(path_type=Path),
    help="Where the revised markdown and its plan are written.",
)
@click.option(
    "--history-dir",
    default=_DEFAULT_HISTORY_DIR,
    type=click.Path(path_type=Path),
    help="Where local version history is recorded (default: output/.history).",
)
def edit_confluence_cmd(
    instruction: str,
    space: str,
    title: str,
    host: str,
    tier: str | None,
    do_apply: bool,
    yes: bool,
    allow_macros: bool,
    out_dir: Path,
    history_dir: Path,
):
    """Edit one live Confluence page from a plain-language instruction.

    Fetches the page, plans the edits, shows you the plan and the resulting
    diff, and publishes only if you pass --apply and confirm. The page's
    "before" state is recorded to local version history either way, and the
    plan is saved alongside the revision, so there is always something to
    diff against and a record of why it changed.
    """
    from policyforge.edit.session import EditTarget

    _edit_run(
        targets=[EditTarget(space=space, title=title, tier=tier or "")],
        instruction=instruction,
        host=host,
        do_apply=do_apply,
        yes=yes,
        allow_macros=allow_macros,
        out_dir=out_dir,
        history_dir=history_dir,
        config=load_config(),
    )


@cli.command("edit-topic")
@click.option("--instruction", required=True, help="What to change, in plain language.")
@click.option("--topic-name", required=True, help="Topic in the registry whose documents to edit.")
@click.option(
    "--topics",
    "topics_path",
    default=Path("config/topics.yaml"),
    type=click.Path(path_type=Path),
    help="Topic registry to resolve --topic-name against.",
)
@click.option(
    "--host", required=True, help="Confluence base URL, e.g. https://x.atlassian.net/wiki."
)
@click.option(
    "--tiers",
    default=None,
    help="Comma-separated subset of tiers to edit (e.g. 'standard,procedure'). "
    "Default: every page the topic declares.",
)
@click.option(
    "--apply",
    "do_apply",
    is_flag=True,
    help="Actually publish. Without this nothing in Confluence changes.",
)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt before publishing.")
@click.option(
    "--allow-macros",
    is_flag=True,
    help="Proceed even though a page uses Confluence macros this tool cannot round-trip.",
)
@click.option(
    "--out-dir",
    default=Path("output/edits"),
    type=click.Path(path_type=Path),
    help="Where revised markdown and plans are written.",
)
@click.option(
    "--history-dir",
    default=_DEFAULT_HISTORY_DIR,
    type=click.Path(path_type=Path),
    help="Where local version history is recorded (default: output/.history).",
)
def edit_topic_cmd(
    instruction: str,
    topic_name: str,
    topics_path: Path,
    host: str,
    tiers: str | None,
    do_apply: bool,
    yes: bool,
    allow_macros: bool,
    out_dir: Path,
    history_dir: Path,
):
    """Apply one instruction across a topic's whole document set.

    A change like "access reviews move to monthly" lands differently in each
    tier: the Standard states the requirement, the Procedure carries the
    steps, and the Policy usually shouldn't change at all. Each page is
    planned separately and tier-aware, but reviewed and published as one
    change — and a page whose plan comes back empty is left alone rather than
    having an edit forced into it.
    """
    from policyforge.edit.session import EditTarget
    from policyforge.topics.registry import load_topics

    registry = load_topics(topics_path)
    topic = next((t for t in registry if t.name.lower() == topic_name.lower()), None)
    if topic is None:
        raise click.UsageError(
            f"No topic named {topic_name!r} in {topics_path}. Available: "
            + ", ".join(sorted(t.name for t in registry))
        )

    space = (topic.confluence or {}).get("space")
    pages = topic.confluence_pages()
    if not space or not pages:
        raise click.UsageError(
            f"Topic {topic.name!r} has no `confluence:` block naming its space and "
            "pages, so there is nothing to edit. Add one to the registry:\n"
            "    confluence:\n"
            "      space: ENG\n"
            "      pages:\n"
            '        standard: "<page title>"'
        )

    if tiers:
        wanted = {t.strip().lower() for t in tiers.split(",") if t.strip()}
        pages = [(tier, title) for tier, title in pages if tier.lower() in wanted]
        if not pages:
            raise click.UsageError(
                f"Topic {topic.name!r} declares no pages for tier(s) {tiers!r}. It has: "
                + ", ".join(tier for tier, _ in topic.confluence_pages())
            )

    click.echo(
        f"Topic {topic.name!r} (owner: {topic.owner or 'unassigned'}) — "
        f"{len(pages)} page(s) in {space}"
    )
    _edit_run(
        targets=[EditTarget(space=space, title=title, tier=tier) for tier, title in pages],
        instruction=instruction,
        host=host,
        do_apply=do_apply,
        yes=yes,
        allow_macros=allow_macros,
        out_dir=out_dir,
        history_dir=history_dir,
        config=load_config(),
    )


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
        history_dir,
        slug,
        markdown_text,
        source="confluence-import",
        metadata={"space": space, "title": title},
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
    # "confluence" is the stream `edit-confluence`/`edit-topic` write into,
    # keyed by page-title slug rather than document name. Without it here,
    # those commands recorded history this command could not display.
    type=click.Choice(["standard", "policy", "procedure", "confluence"]),
    required=True,
)
@click.option(
    "--name",
    required=True,
    help="Document slug/filename stem — the stem of the file `policyforge generate` "
    "wrote via --out (e.g. 'authenticator-mgmt' for authenticator-mgmt.md), the "
    "--name given to `import-confluence`, or for --tier confluence, the page title "
    "slugified (e.g. 'access-control-standard').",
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
                raise click.UsageError(
                    f"--diff must be 'N:M' or 'latest', got {diff_range!r}."
                ) from exc
        click.echo(diff_versions(history_dir, slug, v1, v2))
        return

    for record in records:
        click.echo(
            f"v{record.version}  {record.timestamp}  {record.source:<22} "
            f"+{record.lines_added}/-{record.lines_removed}  {record.content_hash}"
        )
        # An edit's plan is the "why" behind the version. Storing it without
        # ever showing it would leave the changelog answering what changed but
        # not what was asked for, or what was deliberately not done.
        metadata = record.metadata or {}
        plan = metadata.get("plan")
        if plan:
            click.echo(f"        asked: {plan.get('instruction', '')}")
            for step in plan.get("steps") or []:
                click.echo(
                    f"        - [{step.get('kind')}] {step.get('target')}: {step.get('summary')}"
                )
            for risk in plan.get("risks") or []:
                click.echo(f"        ! flagged: {risk}")
            for skipped in plan.get("out_of_scope") or []:
                click.echo(f"        ~ not done: {skipped}")
        elif metadata.get("instruction"):
            click.echo(f"        asked: {metadata['instruction']}")


def _zardoz_setting(config: dict, key: str, override: str) -> str:
    """CLI flag beats config file beats nothing.

    Host and supporting space live in config because they are properties of
    the organization rather than of one invocation — you type them once, not
    every time you open the shell.
    """
    if override:
        return override
    return str((config.get("zardoz") or {}).get(key) or "")


@cli.group("zardoz", invoke_without_command=True)
@click.option(
    "--topics",
    "topics_path",
    default=Path("config/topics.yaml"),
    type=click.Path(path_type=Path),
    help="Topic registry to load, for ownership and page lookups.",
)
@click.option(
    "--corpus-dir",
    default=Path("output/.zardoz"),
    type=click.Path(path_type=Path),
    help="Where the synced document snapshot lives.",
)
@click.option("--no-art", is_flag=True, help="Skip the floating head on launch.")
@click.option(
    "--plain",
    is_flag=True,
    help="Drop the Zardoz voice from the shell chrome entirely. Answers are "
    "plain either way — this only affects greetings, prompts and errors.",
)
@click.pass_context
def zardoz_cmd(ctx, topics_path: Path, corpus_dir: Path, no_art: bool, plain: bool):
    """Ask questions about your published policy set, conversationally.

    Run with no subcommand to open the shell. Zardoz reads; it does not
    write. It can draft a `policyforge edit-topic` command for you to run,
    but every change to a live page still goes through that command's gates.
    """
    from policyforge.topics.registry import TopicRegistryError, load_topics

    # A missing or broken registry is not fatal: the shell is still useful
    # without it, and starting up to say what's wrong beats a traceback.
    topics, registry_note = [], ""
    try:
        topics = load_topics(topics_path)
    except FileNotFoundError:
        registry_note = (
            f"  (no topic registry at {topics_path} — /topics will be empty. "
            "Copy config/topics.example.yaml to start one.)"
        )
    except TopicRegistryError as exc:
        registry_note = f"  (topic registry at {topics_path} could not be read: {exc})"

    ctx.ensure_object(dict)
    ctx.obj.update(topics=topics, topics_path=topics_path, corpus_dir=corpus_dir)
    if ctx.invoked_subcommand is not None:
        return

    from policyforge.zardoz.art import banner
    from policyforge.zardoz.corpus import load_corpus
    from policyforge.zardoz.shell import ShellState, run_shell

    # An unsynced corpus is a normal state to open the shell in, not an
    # error: /topics and /corpus both still answer, and /corpus is where the
    # explanation of what to do about it lives.
    corpus, corpus_note = None, ""
    try:
        corpus = load_corpus(corpus_dir)
    except FileNotFoundError:
        corpus_note = "  (no documents synced yet — run `policyforge zardoz sync`)"
    except ValueError as exc:
        corpus_note = f"  ({exc})"

    # An LLM is optional. Without one the shell still finds and shows the
    # passages a question is about — retrieval is entirely offline — so a
    # missing API key costs you the prose, not the search.
    provider, provider_note = None, ""
    try:
        provider = get_provider(load_config())
    except FileNotFoundError:
        provider_note = "No config/config.yaml, so no model to write answers with"
    except (KeyError, ValueError) as exc:
        provider_note = f"No usable llm config ({exc})"

    click.echo(banner(art=not no_art, plain=plain))
    for note in (registry_note, corpus_note):
        if note:
            click.echo(note)
    if provider_note:
        click.echo(f"  ({provider_note} — questions will return passages, not prose)")
    if corpus is not None and corpus.is_stale:
        click.echo(f"  (this snapshot is {corpus.age_days:.0f} days old — re-sync, then /reload)")
    click.echo("")

    run_shell(
        ShellState(
            topics=topics,
            plain=plain,
            corpus=corpus,
            corpus_dir=corpus_dir,
            provider=provider,
            provider_note=provider_note,
        ),
        read=lambda prompt: click.prompt(prompt, prompt_suffix="", show_default=False),
        write=click.echo,
    )


@zardoz_cmd.command("sync")
@click.option(
    "--content-dir",
    default=None,
    type=click.Path(path_type=Path),
    help="Markdown content tree to read. Defaults to `zardoz.content_dir` in "
    "config.yaml. Needs no credentials.",
)
@click.option(
    "--host",
    default="",
    help="Confluence base URL. Defaults to `zardoz.host` in config.yaml. Omit "
    "to sync from markdown only.",
)
@click.option(
    "--supporting-space",
    default="",
    help="Extra space to pull as unowned supporting context. Defaults to "
    "`zardoz.supporting_space` in config.yaml. Omit for registry pages only.",
)
@click.option(
    "--max-results",
    default=500,
    show_default=True,
    help="Refuse to walk a supporting space larger than this, rather than "
    "silently syncing an arbitrary subset of it.",
)
@click.option(
    "--allow-empty",
    is_flag=True,
    help="Let a sync that resolves nothing clear the existing corpus. Without "
    "this, a run that finds no documents leaves the previous snapshot alone.",
)
@click.pass_context
def zardoz_sync(
    ctx,
    content_dir: Path | None,
    host: str,
    supporting_space: str,
    max_results: int,
    allow_empty: bool,
):
    """Build the local snapshot Zardoz answers from.

    Reads a markdown content tree, a Confluence space, or both. Markdown
    needs no credentials at all, so a repo-backed document set can be synced
    and questioned offline. Where both are configured the tree wins: in that
    arrangement the file is the source of truth and the page is a copy of it.

    Documents that know their owner — from the topic registry, or from their
    own frontmatter — are trusted; everything else is supporting context that
    answers may use and will say they used.
    """
    from policyforge.zardoz.corpus import sync_corpus

    topics = ctx.obj["topics"]
    corpus_dir = ctx.obj["corpus_dir"]

    try:
        config = load_config()
    except FileNotFoundError:
        config = {}

    host = _zardoz_setting(config, "host", host)
    supporting_space = _zardoz_setting(config, "supporting_space", supporting_space)
    if content_dir is None:
        configured = _zardoz_setting(config, "content_dir", "")
        content_dir = Path(configured) if configured else None

    if content_dir is None and not host:
        raise click.UsageError(
            "Nothing to sync from. Point at a markdown tree, a Confluence host, or "
            "both:\n"
            "    policyforge zardoz sync --content-dir docs\n"
            "or in config/config.yaml:\n"
            "    zardoz:\n"
            "      content_dir: docs\n"
            "      host: https://yourorg.atlassian.net/wiki"
        )
    if content_dir is not None and not content_dir.exists():
        raise click.UsageError(
            f"No content directory at {content_dir}. Create it, point --content-dir "
            "somewhere else, or drop it and sync from Confluence only."
        )
    if host and not topics:
        raise click.UsageError(
            f"No topics loaded from {ctx.obj['topics_path']}, so there are no Confluence "
            "pages to sync. Copy config/topics.example.yaml and declare each topic's "
            "pages under a `confluence:` block, or sync from markdown only."
        )

    what = []
    if content_dir is not None:
        what.append(f"markdown under {content_dir}")
    if host:
        declared = sum(len(topic.confluence_pages()) for topic in topics)
        what.append(f"{declared} declared page(s) from {len(topics)} topic(s)")
        if supporting_space:
            what.append(f"space {supporting_space}")
    click.echo("Syncing " + ", plus ".join(what))

    report = sync_corpus(
        topics,
        host=host,
        content_dir=content_dir,
        supporting_space=supporting_space,
        corpus_dir=corpus_dir,
        max_results=max_results,
        allow_empty=allow_empty,
    )
    click.echo("")
    click.echo(report.format_report())
    if report.refused_empty:
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
