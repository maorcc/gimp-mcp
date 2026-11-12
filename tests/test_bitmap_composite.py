#!/usr/bin/env python3
"""Regression test for composite pixels in region snapshots.

Requires GIMP with the gimp-mcp plug-in server running on port 9877.
"""

import base64
import json
import os
import socket
import tempfile


def command(command_type, params=None):
    """Send one command to the live GIMP plug-in."""
    payload = {"type": command_type, "params": params or {}}
    with socket.create_connection(("127.0.0.1", 9877), timeout=20) as connection:
        connection.settimeout(20)
        connection.sendall(json.dumps(payload).encode() + b"\n")
        response = b""
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            response += chunk
            try:
                return json.loads(response.decode())
            except json.JSONDecodeError:
                continue
    raise AssertionError(f"GIMP returned an incomplete response: {response[:120]!r}")


def execute(code):
    """Execute Python inside GIMP through the plug-in's test hook."""
    payload = {"cmds": [code]}
    with socket.create_connection(("127.0.0.1", 9877), timeout=20) as connection:
        connection.settimeout(20)
        connection.sendall(json.dumps(payload).encode() + b"\n")
        response = b""
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            response += chunk
            try:
                return json.loads(response.decode())
            except json.JSONDecodeError:
                continue
    raise AssertionError(f"GIMP returned an incomplete response: {response[:120]!r}")


def require_success(response, operation):
    assert response.get("status") == "success", f"{operation} failed: {response}"
    return response.get("results")


def extract_marker(response, marker):
    outputs = require_success(response, marker)
    combined = "\n".join(str(output) for output in outputs)
    for line in combined.splitlines():
        if line.startswith(marker):
            return line[len(marker) :]
    raise AssertionError(f"Missing {marker!r} in GIMP output: {combined}")


def assert_primary_color(pixel, channel):
    """Assert an RGBA pixel is opaque and dominated by one primary channel."""
    red, green, blue, alpha = pixel
    channels = {"red": red, "green": green, "blue": blue}
    assert channels[channel] > 0.9, f"Expected {channel} pixel, got {pixel}"
    for name, value in channels.items():
        if name != channel:
            assert value < 0.1, f"Expected {channel} pixel, got {pixel}"
    assert alpha > 0.9, f"Expected opaque pixel, got {pixel}"


def main():
    setup_code = r"""
from gi.repository import Gimp, Gegl

image = Gimp.Image.new(32, 32, Gimp.ImageBaseType.RGB)
base = Gimp.Layer.new(
    image, "Red base", 32, 32, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL
)
image.insert_layer(base, None, 0)

top = Gimp.Layer.new(
    image, "Blue corner", 32, 32, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL
)
image.insert_layer(top, None, 0)

Gimp.context_push()
try:
    Gimp.context_set_foreground(Gegl.Color.new("#ff0000"))
    Gimp.Drawable.edit_fill(base, Gimp.FillType.FOREGROUND)
    Gimp.Drawable.edit_fill(top, Gimp.FillType.TRANSPARENT)
    image.select_rectangle(Gimp.ChannelOps.REPLACE, 0, 0, 16, 16)
    Gimp.context_set_foreground(Gegl.Color.new("#0000ff"))
    Gimp.Drawable.edit_fill(top, Gimp.FillType.FOREGROUND)
    Gimp.Selection.none(image)
finally:
    Gimp.context_pop()

print("COMPOSITE_TEST_IMAGE_ID:" + str(image.get_id()))
"""

    image_id = int(extract_marker(execute(setup_code), "COMPOSITE_TEST_IMAGE_ID:"))
    snapshot_path = None
    try:
        snapshot = command(
            "get_image_bitmap",
            {
                "image_index": 0,
                "region": {"origin_x": 0, "origin_y": 0, "width": 32, "height": 32},
            },
        )
        snapshot_result = require_success(snapshot, "get_image_bitmap")
        assert snapshot_result["width"] == 32
        assert snapshot_result["height"] == 32

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as snapshot_file:
            snapshot_file.write(base64.b64decode(snapshot_result["image_data"]))
            snapshot_path = snapshot_file.name

        inspect_code = f"""
from gi.repository import Gimp, Gio
import json as _json

snapshot = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path({snapshot_path!r}))
try:
    layer = snapshot.get_layers()[0]
    pixels = [layer.get_pixel(4, 4).get_rgba(), layer.get_pixel(24, 24).get_rgba()]
    print("COMPOSITE_TEST_PIXELS:" + _json.dumps(pixels))
finally:
    snapshot.delete()
"""
        pixels = json.loads(extract_marker(execute(inspect_code), "COMPOSITE_TEST_PIXELS:"))
        assert_primary_color(pixels[0], "blue")
        assert_primary_color(pixels[1], "red")
    finally:
        if snapshot_path:
            os.unlink(snapshot_path)
        cleanup_code = f"""
from gi.repository import Gimp

image = Gimp.Image.get_by_id({image_id})
if image is not None and image.is_valid():
    image.delete()
"""
        require_success(execute(cleanup_code), "cleanup")

    print("PASS: region snapshot contains the visible composite")


if __name__ == "__main__":
    main()
