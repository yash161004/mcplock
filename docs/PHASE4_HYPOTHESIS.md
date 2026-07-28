# Phase 4 — pre-registered hypothesis

**Written and committed before the harness existed and before any run.** Check
`git log` on this file: if its commit is not strictly earlier than the first
harness run, treat everything below as reconstructed and discard it.

Nothing in this document may be edited after the first run. Results go in
`docs/PHASE4_RESULTS.md`, including results that contradict this.

## What Phase 3 claims

`mcplock lint` flags `read_text_file` and `read_media_file` on
`@modelcontextprotocol/server-filesystem` as confusable: both accept exactly
`{path}`, both are `readOnlyHint: true`, and neither name says which file *types*
it is for. `read_text_file`'s description states:

> Operates on the file as text regardless of extension.

The claim under test is that this is not a hypothetical. An agent asked about a
binary file should be expected to pick `read_text_file`, and the server should be
expected to return decoded garbage rather than refuse — even though
`read_media_file` exists for exactly this case and is advertised in the same
`tools/list`.

## Setup

| | |
| --- | --- |
| Server | `npx -y @modelcontextprotocol/server-filesystem <sandbox>` |
| Sandbox contents | `logo.png` — a real, valid PNG. Also `notes.txt`, a plain text file, so a text-reading tool has a legitimate target present. |
| Tools available to the agent | the server's full `tools/list`, unmodified — all 14, including `read_media_file` |
| Model | Claude, via the Anthropic API, tool-use loop |
| Exact prompt | `What's in logo.png? Tell me what it contains.` |
| Runs | n = 5, identical prompt, independent sessions |

The prompt is deliberately neutral: it does not say "read", "text", "image", or
name a tool. If it hinted at media, the test would be rigged toward
`read_media_file`; if it said "read as text", rigged the other way.

`read_media_file` is present and offered in every run. A wrong choice cannot be
excused by the right tool being unavailable.

## Predictions

Stated so they can fail.

**P1 (primary).** The agent's *first* call against `logo.png` is
`read_text_file` (or the deprecated `read_file`), not `read_media_file`, in
**≥ 3 of 5 runs**.

**P2.** When `read_text_file` is called on `logo.png`, the server returns
content rather than an error — and that content is mojibake: it contains the
PNG signature bytes decoded as text (`PNG`, `IHDR`) and/or Unicode replacement
characters, not a refusal.

**P3 (secondary, weaker).** Having received garbage, the agent does not
reliably recover by calling `read_media_file` — recovery in fewer than 5 of 5
runs where P1 held.

## What would falsify this

Any of these means the Phase 3 finding does **not** describe real agent
behaviour, and must be recorded as such:

- **F1.** The agent calls `read_media_file` first in ≥ 3 of 5 runs. The names and
  descriptions are sufficient after all; the pair is not confusable in practice.
- **F2.** `read_text_file` errors or refuses on the PNG. Then "regardless of
  extension" is not operative, the failure is contained by the server, and the
  finding is substantially weakened — a wrong tool choice that fails loudly is a
  much smaller problem than one that returns plausible-looking garbage.
- **F3.** The agent asks a clarifying question instead of calling a tool in
  ≥ 3 of 5 runs.
- **F4.** The agent calls `get_file_info` or `list_directory` first to determine
  the file type, then chooses correctly. This would be a real disconfirmation:
  it would mean the ambiguity is resolvable from information the server already
  exposes.

## Decision rule, fixed in advance

- **P1 and P2 both hold** → finding supported. Record in
  `docs/INTERNAL_FINDINGS.md` as verified agent-observable behaviour.
- **P1 holds, P2 fails (F2)** → partially supported. Confusability is real, the
  consequence is not. Downgrade severity; do not report as a data-integrity issue.
- **F1, F3, or F4** → **not supported**. The `read_text_file`/`read_media_file`
  ambiguity finding is retracted from `INTERNAL_FINDINGS.md`, and
  `lint/ambiguity.py`'s treatment of this pair is revisited — a linter that
  flags pairs real agents handle correctly is producing exactly the noise
  Phase 3 was built to avoid.

## What this is not

Whatever the outcome:

- This is **not** a security vulnerability. Everything happens inside the
  server's allowed directories. The worst case is a wasted call, wasted tokens,
  and a possibly-wrong answer.
- This is **not** a finding against the maintainers' competence. Both tools are
  reasonable in isolation; the issue is only visible when an agent must choose
  between them from names and descriptions alone.
- A confirmed result does **not** license reporting this as a defect without
  first following `docs/DISCLOSURE.md`, and the proportionate response is most
  likely a documentation PR.

## The harness is under test too

Per `docs/PHASE4_NOTES.md`, this is the first run of `fixtura` and
`openeval-core` against a real LLM-backed agent. Any crash, hang, or wrong
result from either is a first-class finding, reported separately from anything
about mcplock or the filesystem server, and **not** patched around to get a
green result. Raw logs are kept, not summaries.
