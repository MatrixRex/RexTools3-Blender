"""Build the installable extension zip without Blender.

Same layout as `blender --command extension build`: blender_manifest.toml at the zip
root plus every file not matched by the manifest's [build] paths_exclude_pattern
(gitignore-style: "/x" only at the top, "x/" only directories, "*" wildcards).

Usage (Python 3.11+): python .github/scripts/build_extension.py [output_dir]
Writes <output_dir>/<id>-<version>.zip (default output_dir: dist) and prints its path.
"""
import fnmatch
import os
import sys
import tomllib
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_EXCLUDE = ["__pycache__/", "/.git/", "/*.zip"]


def excluded(parts, is_dir, patterns):
    """True when the path (its parts, relative to the root) matches an exclude pattern."""
    for pattern in patterns:
        if pattern.endswith("/") and not is_dir:
            continue
        body = pattern.rstrip("/")
        segs = body.lstrip("/").split("/")
        tail = parts if "/" in body else parts[-len(segs):]  # a slash anchors it to the root
        if len(tail) == len(segs) and all(fnmatch.fnmatchcase(p, s) for p, s in zip(tail, segs)):
            return True
    return False


def main():
    out_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist"))
    with open(os.path.join(ROOT, "blender_manifest.toml"), "rb") as f:
        manifest = tomllib.load(f)
    patterns = manifest.get("build", {}).get("paths_exclude_pattern", DEFAULT_EXCLUDE)

    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, f"{manifest['id']}-{manifest['version']}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for top, dirs, files in os.walk(ROOT):
            rel = os.path.relpath(top, ROOT)
            base = [] if rel == "." else rel.split(os.sep)
            dirs[:] = sorted(d for d in dirs if os.path.join(top, d) != out_dir
                             and not excluded(base + [d], True, patterns))
            for name in sorted(files):
                if not excluded(base + [name], False, patterns):
                    zf.write(os.path.join(top, name), "/".join(base + [name]))
    print(zip_path)


if __name__ == "__main__":
    main()
