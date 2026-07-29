"""Exercise fixtura and openeval-core on realistic trajectories, without an LLM.

    python scripts/phase4_stub_harness.py
    python scripts/phase4_stub_harness.py --scenario header_only -v

Why this exists
---------------
fixtura and openeval-core are under test in this project (see the docstring in
`phase4_experiment.py`). Folding them in as real PyPI dependencies already found
three shipped defects that their own unit tests could not: fixtura 1.x installed
top-level `recorder`/`replay`/`tools` instead of namespacing, openeval-core
0.1.2 resolved but had no `adapters.fixtura` to import, and the bare name
`openeval` on PyPI is an unrelated stub. Those are distribution bugs — only an
outside consumer hits them.

What was never exercised is the *runtime* path on a realistic trajectory. The
only end-to-end evidence is `pipeline_check` in `phase4_p2_and_pipeline.py`: a
hand-built three-event trace. The real agent run (`run01`) died at
`anthropic.AuthenticationError: 401` before reaching either library, leaving a
91-byte header-only trace behind.

This harness closes that gap at zero cost. It replaces only the model — the
part that costs money — with a scripted policy, and keeps everything else real:
a real `@modelcontextprotocol/server-filesystem` subprocess over stdio, real
tool calls, real responses, fixtura's real recorder, OpenEval's real adapter and
metric. The event shapes are copied from `phase4_experiment.run_once` on
purpose, so a trace produced here is structurally what a real run produces.

What it cannot tell you
-----------------------
Nothing about what a real model *chooses*. That is P1 of the pre-registered
hypothesis and genuinely needs an API key. This harness tests the plumbing those
choices would flow through, which is a separate question that was being blocked
by the same missing key.

Findings, not failures
----------------------
A scenario that trips fixtura or OpenEval is recorded in `harness_findings` and
the run continues. Per `docs/PHASE4_NOTES.md`, defects in the libraries under
test are results to report upstream, never obstacles to patch around here. A
non-zero exit means a *finding was recorded*, not that this script is broken.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.phase4_experiment import (  # noqa: E402  (path set above)
    EXPECTED_TOOL,
    PROMPT,
    RUNS_DIR,
    SANDBOX,
    content_blocks_to_tool_result,
    make_png,
)

OUT_PATH = RUNS_DIR / "stub_harness.json"

# Each scenario is a fixed list of tool decisions, standing in for what a model
# would have chosen. Kept deliberately boring and readable: the value is in the
# shape of the trajectory, not in cleverness.
#
#   expect_score — what ToolSelectionAccuracy should return for EXPECTED_TOOL.
#                  None means "no assertion", used where the point is whether the
#                  libraries survive the input at all.
SCENARIOS: dict[str, dict[str, Any]] = {
    "correct_first": {
        "why": "Baseline. The agent picks the right tool immediately.",
        "calls": [("read_media_file", {"path": "logo.png"})],
        "expect_score": 1.0,
    },
    "wrong_then_recover": {
        "why": (
            "The trajectory the hypothesis predicts: read the binary as text, "
            "get garbage back, then correct. Two steps, one of them wrong."
        ),
        "calls": [
            ("read_text_file", {"path": "logo.png"}),
            ("read_media_file", {"path": "logo.png"}),
        ],
        "expect_score": 1.0,
    },
    "wrong_only": {
        "why": "No recovery. The metric must score 0.0, not crash or pass.",
        "calls": [("read_text_file", {"path": "logo.png"})],
        "expect_score": 0.0,
    },
    "tool_error": {
        "why": (
            "A real MCP error, not a simulated one — the path does not exist. "
            "Exercises the error branch of the recorder's tool_call event."
        ),
        "calls": [("read_text_file", {"path": "does_not_exist.txt"})],
        "expect_score": 0.0,
    },
    "long_trajectory": {
        "why": (
            "Twelve steps of realistic wandering. The only prior evidence was a "
            "three-event trace; this checks the recorder and adapter hold up "
            "over a trajectory long enough for step ordering to matter."
        ),
        "calls": [
            ("list_directory", {"path": "."}),
            ("read_text_file", {"path": "notes.txt"}),
            ("list_directory", {"path": "."}),
            ("read_text_file", {"path": "logo.png"}),
            ("get_file_info", {"path": "logo.png"}),
            ("read_media_file", {"path": "logo.png"}),
        ],
        "expect_score": 1.0,
    },
    "header_only": {
        "why": (
            "The edge case run01 actually produced: the run dies before any "
            "step completes, leaving a trace with a header and nothing else. "
            "fixtura wrote 91 bytes; whether OpenEval's adapter can read that "
            "back was never tested."
        ),
        "calls": [],
        "expect_score": None,
    },
}


def ensure_sandbox() -> None:
    """Same fixtures the real experiment uses, so traces are comparable."""
    SANDBOX.mkdir(parents=True, exist_ok=True)
    logo = SANDBOX / "logo.png"
    if not logo.exists():
        make_png(logo)
    notes = SANDBOX / "notes.txt"
    if not notes.exists():
        notes.write_text(
            "Scratch notes for the stub harness. Plain text, safe to read.\n",
            encoding="utf-8",
        )


async def record_scenario(name: str, spec: dict[str, Any], verbose: bool) -> dict[str, Any]:
    """Drive the scripted calls against the real server, recording with fixtura.

    Mirrors the event shapes emitted by `phase4_experiment.run_once`. The only
    substitution is the model: an `llm_call` event is still recorded before each
    tool call, with provider "scripted", so the trace has the same structure a
    real run would.
    """
    from fixtura.recorder.recorder import ExecutionRecorder
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    trace_path = RUNS_DIR / f"stub_{name}.trace"
    events_path = RUNS_DIR / f"stub_{name}.events.jsonl"
    if trace_path.exists():
        trace_path.unlink()

    findings: list[dict[str, str]] = []
    events: list[dict[str, Any]] = []
    recorder = ExecutionRecorder(trace_file=trace_path)

    def emit(event: dict[str, Any]) -> None:
        try:
            recorder.record_event(event)
        except Exception as exc:  # a recorder that rejects a valid event is a finding
            findings.append(
                {
                    "library": "fixtura",
                    "where": f"record_event({event.get('event_type')})",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        events.append(event)

    emit({"event_type": "trace_header", "step_id": 0, "timestamp": time.time()})

    tool_calls: list[dict[str, Any]] = []
    step = 0

    if spec["calls"]:
        params = StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", str(SANDBOX)],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                for tool_name, arguments in spec["calls"]:
                    step += 1
                    emit(
                        {
                            "event_type": "llm_call",
                            "step_id": step,
                            "timestamp": time.time(),
                            "prompt": PROMPT if step == 1 else "<continued conversation>",
                            "completion": f"I'll call {tool_name}.",
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "finish_reason": "tool_use",
                            "provider": "scripted",
                            "model": "scripted-stub",
                            "latency_ms": 0.0,
                        }
                    )

                    started = time.time()
                    try:
                        outcome = await session.call_tool(tool_name, arguments)
                        _blocks, plain = content_blocks_to_tool_result(outcome)
                        error = None
                    except Exception as exc:  # a failing tool call is data, not a crash
                        plain = f"ERROR: {exc}"
                        error = str(exc)

                    step += 1
                    tool_calls.append({"tool_name": tool_name, "arguments": arguments})
                    emit(
                        {
                            "event_type": "tool_call",
                            "step_id": step,
                            "timestamp": time.time(),
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "response": plain[:8000],
                            "permission_decision": "allowed",
                            "error": error,
                            "latency_ms": (time.time() - started) * 1000,
                        }
                    )
                    if verbose:
                        tag = "ERR " if error else "ok  "
                        print(f"    {tag}{tool_name} -> {plain[:60]!r}")

    events_path.write_text(
        "\n".join(json.dumps(e, default=str) for e in events) + "\n", encoding="utf-8"
    )

    return {
        "trace_file": str(trace_path),
        "events_file": str(events_path),
        "trace_bytes": trace_path.stat().st_size if trace_path.exists() else 0,
        "events_recorded": len(events),
        "tool_calls": tool_calls,
        "findings": findings,
    }


def score_scenario(name: str, spec: dict[str, Any], recorded: dict[str, Any]) -> dict[str, Any]:
    """Read the trace back through OpenEval and score it.

    Everything here is wrapped: the question being asked is whether these
    libraries survive real input, so an exception is the answer, not an abort.
    """
    from openeval.adapters.fixtura import from_fixtura_trace
    from openeval.metrics import ToolSelectionAccuracy
    from openeval.models import EvalTestCase

    findings: list[dict[str, str]] = list(recorded["findings"])
    out: dict[str, Any] = {"scored": False}

    try:
        trace = from_fixtura_trace(
            recorded["trace_file"],
            task_id=f"stub_{name}",
            input_text=PROMPT,
            final_output="<scripted run, no model output>",
        )
    except Exception as exc:
        findings.append(
            {
                "library": "openeval-core",
                "where": f"from_fixtura_trace({name})",
                "error": f"{type(exc).__name__}: {exc}",
                "detail": traceback.format_exc(limit=3),
            }
        )
        out["findings"] = findings
        return out

    out["steps_parsed"] = len(trace.steps)

    case = EvalTestCase(
        task_id=f"stub_{name}",
        input=PROMPT,
        # Key is "tool", not "tool_name" — expected_tool_calls is untyped and the
        # metric indexes call["tool"]. See H-002 in docs/PHASE4_RESULTS.md.
        expected_tool_calls=[{"tool": EXPECTED_TOOL}],
        expected_final_state={},
        expected_output_contains=[],
        max_steps=24,
        timeout_seconds=120.0,
    )

    try:
        result = ToolSelectionAccuracy().score(trace, case)
    except Exception as exc:
        findings.append(
            {
                "library": "openeval-core",
                "where": f"ToolSelectionAccuracy.score({name})",
                "error": f"{type(exc).__name__}: {exc}",
                "detail": traceback.format_exc(limit=3),
            }
        )
        out["findings"] = findings
        return out

    out.update(
        {
            "scored": True,
            "metric": result.metric_name,
            "score": result.score,
            "passed": result.passed,
            "details": getattr(result, "details", None),
        }
    )

    expected = spec["expect_score"]
    if expected is not None and result.score != expected:
        findings.append(
            {
                "library": "openeval-core",
                "where": f"ToolSelectionAccuracy.score({name})",
                "error": (
                    f"expected score {expected} for tool sequence "
                    f"{[c['tool_name'] for c in recorded['tool_calls']]}, got {result.score}"
                ),
            }
        )

    # Every recorded tool_call should survive the round trip. A trace that loses
    # steps between writing and parsing is the failure mode that would silently
    # invalidate every result built on this pipeline.
    expected_steps = len(recorded["tool_calls"])
    parsed_tools = [s for s in trace.steps if getattr(s, "tool_name", None)]
    if expected_steps and len(parsed_tools) != expected_steps:
        findings.append(
            {
                "library": "fixtura/openeval-core",
                "where": f"round trip ({name})",
                "error": (
                    f"recorded {expected_steps} tool calls but parsed back "
                    f"{len(parsed_tools)}"
                ),
            }
        )

    out["findings"] = findings
    return out


def probe_api_contracts() -> list[dict[str, str]]:
    """Check assumptions a consumer would reasonably make about these APIs.

    Separate from the scenarios: these are about the shape of the contract, not
    about whether a trajectory scores correctly.
    """
    import tempfile

    from fixtura.recorder.recorder import ExecutionRecorder

    findings: list[dict[str, str]] = []

    # A recorder should not modify the dict it was handed. `phase4_experiment`
    # keeps each event after recording it, to write the plain-text .events.jsonl
    # that exists precisely so the run is auditable without decoding a zstd blob.
    # If the recorder edits those dicts, that log silently stops being a record of
    # what the caller emitted.
    probe_dir = Path(tempfile.mkdtemp())
    recorder = ExecutionRecorder(trace_file=probe_dir / "probe.trace")
    event = {"event_type": "trace_header", "step_id": 0, "timestamp": 1.0}
    before = dict(event)
    try:
        recorder.record_event(event)
    except Exception as exc:
        findings.append(
            {
                "library": "fixtura",
                "where": "record_event (contract probe)",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        return findings

    if event != before:
        changed = {
            k: f"{before.get(k)!r} -> {event.get(k)!r}"
            for k in set(before) | set(event)
            if before.get(k) != event.get(k)
        }
        findings.append(
            {
                "library": "fixtura",
                "where": "ExecutionRecorder.record_event",
                "error": (
                    "mutates the caller's event dict in place instead of copying: "
                    f"{changed}. Callers that retain the dict — as "
                    "phase4_experiment does to write .events.jsonl — end up "
                    "logging the recorder's values, not their own. The step_id "
                    "type also changes from int to str."
                ),
            }
        )

    return findings


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", choices=sorted(SCENARIOS), help="run just one")
    ap.add_argument("-v", "--verbose", action="store_true", help="print each tool call")
    args = ap.parse_args()

    ensure_sandbox()
    names = [args.scenario] if args.scenario else list(SCENARIOS)

    results: dict[str, Any] = {}
    all_findings: list[dict[str, str]] = []

    contract_findings = probe_api_contracts()
    if contract_findings:
        print("\n[api contracts]")
        for f in contract_findings:
            print(f"    FINDING [{f['library']}] {f['where']}: {f['error']}")
    all_findings.extend(contract_findings)

    for name in names:
        spec = SCENARIOS[name]
        print(f"\n[{name}] {spec['why']}")
        recorded = await record_scenario(name, spec, args.verbose)
        scored = score_scenario(name, spec, recorded)

        entry = {**{k: v for k, v in recorded.items() if k != "findings"}, **scored}
        results[name] = entry
        all_findings.extend(entry.get("findings", []))

        if entry.get("scored"):
            print(
                f"    trace {entry['trace_bytes']}B | "
                f"{entry['steps_parsed']} steps parsed | "
                f"score {entry['score']} (passed={entry['passed']})"
            )
        else:
            print(f"    trace {entry['trace_bytes']}B | NOT SCORED — see findings")
        for f in entry.get("findings", []):
            print(f"    FINDING [{f['library']}] {f['where']}: {f['error']}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "note": (
                    "Scripted trajectories, no LLM. Tests the fixtura -> OpenEval "
                    "runtime path only; says nothing about real model behaviour."
                ),
                "scenarios": results,
                "api_contract_findings": contract_findings,
                "harness_findings": all_findings,
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"\n{len(names)} scenario(s), {len(all_findings)} finding(s) -> {OUT_PATH}")
    if all_findings:
        print("Findings are results about the libraries under test. Report them; do not")
        print("patch around them here. See docs/PHASE4_NOTES.md.")
    return 1 if all_findings else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
