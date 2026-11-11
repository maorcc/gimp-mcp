#!/usr/bin/env python3
"""In-process regression test for headless open_image (PR #67).

`gimp -i` has no display backend, so Gimp.Display.new() raises
"constructor returned NULL" even though the image loaded. _open_image
must keep the image open and report display_opened: False instead of
failing the whole operation.

Stubs gi.repository so the plugin imports without a running GIMP, makes
Gimp.Display.new() raise, and asserts status == success with
display_opened False. Exits 0 on pass, 1 on fail — no GIMP needed.
"""
import importlib.util
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(HERE, os.pardir, "gimp-mcp-plugin.py")

MODES = ("RGB", "Gray", "Indexed", "Unknown")


class FakeImage:
    def __init__(self, ident=1, width=320, height=240):
        self._id, self._w, self._h = ident, width, height

    def get_id(self):
        return self._id

    def get_width(self):
        return self._w

    def get_height(self):
        return self._h

    def get_base_type(self):
        return "RGB"

    def get_layers(self):
        return []


def install_gi_stub(display_raises=False):
    """Importable gi with fake Gimp/GLib/GObject for plugin module import."""
    gi = types.ModuleType("gi")
    gi.require_version = lambda *a, **k: None
    repository = types.ModuleType("gi.repository")

    class Gimp:
        class PlugIn:
            # MCPPlugin.__gtype__ is read at module import (Gimp.main call).
            __gtype__ = "stub-gtype"

        class RunMode:
            NONINTERACTIVE = 1
            INTERACTIVE = 0

        class ImageBaseType:
            RGB, GRAY, INDEXED = MODES[:3]

        class Display:
            @staticmethod
            def new(image):
                if display_raises:
                    raise ValueError("constructor returned NULL")
                # Distinct sentinel so the success path yields a truthy display.
                return object()

        @staticmethod
        def displays_flush():
            pass

        @staticmethod
        def main(gtype, argv):
            pass

        @staticmethod
        def file_load(run_mode, gio_file):
            return FakeImage()

    class GLib:
        class Error(Exception):
            pass

        @staticmethod
        def dtext(domain, msg):
            return msg

    class GObject:
        class ParamFlags:
            READWRITE = 0

    class Gio:
        class File:
            @staticmethod
            def new_for_path(path):
                return ("gio-file", path)

    dtext = GLib.dtext
    GLib.dgettext = dtext
    repository.Gimp, repository.GLib, repository.GObject, repository.Gio = \
        Gimp, GLib, GObject, Gio
    gi.repository = repository
    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repository


def load_plugin():
    spec = importlib.util.spec_from_file_location("gimp_mcp_plugin", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_case(plugin, expect_display_opened):
    """Call _open_image and check the returned metadata and display flag.

    Whether Display.new raises is fixed by install_gi_stub() before the
    plugin module is loaded, so each case loads its own module copy.
    Returns a list of failure descriptions (empty = pass).
    """
    res = plugin._open_image({"file_path": "/tmp/fake-test-image.png"})
    failures = []
    if res.get("status") != "success":
        failures.append(f"status={res.get('status')!r}, expected 'success' "
                        f"(error: {res.get('error')})")
    results = res.get("results", {})
    if results.get("image_id") != 1:
        failures.append(f"image_id={results.get('image_id')!r}, expected 1")
    if results.get("width") != 320:
        failures.append(f"width={results.get('width')!r}, expected 320")
    if results.get("height") != 240:
        failures.append(f"height={results.get('height')!r}, expected 240")
    if results.get("color_mode") != "RGB":
        failures.append(f"color_mode={results.get('color_mode')!r}, expected 'RGB'")
    if results.get("display_opened") is not expect_display_opened:
        failures.append(f"display_opened={results.get('display_opened')!r}, "
                        f"expected {expect_display_opened}")
    return failures


def main():
    # Case 1: headless — Display.new raises, image must survive with
    # display_opened False.
    install_gi_stub(display_raises=True)
    case1 = load_plugin()
    f1 = run_case(case1.MCPPlugin(), False)

    # Case 2: graphical success path — Display.new succeeds; a regression
    # that always reports False would be caught here.
    install_gi_stub(display_raises=False)
    case2 = load_plugin()
    f2 = run_case(case2.MCPPlugin(), True)

    failures = [f"headless case: {f}" for f in f1] + \
               [f"graphical case: {f}" for f in f2]

    if failures:
        print("FAIL: test_open_image_headless")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS: test_open_image_headless — _open_image reports "
          "display_opened False when Gimp.Display.new() fails and True when "
          "it succeeds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
