# GIMP Python-Fu via MCP Documentation

## Overview
This document describes how to execute Python-Fu commands in GIMP using the MCP (Model Context Protocol) interface through the `gimp:call_api` function.

## Basic Method

### Function Call Structure
```json
{
  "api_path": "exec",
  "args": ["python-fu-console", ["<python_code>"]]
}
```

### Parameters Explanation
- **api_path**: `"exec"` - Accesses GIMP's Procedure Database (PDB) to run a procedure
- **args**: Array with two elements:
  - `"python-fu-console"` - The Python-Fu console procedure name
  - `["<python_code>"]` - Array containing the Python code string to execute
         all commands are executed in the same process context, 
         so ["x=5","print(x)"] will work

## Tested Examples

### Simple Print Command (Console)
```json
{
  "api_path": "exec",
  "args": ["python-fu-console", ["print('hello world')"]]
}
```

**Result**: Returns `"hello world"` when successful.

### Simple Expression Evaluation
```json
{
  "api_path": "exec",
  "args": ["python-fu-eval", ["2 + 2"]]
}
```

**Result**: Returns `"4"` - the actual result of the Python expression.

## Important Notes

### String Escaping
- Use single quotes inside double quotes: `["print('hello world')"]`
- Or escape double quotes: `["print(\"hello world\")"]`
- Python code must be properly escaped as a JSON string

### Python-Fu Procedure Types
- **`python-fu-console`**: Executes Python code and returns output.
- **`python-fu-eval`**: Evaluates Python expressions and returns the actual result value.

### Return Values
- **python-fu-console**: Returns command output on success, error messages on failure
- **python-fu-eval**: Returns the actual result of the Python expression
- Print statements from python-fu-console are returned in MCP response
- Errors will return error messages or exception details

### Limitations
- Commands execute in GIMP's Python-Fu environment
- Access to GIMP's Python API and loaded modules

## GIMP 3.0 API Findings

### Working Methods
- **`Gimp.get_images()`**: Returns a list of currently open images
  ```python
  images = Gimp.get_images()  # Returns list of Image objects
  ```

- **`image.get_layers()`**: Gets layers from an image object
  ```python
  layers = image.get_layers()  # Returns list of Layer objects
  ```

- **Get foreground color** 
  ```python
    fg_color = Gimp.context_get_foreground(); 
    print(f'Current foreground: {fg_color}'); 
    print(type(fg_color))
  ```
  
- **Set foreground color** 
  ```python
    from gi.repository import Gegl; 
    black_color = Gegl.Color.new('black'); 
    Gimp.context_set_foreground(black_color); 
    print('Foreground color set to black')`
  ```
  
 - **Basic object access**:
  ```python
  images = Gimp.get_images()
  image = images[0]  # Get first image
  layers = image.get_layers()
  layer = layers[0]  # Get first layer
  ```

- **Draw a line**:
  ```python
Gimp.pencil(Gimp.get_images().get_layers()[0], [0, 0, 200, 200])
Gimp.displays_flush()
    ```

- **draw a filled ellipse**: 
  ```python
Gimp.Image.select_ellipse(image, Gimp.ChannelOps.REPLACE, 100, 100, 30, 20)
Gimp.Drawable.edit_fill(drawable, Gimp.FillType.FOREGROUND)
Gimp.displays_flush()
    ```

### Non-Working Methods (GIMP 3.0 Changes)
- **`Gimp.get_active_image()`**: ❌ Does not exist
- **`Gimp.list_images()`**: ❌ Does not exist  
- **`Gimp.get_active_layer()`**: ❌ Does not exist
- **`from gimpfu import *`**: ❌ gimpfu module not available in GIMP 3.0

### API Structure Insights
- GIMP 3.0 uses GObject Introspection (gi.repository.Gimp)
- PDB object type: `<class 'gi.repository.Gimp.PDB'>`
- Image objects: `<Gimp.Image object at 0x... (GimpImage at 0x...)>`
- Layer objects: `<Gimp.Layer object at 0x... (GimpLayer at 0x...)>`
- The API has significantly changed from GIMP 2.x to 3.0

### Tested Working Example
- **Get layers** 
```json
{
  "api_path": "exec",
  "args": ["python-fu-console", ["images = Gimp.get_images(); image = images[0]; layers = image.get_layers(); print(f'Found {len(images)} images with {len(layers)} layers')"]]
}
```
- **draw a diagonal line from [0,200] to [200,0]** 
```json
{
  "api_path": "exec",
  "args": ["python-fu-console", [
    "from gi.repository import Gimp",
    "images = Gimp.get_images()", 
    "image = images[0]", 
    "layers = image.get_layers()", 
    "layer = layers[0]", 
    "drawable = layer",
    "Gimp.context_set_brush_size(2.0)",
    "Gimp.pencil(drawable, [0, 200, 200, 0])",
    "Gimp.displays_flush()"
  ]]}
```

## Potential Use Cases
- Execute GIMP automation scripts
- Test GIMP Python API functions
- Batch process images
- Create custom GIMP tools and filters
- Debug GIMP Python scripts
