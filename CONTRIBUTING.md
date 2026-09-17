# Contributing

## Before you start

Run the gate once so you know it passes on a clean tree:

```bash
python scripts/check.py
```

It runs ruff (lint and format), pytest, bandit, semgrep, pip-audit and
mdformat, plus gitleaks if the binary is on your PATH. It exits non-zero, so
it works as a pre-push hook. `pre-commit install` wires the fast subset to
run on commit.

Python 3.12 in a project `.venv`. Dependencies for CI come from a hashed
lock (`requirements/ci.txt`); if you add a dependency, regenerate it with the
command in that file's header rather than editing it by hand.

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
| `export/publish.py`, `export/pull.py`                          | Dry run is the default; a moved page is not overwritten                         |
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
- **A number without an epoch is not comparable and is worse than no
  number.** If you changed a prompt, open a new epoch in
  [MEASUREMENTS.md](MEASUREMENTS.md) rather than filing results under the
  old text. Prompt fingerprints will tell you when this has happened.

Record the runs that got worse. Several entries in MEASUREMENTS.md are
changes that were measured, found harmful, and reverted — that is the file
working, not a blemish on it.

## Regenerating a catalog

Know the build steps before re-running an `etl-*` command. **The HIPAA
catalog is built by two commands in order** — `etl-hipaa` fetches the
regulation, then `etl-hipaa-crosswalk` attaches NIST's CPRT mappings to the
same file. Running the first alone returns a complete-looking catalog with
its mappings emptied, and HIPAA-to-NIST mapping silently stops working.
Stage to a scratch path and diff before touching the committed file.

## Changes a Windows gate cannot check

CI runs on Linux with Python 3.12, and `scripts/check.py` on a Windows
machine passes some things that fail there. CI was red on this branch from
its first push for two such reasons: provenance stamps were hashed from
catalogs with Windows line endings, and a help-text fixture relied on the
docstring dedenting Python 3.13 does and 3.12 does not.

So if you **restamp a catalog or regenerate a fixture**, run the tests on
Linux 3.12 before pushing. For example:

```bash
docker run --rm -v "$PWD":/src -w /src python:3.12-slim sh -c "\
  apt-get update -qq >/dev/null && apt-get install -y -qq git >/dev/null && \
  pip install -q --root-user-action=ignore --require-hashes -r requirements/ci.txt && \
  pip install -q --root-user-action=ignore --no-deps -e . && \
  pytest -q -p no:cacheprovider"
```

`git` is installed first because the slim image has none, and the content-tree
edit tests shell out to it. Without it, eight tests fail for a reason CI's
runner does not share. On Git Bash for Windows, prefix the command with
`MSYS_NO_PATHCONV=1` so `/src` is not rewritten into a Windows path.

## Documentation

Markdown is a real deliverable here, not a nicety. `mdformat` runs in CI over
every tracked `*.md`. If you change behaviour described in [docs/](docs/),
change the doc in the same PR — the docs claim to be checkable, and a claim
pointing at code that moved is worse than no claim.

## Licensed content

Never commit HITRUST CSF, GovRAMP, or any licensed export. Keep it in
`local_content/` (gitignored). `allow_licensed_in_repo` stays `false` unless
your own licence permits otherwise, and that is your decision to make in your
own fork, not one to change here.

Never commit organization-specific content: `config/config.yaml`,
`config/topics.yaml`, anything under `output/`.

## Security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).
