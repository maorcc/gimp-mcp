#!/usr/bin/env python3
"""Tests for running tools off the event loop and the runtime sync mode (issue #83).

- Every GIMP tool is registered with FastMCP as an async function, while the module
  keeps the plain sync function.
- Calls sent at the same time run one at a time, in the order they were sent.
- The event loop stays free while a tool runs.
- "sync" mode: a cancelled call waits until the tool finishes.
- "async" mode: a cancelled call returns at once; the tool still finishes, and the
  next call doesn't start until it has.
- set_sync_mode validates and sets GIMP_MCP_SYNC_MODE; check_server reports it.

No GIMP needed. Run with: uv run tests/test_sync_mode.py
Exits 0 on pass, 1 on fail.
"""
import inspect
import os
import sys
import threading
import time

import anyio

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir))

os.environ.pop("GIMP_MCP_SYNC_MODE", None)
import gimp_mcp_server as server  # noqa: E402

failures = []


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}: {name}{f' ({detail})' if detail and not condition else ''}")
    if not condition:
        failures.append(name)


def registered(name):
    return server.mcp._tool_manager.get_tool(name).fn


# Registration: async for FastMCP, sync in the module.
tools = server.mcp._tool_manager.list_tools()
gimp_tools = [t for t in tools if t.name != "set_sync_mode"]
check("all GIMP tools are registered as async",
      all(inspect.iscoroutinefunction(t.fn) for t in gimp_tools),
      str([t.name for t in gimp_tools if not inspect.iscoroutinefunction(t.fn)]))
check("module keeps check_server as a sync function",
      not inspect.iscoroutinefunction(server.check_server))
check("tool parameters are unchanged by the wrapper",
      "max_width" in server.mcp._tool_manager.get_tool("get_image_bitmap").parameters["properties"])

# Fake tools, registered the same way as the real ones.
log = []
log_lock = threading.Lock()


def record(event):
    with log_lock:
        log.append((event, time.monotonic()))


@server.gimp_tool(name="_test_slow")
def _test_slow(label: str, seconds: float) -> str:
    record(f"start {label}")
    time.sleep(seconds)
    record(f"end {label}")
    return label


slow = registered("_test_slow")


def events():
    return [e for e, _ in log]


def at(event):
    return next(t for e, t in log if e == event)


async def test_order_and_free_loop():
    log.clear()
    results = []
    ticks = 0

    async def call(label, seconds):
        results.append(await slow(label=label, seconds=seconds))

    async def ticker():
        nonlocal ticks
        for _ in range(20):
            await anyio.sleep(0.02)
            ticks += 1

    async with anyio.create_task_group() as tg:
        tg.start_soon(ticker)
        # Later calls are shorter, so they'd finish first if they ran in parallel.
        for i, seconds in enumerate([0.3, 0.2, 0.1, 0.05]):
            tg.start_soon(call, str(i), seconds)
            await anyio.sleep(0.01)
    check("concurrent calls finish in the order sent", results == ["0", "1", "2", "3"], str(results))
    check("concurrent calls never overlap",
          events() == [f"{k} {i}" for i in "0123" for k in ("start", "end")], str(events()))
    check("event loop stays free while tools run", ticks == 20, f"ticks={ticks}")


async def cancel_after(delay, label, seconds):
    """Start a call, cancel it after `delay`; return how long the caller waited."""
    started = time.monotonic()
    with anyio.CancelScope() as scope:
        async with anyio.create_task_group() as tg:
            tg.start_soon(lambda: slow(label=label, seconds=seconds))
            await anyio.sleep(delay)
            scope.cancel()
    return time.monotonic() - started


async def test_sync_mode_cancel():
    log.clear()
    os.environ["GIMP_MCP_SYNC_MODE"] = "sync"
    waited = await cancel_after(0.1, "s", 0.5)
    check("sync: a cancelled call waits for the tool to finish", waited >= 0.45, f"waited {waited:.2f}s")
    check("sync: the tool finished", "end s" in events(), str(events()))


async def test_async_mode_cancel():
    log.clear()
    os.environ["GIMP_MCP_SYNC_MODE"] = "async"
    waited = await cancel_after(0.1, "a", 0.5)
    check("async: a cancelled call returns at once", waited < 0.3, f"waited {waited:.2f}s")
    check("async: the tool is still running when the call returns", "end a" not in events(), str(events()))
    # The next call must wait for the abandoned one, not interleave with it.
    await slow(label="next", seconds=0.01)
    check("async: the abandoned tool still finishes", "end a" in events(), str(events()))
    check("async: the next call starts only after the abandoned one ends",
          at("start next") >= at("end a"), str(events()))


async def main():
    await test_order_and_free_loop()
    await test_sync_mode_cancel()
    await test_async_mode_cancel()


anyio.run(main)

# Mode selection.
os.environ.pop("GIMP_MCP_SYNC_MODE", None)
check("default mode is sync", server._sync_mode() == "sync")
os.environ["GIMP_MCP_SYNC_MODE"] = "bogus"
check("an invalid GIMP_MCP_SYNC_MODE falls back to sync", server._sync_mode() == "sync")

r = server.set_sync_mode("ASYNC")
check("set_sync_mode sets async", r == {"status": "success", "sync_mode": "async"}
      and os.environ["GIMP_MCP_SYNC_MODE"] == "async" and server._sync_mode() == "async", str(r))
r = server.set_sync_mode("later")
check("set_sync_mode rejects an unknown mode",
      r["status"] == "error" and server._sync_mode() == "async", str(r))
server.set_sync_mode("sync")
check("set_sync_mode sets sync back", server._sync_mode() == "sync")

# check_server reports the mode, connected or not.
server.GIMP_PORT = 1  # nothing listens here
s = server.check_server(None)
check("check_server reports sync_mode when not connected",
      not s["connected"] and s.get("sync_mode") == "sync", str(s))

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
