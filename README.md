# GIMP MCP

## Overview
This document describes how to install and use the GIMP MCP, which gives Claude Desktop and other MCP clients the option to control GIMP.

## Prerequesits
- GIMP 3.0 and above

## Installation

### 1. Install the gimp plugin for mcp server

To install the plugin, copy the `gimp-mcp-plugin.py` to your GIMP `plug-ins` directory.

For detailed instructions on locating your GIMP plugins folder across different operating systems, please refer to this guide:

[**GIMP Plugin Installation ``Guide (Wikibooks)**](https://en.wikibooks.org/wiki/GIMP/Installing_Plugins)

Make sure the plugin file has "execute" permission.

For example, if your gimp is installed with snap, you can use the following commands to copy the plugin to the correct directory:
```bash
mkdir ~/snap/gimp/current/.config/GIMP/3.0/plug-ins/gimp-mcp-plugin
cp gimp-mcp-plugin.py ~/snap/gimp/current/.config/GIMP/3.0/plug-ins/gimp-mcp-plugin
chmod +x ~/snap/gimp/current/.config/GIMP/3.0/plug-ins/gimp-mcp-plugin/gimp-mcp-plugin.py
`````

Restart GIMP.

Open any image in GIMP, and then you should see a new menu item under `Tools > Start MCP Server`. Click it to start the MCP server.


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

## Usage

1. Open any image in GIMP, Under Tools manu click `Start MCP Server`.
1. Start Claude Desktop
2. Tell Claude to read the file GIMP_MCP_PROTOCOL.md
3. Tell claude to do something with GIMP, like "Draw a line".
