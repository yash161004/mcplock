"""Phase 4 partials that need no LLM credentials.

Two independent things, kept separate on purpose:

1. **P2** — a claim about the *server*, not the agent: does `read_text_file`
   return decoded garbage for a PNG rather than refusing? Callable directly.
   This is a real result against the real server.

2. **Harness pipeline validation** — drive fixtura's recorder and OpenEval's
   scorer with a *synthetic* trace of known shape, to confirm the plumbing works
   and to surface bugs in either. This is NOT an experiment result and its
   numbers say nothing about agent behaviour.

P1 and P3 need a real LLM and remain unrun.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.phase4_experiment import PROMPT, RUNS_DIR, SANDBOX, setup_sandbox  # noqa: E402

PNG_SIGNATURE_MARKERS = ("PNG", "IHDR", "IDAT", "IEND", "�")


async def test_p2() -> dict:
    """Call read_text_file and read_media_file on a real PNG. No agent involved."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", str(SANDBOX)],
    )

    out: dict = {}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            for tool in ("read_text_file", "read_media_file"):
                try:
                    result = await session.call_tool(tool, {"path": str(SANDBOX / "logo.png")})
                    blocks = []
                    for item in result.content or []:
                        kind = getattr(item, "type", "?")
                        if kind == "text":
                            blocks.append({"type": "text", "text": item.text})
                        elif kind == "image":
                            blocks.append(
                                {
                                    "type": "image",
                                    "mime": item.mimeType,
                                    "base64_len": len(item.data),
                                }
                            )
                        else:
                            blocks.append({"type": kind})
                    out[tool] = {
                        "raised": False,
                        "is_error": bool(getattr(result, "isError", False)),
                        "blocks": blocks,
                    }
                except Exception as exc:
                    out[tool] = {"raised": True, "error": f"{type(exc).__name__}: {exc}"}

    text = out.get("read_text_file", {})
    returned_text = ""
    if not text.get("raised"):
        returned_text = "".join(b.get("text", "") for b in text.get("blocks", []))

    out["_verdict"] = {
        "read_text_file_refused": bool(text.get("raised") or text.get("is_error")),
        "markers_found": sorted(m for m in PNG_SIGNATURE_MARKERS if m in returned_text),
        "returned_chars": len(returned_text),
        "sample_repr": repr(returned_text[:220]),
    }
    return out


def validate_pipeline() -> dict:
    """Synthetic trace through fixtura -> OpenEval. Plumbing check only."""
    from openeval.adapters.fixtura import from_fixtura_trace
    from openeval.metrics import ToolSelectionAccuracy
    from openeval.models import EvalTestCase
    from recorder.recorder import ExecutionRecorder

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    trace_path = RUNS_DIR / "pipeline_check.trace"
    if trace_path.exists():
        trace_path.unlink()

    recorder = ExecutionRecorder(trace_file=trace_path)
    now = time.time()
    for event in [
        {"event_type": "trace_header", "step_id": 0, "timestamp": now},
        {
            "event_type": "llm_call",
            "step_id": 1,
            "timestamp": now,
            "prompt": PROMPT,
            "completion": "I'll read the file.",
            "input_tokens": 10,
            "output_tokens": 5,
            "finish_reason": "tool_use",
            "provider": "synthetic",
            "model": "synthetic",
        },
        {
            "event_type": "tool_call",
            "step_id": 2,
            "timestamp": now,
            "tool_name": "read_text_file",
            "arguments": {"path": "logo.png"},
            "response": "�PNG garbage",
            "permission_decision": "allowed",
        },
        {
            "event_type": "tool_call",
            "step_id": 3,
            "timestamp": now,
            "tool_name": "read_media_file",
            "arguments": {"path": "logo.png"},
            "response": "<image image/png>",
            "permission_decision": "allowed",
        },
    ]:
        recorder.record_event(event)

    findings: list[str] = []
    report: dict = {"trace_file": str(trace_path)}

    try:
        trace = from_fixtura_trace(trace_path, task_id="pipeline", input_text=PROMPT)
        report["steps_parsed"] = len(trace.steps)
        report["tool_names_parsed"] = [s.tool_name for s in trace.steps if s.tool_name]
    except Exception as exc:
        report["adapter_error"] = f"{type(exc).__name__}: {exc}"
        report["adapter_traceback"] = traceback.format_exc()
        findings.append("openeval.adapters.fixtura.from_fixtura_trace raised")
        report["harness_findings"] = findings
        return report

    # The key is "tool", not "tool_name". EvalTestCase.expected_tool_calls is an
    # untyped list[dict], and TraceStep names the same concept `tool_name`, so
    # the wrong key is easy to reach for — see H-002 in PHASE4_RESULTS.md.
    for label, expected in [
        ("expects_read_media_file", [{"tool": "read_media_file"}]),
        ("expects_only_a_tool_never_called", [{"tool": "search_files"}]),
    ]:
        case = EvalTestCase(
            task_id="pipeline",
            input=PROMPT,
            expected_tool_calls=expected,
            expected_final_state={},
            expected_output_contains=[],
            max_steps=12,
            timeout_seconds=60.0,
        )
        try:
            result = ToolSelectionAccuracy().score(trace, case)
            report[label] = {
                "score": result.score,
                "passed": result.passed,
                "details": result.details,
            }
        except Exception as exc:
            report[label] = {"error": f"{type(exc).__name__}: {exc}"}
            findings.append(f"ToolSelectionAccuracy.score raised for {label}")

    report["harness_findings"] = findings
    return report


def main() -> int:
    setup_sandbox()

    print("=== P2: real server behaviour on a real PNG (no agent) ===")
    p2 = asyncio.run(test_p2())
    print(json.dumps(p2["_verdict"], indent=2))

    print("\n=== harness pipeline validation (synthetic trace, NOT a result) ===")
    pipeline = validate_pipeline()
    print(json.dumps({k: v for k, v in pipeline.items() if "traceback" not in k}, indent=2))

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "p2_and_pipeline.json").write_text(
        json.dumps({"p2": p2, "pipeline": pipeline}, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"\nraw output: {RUNS_DIR / 'p2_and_pipeline.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
