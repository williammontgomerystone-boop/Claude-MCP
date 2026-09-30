"""MCP server exposing a Zotero library to Claude."""

from __future__ import annotations

import html
import re
from typing import Any

from mcp.server.mcpserver import MCPServer

from .client import ZoteroClient, ZoteroConfig, ZoteroError

mcp = MCPServer(
    name="zotero",
    instructions=(
        "Tools for searching and reading the user's Zotero library. Item keys are "
        "8-character IDs such as 'ABCD1234'. Search first, then fetch details by key."
    ),
)

_client: ZoteroClient | None = None


def get_client() -> ZoteroClient:
    global _client
    if _client is None:
        _client = ZoteroClient(ZoteroConfig.from_env())
    return _client


def set_client(client: ZoteroClient | None) -> None:
    global _client
    _client = client


def _strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text)).strip()


def _creators(data: dict[str, Any]) -> str:
    names = []
    for c in data.get("creators", []):
        if "lastName" in c:
            names.append(f"{c['lastName']}, {c.get('firstName', '')}".strip(", "))
        elif "name" in c:
            names.append(c["name"])
    return "; ".join(names)


def _summary(item: dict[str, Any]) -> str:
    data = item.get("data", item)
    parts = [f"[{data.get('key')}] {data.get('title') or data.get('note', '')[:80] or '(untitled)'}"]
    authors = _creators(data)
    year = (item.get("meta", {}).get("parsedDate") or data.get("date", ""))[:4]
    detail = ", ".join(p for p in (authors, year, data.get("itemType")) if p)
    if detail:
        parts.append(f"    {detail}")
    return "\n".join(parts)


def _format_list(items: list[dict[str, Any]], empty: str) -> str:
    if not items:
        return empty
    return "\n".join(_summary(i) for i in items)


def _error(e: ZoteroError) -> str:
    return f"Error: {e}"


@mcp.tool()
async def search_items(query: str, limit: int = 25, include_fulltext: bool = False) -> str:
    """Search the Zotero library by title, creator, year, and optionally full text.

    Args:
        query: Words to search for.
        limit: Maximum results (1-100).
        include_fulltext: Also search inside PDFs and notes (slower).
    """
    try:
        items = await get_client().get(
            "/items/top",
            q=query,
            qmode="everything" if include_fulltext else "titleCreatorYear",
            limit=max(1, min(limit, 100)),
        )
    except ZoteroError as e:
        return _error(e)
    return _format_list(items, f"No items matched '{query}'.")


@mcp.tool()
async def get_recent_items(limit: int = 10) -> str:
    """List the most recently added items in the library.

    Args:
        limit: Maximum results (1-100).
    """
    try:
        items = await get_client().get(
            "/items/top", sort="dateAdded", direction="desc", limit=max(1, min(limit, 100))
        )
    except ZoteroError as e:
        return _error(e)
    return _format_list(items, "The library is empty.")


@mcp.tool()
async def get_item(item_key: str) -> str:
    """Get full metadata for one item, plus its notes and attachments.

    Args:
        item_key: The 8-character Zotero item key.
    """
    client = get_client()
    try:
        item = await client.get(f"/items/{item_key}")
        children = await client.get(f"/items/{item_key}/children")
    except ZoteroError as e:
        return _error(e)

    data = item["data"]
    skip = {"key", "version", "relations", "collections", "creators", "tags", "dateModified"}
    lines = [f"Title: {data.get('title', '(untitled)')}"]
    if authors := _creators(data):
        lines.append(f"Creators: {authors}")
    for field, value in data.items():
        if field not in skip and field != "title" and value not in ("", [], {}, None):
            lines.append(f"{field}: {value}")
    if tags := [t["tag"] for t in data.get("tags", [])]:
        lines.append(f"Tags: {', '.join(tags)}")

    notes = [c["data"] for c in children if c["data"].get("itemType") == "note"]
    attachments = [c["data"] for c in children if c["data"].get("itemType") == "attachment"]
    for a in attachments:
        lines.append(
            f"Attachment [{a['key']}]: {a.get('title', '')} ({a.get('contentType', 'unknown type')})"
        )
    for n in notes:
        lines.append(f"\nNote [{n['key']}]:\n{_strip_html(n.get('note', ''))}")
    return "\n".join(lines)


@mcp.tool()
async def get_fulltext(attachment_key: str) -> str:
    """Get the indexed full text of a PDF or other attachment.

    Args:
        attachment_key: Key of the attachment (see get_item), not the parent item.
    """
    try:
        result = await get_client().get(f"/items/{attachment_key}/fulltext")
    except ZoteroError as e:
        return _error(e)
    content = result.get("content", "")
    return content or "This attachment has no indexed full text."


@mcp.tool()
async def list_collections() -> str:
    """List all collections (folders) in the library."""
    try:
        collections = await get_client().get("/collections", limit=100)
    except ZoteroError as e:
        return _error(e)
    if not collections:
        return "No collections."
    by_key = {c["data"]["key"]: c["data"] for c in collections}

    def path(key: str) -> str:
        c = by_key[key]
        parent = c.get("parentCollection")
        return f"{path(parent)} / {c['name']}" if parent and parent in by_key else c["name"]

    rows = sorted(
        (path(c["data"]["key"]), c["data"]["key"], c.get("meta", {}).get("numItems"))
        for c in collections
    )
    return "\n".join(f"[{k}] {p}" + (f" ({n} items)" if n is not None else "") for p, k, n in rows)


@mcp.tool()
async def get_collection_items(collection_key: str, limit: int = 50) -> str:
    """List the items in a collection.

    Args:
        collection_key: Key from list_collections.
        limit: Maximum results (1-100).
    """
    try:
        items = await get_client().get(
            f"/collections/{collection_key}/items/top", limit=max(1, min(limit, 100))
        )
    except ZoteroError as e:
        return _error(e)
    return _format_list(items, "This collection is empty.")


@mcp.tool()
async def get_citation(item_keys: list[str], style: str = "apa") -> str:
    """Format a bibliography for one or more items.

    Args:
        item_keys: Item keys to cite.
        style: CSL style name, e.g. apa, chicago-note-bibliography, mla, ieee, nature.
    """
    try:
        items = await get_client().get(
            "/items", itemKey=",".join(item_keys), format="json", include="bib", style=style
        )
    except ZoteroError as e:
        return _error(e)
    if not items:
        return "No matching items."
    return "\n\n".join(_strip_html(i.get("bib", "")) for i in items)


@mcp.tool()
async def add_note(parent_item_key: str, note: str) -> str:
    """Attach a new note to an item. Requires a Web API key with write access.

    Args:
        parent_item_key: Key of the item the note belongs to.
        note: Note text. Plain text or simple HTML.
    """
    body = note if note.lstrip().startswith("<") else "".join(
        f"<p>{html.escape(p)}</p>" for p in note.split("\n\n")
    )
    try:
        result = await get_client().post(
            "/items", [{"itemType": "note", "parentItem": parent_item_key, "note": body, "tags": []}]
        )
    except ZoteroError as e:
        return _error(e)
    if result.get("failed"):
        return f"Error: Zotero rejected the note: {result['failed']}"
    key = next(iter(result.get("successful", {}).values()), {}).get("key", "?")
    return f"Note {key} added to item {parent_item_key}."


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
