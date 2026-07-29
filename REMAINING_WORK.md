# Remaining work — mcplock, fixtura, OpenEval

**Written:** 2026-07-29 · For a fresh agent (Antigravity, OpenCode, new Claude Code session) picking this up cold.

Read [HANDOFF.md](HANDOFF.md) and `CLAUDE.md` first — especially *"Deviations from
this brief (decided, do not fix back)"*. Also read `openFixturaadapter.md` in the
fixtura repo: it records why the dependency pins are what they are, and reversing
them reintroduces shipped bugs.

---

## 0. State as of writing — verify before trusting

| Package | Published on PyPI | Repo HEAD | Tag |
|---|---|---|---|
| `mcplock` | **0.1.0** | `aa06468` (0.1.1) | `v0.1.1` exists, **unpublished** |
| `fixtura` | **1.1.1** | `febf15a` (2.0.0) | **no `v2.0.0` tag** — deliberate |
| `openeval-core` | **0.2.1** | `c513d63` | current |

```bash
# re-verify
curl -s https://pypi.org/pypi/mcplock/json | python -c "import sys,json;print(json.load(sys.stdin)['info']['version'])"
```

fixtura and OpenEval are **functionally complete**. All outstanding work is
mcplock's, plus one release step for fixtura that is gated on mcplock.

---

## 1. BLOCKER — publish mcplock 0.1.1

Everything else on the critical path waits on this.

**Why it matters:** mcplock 0.1.0 is published with `fixtura>=1.0.7` and **no
upper bound**. fixtura 2.0.0 moves every package under the `fixtura.` namespace.
The moment `v2.0.0` is tagged, anyone on mcplock 0.1.0 resolves it and breaks at
`from recorder.recorder import ExecutionRecorder`. 0.1.1 contains the cap
(`fixtura>=1.1.1,<2`) that closes this. **The cap is worthless until published.**

**Status:** `v0.1.1` is tagged and the publish workflow runs, but the upload step
fails. Four attempts, identical error:

```
* `invalid-publisher`: valid token, but no corresponding publisher
  (Publisher with matching claims was not found)
```

Everything before the upload passes: tag-vs-version guard, build, sdist leak
check. This is **purely a PyPI Trusted Publisher configuration mismatch**, not a
code problem.

Claims GitHub actually sends (confirmed in the run log):

| Claim | Value |
|---|---|
| `repository` | `yash161004/mcplock` |
| `repository_owner` | `yash161004` |
| `workflow_ref` | `.../.github/workflows/publish.yml@refs/tags/v0.1.1` |
| `environment` | `pypi` |

Already ruled out: pending-vs-project publisher (moved to the project), the
workflow-name field, and the environment name. **Not yet checked: whether the
publisher was configured on `test.pypi.org` instead of `pypi.org`** — that
produces exactly this symptom indefinitely.

### Pick one — do not keep re-running blindly

**A. Manual upload (fastest, matches how 0.1.0 shipped):**

```bash
git checkout master && git pull && rm -rf dist build && python -m build && twine upload dist/*
```

**B. API token fallback in CI.** The owner adds a repo secret `PYPI_API_TOKEN`
(GitHub → Settings → Secrets and variables → Actions). Then add to the publish
step:

```yaml
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
```

**C. Fix the Trusted Publisher config** (check pypi.org vs test.pypi.org first).

Retrying is free and never needs a re-tag:
`gh run rerun 30423208516 --failed`

**Agents must not handle PyPI tokens directly.** Option B requires the owner to
create and paste the secret; an agent only edits the workflow.

---

## 2. Tag fixtura v2.0.0 — ONLY after §1 is published

```bash
cd <fixtura> && git checkout master && git pull && git tag v2.0.0 && git push origin v2.0.0
```

fixtura's publish workflow is proven (it shipped 1.1.1) and has a
tag-vs-pyproject guard. **Do not tag this before mcplock 0.1.1 is live on PyPI** —
that ordering is the entire point of §1.

Releasing 2.0.0 also carries the corrected README badges to the PyPI page, which
is the only reason the cosmetic 1.1.2 was declined.

---

## 3. mcplock Phase 6 — ship (the real remaining project work)

Per `HANDOFF.md`, phases 0–5 are done; 6 is not started. Mostly owner decisions,
not code.

### 3.1 Disclosure — DONE, do not reopen

All six findings were verified against upstream source on 2026-07-29. **Only
F-001 was real.** It is fixed by PR modelcontextprotocol/servers#4569 (open).

| ID | Verdict |
| --- | --- |
| F-001 | Real. Reported via PR #4569. |
| F-002 | **Retracted** — mcplock false positive (filesystem-biased scope check) |
| F-003 | Real, but `server-everything` is a test server by design |
| F-004 | Descriptions genuinely distinguish themselves; too weak to send |
| F-005 | **Mostly false positive** — "drop" matched the drag gesture |
| F-006 | Repo archived since 2025-05-28; ineligible for reports |

Both linter defects F-002/F-005 exposed are fixed: the sweep went from 10 scope
findings to **2, with none false**. Verdicts and reasoning live in
`.private/INTERNAL_FINDINGS.md` (not `docs/` — that path is stale above).

**Remaining actions:**
- Delete `.private/disclosure_drafts/mcp_server_sqlite.md` and
  `playwright_mcp.md` — they correspond to F-006 and F-005 and must not be sent.
- If PR #4569 merges, F-001's window closes: move it into `docs/FINDINGS.md`
  (public, currently an empty placeholder) linking the PR. If it is rejected or
  ignored for 90 days, record *that* — `docs/DISCLOSURE.md` §4 requires the
  maintainer's response be reported honestly, including disagreement.

An agent must still **never send** anything to a maintainer without the owner.

### 3.2 Phase 5 gap — the Action does not post a PR comment

The brief's Phase 5 called for the GitHub Action to post a PR comment
summarising lint findings. `check` works in CI; **the comment step was never
built.** This is the largest genuinely unbuilt piece of code.

Lives in `.github/actions/mcp-lock-action/action.yml`. Note that file has already
had a script-injection fix (`8f2a8a6`) — do not reintroduce untrusted
interpolation into `run:` blocks. Pass values via `env:` and quote them.

### 3.3 Pre-publish checklist

Work the checklist at the end of `CLAUDE.md`. Several items are already done
(LICENSE added, findings untracked, README made standalone for PyPI) — verify
rather than assume.

### 3.4 Doc drift

Re-check counts before trusting any doc. As of 2026-07-29 the suite is
**145 tests**:

```bash
.venv/Scripts/python -m pytest tests -q     # ~95s, e2e spawns real MCP servers
```

### 3.5 Run the Action in a real external repo

Brief §6 success metric, not done. Create a small public repo consuming the
published Action against `@modelcontextprotocol/server-filesystem` (no
credentials needed), with a committed baseline. Get one green run and one
deliberately-failed run showing drift caught. Link both from README.md.

### 3.6 Write the public writeup

Brief §6, not done — the main credibility deliverable. Real numbers available:

- 85 tools across 11 public servers; 1 unreachable
- Scope lint: **10 findings → 2** after fixing two verified false positives
- Ambiguity: the brief's TF-IDF-at-85% flags **0 of 91 pairs**; the
  schema-substitutability gate removes 63 before scoring and flags 4, with a
  0.33–0.50 margin between classes
- One finding verified upstream and fixed via PR #4569
- Two linter defects found *by* verification, both fixed with regression tests
  built from real upstream strings

**The honest framing is the interesting one:** most candidates did not survive
verification and two were the tool's own fault. A writeup claiming six findings
would be false. One claiming a single real finding plus a precision problem that
got measured and fixed is credible and more useful.

Note the Phase 4 hypothesis was pre-registered and is **permanently unresolved**
— P1 needed paid API access and was never run (`docs/PHASE4_RESULTS.md`). Do not
imply it was confirmed.

Draft into `.private/` for owner review. **Do not publish** — owner's call, and
it names third-party servers.

### 3.7 Registry submission

Investigate whether an MCP registry accepts a *scanning tool* rather than a
server. If none fits, record that and close it rather than forcing a bad fit.


---

## 4. Optional / later

- **Migrate mcplock to fixtura 2.x.** Update both call sites — `scripts/phase4_experiment.py:136`
  and `scripts/phase4_p2_and_pipeline.py:94` — from `recorder.recorder` to
  `fixtura.recorder.recorder`, then move the pin to `fixtura>=2.0.0`. Those are
  the only fixtura-namespace usages; everything else goes through
  `openeval.adapters.fixtura`, which is unaffected.
- **mcplock has no CI workflow at all** (only `.github/actions/` and now
  `publish.yml`). fixtura and OpenEval both gate merges on tests. Adding one here
  would be consistent and cheap.

---

## 5. Hard constraints — do not violate

- **Zero-cost project.** No paid APIs, hosted services, or credits. Settled
  decision, not a budget to negotiate.
- **Publishing is irreversible.** PyPI forbids re-uploading a version. Never
  release to "test" something. Confirm with the owner before any tag push.
- **Never depend on the bare name `openeval`** — unrelated abandoned stub that
  installs cleanly and does nothing. It is `openeval-core`, floor `>=0.2.1`.
- **`pip install --dry-run` proves resolution, not importability.** It resolves
  without importing, so it cannot catch a package that installs and then fails at
  import. Verify integrations with a real import in a clean venv. This single
  mistake is what made the original fixtura/OpenEval breakage invisible.
- **Do not send disclosures.** See §3.1.
- **Do not weaken the sdist leak guard.**

---

## 6. Recommended order

1. §1 — publish mcplock 0.1.1 (pick A, B, or C)
2. §2 — tag fixtura `v2.0.0`
3. §3.4 — fix the stale test count (30 seconds)
4. §3.2 — build the PR-comment step
5. §3.1 — owner decides on disclosure; agents may verify, never send
6. §3.3 — pre-publish checklist, then release mcplock 1.0.0 when ready

Steps 1 and 2 are the critical path and unblock a real correctness hazard for
anyone already on mcplock 0.1.0. Everything else can proceed in parallel.
