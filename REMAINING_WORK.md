# Remaining work — mcplock, fixtura, OpenEval

**Last reconciled:** 2026-07-29 (second pass, after the Antigravity/OpenCode
track landed). For a fresh agent picking this up cold.

Read [HANDOFF.md](HANDOFF.md) and `AGENT_BRIEF.md` first — especially
*"Deviations from this brief (decided, do not fix back)"*. Also read
`openFixturaadapter.md` in the fixtura repo: it records why the dependency pins
are what they are, and reversing them reintroduces shipped bugs.

---

## 0. State — verified 2026-07-29

| Package | Published on PyPI | Repo HEAD |
|---|---|---|
| `mcplock` | **1.0.3** | `1.0.3`, tagged `v1.0.3` |
| `fixtura` | **2.0.1** | `2.0.1`, tagged `v2.0.1` |
| `openeval-core` | **0.2.1** | current |

```bash
# re-verify before trusting the table
curl -s https://pypi.org/pypi/mcplock/json | python -c "import sys,json;print(json.load(sys.stdin)['info']['version'])"
```

Test suite: **147 passing** (`.venv/Scripts/python -m pytest tests -q`, ~90s;
the `e2e` ones spawn real MCP servers over stdio). CI is green on master across
Python 3.11/3.12/3.13.

Check the exit code, not the tail of the output — `pytest ... | tail -3` reports
`tail`'s status, so a `&&` chain after it runs even on a red suite. Use
`${PIPESTATUS[0]}`. This has already caused one push on a failing test.

**The previous revision of this file is obsolete.** Its §1 (publish mcplock
0.1.1) and §2 (tag fixtura v2.0.0) — described as the blocking critical path —
are both done. So are §3.1, §3.2, §3.4, §3.5, §3.6, §3.7, and both §4 optional
items. What follows is what actually remains.

---

## 1. Owner-only actions

Agents can prepare these but must not perform them.

### 1.1 PyPI Trusted Publishing — RESOLVED 2026-07-29

Registered and verified. Do not reopen.

| Field | Value |
|---|---|
| Owner | `yash161004` |
| Repository name | `mcplock` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

**The environment field was the cause.** Four tag-triggered attempts had failed
with `invalid-publisher`; PyPI's troubleshooting guide lists an environment
mismatch as a cause, and the registration link PyPI generates does not prefill
that field. Registering it as `pypi`, matching the job's `environment: name:`,
fixed it.

Verified without publishing anything, by re-running the old `v1.0.0` publish
(run `30425739738`, attempt 2). That revision of the workflow had no `password:`
input, so it was pure OIDC, against a version PyPI already holds:

```
##[notice]Generating and uploading digital attestations
  -> mcplock-1.0.0-py3-none-any.whl.publish.attestation
  -> mcplock-1.0.0.tar.gz.publish.attestation
Uploading distributions to https://upload.pypi.org/legacy/
400 File already exists ('mcplock-1.0.0-py3-none-any.whl', ...)
```

`File already exists` rather than `invalid-publisher` proves the OIDC exchange
succeeded, and the attestations were generated — they only exist on the Trusted
Publishing path. This is a safe test to repeat: a duplicate version is hard
rejected, so it cannot publish.

The `PYPI_API_TOKEN` secret was **deleted** on 2026-07-29 once this was proven,
and the token itself **revoked on PyPI** the same day. Deleting the GitHub
secret alone would not have invalidated it — the token stays live on the PyPI
account until explicitly removed. No secrets remain on the repository, and no
long-lived PyPI credential exists for this project.

History, for anyone auditing the releases:

| Version | How it published | Attestations |
|---|---|---|
| 0.1.0, 1.0.0, 1.0.1 | manual `twine upload` | no |
| 1.0.2 | CI, API token | **no** — the token silently disabled them |
| **1.0.3** | **CI, OIDC** | **yes — verified** |

1.0.3 was the first release to publish through Trusted Publishing, in run
`30472686196`. Confirmed rather than assumed: `USE_PYPI_TOKEN` was empty so the
OIDC branch ran, the log shows `Generating and uploading digital attestations`,
and PyPI's integrity endpoint returns HTTP 200 for both artifacts:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  https://pypi.org/integrity/mcplock/1.0.3/mcplock-1.0.3-py3-none-any.whl/provenance
```

Use that endpoint, not the `provenance` field in `https://pypi.org/pypi/<pkg>/<ver>/json`
— that field was stale-cached and read `null` for a release that demonstrably
had attestations, which is misleading in exactly the direction that matters.

Releases from 1.0.3 onward inherit this as long as `USE_PYPI_TOKEN` stays unset.
1.0.2 and earlier cannot be fixed retroactively; PyPI forbids re-uploading a
version, and burning a version number to republish identical code is not worth
it.

### 1.1a How the two paths are selected

`gh-action-pypi-publish` picks with:

```bash
[[ "${INPUT_USER}" == "__token__" && -z "${INPUT_PASSWORD}" ]] \
    && TRUSTED_PUBLISHING=true || TRUSTED_PUBLISHING=false
```

so an empty `password` means OIDC. The workflow gates the token behind a
repository **variable**, not the mere presence of the secret:

```yaml
password: ${{ vars.USE_PYPI_TOKEN == 'true' && secrets.PYPI_API_TOKEN || '' }}
```

- Default (variable unset) → OIDC, with attestations.
- `USE_PYPI_TOKEN=true` **and** the secret present → token, and the run logs a
  `::warning::` that attestations are disabled.
- `USE_PYPI_TOKEN=true` but no secret → falls through to OIDC.

This exists because 1.0.2 lost its provenance silently: the secret alone was
enough to divert to the token path, and the action only mentions it in a passing
warning. For a supply-chain tool, that is the wrong default. Giving up
provenance now takes a deliberate act.

**Agents must never handle a PyPI token directly.**

Retrying is free and never needs a re-tag: `gh run rerun <id> --failed`.

### 1.2 Releasing — bump before you tag

The publish workflow's first step refuses to build unless the tag matches
`pyproject.toml`. Tag `v1.0.2` was once pushed while pyproject still said
1.0.1; the guard stopped it before the upload, which is what it is for. Nothing
reached PyPI, but the tag then had to be deleted and re-created.

Order that works — bump, commit, push, *then* tag:

```bash
# 1. bump BOTH pyproject.toml version and mcplock/__init__.py __version__
#    (tests/test_packaging.py fails if they disagree)
.venv/Scripts/python -m pytest tests -q
git commit -am "release: vX.Y.Z" && git push origin master
git tag vX.Y.Z && git push origin vX.Y.Z
```

If a tag was pushed early, delete it on both sides before re-tagging —
`git push origin :refs/tags/vX.Y.Z` then `git tag -d vX.Y.Z`. Re-pushing a
moved tag without deleting it first does not re-trigger cleanly.

Note 1.0.1 was never tagged: PyPI already holds it, and PyPI forbids
re-uploading a version, so a retroactive `v1.0.1` tag would only fail at upload.

**Confirm with the owner before any tag push.**

### 1.3 Disclosure — send or don't

F-001 is fixed by PR [modelcontextprotocol/servers#4569](https://github.com/modelcontextprotocol/servers/pull/4569),
still **open** as of 2026-07-29. `docs/FINDINGS.md` records it publicly and
tracks the PR. `docs/DISCLOSURE.md` §4 requires the maintainer's response be
reported honestly, including disagreement or silence:

- If #4569 merges → update `docs/FINDINGS.md` status to closed.
- If it is rejected or ignored for 90 days (from 2026-07-29 → **2026-10-27**) →
  record *that* outcome, do not quietly drop it.

`.private/disclosure_drafts/modelcontextprotocol_servers.md` is the one
surviving draft; the F-005 and F-006 drafts were correctly deleted. **An agent
must never send anything to a maintainer.**

### 1.4 Publish the writeup — or don't

`.private/PUBLIC_WRITEUP_DRAFT.md` is written and awaiting owner review. It
names third-party servers whose maintainers have not been contacted, so it
stays in `.private/` until the owner decides. **Do not publish.**

---

## 2. Closed — do not reopen

| Item | Outcome |
|---|---|
| Publish mcplock | 1.0.1 live on PyPI |
| Tag fixtura v2.0.0 | Live on PyPI |
| Disclosure verdicts (F-001..F-006) | Only F-001 real; verified against upstream source. `.private/INTERNAL_FINDINGS.md` |
| Action PR-comment step | Built — `.github/actions/mcp-lock-action/action.yml`, `comment-on-pr` input, `auto`/`true`/`false` |
| Test-count doc drift | 147, verified by running the suite |
| External-repo validation | [mcplock-demo](https://github.com/yash161004/mcplock-demo) — one green run, one deliberately-failing run, both linked from README |
| Registry submission | No MCP registry accepts a scanning *tool* rather than a server. 11 evaluated; conclusion recorded in `.private/REGISTRY_SUBMISSION.md`. Closed rather than forced into a bad fit |
| fixtura 2.x migration | Both Phase 4 scripts moved to `fixtura.recorder.recorder`; pin lifted to `>=2.0.0` |
| mcplock CI workflow | `.github/workflows/ci.yml`, 3.11/3.12/3.13 |
| `__version__` drift | `mcplock/__init__.py` said `0.1.0` while pyproject said `1.0.1`, and that shipped. Fixed, with `tests/test_packaging.py::test_dunder_version_matches_pyproject` to stop it recurring |

The Phase 4 hypothesis was pre-registered and is **permanently unresolved** — P1
needed paid API access and was never run (`docs/PHASE4_RESULTS.md`). Do not imply
it was confirmed.

---

## 3. Hard constraints — do not violate

- **Zero-cost project.** No paid APIs, hosted services, or credits. Settled
  decision, not a budget to negotiate.
- **Publishing is irreversible.** PyPI forbids re-uploading a version. Never
  release to "test" something. Confirm with the owner before any tag push.
- **Never depend on the bare name `openeval`** — unrelated abandoned stub that
  installs cleanly and does nothing. It is `openeval-core`, floor `>=0.2.1`.
- **`pip install --dry-run` proves resolution, not importability.** It resolves
  without importing, so it cannot catch a package that installs and then fails
  at import. Verify integrations with a real import in a clean venv. This single
  mistake is what made the original fixtura/OpenEval breakage invisible.
- **Do not send disclosures.** See §1.3.
- **Do not weaken the sdist leak guard** (`tests/test_packaging.py`, plus the
  tarball check in `publish.yml`).
- **Never track anything under `.private/`.** The repository is public.
