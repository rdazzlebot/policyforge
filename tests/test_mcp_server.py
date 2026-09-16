"""The MCP surface, whose defining property is that it cannot write.

Exposing the analyses to other agents is only safe because every tool reads
what is already on disk. That has to be a structural fact rather than a
promise, so the guard below mirrors the one that already keeps the publish
path unreachable from `zardoz/`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from policyforge.mcp import server as mcp_server
from policyforge.mcp.server import TOOLS, build_state, call_tool

# ---- the property that makes this safe ---------------------------------


def test_no_module_here_can_reach_the_publish_path():
    """Structural, not a convention.

    Checked over the parsed AST rather than as a substring, so the module
    stays free to *discuss* the publish path in its docstring — which it
    needs to, since the reason it does not call it is the whole point. The
    walk covers every node, so a lazy import inside a function body is
    caught as readily as one at the top of the file.
    """
    forbidden = {
        "update_page_body",
        "export_to_confluence",
        "confluence_exporter",
        "publish_tree",
        "apply_edit_plan",
        "apply_targets",
    }
    sources = list(Path(mcp_server.__file__).parent.glob("*.py"))
    assert sources, "expected to find the mcp package sources"

    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        referenced: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                referenced.update(part for a in node.names for part in a.name.split("."))
            elif isinstance(node, ast.ImportFrom):
                referenced.update((node.module or "").split("."))
                referenced.update(a.name for a in node.names)
            elif isinstance(node, ast.Name):
                referenced.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced.add(node.attr)

        leaked = referenced & forbidden
        assert not leaked, f"{path.name} reaches a write path: {', '.join(sorted(leaked))}"


def test_the_tool_list_is_closed_and_every_tool_is_dispatchable():
    """A tool nobody can run, or a route to a tool nobody declared, is a bug.

    The registry of skills grows whenever somebody adds an analysis. The
    tool list must not, which is why it is written by hand — adding a tool
    should be a deliberate act with a diff.
    """
    declared = {tool.name for tool in TOOLS}
    routable = set(mcp_server._DISPATCH) | {"ask_documents"}
    assert declared == routable


def test_no_tool_describes_itself_as_changing_anything():
    """The descriptions are what an agent chooses a tool from.

    Matching on the bare word "publish" was the first attempt and was wrong:
    NIST *publishes* the crosswalk, and a topic *publishes* documents, so
    two honest descriptions tripped it. The check has to be about phrasings
    that tell a caller this tool mutates something, not about a word that
    also describes who wrote a standard.
    """
    mutating = (
        "publishes the",
        "will publish",
        "applies the",
        "writes the",
        "updates the page",
        "edits the page",
        "changes the document",
    )
    for tool in TOOLS:
        described = tool.description.lower()
        for phrase in mutating:
            assert phrase not in described, f"{tool.name} describes itself as writing: {phrase!r}"


def test_every_tool_has_a_usable_schema():
    for tool in TOOLS:
        assert tool.schema["type"] == "object"
        assert tool.schema.get("additionalProperties") is False
        for name, spec in tool.schema["properties"].items():
            assert spec.get("description"), f"{tool.name}.{name} has no description"
        for required in tool.schema.get("required", []):
            assert required in tool.schema["properties"]


# ---- behaviour, against a state with nothing loaded --------------------


@pytest.fixture
def empty_state(tmp_path):
    """A server with no registry, no corpus and no model.

    The most common way this will first be run, and every tool has to answer
    rather than raise.
    """
    return build_state({}, corpus_dir=tmp_path / "corpus", topics_path=tmp_path / "topics.yaml")


def test_an_empty_install_answers_every_tool_without_raising(empty_state):
    for tool in TOOLS:
        result = call_tool(empty_state, tool.name, {})
        assert isinstance(result, str) and result.strip(), f"{tool.name} returned nothing"


def test_an_unknown_tool_is_reported_not_raised(empty_state):
    assert "No such tool" in call_tool(empty_state, "delete_everything", {})


def test_asking_nothing_asks_for_a_question(empty_state):
    assert "Ask a question" in call_tool(empty_state, "ask_documents", {"question": "   "})


def test_missing_arguments_do_not_crash_a_skill(empty_state):
    assert call_tool(empty_state, "team_bundle", {}).strip()
    assert call_tool(empty_state, "addresses", {"requirement": ""}).strip()


def test_arguments_of_the_wrong_type_are_coerced_not_fatal(empty_state):
    """A client can send anything; a tool call should not be the thing that
    takes the server down."""
    assert call_tool(empty_state, "coverage", {"baseline": 3}).strip()
    assert call_tool(empty_state, "ask_documents", {"question": None}).strip()


def test_none_arguments_are_tolerated(empty_state):
    assert call_tool(empty_state, "corpus", None).strip()


# ---- the answers match the shell's ------------------------------------


def test_a_tool_returns_exactly_what_the_shell_returns(empty_state):
    """No second code path. A tool that reformatted a report would let the
    CLI and an agent disagree about the same repository."""
    from policyforge.zardoz.shell import dispatch

    assert call_tool(empty_state, "corpus", {}) == dispatch("/corpus", empty_state)
    assert call_tool(empty_state, "topics", {}) == dispatch("/topics", empty_state)


def test_the_bundle_tool_reaches_the_registry(tmp_path):
    import yaml

    topics_path = tmp_path / "topics.yaml"
    topics_path.write_text(
        yaml.safe_dump(
            {
                "topics": [
                    {"name": "Access Review", "owner": "IAM", "nist_controls": ["AC-2"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    state = build_state({}, corpus_dir=tmp_path / "corpus", topics_path=topics_path)
    assert "Access Review" in call_tool(state, "topics", {})


# ---- the optional dependency -------------------------------------------


def test_the_missing_dependency_message_names_the_extra():
    """`mcp` is in this venv only because semgrep depends on it.

    Anyone installing PolicyForge normally will not have it, and the error
    they get should name the extra rather than being an ImportError.
    """
    assert "policyforge[mcp]" in mcp_server._INSTALL_HINT
    assert "optional" in mcp_server._INSTALL_HINT


def test_model_calls_from_a_tool_are_attributed_to_the_mcp_surface(empty_state):
    """A-09 put questions in the ledger so a challenged answer could be
    traced to what was asked. Once an agent can call ask_documents in a
    loop, "a person asked this" stops being implied — and an unexpected
    line on a bill has to be attributable to a tool rather than a colleague.
    """
    assert empty_state.surface == "mcp"


def test_a_terminal_session_is_still_attributed_to_zardoz():
    """The default must not have moved under the REPL."""
    from policyforge.zardoz.shell import ShellState

    assert ShellState().surface == "zardoz"


def test_only_one_tool_calls_a_model_and_says_so():
    """The cost asymmetry is invisible otherwise: six of seven tools are
    set arithmetic over local files, and the calling agent chooses from
    these descriptions."""
    costly = [t for t in TOOLS if "calls a language model" in t.description]
    assert [t.name for t in costly] == ["ask_documents"]
