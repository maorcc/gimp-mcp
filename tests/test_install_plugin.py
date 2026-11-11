#!/usr/bin/env python3
"""Tests for `gimp-mcp-plugin install-plugin` (issue #94).

Uses a temporary fake home directory, so the real GIMP config is never touched.
Linux/macOS paths are exercised by faking the platform where needed.

Run with the project environment (needs the mcp package): uv run tests/test_install_plugin.py
Exits 0 on pass, 1 on fail.
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir))

import gimp_mcp_server as server  # noqa: E402

failures = []


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}: {name}{f' ({detail})' if detail and not condition else ''}")
    if not condition:
        failures.append(name)


@contextlib.contextmanager
def fake_home(platform="linux"):
    """A temp home dir with GIMP3_DIRECTORY / XDG_CONFIG_HOME cleared and the platform faked."""
    home = Path(tempfile.mkdtemp())
    env = {k: v for k, v in os.environ.items() if k not in ("GIMP3_DIRECTORY", "XDG_CONFIG_HOME")}
    try:
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(Path, "home", return_value=home), \
             mock.patch.object(server.sys, "platform", platform):
            yield home
    finally:
        shutil.rmtree(home)


def run_cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = server._install_plugin_cli(list(args))
    return code, out.getvalue(), err.getvalue()


bundled_version = server._file_plugin_version(server.PLUGIN_SOURCE)
check("bundled plugin exists and reports a version",
      server.PLUGIN_SOURCE.is_file() and bundled_version == server.SERVER_VERSION, str(bundled_version))

if os.name != "nt":
    # Newest 3.x wins across the standard and snap locations; 2.10 and non-version dirs are ignored.
    with fake_home() as home:
        for d in [".config/GIMP/3.0", ".config/GIMP/2.10", ".config/GIMP/themes",
                  "snap/gimp/current/.config/GIMP/3.2"]:
            (home / d).mkdir(parents=True)
        found = server.find_gimp_config_dir()
        check("finds newest GIMP 3.x dir (snap 3.2 over standard 3.0)",
              found == home / "snap/gimp/current/.config/GIMP/3.2", str(found))

    # Numeric, not string, comparison: 3.10 is newer than 3.2.
    with fake_home() as home:
        for d in [".config/GIMP/3.2", ".config/GIMP/3.10"]:
            (home / d).mkdir(parents=True)
        found = server.find_gimp_config_dir()
        check("3.10 beats 3.2", found == home / ".config/GIMP/3.10", str(found))

    with fake_home("darwin") as home:
        (home / "Library/Application Support/GIMP/3.2").mkdir(parents=True)
        found = server.find_gimp_config_dir()
        check("finds the macOS config dir",
              found == home / "Library/Application Support/GIMP/3.2", str(found))

    with fake_home() as home:
        (home / ".config/GIMP/3.2").mkdir(parents=True)
        with mock.patch.dict(os.environ, {"GIMP3_DIRECTORY": str(home / "custom")}):
            found = server.find_gimp_config_dir()
        check("GIMP3_DIRECTORY overrides the search", found == home / "custom", str(found))

    # Fresh install: creates plug-ins/gimp-mcp-plugin/gimp-mcp-plugin.py, executable, same content.
    with fake_home() as home:
        gimp_dir = home / ".config/GIMP/3.2"
        gimp_dir.mkdir(parents=True)
        target = gimp_dir / "plug-ins/gimp-mcp-plugin/gimp-mcp-plugin.py"

        code, out, _ = run_cli("--dry-run")
        check("dry run writes nothing", code == 0 and not target.exists() and "Would install" in out, out)

        code, out, _ = run_cli()
        check("installs into the plug-ins folder",
              code == 0 and target.read_bytes() == server.PLUGIN_SOURCE.read_bytes()
              and "new install" in out and "Restart GIMP" in out, out)
        check("installed plugin is executable", os.access(target, os.X_OK))

        # Update over a plugin from before the version handshake.
        target.write_text("# old plugin without a version\n")
        code, out, _ = run_cli()
        check("updates an old plugin and says what it replaced",
              code == 0 and "replacing version unknown" in out
              and target.read_bytes() == server.PLUGIN_SOURCE.read_bytes(), out)

    with fake_home() as home:
        code, _, err = run_cli()
        check("no GIMP 3 dir: fails with a hint", code == 1 and "--gimp-dir" in err, err)

        explicit = home / "elsewhere/GIMP/3.2"
        code, out, _ = run_cli("--gimp-dir", str(explicit))
        check("--gimp-dir installs there even if nothing was found",
              code == 0 and (explicit / "plug-ins/gimp-mcp-plugin/gimp-mcp-plugin.py").is_file(), out)

# The install command shown in version warnings matches how the server is running.
with mock.patch.object(server, "_running_from_checkout", return_value=False):
    check("installed server suggests the matching uvx version",
          server.install_plugin_command() == f"uvx gimp-mcp-plugin@{server.SERVER_VERSION} install-plugin")
    check("installed server's version warning uses that command",
          server.install_plugin_command() in server.version_status(None)["version_warning"])
with mock.patch.object(server, "_running_from_checkout", return_value=True):
    check("checkout suggests uv run from the checkout",
          server.install_plugin_command().startswith("uv run --directory ")
          and server.install_plugin_command().endswith("gimp_mcp_server.py install-plugin"))

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
