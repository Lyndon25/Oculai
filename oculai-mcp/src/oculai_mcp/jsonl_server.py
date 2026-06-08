"""JSONL Server — stdio bridge for Oculai tools from TypeScript/Electron.

Replaces the MCP JSON-RPC transport with a simple JSONL protocol
so the Electron main process can call Oculai tools via child_process.spawn.

Protocol (one JSON object per line, newline-delimited):

    Inbound (stdin):
    {"id": "req-1", "method": "oculai_create_run", "params": {"job_title": "...", "jd_text": "..."}}

    Outbound (stdout):
    {"id": "req-1", "ok": true, "result": {"run_id": "...", "status": "draft"}}
    {"id": "req-1", "ok": false, "error": {"code": "TOOL_ERROR", "message": "..."}}

    System messages (sent to stderr for logging):
    {"type": "ready", "tools": 41, "pid": 12345}
    {"type": "shutdown", "reason": "stdin closed"}

All stderr output is JSONL system messages for the TypeScript host to parse.
Stdout is exclusively for tool call responses.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import traceback
from typing import Any

# Ensure the package root is on sys.path for imports
_package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _package_dir not in sys.path:
    sys.path.insert(0, _package_dir)

from oculai_mcp.tools.errors import OculaiError

# Async-safe shutdown flag set by signal handlers
_shutdown_requested = False


def _handle_signal(signum: int, _frame: Any) -> None:
    """Async-safe signal handler: set a flag for the event loop to pick up.

    Does NOT call sys.exit() or write to stderr — both are unsafe in signal handlers.
    The main loop polls _shutdown_requested and exits cleanly.
    """
    global _shutdown_requested
    _shutdown_requested = True


async def main() -> None:
    """Run the JSONL server on stdin/stdout.

    Reads JSONL requests from stdin, dispatches to tool handlers from
    tool_registry, and writes JSONL responses to stdout.
    """
    # Lazy import after path setup
    from oculai_mcp.tool_registry import TOOL_REGISTRY, get_tool

    # Signal readiness to host
    _emit_system({"type": "ready", "tools": len(TOOL_REGISTRY), "pid": os.getpid()})

    # Read lines from stdin asynchronously
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    try:
        while not _shutdown_requested:
            line = await reader.readline()
            if not line:
                # EOF — stdin closed, graceful shutdown
                _emit_system({"type": "shutdown", "reason": "stdin closed"})
                break

            line_str = line.decode("utf-8").strip()
            if not line_str:
                continue

            try:
                request = json.loads(line_str)
            except json.JSONDecodeError as exc:
                _emit_response({"id": None, "ok": False, "error": {"code": "PARSE_ERROR", "message": str(exc)}})
                continue

            req_id = request.get("id")
            method = request.get("method", "")
            params = request.get("params", {})

            handler = get_tool(method)
            if handler is None:
                _emit_response({
                    "id": req_id,
                    "ok": False,
                    "error": {
                        "code": "UNKNOWN_TOOL",
                        "message": f"Tool '{method}' not found. Available: {list(TOOL_REGISTRY.keys())}",
                    },
                })
                continue

            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(params)
                else:
                    result = handler(params)
                _emit_response({"id": req_id, "ok": True, "result": result})
            except OculaiError as exc:
                error_payload: dict[str, Any] = {
                    "code": exc.code,
                    "message": exc.message,
                }
                if exc.details is not None:
                    error_payload["details"] = exc.details
                _emit_response({
                    "id": req_id,
                    "ok": False,
                    "error": error_payload,
                })
            except Exception as exc:
                _emit_response({
                    "id": req_id,
                    "ok": False,
                    "error": {
                        "code": "TOOL_ERROR",
                        "message": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                })

    except asyncio.CancelledError:
        _emit_system({"type": "shutdown", "reason": "cancelled"})
    finally:
        if _shutdown_requested:
            _emit_system({"type": "shutdown", "reason": "signal received"})
        # Give the event loop a moment to flush
        try:
            await asyncio.wait_for(asyncio.sleep(0.1), timeout=1.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass


def _emit_system(msg: dict[str, Any]) -> None:
    """Write a system message to stderr (JSONL)."""
    sys.stderr.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def _emit_response(msg: dict[str, Any]) -> None:
    """Write a tool response to stdout (JSONL)."""
    sys.stdout.write(json.dumps(msg, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    asyncio.run(main())
