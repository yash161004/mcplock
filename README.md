# mcplock

`npm audit` / Subresource Integrity, but for MCP tool descriptions.

mcplock pins what an agent is allowed to trust about a tool, detects silent
drift in tool definitions, and flags ambiguous or unscoped tools before an agent
misuses them.

> **Status: pre-v0.1, under active development.** Phase 0 (setup + first real
> fixture) is done; snapshot/hash, diff, and lint are in progress.

## Planned usage

```bash
mcplock snapshot "npx -y @modelcontextprotocol/server-filesystem ./data"
mcplock check    "npx -y @modelcontextprotocol/server-filesystem ./data"
mcplock lint     "npx -y @modelcontextprotocol/server-filesystem ./data"
```

`check` exits non-zero on high-severity drift, which is what makes it useful in
CI.

## Development

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -e ".[dev]"
pytest
```

## Responsible disclosure

See [docs/DISCLOSURE.md](docs/DISCLOSURE.md). Findings against third-party
servers are reported privately first and logged in
[docs/FINDINGS.md](docs/FINDINGS.md) only after the disclosure window closes.
