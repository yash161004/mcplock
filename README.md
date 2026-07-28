# mcplock

`npm audit` / Subresource Integrity, but for MCP tool descriptions.

mcplock pins what an agent is allowed to trust about a tool, detects silent
drift in tool definitions, and flags ambiguous or unscoped tools before an agent
misuses them.

> **Status: pre-v0.1, under active development.** `snapshot` works against real
> servers. `check` (diff) and `lint` are not implemented yet.

## Usage

```bash
mcplock snapshot "npx -y @modelcontextprotocol/server-filesystem ./data"
```

Baselines are stored as flat JSON under `~/.mcplock/snapshots/` (override the
root with `MCPLOCK_HOME`).

Planned, not yet implemented:

```bash
mcplock check "npx -y @modelcontextprotocol/server-filesystem ./data"
mcplock lint  "npx -y @modelcontextprotocol/server-filesystem ./data"
```

`check` will exit non-zero on high-severity drift, which is what makes it useful
in CI.

## Hash model

A tool is pinned by four hashes:

| Hash                | Covers                       | Purpose                                    |
| ------------------- | ---------------------------- | ------------------------------------------ |
| `content_hash`      | description + `inputSchema`  | did the meaning of this tool change        |
| `description_hash`  | description                  | name which side moved                      |
| `schema_hash`       | `inputSchema`                | name which side moved                      |
| `annotations_hash`  | `annotations`                | behavioural promises, tracked separately   |

`annotations_hash` is deliberately **not** folded into `content_hash`.
`destructiveHint` and `readOnlyHint` are assertions an agent may gate its
behaviour on, so a flip is its own critical finding — folding it in would make
it indistinguishable from a typo fix.

`title`, `outputSchema`, and `execution` are not hashed in v0.1; there is no
concrete drift scenario for them yet.

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
