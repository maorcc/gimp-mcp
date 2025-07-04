# GIMP MCP interface

## Overview
This document describes how to install and use the GIMP MCP interface, which gives Claude the option to control GIMP

## add these lines to your CLAUDE configuration ~/.config/Claude/claude_desktop_config.json
"gimp": {
        "command": "uv",
        "args": [ "run",
                  "--directory",
                  "/home/tomer/temp/sgt/src",
                  "gimp_mcp/server.py" ]
    },

##jput the GIMP plugin under ~/.config/GIMP/3.0/plug-ins/gimp-mcp-plugin
- mkdir ~/.config/GIMP/3.0/plug-ins/gimp-mcp-plugin


