"""Materialize six complete, hash-bound historical fixtures without overwrites.

Run from any directory with Python 3.11+. The repository root is inferred from
this script; --root may select an independently extracted copy of the bundle.
Only the six fixed output paths below are allowed. No experiment is executed.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile


REVIEW = Path("docs/ics_circulation_v3/review_20261011")
OUTPUT = Path("outputs/experiments/ics_circulation_v3/phase4_w3_cursor_original_map_20261009")
NAMES = frozenset(f"{scene}_{kind}.json" for scene in
                  ("cross_cycle", "counterflow", "near_full")
                  for kind in ("original", "cursor"))


def digest(path: Path) -> tuple[str, int]:
    total, result = 0, hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            result.update(chunk)
    return result.hexdigest(), total


def safe_path(root: Path, relative: str) -> Path:
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or "\\" in relative or ":" in relative:
        raise ValueError(f"unsafe relative path: {relative!r}")
    path = root.joinpath(*value.parts)
    if not path.resolve().is_relative_to(root):
        raise ValueError(f"path escapes repository: {relative!r}")
    if path.is_symlink():
        raise ValueError(f"refusing symlink file: {relative!r}")
    return path


def prepare(root: Path) -> list[dict]:
    root = root.resolve(strict=True)
    fixture_dir = REVIEW / "fixtures"
    manifest_path = safe_path(root, (fixture_dir / "manifest.json").as_posix())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "ics-v3-complete-cursor-fixtures-v1":
        raise ValueError("unexpected fixture manifest schema")
    entries = manifest["fixtures"]
    expected = {(OUTPUT / name).as_posix() for name in NAMES}
    if len(entries) != 6 or {entry["original_path"] for entry in entries} != expected:
        raise ValueError("fixture manifest must contain exactly the six fixed paths")
    results = []
    for entry in entries:
        relative = entry["original_path"]
        archive_relative = (fixture_dir / (PurePosixPath(relative).name + ".gz")).as_posix()
        if entry["gzip_path"] != archive_relative:
            raise ValueError("unexpected gzip fixture path")
        archive = safe_path(root, archive_relative)
        wanted_archive = (entry["gzip_sha256"], entry["gzip_bytes"])
        wanted_original = (entry["original_sha256"], entry["original_bytes"])
        if digest(archive) != wanted_archive:
            raise ValueError(f"gzip SHA256/size mismatch: {archive_relative}")
        target = safe_path(root, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Resolve again after mkdir to reject any parent redirection.
        target = safe_path(root, relative)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix=".ics-fixture-", suffix=".tmp",
                                             dir=target.parent, delete=False) as out:
                temporary = Path(out.name)
                with gzip.open(archive, "rb") as stream:
                    size = 0
                    checksum = hashlib.sha256()
                    while chunk := stream.read(1024 * 1024):
                        size += len(chunk)
                        if size > entry["original_bytes"]:
                            raise ValueError(f"decompressed fixture exceeds bound: {relative}")
                        checksum.update(chunk)
                        out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            if (checksum.hexdigest(), size) != wanted_original:
                raise ValueError(f"decompressed SHA256/size mismatch: {relative}")
            if target.exists():
                if digest(target) != wanted_original:
                    raise ValueError(f"existing fixture differs; left untouched: {relative}")
                status = "existing_verified"
            else:
                # A same-filesystem hard link publishes complete bytes atomically
                # and, unlike replace(), cannot overwrite a concurrently made file.
                try:
                    os.link(temporary, target)
                    status = "materialized"
                except FileExistsError:
                    if digest(target) != wanted_original:
                        raise ValueError(f"concurrent differing fixture; left untouched: {relative}")
                    status = "existing_verified"
            results.append({"path": relative, "status": status,
                            "sha256": wanted_original[0], "bytes": wanted_original[1]})
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    args = parser.parse_args()
    print(json.dumps({"status": "passed", "physics_runs": 0,
                      "fixtures": prepare(args.root)}, indent=2))


if __name__ == "__main__":
    main()
