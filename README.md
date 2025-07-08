# GIMP MCP

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Works with Claude Desktop](https://img.shields.io/badge/Works%20with-Claude%20Desktop-7B2CBF.svg)](https://claude.ai/desktop)

## Overview

This project enables non-technical users to edit images with GIMP through simple conversational commands, bridging the gap between GIMP's powerful capabilities and natural language interaction. It also allows professionals to execute complex multi-step workflows faster than traditional point-and-click methods.

Users can describe what they want to achieve - from basic photo adjustments to sophisticated artistic modifications. For example, "brighten the background and add a vintage filter" or "remove the red-eye and sharpen the subject" - and the system translates these requests into precise GIMP operations.

The project is functional and exposes all GIMP features via MCP. The main development focus is creating comprehensive AI-readable documentation to help AI agents use GIMP efficiently.


## Prerequisites
* **GIMP 3.0 and above:** This project is developed and tested with GIMP 3.0.
* **MCP-compatible AI client:** Claude Desktop, Gemini CLI, PydanticAI, or other MCP clients.
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


### 2. Configure MCP Client
Configure your MCP client:
#### Claude Desktop
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

#### Gemini CLI
Configure your Gemini CLI MCP server in `~/.config/gemini/.gemini_config.json`:
```json
{
  "mcpServers": {
    "gimp": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "your/path/to/gimp-mcp-server",
        "server.py"
      ]
    }
  }
}
```

#### PydanticAI
For PydanticAI agents, use the MCPServerStdio class:
```python
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio

server = MCPServerStdio(
    'uv',
    args=[
        'run',
        '--directory',
        'your/path/to/gimp-mcp-server',
        'server.py'
    ]
)

agent = Agent('openai:gpt-4o', mcp_servers=[server])
```

#### Other MCP Clients
For other MCP clients that support stdio transport, use the command:
```bash
uv run --directory your/path/to/gimp-mcp-server server.py
```

## Usage

**Note:** Ensure your MCP client is configured with the GIMP MCP server before starting.

1. Open any image in GIMP, Under Tools menu click `Start MCP Server`.
2. Start your MCP client (Claude Desktop, Gemini CLI, etc.)
3. Tell the AI to interact with GIMP, like "Draw a face and a sheep with Gimp".

<img src="gimp-screenshot1.png" alt="GIMP MCP Example" width="400">

*Example output from the prompt "draw me a face and a sheep" using GIMP MCP*

## Suggestions for Improvement

- **Add Recipes**: Create a collection of common GIMP tasks and workflows as MCP recipes.
- **Undo capabilities**: Implement a way to undo actions in GIMP through the MCP interface.
- **Visual feedback**: Provide visual feedback to the MCP client for actions performed in GIMP, such as showing the modified image or layer.
- **API discovery**: Create dynamic tool discovery that exposes available GIMP functions as separate MCP tools instead of requiring manual PyGObject code
- **Error context**: Enhance error messages with specific GIMP API context, line numbers, and suggested fixes for common issues
- **GIMP plugin robustness**: Make sure resources are released appropriately, and prevent misconduct from mcp client on the PyGObject API.

## Contributing

Contributions are welcome! Whether it's bug fixes, new features, or documentation improvements, feel free to submit a Pull Request or open an issue.
