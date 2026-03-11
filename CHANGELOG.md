# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2] - 2026-03-11

### Added
- **Weight Tools: Init Weight Paint**:
  - New operator that correctly initializes a weight painting session.
  - Automatically finds the armature modifier on a selected mesh, OR finds bound meshes if an armature is selected in Pose Mode.
  - Correctly manages selection (Armature + Mesh) and enters Weight Paint mode.
  - This prevents the common issue of entering weight paint mode without the rig being correctly selected for bone painting.
  - Available in both "Weight Tools" (Weight Paint mode) and "Pose Tools" (Pose mode).

## [0.2.1] - 2026-03-09

### Added
- **Hierarchical Export Overrides**:
  - Implemented a "Local > Parent > Global" settings resolution system for collections.
  - Sub-collections now automatically inherit settings (path, format, etc.) from their parent collections unless they have their own overrides enabled.
  - New "RexTools Global Export" panel in Scene Properties for central management of global defaults.
- **Unified Export Preview**:
  - Combined "Export Targets" and "Overrides" into a single hierarchical preview section.
  - Export items are now grouped by their effective settings source (specific collection override or global).
  - Parent groups in the preview list are now collapsible for better organization in complex scenes.
  - Clicking any item in the preview automatically navigates to and activates its configuration in the Properties editor.

### Changed
- **UI Refactoring**:
  - Completely reorganized the Export Manager panel to prioritize "Batch Export" and a clean "Export Preview" workflow.
  - Rebuilt the Top Bar Export popup to match the sidebar's naming, structure, and hierarchical logic.
  - Simplified the override list by removing redundant path fields; all configuration is now handled in the dedicated Properties tabs.
- **Consolidated Overrides**:
  - Removed object-level path overrides to focus on a collection-centric workflow.
  - Expanded collection overrides to include all global and additional settings (Format, Preset, Reset Transform, etc.).

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
