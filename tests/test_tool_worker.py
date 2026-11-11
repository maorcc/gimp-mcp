#!/usr/bin/env python3
"""Tests for running tools on the GIMP worker thread instead of the event loop (issue #83).

- Every GIMP tool is registered with FastMCP as an async function, while the module
  keeps the plain sync function.
- Calls sent at the same time run one at a time, in the order they were sent.
- The event loop keeps running while a tool runs.
- Cancelling a running call returns at once; the tool still finishes, and the next
  call starts only after it ends.
- Cancelling a queued call means it never runs, and the calls behind it keep their order,
  even if the worker reaches it before the event loop runs again.
- Over the MCP protocol, a notifications/cancelled message gets the client its
  answer at once.
- A tool that raises reports the error, and the worker keeps serving calls.

No GIMP needed. Run with: uv run tests/test_tool_worker.py
Exits 0 on pass, 1 on fail.
"""
import asyncio
import inspect
import os
import sys
import threading
import time

import anyio
import mcp.types as types
from mcp.shared.exceptions import McpError
from mcp.shared.memory import create_connected_server_and_client_session

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir))

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
check("all tools are registered as async",
      all(inspect.iscoroutinefunction(t.fn) for t in tools),
      str([t.name for t in tools if not inspect.iscoroutinefunction(t.fn)]))
check("module keeps check_server as a sync function",
      not inspect.iscoroutinefunction(server.check_server))
check("tool parameters are unchanged by the wrapper",
      "max_width" in server.mcp._tool_manager.get_tool("get_image_bitmap").parameters["properties"])

# A fake tool, registered the same way as the real ones.
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


release = threading.Event()


@server.gimp_tool(name="_test_gate")
def _test_gate(label: str) -> str:
    """Runs until the test sets `release`."""
    record(f"start {label}")
    release.wait(5)
    record(f"end {label}")
    return label


gate = registered("_test_gate")


@server.gimp_tool(name="_test_fail")
def _test_fail() -> str:
    raise RuntimeError("boom")


def events():
    return [e for e, _ in log]


def at(event):
    return next(t for e, t in log if e == event)


async def wait_for(event, timeout=5):
    try:
        with anyio.fail_after(timeout):
            while event not in events():
                await anyio.sleep(0.005)
    except TimeoutError:
        raise AssertionError(f"timed out after {timeout} s waiting for {event!r}; got {events()}") from None


async def test_order_and_free_loop():
    log.clear()
    results = []
    ticks = []

    async def call(label, seconds):
        results.append(await slow(label=label, seconds=seconds))

    async def ticker():
        for _ in range(20):
            await anyio.sleep(0.02)
            ticks.append(time.monotonic())

    async with anyio.create_task_group() as tg:
        tg.start_soon(ticker)
        # Later calls are shorter, so they'd finish first if they ran in parallel.
        for i, seconds in enumerate([0.3, 0.2, 0.1, 0.05]):
            tg.start_soon(call, str(i), seconds)
            await anyio.sleep(0.01)
    check("concurrent calls finish in the order sent", results == ["0", "1", "2", "3"], str(results))
    check("concurrent calls never overlap",
          events() == [f"{k} {i}" for i in "0123" for k in ("start", "end")], str(events()))
    during = [t for t in ticks if at("start 0") < t < at("end 0")]
    check("event loop keeps running while a tool runs", len(during) >= 5,
          f"{len(during)} ticks during the 0.3 s call")


async def test_cancel_running():
    log.clear()
    started = time.monotonic()
    with anyio.CancelScope() as scope:
        async with anyio.create_task_group() as tg:
            tg.start_soon(lambda: slow(label="a", seconds=0.5))
            await wait_for("start a")
            scope.cancel()
    waited = time.monotonic() - started
    check("cancelling a running call returns at once", waited < 0.3, f"waited {waited:.2f}s")
    check("the cancelled tool is still running", "end a" not in events(), str(events()))
    await slow(label="next", seconds=0.01)
    check("the cancelled tool still finishes", "end a" in events(), str(events()))
    check("the next call starts only after the cancelled one ends",
          at("start next") >= at("end a"), str(events()))


async def test_cancel_queued():
    """A runs; B and C are queued; B is cancelled. B never runs, and C runs after A."""
    log.clear()
    results = []

    async def call(label, seconds):
        results.append(await slow(label=label, seconds=seconds))

    async with anyio.create_task_group() as tg:
        tg.start_soon(call, "A", 0.3)
        await wait_for("start A")
        with anyio.CancelScope() as b_scope:
            async with anyio.create_task_group() as b_group:
                b_group.start_soon(call, "B", 0.01)
                await anyio.sleep(0.02)
                tg.start_soon(call, "C", 0.01)
                await anyio.sleep(0.02)
                b_scope.cancel()
    check("a call cancelled while queued never runs", "start B" not in events(), str(events()))
    check("the calls around it keep their order",
          events() == ["start A", "end A", "start C", "end C"] and results == ["A", "C"],
          f"{events()} {results}")


async def test_cancel_queued_before_loop_runs():
    """The cancel must reach the queued call at once, not on the next loop iteration.

    B is queued behind A. The test cancels B, lets A finish, and blocks the event loop
    while the worker moves on, so nothing scheduled for later can stop B in time.
    """
    log.clear()
    release.clear()
    task_a = asyncio.create_task(gate(label="A"))
    await wait_for("start A")
    task_b = asyncio.create_task(slow(label="B", seconds=0.01))
    await anyio.sleep(0.02)
    task_b.cancel()
    release.set()
    time.sleep(0.3)  # deliberately block the loop while the worker picks the next call
    await asyncio.gather(task_a, task_b, return_exceptions=True)
    await slow(label="after", seconds=0.01)
    check("a queued call cancelled just before the worker reaches it never runs",
          "start B" not in events() and task_b.cancelled(), str(events()))


async def test_protocol_cancel():
    """notifications/cancelled over a real MCP session."""
    log.clear()
    async with create_connected_server_and_client_session(server.mcp) as client:
        outcome = {}

        async def call():
            try:
                await client.call_tool("_test_slow", {"label": "p", "seconds": 0.5})
                outcome["result"] = "returned"
            except McpError as e:
                outcome["result"] = e.error.message
            outcome["at"] = time.monotonic()

        async with anyio.create_task_group() as tg:
            tg.start_soon(call)
            await wait_for("start p")
            request_id = client._request_id - 1
            await client.send_notification(types.ClientNotification(types.CancelledNotification(
                params=types.CancelledNotificationParams(requestId=request_id))))
            sent = time.monotonic()
        check("protocol: the client gets the cancellation at once",
              outcome.get("result") == "Request cancelled" and outcome["at"] - sent < 0.3,
              str(outcome))
        r = await client.call_tool("_test_slow", {"label": "q", "seconds": 0.01})
        check("protocol: the next call works and runs after the cancelled one",
              not r.isError and at("start q") >= at("end p"), f"{r} {events()}")


async def test_tool_error():
    """A tool that raises reports the error, and the worker keeps serving calls."""
    log.clear()
    async with create_connected_server_and_client_session(server.mcp) as client:
        r = await client.call_tool("_test_fail", {})
        check("a tool error reaches the client",
              r.isError and "boom" in r.content[0].text, str(r))
        r = await client.call_tool("_test_slow", {"label": "after", "seconds": 0.01})
        check("the worker keeps running after a tool error",
              not r.isError and "end after" in events(), f"{r} {events()}")


async def main():
    await test_order_and_free_loop()
    await test_cancel_running()
    await test_cancel_queued()
    await test_cancel_queued_before_loop_runs()
    await test_protocol_cancel()
    await test_tool_error()


anyio.run(main)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
