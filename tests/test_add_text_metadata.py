#!/usr/bin/env python3
"""Regression test for issue #15 — add_text must return real layer metadata.

Before the fix, _add_text returned placeholder values when PDB return-value
unpacking failed:
    {'layer_name': 'unknown', 'layer_id': -1, 'text_width': 0, ...}
while status was still 'success', so any follow-up op targeting the layer
by name/id would fail silently.

This test opens tests/continuous_edit_test/files/winry_joy.png, adds a text
layer, and asserts:
  - status == 'success'
  - layer_id is a positive int (not -1)
  - layer_name is not 'unknown' and not empty
  - text_width / text_height are positive (the layer actually rendered)
  - list_layers sees the new layer with the same id/name — proving the
    returned handle is usable for chaining (the whole point of issue #15).

Requires the GIMP MCP plugin running on localhost:9877.
Exit 0 on pass, 1 on fail.
"""
import json
import os
import socket
import sys

HOST, PORT = '127.0.0.1', 9877
HERE = os.path.dirname(os.path.abspath(__file__))
TEST_IMAGE = os.path.join(HERE, 'continuous_edit_test', 'files', 'winry_joy.png')


def send(msg, timeout=30):
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
    return send({'type': t, 'params': params or {}})


def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    if not os.path.exists(TEST_IMAGE):
        fail(f"test image missing: {TEST_IMAGE}")

    print(f"Opening test image: {TEST_IMAGE}")
    r = cmd('open_image', {'file_path': TEST_IMAGE})
    if r.get('status') != 'success':
        fail(f"open_image: {r.get('error', '')}")

    # Use image_index 0 — this will be the most recently opened image in
    # many impls, but we check list_images to be safe.
    li = cmd('list_images', {})
    images = (li.get('results') or {}).get('images') or []
    if not images:
        fail("no images after open_image")
    # Prefer the image whose path matches
    target_index = 0
    for i, info in enumerate(images):
        if isinstance(info, dict) and info.get('file_path', '').endswith('winry_joy.png'):
            target_index = i
            break
    print(f"Using image_index={target_index}")

    print("Calling add_text with real parameters...")
    r = cmd('add_text', {
        'image_index': target_index,
        'text':        'Issue15',
        'x':           10,
        'y':           10,
        'font':        'Sans',
        'size':        24,
        'color':       '#ff0000',
    })
    print(f"  response: {json.dumps(r)[:300]}")

    if r.get('status') != 'success':
        fail(f"add_text reported error: {r.get('error', '')}")

    results = r.get('results') or {}
    layer_id    = results.get('layer_id')
    layer_name  = results.get('layer_name')
    text_w      = results.get('text_width')
    text_h      = results.get('text_height')

    # Core assertions for issue #15
    if not isinstance(layer_id, int) or layer_id < 0:
        fail(f"layer_id is placeholder: {layer_id!r} (expected positive int)")
    if not layer_name or layer_name == 'unknown':
        fail(f"layer_name is placeholder: {layer_name!r}")
    if not isinstance(text_w, int) or text_w <= 0:
        fail(f"text_width is placeholder/zero: {text_w!r}")
    if not isinstance(text_h, int) or text_h <= 0:
        fail(f"text_height is placeholder/zero: {text_h!r}")

    # Prove the handle is chainable: list_layers must see the returned
    # layer_id and layer_name on the current image.
    ll = cmd('list_layers', {'image_index': target_index})
    if ll.get('status') != 'success':
        fail(f"list_layers failed: {ll.get('error', '')}")
    layers = (ll.get('results') or {}).get('layers') or []
    match = next((lyr for lyr in layers
                  if lyr.get('id') == layer_id or lyr.get('name') == layer_name),
                 None)
    if match is None:
        fail(f"returned layer (id={layer_id}, name={layer_name!r}) not in list_layers: {layers}")

    print(f"PASS add_text: layer_id={layer_id} name={layer_name!r} size={text_w}x{text_h}")
    print(f"PASS list_layers confirms layer is chainable: {match}")
    sys.exit(0)


if __name__ == '__main__':
    main()
