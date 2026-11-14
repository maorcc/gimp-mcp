#!/usr/bin/env python3
"""Live regression test for issue #90: a PDB call GIMP rejects must return an error.

Creates a small low-contrast image, locks its layer's pixels and calls
auto_levels on it. GIMP rejects the edit, so the tool must return
status "error" and the pixels must be unchanged. It then unlocks the layer
and calls auto_levels again, which must succeed and stretch the contrast;
that shows the lock is what blocked the first call.

Requires the GIMP MCP plugin running on localhost:9877 (GIMP_MCP_PORT
overrides the port). Watch GIMP while it runs: the rejected call should not
open a modal error dialog (see #110). Exits 0 on pass, 1 on fail.
"""
import json
import os
import socket
import sys

HOST, PORT = '127.0.0.1', int(os.environ.get('GIMP_MCP_PORT', 9877))
LAYER = 'pdb-status-test'


def send(msg, timeout=60):
    """Send one JSON message to the plugin socket and return the decoded reply."""
    with socket.create_connection((HOST, PORT), timeout=timeout) as s:
        s.sendall(json.dumps(msg).encode() + b'\n')
        buf = b''
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            try:
                return json.loads(buf.decode())
            except json.JSONDecodeError:
                continue
    return {'status': 'error', 'error': 'parse: ' + buf.decode()[:200]}


def cmd(t, params=None):
    """Send a {type, params} tool command."""
    return send({'type': t, 'params': params or {}})


def py(*lines):
    """Run Python lines in the plugin's persistent context; return the printed output."""
    r = send({'cmds': list(lines)})
    if r.get('status') != 'success':
        fail(f"exec failed: {r.get('error', r)}")
    return ''.join(r.get('results') or []).strip()


def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def create_image():
    """Create a display-less low-contrast RGB image; return its image_index."""
    py(
        "from gi.repository import Gimp, Gegl",
        "_pdbtest_img = Gimp.Image.new(200, 200, Gimp.ImageBaseType.RGB)",
        f"_pdbtest_layer = Gimp.Layer.new(_pdbtest_img, '{LAYER}', 200, 200, "
        "Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)",
        "_pdbtest_img.insert_layer(_pdbtest_layer, None, 0)",
        "Gimp.context_push()",
        # A paint opacity or mode left over in the running GIMP would change the fill.
        "Gimp.context_set_opacity(100.0)",
        "Gimp.context_set_paint_mode(Gimp.LayerMode.NORMAL)",
        "Gimp.context_set_foreground(Gegl.Color.new('rgb(0.45, 0.45, 0.45)'))",
        "_pdbtest_layer.edit_fill(Gimp.FillType.FOREGROUND)",
        "_pdbtest_img.select_rectangle(Gimp.ChannelOps.REPLACE, 50, 50, 100, 100)",
        "Gimp.context_set_foreground(Gegl.Color.new('rgb(0.55, 0.55, 0.55)'))",
        "_pdbtest_layer.edit_fill(Gimp.FillType.FOREGROUND)",
        "Gimp.Selection.none(_pdbtest_img)",
        "Gimp.context_pop()",
    )
    return image_index()


def image_index():
    """Return the current index of the test image in Gimp.get_images()."""
    out = py("print(next(i for i, im in enumerate(Gimp.get_images()) "
             "if im.get_id() == _pdbtest_img.get_id()))")
    return int(out)


def std_dev():
    """Return the value-channel std-dev of the test layer."""
    r = cmd('get_histogram', {'image_index': image_index(), 'layer_name': LAYER})
    if r.get('status') != 'success':
        fail(f"get_histogram: {r.get('error', r)}")
    return float(r['results']['std_dev'])


def auto_levels():
    return cmd('auto_levels', {'image_index': image_index(), 'layer_name': LAYER})


def main():
    created = False
    try:
        create_image()
        created = True
        before = std_dev()
        print(f"low-contrast image created, std_dev={before:.4f}")

        py("_pdbtest_layer.set_lock_content(True)")
        r = auto_levels()
        print(f"auto_levels on locked layer: {json.dumps(r)[:300]}")
        if r.get('status') != 'error':
            fail("auto_levels on a locked layer reported success")
        locked_after = std_dev()
        if abs(locked_after - before) > 1e-6:
            fail(f"pixels changed on a locked layer: std_dev {before:.4f} -> {locked_after:.4f}")
        print("PASS: locked layer -> status error, pixels unchanged")

        py("_pdbtest_layer.set_lock_content(False)")
        r = auto_levels()
        if r.get('status') != 'success':
            fail(f"auto_levels on the unlocked layer failed: {r.get('error', r)}")
        after = std_dev()
        if after <= before:
            fail(f"auto_levels did not stretch the unlocked layer: std_dev {before:.4f} -> {after:.4f}")
        print(f"PASS: unlocked layer -> success, std_dev {before:.4f} -> {after:.4f}")
        return 0
    finally:
        if created:
            try:
                py("_pdbtest_img.delete()")
            except SystemExit:
                print("  (cleanup) could not delete the test image", file=sys.stderr)


if __name__ == '__main__':
    sys.exit(main())
