# Changelog

All notable changes to `gimp-mcp-plugin` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

The plugin and the MCP server must run exactly the same version. To upgrade, restart your
MCP client so it starts the new server, then run `uvx gimp-mcp-plugin@latest install-plugin`
and restart GIMP. If you pin the server to a version, install that version's plugin with
`uvx gimp-mcp-plugin@X.Y.Z install-plugin`; from a checkout, run
`uv run gimp_mcp_server.py install-plugin`. `check_server` and `get_gimp_info` print the
right command when the versions differ.

## [Unreleased]

### Fixed
- Tools that call GIMP procedures no longer report success when GIMP rejects the call
  (for example on a locked layer) or doesn't have the procedure. They now return an
  error with GIMP's message, and the image is left unchanged. This affects most
  adjustment, filter, selection, drawing, text, transform and save tools, so a call that
  used to "succeed" without changing anything may now return an error (#90).

## [0.3.0] - 2026-11-12

### Added
- `GIMP_MCP_TIMEOUT` sets how many seconds the MCP server waits for GIMP to finish a
  command (default 300). `check_server` and `get_gimp_info` report it as
  `timeout_seconds`, and a timed-out command now says so and tells you how to raise it (#108).

### Changed
- Tools run on a single worker thread off the server's event loop, in the order they were
  sent. The server keeps answering pings and cancellations while GIMP runs a long
  command. A cancelled command that is still waiting never runs, but one GIMP has already
  started finishes in the background, so check the image before retrying it, or the edit
  may be applied twice (#106).

## [0.2.1] - 2026-11-11

### Fixed
- `denoise`, `apply_gaussian_blur`, `apply_pixelate`, `apply_emboss`, `apply_vignette` and
  `apply_noise` reported success on GIMP 3.2 without changing the image. They now apply
  the filter and raise an error for unknown or out-of-range parameters (#103).
- `get_histogram` returned wrong values (#48, #102).
- `new_canvas` no longer lets the current paint opacity or mode affect its background
  fill (#102).
- The fill and draw tools, and `create_layer`, now reset opacity and paint mode before
  painting, so a value left by an earlier `call_api` call no longer changes their result.
  Your own context settings are restored afterwards (#104).

## [0.2.0] - 2026-11-11

### Added
- `install-plugin` subcommand: `uvx gimp-mcp-plugin@latest install-plugin` installs the
  bundled GIMP plugin into the newest GIMP 3.x config dir (Linux standard/Snap/Flatpak,
  macOS, Windows including the Microsoft Store version). Supports `--dry-run`,
  `--gimp-dir DIR` and the `GIMP3_DIRECTORY` override (#98, #100).

### Changed
- The README documents `uvx gimp-mcp-plugin@latest` as the main way to install and
  run the server (#99).

## [0.1.0] - 2026-11-11

First release on PyPI as `gimp-mcp-plugin` (#96).

### Added
- Plugin/server version check: `check_server` and `get_gimp_info` report a mismatch
  and the command that fixes it (#95).
- **Tools > MCP > MCP Server Settings...** dialog with autostart and a configurable
  port (#91).

### Fixed
- **Tools > MCP > Check** and **Restart** reported the wrong server state (#93).
- `adjust_brightness_contrast` now matches GIMP 3's perceptual result (#58).
- `auto_levels` on GIMP 3.2 (#60).
- `edit_text` pixel units on GIMP 3.2 (#59).
- `open_image` no longer fails in headless mode when no display can be created (#67).
- `get_pixel_color` returns sRGB instead of linear values (#55).
- The plugin no longer crashes after a client-side timeout (#82).

[Unreleased]: https://github.com/gimp-mcp/gimp-mcp/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/gimp-mcp/gimp-mcp/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/gimp-mcp/gimp-mcp/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/gimp-mcp/gimp-mcp/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/gimp-mcp/gimp-mcp/releases/tag/v0.1.0
