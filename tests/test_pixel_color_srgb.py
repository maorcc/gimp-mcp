#!/usr/bin/env python3
"""Regression test for issue #43 — get_pixel_color must return sRGB values.

GIMP stores colour in linear light; get_pixel_color used to scale those raw
linear floats by 255, so #ff5733 read back as #ff1808 and #808080 as #373737.

The test writes known 8-bit sRGB bytes straight into a layer buffer (so it
does not depend on any colour-parsing path, see #44/#50), then checks that
get_pixel_color reports exactly those bytes.

Requires the GIMP MCP plugin running on localhost:9877.
Exits 0 on pass, 1 on fail.
"""
import json
import socket
import sys

HOST, PORT = '127.0.0.1', 9877
LAYER_NAME = 'pr55-pixel-test'
CELL       = 10          # each colour occupies a CELL x CELL square

# (r, g, b, a) written as "R'G'B'A u8" and expected back from get_pixel_color.
SWATCHES = [
    (0xff, 0x57, 0x33, 255),   # old bug: #ff1808
    (0x80, 0x80, 0x80, 255),   # old bug: #373737 (most sensitive to gamma)
    (0x64, 0x95, 0xed, 255),   # old bug: #204cd7
    (0x12, 0x34, 0x56, 255),   # old bug: #010817
    (0x00, 0x00, 0x00, 255),
    (0xff, 0xff, 0xff, 255),
    (0x33, 0x66, 0xcc, 128),   # alpha must pass through without gamma
]


# ── transport ─────────────────────────────────────────────────────────────

def send(msg, timeout=30):
    """Send one JSON message to the MCP socket and return the reply."""
    s = socket.socket()
    s.settimeout(timeout)
    s.connect((HOST, PORT))
    s.send(json.dumps(msg).encode() + b'\n')
    buf = b''
    while True:
        try:
            chunk = s.recv(65536)
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
        return {'status': 'error', 'error': 'parse: ' + buf.decode()[:200]}


def cmd(t, params=None):
    """Send a {type, params} command."""
    return send({'type': t, 'params': params or {}})


def run_python(lines):
    """Run Python inside GIMP; return the printed output of the last line."""
    r = send({'cmds': lines})
    if r.get('status') != 'success':
        fail(f"python exec failed: {r.get('error', r)}")
    return (r.get('results') or [''])[-1].strip()


def fail(msg):
    """Abort with a failure banner on stderr."""
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


# ── test steps ────────────────────────────────────────────────────────────

def create_test_image():
    """Create an RGBA image holding SWATCHES as exact bytes; return its id.

    No display is opened, so the image can be deleted afterwards without
    close_image (which fails on GIMP 3.2, see #51).
    """
    width = CELL * len(SWATCHES)
    pixels = bytearray()
    for _row in range(CELL):
        for swatch in SWATCHES:
            pixels += bytes(swatch) * CELL

    out = run_python([
        "from gi.repository import Gimp, Gegl",
        f"_t_img = Gimp.Image.new({width}, {CELL}, Gimp.ImageBaseType.RGB)",
        f"_t_lyr = Gimp.Layer.new(_t_img, {LAYER_NAME!r}, {width}, {CELL}, "
        "Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)",
        "_t_img.insert_layer(_t_lyr, None, 0)",
        "_t_buf = _t_lyr.get_buffer()",
        f"_t_buf.set(Gegl.Rectangle.new(0, 0, {width}, {CELL}), \"R'G'B'A u8\", "
        f"bytes.fromhex({pixels.hex()!r}))",
        "_t_buf.flush()",
        "print(_t_img.get_id())",
    ])
    try:
        return int(out)
    except ValueError:
        fail(f"could not create test image, got: {out!r}")


def find_image_index(image_id):
    """Map an image id to the image_index the tools expect."""
    r = cmd('list_images', {})
    images = (r.get('results') or {}).get('images') or []
    for info in images:
        if info.get('image_id') == image_id:
            return info['index']
    fail(f"test image id={image_id} not in list_images: {images}")


def check_swatches(image_index):
    """Read the centre of each swatch and compare with what was written."""
    failures = []
    for i, (r, g, b, a) in enumerate(SWATCHES):
        x, y = i * CELL + CELL // 2, CELL // 2
        resp = cmd('get_pixel_color', {
            'image_index': image_index, 'layer_name': LAYER_NAME, 'x': x, 'y': y,
        })
        if resp.get('status') != 'success':
            fail(f"get_pixel_color({x},{y}) error: {resp.get('error', '')}")
        res = resp.get('results') or {}

        want_hex = f"#{r:02x}{g:02x}{b:02x}"
        got = (res.get('color_hex'), res.get('color_rgb'), res.get('alpha'))
        want = (want_hex, [r, g, b], a)
        status = 'ok ' if got == want else 'BAD'
        print(f"  {status} wrote {want_hex} a={a:<3} -> read {got[0]} rgb={got[1]} a={got[2]}")
        if got != want:
            failures.append(want_hex)
    return failures


def delete_image(image_id):
    """Delete the test image so a persistent GIMP session stays clean."""
    if image_id is None:
        return
    try:
        send({'cmds': [
            "from gi.repository import Gimp",
            f"[im.delete() for im in Gimp.get_images() if im.get_id() == {image_id}]",
        ]})
    except Exception as e:
        print(f"  (cleanup) delete failed: {e}", file=sys.stderr)


# ── entry point ───────────────────────────────────────────────────────────

def main():
    image_id = None
    try:
        image_id = create_test_image()
        image_index = find_image_index(image_id)
        print(f"Test image id={image_id} index={image_index}")
        failures = check_swatches(image_index)
        if failures:
            fail(f"{len(failures)}/{len(SWATCHES)} colours read back wrong: {failures}")
        print(f"PASS get_pixel_color: all {len(SWATCHES)} colours read back exactly")
        sys.exit(0)
    except ConnectionRefusedError:
        fail(f"GIMP MCP plugin not reachable on {HOST}:{PORT} (Tools > MCP > Start MCP Server)")
    finally:
        delete_image(image_id)


if __name__ == '__main__':
    main()
