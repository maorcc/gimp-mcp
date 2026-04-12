#!/usr/bin/env python3
# GIMP MCP Server Script — improved fork
# Adds: new_canvas, check_server, restart_server, no bitmap size restrictions

from mcp.server.fastmcp import FastMCP, Context, Image
import socket
import json
import logging
import base64
import traceback
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GimpMCPServer")

GIMP_HOST = 'localhost'
GIMP_PORT = 9877

class GimpConnection:
    def __init__(self, host=GIMP_HOST, port=GIMP_PORT):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self):
        if self.sock:
            return
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to GIMP at {self.host}:{self.port}")
        except Exception as e:
            self.sock = None
            logger.error(f"Failed to connect: {e}")
            raise ConnectionError(f"Could not connect to GIMP at {self.host}:{self.port}. Ensure the MCP Server plugin is running (Tools > Start MCP Server).")

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send_command(self, command_type, params=None):
        if not self.sock:
            self.connect()
        command = {"type": command_type, "params": params or {"args": []}}
        try:
            self.sock.sendall(json.dumps(command).encode('utf-8'))
            response_data = b''
            while True:
                chunk = self.sock.recv(8192)
                if not chunk:
                    break
                response_data += chunk
                try:
                    json.loads(response_data.decode('utf-8'))
                    break
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
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

def reset_gimp_connection():
    global _gimp_connection
    if _gimp_connection:
        _gimp_connection.disconnect()
    _gimp_connection = None

# MCP server
mcp = FastMCP("GimpMCP", description="GIMP integration through MCP — with new_canvas, check_server, restart_server")

@mcp.tool()
def check_server(ctx: Context) -> dict:
    """Check whether the GIMP MCP plugin socket is reachable and responding.

    Returns a status dict:
    - connected: bool
    - host / port: where it tried
    - gimp_version: if connected successfully
    - error: description if not connected

    Use this before any other operation to verify the GIMP plugin is running.
    If not connected, open GIMP and run Tools > Start MCP Server.
    """
    try:
        test_conn = GimpConnection(GIMP_HOST, GIMP_PORT)
        test_conn.connect()
        result = test_conn.send_command("get_gimp_info")
        version = result.get("results", {}).get("version", {}).get("version_method", "unknown")
        return {"connected": True, "host": GIMP_HOST, "port": GIMP_PORT, "gimp_version": version}
    except Exception as e:
        return {"connected": False, "host": GIMP_HOST, "port": GIMP_PORT, "error": str(e)}


@mcp.tool()
def restart_server(ctx: Context) -> dict:
    """Drop and re-establish the connection to the GIMP MCP plugin.

    Use this when:
    - GIMP was restarted after Claude Code was already running
    - The socket connection dropped mid-session
    - check_server() shows not connected but GIMP is open

    Returns the new connection status (same format as check_server).
    """
    reset_gimp_connection()
    time.sleep(0.5)
    return check_server(ctx)


@mcp.tool()
def new_canvas(
    ctx: Context,
    width: int,
    height: int,
    name: str = "Untitled",
    color_mode: str = "RGB",
    fill: str = "white",
    resolution: int = 72
) -> dict:
    """Create a new blank canvas in GIMP and open it in a display window.

    Parameters:
    - width: Canvas width in pixels
    - height: Canvas height in pixels
    - name: Layer/image name (default: "Untitled")
    - color_mode: "RGB" (default), "RGBA", "GRAY", "GRAYA"
    - fill: Fill color for the background layer. Any CSS color name or
            hex string: "white" (default), "black", "transparent",
            "#FF5733", "rgb(100,200,50)", etc.
    - resolution: DPI resolution (default: 72)

    Returns:
    - image_id: internal GIMP image ID
    - width / height: confirmed dimensions
    - color_mode: confirmed mode
    - display_opened: whether a GIMP window was opened

    Examples:
    - new_canvas(1024, 1024) — white 1024x1024 RGB canvas
    - new_canvas(1920, 1080, name="Background", fill="black")
    - new_canvas(512, 512, color_mode="RGBA", fill="transparent")
    """
    try:
        mode_map = {
            "RGB": "Gimp.ImageBaseType.RGB",
            "RGBA": "Gimp.ImageBaseType.RGB",
            "GRAY": "Gimp.ImageBaseType.GRAY",
            "GRAYA": "Gimp.ImageBaseType.GRAY",
        }
        layer_type_map = {
            "RGB":   "Gimp.ImageType.RGB_IMAGE",
            "RGBA":  "Gimp.ImageType.RGBA_IMAGE",
            "GRAY":  "Gimp.ImageType.GRAY_IMAGE",
            "GRAYA": "Gimp.ImageType.GRAYA_IMAGE",
        }
        base_type = mode_map.get(color_mode.upper(), "Gimp.ImageBaseType.RGB")
        layer_type = layer_type_map.get(color_mode.upper(), "Gimp.ImageType.RGB_IMAGE")

        fill_cmd = (
            "Gimp.context_set_background(Gegl.Color.new('white'))\n"
            "fill_type = Gimp.FillType.TRANSPARENT"
            if fill.lower() == "transparent"
            else f"bg_color = Gegl.Color.new('{fill}')\nGimp.context_set_background(bg_color)"
        )
        fill_type = "Gimp.FillType.TRANSPARENT" if fill.lower() == "transparent" else "Gimp.FillType.BACKGROUND"

        cmds = [
            "from gi.repository import Gimp, Gegl",
            f"_nc_image = Gimp.Image.new({width}, {height}, {base_type})",
            f"_nc_image.set_resolution({resolution}, {resolution})",
            f"_nc_layer = Gimp.Layer.new(_nc_image, '{name}', {width}, {height}, {layer_type}, 100, Gimp.LayerMode.NORMAL)",
            "_nc_image.insert_layer(_nc_layer, None, 0)",
            fill_cmd,
            f"Gimp.Drawable.edit_fill(_nc_layer, {fill_type})",
            "_nc_display = Gimp.Display.new(_nc_image)",
            "Gimp.displays_flush()",
            f"print(_nc_image.get_id())",
        ]
        conn = get_gimp_connection()
        result = conn.send_command("call_api", {
            "api_path": "exec",
            "args": ["pyGObject-console", cmds],
            "kwargs": {}
        })
        return {
            "status": "success",
            "width": width,
            "height": height,
            "color_mode": color_mode,
            "fill": fill,
            "resolution": resolution,
            "display_opened": True,
            "raw": result
        }
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"Failed to create new canvas: {e}")


@mcp.tool()
def get_image_bitmap(ctx: Context, max_width: int | None = None, max_height: int | None = None, region: dict | None = None) -> Image:
    """Get the current open image in GIMP as an Image object with optional scaling and region selection.

    No size restrictions — pass any max_width/max_height you need.
    For large images, omit max_width/max_height to get the full resolution.

    Supports two main use cases:
    1. Full image with optional scaling (pass max_width/max_height)
    2. Region extraction with optional scaling (pass region dict)

    Parameters:
    - max_width, max_height: Target dimensions for scaling (aspect-ratio preserved).
      Omit for full resolution.
    - region: Dictionary with keys:
        - origin_x, origin_y: Top-left corner of region to extract
        - width, height: Dimensions of region to extract
        - max_width, max_height: Optional scaling for the extracted region

    Examples:
    - Full image at full res: get_image_bitmap()
    - Full image scaled: get_image_bitmap(max_width=2048, max_height=2048)
    - Region: get_image_bitmap(region={"origin_x": 0, "origin_y": 0, "width": 512, "height": 512})

    Returns:
    - Image object containing PNG data in MCP-compliant format
    - Includes width, height, and base64-encoded image data

    The returned Image object automatically handles base64 encoding and MIME types
    according to the Model Context Protocol specification.

    Raises:
    - RuntimeError if no image is open, region is invalid, or export fails
    """
    try:

        print("Requesting current image bitmap from GIMP...")

        conn = get_gimp_connection()
        
        # Build parameters for the bitmap request
        params = {}
        if max_width is not None:
            params["max_width"] = max_width
        if max_height is not None:
            params["max_height"] = max_height
        if region is not None:
            params["region"] = region
            
        result = conn.send_command("get_image_bitmap", params)
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
def get_state_snapshot(
    ctx: Context,
    image_index: int = 0,
    max_size: int = 512,
    region: dict | None = None,
    label: str = ""
) -> Image:
    """Return a live visual snapshot of the current image state — no file save needed.

    AI agents call this to get immediate visual feedback after any edit operation,
    letting them verify results and decide next steps without saving to disk.

    Parameters:
    - image_index: Which open image to snapshot (default: 0 = most recent)
    - max_size: Maximum width/height of the returned preview in pixels (default: 512)
    - region: Optional dict {x, y, width, height} to zoom into a specific area
              e.g. {"x": 200, "y": 300, "width": 100, "height": 80} for mouth area
    - label: Optional annotation label (logged but not drawn — for agent bookkeeping)

    Returns:
    - PNG image of the current GIMP canvas state (with alpha if present)

    Typical agent workflow:
        1. open_image / new_canvas
        2. <edit operations>
        3. get_state_snapshot()          ← see result, decide next step
        4. <more edits>
        5. get_state_snapshot(region={"x":200,"y":300,"width":100,"height":80})
        6. export_image when satisfied
    """
    try:
        if label:
            print(f"[snapshot] {label}")
        conn = get_gimp_connection()
        params: dict = {"image_index": image_index}
        if max_size:
            params["max_width"]  = max_size
            params["max_height"] = max_size
        if region:
            params["region"] = {
                "origin_x": int(region.get("x", 0)),
                "origin_y": int(region.get("y", 0)),
                "width":    int(region.get("width",  max_size)),
                "height":   int(region.get("height", max_size)),
            }
        result = conn.send_command("get_image_bitmap", params)
        if result["status"] == "success":
            img_info  = result["results"]
            b64_data  = img_info["image_data"]
            raw_bytes = base64.b64decode(b64_data)
            return Image(data=raw_bytes, format="png")
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"get_state_snapshot failed: {e}")


@mcp.tool()
def get_context_state(ctx: Context) -> dict:
    """Get the current GIMP context state (colors, brush, settings).

    IMPORTANT: Context state can be changed by the user in GIMP UI at any time.
    Check context state before operations that depend on specific settings.

    Returns information about:
    - Foreground and background colors (RGB/RGBA values)
    - Current brush and its properties
    - Opacity setting (0-100%)
    - Paint/blend mode
    - Feather state and radius
    - Antialiasing state

    Use cases:
    - Verify colors before drawing operations
    - Check if feathering is enabled (avoid unwanted blurry edges)
    - Ensure correct opacity and blend mode
    - Detect if user changed settings in GIMP UI

    Returns:
    - Dictionary containing current context state
    - Raises exception if unable to get context state
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("get_context_state", params={})
        if result["status"] == "success":
            return result["results"]
        else:
            raise Exception(f"GIMP error: {result.get('error', 'Unknown error')}")
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"Failed to get context state: {e}")


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

    GUIDANCE PROMPTS:
    - For common operations and best practices, invoke the 'gimp_best_practices' prompt
    - For complex multi-element drawings with layers, invoke the 'gimp_iterative_workflow' prompt

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

@mcp.prompt(
    description="GIMP MCP best practices for common operations - filling shapes, bezier paths, and variable persistence"
)
def gimp_best_practices() -> str:
    """Returns guidance on best practices for GIMP operations via MCP.

    This prompt provides critical DO/DON'T patterns that help AI assistants
    and users avoid common mistakes when working with GIMP through MCP.
    """
    docs_path = Path(__file__).parent / "docs" / "best_practices.md"
    return docs_path.read_text()

@mcp.prompt(
    description="Iterative workflow guidance for building complex images with proper validation and layer management"
)
def gimp_iterative_workflow() -> str:
    """Returns comprehensive guidance on iterative workflow with GIMP MCP.

    This prompt teaches AI assistants how to:
    - Plan layer structures before drawing
    - Work incrementally with continuous validation
    - Self-critique using get_image_bitmap()
    - Fix problems properly instead of painting over them
    - Leverage GIMP's professional features for clean, organized work
    """
    docs_path = Path(__file__).parent / "docs" / "iterative_workflow.md"
    return docs_path.read_text()

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 1 — File Operations
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def open_image(ctx: Context, file_path: str) -> dict:
    """Open an image file in GIMP and create a display window.

    Parameters:
    - file_path: Absolute path to the image file to open (PNG, JPEG, TIFF, etc.)

    Returns:
    - image_id: internal GIMP image ID
    - width / height: image dimensions in pixels
    - color_mode: RGB / Grayscale / Indexed
    - num_layers: number of layers in the image
    - display_opened: whether a GIMP display window was created
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("open_image", {"file_path": file_path})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"open_image failed: {e}")


@mcp.tool()
def save_xcf(ctx: Context, file_path: str, image_index: int = 0) -> dict:
    """Save the current image as a GIMP XCF file (preserves all layers and metadata).

    Parameters:
    - file_path: Absolute path for the output .xcf file
    - image_index: Index of the image to save (default 0 = first open image)

    Returns:
    - status: "success" or "error"
    - file_path: confirmed output path
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("save_xcf", {"file_path": file_path, "image_index": image_index})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"save_xcf failed: {e}")


@mcp.tool()
def export_image(
    ctx: Context,
    file_path: str,
    format: str = "png",
    quality: int = 90,
    flatten: bool = True,
    image_index: int = 0
) -> dict:
    """Export the current image to a raster file (PNG, JPEG, WEBP, TIFF).

    Parameters:
    - file_path: Absolute path for the output file
    - format: Output format — "png" (default), "jpeg", "webp", "tiff"
    - quality: JPEG/WEBP quality 1-100 (default 90; ignored for PNG/TIFF)
    - flatten: Flatten all layers before export (default True)
    - image_index: Index of the image to export (default 0)

    Returns:
    - status, file_path, format, file_size_bytes
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("export_image", {
            "file_path": file_path,
            "format": format,
            "quality": quality,
            "flatten": flatten,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"export_image failed: {e}")


@mcp.tool()
def batch_export(
    ctx: Context,
    output_dir: str,
    format: str = "png",
    quality: int = 90,
    name_pattern: str = "{name}",
    image_index: int | None = None
) -> dict:
    """Export all open images (or a specific one) to a directory.

    Parameters:
    - output_dir: Directory to write exported files into
    - format: "png", "jpeg", "webp", "tiff" (default "png")
    - quality: JPEG/WEBP quality (default 90)
    - name_pattern: Filename template — use {name} for image name, {index} for position
    - image_index: If set, export only that image; omit to export all open images

    Returns:
    - exported: list of {file_path, name, width, height}
    - count: number of files written
    - errors: list of any export errors
    """
    try:
        params: dict = {
            "output_dir": output_dir,
            "format": format,
            "quality": quality,
            "name_pattern": name_pattern,
        }
        if image_index is not None:
            params["image_index"] = image_index
        conn = get_gimp_connection()
        result = conn.send_command("batch_export", params)
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"batch_export failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 2 — Image Adjustments
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def auto_levels(ctx: Context, image_index: int = 0, layer_name: str | None = None) -> dict:
    """Automatically stretch the tonal range of an image (auto levels / auto stretch contrast).

    Parameters:
    - image_index: Index of the target image (default 0)
    - layer_name: Name of the layer to adjust; defaults to active layer

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("auto_levels", {"image_index": image_index, "layer_name": layer_name})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"auto_levels failed: {e}")


@mcp.tool()
def adjust_curves(
    ctx: Context,
    preset: str = "s_curve",
    points: list | None = None,
    channel: str = "value",
    image_index: int = 0,
    layer_name: str | None = None
) -> dict:
    """Adjust tonal curves for a layer.

    Parameters:
    - preset: Built-in curve shape — "s_curve" (default), "lighten", "darken", "contrast"
    - points: Custom control points as [[input, output], ...] override (overrides preset)
    - channel: "value" (all), "red", "green", "blue", "alpha"
    - image_index: Target image index (default 0)
    - layer_name: Layer to adjust; defaults to active layer

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("adjust_curves", {
            "preset": preset,
            "points": points,
            "channel": channel,
            "image_index": image_index,
            "layer_name": layer_name,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"adjust_curves failed: {e}")


@mcp.tool()
def adjust_brightness_contrast(
    ctx: Context,
    brightness: int = 0,
    contrast: int = 0,
    image_index: int = 0,
    layer_name: str | None = None
) -> dict:
    """Adjust brightness and contrast of a layer.

    Parameters:
    - brightness: -127 to +127 (default 0)
    - contrast: -127 to +127 (default 0)
    - image_index: Target image index (default 0)
    - layer_name: Layer to adjust; defaults to active layer

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("adjust_brightness_contrast", {
            "brightness": brightness,
            "contrast": contrast,
            "image_index": image_index,
            "layer_name": layer_name,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"adjust_brightness_contrast failed: {e}")


@mcp.tool()
def adjust_hue_saturation(
    ctx: Context,
    hue: float = 0,
    saturation: float = 0,
    lightness: float = 0,
    color_range: str = "all",
    image_index: int = 0,
    layer_name: str | None = None
) -> dict:
    """Adjust hue, saturation, and lightness of a layer.

    Parameters:
    - hue: Hue rotation -180 to +180 (default 0)
    - saturation: Saturation shift -100 to +100 (default 0)
    - lightness: Lightness shift -100 to +100 (default 0)
    - color_range: "all", "red", "yellow", "green", "cyan", "blue", "magenta" (default "all")
    - image_index: Target image index (default 0)
    - layer_name: Layer to adjust; defaults to active layer

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("adjust_hue_saturation", {
            "hue": hue,
            "saturation": saturation,
            "lightness": lightness,
            "color_range": color_range,
            "image_index": image_index,
            "layer_name": layer_name,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"adjust_hue_saturation failed: {e}")


@mcp.tool()
def adjust_color_balance(
    ctx: Context,
    cyan_red: float = 0,
    magenta_green: float = 0,
    yellow_blue: float = 0,
    range: str = "midtones",
    image_index: int = 0,
    layer_name: str | None = None
) -> dict:
    """Adjust color balance (shadows / midtones / highlights) of a layer.

    Parameters:
    - cyan_red: -100 to +100 (negative = cyan, positive = red; default 0)
    - magenta_green: -100 to +100 (default 0)
    - yellow_blue: -100 to +100 (default 0)
    - range: "shadows", "midtones" (default), "highlights"
    - image_index: Target image index (default 0)
    - layer_name: Layer to adjust; defaults to active layer

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("adjust_color_balance", {
            "cyan_red": cyan_red,
            "magenta_green": magenta_green,
            "yellow_blue": yellow_blue,
            "range": range,
            "image_index": image_index,
            "layer_name": layer_name,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"adjust_color_balance failed: {e}")


@mcp.tool()
def sharpen(
    ctx: Context,
    amount: float = 50.0,
    radius: float = 3.0,
    threshold: int = 0,
    image_index: int = 0,
    layer_name: str | None = None
) -> dict:
    """Sharpen a layer using unsharp mask.

    Parameters:
    - amount: Sharpening strength 0-500 (default 50.0)
    - radius: Blur radius for the mask in pixels (default 3.0)
    - threshold: Minimum difference before sharpening is applied (default 0)
    - image_index: Target image index (default 0)
    - layer_name: Layer to sharpen; defaults to active layer

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("sharpen", {
            "amount": amount,
            "radius": radius,
            "threshold": threshold,
            "image_index": image_index,
            "layer_name": layer_name,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"sharpen failed: {e}")


@mcp.tool()
def blur(
    ctx: Context,
    radius_x: float = 5.0,
    radius_y: float = 5.0,
    image_index: int = 0,
    layer_name: str | None = None
) -> dict:
    """Apply Gaussian blur to a layer.

    Parameters:
    - radius_x: Horizontal blur radius in pixels (default 5.0)
    - radius_y: Vertical blur radius in pixels (default 5.0)
    - image_index: Target image index (default 0)
    - layer_name: Layer to blur; defaults to active layer

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("blur", {
            "radius_x": radius_x,
            "radius_y": radius_y,
            "image_index": image_index,
            "layer_name": layer_name,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"blur failed: {e}")


@mcp.tool()
def denoise(
    ctx: Context,
    strength: int = 50,
    image_index: int = 0,
    layer_name: str | None = None
) -> dict:
    """Reduce noise in a layer using GEGL noise-reduction.

    Parameters:
    - strength: Noise reduction strength 0-100 (default 50)
    - image_index: Target image index (default 0)
    - layer_name: Layer to denoise; defaults to active layer

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("denoise", {
            "strength": strength,
            "image_index": image_index,
            "layer_name": layer_name,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"denoise failed: {e}")


@mcp.tool()
def desaturate(
    ctx: Context,
    mode: str = "luminosity",
    image_index: int = 0,
    layer_name: str | None = None
) -> dict:
    """Convert a layer to grayscale (desaturate).

    Parameters:
    - mode: Desaturation algorithm — "luminosity" (default), "luma", "average", "lightness"
    - image_index: Target image index (default 0)
    - layer_name: Layer to desaturate; defaults to active layer

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("desaturate", {
            "mode": mode,
            "image_index": image_index,
            "layer_name": layer_name,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"desaturate failed: {e}")


@mcp.tool()
def invert_colors(
    ctx: Context,
    image_index: int = 0,
    layer_name: str | None = None
) -> dict:
    """Invert all colors in a layer (create a negative).

    Parameters:
    - image_index: Target image index (default 0)
    - layer_name: Layer to invert; defaults to active layer

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("invert_colors", {
            "image_index": image_index,
            "layer_name": layer_name,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"invert_colors failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 3 — Resize & Transform
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def scale_image(
    ctx: Context,
    width: int,
    height: int,
    interpolation: str = "cubic",
    image_index: int = 0
) -> dict:
    """Scale an image to exact pixel dimensions.

    Parameters:
    - width: Target width in pixels
    - height: Target height in pixels
    - interpolation: "cubic" (default), "linear", "none"
    - image_index: Target image index (default 0)

    Returns: {status, width, height}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("scale_image", {
            "width": width,
            "height": height,
            "interpolation": interpolation,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"scale_image failed: {e}")


@mcp.tool()
def scale_to_fit(
    ctx: Context,
    max_width: int,
    max_height: int,
    interpolation: str = "cubic",
    image_index: int = 0
) -> dict:
    """Scale an image to fit within a bounding box, preserving aspect ratio.

    Parameters:
    - max_width: Maximum allowed width in pixels
    - max_height: Maximum allowed height in pixels
    - interpolation: "cubic" (default), "linear", "none"
    - image_index: Target image index (default 0)

    Returns: {status, width, height} — final dimensions after scaling
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("scale_to_fit", {
            "max_width": max_width,
            "max_height": max_height,
            "interpolation": interpolation,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"scale_to_fit failed: {e}")


@mcp.tool()
def crop_to_selection(
    ctx: Context,
    autocrop: bool = False,
    image_index: int = 0
) -> dict:
    """Crop the image canvas to the current selection bounds.

    Parameters:
    - autocrop: If True, auto-detect crop bounds instead of using selection (default False)
    - image_index: Target image index (default 0)

    Returns: {status, x, y, width, height} — crop region applied
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("crop_to_selection", {
            "autocrop": autocrop,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"crop_to_selection failed: {e}")


@mcp.tool()
def crop_to_rect(
    ctx: Context,
    x: int,
    y: int,
    width: int,
    height: int,
    image_index: int = 0
) -> dict:
    """Crop the image canvas to an explicit rectangle.

    Parameters:
    - x, y: Top-left corner of the crop rectangle
    - width, height: Dimensions of the crop rectangle
    - image_index: Target image index (default 0)

    Returns: {status, x, y, width, height}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("crop_to_rect", {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"crop_to_rect failed: {e}")


@mcp.tool()
def rotate_image(
    ctx: Context,
    angle: float,
    image_index: int = 0
) -> dict:
    """Rotate the entire image.

    Parameters:
    - angle: Rotation in degrees — 90, 180, 270 use lossless GIMP rotation;
             other values rotate all layers with interpolation and flatten
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("rotate_image", {
            "angle": angle,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"rotate_image failed: {e}")


@mcp.tool()
def flip_image(
    ctx: Context,
    direction: str = "horizontal",
    image_index: int = 0
) -> dict:
    """Flip the entire image horizontally or vertically.

    Parameters:
    - direction: "horizontal" (default) or "vertical"
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("flip_image", {
            "direction": direction,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"flip_image failed: {e}")


@mcp.tool()
def resize_canvas(
    ctx: Context,
    width: int,
    height: int,
    anchor: str = "center",
    fill: str = "transparent",
    image_index: int = 0
) -> dict:
    """Resize the image canvas without scaling the content.

    Parameters:
    - width, height: New canvas dimensions in pixels
    - anchor: Position of existing content — "center" (default), "top-left", "top",
              "top-right", "left", "right", "bottom-left", "bottom", "bottom-right"
    - fill: Color for new canvas areas — CSS color or "transparent"
    - image_index: Target image index (default 0)

    Returns: {status, width, height, offset_x, offset_y}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("resize_canvas", {
            "width": width,
            "height": height,
            "anchor": anchor,
            "fill": fill,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"resize_canvas failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 4 — Selections
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def select_rectangle(
    ctx: Context,
    x: int,
    y: int,
    width: int,
    height: int,
    operation: str = "replace",
    feather: float = 0,
    image_index: int = 0
) -> dict:
    """Create a rectangular selection.

    Parameters:
    - x, y: Top-left corner of the selection
    - width, height: Dimensions of the selection
    - operation: "replace" (default), "add", "subtract", "intersect"
    - feather: Feather radius in pixels (default 0 = no feather)
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("select_rectangle", {
            "x": x, "y": y, "width": width, "height": height,
            "operation": operation, "feather": feather, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"select_rectangle failed: {e}")


@mcp.tool()
def select_ellipse(
    ctx: Context,
    x: int,
    y: int,
    width: int,
    height: int,
    operation: str = "replace",
    feather: float = 0,
    image_index: int = 0
) -> dict:
    """Create an elliptical selection.

    Parameters:
    - x, y: Top-left corner of the bounding box
    - width, height: Bounding box dimensions
    - operation: "replace" (default), "add", "subtract", "intersect"
    - feather: Feather radius in pixels (default 0)
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("select_ellipse", {
            "x": x, "y": y, "width": width, "height": height,
            "operation": operation, "feather": feather, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"select_ellipse failed: {e}")


@mcp.tool()
def select_by_color(
    ctx: Context,
    color: str,
    threshold: int = 15,
    operation: str = "replace",
    image_index: int = 0,
    layer_name: str | None = None
) -> dict:
    """Select regions by color similarity.

    Parameters:
    - color: Target color as CSS name, hex (#rrggbb), or rgb() string
    - threshold: Color similarity tolerance 0-255 (default 15)
    - operation: "replace" (default), "add", "subtract", "intersect"
    - image_index: Target image index (default 0)
    - layer_name: Layer to sample from; defaults to active layer

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("select_by_color", {
            "color": color,
            "threshold": threshold,
            "operation": operation,
            "image_index": image_index,
            "layer_name": layer_name,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"select_by_color failed: {e}")


@mcp.tool()
def select_all(ctx: Context, image_index: int = 0) -> dict:
    """Select the entire image canvas.

    Parameters:
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("select_all", {"image_index": image_index})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"select_all failed: {e}")


@mcp.tool()
def select_none(ctx: Context, image_index: int = 0) -> dict:
    """Remove / deselect all selections.

    Parameters:
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("select_none", {"image_index": image_index})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"select_none failed: {e}")


@mcp.tool()
def invert_selection(ctx: Context, image_index: int = 0) -> dict:
    """Invert the current selection (select what is not selected).

    Parameters:
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("invert_selection", {"image_index": image_index})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"invert_selection failed: {e}")


@mcp.tool()
def modify_selection(
    ctx: Context,
    operation: str,
    amount: float,
    image_index: int = 0
) -> dict:
    """Grow, shrink, feather, border, or sharpen the current selection.

    Parameters:
    - operation: "grow", "shrink", "feather", "border", "sharpen"
    - amount: Pixel radius for grow/shrink/feather/border; ignored for sharpen
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("modify_selection", {
            "operation": operation,
            "amount": amount,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"modify_selection failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 5 — Layer Operations
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def create_layer(
    ctx: Context,
    name: str = "New Layer",
    width: int | None = None,
    height: int | None = None,
    fill: str = "transparent",
    opacity: float = 100,
    blend_mode: str = "NORMAL",
    position: int = -1,
    image_index: int = 0
) -> dict:
    """Create and insert a new layer into an image.

    Parameters:
    - name: Layer name (default "New Layer")
    - width, height: Layer dimensions; defaults to image dimensions
    - fill: Initial fill — "transparent" (default), "white", "black", or any CSS color
    - opacity: Layer opacity 0-100 (default 100)
    - blend_mode: GIMP layer mode name — "NORMAL" (default), "MULTIPLY", "SCREEN", etc.
    - position: Stack position — -1 = top (default), 0 = bottom
    - image_index: Target image index (default 0)

    Returns: {layer_name, layer_id, width, height, position}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("create_layer", {
            "name": name, "width": width, "height": height,
            "fill": fill, "opacity": opacity, "blend_mode": blend_mode,
            "position": position, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"create_layer failed: {e}")


@mcp.tool()
def duplicate_layer(
    ctx: Context,
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Duplicate a layer and insert the copy above it.

    Parameters:
    - layer_name: Name of the layer to duplicate; defaults to active layer
    - image_index: Target image index (default 0)

    Returns: {layer_name, layer_id}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("duplicate_layer", {
            "layer_name": layer_name,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"duplicate_layer failed: {e}")


@mcp.tool()
def delete_layer(
    ctx: Context,
    layer_name: str | None = None,
    layer_index: int | None = None,
    image_index: int = 0
) -> dict:
    """Delete a layer from an image.

    Parameters:
    - layer_name: Name of the layer to delete
    - layer_index: Position index of the layer (alternative to layer_name)
    - image_index: Target image index (default 0)

    Provide either layer_name or layer_index. Defaults to active layer if neither given.

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("delete_layer", {
            "layer_name": layer_name,
            "layer_index": layer_index,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"delete_layer failed: {e}")


@mcp.tool()
def rename_layer(
    ctx: Context,
    new_name: str,
    old_name: str | None = None,
    layer_index: int | None = None,
    image_index: int = 0
) -> dict:
    """Rename a layer.

    Parameters:
    - new_name: New name for the layer
    - old_name: Current name of the layer to rename
    - layer_index: Position index alternative to old_name
    - image_index: Target image index (default 0)

    Returns: {old_name, new_name}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("rename_layer", {
            "old_name": old_name,
            "layer_index": layer_index,
            "new_name": new_name,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"rename_layer failed: {e}")


@mcp.tool()
def set_layer_properties(
    ctx: Context,
    layer_name: str | None = None,
    layer_index: int | None = None,
    opacity: float | None = None,
    blend_mode: str | None = None,
    visible: bool | None = None,
    image_index: int = 0
) -> dict:
    """Set properties on an existing layer.

    Parameters:
    - layer_name / layer_index: Identify the layer (defaults to active layer)
    - opacity: New opacity 0-100 (omit to leave unchanged)
    - blend_mode: New GIMP layer mode name (omit to leave unchanged)
    - visible: True/False visibility (omit to leave unchanged)
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("set_layer_properties", {
            "layer_name": layer_name, "layer_index": layer_index,
            "opacity": opacity, "blend_mode": blend_mode,
            "visible": visible, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"set_layer_properties failed: {e}")


@mcp.tool()
def reorder_layer(
    ctx: Context,
    new_position: int,
    layer_name: str | None = None,
    layer_index: int | None = None,
    image_index: int = 0
) -> dict:
    """Move a layer to a new stack position.

    Parameters:
    - new_position: Target stack index (0 = bottom)
    - layer_name / layer_index: Identify the layer (defaults to active layer)
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("reorder_layer", {
            "layer_name": layer_name, "layer_index": layer_index,
            "new_position": new_position, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"reorder_layer failed: {e}")


@mcp.tool()
def flatten_image(ctx: Context, image_index: int = 0) -> dict:
    """Flatten all layers into a single background layer.

    Parameters:
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("flatten_image", {"image_index": image_index})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"flatten_image failed: {e}")


@mcp.tool()
def merge_visible_layers(ctx: Context, image_index: int = 0) -> dict:
    """Merge all visible layers into a single layer.

    Parameters:
    - image_index: Target image index (default 0)

    Returns: {layer_name, layer_id}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("merge_visible_layers", {"image_index": image_index})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"merge_visible_layers failed: {e}")


@mcp.tool()
def list_layers(ctx: Context, image_index: int = 0) -> dict:
    """List all layers in an image with their properties.

    Parameters:
    - image_index: Target image index (default 0)

    Returns: {layers: [{name, id, visible, opacity, blend_mode, width, height, has_alpha}], count}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("list_layers", {"image_index": image_index})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"list_layers failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 6 — Color & Paint
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def fill_layer(
    ctx: Context,
    color: str,
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Fill an entire layer with a solid color.

    Parameters:
    - color: Fill color as CSS name, hex, or rgb() string
    - layer_name: Layer to fill; defaults to active layer
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("fill_layer", {
            "color": color, "layer_name": layer_name, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"fill_layer failed: {e}")


@mcp.tool()
def fill_selection(
    ctx: Context,
    color: str,
    image_index: int = 0,
    layer_name: str | None = None
) -> dict:
    """Fill the current selection with a solid color.

    Parameters:
    - color: Fill color as CSS name, hex, or rgb() string
    - image_index: Target image index (default 0)
    - layer_name: Target layer; defaults to active layer

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("fill_selection", {
            "color": color, "image_index": image_index, "layer_name": layer_name,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"fill_selection failed: {e}")


@mcp.tool()
def set_colors(
    ctx: Context,
    foreground: str | None = None,
    background: str | None = None
) -> dict:
    """Set the GIMP foreground and/or background color.

    Parameters:
    - foreground: New foreground color (CSS name, hex, rgb()); omit to leave unchanged
    - background: New background color; omit to leave unchanged

    Returns: {foreground, background} confirmation dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("set_colors", {
            "foreground": foreground, "background": background,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"set_colors failed: {e}")


@mcp.tool()
def draw_line(
    ctx: Context,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: str | None = None,
    width: float = 2.0,
    tool: str = "pencil",
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Draw a straight line on a layer.

    Parameters:
    - x1, y1: Start point
    - x2, y2: End point
    - color: Stroke color (CSS / hex / rgb); uses current foreground if omitted
    - width: Stroke width in pixels (default 2.0)
    - tool: "pencil" (default, hard edge) or "paintbrush" (soft edge)
    - layer_name: Target layer; defaults to active layer
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("draw_line", {
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "color": color, "width": width, "tool": tool,
            "layer_name": layer_name, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"draw_line failed: {e}")


@mcp.tool()
def draw_rectangle(
    ctx: Context,
    x: int,
    y: int,
    width: int,
    height: int,
    color: str | None = None,
    line_width: float = 2.0,
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Draw a rectangle outline (stroke only) on a layer.

    Parameters:
    - x, y: Top-left corner
    - width, height: Rectangle dimensions
    - color: Stroke color; uses current foreground if omitted
    - line_width: Stroke width in pixels (default 2.0)
    - layer_name: Target layer; defaults to active layer
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("draw_rectangle", {
            "x": x, "y": y, "width": width, "height": height,
            "color": color, "line_width": line_width,
            "layer_name": layer_name, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"draw_rectangle failed: {e}")


@mcp.tool()
def draw_ellipse(
    ctx: Context,
    x: int,
    y: int,
    width: int,
    height: int,
    color: str | None = None,
    line_width: float = 2.0,
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Draw an ellipse outline (stroke only) on a layer.

    Parameters:
    - x, y: Top-left corner of the bounding box
    - width, height: Bounding box dimensions
    - color: Stroke color; uses current foreground if omitted
    - line_width: Stroke width in pixels (default 2.0)
    - layer_name: Target layer; defaults to active layer
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("draw_ellipse", {
            "x": x, "y": y, "width": width, "height": height,
            "color": color, "line_width": line_width,
            "layer_name": layer_name, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"draw_ellipse failed: {e}")


@mcp.tool()
def fill_rectangle(
    ctx: Context,
    x: int,
    y: int,
    width: int,
    height: int,
    color: str,
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Fill a rectangular region with a solid color.

    Parameters:
    - x, y: Top-left corner
    - width, height: Rectangle dimensions
    - color: Fill color (CSS name, hex, or rgb() string)
    - layer_name: Target layer; defaults to active layer
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("fill_rectangle", {
            "x": x, "y": y, "width": width, "height": height,
            "color": color, "layer_name": layer_name, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"fill_rectangle failed: {e}")


@mcp.tool()
def fill_ellipse(
    ctx: Context,
    x: int,
    y: int,
    width: int,
    height: int,
    color: str,
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Fill an elliptical region with a solid color.

    Parameters:
    - x, y: Top-left corner of the bounding box
    - width, height: Bounding box dimensions
    - color: Fill color (CSS name, hex, or rgb() string)
    - layer_name: Target layer; defaults to active layer
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("fill_ellipse", {
            "x": x, "y": y, "width": width, "height": height,
            "color": color, "layer_name": layer_name, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"fill_ellipse failed: {e}")


@mcp.tool()
def gradient_fill(
    ctx: Context,
    color1: str = "black",
    color2: str = "white",
    x1: float = 0,
    y1: float = 0,
    x2: float | None = None,
    y2: float | None = None,
    gradient_type: str = "linear",
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Fill a layer or selection with a gradient.

    Parameters:
    - color1: Start color (default "black")
    - color2: End color (default "white")
    - x1, y1: Gradient start point (default top-left 0,0)
    - x2, y2: Gradient end point (defaults to bottom-right of image)
    - gradient_type: "linear" (default) or "radial"
    - layer_name: Target layer; defaults to active layer
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("gradient_fill", {
            "color1": color1, "color2": color2,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "gradient_type": gradient_type,
            "layer_name": layer_name, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"gradient_fill failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 7 — Text
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def add_text(
    ctx: Context,
    text: str,
    x: int = 0,
    y: int = 0,
    font: str = "Sans",
    size: int = 24,
    color: str = "black",
    image_index: int = 0
) -> dict:
    """Add a text layer to an image.

    Parameters:
    - text: The text string to render
    - x, y: Position of the text layer's top-left corner (default 0, 0)
    - font: Font family name — "Sans" (default), "Serif", etc.
    - size: Font size in pixels (default 24)
    - color: Text color (CSS name, hex, or rgb() string; default "black")
    - image_index: Target image index (default 0)

    Returns: {layer_name, layer_id, text_width, text_height, position}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("add_text", {
            "text": text, "x": x, "y": y,
            "font": font, "size": size, "color": color,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"add_text failed: {e}")


@mcp.tool()
def edit_text(
    ctx: Context,
    layer_name: str,
    text: str | None = None,
    font: str | None = None,
    size: float | None = None,
    color: str | None = None,
    image_index: int = 0
) -> dict:
    """Edit an existing text layer's content or formatting.

    Parameters:
    - layer_name: Name of the text layer to edit
    - text: New text content (omit to leave unchanged)
    - font: New font family (omit to leave unchanged)
    - size: New font size in pixels (omit to leave unchanged)
    - color: New text color (omit to leave unchanged)
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("edit_text", {
            "layer_name": layer_name, "text": text,
            "font": font, "size": size, "color": color,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"edit_text failed: {e}")


@mcp.tool()
def list_fonts(ctx: Context, filter: str | None = None) -> dict:
    """List available fonts installed in GIMP.

    Parameters:
    - filter: Optional string to filter font names (case-insensitive substring match)

    Returns: {fonts: [font_name, ...], count}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("list_fonts", {"filter": filter})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"list_fonts failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 8 — Filters & Effects
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def apply_drop_shadow(
    ctx: Context,
    offset_x: int = 5,
    offset_y: int = 5,
    blur_radius: float = 10,
    color: str = "black",
    opacity: float = 60,
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Apply a drop shadow effect to a layer.

    Parameters:
    - offset_x, offset_y: Shadow offset in pixels (default 5, 5)
    - blur_radius: Shadow softness radius (default 10)
    - color: Shadow color (default "black")
    - opacity: Shadow opacity 0-100 (default 60)
    - layer_name: Target layer; defaults to active layer
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("apply_drop_shadow", {
            "offset_x": offset_x, "offset_y": offset_y,
            "blur_radius": blur_radius, "color": color, "opacity": opacity,
            "layer_name": layer_name, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"apply_drop_shadow failed: {e}")


@mcp.tool()
def apply_gaussian_blur(
    ctx: Context,
    radius: float = 5.0,
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Apply Gaussian blur as a destructive filter operation.

    Parameters:
    - radius: Blur radius in pixels (default 5.0)
    - layer_name: Target layer; defaults to active layer
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("apply_gaussian_blur", {
            "radius": radius, "layer_name": layer_name, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"apply_gaussian_blur failed: {e}")


@mcp.tool()
def apply_pixelate(
    ctx: Context,
    block_size: int = 10,
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Pixelate a layer using a mosaic/block effect.

    Parameters:
    - block_size: Size of each mosaic block in pixels (default 10)
    - layer_name: Target layer; defaults to active layer
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("apply_pixelate", {
            "block_size": block_size, "layer_name": layer_name, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"apply_pixelate failed: {e}")


@mcp.tool()
def apply_emboss(
    ctx: Context,
    azimuth: float = 315,
    elevation: float = 45,
    depth: float = 2,
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Apply an emboss (bas-relief) effect to a layer.

    Parameters:
    - azimuth: Light direction in degrees 0-360 (default 315 = top-left)
    - elevation: Light elevation angle 0-90 (default 45)
    - depth: Effect depth/intensity (default 2)
    - layer_name: Target layer; defaults to active layer
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("apply_emboss", {
            "azimuth": azimuth, "elevation": elevation, "depth": depth,
            "layer_name": layer_name, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"apply_emboss failed: {e}")


@mcp.tool()
def apply_vignette(
    ctx: Context,
    softness: float = 3.0,
    shape: float = 1.0,
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Apply a vignette darkening effect around the edges of a layer.

    Parameters:
    - softness: Edge softness / fade width (default 3.0)
    - shape: Shape factor — 1.0 = elliptical (default), values >1 = more rectangular
    - layer_name: Target layer; defaults to active layer
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("apply_vignette", {
            "softness": softness, "shape": shape,
            "layer_name": layer_name, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"apply_vignette failed: {e}")


@mcp.tool()
def apply_noise(
    ctx: Context,
    amount: float = 0.2,
    layer_name: str | None = None,
    image_index: int = 0
) -> dict:
    """Add noise/grain to a layer.

    Parameters:
    - amount: Noise intensity 0.0-1.0 (default 0.2)
    - layer_name: Target layer; defaults to active layer
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("apply_noise", {
            "amount": amount, "layer_name": layer_name, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"apply_noise failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 9 — Export Pipelines
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def export_icon_sizes(
    ctx: Context,
    output_dir: str,
    platform: str = "android",
    source_image_index: int = 0,
    format: str = "png"
) -> dict:
    """Export an image as a complete icon set for Android or iOS.

    Android sizes: 48 (mdpi), 72 (hdpi), 96 (xhdpi), 144 (xxhdpi),
                   192 (xxxhdpi), 512 (Play Store)
    iOS sizes: 20x1/2/3, 29x1/2/3, 40x2/3, 60x2/3, 76x1/2, 83.5x2, 1024x1

    Parameters:
    - output_dir: Directory to write icon files into
    - platform: "android" (default) or "ios"
    - source_image_index: Image to use as source (default 0)
    - format: Output format — "png" (default)

    Returns: {exported: [{size, file_path}], count, platform}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("export_icon_sizes", {
            "output_dir": output_dir, "platform": platform,
            "source_image_index": source_image_index, "format": format,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"export_icon_sizes failed: {e}")


@mcp.tool()
def export_web_optimized(
    ctx: Context,
    output_dir: str,
    jpeg_quality: int = 85,
    png_compression: int = 9,
    max_width: int | None = None,
    max_height: int | None = None,
    image_index: int = 0
) -> dict:
    """Export an image as both JPEG and PNG, choosing the smaller format.

    Parameters:
    - output_dir: Directory to write output files
    - jpeg_quality: JPEG quality 1-100 (default 85)
    - png_compression: PNG compression level 0-9 (default 9)
    - max_width / max_height: Optional scaling before export
    - image_index: Source image index (default 0)

    Returns: {jpeg_path, jpeg_size, png_path, png_size, recommendation}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("export_web_optimized", {
            "output_dir": output_dir,
            "jpeg_quality": jpeg_quality,
            "png_compression": png_compression,
            "max_width": max_width,
            "max_height": max_height,
            "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"export_web_optimized failed: {e}")


@mcp.tool()
def warp_region(
    ctx: Context,
    vectors: list,
    image_index: int = 0,
    layer_name: str | None = None,
) -> dict:
    """Warp / liquify a region of the image by pushing pixels in a direction.

    Uses GEGL warp (GIMP 3 native) with plug-in-iwarp fallback. Ideal for
    subtle facial expression edits — e.g. turning a neutral mouth into a smile
    by pushing the mouth corners upward.

    Parameters:
    - vectors: List of warp stroke dicts, each with:
        - x, y      : center of the warp influence (pixels)
        - dx, dy    : push direction — negative dy = push upward
        - radius    : influence radius in pixels (default: 40)
        - amount    : deform strength 0–1 (default: 0.3)
    - image_index: Which open image to edit (default: 0)
    - layer_name: Target layer; omit to use the active/top layer

    Examples — make a character smile:
        warp_region(vectors=[
            {"x": 215, "y": 355, "dx":  5, "dy": -8, "radius": 18, "amount": 0.45},
            {"x": 295, "y": 355, "dx": -5, "dy": -8, "radius": 18, "amount": 0.45},
            {"x": 255, "y": 370, "dx":  0, "dy": -4, "radius": 22, "amount": 0.30},
        ])

    Returns: {"warped_vectors": N}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("warp_region", {
            "image_index": image_index,
            "layer_name":  layer_name,
            "vectors":     vectors,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"warp_region failed: {e}")


@mcp.tool()
def batch_resize(
    ctx: Context,
    width: int | None = None,
    height: int | None = None,
    scale_factor: float | None = None,
    maintain_aspect: bool = True
) -> dict:
    """Resize all open images to a common target size.

    Parameters:
    - width / height: Target dimensions in pixels (provide one or both)
    - scale_factor: Proportional scale (e.g. 0.5 = 50%); overrides width/height if set
    - maintain_aspect: Preserve aspect ratio when only one dimension is given (default True)

    Returns: {results: [{image_id, old_width, old_height, new_width, new_height}], count}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("batch_resize", {
            "width": width, "height": height,
            "scale_factor": scale_factor, "maintain_aspect": maintain_aspect,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"batch_resize failed: {e}")


@mcp.tool()
def export_sprite_sheet(
    ctx: Context,
    output_path: str,
    columns: int | None = None,
    padding: int = 0,
    source: str = "layers",
    image_index: int = 0
) -> dict:
    """Combine multiple frames into a sprite sheet PNG.

    Parameters:
    - output_path: Absolute path for the output PNG file
    - columns: Number of columns in the grid (defaults to square root of frame count)
    - padding: Pixel gap between frames (default 0)
    - source: "layers" (each layer is a frame; default) or "images" (each open image)
    - image_index: Source image when source="layers" (default 0)

    Returns: {file_path, columns, rows, frame_width, frame_height, count}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("export_sprite_sheet", {
            "output_path": output_path, "columns": columns,
            "padding": padding, "source": source, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"export_sprite_sheet failed: {e}")


@mcp.tool()
def export_social_media_kit(
    ctx: Context,
    output_dir: str,
    platforms: list | None = None,
    image_index: int = 0
) -> dict:
    """Export an image resized for multiple social media platforms.

    Platform sizes (all in pixels):
    - instagram_square: 1080x1080
    - instagram_story: 1080x1920
    - twitter_header: 1500x500
    - facebook_cover: 820x312
    - youtube_thumbnail: 1280x720

    Parameters:
    - output_dir: Directory to write output files
    - platforms: List of platform names to export (omit for all five)
    - image_index: Source image index (default 0)

    Returns: {exported: [{platform, file_path, width, height}], count}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("export_social_media_kit", {
            "output_dir": output_dir, "platforms": platforms, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"export_social_media_kit failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 10 — Utility
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_images(ctx: Context) -> dict:
    """List all images currently open in GIMP.

    Returns:
    - images: list of {index, image_id, name, width, height, color_mode,
                       num_layers, file_path, is_dirty}
    - count: total number of open images
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("list_images", {})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"list_images failed: {e}")


@mcp.tool()
def set_active_image(ctx: Context, image_index: int) -> dict:
    """Raise a specific image to the front / make it active in GIMP.

    Parameters:
    - image_index: Index of the image to activate (from list_images)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("set_active_image", {"image_index": image_index})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"set_active_image failed: {e}")


@mcp.tool()
def undo(ctx: Context, steps: int = 1, image_index: int = 0) -> dict:
    """Undo one or more operations on an image.

    Parameters:
    - steps: Number of undo steps (default 1)
    - image_index: Target image index (default 0)

    Returns: {steps_undone}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("undo", {"steps": steps, "image_index": image_index})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"undo failed: {e}")


@mcp.tool()
def redo(ctx: Context, steps: int = 1, image_index: int = 0) -> dict:
    """Redo one or more previously undone operations on an image.

    Parameters:
    - steps: Number of redo steps (default 1)
    - image_index: Target image index (default 0)

    Returns: {steps_redone}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("redo", {"steps": steps, "image_index": image_index})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"redo failed: {e}")


@mcp.tool()
def convert_color_mode(
    ctx: Context,
    mode: str,
    num_colors: int = 256,
    image_index: int = 0
) -> dict:
    """Convert an image to a different color mode.

    Parameters:
    - mode: "RGB", "GRAY", or "INDEXED"
    - num_colors: Number of colors for INDEXED mode (default 256)
    - image_index: Target image index (default 0)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("convert_color_mode", {
            "mode": mode, "num_colors": num_colors, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"convert_color_mode failed: {e}")


@mcp.tool()
def close_image(
    ctx: Context,
    image_index: int = 0,
    save_first: bool = False
) -> dict:
    """Close an image, optionally saving as XCF first.

    Parameters:
    - image_index: Index of the image to close (default 0)
    - save_first: If True, save as XCF before closing (default False)

    Returns status dict.
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("close_image", {
            "image_index": image_index, "save_first": save_first,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"close_image failed: {e}")


@mcp.tool()
def get_selection_bounds(ctx: Context, image_index: int = 0) -> dict:
    """Get the bounding rectangle of the current selection.

    Parameters:
    - image_index: Target image index (default 0)

    Returns: {has_selection, x, y, width, height}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("get_selection_bounds", {"image_index": image_index})
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"get_selection_bounds failed: {e}")


@mcp.tool()
def get_pixel_color(
    ctx: Context,
    x: int,
    y: int,
    image_index: int = 0,
    layer_name: str | None = None
) -> dict:
    """Get the color of a single pixel.

    Parameters:
    - x, y: Pixel coordinates
    - image_index: Target image index (default 0)
    - layer_name: Layer to sample from; defaults to active layer

    Returns: {color_hex, color_rgb: [r, g, b], alpha}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("get_pixel_color", {
            "x": x, "y": y, "image_index": image_index, "layer_name": layer_name,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"get_pixel_color failed: {e}")


@mcp.tool()
def get_histogram(
    ctx: Context,
    channel: str = "value",
    image_index: int = 0
) -> dict:
    """Get histogram statistics for a channel of the active layer.

    Parameters:
    - channel: "value" (all; default), "red", "green", "blue", "alpha"
    - image_index: Target image index (default 0)

    Returns: {mean, median, std_dev, min, max, pixels, count}
    """
    try:
        conn = get_gimp_connection()
        result = conn.send_command("get_histogram", {
            "channel": channel, "image_index": image_index,
        })
        if result["status"] == "success":
            return result["results"]
        raise Exception(result.get("error", "Unknown error"))
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"get_histogram failed: {e}")


def main():
    mcp.run()

if __name__ == "__main__":
    main()