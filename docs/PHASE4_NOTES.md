# Phase 4 — validation notes

Read this before starting Phase 4. Not applicable to Phases 1–3.

Phase 4 runs `snapshot` + `lint` against 10–15 real public MCP servers, using
the `validate` extra (`fixtura` + `openeval-core`) to drive a real LLM-backed
agent.

## The harness is under test too

This is the **first end-to-end run of fixtura and OpenEval against a real
LLM-backed agent**. Both have so far only been validated against scripted/toy
agents, with zero external users. Phase 4 is therefore two experiments at once:
mcplock against real servers, and the harness against a real agent.

That changes how failures are handled:

1. **Harness failures are findings.** Any crash, hang, wrong result, or
   surprising behavior from fixtura or openeval-core gets logged and reported
   back as a first-class finding — the same standard as a finding against a
   third-party MCP server. Do not treat it as environment noise to route around.

2. **Do not patch around harness bugs to make Phase 4 tests pass.** A green
   Phase 4 obtained by working around a fixtura/OpenEval bug destroys the point
   of the run. Surface the bug, stop, and decide deliberately. Catching these is
   part of the deliverable.

3. **Keep raw output, not summaries.** Persist unedited logs, stdout/stderr,
   recordings, and exit codes from every run under a Phase 4 artifacts
   directory. Narrated summaries are not a substitute — the raw behavior has to
   be verifiable directly, by someone who was not present for the run.

## Ordering

Findings against *third-party* servers still follow
[DISCLOSURE.md](DISCLOSURE.md). Harness findings are against the author's own
projects, so no disclosure window applies — report them immediately.
