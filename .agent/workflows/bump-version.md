---
description: Strict version bump protocol across __init__.py, blender_manifest.toml, and CHANGELOG.md
---

1. Confirm with the user that current changes are tested and ready for release.
2. Determine current version from [__init__.py](file:///e:/Nazmul/RexToolsBlender/__init__.py) and [blender_manifest.toml](file:///e:/Nazmul/RexToolsBlender/blender_manifest.toml).
3. Propose the bump:
   - **Patch (`x.y.Z+1`)**: Bug fixes, refactoring, minor optimizations.
   - **Minor (`x.Y+1.0`)**: New feature, new panel/operator, substantial addition.
   - **Major (`X+1.0.0`)**: Breaking architectural changes (explicitly user-directed).
4. Upon user approval, synchronize:
   - [__init__.py](file:///e:/Nazmul/RexToolsBlender/__init__.py) -> `"version": (x, y, z)`
   - [blender_manifest.toml](file:///e:/Nazmul/RexToolsBlender/blender_manifest.toml) -> `version = "x.y.z"`
5. Update [CHANGELOG.md](file:///e:/Nazmul/RexToolsBlender/CHANGELOG.md) with the new version section and current date (`YYYY-MM-DD`).
6. Check if [README.md](file:///e:/Nazmul/RexToolsBlender/README.md) needs corresponding updates and ask the user.
7. Run `python .agent/scripts/reload_addon.py` from workspace root to reload the addon.
