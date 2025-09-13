#!/usr/bin/env python3
# GIMP MCP Server Script
# Provides an MCP interface to control GIMP via a socket connection.

from mcp.server.fastmcp import FastMCP, Context, Image  # Adjust based on your MCP library
import socket
import json
import logging
import base64
import traceback

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GimpMCPServer")

class GimpConnection:
    def __init__(self, host='localhost', port=9877):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self):
        if self.sock:
            return
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to GIMP at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise ConnectionError("Could not connect to GIMP. Ensure the MCP Server plugin is running.")

    def send_command(self, command_type, params=None):
        if not self.sock:
            self.connect()
        command = {"type": command_type, "params": params or {"args": []}}
        try:
            self.sock.sendall(json.dumps(command).encode('utf-8'))
            
            # Receive response in chunks for large data
            response_data = b''
            while True:
                chunk = self.sock.recv(8192)
                if not chunk:
                    break
                response_data += chunk
                
                # Try to parse as complete JSON
                try:
                    json.loads(response_data.decode('utf-8'))
                    break  # Complete JSON received
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue  # Need more data
                    
            self.sock = None
            return json.loads(response_data.decode('utf-8'))
        except Exception as e:
            logger.error(f"Communication error: {e}")
            self.sock = None
            raise Exception(f"Error communicating with GIMP: {e}")

# Global connection
_gimp_connection = None

def get_gimp_connection():
    global _gimp_connection
    if _gimp_connection is None:
        _gimp_connection = GimpConnection()
        _gimp_connection.connect()
    return _gimp_connection

# MCP server
mcp = FastMCP("GimpMCP", description="GIMP integration through MCP")

@mcp.tool()
def get_image_bitmap(ctx: Context) -> Image:
    """Get the current open image in GIMP as an Image object.
    
    Returns the currently active image (or first open image) as a PNG Image
    that can be directly processed by Claude and other MCP clients.
    
    Returns:
    - Image object containing PNG data in MCP-compliant format
    - Raises exception if no images are open or export fails
    
    The returned Image object automatically handles base64 encoding and MIME types
    according to the Model Context Protocol specification.
    """
    try:

        print("Requesting current image bitmap from GIMP...")

        conn = get_gimp_connection()
        result = conn.send_command("get_image_bitmap")
        if result["status"] == "success":
            # Extract the base64 image data 
            image_info = result["results"]
            base64_data = image_info["image_data"]

            as_bytes = base64.b64decode(base64_data)

            # Return as MCP Image object (base64 data will be handled automatically)
            return Image(data=as_bytes, format="png")
        else:
            raise Exception(f"GIMP error: {result.get('error', 'Unknown error')}")
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"Failed to get image bitmap: {e}")


@mcp.tool()
def get_image_metadata(ctx: Context) -> dict:
    """Get metadata about the current open image in GIMP without the bitmap data.
    
    Returns detailed information about the currently active image including:
    - Image dimensions (width, height)
    - Color mode and base type
    - Number of layers and channels
    - File information if available
    - Layer structure and properties
    
    This is much faster than get_image_bitmap() since it doesn't export the actual image data.
    Perfect for when you only need to know image properties for decision making.
    
    Returns:
    - Dictionary containing comprehensive image metadata
    - Raises exception if no images are open
    """
    try:
        print("Requesting current image metadata from GIMP...")
        
        conn = get_gimp_connection()
        result = conn.send_command("get_image_metadata")
        if result["status"] == "success":
            return result["results"]
        else:
            raise Exception(f"GIMP error: {result.get('error', 'Unknown error')}")
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"Failed to get image metadata: {e}")


@mcp.tool()
def get_gimp_info(ctx: Context) -> dict:
    """Get comprehensive information about the GIMP installation and environment.
    
    Returns detailed information about GIMP that AI assistants need to understand
    the current environment, including:
    - GIMP version and build information
    - Installation paths and directories
    - Available plugins and procedures
    - System configuration
    - Runtime environment details
    
    This information helps AI assistants provide better support and troubleshooting
    by understanding the specific GIMP setup they're working with.
    
    Returns:
    - Dictionary containing comprehensive GIMP environment information
    - Raises exception if GIMP connection fails
    """
    try:
        print("Requesting GIMP environment information...")
        
        conn = get_gimp_connection()
        result = conn.send_command("get_gimp_info")
        if result["status"] == "success":
            return result["results"]
        else:
            raise Exception(f"GIMP error: {result.get('error', 'Unknown error')}")
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"Failed to get GIMP info: {e}")


@mcp.tool()
def call_api(ctx: Context, api_path: str, args: list = [], kwargs: dict = {}) -> str:
    """Call GIMP 3.0 API methods through PyGObject console.

    GIMP MCP Protocol:
    - Use api_path="exec" to execute Python code in GIMP
    - args[0] should be "pyGObject-console" for executing commands
    - args[1] should be array of Python code strings to execute
    - Commands execute in persistent context - imports and variables persist
    - Always call Gimp.displays_flush() after drawing operations

    For image operations, use get_image_bitmap()
    which return proper MCP Image objects that Claude can process directly.

    Optional Initialization Pattern:
    ["images = Gimp.get_images()", "image1 = images[0]",
     "layers = image1.get_layers()", "layer1 = layers[0]", "drawable1 = layer1"]

    Common Operations:
    - Draw line: ["Gimp.pencil(drawable1, [0, 0, 200, 200])", "Gimp.displays_flush()"]
    - Set color: ["from gi.repository import Gegl", "red_color = Gegl.Color.new('red')", 
                  "Gimp.context_set_foreground(red_color)"]
    - Draw ellipse: ["Gimp.Image.select_ellipse(image1, Gimp.ChannelOps.REPLACE, 100, 100, 30, 20)",
                     "Gimp.Drawable.edit_fill(drawable1, Gimp.FillType.FOREGROUND)",
                     "Gimp.Selection.none(image1)", "Gimp.displays_flush()"]
    - Paint curve: ["Gimp.paintbrush_default(drawable1, [50.0, 50.0, 150.0, 200.0, 250.0, 50.0, 350.0, 200.0])", 
                    "Gimp.displays_flush()"]
    - Draw bezier curve: ["path = Gimp.Path.new(image1, 'my_bezier_path')", 
                          "image1.insert_path(path, None, 0)",
                          "stroke_id = path.bezier_stroke_new_moveto(100, 100)",
                          "path.bezier_stroke_cubicto(stroke_id, 150, 50, 250, 150, 300, 100)",
                          "Gimp.Drawable.edit_stroke_item(drawable1, path)",
                          "Gimp.Selection.none(image1)", "Gimp.displays_flush()"]
    - Get open filenames: ["print([x.get_file().get_path() for x in Gimp.get_images()])"]
    - Copy layer between images: ["image1 = Gimp.get_images()[0]", "image2 = Gimp.get_images()[1]",
                                  "width = image1.get_width()", "height = image1.get_height()",
                                  "image1.select_rectangle(Gimp.ChannelOps.REPLACE, 0, 0, width, height)",
                                  "image1_layers = image1.get_selected_layers()", "drawable = image1_layers[0]",
                                  "Gimp.edit_copy([drawable])", "image2_layers = image2.get_layers()",
                                  "target_drawable = image2_layers[0]", "floating_sel = Gimp.edit_paste(target_drawable, True)[0]",
                                  "Gimp.floating_sel_anchor(floating_sel)", "Gimp.displays_flush()"]
    - New image: ["image1 = Gimp.Image.new(350, 800, Gimp.ImageBaseType.RGB)",
                  "layer1 = Gimp.Layer.new(image1, 'Background', 350, 800, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)",
                  "image1.insert_layer(layer1, None, 0)", "drawable1 = layer1",
                  "white_color = Gegl.Color.new('white')", "Gimp.context_set_background(white_color)",
                  "Gimp.Drawable.edit_fill(drawable1, Gimp.FillType.BACKGROUND)", "Gimp.Display.new(image1)"]
    
    Important Tips:
    - When filling layers with color, ensure layer has alpha channel using Gimp.Layer.add_alpha()
    - Use Gimp.Drawable.fill() for reliable full-layer fills
    - Specify colors precisely with rgb(R, G, B) or rgba(R, G, B, A) to avoid transparency issues
    - After drawing operations, always call Gimp.displays_flush()
    - After selection operations for drawing, unselect with Gimp.Selection.none(image1)

    GIMP 3.0 API Changes:
    - Use Gimp.get_images() instead of deprecated Gimp.list_images()
    - Use image.get_layers() instead of Gimp.get_active_layer()
    - gimpfu module not available in GIMP 3.0
    - Colors created with Gegl.Color.new('color_name')
    - Full API documentation: https://developer.gimp.org/api/3.0/libgimp/

    Parameters:
    - api_path: Use "exec" for Python execution
    - args: ["pyGObject-console", ["python_code_array"]] or ["pyGObject-eval", ["expression"]]
    - kwargs: Dictionary of keyword arguments (rarely used)

    Returns:
    - JSON string of the result or error message
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("call_api", {"api_path": api_path, "args": args, "kwargs": kwargs})
        if result["status"] == "success":
            return json.dumps(result["results"])
        else:
            return f"Error: {json.dumps(result["error"])}"
    except Exception as e:
        return f"Error: {e}"

def main():
    mcp.run()

if __name__ == "__main__":
    main()