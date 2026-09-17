"""An organization's own crosswalk: seed it, check it, propose and review changes."""

from __future__ import annotations

import re
from pathlib import Path

import click

from policyforge.cli import cli

_DEFAULT_CONTROLS = (
    Path("data/frameworks/nist-800-53-r5/controls.json"),
    Path("data/frameworks/hipaa-security-rule/controls.json"),
)


def _published_catalogs(paths) -> list:
    """The catalogs as published, with no overlay applied.

    Seeding and checking compare an overlay against what the catalog itself
    says, so they must not read through the overlay they are about.
    """
    from policyforge.ingest.schema import load_controls

    controls: list = []
    for path in paths:
        controls.extend(load_controls(path))
    return controls


def _framework_slug(framework: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", framework.lower()).strip("-")


_controls_option = click.option(
    "--controls",
    "controls_paths",
    multiple=True,
    default=_DEFAULT_CONTROLS,
    type=click.Path(exists=True, path_type=Path),
    help="A controls.json. Repeatable; pass the 800-53 catalog and the mapped framework's.",
)


@cli.group("crosswalk")
def crosswalk_group():
    """Your organization's reviewed mapping of a framework onto 800-53.

    Published crosswalks are pairs with no stated relationship or reasoning.
    An overlay in config/crosswalks/ records which pairs your organization
    accepts, rejects or has added, and only accepted pairs reach `map`,
    `synthesize`, `coverage`, `bundle` and Zardoz.
    """


@crosswalk_group.command("seed")
@click.option(
    "--framework",
    default="HIPAA Security Rule",
    show_default=True,
    help="The framework to map, as its catalog names it.",
)
@_controls_option
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Where to write the overlay (default: config/crosswalks/<framework>.yaml).",
)
@click.option("--force", is_flag=True, help="Overwrite an existing overlay.")
def crosswalk_seed(framework: str, controls_paths, out: Path | None, force: bool):
    """Write an overlay holding the published mapping, every pair accepted.

    Changes nothing on its own — the pipeline reads the same pairs it did
    before. It is the file you then review: reject a pair by changing its
    status, add one with a new row, and record why.
    """
    from policyforge.crosswalk.overlay import (
        DEFAULT_OVERLAY_DIR,
        OverlayError,
        dump_overlay,
        seed_overlay,
    )

    out = out or DEFAULT_OVERLAY_DIR / f"{_framework_slug(framework)}.yaml"
    if out.exists() and not force:
        raise click.ClickException(
            f"{out} already exists, and it may hold decisions somebody made. "
            "Pass --force to replace it with the published mapping."
        )
    try:
        overlay = seed_overlay(_published_catalogs(controls_paths), framework)
    except OverlayError as exc:
        raise click.ClickException(str(exc)) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dump_overlay(overlay), encoding="utf-8")
    pairs = sum(len(rows) for rows in overlay.requirements.values())
    unmapped = sum(1 for rows in overlay.requirements.values() if not rows)
    click.echo(
        f"Wrote {len(overlay.requirements)} {framework} requirements ({pairs} published "
        f"pairs, {unmapped} with none) -> {out}"
    )


@crosswalk_group.command("check")
@_controls_option
@click.option(
    "--overlays",
    "overlay_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory of overlays (default: config/crosswalks).",
)
@click.option("--strict", is_flag=True, help="Exit non-zero when anything needs attention.")
def crosswalk_check(controls_paths, overlay_dir: Path | None, strict: bool):
    """Report what in each overlay no longer matches the catalogs."""
    from policyforge.crosswalk.overlay import (
        DEFAULT_OVERLAY_DIR,
        OverlayError,
        check_overlay,
        load_overlays,
    )

    try:
        overlays = load_overlays(overlay_dir or DEFAULT_OVERLAY_DIR)
    except OverlayError as exc:
        raise click.ClickException(str(exc)) from exc
    if not overlays:
        click.echo(
            f"No overlays in {overlay_dir or DEFAULT_OVERLAY_DIR}. Every framework uses its "
            "published mapping. Start one with `policyforge crosswalk seed`."
        )
        return

    controls = _published_catalogs(controls_paths)
    attention = False
    for overlay in overlays:
        check = check_overlay(overlay, controls)
        click.echo(f"{overlay.path}: {overlay.framework}")
        click.echo(
            f"  {len(overlay.requirements)} requirements, {check.proposed} pair(s) awaiting review"
        )
        for rid in check.unknown_requirements:
            click.echo(
                f"  unknown requirement: {rid} — not in the loaded {overlay.framework} catalog"
            )
        for rid, control in check.unknown_controls:
            click.echo(f"  unknown control: {rid} -> {control} — not in the loaded catalogs")
        for rid, control in check.unreviewed_published:
            click.echo(
                f"  unreviewed: {rid} -> {control} is published but the overlay neither "
                "accepts nor rejects it"
            )
        if check.is_clean:
            click.echo("  matches the catalogs")
        attention = attention or not check.is_clean
    if strict and attention:
        raise SystemExit(1)
