import httpx
import pytest
import respx

from zotero_mcp import server
from zotero_mcp.client import ZoteroClient, ZoteroConfig, ZoteroError

BASE = "https://api.zotero.org/users/123"

ITEM = {
    "key": "ABCD1234",
    "meta": {"parsedDate": "2021-05-01"},
    "data": {
        "key": "ABCD1234",
        "itemType": "journalArticle",
        "title": "Attention Is All You Need",
        "creators": [{"creatorType": "author", "firstName": "Ashish", "lastName": "Vaswani"}],
        "date": "2021",
        "DOI": "10.1234/abc",
        "tags": [{"tag": "transformers"}],
    },
}


@pytest.fixture
def web_client():
    client = ZoteroClient(ZoteroConfig("https://api.zotero.org", "/users/123", "secret", False))
    server.set_client(client)
    yield client
    server.set_client(None)


def text(result) -> str:
    return result.content[0].text


async def call(name, **args):
    return text(await server.mcp.call_tool(name, args))


@pytest.mark.anyio
@respx.mock
async def test_search_sends_key_and_formats(web_client):
    route = respx.get(f"{BASE}/items/top").respond(json=[ITEM])
    out = await call("search_items", query="attention")
    assert route.calls[0].request.headers["Zotero-API-Key"] == "secret"
    assert route.calls[0].request.url.params["qmode"] == "titleCreatorYear"
    assert "[ABCD1234] Attention Is All You Need" in out
    assert "Vaswani, Ashish, 2021, journalArticle" in out


@pytest.mark.anyio
@respx.mock
async def test_get_item_includes_notes_and_attachments(web_client):
    respx.get(f"{BASE}/items/ABCD1234").respond(json=ITEM)
    respx.get(f"{BASE}/items/ABCD1234/children").respond(json=[
        {"data": {"key": "NOTE0001", "itemType": "note", "note": "<p>Key &amp; idea</p>"}},
        {"data": {"key": "PDF00001", "itemType": "attachment", "title": "Full Text PDF",
                  "contentType": "application/pdf"}},
    ])
    out = await call("get_item", item_key="ABCD1234")
    assert "DOI: 10.1234/abc" in out
    assert "Tags: transformers" in out
    assert "Attachment [PDF00001]: Full Text PDF (application/pdf)" in out
    assert "Key & idea" in out


@pytest.mark.anyio
@respx.mock
async def test_collections_show_hierarchy(web_client):
    respx.get(f"{BASE}/collections").respond(json=[
        {"data": {"key": "PARENT01", "name": "Thesis"}, "meta": {"numItems": 3}},
        {"data": {"key": "CHILD001", "name": "Chapter 1", "parentCollection": "PARENT01"},
         "meta": {"numItems": 2}},
    ])
    out = await call("list_collections")
    assert "[CHILD001] Thesis / Chapter 1 (2 items)" in out


@pytest.mark.anyio
@respx.mock
async def test_add_note_posts_html(web_client):
    route = respx.post(f"{BASE}/items").respond(
        json={"successful": {"0": {"key": "NEWNOTE1"}}, "failed": {}}
    )
    out = await call("add_note", parent_item_key="ABCD1234", note="a < b\n\nsecond")
    body = route.calls[0].request.read().decode()
    assert "<p>a &lt; b</p><p>second</p>" in body
    assert out == "Note NEWNOTE1 added to item ABCD1234."


@pytest.mark.anyio
@respx.mock
async def test_forbidden_is_reported(web_client):
    respx.get(f"{BASE}/items/top").respond(status_code=403)
    out = await call("get_recent_items")
    assert out.startswith("Error: Zotero returned 403")


@pytest.mark.anyio
async def test_local_api_is_read_only():
    client = ZoteroClient(ZoteroConfig("http://localhost:23119/api", "/users/0", None, True))
    server.set_client(client)
    try:
        out = await call("add_note", parent_item_key="ABCD1234", note="x")
    finally:
        server.set_client(None)
    assert "read-only" in out


def test_config_requires_credentials(monkeypatch):
    for var in ("ZOTERO_LOCAL", "ZOTERO_API_KEY", "ZOTERO_LIBRARY_ID"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ZoteroError):
        ZoteroConfig.from_env()
    monkeypatch.setenv("ZOTERO_LOCAL", "true")
    config = ZoteroConfig.from_env()
    assert config.base_url == "http://localhost:23119/api" and config.library_prefix == "/users/0"


@pytest.fixture
def anyio_backend():
    return "asyncio"
