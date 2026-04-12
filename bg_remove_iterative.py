#!/usr/bin/env python3
"""
Iterative background removal using get_state_snapshot as AI visual feedback.

Loop:
  1. Scan image for remaining background-colored opaque pixels
  2. Run contiguous-select (magic wand) + delete on each found seed point
  3. Snapshot → agent inspects result
  4. Repeat until no BG pixels remain or max iterations hit
"""
import socket, json, base64

# ── transport ───────────────────────────────────────────────────────────────

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
    s = socket.socket(); s.settimeout(60)
    s.connect(('127.0.0.1', 9877))
    s.send(json.dumps({'cmds': [code]}).encode() + b'\n')
    r = b''
    while True:
        try:
            d = s.recv(65536)
            if not d: break
            r += d
            try: json.loads(r.decode()); break
            except: continue
        except socket.timeout: break
    s.close()
    try: return json.loads(r.decode().strip())
    except: return {'status': 'error', 'error': 'parse: ' + r.decode()[:200]}

def snapshot(label="", region=None, max_size=512):
    params = {'image_index': 0, 'max_width': max_size, 'max_height': max_size}
    if region:
        params['region'] = {'origin_x': region['x'], 'origin_y': region['y'],
                            'width': region['w'], 'height': region['h']}
    r = cmd('get_image_bitmap', params)
    if r.get('status') == 'success':
        raw = base64.b64decode(r['results']['image_data'])
        tag = f" [{label}]" if label else ""
        print(f"  Snapshot{tag}: {len(raw)//1024}KB  "
              f"{r['results']['width']}x{r['results']['height']}px")
        return raw
    print(f"  Snapshot FAILED: {r.get('error','')}")
    return None

def save_png(raw, path):
    with open(path, 'wb') as f: f.write(raw)
    print(f"  Saved: {path}")

# ── GIMP helpers (run inside GIMP) ──────────────────────────────────────────

INIT_CODE = r"""
from gi.repository import Gimp, Gegl
import traceback as _tb, json as _json
try:
    image = Gimp.get_images()[0]
    layer = image.get_layers()[0]
    if not layer.has_alpha():
        layer.add_alpha()
    print("INIT_OK w=%d h=%d" % (image.get_width(), image.get_height()))
except Exception as e:
    print("INIT_ERR: " + str(e))
"""

# Scan image for remaining background-colored opaque pixels.
# Background signature: green/teal foliage — G dominates, or blue sky.
# In GIMP 3.2 layer.get_pixel() returns a Gegl.Color; use .get_rgba() for floats.
# Returns JSON list of [x,y] seed candidates on stdout as BGPTS:[...]
SCAN_CODE_TEMPLATE = r"""
from gi.repository import Gimp
import json as _json

image = Gimp.get_images()[0]
layer = image.get_layers()[0]
w = image.get_width()
h = image.get_height()

STEP     = {step}     # grid spacing (px)
THRESHOLD = {thresh}  # green-dominance threshold (0-255 scale)

candidates = []
for gy in range(0, h, STEP):
    for gx in range(0, w, STEP):
        try:
            px   = layer.get_pixel(gx, gy)
            rgba = px.get_rgba()               # returns (r,g,b,a) floats 0..1
            r8 = int(rgba[0] * 255)
            g8 = int(rgba[1] * 255)
            b8 = int(rgba[2] * 255)
            a8 = int(rgba[3] * 255)
            if a8 < 30:            # skip transparent pixels (already removed)
                continue
            # BG signatures:
            #   green foliage  → g > r+THRESH and g > b+(THRESH//2)
            #   teal/cyan BG   → g > r+THRESH and b > r+(THRESH//2)
            #   blue sky       → b > r+20 and b > g+10 and b < 220
            is_green = (g8 > r8 + THRESHOLD) and (g8 > b8 + THRESHOLD // 2)
            is_teal  = (g8 > r8 + THRESHOLD) and (b8 > r8 + THRESHOLD // 2)
            is_sky   = (b8 > r8 + 20) and (b8 > g8 + 10) and (b8 < 220) and (g8 < 200)
            if is_green or is_teal or is_sky:
                candidates.append([gx, gy])
        except Exception:
            pass

print("BGPTS:" + _json.dumps(candidates))
"""

# Remove a batch of seed points via contiguous-select + delete.
REMOVE_CODE_TEMPLATE = r"""
from gi.repository import Gimp
import traceback as _tb
try:
    image = Gimp.get_images()[0]
    layer = image.get_layers()[0]
    pdb   = Gimp.get_pdb()
    proc  = pdb.lookup_procedure("gimp-image-select-contiguous-color")

    pts = {pts}
    for i, (bx, by) in enumerate(pts):
        op = Gimp.ChannelOps.REPLACE if i == 0 else Gimp.ChannelOps.ADD
        cfg = proc.create_config()
        cfg.set_property("image",     image)
        cfg.set_property("operation", op)
        cfg.set_property("drawable",  layer)
        cfg.set_property("x",         float(bx))
        cfg.set_property("y",         float(by))
        proc.run(cfg)

    # Grow 1px to close micro-gaps then feather for soft edge
    gp = pdb.lookup_procedure("gimp-selection-grow")
    if gp:
        c = gp.create_config(); c.set_property("image", image)
        c.set_property("steps", 1); gp.run(c)
    fp = pdb.lookup_procedure("gimp-selection-feather")
    if fp:
        c = fp.create_config(); c.set_property("image", image)
        c.set_property("radius", {feather}); fp.run(c)

    Gimp.Drawable.edit_clear(layer)

    np = pdb.lookup_procedure("gimp-selection-none")
    if np:
        c = np.create_config(); c.set_property("image", image); np.run(c)

    Gimp.displays_flush()
    print("REMOVED_%d_SEEDS" % len(pts))
except Exception as e:
    print("REMOVE_ERR: " + str(e) + _tb.format_exc())
"""

# ── main ────────────────────────────────────────────────────────────────────

OUT = 'C:/localMll/cruellaOutput'
SRC = 'C:/localMll/cruellaOutput/navi_portrait.png'

print("=" * 60)
print("Iterative background removal with snapshot feedback")
print("=" * 60)

# ── Step 0: open fresh image ────────────────────────────────────────────────
print("\nStep 0: Open original")
r = cmd('list_images', {})
for _ in r.get('results', {}).get('images', []):
    cmd('close_image', {'image_index': 0})
r = cmd('open_image', {'file_path': SRC})
print(f"  Opened: {r.get('status')}  id={r.get('results',{}).get('image_id')}")

r = exec_gimp(INIT_CODE)
out = (r.get('results') or [''])[0]
print(f"  Init: {out.strip()}")

# ── Step 1: snapshot original ───────────────────────────────────────────────
print("\nStep 1: Original snapshot (before any removal)")
raw = snapshot(label="original")
if raw: save_png(raw, f'{OUT}/iter_00_original.png')

# ── Step 2: initial broad BG removal (edge-seed pass) ──────────────────────
print("\nStep 2: Initial broad removal from image edges")

INIT_REMOVE = r"""
from gi.repository import Gimp
import traceback as _tb
try:
    image = Gimp.get_images()[0]
    layer = image.get_layers()[0]
    if not layer.has_alpha(): layer.add_alpha()
    pdb  = Gimp.get_pdb()
    proc = pdb.lookup_procedure("gimp-image-select-contiguous-color")

    # Dense edge sampling — top/bottom/left/right strips + corners
    edge_pts = []
    w = image.get_width(); h = image.get_height()
    step = 15
    for x in range(0, w, step):
        edge_pts += [(x, 0), (x, 2), (x, h-1), (x, h-3)]
    for y in range(0, h, step):
        edge_pts += [(0, y), (2, y), (w-1, y), (w-3, y)]

    for i, (bx, by) in enumerate(edge_pts):
        op = Gimp.ChannelOps.REPLACE if i == 0 else Gimp.ChannelOps.ADD
        cfg = proc.create_config()
        cfg.set_property("image",     image)
        cfg.set_property("operation", op)
        cfg.set_property("drawable",  layer)
        cfg.set_property("x",         float(bx))
        cfg.set_property("y",         float(by))
        proc.run(cfg)

    gp = pdb.lookup_procedure("gimp-selection-grow")
    if gp:
        c = gp.create_config(); c.set_property("image", image); c.set_property("steps", 2); gp.run(c)
    fp = pdb.lookup_procedure("gimp-selection-feather")
    if fp:
        c = fp.create_config(); c.set_property("image", image); c.set_property("radius", 1.0); fp.run(c)

    Gimp.Drawable.edit_clear(layer)

    np = pdb.lookup_procedure("gimp-selection-none")
    if np:
        c = np.create_config(); c.set_property("image", image); np.run(c)

    Gimp.displays_flush()
    print("INIT_REMOVED")
except Exception as e:
    print("INIT_ERR: " + str(e))
    print(_tb.format_exc())
"""

r = exec_gimp(INIT_REMOVE)
out = (r.get('results') or [''])[0]
print(f"  GIMP: {out.strip()}")
raw = snapshot(label="after-init")
if raw: save_png(raw, f'{OUT}/iter_01_init.png')

# ── Step 3: iterative refinement loop ───────────────────────────────────────
print("\nStep 3: Iterative refinement")

MAX_ITERS = 12

# Grid step and green-threshold per iteration
# Early passes: coarse grid, strict threshold (only obvious BG)
# Later passes: fine grid, relaxed threshold (catch remnants)
SCHEDULES = [
    # (grid_step, green_threshold, feather_px)
    (25, 30, 1.5),
    (20, 25, 1.5),
    (15, 20, 1.0),
    (12, 18, 1.0),
    (10, 15, 0.8),
    (8,  12, 0.8),
    (6,  10, 0.5),
    (5,   8, 0.5),
    (4,   7, 0.3),
    (3,   6, 0.3),
    (2,   5, 0.3),
    (2,   4, 0.2),
]

for iteration, (step_px, thresh, feather) in enumerate(SCHEDULES[:MAX_ITERS]):
    print(f"\n  Iteration {iteration+1}/{MAX_ITERS}: "
          f"grid={step_px}px  threshold={thresh}  feather={feather}px")

    # Scan for remaining BG pixels
    scan_code = SCAN_CODE_TEMPLATE.replace('{step}', str(step_px)) \
                                   .replace('{thresh}', str(thresh))
    r = exec_gimp(scan_code)
    out_lines = (r.get('results') or [''])[0]

    # Parse BGPTS from output
    bg_pts = []
    for line in out_lines.strip().splitlines():
        if line.startswith('BGPTS:'):
            try:
                bg_pts = json.loads(line[6:])
            except Exception:
                pass

    print(f"    Found {len(bg_pts)} BG candidate pixels")

    if not bg_pts:
        print("    No background pixels detected — done!")
        break

    # Batch seeds (avoid sending thousands at once; contiguous-select
    # from N seeds is O(N*pixels), so cap per-pass at 80 seeds)
    MAX_SEEDS = 80
    seeds = bg_pts[:MAX_SEEDS]
    remove_code = REMOVE_CODE_TEMPLATE \
        .replace('{pts}', repr(seeds)) \
        .replace('{feather}', str(feather))
    r = exec_gimp(remove_code)
    out_rm = (r.get('results') or [''])[0]
    print(f"    GIMP: {out_rm.strip()[:80]}")

    # Snapshot every other iteration as agent checkpoint
    if iteration % 2 == 0 or len(bg_pts) < 20:
        raw = snapshot(label=f"iter-{iteration+1}")
        if raw:
            save_png(raw, f'{OUT}/iter_{iteration+2:02d}_pass{iteration+1}.png')

# ── Step 4: despeckle — catch isolated green pixels contiguous can't reach ───
print("\nStep 4: Despeckle pass (by-color-select on remaining green speckles)")

DESPECKLE_CODE = r"""
from gi.repository import Gimp
import traceback as _tb

try:
    image = Gimp.get_images()[0]
    layer = image.get_layers()[0]
    pdb   = Gimp.get_pdb()
    w     = image.get_width()
    h     = image.get_height()

    # Full 1px scan — collect every remaining green-tinted opaque pixel.
    # Threshold is loose (g > r+8) to catch faded/semi-transparent speckles.
    green_pts = []
    for gy in range(h):
        for gx in range(w):
            rgba = layer.get_pixel(gx, gy).get_rgba()
            r8 = int(rgba[0]*255); g8 = int(rgba[1]*255)
            b8 = int(rgba[2]*255); a8 = int(rgba[3]*255)
            if a8 > 5 and g8 > r8 + 8 and g8 > b8 + 4 and g8 > 15:
                green_pts.append((gx, gy))

    print("SPECKLE_COUNT:" + str(len(green_pts)))

    if green_pts:
        MAX_SPECKLES = 2000
        if len(green_pts) > MAX_SPECKLES:
            print("SPECKLE_CAPPED:" + str(MAX_SPECKLES))
            green_pts = green_pts[:MAX_SPECKLES]

        # Build selection from individual 1×1 rectangles — works on isolated pixels
        # that contiguous-select cannot reach.
        sel_proc = pdb.lookup_procedure("gimp-image-select-rectangle")
        for i, (bx, by) in enumerate(green_pts):
            op = Gimp.ChannelOps.REPLACE if i == 0 else Gimp.ChannelOps.ADD
            cfg = sel_proc.create_config()
            cfg.set_property("image",     image)
            cfg.set_property("operation", op)
            cfg.set_property("x",         bx)
            cfg.set_property("y",         by)
            cfg.set_property("width",     1)
            cfg.set_property("height",    1)
            sel_proc.run(cfg)

        Gimp.Drawable.edit_clear(layer)

        np = pdb.lookup_procedure("gimp-selection-none")
        if np:
            c = np.create_config(); c.set_property("image", image); np.run(c)

        Gimp.displays_flush()
        print("DESPECKLE_DONE:" + str(len(green_pts)))
    else:
        print("DESPECKLE_CLEAN")
except Exception as e:
    print("DESPECKLE_ERR:" + str(e))
    print(_tb.format_exc())
"""

r = exec_gimp(DESPECKLE_CODE)
out = (r.get('results') or [''])[0]
for line in out.strip().splitlines():
    print(f"  GIMP: {line}")

raw = snapshot(label="post-despeckle")
if raw: save_png(raw, f'{OUT}/iter_despeckle.png')

# Corner checks after despeckle
for zone_name, region in [
    ("top-left",  {'x':   0, 'y':   0, 'w': 150, 'h': 150}),
    ("top-right", {'x': 360, 'y':   0, 'w': 150, 'h': 150}),
    ("bot-left",  {'x':   0, 'y': 360, 'w': 150, 'h': 150}),
]:
    raw_z = snapshot(label=zone_name, region=region, max_size=256)
    if raw_z: save_png(raw_z, f'{OUT}/despeckle_{zone_name}.png')

# ── Step 5: final snapshot + export ─────────────────────────────────────────
print("\nStep 5: Final snapshot and export")
raw = snapshot(label="final", max_size=512)
if raw: save_png(raw, f'{OUT}/iter_final.png')

# Zoom into a few critical zones to verify cleanliness
for zone_name, region in [
    ("top-left",  {'x':   0, 'y':   0, 'w': 150, 'h': 150}),
    ("top-right", {'x': 360, 'y':   0, 'w': 150, 'h': 150}),
    ("bot-left",  {'x':   0, 'y': 360, 'w': 150, 'h': 150}),
]:
    raw_z = snapshot(label=zone_name, region=region, max_size=256)
    if raw_z: save_png(raw_z, f'{OUT}/iter_final_{zone_name}.png')

r = cmd('export_image', {
    'image_index': 0,
    'file_path':   f'{OUT}/navi_clean_final.png',
    'file_type':   'png',
})
print(f"\nExport: {r.get('status')} -> navi_clean_final.png")
print("\n" + "=" * 60)
print("Done. Check iter_final.png — should be character-only.")
