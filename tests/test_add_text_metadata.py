#!/usr/bin/env python3
"""Regression test for issue #15 — add_text must return real layer metadata.

Before the fix, ``_add_text`` returned placeholder values when PDB
return-value unpacking failed::

    {'layer_name': 'unknown', 'layer_id': -1, 'text_width': 0, ...}

while ``status`` was still ``'success'``, so any follow-up op targeting
the layer by id/name would fail silently.

What this test proves
---------------------

1. ``add_text`` responds with ``status == 'success'``.
2. The returned ``layer_id``/``layer_name``/``text_width``/``text_height``
   are **real values**, not the old ``-1`` / ``'unknown'`` / ``0``
   sentinels.
3. ``list_layers`` can see a layer that matches the returned id *and*
   name — proving the handle is actually chainable, which is the whole
   point of issue #15.

The test reuses the character portrait already committed for the
continuous-edit test (``tests/continuous_edit_test/files/winry_joy.png``)
so no new fixture is needed.

Requirements: GIMP MCP plugin must be running on ``localhost:9877``.
Exits 0 on pass, 1 on fail.
"""
import json
import os
import socket
import sys

HOST, PORT = '127.0.0.1', 9877
HERE       = os.path.dirname(os.path.abspath(__file__))
TEST_IMAGE = os.path.join(HERE, 'continuous_edit_test', 'files', 'winry_joy.png')


# ── transport ─────────────────────────────────────────────────────────────

def send(msg, timeout=30):
    """Send one JSON message to the GIMP MCP socket and return the reply.

    The plugin emits newline-delimited JSON; we keep reading until
    ``json.loads`` succeeds on the accumulated buffer.
    """
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
    """Convenience wrapper: send a ``{type, params}`` command."""
    return send({'type': t, 'params': params or {}})


def fail(msg):
    """Abort the test with a clear failure banner on stderr."""
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


# ── test steps ────────────────────────────────────────────────────────────

def open_test_image():
    """Open the test image and return ``(target_index, opened_id)``.

    Uses the ``image_id`` returned by ``open_image`` to find the matching
    entry in ``list_images``. This is the authoritative handle — matching
    by path suffix alone can pick a stale duplicate in a persistent GIMP
    session. Path-suffix matching is kept as a fallback only for the
    case where ``image_id`` is missing from the ``open_image`` response.
    """
    if not os.path.exists(TEST_IMAGE):
        fail(f"test image missing: {TEST_IMAGE}")

    print(f"Opening test image: {TEST_IMAGE}")
    r = cmd('open_image', {'file_path': TEST_IMAGE})
    if r.get('status') != 'success':
        fail(f"open_image: {r.get('error', '')}")

    opened_id = r.get('image_id') or (r.get('results') or {}).get('image_id')

    li     = cmd('list_images', {})
    images = (li.get('results') or {}).get('images') or []
    if not images:
        fail("no images after open_image")

    target_index = None
    if opened_id is not None:
        target_index = _find_index_by(images, 'image_id', opened_id)
    if target_index is None:
        target_index = _find_index_by_suffix(images, 'winry_joy.png')
    if target_index is None:
        target_index = 0

    print(f"Using image_index={target_index} (image_id={opened_id})")
    return target_index, opened_id


def _find_index_by(images, key, value):
    """Return the index of the image whose ``key`` equals ``value``, or None."""
    for i, info in enumerate(images):
        if isinstance(info, dict) and info.get(key) == value:
            return i
    return None


def _find_index_by_suffix(images, suffix):
    """Return the index of the image whose ``file_path`` ends with ``suffix``."""
    for i, info in enumerate(images):
        if isinstance(info, dict) and info.get('file_path', '').endswith(suffix):
            return i
    return None


def call_add_text(target_index):
    """Invoke ``add_text`` with concrete parameters and return the response."""
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
    return r.get('results') or {}


def assert_real_metadata(results):
    """Verify ``add_text`` returned real values, not issue #15 placeholders.

    ``layer_id`` must be **strictly positive**. A real ``Gimp.Drawable``
    id is never 0, so accepting 0 would let a default-int return slip
    through the check just as the old ``-1`` sentinel did.

    Returns ``(layer_id, layer_name, text_width, text_height)`` on
    success; aborts via :func:`fail` on any placeholder.
    """
    layer_id   = results.get('layer_id')
    layer_name = results.get('layer_name')
    text_w     = results.get('text_width')
    text_h     = results.get('text_height')

    if not isinstance(layer_id, int) or layer_id <= 0:
        fail(f"layer_id is placeholder: {layer_id!r} (expected positive int)")
    if not layer_name or layer_name == 'unknown':
        fail(f"layer_name is placeholder: {layer_name!r}")
    if not isinstance(text_w, int) or text_w <= 0:
        fail(f"text_width is placeholder/zero: {text_w!r}")
    if not isinstance(text_h, int) or text_h <= 0:
        fail(f"text_height is placeholder/zero: {text_h!r}")
    return layer_id, layer_name, text_w, text_h


def assert_chainable(target_index, layer_id, layer_name):
    """Verify the returned handle is visible to ``list_layers``.

    Requires a single listed layer whose ``id`` **and** ``name`` both
    match the metadata we got back. Matching on either-or would happily
    succeed against an unrelated layer that happens to share a
    (non-unique) name, which could mask a real bug where the returned
    ``id`` does not resolve to the new text layer.

    The whole point of issue #15 is that clients must be able to chain
    further operations on the new text layer — only a full id+name
    match actually proves that.
    """
    ll = cmd('list_layers', {'image_index': target_index})
    if ll.get('status') != 'success':
        fail(f"list_layers failed: {ll.get('error', '')}")

    layers = (ll.get('results') or {}).get('layers') or []
    match  = next((lyr for lyr in layers
                   if lyr.get('id') == layer_id and lyr.get('name') == layer_name),
                  None)
    if match is None:
        fail(f"returned layer (id={layer_id}, name={layer_name!r}) not in list_layers: {layers}")
    return match


# ── entry point ───────────────────────────────────────────────────────────

def main():
    target_index, _opened_id = open_test_image()
    results                  = call_add_text(target_index)
    layer_id, layer_name, w, h = assert_real_metadata(results)
    match                    = assert_chainable(target_index, layer_id, layer_name)

    print(f"PASS add_text: layer_id={layer_id} name={layer_name!r} size={w}x{h}")
    print(f"PASS list_layers confirms layer is chainable: {match}")
    sys.exit(0)


if __name__ == '__main__':
    main()
