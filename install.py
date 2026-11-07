#!/usr/bin/env python3
# Copyright 2026 S. Alex Thompson
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Copy a release of the UI into a project, with a manifest its tests check (README.md#using-it-in-a-project):

    python install.py ../sitelabs-partitioned-graph/app/static/graph-ui
    python install.py --check ../sitelabs-partitioned-graph/app/static/graph-ui

The standard library only. What the target holds is replaced: it is a copy, not to be edited there.
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"


def version() -> str:
    return (ROOT / "VERSION").read_text().strip()


def hashes(directory: Path) -> dict[str, str]:
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file() and p.name != "MANIFEST.json"}


def install(target: Path) -> dict:
    if target.exists() and not (target / "MANIFEST.json").exists() and any(target.iterdir()):
        raise SystemExit(f"{target} has files and no MANIFEST.json: not replacing what this didn't install")
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(UI, target, ignore=shutil.ignore_patterns("__pycache__", "MANIFEST.json"))
    manifest = {"name": "sitelabs-graph-ui", "version": version(), "files": hashes(target)}
    (target / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def check(target: Path) -> list[str]:
    """What differs between this release and the target's copy; nothing means they are the same."""
    path = target / "MANIFEST.json"
    if not path.exists():
        return [f"{path} is missing"]
    manifest, problems = json.loads(path.read_text()), []
    if manifest["version"] != version():
        problems.append(f"the target has version {manifest['version']}, this is {version()}")
    want, have = hashes(UI), hashes(target)
    problems += [f"{name} differs" for name in sorted(set(want) | set(have)) if want.get(name) != have.get(name)]
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", type=Path)
    ap.add_argument("--check", action="store_true", help="change nothing; fail if the target isn't this release")
    a = ap.parse_args()
    if a.check:
        problems = check(a.target)
        print("\n".join(problems) or f"{a.target} is sitelabs-graph-ui {version()}")
        sys.exit(1 if problems else 0)
    print(f"{a.target}: sitelabs-graph-ui {install(a.target)['version']}")


if __name__ == "__main__":
    main()
