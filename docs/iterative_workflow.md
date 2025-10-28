# Iterative Workflow with GIMP MCP

## The Golden Rule

**Check your work after every 3-5 operations. Don't continue blindly.**

## Why Iterative Workflow Matters

### Common Problems Without Validation
- AI treats GIMP like a single-canvas drawing tool
- Paints everything on one layer, creating overlapping messes
- Doesn't check work until explicitly asked
- Fixes problems by painting over them, creating more problems
- Doesn't leverage GIMP's powerful features (layers, masks, selections)

### The Better Approach
- Use layers to separate elements (background, body, head, details)
- Check work after each major step
- Use proper selection tools and masks
- Build incrementally with validation
- Fix issues properly by working on the right layer

---

## Phase-Based Workflow

### Phase 1: Planning (BEFORE drawing anything)
```python
# 1. Understand what you're working with
metadata = get_image_metadata()
print(f"Canvas: {metadata['basic']['width']}x{metadata['basic']['height']}")
print(f"Existing layers: {len(metadata['structure']['layers'])}")

# 2. Plan your layer structure
# Example for drawing an animal:
# - background_layer: sky and ground
# - body_layer: main body and legs
# - head_layer: head and ears
# - details_layer: eyes, nose, facial features
# - texture_layer: fur/wool texture overlay
```

### Phase 2: Layer Setup
```python
# Create layers BEFORE drawing
["from gi.repository import Gimp",
 "images = Gimp.get_images()",
 "image = images[0]",
 "width = image.get_width()",
 "height = image.get_height()",

 # Create layers from back to front
 "body_layer = Gimp.Layer.new(image, 'Body', width, height, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)",
 "image.insert_layer(body_layer, None, 0)",

 "head_layer = Gimp.Layer.new(image, 'Head', width, height, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)",
 "image.insert_layer(head_layer, None, 0)",

 "details_layer = Gimp.Layer.new(image, 'Details', width, height, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)",
 "image.insert_layer(details_layer, None, 0)"]
```

### Phase 3: Incremental Drawing with Validation

**Pattern:**
1. Set active layer
2. Draw 3-5 elements
3. Validate with get_image_bitmap()
4. Review and fix issues
5. Repeat

**Example:**
```python
# Step 1: Draw body on body layer
call_api("exec", ["pyGObject-console", [
    "drawable = body_layer",
    # Draw body operations...
    "Gimp.displays_flush()"
]])

# Step 2: VALIDATE (critical!)
bitmap = get_image_bitmap(max_width=1024, max_height=1024)
# Actually look at bitmap - does the body look right?

# Step 3: Fix issues if any (on correct layer!)
if issues_found:
    call_api("exec", ["pyGObject-console", [
        "drawable = body_layer",  # Work on right layer
        # Fix operations...
        "Gimp.displays_flush()"
    ]])

# Step 4: Move to next layer
call_api("exec", ["pyGObject-console", [
    "drawable = head_layer",
    # Draw head operations...
    "Gimp.displays_flush()"
]])

# Step 5: VALIDATE again
bitmap = get_image_bitmap(max_width=1024, max_height=1024)
```

---

## Common Mistakes to Avoid

### ❌ Mistake 1: Painting Over Problems
```python
# WRONG: Nose got covered, so paint over everything
["Gimp.context_set_foreground(face_color)",
 "# Paint large area to cover the problem",
 "# This creates more mess!"]
```

### ✅ Correct: Fix on Right Layer
```python
# RIGHT: Fix the specific issue
["# Switch to layer that has the problem",
 "drawable = head_layer",
 "# Clear the area properly with selection or edit_clear",
 "# Redraw just what's needed",
 "Gimp.displays_flush()"]

# Then validate
get_image_bitmap(max_width=1024, max_height=1024)
```

### ❌ Mistake 2: No Validation Until End
```python
# WRONG: Draw 50 operations then check
draw_background()
draw_body()
draw_head()
draw_details()
draw_texture()
# Now check... oh no, something went wrong at step 2!
```

### ✅ Correct: Continuous Validation
```python
# RIGHT: Validate frequently
draw_background()
validate()  # ← Check here

draw_body()
validate()  # ← And here

draw_head()
validate()  # ← And here
# Much easier to fix problems early!
```

---

## Self-Critique Questions

After each validation with `get_image_bitmap()`, ask yourself:

### 1. Layer Issues
- Are elements on the correct layer?
- Are layers overlapping correctly?
- Do I need to reorder layers?

### 2. Visual Quality
- Do shapes look like I intended?
- Are edges sharp and clean (not blurry)?
- Are colors correct? (Use get_context_state() to verify)
- Are there unwanted artifacts or overlaps?
- Did I avoid unnecessary feathering? (Check get_context_state())

### 2a. Regional Verification (Efficient)
- Instead of checking full image, extract just the modified region
- Higher resolution possible for small areas
- Faster feedback, saves resources
- Example: get_image_bitmap(region={"origin_x": 100, "origin_y": 50, "width": 200, "height": 200})

### 3. Selection Cleanup
- Did I clear selections after drawing?
- Are there selection artifacts visible?

### 4. Next Steps
- Is it safe to continue, or should I fix this first?
- What's the next logical element to draw?
- Which layer should it go on?

---

## Advanced: Layer Management

### Create Multiple Layers
```python
# Create organized layer structure
["from gi.repository import Gimp",
 "image = Gimp.get_images()[0]",
 "width, height = image.get_width(), image.get_height()",

 # Background layer
 "bg_layer = Gimp.Layer.new(image, 'Background', width, height, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)",
 "image.insert_layer(bg_layer, None, 0)",

 # Object layer
 "obj_layer = Gimp.Layer.new(image, 'Object', width, height, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)",
 "image.insert_layer(obj_layer, None, 0)",

 # Details layer on top
 "detail_layer = Gimp.Layer.new(image, 'Details', width, height, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)",
 "image.insert_layer(detail_layer, None, 0)"]
```

### Switch Between Layers
```python
# Work on different layers
["# Get all layers",
 "layers = image.get_layers()",

 "# Work on background (bottom layer)",
 "bg_drawable = layers[2]",  # Layers are 0=top, higher indices=lower
 "# ... draw on background ...",

 "# Switch to top layer for details",
 "detail_drawable = layers[0]",
 "# ... draw details ...",
 "Gimp.displays_flush()"]
```

### Layer Visibility and Opacity
```python
# Control layer visibility and blending
["layer = image.get_layers()[0]",

 "# Hide/show layer",
 "layer.set_visible(False)",  # Hide
 "layer.set_visible(True)",   # Show

 "# Adjust opacity (0-100)",
 "layer.set_opacity(50.0)",   # 50% transparent

 "Gimp.displays_flush()"]
```

### Fix Mistakes on Specific Layer
```python
# Erase part of a layer without affecting others
["# Select the layer with the mistake",
 "layer_to_fix = image.get_layers()[1]",
 "drawable = layer_to_fix",

 "# Select area to clear",
 "Gimp.Image.select_rectangle(image, Gimp.ChannelOps.REPLACE, x, y, width, height)",

 "# Clear selection (makes it transparent)",
 "Gimp.Drawable.edit_clear(drawable)",

 "# Redraw correctly",
 "Gimp.context_set_foreground(correct_color)",
 "Gimp.Drawable.edit_fill(drawable, Gimp.FillType.FOREGROUND)",

 "Gimp.Selection.none(image)",
 "Gimp.displays_flush()"]
```

---

## Advanced: Using Masks and Selections

### Layer Masks for Non-Destructive Editing
```python
# Add a mask to control visibility
["mask = Gimp.LayerMask.new(layer, Gimp.AddMaskType.WHITE)",
 "layer.add_mask(mask)",
 "# Now paint on mask to hide/show parts"]
```

### Selection-Based Operations
```python
# Use selections for precise control
["# Create selection",
 "Gimp.Image.select_ellipse(image, Gimp.ChannelOps.REPLACE, x, y, w, h)",

 "# Fill selection (NO feathering by default for sharp, clean edges)",
 "Gimp.Drawable.edit_fill(drawable, Gimp.FillType.FOREGROUND)",

 "# CRITICAL: Clear selection",
 "Gimp.Selection.none(image)",
 "Gimp.displays_flush()"]

# Only use feathering when specifically needed for artistic effects:
# ["Gimp.Selection.feather(image, radius)"]  # Use ONLY if soft edges are explicitly desired
```

---

## Summary: The Professional Workflow

The key to success with GIMP MCP:

1. **Plan** layer structure first
2. **Build** incrementally (3-5 operations at a time)
3. **Validate** after each build phase with `get_image_bitmap()`
4. **Fix** issues immediately on correct layer
5. **Continue** only when current phase is correct

**Don't treat GIMP like a single canvas - leverage its professional features!**

Work like a professional digital artist, not like someone with a single paintbrush on a single canvas.
