#!/usr/bin/env python3
"""Continuous editing regression test: composite + selective recolor.

Exercises a realistic AI-agent editing loop end-to-end against the
GIMP MCP plugin. Input assets live next to this script under
`files/` and all snapshots/exports go to `output/`.

Pipeline order is strict: BG removal FIRST, hair recolor SECOND (on the
standalone cutout so blonde selection doesn't see any bg pixels), and
only THEN is the new background image set and the composite built.

  1. Open the character portrait (files/winry_joy.png).

  2. Run nine independent "bg filters" over the whole image and
     combine them by per-pixel voting. Each filter is one view of the
     image — B&W darkness, blue-hue dominance, low saturation, low
     local gradient, near-border spatial prior, etc. — and each filter
     contributes up to 50 NESTED closed regions ("paths") at rising
     strictness into a combined pool (9 × 50 = up to 450 paths total).
     A pixel gets +1 vote for every path it falls inside; deeply-bg
     pixels land inside many paths per filter, subject pixels land
     inside few. Phase 1: pixels with ≥ 1100 votes (out of a pool
     of 9 filters × 200 paths = 1800 paths total) have their alpha
     rewritten to 0 (genuinely transparent — the alpha channel is
     added to the layer if absent). Phase 2 computes a cumulative
     4-direction sqrt-damped score per pixel and then runs strict
     4-connectivity union-find connected-component labelling;
     only the SINGLE biggest connected region is retained, the
     main_matrix score is zeroed everywhere else and those pixels
     are dropped (alpha = 0). Phase 3 looks at the main_matrix
     scores inside the biggest region, computes the 1st
     percentile, and drops just the bottom 1% by score — minimal
     erosion. Phase 4 ("fuzzy border") finally runs a separable
     2-pass box blur with radius 2 on the alpha channel only —
     the sharp 0/255 cutoff at the subject edge becomes a soft
     gradient so the cutout composites smoothly into the new
     background instead of looking like cardboard cutout. This
     replaces
     earlier palette/color-select approaches, which failed on starry
     backgrounds whose tones overlapped with the character's hair
     shadows.

  3. Detect the character's hair and recolor it red (still on the
     standalone cutout, before any compositing):
       - Select by color seeded on a golden-yellow hair tone. Since
         the bg is already transparent, the selection can only touch
         hair pixels (alpha-zero pixels are skipped by the tool).
       - Rotate the YELLOW hue range by −60° (yellow → red) preserving
         per-pixel luminance, then deepen the resulting RED range so
         shadow strands go deep crimson.
       - Push extra red into highlights and shadows via color-balance
         with preserve-luminosity for vivid red hair with visible
         shadow roots and bright curl highlights.

  4. Open the night landscape (files/bg_night_2048.png) as a second
     image, load the recolored cutout as a new layer on top, scale
     it to ~70% of the canvas height, and anchor it near the
     lower-centre of the scene.

  5. Export the final composite PNG.

Usage:
    python tests/continuous_edit_test/continuous_edit_test.py
    python tests/continuous_edit_test/continuous_edit_test.py \\
        --character PATH --background PATH --out DIR

Requires the GIMP MCP plugin to be running (GIMP open, server on :9877).
Exits 0 on success, 1 on any transport or GIMP-side failure.
"""
import argparse
import base64
import json
import os
import socket
import sys

HOST, PORT = '127.0.0.1', 9877


# ── transport ────────────────────────────────────────────────────────────────

def _send(msg, timeout=60, recv_size=65536, parse_truncate=200):
    s = socket.socket()
    s.settimeout(timeout)
    s.connect((HOST, PORT))
    s.send(json.dumps(msg).encode() + b'\n')
    buf = b''
    while True:
        try:
            chunk = s.recv(recv_size)
            if not chunk:
                break
            buf += chunk
            try:
                json.loads(buf.decode())
                break
            except json.JSONDecodeError:
                continue
        except socket.timeout:
            break
    s.close()
    try:
        return json.loads(buf.decode().strip())
    except json.JSONDecodeError:
        return {'status': 'error', 'error': 'parse: ' + buf.decode()[:parse_truncate]}


def cmd(t, params=None):
    return _send({'type': t, 'params': params or {}})


def exec_gimp(code):
    return _send({'cmds': [code]})


# ── helpers ──────────────────────────────────────────────────────────────────

def snapshot(path, image_index=0, max_size=640):
    """Pull a PNG snapshot of the current image and save it."""
    r = cmd('get_image_bitmap', {
        'image_index': image_index,
        'max_width':   max_size,
        'max_height':  max_size,
    })
    if r.get('status') != 'success':
        print(f"    Snapshot FAILED: {r.get('error', '')}", file=sys.stderr)
        return False
    raw = base64.b64decode(r['results']['image_data'])
    with open(path, 'wb') as f:
        f.write(raw)
    print(f"    Snapshot saved: {path}  ({len(raw)//1024}KB)")
    return True


def require_success(label, r):
    if r.get('status') != 'success':
        print(f"ERROR: {label}: {r.get('error', '')}", file=sys.stderr)
        sys.exit(1)
    return r


def run_gimp(label, code):
    """Run a Python block inside GIMP, fail fast on transport or script error."""
    r = exec_gimp(code)
    if r.get('status') != 'success':
        print(f"ERROR: {label} transport failed: {r.get('error', '')}", file=sys.stderr)
        sys.exit(1)
    out = (r.get('results') or [''])[0]
    for line in out.strip().splitlines():
        print(f"    GIMP: {line}")
    if 'ERROR' in out or 'Traceback' in out:
        print(f"ERROR: {label} plugin error:\n{out}", file=sys.stderr)
        sys.exit(1)
    return out


# ── CLI ──────────────────────────────────────────────────────────────────────

_here = os.path.dirname(os.path.abspath(__file__))
parser = argparse.ArgumentParser(description="Continuous editing regression test via GIMP MCP")
parser.add_argument('--character',  default=os.path.join(_here, 'files', 'winry_joy.png'),     help='Character portrait PNG')
parser.add_argument('--background', default=os.path.join(_here, 'files', 'bg_night_2048.png'), help='Background landscape PNG')
parser.add_argument('--out',        default=os.path.join(_here, 'output'),                      help='Output directory')
args = parser.parse_args()

char_path = os.path.abspath(args.character)
bg_path   = os.path.abspath(args.background)
out_dir   = os.path.abspath(args.out)

for p in (char_path, bg_path):
    if not os.path.isfile(p):
        print(f"ERROR: input not found: {p}", file=sys.stderr)
        sys.exit(1)
os.makedirs(out_dir, exist_ok=True)


# ── close any open images so the test starts from a clean slate ─────────────

print("=" * 72)
print("STEP 0: Reset GIMP workspace")
# Close every open image via a direct exec — the MCP close_image
# dispatch uses `Gimp.display_list()` which was removed in GIMP 3.2,
# so on plugins loaded before that fix lands it leaks ghost images
# across runs.
run_gimp('reset workspace', r"""
from gi.repository import Gimp
before = len(Gimp.get_images())
gd = getattr(Gimp, "get_displays", None)
if gd is None:
    gd = getattr(Gimp, "display_list", None)
for img in list(Gimp.get_images()):
    if gd is not None:
        try:
            for d in list(gd()):
                try:
                    if d.get_image().get_id() == img.get_id():
                        Gimp.Display.delete(d)
                except Exception:
                    pass
        except Exception:
            pass
    # Delete the image itself regardless of whether we could close its displays.
    try:
        img.delete()
    except Exception:
        pass
remaining = len(Gimp.get_images())
print("RESET_OK before=" + str(before) + " remaining=" + str(remaining))
""")


# ── STEP 1: open character, capture original state ──────────────────────────

print("\nSTEP 1: Open character portrait")
r_open = require_success('open character', cmd('open_image', {'file_path': char_path}))
char_image_id = r_open.get('results', {}).get('image_id')
print(f"    char image_id = {char_image_id}")
snapshot(f'{out_dir}/01_character_original.png')


# ── STEP 2: 9-filter per-pixel voting bg removal ────────────────────────────
# Color-based detection is too fragile here: starry-night bg shares
# dark tones with hair shadows, so any palette-based pass over-eats the
# subject. Instead, produce 9 different "views" of the whole image —
# each view is a filter that highlights bg regions using a different
# criterion (luminance, hue, saturation, gradient, spatial prior, ...).
# Each filter's bg region is a closed "path" covering some set of
# pixels. We pool the 9 paths into a per-pixel vote map: a pixel gets
# +1 vote for every path it falls inside. Pixels with >= 5 votes are
# flagged as consensus-bg and get their alpha set to 0 (removed).
# Pixels with fewer votes are kept — the subject survives because its
# distinctive features (flesh, hair, outlines) fail most of the filters.
#
# The 9 "paths" / filters:
#   1. B&W darkness        — luminance < ~25%
#   2. Dark + unsaturated  — low L AND max-min small (flat dark bg)
#   3. Low local gradient  — 4-neighbour gradient small (flat regions)
#   4. Blue dominant       — B > R and B > G (night-sky bias)
#   5. Low saturation      — (max-min)/max < 0.25
#   6. Posterize dark      — falls into the bottom 2-bit bucket
#   7. Blue hue band       — strongly blue/violet hue angle
#   8. Dark value          — max(R,G,B) < 70
#   9. Near-border spatial — within 10% of the image border

print("\nSTEP 2: 9-filter per-pixel voting bg removal")
bg_removal = r"""
from gi.repository import Gimp, Gegl
import traceback as _tb
try:
    Gegl.init(None)
    image = Gimp.get_images()[0]
    base  = image.get_layers()[0]
    # Make absolutely sure there's an alpha channel before we read or
    # write any bytes — without this, writing 0 into the alpha slot
    # can end up flattened to opaque white downstream.
    if not base.has_alpha():
        base.add_alpha()
    print("  base has_alpha=%s" % base.has_alpha())
    W, H = image.get_width(), image.get_height()
    N    = W * H
    FMT  = "R'G'B'A u8"
    rect = Gegl.Rectangle.new(0, 0, W, H)

    # Pull raw RGBA bytes for the whole image (list of ints, length N*4).
    raw = base.get_buffer().get(rect, 1.0, FMT, Gegl.AbyssPolicy.CLAMP)

    # Per-channel flat arrays for fast tight loops.
    Rc = raw[0::4]
    Gc = raw[1::4]
    Bc = raw[2::4]
    Ac = raw[3::4]

    # Pre-computed totals used for filter thresholds / stats.
    opaque_idx = [i for i in range(N) if Ac[i] > 32]
    total_op   = len(opaque_idx)
    print("  image %dx%d, %d opaque pixels" % (W, H, total_op))

    # Border margin for spatial filter 9: ~10% of the short side.
    border = max(1, int(0.10 * min(W, H)))
    border_x1 = border
    border_x2 = W - border
    border_y1 = border
    border_y2 = H - border

    # Each of the 9 filters contributes up to PATHS_PER_FILTER nested
    # paths into the combined pool. For filter f with metric m_f and
    # operating range [m_min, m_max] for "this is bg", path k (k in
    # 0..PATHS_PER_FILTER-1) covers pixels whose metric value lies
    # more than k/(PATHS_PER_FILTER-1) of the way into the bg-side of
    # the range. A deeply-bg pixel satisfies most paths from many
    # filters → high vote. A subject pixel satisfies few → low vote.
    PATHS_PER_FILTER = 200
    TOTAL_PATHS = 9 * PATHS_PER_FILTER
    votes = [0] * N
    fc = [0] * 10   # total path-hits per filter (sum across all pixels)

    # Nested-range helper:
    #   value_ok_when_less : path k triggers when metric < lo + k*step
    #     returns how many k in [0..N-1] with (lo + k*step) > metric
    #   value_ok_when_greater : path k triggers when metric > hi - k*step
    #     returns how many k in [0..N-1] with (hi - k*step) < metric
    def nest_less(metric, lo, hi, n_paths):
        # count = number of T in [lo, hi] (n_paths samples) with T > metric
        if metric >= hi: return 0
        if metric <= lo: return n_paths
        span = hi - lo
        return n_paths - 1 - int((metric - lo) * (n_paths - 1) / span)

    def nest_greater(metric, lo, hi, n_paths):
        # count = number of T in [lo, hi] (n_paths samples) with T < metric
        if metric <= lo: return 0
        if metric >= hi: return n_paths
        span = hi - lo
        return int((metric - lo) * (n_paths - 1) / span) + 1

    # --------------------------------------------------------------
    # Per-pixel filters (1, 2, 4, 5, 6, 7, 8). Each publishes up to
    # PATHS_PER_FILTER nested paths. filter 2 composites two metrics
    # (luminance AND chroma must both be in-range) so its path count
    # is capped at min(count_L, count_C).
    # --------------------------------------------------------------
    for i in opaque_idx:
        r = Rc[i]; g = Gc[i]; b = Bc[i]
        mx = r if r >= g and r >= b else (g if g >= b else b)
        mn = r if r <= g and r <= b else (g if g <= b else b)
        chroma = mx - mn
        L  = 0.299 * r + 0.587 * g + 0.114 * b
        v  = 0

        # 1. B&W darkness — paths: L < T, T in [30, 150]
        c = nest_less(L, 30, 150, PATHS_PER_FILTER)
        v += c; fc[1] += c

        # 2. Dark + low chroma — joint: L<TL AND chroma<TC (both nested)
        cL = nest_less(L,      50, 130, PATHS_PER_FILTER)
        cC = nest_less(chroma, 20,  70, PATHS_PER_FILTER)
        c  = cL if cL < cC else cC
        v += c; fc[2] += c

        # 4. Blue-dominant — paths: b-r > k AND b-g > k, k in [0, 30]
        dm = (b - r) if (b - r) < (b - g) else (b - g)
        c  = nest_greater(dm, 0, 30, PATHS_PER_FILTER)
        v += c; fc[4] += c

        # 5. Low saturation — paths: sat% < T, T in [5, 50]
        sat_pct = 100 if mx == 0 else (mx - mn) * 100 // mx
        c = nest_less(sat_pct, 5, 50, PATHS_PER_FILTER)
        v += c; fc[5] += c

        # 6. Posterize dark — paths: (r>>6)+(g>>6)+(b>>6) <= T, T in [0, 9]
        ps = (r >> 6) + (g >> 6) + (b >> 6)
        # Discrete metric in 0..9: nest_less is still correct.
        c = nest_less(ps, 0, 9, PATHS_PER_FILTER)
        v += c; fc[6] += c

        # 7. Strongly blue-hued — like filter 4 but offset threshold range [5, 35]
        c = nest_greater(dm, 5, 35, PATHS_PER_FILTER)
        v += c; fc[7] += c

        # 8. Dark value — paths: max(R,G,B) < T, T in [30, 150]
        c = nest_less(mx, 30, 150, PATHS_PER_FILTER)
        v += c; fc[8] += c

        votes[i] = v

    # --------------------------------------------------------------
    # Filter 3: low local gradient — paths at grad < T, T in [10, 80].
    # --------------------------------------------------------------
    for y in range(H):
        row = y * W
        for x in range(W):
            i = row + x
            if Ac[i] <= 32:
                continue
            gmax = 0
            if x + 1 < W:
                j = i + 1
                d = abs(Rc[i]-Rc[j]) + abs(Gc[i]-Gc[j]) + abs(Bc[i]-Bc[j])
                if d > gmax: gmax = d
            if y + 1 < H:
                j = i + W
                d = abs(Rc[i]-Rc[j]) + abs(Gc[i]-Gc[j]) + abs(Bc[i]-Bc[j])
                if d > gmax: gmax = d
            c = nest_less(gmax, 10, 80, PATHS_PER_FILTER)
            votes[i] += c
            fc[3] += c

    # --------------------------------------------------------------
    # Filter 9: border proximity — paths at d_border < T,
    # T in [2, short/3] (a spread of frame widths).
    # --------------------------------------------------------------
    short = min(W, H)
    b_hi  = max(3, short // 3)
    for y in range(H):
        row = y * W
        for x in range(W):
            i = row + x
            if Ac[i] <= 32:
                continue
            d_border = min(x, y, W - 1 - x, H - 1 - y)
            c = nest_less(d_border, 2, b_hi, PATHS_PER_FILTER)
            votes[i] += c
            fc[9] += c

    print("  path pool size: %d (9 filters × %d paths)" % (TOTAL_PATHS, PATHS_PER_FILTER))
    print("  total path-hits per filter (summed across all pixels):")
    for k in range(1, 10):
        print("    f%d: %d" % (k, fc[k]))

    # Vote histogram (bucketed into 10 ranges for legibility).
    hist_buckets = 10
    bucket_size  = max(1, (TOTAL_PATHS + 1) // hist_buckets)
    hist = [0] * hist_buckets
    for i in opaque_idx:
        b_idx = min(hist_buckets - 1, votes[i] // bucket_size)
        hist[b_idx] += 1
    print("  vote histogram (opaque, bucket=%d votes wide):" % bucket_size)
    for k in range(hist_buckets):
        lo = k * bucket_size
        hi = (k + 1) * bucket_size - 1 if k < hist_buckets - 1 else TOTAL_PATHS
        print("    [%3d..%3d]: %d" % (lo, hi, hist[k]))

    # --------------------------------------------------------------
    # Phase 1: mark every pixel with >= 200 path hits as bg. 200 is
    # deliberately strict so the first pass only erases pixels the
    # consensus is very confident about — we'll catch the rest in
    # Phase 2 below with connected-component analysis.
    # --------------------------------------------------------------
    THRESHOLD = 1100
    out = list(raw)
    phase1_removed = 0
    surviving = [False] * N   # mask: True = pixel still opaque after Phase 1
    for i in opaque_idx:
        if votes[i] >= THRESHOLD:
            out[i * 4 + 3] = 0
            phase1_removed += 1
        else:
            surviving[i] = True

    # --------------------------------------------------------------
    # Phase 2: cumulative 4-direction scoring with sqrt-damped merge.
    #
    # For each of 4 directional passes:
    #   - Build a fresh per-pixel matrix dm. Surviving pixels start
    #     at 1, non-surviving at 0.
    #   - Sweep the matrix in that direction's order (e.g. top-left
    #     pass: top->bottom, left->right). At each surviving pixel:
    #         dm[x,y] = 1 + dm[horizontal-prev] + dm[vertical-prev]
    #     so values keep growing the deeper into a connected region
    #     we go (Pascal-triangle-like accumulation). Non-surviving
    #     pixels stay at 0 and don't propagate.
    #   - Merge into the main matrix:
    #         main[i] = sqrt(main[i]) * dm[i]
    #     The square root damps the otherwise explosive growth from
    #     repeated multiplication, while still letting pixels deep
    #     in a region score much higher than edge / speck pixels.
    #
    # main_matrix is initialised to 2 everywhere. After all four
    # passes, deeply-interior pixels carry huge scores and edge /
    # island pixels carry small ones.
    # --------------------------------------------------------------
    import math
    main_matrix = [2.0] * N

    def cumulative_pass(y_range, x_range, neg_dx, neg_dy):
        # Build directional matrix dm via cumulative scan in the
        # given row/column order. For a surviving pixel at (x,y):
        #   dm[x,y] = 1 + dm[horizontal-prev] + dm[vertical-prev]
        # where "prev" neighbours are the ones already visited under
        # the scan order (controlled by neg_dx / neg_dy = ±1).
        dm = [0.0] * N
        for y in y_range:
            row = y * W
            for x in x_range:
                i = row + x
                if not surviving[i]:
                    continue
                v = 1.0   # self contributes 1 (surviving)
                xx = x + neg_dx   # already-visited horizontal neighbour
                if 0 <= xx < W:
                    v += dm[row + xx]
                yy = y + neg_dy   # already-visited vertical neighbour
                if 0 <= yy < H:
                    v += dm[yy * W + x]
                dm[i] = v
        return dm

    direction_matrices = [
        # (y_range, x_range, neg_dx, neg_dy) — each tuple is one of
        # the 4 corner sweeps. neg_dx / neg_dy point back to the
        # neighbour we visited just before the current pixel.
        (range(H),               range(W),               -1, -1),  # top-left
        (range(H),               range(W - 1, -1, -1),   +1, -1),  # top-right
        (range(H - 1, -1, -1),   range(W),               -1, +1),  # bottom-left
        (range(H - 1, -1, -1),   range(W - 1, -1, -1),   +1, +1),  # bottom-right
    ]

    for (yr, xr, dxn, dyn) in direction_matrices:
        dm = cumulative_pass(yr, xr, dxn, dyn)
        for i in range(N):
            if surviving[i]:
                main_matrix[i] = math.sqrt(main_matrix[i]) * dm[i]
            else:
                main_matrix[i] = 0.0

    # Logarithmic histogram of main_matrix values across surviving
    # pixels — values vary by many orders of magnitude.
    bin_edges = [0, 1, 2, 4, 8, 32, 128, 512, 2048,
                 8192, 32768, 1e5, 1e6, 1e9, 1e12, 1e30]
    bin_counts = [0] * len(bin_edges)
    for i in range(N):
        v = main_matrix[i]
        for k, e in enumerate(bin_edges):
            if v <= e:
                bin_counts[k] += 1
                break
        else:
            bin_counts[-1] += 1
    print("  main_matrix value distribution (sqrt-damped product of 4 dirs):")
    lo = 0.0
    for k, e in enumerate(bin_edges):
        if bin_counts[k]:
            print("    (%g .. %g]  pixels=%d" % (lo, e, bin_counts[k]))
        lo = e

    # --------------------------------------------------------------
    # Phase 2 finaliser: run strict 4-connectivity union-find CC
    # labelling over the survivors, find the SINGLE biggest
    # connected region, and zero out main_matrix for every pixel
    # that isn't part of it. After this step, main_matrix holds
    # scores only inside the biggest region and zero everywhere
    # else. Pixels outside the biggest region are dropped here
    # (alpha = 0) so only that region can feed Phase 3.
    # --------------------------------------------------------------
    CC_REACH = 1
    parent = [0]   # sentinel; real labels start at 1

    def cc_find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def cc_union(a, b):
        ra = cc_find(a); rb = cc_find(b)
        if ra == rb:
            return
        if ra < rb:
            parent[rb] = ra
        else:
            parent[ra] = rb

    labels = [0] * N
    next_label = 1
    for y in range(H):
        row = y * W
        for x in range(W):
            i = row + x
            if not surviving[i]:
                continue
            up_lbl   = labels[(y - 1) * W + x] if y > 0 else 0
            left_lbl = labels[row + (x - 1)]   if x > 0 else 0
            if up_lbl and left_lbl:
                lbl = up_lbl if up_lbl < left_lbl else left_lbl
                labels[i] = lbl
                if up_lbl != left_lbl:
                    cc_union(up_lbl, left_lbl)
            elif up_lbl:
                labels[i] = up_lbl
            elif left_lbl:
                labels[i] = left_lbl
            else:
                labels[i] = next_label
                parent.append(next_label)
                next_label += 1

    def cc_cross_pass(y_range, x_range, dy_sign, dx_sign):
        for y in y_range:
            row = y * W
            for x in x_range:
                i = row + x
                own = labels[i]
                if not own:
                    continue
                yy = y + dy_sign
                if 0 <= yy < H:
                    nb = labels[yy * W + x]
                    if nb:
                        cc_union(own, nb)
                xx = x + dx_sign
                if 0 <= xx < W:
                    nb = labels[row + xx]
                    if nb:
                        cc_union(own, nb)

    cc_cross_pass(range(H),             range(W - 1, -1, -1), -1, +1)
    cc_cross_pass(range(H - 1, -1, -1), range(W),             +1, -1)
    cc_cross_pass(range(H - 1, -1, -1), range(W - 1, -1, -1), +1, +1)

    # Resolve roots and count region sizes.
    resolved = [0] * N
    size = {}
    for i in range(N):
        if labels[i]:
            r = cc_find(labels[i])
            resolved[i] = r
            size[r] = size.get(r, 0) + 1

    n_regions = len(size)
    if n_regions == 0:
        biggest_root = 0
        biggest_size = 0
    else:
        biggest_root = max(size, key=size.get)
        biggest_size = size[biggest_root]
        print("  CC analysis: %d connected regions; biggest root=%d size=%d"
              % (n_regions, biggest_root, biggest_size))

    # Zero main_matrix and drop alpha for every pixel NOT in the
    # biggest region.
    phase2_removed = 0
    for i in range(N):
        if resolved[i] != biggest_root:
            main_matrix[i] = 0.0
            if surviving[i]:
                out[i * 4 + 3] = 0
                phase2_removed += 1

    # --------------------------------------------------------------
    # Phase 3: within the biggest region, compute the 1st
    # percentile of main_matrix scores and drop any pixel whose
    # score is at or below that cutoff. Almost no erosion — only
    # the absolute softest 1% of the subject region is removed.
    # --------------------------------------------------------------
    region_scores = [main_matrix[i] for i in range(N)
                     if resolved[i] == biggest_root and main_matrix[i] > 0]
    region_scores.sort()
    phase3_removed = 0
    kept_region_pixels = 0
    if region_scores:
        p1_idx = max(0, int(len(region_scores) * 0.01) - 1)
        p1_score = region_scores[p1_idx]
        print("  biggest-region score p1=%g  (kept pixels must have score > %g)"
              % (p1_score, p1_score))
        for i in range(N):
            if resolved[i] != biggest_root:
                continue
            if main_matrix[i] > p1_score:
                kept_region_pixels += 1
            else:
                out[i * 4 + 3] = 0
                phase3_removed += 1
    else:
        print("  biggest-region score p1=<empty>  (no surviving pixels)")

    phase2_removed += phase3_removed   # combined drop count for the report

    # --------------------------------------------------------------
    # Phase 4: Fuzzy Border. Softly blur the alpha channel only
    # (RGB stays untouched) so the sharp 0/255 cutoff at the
    # subject edge becomes a gradient. Uses a separable 2-pass
    # box blur with radius BORDER_RADIUS. Pixels deep inside the
    # subject stay opaque (their 5x5 neighbourhood is all-255);
    # pixels deep in the bg stay transparent (neighbourhood 0);
    # pixels on the boundary pick up intermediate alpha values
    # for a smooth composite.
    # --------------------------------------------------------------
    BORDER_RADIUS = 2
    alpha_src = [out[i * 4 + 3] for i in range(N)]
    # Horizontal pass.
    alpha_h = [0] * N
    for y in range(H):
        row = y * W
        for x in range(W):
            s = 0; cnt = 0
            lo = x - BORDER_RADIUS
            if lo < 0: lo = 0
            hi = x + BORDER_RADIUS
            if hi >= W: hi = W - 1
            for xx in range(lo, hi + 1):
                s += alpha_src[row + xx]
                cnt += 1
            alpha_h[row + x] = s // cnt
    # Vertical pass.
    alpha_v = [0] * N
    for x in range(W):
        for y in range(H):
            s = 0; cnt = 0
            lo = y - BORDER_RADIUS
            if lo < 0: lo = 0
            hi = y + BORDER_RADIUS
            if hi >= H: hi = H - 1
            for yy in range(lo, hi + 1):
                s += alpha_h[yy * W + x]
                cnt += 1
            alpha_v[y * W + x] = s // cnt
    # Edge-alpha histogram for visibility.
    bucket = [0] * 6  # 0, 1-50, 51-100, 101-180, 181-254, 255
    for a in alpha_v:
        if a == 0:     bucket[0] += 1
        elif a <= 50:  bucket[1] += 1
        elif a <= 100: bucket[2] += 1
        elif a <= 180: bucket[3] += 1
        elif a <= 254: bucket[4] += 1
        else:          bucket[5] += 1
    print("  fuzzy-border alpha histogram: "
          "0=%d, 1-50=%d, 51-100=%d, 101-180=%d, 181-254=%d, 255=%d"
          % (bucket[0], bucket[1], bucket[2], bucket[3], bucket[4], bucket[5]))
    for i in range(N):
        out[i * 4 + 3] = alpha_v[i]

    # --------------------------------------------------------------
    # Write the modified RGBA buffer back. The alpha channel was
    # added at the top of this block, so writing 0 into the A byte
    # gives genuine 100%-transparent pixels (not painted white) that
    # composite cleanly over the new background image.
    # --------------------------------------------------------------
    if not base.has_alpha():
        base.add_alpha()
    base.get_buffer().set(rect, FMT, out)
    base.update(0, 0, W, H)

    Gimp.displays_flush()
    total_removed = phase1_removed + phase2_removed
    print("BG_REMOVED_9PATHS_MUL phase1=%d phase2=%d total=%d of %d opaque "
          "(%.1f%%) at threshold=%d, kept_interior=%d"
          % (phase1_removed, phase2_removed, total_removed, total_op,
             total_removed * 100.0 / max(total_op, 1), THRESHOLD,
             kept_region_pixels))
except Exception as e:
    print("ERROR: " + str(e))
    print(_tb.format_exc())
"""
run_gimp('bg removal (9×200 paths, threshold=1100, biggest-CC + score>p1, fuzzy border r=2)', bg_removal)
snapshot(f'{out_dir}/02_character_nobg.png')


# ── STEP 3: recolor hair on the cutout BEFORE compositing ──────────────────
# The character now has a transparent bg, so selecting the blonde palette
# by color matches only hair pixels (empty pixels have alpha=0 and are
# skipped). A luminance-preserving hue rotation turns yellow -> red while
# keeping the original brightness distribution, which gives natural hair
# highlights and shadows. Two hue-saturation passes and a color-balance
# pass on shadows/highlights push the result toward a vivid red.

print("\nSTEP 3: Detect hair and recolor red (on standalone cutout)")

hair_recolor = r"""
from gi.repository import Gimp, Gegl
import traceback as _tb
try:
    image = Gimp.get_images()[0]  # only image open at this point — the character
    char  = image.get_layers()[0]
    image.set_selected_layers([char])
    pdb = Gimp.get_pdb()

    # Clear any leftover selection.
    npr = pdb.lookup_procedure("gimp-selection-none")
    if npr:
        c = npr.create_config(); c.set_property("image", image); npr.run(c)

    # Golden-yellow seed for the hair. Threshold 0.45 covers the full
    # blonde band (highlights through mid-tones) without bleeding into skin.
    sample_color = Gegl.Color.new("rgb(0.96,0.80,0.30)")

    Gimp.context_push()
    Gimp.context_set_sample_threshold(0.45)
    Gimp.context_set_antialias(True)
    Gimp.context_set_feather(True)
    Gimp.context_set_feather_radius(2.0, 2.0)
    try:
        sel_proc = pdb.lookup_procedure("gimp-image-select-color")
        cfg = sel_proc.create_config()
        cfg.set_property("image",     image)
        cfg.set_property("operation", Gimp.ChannelOps.REPLACE)
        cfg.set_property("drawable",  char)
        cfg.set_property("color",     sample_color)
        sel_proc.run(cfg)
    finally:
        Gimp.context_pop()

    gp = pdb.lookup_procedure("gimp-selection-grow")
    if gp:
        c = gp.create_config(); c.set_property("image", image); c.set_property("steps", 1); gp.run(c)

    # Shift yellow -> red while preserving per-pixel luminance, then
    # deepen the now-red shadows.
    hs = pdb.lookup_procedure("gimp-drawable-hue-saturation")
    if hs:
        c = hs.create_config()
        c.set_property("drawable",   char)
        c.set_property("hue-range",  Gimp.HueRange.YELLOW)
        c.set_property("hue-offset", -60.0)
        c.set_property("lightness",   0.0)
        c.set_property("saturation", 25.0)
        c.set_property("overlap",     0.0)
        hs.run(c)
        c = hs.create_config()
        c.set_property("drawable",   char)
        c.set_property("hue-range",  Gimp.HueRange.RED)
        c.set_property("hue-offset",  0.0)
        c.set_property("lightness",  -8.0)
        c.set_property("saturation", 20.0)
        c.set_property("overlap",     0.0)
        hs.run(c)

    cb = pdb.lookup_procedure("gimp-drawable-color-balance")
    if cb:
        for trans_mode, cr, yb in ((2, 25.0, -10.0),   # highlights
                                   (0, 40.0,  10.0)):  # shadows
            c = cb.create_config()
            c.set_property("drawable",      char)
            c.set_property("transfer-mode", trans_mode)
            c.set_property("cyan-red",      cr)
            c.set_property("magenta-green", 0.0)
            c.set_property("yellow-blue",   yb)
            c.set_property("preserve-lum",  True)
            cb.run(c)

    npr = pdb.lookup_procedure("gimp-selection-none")
    if npr:
        c = npr.create_config(); c.set_property("image", image); npr.run(c)

    Gimp.displays_flush()
    print("HAIR_RECOLORED")
except Exception as e:
    print("ERROR: " + str(e))
    print(_tb.format_exc())
"""
run_gimp('hair recolor', hair_recolor)
snapshot(f'{out_dir}/03_hair_red.png')

# Export the recolored cutout so we can re-open it as a layer on top of
# the new background image.
cutout_path = f'{out_dir}/_character_cutout.png'
require_success('export cutout', cmd('export_image', {
    'image_index': 0,
    'file_path':   cutout_path,
    'file_type':   'png',
}))


# ── STEP 4: composite the recolored cutout onto the night background ──────

print("\nSTEP 4: Open background and composite recolored character")
r_open_bg = require_success('open background', cmd('open_image', {'file_path': bg_path}))
bg_image_id = r_open_bg.get('results', {}).get('image_id')
print(f"    bg image_id = {bg_image_id}, char image_id = {char_image_id}")

# Locate the bg image's current index (needed by MCP tools that take
# image_index rather than image_id — e.g. export_image, snapshot).
ls = require_success('list images', cmd('list_images', {}))
bg_basename = os.path.basename(bg_path)
bg_index = next(
    (img['index'] for img in ls['results']['images']
     if img.get('image_id') == bg_image_id),
    None,
)
if bg_index is None:
    print(f"ERROR: could not find bg image id={bg_image_id} in open images: {ls}", file=sys.stderr)
    sys.exit(1)
snapshot(f'{out_dir}/04_background_only.png', image_index=bg_index)

composite_code = r"""
from gi.repository import Gimp, Gegl
import traceback as _tb
try:
    Gegl.init(None)
    bg_image_id    = %BG_IMAGE_ID%
    char_image_id  = %CHAR_IMAGE_ID%
    bg_image   = None
    char_image = None
    for img in Gimp.get_images():
        if img.get_id() == bg_image_id:
            bg_image = img
        elif img.get_id() == char_image_id:
            char_image = img
    if bg_image is None or char_image is None:
        raise RuntimeError("need both bg and character images open "
                           "(got bg=%s, char=%s)" % (bg_image, char_image))
    bg_w, bg_h = bg_image.get_width(), bg_image.get_height()

    # --- Pull the character base layer's RGBA bytes directly ----------
    char_base = char_image.get_layers()[0]
    if not char_base.has_alpha():
        char_base.add_alpha()
    cw = char_base.get_width()
    ch = char_base.get_height()
    src_rect = Gegl.Rectangle.new(0, 0, cw, ch)
    FMT = "R'G'B'A u8"
    raw_char = char_base.get_buffer().get(src_rect, 1.0, FMT, Gegl.AbyssPolicy.CLAMP)
    # Force into a plain list of ints — Gegl.Buffer.set expects list, but
    # Gegl.Buffer.get can hand back an immutable bytes object in some
    # bindings which set() then silently ignores.
    char_data = list(raw_char)
    print("  source layer: %dx%d alpha=%s bytes=%d"
          % (cw, ch, char_base.has_alpha(), len(char_data)))

    # Verify at least some pixels ARE transparent in the source —
    # otherwise the cutout never actually got alpha=0 written.
    alpha_zero = sum(1 for k in range(3, len(char_data), 4) if char_data[k] == 0)
    alpha_full = sum(1 for k in range(3, len(char_data), 4) if char_data[k] == 255)
    print("  source alpha distribution: 0-alpha=%d  255-alpha=%d  total=%d"
          % (alpha_zero, alpha_full, cw * ch))

    # --- Create an RGBA layer in the bg image and write the bytes in --
    # Using Gimp.ImageType.RGBA_IMAGE forces a 4-channel buffer from the
    # start, so there is no "convert to alpha" step that could silently
    # drop transparency.
    char_layer = Gimp.Layer.new(
        bg_image, "Character", cw, ch,
        Gimp.ImageType.RGBA_IMAGE, 100.0, Gimp.LayerMode.NORMAL,
    )
    bg_image.insert_layer(char_layer, None, 0)
    if not char_layer.has_alpha():
        char_layer.add_alpha()
    char_layer.get_buffer().set(src_rect, FMT, char_data)
    char_layer.update(0, 0, cw, ch)

    # Verify the bytes actually landed in the new layer's buffer.
    verify = char_layer.get_buffer().get(src_rect, 1.0, FMT, Gegl.AbyssPolicy.CLAMP)
    v_full = sum(1 for k in range(3, len(verify), 4) if verify[k] == 255)
    v_zero = sum(1 for k in range(3, len(verify), 4) if verify[k] == 0)
    print("  layer after set: 0-alpha=%d  255-alpha=%d" % (v_zero, v_full))

    # --- Scale + position ---------------------------------------------
    target_h = int(bg_h * 0.70)
    target_w = int(cw * (target_h / ch))
    char_layer.scale(target_w, target_h, True)
    off_x = (bg_w - target_w) // 2
    off_y = bg_h - target_h - int(bg_h * 0.05)
    char_layer.set_offsets(off_x, off_y)

    # Diagnostics: make sure the layer is actually visible / selectable
    # post-scale and its pixel data survived the scale resample.
    char_layer.set_visible(True)
    try:
        char_layer.set_opacity(100.0)
    except Exception:
        pass
    scaled_rect = Gegl.Rectangle.new(0, 0, char_layer.get_width(), char_layer.get_height())
    scaled_data = char_layer.get_buffer().get(scaled_rect, 1.0, FMT, Gegl.AbyssPolicy.CLAMP)
    sv_full = sum(1 for k in range(3, len(scaled_data), 4) if scaled_data[k] > 200)
    sv_zero = sum(1 for k in range(3, len(scaled_data), 4) if scaled_data[k] < 50)
    print("  scaled layer: %dx%d  visible=%s  0-alpha=%d  255-alpha=%d"
          % (char_layer.get_width(), char_layer.get_height(),
             char_layer.get_visible(), sv_zero, sv_full))

    Gimp.displays_flush()

    # Dump bg_image's layer list to confirm the char layer is present
    # on the actual image we intend to export from.
    print("  bg_image id=%d layers after insert:" % bg_image.get_id())
    for L in bg_image.get_layers():
        off = L.get_offsets()
        print("    layer id=%d name=%r size=%dx%d offset=(%d,%d) visible=%s opacity=%.1f"
              % (L.get_id(), L.get_name(),
                 L.get_width(), L.get_height(),
                 off.offset_x, off.offset_y,
                 L.get_visible(), L.get_opacity()))

    print("COMPOSITE_OK bg=%dx%d  char=%dx%d  at=(%d,%d)  alpha=%s"
          % (bg_w, bg_h, target_w, target_h, off_x, off_y,
             char_layer.has_alpha()))
except Exception as e:
    print("ERROR: " + str(e))
    print(_tb.format_exc())
""".replace('%BG_IMAGE_ID%', json.dumps(bg_image_id)) \
   .replace('%CHAR_IMAGE_ID%', json.dumps(char_image_id))

run_gimp('composite', composite_code)
snapshot(f'{out_dir}/05_composited.png', image_index=bg_index)


# ── STEP 5: export final composite ──────────────────────────────────────────

print("\nSTEP 5: Export final composite")
final_path = f'{out_dir}/final_composite.png'
require_success('export final', cmd('export_image', {
    'image_index': bg_index,
    'file_path':   final_path,
    'file_type':   'png',
}))

print("\n" + "=" * 72)
print(f"SUCCESS: continuous edit test complete -> {final_path}")
print(f"Intermediate snapshots in: {out_dir}/")
