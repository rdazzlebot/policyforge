"""Pull an existing page's content back out of Confluence, converting its
storage format (XHTML) back to this project's canonical markdown — the
reverse of confluence_exporter.py's markdown_to_confluence /
export_to_confluence.

Two things this exists for:
- Bootstrapping: bring a policy that already lives in Confluence (written
  by hand before this tool existed) into the pipeline so it can be tracked
  going forward — see history/version_store.py.
- Drift detection: `cli.py`'s `import-confluence` command records the
  imported content into the *same* version stream as `generate` for that
  tier/name, so you can diff "what this tool last generated" against
  "what's actually live" in case someone hand-edited the published page.

Conversion is not guaranteed lossless for Confluence-native macros beyond
the `code` macro this project's own exporter emits (see
`_restore_code_fences`) — round-trip fidelity is only guaranteed for
documents this tool itself published. A panel, expand block, or page
property macro will pass through as raw HTML rather than vanishing or
crashing, but it won't come back as clean markdown either.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ._confluence_auth import API_CONTENT_PATH, confluence_auth


@dataclass
class ConfluencePage:
    id: str
    title: str
    version: int
    storage_body: str
    webui_url: str


def fetch_confluence_page(
    *,
    space: str,
    title: str,
    host: str,
    username_env: str = "CONFLUENCE_USERNAME",
    token_env: str = "CONFLUENCE_API_TOKEN",
) -> ConfluencePage:
    """Look up a page by title within a space and return its current
    storage-format body and version number. Raises LookupError if no page
    with that exact title exists in that space."""
    import requests

    auth, headers = confluence_auth(username_env=username_env, token_env=token_env)
    base = host.rstrip("/")

    response = requests.get(
        f"{base}/{API_CONTENT_PATH}",
        params={"title": title, "spaceKey": space, "expand": "body.storage,version"},
        auth=auth,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    if not results:
        raise LookupError(f"No Confluence page titled {title!r} found in space {space!r}.")

    page = results[0]
    return ConfluencePage(
        id=page["id"],
        title=page["title"],
        version=page["version"]["number"],
        storage_body=page["body"]["storage"]["value"],
        webui_url=f"{base}{page['_links']['webui']}",
    )


_CODE_MACRO_RE = re.compile(
    r'<ac:structured-macro ac:name="code">'
    r'(?:<ac:parameter ac:name="language">(?P<language>[^<]*)</ac:parameter>)?'
    r"<ac:plain-text-body><!\[CDATA\[(?P<code>.*?)\]\]></ac:plain-text-body>"
    r"</ac:structured-macro>",
    re.DOTALL,
)


def _restore_code_fences(storage_html: str) -> str:
    """Turn this project's own `code` structured macro (see
    confluence_exporter.py's `_ConfluenceRenderer.fence`) back into a plain
    `<pre><code>` block markdownify already knows how to render as a fenced
    code block, before handing the rest of the document to markdownify —
    markdownify has no Confluence-macro-specific knowledge of its own."""

    def _replace(match: re.Match[str]) -> str:
        language = match.group("language") or ""
        code = match.group("code").replace("]]]]><![CDATA[>", "]]>")
        lang_attr = f' class="language-{language}"' if language else ""
        return f"<pre><code{lang_attr}>{code}</code></pre>"

    return _CODE_MACRO_RE.sub(_replace, storage_html)


def _code_language_callback(el) -> str | None:
    """markdownify only emits a bare ``` fence by default; pull the
    language back out of the `class="language-X"` attribute
    `_restore_code_fences` set on the `<code>` tag, so a fenced code block
    keeps its language on the round trip."""
    code = el.find("code")
    if code is None:
        return None
    for css_class in code.get("class", []):
        if css_class.startswith("language-"):
            return css_class[len("language-") :]
    return None


def confluence_to_markdown(storage_html: str) -> str:
    """Convert a Confluence storage-format page body back to CommonMark
    markdown."""
    from markdownify import markdownify

    prepared = _restore_code_fences(storage_html)
    return (
        markdownify(
            prepared,
            heading_style="ATX",
            bullets="-",
            code_language_callback=_code_language_callback,
        ).strip()
        + "\n"
    )


def import_from_confluence(
    *,
    space: str,
    title: str,
    host: str,
    username_env: str = "CONFLUENCE_USERNAME",
    token_env: str = "CONFLUENCE_API_TOKEN",
) -> str:
    """Fetch a page from Confluence and convert it to markdown — the
    reverse of confluence_exporter.py's `export_to_confluence`."""
    page = fetch_confluence_page(
        space=space, title=title, host=host, username_env=username_env, token_env=token_env
    )
    return confluence_to_markdown(page.storage_body)
