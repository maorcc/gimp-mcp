#!/usr/bin/env python3
"""Regression test for Tools > MCP > Check / Restart (issue #92).

GIMP runs each menu click in a fresh plug-in process, so the Check and
Restart handlers must find the server over its socket rather than through
self.running. This test runs a real MCP server (accept thread + client
threads) on a free localhost port and calls the menu handlers on a separate
MCPPlugin instance that has never started a server, like a menu-click
process would.

Stubs gi.repository so the plugin imports without a running GIMP.
Exits 0 on pass, 1 on fail.
"""
import importlib.util
import os
import socket
import sys
import threading
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(HERE, os.pardir, "gimp-mcp-plugin.py")

SUCCESS, EXECUTION_ERROR = "SUCCESS", "EXECUTION_ERROR"


def install_gi_stub():
    """Install a fake gi.repository with just enough of Gimp/GLib/GObject to import the plug-in."""
    gi = types.ModuleType("gi")
    gi.require_version = lambda *a, **k: None
    repository = types.ModuleType("gi.repository")

    class Gimp:
        class PlugIn:
            __gtype__ = "stub-gtype"

        class RunMode:
            INTERACTIVE, NONINTERACTIVE = 0, 1

        class PDBStatusType:
            pass

        @staticmethod
        def main(gtype, argv):
            pass

        @staticmethod
        def message(text):
            pass

    Gimp.PDBStatusType.SUCCESS = SUCCESS
    Gimp.PDBStatusType.EXECUTION_ERROR = EXECUTION_ERROR

    class GLib:
        class Error(Exception):
            pass

        @staticmethod
        def dgettext(domain, msg):
            return msg

    class GObject:
        class ParamFlags:
            READWRITE = 0

    repository.Gimp, repository.GLib, repository.GObject = Gimp, GLib, GObject
    gi.repository = repository
    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repository


def load_plugin():
    """Import gimp-mcp-plugin.py as a module (its file name has a hyphen)."""
    spec = importlib.util.spec_from_file_location("gimp_mcp_plugin", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeProcedure:
    """Stand-in for Gimp.Procedure; handlers' return values are just the PDB status."""

    @staticmethod
    def new_return_values(status, error):
        """Return the status so the test can assert on it."""
        return status


class FakeConfig:
    """Stand-in for Gimp.ProcedureConfig with a fixed run mode."""

    def __init__(self, run_mode=1):
        """run_mode is a Gimp.RunMode value; non-interactive (1) by default."""
        self.run_mode = run_mode

    def get_property(self, name):
        """Return the run mode for the run-mode property."""
        return self.run_mode


def free_port():
    """Return a localhost TCP port that is currently free."""
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def start_server(mod, port):
    """Start a real MCP server in this process, as autostart would."""
    server = mod.MCPPlugin(port=port)
    server.socket = server._bind_listener()
    server.running = True
    thread = threading.Thread(target=server._start_server_thread, daemon=True)
    thread.start()
    return server, thread


def stop_server(server, thread):
    """Stop the server's accept loop and wait for the thread to exit."""
    server.running = False
    thread.join(timeout=5)


def menu_click(mod, handler_name):
    """Run a menu handler on a plug-in instance that never started a server."""
    menu = mod.MCPPlugin()
    messages = []
    menu._report = lambda config, message: messages.append(message)
    status = getattr(menu, handler_name)(FakeProcedure(), FakeConfig(), None)
    return status, " | ".join(messages)


def main():
    """Run every scenario, print PASS/FAIL, and return the process exit code."""
    install_gi_stub()
    mod = load_plugin()
    port = free_port()
    mod.load_settings = lambda: {"autostart": True, "port": port}
    failures = []

    def expect(label, cond, detail):
        """Record a failure (label and detail) when cond is false."""
        if not cond:
            failures.append(f"{label}: {detail}")

    # 1. Server running: Check reports RUNNING on the saved port.
    server, thread = start_server(mod, port)
    status, msg = menu_click(mod, "_run_check")
    expect("check while running", "RUNNING" in msg and str(port) in msg, msg)

    # 1b. Interactive run (a real menu click): the real _report shows the
    # result in GIMP through Gimp.message.
    shown = []
    real_message = mod.Gimp.message
    mod.Gimp.message = shown.append
    try:
        mod.MCPPlugin()._run_check(FakeProcedure(), FakeConfig(run_mode=0), None)
    finally:
        mod.Gimp.message = real_message
    expect("interactive check shows Gimp.message",
           len(shown) == 1 and "RUNNING" in shown[0] and str(port) in shown[0], shown)

    # 2. Restart from the menu, several times; the server must keep answering.
    for i in range(3):
        old_socket = server.socket
        status, msg = menu_click(mod, "_run_restart")
        expect(f"restart #{i + 1}", status == SUCCESS and "restarted" in msg, f"{status}: {msg}")
        expect(f"socket replaced by restart #{i + 1}", server.socket is not old_socket,
               "listener was not re-bound")
        expect(f"probe after restart #{i + 1}",
               mod.probe_listener("localhost", port) == "mcp", "server stopped answering")
    expect("server still running after restarts", server.running and thread.is_alive(),
           "accept thread exited")

    # 3. Server stopped: Check reports STOPPED, Restart fails with a hint.
    stop_server(server, thread)
    status, msg = menu_click(mod, "_run_check")
    expect("check while stopped", "STOPPED" in msg, msg)
    status, msg = menu_click(mod, "_run_restart")
    expect("restart while stopped", status == EXECUTION_ERROR and "No MCP server" in msg,
           f"{status}: {msg}")

    # 4. Another program on the port: reported as a conflict, not as running.
    other = socket.socket()
    other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    other.bind(("localhost", port))
    other.listen(4)

    def junk_replies():
        """Act as an unrelated program: answer every connection with non-MCP JSON."""
        while True:
            try:
                conn, _ = other.accept()
            except OSError:
                return
            conn.sendall(b'{"hello": "not mcp"}')
            conn.close()

    threading.Thread(target=junk_replies, daemon=True).start()
    status, msg = menu_click(mod, "_run_check")
    expect("check with other listener", "in use by another program" in msg.lower(), msg)
    status, msg = menu_click(mod, "_run_restart")
    expect("restart with other listener",
           status == EXECUTION_ERROR and "in use by another program" in msg, f"{status}: {msg}")
    other.close()

    # 5. In-process restart_server on a plug-in with no server is an error, not a crash.
    res = mod.MCPPlugin()._restart_server()
    expect("in-process restart without server", res.get("status") == "error", res)

    # 6. A failed re-bind reports an error and stops the server cleanly.
    server, thread = start_server(mod, free_port())

    def failing_bind():
        """Simulate the port no longer being bindable during a restart."""
        raise OSError("simulated bind failure")

    server._bind_listener = failing_bind
    res = server._restart_server()
    expect("failed rebind reports error", res.get("status") == "error", res)
    thread.join(timeout=5)
    expect("failed rebind stops server", not server.running and not thread.is_alive(),
           "server still running after failed rebind")

    if failures:
        print("FAIL: test_menu_check_restart")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS: test_menu_check_restart - Check and Restart find the server over its socket")
    return 0


if __name__ == "__main__":
    sys.exit(main())
