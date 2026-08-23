"""Confluence export — a secondary, additional feature layered on top of
the canonical markdown output, not an independent generation path.

This module takes the *already-generated, already-quality-checked* markdown
from generate/policy_writer.py and converts it to Confluence storage
format, then optionally publishes via the Confluence REST API. It does not
call the LLM and does not regenerate content — that guarantees the
markdown and Confluence versions of a document can't drift from each other
in substance, only in formatting.

This module originally evaluated (and briefly used) the `md2cf` package for
both jobs, per this module's original TODO. It was dropped: md2cf pins
every one of its own dependencies to an exact, years-old version —
`mistune==0.8.4` (dozens of known CVEs) and `requests==2.31.0` (known
CVEs) among them — which is exactly what this repo's own `pip-audit` gate
exists to catch. Instead:

- `markdown_to_confluence` renders with `markdown-it-py` (already a
  maintained transitive dependency via `mdformat`) plus a small custom
  renderer subclass that only needs to special-case fenced code blocks
  (Confluence's `code` macro) — every other CommonMark/GFM construct this
  project's generated output uses (headings, paragraphs, emphasis, lists,
  tables, links, inline code) renders to valid Confluence storage format
  (an XHTML dialect) via markdown-it-py's default HTML output, unmodified.
- `export_to_confluence` calls the Confluence Content REST API directly via
  `requests`, with no dependency pinned to a specific vulnerable version.

Confluence API credentials are read from environment variables only,
matching the pattern in llm/anthropic_provider.py — never from a committed
config file.
"""

from __future__ import annotations

import os

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from mdit_py_plugins.gfm import gfm_plugin

_API_CONTENT_PATH = "rest/api/content"


class _ConfluenceRenderer(RendererHTML):
    """markdown-it-py's default HTML renderer already produces valid
    Confluence storage format for everything except fenced code blocks,
    which Confluence expects as its `code` structured macro rather than a
    bare `<pre><code>` (for syntax highlighting in the rendered page)."""

    def fence(self, tokens, idx, options, env):
        token = tokens[idx]
        info = token.info.strip()
        language = info.split()[0] if info else ""
        # Guard against the code content itself containing "]]>", which
        # would otherwise prematurely terminate the CDATA section.
        content = token.content.replace("]]>", "]]]]><![CDATA[>")
        language_param = (
            f'<ac:parameter ac:name="language">{language}</ac:parameter>' if language else ""
        )
        return (
            '<ac:structured-macro ac:name="code">'
            f"{language_param}"
            f"<ac:plain-text-body><![CDATA[{content}]]></ac:plain-text-body>"
            "</ac:structured-macro>\n"
        )


def markdown_to_confluence(markdown_text: str) -> str:
    """Convert already-generated canonical markdown to Confluence storage
    format (XHTML-based). Does not touch the LLM or regenerate content."""
    md = MarkdownIt("commonmark", renderer_cls=_ConfluenceRenderer).use(gfm_plugin)
    return md.render(markdown_text)


def export_to_confluence(
    markdown_text: str,
    *,
    space: str,
    title: str,
    host: str,
    parent_id: str | None = None,
    username_env: str = "CONFLUENCE_USERNAME",
    token_env: str = "CONFLUENCE_API_TOKEN",
) -> str:
    """Convert `markdown_text` to Confluence storage format and create (or,
    if a page with this title already exists in the space, update) the
    page. Returns the resulting page's URL.

    Auth: HTTP Basic with (`username_env`, `token_env`) — an email + API
    token on Confluence Cloud. If `username_env` isn't set, `token_env` is
    sent as a Bearer token instead, for Confluence Server/Data Center
    personal access tokens.
    """
    token = os.environ.get(token_env)
    if not token:
        raise RuntimeError(
            f"Environment variable {token_env} is not set. Export your "
            f"Confluence API token before running policyforge, e.g.:\n"
            f"  export {token_env}=..."
        )
    username = os.environ.get(username_env)

    import requests

    base = host.rstrip("/")
    auth = (username, token) if username else None
    headers = {} if auth else {"Authorization": f"Bearer {token}"}

    body = markdown_to_confluence(markdown_text)
    body_payload = {"storage": {"value": body, "representation": "storage"}}
    ancestors = [{"id": parent_id}] if parent_id else None

    search = requests.get(
        f"{base}/{_API_CONTENT_PATH}",
        params={"title": title, "spaceKey": space, "expand": "version"},
        auth=auth,
        headers=headers,
        timeout=30,
    )
    search.raise_for_status()
    results = search.json().get("results", [])

    if results:
        page = results[0]
        payload = {
            "id": page["id"],
            "type": "page",
            "title": title,
            "space": {"key": space},
            "body": body_payload,
            "version": {"number": page["version"]["number"] + 1},
        }
        if ancestors:
            payload["ancestors"] = ancestors
        response = requests.put(
            f"{base}/{_API_CONTENT_PATH}/{page['id']}",
            json=payload,
            auth=auth,
            headers=headers,
            timeout=30,
        )
    else:
        payload = {"type": "page", "title": title, "space": {"key": space}, "body": body_payload}
        if ancestors:
            payload["ancestors"] = ancestors
        response = requests.post(
            f"{base}/{_API_CONTENT_PATH}", json=payload, auth=auth, headers=headers, timeout=30
        )

    response.raise_for_status()
    data = response.json()
    return f"{base}{data['_links']['webui']}"
