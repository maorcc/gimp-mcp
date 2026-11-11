# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a GIMP MCP (Model Context Protocol) integration that enables external control of GIMP 3.2 through Claude Desktop and other MCP clients. The system consists of two main components:

1. **GIMP Plugin** (`gimp-mcp-plugin.py`): A GIMP 3.2 plugin that starts a socket server inside GIMP
2. **MCP Server** (`gimp-mcp-server.py`): An MCP server that connects to the GIMP plugin and exposes GIMP functionality

## Architecture

The system uses a client-server architecture:
- GIMP Plugin creates a socket server (localhost:9877) that accepts Python-Fu commands
- MCP Server connects to this socket and exposes a `call_api` tool for MCP clients
- Commands are executed in GIMP's Python-Fu environment with access to the full GIMP 3.2 API

## Installation & Setup

The server and plugin ship together on PyPI as `gimp-mcp-plugin`; `uvx gimp-mcp-plugin` runs
the server, and the bundled `gimp-mcp-plugin.py` is installed with the `install-plugin` subcommand.

### GIMP Plugin Installation
```bash
uvx gimp-mcp-plugin@latest install-plugin            # from PyPI
uv run gimp_mcp_server.py install-plugin             # from a checkout (installs this repo's plugin)
```
It installs into `<GIMP config>/plug-ins/gimp-mcp-plugin/` under the newest GIMP 3.x config
dir it finds (Linux standard/Snap/Flatpak, macOS, Windows; `GIMP3_DIRECTORY` overrides).
`--dry-run` shows the target, `--gimp-dir DIR` sets it. GIMP's config dir is named after its
**major.minor** version and moves on each minor upgrade (e.g. 3.0 → 3.2), so re-run it after
upgrading GIMP; the active path is shown in **Edit > Preferences > Folders > Plug-ins**.

Then start it from **Tools > MCP > Start MCP Server** in GIMP, or enable autostart (and set the
port) in **Tools > MCP > MCP Server Settings...**. Settings are stored in `gimp-mcp.json` in the
GIMP config dir; a non-default port must also be set as `GIMP_MCP_PORT` for the MCP server.

The plugin and server versions must match exactly (`check_server` / `get_gimp_info` report a
mismatch with the fix command). A release bumps `pyproject.toml` `version`, `SERVER_VERSION` in
`gimp_mcp_server.py` and `PLUGIN_VERSION` in `gimp-mcp-plugin.py` together
(`tests/test_version_handshake.py` checks this).

### MCP Server Configuration
Add to Claude Desktop config (`~/.config/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "gimp": {
      "command": "uvx",
      "args": ["gimp-mcp-plugin@latest"]
    }
  }
}
```
For development, run from the checkout instead:
`"command": "uv", "args": ["run", "--directory", "/path/to/gimp-mcp", "gimp_mcp_server.py"]`.
Claude Code started in the repo uses `.mcp.json`, which does the same.

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
  "args": ["exec", ["print('hello world')"]]
}
```

### GIMP 3.2 API Key Points

- Use `Gimp.get_images()` instead of deprecated `Gimp.list_images()`
- Access layers via `image.get_layers()` instead of `Gimp.get_active_layer()`
- Colors are created with `Gegl.Color.new('color_name')`
  or with color RGB values, e.g. `Gegl.Color.new("rgb(1.0, 0.647, 0.0)")`. Notice, each RGB value is in the range 0-1
- Always call `Gimp.displays_flush()` after drawing operations

### Essential Initialization Pattern
Most GIMP operations should start with this initialization:
```python
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
- GIMP 3.2 API differs significantly from 2.x - consult https://developer.gimp.org/api/3.0/libgimp/
- Always verify API calls work before building complex operations
- The `gimpfu` module is not available in GIMP 3.2
- Use proper error handling as socket connections can fail

## File Structure

- `gimp-mcp-plugin.py`: GIMP plugin with socket server and command execution
- `gimp_mcp_server.py`: MCP server that bridges socket to MCP protocol
- `docs/best_practices.md`: Best practices, common recipes, self-critique checklist, and guidelines exposed via MCP prompts
- `docs/iterative_workflow.md`: Professional iterative workflow guidance for building complex images with layer management and validation
- `GIMP_MCP_PROTOCOL.md`: Detailed API documentation and examples
- `README.md`: Installation and setup instructions
