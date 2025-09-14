# GIMP PyGObject via MCP Documentation

## Overview
This document describes how to execute PyGObject commands in GIMP using the MCP (Model Context Protocol) interface. The GIMP MCP server provides multiple tools for interacting with GIMP 3.0, including image export capabilities that return MCP-compliant Image objects.

## Available MCP Tools

### 1. Image Export Tools

#### `get_image_bitmap()` 
Returns the current open image as an MCP-compliant Image object in PNG format.
- **Returns**: Image object that Claude can directly process
- **Format**: PNG
- **MCP Compliant**: Yes - returns proper ImageContent structure

#### `get_image_metadata()` 
Returns comprehensive metadata about the current open image without transferring bitmap data.
- **Returns**: Dictionary containing detailed image information
- **Performance**: Much faster than `get_image_bitmap()` - no image export required
- **Use case**: Perfect for analysis, decision making, and information gathering

**Returned metadata includes:**
- **Basic properties**: width, height, color mode, precision, resolution, unsaved changes status
- **Structure information**: number of layers/channels/paths with detailed properties
- **Layer details**: name, visibility, opacity, blend mode, dimensions, alpha channel
- **Channel information**: name, visibility, opacity, color
- **Path/vector data**: name, visibility, stroke count
- **File information**: path, URI, basename (if image was saved)

#### `get_gimp_info()` 
Returns comprehensive information about the GIMP installation and runtime environment.
- **Returns**: Dictionary containing detailed GIMP environment information
- **Performance**: Fast - gathers system information without heavy operations
- **Use case**: Environment discovery, troubleshooting, capability detection, optimal support

**Returned information includes:**
- **Version details**: GIMP version string, major/minor/micro versions
- **Directory paths**: user directory, system data, plugins, locale, sysconf directories
- **Session information**: number of open images, file paths, basic image properties
- **PDB capabilities**: Procedure Database availability, sample procedure tests
- **Current context**: foreground/background colors, brush settings
- **System capabilities**: Python modules, MCP features, API version
- **Platform information**: OS details, environment variables, Python version

### 2. General API Tool

#### `call_api(api_path, args=[], kwargs={})`

Execute GIMP 3.0 API methods through PyGObject console.

**GIMP MCP Protocol:**
- Use api_path="exec" to execute Python code in GIMP
- args[0] should be "pyGObject-console" for executing commands
- args[1] should be array of Python code strings to execute
- Commands execute in persistent context - imports and variables persist
- Always call Gimp.displays_flush() after drawing operations

For image operations, use `get_image_bitmap()` for full image export, `get_image_metadata()` for fast information gathering, or `get_gimp_info()` for environment discovery.
All tools return MCP-compliant data that AI assistants can process directly.

## Basic Method

### Function Call Structure
```json
{
  "api_path": "exec",
  "args": ["pyGObject-console", ["<python_code>"]]
}
```

### Parameters Explanation
- **api_path**: `"exec"` - Accesses GIMP's Procedure Database (PDB) to run a procedure
- **args**: Array with two elements:
  - `"pyGObject-console"` - The PyGObject console procedure name
  - `["<python_code>"]` - Array containing the Python code string to execute
         all commands are executed in the same process context, 
         so ["x=5","print(x)"] will work

## Tested Examples

### Simple Print Command (Console)
```json
{
  "api_path": "exec",
  "args": ["pyGObject-console", ["print('hello world')"]]
}
```

**Result**: Returns `"hello world"` when successful.

### Simple Expression Evaluation
```json
{
  "api_path": "exec",
  "args": ["pyGObject-eval", ["2 + 2"]]
}
```

**Result**: Returns `"4"` - the actual result of the Python expression.

## Important Notes

### String Escaping
- Use single quotes inside double quotes: `["print('hello world')"]`
- Or escape double quotes: `["print(\"hello world\")"]`
- Python code must be properly escaped as a JSON string

### PyGObject Procedure Types
- **`pyGObject-console`**: Executes Python code and returns output.
- **`pyGObject-eval`**: Evaluates Python expressions and returns the actual result value.

### Return Values
- **pyGObject-console**: Returns command output on success, error messages on failure
- **pyGObject-eval**: Returns the actual result of the Python expression
- Print statements from pyGObject-console are returned in MCP response
- Errors will return error messages or exception details

### Limitations
- Commands execute in GIMP's PyGObject environment
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

- **`image.get_active_layer()`**: Gets the active layer from an image
  ```python
  active_layer = image.get_active_layer()  # Returns Layer object
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

- **Draw a filled ellipse**: 
  ```python
  Gimp.Image.select_ellipse(image, Gimp.ChannelOps.REPLACE, 100, 100, 30, 20)
  Gimp.Drawable.edit_fill(drawable, Gimp.FillType.FOREGROUND)
  Gimp.Selection.none(image)
  Gimp.displays_flush()
  ```

- **Paint curve with paintbrush**:
  ```python
  Gimp.paintbrush_default(drawable, [50.0, 50.0, 150.0, 200.0, 250.0, 50.0, 350.0, 200.0])
  Gimp.displays_flush()
  ```

- **Draw bezier curve**:
  ```python
  path = Gimp.Path.new(image, 'my_bezier_path')
  image.insert_path(path, None, 0)
  stroke_id = path.bezier_stroke_new_moveto(100, 100)
  path.bezier_stroke_cubicto(stroke_id, 150, 50, 250, 150, 300, 100)
  Gimp.Drawable.edit_stroke_item(drawable, path)
  Gimp.Selection.none(image)
  Gimp.displays_flush()
  ```

- **Create new image**:
  ```python
  image = Gimp.Image.new(350, 800, Gimp.ImageBaseType.RGB)
  layer = Gimp.Layer.new(image, 'Background', 350, 800, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)
  image.insert_layer(layer, None, 0)
  drawable = layer
  white_color = Gegl.Color.new('white')
  Gimp.context_set_background(white_color)
  Gimp.Drawable.edit_fill(drawable, Gimp.FillType.BACKGROUND)
  Gimp.Display.new(image)
  ```

### Important Tips
- When filling layers with color, ensure layer has alpha channel using `Gimp.Layer.add_alpha()`
- Use `Gimp.Drawable.fill()` for reliable full-layer fills
- Specify colors precisely with rgb(R, G, B) or rgba(R, G, B, A) to avoid transparency issues
- After drawing operations, always call `Gimp.displays_flush()`
- After selection operations for drawing, unselect with `Gimp.Selection.none(image)`
- Use `from gi.repository import Gio` for file operations: `Gio.File.new_for_path(path)`

### Non-Working Methods (GIMP 3.0 Changes)
- **`Gimp.get_active_image()`**: ❌ Does not exist
- **`Gimp.list_images()`**: ❌ Does not exist  
- **`Gimp.get_active_layer()`**: ❌ Does not exist (use `image.get_active_layer()` instead)
- **`from gimpfu import *`**: ❌ gimpfu module not available in GIMP 3.0
- **`Gimp.file_new_for_path()`**: ❌ Use `Gio.File.new_for_path()` instead

### API Structure Insights
- GIMP 3.0 uses GObject Introspection (gi.repository.Gimp)
- PDB object type: `<class 'gi.repository.Gimp.PDB'>`
- Image objects: `<Gimp.Image object at 0x... (GimpImage at 0x...)>`
- Layer objects: `<Gimp.Layer object at 0x... (GimpLayer at 0x...)>`
- The API has significantly changed from GIMP 2.x to 3.0
- Colors are created with `Gegl.Color.new('color_name')`
- File objects use Gio library: `from gi.repository import Gio`

### Tested Working Examples

### Tested Working Example
- **Get layers** 
```json
{
  "api_path": "exec",
  "args": ["pyGObject-console", ["images = Gimp.get_images(); image = images[0]; layers = image.get_layers(); print(f'Found {len(images)} images with {len(layers)} layers')"]]
}
```
- **draw a diagonal line from [0,200] to [200,0]** 
```json
{
  "api_path": "exec",
  "args": ["pyGObject-console", [
    "from gi.repository import Gimp",
    "images = Gimp.get_images()", 
    "image = images[0]", 
    "layers = image.get_layers()", 
    "layer = layers[0]", 
    "drawable = layer",
    "Gimp.context_set_brush_size(2.0)",
    "Gimp.pencil(drawable, [0, 200, 200, 0])",
    "Gimp.displays_flush()"
  ]]
}
```

#### Initialize Working Context
```json
{
  "api_path": "exec",
  "args": ["pyGObject-console", [
    "images = Gimp.get_images()",
    "image1 = images[0]",
    "layers = image1.get_layers()",
    "layer1 = layers[0]",
    "drawable1 = layer1"
  ]]
}
```

## MCP Image Export Integration

### Direct Image Access
The GIMP MCP server now provides dedicated tools for image export that return MCP-compliant Image objects:

#### Using `get_image_bitmap()`
```python
# This returns an Image object that Claude can directly process
image = get_image_bitmap()

**Purpose:** Get the current image as a base64-encoded PNG bitmap with support for region extraction and scaling

**Parameters:**
- `max_width` (integer, optional): Maximum width for full image scaling (center inside)
- `max_height` (integer, optional): Maximum height for full image scaling (center inside)
- `origin_x` (integer, optional): X coordinate for region extraction (requires all region params)
- `origin_y` (integer, optional): Y coordinate for region extraction (requires all region params)
- `width` (integer, optional): Width of region to extract (requires all region params)
- `height` (integer, optional): Height of region to extract (requires all region params)
- `scaled_to_width` (integer, optional): Target width for scaling extracted region
- `scaled_to_height` (integer, optional): Target height for scaling extracted region

**Usage Modes:**
1. **Full Image:** No parameters - returns full image
2. **Full Image Scaled:** `max_width` + `max_height` - scales full image to fit within bounds
3. **Region Extract:** `origin_x` + `origin_y` + `width` + `height` - extracts specific region
4. **Region Extract + Scale:** Region params + `scaled_to_width` + `scaled_to_height` - extracts and scales

**Scaling Behavior:** All scaling uses "center inside" logic, preserving aspect ratio without cropping or distortion.

**Response Format:**
```json
{
  "status": "success",
  "results": {
    "image_data": "<base64-encoded-png-data>",
    "format": "png", 
    "width": 800,
    "height": 600,
    "original_width": 1920,
    "original_height": 1080,
    "encoding": "base64",
    "processing_applied": {
      "region_extracted": true,
      "scaled": true,
      "region_coords": {
        "x": 100,
        "y": 100,
        "w": 400,
        "h": 300
      }
    }
  }
}
```

#### Using `get_image_metadata()`
```python
# Fast metadata retrieval without bitmap transfer
metadata = get_image_metadata()

# Example response structure:
{
  "basic": {
    "width": 1920,
    "height": 1080,
    "base_type": "RGB",
    "precision": "8-bit integer",
    "resolution_x": 72.0,
    "resolution_y": 72.0,
    "is_dirty": true
  },
  "structure": {
    "num_layers": 3,
    "num_channels": 0,
    "num_paths": 1,
    "layers": [
      {
        "name": "Background",
        "visible": true,
        "opacity": 100.0,
        "width": 1920,
        "height": 1080,
        "has_alpha": false,
        "blend_mode": "NORMAL",
        "layer_type": "RGB_IMAGE"
      }
    ],
    "channels": [],
    "paths": [
      {
        "name": "Path 1",
        "visible": true,
        "num_strokes": 2
      }
    ]
  },
  "file": {
    "path": "/home/user/image.xcf",
    "basename": "image.xcf"
  }
}
```

#### Using `get_gimp_info()`
```python
# Get comprehensive GIMP environment information
gimp_info = get_gimp_info()

# Example response structure:
{
  "version": {
    "version_method": "3.1.4",
    "detected_version": "3.1.4",
    "available_version_attributes": ["version"],
    "gimp_module_type": "<class 'gi.module.Gimp'>"
  },
  "directories": {
    "user_directory": "/home/user/.config/GIMP/3.1",
    "system_data_directory": "/usr/share/gimp/3.1", 
    "plugin_directory": "/usr/lib/gimp/3.1/plug-ins",
    "available_directory_methods": ["directory", "data_directory", "plug_in_directory"]
  },
  "session": {
    "num_open_images": 2,
    "has_open_images": true,
    "open_image_files": [
      {
        "index": 0,
        "width": 1920,
        "height": 1080,
        "base_type": "RGB",
        "path": "/home/user/photo.jpg",
        "is_dirty": false
      }
    ]
  },
  "pdb": {
    "available": true,
    "sample_procedures": [
      {"name": "file-png-export", "available": true},
      {"name": "gimp-image-new", "available": true}
    ]
  },
  "context": {
    "foreground_color": "rgba(0,0,0,1)",
    "background_color": "rgba(255,255,255,1)",
    "brush_size": 20.0
  },
  "capabilities": {
    "has_python_console": true,
    "mcp_server_running": true,
    "supports_image_export": true,
    "supports_metadata_export": true,
    "supports_gimp_info": true,
    "api_version": "3.0+",
    "gimp_module_attributes": 127,
    "gimp_methods": ["Brush", "Channel", "Context", "Display", "Drawable"],
    "available_modules": [
      {"name": "gi.repository.Gimp", "available": true},
      {"name": "gi.repository.Gegl", "available": true}
    ]
  },
  "system": {
    "platform": "Linux-6.2.0-generic-x86_64",
    "python_version": "3.11.4",
    "environment_vars": {
      "HOME": "/home/user",
      "USER": "user"
    }
  }
}
```

#### When to Use Each Tool
- **`get_image_bitmap()`**: When you need to visually analyze or process the actual image
- **`get_image_metadata()`**: When you need image properties for decision making, validation, or information display
- **`get_gimp_info()`**: When you need environment information for troubleshooting, capability detection, or optimal support

## Plugin Architecture

### Connection Protocol
- **Host**: localhost (default)
- **Port**: 9877 (default)
- **Transport**: TCP socket
- **Format**: JSON messages
- **Auto-disconnect**: Configurable (default: true)

### Command Types
1. **`"get_image_bitmap"`**: Direct bitmap export
2. **`"disable_auto_disconnect"`**: Keep connection alive
3. **JSON with `"cmds"`**: Execute command array  
4. **JSON with `"params"`**: Structured API calls

### Error Handling
- Multiple export fallback methods
- Robust error reporting with tracebacks
- Graceful handling of missing procedures
- Property name flexibility for different GIMP versions

## Potential Use Cases
- Execute GIMP automation scripts
- Test GIMP Python API functions
- Batch process images
- Create custom GIMP tools and filters
- Debug GIMP Python scripts
