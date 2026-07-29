# Findings

Public log of findings, published only after the process in
[DISCLOSURE.md](DISCLOSURE.md) has run its course for each entry.

Empty by design — nothing has been disclosed yet.

| Date reported | Server | Finding | Status | Public date |
| ------------- | ------ | ------- | ------ | ----------- |
| 2026-07-29 | `@modelcontextprotocol/server-filesystem` | `read_file` description omitted allowed-directories scope boundary notice (F-001) | Open — PR [#4569](https://github.com/modelcontextprotocol/servers/pull/4569) | 2026-07-29 |

### Active / Tracked Findings

#### F-001: Missing Scope Boundary on `read_file`
- **Server:** `@modelcontextprotocol/server-filesystem` (in [`modelcontextprotocol/servers`](https://github.com/modelcontextprotocol/servers))
- **Issue:** All 13 other filesystem server tools include `"Only works within allowed directories."` at the end of their tool descriptions. `read_file` (the deprecated alias for `read_text_file`) shares the exact same schema and handler, but lacked this boundary statement in its description text.
- **Status:** Open. Submitted fix via PR [#4569](https://github.com/modelcontextprotocol/servers/pull/4569) on 2026-07-29. Pending maintainer review.

