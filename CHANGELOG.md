# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-09-26

### Changed

- **Modular Architecture Refactoring**:
  - Proactively decoupled monolithic operator files into dedicated core utility modules adhering to clean separation of concerns:
    - **Context Aware Selection**: Extracted pure BMesh topology traversal algorithms, loop/ring edge walkers, and bounded pathfinding to `core/bmesh_selection.py`.
    - **RExport Operators**: Extracted collection hierarchy resolution, recursive override lookups, and export grouping to `core/export_overrides.py`. Extracted texture resolution, image extraction, and file naming to `core/export_texture_utils.py`.
    - **Marmoset Bridge**: Extracted image caching, shader socket inspection, high/low poly group regex detection, and bake group population to `core/marmoset_utils.py`.
    - **Meshy 3D Operators**: Extracted GLB/FBX import/export helpers, local space alignment, and in-place mesh replacement mechanics to `core/meshy_io.py`.
  - Fixed an f-string backslash syntax incompatibility in Marmoset model import script generator for broader Python version support.

## [0.4.1] - 2026-09-23

### Added

- **Easy PBR Material Graph Converter**:
  - Implemented automatic tracing and conversion of regular (manually created or imported via FBX, OBJ, glTF) materials to RexTools3's Easy PBR graph system.
  - Recognizes standard PBR sockets: Base Color, AO, Roughness, Metallic, Normal, Alpha, Emission, and Displacement/Height.
  - Auto-detects glTF packed ORM textures (`R` -> AO, `G` -> Roughness, `B` -> Metallic) and sets up channel split nodes.
  - Automatically identifies DirectX green channel inverted normal maps (`flip_normal_g`), alpha clip thresholds, tints, and UV tiling.
  - **Strict Node Retention on Partial Conversions**: If a material contains complex or procedural networks (e.g., Noise Textures, ColorRamps, custom procedural shaders), those nodes and their socket connections are strictly retained without breaking or deleting them.
  - **Confirmation Dialog**: Added an interactive confirmation dialog for partially convertible materials detailing convertible vs. retained components before executing changes. Fully convertible materials convert cleanly without interruption.
  - **Batch Material Conversion**: Added `pbr.batch_convert_to_easy_pbr` to batch-convert all unique materials on selected mesh objects.
  - **UI Integration**: Added detection prompts and conversion operators in both the Easy PBR panel (`PBR_PT_MaterialPanel`) and Material Tools panel (`PBR_PT_BatchMaterialPanel`).

## [0.4.0] - 2026-07-16

### Added

- **Marmoset Bridge Multi-Mesh Support**:
  - Implements exporting and baking multiple high-poly and low-poly meshes under a single bake group (or multiple bake groups).
  - Automatically classifies selected meshes into high-poly and low-poly lists based on collection naming, suffix naming (regex-matching suffixes like `_low_bolts`, `_low.001`, etc.), and relative vertex counts.
  - Renames meshes adhering to Marmoset's Quick Loader variation syntax: `<asset_name>_low_<variation>` and `<asset_name>_high_<variation>` (preserving original names as variations, or assigning numbered suffixes if base name is empty/matches the asset name).
  - Aligns origin matrices for paired high-poly/low-poly meshes sharing the same variation base name.
  - Automatically matches and assigns materials across all paired high-poly/low-poly meshes.
  - Re-exports all low-poly meshes into `{asset_name}_low.fbx` and all high-poly meshes into `{asset_name}_high.fbx` in a single operation.
  - Batch assigns baked textures to all selected low-poly objects with one click.
- **Detailed Set Preview UI**:
  - Displays a list of resolved low-poly/high-poly bake sets (e.g., `Set 1: Wheels (car_low_wheels, car_high_wheels)`) instead of simple counts, showing the capitalized common name (variation/base name) of each set.
  - Displays clear error/warning labels for any unpaired low-poly or high-poly meshes in the active selection.
- **Marmoset Hot Reload (Mesh Resending)**:
  - Added a running process check in the bridge send operator. If Marmoset Toolbag is already running, it only exports the updated FBX files to the output directory and bypasses launching a new instance, allowing Marmoset's built-in file watcher to hot-reload the updated geometry immediately.

## [0.3.0] - 2026-06-18

### Added

- **Texture Oven Baking Panel**:
  - Implements an automated texture baking tool to generate Albedo, Ambient Occlusion (AO), and Normal maps.
  - Supports Target (low-poly) and Source (high-poly) mesh picker inputs.
  - Automatically splits mesh edges, performs UV unwrapping/packing, and applies displacement modifier adjustments in real-time.
  - Provides configurable resolution selectors (up to 2048x2048), AO sample count controls, and a dedicated direct image-saving workflow.
- **Quick Delete System**:
  - Fully keyboard-driven selection/deletion system operating under Mesh Edit Mode.
  - Configurable in preferences with three distinct paradigms:
    - **Nested WASD (Double-Tap)**: A two-step menu system where category selection happens first via WASD, followed by specific action execution.
    - **Keyboard Grid Layout (Direct)**: QWERTY layout grid mapping direct keys to deletion, dissolution, merge, and extras operations.
    - **Hold-and-Press Modifiers (WASD)**: Dynamic switching of WASD actions in real-time by holding Shift (for Dissolve), Alt (for Merge), and Ctrl (for Extras).
  - Features dynamic HUD drawing of keys and preview labels based on active modes and held modifier keys.
- **Curve Path Selection**:
  - Enhanced context-aware selection in Curve Edit Mode.
  - Shift + Double-clicking two selected control points automatically computes and selects the path of points between them.
  - Supports cyclic wrapping on closed-loop splines, automatically selecting the shorter path around the loop.

### Fixed

- **Modal Overlap Protection**: Increased quick delete modal width and shortened grid labels to prevent layout overlap.
- **Reference Error in Draw Callback**: Handled potential `ReferenceError` in modal `draw_callback` during teardown/modal termination.
- **Keymap Settings Labels**: Enhanced display layout of keymap settings in preferences UI to include clear `Mesh:` or `Curve:` prefix labels.

## [0.2.5] - 2026-06-18

### Added

- **Collapsible Panel Merging**:
  - Merged the "Bone Batch Rename" panel and the "Rename Tools" panel into a single unified **Rename Tools** sidebar panel.
  - Placed both the Bone Batch Rename and Mesh High/Low Rename sections within collapsible boxes.
  - Added preference toggles to control the visibility of each sub-tool section globally.
- **Customizable Sidebar Categories**:
  - Upgraded addon preference settings to allow the user to change the sidebar tab category name for each individual panel (Common Tools, Material Tools, Quick Asset Export, Object Tools, UV Tools, Rename Tools, Edit Tools, UV Mesh Tools, Cleanup Tools, Pose Tools, Chain Constraints, Sculpt Tools, Weight Tools, Node Helper, and RExport) dynamically from the default `"RexTools3"` or `"RExport"`.
  - Panel classes are unregistered and re-registered in real-time as the tab category is modified in the preferences UI.
- **Material Tools Restructuring**:
  - Moved **Replace Materials** and **Extract Textures** out of Common Tools and into the Material Tools panel under a **Material Utilities** box.
  - Placed the **Batch Texture Assign** system inside its own dedicated box with a visibility toggle in preferences.
  - Renamed the initialization button from "Init Batch Texture Assign" to **Get Materials**.
- **Quick Asset Export**:
  - Mark selected objects in the active file as assets and write them straight into an asset library without leaving or cluttering the workspace.
  - Dynamically retrieves configured asset libraries from Blender preferences.
  - Dynamically reads and lists existing catalogs from `blender_assets.cats.txt` in a dropdown menu.
  - Supports custom library folders, custom catalog creation, separate or combined file exports, and automatic clean-up of asset markings in the working file.
  - Integrated into the Object and Object Context menus, and as a dedicated panel in the RexTools3 sidebar.
  - Displays progress and success overlays using the custom viewport notification system.
- **Rex Shading & View Pie Menus**:
  - **Rex Shading Pie (`Z` key)**: Created custom pie menu `VIEW3D_MT_rex_shading_pie` to replace Blender's native shading pie. Includes Solid, Wireframe, Material Preview, Rendered, Toggle X-Ray, Toggle Overlays, and a permanent **Wireframe Overlay** toggle in the South-East slot. In Edit Mode, dynamically shows a **Retopo** toggle. In Weight Paint Mode, dynamically shows a **Contours** toggle.
  - **Rex View Pie (`W` key)**: Created custom pie menu `VIEW3D_MT_rex_view_pie` to replace default selection tool cycle. Contains Left, Right, Bottom, Top, Front, and Back viewpoint camera control buttons, plus **Orbit 90° Left** and **Orbit 90° Right** buttons placed in the middle row (West/East slots).
  - **Keymap Registration**: Correctly registers both overrides on 3D View addon keymaps and cleanly removes them on unregistration.
- **Smart Loop Selection**:
  - Implemented smart loop/ring selection for Vertex, Edge, and Face selection modes under `Shift + Double-click`.
  - **Edge Mode**: Automatically performs edge ring selection if the two selected edges are parallel, otherwise performs edge loop selection.
  - **Face Mode**: Smartly detects adjacent faces and traverses the perpendicular face loop in both directions.
  - **Vertex Mode**: Smartly detects adjacent vertices and traverses the edge loop containing their connecting edge to select a vertex loop.
  - Retains all previous selections during smart selections.
- **Easy PBR Improvements**:
  - **Set Viewport Color**: Added a new operator `pbr.set_viewport_color` that samples the material's base color (averaging base texture pixels via 16x16 grid or using default solid colors, multiplied by any active Base Color Tint) to update the material's viewport display color, metallic, and roughness settings.
  - **Open in UV/Image Editor**: Added a new operator `pbr.open_in_image_editor` that traces the node tree for a socket and displays its assigned texture in the UV/Image Editor.
  - **UV Editor Preservation**: The open operator detects and prioritizes active UV Editors (`ui_type == 'UV'`) to display images without switching their workspace sub-type.
  - **Collapsible Section Layout**: Grouped the PBR tools into three collapsible panels: "Texture Auto Loader", "Texture Utilities", and "Viewport Color" (positioned at the bottom).
  - Removed the redundant `PACKING MODE ACTIVE` alert box.

### Fixed

- **Headless / Background Startup**:
  - Wrapped GPU shader compilations in `ui/drawing.py` in safe try-except blocks to prevent import crashes when running Blender headlessly (background/no GPU context).
- **Keymap Registration Cleanup**:
  - Moved module-level keymap registration in `operators/pie_test.py` into standard `register()` and `unregister()` functions to avoid startup crashes in clean/factory environments.
- **Custom Viewport Overlay / Popup System**:
  - Aligned drawn text font size with the measured layout wrapping size, resolving right-side text overflow in `MessageBox` popups.
  - Added smart line wrapping for paragraphs/hard newlines (`\n`) and automatic wrapping at path separators/special characters (`\`, `/`, `.`, `-`, `_`) for long tokens (such as file paths).
  - Implemented automatic recovery/restart for the modal viewport event watcher when terminated by window/workspace changes, preventing click-to-close labels from getting stuck.
  - Added a persistent blend-file load handler to automatically clear stale overlays.
- **Easy PBR Save Textures Fallback**:
  - Fixed a bug where saving textures failed (or crashed Blender GUI) if the source texture file was renamed or missing from disk.
  - Implemented a robust direct saving mechanism using safe `filepath_raw` manipulation to write raw pixels from memory to the local `textures/` folder in their original file formats.
  - Ensures the saved files use the current renamed image block name (`img.name`) inside Blender.

## [0.2.4] - 2026-06-05

### Added

- **Batch Export: Copy Textures Tool**:
  - New operator `rextools3.copy_textures` that scans materials used by current export targets.
  - Automatically identifies all file-based, sequence-based, and tiled (`.udim`) textures.
  - Copies textures to a selected destination folder.
  - Supports global destination setting (`texture_copy_path`) and per-collection overrides with override toggle logic.
  - Exposes folder picker and copy buttons in the Export Manager sidebar, Scene settings properties, and Topbar quick export settings popup.

## [0.2.3] - 2026-06-04

### Added

- **Context-Aware Selection Tool**:
  - New selection operator `rextools3.context_aware_select` bound to double-click in Mesh and Curve Edit Modes.
  - Automatically selects linked geometry in Mesh Vertex/Face selection modes, and linked spline control points in Curve Edit Mode.
  - Automatically selects edge loops in Mesh Edge selection mode.
  - Fully supports `Shift + Double-click` to extend/toggle edge loop selections.
  - Exposes tool properties in the Adjust Last Operation (Redo) panel dynamically based on the current mode:
    - Vertex/Face mode: Exposes boundary limitations (`delimit`).
    - Edge mode: Exposes ring selection toggle (`ring`).

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
