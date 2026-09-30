# Claude + Zotero

An MCP server that lets Claude search and read your Zotero library. It works with Claude Desktop and Claude Code.

Claude gets these tools:

| Tool | What it does |
| --- | --- |
| `search_items` | Search by title, author, and year, or inside PDFs and notes |
| `get_recent_items` | List what you added most recently |
| `get_item` | Full metadata for one item, with its notes and attachments |
| `get_fulltext` | The indexed text of a PDF attachment |
| `list_collections` | Your collections, shown as a folder tree |
| `get_collection_items` | The items in one collection |
| `get_citation` | A formatted bibliography in APA, MLA, Chicago, or any CSL style |
| `add_note` | Attach a note to an item (Web API mode only) |

## 1. Install

You need Python 3.10 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
git clone https://github.com/williammontgomerystone-boop/Claude-MCP.git
cd Claude-MCP
uv sync
```

## 2. Choose how to connect to Zotero

There are two modes. Pick one.

**Local mode** reads straight from the Zotero desktop app. It needs no API key, but Zotero must be open, and it is read-only.

1. Install Zotero 7.
2. In Zotero, open Settings > Advanced and turn on "Allow other applications on this computer to communicate with Zotero".
3. Use `ZOTERO_LOCAL=true` in the config below.

**Web API mode** goes through zotero.org. It works when Zotero is closed and it can add notes. Your library must be syncing to zotero.org.

1. Go to https://www.zotero.org/settings/keys.
2. Copy the number shown as "Your user ID for use in API calls". That is your `ZOTERO_LIBRARY_ID`.
3. Click "Create new private key". Tick "Allow library access", and also "Allow write access" if you want Claude to add notes. Save and copy the key. That is your `ZOTERO_API_KEY`.

For a group library, set `ZOTERO_LIBRARY_TYPE=group` and use the group ID from the group's URL as `ZOTERO_LIBRARY_ID`.

## 3. Add it to Claude

### Claude Desktop

Open Settings > Developer > Edit Config. This opens `claude_desktop_config.json`. Add the `zotero` entry, replacing the path with where you cloned the repo:

```json
{
  "mcpServers": {
    "zotero": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/Claude-MCP", "claude-zotero-mcp"],
      "env": {
        "ZOTERO_LOCAL": "true"
      }
    }
  }
}
```

For Web API mode, replace the `env` block with:

```json
"env": {
  "ZOTERO_API_KEY": "your-key",
  "ZOTERO_LIBRARY_ID": "1234567"
}
```

Quit and reopen Claude Desktop. The Zotero tools appear under the tools menu in the chat box.

If Claude Desktop cannot find `uv`, use its full path as `command`. Run `which uv` (macOS, Linux) or `where uv` (Windows) to get it.

### Claude Code

```sh
# Local mode
claude mcp add zotero -e ZOTERO_LOCAL=true -- uv run --directory /path/to/Claude-MCP claude-zotero-mcp

# Web API mode
claude mcp add zotero -e ZOTERO_API_KEY=your-key -e ZOTERO_LIBRARY_ID=1234567 -- uv run --directory /path/to/Claude-MCP claude-zotero-mcp
```

Run `/mcp` inside Claude Code to confirm it is connected.

## 4. Try it

- "Find the papers in my Zotero library about sleep and memory."
- "Summarize the PDF for the Vaswani 2017 paper."
- "Give me an APA bibliography for everything in my Thesis collection."
- "Add a note to that paper with the three main findings."

## Troubleshooting

"Could not reach Zotero on localhost:23119" means Zotero is closed or the setting in step 2 is off.

"403 Forbidden" means the API key is wrong or lacks the permission you need. Adding notes requires write access.

`get_fulltext` returns nothing when Zotero has not indexed that PDF. In Zotero, right-click the PDF and choose "Reindex Item". In Web API mode, full text also has to be synced.

## Development

```sh
uv sync --extra dev
uv run pytest
```
