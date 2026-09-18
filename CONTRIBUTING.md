# Contributing

## Before you start

Run the gate once so you know it passes on a clean tree:

```bash
python scripts/check.py
```

It runs ruff (lint and format), pytest, bandit, semgrep, pip-audit and
mdformat, plus gitleaks if the binary is on your PATH.

semgrep is not in the `dev` extra. It pins its own dependencies exactly, and
installed beside the project those pins became the project's, so it has its
own hashed lock in `requirements/semgrep/` and its own environment:

```bash
python -m venv .tools/semgrep
.tools/semgrep/Scripts/pip install --require-hashes -r requirements/semgrep/semgrep.txt
```

(`bin/` rather than `Scripts/` outside Windows.) The gate finds it there or on
your PATH, and skips it with a note otherwise; CI always runs it. It exits non-zero, so
it works as a pre-push hook. `pre-commit install` wires the fast subset to
run on commit.

Python 3.12 in a project `.venv`. Dependencies come from three hashed locks,
each regenerated with the command in its own header, never edited by hand:

| Lock                               | Installed by                            | Header command                                                                                                                           |
| ---------------------------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `requirements/ci.txt`              | CI, the dev container                   | `uv pip compile pyproject.toml --extra dev --extra mcp --universal --python-version 3.12 --generate-hashes -o requirements/ci.txt`       |
| `requirements/runtime.txt`         | the container image                     | `uv pip compile pyproject.toml --extra mcp --universal --python-version 3.12 --generate-hashes -o requirements/runtime.txt`              |
| `requirements/semgrep/semgrep.txt` | CI, the dev container, `.tools/semgrep` | `uv pip compile requirements/semgrep/semgrep.in --universal --python-version 3.12 --generate-hashes -o requirements/semgrep/semgrep.txt` |

**A change to the dependencies in `pyproject.toml` means regenerating
`ci.txt` and `runtime.txt` together.** The runtime lock must pin exactly the
versions CI tests (`tests/test_container.py` checks), so regenerate `ci.txt`
first and seed `runtime.txt` from it: `cp requirements/ci.txt requirements/runtime.txt`, then run
the runtime command. uv keeps the versions already in its output file.
Dependabot's own edits to these locks are Linux-only and are regenerated the
same way rather than merged. To move semgrep, change the version in
`requirements/semgrep/semgrep.in`, regenerate `semgrep.txt`, and change the
`rev:` in `.pre-commit-config.yaml` with it.

## The one rule that is not about style

**Some behaviour in this repository is a stated commitment, not an
implementation detail.** [docs/commitments.md](docs/commitments.md) lists
eight of them, each with the test that fails when it stops being true. If
your change makes one of those tests fail, the fix is almost never to edit
the test.

Changing a commitment deliberately is allowed and is a **breaking change**:
it needs a major version bump and a `Security` entry in
[CHANGELOG.md](CHANGELOG.md) saying what changed and why.

The paths where this bites most often:

| If you touch                                                   | Read first                                                                      |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `llm/boundary.py`, `llm/channel.py`                            | What may be sent where, and why it raises rather than warns                     |
| `llm/ledger.py`                                                | It records metadata and never content, on purpose                               |
| `llm/fence.py`, anything building a prompt from retrieved text | The fence is measured; changing it changes a security property                  |
| `ingest/parser_gate.py`                                        | Gating of model-written code                                                    |
| `ingest/byoc_loader.py` and the framework loaders              | Licensed content is read, never written to a public path                        |
| `export/publisher.py`, `export/publish.py`, `export/pull.py`   | Dry run is the default; a moved page is not overwritten; the guards are generic |
| Anything adding a URL or an env read                           | `tests/test_no_undeclared_endpoints.py`, `tests/test_credential_containment.py` |

## Adding a CLI command

Commands live in `src/policyforge/cli/`, one module per area. A command
module must import `load_config` and `get_provider` from
`policyforge.cli._common`, **never directly** — `tests/test_cli_seam.py`
enforces this over the AST. The test suite patches those names on
`policyforge.cli`, and a direct import in a submodule puts the command out
of the patch's reach: a test that believes it holds a fake provider would
build a real one, and could make real, billed calls.

## Adding an outbound endpoint

Adding a host to `ALLOWED_HOSTS` in
[`tests/test_no_undeclared_endpoints.py`](tests/test_no_undeclared_endpoints.py)
is a deliberate act, which is the point. Say in the PR what the endpoint is,
what is sent to it, and whether any of it is the operator's content. If it
receives content rather than serving public catalog data, it also needs a
row in [docs/subprocessors.md](docs/subprocessors.md).

## Reading an environment variable

Declare it in `DECLARED_ENV_READERS` in
[`tests/test_credential_containment.py`](tests/test_credential_containment.py)
with what it reads and why. **Never read one in a module that defines prompt
text** — the test refuses it, and the reason is that the accident this
prevents is an env value landing in an f-string three lines from a prompt
constant.

If it is a new *credential*, it also belongs in `_CREDENTIALS` in
`tests/conftest.py`, so the suite cannot reach a paid endpoint with it.

## Prompts

Prompt text is registered in [`llm/prompts.py`](src/policyforge/llm/prompts.py)
so a measured run can say which text produced it. Changing a prompt changes
what [MEASUREMENTS.md](MEASUREMENTS.md) is comparable with — bump the
prompt's `version` and open a new epoch rather than editing numbers recorded
under the old text.

Note for anyone writing tooling over prompts: they are bound as
`SYSTEM_PROMPT = register(...)`, an `ast.Call`, not a bare string constant.
Anything matching on the assignment shape must look *underneath* the assigned
value or it will silently miss them.

## Tests

Match the house style: the module docstring says **why the test exists and
what failure it prevents**, not what it asserts. Where a rule is currently
prose in a docstring, prefer moving it into a test — several of the checks
here exist because prose was the wrong form for a rule.

**No test may touch the network.** This is a rule, not an enforced
property — there is no socket guard. What backs it is `conftest.py`
stripping every credential that could reach a provider (and disarming
dotenv's loader, so a dependency cannot put one back), which makes an
accidental paid call fail rather than succeed quietly. Hitting an
unauthenticated endpoint would still work, so this one is on the author.

## Running evals

Evals call a real model and cost real money, so they are not part of
`scripts/check.py`. Two things about running them honestly:

- **Run from a worktree pinned to a commit.** A suite started before a merge
  imports modules at process start, so it can finish having measured code
  that no longer exists, and nothing in the result would say so. The eval
  report prints the commit it ran from and whether the tree was dirty —
  a dirty tree means the number is not attributable to anything.
- **In a worktree, put its `src/` first on the path.** The editable install
  pins the checkout it was made from, so any interpreter from the
  virtualenv imports *that* checkout's `policyforge` — a gate or a bare
  `pytest` run in a worktree would report on code it never loaded.
  `scripts/check.py` and `pytest` both refuse to start when the package
  they resolve is not under the tree they were run from, and print the
  `PYTHONPATH=<tree>/src` invocation that fixes it (`scripts/tree_guard.py`).
- **A number without an epoch is not comparable and is worse than no
  number.** If you changed a prompt, open a new epoch in
  [MEASUREMENTS.md](MEASUREMENTS.md) rather than filing results under the
  old text. Prompt fingerprints will tell you when this has happened.

Record the runs that got worse. Several entries in MEASUREMENTS.md are
changes that were measured, found harmful, and reverted — that is the file
working, not a blemish on it.

**A change to what the harness sends is checked with a capture, not a
run.** Two runs at the same score can differ in what they asked for — the
harness once sent an effort level production did not, for five epochs, and
no pass rate could show it. `scripts/capture_eval_requests.py` replaces
`litellm.completion` with a recorder and runs the harness for real, so it
costs nothing and reaches no vendor; the recorded keyword arguments are the
request. Capture on `main`, capture on the branch, compare:

```bash
python scripts/capture_eval_requests.py before.json --model openrouter/deepseek/deepseek-v4-flash --suite routing --limit 2 --repeat 1
# switch to the branch
python scripts/capture_eval_requests.py after.json --model openrouter/deepseek/deepseek-v4-flash --suite routing --limit 2 --repeat 1
python scripts/capture_eval_requests.py --compare before.json after.json
```

Identical means the numbers in MEASUREMENTS.md stay comparable. A
difference is either the point of the change, in which case the pull
request says so and a new epoch follows, or a finding. Do this for any
change under `evals/`, `scripts/eval_zardoz.py`, `llm/`, or a prompt's
call site. The capture stands in for `litellm.completion` and nothing
else, so it sees only LiteLLM-backed runs — the `--model` path, which is
what MEASUREMENTS.md was measured with. A change to the Anthropic,
Vertex, Bedrock or OpenAI-compatible providers is not covered by it;
say in the pull request how that request shape was checked instead.

## Regenerating a catalog

Know the build steps before re-running an `etl-*` command. **The HIPAA
catalog is built by two commands in order** — `etl-hipaa` fetches the
regulation, then `etl-hipaa-crosswalk` attaches NIST's CPRT mappings to the
same file. Running the first alone returns a complete-looking catalog with
its mappings emptied, and HIPAA-to-NIST mapping silently stops working.
Stage to a scratch path and diff before touching the committed file.

## Changes a Windows gate cannot check

CI runs every check on Linux with Python 3.12, and the test suite alone on
Windows and macOS (3.12) as well. `scripts/check.py` on a Windows machine
still passes some things that fail on Linux. CI was red on this branch from
its first push for two such reasons: provenance stamps were hashed from
catalogs with Windows line endings, and a help-text fixture relied on the
docstring dedenting Python 3.13 does and 3.12 does not.

A third reached main with CI green: mcp 2.0 broke `policyforge mcp` on
startup, and no test started the server.

So if you **restamp a catalog, regenerate a fixture or a lock, touch a
Dockerfile, or move a dependency**, run CI's checks on Linux 3.12 before
pushing:

```bash
python scripts/ci_in_docker.py
```

It needs Docker and nothing else installed. It clones your committed HEAD
into a container, so uncommitted changes are listed and left out, and runs
CI's steps in CI's order. Then it runs what CI does not check yet: every lock
must reproduce from its header command, the runtime lock must pin what CI
tests, and `policyforge mcp` must answer a real client. Last, it builds the
runtime image from a clean export with private files planted in it (a
licensed catalog, a `.env`, an org config), checks that none reached the
build context or the image, and runs the same MCP client against the server inside it.
`--no-image` skips that last part.

### Working in the dev container

Opening the repository in VS Code with the Dev Containers extension ("Reopen
in Container") gives the environment CI runs in. Linux and Python 3.12,
dependencies from the hashed locks, semgrep in its own environment on PATH,
and `python scripts/check.py` running every check with nothing skipped but
gitleaks. The environments live in `/opt`, outside the workspace, so your
host's `.venv` is not touched. A Windows checkout works as it is: the
container has been run against one with CRLF line endings.

## Documentation

Markdown is a real deliverable here, not a nicety. `mdformat` runs in CI over
every tracked `*.md`. If you change behaviour described in [docs/](docs/),
change the doc in the same PR — the docs claim to be checkable, and a claim
pointing at code that moved is worse than no claim.

## Adding a package or a catalog

`pyproject.toml` lists packages and bundled files by hand, because the
catalogs are mapped into the package from `data/frameworks/`, outside `src/`.
A new subpackage goes into `[tool.setuptools] packages`. A new
**public-domain** catalog goes into `policyforge.scaffold.BUNDLED_CATALOGS`
and into the package-data list file by file. Never add a glob there.
`tests/test_scaffold.py` fails until both lists agree with the repository.

The sdist is a build input, not a test distribution: `MANIFEST.in` prunes
`tests/`, because setuptools would otherwise ship the test modules without
their fixtures. Run the suite from a clone. Don't add `tests/` back to it.

## Cutting a release

1. Move the `## Unreleased` changelog entries under the new version. Bump
   `version` in `pyproject.toml` and `__version__` in
   `src/policyforge/__init__.py` together; a test compares them.
1. Merge that to `main`, then tag the merge commit `vX.Y.Z` and publish a
   GitHub Release from the tag.
1. Update `Formula/policyforge.rb` in
   [rdazzlebot/homebrew-tap](https://github.com/rdazzlebot/homebrew-tap):
   point `url` at
   `https://github.com/rdazzlebot/policyforge/archive/refs/tags/vX.Y.Z.tar.gz`
   and set `sha256` to that tarball's hash (`curl -sL <url> | shasum -a 256`).
   If a runtime dependency changed, regenerate the `resource` blocks with
   `brew update-python-resources policyforge`, not by hand.
1. Before pushing the formula, run `brew install --build-from-source`,
   `brew test policyforge` and `brew audit --strict policyforge` on macOS or
   Linux. None of these run on Windows; the `homebrew/brew` Docker image has
   Linux Homebrew.

## Licensed content

Never commit HITRUST CSF, GovRAMP, or any licensed export. Keep it in
`local_content/` (gitignored). `allow_licensed_in_repo` stays `false` unless
your own licence permits otherwise, and that is your decision to make in your
own fork, not one to change here.

Never commit organization-specific content: `config/config.yaml`,
`config/topics.yaml`, anything under `output/`.

## Security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).
