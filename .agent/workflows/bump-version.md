---
description: Release a new version end to end - bump, changelog, README, checks, commit, tag, push
---

The user asking to bump the version is the go-ahead for every step below (it replaces the
confirmation steps of update-changelog.md and update-readme.md). Only stop to ask when a
check fails in a way you can't fix, or when the changes don't make the bump level clear.

1. Make sure you are on `main` and the feature work is committed.
2. Pick the bump from the changes since the last tag (`git log <last vX.Y.Z tag>..HEAD`; the whole history if there is none):
   - **Patch (`x.y.Z+1`)**: bug fixes, refactors, small tweaks.
   - **Minor (`x.Y+1.0`)**: new features, operators, panels or options; substantial additions.
   - **Major (`X+1.0.0`)**: only when the user asks for it.
   Use the level the user names, if any. The current version is in `blender_manifest.toml`.
3. Set the new version in [__init__.py](file:///e:/Nazmul/RexToolsBlender/__init__.py) (`"version": (x, y, z)`) and [blender_manifest.toml](file:///e:/Nazmul/RexToolsBlender/blender_manifest.toml) (`version = "x.y.z"`). If the minimum Blender changed, update `blender_version_min`, `bl_info["blender"]` and README's Requirements together.
4. Add `## [x.y.z] - YYYY-MM-DD` (today) at the top of [CHANGELOG.md](file:///e:/Nazmul/RexToolsBlender/CHANGELOG.md), with `### Added` / `### Changed` / `### Fixed` entries written for users in the existing style.
5. Update [README.md](file:///e:/Nazmul/RexToolsBlender/README.md) where features or requirements changed.
6. Run the checks, fix what they report, and repeat until all pass. Keep every output outside the repo (e.g. the scratchpad):
   - `py .agent/scripts/check_release.py --notes <tmp>/notes.md`: manifest, bl_info and CHANGELOG versions agree, bl_info "blender" matches `blender_version_min`, the changelog section has content, on `main`, tag `vx.y.z` is free locally and on origin. Writes the release notes.
   - `"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --factory-startup --command extension validate .`: Blender accepts the manifest.
   - `"C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe" .github/scripts/build_extension.py <tmp>`: the zip builds (the same script GitHub runs; it needs Python 3.11+).
7. Commit, matching the history: `chore(release): bump version to x.y.z` (CHANGELOG.md, __init__.py, blender_manifest.toml), then `docs(readme): ...` if README changed.
8. Tag the last commit: `git tag -a vx.y.z --cleanup=verbatim -F <tmp>/notes.md`. The tag message becomes the GitHub release notes; `--cleanup=verbatim` keeps the `###` headings.
9. Push both: `git push origin main vx.y.z`. The tag runs [.github/workflows/release.yml](file:///e:/Nazmul/RexToolsBlender/.github/workflows/release.yml), which builds `rextools3-x.y.z.zip` and publishes the release. Never commit zips.
10. Run `py .agent/scripts/reload_addon.py`, then report the version, the tag and the release page: `https://github.com/MatrixRex/RexTools3-Blender/releases/tag/vx.y.z`.
