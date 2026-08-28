---
description: Update CHANGELOG.md and sync version numbers after user confirmation
---

1. Ensure the user has confirmed that the feature or bug fix is fully implemented and tested in Blender.
2. Ask the user for confirmation before editing `CHANGELOG.md`, proposing the appropriate version bump (Patch for fixes/tweaks, Minor for new features) and displaying current vs proposed new version numbers.
3. Once the user approves:
   - Synchronize the new version in [__init__.py](file:///e:/Nazmul/RexToolsBlender/__init__.py) (`"version": (x, y, z)`) and [blender_manifest.toml](file:///e:/Nazmul/RexToolsBlender/blender_manifest.toml) (`version = "x.y.z"`).
   - Open [CHANGELOG.md](file:///e:/Nazmul/RexToolsBlender/CHANGELOG.md) and insert a new header `## [x.y.z] - YYYY-MM-DD`.
   - Categorize entries following Keep a Changelog:
     - `### Added` for new features or capabilities.
     - `### Changed` for modifications to existing features.
     - `### Fixed` for bug fixes.
4. Present the updated changelog to the user for review.
5. Run `python .agent/scripts/reload_addon.py` from workspace root to reload the addon with the updated version metadata.
