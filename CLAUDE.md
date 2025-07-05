# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a GIMP MCP (Model Context Protocol) integration that enables external control of GIMP 3.0 through Claude Desktop and other MCP clients. The system consists of two main components:

1. **GIMP Plugin** (`gimp-mcp-plugin.py`): A GIMP 3.0 plugin that starts a socket server inside GIMP
2. **MCP Server** (`gimp-mcp-server.py`): An MCP server that connects to the GIMP plugin and exposes GIMP functionality

## Architecture

The system uses a client-server architecture:
- GIMP Plugin creates a socket server (localhost:9877) that accepts Python-Fu commands
- MCP Server connects to this socket and exposes a `call_api` tool for MCP clients
- Commands are executed in GIMP's Python-Fu environment with access to the full GIMP 3.0 API

## Installation & Setup

### GIMP Plugin Installation
```bash
# For snap installations
mkdir ~/snap/gimp/current/.config/GIMP/3.0/plug-ins/gimp-mcp-plugin
cp gimp-mcp-plugin.py ~/snap/gimp/current/.config/GIMP/3.0/plug-ins/gimp-mcp-plugin
chmod +x ~/snap/gimp/current/.config/GIMP/3.0/plug-ins/gimp-mcp-plugin/gimp-mcp-plugin.py
```

### MCP Server Configuration
Add to Claude Desktop config (`~/.config/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "gimp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/gimp-mcp", "gimp-mcp-server.py"]
    }
  }
}
```

## Development Commands

There are no build, test, or lint commands as this is a simple Python script project without dependencies or test framework.

## API Usage

### Core MCP Tool
The main interface is the `call_api` tool with parameters:
- `api_path`: "exec" for Python-Fu execution
- `args`: Array containing procedure name and code/expressions

### Common Command Patterns

**Execute Python Commands:**
```json
{
  "api_path": "exec",
  "args": ["python-fu-console", ["print('hello world')"]]
}
```

**Evaluate Expressions:**
```json
{
  "api_path": "exec", 
  "args": ["python-fu-eval", ["2 + 2"]]
}
```

### GIMP 3.0 API Key Points

- Use `Gimp.get_images()` instead of deprecated `Gimp.list_images()`
- Access layers via `image.get_layers()` instead of `Gimp.get_active_layer()`
- Import `from gi.repository import Gimp, Gegl` for full API access
- Colors are created with `Gegl.Color.new('color_name')`
- Always call `Gimp.displays_flush()` after drawing operations

### Essential Initialization Pattern
Most GIMP operations should start with this initialization:
```python
from gi.repository import Gimp
images = Gimp.get_images()
image = images[0]  # or image1 = images[0]
layers = image.get_layers()
layer = layers[0]  # or layer1 = layers[0]
drawable = layer   # or drawable1 = layer
```

### Common Operations

**Drawing a line:**
```python
Gimp.pencil(drawable, [x1, y1, x2, y2])
Gimp.displays_flush()
```

**Setting colors:**
```python
from gi.repository import Gegl
red_color = Gegl.Color.new("red")
Gimp.context_set_foreground(red_color)
```

**Creating shapes:**
```python
Gimp.Image.select_ellipse(image, Gimp.ChannelOps.REPLACE, x, y, width, height)
Gimp.Drawable.edit_fill(drawable, Gimp.FillType.FOREGROUND)
Gimp.Selection.none(image)
Gimp.displays_flush()
```

## Important Notes

- Commands execute in a persistent Python context - imports and variables persist between calls
- GIMP 3.0 API differs significantly from 2.x - consult https://developer.gimp.org/api/3.0/libgimp/
- Always verify API calls work before building complex operations
- The `gimpfu` module is not available in GIMP 3.0
- Use proper error handling as socket connections can fail

## File Structure

- `gimp-mcp-plugin.py`: GIMP plugin with socket server and command execution
- `gimp-mcp-server.py`: MCP server that bridges socket to MCP protocol  
- `GIMP_MCP_PROTOCOL.md`: Detailed API documentation and examples
- `RECIPES.md`: Quick reference for common GIMP operations
- `README.md`: Installation and setup instructions