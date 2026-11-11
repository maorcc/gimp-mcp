#!/usr/bin/env python3
"""Tests for the plugin/server version handshake (issue #94).

- PLUGIN_VERSION, SERVER_VERSION and pyproject.toml's version must match.
- version_status() reports a match, and warns about an old plugin (including
  one that predates the handshake) or an old server.

Run with the project environment (needs the mcp package): uv run tests/test_version_handshake.py
Exits 0 on pass, 1 on fail.
"""
import copy
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
sys.path.insert(0, ROOT)

import gimp_mcp_server as server  # noqa: E402

failures = []


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}: {name}{f' ({detail})' if detail and not condition else ''}")
    if not condition:
        failures.append(name)


# Versions are kept in sync. The plugin is read as text because it imports gi.
with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
    pyproject_version = tomllib.load(f)["project"]["version"]
with open(os.path.join(ROOT, "gimp-mcp-plugin.py"), encoding="utf-8") as f:
    match = re.search(r'^PLUGIN_VERSION = "([^"]+)"', f.read(), re.MULTILINE)
plugin_version = match.group(1) if match else None

check("plugin defines PLUGIN_VERSION", plugin_version is not None)
check("SERVER_VERSION matches pyproject.toml", server.SERVER_VERSION == pyproject_version,
      f"{server.SERVER_VERSION} != {pyproject_version}")
check("PLUGIN_VERSION matches SERVER_VERSION", plugin_version == server.SERVER_VERSION,
      f"{plugin_version} != {server.SERVER_VERSION}")

# version_status() outcomes, with a fixed server version.
server.SERVER_VERSION = "0.4.0"

s = server.version_status("0.4.0")
check("matching version is ok", s["version_ok"] and "version_warning" not in s, str(s))

s = server.version_status(None)
check("plugin without a version is flagged",
      not s["version_ok"] and "doesn't report a version" in s["version_warning"]
      and "restart GIMP" in s["version_warning"], str(s))

s = server.version_status("0.3.9")
check("older plugin asks to update the plugin",
      not s["version_ok"] and "Update the plugin" in s["version_warning"], str(s))

s = server.version_status("0.10.0")
check("newer plugin asks to update the server (numeric, not string, comparison)",
      not s["version_ok"] and "Update the server" in s["version_warning"], str(s))

s = server.version_status("garbage")
check("unparseable version still warns", not s["version_ok"] and "version_warning" in s, str(s))


# check_server() with a fake connection returning a canned get_gimp_info response.
def fake_connection(response):
    class FakeConnection:
        def __init__(self, host, port):
            pass

        def connect(self):
            pass

        def send_command(self, command_type, params=None):
            return response

    return FakeConnection


server.GimpConnection = fake_connection(
    {"status": "success", "results": {"mcp_plugin_version": "0.4.0",
                                      "version": {"version_method": "3.2.8"}}})
s = server.check_server(None)
check("check_server reports a matching plugin",
      s["connected"] and s["version_ok"] and s["gimp_version"] == "3.2.8", str(s))

for plugin_version, update in [("0.3.9", "Update the plugin"), ("0.10.0", "Update the server")]:
    server.GimpConnection = fake_connection(
        {"status": "success", "results": {"mcp_plugin_version": plugin_version}})
    s = server.check_server(None)
    check(f"check_server warns for plugin {plugin_version}",
          s["connected"] and not s["version_ok"] and update in s.get("version_warning", "")
          and s.get("plugin_version") == plugin_version and s.get("server_version") == "0.4.0",
          str(s))

server.GimpConnection = fake_connection({"status": "error", "error": "boom"})
s = server.check_server(None)
check("check_server reports a get_gimp_info error, not an outdated plugin",
      s["connected"] and "boom" in s.get("error", "") and "version_warning" not in s, str(s))

# get_gimp_info() adds the same version fields to the plugin's info and keeps the rest.
gimp_details = {"version": {"version_method": "3.2.8"}, "directories": {"user_directory": "/tmp/gimp"}}
server.get_gimp_connection = lambda: fake_connection(
    {"status": "success", "results": {"mcp_plugin_version": "0.3.9", **copy.deepcopy(gimp_details)}})(None, None)
s = server.get_gimp_info(None)
check("get_gimp_info warns about an older plugin",
      s.get("version_ok") is False and "Update the plugin" in s.get("version_warning", "")
      and s.get("plugin_version") == "0.3.9" and s.get("server_version") == "0.4.0", str(s))
check("get_gimp_info keeps GIMP's own info",
      all(s.get(key) == value for key, value in gimp_details.items()), str(s))

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
