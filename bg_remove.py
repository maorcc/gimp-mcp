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

    # Background sampling — only safe green/teal zones, never inside character
    bg_pts = [
        # Top green band
        (50,3),(100,3),(150,3),(200,3),(250,3),(300,3),(350,3),(400,3),(450,3),(505,3),
        # Left strip
        (3,50),(3,100),(3,150),(3,200),(3,250),(3,300),(3,350),(3,400),
        # Right strip
        (509,50),(509,100),(509,150),(509,200),(509,250),(509,350),
        # Bottom strip
        (3,509),(100,509),(509,509),(400,509),
    ]

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
output = r.get('results', [''])[0] if r.get('results') else r.get('error', '')
print(f"GIMP output: {output}")

r = cmd('export_image', {'image_index': 0, 'file_path': args.output, 'file_type': 'png'})
print(f"Export: {r.get('status')} -> {args.output}")
if r.get('status') != 'success':
    print(f"ERROR: Export failed: {r.get('error', '')}", file=sys.stderr)
    sys.exit(1)
