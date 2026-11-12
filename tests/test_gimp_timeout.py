#!/usr/bin/env python3
"""Tests for the configurable GIMP reply timeout (GIMP_MCP_TIMEOUT).

- GIMP_MCP_TIMEOUT sets how long a command waits for GIMP; unset, empty or invalid
  values fall back to 300 s.
- A command GIMP doesn't answer in time fails with a message that names the timeout,
  warns that GIMP may still be running it, and points at GIMP_MCP_TIMEOUT.
- check_server and get_gimp_info report the timeout in effect.

No GIMP needed: a fake plugin socket stands in for it.
Run with: uv run tests/test_gimp_timeout.py
Exits 0 on pass, 1 on fail.
"""
import json
import os
import socket
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir))

import gimp_mcp_server as server  # noqa: E402

failures = []


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}: {name}{f' ({detail})' if detail and not condition else ''}")
    if not condition:
        failures.append(name)


def timeout_for(value):
    if value is None:
        os.environ.pop("GIMP_MCP_TIMEOUT", None)
    else:
        os.environ["GIMP_MCP_TIMEOUT"] = value
    return server._timeout_from_env()


# Parsing the environment variable.
check("unset uses the default", timeout_for(None) == 300)
check("empty uses the default", timeout_for("  ") == 300)
check("whole seconds are accepted", timeout_for("900") == 900)
check("fractions are accepted", timeout_for("2.5") == 2.5)
for bad in ["abc", "0", "-5", "nan", "inf"]:
    check(f"invalid value {bad!r} uses the default", timeout_for(bad) == 300)
os.environ.pop("GIMP_MCP_TIMEOUT", None)


class FakePlugin:
    """Listens like the GIMP plugin. Replies to get_gimp_info, and stays silent
    for any other command, like GIMP busy with a long one."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("localhost", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                client, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def _handle(self, client):
        with client:
            data = b""
            while not data.endswith(b"\n"):
                chunk = client.recv(8192)
                if not chunk:
                    return
                data += chunk
            command = json.loads(data)
            if command["type"] == "get_gimp_info":
                reply = {"status": "success", "results": {
                    "version": {"version_method": "3.2.0"},
                    "mcp_plugin_version": server.SERVER_VERSION,
                }}
                client.sendall(json.dumps(reply).encode())
            else:
                time.sleep(2)

    def close(self):
        self.sock.close()


plugin = FakePlugin()
server.GIMP_PORT = plugin.port
server.GimpConnection.__init__.__defaults__ = (server.GIMP_HOST, plugin.port)
server.GIMP_TIMEOUT = 0.3

# A command GIMP doesn't answer in time.
started = time.monotonic()
try:
    server.GimpConnection().send_command("exec", {"args": ["exec", ["pass"]]})
    error = None
except Exception as e:
    error = str(e)
elapsed = time.monotonic() - started
check("silent GIMP raises an error", error is not None)
check("the wait follows GIMP_TIMEOUT", server.GIMP_TIMEOUT * 0.9 <= elapsed < 1.5,
      f"{elapsed:.2f} s")
error = error or ""
check("error names the timeout", "within 0.3 s" in error, error)
check("error warns GIMP may still be running it", "may still be running" in error, error)
check("error points at GIMP_MCP_TIMEOUT", "GIMP_MCP_TIMEOUT" in error, error)

# The timeout in effect is reported.
status = server.check_server(None)
check("check_server connects to the fake plugin", status.get("connected") is True, str(status))
check("check_server reports timeout_seconds", status.get("timeout_seconds") == 0.3, str(status))
info = server.get_gimp_info(None)
check("get_gimp_info reports timeout_seconds", info.get("timeout_seconds") == 0.3, str(info))

plugin.close()
server.GimpConnection.__init__.__defaults__ = (server.GIMP_HOST, 1)
server.GIMP_PORT = 1
status = server.check_server(None)
check("check_server reports timeout_seconds when not connected",
      status.get("connected") is False and status.get("timeout_seconds") == 0.3, str(status))

print(f"\n{'All tests passed' if not failures else f'{len(failures)} failed: {failures}'}")
sys.exit(1 if failures else 0)
