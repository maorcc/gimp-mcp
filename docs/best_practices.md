# GIMP MCP Best Practices & Recipes

## ✅ FILLING SHAPES - The Right Way

**DO: Use Polygon Selection for Filled Shapes**
```python
# Best method for solid filled shapes
points = [x1, y1, x2, y2, x3, y3, ...]  # Flat array of coordinates
Gimp.Image.select_polygon(image, Gimp.ChannelOps.REPLACE, points)
Gimp.context_set_foreground(color)
Gimp.Drawable.edit_fill(drawable, Gimp.FillType.FOREGROUND)
Gimp.Selection.none(image)
Gimp.displays_flush()
```

**DON'T: Use Paintbrush for Filling Areas**
```python
# ❌ This creates thin strokes, not solid fills
points = [x1, y1, x2, y2, x3, y3, ...]
Gimp.paintbrush_default(drawable, points)  # Creates outline only!
```

**WHY**: The paintbrush tool draws along a path with the current brush size. For solid fills, polygon selection ensures complete coverage.

## ✅ BEZIER PATHS - For Outlines Only

**DO: Use Bezier Paths for Smooth Outlines**
```python
# Bezier paths are perfect for stroked outlines with curves
path = Gimp.Path.new(image, 'curved_outline')
image.insert_path(path, None, 0)
stroke_id = path.bezier_stroke_new_moveto(x1, y1)
path.bezier_stroke_cubicto(stroke_id, cx1, cy1, cx2, cy2, x2, y2)
# Stroke creates the outline
Gimp.Drawable.edit_stroke_item(drawable, path)
Gimp.displays_flush()
```

**DON'T: Try to Fill Bezier Paths Directly**
```python
# ❌ This method doesn't exist in GIMP 3.0
path.to_selection()  # AttributeError!
```

**WHY**: GIMP 3.0's bezier paths are designed for vector strokes. For filled curved shapes, approximate with polygon selections or use multiple overlapping ellipses.

## ✅ VARIABLE PERSISTENCE - Reuse, Don't Repeat

**DO: Initialize Once, Reuse**
```python
# First call - set up context
["from gi.repository import Gimp, Gegl",
 "images = Gimp.get_images()",
 "image1 = images[0]",
 "layer1 = image1.get_layers()[0]",
 "drawable1 = layer1"]

# Later calls - variables still available
["Gimp.Selection.all(image1)",
 "Gimp.Drawable.edit_fill(drawable1, Gimp.FillType.FOREGROUND)"]
```

**DON'T: Repeat Imports and Initialization**
```python
# ❌ Wasteful - these persist between calls
["from gi.repository import Gimp",  # Already imported!
 "images = Gimp.get_images()",      # Already have this!
 "image1 = images[0]"]              # Already assigned!
```

**WHY**: PyGObject console maintains a persistent Python environment. Variables, imports, and functions remain in memory between calls.

---

## ✅ SELECTION FEATHERING - Use Sparingly

**DO: Use Sharp Selections by Default**
```python
# Most shapes should have clean, sharp edges
points = [x1, y1, x2, y2, x3, y3, ...]
Gimp.Image.select_polygon(image, Gimp.ChannelOps.REPLACE, points)
# NO feathering - fills will have sharp, clean edges
Gimp.Drawable.edit_fill(drawable, Gimp.FillType.FOREGROUND)
Gimp.Selection.none(image)
```

**DON'T: Add Feathering Without Good Reason**
```python
# ❌ This creates blurry, unclear edges
Gimp.Image.select_ellipse(image, Gimp.ChannelOps.REPLACE, x, y, w, h)
Gimp.Selection.feather(image, 10)  # Blurs the edges!
Gimp.Drawable.edit_fill(drawable, Gimp.FillType.FOREGROUND)
```

**WHEN to Use Feathering:**
- Soft shadows or glows
- Blending elements naturally into backgrounds
- Creating soft, artistic effects
- ONLY when explicitly requested by user

**WHY**: Sharp edges look professional and clean. Feathering creates blurry, unclear edges that make drawings look unprofessional unless specifically needed for artistic effect.

---

## Common Recipes

### Initialization
```python
# Basic initialization
["from gi.repository import Gimp, Gegl"]

# Recommended full initialization
["from gi.repository import Gimp, Gegl",
 "images = Gimp.get_images()",
 "image1 = images[0]",
 "layer1 = image1.get_layers()[0]",
 "drawable1 = layer1"]
```

### Setting Colors
```python
# Set foreground to red
["red_color = Gegl.Color.new('red')",
 "Gimp.context_set_foreground(red_color)"]

# Set foreground to black
["black_color = Gegl.Color.new('black')",
 "Gimp.context_set_foreground(black_color)"]

# Set background to white
["white_color = Gegl.Color.new('white')",
 "Gimp.context_set_background(white_color)"]
```

### Drawing Operations

**Draw a Line**
```python
["Gimp.pencil(drawable1, [0, 0, 200, 200])",
 "Gimp.displays_flush()"]
```

**Draw a Filled Ellipse**
```python
["Gimp.Image.select_ellipse(image1, Gimp.ChannelOps.REPLACE, 100, 100, 30, 20)",
 "Gimp.Drawable.edit_fill(drawable1, Gimp.FillType.FOREGROUND)",
 "Gimp.Selection.none(image1)",
 "Gimp.displays_flush()"]
```

**Paint a Curve with Brush (for strokes, not fills)**
```python
# Note: Use this for decorative strokes or outlines, NOT for filling shapes
["Gimp.paintbrush_default(drawable1, [50.0, 50.0, 150.0, 200.0, 250.0, 50.0, 350.0, 200.0])",
 "Gimp.displays_flush()"]
```

**Draw a Bezier Curve (for outlines)**
```python
["path = Gimp.Path.new(image1, 'my_bezier_path')",
 "image1.insert_path(path, None, 0)",
 "stroke_id = path.bezier_stroke_new_moveto(100, 100)",
 "path.bezier_stroke_cubicto(stroke_id, 150, 50, 250, 150, 300, 100)",
 "Gimp.Drawable.edit_stroke_item(drawable1, path)",
 "Gimp.Selection.none(image1)",
 "Gimp.displays_flush()"]
```

### Image Management

**Create a New Image**
```python
["from gi.repository import Gimp, Gegl",
 "image1 = Gimp.Image.new(350, 800, Gimp.ImageBaseType.RGB)",
 "layer1 = Gimp.Layer.new(image1, 'Background', 350, 800, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)",
 "image1.insert_layer(layer1, None, 0)",
 "drawable1 = layer1",
 "white_color = Gegl.Color.new('white')",
 "Gimp.context_set_background(white_color)",
 "Gimp.Drawable.edit_fill(drawable1, Gimp.FillType.BACKGROUND)",
 "Gimp.Display.new(image1)"]
```

**Get Open Filenames**
```python
["print([x.get_file().get_path() for x in Gimp.get_images()])"]
```

**Copy Layer Between Images**
```python
["image1 = Gimp.get_images()[0]",
 "image2 = Gimp.get_images()[1]",
 "width = image1.get_width()",
 "height = image1.get_height()",
 "image1.select_rectangle(Gimp.ChannelOps.REPLACE, 0, 0, width, height)",
 "image1_layers = image1.get_selected_layers()",
 "drawable = image1_layers[0]",
 "Gimp.edit_copy([drawable])",
 "image2_layers = image2.get_layers()",
 "target_drawable = image2_layers[0]",
 "floating_sel = Gimp.edit_paste(target_drawable, True)[0]",
 "Gimp.floating_sel_anchor(floating_sel)",
 "Gimp.displays_flush()"]
```

---

## Tips & Guidelines

### Verification After Drawing
After drawing operations, capture a high-resolution region to verify output quality:
- Use `get_image_bitmap()` with region parameter to check specific areas
- Extract only the modified area (saves resources, faster feedback)
- Can use higher resolution for small regions
- Example: After drawing a face, get just the face region at high quality
- Catch issues early before continuing to next elements

### Context State Awareness
Check `get_context_state()` before operations that depend on settings:
- User can change colors, brush, or settings in GIMP UI at any time
- Verify foreground/background colors before drawing
- Check if feathering is enabled (to avoid unwanted blurry edges)
- Ensure opacity and blend mode are as expected
- Example: Before drawing red circle, verify foreground is actually red

### API Verification
- Before executing any API command you haven't verified, consult the documentation at https://developer.gimp.org/api/3.0/libgimp/
- After executing a command, verify GIMP responded with a successful message, e.g., `{"status": "success", "results": ["", "", ...]}`

### Display Updates
- After drawing operations, always call `Gimp.displays_flush()`
- After selection operations for drawing, unselect with `Gimp.Selection.none(image)`

### Layer Management
- When filling layers with color, ensure the layer has an alpha channel using `Gimp.Layer.add_alpha()`
- Use `Gimp.Drawable.fill()` for reliable full-layer fills
- Specify colors precisely with `rgb(R, G, B)` or `rgba(R, G, B, A)` to avoid transparency issues

### Context Efficiency
- No need to repeat import commands - once imported, packages remain available
- Variables persist between calls - initialize once, reuse many times
- Use `Gimp.context_push()` and `Gimp.context_pop()` to save/restore context when needed

---

## ✅ SELF-CRITIQUE CHECKLIST

After calling `get_image_bitmap()`, systematically check:

### Visual Inspection
- [ ] Do all shapes match their intended form?
- [ ] Are edges sharp and clean (not blurry)?
- [ ] Are colors correct and consistent?
- [ ] Are there any unwanted overlaps or artifacts?
- [ ] Is the overall composition balanced?

### Technical Inspection
- [ ] Are elements on correct layers?
- [ ] Were all selections cleared after use?
- [ ] Is Gimp.displays_flush() called after drawing?
- [ ] Are feather/antialiasing settings appropriate?

### Common Artifacts to Look For
- **Blurry/cloudy edges**: Usually from unwanted feathering - remove feathering for clean edges
- **Cloudy areas**: From feathered selections overlapping - avoid feathering unless explicitly needed
- **Missing elements**: Drew on wrong layer or forgot flush
- **Unexpected colors**: Forgot to set foreground/background color
- **Rectangular artifacts**: Forgot to clear selection

### Action Based on Inspection

**If everything looks good:**
- Proceed to next phase
- Document what works for future reference

**If issues found:**
- STOP drawing new elements
- Identify which layer has the problem
- Fix on that specific layer
- Validate fix with another get_image_bitmap()
- Only continue when satisfied

**Never:**
- Paint over problems (creates more problems)
- Continue when something looks wrong
- Skip validation "to save time"

---

These patterns are based on practical experience and will help you succeed faster with GIMP MCP operations.
