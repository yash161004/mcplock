# mcplock

`npm audit` / Subresource Integrity, but for MCP tool descriptions.

mcplock pins what an agent is allowed to trust about a tool, detects silent
drift in tool definitions, and flags ambiguous or unscoped tools before an agent
misuses them.

> **Status: pre-v0.1, under active development.** `snapshot`, `check`, `lint`,
> and the GitHub Action are implemented.

## Usage

```bash
mcplock snapshot "npx -y @modelcontextprotocol/server-filesystem ./data"
mcplock check "npx -y @modelcontextprotocol/server-filesystem ./data"
mcplock lint "npx -y @modelcontextprotocol/server-filesystem ./data"
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

`lint` exits 0 even with findings unless `--strict`. These are judgment calls
needing human review, not the binary facts `check` deals in — failing a build on
a heuristic is how a linter gets switched off.

## Linting

**Ambiguity** — "could an agent pick the wrong one of these two?" Description
similarity alone does not answer that: on the 14 real tools of the official
filesystem server, TF-IDF cosine at the 85% threshold flags **0 of 91 pairs**,
and the confusable and distinct pairs are not separable by *any* single cosine
threshold. So the check is gated on **schema substitutability** — can one set of
arguments satisfy both tools? — then scored on name affinity and description
similarity, with a veto on opposing verbs (`read`/`write`, `create`/`delete`).

On that server the gate removes 63 of 91 pairs before scoring, and 4 are
flagged: the three-way `read_file`/`read_text_file`/`read_media_file` cluster and
`list_directory`/`list_directory_with_sizes`. The threshold sits in a 0.33–0.50
gap between the two classes.

**Scope** — two checks. A destructive verb with no boundary language anywhere
(strengthened by unbounded words like "arbitrary" or "any file on the host"),
and a *convention departure*: a tool omitting a boundary statement the rest of
its own server makes. Neither inspects behaviour, so both are documentation
gaps, never vulnerabilities.

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

## CI

mcplock provides a reusable composite GitHub Action to gate pull requests against tool-definition drift in CI.

Add `.github/workflows/mcplock.yml` to your repository:

```yaml
name: Check MCP Tool Definitions

on:
  pull_request:
    branches: [ main ]

jobs:
  check-drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Verify MCP Server Baseline
        uses: yash161004/mcplock/.github/actions/mcp-lock-action@master
        with:
          server: 'npx -y @modelcontextprotocol/server-filesystem ./data'
          fail-on: 'high'
```

### Demo

A real CI run against `@modelcontextprotocol/server-filesystem`:
- [✓ Green run](https://github.com/yash161004/mcplock-demo/actions/runs/30425018340) — baseline captured and verified clean
- [✗ Broken run](https://github.com/yash161004/mcplock-demo/actions/runs/30425300912) — injected description drift detected at HIGH severity, build fails

### Action Inputs

| Input | Description | Default |
| --- | --- | --- |
| `server` | Server command or streamable-HTTP URL | **Required** |
| `transport` | `stdio` \| `http` \| `auto` | `auto` |
| `fail-on` | Lowest severity threshold to fail build (`critical` \| `high` \| `medium` \| `informational`) | `high` |
| `json-report` | Optional path to write machine-readable JSON report | `""` |
| `env` | Space-separated `KEY=VALUE` environment variables for stdio server | `""` |
| `python-version` | Python version for `setup-python` | `3.11` |
| `mcplock-version` | PyPI version specifier for `mcplock` | `mcplock` |

## Development

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -e ".[dev]"
pytest
```

## What it found

mcplock was run against 11 public MCP servers — 85 tools in total. The results,
including what did *not* hold up, are written up in
**[the project writeup](https://github.com/yash161004/mcplock/blob/master/docs/WRITEUP.md)**:

- **1 real finding** out of 6 candidates taken to upstream verification, fixed
  via [PR #4569](https://github.com/modelcontextprotocol/servers/pull/4569)
- **2 defects in mcplock itself**, found *by* that verification and fixed with
  regression tests built from real upstream strings — the scope lint went from
  10 findings to 2, with none false
- **The brief's proposed ambiguity heuristic does not work.** TF-IDF cosine at
  85% flags 0 of 91 pairs; what makes it work is gating on schema
  substitutability first

The writeup also covers a provenance failure in this project's own release
pipeline, because a tool that detects silent degradation should say when it
suffered one.

## Responsible disclosure

mcplock reads tool definitions that servers publish through `tools/list`. When
it surfaces something real in someone else's server, we handle it like this:

1. **Private report first** — to the project's security contact, `SECURITY.md`,
   or a private advisory, with the exact observed text, the date observed, and a
   reproduction.
2. **90 days by default** — shorter if it is fixed sooner, longer only if the
   maintainer is engaged and asks. Silence is not a reason to extend.
3. **Nothing public before then** — not the server, not the finding.
4. **Honest credit** — the maintainer's response is recorded as it happened,
   including disagreement.

We report on names, descriptions, and input schemas only. We do not test
authentication, access anyone's data, or exploit anything beyond confirming what
we saw.

Note what these checks are and are not: they read *descriptions*, not behaviour.
A tool whose description omits a boundary may still enforce one perfectly. Those
findings are documentation gaps, and reporting them as vulnerabilities would be
wrong.

To report an issue in mcplock itself, contact the maintainer privately. The same
90-day standard applies to us.
