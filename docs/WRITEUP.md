# mcplock: pinning what agents trust about MCP tools

## One-line summary

`npm audit` / Subresource Integrity, but for MCP tool descriptions — a CLI
that pins what an agent is allowed to trust about a tool, detects silent
drift, and flags ambiguous or unscoped tools before an agent misuses them.

## What it does

mcplock connects to an MCP server, snapshots its `tools/list` output,
normalises the definitions, hashes them (SHA-256 per field), stores a
baseline, and re-checks it on demand. Then it lints for two classes of
defect that don't need a running agent:

1. **Ambiguity** — "could an agent pick the wrong one of these two?"
2. **Missing scope** — "does this tool say what it operates on?"

The output is a CLI report (via `rich`) and a machine-readable JSON report
for CI, with four severity bands.

## The honesty problem

This project worked best when it stopped being about finding faults in
other people's servers and started being about measuring its own precision.
The numbers below are what came out of that.

## Numbers from the real-server sweep

- **11 of 12 servers** reached (one unreachable — recorded as ecosystem
  data, not a failed run)
- **85 tools** linted across those 11 servers
- **10 scope findings** from the first-pass lint
- **6 ambiguity findings** from the first-pass lint

## What survived verification

**1 finding out of 6 formally verified** was real and worth reporting.

The linter produced 16 raw hits (10 scope + 6 ambiguity) across 85 tools.
Of those, 6 formally distinct candidates were taken to upstream
verification. Only one survived.

That finding was a convention-departure on
`@modelcontextprotocol/server-filesystem`: `read_file`'s description
omitted a boundary sentence that its 13 sibling tools all include. The
fix author's own framing in [PR #4569](https://github.com/modelcontextprotocol/servers/pull/4569)
describes it as "a documentation gap, not a security issue" — path
validation is unchanged and works correctly. The defect was in the
description only. The PR adds the missing sentence.

The remaining 5 broke down as:

| Outcome | Count | What it means |
|---------|-------|---------------|
| Linter false positive | 2 | mcplock's own bug — fixed |
| Real but not a defect | 1 | Deliberate test/demo server; near-duplicate tools are the point |
| Too weak to report | 1 | Descriptions genuinely distinguish themselves |
| Repo archived, ineligible | 1 | Server repo archived; disclaims reporting |
| Not a defect | 1 | Domain-appropriate scope is present, just not in filesystem vocabulary — linter didn't recognise it |

*(The five non-reportable candidates involved several different third-party
servers. None of those servers is named here, since none of the findings
against them cleared the bar for public disclosure — see "Responsible
disclosure" below.)*

## What we learned about the linter

The verification process found two defects in mcplock itself — both fixed,
both with regression tests built from real upstream strings:

1. **`states_scope()` was filesystem-biased.** It only recognised boundary
   phrases like "within allowed directories". It missed "from the knowledge
   graph" and "on the active page". Fix: recognise `from|on|in the <noun>`
   constructions.

2. **`DESTRUCTIVE_VERBS` ignored word sense.** A tool name containing "drop"
   matched on the word alone, even though the tool performed a UI
   drag-and-drop gesture rather than a deletion. Fix: require a destructive
   object nearby, or drop ambiguous verbs.

After both fixes the sweep went from 10 scope findings to **2, with none
false**.

## What we learned about our own supply chain

A tool that exists to catch silent changes in someone else's software should
be able to say how its own releases are built. Ours could not, for a while,
and the way it failed is the same failure mode mcplock was written to catch.

PyPI's Trusted Publishing mints a short-lived credential per CI run via OIDC
and attaches **PEP 740 provenance attestations** — signed statements binding
each artifact to the workflow, repository and commit that produced it. It is
the strictly better option, and it is what a package like this one ought to
ship with.

It did not work. Five attempts across two tagged releases failed at the
upload step, every one with the same error:

```
invalid-publisher: valid token, but no corresponding publisher
  (Publisher with matching claims was not found)
```

The pragmatic fix was an API token, and that is where the interesting part
starts. Supplying a token does not merely change *how* the package uploads —
it silently turns provenance off. `pypa/gh-action-pypi-publish` selects its
auth path on whether a password is present:

```bash
[[ "${INPUT_USER}" == "__token__" && -z "${INPUT_PASSWORD}" ]] \
    && TRUSTED_PUBLISHING=true || TRUSTED_PUBLISHING=false
```

and reports the consequence only as a passing warning:

> The workflow was run with the 'attestations: true' input, but an explicit
> password was also set, disabling Trusted Publishing. As a result, the
> attestations input is ignored.

The release succeeded. Every check was green. The package was fine. It just
had no provenance, and nothing in the outcome said so — one warning line in a
21-second log that scrolls past. **mcplock 1.0.2 is on PyPI permanently
without attestations**, because PyPI does not allow re-uploading a version.

The root cause of the original failure was mundane: the trusted publisher had
to be registered with the **environment name** matching the workflow job's
`environment:`, and the registration link PyPI itself generates does not
prefill that field. Once corrected, OIDC worked first try.

Two things worth generalising:

1. **A security control that degrades silently is one you will eventually
   lose without noticing.** This is precisely the class of problem mcplock
   exists for — not a change that breaks loudly, but one that leaves
   everything green while quietly removing a guarantee. We shipped an
   instance of it in the tool's own release pipeline, which is either
   embarrassing or the best possible argument for the tool, depending on
   how charitable you feel.

2. **The fix is to make the degradation loud, not to forbid the fallback.**
   The token path is now gated behind an explicit repository variable rather
   than the mere presence of a secret, and emits a `::warning::` naming what
   is being given up. Break-glass access survives; losing provenance by
   accident does not.

A related, smaller version of the same lesson: mcplock 1.0.1 shipped
reporting `__version__ == "0.1.0"`, because the version lived in two files
and nothing tied them together. A tool for detecting drift between a
recorded value and a live one had drifted between two of its own. There is
now a test asserting they match — which is, at bottom, the same idea as the
product.

## What we learned about ambiguity detection

The project brief proposed TF-IDF cosine similarity at an 85% threshold.
On the 14-tool filesystem server that flags **0 of 91 pairs**, and no
single cosine threshold separates confusable pairs from distinct pairs.

The actual implementation gates on **schema substitutability** — can one
set of arguments satisfy both tools? — then scores on name affinity and
description similarity, with a veto on opposing verbs (`read`/`write`,
`create`/`delete`). On that server the gate removes 63 of 91 pairs before
scoring, and 4 are flagged. The threshold sits in a 0.33–0.50 gap between
the two classes.

The distinction matters because:
- **Cosine alone is not a signal.** It conflates "described in a similar
  tone" with "an agent might confuse these". The two classes overlap
  completely.
- **Schema substitutability is what drives real confusion.** If you can
  call either tool with the same arguments, the description is the only
  thing left to choose on. That's where the vulnerability lives.

## The Phase 4 hypothesis (unresolved)

A pre-registered hypothesis (committed before any harness code existed)
predicted that an LLM-backed agent would choose `read_text_file` over
`read_media_file` for a binary file, and receive decoded garbage rather
than a refusal. The consequence half — the server returns garbage rather
than refusing — was confirmed against the real server. Whether an agent
actually makes that wrong choice, and how it recovers, was never tested,
because the environment had no usable API key and the project chose to
stay zero-cost rather than fund one.

**The hypothesis is permanently unresolved under the pre-registered
decision rule.** The agent-choice prediction is the primary claim; the
confirmed consequence alone does not support it. This document does not
claim confirmed agent behaviour. A future researcher could finish it: the
harness is in the repo and completes the test if an API key is supplied.

## What this means for the ecosystem

One real finding from 85 tools across 11 servers in July 2026 is
simultaneously encouraging (the ecosystem is not in crisis) and
disappointing (one finding is not enough for a paper).

The useful outcome is the measurement itself, plus two linter defects that
nobody else would have caught because nobody else was running this check.
The project's best contribution may be the method — how to scope an
ambiguity linter so it produces signal rather than noise — more than the
findings it generates.

## Responsible disclosure

Per `docs/DISCLOSURE.md`: one finding was reported privately via a GitHub
PR before anything was made public. No other finding against a third-party
server has been filed, because nothing else cleared the reporting bar —
and no other server involved in this sweep is named in this document as a
result.

## Technical details

- **Hash model:** Per-field SHA-256 (description, `inputSchema`,
  annotations). Annotations are deliberately separate from content so a
  `destructiveHint` flip is distinguishable from a typo fix.
- **Severity:** Four bands — `critical` (annotation flip), `high` (content
  change widening capability), `medium` (tool disappeared),
  `informational` (cosmetic).
- **Storage:** Flat JSON under `~/.mcplock/snapshots/` (or `$MCPLOCK_HOME`).
- **Transport:** stdio and streamable HTTP. `--env` for credentials, never
  persisted.
- **CI:** Composite GitHub Action, reusable, posts check annotations and an
  optional PR comment summarising findings. Caller input is passed through
  `env:` rather than interpolated into `run:` blocks — the naive version was
  a live script-injection defect, and there is a test guarding against its
  return.
- **Releases:** Tag-triggered, published to PyPI via Trusted Publishing (OIDC)
  with PEP 740 attestations, from 1.0.3 onward. Earlier versions have no
  provenance and cannot be given any, for the reasons in the supply chain
  section above. No long-lived credential exists for the project. The workflow
  refuses to build when the tag and `pyproject.toml` disagree, and refuses to
  ship an sdist containing undisclosed findings.

## Data

- 11 public MCP servers reached, spanning filesystem access, memory/graph
  storage, sequential reasoning, browser automation, version control,
  network fetch, time, documentation lookup, search, and database access —
  85 tools total
- 1 unreachable (auth-gated, expected)
- Scope findings after fixes: 2, both true positives — one is the disclosed
  finding on the filesystem server referenced above; the other is on a
  different server and is not named here, pending disclosure
- Ambiguity findings: 6 across the sweep — 4 on the filesystem server
  (discussed above), and 1 each on two others. All gated by schema
  substitutability
- 147 unit + integration tests (the `e2e` ones spawn real MCP servers over
  stdio); CI runs them on Python 3.11, 3.12 and 3.13

---

*This is an anonymized version of an internal draft. Server names not
already public through the disclosed PR have been generalized, per this
project's responsible-disclosure policy — findings against a server are
not published until the maintainer has been given the chance to respond,
or the finding has otherwise cleared that bar.*
