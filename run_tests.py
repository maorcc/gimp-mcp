#!/usr/bin/env python3
import base64
import socket
import json
import os
import shutil
import struct
import sys
import tempfile
import zlib

def send(msg):
    s = socket.socket()
    s.settimeout(20)
    s.connect(('127.0.0.1', 9877))
    s.send(json.dumps(msg).encode() + b'\n')
    r = b''
    while True:
        try:
            d = s.recv(8192)
            if not d:
                break
            r += d
            try:
                json.loads(r.decode())
                break
            except json.JSONDecodeError:
                continue
        except socket.timeout:
            break
    s.close()
    try:
        return json.loads(r.decode().strip())
    except json.JSONDecodeError:
        return {'status': 'error', 'error': 'parse error: ' + r.decode()[:80]}

def cmd(t, params=None):
    return send({'type': t, 'params': params if params is not None else {}})

def bitmap(params=None):
    """Return an image's composite pixel stream (decompressed PNG IDAT), or None on error.

    Raw PNG bytes can't be compared directly: the export embeds a timestamp.
    """
    data = cmd('get_image_bitmap', params or {}).get('results', {}).get('image_data')
    if not data:
        return None
    png, pos, idat = base64.b64decode(data), 8, b''
    while pos < len(png):
        length = struct.unpack('>I', png[pos:pos + 4])[0]
        if png[pos + 4:pos + 8] == b'IDAT':
            idat += png[pos + 8:pos + 8 + length]
        pos += 12 + length
    return zlib.decompress(idat)

def magic(path):
    """Identify a file's real format from its leading bytes."""
    try:
        with open(path, 'rb') as f:
            head = f.read(12)
    except OSError as e:
        return str(e)
    if head.startswith(b'\x89PNG'):
        return 'png'
    if head.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    return repr(head[:4])

passed = 0
failed = 0
failures = []

def t(name, r):
    global passed, failed
    ok = r.get('status') == 'success'
    if ok:
        passed += 1
    else:
        failed += 1
        failures.append((name, str(r.get('error', ''))[:90]))
    detail = str(r.get('results', '') if ok else r.get('error', ''))[:65]
    print(f"  {'PASS' if ok else 'FAIL'} {name}: {detail}")
    return r

def chk(name, ok, detail=''):
    """Assert an arbitrary boolean condition (beyond response status)."""
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        failures.append((name, str(detail)[:90]))
    print(f"  {'PASS' if ok else 'FAIL'} {name}: {str(detail)[:65]}")
    return ok

# Setup
r = cmd('new_canvas', {'width': 200, 'height': 200, 'fill': 'white'})
img_id = r.get('image_id') or r.get('results', {}).get('image_id')
print(f"Setup: {r.get('status')} img_id={img_id}")
if r.get('status') != 'success':
    print(f"Setup failed: {r.get('error', '')}", file=sys.stderr)
    sys.exit(1)

print()
print("=== Cat 1: Info ===")
t('get_gimp_info',    cmd('get_gimp_info'))
t('list_images',      cmd('list_images', {}))
t('get_metadata',     cmd('get_image_metadata'))
t('list_layers',      cmd('list_layers', {'image_index': 0}))
t('pixel_color',      cmd('get_pixel_color', {'image_index': 0, 'x': 10, 'y': 10}))
t('get_histogram',    cmd('get_histogram', {'image_index': 0, 'channel': 'value'}))
t('selection_bounds', cmd('get_selection_bounds', {'image_index': 0}))

print()
print("=== Cat 2: Adjustments ===")
t('auto_levels',   cmd('auto_levels', {'image_index': 0}))
t('adjust_curves', cmd('adjust_curves', {'image_index': 0, 'channel': 'value', 'points': [0,0,128,148,255,255]}))
t('brightness',    cmd('adjust_brightness_contrast', {'image_index': 0, 'brightness': 10, 'contrast': 5}))
t('hue_sat',       cmd('adjust_hue_saturation', {'image_index': 0, 'hue': 5, 'saturation': 10, 'lightness': 0}))
t('color_balance', cmd('adjust_color_balance', {'image_index': 0, 'cyan_red': 10, 'magenta_green': 0, 'yellow_blue': -10}))
t('sharpen',       cmd('sharpen',       {'image_index': 0, 'amount': 0.3}))
t('blur',          cmd('blur',          {'image_index': 0, 'radius_x': 1.0, 'radius_y': 1.0}))
t('denoise',       cmd('denoise',       {'image_index': 0}))
t('desaturate',    cmd('desaturate',    {'image_index': 0}))
t('invert',        cmd('invert_colors', {'image_index': 0}))

print()
print("=== Cat 3: Transform ===")
t('scale_image',   cmd('scale_image',   {'image_index': 0, 'width': 150, 'height': 150}))
t('scale_to_fit',  cmd('scale_to_fit',  {'image_index': 0, 'max_width': 120, 'max_height': 120}))
t('crop_to_rect',  cmd('crop_to_rect',  {'image_index': 0, 'x': 0, 'y': 0, 'width': 100, 'height': 100}))
t('rotate_image',  cmd('rotate_image',  {'image_index': 0, 'angle': 90}))
t('flip_image',    cmd('flip_image',    {'image_index': 0, 'direction': 'horizontal'}))
t('resize_canvas', cmd('resize_canvas', {'image_index': 0, 'width': 120, 'height': 120, 'offset_x': 0, 'offset_y': 0}))

print()
print("=== Cat 4: Selections ===")
t('select_rect',    cmd('select_rectangle', {'image_index': 0, 'x': 10, 'y': 10, 'width': 40, 'height': 40}))
t('select_ellipse', cmd('select_ellipse',   {'image_index': 0, 'x': 10, 'y': 10, 'width': 40, 'height': 40}))
# Regression #23: select_by_color must actually create a selection, not
# silently no-op while reporting success. Fill a known color and clear any
# prior selection first, so a leftover selection can't mask a no-op.
# Assert the setup itself succeeds so a broken fill can't skew the real check.
t('select_setup_fill', cmd('fill_layer',  {'image_index': 0, 'color': '#ffffff'}))
t('select_setup_none', cmd('select_none', {'image_index': 0}))
t('select_color',   cmd('select_by_color',  {'image_index': 0, 'color': '#ffffff'}))
_sel = cmd('get_selection_bounds', {'image_index': 0})
chk('select_color_nonempty', _sel.get('results', {}).get('has_selection') is True, _sel.get('results'))
t('select_all',     cmd('select_all',       {'image_index': 0}))
t('select_none',    cmd('select_none',      {'image_index': 0}))
t('invert_sel',     cmd('invert_selection', {'image_index': 0}))
t('modify_sel',     cmd('modify_selection', {'image_index': 0, 'operation': 'grow', 'amount': 3}))

print()
print("=== Cat 5: Layers ===")
t('create_layer',    cmd('create_layer',     {'image_index': 0, 'name': 'TLayer', 'width': 80, 'height': 80}))
t('duplicate_layer', cmd('duplicate_layer',  {'image_index': 0}))
t('list_layers2',    cmd('list_layers',      {'image_index': 0}))
t('rename_layer',    cmd('rename_layer',     {'image_index': 0, 'new_name': 'Renamed'}))
t('set_layer_props', cmd('set_layer_properties', {'image_index': 0, 'opacity': 80}))
t('reorder_layer',   cmd('reorder_layer',    {'image_index': 0, 'layer_name': 'Renamed', 'new_position': 0}))
t('delete_layer',    cmd('delete_layer',     {'image_index': 0, 'layer_name': 'Renamed'}))
t('merge_visible',   cmd('merge_visible_layers', {'image_index': 0}))
t('flatten_image',   cmd('flatten_image',    {'image_index': 0}))

print()
print("=== Cat 6: Drawing ===")
t('fill_layer',     cmd('fill_layer',     {'image_index': 0, 'color': '#ff0000'}))
t('set_colors',     cmd('set_colors',     {'foreground': '#000000', 'background': '#ffffff'}))
t('fill_selection', cmd('fill_selection', {'image_index': 0, 'fill_type': 'foreground'}))
t('draw_line',      cmd('draw_line',      {'image_index': 0, 'x1': 0, 'y1': 0, 'x2': 50, 'y2': 50, 'color': '#000000', 'width': 2}))
t('draw_rect',      cmd('draw_rectangle', {'image_index': 0, 'x': 10, 'y': 10, 'width': 30, 'height': 30, 'color': '#0000ff', 'line_width': 2.0}))
t('draw_ellipse',   cmd('draw_ellipse',   {'image_index': 0, 'x': 10, 'y': 10, 'width': 30, 'height': 30, 'color': '#00ff00', 'line_width': 2.0}))
t('fill_rectangle', cmd('fill_rectangle', {'image_index': 0, 'x': 5, 'y': 5, 'width': 20, 'height': 20, 'color': '#ffff00'}))
t('fill_ellipse',   cmd('fill_ellipse',   {'image_index': 0, 'x': 5, 'y': 5, 'width': 20, 'height': 20, 'color': '#ff00ff'}))
t('gradient_fill',  cmd('gradient_fill',  {'image_index': 0, 'x1': 0, 'y1': 0, 'x2': 80, 'y2': 80}))

print()
print("=== Cat 7: Text ===")
t('add_text',   cmd('add_text',   {'image_index': 0, 'text': 'Hello', 'x': 10, 'y': 10, 'size': 12, 'color': '#000000'}))
t('list_fonts', cmd('list_fonts', {}))

print()
print("=== Cat 8: Filters ===")
t('gaussian_blur', cmd('apply_gaussian_blur', {'image_index': 0, 'radius': 2.0}))
t('pixelate',      cmd('apply_pixelate',      {'image_index': 0, 'block_size': 5}))
t('emboss',        cmd('apply_emboss',        {'image_index': 0}))
t('vignette',      cmd('apply_vignette',      {'image_index': 0}))
t('noise',         cmd('apply_noise',         {'image_index': 0}))
t('drop_shadow',   cmd('apply_drop_shadow',   {'image_index': 0}))

print()
print("=== Cat 9: Filters change pixels ===")
# Regression: GEGL-backed tools used to return success with unchanged pixels.
# Paint a known two-tone pattern, then require each tool to alter the composite.
_info = next(i for i in cmd('list_images', {}).get('results', {}).get('images', []) if i['index'] == 0)
W, H = _info['width'], _info['height']
t('px_flatten', cmd('flatten_image',  {'image_index': 0}))
t('px_fill',    cmd('fill_layer',     {'image_index': 0, 'color': '#a0a0a0'}))
t('px_rect',    cmd('fill_rectangle', {'image_index': 0, 'x': 0, 'y': 0, 'width': W // 2, 'height': H, 'color': '#404040'}))

def changes(name, tool, params):
    """Run a tool and assert the image composite actually changed."""
    before = bitmap({'image_index': 0})
    r = t(name, cmd(tool, dict(params, image_index=0)))
    after = bitmap({'image_index': 0})
    chk(name + '_changes_pixels', before is not None and after is not None and before != after,
        'pixels changed' if before != after else 'pixels unchanged')
    return r

changes('px_sharpen',       'sharpen',             {'amount': 80, 'radius': 2.0})
changes('px_blur',          'blur',                {'radius_x': 2.0, 'radius_y': 2.0})
changes('px_gaussian_blur', 'apply_gaussian_blur', {'radius': 2.0})
changes('px_pixelate',      'apply_pixelate',      {'block_size': 8})
changes('px_emboss',        'apply_emboss',        {})
changes('px_vignette',      'apply_vignette',      {})
changes('px_noise',         'apply_noise',         {'amount': 0.3})
changes('px_denoise',       'denoise',             {})

# Drop shadow must be blurred (soft edge) and keep the requested opacity.
t('px_box_layer', cmd('create_layer',   {'image_index': 0, 'name': 'Box'}))
t('px_box_fill',  cmd('fill_rectangle', {'image_index': 0, 'layer_name': 'Box', 'x': 30, 'y': 30,
                                         'width': 40, 'height': 40, 'color': '#ff0000'}))
changes('px_drop_shadow', 'apply_drop_shadow', {'layer_name': 'Box', 'offset_x': 8, 'offset_y': 8,
                                                'blur_radius': 4, 'opacity': 50})
_layers = cmd('list_layers', {'image_index': 0}).get('results', {}).get('layers', [])
_shadow = next((lyr for lyr in _layers if lyr['name'] == 'Drop Shadow'), None)
chk('px_shadow_opacity', _shadow is not None and round(_shadow['opacity']) == 50, _shadow and _shadow['opacity'])
_alpha = None
if _shadow:
    # Left edge of the shadow rectangle (image x=38) in layer coordinates.
    _ox, _oy = _shadow['offsets'][1], _shadow['offsets'][2]
    _px = cmd('get_pixel_color', {'image_index': 0, 'layer_name': 'Drop Shadow', 'x': 38 - _ox, 'y': 50 - _oy})
    _alpha = _px.get('results', {}).get('alpha')
chk('px_shadow_blurred', _alpha is not None and 0 < _alpha < 255, f'edge alpha={_alpha}')

print()
print("=== Cat 10: Export formats ===")
# Regression: .jpg exports used to contain PNG bytes, and export_web_optimized
# always wrote image.jpg / image.png.
out_dir = tempfile.mkdtemp(prefix='gimp_mcp_test_')
for fmt, want in (('png', 'png'), ('jpg', 'jpeg')):
    path = os.path.join(out_dir, 'export_test.' + fmt)
    t('export_' + fmt, cmd('export_image', {'image_index': 0, 'file_path': path, 'format': fmt}))
    chk('export_' + fmt + '_magic', magic(path) == want, magic(path))
_web = t('export_web', cmd('export_web_optimized', {'image_index': 0, 'output_dir': out_dir, 'max_width': 64}))
_web = _web.get('results', {})
for key, want in (('jpeg_path', 'jpeg'), ('png_path', 'png')):
    chk('export_web_' + want + '_magic', magic(_web.get(key, '')) == want, magic(_web.get(key, '')))
chk('export_web_named', bool(_web) and not os.path.basename(_web.get('jpeg_path', '')).startswith('image.'),
    _web.get('jpeg_path'))
_batch = t('batch_export_jpg', cmd('batch_export', {'image_index': 0, 'output_dir': out_dir, 'format': 'jpg'}))
_exported = _batch.get('results', {}).get('exported', [])
chk('batch_export_jpg_magic', bool(_exported) and magic(_exported[0]['file_path']) == 'jpeg',
    _exported and magic(_exported[0]['file_path']))
shutil.rmtree(out_dir, ignore_errors=True)

print()
print("=== Cat 11: get_image_bitmap image_index ===")
# Regression: get_image_bitmap always rendered images[0]. Add a small
# display-less duplicate and require each index to return its own size.
t('dup_image', send({'cmds': ["_t_dup = Gimp.get_images()[0].duplicate()", "_t_dup.scale(48, 32)"]}))
_imgs = cmd('list_images', {}).get('results', {}).get('images', [])
for label, info in (('dup',  next((i for i in _imgs if (i['width'], i['height']) == (48, 32)), None)),
                    ('orig', next((i for i in _imgs if i['image_id'] == img_id), None))):
    _res = cmd('get_image_bitmap', {'image_index': info['index']}).get('results', {}) if info else {}
    chk('bitmap_index_' + label,
        info is not None and (_res.get('width'), _res.get('height')) == (info['width'], info['height']),
        f"want {info and (info['width'], info['height'])} got {(_res.get('width'), _res.get('height'))}")
t('dup_image_delete', send({'cmds': ["_t_dup.delete()"]}))

print()
print(f"=== TOTAL: {passed}/{passed+failed} PASSED ===")
if failures:
    print("Failures:")
    for n, e in failures:
        print(f"  {n}: {e}")

sys.exit(1 if failures else 0)
