# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-03-04

### Added
- **Batch Export: Reset Transform**: Added a new toggle to export settings.
  - When enabled, objects are temporarily moved to the world origin (0,0,0 position/rotation) during export and restored immediately after.
  - Default is ON.
  - Useful for game engine workflows where assets need centered foundations.

## [0.1.1] - 2026-01-27

### Added
- **Apply Modifiers Tool**: A new tool to batch apply modifiers on selected mesh objects.
  - Includes a customizable **Ignore List** in the RexTools3 sidebar.
  - Smartly skips hidden, invalid, or zero-influence modifiers.
  - Default ignore list includes "Armature" to protect rig bindings.
- **Smart Join Improvements**: Refactored `Ctrl + J` to check for UV map mismatches.
  - Warns the user via overlay if UV names or counts do not match between selected objects.
  - Uses a custom operator to ensure predictability and discoverability.
- **Weight Tools Section**: New panel visible only in Weight Paint mode.
- **XRay Brush Toggle**: A toggle that saves current brush settings and force-disables Front Face Only, Front Face Falloff, and sets Falloff Shape to Projected. Restores previous settings when toggled off.

## [0.1.0] - 2026-01-27

### Added
- **Tools: Common Tools**: Added "Extract Textures" button to pack and then unpack all textures locally.

### Changed
- Removed "Arrange All Nodes" from the Common Tools panel (still available in Shader Editor context menu and Node Helper panel).

## [0.0.1] - 2026-01-26

### Added
- **Started using changelog**
- **Tools: Easy PBR**
- **Tools: Batch Export**
- **Tools: Common Tools**
- **Tools: Object Tools**
- **Tools: UV Tools**
- **Tools: Shader Tools**
- Added "Arrange All Nodes" to Shader Editor context menu
- Added "Arrange All Nodes" to RexTools3 sidebar tab in Shader Editor and 3D Viewport
- **Added comprehensive README.md with tool locations and features**
- **Added Packed Texture Setup to Easy PBR**: High-density UI in file selector for mapping R, G, B, A channels to PBR slots (e.g., ORM, RA, etc.).
- **Added UV Tiling to Easy PBR**: Vector 2 field in material properties to scale all textures simultaneously, with automatic Mapping and Texture Coordinate node management.


### Changed
- Moved "Arrange All Nodes" button from Easy PBR material panel to more accessible locations (Context Menu and RexTools3 Sidebar)
