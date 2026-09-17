"""An organization's own crosswalk: seed it, check it, propose and review changes."""

from __future__ import annotations

import re
from pathlib import Path

import click

from policyforge.cli import cli
from policyforge.cli._common import get_provider, load_config_or_empty

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
            f"  {len(overlay.requirements)} requirements, {check.proposed} pair(s) needing review"
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


def _overlay_path(framework: str, overlay: Path | None) -> Path:
    from policyforge.crosswalk.overlay import DEFAULT_OVERLAY_DIR

    return overlay or DEFAULT_OVERLAY_DIR / f"{_framework_slug(framework)}.yaml"


def _open_overlay(path: Path, framework: str, controls):
    from policyforge.crosswalk.overlay import OverlayError, load_overlay, seed_overlay

    try:
        if path.exists():
            overlay = load_overlay(path)
            if overlay.framework.casefold() != framework.casefold():
                raise click.ClickException(
                    f"{path} maps {overlay.framework!r}, not {framework!r}. Pass --overlay."
                )
            return overlay
        overlay = seed_overlay(controls, framework)
    except OverlayError as exc:
        raise click.ClickException(str(exc)) from exc
    overlay.path = path
    return overlay


def _save(overlay) -> None:
    from policyforge.crosswalk.overlay import dump_overlay

    overlay.path.parent.mkdir(parents=True, exist_ok=True)
    overlay.path.write_text(dump_overlay(overlay), encoding="utf-8")


@crosswalk_group.command("propose")
@click.option("--framework", default="HIPAA Security Rule", show_default=True)
@_controls_option
@click.option(
    "--overlay",
    type=click.Path(path_type=Path),
    default=None,
    help="The overlay to record proposals in (default: config/crosswalks/<framework>.yaml; "
    "seeded from the published mapping when it does not exist).",
)
@click.option("--only", multiple=True, help="Propose for this requirement id only. Repeatable.")
def crosswalk_propose(framework: str, controls_paths, overlay: Path | None, only):
    """Ask the configured model to read each requirement against 800-53.

    One call per requirement. Nothing it says is a decision: a published
    pair it confirms gains the quotes that justify it, one it could not
    justify is flagged but stays accepted, and a pair it adds is proposed.
    Run `policyforge crosswalk review` to decide them.
    """
    from policyforge.cli.documents import _enforce_catalogs, _most_restrictive
    from policyforge.crosswalk.candidates import WordIndex, catalog_entries
    from policyforge.crosswalk.overlay import published_pairs
    from policyforge.crosswalk.propose import MergeReport, merge, propose_for, requirements_of
    from policyforge.llm import ledger

    config = load_config_or_empty()
    # Catalog text is sent to the provider, so a catalog that may not leave is
    # refused here exactly as `synthesize` refuses it.
    classified = _enforce_catalogs(controls_paths, config)
    controls = _published_catalogs(controls_paths)
    requirements = requirements_of(controls, framework)
    if only:
        wanted = set(only)
        requirements = [r for r in requirements if r.requirement_id in wanted]
        missing = wanted - {r.requirement_id for r in requirements}
        if missing:
            raise click.UsageError(f"Not {framework} requirements: {', '.join(sorted(missing))}")
    if not requirements:
        raise click.UsageError(f"No {framework} requirements in the loaded catalogs.")
    entries = catalog_entries(controls)
    if not entries:
        raise click.UsageError("No 800-53 catalog among --controls to map onto.")

    provider = get_provider(config)
    if not getattr(provider, "supports_schema", lambda: False)():
        raise click.ClickException(
            "The configured provider cannot hold a reply to a schema, and a mapping read "
            "out of free prose is not one to put in front of a reviewer."
        )
    model = str((config.get("llm") or {}).get("model") or getattr(provider, "model", "unknown"))

    path = _overlay_path(framework, overlay)
    record = _open_overlay(path, framework, controls)
    published = published_pairs(controls, framework)
    index = WordIndex(entries)
    total = MergeReport()

    with ledger.about(
        f"crosswalk/{_framework_slug(framework)}",
        site="crosswalk-propose",
        content_class=_most_restrictive(classified),
    ):
        for number, requirement in enumerate(requirements, start=1):
            proposal = propose_for(
                requirement,
                framework=framework,
                published=published.get(requirement.requirement_id, []),
                entries=entries,
                index=index,
                provider=provider,
            )
            step = merge(record, [proposal], controls, model=model)
            # Written after every requirement, so an interrupted run keeps what
            # it paid for.
            _save(record)
            total.confirmed += step.confirmed
            total.not_confirmed += step.not_confirmed
            total.proposed += step.proposed
            total.left_reviewed += step.left_reviewed
            total.rejected_again += step.rejected_again
            total.errors.extend(step.errors)
            if proposal.error:
                outcome = f"error: {proposal.error}"
            else:
                outcome = (
                    f"{step.confirmed} confirmed, {step.not_confirmed} not confirmed, "
                    f"{step.proposed} new"
                )
                if proposal.refused:
                    outcome += f", {len(proposal.refused)} refused for unverifiable quotes"
            click.echo(f"[{number}/{len(requirements)}] {requirement.requirement_id}: {outcome}")

    click.echo(
        f"\n{total.confirmed} published pair(s) confirmed with quotes, {total.not_confirmed} "
        f"flagged as not confirmed, {total.proposed} new pair(s) proposed -> {path}"
    )
    if total.left_reviewed:
        click.echo(f"{total.left_reviewed} reviewed row(s) left unchanged.")
    if total.errors:
        click.echo(f"{len(total.errors)} requirement(s) failed and were left as they were:")
        for line in total.errors:
            click.echo(f"  {line}")
    click.echo("Nothing reaches the pipeline until reviewed: policyforge crosswalk review")


def _reviewer() -> str:
    import getpass
    import subprocess  # nosec B404 - asks git for the configured name, nothing else

    try:
        name = subprocess.run(  # nosec B603 B607
            ["git", "config", "user.name"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        name = ""
    return name or getpass.getuser()


@crosswalk_group.command("review")
@click.option("--framework", default="HIPAA Security Rule", show_default=True)
@_controls_option
@click.option("--overlay", type=click.Path(path_type=Path), default=None)
@click.option("--who", default=None, help="Recorded as the reviewer (default: git user.name).")
def crosswalk_review(framework: str, controls_paths, overlay: Path | None, who: str | None):
    """Decide, one at a time, each pair a model flagged or proposed.

    Flagged published pairs come first — the ones a model could not find a
    basis for — then new proposals. Each decision is written as it is made,
    with who made it and when. Accept keeps or adds the pair; reject removes
    it from everything built on this crosswalk.
    """
    from datetime import date

    from policyforge.crosswalk.candidates import catalog_entries
    from policyforge.crosswalk.overlay import ACCEPTED, REJECTED
    from policyforge.crosswalk.propose import requirements_of

    path = _overlay_path(framework, overlay)
    if not path.exists():
        raise click.ClickException(
            f"No overlay at {path}. Run `policyforge crosswalk propose` first."
        )
    controls = _published_catalogs(controls_paths)
    record = _open_overlay(path, framework, controls)
    entries = catalog_entries(controls)
    requirements = {r.requirement_id: r for r in requirements_of(controls, framework)}

    queue = [
        (rid, row) for rid, rows in record.requirements.items() for row in rows if row.needs_review
    ]
    queue.sort(key=lambda item: (not item[1].flags, item[0]))
    if not queue:
        click.echo(f"Nothing in {path} needs review.")
        return

    reviewer = who or _reviewer()
    decided = 0
    for position, (rid, row) in enumerate(queue, start=1):
        requirement = requirements.get(rid)
        entry = entries.get(row.control)
        click.echo(f"\n[{position}/{len(queue)}] {rid} -> {row.control}   ({row.status})")
        if requirement is not None:
            if requirement.parent:
                click.echo(f"  under: {requirement.parent[:160]}")
            click.echo(f"  requirement: {requirement.title} — {requirement.text[:300]}")
        if entry is not None:
            click.echo(f"  control: {entry.title} — {entry.text[:300]}")
        click.echo(f"  published: {'yes' if 'published' in row.sources else 'no'}")
        if row.flags:
            click.echo(f"  flags: {', '.join(row.flags)}")
        if row.evidence:
            click.echo(f"  relationship: {row.relationship}")
            click.echo(f'  requirement says: "{row.evidence.get("requirement", "")}"')
            click.echo(f'  control says:     "{row.evidence.get("control", "")}"')
        choice = click.prompt(
            "  [a]ccept, [r]eject, [s]kip, [q]uit",
            type=click.Choice(["a", "r", "s", "q"]),
            show_choices=False,
        )
        if choice == "q":
            break
        if choice == "s":
            continue
        why = click.prompt("  why (optional)", default="", show_default=False)
        row.status = ACCEPTED if choice == "a" else REJECTED
        row.flags = []
        if why:
            row.rationale = why
        row.reviewed_by = {"who": reviewer, "date": date.today().isoformat()}
        _save(record)
        decided += 1

    remaining = sum(1 for rows in record.requirements.values() for r in rows if r.needs_review)
    click.echo(f"\n{decided} decision(s) recorded in {path}; {remaining} still need review.")
