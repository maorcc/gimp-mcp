
# RECIPE BOOK

## Initialization:
```python
["from gi.repository import Gimp"]
```
## Recommended additional initialization
```python
["images = Gimp.get_images()", "image = images[0]", "layers = image.get_layers()", "layer = layers[0]", "drawable = layer"]
```
## EXAMPLES:
- Commands to draw a line on my gimp screen:
["Gimp.pencil(drawable, [0, 0, 200, 200])","Gimp.displays_flush()"]
- set foreground color black
```python
["black_color = Gegl.Color.new(\"black\")", "Gimp.context_set_foreground(black_color)"]
```
- set fg color red
```python
["red_color = Gegl.Color.new(\"red\")", "Gimp.context_set_foreground(red_color)"]
```
```python
["Gimp.context_push()"]
```
```python
["Gimp.Image.select_ellipse(image, Gimp.ChannelOps.REPLACE, 100, 100, 30, 20)"]
```
```python
["Gimp.Drawable.edit_fill(drawable, Gimp.FillType.FOREGROUND)"]
```
```python
["Gimp.Selection.none(image)"]
```

# Tips:
- before executing any API command you have not verified before, verify it in the documentation at https://developer.gimp.org/api/3.0/libgimp/ . This documentaion is your bible.
- After executing a command, verify GIMP responded with a successfull message, e.g. {"status": "success", "results": ["", "", "", "", "", ""]}
- No need to repeat an "import" command in GIMP. once you gave instruction to import some package, no need to import it again.
- After drawing an element on the screen, do "Gimp.displays_flush()". If you used selection operation for drawing, unselect it by "Gimp.Selection.none(image1)".
- When filling layers with color, ensure the layer has an alpha channel using `Gimp.Layer.add_alpha()`. Use `Gimp.Drawable.fill()` for reliable full-layer fills, and specify colors precisely with `rgb(R, G, B)` or `rgba(R, G, B, A)` to avoid transparency issues.

# Recipes:
- initialization: ["from gi.repository import Gimp", "images = Gimp.get_images()", "image1 = images[0]", "layers = image1.get_layers()", "layer1 = layers[0]", "drawable1 = layer1"]
- draw a line: ["Gimp.pencil(drawable1, [0, 0, 200, 200])","Gimp.displays_flush()"]
- draw a filled ellipse: ["Gimp.Image.select_ellipse(image1, Gimp.ChannelOps.REPLACE, 100, 100, 30, 20)", "Gimp.Drawable.edit_fill(drawable1, Gimp.FillType.FOREGROUND)", "Gimp.Selection.none(image1)", "Gimp.displays_flush()"]
- paint a curve with a brush: ["Gimp.paintbrush_default(drawable1, [50.0, 50.0, 150.0, 200.0, 250.0, 50.0, 350.0, 200.0])", "Gimp.displays_flush()"]
- draw a bezier curve: ["path = Gimp.Path.new(image1, \"my_bezier_path\")", "image1.insert_path(path, None, 0)", "stroke_id = path.bezier_stroke_new_moveto(100, 100)", "path.bezier_stroke_cubicto(stroke_id, 150, 50, 250, 150, 300, 100)", "Gimp.Drawable.edit_stroke_item(drawable1, path)", "Gimp.Selection.none(image1)", "Gimp.displays_flush()"]
- create a new image: ["from gi.repository import Gimp, Gegl", "image1 = Gimp.Image.new(350, 800, Gimp.ImageBaseType.RGB)", "layer1 = Gimp.Layer.new(image1, \"Background\", 350, 800, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)", "image1.insert_layer(layer1, None, 0)", "drawable1 = layer1", "white_color = Gegl.Color.new(\"white\")", "Gimp.context_set_background(white_color)", "Gimp.Drawable.edit_fill(drawable1, Gimp.FillType.BACKGROUND)", "Gimp.Display.new(image1)"]
- get open filenames: ["[print([x.get_file().get_path() for x in Gimp.get_images()])"]
- copy the entire background layer of second image to the background layer of the first image: "image1 = Gimp.get_images()[0]", "image2 = Gimp.get_images()[1]", "width = image1.get_width()", "height = image1.get_height()", "image1.select_rectangle(Gimp.ChannelOps.REPLACE, 0, 0, width, height)", "image1_layers = image1.get_selected_layers()", "drawable = image1_layers[0]", "Gimp.edit_copy([drawable])", "image2_layers = image2.get_layers()", "target_drawable = image2_layers[0]", "floating_sel = Gimp.edit_paste(target_drawable, True)[0]", "Gimp.floating_sel_anchor(floating_sel)", "Gimp.displays_flush()"
