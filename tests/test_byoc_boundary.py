"""The licensing boundary around bring-your-own-content.

`byoc_loader` reads framework content its user is licensed for and this
repository is not — HITRUST CSF, GovRAMP, anything without redistribution
rights. Its docstring states the rule plainly: read BYOC in, never write
BYOC to a bundled or public path. Until now that rule existed only as
prose, in a module whose two functions were stubs waiting to be filled in
against a real export.

`load_hitrust_export` is now implemented, which is exactly when the rule
starts to matter: there is real parsed HITRUST content in memory for the
first time. So the checks run over the whole BYOC read path -- the entry
point and the two HITRUST modules behind it -- rather than over the entry
point alone.

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
import policyforge.ingest.hitrust as hitrust
import policyforge.ingest.hitrust_export as hitrust_export

SOURCE = Path(byoc.__file__)

#: Every module that touches licensed content on its way in. Named rather
#: than discovered so that adding a loader is a deliberate act that has to
#: come past this list.
BYOC_MODULES = (byoc, hitrust, hitrust_export)


def _tree(module=byoc):
    source = Path(module.__file__)
    return ast.parse(source.read_text(encoding="utf-8"), filename=str(source))


@pytest.mark.parametrize("module", BYOC_MODULES, ids=lambda m: m.__name__)
def test_the_loader_never_writes_anything(module):
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

    tree = _tree(module)
    referenced = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)} | {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }

    leaked = referenced & forbidden
    assert not leaked, f"{module.__name__} writes: {', '.join(sorted(leaked))}"


@pytest.mark.parametrize("module", BYOC_MODULES, ids=lambda m: m.__name__)
def test_open_is_never_called_for_writing(module):
    for node in ast.walk(_tree(module)):
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
    send their credentials somewhere and their content somewhere else.

    Attribute names are checked here as well as imports, which is why this
    one stays scoped to the entry point: `get` and `post` are HTTP verbs
    and also ordinary dictionary and email-message methods, so the wider
    net only reads correctly on a module thin enough not to need them.
    """
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


@pytest.mark.parametrize("module", BYOC_MODULES, ids=lambda m: m.__name__)
def test_no_byoc_module_imports_a_network_client(module):
    """The same rule as above, by import rather than by attribute, so it can
    cover the parsing modules without tripping over `dict.get`."""
    forbidden = {"requests", "urllib", "urllib3", "httpx", "socket", "http", "ftplib"}

    imported: set[str] = set()
    for node in ast.walk(_tree(module)):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])

    leaked = imported & forbidden
    assert not leaked, f"{module.__name__} imports: {', '.join(sorted(leaked))}"


@pytest.mark.parametrize("module", BYOC_MODULES, ids=lambda m: m.__name__)
def test_no_bundled_path_is_ever_turned_into_a_file_handle(module):
    """The public directory is where redistribution happens, so a parsed
    licensed catalog written there gets committed and pushed.

    Scoped to paths the module actually opens or constructs, not to the
    string appearing anywhere: the module names `data/frameworks/` in the
    error text of both stubs, precisely in order to warn the next
    implementer off it. Failing on that would punish the module for saying
    the thing this test exists to enforce.
    """
    for node in ast.walk(_tree(module)):
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


def test_an_unimplemented_loader_refuses_loudly():
    """A stub that returned [] would look like a framework with no controls,
    and every coverage report built on it would say the organization has
    nothing to do."""
    with pytest.raises(NotImplementedError):
        byoc.load_govramp_export(Path("anything.csv"))


def test_an_implemented_loader_refuses_a_file_it_cannot_read(tmp_path):
    """The same rule, one step along: now that HITRUST parses, the way to
    fail is an export whose columns are unrecognisable. Returning a short
    catalog would be read as a small framework rather than a bad parse."""
    from policyforge.ingest.hitrust_export import ExportFormatError

    export = tmp_path / "not-really-hitrust.csv"
    export.write_text("alpha,beta\n1,2\n", encoding="utf-8")

    with pytest.raises(ExportFormatError) as raised:
        byoc.load_hitrust_export(export)
    # The message has to name what was missing, or the next step is a guess.
    assert "reference" in str(raised.value)


def test_a_loader_refuses_a_format_it_has_no_reader_for(tmp_path):
    from policyforge.ingest.hitrust_export import ExportFormatError

    export = tmp_path / "export.docx"
    export.write_bytes(b"not a spreadsheet")

    with pytest.raises(ExportFormatError):
        byoc.load_hitrust_export(export)
