# Remaining work

For an agent (Antigravity, OpenCode, a fresh Claude Code session) continuing this
project. Read [HANDOFF.md](HANDOFF.md) first — especially **Traps**, which lists
changes that look like cleanups and are regressions.

State as of 2026-07-29: `mcplock` **0.1.0** is on PyPI, the repo is public, 145
tests pass, and PR modelcontextprotocol/servers#4569 is open.

## Hard constraints

1. **Zero cost.** No paid APIs, no hosted services, no credits. Settled decision.
2. **Never track `.private/`.** It holds findings against third-party servers.
   The repo is public; committing any of it breaches `docs/DISCLOSURE.md`.
   `CLAUDE.md` is untracked for the same reason.
3. **Never write findings into `docs/`.** `scripts/phase4_sweep.py` writes to
   `.private/` on purpose.
4. **Don't send anything to a maintainer without the owner's say-so.** Drafting
   is fine; sending is the owner's call.
5. **`read_file` on the filesystem server must keep failing the scope lint.** It
   is the one finding that survived verification. Any lint change that silences
   it has gone too far — `tests/test_scope.py` asserts this.

---

## T1 — Fix Trusted Publishing so 0.1.1 actually ships

**Blocking. Owner action required; an agent cannot finish this.**

`pyproject.toml` says `0.1.1`, tag `v0.1.1` is pushed, but PyPI still serves only
`0.1.0`. The publish workflow ran and failed:

```
invalid-publisher: valid token, but no corresponding publisher
  repository:   yash161004/mcplock
  workflow_ref: .../.github/workflows/publish.yml@refs/tags/v0.1.1
  environment:  pypi
```

No Trusted Publisher is configured on PyPI. **Owner:** go to
https://pypi.org/manage/project/mcplock/settings/publishing/ and add a GitHub
publisher with exactly:

| Field | Value |
| --- | --- |
| Owner | `yash161004` |
| Repository | `mcplock` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

Then re-run the failed job, or delete and re-push the tag.

**Acceptance:** `pip index versions mcplock` shows 0.1.1, and
https://pypi.org/project/mcplock/ shows it.

**Do not** work around this by uploading with a token — the workflow exists so
releases are reproducible from a tag. Fix the publisher config instead.

---

## T2 — Track PR #4569 and respond to review

https://github.com/modelcontextprotocol/servers/pull/4569 — one-line fix adding
"Only works within allowed directories." to `read_file`'s description.

Prepared clone with the branch: `D:\mcplock-disclosures\servers`.

- If review asks for changes, make them there and push to the `fork` remote.
- **If it merges**, that closes F-001's disclosure window: move F-001 from
  `.private/INTERNAL_FINDINGS.md` into `docs/FINDINGS.md` (public), linking the
  PR. That file is currently an empty placeholder and is the project's public
  evidence.
- If it is rejected or ignored for 90 days, record that honestly instead —
  `docs/DISCLOSURE.md` §4 requires the maintainer's response be reported as it
  happened, including disagreement.

**Acceptance:** `docs/FINDINGS.md` has a real entry, or a recorded reason it does
not.

---

## T3 — Close out the other five findings

Verification is **done** (see the verdicts section in
`.private/INTERNAL_FINDINGS.md`). Nothing further is to be sent:

| ID | Verdict |
| --- | --- |
| F-002 | Retracted — mcplock false positive, now fixed |
| F-003 | Real but `server-everything` is a test server by design |
| F-004 | Descriptions genuinely distinguish themselves; too weak |
| F-005 | Mostly false positive — "drop" was the drag gesture; now fixed |
| F-006 | Repo archived since 2025-05-28; ineligible for reports |

**Task:** delete `.private/disclosure_drafts/mcp_server_sqlite.md` and
`.private/disclosure_drafts/playwright_mcp.md`, which correspond to F-006 and
F-005 and must not be sent. Keep the modelcontextprotocol one only if T2 needs
it. Do not re-open these; the analysis is recorded.

---

## T4 — Make the Action post a PR comment (Phase 5 gap)

The brief's Phase 5 asks the Action to "post a PR comment summarizing lint
findings". `check` gating works; the comment step was never built.

Add an optional step to `.github/actions/mcp-lock-action/action.yml` that runs
`mcplock lint --json` and posts a sticky comment on the PR.

**Requirements:**
- Opt-in via a `comment-on-pr` input, default `false`. Never post from a fork PR
  — the token is read-only there and it will fail confusingly.
- Needs `pull-requests: write` permission; document that in the README example.
- **Every caller value must reach the script through `env:`.** See the Traps
  entry: `${{ ... }}` inside `run:` is a script-injection vector, and
  `tests/test_action.py::TestActionScriptInjection` will fail the build if
  reintroduced. `actions/github-script` is acceptable, but the same rule applies.
- Update the input table in README.md.

**Acceptance:** new tests pass alongside the existing injection guards; the
README documents the permission requirement.

---

## T5 — Run the Action in a real external repo

Brief §6 success metric: *"At least 1 GitHub Action run integrated into a real
(even if small) external repo."* Not done.

Create a small public repo that consumes the published Action against a public
MCP server (`@modelcontextprotocol/server-filesystem` needs no credentials), with
a committed baseline so `check` has something to diff. Get one green run and one
deliberately-failed run showing drift being caught.

**Acceptance:** a public repo with both runs visible, linked from README.md.

---

## T6 — Write the public writeup

Brief §6: *"One published writeup with real numbers, not hypotheticals."* This is
the main credibility deliverable and it does not exist yet.

The real numbers now available:

- 85 tools across 11 public MCP servers linted; 1 server unreachable
- Scope lint: **10 findings → 2 after fixing two verified false positives**, with
  zero false positives remaining
- Ambiguity lint: the brief's TF-IDF-at-85% flags **0 of 91 pairs** on the
  filesystem server; the schema-substitutability gate removes 63 of 91 before
  scoring and flags 4, with a 0.33–0.50 margin between classes
- One finding verified against upstream source and fixed via PR #4569
- Two linter defects found *by* verification, both fixed, both with regression
  tests built from real upstream strings

**The honest framing is the interesting one:** most candidate findings did not
survive verification, and two were the tool's own fault. Say that. A writeup
claiming six findings would be false; one claiming one real finding and a
precision problem that got fixed is credible and more useful.

Also worth including: the Phase 4 hypothesis was pre-registered and is
**permanently unresolved** — P1 was never run because it needed paid API access.
See `docs/PHASE4_RESULTS.md`. Do not imply it was confirmed.

**Acceptance:** a draft in `.private/` for the owner to review. **Do not publish
it** — that is the owner's call, and it names third-party servers.

---

## T7 — Registry submission

Brief Phase 6: submit to an MCP tools registry if one accepts community
submissions. Investigate whether one exists that fits a *scanning tool* rather
than an MCP server. If none fits, record that and close the task rather than
forcing a bad fit.

---

## Not tasks — deliberately not doing these

- **GitHub Support ticket to purge old blobs.** Investigated; GitHub's own
  guidance says Support only removes *sensitive* data (credentials/PII) that
  cannot be mitigated by rotation. Ours is neither. Repo has 0 forks. Dropped.
- **Running Phase 4 P1/P3.** Needs a funded API account. Owner declined; the
  hypothesis stays unresolved by decision, not oversight.
- **Rewriting git history again.** Already done once. Old blobs remain reachable
  by direct SHA; accepted.
- **Lifting the `fixtura<2` cap.** 2.0.0 moved to the `fixtura.` namespace and
  the two Phase 4 scripts still use the old imports. Read the `pyproject.toml`
  comment first.
