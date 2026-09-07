"""The licensing boundary around bring-your-own-content.

`byoc_loader` reads framework content its user is licensed for and this
repository is not — HITRUST CSF, GovRAMP, anything without redistribution
rights. Its docstring states the rule plainly: read BYOC in, never write
BYOC to a bundled or public path. Until now that rule existed only as
prose, in a module whose two functions are stubs waiting to be filled in
against a real export.

Prose is the wrong form for it. The moment somebody implements
`load_hitrust_export` against their own MyCSF file, the tempting shortcut
is to cache the parsed controls next to the public ones in
`data/frameworks/` — where they would be committed, pushed, and
redistributed without the license that allows it. That is not a bug that
shows up in a test run; it shows up in somebody's inbox.

Checked over the parsed AST rather than as a substring, so the module stays
free to *discuss* the boundary in its docstring — which it must, since the
reason it does not write is the whole point.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import policyforge.ingest.byoc_loader as byoc

SOURCE = Path(byoc.__file__)


def _tree():
    return ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))


def test_the_loader_never_writes_anything():
    """No file is opened for writing, and no write helper is reached.

    `Path.write_text`, `open(..., "w")`, `shutil.copy` and friends all
    surface as an attribute or a name in the tree.
    """
    forbidden = {
        "write_text",
        "write_bytes",
        "writelines",
        "mkdir",
        "touch",
        "copy",
        "copy2",
        "copyfile",
        "copytree",
        "move",
        "rename",
        "to_csv",
        "to_json",
        "dump",
        "dumps",
        "safe_dump",
    }

    referenced = {node.attr for node in ast.walk(_tree()) if isinstance(node, ast.Attribute)} | {
        node.id for node in ast.walk(_tree()) if isinstance(node, ast.Name)
    }

    leaked = referenced & forbidden
    assert not leaked, f"byoc_loader writes: {', '.join(sorted(leaked))}"


def test_open_is_never_called_for_writing():
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "open":
            modes = [a.value for a in node.args[1:2] if isinstance(a, ast.Constant)]
            modes += [
                k.value.value
                for k in node.keywords
                if k.arg == "mode" and isinstance(k.value, ast.Constant)
            ]
            assert all("r" in m and "+" not in m for m in modes), f"opened for writing: {modes}"


def test_the_loader_never_reaches_the_network():
    """A licensed export is a file the user already has. Fetching one would
    send their credentials somewhere and their content somewhere else."""
    forbidden = {"requests", "urllib", "httpx", "urlopen", "socket", "get", "post"}

    referenced: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            referenced.update(part for a in node.names for part in a.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            referenced.update((node.module or "").split("."))
            referenced.update(a.name for a in node.names)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)

    leaked = referenced & forbidden
    assert not leaked, f"byoc_loader reaches the network: {', '.join(sorted(leaked))}"


def test_no_bundled_path_is_ever_turned_into_a_file_handle():
    """The public directory is where redistribution happens, so a parsed
    licensed catalog written there gets committed and pushed.

    Scoped to paths the module actually opens or constructs, not to the
    string appearing anywhere: the module names `data/frameworks/` in the
    error text of both stubs, precisely in order to warn the next
    implementer off it. Failing on that would punish the module for saying
    the thing this test exists to enforce.
    """
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Call):
            continue
        target = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
        if target not in {"Path", "open", "PurePath"}:
            continue
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                assert "data/frameworks" not in argument.value, (
                    f"a bundled path is opened or constructed: {argument.value!r}"
                )


@pytest.mark.parametrize("loader", ["load_hitrust_export", "load_govramp_export"])
def test_a_stub_refuses_loudly_rather_than_returning_nothing(loader):
    """An unimplemented loader that returned [] would look like a framework
    with no controls, and every coverage report built on it would say the
    organization has nothing to do."""
    with pytest.raises(NotImplementedError):
        getattr(byoc, loader)(Path("anything.csv"))
