# MCP Server

Aegis ships a [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that exposes five tools to any MCP-compatible client — including Claude Desktop. Once configured, you can ask Claude to run data quality checks, inspect audit trails, and search past diagnoses directly from the chat interface.

---

## Start the MCP server

```bash
aegis mcp serve
```

The server listens on stdin/stdout using the MCP stdio transport (the default for Claude Desktop integrations).

---

## Configure Claude Desktop

Add the following to your Claude Desktop configuration file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "aegis": {
      "command": "aegis",
      "args": ["mcp", "serve"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

Restart Claude Desktop after saving. You should see "aegis" appear in the tool list.

---

## Available tools

| Tool | What it does |
|---|---|
| `aegis_run` | Run a rules file against a warehouse and return the full validation report. Accepts `rules_file`, `db_path`, `no_llm`, and `llm` parameters. |
| `aegis_validate` | Validate a rules file offline (schema check only). Returns a list of errors and warnings without touching any data. |
| `aegis_list_runs` | Return a list of recent runs from the audit trail, newest first. Accepts an optional `limit` parameter. |
| `aegis_trajectory` | Return the full node-by-node trajectory for a given `run_id`, including every LLM prompt and response. |
| `aegis_search` | Full-text search across all LLM decisions in the audit trail. Accepts a `query` string and optional `limit`. |

---

## Example prompts

Once connected, you can use natural language with Claude:

- "Run my rules.yaml against demo.db and tell me what failed."
- "Show me the last 5 validation runs."
- "Search the audit trail for anything about null order IDs."
- "Show me the full diagnosis for run run_20260511_143022_a1b2c3."
- "Validate my rules.yaml and fix any errors you find."

---

## Using with other MCP clients

The Aegis MCP server is a standard stdio-transport MCP server and works with any compliant client. For HTTP/SSE transport (e.g. for remote use), run:

```bash
aegis mcp serve --transport sse --port 8765
```
