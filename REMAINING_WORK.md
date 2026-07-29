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
| `mcplock` | **1.0.1** | `1.0.1` — no `v1.0.1` tag (see §2) |
| `fixtura` | **2.0.0** | current |
| `openeval-core` | **0.2.1** | current |

```bash
# re-verify before trusting the table
curl -s https://pypi.org/pypi/mcplock/json | python -c "import sys,json;print(json.load(sys.stdin)['info']['version'])"
```

Test suite: **146 passing** (`.venv/Scripts/python -m pytest tests -q`, ~90s;
the `e2e` ones spawn real MCP servers over stdio). CI is green on master across
Python 3.11/3.12/3.13.

**The previous revision of this file is obsolete.** Its §1 (publish mcplock
0.1.1) and §2 (tag fixtura v2.0.0) — described as the blocking critical path —
are both done. So are §3.1, §3.2, §3.4, §3.5, §3.6, §3.7, and both §4 optional
items. What follows is what actually remains.

---

## 1. Owner-only actions

Agents can prepare these but must not perform them.

### 1.1 Register the PyPI Trusted Publisher — the last open item

1.0.0 and 1.0.1 reached PyPI by manual `twine upload`. 1.0.2 published from CI,
but **with an API token, so it has no PEP 740 provenance attestations.** Every
tag-triggered OIDC attempt before that failed at the upload step:

```
* `invalid-publisher`: valid token, but no corresponding publisher
  (Publisher with matching claims was not found)
```

Everything before the upload passes — tag-vs-version guard, build, sdist leak
check. This is a PyPI configuration mismatch, not a code problem.

**Use the link PyPI generated during run `30440005820`**, logged in as an owner
of the package:

<https://pypi.org/manage/project/mcplock/settings/publishing/?provider=github&owner=yash161004&repository=mcplock&workflow_filename=publish.yml>

It prefills owner, repository, and workflow filename — but **not** the
environment, and that is the field most likely to have been wrong. PyPI's
troubleshooting guide lists it explicitly: *"check if the workflow is using the
same environment as configured when the publisher was configured on PyPI."*

| Field | Value |
|---|---|
| Owner | `yash161004` |
| Repository name | `mcplock` |
| Workflow name | `publish.yml` |
| **Environment name** | **`pypi`** ← must be filled in by hand |

Register on **pypi.org**, not test.pypi.org — that mismatch produces this exact
symptom indefinitely.

**After it works, delete the `PYPI_API_TOKEN` secret.** It is a standing
credential; OIDC mints a short-lived one per run and is the only path that
produces attestations.

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
| Test-count doc drift | 146, verified by running the suite |
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
