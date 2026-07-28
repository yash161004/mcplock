# mcplock

`npm audit` / Subresource Integrity, but for MCP tool descriptions.

mcplock pins what an agent is allowed to trust about a tool, detects silent
drift in tool definitions, and flags ambiguous or unscoped tools before an agent
misuses them.

> **Status: pre-v0.1, under active development.** `snapshot` and `check` work
> against real servers. `lint` is not implemented yet.

## Usage

```bash
mcplock snapshot "npx -y @modelcontextprotocol/server-filesystem ./data"
mcplock check "npx -y @modelcontextprotocol/server-filesystem ./data"
```

Baselines are stored as flat JSON under `~/.mcplock/snapshots/` (override the
root with `MCPLOCK_HOME`).

`check` exit codes — 0 clean, 1 drift at or above `--fail-on` (default `high`),
2 could not check. A missing baseline is exit 2, not 0: exiting clean for an
unpinned server would silently green-light it in CI.

Servers needing credentials take `--env KEY=VALUE` (repeatable). The MCP SDK
inherits only a small safe allowlist when spawning a stdio server, so anything
else must be named explicitly. `--env` values are never written to the snapshot,
and are not part of the server identity.

Not yet implemented:

```bash
mcplock lint "npx -y @modelcontextprotocol/server-filesystem ./data"
```

## Severity

| Severity        | Meaning                                                      |
| --------------- | ------------------------------------------------------------ |
| `critical`      | a behavioural annotation flipped (`destructiveHint`, …)       |
| `high`          | content changed in a way that widens what the tool can do     |
| `medium`        | a pinned tool is gone                                         |
| `informational` | cosmetic rewording, benign new tools, non-behavioural keys    |

Four bands rather than the brief's two: with two, an annotation flip and a
reworded sentence land in the same bucket.

The `high` heuristic stays deliberately simple — trigger vocabulary
(`execute`, `delete`, `send`, `all`, `admin`) entering or leaving a description,
plus two schema widenings (a required parameter becoming optional, a new
parameter with destructive vocabulary). Keyword scanning ignores Unicode format
characters, so `de<ZWSP>lete` cannot slip past it; hashing keeps them, so the
edit still registers as drift.

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
