"""Fetching framework catalogs and turning them into this project's schema."""

from __future__ import annotations

from pathlib import Path

import click

from policyforge.cli import cli
from policyforge.cli._common import (
    get_provider,
    load_config,
)
from policyforge.textfile import write_text_lf


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
    project's data schema. Public-domain content only - see
    ingest/nist_vault_loader.py for what crosswalk columns are stripped
    by default and why.
    """
    import dataclasses
    import json

    from policyforge.ingest.nist_vault_loader import load_vault_controls

    controls = load_vault_controls(controls_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(out, json.dumps([dataclasses.asdict(c) for c in controls], indent=2))
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

    Public domain - a US government work, same basis as the eCFR and CPRT
    sources. Unlike `etl-vault`, this needs no pre-existing vault, so it's
    the way to populate 800-53 data from scratch. See ingest/oscal_loader.py.
    """
    import dataclasses
    import json

    from policyforge.ingest.oscal_loader import (
        CATALOG_URL,
        OSCAL_REF,
        fetch_oscal_baselines,
        fetch_oscal_catalog,
        parse_oscal_catalog,
    )
    from policyforge.ingest.provenance import record_source_provenance

    catalog = fetch_oscal_catalog()
    baselines = {} if no_baselines else fetch_oscal_baselines()
    controls, withdrawn = parse_oscal_catalog(catalog, baselines)

    out.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(out, json.dumps([dataclasses.asdict(c) for c in controls], indent=2))
    enhancements = sum(len(c.enhancements) for c in controls)
    click.echo(
        f"Parsed {len(controls)} controls and {enhancements} enhancements "
        f"({catalog['catalog']['metadata']['version']}) -> {out}"
    )
    click.echo(f"Excluded {withdrawn} withdrawn controls/enhancements.")

    # Provenance travels with the data, not just in the loader's source. A
    # reviewer holding controls.json can now name the upstream revision and
    # check the hash, which is the difference between "an upstream revision"
    # and "an upstream compromise" — the two look identical in a diff.
    stamp = record_source_provenance(
        out.parent / "framework.yaml",
        source_ref=OSCAL_REF,
        source_url=CATALOG_URL,
        content=out.read_bytes(),
    )
    if stamp is not None:
        click.echo(f"Recorded provenance: {OSCAL_REF} sha256:{stamp[:16]}… -> {out.parent}")
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
    API and parse it into this project's data schema. Public domain - a US
    federal regulation, same basis as NIST/FedRAMP/ARC-AMPE - so unlike
    HITRUST/GovRAMP this is safe to bundle directly. See
    ingest/hipaa_loader.py for parsing details.
    """
    import dataclasses
    import json

    from policyforge.ingest.hipaa_loader import (
        current_ecfr_date,
        ecfr_source_url,
        fetch_ecfr_subpart_c_xml,
        parse_hipaa_security_rule,
    )
    from policyforge.ingest.provenance import record_source_provenance

    # Resolved here rather than inside the fetch so the date recorded is
    # provably the date fetched. eCFR has no tags — the effective date is
    # the only thing that names a revision — so it is this framework's
    # equivalent of the OSCAL release tag.
    date = date or current_ecfr_date()

    xml_text = fetch_ecfr_subpart_c_xml(date=date)
    controls = parse_hipaa_security_rule(xml_text)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(out, json.dumps([dataclasses.asdict(c) for c in controls], indent=2))
    stamp = record_source_provenance(
        out.parent / "framework.yaml",
        source_ref=date,
        source_url=ecfr_source_url(date),
        content=out.read_bytes(),
    )
    if stamp is not None:
        click.echo(f"Recorded provenance: {date} sha256:{stamp[:16]}… -> {out.parent}")
    click.echo(f"Parsed {len(controls)} HIPAA Security Rule requirements -> {out}")


def _bundled_catalog_dirs() -> list[Path]:
    """The bundled catalog directories that exist and must never take licensed data.

    Every `data/frameworks` found by searching upward from where the command
    runs, the way git finds a repository root, plus the one in the checkout
    this code was imported from.

    Upward rather than only in the working directory, and the difference was
    a bypass: the first version of this looked for `./data/frameworks`, so a
    command run from inside `data/` looked for `data/data/frameworks`, found
    nothing, and let `--out frameworks/...` write a licensed catalog into the
    repository's bundled directory. What must be protected is the directory
    that gets committed and pushed, wherever the command happens to run.

    Searching upward cannot over-refuse: a `data/frameworks` somewhere above
    only matters if the destination is inside it.
    """
    cwd = Path.cwd()
    candidates = [base / "data" / "frameworks" for base in (cwd, *cwd.parents)]
    here = Path(__file__).resolve()
    if len(here.parents) > 3:
        candidates.append(here.parents[3] / "data" / "frameworks")
    found: list[Path] = []
    for candidate in candidates:
        if candidate.is_dir() and candidate not in found:
            found.append(candidate)
    return found


def _names_a_bundled_catalog_directory(out: Path) -> bool:
    """Whether `out`, as written or as resolved, runs through a `data/frameworks`.

    The identity test below only knows the bundled directories it can find
    from here, so another checkout's is protected by this one alone. It
    compares path components, case-folded, on both the path as given and its
    resolved form. Case-folded because on a case-insensitive filesystem
    `Data/Frameworks` is the same directory: run from outside another
    checkout, an absolute `.../Data/Frameworks/govramp/controls.json` got
    past the case-sensitive substring this replaced and wrote the catalog
    into that checkout's bundled directory (found by policyforge-ba).
    Resolved because `data/x/../frameworks` is the same directory too.

    On a case-sensitive filesystem this refuses a `Data/Frameworks` that is a
    different directory. That is the chosen side to err on: the cost is
    naming another directory, and the other side's cost is a licensed
    catalog in a public repository.
    """
    import os
    from itertools import pairwise

    for spelling in (out, Path(os.path.realpath(out))):
        parts = [part.casefold() for part in spelling.parts]
        if ("data", "frameworks") in pairwise(parts):
            return True
    return False


def _lands_in_bundled_catalogs(out: Path) -> bool:
    """Whether writing `out` would put a file inside a bundled catalog directory.

    Asked of the filesystem, not of the path's spelling. `out` usually does
    not exist yet, so each existing ancestor is compared to each bundled
    directory with `samefile`, which follows the filesystem's own rules: case
    folding where the filesystem folds case, `..`, symlinks and junctions. The
    path is joined to the working directory without normalising it, so a `..`
    is resolved physically, the way the write would resolve it.
    """
    import os

    bundled = _bundled_catalog_dirs()
    if not bundled:
        return False
    probe = out if out.is_absolute() else Path.cwd() / out
    for ancestor in (probe, *probe.parents):
        try:
            if not ancestor.exists():
                continue
            if any(os.path.samefile(ancestor, directory) for directory in bundled):
                return True
        except OSError:
            continue
    return False


def _guard_licensed_write(out: Path, *, force: bool, product: str, licence: str, noun: str):
    """Refuse to write a licensed catalog anywhere it could be redistributed.

    `etl-hitrust` and `etl-govramp` each carried a copy of this, word for word
    apart from what the catalog is called. Two copies of a guard that exists
    to keep licensed content out of a public repository is two places for it
    to be weakened, and one of them would be the one nobody checks.

    Two rules, in order. The bundled `data/frameworks/` directory never takes
    a licensed catalog, whatever the flags — it is this project's public,
    redistributable half, and a file written there gets committed and pushed.
    Anywhere else, a gitignored destination needs no permission, because a
    file git will never stage cannot be redistributed by accident; a tracked
    one needs the repository to have declared it may hold licensed content,
    or an explicit --force.
    """
    from policyforge.frameworks.registry import frameworks_config, is_ignored

    # The bundled directory is this project's public, redistributable half.
    # A licensed catalog written there would be committed and pushed.
    #
    # Two tests, because each alone was bypassable. The spelling test refuses
    # any path running through data/frameworks, in this checkout or another.
    # The identity test asks the filesystem whether the destination is inside
    # the bundled directory this command would actually read, which catches
    # `--out frameworks/...` run from inside data/. Both bypasses were
    # reproduced with --force before their fixes.
    if _names_a_bundled_catalog_directory(out) or _lands_in_bundled_catalogs(out):
        raise click.ClickException(
            f"{out} is inside data/frameworks/, which is this project's bundled "
            f"public content. A {product} must never be written there. Use "
            "local_content/ or your own repository's frameworks/ directory."
        )

    # Gitignored destinations need no permission: a file git will never
    # stage cannot be redistributed by accident. Everywhere else, the
    # repository has to have said it may hold licensed content.
    config = load_config()
    ignored = is_ignored(out)
    permitted = bool(frameworks_config(config).get("allow_licensed_in_repo"))
    if not ignored and not permitted and not force:
        unknown = "" if ignored is False else " (and git could not confirm it is ignored)"
        click.echo(
            f"\n{out} is not gitignored{unknown}, and this repository has not "
            "declared `frameworks.allow_licensed_in_repo`, so writing a licensed "
            "catalog there is refused. Write it under local_content/, set that "
            f"flag in config.yaml if your {licence} licence permits your repository "
            f"to carry the {noun}, or pass --force."
        )
        raise SystemExit(1)


@cli.command("etl-hitrust")
@click.option(
    "--export",
    "export_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Your own MyCSF/HITRUST CSF export (.csv, .tsv, .xlsx, .html, .mhtml). "
    "Keep it in local_content/, which is gitignored.",
)
@click.option(
    "--version",
    "version",
    default="",
    help='CSF release this export is of, e.g. "v11.7". Default: read from the '
    "filename if it names one - a MyCSF export states its release nowhere inside.",
)
@click.option(
    "--out",
    default=None,
    type=click.Path(path_type=Path),
    help="Write the parsed catalog here as controls.json. Omit to parse and "
    "report without writing anything, which is the safe default for licensed "
    "content.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Write --out even though this repository has not declared "
    "`frameworks.allow_licensed_in_repo`.",
)
def etl_hitrust(export_path: Path, version: str, out: Path | None, force: bool):
    """Parse your own licensed HITRUST CSF export into this project's schema.

    HITRUST CSF is licensed content. This project never bundles it and never
    fetches it: you supply an export from your own MyCSF licence and it is
    parsed locally, in memory. Nothing is written unless you pass --out.

    Prefer a CSV export where you have the choice. The rendered HTML/MHTML of
    the same report is more clearly labelled but carries markedly fewer
    authoritative-source mappings, which is most of what makes a CSF export
    worth ingesting.

    See ingest/hitrust.py for the framework's structure and
    ingest/hitrust_export.py for how the columns are identified. If detection
    fails on your export, `policyforge generate-parser --framework hitrust`
    drafts a loader for it from a sample.
    """
    import dataclasses
    import json

    from policyforge.ingest.byoc_loader import load_hitrust_export
    from policyforge.ingest.hitrust import summarize
    from policyforge.ingest.hitrust_export import ExportFormatError

    try:
        controls = load_hitrust_export(export_path, version=version)
    except ExportFormatError as exc:
        raise click.ClickException(
            f"{exc}\n\nIf this export's layout is one this project has not seen, "
            "run:\n  policyforge generate-parser --framework hitrust --sample "
            f"{export_path}"
        ) from exc

    click.echo(summarize(controls).format_report())

    if out is None:
        click.echo(
            "\nNothing written. Pass --out <path> to save a controls.json - into "
            "a repository whose licence permits holding HITRUST content."
        )
        return

    _guard_licensed_write(
        out, force=force, product="HITRUST export", licence="MyCSF", noun="export"
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(out, json.dumps([dataclasses.asdict(c) for c in controls], indent=2))
    click.echo(f"\nWrote {len(controls)} HITRUST control references -> {out}")


@cli.command("etl-govramp")
@click.option(
    "--export",
    "export_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Your own GovRAMP controls matrix workbook (.xlsx/.xlsm), as published. "
    "Keep it in local_content/, which is gitignored.",
)
@click.option(
    "--impact-level",
    type=click.Choice(["Low", "Moderate", "High"], case_sensitive=False),
    default=None,
    help="FIPS 199 level this matrix is for. Default: read from the workbook's "
    "cover sheet, then from the filename. Worth setting on a template somebody "
    "has been working in, where the cover sheet is the first thing edited.",
)
@click.option(
    "--version",
    "version",
    default="",
    help='Revision and template version to stamp, e.g. "Rev 5 (V1.06)". '
    "Default: the revision from the cover sheet plus the version in the filename.",
)
@click.option(
    "--out",
    default=None,
    type=click.Path(path_type=Path),
    help="Write the parsed catalog here as controls.json. Omit to parse and "
    "report without writing anything, which is the safe default for licensed "
    "content.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Write --out even though this repository has not declared "
    "`frameworks.allow_licensed_in_repo`.",
)
def etl_govramp(export_path: Path, impact_level: str | None, version: str, out: Path | None, force):
    """Parse your own GovRAMP controls matrix into this project's schema.

    GovRAMP's Terms & Conditions claim ownership of the documents published
    on their site, and no redistribution grant was found - so, like HITRUST,
    this project never bundles the matrix and never fetches it. You supply
    the workbook and it is parsed locally, in memory. Nothing is written
    unless you pass --out.

    Pass the workbook as GovRAMP publishes it rather than an extract of it:
    the controls sheet is found among the template's other thirteen by its
    header captions, so the Low, Moderate and High workbooks all read
    without being told which they are.

    What this gives you that the 800-53 catalog does not is the profile's
    own two additions - the parameter values GovRAMP has already decided
    ("at least every 3 years"), which `policyforge parameters` would
    otherwise leave open for you to answer, and the requirements it layers
    on top of a control - across the Core/Ready/Authorized tiers. Those
    tiers are *not* impact levels: one Moderate matrix holds all three, and
    60 of its 319 controls stand between a service offering and Core.

    See ingest/govramp.py for the framework's structure and
    ingest/govramp_export.py for how the sheet and its two-row header are
    found. If detection fails on your workbook, `policyforge generate-parser
    --framework govramp` drafts a loader for it from a sample.
    """
    import dataclasses
    import json

    from policyforge.ingest.govramp import summarize
    from policyforge.ingest.govramp_export import ExportFormatError, load_with_rows

    try:
        controls, rows = load_with_rows(
            export_path,
            version=version,
            impact_level=(impact_level or "").title(),
        )
    except ExportFormatError as exc:
        raise click.ClickException(
            f"{exc}\n\nIf this workbook's layout is one this project has not seen, "
            "run:\n  policyforge generate-parser --framework govramp --sample "
            f"{export_path}"
        ) from exc

    click.echo(summarize(controls, rows=rows).format_report())

    if out is None:
        click.echo(
            "\nNothing written. Pass --out <path> to save a controls.json - into "
            "a repository whose licence permits holding GovRAMP content."
        )
        return

    _guard_licensed_write(
        out, force=force, product="GovRAMP matrix", licence="GovRAMP", noun="matrix"
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(out, json.dumps([dataclasses.asdict(c) for c in controls], indent=2))
    enhancements = sum(len(c.enhancements) for c in controls)
    click.echo(f"\nWrote {len(controls)} GovRAMP controls ({enhancements} enhancements) -> {out}")


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
    800-66r2's PDF - Appendix D of that document states the mapping table was
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
    write_text_lf(out_path, json.dumps([dataclasses.asdict(c) for c in controls], indent=2))

    # This step rewrites the same controls.json `etl-hipaa` just stamped, so
    # the recorded hash has to follow it. Only the hash: source_ref and
    # source_url describe where the regulation text came from, and attaching
    # a crosswalk does not change that.
    from policyforge.ingest.provenance import restamp_content

    restamped = restamp_content(out_path.parent / "framework.yaml", content=out_path.read_bytes())

    click.echo(
        f"Mapped {report.mapped_controls} standards and "
        f"{report.mapped_enhancements} implementation specifications "
        f"from {len(mapping)} CPRT citations -> {out_path}"
    )
    if restamped is not None:
        click.echo(f"Updated recorded hash to sha256:{restamped[:16]}…")
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


@cli.command("etl-fedramp")
@click.option(
    "--nist",
    "nist_path",
    default=Path("data/frameworks/nist-800-53-r5/controls.json"),
    type=click.Path(path_type=Path),
    help="The 800-53 catalog this tailoring is applied to. Produced by `policyforge etl-oscal`.",
)
@click.option(
    "--out",
    default=Path("data/frameworks/fedramp/controls.json"),
    type=click.Path(path_type=Path),
    help="Where to write the parsed control data.",
)
def etl_fedramp(nist_path: Path, out: Path):
    """Fetch FedRAMP's published control tailoring and apply it to 800-53.

    Public domain - a US federal program, same basis as the NIST and eCFR
    sources. Read from `fedramp-consolidated-rules.json` in `FedRAMP/rules`,
    which that repository calls its canonical rules dataset.

    This writes a profile, not a baseline. FedRAMP's machine-readable
    Low/Moderate/High baseline selection used to live in
    `GSA/fedramp-automation`, and that repository no longer exists - so
    nothing here says which controls a given system must implement, and
    `Control.baseline` is deliberately left unset rather than guessed. What
    it does carry is FedRAMP's own two additions to the controls it does
    speak to: the organization-defined values FedRAMP has already decided,
    and the guidance it layers on top. See ingest/fedramp.py.
    """
    import dataclasses
    import json

    from policyforge.ingest.fedramp import (
        FEDRAMP_RULES_REF,
        RULES_URL,
        fetch_fedramp_rules,
        parse_fedramp_rules,
    )
    from policyforge.ingest.provenance import record_source_provenance
    from policyforge.ingest.schema import load_controls

    if not nist_path.exists():
        raise click.ClickException(
            f"No 800-53 catalog at {nist_path}. FedRAMP publishes no control text of "
            "its own — it names controls NIST wrote and tailors them — so this "
            "command needs that catalog to join against. Run `policyforge etl-oscal` "
            "first, or point --nist at your own copy."
        )

    nist_controls = load_controls(nist_path)
    rules = fetch_fedramp_rules()
    controls, summary = parse_fedramp_rules(rules, nist_controls)

    out.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(out, json.dumps([dataclasses.asdict(c) for c in controls], indent=2))
    enhancements = sum(len(c.enhancements) for c in controls)
    click.echo(
        f"Wrote {len(controls)} controls and {enhancements} enhancements "
        f"({rules.get('info', {}).get('version', '?')}) -> {out}"
    )
    for line in summary.format_report():
        click.echo(f"  {line}")

    stamp = record_source_provenance(
        out.parent / "framework.yaml",
        source_ref=FEDRAMP_RULES_REF,
        source_url=RULES_URL,
        content=out.read_bytes(),
    )
    if stamp is not None:
        click.echo(
            f"Recorded provenance: {FEDRAMP_RULES_REF[:12]}… sha256:{stamp[:16]}… -> {out.parent}"
        )


@cli.command("etl-arc-ampe")
@click.option(
    "--export",
    "export_path",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Read a local ARC-AMPE Volume II workbook instead of fetching CMS's. "
    "Use this for the Direct Enrollment Entity baseline, which CMS distributes "
    "through zONE rather than publishing.",
)
@click.option(
    "--version",
    "version",
    default="",
    help='Document version to stamp, e.g. "v1.02". Default: the version this loader is pinned to.',
)
@click.option(
    "--nist",
    "nist_path",
    default=Path("data/frameworks/nist-800-53-r5/controls.json"),
    type=click.Path(path_type=Path),
    help="The 800-53 catalog to crosswalk against. ARC-AMPE numbers its "
    "controls with 800-53 identifiers, so each one that resolves here is "
    "anchored on its equivalent. If absent, prints a notice and carries on "
    "without a crosswalk - the catalog is usable alone, just invisible to "
    "`policyforge map`.",
)
@click.option(
    "--out",
    default=Path("data/frameworks/arc-ampe/controls.json"),
    type=click.Path(path_type=Path),
    help="Where to write the parsed control data.",
)
def etl_arc_ampe(export_path: Path | None, version: str, nist_path: Path, out: Path):
    """Fetch CMS's ARC-AMPE Volume II baseline and parse it into this schema.

    Public domain - published by CMS, a federal agency, with no copyright
    notice or redistribution restriction, same basis as the NIST and eCFR
    sources.

    Note which volume this reads. Volume I is the narrative PDF and holds no
    controls; Volume II is the System Security and Privacy Plan workbook,
    and its `AE Mandatory Baseline` sheet is the catalog - 402 controls
    required of an ACA Administering Entity, with CMS's parameter decisions
    already written into the control text. The sheet is found by its shape
    rather than its name, so the Direct Enrollment Entity workbook reads the
    same way via --export. See ingest/arc_ampe.py.
    """
    import dataclasses
    import json

    from policyforge.ingest.arc_ampe import (
        ARC_AMPE_URL,
        ARC_AMPE_VERSION,
        fetch_arc_ampe,
        load_workbook_from_bytes,
        parse_arc_ampe,
    )
    from policyforge.ingest.provenance import record_source_provenance
    from policyforge.ingest.schema import load_controls

    if export_path is not None:
        content = export_path.read_bytes()
        source_url = str(export_path)
    else:
        content = fetch_arc_ampe()
        source_url = ARC_AMPE_URL

    nist_ids: set[str] | None = None
    if nist_path.exists():
        nist_ids = set()
        for control in load_controls(nist_path):
            nist_ids.add(control.control_id)
            nist_ids.update(e.enhancement_id for e in control.enhancements)
    else:
        click.echo(
            f"No 800-53 catalog at {nist_path}, so no crosswalk is recorded. Run "
            "`policyforge etl-oscal` and re-run this to anchor ARC-AMPE on 800-53."
        )

    workbook = load_workbook_from_bytes(content)
    controls, summary = parse_arc_ampe(
        workbook, version=version or ARC_AMPE_VERSION, nist_ids=nist_ids
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(out, json.dumps([dataclasses.asdict(c) for c in controls], indent=2))
    click.echo(f"Wrote {len(controls)} controls -> {out}")
    for line in summary.format_report():
        click.echo(f"  {line}")

    stamp = record_source_provenance(
        out.parent / "framework.yaml",
        source_ref=version or ARC_AMPE_VERSION,
        source_url=source_url,
        content=out.read_bytes(),
    )
    if stamp is not None:
        click.echo(
            f"Recorded provenance: {version or ARC_AMPE_VERSION} "
            f"sha256:{stamp[:16]}… -> {out.parent}"
        )


#: Where a generated parser is written, checked and trial-run. Outside the
#: package on purpose: a file here is never imported by anything until a
#: person promotes it, and `output/` is gitignored.
_PARSER_CANDIDATE_DIR = Path("output/parsers")


#: Where a promoted parser goes, and where the candidate used to be written
#: directly — importable on the next run with nothing between the model's
#: output and the interpreter but `ast.parse`.
_PARSER_PACKAGE_DIR = Path("src/policyforge/ingest")


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
    "export). Its full content is sent to your configured LLM provider - confirm "
    "your license terms permit that before running this.",
)
@click.option(
    "--out",
    default=None,
    type=click.Path(path_type=Path),
    help="Where to write the candidate parser (default: output/parsers/<framework>_loader.py). "
    "It is checked and trial-run there, and not imported by anything until promoted.",
)
@click.option(
    "--force", is_flag=True, help="Overwrite --out, or the promoted module, if it exists."
)
@click.option(
    "--yes",
    is_flag=True,
    help="Skip the confirmation prompt before sending --sample's content to the LLM provider.",
)
@click.option(
    "--promote",
    is_flag=True,
    help="Copy the candidate into src/policyforge/ingest/ once it passes the static check "
    "and its trial run returns records. Without this it stays in output/ for review.",
)
def generate_parser_cmd(
    framework: str,
    sample_path: Path,
    out: Path | None,
    force: bool,
    yes: bool,
    promote: bool,
):
    """Generate a deterministic ETL parser for a BYOC framework export via your
    configured LLM, from a real sample export file.

    The sample is part of the prompt, so the code that comes back was written
    under the influence of a file this tool did not write - and it is about
    to run over a licensed one. So it is checked before it runs, run once
    under watch, and kept out of the package until you promote it. Nothing
    under ingest/*_loader.py calls the LLM at parse time - only this command
    does, and only when you run it.
    """
    from policyforge.ingest.parser_codegen import generate_byoc_parser
    from policyforge.ingest.parser_gate import check_generated_parser, trial_run
    from policyforge.llm.boundary import BoundaryViolation, enforce

    out_path = out or _PARSER_CANDIDATE_DIR / f"{framework}_loader.py"
    if out_path.exists() and not force:
        raise click.UsageError(f"{out_path} already exists. Pass --force to overwrite.")

    config = load_config()

    # Before the file is read, not after. This used to be a paragraph asking
    # the operator to confirm their own licence permitted sending a MyCSF
    # export to a hosted API, which put the one licence question this tool
    # can actually answer in front of the person least able to answer it at
    # 11pm. `enforce` answers it from the configuration instead.
    try:
        decision = enforce(sample_path, config)
    except BoundaryViolation as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Boundary: {decision.explain()}")
    click.echo(
        f"This sends the full contents of {sample_path} to your configured LLM "
        "provider. The boundary check above says the pairing is permitted; whether "
        "your licence permits this particular use of this particular export is "
        "still yours to confirm."
    )
    if not yes:
        click.confirm("Continue?", abort=True)

    sample_text = sample_path.read_text(encoding="utf-8", errors="replace")
    provider = get_provider(config)

    source = generate_byoc_parser(
        framework=framework,
        framework_slug=framework,
        sample_text=sample_text,
        provider=provider,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Before it runs, not after. `ast.parse` used to be the only check, and
    # it proves the output is Python rather than anything about what the
    # Python does.
    violations = check_generated_parser(source, framework_slug=framework)
    if violations:
        rejected = out_path.with_name(f"{out_path.stem}.rejected.py")
        write_text_lf(rejected, source)
        click.echo("Generated parser refused before running it:")
        for violation in violations:
            click.echo(f"  {violation}")
        click.echo(
            f"The code is at {rejected} so you can judge the refusal; it was not run "
            "and nothing imports it."
        )
        raise SystemExit(1)

    write_text_lf(out_path, source)
    click.echo(f"Wrote candidate parser -> {out_path}")

    trial = trial_run(out_path, sample_path, framework_slug=framework)
    if not trial.ok:
        click.echo(f"Trial run against {sample_path} failed: {trial.detail}")
        raise SystemExit(1)
    click.echo(f"Trial run against {sample_path}: {trial.records} record(s), nothing refused.")

    if trial.records == 0:
        click.echo(
            "A parser that returns nothing reads as a framework with no controls, and "
            "every report built on it would say there is nothing to do. Not promoting."
        )
        return

    target = _PARSER_PACKAGE_DIR / f"{framework}_loader.py"
    if not promote:
        click.echo(
            f"Read it before trusting it. Copy it to {target} once you have, or pass "
            "--promote to have this command do that step when both checks pass."
        )
        return
    if target.exists() and not force:
        raise click.UsageError(f"{target} already exists. Pass --force to replace it.")
    target.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(target, source)
    click.echo(
        f"Promoted -> {target}. Add it to your test suite and commit it like any other source file."
    )
