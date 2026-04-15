#!/usr/bin/env python3
"""Remove background from an image using contiguous (fuzzy) select.

Usage:
    python bg_remove.py --input path/to/image.png --output path/to/output.png
"""
import argparse, socket, json, sys

def cmd(t, params=None):
    s = socket.socket()
    s.settimeout(30)
    s.connect(('127.0.0.1', 9877))
    msg = {'type': t, 'params': params if params is not None else {}}
    s.send(json.dumps(msg).encode() + b'\n')
    r = b''
    while True:
        try:
            d = s.recv(8192)
            if not d: break
            r += d
            try: json.loads(r.decode()); break
            except: continue
        except socket.timeout: break
    s.close()
    try: return json.loads(r.decode().strip())
    except: return {'status': 'error', 'error': 'parse: ' + r.decode()[:120]}

def exec_cmds(code_list):
    s = socket.socket()
    s.settimeout(30)
    s.connect(('127.0.0.1', 9877))
    msg = {'cmds': code_list}
    s.send(json.dumps(msg).encode() + b'\n')
    r = b''
    while True:
        try:
            d = s.recv(8192)
            if not d: break
            r += d
            try: json.loads(r.decode()); break
            except: continue
        except socket.timeout: break
    s.close()
    try: return json.loads(r.decode().strip())
    except: return {'status': 'error', 'error': 'parse: ' + r.decode()[:200]}

parser = argparse.ArgumentParser(description="Remove background from an image via GIMP MCP")
parser.add_argument("--input",  required=True, help="Path to input image")
parser.add_argument("--output", required=True, help="Path to save result PNG")
args = parser.parse_args()

# Close everything and start fresh
r = cmd('list_images', {})
imgs = r.get('results', {}).get('images', [])
for _ in imgs:
    cmd('close_image', {'image_index': 0})

# Open original
r = cmd('open_image', {'file_path': args.input})
print(f"Opened: {r.get('status')}")
if r.get('status') != 'success':
    print(f"ERROR: Could not open {args.input}: {r.get('error', '')}", file=sys.stderr)
    sys.exit(1)

bg_removal_code = r"""
from gi.repository import Gimp, Gegl
import traceback as _tb
try:
    image = Gimp.get_images()[0]
    layer = image.get_layers()[0]

    if not layer.has_alpha():
        layer.add_alpha()

    pdb = Gimp.get_pdb()
    proc = pdb.lookup_procedure("gimp-image-select-contiguous-color")

    # Background sampling — only safe edge zones, never inside the subject.
    # Points are computed as fractions of image dimensions so this works for
    # any canvas size (originally hard-coded for 512x512).
    w = image.get_width()
    h = image.get_height()
    xmax = w - 3
    ymax = h - 3
    top_xs  = [int(w * f) for f in (0.10, 0.20, 0.29, 0.39, 0.49, 0.59, 0.68, 0.78, 0.88, 0.98)]
    side_ys = [int(h * f) for f in (0.10, 0.20, 0.29, 0.39, 0.49, 0.59, 0.68, 0.78)]
    right_ys = [int(h * f) for f in (0.10, 0.20, 0.29, 0.39, 0.49, 0.68)]
    bot_xs  = [int(w * f) for f in (0.20, 0.78)]
    bg_pts = (
        [(x, 3) for x in top_xs] +
        [(3, y) for y in side_ys] +
        [(xmax, y) for y in right_ys] +
        [(3, ymax), *[(x, ymax) for x in bot_xs], (xmax, ymax)]
    )

    for i,(bx,by) in enumerate(bg_pts):
        op = Gimp.ChannelOps.REPLACE if i == 0 else Gimp.ChannelOps.ADD
        cfg = proc.create_config()
        cfg.set_property("image",     image)
        cfg.set_property("operation", op)
        cfg.set_property("drawable",  layer)
        cfg.set_property("x",         float(bx))
        cfg.set_property("y",         float(by))
        proc.run(cfg)

    # Grow 2px to close edge gaps
    gp = pdb.lookup_procedure("gimp-selection-grow")
    if gp:
        c = gp.create_config()
        c.set_property("image", image)
        c.set_property("steps", 2)
        gp.run(c)

    # Feather for soft edges
    fp = pdb.lookup_procedure("gimp-selection-feather")
    if fp:
        c = fp.create_config()
        c.set_property("image",  image)
        c.set_property("radius", 1.5)
        fp.run(c)

    # Delete selected background pixels
    Gimp.Drawable.edit_clear(layer)

    # Clear selection via PDB
    np = pdb.lookup_procedure("gimp-selection-none")
    if np:
        c = np.create_config()
        c.set_property("image", image)
        np.run(c)

    Gimp.displays_flush()
    print("BG_REMOVAL_SUCCESS")
except Exception as _e:
    print("ERROR: " + str(_e))
    print(_tb.format_exc())
"""

print("Running background removal...")
r = exec_cmds([bg_removal_code])
if r.get('status') != 'success':
    print(f"ERROR: Background removal transport failed: {r.get('error', '')}", file=sys.stderr)
    sys.exit(1)
output = (r.get('results') or [''])[0]
print(f"GIMP output: {output}")
if 'BG_REMOVAL_SUCCESS' not in output:
    print(f"ERROR: Background removal failed: {output[:200]}", file=sys.stderr)
    sys.exit(1)

r = cmd('export_image', {'image_index': 0, 'file_path': args.output, 'file_type': 'png'})
print(f"Export: {r.get('status')} -> {args.output}")
if r.get('status') != 'success':
    print(f"ERROR: Export failed: {r.get('error', '')}", file=sys.stderr)
    sys.exit(1)
