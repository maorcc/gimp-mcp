# GIMP MCP interface

## Overview
This document describes how to install and use the GIMP MCP interface, which gives Claude the option to control GIMP

## Install

### 1. Install the gimp plugin
Create a gimp plugin directory under Gimp's `plug-ins` directory and copy the `gimp-mcp-plugin.py` file to it.
```
mkdir ~/.config/GIMP/3.0/plug-ins/gimp-mcp-plugin
cp gimp-mcp-plugin.py ~/.config/GIMP/3.0/plug-ins/gimp-mcp-plugin
```

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
