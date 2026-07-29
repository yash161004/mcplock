"""Phase 4: test the pre-registered hypothesis in docs/PHASE4_HYPOTHESIS.md.

Drives a real LLM-backed agent against the real filesystem MCP server, records
every step with fixtura, and scores tool selection with OpenEval.

    python scripts/phase4_experiment.py --runs 5

Raw artifacts land in docs/phase4_runs/: one .trace per run (fixtura's own
format) plus a .jsonl of every event in plain text, because a zstd blob nobody
can read is not a verifiable log.

Read docs/PHASE4_NOTES.md first. fixtura and openeval-core are themselves under
test here; failures in them are findings to record, never to patch around.
"""

from __future__ import annotations

import argparse
import asyncio
import binascii
import json
import struct
import sys
import time
import traceback
import zlib
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

RUNS_DIR = REPO / "docs" / "phase4_runs"
SANDBOX = REPO / "sandbox" / "phase4"

# Fixed by the pre-registration. Do not edit to chase a result.
PROMPT = "What's in logo.png? Tell me what it contains."
EXPECTED_TOOL = "read_media_file"
CONFUSABLE_TOOLS = {"read_text_file", "read_file"}
MODEL = os.environ.get("PHASE4_MODEL_ID", "")


def make_png(path: Path, size: int = 64) -> None:
    """Write a real PNG: a solid red square with a blue diagonal.

    Hand-rolled so the experiment has no image-library dependency. The point is
    only that this is a genuine binary PNG, not a text file with a .png name.
    """

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", binascii.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter type 0 for each scanline
        for x in range(size):
            raw.extend((0, 0, 255) if abs(x - y) < 4 else (255, 0, 0))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def setup_sandbox() -> None:
    SANDBOX.mkdir(parents=True, exist_ok=True)
    make_png(SANDBOX / "logo.png")
    (SANDBOX / "notes.txt").write_text(
        "Meeting notes\n- ship the linter\n- write the hypothesis first\n", encoding="utf-8"
    )


def mcp_tools_to_anthropic(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": t["name"],
            "description": t.get("description") or "",
            "input_schema": t.get("inputSchema") or {"type": "object", "properties": {}},
        }
        for t in tools
    ]


def content_blocks_to_tool_result(result: Any) -> tuple[list[dict[str, Any]], str]:
    """Convert an MCP CallToolResult into Anthropic tool_result blocks.

    Images are passed through as real image blocks rather than a placeholder, so
    an agent that picks read_media_file genuinely sees the picture. Substituting
    a stub there would quietly rig P3.
    """
    blocks: list[dict[str, Any]] = []
    plain: list[str] = []

    for item in getattr(result, "content", []) or []:
        kind = getattr(item, "type", None)
        if kind == "text":
            blocks.append({"type": "text", "text": item.text})
            plain.append(item.text)
        elif kind == "image":
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": item.mimeType,
                        "data": item.data,
                    },
                }
            )
            plain.append(f"<image {item.mimeType}, {len(item.data)} base64 chars>")
        else:
            text = json.dumps(getattr(item, "model_dump", lambda **_: str(item))(mode="json"))
            blocks.append({"type": "text", "text": text})
            plain.append(text)

    if not blocks:
        blocks = [{"type": "text", "text": "<empty result>"}]
        plain = ["<empty result>"]

    return blocks, "\n".join(plain)


async def run_once(run_index: int, max_turns: int = 6) -> dict[str, Any]:
    """One independent agent session. Returns the run record."""
    import anthropic
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from fixtura.recorder.recorder import ExecutionRecorder  # fixtura 2.x namespace

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    trace_path = RUNS_DIR / f"run{run_index:02d}.trace"
    events_path = RUNS_DIR / f"run{run_index:02d}.events.jsonl"

    if trace_path.exists():
        trace_path.unlink()

    recorder = ExecutionRecorder(trace_file=trace_path)
    events: list[dict[str, Any]] = []
    step = 0

    def emit(event: dict[str, Any]) -> None:
        recorder.record_event(event)
        events.append(event)

    emit({"event_type": "trace_header", "step_id": 0, "timestamp": time.time()})

    client = anthropic.Anthropic()
    params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", str(SANDBOX)],
    )

    tool_calls: list[dict[str, Any]] = []
    final_text = ""
    stop_reason = None

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            mcp_tools = [t.model_dump(by_alias=True, exclude_none=True, mode="json") for t in listed.tools]
            anthropic_tools = mcp_tools_to_anthropic(mcp_tools)

            messages: list[dict[str, Any]] = [{"role": "user", "content": PROMPT}]

            for _turn in range(max_turns):
                started = time.time()
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=2048,
                    tools=anthropic_tools,
                    messages=messages,
                )
                latency_ms = (time.time() - started) * 1000
                step += 1

                said = "".join(b.text for b in response.content if b.type == "text")
                stop_reason = response.stop_reason

                emit(
                    {
                        "event_type": "llm_call",
                        "step_id": step,
                        "timestamp": time.time(),
                        "prompt": PROMPT if step == 1 else "<continued conversation>",
                        "completion": said,
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "finish_reason": stop_reason,
                        "provider": "anthropic",
                        "model": MODEL,
                        "latency_ms": latency_ms,
                    }
                )

                if said:
                    final_text = said

                uses = [b for b in response.content if b.type == "tool_use"]
                if not uses:
                    break

                messages.append({"role": "assistant", "content": response.content})
                results: list[dict[str, Any]] = []

                for use in uses:
                    started = time.time()
                    try:
                        outcome = await session.call_tool(use.name, use.input)
                        blocks, plain = content_blocks_to_tool_result(outcome)
                        error = None
                    except Exception as exc:  # a failing tool call is data, not a crash
                        blocks = [{"type": "text", "text": f"ERROR: {exc}"}]
                        plain = f"ERROR: {exc}"
                        error = str(exc)

                    step += 1
                    tool_calls.append({"tool_name": use.name, "arguments": use.input})
                    emit(
                        {
                            "event_type": "tool_call",
                            "step_id": step,
                            "timestamp": time.time(),
                            "tool_name": use.name,
                            "arguments": use.input,
                            "response": plain[:8000],
                            "permission_decision": "allowed",
                            "error": error,
                            "latency_ms": (time.time() - started) * 1000,
                        }
                    )
                    results.append(
                        {"type": "tool_result", "tool_use_id": use.id, "content": blocks}
                    )

                messages.append({"role": "user", "content": results})

    events_path.write_text(
        "\n".join(json.dumps(e, default=str) for e in events) + "\n", encoding="utf-8"
    )

    first = tool_calls[0]["tool_name"] if tool_calls else None
    return {
        "run": run_index,
        "model": MODEL,
        "prompt": PROMPT,
        "trace_file": str(trace_path),
        "events_file": str(events_path),
        "tool_calls": tool_calls,
        "first_tool": first,
        "called_expected": any(c["tool_name"] == EXPECTED_TOOL for c in tool_calls),
        "first_is_confusable": first in CONFUSABLE_TOOLS,
        "recovered_to_expected": (
            first in CONFUSABLE_TOOLS
            and any(c["tool_name"] == EXPECTED_TOOL for c in tool_calls)
        ),
        "stop_reason": stop_reason,
        "final_output": final_text,
    }


def score_run(record: dict[str, Any]) -> dict[str, Any]:
    """Score with OpenEval. Failures here are harness findings, not test failures."""
    from openeval.adapters.fixtura import from_fixtura_trace
    from openeval.metrics import ToolSelectionAccuracy
    from openeval.models import EvalTestCase

    try:
        trace = from_fixtura_trace(
            record["trace_file"],
            task_id=f"phase4_run{record['run']:02d}",
            input_text=PROMPT,
            final_output=record["final_output"],
        )
        case = EvalTestCase(
            task_id=f"phase4_run{record['run']:02d}",
            input=PROMPT,
            # Key is "tool" — EvalTestCase.expected_tool_calls is untyped, and
            # the metric does call["tool"]. See H-002 in PHASE4_RESULTS.md.
            expected_tool_calls=[{"tool": EXPECTED_TOOL}],
            expected_final_state={},
            expected_output_contains=[],
            max_steps=12,
            timeout_seconds=120.0,
        )
        result = ToolSelectionAccuracy().score(trace, case)
        return {
            "ok": True,
            "steps_parsed": len(trace.steps),
            "metric": result.metric_name,
            "score": result.score,
            "passed": result.passed,
            "details": result.details,
        }
    except Exception as exc:
        return {
            "ok": False,
            "harness_error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    setup_sandbox()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    records = []
    for index in range(1, args.runs + 1):
        print(f"--- run {index}/{args.runs} ---", flush=True)
        try:
            record = asyncio.run(run_once(index))
        except Exception as exc:
            print(f"  RUN FAILED: {type(exc).__name__}: {exc}", flush=True)
            records.append(
                {"run": index, "run_error": f"{type(exc).__name__}: {exc}",
                 "traceback": traceback.format_exc()}
            )
            continue

        record["openeval"] = score_run(record)
        records.append(record)
        print(f"  tools: {[c['tool_name'] for c in record['tool_calls']]}", flush=True)
        print(f"  first: {record['first_tool']}  openeval: {record['openeval']}", flush=True)

    (RUNS_DIR / "summary.json").write_text(
        json.dumps(records, indent=2, default=str) + "\n", encoding="utf-8"
    )

    completed = [r for r in records if "run_error" not in r]
    confusable = sum(1 for r in completed if r["first_is_confusable"])
    correct = sum(1 for r in completed if r["first_tool"] == EXPECTED_TOOL)

    print(f"\n=== {len(completed)}/{args.runs} runs completed ===")
    print(f"first call was a confusable text reader : {confusable}")
    print(f"first call was {EXPECTED_TOOL:<24}: {correct}")
    print(f"raw artifacts: {RUNS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
