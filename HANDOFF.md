# Handoff

Written for a fresh agent (Antigravity, OpenCode, or a new Claude Code session)
picking this repo up cold. Remaining work is in [TASKS.md](TASKS.md).

`CLAUDE.md` holds the original brief plus **"Deviations from this brief (decided,
do not fix back)"** — the choices that look wrong against the spec and are not.
It is **kept local and is not in this repository**, so it will be absent from a
fresh clone. The Traps section below carries the parts that matter for changing
code safely; ask the owner for `CLAUDE.md` if you need the full rationale.

## State

| Phase | Status |
|---|---|
| 0 — setup, connector, first fixture | done (`a1e2237`) |
| 1 — normalize / hash / store / `snapshot` | done (`7daeed0`) |
| 2 — diff / severity / `check` | done (`1460302`) |
| 3 — ambiguity + scope lint / `lint` | done (`af07fa2`) |
| 4 — real-server sweep | done (11/12 reached, findings F-001..F-006 candidate-logged) |
| 4 — LLM hypothesis test | **stopped, deliberately** — [docs/PHASE4_RESULTS.md](docs/PHASE4_RESULTS.md) |
| 5 — report polish + GitHub Action | done |
| 6 — ship | not started |

139 tests pass: `.venv/Scripts/python -m pytest tests -q` (~90s; the `e2e` ones
spawn real MCP servers over stdio).

## The one hard constraint

**This project is zero-cost. Do not spend money and do not ask the owner to.**
No paid APIs, no hosted services, no credits. This is a settled decision, not a
budget to negotiate. Everything below is free.

## Phase 4 sweep — done

`scripts/phase4_sweep.py` ran: **11 of 12 servers reached, 85 tools linted**,
producing 6 ambiguity and 10 missing-scope findings. `brave-search` is recorded
unreachable, kept deliberately — that is ecosystem data, not a failed run.

Findings F-001..F-006, the three unsent disclosure drafts, and the raw
per-server finding JSON live in the gitignored **`.private/`**, not in this
repository. They name third-party servers, none of whose maintainers has been
contacted; publishing them would breach `docs/DISCLOSURE.md`. **Nothing has been
sent** — sending is the owner's decision, not an agent's.

## Next task: Phase 6 (ship)

Blocked on owner decisions more than on code. In rough order:

1. **Decide whether the F-00x findings are worth disclosing at all.** They are
   documentation-clarity observations, not defects. Three GitHub issues about
   missing sentences may read as noise; the drafts are honest and proportionate
   if you do send them.
2. **None of them are upstream-verified.** See the re-observation caveat below.
   Criterion 1 of each finding ("check the current upstream source, not this
   fixture") is still unmet for all six.
3. Publish to PyPI so the Action's default `pip install mcplock` resolves. The
   artifacts are built and verified; only the upload is outstanding.
4. Work the pre-publish checklist at the end of the local `CLAUDE.md`. Items 1
   and 2 are done — the findings and `CLAUDE.md` itself are out of the repo.

Still unbuilt from the brief's Phase 5: the Action does **not** post a PR
comment summarising lint findings. `check` in CI works; the comment step does not
exist.

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
- **`import fixtura` does not work on fixtura 1.x** — it installs top-level
  `cli`, `recorder`, `replay`, `security`, `tools` instead, so the scripts use
  `from recorder.recorder import ExecutionRecorder`. That is not a workaround;
  see H-001 in PHASE4_RESULTS.md. **fixtura 2.0.0 fixed it** by moving everything
  under the `fixtura.` namespace, which is why `validate` pins `<2` — the two
  scripts still use the old imports. Read the comment in `pyproject.toml` before
  lifting the cap.
- **`--env` values are secrets.** `ServerTarget.__repr__` is hand-written to
  redact them and the malformed-`--env` error reports by position only. Both
  were live credential leaks. `tests/test_connector.py` guards them.
- **mcp SDK is 2.x.** `streamable_http_client` (2 values, not 3),
  `next_cursor` not `nextCursor`, `MCPServer` not `FastMCP`.
- **Never track anything under `.private/`.** It holds undisclosed third-party
  findings and the unsent disclosure drafts. This repository is public: adding
  any of it back breaches `docs/DISCLOSURE.md` the moment it is pushed. The same
  goes for `CLAUDE.md`, which is deliberately untracked.
- **Never interpolate `${{ ... }}` inside a `run:` block** in the Action. GitHub
  substitutes the raw text before bash parses it, so a crafted `server` or `env`
  input executes on the runner — quoting does not help. Pass caller input through
  `env:` and read it as a shell variable. This was a live defect;
  `tests/test_action.py::TestActionScriptInjection` guards it.
- **A re-capture is not upstream verification.** Re-running `tools/list` against
  the same published package proves the description was transcribed correctly,
  nothing more. An earlier revision recorded findings as `CONFIRMED` — two of
  them citing a "human review" that never happened. Record only what was actually
  done; in a disclosure-track document, overstated provenance is the one
  unrecoverable mistake.

## Environment

Windows, Python 3.14.2, venv at `.venv`. `node`/`npx` present. Repo is
`github.com/yash161004/mcplock`, **public**, branch `master`.
`docs/phase4_runs/` holds raw experiment output — keep raw logs, not summaries.

History was rewritten on 2026-07-29 with `git filter-repo` to purge `CLAUDE.md`,
`INTERNAL_FINDINGS.md`, the disclosure drafts, and the per-server finding JSON,
then force-pushed. Commit SHAs from before that date do not resolve; any clone
predating it must be re-cloned rather than pulled.
