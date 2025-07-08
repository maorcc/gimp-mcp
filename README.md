# GIMP MCP

## Overview

This project enables non-technical users to edit images with GIMP through simple conversational commands, bridging the gap between GIMP's powerful capabilities and natural language interaction. It also allows professionals to execute complex multi-step workflows faster than traditional point-and-click methods.

Users can describe what they want to achieve - from basic photo adjustments to sophisticated artistic modifications. For example, "brighten the background and add a vintage filter" or "remove the red-eye and sharpen the subject" - and the system translates these requests into precise GIMP operations.

The project is functional and exposes all GIMP features via MCP. The main development focus is creating comprehensive AI-readable documentation to help AI agents use GIMP efficiently.


## Prerequisites
* **GIMP 3.0 and above:** This project is developed and tested with GIMP 3.0.
* **Claude Desktop or any other AI tool that supports MCP** .
* **uv:** A modern Python package installer and resolver.

## Installation

### 1. Install the GIMP plugin for mcp server

To install the plugin, copy the `gimp-mcp-plugin.py` to your GIMP `plug-ins` directory.

For detailed instructions on locating your GIMP plugins folder across different operating systems, please refer to this guide:

[**GIMP Plugin Installation Guide (Wikibooks)**](https://en.wikibooks.org/wiki/GIMP/Installing_Plugins)

Make sure the plugin file has "execute" permission.

For example, if your GIMP is installed with snap, you can use the following commands to copy the plugin to the correct directory:
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

1. Open any image in GIMP, Under Tools menu click `Start MCP Server`.
1. Start Claude Desktop
1. Tell Claude to do something with GIMP, like "Draw a face and a sheep with Gimp".

<img src="gimp-screenshot1.png" alt="GIMP MCP Example" width="400">

*Example output from the prompt "draw me a face and a sheep" using GIMP MCP*

## Contributing

Contributions are welcome! Whether it's bug fixes, new features, or documentation improvements, feel free to submit a Pull Request or open an issue.
