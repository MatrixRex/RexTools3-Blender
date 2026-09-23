# RexTools3

**RexTools3** is a collection of sub-tools for speeding up workflow in Blender.

## 🔧 Tools

### 📦 RExport(Batch Mesh Export)

**Location:** `Top bar` and `RExport Panel.`

- **Instant Export**: One-click batch export.
- **Quick Config**: Global export path, and collection override.
- **Export Limiter**: Limit by selection, visible or render visible.
- **Export Format**: FBX, GLTF, OBJ.
- **Export Mode**: Single object, parent hierarchy, or collection.
- **Presets**: Use export presets.
- **Options saved in file**: all options are saved with blender file. So no more guessing what export settings were used.
- **Copy Textures**: Copy all texture images used by materials on the current export targets to a selected folder. Supports global destination setting and per-collection overrides.

### 📦 Quick Blender Assets

**Location:** `RexTools3 panel > Quick Blender Assets` and `Object / Object Context menu > Save Selected as Asset`

Mark selected objects in your working file as assets and write them straight into an asset library without leaving (or cluttering) your current file.

- **Dynamic Catalog Browser**: Dynamically reads and lists all existing catalogs from `blender_assets.cats.txt` in a dropdown menu.
- **Custom Catalog Creation**: Create new catalog subfolders dynamically by specifying a custom catalog path.
- **Auto-populate Libraries**: Automatically displays all configured asset libraries from Blender File Preferences.
- **Clean Working File**: Option to automatically clear local asset markings after export to keep the scene uncluttered.
- **Background Rendering**: Waits for Blender's background engine to render thumbnails before saving, avoiding empty previews.
- **Flexible File Layout**: Export each object to its own `.blend` file or group them into a single `.blend`.
- **Viewport Notifications**: Displays progress and success overlays using RexTools' custom viewport message toast.

### 🛠️ Easy PBR

**Location:** `Material Properties > Easy PBR`

A dedicated panel for rapid PBR material setup and management.

- **Texture Auto-Loader**: Load Base Color map, then use the auto loader to load the rest of the textures based on naming conventions.
- **Packed Texture Setup**: High-density UI in file selector for mapping R, G, B, A channels to PBR slots (e.g., ORM, RA, etc.) during manual assignment.
- **Channel Mapping**: Flexible routing of texture channels (R, G, B, A, or Full) to shader inputs.
- **Invert Maps**: Toggleable inversion for Roughness, Metallic, and AO maps.
- **Debug Preview**: Real-time visual debugging of individual texture slots or mixed shader outputs.
- **Open in UV/Image Editor**: Instantly view any assigned texture slot in the UV/Image editor. Automatically detects and preserves active UV editor workspace views.
- **Set Viewport Color**: One-click button to automatically sample, calculate, and update the material's viewport color, metallic, and roughness values to match its base color and active tints.
- **Material Graph Converter**: Automatically trace and convert regular or imported materials (FBX, OBJ, glTF, manual) into Easy PBR format. Supports glTF packed ORM textures, DirectX normal map flips, and includes an interactive confirmation dialog for partial conversions while strictly retaining complex procedural nodes.
- **More Controls**: Easy access to strength, tint, and alpha clipping parameters organized in clean, collapsible panels.

### 🎨 Material Tools

**Location:** `RexTools3 panel` 

- **Material Utilities**:
  - **Extract Textures**: Pack and unpack all textures to a local `textures/` directory in one go.
  - **Replace Materials**: Batch replace materials across multiple selected objects using the active object's material slots.
- **Batch Texture Assign**:
  - Automatically match and assign PBR textures (Albedo, Normal, Roughness, Metallic, etc.) to multiple gathered materials in a target folder using naming conventions.
  - Includes settings for search directories, recursive lookup, and a list of gathered materials with their real-time pending/assignment status.

### 🎛️ Texture Oven

**Location:** `RexTools3 panel > Texture Oven` 

An automated high-to-low texture baking tool (similar to Marmoset Toolbag) to generate Albedo, Ambient Occlusion (AO), and Normal maps.

- **Mesh Selection**: Simple Target (low-poly) and Source (high-poly) mesh picker inputs.
- **Real-Time Distance Control**: Adjust the displacement modifier distance interactively using a slider in the panel to resolve baking gaps.
- **Resolution Control**: Bake textures at 256x256, 512x512, 1024x1024, or 2048x2048.
- **AO Quality**: Configurable sample counts for Ambient Occlusion baking to balance render time and grain quality.
- **Direct Output Saving**: Clean output directory settings and one-click saving to write the baked PNGs directly to disk.

### 🦫 Marmoset Bridge

**Location:** `RexTools3 panel > Marmoset Bridge`

A comprehensive bridge tool to quickly export meshes and set up baking projects in Marmoset Toolbag.

- **Bake Setup Automation**: Automatically configures the baker output path, resolution, format, and enables/disables specific maps (Albedo, Normals, Roughness, Metallic, AO) in Marmoset Toolbag.
- **Multi-Mesh Baking Support**: Supports selecting and exporting multiple high-poly and low-poly meshes under a single bake group (or multiple bake groups), automatically grouping them via Marmoset's Quick Loader using variation naming (e.g. `<asset_name>_low_<variation>` and `<asset_name>_high_<variation>`).
- **Auto-Rename & Match**: Auto rename high/low meshes and materials, ensuring proper suffix setup and matching mesh origins between low/high pairs.
- **Texture Handoff**: Auto scan high-poly materials' textures (Albedo, Normal, Roughness, Metallic) and assign them to the corresponding Marmoset materials in Toolbag.
- **Mesh Resending (Hot Reload)**: Automatically detects if Marmoset Toolbag is already running; if so, it only re-exports the FBX files and avoids launching a new instance, allowing Marmoset's built-in file watcher to hot-reload updated meshes immediately.
- **Bake Set Preview UI**: Lists resolved low-poly/high-poly bake sets with their capitalized common names in the sidebar before exporting, showing any unpaired objects.
- **Baked Textures Importer**: Automatically scans the bake directory for newly updated textures and assigns them to the corresponding low-poly materials in Blender with one click.

### 🦴 Rigging Tools

**Location:** `Pose Mode > RexTools3 panel`

- **Chain Constraints Adder**: Quickly add constraints (Copy Rotation, etc.) to bone chains with linear influence gradients (From/To) or fixed values. Also remove all constraints from selected bones.

### 🏷️ Rename Tools

**Location:** `Object Mode > RexTools3 panel` 

- **Bone Batch Rename**: Batch rename bones with Find & Replace or Prefix/Suffix support (visible only when an active Armature is selected). Automatically updates associated vertex groups.
- **Auto Rename High/Low**: Automatically detect and rename high-poly and low-poly pairs based on vertex counts, essential for substance painter or baking.

### 🖱️ Selection Tools

**Location:** `Edit Mode > 3D Viewport (Double-click Left Mouse)`

Context aware selection algo copied from: https://github.com/Stromberg90/Scripts

- **Context-Aware Selection**:
  - **Vertex & Face Mode**: Double-click selects the connected linked geometry. Exposes boundary limitation (`delimit`) options (Normal, Material, Seam, Sharp, UV) in the Adjust Last Operation (Redo) panel.
  - **Edge Mode**: Double-click selects the edge loop. Exposes the `ring` selection toggle in the Redo panel.
  - **Curve Edit Mode**: Double-click selects the connected linked control points (splines).
- **Smart Loop Selection (Shift + Double-click)**:
  - Retains any previous selection and intelligently selects a new loop/ring based on your last two selections:
    - **Edge Mode**: Automatically performs an **Edge Ring** selection if the newly double-clicked edge is parallel to the previously selected edge; otherwise, performs a standard **Edge Loop** selection.
    - **Face Mode**: If the last two selected faces are adjacent, it automatically selects the entire perpendicular **Face Loop** running through them.
    - **Vertex Mode**: If the last two selected vertices share an edge, it automatically selects the **Vertex Loop** running along that edge.
    - **Curve Edit Mode**: If two control points on a spline are selected, Shift + Double-click selects the path of points between them. For cyclic (closed-loop) curves, it automatically wraps around to select the shorter path of the loop. If fewer than two points are selected, it selects the linked control points of the newly double-clicked spline.

### ⌨️ Quick Delete System

**Location:** `Edit Mode > 3D Viewport (X key)`

A keyboard-driven deletion and utilities system inside Mesh Edit Mode that displays a clean, interactive HUD.

- **Dynamic HUD Overlay**: Renders active keys and operations directly on screen based on the current mode and active modifier keys, minimizing cognitive overhead.
- **Three Layout Paradigms**:
  - **Nested WASD (Double-Tap)**: A two-step menu system where category selection happens first via WASD, followed by specific action execution.
  - **Keyboard Grid Layout (Direct)**: QWERTY layout grid mapping direct keys (Q, W, E, R, A, S, D, F, Z, X, C, V) to immediate deletion, dissolution, merge, and extras operations.
  - **Hold-and-Press Modifiers (WASD)**: Dynamic switching of WASD actions in real-time by holding Shift (for Dissolve), Alt (for Merge), and Ctrl (for Extras).
- **Configurable Modes**: Choose the preferred mode from Addon Preferences.

### 🥧 Pie Menus

**Location:** `3D Viewport > Z or W`

- **Rex Shading Pie (`Z`)**: Acts as a drop-in replacement for Blender's native shading pie. Replicates all standard shading modes (Solid, Wireframe, Material Preview, Rendered, Toggle X-Ray, Toggle Overlays) and introduces:
  - **Retopo Toggle**: Dynamically appears in the South-West slot while in **Edit Mode**.
  - **Weight Contours Toggle**: Dynamically appears in the South-West slot while in **Weight Paint Mode**.
  - **Wireframe Overlay**: A permanent toggle in the South-East slot to overlay wires on top of solid/material preview.
- **Rex View Pie (`W`)**: A new pie menu for viewport camera navigation and orbit controls:
  - **Radial camera directions**: Switch to Left, Right, Bottom, Top, Front, and Back viewpoints.
  - **Orbit 90° Left / Right**: Rotate the viewport camera 90 degrees left or right (positioned on the middle row).

### 🛠️ Common Tools

**Location:** `RexTools3 panel`

- **Open Folder:** Open the saved blender folder.
- **Purge Orphans:** Clean all unused data from blend file.

### 🧊 Object Tools

**Location:** `Object Mode > RexTools3 panel` 

- **Apply Modifiers**: Batch apply all modifiers from selected objects. Includes a customizable **Ignore List** (defaults to Armature) in the sidebar to skip specific types.
- **Smart Join**: Combine objects while checking for UV name/count mismatches. Replaces the default `Ctrl+J` operation with a safer alternative that warns you of potential data loss during merging.

### 🖌️ Weight Tools

**Location:** `Weight Paint Mode > RexTools3 panel`

- **XRay Brush Toggle**: A one-click toggle for "X-Ray" painting. Saves your current brush settings, then disables Front Face Only, Front Face Falloff, and sets Falloff to Projected. Toggling off restores your previous settings.

### 🧹 Cleanup Tools

**Location:** ` RexTools3 panel`

* **Clean Objects:** Clear custom split normal, remove unused mats and do tris to quad in one button.
* **Clear Seams:** Clear all seams from Mesh.
* **Clean Modifiers:** Remove hidden or all modifiers.
* **Cheker Dissolve:** Easy way to decimate evenly looped cylendrical geometries.

### 📐 UV Tools

**Location:** ` RexTools3 panel`

- **Seam Tools**:

  - **Area Seam**: Mark seams around selected areas.
  - **Angle Loop Seam**: Select and mark seams along edge loops based on angle thresholds.
  - **Seam From Island/Sharp**: Generate seams from existing UV islands or sharp edges.
- **Unwrap Tools:**

  - **Live Unwrap Toggle**: Quick access to Blender's live unwrap feature.
  - **Quad Follow:** Quick button to make quad follow a 1 click thing instead of two.

### 🧪 Shader Tools

**Location:** `Shader Editor > RexTools3 panel`

- **Node Socket Inspector**: View detailed socket info (names, IDs, types) for any selected node in the Shader Editor.
- **Node Layout**: Automatically organize shader nodes into a clean, hierarchical layout. Accessible via Shader Editor context menu or the `RexTools3` sidebar.

## 📥 Installation

1. Download the latest release as a `.zip` file.
2. In Blender, go to **Edit > Preferences > Add-ons**.
3. Click **Install...** and select the downloaded `.zip` file.
4. Enable **RexTools3** from the list.

## 📋 Requirements

- Blender 4.2.0 or later.
