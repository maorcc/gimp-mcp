#!/usr/bin/env python3
"""Regression test for issue #90: failed PDB calls must not report success.

Gimp.Procedure.run() does not raise when GIMP rejects a call; it returns a
value array whose first value is a Gimp.PDBStatusType. The plug-in's
_run_pdb() must turn a non-SUCCESS status into an exception, and
_lookup_pdb() must raise for a missing procedure, so handlers return
{"status": "error"} instead of a false success. Call sites that have a real
alternative for a missing procedure (_blur's GEGL filter, _save_xcf's
Gimp.file_overwrite) must still use it.

Stubs gi.repository so the plugin imports without a running GIMP.
Exits 0 on pass, 1 on fail.
"""
import importlib.util
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(HERE, os.pardir, "gimp-mcp-plugin.py")


class Status:
    """Stand-in for a Gimp.PDBStatusType value (a GEnum with value_nick)."""

    def __init__(self, nick):
        self.value_nick = nick


SUCCESS = Status("success")
EXECUTION_ERROR = Status("execution-error")

# Procedures the fake PDB knows, and what running each returns:
# name -> (status, error message or None). Set per scenario.
PDB_PROCS = {}
CALLS = []  # (what, detail) records of side effects, cleared per scenario


class FakeValueArray:
    """Stand-in for Gimp.ValueArray as returned by Gimp.Procedure.run()."""

    def __init__(self, *values):
        self._values = values

    def index(self, i):
        return self._values[i]

    def length(self):
        return len(self._values)


class FakeProc:
    """Stand-in for Gimp.Procedure that returns a preset status."""

    def __init__(self, name, status, message=None):
        self._name, self._status, self._message = name, status, message

    def get_name(self):
        return self._name

    def create_config(self):
        return types.SimpleNamespace(set_property=lambda *a: None)

    def run(self, cfg):
        CALLS.append(("run", self._name))
        if self._message is None:
            return FakeValueArray(self._status)
        return FakeValueArray(self._status, self._message)


class FakePDB:
    def lookup_procedure(self, name):
        if name not in PDB_PROCS:
            return None
        status, message = PDB_PROCS[name]
        return FakeProc(name, status, message)


class FakeImage:
    def undo_group_start(self):
        pass

    def undo_group_end(self):
        pass

    def get_selected_layers(self):
        return ["layer"]

    def get_layers(self):
        return ["layer"]


def install_gi_stub():
    """Install a fake gi.repository with just enough of Gimp to run the handlers."""
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

        class DesaturateMode:
            LUMINANCE, LUMA, AVERAGE, LIGHTNESS = range(4)

        @staticmethod
        def main(gtype, argv):
            pass

        @staticmethod
        def get_pdb():
            return FakePDB()

        @staticmethod
        def get_images():
            return [FakeImage()]

        @staticmethod
        def displays_flush():
            pass

        @staticmethod
        def file_overwrite(run_mode, image, gio_file):
            CALLS.append(("file_overwrite", gio_file))

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

    class Gio:
        class File:
            @staticmethod
            def new_for_path(path):
                return path

    repository.Gimp, repository.GLib, repository.GObject = Gimp, GLib, GObject
    repository.Gio = Gio
    gi.repository = repository
    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repository


def load_plugin():
    """Import gimp-mcp-plugin.py as a module (its file name has a hyphen)."""
    spec = importlib.util.spec_from_file_location("gimp_mcp_plugin", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def raises(fn, *needles):
    """Return None if fn() raises RuntimeError mentioning every needle, else a reason."""
    try:
        fn()
    except RuntimeError as e:
        missing = [n for n in needles if n not in str(e)]
        return f"error {str(e)!r} lacks {missing}" if missing else None
    return "did not raise"


def scenario(procs):
    """Reset the fake PDB to `procs` and clear recorded calls."""
    PDB_PROCS.clear()
    PDB_PROCS.update(procs)
    CALLS.clear()


def main():
    install_gi_stub()
    mod = load_plugin()
    plugin = mod.MCPPlugin()
    failures = []

    def check(name, problem):
        print(f"{'FAIL' if problem else 'PASS'}: {name}" + (f" ({problem})" if problem else ""))
        if problem:
            failures.append(name)

    # _run_pdb
    ok = FakeProc("p-ok", SUCCESS)
    result = plugin._run_pdb(ok, ok.create_config())
    check("_run_pdb returns the result on SUCCESS",
          None if result.index(0) is SUCCESS else f"got {result.index(0)}")

    bad = FakeProc("p-bad", EXECUTION_ERROR, "Item 'Background' is locked")
    check("_run_pdb raises with the procedure name, status and GIMP's message",
          raises(lambda: plugin._run_pdb(bad, bad.create_config()),
                 "p-bad", "execution-error", "is locked"))

    bare = FakeProc("p-bare", EXECUTION_ERROR)
    check("_run_pdb raises when GIMP gives no message",
          raises(lambda: plugin._run_pdb(bare, bare.create_config()), "p-bare", "execution-error"))

    # _lookup_pdb
    scenario({})
    check("_lookup_pdb raises for a missing procedure",
          raises(lambda: plugin._lookup_pdb("gimp-nope"), "gimp-nope", "not found"))

    # A handler with no alternative: errors must reach the client.
    scenario({"gimp-drawable-desaturate": (SUCCESS, None)})
    r = plugin._desaturate({})
    check("desaturate reports success when GIMP succeeds",
          None if r["status"] == "success" else r.get("error"))

    scenario({"gimp-drawable-desaturate": (EXECUTION_ERROR, "Item 'Background' is locked")})
    r = plugin._desaturate({})
    check("desaturate reports an error when GIMP rejects the call",
          None if r["status"] == "error" and "is locked" in r["error"] else f"got {r}")

    scenario({})
    r = plugin._desaturate({})
    check("desaturate reports an error when the procedure is missing",
          None if r["status"] == "error" and "not found" in r["error"] else f"got {r}")

    # Handlers with an alternative for a missing procedure must still use it.
    scenario({})
    plugin._apply_gegl_filter = lambda image, drawable, op, props: CALLS.append(("gegl", op))
    r = plugin._blur({})
    check("blur falls back to the GEGL filter when plug-in-gauss is missing",
          None if r["status"] == "success" and ("gegl", "gegl:gaussian-blur") in CALLS
          else f"got {r}, calls {CALLS}")

    scenario({"plug-in-gauss": (EXECUTION_ERROR, None)})
    r = plugin._blur({})
    check("blur reports an error when plug-in-gauss fails",
          None if r["status"] == "error" else f"got {r}")

    scenario({})
    r = plugin._save_xcf({"file_path": "/tmp/x.xcf"})
    check("save_xcf falls back to Gimp.file_overwrite when gimp-xcf-save is missing",
          None if r["status"] == "success" and ("file_overwrite", "/tmp/x.xcf") in CALLS
          else f"got {r}, calls {CALLS}")

    scenario({"gimp-xcf-save": (EXECUTION_ERROR, "Permission denied")})
    r = plugin._save_xcf({"file_path": "/tmp/x.xcf"})
    check("save_xcf reports an error when gimp-xcf-save fails",
          None if r["status"] == "error" and "Permission denied" in r["error"] else f"got {r}")

    print(f"\n{'FAILED' if failures else 'PASSED'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
