#!/usr/bin/env python3
"""
Demo: AI agent editing loop using get_state_snapshot for visual feedback.
Pipeline:
  1. Open input image
  2. Remove background  -> snapshot (verify BG gone)
  3. Warp mouth corners up (smile) -> snapshot face region (verify smile)
  4. Export final PNG

Usage:
    python agent_edit_demo.py --input path/to/portrait.png --output-dir path/to/output/
"""
import argparse, socket, json, base64, struct, zlib, sys

# ── low-level transport ─────────────────────────────────────────────────────

def cmd(t, params=None):
    s = socket.socket(); s.settimeout(30)
    s.connect(('127.0.0.1', 9877))
    s.send(json.dumps({'type': t, 'params': params or {}}).encode() + b'\n')
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

def exec_gimp(code):
    """Run Python code inside GIMP via the cmds exec path."""
    s = socket.socket(); s.settimeout(30)
    s.connect(('127.0.0.1', 9877))
    s.send(json.dumps({'cmds': [code]}).encode() + b'\n')
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

def snapshot(image_index=0, max_size=512, region=None, label=""):
    """Get visual state snapshot — core AI feedback loop mechanism."""
    params = {'image_index': image_index, 'max_width': max_size, 'max_height': max_size}
    if region:
        params['region'] = {
            'origin_x': region['x'], 'origin_y': region['y'],
            'width': region['w'],    'height':   region['h'],
        }
    r = cmd('get_image_bitmap', params)
    if r.get('status') == 'success':
        b64 = r['results']['image_data']
        raw = base64.b64decode(b64)
        label_str = f" [{label}]" if label else ""
        print(f"  Snapshot{label_str}: {len(raw)//1024}KB  "
              f"{r['results']['width']}x{r['results']['height']}px")
        return raw
    else:
        print(f"  Snapshot FAILED: {r.get('error','')}")
        return None

def save_png(raw_bytes, path):
    with open(path, 'wb') as f:
        f.write(raw_bytes)
    print(f"  Saved: {path}")

parser = argparse.ArgumentParser(description="AI agent editing demo via GIMP MCP")
parser.add_argument("--input",      required=True, help="Path to input portrait image")
parser.add_argument("--output-dir", required=True, dest="output_dir", help="Directory to save snapshots and final result")
args = parser.parse_args()

OUT = args.output_dir.rstrip('/\\')

# ── STEP 0: close previous images, open original ────────────────────────────
print("="*60)
print("STEP 0: Open original image")
r = cmd('list_images', {})
for _ in r.get('results', {}).get('images', []):
    cmd('close_image', {'image_index': 0})

r = cmd('open_image', {'file_path': args.input})
print(f"  Opened: {r.get('status')}  id={r.get('results',{}).get('image_id')}")
if r.get('status') != 'success':
    print(f"ERROR: Could not open {args.input}: {r.get('error', '')}", file=sys.stderr)
    sys.exit(1)

# ── STEP 1: Snapshot — original state ───────────────────────────────────────
print()
print("STEP 1: Snapshot BEFORE edits (original)")
raw = snapshot(label="original")
if raw: save_png(raw, f'{OUT}/snap_01_original.png')

# ── STEP 2: Remove background ───────────────────────────────────────────────
print()
print("STEP 2: Remove background")

bg_code = r"""
from gi.repository import Gimp, Gegl
import traceback as _tb
try:
    image = Gimp.get_images()[0]
    layer = image.get_layers()[0]
    if not layer.has_alpha(): layer.add_alpha()
    pdb  = Gimp.get_pdb()
    proc = pdb.lookup_procedure("gimp-image-select-contiguous-color")
    bg_pts = [
        (50,3),(100,3),(150,3),(200,3),(250,3),(300,3),(350,3),(400,3),(450,3),(505,3),
        (3,50),(3,100),(3,150),(3,200),(3,250),(3,300),(3,350),(3,400),
        (509,50),(509,100),(509,150),(509,200),(509,250),(509,350),
        (3,509),(100,509),(509,509),(400,509),
    ]
    for i,(bx,by) in enumerate(bg_pts):
        op = Gimp.ChannelOps.REPLACE if i==0 else Gimp.ChannelOps.ADD
        cfg = proc.create_config()
        cfg.set_property("image",image); cfg.set_property("operation",op)
        cfg.set_property("drawable",layer); cfg.set_property("x",float(bx)); cfg.set_property("y",float(by))
        proc.run(cfg)
    gp = pdb.lookup_procedure("gimp-selection-grow")
    if gp:
        c=gp.create_config(); c.set_property("image",image); c.set_property("steps",2); gp.run(c)
    fp = pdb.lookup_procedure("gimp-selection-feather")
    if fp:
        c=fp.create_config(); c.set_property("image",image); c.set_property("radius",1.5); fp.run(c)
    Gimp.Drawable.edit_clear(layer)
    np = pdb.lookup_procedure("gimp-selection-none")
    if np:
        c=np.create_config(); c.set_property("image",image); np.run(c)
    Gimp.displays_flush()
    print("BG_REMOVED")
except Exception as e:
    print("BG_ERROR: " + str(e))
    print(_tb.format_exc())
"""
r = exec_gimp(bg_code)
if r.get('status') != 'success':
    print(f"ERROR: Background removal transport failed: {r.get('error', '')}", file=sys.stderr)
    sys.exit(1)
output = (r.get('results') or [''])[0]
print(f"  GIMP: {output.strip()}")
if 'BG_REMOVED' not in output:
    print(f"ERROR: Background removal failed: {output[:200]}", file=sys.stderr)
    sys.exit(1)

# ── STEP 3: Snapshot — after BG removal ─────────────────────────────────────
print()
print("STEP 3: Snapshot AFTER background removal (agent verifies BG gone)")
raw = snapshot(label="no-bg")
if raw: save_png(raw, f'{OUT}/snap_02_nobg.png')

# Also zoom into face area for the agent to check
print("  Zooming into face region for detail check...")
raw_face = snapshot(region={'x': 140, 'y': 80, 'w': 240, 'h': 300}, label="face-region")
if raw_face: save_png(raw_face, f'{OUT}/snap_03_face_detail.png')

# ── STEP 4: Smile edit — paint smile over neutral mouth ─────────────────────
print()
print("STEP 4: Edit smile — paint smile arc over mouth")

# Coordinates confirmed from snap_03_face_detail.png (face zoomed 140-380, 80-380):
# Full-image mouth area: corners ~(210,358) and (300,358), center dips to (255,370)
# Skin tone sampled from forehead area of the character
smile_code = r"""
from gi.repository import Gimp, Gegl
import math, traceback as _tb
try:
    image = Gimp.get_images()[0]
    layer = image.get_layers()[0]
    pdb   = Gimp.get_pdb()

    # ── helpers ──────────────────────────────────────────────────────────────
    def set_fg(hex_color):
        Gimp.context_set_foreground(Gegl.Color.new(hex_color))

    def pencil_arc(drawable, x_start, x_end, cx, cy_center, cy_corner, steps=50, brush_sz=3.0):
        # Draw a parabolic arc with the pencil tool (flat coord list).
        # a < 0 → opens downward in screen coords (smile ⌣)
        a = (cy_corner - cy_center) / float((x_start - cx) ** 2)
        pts = []
        for i in range(steps + 1):
            x = x_start + (x_end - x_start) * i / steps
            y = a * (x - cx) ** 2 + cy_center
            pts.extend([x, y])
        Gimp.context_set_brush_size(brush_sz)
        Gimp.pencil(drawable, pts)

    def fill_rect(image, layer, x, y, w, h, feather=0.0):
        # Fill a rectangle with the current foreground color (optional feather px).
        sel_proc = pdb.lookup_procedure("gimp-image-select-rectangle")
        if sel_proc:
            cfg = sel_proc.create_config()
            cfg.set_property("image",     image)
            cfg.set_property("operation", Gimp.ChannelOps.REPLACE)
            cfg.set_property("x",         x)
            cfg.set_property("y",         y)
            cfg.set_property("width",     w)
            cfg.set_property("height",    h)
            sel_proc.run(cfg)
        if feather > 0:
            fp = pdb.lookup_procedure("gimp-selection-feather")
            if fp:
                c = fp.create_config(); c.set_property("image", image)
                c.set_property("radius", feather); fp.run(c)
        Gimp.Drawable.edit_fill(layer, Gimp.FillType.FOREGROUND)
        np = pdb.lookup_procedure("gimp-selection-none")
        if np:
            c = np.create_config(); c.set_property("image", image); np.run(c)

    image.undo_group_start()
    Gimp.context_push()
    try:
        Gimp.context_set_opacity(100.0)
        Gimp.context_set_paint_mode(Gimp.LayerMode.NORMAL)

        # ── 1. Sample real skin color from forehead then cover mouth ──────
        try:
            pixel = layer.get_pixel(255, 55)  # forehead area
            bpp  = pixel[0]
            data = list(pixel[1])
            skin_hex = "#{:02x}{:02x}{:02x}".format(data[0], data[1], data[2])
        except Exception:
            skin_hex = "#f0b090"  # fallback anime skin tone
        set_fg(skin_hex)
        fill_rect(image, layer, 193, 341, 129, 42, feather=4.0)

        # ── 2. Upper lip dark line — thin arc ────────────────────────────
        # corners=(210,352), center=(255,362)  → narrow top of mouth
        set_fg("#7a2a2a")
        pencil_arc(layer, 210, 300, 255, 362, 352, steps=50, brush_sz=2.0)

        # ── 3. Smile arc (lower edge) — the main smile curve ─────────────
        # corners=(210,356), center=(255,370)  → smile ⌣
        set_fg("#8b3030")
        pencil_arc(layer, 210, 300, 255, 370, 356, steps=60, brush_sz=2.5)

        # ── 4. Teeth — small white fill between the two arcs ─────────────
        # Approximate teeth region: x=218-292, y=353-368
        set_fg("#f8f0e8")
        fill_rect(image, layer, 218, 354, 74, 13)

        # ── 5. Re-draw smile arc ON TOP of teeth to clean up ──────────────
        set_fg("#8b3030")
        pencil_arc(layer, 210, 300, 255, 370, 356, steps=60, brush_sz=2.5)

        # ── 6. Lower lip highlight — lighter arc just below smile ─────────
        set_fg("#c06868")
        pencil_arc(layer, 216, 294, 255, 374, 361, steps=40, brush_sz=3.0)

        # ── 7. Corner accents — tiny dots for mouth corners ───────────────
        set_fg("#6a2020")
        Gimp.context_set_brush_size(2.5)
        Gimp.pencil(layer, [208.0, 357.0, 210.0, 357.0])
        Gimp.pencil(layer, [300.0, 357.0, 302.0, 357.0])

    finally:
        Gimp.context_pop()
        image.undo_group_end()

    Gimp.displays_flush()
    print("SMILE_DONE")
except Exception as e:
    print("SMILE_ERROR: " + str(e))
    print(_tb.format_exc())
"""
r = exec_gimp(smile_code)
if r.get('status') != 'success':
    print(f"ERROR: Smile edit transport failed: {r.get('error', '')}", file=sys.stderr)
    sys.exit(1)
output = (r.get('results') or [''])[0]
print(f"  GIMP: {output.strip()}")
if 'SMILE_DONE' not in output:
    print(f"ERROR: Smile edit failed: {output[:200]}", file=sys.stderr)
    sys.exit(1)

# ── STEP 5: Snapshot — after smile edit (zoom into face) ────────────────────
print()
print("STEP 5: Snapshot AFTER smile paint (agent verifies expression change)")
raw = snapshot(label="with-smile")
if raw: save_png(raw, f'{OUT}/snap_04_smile.png')

raw_mouth = snapshot(region={'x': 170, 'y': 310, 'w': 180, 'h': 100}, label="mouth-zoom")
if raw_mouth: save_png(raw_mouth, f'{OUT}/snap_05_mouth_zoom.png')

# ── STEP 6: Export final ─────────────────────────────────────────────────────
print()
print("STEP 6: Export final result")
final_out = f'{OUT}/result_smile_nobg.png'
r = cmd('export_image', {
    'image_index': 0,
    'file_path':   final_out,
    'file_type':   'png',
})
print(f"  Export: {r.get('status')} -> {final_out}")
if r.get('status') != 'success':
    print(f"ERROR: Export failed: {r.get('error', '')}", file=sys.stderr)
    sys.exit(1)

print()
print("="*60)
print(f"DONE. Snapshots saved to {OUT}/")
print("  snap_01_original.png    <- before any edits")
print("  snap_02_nobg.png        <- after BG removal (agent checkpoint)")
print("  snap_03_face_detail.png <- zoomed face (agent checkpoint)")
print("  snap_04_smile.png       <- after smile warp (agent checkpoint)")
print("  snap_05_mouth_zoom.png  <- zoomed mouth (agent fine-check)")
print("  result_smile_nobg.png   <- final exported result")
