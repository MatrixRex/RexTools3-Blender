"""Release checks for a version bump; run after editing the files, before committing and tagging.

- blender_manifest.toml `version`, __init__.py bl_info "version" and the newest
  CHANGELOG.md section (`## [x.y.z] - YYYY-MM-DD`) name the same version
- bl_info "blender" matches the manifest's blender_version_min
- that changelog section is not empty
- on branch main, and tag vX.Y.Z exists neither locally nor on origin

Prints every problem and exits 1, or exits 0 when all pass. With --notes FILE it also
writes the changelog section there, for the annotated tag's message (the GitHub
release notes).

Usage: py .agent/scripts/check_release.py [--notes FILE]
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def three_part(version):
    return ".".join((version.split(".") + ["0", "0"])[:3]) if version else None


def main():
    parser = argparse.ArgumentParser(description="Release checks for a version bump.")
    parser.add_argument("--notes", help="write this version's changelog section to this file")
    args = parser.parse_args()
    problems = []

    manifest = read("blender_manifest.toml")
    found = re.search(r'^version\s*=\s*"([^"]+)"', manifest, re.M)
    version = found.group(1) if found else None
    found = re.search(r'^blender_version_min\s*=\s*"([^"]+)"', manifest, re.M)
    blender_min = three_part(found.group(1)) if found else None

    init = read("__init__.py")

    def bl_info(key):
        m = re.search(rf'"{key}":\s*\((\d+),\s*(\d+),\s*(\d+)\)', init)
        return ".".join(m.groups()) if m else None

    changelog = read("CHANGELOG.md")
    head = re.search(r"^## \[([^\]]+)\] - \d{4}-\d{2}-\d{2}\s*$", changelog, re.M)
    section = ""
    if head:
        rest = changelog[head.end():]
        nxt = re.search(r"^## \[", rest, re.M)
        section = (rest[:nxt.start()] if nxt else rest).strip()

    if not version:
        problems.append("blender_manifest.toml has no version")
    if bl_info("version") != version:
        problems.append(f"__init__.py bl_info version is {bl_info('version')}, the manifest has {version}")
    if bl_info("blender") != blender_min:
        problems.append(f"__init__.py bl_info blender is {bl_info('blender')}, "
                        f"the manifest's blender_version_min is {blender_min}")
    if not head:
        problems.append("CHANGELOG.md has no '## [x.y.z] - YYYY-MM-DD' section")
    elif head.group(1) != version:
        problems.append(f"the newest CHANGELOG.md section is [{head.group(1)}], the manifest has {version}")
    elif not section:
        problems.append(f"CHANGELOG.md section [{version}] is empty")

    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main":
        problems.append(f"not on main (on {branch or 'unknown'})")
    tag = f"v{version}"
    if git("tag", "-l", tag).stdout.strip():
        problems.append(f"tag {tag} already exists locally")
    remote = git("ls-remote", "--exit-code", "--tags", "origin", f"refs/tags/{tag}")
    if remote.returncode == 0:
        problems.append(f"tag {tag} already exists on origin")
    elif remote.returncode != 2:
        problems.append(f"could not check origin for {tag}: {remote.stderr.strip()}")

    if problems:
        print("Release checks failed:")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)
    if args.notes:
        with open(args.notes, "w", encoding="utf-8", newline="\n") as f:
            f.write(section + "\n")
    print(f"Release checks passed for {tag}")


if __name__ == "__main__":
    main()
