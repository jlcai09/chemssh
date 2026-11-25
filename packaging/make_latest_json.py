#!/usr/bin/env python3
"""Write latest.json for a ChemSSH release (consumed by chemssh-launcher's one-click installer).

Usage: make_latest_json.py <version> <output-dir>

The manifest lists the release archives with their sha256 and a ``deps_fingerprint``. The
fingerprint covers everything that decides whether the virtualenv must be rebuilt
(dependencies, python requirement, entry points, legacy-Linux constraints). Two releases with the
same fingerprint can be updated by replacing the application files only.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Error: Python 3.11+ (built-in tomllib) or 'tomli' on Python 3.10 is required to write latest.json"
        ) from exc

ROOT = Path(__file__).resolve().parent.parent


def deps_fingerprint(root: Path = ROOT) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")).get("project", {})
    constraints = root / "constraints-oldlinux.txt"
    payload = {
        "dependencies": sorted(project.get("dependencies", [])),
        "requires-python": project.get("requires-python", ""),
        "scripts": dict(sorted(project.get("scripts", {}).items())),
        "constraints": hashlib.sha256(constraints.read_bytes()).hexdigest() if constraints.exists() else "",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    version, output_dir = argv[1], Path(argv[2])
    files = []
    for suffix in (".tar.gz", ".zip"):
        archive = output_dir / f"chemssh-{version}{suffix}"
        if not archive.exists():
            print(f"Error: missing archive {archive}", file=sys.stderr)
            return 1
        files.append({"name": archive.name, "sha256": file_sha256(archive)})
    manifest = {
        "version": version,
        "tag": f"v{version}",
        "deps_fingerprint": deps_fingerprint(),
        "files": files,
    }
    target = output_dir / "latest.json"
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
