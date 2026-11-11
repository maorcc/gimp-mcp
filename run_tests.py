#!/usr/bin/env python3
import socket
import json
import sys

def cmd(t, params=None):
    s = socket.socket()
    s.settimeout(20)
    s.connect(('127.0.0.1', 9877))
    msg = {'type': t, 'params': params if params is not None else {}}
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
_hist = t('get_histogram', cmd('get_histogram', {'image_index': 0, 'channel': 'value'}))
# Regression #47: the canvas is still a uniform white 200x200 fill here, so
# every statistic is known. Reading the PDB status slot as 'mean' (the
# off-by-one fixed in #48) gives mean=3 and shifts every other field.
_h = _hist.get('results', {})
_expected = {'mean': 255.0, 'std_dev': 0.0, 'median': 255.0, 'pixels': 40000.0, 'count': 40000.0}
chk('histogram_values',
    all(isinstance(_h.get(k), (int, float)) and abs(_h[k] - v) < 0.01 for k, v in _expected.items()),
    _h)
# A uniform fill has std_dev 0, the same as _safe()'s fallback, so also check
# a non-uniform image: columns 0-49 black, the rest white (1 in 4 black).
# mean = 0.75 * 255, std_dev = 255 * sqrt(0.25 * 0.75), median = 255.
cmd('fill_rectangle', {'image_index': 0, 'x': 0, 'y': 0, 'width': 50, 'height': 200, 'color': '#000000'})
_h = cmd('get_histogram', {'image_index': 0, 'channel': 'value'}).get('results', {})
_expected = {'mean': 191.25, 'std_dev': 110.4182, 'median': 255.0, 'pixels': 40000.0, 'count': 40000.0}
chk('histogram_values_mixed',
    all(isinstance(_h.get(k), (int, float)) and abs(_h[k] - v) < 0.01 for k, v in _expected.items()),
    _h)
cmd('fill_layer', {'image_index': 0, 'color': '#ffffff'})  # restore the white canvas for later tests
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
# The filter tools above only check status, and _apply_gegl_filter used to
# report success without applying anything. Each check here starts from a
# known image and asserts a change that only the filter itself can make.
cmd('new_canvas', {'width': 200, 'height': 200, 'fill': 'white'})


def px(x, y):
    return cmd('get_pixel_color', {'image_index': 0, 'x': x, 'y': y}).get('results', {}).get('color_rgb')


def std_dev():
    return cmd('get_histogram', {'image_index': 0, 'channel': 'value'}).get('results', {}).get('std_dev')


def half_black():
    """White canvas with columns 0-149 black."""
    cmd('select_none', {'image_index': 0})
    cmd('fill_layer', {'image_index': 0, 'color': '#ffffff'})
    cmd('fill_rectangle', {'image_index': 0, 'x': 0, 'y': 0, 'width': 150, 'height': 200, 'color': '#000000'})


# Pixelate: the 100px block over columns 100-199 is half black, half white.
half_black()
t('f_pixelate', cmd('apply_pixelate', {'image_index': 0, 'block_size': 100}))
_p = px(120, 50)
chk('f_pixelate_blends', _p is not None and 0 < _p[0] < 255, _p)

# Gaussian blur: 5px left of the black/white edge picks up some white.
half_black()
t('f_gaussian_blur', cmd('apply_gaussian_blur', {'image_index': 0, 'radius': 10.0}))
_p = px(145, 50)
chk('f_gaussian_blur_spreads', _p is not None and _p[0] > 0, _p)

# Emboss: a flat white area is shaded to a gray, not left white.
cmd('fill_layer', {'image_index': 0, 'color': '#ffffff'})
t('f_emboss', cmd('apply_emboss', {'image_index': 0}))
_p = px(100, 100)
chk('f_emboss_shades', _p is not None and _p[0] < 255, _p)

# Vignette: corners darken while the center stays white.
cmd('fill_layer', {'image_index': 0, 'color': '#ffffff'})
t('f_vignette', cmd('apply_vignette', {'image_index': 0}))
_c, _m = px(0, 0), px(100, 100)
chk('f_vignette_darkens_corner', _c is not None and _m is not None and _c[0] < _m[0], {'corner': _c, 'center': _m})

# Noise, then denoise: a flat gray gains variation, then loses some of it.
cmd('fill_layer', {'image_index': 0, 'color': '#808080'})
t('f_noise', cmd('apply_noise', {'image_index': 0, 'amount': 0.5}))
_noisy = std_dev()
chk('f_noise_adds_variation', isinstance(_noisy, (int, float)) and _noisy > 1.0, _noisy)
t('f_denoise', cmd('denoise', {'image_index': 0, 'strength': 100}))
_clean = std_dev()
chk('f_denoise_reduces_variation',
    isinstance(_clean, (int, float)) and isinstance(_noisy, (int, float)) and _clean < _noisy,
    {'before': _noisy, 'after': _clean})

# Bad arguments must now fail instead of reporting success.
_r = cmd('apply_vignette', {'image_index': 0, 'softness': 3.0})
chk('f_vignette_rejects_out_of_range', _r.get('status') == 'error', _r.get('error'))
_r = cmd('apply_vignette', {'image_index': 0, 'shape': 'hexagon'})
chk('f_vignette_rejects_bad_shape', _r.get('status') == 'error', _r.get('error'))

print()
print(f"=== TOTAL: {passed}/{passed+failed} PASSED ===")
if failures:
    print("Failures:")
    for n, e in failures:
        print(f"  {n}: {e}")

sys.exit(1 if failures else 0)
