# Handoff

Written for a fresh agent (Antigravity, OpenCode, or a new Claude Code session)
picking this repo up cold. Read [CLAUDE.md](CLAUDE.md) first — especially
**"Deviations from this brief (decided, do not fix back)"**, which lists choices
that look wrong against the original spec and are not.

## State

| Phase | Status |
|---|---|
| 0 — setup, connector, first fixture | done (`a1e2237`) |
| 1 — normalize / hash / store / `snapshot` | done (`7daeed0`) |
| 2 — diff / severity / `check` | done (`d51dae0`) |
| 3 — ambiguity + scope lint / `lint` | done (`6d53d2a`) |
| 4 — real-server sweep | **in progress — see below** |
| 4 — LLM hypothesis test | **stopped, deliberately** — [docs/PHASE4_RESULTS.md](docs/PHASE4_RESULTS.md) |
| 5 — report polish + GitHub Action | not started |
| 6 — ship | not started |

117 tests pass: `.venv/Scripts/python -m pytest tests -q` (~60s; the `e2e` ones
spawn real MCP servers over stdio).

## The one hard constraint

**This project is zero-cost. Do not spend money and do not ask the owner to.**
No paid APIs, no hosted services, no credits. This is a settled decision, not a
budget to negotiate. Everything below is free.

## Next task: finish the Phase 4 sweep

`scripts/phase4_sweep.py` exists and is **untested — it has never been run.**
It snapshots and lints ~12 public MCP servers over stdio and writes
`docs/phase4_runs/sweep.json`. No API key, no credentials, `npx`/`uvx` only.

```bash
python scripts/phase4_sweep.py
```

Expect several servers to fail to start (wrong package name, needs auth, `uvx`
missing). **Record failures, don't delete the entries** — "unreachable" is data
about the ecosystem. Fix package names where they're simply wrong.

Then, for each server that returned findings:

1. Add real ones to [docs/INTERNAL_FINDINGS.md](docs/INTERNAL_FINDINGS.md) as
   `candidate`, following the F-001 format already there.
2. Verify against current upstream source before promoting past `candidate` —
   one capture on one day proves nothing about `main`.
3. Follow [docs/DISCLOSURE.md](docs/DISCLOSURE.md) before any public mention.
4. Characterise honestly: these linters read *descriptions*, not behaviour.
   A missing boundary sentence is a documentation gap, **never** a
   vulnerability. F-001's wording is the model to copy, and
   `tests/test_scope.py` asserts that wording.

After that, Phase 5 (report polish + the GitHub Action) is the highest-value
remaining work — it's what makes `check` usable in CI.

## Traps

Each of these was a real bug or a real decision. Re-introducing them is a
regression, even though each looks like a cleanup.

- **`content_hash` covers description + `inputSchema` only.** Annotations are
  hashed separately on purpose so a `destructiveHint` flip is distinguishable
  from a typo. §4 of the brief calls it `full_hash`; that name is wrong now.
- **Ambiguity linting is not cosine similarity alone.** The brief's TF-IDF-at-85%
  flags **0 of 91 pairs** on the real filesystem server. The schema-substitutability
  gate is what makes it work. Don't "simplify" it back.
- **`openeval-core>=0.2.1`, never `openeval`.** The bare name on PyPI is an
  unrelated abandoned stub that installs cleanly and does nothing. `0.1.2`
  resolves but lacks the adapter module — `pip install --dry-run` cannot catch
  that, because it resolves without importing.
- **`import fixtura` does not work** — the distribution installs top-level `cli`,
  `recorder`, `replay`, `security`, `tools` instead. Use `from recorder.recorder
  import ExecutionRecorder`. That is not a workaround; see H-001 in
  PHASE4_RESULTS.md, which is a finding to report upstream.
- **`--env` values are secrets.** `ServerTarget.__repr__` is hand-written to
  redact them and the malformed-`--env` error reports by position only. Both
  were live credential leaks. `tests/test_connector.py` guards them.
- **mcp SDK is 2.x.** `streamable_http_client` (2 values, not 3),
  `next_cursor` not `nextCursor`, `MCPServer` not `FastMCP`.
- **Don't publish `docs/INTERNAL_FINDINGS.md`.** It holds undisclosed
  third-party findings. See the pre-publish checklist at the end of CLAUDE.md.

## Environment

Windows, Python 3.14.2, venv at `.venv`. `node`/`npx` present. Repo is
`github.com/yash161004/mcplock`, **private**, branch `master`.
`docs/phase4_runs/` holds raw experiment output — keep raw logs, not summaries.
