# GIMP MCP

## Overview
This document describes how to install and use the GIMP MCP, which gives Claude Desktop and other MCP clients the option to control GIMP.

## Prerequesits
- GIMP 3.0 and above

## Installation

### 1. Install the gimp plugin for mcp server

To install the plugin, copy the `gimp-mcp-plugin.py` to your GIMP `plug-ins` directory.

For detailed instructions on locating your GIMP plugins folder across different operating systems, please refer to this guide:

[**GIMP Plugin Installation Guide (Wikibooks)**](https://en.wikibooks.org/wiki/GIMP/Installing_Plugins)

You can also create a symbolic link to the plugin file in the GIMP plug-ins directory. This is useful if you want to keep the plugin file in this project directory for easy updates.
For example:
```bash
ln -s gimp-mcp-plugin.py ~/snap/gimp/current/.config/GIMP/3.0/plug-ins/gimp-mcp-plugin
```

Restart GIMP for the plugin to appear.


### 2. Install the mcp server
Add these lines to your Claude Desktop configuration file. (On Linux/macOS: ~/.config/Claude/claude_desktop_config.json )
```json
{
  "mcpServers": {
    "gimp": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "your/path/to/gimp-mcp-server",
        "server.py" ]
    }
  }
}
```
