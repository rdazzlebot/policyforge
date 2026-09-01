"""Where framework content lives, and who is allowed to hold a copy of it.

Some of the catalogs this project maps between are public-domain government
works and some are licensed. That is not a detail of packaging — it decides
which repository a file may sit in, and getting it wrong is a licence
breach rather than a bug.

The arrangement this supports has two repositories with different rights:

* **This one** is open, Apache-licensed, and may hold only content anyone
  may redistribute: NIST 800-53, FedRAMP, ARC-AMPE, the HIPAA Security Rule.
  A HITRUST CSF export must never be committed here, and `local_content/` is
  gitignored precisely so an accidental copy cannot be.
* **The organization's own repository** — private, holding its `docs/` tree,
  its `topics.yaml`, its config — very often *may* hold that same HITRUST
  export, because its own MyCSF licence permits internal use. Telling that
  organization to keep its licensed catalog outside its own private repo,
  when the licence allows it, is a restriction this project has no standing
  to impose and which makes CI harder for no benefit.

So the rule cannot be "licensed content never goes in a repo". It has to be
"licensed content never goes in a repo that has not said it may hold it",
and that is a decision only the repository owner can make. They make it once,
in config:

    frameworks:
      allow_licensed_in_repo: true    # our MyCSF licence permits this

This project's own config does not set it, so `policyforge check` fails here
the moment licensed content is committed — while the same command passes in
a repository whose owner has declared the right. The mechanism is a declared
permission rather than a path convention, because a path convention is a
thing you can forget and a failing check is not.

**What is not decided here.** Whether a *generated document* citing
`[HITRUST 01.c]` may be redistributed is a question about identifiers,
paraphrase and fair use that depends on the licence and the jurisdiction,
and this tool has no business answering it. What it can do is tell you which
of your documents drew on licensed material — see `derived_from` — so the
question is asked about the right files by someone qualified to answer it.
"""

from __future__ import annotations

# Used for exactly one thing: asking git whether a path is tracked.
import subprocess  # nosec B404
from dataclasses import dataclass, field
from pathlib import Path

#: Filename declaring what a framework directory holds and under what terms.
MANIFEST_NAME = "framework.yaml"

#: Searched in order when config names none. `data/frameworks` is what ships
#: with this project; `frameworks/` is where a consuming repository would
#: naturally put its own, next to its `docs/`.
DEFAULT_SEARCH_PATHS = ("data/frameworks", "frameworks", "local_content")

PUBLIC_DOMAIN = "public-domain"
LICENSED = "licensed"


@dataclass
class Framework:
    """One catalog on disk, and the terms it came with."""

    id: str
    path: Path
    name: str = ""
    version: str = ""
    #: `public-domain` or `licensed`. Anything a manifest does not declare is
    #: treated as licensed: assuming content is freely redistributable
    #: because nobody said otherwise is the failure mode with consequences.
    licence: str = LICENSED
    source: str = ""
    notes: str = ""
    #: True when a manifest was found. Without one there is nothing to go on
    #: but the directory's location, so the framework is reported as
    #: undeclared rather than assumed safe.
    declared: bool = False

    @property
    def redistributable(self) -> bool:
        return self.licence == PUBLIC_DOMAIN

    @property
    def controls_path(self) -> Path:
        return self.path / "controls.json"

    @property
    def has_controls(self) -> bool:
        return self.controls_path.exists()


def _read_manifest(directory: Path) -> dict:
    import yaml

    manifest = directory / MANIFEST_NAME
    if not manifest.exists():
        return {}
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def load_framework(directory: Path) -> Framework:
    """Read one framework directory, declared or not."""
    data = _read_manifest(directory)
    licence = str(data.get("licence") or data.get("license") or "").strip().lower()
    return Framework(
        id=str(data.get("id") or directory.name),
        path=directory,
        name=str(data.get("name") or directory.name),
        version=str(data.get("version") or ""),
        licence=PUBLIC_DOMAIN if licence == PUBLIC_DOMAIN else LICENSED,
        source=str(data.get("source") or ""),
        notes=str(data.get("notes") or ""),
        declared=bool(data),
    )


def frameworks_config(config: dict | None = None) -> dict:
    """Normalize the `frameworks:` block, which has had two shapes.

    The first shape was a list of `{id, source, path}` entries. It was
    documented for a long time and read by nothing, so config files in the
    wild contain it — and a version that crashed on them would break every
    existing install at once. The paths it names are carried over as search
    roots, which is the only part of it that was ever actionable.

    `allow_licensed_in_repo` did not exist in that shape, so it stays off.
    Defaulting a permission to on because an old config could not express it
    is exactly backwards.
    """
    raw = (config or {}).get("frameworks")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        extra: list[str] = []
        for entry in raw:
            if isinstance(entry, dict) and entry.get("path"):
                parent = str(Path(str(entry["path"])).parent)
                if parent and parent not in extra:
                    extra.append(parent)
        return {"search_paths": [*DEFAULT_SEARCH_PATHS, *extra]} if extra else {}
    return {}


def search_paths(config: dict | None = None) -> list[Path]:
    configured = frameworks_config(config).get("search_paths")
    if isinstance(configured, list) and configured:
        return [Path(str(entry)) for entry in configured]
    return [Path(entry) for entry in DEFAULT_SEARCH_PATHS]


def discover(config: dict | None = None, *, roots: list[Path] | None = None) -> list[Framework]:
    """Every framework directory found under the search paths.

    A directory counts if it holds a `controls.json` or a manifest — the two
    things that make it a framework rather than somewhere a framework will
    eventually go.
    """
    found: dict[str, Framework] = {}
    for root in roots if roots is not None else search_paths(config):
        if not root.exists():
            continue
        for directory in sorted(p for p in root.iterdir() if p.is_dir()):
            if (
                not (directory / "controls.json").exists()
                and not (directory / MANIFEST_NAME).exists()
            ):
                continue
            framework = load_framework(directory)
            # First search path wins, so a repository can shadow a bundled
            # catalog with its own newer export without deleting anything.
            found.setdefault(framework.id, framework)
    return list(found.values())


def is_tracked(path: Path) -> bool | None:
    """Whether git tracks anything under `path`.

    Tracked is the precise question, not "is it gitignored": a file can be
    absent from .gitignore and still untracked, and only a tracked file gets
    pushed. Returns None when git cannot answer — no repository, no git
    binary — so a caller can say "unknown" instead of implying safety.
    """
    try:
        # Fixed argv and no shell; the only variable part is a path the
        # caller already has. `git` resolves from PATH on purpose, since
        # pinning an absolute path would break every platform but one.
        result = subprocess.run(  # nosec B603 B607
            ["git", "ls-files", "--", str(path)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


@dataclass
class LicenceFinding:
    framework: Framework
    message: str
    severity: str = "error"


@dataclass
class LicenceReport:
    frameworks: list[Framework] = field(default_factory=list)
    findings: list[LicenceFinding] = field(default_factory=list)
    allowed: bool = False

    @property
    def errors(self) -> list[LicenceFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def format_report(self) -> str:
        lines = [f"{len(self.frameworks)} framework(s):"]
        width = max((len(f.id) for f in self.frameworks), default=0)
        for framework in self.frameworks:
            terms = "public domain" if framework.redistributable else "LICENSED"
            declared = "" if framework.declared else "  (undeclared)"
            lines.append(f"  {framework.id.ljust(width)}  {terms}{declared}  {framework.path}")

        if self.findings:
            lines.append("")
            for finding in self.findings:
                mark = "ERROR" if finding.severity == "error" else "warn "
                lines.append(f"  {mark}  {finding.framework.id}: {finding.message}")
        return "\n".join(lines)


def check_licences(config: dict | None = None, *, roots: list[Path] | None = None) -> LicenceReport:
    """Verify no licensed catalog is committed without the right to hold it."""
    allowed = bool(frameworks_config(config).get("allow_licensed_in_repo"))
    frameworks = discover(config, roots=roots)
    report = LicenceReport(frameworks=frameworks, allowed=allowed)

    for framework in frameworks:
        if framework.redistributable:
            continue

        tracked = is_tracked(framework.path)
        if tracked and not allowed:
            report.findings.append(
                LicenceFinding(
                    framework,
                    f"licensed content at {framework.path} is committed to this "
                    "repository, which has not declared the right to hold it. Either "
                    "remove it and keep it untracked, or set "
                    "`frameworks.allow_licensed_in_repo: true` if your licence "
                    "permits your repository to carry it.",
                )
            )
        elif tracked is None:
            report.findings.append(
                LicenceFinding(
                    framework,
                    "could not ask git whether this is committed, so its licence "
                    "position is unverified here.",
                    severity="warning",
                )
            )
        if not framework.declared:
            report.findings.append(
                LicenceFinding(
                    framework,
                    f"has no {MANIFEST_NAME}, so it is treated as licensed. Add one "
                    "declaring its terms.",
                    severity="warning",
                )
            )

    return report


def derived_from(controls_paths: list[Path], config: dict | None = None) -> list[Framework]:
    """Which discovered frameworks a set of `--controls` inputs came from.

    The question worth asking about a generated document is not whether the
    tool is careful but whether *this file* drew on licensed material. This
    answers it for the inputs of a run, so the redistribution question gets
    asked about the right documents.
    """
    resolved = {path.resolve() for path in controls_paths}
    return [
        framework for framework in discover(config) if framework.controls_path.resolve() in resolved
    ]
